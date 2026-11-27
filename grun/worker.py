"""The generic worker: claim, machine lock, Ollama eviction, memory wait, engine, close the entry.

Adapted from gvoice@8a17618 gvoice/worker.py and gimg@HEAD gimg/worker.py. It never imports an application: the
engine, the profile loader and the order store (the record of finished attempts, invariant 9) come from outside."""
from __future__ import annotations

import errno
import fcntl
import os
import signal
import sys
import time

from . import i18n, limits, log, machine_lock, ollama, paths
from .engine import Cancelled, EngineError, EngineTimeout, Job
from .errors import GrunError
from .queue import make_error

LOCK_RETRY_S = 0.02
LOCK_PATIENCE_S = 0.3  # after this, keep trying only while nothing but probes (shared locks) hold the file
PROBE_PATIENCE_S = 5.0
RUN_SCHEMA = "grun.run/0"  # provisional (D-13)
SIGNALS = tuple(getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name))


def _ms(seconds: float) -> int:
    return int(round(seconds * 1000))


class Worker:
    def __init__(self, queue, engine, *, app: str, load_profile, order_store=None, log_path=None, lang=None,
                 memory_poll_s: float = 0.5):
        self.queue = queue
        self.engine = engine
        self.app = app
        self.load_profile = load_profile
        self.order_store = order_store
        self.log_path = log_path
        self.lang = lang
        self.memory_poll_s = memory_poll_s

    # -- output ------------------------------------------------------------------------------------------

    def _stderr(self, key: str, **params) -> None:
        try:
            print(i18n.t(key, self.lang, **params), file=sys.stderr, flush=True)
        except Exception:
            pass

    def _append(self, entry_id, record: dict) -> None:
        if self.log_path is None:
            return
        try:
            log.append(self.log_path, record)
        except Exception as exc:  # the log is best effort
            self._stderr("worker.log_failed", id=entry_id, reason=str(exc))

    def _emit(self, event: str, entry_id, **fields) -> None:
        self._append(entry_id, dict(fields, event=event, app=self.app, entry=entry_id, at=log.now()))

    # -- worker.lock -------------------------------------------------------------------------------------

    @staticmethod
    def _only_probes(path) -> bool:
        """Is the file held by shared locks only (probes)? A shared lock succeeds only if no one holds it exclusively."""
        try:
            fd = os.open(str(path), os.O_RDWR)
        except OSError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
        finally:
            os.close(fd)

    def _take_worker_lock(self) -> int:
        """Exclusive ``worker.lock``, with a short retry: readers with recovery and `worker_alive` take a shared lock
        for a moment, so a single ``LOCK_EX | LOCK_NB`` could fail against a probe and wrongly say "already running"."""
        path = paths.worker_lock_path(self.queue.data)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            raise GrunError("worker.already_running", path=str(path)) from exc
        start = time.monotonic()
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fd
                except OSError as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EACCES):
                        raise
                elapsed = time.monotonic() - start
                if elapsed >= PROBE_PATIENCE_S or (elapsed >= LOCK_PATIENCE_S and not self._only_probes(path)):
                    raise GrunError("worker.already_running", path=str(path))
                time.sleep(LOCK_RETRY_S)
        except BaseException:
            os.close(fd)
            raise

    # -- signals -----------------------------------------------------------------------------------------

    @staticmethod
    def _install_signals() -> dict:
        def handler(signum, frame):
            raise SystemExit(128 + signum)

        old = {}
        for sig in SIGNALS:
            try:
                old[sig] = signal.signal(sig, handler)
            except ValueError:  # not the main thread: the caller owns the signals
                break
        return old

    @staticmethod
    def _restore_signals(old: dict) -> None:
        for sig, previous in old.items():
            try:
                signal.signal(sig, previous)
            except (ValueError, TypeError):
                pass

    # -- the loop ----------------------------------------------------------------------------------------

    def _recover(self) -> None:
        before = {e["id"] for e in self.queue.list_entries(["running"])}
        self.queue.recover_orphans()
        for entry in self.queue.list_entries():
            if entry["id"] in before and entry["state"] != "running":
                self._emit("OrphanRecovered", entry["id"], state=entry["state"])

    def run(self, once: bool = False) -> int:
        """Treat queued entries until there are none (or one, with `once`); returns how many. Raises only
        ``worker.already_running``."""
        fd = self._take_worker_lock()
        old = self._install_signals()
        count = 0
        try:
            try:
                self._recover()
                while True:
                    if not self.run_once():
                        break
                    count += 1
                    if once:
                        break
            except Exception as exc:  # the queue itself failed: stop, the entries stay for the next worker
                self._stderr("error.worker.unexpected", message="%s: %s" % (type(exc).__name__, exc))
            return count
        finally:
            self._restore_signals(old)
            os.close(fd)

    def run_once(self) -> bool:
        """Claim and treat one entry; ``False`` if there was none (empty, paused or all held)."""
        entry = self.queue.claim()
        if entry is None:
            return False
        self._process(entry)
        return True

    # -- one entry ---------------------------------------------------------------------------------------

    def _error_for(self, exc: Exception) -> dict:
        if isinstance(exc, GrunError):
            params = dict(exc.params)
            errors = params.pop("errors", ())
            return make_error(exc.code, errors, **params)
        if isinstance(exc, EngineTimeout):
            return make_error("engine.timeout")
        if isinstance(exc, EngineError):
            if exc.code:
                return make_error(exc.code, **exc.params)
            return make_error("engine.failed", message=exc.message)
        return make_error("worker.unexpected", message="%s: %s" % (type(exc).__name__, exc))

    def _finish(self, entry_id, state, error=None, attempt_id=None):
        """Close the entry; returns ``(state, error)`` as stored, or as meant when the queue refused."""
        try:
            try:
                self.queue.finish(entry_id, state, error=error, attempt_id=attempt_id)
            except GrunError as exc:
                if state != "cancelled" or exc.code != "queue.invalid_transition":
                    raise
                # cancelled without a cancel request: that is a bug of the engine, not a cancel
                state, error = "failed", make_error("worker.unexpected", message="Cancelled: no cancel was requested")
                self.queue.finish(entry_id, state, error=error)
        except Exception as exc:
            reason = exc.code if isinstance(exc, GrunError) else "%s: %s" % (type(exc).__name__, exc)
            self._stderr("worker.finish_failed", id=entry_id, reason=reason)
        return state, error

    def _progress_callback(self, entry_id):
        def on_progress(progress):
            """Progress is informative: whatever the queue says about it is swallowed."""
            try:
                preview = progress.get("preview")
                self.queue.set_progress(entry_id, {k: v for k, v in progress.items() if k != "preview"})
            except Exception:
                preview = progress.get("preview") if isinstance(progress, dict) else None
            if preview:
                try:
                    self.queue.set_preview(entry_id, preview)
                except Exception:
                    pass

        return on_progress

    def _wait_memory(self, job, entry_id, should_cancel) -> float:
        """D-8: wait, without a time limit, until the free memory reaches the threshold. Returns seconds waited."""
        minimum = None
        threshold = getattr(self.engine, "min_free_memory_mb", None)
        if callable(threshold):
            minimum = threshold(job)
        if minimum is None:
            minimum = job.machine.get("minFreeMemoryMb")
        if not minimum:
            return 0.0
        started = None
        while True:
            free = limits.available_memory_mb()
            if free is None or free >= minimum:  # unreadable memory passes
                return 0.0 if started is None else time.monotonic() - started
            if started is None:
                started = time.monotonic()
                self._stderr("worker.waiting_memory", id=entry_id, free=free, min=minimum)
            if should_cancel():
                raise machine_lock.WaitCancelled()
            time.sleep(self.memory_poll_s)

    def _execute(self, entry, profile, timings):
        """Steps 3 to 8 (the order inside the holder, DDD §4). Returns the result."""
        entry_id = entry["id"]
        should_cancel = lambda: self.queue.is_cancel_requested(entry_id)  # noqa: E731
        job = Job(entry=dict(entry), machine=profile)
        asked = time.monotonic()

        def on_wait():
            self._emit("LockWaited", entry_id)

        with machine_lock.hold(should_cancel, on_wait, app=self.app, entry=entry_id):
            timings["lock"] = time.monotonic() - asked
            self._emit("LockAcquired", entry_id, waitedMs=_ms(timings["lock"]))
            evicted = ollama.evict(profile, should_cancel)
            if evicted:
                self._emit("OllamaEvicted", entry_id, models=evicted)
            timings["memory"] = self._wait_memory(job, entry_id, should_cancel)
            if timings["memory"]:
                self._emit("MemoryWaited", entry_id, waitedMs=_ms(timings["memory"]))
            result = self.engine.run(job, self._progress_callback(entry_id), should_cancel, machine_lock.held_fds())
        if should_cancel():
            raise Cancelled()
        return result

    def _process(self, entry: dict) -> None:
        entry_id = entry["id"]
        started = time.monotonic()
        timings = {"lock": 0.0, "memory": 0.0}
        self._emit("EntryClaimed", entry_id)
        state, error, attempt_id = "done", None, None
        try:
            profile = self.load_profile()
            attempt_id = self.order_store.attempt_for_entry(entry) if self.order_store is not None else None
            if attempt_id is None:  # invariant 9: an attempt already made is never run again
                result = self._execute(entry, profile, timings)
                if self.order_store is not None:
                    attempt_id = self.order_store.add_attempt(entry, result)
        except (Cancelled, machine_lock.WaitCancelled):
            state = "cancelled"
        except Exception as exc:  # KeyboardInterrupt and SystemExit go through
            state, error, attempt_id = "failed", self._error_for(exc), None
        state, error = self._finish(entry_id, state, error, attempt_id if state == "done" else None)
        code = error["code"] if error else None
        self._emit("EntryFinished", entry_id, state=state, errorCode=code)
        self._append(entry_id, {"schema": RUN_SCHEMA, "app": self.app, "entry": entry_id, "state": state,
                                "errorCode": code, "lockWaitMs": _ms(timings["lock"]),
                                "memoryWaitMs": _ms(timings["memory"]),
                                "runMs": _ms(time.monotonic() - started)})

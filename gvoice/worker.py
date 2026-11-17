"""The queue worker: one process at a time (``<data>/worker.lock``, non-blocking flock), one job at a time on the
machine (``<state>/gpu.lock``, `machine_lock`, D8).

Copiado de gimg@fa1076e (D7); adaptado a gvoice (D10): sin imágenes, composición ni metadatos de PNG; tres clases
de trabajo y el candado de la máquina.

Right after taking its lock the worker recovers the queue (`queue.recover_orphans`): holding the lock proves no other
worker is alive, so every ``running`` entry is dead and goes back to ``queued`` (``cancelled`` if a cancel was
requested) and its pending audio is deleted.

Per entry: claim -> wait for the machine lock (the entry shows ``running``; a cancel ends the wait) -> the job. The
lock is held for the whole job, so another generator (the image one) never runs at the same time.

* ``voice``: machine profile again (it may have changed since enqueue) -> engine ``design`` (instruction of the
  entry, the test text, the design model of the profile) -> ``orders.add_attempt``.
* ``line``: the voice print of the reference take the entry was made with, for the production model
  (`queue.production_model`; ``worker.print_missing`` with its model, voice and take if the files are not there)
  -> engine ``line`` -> ``orders.add_attempt``.
* ``prints``: for each model `orders.missing_prints` says the take lacks: engine ``voiceprint`` on the take's audio
  -> ``orders.set_prints``. A model that fails stops the job (the ones already made stay).

Audio: named after the queue entry id. The engine writes ``attempts/q<entry>/.pending.wav``; the worker
`os.replace`s it onto ``audio.wav`` and only then calls `orders.add_attempt(..., entry_id=entry)`, idempotent per
entry: a crash at any point leaves either no attempt or one with its audio, and a retry never duplicates it. The
pending file is removed on every failure or cancel; if `add_attempt` fails the moved audio is removed too.

Memory (D15, F2.3): with an engine that watches memory (`Engine.watches_memory`, the real one) the job, once it
holds the machine lock, waits until ``MemAvailable`` reaches ``minFreeMemoryMb`` (`_wait_for_memory`: it never fails
for that; a cancel ends the wait; the reason is printed once to stderr). The lock is held first on purpose: the other
generator (images) cannot start and eat the memory between the check and the start, and what the waiting job
reserves is only the lock, not memory. During the run the engine's watchdog aborts below ``watchMemoryMb``
(``engine.low_memory``). On start the worker also deletes the ``.qwentts-*`` folders a killed run left
(`clean_workdirs`).

Errors: the entry ``error`` is ``{"code", "params"}`` plus ``"errors"`` (schema errors) when there are any
(`queue.make_error`; render with `queue.error_text`): a `GvoiceError` keeps its code and params, `EngineTimeout` is
``engine.timeout``, an `EngineError` with a `code` keeps it, any other is ``engine.failed`` with ``{"message"}``,
anything else ``worker.unexpected``. Log (D16): one line for every operation that fails or succeeds (a ``prints`` job
writes one per model); a cancel writes none. Once the result exists nothing can fail the entry: the success log line
and `queue.finish` are best effort. No `finish` error ever stops `run()`."""
from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import signal
import sys
import threading
import time

from . import engine as engine_mod
from . import i18n, limits, log, machine_lock, orders, paths, queue, speech_locale
from .errors import GvoiceError

MEMORY_POLL_S = 0.5  # how often a job waiting for memory looks again
LOCK_RETRY_S = 0.3  # how long `_single_worker` keeps trying the lock before it says another worker is alive


def lock_path():
    return queue.worker_lock_path()


@contextlib.contextmanager
def _single_worker():
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        # a momentary holder (`queue._no_worker` probing the lock) must not make a fresh worker give up
        deadline = time.monotonic() + LOCK_RETRY_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise GvoiceError("worker.already_running", path=str(path))
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)


def _unlink(path) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def _error_for(exc: BaseException) -> dict:
    if isinstance(exc, GvoiceError):
        return queue.make_error(exc.code, exc.errors, **exc.params)
    if isinstance(exc, engine_mod.EngineTimeout):
        return queue.make_error("engine.timeout")
    if isinstance(exc, engine_mod.EngineError) and exc.code:
        return queue.make_error(exc.code, **exc.params)
    if isinstance(exc, engine_mod.EngineError):
        return queue.make_error("engine.failed", message=exc.message)
    return queue.make_error("worker.unexpected", message="%s: %s" % (type(exc).__name__, exc))


_OPERATION = {"voice": log.OP_DESIGN, "line": log.OP_LINE, "prints": log.OP_PRINT}


def _log_line(entry: dict, machine: dict, provider: str, result=None, error=None, stats=None, **spec) -> None:
    """Append the D16 line of one operation (the `spec` fields: ``model``, ``text``...); never raises."""
    try:
        spec.setdefault("seed", entry.get("seed"))
        spec.setdefault("text", entry.get("text"))
        record = log.record_for(entry["key"], entry["kind"], spec, machine, provider, result=result, error=error,
                                operation=_OPERATION[entry["kind"]], stats=stats)
        log.append(entry["project"], record)
    except Exception:  # the log must never hide the real failure
        pass


def _finish(entry_id, state, lang=None, **kw) -> None:
    """`queue.finish` that never raises: the entry stays ``running`` and recovery deals with it."""
    try:
        queue.finish(entry_id, state, **kw)
    except Exception as exc:
        print(i18n.t("worker.finish_failed", lang, id=entry_id, reason=exc), file=sys.stderr)


def _wait_for_memory(entry: dict, eng, machine: dict, should_cancel, lang=None) -> None:
    """Wait (polling, cancelable) until free memory is at least ``minFreeMemoryMb``; engines that do not watch memory
    (the fake one) never wait. Says why it waits, once, on stderr."""
    if not getattr(eng, "watches_memory", False):
        return
    said = False
    while True:
        free = limits.available_memory_mb()
        try:
            limits.check_memory(free, machine)
            return
        except limits.LimitError as exc:
            if not said:
                said = True
                print(i18n.t("worker.waiting_memory", lang, id=entry["id"], free=exc.params["free"],
                             min=exc.params["min"]), file=sys.stderr)
        if should_cancel():
            raise machine_lock.WaitCancelled()
        time.sleep(MEMORY_POLL_S)


def clean_workdirs() -> int:
    """Delete the ``.qwentts-*`` folders under the projects' data that a killed run left; returns how many. Only
    safe with the worker lock held (no engine is alive)."""
    from . import engine_qwentts
    removed = 0
    for root, dirs, _files in os.walk(paths.data_dir() / "projects"):
        for name in list(dirs):
            if name.startswith(engine_qwentts.WORKDIR_PREFIX):
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
                dirs.remove(name)
                removed += 1
    return removed


def _model_of(machine: dict, use: str):
    """The model the profile names for `use` (``design``), checked against the profile."""
    model = (machine.get("models") or {}).get(use)
    if model is not None:
        limits.check_model(use, model, machine)
    return model


def _take(entry: dict, eng, machine: dict, state: dict, should_cancel):
    """A ``voice`` or ``line`` take, up to and including `add_attempt`; returns the attempt id."""
    entry_id, project, key = entry["id"], entry["project"], entry["key"]
    existing = orders.attempt_for_entry(project, key, entry_id)
    if existing is not None:  # a crash after add_attempt: the attempt and its audio are already there
        return existing["id"]
    tmp = orders.pending_audio_path(project, key, entry_id)
    state["tmp"] = tmp
    tmp.parent.mkdir(parents=True, exist_ok=True)
    spec = {"seed": entry["seed"], "text": entry["text"]}
    if entry["kind"] == "voice":
        model = _model_of(machine, "design")
        job = engine_mod.DesignJob(
            instruction=entry["instruction"], text=entry["text"], seed=entry["seed"], output=str(tmp), model=model,
            machine=machine, timeout_s=limits.timeout_s(machine),
            language=speech_locale.language(entry.get("locale")))
        spec["instruction"] = entry["instruction"]
        if entry.get("locale"):
            spec["locale"] = entry["locale"]
        state["spec"] = {"model": model, "text": entry["text"]}
        state["result"] = eng.design(job, should_cancel)
    else:
        model = queue.production_model(project, machine)
        limits.check_model("produce", model, machine)
        voice = entry.get("voice") or orders.get(project, key)["voice"]  # old queue files have no voice
        voice_order = orders.get(project, voice)
        reference = next((a for a in voice_order["attempts"] if a["id"] == entry["reference"]), None)
        if reference is None:
            raise GvoiceError("order.reference_unknown", reference=str(entry["reference"]), voice=voice)
        spk, rvq = orders.print_paths(project, voice, reference, model)
        if not (spk.is_file() and rvq.is_file()):
            raise GvoiceError("worker.print_missing", model=model, voice=voice, take=reference["id"])
        job = engine_mod.LineJob(
            spk=str(spk), rvq=str(rvq), text=entry["text"], seed=entry["seed"], output=str(tmp), model=model,
            machine=machine, timeout_s=limits.timeout_s(machine), reference_text=reference.get("text"),
            language=speech_locale.language(reference.get("locale")))  # the take's, not the voice's now
        if reference.get("locale"):
            spec["locale"] = reference["locale"]
        spec["voice"] = voice
        spec["reference"] = entry["reference"]
        state["spec"] = {"model": model, "text": entry["text"]}
        state["result"] = eng.line(job, should_cancel)
    if should_cancel():
        raise engine_mod.Cancelled()
    final = tmp.parent / "audio.wav"
    try:
        os.replace(tmp, final)
    except OSError as exc:
        raise GvoiceError("worker.audio_move", reason=str(exc))
    state["tmp"] = None
    state["final"] = final  # if add_attempt fails nothing refers to the audio
    spec["result"] = state["result"]
    attempt_id = orders.add_attempt(project, key, spec, entry_id=entry_id)
    state["final"] = None
    return attempt_id


def _prints(entry: dict, eng, machine: dict, state: dict, should_cancel, provider: str, lang=None):
    """The ``prints`` job: one voice print per missing model. Returns the take id."""
    project, key, take = entry["project"], entry["key"], entry["take"]
    order = orders.get(project, key)
    attempt = next((a for a in order["attempts"] if a["id"] == take), None)
    if attempt is None:
        raise GvoiceError("order.attempt_unknown", attempt=take, order=key)
    audio = orders.attempt_audio(project, key, attempt)
    if "audioMs" not in attempt or not audio.is_file():
        raise GvoiceError("worker.take_without_audio", take=take, voice=key)
    for model in orders.missing_prints(project, key, take):
        spk, rvq = orders.print_paths(project, key, attempt, model)
        job = engine_mod.PrintJob(
            reference=str(audio), text=attempt["text"], model=model, spk=str(spk), rvq=str(rvq),
            machine=machine, timeout_s=limits.timeout_s(machine))
        try:
            result = eng.voiceprint(job, should_cancel)
        except engine_mod.Cancelled:
            raise
        except Exception as exc:
            _log_line(entry, machine, provider, error=queue.error_text(_error_for(exc), "en"),
                      stats=getattr(exc, "stats", None), model=model, text=attempt["text"])
            raise
        try:
            orders.set_prints(project, key, take, model, result)
        except Exception as exc:
            _log_line(entry, machine, provider, error=queue.error_text(_error_for(exc), "en"), model=model,
                      text=attempt["text"])
            raise
        _log_line(entry, machine, provider, result=result, model=model, text=attempt["text"])
    return take


def _process(entry: dict, eng, lang=None) -> None:
    entry_id = entry["id"]
    machine = {}
    state = {"tmp": None, "final": None, "result": None, "spec": {}}

    def should_cancel():
        return queue.is_cancel_requested(entry_id)

    try:
        with machine_lock.hold(should_cancel):
            machine.update(limits.load_machine())
            orders.get(entry["project"], entry["key"])
            _wait_for_memory(entry, eng, machine, should_cancel, lang)
            if entry["kind"] == "prints":
                attempt_id = _prints(entry, eng, machine, state, should_cancel, eng.provider, lang)
            else:
                attempt_id = _take(entry, eng, machine, state, should_cancel)
    except (engine_mod.Cancelled, machine_lock.WaitCancelled):
        _finish(entry_id, "cancelled", lang)
        return
    except Exception as exc:  # a bug must not leave the entry running or kill the loop
        error = _error_for(exc)
        if entry["kind"] != "prints":  # a prints job logged its own failing operation
            _log_line(entry, machine, eng.provider, error=queue.error_text(error, "en") or error["code"],
                      stats=getattr(exc, "stats", None), **state["spec"])
        _finish(entry_id, "failed", lang, error=error)
        return
    finally:
        for leftover in (state["tmp"], state["final"]):
            if leftover is not None:
                _unlink(leftover)
        if state["tmp"] is not None:
            with contextlib.suppress(OSError):
                state["tmp"].parent.rmdir()
    # the result exists: from here nothing may fail the entry
    if entry["kind"] != "prints" and state["result"] is not None:
        try:
            log.append(entry["project"], log.record_for(
                entry["key"], entry["kind"], dict(entry, **state["spec"]), machine, eng.provider,
                result=state["result"], operation=_OPERATION[entry["kind"]]))
        except Exception as exc:
            print(i18n.t("worker.log_failed", lang, id=entry_id, reason=exc), file=sys.stderr)
    _finish(entry_id, "done", lang, attempt_id=attempt_id)


def _terminate(signum, frame):
    raise SystemExit(128 + signum)


@contextlib.contextmanager
def _exit_on_signals():
    """SIGTERM and SIGHUP end the worker through `SystemExit`, like Ctrl-C does through `KeyboardInterrupt`: the
    ``finally`` blocks run (the machine lock is closed, the pending audio deleted). The entry in progress stays
    ``running`` and `queue.recover_orphans` requeues it on the next run. Only in the main thread; the old handlers
    come back on exit."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {}
    try:
        for name in ("SIGTERM", "SIGHUP"):
            if hasattr(signal, name):
                num = getattr(signal, name)
                previous[num] = signal.signal(num, _terminate)
        yield
    finally:
        for num, handler in previous.items():
            signal.signal(num, handler)


def run(once: bool = False, engine=None, lang=None) -> int:
    """Process queued entries (one with `once`, else until none is left); returns how many were handled.

    `lang` is the language of the messages the worker prints. Raises ``GvoiceError("worker.already_running")`` if
    another process holds the worker lock."""
    with _single_worker(), _exit_on_signals():
        queue.recover_orphans()
        if not machine_lock.busy():  # an engine orphaned by a killed worker still holds the lock (and its folder)
            clean_workdirs()
        eng = engine or engine_mod.get_engine()
        handled = 0
        while True:
            entry = queue.claim()
            if entry is None:
                return handled
            _process(entry, eng, lang)
            handled += 1
            if once:
                return handled

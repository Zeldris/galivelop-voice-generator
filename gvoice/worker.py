"""The queue worker of gvoice: `grun.worker.Worker` plus the three kinds of job that are gvoice's (R3, D-9).

grun does the generic part: one worker per data folder (``<data>/worker.lock``), recovery of the entries a dead worker
left, signals (SIGTERM and SIGHUP end the worker through `SystemExit`), the machine lock (``<state>/gpu.lock``, D8), the
eviction of Ollama (D-7; ``engine.ollama`` and ``engine.ollamaUrl`` of the machine profile, ``GRUN_OLLAMA_URL``), the
wait for ``minFreeMemoryMb`` (D15; a cancel ends it), the cancel, and the classification of what fails into the
``error`` of the entry (`grun.worker.Worker._error_for`: a `GrunError` keeps its code and params, `EngineTimeout` is
``engine.timeout``, an `EngineError` with a ``code`` keeps it, any other is ``engine.failed``, anything else
``worker.unexpected``).

What stays here is the adapter, `VoiceRunner`, which is grun's engine (``run``) and order store
(``attempt_for_entry``, ``add_attempt``, invariant 9) at once, and `_WorkerQueue`, the queue the worker uses:

* ``voice``: the design model of the machine profile -> engine ``design`` (instruction of the entry, test text, seed).
* ``line``: the voice print of the reference take the entry was made with, for the production model
  (`queue.production_model`; ``worker.print_missing`` with its model, voice and take if the files are not there) ->
  engine ``line``.
* ``prints``: for each model `orders.missing_prints` says the take lacks: engine ``voiceprint`` on the take's audio ->
  ``orders.set_prints``. A model that fails stops the job (the ones already made stay).

Audio: named after the queue entry id. The engine writes ``attempts/q<entry>/.pending.wav``; `VoiceRunner.add_attempt`
`os.replace`s it onto ``audio.wav`` and only then calls `orders.add_attempt(..., entry_id=entry)`, idempotent per
entry: a crash at any point leaves either no attempt or one with its audio, and a retry never duplicates it (a take
already stored is found by ``attempt_for_entry`` and never made twice). The pending file is removed on every failure
or cancel (`VoiceRunner.run` and `_WorkerQueue.finish`; after a kill, `queue.clean_pending` at the next recovery);
if `add_attempt` fails the moved audio is removed too. On start the worker also deletes the ``.qwentts-*`` folders a
killed run left (`clean_workdirs`, only with no holder of the machine lock).

Memory (D15, F2.3): only an engine that watches memory (`Engine.watches_memory`, the real one) makes the job wait for
``minFreeMemoryMb`` (`VoiceRunner.min_free_memory_mb`); the fake one never waits. During the run the engine's watchdog
aborts below ``watchMemoryMb`` (``engine.low_memory``).

Log (D16, `log`): one line for every operation that fails or succeeds (a ``prints`` job writes one per model); a
cancel writes none. It is written by `_WorkerQueue.finish` just before the entry is closed (best effort: it never
fails the entry; ``worker.log_failed`` on stderr) and, for ``prints``, per model by the runner. The entry ``error`` is
the one grun makes, plus ``"errors"`` (schema errors) when a `GvoiceError` carries them (`_for_grun`)."""
from __future__ import annotations

import contextlib
import functools
import os
import shutil
import sys

from grun import queue as grun_queue
from grun import worker as grun_worker
from grun.errors import GrunError

from . import engine as engine_mod
from . import errors, i18n, limits, log, machine_lock, orders, paths, queue, speech_locale
from .errors import GvoiceError

MEMORY_POLL_S = 0.5  # how often a job waiting for memory looks again


def lock_path():
    return queue.worker_lock_path()


def _unlink(path) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def _as_grun(exc: BaseException) -> BaseException:
    """A `GvoiceError` that carries schema errors as a `GrunError` whose ``errors`` param the worker stores in the entry
    (`grun.worker.Worker._error_for`); any other error as it is."""
    if isinstance(exc, GvoiceError) and exc.errors:
        return GrunError(exc.code, errors=exc.errors, **exc.params)
    return exc


def _for_grun(fn):
    """Make what `fn` raises what grun classifies (`_as_grun`)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except GvoiceError as exc:
            converted = _as_grun(exc)
            if converted is exc:
                raise
            raise converted from exc
    return wrapper


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


class VoiceRunner:
    """grun's engine and order store for gvoice (see the module docstring). One per `run`; it keeps what the entry in
    progress needs for its log line (``ctx``: spec, result, stats), that `_WorkerQueue.finish` reads."""

    def __init__(self, engine: engine_mod.Engine, lang=None):
        self.engine = engine
        self.lang = lang
        self.machine = {}
        self.ctx = None

    # -- the profile ---------------------------------------------------------------------------------------

    @_for_grun
    def load_profile(self) -> dict:
        """The machine profile as it is now (it may have changed since enqueue)."""
        self.ctx = None
        self.machine = {}
        self.machine = limits.load_machine()
        return self.machine

    def min_free_memory_mb(self, job):
        """What the worker waits for before the run: ``minFreeMemoryMb`` with an engine that watches memory, else 0."""
        if not getattr(self.engine, "watches_memory", False):
            return 0
        return job.machine.get("minFreeMemoryMb") or 0

    # -- the order store (invariant 9) -------------------------------------------------------------------------

    @_for_grun
    def attempt_for_entry(self, entry: dict):
        """Start of the entry: its order must exist; the id of the take it already made (a crash after `add_attempt`),
        else ``None``. A ``prints`` job has none: its finished models are skipped by `orders.missing_prints`."""
        self.ctx = {"id": entry["id"], "spec": {}, "result": None, "take": None, "tmp": None, "stats": None}
        project, key = entry["project"], entry["key"]
        orders.get(project, key)
        if entry["kind"] == "prints":
            return None
        existing = orders.attempt_for_entry(project, key, entry["id"])
        return None if existing is None else existing["id"]

    @_for_grun
    def add_attempt(self, entry: dict, result):
        """The result exists: store the take (``voice``, ``line``) and return its id; for ``prints``, the take."""
        if entry["kind"] == "prints":
            return entry["take"]
        tmp = self.ctx["tmp"]
        final = tmp.parent / "audio.wav"
        try:
            os.replace(tmp, final)
        except OSError as exc:
            raise GvoiceError("worker.audio_move", reason=str(exc))
        try:
            return orders.add_attempt(entry["project"], entry["key"], self.ctx["take"], entry_id=entry["id"])
        except BaseException:  # nothing refers to the audio
            _unlink(final)
            raise

    # -- the engine ----------------------------------------------------------------------------------------------

    @_for_grun
    def run(self, job, on_progress, should_cancel, pass_fds):
        """The job of the entry; the engine itself keeps the machine lock open in its child (`machine_lock.held_fds`)."""
        entry, machine, ctx = job.entry, job.machine, self.ctx
        try:
            if entry["kind"] == "prints":
                return self._prints(entry, machine, should_cancel)
            return self._take(entry, machine, should_cancel)
        except BaseException as exc:
            ctx["stats"] = getattr(exc, "stats", None)
            if ctx["tmp"] is not None:  # nothing was moved yet: the pending audio goes
                _unlink(ctx["tmp"])
                with contextlib.suppress(OSError):
                    ctx["tmp"].parent.rmdir()
            raise

    def _take(self, entry: dict, machine: dict, should_cancel):
        """A ``voice`` or ``line`` take up to the pending audio; returns the engine's result."""
        ctx = self.ctx
        project, key = entry["project"], entry["key"]
        tmp = orders.pending_audio_path(project, key, entry["id"])
        ctx["tmp"] = tmp
        tmp.parent.mkdir(parents=True, exist_ok=True)
        spec = {"seed": entry["seed"], "text": entry["text"]}
        if entry["kind"] == "voice":
            model = _model_of(machine, "design")
            job = engine_mod.DesignJob(
                instruction=entry["instruction"], text=entry["text"], seed=entry["seed"], output=str(tmp),
                model=model, machine=machine, timeout_s=limits.timeout_s(machine),
                language=speech_locale.language(entry.get("locale")))
            spec["instruction"] = entry["instruction"]
            if entry.get("locale"):
                spec["locale"] = entry["locale"]
            ctx["spec"] = {"model": model, "text": entry["text"]}
            result = self.engine.design(job, should_cancel)
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
            ctx["spec"] = {"model": model, "text": entry["text"]}
            result = self.engine.line(job, should_cancel)
        ctx["result"] = result
        ctx["take"] = dict(spec, result=result)
        return result

    def _prints(self, entry: dict, machine: dict, should_cancel):
        """The ``prints`` job: one voice print per missing model. Returns the take id."""
        project, key, take = entry["project"], entry["key"], entry["take"]
        order = orders.get(project, key)
        attempt = next((a for a in order["attempts"] if a["id"] == take), None)
        if attempt is None:
            raise GvoiceError("order.attempt_unknown", attempt=take, order=key)
        audio = orders.attempt_audio(project, key, attempt)
        if "audioMs" not in attempt or not audio.is_file():
            raise GvoiceError("worker.take_without_audio", take=take, voice=key)
        provider = self.engine.provider
        for model in orders.missing_prints(project, key, take):
            spk, rvq = orders.print_paths(project, key, attempt, model)
            job = engine_mod.PrintJob(
                reference=str(audio), text=attempt["text"], model=model, spk=str(spk), rvq=str(rvq),
                machine=machine, timeout_s=limits.timeout_s(machine))
            try:
                result = self.engine.voiceprint(job, should_cancel)
            except engine_mod.Cancelled:
                raise
            except Exception as exc:
                _log_line(entry, machine, provider, error=queue.error_text(_error_of(exc), "en"),
                          stats=getattr(exc, "stats", None), model=model, text=attempt["text"])
                raise
            try:
                orders.set_prints(project, key, take, model, result)
            except Exception as exc:
                _log_line(entry, machine, provider, error=queue.error_text(_error_of(exc), "en"), model=model,
                          text=attempt["text"])
                raise
            _log_line(entry, machine, provider, result=result, model=model, text=attempt["text"])
        return take

    # -- the log ---------------------------------------------------------------------------------------------------

    def closing(self, q, entry_id, state: str, error) -> None:
        """Called by `_WorkerQueue.finish` before the entry is closed: the pending audio of a failed or cancelled
        entry goes, and the D16 line of a ``voice`` or ``line`` is written (``failed`` or ``done``; ``prints`` wrote
        its own). Never raises."""
        try:
            entry = q.get(entry_id)
        except Exception:
            return
        if state != "done":
            with contextlib.suppress(Exception):
                queue.clean_pending(entry)
        if entry["kind"] == "prints" or state == "cancelled":
            return
        ctx = self.ctx if self.ctx and self.ctx["id"] == entry_id else {"spec": {}, "result": None, "stats": None}
        provider = self.engine.provider
        if state == "failed":
            _log_line(entry, self.machine, provider, error=queue.error_text(error, "en") or (error or {}).get("code"),
                      stats=ctx["stats"], **ctx["spec"])
        elif ctx["result"] is not None:  # a take found already stored has no result: nothing to log
            try:
                log.append(entry["project"], log.record_for(
                    entry["key"], entry["kind"], dict(entry, **ctx["spec"]), self.machine, provider,
                    result=ctx["result"], operation=_OPERATION[entry["kind"]]))
            except Exception as exc:
                print(i18n.t("worker.log_failed", self.lang, id=entry_id, reason=exc), file=sys.stderr)


_CLASSIFIER = grun_worker.Worker(None, None, app="gvoice", load_profile=None)


def _error_of(exc: BaseException) -> dict:
    """The ``error`` of an entry for `exc`, as the worker stores it (for the log line of a failed print)."""
    return _CLASSIFIER._error_for(_as_grun(exc))


class _WorkerQueue(grun_queue.Queue):
    """The queue of the worker: its recovery also deletes the workdirs of a killed engine, and closing an entry writes
    its D16 log line (`VoiceRunner.closing`)."""

    runner = None

    def recover_orphans(self) -> None:
        super().recover_orphans()
        if not machine_lock.busy():  # an engine orphaned by a killed worker still holds the lock (and its folder)
            clean_workdirs()

    def finish(self, entry_id, state, error=None, attempt_id=None):
        if self.runner is not None:
            self.runner.closing(self, entry_id, state, error)
        return super().finish(entry_id, state, error=error, attempt_id=attempt_id)


def run(once: bool = False, engine=None, lang=None) -> int:
    """Process queued entries (one with `once`, else until none is left); returns how many were handled.

    `lang` is the language of the messages the worker prints. Raises ``GvoiceError("worker.already_running")`` if
    another process holds the worker lock."""
    runner = VoiceRunner(engine or engine_mod.get_engine(), lang)
    work_queue = queue._queue(_WorkerQueue)
    work_queue.runner = runner
    worker = grun_worker.Worker(work_queue, runner, app="gvoice", load_profile=runner.load_profile, order_store=runner,
                                lang=lang, memory_poll_s=MEMORY_POLL_S)
    try:
        work_queue.list_entries()  # grun's `Worker.run` swallows a failing queue (`queue.corrupt`): fail here instead
        return worker.run(once)
    except GrunError as exc:
        raise errors.from_grun(exc) from None

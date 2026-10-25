"""The queue worker: one process at a time (``<data>/worker.lock``, non-blocking flock).

Copiado de gimg@0d02f51 (D7); cambia: GVOICE_*, dos tipos de entrada (``attempt``: design / speak; ``print``:
extract_print) en vez de ``generate``, audio ``.wav``, el candado de la máquina (`machinelock.hold`, D8) alrededor
de la llamada al motor y nada más, y la comprobación de que el pedido y la voz siguen en el proyecto.

Right after taking its lock the worker recovers the queue (`queue.recover_orphans`): holding the lock proves no
other worker is alive, so every ``running`` entry is dead and goes back to ``queued`` (``cancelled`` if a cancel was
requested), and the ``.pending-<entry>.wav`` files of those entries are deleted.

Per ``attempt`` entry: claim -> the order and its voice must still exist in the project -> if an attempt with
``queueEntry == entry id`` already exists (crash after `add_attempt`), skip the engine and finish ``done`` ->
machine profile (it may have changed since enqueue) -> machine lock (`machinelock.hold`; the entry stays ``running``
and cancellable while it waits) -> engine -> `orders.add_attempt` -> log line -> finish.

Audio: named after the queue entry id, unique across the generator. The engine writes
``attempts/.pending-<entry>.wav``; the worker `os.replace`s it onto ``attempts/q<entry>.wav`` and only then calls
`orders.add_attempt(..., entry_id=entry)`, idempotent per entry. A crash at any point leaves either no attempt or
one with its audio, and a retry never duplicates it. The pending file is removed on every failure or cancel; if
`add_attempt` fails the moved audio is removed too.

Once the attempt exists nothing can fail the entry: the success log line and `queue.finish` are best effort (an
entry whose `finish` failed stays ``running`` and recovery deals with it), and no failure line is written. No
`finish` error ever stops `run()`.

Errors: the entry ``error`` is ``{"code", "params"}`` plus ``"errors"`` when there are schema errors
(`queue.make_error`; render with `queue.error_text`): a `GvoiceError` keeps its code, params and schema errors,
`EngineTimeout` is ``engine.timeout``, any other `EngineError` is ``engine.failed`` with ``{"message"}``, anything
else ``worker.unexpected`` with ``{"message": "Type: msg"}``.
Log: one line for every operation that reaches the worker and fails or succeeds (``app.error`` is the English
rendering of the error); a cancel writes no line.

F1.5 SEAMS (marked below): `_fixed_print` (the print a ``line`` speaks with, and the id of the reference it comes
from), `_print_job` (what a ``print`` entry extracts from) and `_print_commit` / `_print_discard` (what is written
after / instead). They read the layout of D10 directly; F1.5 moves them into ``voices`` and keeps these signatures.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import engine as engine_mod
from . import fsutil, i18n, log, machine, machinelock, orders, paths, projects, queue
from .errors import GvoiceError


def lock_path():
    return queue.worker_lock_path()


@contextlib.contextmanager
def _single_worker():
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GvoiceError("worker.already_running", path=str(path))
        yield
    finally:
        os.close(fd)


def _unlink(path) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


# ---- F1.5 seams: the voice folder (``<data>/projects/<project>/voices/<voice>/``) ---------------------------

def _voice_dir(project: str, voice: str) -> Path:
    return paths.inside(paths.project_data_dir(project), "voices/" + voice)


def _print_files(project: str, voice: str, model: str) -> tuple:
    folder = _voice_dir(project, voice) / "prints"
    return folder / (model + ".spk"), folder / (model + ".rvq"), folder / (model + ".json")


def _fixed_print(entry: dict, voice: str, model: str) -> tuple:
    """``(reference id, .spk, .rvq)`` of the up-to-date print a line speaks with. Up to date: both files exist and
    ``print.json`` (written last) names the reference. Raises ``worker.voice_not_fixed`` otherwise."""
    spk, rvq, marker = _print_files(entry["project"], voice, model)
    try:
        reference = fsutil.read_json(marker)["reference"]
    except (OSError, ValueError, KeyError, TypeError):
        reference = None
    if type(reference) is not int or not spk.is_file() or not rvq.is_file():
        raise GvoiceError("worker.voice_not_fixed", voice=voice, model=model)
    return reference, spk, rvq


def _print_job(entry: dict, machine_profile: dict) -> engine_mod.PrintJob:
    """The job of a ``print`` entry: the voice's ``reference.wav`` and ``reference.txt`` (copied there by choosing)."""
    folder = _voice_dir(entry["project"], entry["voice"])
    wav, txt = folder / "reference.wav", folder / "reference.txt"
    for needed in (wav, txt):
        if not needed.is_file():
            raise GvoiceError("worker.reference_missing", path=str(needed))
    spk, rvq, marker = _print_files(entry["project"], entry["voice"], entry["model"])
    _unlink(marker)  # the files are about to change: the old marker would lie
    return engine_mod.PrintJob(
        reference=str(wav), reference_text=txt.read_text(encoding="utf-8"), model=entry["model"],
        spk=str(spk), rvq=str(rvq), device=machine_profile["engine"]["device"],
        timeout_s=machine_profile.get("timeoutS"))


def _print_commit(entry: dict, result) -> None:
    """After the engine: ``print.json`` is the last thing written, so "up to date" is never true half way."""
    marker = _print_files(entry["project"], entry["voice"], entry["model"])[2]
    fsutil.write_json(marker, {
        "reference": entry["reference"], "device": result.device, "engineVersion": result.engine_version,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})


def _print_discard(entry: dict) -> None:
    """The print failed or was cancelled: remove what it may have left."""
    for path in _print_files(entry["project"], entry["voice"], entry["model"]):
        _unlink(path)


# ---- worker -------------------------------------------------------------------------------------------------

def _error_for(exc: BaseException) -> dict:
    if isinstance(exc, GvoiceError):
        return queue.make_error(exc.code, exc.errors, **exc.params)
    if isinstance(exc, engine_mod.EngineTimeout):
        return queue.make_error("engine.timeout")
    if isinstance(exc, engine_mod.EngineError):
        return queue.make_error("engine.failed", message=exc.message)
    return queue.make_error("worker.unexpected", message="%s: %s" % (type(exc).__name__, exc))


def _log_record(entry: dict, profile: dict, provider: str, **kw) -> dict:
    """The log line of an entry. Before the profile is loaded (`profile` empty) the model is unknown: ``""``."""
    task = queue.task_of(entry)
    params = entry.get("params") or {}
    text = params.get("text") or (params.get("testText") if task == "design" else None)
    try:
        model = queue.model_of(entry, profile)
    except (KeyError, TypeError):
        model = ""
    key = entry["voice"] if entry["kind"] == "print" else entry["key"]
    device = (profile.get("engine") or {}).get("device")
    return log.record_for(task, key, profile, provider, model, seed=entry.get("seed"),
                          text_chars=len(text) if text else None, device=device, **kw)


def _log_failure(entry: dict, profile: dict, provider: str, error: dict) -> None:
    try:
        text = queue.error_text(error, "en") or error["code"]
        log.append(entry["project"], _log_record(entry, profile, provider, error=text))
    except Exception:  # the log must never hide the real failure
        pass


def _finish(entry_id, state, lang=None, **kw) -> None:
    """`queue.finish` that never raises: the entry stays ``running`` and recovery deals with it."""
    try:
        queue.finish(entry_id, state, **kw)
    except Exception as exc:
        print(i18n.t("worker.finish_failed", lang, id=entry_id, reason=exc), file=sys.stderr)


def _check_exists(entry: dict) -> None:
    """The project, the order (for an attempt) and the voice must still exist: they may be gone since enqueue."""
    config = projects.get(entry["project"])["config"]
    if entry["kind"] == "attempt":
        orders.get(entry["project"], entry["type"], entry["key"])
        voice = entry["key"] if entry["type"] == "voice" else entry["params"]["voice"]
    else:
        voice = entry["voice"]
    if voice not in config["voices"]:
        raise GvoiceError("order.unknown_voice", project=entry["project"], voice=voice)


def _call_engine(call, should_cancel):
    """Run one engine operation holding the machine lock. Cancelling while waiting for it raises `Cancelled`."""
    with machinelock.hold(should_cancel):
        return call()


def _generate(entry: dict, eng, profile: dict, state: dict):
    """An ``attempt`` entry up to and including `add_attempt`; returns the attempt id. `state["tmp"]`/`["final"]`
    are the files to clean up if it raises."""
    entry_id, project, type_, key = entry["id"], entry["project"], entry["type"], entry["key"]
    _check_exists(entry)
    existing = orders.attempt_for_entry(project, type_, key, entry_id)
    if existing is not None:  # a crash after add_attempt: the attempt and its audio are already there
        return existing["id"]
    profile.update(machine.load_machine())
    device, timeout = profile["engine"]["device"], profile.get("timeoutS")
    params, seed = entry["params"], entry["seed"]
    tmp = orders.pending_audio_path(project, type_, key, entry_id)
    state["tmp"] = tmp
    cancelled = lambda: queue.is_cancel_requested(entry_id)  # noqa: E731
    spec = {"seed": seed, "device": device, "engine": eng.provider}
    if type_ == "voice":
        spec.update(instruct=params["instruct"], testText=params["testText"], model=profile["models"]["design"])
        job = engine_mod.DesignJob(instruct=params["instruct"], text=params["testText"], seed=seed,
                                   model=spec["model"], output=str(tmp), device=device, timeout_s=timeout)
        call = lambda: eng.design(job, cancelled)  # noqa: E731
    else:
        reference, spk, rvq = _fixed_print(entry, params["voice"], params["model"])
        spec.update(text=params["text"], model=params["model"], voiceReference=reference)
        job = engine_mod.SpeakJob(text=params["text"], seed=seed, model=params["model"], spk=str(spk),
                                  rvq=str(rvq), output=str(tmp), device=device, timeout_s=timeout)
        call = lambda: eng.speak(job, cancelled)  # noqa: E731
    state["result"] = _call_engine(call, cancelled)
    if cancelled():
        raise engine_mod.Cancelled()
    final = tmp.parent / ("q%d.wav" % entry_id)
    try:
        os.replace(tmp, final)
    except OSError as exc:
        raise GvoiceError("worker.audio_move", reason=str(exc))
    state["tmp"] = None
    state["final"] = final
    spec["engineVersion"] = state["result"].engine_version
    spec["device"] = state["result"].device or device
    attempt_id = orders.add_attempt(project, type_, key, spec, entry_id=entry_id)
    state["final"] = None
    return attempt_id


def _generate_print(entry: dict, eng, profile: dict, state: dict):
    """A ``print`` entry: extract the prints; ``None`` is the attempt id. On any failure the files are discarded."""
    _check_exists(entry)
    profile.update(machine.load_machine())
    cancelled = lambda: queue.is_cancel_requested(entry["id"])  # noqa: E731
    job = _print_job(entry, profile)
    state["discard"] = True  # from here the voice's files may change
    state["result"] = _call_engine(lambda: eng.extract_print(job, cancelled), cancelled)
    if cancelled():
        raise engine_mod.Cancelled()
    _print_commit(entry, state["result"])
    state["discard"] = False
    return None


def _process(entry: dict, eng, lang=None) -> None:
    entry_id = entry["id"]
    profile = {}
    state = {"tmp": None, "final": None, "result": None, "discard": False}
    try:
        if entry["kind"] == "attempt":
            attempt_id = _generate(entry, eng, profile, state)
        else:
            attempt_id = _generate_print(entry, eng, profile, state)
    except engine_mod.Cancelled:
        _finish(entry_id, "cancelled", lang)
        return
    except Exception as exc:  # a bug must not leave the entry running or kill the loop
        error = _error_for(exc)
        _log_failure(entry, profile, eng.provider, error)
        _finish(entry_id, "failed", lang, error=error)
        return
    finally:
        for leftover in (state["tmp"], state["final"]):
            if leftover is not None:
                _unlink(leftover)
        if state["discard"]:
            with contextlib.suppress(Exception):
                _print_discard(entry)
    # the work is stored: from here nothing may fail the entry
    if state["result"] is not None:
        try:
            log.append(entry["project"], _log_record(entry, profile, eng.provider, result=state["result"]))
        except Exception as exc:
            print(i18n.t("worker.log_failed", lang, id=entry_id, reason=exc), file=sys.stderr)
    _finish(entry_id, "done", lang, attempt_id=attempt_id)


def run(once: bool = False, engine=None, lang=None) -> int:
    """Process queued entries (one with `once`, else until none is left); returns how many were handled.

    `lang` is the language of the messages the worker prints (the CLI passes its ``--lang``).
    Raises ``GvoiceError("worker.already_running")`` if another process holds the worker lock."""
    with _single_worker():
        queue.recover_orphans()
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

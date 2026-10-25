"""Persistent job queue (D10): one for the whole generator, ``<data>/queue.json``.

Copiado de gimg@0d02f51 (D7); cambia: GVOICE_*, GvoiceError, la entrada lleva ``kind`` (``attempt`` o ``print``) en
vez de perfil/prompt/imágenes, ``enqueue_attempts`` / ``enqueue_print``, la recuperación borra el
``.pending-<entrada>.wav`` y el estimado sale del perfil de máquina (motor, tarea, modelo y dispositivo).

``{"nextId": n, "entries": [...]}``. Entry, always: ``id``, ``kind``, ``project``, ``state``
(queued|running|done|failed|cancelled), ``pid``, ``enqueuedAt``, ``startedAt``, ``finishedAt``, ``error``,
``attemptId``, ``cancelRequested``. ``kind == "attempt"`` (one take of a ``voice`` order or one ``line``): also
``type`` (voice|line), ``key``, ``seed`` and ``params`` (voice: ``instruct``, ``testText``; line: ``text``,
``model``, ``voice``). ``kind == "print"`` (extract the prints of a voice): ``voice``, ``model`` and ``reference``
(id of the take of the voice's ``voice`` order that is the reference). Entries stay in arrival order.

``error`` of a failed entry is ``{"code": ..., "params": {...}}`` (JSON); `error_text` renders it.

Every read goes through one locked transaction (`fsutil.lock` of ``queue.json``), which also recovers
the file. Recovery is decided by the worker lock (``<data>/worker.lock``), not by pids: a process that can take
it without waiting knows no worker is alive, so every ``running`` entry is dead and goes back to ``queued``
(or to ``cancelled`` if a cancel was already requested), and the ``.pending-<entry>.wav`` files it left are
deleted. If the lock is taken, running entries are left alone. `list_entries`, `get` and `enqueue_*` try this;
the worker does it right after taking its own lock (`recover_orphans`); `claim`, `cancel`, `finish`,
`next_queued` and `is_cancel_requested` never do. ``pid`` stays in the entry as information only.
Only the last `KEEP_TERMINAL` finished entries are kept.
"""
from __future__ import annotations

import contextlib
import copy
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import engine as engine_mod
from . import fsutil, i18n, log, machine, orders, paths, projects, schema, voices
from .errors import GvoiceError

KEEP_TERMINAL = 200
TERMINAL = ("done", "failed", "cancelled")
STATES = ("queued", "running") + TERMINAL
KINDS = ("attempt", "print")


def queue_path() -> Path:
    return paths.data_dir() / "queue.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def worker_lock_path() -> Path:
    return paths.data_dir() / "worker.lock"


@contextlib.contextmanager
def _no_worker():
    """Yields True if the worker lock could be taken without waiting (no worker alive), else False.
    A second open() + flock inside the worker's own process fails too, which correctly means "alive"."""
    path = worker_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield False
        return
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            free = True
        except OSError:
            free = False
        yield free
    finally:
        os.close(fd)


def _load() -> dict:
    path = queue_path()
    try:
        data = fsutil.read_json(path, default={"nextId": 1, "entries": []})
    except (OSError, ValueError):
        raise GvoiceError("queue.corrupt", path=str(path))
    if (not isinstance(data, dict) or not isinstance(data.get("entries"), list)
            or not isinstance(data.get("nextId"), int)
            or not all(isinstance(e, dict) and e.get("state") in STATES and e.get("kind") in KINDS
                       and isinstance(e.get("id"), int)
                       for e in data["entries"])):
        raise GvoiceError("queue.corrupt", path=str(path))
    return data


def _clean_pending(entry: dict) -> None:
    if entry.get("kind") != "attempt":  # a print writes its files in one atomic step each; nothing pending
        return
    try:
        folder = orders.pending_audio_path(entry["project"], entry["type"], entry["key"], entry["id"]).parent
        names = ".pending-%d.wav" % entry["id"]
        for found in list(folder.glob(names)) + list(folder.glob("." + names + ".*.tmp")):
            with contextlib.suppress(OSError):
                found.unlink()
    except Exception:  # a bad entry must not stop the recovery
        pass


def _recover(data: dict, running_dead: bool) -> list:
    """Prune, and (`running_dead`) send every ``running`` entry back to ``queued``/``cancelled``.
    Returns the entries recovered."""
    now = _now()
    recovered = []
    for entry in data["entries"]:
        if running_dead and entry["state"] == "running":
            entry["pid"] = None
            entry["startedAt"] = None
            if entry.get("cancelRequested"):
                entry["state"] = "cancelled"
                entry["finishedAt"] = now
            else:
                entry["state"] = "queued"
            recovered.append(entry)
    done = [e for e in data["entries"] if e["state"] in TERMINAL]
    if len(done) > KEEP_TERMINAL:
        drop = {e["id"] for e in done[:len(done) - KEEP_TERMINAL]}
        data["entries"] = [e for e in data["entries"] if e["id"] not in drop]
    return recovered


def _txn(change, recover: bool = False, own_lock: bool = False):
    """Locked read, `change(data)` (edits in place, returns the result), write if anything changed.

    `recover`: try the worker lock and, if free, recover ``running`` entries first. `own_lock`: the caller
    already holds the worker lock (the worker): recover without trying. Pruning always happens."""
    path = queue_path()
    with fsutil.lock(path), contextlib.ExitStack() as stack:
        free = own_lock or (recover and stack.enter_context(_no_worker()))
        data = _load()
        before = copy.deepcopy(data)
        for entry in _recover(data, bool(free)):
            _clean_pending(entry)
        result = change(data)
        if data != before:
            fsutil.write_json(path, data)
        return copy.deepcopy(result)


def recover_orphans() -> None:
    """For the worker, which holds the worker lock: every ``running`` entry is dead; recover them all."""
    _txn(lambda data: None, own_lock=True)


def _find(data: dict, entry_id) -> dict:
    for entry in data["entries"]:
        if type(entry_id) is int and entry["id"] == entry_id:
            return entry
    raise GvoiceError("queue.unknown", id=str(entry_id))


_SPEC_FIELDS = {"voice": ("seed", "instruct", "testText"), "line": ("seed", "text", "model", "voice")}


def _add(entries: list) -> list:
    now = _now()

    def change(data):
        added = []
        for fields in entries:
            entry = {"id": data["nextId"], "project": fields.pop("project"), "state": "queued", "pid": None,
                     "enqueuedAt": now, "startedAt": None, "finishedAt": None, "error": None,
                     "attemptId": None, "cancelRequested": False}
            entry.update(fields)
            data["nextId"] += 1
            data["entries"].append(entry)
            added.append(entry)
        return added

    return _txn(change, recover=True)


def enqueue_attempts(project: str, type_: str, key: str, specs: list) -> list:
    """Queue one ``attempt`` entry per spec (from ``orders.attempt_specs``); returns the new entries.

    The order must exist and the machine profile must load; nothing is queued if a spec lacks a field. A ``line``
    is queued only if its voice has an up-to-date print for its model (`voices.fixed_print`, else
    ``line.voice_not_fixed``); the worker checks it again."""
    orders.get(project, type_, key)
    machine.load_machine()
    fields = _SPEC_FIELDS[type_]
    for spec in specs:
        missing = [f for f in fields if not isinstance(spec, dict) or f not in spec]
        if missing:
            raise GvoiceError("order.spec_invalid", missing=", ".join(missing))
    if type_ == "line":
        for spec in specs:
            voices.fixed_print(project, spec["voice"], spec["model"])
    return _add([{"kind": "attempt", "project": project, "type": type_, "key": key, "seed": spec["seed"],
                  "params": {f: copy.deepcopy(spec[f]) for f in fields if f != "seed"}} for spec in specs])


def enqueue_print(project: str, voice: str, model: str, reference: int) -> dict:
    """Queue a ``print`` entry: extract the prints of `voice` for the Base `model` from take `reference`.

    The voice must be in the project and have a ``voice`` order that has the take `reference`, and the model one
    of its print models. (`voices.choose` is the normal way to get here.)"""
    config = projects.get(project)["config"]
    if voice not in config["voices"]:
        raise GvoiceError("order.unknown_voice", project=project, voice=str(voice))
    allowed = projects.print_models(config)
    if model not in allowed:
        raise GvoiceError("order.model_not_allowed", model=str(model), allowed=", ".join(allowed))
    if type(reference) is not int or reference < 1:
        raise GvoiceError("order.spec_invalid", missing="reference")
    if not any(t["id"] == reference for t in orders.get(project, "voice", voice)["attempts"]):
        raise GvoiceError("order.attempt_unknown", attempt=reference, order=voice, type="voice")
    return _add([{"kind": "print", "project": project, "voice": voice, "model": model, "reference": reference}])[0]


def list_entries(states=None) -> list:
    """Entries in arrival order, optionally only those whose state is in `states`."""
    wanted = None if states is None else set(states)
    return _txn(lambda data: [e for e in data["entries"] if wanted is None or e["state"] in wanted],
                recover=True)


def get(entry_id) -> dict:
    return _txn(lambda data: _find(data, entry_id), recover=True)


def cancel(entry_id) -> dict:
    """queued -> cancelled; running -> ``cancelRequested: true`` (the worker stops it); finished -> error."""
    def change(data):
        entry = _find(data, entry_id)
        if entry["state"] == "queued":
            entry["state"] = "cancelled"
            entry["finishedAt"] = _now()
        elif entry["state"] == "running":
            entry["cancelRequested"] = True
        else:
            raise GvoiceError("queue.not_cancellable", id=entry["id"], state=entry["state"])
        return entry

    return _txn(change)


def next_queued():
    """The first queued entry, without taking it; ``None`` if there is none."""
    return _txn(lambda data: next((e for e in data["entries"] if e["state"] == "queued"), None))


def claim():
    """Mark the first queued entry ``running`` with this process's pid; returns it, or ``None``."""
    def change(data):
        entry = next((e for e in data["entries"] if e["state"] == "queued"), None)
        if entry is not None:
            entry["state"] = "running"
            entry["pid"] = os.getpid()
            entry["startedAt"] = _now()
        return entry

    return _txn(change)


def make_error(code: str, errors=(), **params) -> dict:
    """The ``error`` of an entry: ``{"code", "params"}`` (JSON-serialisable: values that are not become text),
    plus ``"errors": [{"path", "code", "params"}]`` when there are schema errors (`GvoiceError.errors`)."""
    error = {"code": code, "params": params}
    if errors:
        error["errors"] = [{"path": e.path, "code": e.code, "params": e.params} for e in errors]
    return json.loads(json.dumps(error, default=str))


def error_text(error, lang: str | None = None) -> str:
    """Render an entry's ``error`` (or the entry itself) with i18n; ``""`` if there is no error."""
    if isinstance(error, dict) and "state" in error:
        error = error.get("error")
    if not error:
        return ""
    if isinstance(error, str):  # older or hand-edited queue.json
        return error
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return str(error)
    code, params = error["code"], error.get("params")
    params = params if isinstance(params, dict) else {}
    try:
        text = i18n.t("error." + code, lang, **params)
    except (KeyError, IndexError, TypeError, ValueError):  # missing or oddly named placeholder
        return code
    if text == "error." + code:  # no text for this code: show the code
        text = code
    return "\n".join([text] + _schema_lines(error.get("errors"), lang))


def _schema_lines(errors, lang) -> list:
    """Texts of the stored schema errors; an old or odd shape (not a list of dicts) is skipped item by item."""
    lines = []
    for item in errors if isinstance(errors, list) else ():
        try:
            lines.append(schema.format_error(schema.ValidationError(
                str(item["path"]), str(item["code"]), dict(item["params"])), lang))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            continue
    return lines


def finish(entry_id, state: str, error=None, attempt_id=None) -> dict:
    """Close a running entry as done, failed or cancelled. `error`: ``{"code", "params"}`` (see `make_error`);
    a plain string is taken as a code without params."""
    if state not in TERMINAL:
        raise GvoiceError("queue.bad_state", state=str(state), states=", ".join(TERMINAL))
    if isinstance(error, str):
        error = make_error(error)

    def change(data):
        entry = _find(data, entry_id)
        if entry["state"] != "running":
            raise GvoiceError("queue.not_running", id=entry["id"], state=entry["state"])
        entry.update(state=state, error=error, attemptId=attempt_id, finishedAt=_now(), pid=None)
        return entry

    return _txn(change)


def is_cancel_requested(entry_id) -> bool:
    """Polled by the worker every few ms: a plain locked read, it never tries the worker lock."""
    return _txn(lambda data: bool(_find(data, entry_id).get("cancelRequested")))


def task_of(entry: dict) -> str:
    """The log task of an entry: ``design`` (voice), ``speak`` (line) or ``print``."""
    if entry["kind"] == "print":
        return "print"
    return "design" if entry["type"] == "voice" else "speak"


def model_of(entry: dict, profile: dict) -> str:
    """The engine model an entry uses: the profile's design model, or the Base model of the line / print."""
    if task_of(entry) == "design":
        return profile["models"]["design"]
    return entry["params"]["model"] if entry["kind"] == "attempt" else entry["model"]


def estimate_for(entry: dict, provider: str | None = None):
    """Median duration (ms) of similar past operations (same engine, task, model and device), or ``None``.
    `provider` defaults to the configured engine's."""
    if provider is None:
        provider = engine_mod.get_engine().provider
    profile = machine.load_machine()
    return log.estimate(entry["project"], provider, task_of(entry), model_of(entry, profile),
                        profile["engine"]["device"])

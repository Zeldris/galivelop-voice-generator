"""Persistent job queue (D10): one for the whole generator, ``<data>/queue.json``.

Copiado de gimg@fa1076e (D7); adaptado a gvoice (D10): sin imágenes, perfiles, plantillas, mover ni progreso; los
trabajos son de tres clases (``kind``).

``{"nextId": n, "entries": [...]}``; entry: ``id``, ``kind``, ``project``, ``key``, ``seed``, ``text``, ``state``
(queued|running|done|failed|cancelled), ``pid``, ``enqueuedAt``, ``startedAt``, ``finishedAt``, ``error``,
``attemptId``, ``cancelRequested`` and, by kind:

* ``voice``: a take of a voice (``instruction`` from the design sheet; the engine's ``design``; never for a voice
  from a sample, `orders.is_sample`);
* ``line``: a take of a line (``voice`` and ``reference``: the voice it was made for and the take of it it is made with; the engine's ``line`` with the
  voice print of the production model, `production_model`);
* ``prints``: the voice prints (one per model that `orders.missing_prints` says the take lacks) of take ``take`` of a
  voice; ``attemptId`` is that take when done.

One worker takes the queued entries in arrival order (lowest id first), so the ``prints`` job of a voice that was just
chosen goes before the lines asked for after it. ``error`` of a failed entry is ``{"code", "params"}`` (JSON);
`error_text` renders it.

Every read goes through one locked transaction (`fsutil.lock` of ``queue.json``), which also recovers the file.
Recovery is decided by the worker lock (``<data>/worker.lock``), not by pids: a process that can take it without
waiting knows no worker is alive, so every ``running`` entry is dead and goes back to ``queued`` (or to ``cancelled``
if a cancel was already requested), and the pending audio it left is deleted. If the lock is taken, running entries
are left alone. `list_entries`, `get` and `enqueue` try this; the worker does it right after taking its own lock
(`recover_orphans`); `claim`, `cancel`, `finish` and `is_cancel_requested` never do. Only the last `KEEP_TERMINAL`
finished entries are kept.

Service functions (the queue sits above `orders`, which never imports it): `submit_order`, `new_takes`, `choose` and
`undo` wrap the order's own, and queue the ``prints`` job when a voice take becomes the reference without all its
prints (`enqueue_prints`)."""
from __future__ import annotations

import contextlib
import copy
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import engine, fsutil, i18n, limits, orders, paths, projects, schema
from .errors import GvoiceError

KEEP_TERMINAL = 200
TERMINAL = ("done", "failed", "cancelled")
STATES = ("queued", "running") + TERMINAL
KINDS = ("voice", "line", "prints")


def queue_path() -> Path:
    return paths.data_dir() / "queue.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def worker_lock_path() -> Path:
    return paths.data_dir() / "worker.lock"


@contextlib.contextmanager
def _no_worker():
    """Yields True if the worker lock could be taken without waiting (no worker alive), else False. The probe takes
    it shared: only the worker holds it exclusively, so a probe never makes another probe see a worker that is not
    there."""
    path = worker_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield False
        return
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            free = True
        except OSError:
            free = False
        yield free
    finally:
        os.close(fd)


def worker_alive():
    """Does a worker hold ``worker.lock`` right now? ``True`` / ``False``, or ``None`` when it cannot be known.
    A pure read: it creates neither the data folder nor the lock."""
    try:
        fd = os.open(str(worker_lock_path()), os.O_RDWR)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
        return False
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
                       and isinstance(e.get("id"), int) for e in data["entries"])):
        raise GvoiceError("queue.corrupt", path=str(path))
    return data


def _clean_pending(entry: dict) -> None:
    """Delete what a dead worker left of `entry`: the pending audio of a take, the temporary files of a print."""
    try:
        if entry["kind"] in ("voice", "line"):
            pending = orders.pending_audio_path(entry["project"], entry["key"], entry["id"])
            found = list(pending.parent.glob(pending.name + "*"))
        else:
            order = orders.get(entry["project"], entry["key"])
            attempt = next(a for a in order["attempts"] if a["id"] == entry["take"])
            found = list(orders.attempt_dir(entry["project"], entry["key"], attempt).glob("prints/.*.tmp"))
        for item in found:
            with contextlib.suppress(OSError):
                item.unlink()
        if entry["kind"] in ("voice", "line"):
            with contextlib.suppress(OSError):
                pending.parent.rmdir()  # only if it is empty
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


def _first_queued(data: dict):
    return min((e for e in data["entries"] if e["state"] == "queued"), key=lambda e: e["id"], default=None)


def _find(data: dict, entry_id) -> dict:
    for entry in data["entries"]:
        if type(entry_id) is int and entry["id"] == entry_id:
            return entry
    raise GvoiceError("queue.unknown", id=str(entry_id))


def production_model(project: str, machine: dict | None = None) -> str:
    """The base model that makes the lines of `project` (D15): the first ``models.produce`` of the machine profile.
    It must be one of the project's ``printModels`` (the voice prints exist only for those): else
    ``queue.model_not_printed``; a profile that names none is ``queue.no_production_model``."""
    machine = limits.load_machine() if machine is None else machine
    produce = (machine.get("models") or {}).get("produce")
    model = produce if isinstance(produce, str) else (produce[0] if produce else None)
    if not model:
        raise GvoiceError("queue.no_production_model", profile=str(machine.get("name")))
    printed = projects.get(project)["config"]["printModels"]
    if model not in printed:
        raise GvoiceError("queue.model_not_printed", model=model, project=project, models=", ".join(printed))
    return model


def _entry(data: dict, kind: str, project: str, key: str, now: str, **fields) -> dict:
    entry = {"id": data["nextId"], "kind": kind, "project": project, "key": key, "seed": None, "text": None,
             "state": "queued", "pid": None, "enqueuedAt": now, "startedAt": None, "finishedAt": None,
             "error": None, "attemptId": None, "cancelRequested": False}
    entry.update(fields)
    data["nextId"] += 1
    data["entries"].append(entry)
    return entry


def enqueue(project: str, key: str, specs: list) -> list:
    """Queue one take per spec (from ``orders.attempt_specs``); returns the new entries.

    The order must exist, and a ``line`` needs the production model of the machine to be one of the project's
    ``printModels`` (`production_model`); nothing is queued if anything fails."""
    order = orders.get(project, key)
    kind = order["type"]
    if orders.is_sample(order):  # a voice from a sample makes no design takes
        raise GvoiceError("order.sample_no_takes", order=key)
    engine.check_configured()
    if kind == "line":
        production_model(project)
    needed = ("seed", "text", "instruction" if kind == "voice" else "reference")
    for spec in specs:
        missing = [k for k in needed if k not in spec]
        if missing:
            raise GvoiceError("order.spec_invalid", missing=", ".join(missing))
    now = _now()

    def change(data):
        return [_entry(data, kind, project, key, now, seed=spec["seed"], text=spec["text"],
                       **({"instruction": spec["instruction"],
                           **({"locale": spec["locale"]} if spec.get("locale") else {})} if kind == "voice"
                          else {"voice": spec.get("voice", order["voice"]), "reference": spec["reference"]}))
                for spec in specs]

    return _txn(change, recover=True)


def enqueue_prints(project: str, key: str, take: int):
    """Queue the ``prints`` job of take `take` of voice `key`; ``None`` when there is nothing to do: the take has all
    its prints (`orders.missing_prints` is empty) or a ``prints`` job for it is already queued or running."""
    if not orders.missing_prints(project, key, take):
        return None
    engine.check_configured()
    now = _now()

    def change(data):
        for entry in data["entries"]:
            if (entry["kind"] == "prints" and entry["state"] in ("queued", "running")
                    and (entry["project"], entry["key"], entry["take"]) == (project, key, take)):
                return None
        return _entry(data, "prints", project, key, now, take=take)

    return _txn(change, recover=True)


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


def clear(project: str | None = None) -> list:
    """Cancel every ``queued`` entry (of `project`, if given); a ``running`` one is never touched."""
    def change(data):
        now = _now()
        found = [e for e in data["entries"] if e["state"] == "queued" and (project is None or e["project"] == project)]
        for entry in found:
            entry["state"] = "cancelled"
            entry["finishedAt"] = now
        return found

    return _txn(change)


def next_queued():
    """The first queued entry, without taking it; ``None`` if there is none."""
    return _txn(_first_queued)


def claim():
    """Mark the first queued entry ``running`` with this process's pid; returns it, or ``None``."""
    def change(data):
        entry = _first_queued(data)
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
    if isinstance(error, str):  # hand-edited queue.json
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
    """Texts of the stored schema errors; an odd shape (not a list of dicts) is skipped item by item."""
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


def entry_view(entry: dict, lang: str | None = None) -> dict:
    """The JSON form of an entry for ``gvoice queue list --json``: the entry plus ``errorText``."""
    item = dict(entry)
    text = error_text(entry, lang)
    if text:
        item["errorText"] = text
    return item


def submit_order(project: str, order: dict, count: int = 1) -> tuple:
    """Store the order and queue `count` takes of it. Returns ``(record, entries)``; the record of a ``voice`` has
    the `sheet` warnings. A line whose machine cannot make it (`production_model`) is refused before it is stored."""
    engine.check_configured()
    if isinstance(order, dict):
        orders.check_count(count, order.get("seed"))
        if order.get("type") == "line":
            production_model(project)
    record = orders.submit(project, order)
    if orders.is_sample(record):  # nothing to queue: the take is the sample; choosing it queues the prints
        return record, []
    specs = orders.attempt_specs(project, record["key"], count)
    return record, enqueue(project, record["key"], specs)


def new_takes(project: str, key: str, count: int = 1, *, seed=None) -> list:
    """Queue `count` more takes of an order. Returns the new entries."""
    return enqueue(project, key, orders.attempt_specs(project, key, count, seed=seed))


def choose(project: str, key: str, attempt_id: int) -> dict:
    """`orders.choose` and, for a voice, the ``prints`` job of the take if it lacks any print. Returns
    ``{"old", "new", "entries"}`` (``entries``: the job queued, if any). Choosing the take that is already chosen
    queues the job again when prints are still missing and none is queued, so a failed enqueue can be repeated."""
    kind = orders.get(project, key)["type"]
    if kind == "voice":  # only a voice queues a job
        engine.check_configured()
    result = orders.choose(project, key, attempt_id)
    job = enqueue_prints(project, key, attempt_id) if kind == "voice" else None
    return dict(result, entries=[job] if job else [])


def undo(project: str, key: str) -> dict:
    """`orders.undo` and, for a voice that goes back to a take without all its prints, the ``prints`` job of it."""
    kind = orders.get(project, key)["type"]
    if kind == "voice":
        engine.check_configured()
    result = orders.undo(project, key)
    job = enqueue_prints(project, key, result["new"]) if kind == "voice" and result["new"] is not None else None
    return dict(result, entries=[job] if job else [])

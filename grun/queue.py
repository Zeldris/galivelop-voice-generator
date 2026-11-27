"""Persistent job queue of an application: ``<data>/queue.json`` (D-10, no migration).

Merged from gimg@HEAD gimg/queue.py and gvoice@8a17618 gvoice/queue.py (D-6).

``{"nextId": n, "entries": [...]}``. The application's own fields travel in each entry as they were given
(`Queue.enqueue` deep-copies them); `grun` adds the core ones: ``id``, ``position`` (where a ``queued`` entry stands:
the worker takes the lowest one, ties and entries without a valid one by id), ``state``
(queued|running|done|failed|cancelled), ``pid`` (information only), ``enqueuedAt``, ``startedAt``, ``finishedAt``,
``error``, ``attemptId``, ``cancelRequested``, ``orphanCount`` (how many times a dead worker left it running; an
older entry without it counts 0) and, for the entries of one `enqueue` call that form a batch, ``batch``
(``{"id": id of the first entry, "index", "size"}``) and, if `stop_batch` cancelled it, ``stoppedBy``. Unknown fields
of an older file are kept. A running entry may have ``progress`` and ``preview`` (`set_progress`, `set_preview`);
both go away when it finishes or goes back to ``queued``.

``error`` of a failed entry is ``{"code": ..., "params": {...}}`` (JSON); `error_text` renders it.

Every state change goes through `_transition` (invariant 8). Every read goes through one locked transaction
(`fsutil.lock` of ``queue.json``), which also recovers the file. Recovery is decided by the worker lock
(``<data>/worker.lock``), not by pids: a process that can take it without waiting knows no worker is alive, so
every ``running`` entry is dead: it is closed as ``cancelled`` if a cancel was requested, else ``orphanCount`` goes
up and, at 2, it fails with ``queue.orphaned`` (D-5), else it goes back to ``queued``. `list_entries`, `get` and
`enqueue` try this; the worker does it right after taking its own lock (`recover_orphans`); `claim`, `cancel`,
`finish`, `next_queued` and `is_cancel_requested` never do. Only the last ``keep_terminal`` finished entries are kept.
This module never deletes a lock file (invariant 5): `resume` removes only the pause mark.
"""
from __future__ import annotations

import contextlib
import copy
import fcntl
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from . import fsutil, i18n, paths
from .errors import GrunError

TERMINAL = ("done", "failed", "cancelled")
STATES = ("queued", "running") + TERMINAL
MOVES = ("up", "down", "top")
MAX_ORPHANINGS = 2  # a running entry left by a dead worker this many times fails instead of going back to queued
CORE_KEYS = ("id", "position", "state", "pid", "enqueuedAt", "startedAt", "finishedAt", "error", "attemptId",
             "cancelRequested", "orphanCount", "batch", "stoppedBy", "progress", "preview")

# (from, to) -> the routes (`via`) allowed to make that change of state
TRANSITIONS = {
    ("queued", "running"): ("claim",),
    ("queued", "cancelled"): ("cancel", "clear", "cancel_batch", "stop_batch"),
    ("running", "done"): ("finish",),
    ("running", "failed"): ("finish", "recovery"),
    ("running", "cancelled"): ("finish", "recovery"),  # only with cancelRequested
    ("running", "queued"): ("recovery",),
}
VIAS = tuple(sorted({v for routes in TRANSITIONS.values() for v in routes}))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _transition(entry: dict, to: str, *, via: str) -> dict:
    """The only place that changes ``entry["state"]`` (invariant 8). Anything outside `TRANSITIONS` (or a
    ``running -> cancelled`` of `finish` without ``cancelRequested``) is ``queue.invalid_transition``."""
    frm = entry["state"]
    if via not in TRANSITIONS.get((frm, to), ()) or (
            frm == "running" and to == "cancelled" and not entry.get("cancelRequested")):
        raise GrunError("queue.invalid_transition", id=entry["id"], from_state=frm, to_state=to)
    entry["state"] = to
    if to == "running":
        entry["pid"] = os.getpid()
        entry["startedAt"] = _now()
    elif to == "queued":
        entry.update(pid=None, startedAt=None)
        entry.pop("progress", None)
        entry.pop("preview", None)
    else:
        entry.update(pid=None, finishedAt=_now())
        entry.pop("progress", None)
        entry.pop("preview", None)
        if via == "recovery":
            entry["startedAt"] = None
    return entry


def _pos(entry: dict):
    """Sort key of a queued entry: its ``position`` (else its id), then its id."""
    pos = entry.get("position")
    return (pos if isinstance(pos, (int, float)) and not isinstance(pos, bool) else entry["id"], entry["id"])


def _slots(line: list) -> list:
    """The positions a reordered `line` is dealt: its own when strictly increasing, else distinct ones from the
    lowest (repeated positions would let the id tie-break undo a move)."""
    slots = [_pos(e)[0] for e in line]
    if all(a < b for a, b in zip(slots, slots[1:])):
        return slots
    start = int(math.floor(min(slots)))
    return list(range(start, start + len(slots)))


def _block_key(entry: dict):
    """Which batch block an entry belongs to; a loose entry (or an old non-dict ``batch``) is its own block."""
    batch = entry.get("batch")
    return batch.get("id", ("e", entry["id"])) if isinstance(batch, dict) else ("e", entry["id"])


def _find(data: dict, entry_id) -> dict:
    for entry in data["entries"]:
        if type(entry_id) is int and entry["id"] == entry_id:
            return entry
    raise GrunError("queue.unknown", id=str(entry_id))


def _batch(data: dict, batch_id) -> list:
    found = [e for e in data["entries"] if isinstance(e.get("batch"), dict) and type(batch_id) is int
             and e["batch"].get("id") == batch_id]
    if not found:
        raise GrunError("queue.batch_not_found", id=str(batch_id))
    return found


def _check_move(to) -> None:
    if to not in MOVES:
        raise GrunError("queue.bad_move", to=str(to), allowed=", ".join(MOVES))


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def make_error(code: str, errors=(), **params) -> dict:
    """The ``error`` of an entry: ``{"code", "params"}`` (JSON-serialisable: values that are not become text),
    plus ``"errors": [{"path", "code", "params"}]`` when there are detail errors (dicts or objects with those
    attributes)."""
    error = {"code": code, "params": params}
    if errors:
        rows = []
        for e in errors:
            if isinstance(e, dict):
                rows.append({"path": e["path"], "code": e["code"], "params": e.get("params") or {}})
            else:
                rows.append({"path": e.path, "code": e.code, "params": e.params})
        error["errors"] = rows
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
    except (KeyError, IndexError, TypeError, ValueError):  # oddly named placeholder
        return code
    if text == "error." + code:  # no text for this code: show the code
        text = code
    return "\n".join([text] + _detail_lines(error.get("errors"), lang))


def _detail_lines(errors, lang) -> list:
    """``"- <path>: <text>"`` per stored error; an odd shape (not a list of dicts) is skipped item by item."""
    lines = []
    for item in errors if isinstance(errors, list) else ():
        try:
            text = i18n.t("error." + str(item["code"]), lang, **dict(item.get("params") or {}))
            lines.append("- %s: %s" % (item["path"], text))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            continue
    return lines


class Queue:
    """The queue of one application, stored under `data` (``<data>/queue.json``).

    `held(entry)`: ``None`` or the reason an entry must not be claimed (`entry_view` shows it as ``held``).
    `clean_pending(entry)`: called for each entry recovered; its exceptions are swallowed.
    `keep_terminal`: how many finished entries are kept."""

    def __init__(self, data, *, held=None, clean_pending=None, keep_terminal: int = 200):
        self.data = Path(data)
        self._held = held
        self._clean_pending = clean_pending
        self.keep_terminal = keep_terminal
        self._path = paths.queue_path(self.data)

    # -- storage -----------------------------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            data = fsutil.read_json(self._path, default={"nextId": 1, "entries": []})
        except (OSError, ValueError):
            raise GrunError("queue.corrupt", path=str(self._path))
        if (not isinstance(data, dict) or not isinstance(data.get("entries"), list)
                or not isinstance(data.get("nextId"), int) or isinstance(data.get("nextId"), bool)
                or not all(isinstance(e, dict) and e.get("state") in STATES and type(e.get("id")) is int
                           for e in data["entries"])):
            raise GrunError("queue.corrupt", path=str(self._path))
        return data

    @contextlib.contextmanager
    def _no_worker(self):
        """Yields True if the worker lock could be taken without waiting (no worker alive), else False. The probe is
        shared, like `worker_alive`: only the worker holds it exclusively, so probes never see each other."""
        path = paths.worker_lock_path(self.data)
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

    def _recover(self, data: dict, running_dead: bool) -> list:
        """Prune, and (`running_dead`) deal with every ``running`` entry. Returns the entries recovered."""
        recovered = []
        for entry in data["entries"]:
            if not (running_dead and entry["state"] == "running"):
                continue
            count = entry.get("orphanCount")
            count = count if type(count) is int and count >= 0 else 0
            if entry.get("cancelRequested"):
                _transition(entry, "cancelled", via="recovery")
            else:
                count += 1
                entry["orphanCount"] = count
                if count >= MAX_ORPHANINGS:
                    entry["error"] = make_error("queue.orphaned", id=entry["id"], count=count)
                    _transition(entry, "failed", via="recovery")
                else:
                    _transition(entry, "queued", via="recovery")
            recovered.append(entry)
        done = [e for e in data["entries"] if e["state"] in TERMINAL]
        if len(done) > self.keep_terminal:
            drop = {e["id"] for e in done[:len(done) - self.keep_terminal]}
            data["entries"] = [e for e in data["entries"] if e["id"] not in drop]
        return recovered

    def _txn(self, change, recover: bool = False, own_lock: bool = False):
        """Locked read, `change(data)` (edits in place, returns the result), write if anything changed.

        `recover`: try the worker lock and, if free, recover ``running`` entries first. `own_lock`: the caller
        already holds the worker lock (the worker): recover without trying. Pruning always happens. A failed
        write leaves the previous file (`fsutil.write_json` is atomic)."""
        with fsutil.lock(self._path), contextlib.ExitStack() as stack:
            free = own_lock or (recover and stack.enter_context(self._no_worker()))
            data = self._load()
            before = copy.deepcopy(data)
            recovered = self._recover(data, bool(free))
            result = change(data)
            if data != before:
                fsutil.write_json(self._path, data)
                for entry in recovered:  # only once the recovery is stored
                    self._clean(entry)
            return copy.deepcopy(result)

    def _clean(self, entry: dict) -> None:
        if self._clean_pending is not None:
            try:
                self._clean_pending(copy.deepcopy(entry))
            except Exception:  # a bad entry must not stop the recovery
                pass

    def recover_orphans(self) -> None:
        """For the worker, which holds the worker lock: every ``running`` entry is dead; recover them all."""
        self._txn(lambda data: None, own_lock=True)

    def _is_held(self, entry: dict):
        return None if self._held is None else self._held(entry)

    def _first_queued(self, data: dict):
        """The first queued entry the worker may start: held ones are skipped."""
        for entry in sorted((e for e in data["entries"] if e["state"] == "queued"), key=_pos):
            if self._is_held(entry) is None:
                return entry
        return None

    # -- adding and reading --------------------------------------------------------------------------------

    def enqueue(self, items: list, *, batch=None) -> list:
        """Queue one entry per item (a dict with the application's fields, deep-copied); returns the new entries.

        A batch (``batch`` in each entry) if `batch` is True, or None and there is more than one item; ``False``
        never. An item that is not a dict or carries a key of `CORE_KEYS` is ``queue.bad_item`` and nothing is queued."""
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise GrunError("queue.bad_item", index=index, reason="is not an object")
            clash = [k for k in CORE_KEYS if k in item]
            if clash:
                raise GrunError("queue.bad_item", index=index, reason="uses the reserved field " + ", ".join(clash))
        now = _now()

        def change(data):
            added = []
            for item in items:
                entry = copy.deepcopy(item)
                entry.update({"id": data["nextId"], "position": data["nextId"], "state": "queued", "pid": None,
                              "enqueuedAt": now, "startedAt": None, "finishedAt": None, "error": None,
                              "attemptId": None, "cancelRequested": False, "orphanCount": 0})
                data["nextId"] += 1
                data["entries"].append(entry)
                added.append(entry)
            if added and (batch is True or (batch is None and len(added) > 1)):
                for index, entry in enumerate(added):
                    entry["batch"] = {"id": added[0]["id"], "index": index, "size": len(added)}
            return added

        return self._txn(change, recover=True)

    def list_entries(self, states=None) -> list:
        """Entries in arrival order, optionally only those whose state is in `states`."""
        wanted = None if states is None else set(states)
        return self._txn(lambda data: [e for e in data["entries"] if wanted is None or e["state"] in wanted],
                         recover=True)

    def get(self, entry_id) -> dict:
        return self._txn(lambda data: _find(data, entry_id), recover=True)

    def list_runnable(self) -> list:
        """The queued entries the worker could start: those `held` does not retain."""
        return [e for e in self.list_entries(["queued"]) if self._is_held(e) is None]

    def is_cancel_requested(self, entry_id) -> bool:
        """Polled by the worker often: a plain locked read, it never tries the worker lock."""
        return self._txn(lambda data: bool(_find(data, entry_id).get("cancelRequested")))

    def entry_view(self, entry: dict, lang: str | None = None) -> dict:
        """The JSON form of an entry: the entry plus ``held`` (the reason, if retained) and ``errorText``."""
        item = dict(entry)
        held = self._is_held(entry)
        if held is not None:
            item["held"] = held
        text = error_text(entry, lang)
        if text:
            item["errorText"] = text
        return item

    # -- cancelling and ordering ---------------------------------------------------------------------------

    def cancel(self, entry_id) -> dict:
        """queued -> cancelled; running -> ``cancelRequested: true`` (the worker stops it); finished -> error."""
        def change(data):
            entry = _find(data, entry_id)
            if entry["state"] == "queued":
                _transition(entry, "cancelled", via="cancel")
            elif entry["state"] == "running":
                entry["cancelRequested"] = True
            else:
                raise GrunError("queue.not_cancellable", id=entry["id"], state=entry["state"])
            return entry

        return self._txn(change)

    def cancel_batch(self, batch_id) -> list:
        """`cancel` for a whole batch; returns all of its entries. Unknown: ``queue.batch_not_found``; nothing
        queued or running: ``queue.not_cancellable``."""
        def change(data):
            mine = _batch(data, batch_id)
            if not any(e["state"] in ("queued", "running") for e in mine):
                raise GrunError("queue.not_cancellable", id=batch_id, state="finished")
            for entry in mine:
                if entry["state"] == "queued":
                    _transition(entry, "cancelled", via="cancel_batch")
                elif entry["state"] == "running":
                    entry["cancelRequested"] = True
            return mine

        return self._txn(change)

    def stop_batch(self, batch_id, by) -> list:
        """The batch is good enough: cancel its ``queued`` entries (the running and finished ones stay) and record
        ``stoppedBy`` = `by` in each. Returns the entries cancelled (none if the batch is unknown)."""
        def change(data):
            found = [e for e in data["entries"] if e["state"] == "queued" and isinstance(e.get("batch"), dict)
                     and e["batch"].get("id") == batch_id]
            for entry in found:
                _transition(entry, "cancelled", via="stop_batch")
                entry["stoppedBy"] = by
            return found

        return self._txn(change)

    def clear(self, **match) -> list:
        """Cancel every ``queued`` entry whose fields equal `match` (all of them without it); a ``running`` one
        is never touched. Returns the cancelled."""
        def change(data):
            found = [e for e in data["entries"] if e["state"] == "queued"
                     and all(k in e and e[k] == v for k, v in match.items())]
            for entry in found:
                _transition(entry, "cancelled", via="clear")
            return found

        return self._txn(change)

    def move(self, entry_id, to: str) -> dict:
        """Move a ``queued`` entry in the line the worker takes from: ``up``/``down`` one place (at the end of the
        line nothing changes), ``top`` first. Another state is ``queue.not_movable``; another `to`, ``queue.bad_move``.
        Only the positions of the queued entries are permuted among themselves, so a later enqueue still goes last."""
        _check_move(to)

        def change(data):
            entry = _find(data, entry_id)
            if entry["state"] != "queued":
                raise GrunError("queue.not_movable", id=entry["id"], state=entry["state"])
            line = sorted((e for e in data["entries"] if e["state"] == "queued"), key=_pos)
            slots = _slots(line)
            at = line.index(entry)
            if to == "top":
                line.insert(0, line.pop(at))
            elif to == "up" and at > 0:
                line[at - 1], line[at] = line[at], line[at - 1]
            elif to == "down" and at < len(line) - 1:
                line[at + 1], line[at] = line[at], line[at + 1]
            for item, slot in zip(line, slots):
                item["position"] = slot
            return entry

        return self._txn(change)

    def move_batch(self, batch_id, to: str) -> list:
        """`move` for a whole batch: its ``queued`` entries move as one contiguous block, ``up``/``down`` past the
        neighbouring entry or batch block, ``top`` to the head of the line. Returns the batch's entries that moved.
        Unknown batch: ``queue.batch_not_found``; nothing queued in it: ``queue.not_movable``."""
        _check_move(to)

        def change(data):
            mine = [e for e in _batch(data, batch_id) if e["state"] == "queued"]
            if not mine:
                raise GrunError("queue.not_movable", id=batch_id, state="finished")
            line = sorted((e for e in data["entries"] if e["state"] == "queued"), key=_pos)
            slots = _slots(line)
            ids = {e["id"] for e in mine}
            rest = [e for e in line if e["id"] not in ids]
            at = next(i for i, e in enumerate(line) if e["id"] in ids)  # where its first entry stood among the others
            starts = [i for i in range(len(rest) + 1)
                      if i in (0, len(rest)) or _block_key(rest[i]) != _block_key(rest[i - 1])]
            if to == "top":
                ins = 0
            elif to == "up":
                ins = max((i for i in starts if i < at), default=at)
            else:
                ins = min((i for i in starts if i > at), default=at)
            for item, slot in zip(rest[:ins] + sorted(mine, key=_pos) + rest[ins:], slots):
                item["position"] = slot
            return sorted(mine, key=_pos)

        return self._txn(change)

    # -- the worker's side ---------------------------------------------------------------------------------

    def next_queued(self):
        """The first queued entry the worker may start, without taking it; ``None`` if there is none."""
        return self._txn(self._first_queued)

    def claim(self):
        """Mark the first runnable queued entry ``running`` with this process's pid; returns it, or ``None`` (also
        while the queue is paused: the mark is checked under the queue lock, so a `pause` that returned stops
        every later claim)."""
        def change(data):
            entry = None if self.is_paused() else self._first_queued(data)
            if entry is not None:
                _transition(entry, "running", via="claim")
            return entry

        return self._txn(change)

    def finish(self, entry_id, state: str, error=None, attempt_id=None) -> dict:
        """Close a running entry as done, failed or cancelled (the last one needs ``cancelRequested``). `error`:
        ``{"code", "params"}`` (see `make_error`); a plain string is taken as a code without params."""
        if state not in TERMINAL:
            raise GrunError("queue.bad_state", state=str(state), states=", ".join(TERMINAL))
        if isinstance(error, str):
            error = make_error(error)

        def change(data):
            entry = _find(data, entry_id)
            if entry["state"] != "running":
                raise GrunError("queue.not_running", id=entry["id"], state=entry["state"])
            _transition(entry, state, via="finish")
            entry.update(error=error, attemptId=attempt_id)
            return entry

        return self._txn(change)

    def _set_running(self, entry_id, field: str, value) -> dict:
        def change(data):
            entry = _find(data, entry_id)
            if entry["state"] != "running":
                raise GrunError("queue.not_running", id=entry["id"], state=entry["state"])
            if entry.get(field) != value:  # a pulse with nothing new does not rewrite the file
                entry[field] = value
            return entry

        return self._txn(change)

    def set_progress(self, entry_id, progress: dict) -> dict:
        """Store ``{"step": n, "steps": N, "etaS": seconds | None}`` in a running entry. Only the three keys;
        ``0 <= step <= steps``, ``steps >= 1``; ``etaS`` is ``None`` or a number >= 0. Anything else is
        ``queue.bad_progress``; a finished or queued entry is ``queue.not_running``."""
        ok = (isinstance(progress, dict) and set(progress) == {"step", "steps", "etaS"}
              and all(type(progress[k]) is int for k in ("step", "steps"))
              and 0 <= progress["step"] <= progress["steps"] and progress["steps"] >= 1
              and (progress["etaS"] is None or _number(progress["etaS"])))
        if not ok:
            raise GrunError("queue.bad_progress", progress=json.dumps(progress, default=str))
        return self._set_running(entry_id, "progress", dict(progress))

    def set_preview(self, entry_id, path) -> dict:
        """Store the path of the engine's preview image in a running entry (the file may not exist yet)."""
        if not isinstance(path, str) or not path or "\x00" in path or "\n" in path:
            raise GrunError("queue.bad_progress", progress=repr(path))
        return self._set_running(entry_id, "preview", path)

    # -- pause and worker ----------------------------------------------------------------------------------

    def is_paused(self) -> bool:
        """Is the queue paused? The worker finishes what it runs and takes no other entry."""
        return paths.pause_path(self.data).exists()

    def pause(self) -> bool:
        """Leave the pause mark; False if it was already there (pausing twice is harmless)."""
        mark = paths.pause_path(self.data)
        with fsutil.lock(self._path):  # the queue's own lock: `claim` checks the mark under it
            try:
                fd = os.open(str(mark), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return False
            with os.fdopen(fd, "w") as fh:
                fh.write(_now() + "\n")
        return True

    def resume(self) -> bool:
        """Remove the pause mark; False if there was none."""
        with fsutil.lock(self._path):
            try:
                paths.pause_path(self.data).unlink()
            except FileNotFoundError:
                return False
        return True

    def worker_alive(self):
        """Does a worker hold ``worker.lock`` right now? ``True`` / ``False``, or ``None`` when it cannot be known.
        A pure read: it creates neither the folder nor the file (no lock file means no worker ever ran). Callers
        that start workers must treat ``None`` as "do not start"."""
        return fsutil.held(paths.worker_lock_path(self.data))

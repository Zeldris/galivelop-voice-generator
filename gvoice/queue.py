"""Persistent job queue (D10): one for the whole generator, ``<data>/queue.json``.

The queue itself (the file and its transaction, order, recovery of orphans by ``worker.lock``, the limit of finished
entries, the states) is `grun.queue.Queue` (R3, D-10: the file of gimg/gvoice is read as it is, no migration). This module
is the thin layer that is gvoice's: the three kinds of job (``kind``), the services above `orders`, the error texts and
the cleaning of the pending audio of a dead worker. Errors raised by grun (`GrunError`) come out as `GvoiceError`
(`errors.from_grun`), rendered with the texts of gvoice.

``{"nextId": n, "entries": [...]}``; entry: ``id``, ``kind``, ``project``, ``key``, ``seed``, ``text``, ``state``
(queued|running|done|failed|cancelled), ``pid``, ``enqueuedAt``, ``startedAt``, ``finishedAt``, ``error``,
``attemptId``, ``cancelRequested`` and, by kind:

* ``voice``: a take of a voice (``instruction`` from the design sheet; the engine's ``design``);
* ``line``: a take of a line (``voice`` and ``reference``: the voice it was made for and the take of it it is made with; the engine's ``line`` with the
  voice print of the production model, `production_model`);
* ``prints``: the voice prints (one per model that `orders.missing_prints` says the take lacks) of take ``take`` of a
  voice; ``attemptId`` is that take when done.

grun adds ``position`` and ``orphanCount`` (a worker that died with the entry running twice fails it with
``queue.orphaned``); a take is never a batch, so there is no ``batch``. One worker takes the queued entries in arrival
order (lowest position, then lowest id), so the ``prints`` job of a voice that was just chosen goes before the lines
asked for after it. ``error`` of a failed entry is ``{"code", "params"}`` (JSON); `error_text` renders it.

Service functions (the queue sits above `orders`, which never imports it): `submit_order`, `new_takes`, `choose` and
`undo` wrap the order's own, and queue the ``prints`` job when a voice take becomes the reference without all its
prints (`enqueue_prints`)."""
from __future__ import annotations

import contextlib
import functools
from pathlib import Path

from grun import fsutil, paths as grun_paths, queue as grun_queue
from grun.errors import GrunError

from . import engine, errors, i18n, limits, orders, paths, projects, schema
from .errors import GvoiceError

KEEP_TERMINAL = 200
TERMINAL = grun_queue.TERMINAL
STATES = grun_queue.STATES
KINDS = ("voice", "line", "prints")


def queue_path() -> Path:
    return grun_paths.queue_path(paths.data_dir())


def worker_lock_path() -> Path:
    return grun_paths.worker_lock_path(paths.data_dir())


def _clean_pending(entry: dict) -> None:
    """Delete what a dead worker left of `entry`: the pending audio of a take, the temporary files of a print.
    (grun calls it for each entry it recovers and swallows what it raises.)"""
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


def _queue() -> grun_queue.Queue:
    """The queue of the data folder of this moment (it follows ``GVOICE_DATA_HOME``)."""
    return grun_queue.Queue(paths.data_dir(), clean_pending=_clean_pending, keep_terminal=KEEP_TERMINAL)


def _gvoice_errors(fn):
    """grun raises `GrunError`: callers of gvoice get the `GvoiceError` with the same code and parameters."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except GvoiceError:
            raise
        except GrunError as exc:
            raise errors.from_grun(exc) from None
    return wrapper


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


def _item(kind: str, project: str, key: str, **fields) -> dict:
    """What gvoice gives grun for one entry: every entry carries ``seed`` and ``text`` (``None`` for ``prints``)."""
    return dict({"kind": kind, "project": project, "key": key, "seed": None, "text": None}, **fields)


@_gvoice_errors
def enqueue(project: str, key: str, specs: list) -> list:
    """Queue one take per spec (from ``orders.attempt_specs``); returns the new entries.

    The order must exist, and a ``line`` needs the production model of the machine to be one of the project's
    ``printModels`` (`production_model`); nothing is queued if anything fails."""
    order = orders.get(project, key)
    kind = order["type"]
    engine.check_configured()
    if kind == "line":
        production_model(project)
    needed = ("seed", "text", "instruction" if kind == "voice" else "reference")
    for spec in specs:
        missing = [k for k in needed if k not in spec]
        if missing:
            raise GvoiceError("order.spec_invalid", missing=", ".join(missing))
    items = [_item(kind, project, key, seed=spec["seed"], text=spec["text"],
                   **({"instruction": spec["instruction"],
                       **({"locale": spec["locale"]} if spec.get("locale") else {})} if kind == "voice"
                      else {"voice": spec.get("voice", order["voice"]), "reference": spec["reference"]}))
             for spec in specs]
    return _queue().enqueue(items, batch=False)  # a take is not a batch (invariant 13)


@_gvoice_errors
def enqueue_prints(project: str, key: str, take: int):
    """Queue the ``prints`` job of take `take` of voice `key`; ``None`` when there is nothing to do: the take has all
    its prints (`orders.missing_prints` is empty) or a ``prints`` job for it is already queued or running."""
    if not orders.missing_prints(project, key, take):
        return None
    engine.check_configured()
    queue = _queue()
    # grun has no "enqueue unless" in one transaction: the callers that make ``prints`` jobs queue up on their own lock
    with fsutil.lock(paths.data_dir() / "queue.prints"):
        for entry in queue.list_entries(["queued", "running"]):
            if (entry.get("kind") == "prints"
                    and (entry["project"], entry["key"], entry.get("take")) == (project, key, take)):
                return None
        return queue.enqueue([_item("prints", project, key, take=take)], batch=False)[0]


@_gvoice_errors
def list_entries(states=None) -> list:
    """Entries in arrival order, optionally only those whose state is in `states`."""
    return _queue().list_entries(states)


@_gvoice_errors
def get(entry_id) -> dict:
    return _queue().get(entry_id)


@_gvoice_errors
def cancel(entry_id) -> dict:
    """queued -> cancelled; running -> ``cancelRequested: true`` (the worker stops it); finished -> error."""
    return _queue().cancel(entry_id)


@_gvoice_errors
def clear(project: str | None = None) -> list:
    """Cancel every ``queued`` entry (of `project`, if given); a ``running`` one is never touched."""
    return _queue().clear() if project is None else _queue().clear(project=project)


@_gvoice_errors
def next_queued():
    """The first queued entry, without taking it; ``None`` if there is none."""
    return _queue().next_queued()


@_gvoice_errors
def claim():
    """Mark the first queued entry ``running`` with this process's pid; returns it, or ``None``."""
    return _queue().claim()


@_gvoice_errors
def recover_orphans() -> None:
    """For the worker, which holds the worker lock: every ``running`` entry is dead; recover them all."""
    _queue().recover_orphans()


def worker_alive():
    """Does a worker hold ``worker.lock`` right now? ``True`` / ``False``, or ``None`` when it cannot be known.
    A pure read: it creates neither the data folder nor the lock."""
    return _queue().worker_alive()


def make_error(code: str, errors=(), **params) -> dict:
    """The ``error`` of an entry: ``{"code", "params"}`` (JSON-serialisable: values that are not become text),
    plus ``"errors": [{"path", "code", "params"}]`` when there are schema errors (`GvoiceError.errors`)."""
    return grun_queue.make_error(code, errors, **params)


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


@_gvoice_errors
def finish(entry_id, state: str, error=None, attempt_id=None) -> dict:
    """Close a running entry as done, failed or cancelled (the last one needs ``cancelRequested``). `error`:
    ``{"code", "params"}`` (see `make_error`); a plain string is taken as a code without params."""
    return _queue().finish(entry_id, state, error, attempt_id)


@_gvoice_errors
def is_cancel_requested(entry_id) -> bool:
    """Polled by the worker every few ms: a plain locked read, it never tries the worker lock."""
    return _queue().is_cancel_requested(entry_id)


def entry_view(entry: dict, lang: str | None = None) -> dict:
    """The JSON form of an entry for ``gvoice queue list --json``: the entry plus ``errorText`` (with the texts of
    gvoice; grun's own `entry_view` renders with its own)."""
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

"""Orders and attempts (D10): storage, states, notes, choose and undo.

Copiado de gimg@0d02f51 (D7); cambia: no hay perfil, la carpeta es ``orders/<tipo>/<key>/`` y la API toma
``(project, type, key)``; dos tipos (``voice``: una toma por intento; ``line``: una frase con una voz y un modelo
Base) en vez de prompt, estilo y referencias de imagen; audio ``.wav``; ``model`` y ``count`` en el pedido; sin
perfiles, sin ``check_key`` (el límite de la clave es el del esquema) y con la clave ``attempts`` reservada.

Layout: ``<data>/projects/<project>/orders/<type>/<key>/order.json`` and ``.../attempts/<id>.wav``. The same key
may exist under both types: they are different orders.

Attempt fields: ``id, state, seed, note, createdAt, audio, device, model, engine?, engineVersion?, queueEntry?``
plus, for ``voice``, ``instruct`` and ``testText`` and, for ``line``, ``text`` (the sentence as it was when the
attempt was made) and ``voiceReference`` (id of the reference take of the voice it was spoken with; set by whoever
creates the attempt, the worker).

This module neither enqueues (queue, F1.4) nor delivers (F1.5): `choose` and `undo` return the old and new chosen
ids so the reference can hook in. Every read-modify-write holds `fsutil.lock` of ``order.json``.

Public API: `submit`, `attempt_specs`, `add_attempt`, `attempt_for_entry`, `attempt_audio`, `pending_audio_path`,
`entry_audio_name`, `mark`, `note`, `choose`, `undo`, `get`, `list_orders`. All raise `GvoiceError` with codes
``order.*`` on bad input.
"""
from __future__ import annotations

import copy
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from . import fsutil, paths, projects, schema, sheet
from .errors import GvoiceError

TYPES = ("voice", "line")
STATES = ("new", "candidate", "discarded")
SEED_LIMIT = 2 ** 32
RESERVED = "attempts"  # a key segment after the first would be the attempts folder of its parent order
_ORDER_FILE = "order.json"
_rng = random.SystemRandom()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _common(name: str) -> dict:
    return copy.deepcopy(schema.load_schema("common")["$defs"][name])


def _count_limits() -> tuple:
    props = schema.load_schema("order")["properties"]["count"]
    return props["minimum"], props["maximum"]


def _check_id(type_, key) -> None:
    """`type_` must be a known type; `key` must satisfy the common ``key`` schema and not use the reserved segment."""
    if type_ not in TYPES:
        raise GvoiceError("order.type_invalid", type=str(type_), types=", ".join(TYPES))
    errors = schema.validate(key, _common("key"))
    if errors:
        raise GvoiceError("order.invalid", errors=errors)
    if RESERVED in key.split("/")[1:]:
        raise GvoiceError("order.key_reserved", order=key, word=RESERVED)


def _order_dir(project: str, type_: str, key: str) -> Path:
    """Folder of one order. Every public entry point builds it, so type and key are validated here."""
    _check_id(type_, key)
    return paths.inside(paths.project_data_dir(project), "orders/%s/%s" % (type_, key))


def _order_file(project: str, type_: str, key: str) -> Path:
    return _order_dir(project, type_, key) / _ORDER_FILE


def attempt_audio(project: str, type_: str, key: str, attempt: dict) -> Path:
    """Where the audio of an attempt record lives: its ``audio`` field, relative to the order folder
    (``attempts/<id>.wav``, or ``attempts/q<entry>.wav`` for an attempt made by a queue entry).
    The path is resolved and must stay inside the order folder (D25). Path only; nothing is read."""
    return paths.inside(_order_dir(project, type_, key), attempt["audio"])


def pending_audio_path(project: str, type_: str, key: str, entry_id: int) -> Path:
    """Where the engine writes the audio of queue entry `entry_id` before it is final:
    ``attempts/.pending-<entry>.wav`` (same filesystem as the final ``attempts/q<entry>.wav``)."""
    return _order_dir(project, type_, key) / "attempts" / (".pending-%d.wav" % int(entry_id))


def entry_audio_name(entry_id: int) -> str:
    """The ``audio`` field of the attempt made by queue entry `entry_id` (unique across the generator)."""
    return "attempts/q%d.wav" % int(entry_id)


def _unknown_voice(project: str, voice: str, config: dict) -> None:
    if voice not in config["voices"]:
        raise GvoiceError("order.unknown_voice", project=project, voice=voice)


def _line_model(config: dict, model) -> str:
    """`model`, or the first of the project's print models; it must be one of them."""
    allowed = projects.print_models(config)
    model = allowed[0] if model is None else model
    if model not in allowed:
        raise GvoiceError("order.model_not_allowed", model=str(model), allowed=", ".join(allowed))
    return model


def _check_target(project: str, order: dict, config: dict) -> None:
    """The voice must exist in the project; for a line, its model must be one of the print models."""
    if order["type"] == "voice":
        _unknown_voice(project, order["key"], config)
    else:
        _unknown_voice(project, order["voice"], config)
        _line_model(config, order.get("model"))


def _read(project: str, type_: str, key: str) -> dict:
    path = _order_file(project, type_, key)
    try:
        data = fsutil.read_json(path)
    except FileNotFoundError:
        raise GvoiceError("order.unknown", project=project, type=type_, order=key)
    except (OSError, ValueError):
        raise GvoiceError("order.corrupt", path=str(path))
    return _shape(data, path, type_, key)


def _shape(data, path, type_=None, key=None) -> dict:
    """`data` must look like an order and, when given, match the type and key of its folder."""
    if (not isinstance(data, dict) or not isinstance(data.get("attempts"), list)
            or data.get("type") not in TYPES or not isinstance(data.get("key"), str)
            or "chosen" not in data or not isinstance(data.get("chosenHistory"), list)
            or (type_ is not None and data["type"] != type_) or (key is not None and data["key"] != key)):
        raise GvoiceError("order.corrupt", path=str(path))
    return data


def _modify(project: str, type_: str, key: str, change):
    """Locked read-modify-write: `change(order)` edits in place and returns the call's result."""
    path = _order_file(project, type_, key)
    if not path.exists():  # do not create folders or lock files for an unknown order
        raise GvoiceError("order.unknown", project=project, type=type_, order=key)
    with fsutil.lock(path):
        order = _read(project, type_, key)
        result = change(order)
        order["updatedAt"] = _now()
        fsutil.write_json(path, order)
    return result


def _attempt(order: dict, attempt_id) -> dict:
    for item in order["attempts"]:
        if type(attempt_id) is int and item["id"] == attempt_id:
            return item
    raise GvoiceError("order.attempt_unknown", attempt=attempt_id, order=order["key"], type=order["type"])


def submit(project: str, order: dict) -> dict:
    """Create or update an order; returns the stored record (a copy).

    `order` follows the ``order`` schema (``count`` is accepted but not stored: it is for the caller to
    pass to `attempt_specs`). A ``voice`` order's key must be a voice of the project; a ``line`` order's ``voice``
    too, and its ``model`` (default: the first) one of the project's print models. Resubmitting the same type + key
    replaces the type's fields (a missing ``seed`` or ``model`` clears it) and keeps attempts, chosen and history.
    The same key under the other type is another order. Does not enqueue."""
    errors = schema.validate(order, schema.load_schema("order"))
    if errors:
        raise GvoiceError("order.invalid", errors=errors)
    key, type_ = order["key"], order["type"]
    _check_id(type_, key)
    config = projects.get(project)["config"]
    _check_target(project, order, config)
    if type_ == "voice":
        fields = {"seed": order.get("seed"), "testText": order["testText"],
                  "designSheet": copy.deepcopy(order["designSheet"])}
    else:
        fields = {"seed": order.get("seed"), "voice": order["voice"], "text": order["text"],
                  "model": order.get("model")}
    path = _order_file(project, type_, key)
    with fsutil.lock(path):
        now = _now()
        try:
            record = _read(project, type_, key)
        except GvoiceError as exc:
            if exc.code != "order.unknown":
                raise
            record = {"key": key, "type": type_, "createdAt": now, "attempts": [],
                      "chosen": None, "chosenHistory": []}
        record.update(fields)
        record["updatedAt"] = now
        fsutil.write_json(path, record)
    return copy.deepcopy(record)


def attempt_specs(project: str, type_: str, key: str, count: int = 1, *, seed=None) -> list:
    """Specs of `count` (1-20, the ``count`` limits of the order schema) attempts to enqueue; never changes the stored order.

    The voice (and, for a line, the model) is checked again against the project's current configuration.
    Each spec is ``{"seed", "instruct", "testText"}`` for ``voice`` (the instruct is `sheet.build_instruct` of the
    order's design sheet) and ``{"seed", "text", "model", "voice"}`` for ``line`` (``model`` resolved).
    Seeds: `seed` if given, else the order's seed, then ``seed + i`` for attempt i (0-based); with neither, a
    random integer in ``[0, 2**32)`` per attempt (`random.SystemRandom`)."""
    low, high = _count_limits()
    if not isinstance(count, int) or isinstance(count, bool) or not low <= count <= high:
        raise GvoiceError("order.count_invalid", min=low, max=high)
    if seed is not None:
        errors = schema.validate(seed, _common("seed"))
        if errors:
            raise GvoiceError("order.invalid", errors=errors)
    order = get(project, type_, key)
    config = projects.get(project)["config"]
    _check_target(project, order, config)
    base = order["seed"] if seed is None else seed
    specs = []
    for i in range(count):
        spec = {"seed": _rng.randrange(SEED_LIMIT) if base is None else base + i}
        if type_ == "voice":
            spec["instruct"] = sheet.build_instruct(order["designSheet"])
            spec["testText"] = order["testText"]
        else:
            spec["text"] = order["text"]
            spec["model"] = _line_model(config, order.get("model"))
            spec["voice"] = order["voice"]
        specs.append(spec)
    return specs


def attempt_for_entry(project: str, type_: str, key: str, entry_id: int):
    """The attempt made by queue entry `entry_id` (a copy), or ``None``."""
    for item in get(project, type_, key)["attempts"]:
        if item.get("queueEntry") == entry_id and type(entry_id) is int:
            return copy.deepcopy(item)
    return None


_STR = {"type": "string", "minLength": 1}


def _spec_schema(type_: str) -> dict:
    seed, device = _common("seed"), _common("device")
    if type_ == "voice":
        props = {"seed": seed, "instruct": _STR, "testText": _common("testText"), "model": _STR, "device": device}
    else:
        model = _common("baseModel")
        props = {"seed": seed, "text": {"type": "string", "minLength": 1,
                                        "maxLength": schema.load_schema("order")["properties"]["text"]["maxLength"]},
                 "model": model, "device": device, "voiceReference": {"type": "integer", "minimum": 1}}
    return {"type": "object", "required": sorted(props), "properties": props}


def add_attempt(project: str, type_: str, key: str, spec: dict, entry_id=None) -> int:
    """Append an attempt in state ``new`` (used by the worker after generating); returns its id.

    Ids are sequential from 1. `spec` needs ``seed``, ``model`` (a line's must be one of the project's print
    models), ``device`` and, for ``voice``, ``instruct`` and ``testText``; for ``line``, ``text`` and
    ``voiceReference`` (an integer id). ``engine`` / ``engineVersion`` (strings, optional) are stored as given.
    Without `entry_id`, ``audio`` is ``attempts/<id>.wav``, relative to the order folder. With `entry_id` (the queue
    entry that made it) ``audio`` is ``attempts/q<entry>.wav`` and the attempt records ``queueEntry``; the call is
    idempotent per entry: if an attempt with that ``queueEntry`` exists, its id is returned and nothing is added."""
    if entry_id is not None and (type(entry_id) is not int or entry_id < 1):
        raise GvoiceError("order.spec_invalid", missing="entry_id")
    _check_id(type_, key)
    if not isinstance(spec, dict):
        raise GvoiceError("order.spec_invalid", missing="spec")
    config = projects.get(project)["config"]
    sch = _spec_schema(type_)
    missing = [k for k in sch["required"] if k not in spec]
    if missing:
        raise GvoiceError("order.spec_invalid", missing=", ".join(missing))
    errors = schema.validate({k: spec[k] for k in sch["required"]}, sch)
    if errors:
        raise GvoiceError("order.invalid", errors=errors)
    if type_ == "line":
        _line_model(config, spec["model"])

    def change(order):
        if entry_id is not None:
            for item in order["attempts"]:
                if item.get("queueEntry") == entry_id:
                    return item["id"]
        new_id = max((a["id"] for a in order["attempts"]), default=0) + 1
        record = {"id": new_id, "state": "new"}
        record.update({k: copy.deepcopy(spec[k]) for k in sch["required"]})
        record.update({
            "audio": "attempts/%d.wav" % new_id if entry_id is None else entry_audio_name(entry_id),
            "note": "",
            "createdAt": _now(),
        })
        if entry_id is not None:
            record["queueEntry"] = entry_id
        for extra in ("engine", "engineVersion"):  # which engine made it
            if isinstance(spec.get(extra), str):
                record[extra] = spec[extra]
        order["attempts"].append(record)
        return new_id

    return _modify(project, type_, key, change)


def mark(project: str, type_: str, key: str, attempt_id: int, state: str) -> dict:
    """Set an attempt's state (new|candidate|discarded); the chosen one cannot be discarded."""
    if state not in STATES:
        raise GvoiceError("order.state_invalid", state=str(state), states=", ".join(STATES))

    def change(order):
        item = _attempt(order, attempt_id)
        if state == "discarded" and order["chosen"] == attempt_id:
            raise GvoiceError("order.discard_chosen", attempt=attempt_id)
        item["state"] = state
        return copy.deepcopy(item)

    return _modify(project, type_, key, change)


def note(project: str, type_: str, key: str, attempt_id: int, text: str) -> dict:
    """Replace an attempt's note (``""`` clears it)."""
    if not isinstance(text, str):
        raise GvoiceError("order.note_invalid")

    def change(order):
        item = _attempt(order, attempt_id)
        item["note"] = text
        return copy.deepcopy(item)

    return _modify(project, type_, key, change)


def choose(project: str, type_: str, key: str, attempt_id: int) -> dict:
    """Choose an attempt; returns ``{"old": id|None, "new": id}`` for the reference to act on.

    The previous chosen (even ``None``) is pushed to ``chosenHistory``. A discarded attempt cannot be
    chosen. Choosing the already chosen attempt changes nothing (``old == new``, no push)."""
    def change(order):
        item = _attempt(order, attempt_id)
        if item["state"] == "discarded":
            raise GvoiceError("order.choose_discarded", attempt=attempt_id)
        old = order["chosen"]
        if old != attempt_id:
            order["chosenHistory"].append(old)
            order["chosen"] = attempt_id
        return {"old": old, "new": attempt_id}

    return _modify(project, type_, key, change)


def undo(project: str, type_: str, key: str) -> dict:
    """Pop the last chosen from the history (may be ``None``); returns ``{"old", "new"}``.

    Errors with ``order.history_empty`` if there is nothing to undo, and with ``order.undo_discarded`` if the
    attempt it would go back to was discarded meanwhile (going back to ``None`` is always allowed)."""
    def change(order):
        if not order["chosenHistory"]:
            raise GvoiceError("order.history_empty", order=order["key"], type=order["type"])
        old = order["chosen"]
        target = order["chosenHistory"][-1]
        if target is not None and _attempt(order, target)["state"] == "discarded":
            raise GvoiceError("order.undo_discarded", attempt=target)
        order["chosenHistory"].pop()
        order["chosen"] = target
        return {"old": old, "new": order["chosen"]}

    return _modify(project, type_, key, change)


def get(project: str, type_: str, key: str) -> dict:
    """The order record (a fresh copy); ``order.unknown`` if it does not exist."""
    projects.get(project)
    return _read(project, type_, key)


def list_orders(project: str, type_: str | None = None, chosen: bool | None = None) -> list:
    """Orders of a project sorted by (type, key). `chosen` True/False keeps only orders with/without
    a chosen attempt; `type_` keeps one type."""
    projects.get(project)
    if type_ is not None and type_ not in TYPES:
        raise GvoiceError("order.type_invalid", type=str(type_), types=", ".join(TYPES))
    base = paths.project_data_dir(project) / "orders"
    found = []
    for kind in ((type_,) if type_ else TYPES):
        for folder, _dirs, files in os.walk(base / kind):
            if _ORDER_FILE not in files:
                continue
            file = Path(folder) / _ORDER_FILE
            try:
                record = _shape(fsutil.read_json(file), file, kind, os.path.relpath(folder, base / kind))
            except (OSError, ValueError):
                raise GvoiceError("order.corrupt", path=str(file))
            if chosen is not None and (record["chosen"] is not None) != chosen:
                continue
            found.append(record)
    return sorted(found, key=lambda r: (r["type"], r["key"]))

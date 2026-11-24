"""Orders and takes (D10): storage, states, notes, choose and undo, voice prints and stale lines.

Copiado de gimg@fa1076e (D7); adaptado a gvoice (D9, D10): sin perfiles, composición, texto, plantillas, borradores
ni entrega; el pedido se identifica por proyecto + clave, y hay dos tipos, `voice` y `line`.

Layout: ``<data>/projects/<project>/orders/<key>/@/order.json``. The ``@`` folder keeps key ``a/b`` apart from
key ``a`` (a key segment cannot hold ``@``). Beside ``order.json``, one folder per attempt (a *take*):
``@/attempts/<id>/`` (or ``q<entry>`` for an attempt made by a queue entry) with ``audio.wav`` and, for a voice,
``prints/<model>.spk`` and ``prints/<model>.rvq`` (the voice prints, one pair per base model of the project's
``printModels``).

* ``voice``: each attempt is a take with a seed, the test text and the instruction built from the design sheet
  (`sheet.instruction`). Choosing a take makes it the voice's *reference* (it fixes the voice); `submit` also returns
  the `sheet.warnings` (never stored, never blocking).
  A voice is *designed* (takes with ``origin: "design"``) or *cloned*: its order holds ``clip`` (``audio``, ``text``,
  ``source``) instead of a sheet, and its takes are clips of a human voice (``origin: "clip"``, ``sourceSha256``,
  ``seed: None``, no ``instruction``; take 1 is the clip). A voice never changes class (``order.clip_kind_changed``).
  An attempt without ``origin`` (older data) is a ``design`` one; read it with ``attempt.get("origin", "design")``.
* ``line``: a voice (a ``voice`` order of the same project with a chosen reference) and a text. Each attempt records
  the voice (``voice``) and the reference take (``reference``) it was made with. A chosen line is *stale*
  (`is_stale`) when its voice changed or that take is not the voice's current reference; it is computed, never stored, and nothing regenerates it by itself.

This module neither enqueues nor runs the engine (queue and worker, F1.5): `add_attempt` and `set_prints` are what
the worker calls with an `EngineResult`. `choose` and `undo` return the old and new chosen ids.
Every read-modify-write holds `fsutil.lock` of ``order.json``. All raise `GvoiceError` with codes ``order.*``.

Public API: `submit`, `attempt_specs`, `add_attempt`, `attempt_for_entry`, `attempt_dir`, `attempt_audio`,
`pending_audio_path`, `print_paths`, `missing_prints`, `set_prints`, `mark`, `note`, `choose`, `undo`, `reference`,
`is_stale`, `stale_lines`, `get`, `list_orders`."""
from __future__ import annotations

import copy
import hashlib
import io
import os
import random
import wave
from datetime import datetime, timezone
from pathlib import Path

from . import fsutil, paths, projects, schema, sheet
from .errors import GvoiceError

STATES = ("new", "candidate", "discarded")
SEED_LIMIT = schema.load_schema("common")["$defs"]["seed"]["maximum"] + 1  # one place: common.schema.json
TYPES = ("voice", "line")
CLIP_MIN_SECONDS = 3
CLIP_MAX_SECONDS = 30
ORIGINS = ("design", "clip", "print")
_ORDER_FILE = "order.json"
_MARK = "@"
_rng = random.SystemRandom()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_fields_of(probe: dict) -> None:
    errors = schema.validate(probe, schema.load_schema("order"))
    if errors:
        raise GvoiceError("order.invalid", errors=errors)


def _check_key(key) -> None:
    """`key` must satisfy the order schema (``key`` pattern) and D25."""
    _check_fields_of({"key": key, "type": "line", "voice": "x", "text": "x"})
    paths.check_key(key)


def _order_dir(project: str, key: str) -> Path:
    """Folder of one order. Every public entry point builds it, so the key is validated here."""
    _check_key(key)
    return paths.inside(paths.project_data_dir(project), "orders/%s/%s" % (key, _MARK))


def _order_file(project: str, key: str) -> Path:
    return _order_dir(project, key) / _ORDER_FILE


def _read(project: str, key: str) -> dict:
    path = _order_file(project, key)
    try:
        data = fsutil.read_json(path)
    except FileNotFoundError:
        raise GvoiceError("order.unknown", project=project, order=key)
    except (OSError, ValueError):
        raise GvoiceError("order.corrupt", path=str(path))
    return _shape(data, path)


def _shape(data, path) -> dict:
    if (not isinstance(data, dict) or not isinstance(data.get("attempts"), list)
            or data.get("type") not in TYPES or not isinstance(data.get("key"), str)
            or "chosen" not in data or not isinstance(data.get("chosenHistory"), list)):
        raise GvoiceError("order.corrupt", path=str(path))
    return data


def _modify(project: str, key: str, change):
    """Locked read-modify-write: `change(order)` edits in place and returns the call's result."""
    path = _order_file(project, key)
    if not path.exists():  # do not create folders or lock files for an unknown order
        raise GvoiceError("order.unknown", project=project, order=key)
    with fsutil.lock(path):
        order = _read(project, key)
        result = change(order)
        order["updatedAt"] = _now()
        fsutil.write_json(path, order)
    return result


def _attempt(order: dict, attempt_id) -> dict:
    for item in order["attempts"]:
        if type(attempt_id) is int and item["id"] == attempt_id:
            return item
    raise GvoiceError("order.attempt_unknown", attempt=attempt_id, order=order["key"])


def _is_type(order: dict, expected: str) -> None:
    if order["type"] != expected:
        raise GvoiceError("order.wrong_type", order=order["key"], type=order["type"], expected=expected)


def _voice_order(project: str, voice: str) -> dict:
    """The ``voice`` order `voice` of the project, or ``order.voice_unknown``."""
    try:
        record = _read(project, voice)
    except GvoiceError as exc:
        if exc.code != "order.unknown":
            raise
        record = None
    if record is None or record["type"] != "voice":
        raise GvoiceError("order.voice_unknown", project=project, voice=voice)
    return record


def _fixed_voice(project: str, voice: str) -> tuple:
    """``(voice order, its reference attempt id)``; ``order.voice_not_fixed`` if no take is chosen yet."""
    record = _voice_order(project, voice)
    if record["chosen"] is None:
        raise GvoiceError("order.voice_not_fixed", voice=voice)
    return record, record["chosen"]


def _read_clip(project: str, clip: dict) -> tuple:
    """``(wav bytes, sha256 hex, duration ms)`` of ``clip["audio"]``, a path relative to the project root (D25).
    Raises ``order.clip_missing``, ``order.clip_not_wav`` or ``order.clip_duration``."""
    root = projects.get(project)["root"]
    path = paths.inside(root, clip["audio"])
    if not path.is_file():
        raise GvoiceError("order.clip_missing", path=clip["audio"])
    try:
        data = path.read_bytes()
    except OSError:
        raise GvoiceError("order.clip_missing", path=clip["audio"])
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
            w.readframes(min(frames, 1))
    except (wave.Error, EOFError, ValueError, OSError):
        raise GvoiceError("order.clip_not_wav", path=clip["audio"])
    if rate <= 0:
        raise GvoiceError("order.clip_not_wav", path=clip["audio"])
    seconds = frames / rate
    if not CLIP_MIN_SECONDS <= seconds <= CLIP_MAX_SECONDS:
        raise GvoiceError("order.clip_duration", path=clip["audio"], seconds="%.1f" % seconds,
                          min=CLIP_MIN_SECONDS, max=CLIP_MAX_SECONDS)
    return data, hashlib.sha256(data).hexdigest(), int(round(seconds * 1000))


def clip_relative(project: str, source) -> str:
    """The path of a clip file of the system (relative to the cwd, or absolute) as a POSIX path relative to the root
    of the project, links resolved. Outside the root: ``order.clip_outside``."""
    root = Path(projects.get(project)["root"]).resolve()
    try:
        target = Path(source).expanduser().resolve()
        return target.relative_to(root).as_posix()
    except (ValueError, OSError, RuntimeError):
        raise GvoiceError("order.clip_outside", path=str(source), root=str(root))


def submit(project: str, order: dict) -> dict:
    """Create or update an order; returns the stored record (a copy).

    `order` follows the ``order`` schema. A ``line`` needs a ``voice`` order of the project with a chosen reference
    (``order.voice_unknown`` / ``order.voice_not_fixed``). Resubmitting the same key replaces seed (a missing ``seed``
    clears it), testText and designSheet (voice) or voice and text (line), and keeps attempts, chosen and history;
    its type cannot change (``order.type_changed``). Does not enqueue. A voice resubmitted without ``locale`` keeps
    the one it has (the UI form has no such field, so a resubmit must not wipe it); a new ``locale`` replaces it.

    A ``voice`` carries a ``designSheet`` + ``testText`` or a ``clip`` (``{audio, text, source?}``, ``audio`` relative
    to the project root: a PCM WAV of 3 to 30 s). A clip becomes take 1 (``origin: "clip"``, the audio copied to
    ``attempts/<id>/audio.wav``, ``sourceSha256``, ``audioMs``, no seed); resubmitting a clip with the same sha256 as
    an existing clip take adds nothing, another one adds a take. A voice keeps its class (``order.clip_kind_changed``).

    A ``voice`` also gets ``warnings``, a list of ``{"code", "params"}`` from `sheet.warnings` (D11): it is in the
    returned copy only, never stored, and does not block."""
    _check_fields_of(order)
    paths.check_key(order["key"])
    projects.get(project)
    key = order["key"]
    kind = order["type"]
    if kind == "line":
        _fixed_voice(project, order["voice"])
        fields = {"voice": order["voice"], "text": order["text"]}
        for name in ("say", "split"):
            if name in order:
                fields[name] = order[name]
    elif "clip" in order:
        clip = copy.deepcopy(order["clip"])
        clip_data = _read_clip(project, clip)
        fields = {"clip": clip}
        if order.get("locale") is not None:
            fields["locale"] = order["locale"]
    else:
        clip_data = None
        fields = {"testText": order["testText"], "designSheet": copy.deepcopy(order["designSheet"])}
        if order.get("locale") is not None:
            fields["locale"] = order["locale"]
    fields["seed"] = order.get("seed")
    path = _order_file(project, key)
    with fsutil.lock(path):
        now = _now()
        try:
            record = _read(project, key)
        except GvoiceError as exc:
            if exc.code != "order.unknown":
                raise
            record = {"key": key, "type": kind, "createdAt": now, "attempts": [], "chosen": None,
                      "chosenHistory": []}
        if record["type"] != kind:
            raise GvoiceError("order.type_changed", order=key, type=record["type"], new=kind)
        if kind == "voice":
            was_clip = "clip" in record or any(a.get("origin") == "clip" for a in record["attempts"])
            was_design = "designSheet" in record or any(a.get("origin", "design") == "design"
                                                         for a in record["attempts"])
            if (was_clip and "clip" not in fields) or (was_design and "clip" in fields):
                raise GvoiceError("order.clip_kind_changed", order=key, type="clip" if was_clip else "design")
            for gone in (("designSheet", "testText") if "clip" in fields else ("clip",)):
                record.pop(gone, None)
        if kind == "line":  # a resubmit replaces say and split: a missing one is cleared
            for gone in ("say", "split"):
                if gone not in fields:
                    record.pop(gone, None)
        record.update(fields)
        if kind == "voice" and "clip" in fields:
            data, sha, ms = clip_data
            if not any(a.get("origin") == "clip" and a.get("sourceSha256") == sha for a in record["attempts"]):
                new_id = max((a["id"] for a in record["attempts"]), default=0) + 1
                folder = _attempt_folder(new_id, None)
                target = paths.inside(_order_dir(project, key), folder + "/audio.wav")
                target.parent.mkdir(parents=True, exist_ok=True)
                with fsutil.atomic_output(target) as tmp:
                    tmp.write_bytes(data)
                take = {"id": new_id, "origin": "clip", "state": "new", "seed": None, "text": fields["clip"]["text"],
                        "sourceSha256": sha, "audioMs": ms, "dir": folder, "audio": folder + "/audio.wav",
                        "note": "", "createdAt": now, "prints": {}}
                if record.get("locale"):
                    take["locale"] = record["locale"]
                record["attempts"].append(take)
        record["updatedAt"] = now
        fsutil.write_json(path, record)
    result = copy.deepcopy(record)
    if kind == "voice" and "designSheet" in order:
        result["warnings"] = [{"code": w.code, "params": dict(w.params)} for w in sheet.warnings(order["designSheet"])]
    return result


def check_count(count, base=None) -> None:
    """`count` must be an integer in 1..50 (``order.count_invalid``) and, with a base seed, ``base + count - 1`` must
    fit the seed range (``order.seed_range``). Raises before anything is stored."""
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 50:
        raise GvoiceError("order.count_invalid", min=1, max=50)
    if isinstance(base, int) and not isinstance(base, bool) and base + count - 1 >= SEED_LIMIT:
        raise GvoiceError("order.seed_range", seed=base, count=count, max=SEED_LIMIT - 1)


def attempt_specs(project: str, key: str, count: int = 1, *, seed=None) -> list:
    """Specs of `count` attempts to enqueue; never changes the stored order.

    A spec is ``{"seed", "text"}`` plus, for a ``voice``, ``"instruction"`` (from the design sheet) and, for a
    ``line``, ``"voice"`` (the line's current voice) and ``"reference"`` (that voice's current reference attempt id;
    ``order.voice_not_fixed`` without one).
    Seed: `seed` if given, else the order's, then ``seed + i`` for attempt i (0-based); with neither, a random
    integer in ``[0, 2**32)`` per attempt."""
    if seed is not None:
        _check_fields_of({"key": "x", "type": "line", "voice": "x", "text": "x", "seed": seed})
    order = get(project, key)
    base = order.get("seed") if seed is None else seed
    check_count(count, base)
    if order["type"] == "voice":
        if "clip" in order:
            raise GvoiceError("order.clip_no_design", order=key)
        locale = order.get("locale")
        extra = {"instruction": sheet.instruction(order["designSheet"], locale), "text": order["testText"]}
        if locale is not None:
            extra["locale"] = locale
    else:
        extra = {"voice": order["voice"], "reference": _fixed_voice(project, order["voice"])[1],
                 "text": order["text"]}
        if order.get("say"):
            extra["said"] = order["say"]
        if order.get("split"):
            extra["split"] = True
    return [dict(extra, seed=_rng.randrange(SEED_LIMIT) if base is None else base + i) for i in range(count)]


def attempt_for_entry(project: str, key: str, entry_id: int):
    """The attempt made by queue entry `entry_id` (a copy), or ``None``."""
    for item in get(project, key)["attempts"]:
        if item.get("queueEntry") == entry_id and type(entry_id) is int:
            return copy.deepcopy(item)
    return None


def attempt_dir(project: str, key: str, attempt: dict) -> Path:
    """Folder of an attempt record: its ``dir`` field, relative to the order folder (D25). Path only."""
    return paths.inside(_order_dir(project, key), attempt["dir"])


def attempt_audio(project: str, key: str, attempt: dict) -> Path:
    """Where the audio of an attempt record lives: its ``audio`` field (D25). Path only; nothing is read."""
    return paths.inside(_order_dir(project, key), attempt["audio"])


def pending_audio_path(project: str, key: str, entry_id: int) -> Path:
    """Where the engine writes the audio of queue entry `entry_id` before it is final:
    ``attempts/q<entry>/.pending.wav`` (same folder as the final ``audio.wav``). Path only."""
    return _order_dir(project, key) / "attempts" / ("q%d" % int(entry_id)) / ".pending.wav"


def _attempt_folder(attempt_id: int, entry_id) -> str:
    return "attempts/%s" % ("q%d" % entry_id if entry_id is not None else attempt_id)


def _base_model(model) -> str:
    allowed = schema.load_schema("common")["$defs"]["baseModel"]["enum"]
    if model not in allowed:
        raise GvoiceError("order.print_model", model=str(model), models=", ".join(allowed))
    return model


def print_paths(project: str, key: str, attempt: dict, model: str) -> tuple:
    """``(spk, rvq)`` where the voice print of `attempt` for base model `model` lives:
    ``<attempt>/prints/<model>.spk|.rvq`` (D25). Path only; nothing is read."""
    _base_model(model)
    folder = attempt_dir(project, key, attempt)
    return (paths.inside(folder, "prints/%s.spk" % model), paths.inside(folder, "prints/%s.rvq" % model))


def missing_prints(project: str, key: str, attempt_id: int) -> list:
    """The models of the project's ``printModels`` (config order) for which take `attempt_id` of voice `key` lacks
    the ``.spk`` or the ``.rvq`` file on disk. A voice order only."""
    order = get(project, key)
    _is_type(order, "voice")
    attempt = _attempt(order, attempt_id)
    models = projects.get(project)["config"]["printModels"]
    return [m for m in models if not all(p.is_file() for p in print_paths(project, key, attempt, m))]


def add_attempt(project: str, key: str, spec: dict, entry_id=None) -> int:
    """Append an attempt in state ``new`` (used by the worker after generating); returns its id.

    Ids are sequential from 1. `spec` needs ``seed`` and ``text`` plus ``instruction`` (voice) or ``reference``
    (line: the attempt id of the reference take it was made with, which must exist in the spec's ``voice``, the voice
    it was made for; recorded on the attempt, and the line's current voice when the spec has none).
    The audio is ``<dir>/audio.wav`` (``attempts/<id>`` or, with `entry_id`, ``attempts/q<entry>``); with `entry_id`
    the attempt records ``queueEntry`` and the call is idempotent per entry (an existing one's id is returned).
    ``result``, an `EngineResult` (or its dict), is stored as the D16 metadata: ``device``, ``engineVersion``,
    ``engineCommit``, ``model``, ``durationMs``, ``audioMs``, ``loadMs`` and ``command``; the seed stored is the
    spec's. Nothing is read or written on disk: the audio is the caller's job."""
    if entry_id is not None and (type(entry_id) is not int or entry_id < 1):
        raise GvoiceError("order.spec_invalid", missing="entry_id")
    current = get(project, key)
    kind = current["type"]
    needed = ("seed", "text", "instruction" if kind == "voice" else "reference")
    missing = [k for k in needed if k not in spec]
    if missing:
        raise GvoiceError("order.spec_invalid", missing=", ".join(missing))
    _check_fields_of({"key": "x", "type": "line", "voice": "x", "text": "x", "seed": spec["seed"]})
    if not isinstance(spec["text"], str) or (kind == "voice" and not isinstance(spec["instruction"], str)):
        raise GvoiceError("order.spec_invalid", missing="text")
    if kind == "line":
        line_voice = spec.get("voice", current["voice"])  # the voice the take was made for, not the current one
        if not isinstance(line_voice, str):
            raise GvoiceError("order.spec_invalid", missing="voice")
        voice = _voice_order(project, line_voice)
        if type(spec["reference"]) is not int or not any(a["id"] == spec["reference"] for a in voice["attempts"]):
            raise GvoiceError("order.reference_unknown", reference=str(spec["reference"]), voice=line_voice)
    result = spec.get("result")
    if result is not None and not isinstance(result, dict):
        result = dict(vars(result))

    def change(order):
        if entry_id is not None:
            for item in order["attempts"]:
                if item.get("queueEntry") == entry_id:
                    return item["id"]
        new_id = max((a["id"] for a in order["attempts"]), default=0) + 1
        folder = _attempt_folder(new_id, entry_id)
        record = {"id": new_id, "state": "new", "seed": spec["seed"], "text": spec["text"], "dir": folder,
                  "audio": folder + "/audio.wav", "note": "", "createdAt": _now()}
        if kind == "voice":
            record["origin"] = "design"
            record["instruction"] = spec["instruction"]
            record["prints"] = {}
        else:
            record["voice"] = line_voice
            record["reference"] = spec["reference"]
            if spec.get("said"):  # what the engine was given, when it is not the text
                record["said"] = spec["said"]
            if spec.get("split"):
                record["split"] = True
        if spec.get("locale"):  # the language the take was spoken in (a line: its reference take's)
            record["locale"] = spec["locale"]
        if entry_id is not None:
            record["queueEntry"] = entry_id
        paths.inside(_order_dir(project, key), record["audio"])
        for name, field in (("device", "device"), ("engine_version", "engineVersion"),
                            ("engine_commit", "engineCommit"), ("model", "model"), ("duration_ms", "durationMs"),
                            ("audio_ms", "audioMs"), ("load_ms", "loadMs")):
            if result and result.get(name) is not None:
                record[field] = result[name]
        if result and isinstance(result.get("command"), list) and all(isinstance(a, str) for a in result["command"]):
            record["command"] = list(result["command"])
        order["attempts"].append(record)
        return new_id

    return _modify(project, key, change)


def set_prints(project: str, key: str, attempt_id: int, model: str, result=None) -> dict:
    """Record that the voice print of take `attempt_id` for base model `model` was made (the worker, F1.5): stores
    ``prints[model]`` with the D16 metadata of `result` (an `EngineResult` or its dict). Returns the attempt (a copy).
    Nothing is read or written on disk: the ``.spk`` and ``.rvq`` files are the caller's job. A voice order only."""
    _base_model(model)
    if result is not None and not isinstance(result, dict):
        result = dict(vars(result))

    def change(order):
        _is_type(order, "voice")
        item = _attempt(order, attempt_id)
        meta = {"madeAt": _now()}
        for name, field in (("device", "device"), ("engine_version", "engineVersion"),
                            ("engine_commit", "engineCommit"), ("duration_ms", "durationMs")):
            if result and result.get(name) is not None:
                meta[field] = result[name]
        item.setdefault("prints", {})[model] = meta
        return copy.deepcopy(item)

    return _modify(project, key, change)


def mark(project: str, key: str, attempt_id: int, state: str) -> dict:
    """Set an attempt's state (new|candidate|discarded); the chosen one cannot be discarded."""
    if state not in STATES:
        raise GvoiceError("order.state_invalid", state=str(state), states=", ".join(STATES))

    def change(order):
        item = _attempt(order, attempt_id)
        if state == "discarded" and order["chosen"] == attempt_id:
            raise GvoiceError("order.discard_chosen", attempt=attempt_id)
        item["state"] = state
        return copy.deepcopy(item)

    return _modify(project, key, change)


def note(project: str, key: str, attempt_id: int, text: str) -> dict:
    """Replace an attempt's note (``""`` clears it)."""
    if not isinstance(text, str):
        raise GvoiceError("order.note_invalid")

    def change(order):
        item = _attempt(order, attempt_id)
        item["note"] = text
        return copy.deepcopy(item)

    return _modify(project, key, change)


def check_choosable(attempt: dict) -> None:
    """The one eligibility rule: a discarded attempt and one without audio yet (no ``audioMs`` from the engine)
    cannot be chosen (raises, else returns)."""
    if attempt["state"] == "discarded":
        raise GvoiceError("order.choose_discarded", attempt=attempt["id"])
    if "audioMs" not in attempt:
        raise GvoiceError("order.choose_no_audio", attempt=attempt["id"])


def choose(project: str, key: str, attempt_id: int) -> dict:
    """Choose an attempt; returns ``{"old": id|None, "new": id}``. For a voice it makes the take the reference
    (the worker then makes its prints: F1.5).

    The previous chosen (even ``None``) is pushed to ``chosenHistory``. A discarded attempt and one without audio
    cannot be chosen. Choosing the already chosen attempt changes nothing (``old == new``, no push)."""
    def change(order):
        item = _attempt(order, attempt_id)
        check_choosable(item)
        old = order["chosen"]
        if old != attempt_id:
            order["chosenHistory"].append(old)
            order["chosen"] = attempt_id
        return {"old": old, "new": attempt_id}

    return _modify(project, key, change)


def undo(project: str, key: str) -> dict:
    """Pop the last chosen from the history (may be ``None``); returns ``{"old", "new"}``.

    Errors with ``order.history_empty`` if there is nothing to undo and ``order.undo_discarded`` if the previous
    chosen is discarded. Undoing a voice goes back to the previous reference: its prints are still beside the take
    if they were made, so no work is repeated (see `missing_prints`)."""
    def change(order):
        if not order["chosenHistory"]:
            raise GvoiceError("order.history_empty", order=order["key"])
        old = order["chosen"]
        target = order["chosenHistory"][-1]
        if target is not None and _attempt(order, target)["state"] == "discarded":
            raise GvoiceError("order.undo_discarded", attempt=target)
        order["chosenHistory"].pop()
        order["chosen"] = target
        return {"old": old, "new": target}

    return _modify(project, key, change)


def get(project: str, key: str) -> dict:
    """The order record (a fresh copy); ``order.unknown`` if it does not exist."""
    projects.get(project)
    return _read(project, key)


def reference(project: str, voice: str):
    """The current reference attempt id of voice `voice` (its chosen take), or ``None`` if it is not fixed."""
    return _voice_order(project, voice)["chosen"]


def is_stale(project: str, key: str) -> bool:
    """Whether the chosen attempt of line `key` is stale (D10): it was made for another voice than the line's
    current one, with a reference take that is not that voice's current reference, or in another locale than that
    take's. Calculated each time, never stored. ``False`` when the line has no chosen attempt."""
    order = get(project, key)
    _is_type(order, "line")
    if order["chosen"] is None:
        return False
    return _stale(order, *_reference_and_locale(project, order["voice"]))


def _reference_and_locale(project: str, voice: str) -> tuple:
    """``(current reference id, locale of that take)`` of voice `voice` (locale ``None`` if the take is not among its
    attempts: its lines then come out stale, no error). The locale is the take's, not the voice
    order's now: a line is spoken with its reference's locale, so a voice resubmitted with another locale but the
    same take leaves its lines current (they would come out the same if regenerated)."""
    record = _voice_order(project, voice)
    current = record["chosen"]
    found = next((a for a in record["attempts"] if a["id"] == current), None) if current is not None else None
    return current, (found.get("locale") if found else None)


def _stale(order: dict, current, locale=None) -> bool:
    """`order` (a line with a chosen attempt) against the current reference `current` of its voice and that take's
    ``locale``:
    stale if the attempt was made for another voice (an old attempt without ``voice`` counts as the line's), with
    another take or in another locale (an attempt without ``locale`` was made with none)."""
    attempt = _attempt(order, order["chosen"])
    return (attempt.get("voice", order["voice"]) != order["voice"] or attempt.get("reference") != current
            or attempt.get("locale") != locale)


def stale_lines(project: str, voice: str) -> list:
    """Keys (sorted) of the lines whose current voice is `voice` and whose chosen attempt is stale."""
    current, locale = _reference_and_locale(project, voice)
    return [r["key"] for r in list_orders(project, type="line")
            if r["voice"] == voice and r["chosen"] is not None and _stale(r, current, locale)]


def list_orders(project: str, type: str | None = None, chosen: bool | None = None) -> list:
    """Orders of a project sorted by key. `type` keeps one type (``voice`` or ``line``); `chosen` True/False keeps
    only orders with/without a chosen attempt."""
    if type is not None and type not in TYPES:
        raise GvoiceError("order.type_invalid", type=str(type), types=", ".join(TYPES))
    projects.get(project)
    base = paths.project_data_dir(project) / "orders"
    found = []
    for folder, _dirs, files in os.walk(base):
        if _ORDER_FILE not in files or os.path.basename(folder) != _MARK:
            continue
        file = Path(folder) / _ORDER_FILE
        try:
            record = _shape(fsutil.read_json(file), file)
        except (OSError, ValueError):
            raise GvoiceError("order.corrupt", path=str(file))
        if type is not None and record["type"] != type:
            continue
        if chosen is not None and (record["chosen"] is not None) != chosen:
            continue
        found.append(record)
    return sorted(found, key=lambda r: r["key"])

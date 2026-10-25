"""The reference of a voice and its prints (D2, D10): choose, undo, status and the gate of ``line``.

Folder of a voice: ``<data>/projects/<project>/voices/<voice>/``.
- ``reference.wav`` + ``reference.txt``: the audio and the text of the chosen take (copied there by `choose`).
- ``reference.json`` ``{"reference": <take id>, "createdAt"}``: **the current reference of the voice**, written last
  (after the audio and the text). Without it the voice has no reference.
- ``prints/<model>.spk`` + ``.rvq`` and ``prints/<model>.json`` ``{"reference", "device", "engineVersion",
  "createdAt"}``: the print for one Base model; the ``.json`` is written last. A print is **up to date** when its
  ``.json`` names the current reference and both files exist.

Everything that changes the reference or commits a print holds `fsutil.lock` of ``reference.json``, so a print
extracted from a reference that was replaced meanwhile is never marked (``voice.print_stale``). "Stale line"
(desfasada) is computed by `status`, never stored.
"""
from __future__ import annotations

import contextlib
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import engine as engine_mod
from . import fsutil, orders, paths, projects, schema
from .errors import GvoiceError

_REFERENCE = "reference.json"
_NAME = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unlink(path) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def voice_dir(project: str, voice: str) -> Path:
    """Folder of a voice; the name must look like a voice name (so it cannot leave ``voices/``)."""
    global _NAME
    if _NAME is None:
        _NAME = re.compile(schema.load_schema("common")["$defs"]["name"]["pattern"])
    if not isinstance(voice, str) or not _NAME.search(voice) or "\n" in voice:
        raise GvoiceError("order.unknown_voice", project=str(project), voice=str(voice))
    return paths.inside(paths.project_data_dir(project), "voices/" + voice)


def check_model(config: dict, model) -> str:
    """`model` must still be one of the project's print models (``order.model_not_allowed`` otherwise)."""
    allowed = projects.print_models(config)
    if model not in allowed:
        raise GvoiceError("order.model_not_allowed", model=str(model), allowed=", ".join(allowed))
    return model


def print_files(project: str, voice: str, model: str) -> tuple:
    """``(.spk, .rvq, .json)`` of the print of `voice` for `model`. The model must be a Base model of the common
    schema, so its name cannot take the path out of ``prints/``."""
    base = schema.load_schema("common")["$defs"]["baseModel"]
    if schema.validate(model, base):
        raise GvoiceError("order.model_not_allowed", model=str(model), allowed=", ".join(base["enum"]))
    folder = voice_dir(project, voice) / "prints"
    return folder / (model + ".spk"), folder / (model + ".rvq"), folder / (model + ".json")


def _check_voice(project: str, voice: str) -> dict:
    config = projects.get(project)["config"]
    if voice not in config["voices"]:
        raise GvoiceError("order.unknown_voice", project=project, voice=str(voice))
    return config


def reference_id(project: str, voice: str):
    """The id of the current reference of `voice` (a take of its ``voice`` order), or ``None``."""
    try:
        value = fsutil.read_json(voice_dir(project, voice) / _REFERENCE)["reference"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return value if type(value) is int else None


def _print_reference(project: str, voice: str, model: str):
    """The reference a print was made with, if its files and marker are there; else ``None``."""
    spk, rvq, marker = print_files(project, voice, model)
    try:
        value = fsutil.read_json(marker)["reference"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return value if type(value) is int and spk.is_file() and rvq.is_file() else None


def is_up_to_date(project: str, voice: str, model: str) -> bool:
    current = reference_id(project, voice)
    return current is not None and _print_reference(project, voice, model) == current


def fixed_print(project: str, voice: str, model: str) -> tuple:
    """``(reference id, .spk, .rvq)`` of the up-to-date print a line speaks with.
    Raises ``line.voice_not_fixed`` when the voice has none for `model` (none, or made with another reference)."""
    spk, rvq, _marker = print_files(project, voice, model)
    if not is_up_to_date(project, voice, model):
        raise GvoiceError("line.voice_not_fixed", voice=voice, model=model)
    return reference_id(project, voice), spk, rvq


# ---- the prints of a ``print`` queue entry (called by the worker) -----------------------------------------

def print_job(entry: dict, machine_profile: dict) -> engine_mod.PrintJob:
    """The job of a ``print`` entry. ``voice.print_stale`` if `entry["reference"]` is no longer the current
    reference of the voice (nothing is touched); ``voice.reference_missing`` if its audio or text are gone."""
    project, voice, model = entry["project"], entry["voice"], entry["model"]
    spk, rvq, marker = print_files(project, voice, model)
    if reference_id(project, voice) != entry["reference"]:
        raise GvoiceError("voice.print_stale", voice=voice, model=model, reference=entry["reference"])
    folder = voice_dir(project, voice)
    wav, txt = folder / "reference.wav", folder / "reference.txt"
    for needed in (wav, txt):
        if not needed.is_file():
            raise GvoiceError("voice.reference_missing", path=str(needed))
    _unlink(marker)  # the files are about to change: the old marker would lie
    return engine_mod.PrintJob(
        reference=str(wav), reference_text=txt.read_text(encoding="utf-8"), model=model,
        spk=str(spk), rvq=str(rvq), device=machine_profile["engine"]["device"],
        timeout_s=machine_profile.get("timeoutS"))


def print_commit(entry: dict, result) -> None:
    """After the engine: the ``.json`` is the last thing written, so "up to date" is never true half way.
    Under the voice lock, the reference must still be the one the print was made from, else ``voice.print_stale``
    (the caller discards the files)."""
    project, voice, model = entry["project"], entry["voice"], entry["model"]
    marker = print_files(project, voice, model)[2]
    with fsutil.lock(voice_dir(project, voice) / _REFERENCE):
        if reference_id(project, voice) != entry["reference"]:
            raise GvoiceError("voice.print_stale", voice=voice, model=model, reference=entry["reference"])
        fsutil.write_json(marker, {"reference": entry["reference"], "device": result.device,
                                   "engineVersion": result.engine_version, "createdAt": _now()})


def print_discard(entry: dict) -> None:
    """The print failed, was cancelled or was stale: remove what it may have left."""
    for path in print_files(entry["project"], entry["voice"], entry["model"]):
        _unlink(path)


# ---- choose, undo, status -----------------------------------------------------------------------------------

def _copy_atomic(source, dest: Path) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix="." + dest.name + ".", suffix=".tmp")
    try:
        fsutil.honour_umask(fd)
        with os.fdopen(fd, "wb") as out, open(source, "rb") as src:
            while True:
                block = src.read(1 << 20)
                if not block:
                    break
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dest)
    except BaseException:
        _unlink(tmp)
        raise


def _take(project: str, voice: str, take_id) -> tuple:
    """``(take record, audio path)`` of a take of the voice's ``voice`` order that can be a reference."""
    order = orders.get(project, "voice", voice)  # order.unknown if the voice has no ``voice`` order
    take = next((t for t in order["attempts"] if type(take_id) is int and t["id"] == take_id), None)
    if take is None or take["state"] == "discarded":
        orders.choose(project, "voice", voice, take_id)  # raises order.attempt_unknown / order.choose_discarded
    audio = orders.attempt_audio(project, "voice", voice, take)
    if not audio.is_file():
        raise GvoiceError("voice.take_audio_missing", take=take_id, path=str(audio))
    return take, audio


def _apply(project: str, voice: str, config: dict, take: dict, audio: Path) -> list:
    """Make `take` the reference on disk (``reference.json`` last) and queue the prints that are missing.
    Called with the voice lock held. Returns the new ``print`` entries."""
    folder = voice_dir(project, voice)
    folder.mkdir(parents=True, exist_ok=True)
    _copy_atomic(audio, folder / "reference.wav")
    text = take.get("testText", "")
    fd, tmp = tempfile.mkstemp(dir=str(folder), prefix=".reference.txt.", suffix=".tmp")
    try:
        fsutil.honour_umask(fd)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, folder / "reference.txt")
    except BaseException:
        _unlink(tmp)
        raise
    fsutil.write_json(folder / _REFERENCE, {"reference": take["id"], "createdAt": _now()})
    return _queue_prints(project, voice, config, take["id"])


def _voice_prints(project: str, voice: str) -> list:
    from . import queue
    return [e for e in queue.list_entries(["queued", "running"])
            if e["kind"] == "print" and e["project"] == project and e["voice"] == voice]


def _cancel(entries: list) -> None:
    from . import queue
    for entry in entries:
        with contextlib.suppress(GvoiceError):  # it may have finished meanwhile
            queue.cancel(entry["id"])


def _queue_prints(project: str, voice: str, config: dict, reference: int) -> list:
    """Cancel the pending prints of other references and queue one print per print model that is neither up to
    date nor already pending for `reference`."""
    from . import queue
    pending = _voice_prints(project, voice)
    _cancel([e for e in pending if e["reference"] != reference])
    have = {e["model"] for e in pending if e["reference"] == reference}
    return [queue.enqueue_print(project, voice, model, reference) for model in projects.print_models(config)
            if model not in have and not is_up_to_date(project, voice, model)]


def choose(project: str, voice: str, take_id: int) -> dict:
    """Choose a take of the voice's ``voice`` order as its reference; returns ``{"old", "new", "prints"}``
    (the ``print`` entries queued, one per print model without an up-to-date print).

    The take must exist in the order, not be discarded and have its audio. Choosing the current reference again
    repeats the copy and queues what is missing (so it repairs an interrupted choose)."""
    config = _check_voice(project, voice)
    take, audio = _take(project, voice, take_id)
    folder = voice_dir(project, voice)
    folder.mkdir(parents=True, exist_ok=True)
    with fsutil.lock(folder / _REFERENCE):
        change = orders.choose(project, "voice", voice, take_id)
        return {"old": change["old"], "new": change["new"], "prints": _apply(project, voice, config, take, audio)}


def _clear(project: str, voice: str) -> None:
    folder = voice_dir(project, voice)
    _unlink(folder / _REFERENCE)  # first: from here the voice has no reference and nothing is "up to date"
    for name in ("reference.wav", "reference.txt"):
        _unlink(folder / name)
    prints = folder / "prints"
    if prints.is_dir():
        for path in prints.iterdir():
            if path.is_file():
                _unlink(path)


def undo(project: str, voice: str) -> dict:
    """Undo the last choice of the voice's reference; returns ``{"old", "new", "prints"}``. Going back to no
    reference removes the reference and every print and cancels the pending ones."""
    config = _check_voice(project, voice)
    order = orders.get(project, "voice", voice)
    target = order["chosenHistory"][-1] if order["chosenHistory"] else None
    take = audio = None
    if target is not None:  # check the audio before popping the history
        take, audio = _take(project, voice, target)
    folder = voice_dir(project, voice)
    folder.mkdir(parents=True, exist_ok=True)
    with fsutil.lock(folder / _REFERENCE):
        change = orders.undo(project, "voice", voice)
        if change["new"] is None:
            _cancel(_voice_prints(project, voice))
            _clear(project, voice)
            return {"old": change["old"], "new": None, "prints": []}
        return {"old": change["old"], "new": change["new"], "prints": _apply(project, voice, config, take, audio)}


def stale_lines(project: str, voice: str, reference) -> list:
    """The chosen lines of `voice` whose chosen take was made with a reference that is not `reference`:
    ``[{"key", "chosen", "voiceReference"}]`` sorted by key."""
    found = []
    for order in orders.list_orders(project, "line", chosen=True):
        if order["voice"] != voice:
            continue
        take = next((t for t in order["attempts"] if t["id"] == order["chosen"]), None)
        made = take.get("voiceReference") if take else None
        if take is not None and made != reference:
            found.append({"key": order["key"], "chosen": order["chosen"], "voiceReference": made})
    return found


def status(project: str, voice: str) -> dict:
    """``{"voice", "reference", "prints", "staleLines"}``, all computed: the current reference (id or ``None``),
    the print models whose print is up to date, and the stale lines (see `stale_lines`)."""
    config = _check_voice(project, voice)
    reference = reference_id(project, voice)
    return {"voice": voice, "reference": reference,
            "prints": [m for m in projects.print_models(config) if is_up_to_date(project, voice, m)],
            "staleLines": stale_lines(project, voice, reference)}

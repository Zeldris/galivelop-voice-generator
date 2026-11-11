"""Machine profile loading and safety limits: time, memory and models (D15).

Copiado de gimg@fa1076e (D7); adaptado a gvoice: no pixel, step or reference limits."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import fsutil, paths, schema
from .errors import GvoiceError

DEFAULT_PROFILE = "steam-deck"
_PRESETS = Path(__file__).resolve().parent / "machine_profiles"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


class LimitError(GvoiceError):
    """A job exceeds a limit of the machine profile."""


def _load_file(path: Path, shown: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise GvoiceError("machine.missing", path=shown)
    except (OSError, ValueError) as exc:
        raise GvoiceError("machine.unreadable", path=shown, reason=str(exc))
    errors = schema.validate(data, schema.load_schema("machine-profile"))
    if errors:
        raise GvoiceError("machine.invalid", errors=errors, path=shown)
    return data


def _preset(name) -> dict:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise GvoiceError("machine.bad_name", name=str(name))
    return _load_file(_PRESETS / (name + ".json"), name)


def load_machine(ref: str | None = None) -> dict:
    """Machine profile: `ref` (a preset name or a JSON path), else ``GVOICE_MACHINE_PROFILE``,
    else ``machineProfile`` in ``<config>/config.json``, else ``steam-deck``.

    A value containing ``/`` or ending in ``.json`` is a file path; anything else is a preset name
    (validated, so it cannot leave `gvoice/machine_profiles/`)."""
    if not ref:
        ref = os.environ.get("GVOICE_MACHINE_PROFILE")
    if not ref:
        config_file = paths.config_dir() / "config.json"
        try:
            config = fsutil.read_json(config_file, {})
        except (OSError, ValueError) as exc:
            raise GvoiceError("machine.config_unreadable", path=str(config_file), reason=str(exc))
        ref = config.get("machineProfile") if isinstance(config, dict) else None
    if not ref:
        ref = DEFAULT_PROFILE
    if not isinstance(ref, str):
        raise GvoiceError("machine.bad_name", name=str(ref))
    if "/" in ref or ref.endswith(".json"):
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in ref):
            raise GvoiceError("machine.bad_path", path=repr(ref))
        try:
            path = Path(ref).expanduser()
        except (RuntimeError, OSError) as exc:
            raise GvoiceError("machine.unreadable", path=ref, reason=str(exc))
        return _load_file(path, ref)
    return _preset(ref)


def timeout_s(machine: dict) -> int:
    """Time limit of one attempt, in seconds (``timeoutS``)."""
    return machine["timeoutS"]


def check_memory(free_mb, machine: dict) -> None:
    """Raise `LimitError` if `free_mb` is below ``minFreeMemoryMb`` (to start a job). ``None`` (unknown) passes."""
    minimum = machine.get("minFreeMemoryMb")
    if free_mb is not None and minimum is not None and free_mb < minimum:
        raise LimitError("limit.memory", free=free_mb, min=minimum)


def must_abort(free_mb, machine: dict) -> bool:
    """Whether a running job has to be aborted: free memory fell below ``watchMemoryMb``."""
    watch = machine.get("watchMemoryMb")
    return free_mb is not None and watch is not None and free_mb < watch


def check_model(use: str, model: str, machine: dict) -> None:
    """Raise `LimitError` if `model` is not allowed for `use` (``design`` or ``produce``) by the profile."""
    models = machine.get("models") or {}
    allowed = models.get(use)
    if allowed is None:
        return
    allowed = [allowed] if isinstance(allowed, str) else list(allowed)
    if model not in allowed:
        raise LimitError("limit.model", model=model, use=use, allowed=", ".join(allowed))


def available_memory_mb(meminfo: str = "/proc/meminfo"):
    """``MemAvailable`` in MB, or ``None`` where it cannot be read."""
    try:
        with open(meminfo, encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None

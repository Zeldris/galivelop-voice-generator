"""Machine profile loading and safety limits: time, memory and models (D15).

Adapter over `grun.limits` (R3): the time and memory limits and the memory readers are grun's (re-exported; the test
hooks are ``GRUN_MEMINFO`` and ``GRUN_PROC_STATUS``). Here stay what is gvoice's: `LimitError` as a `GvoiceError`
(`check_memory` re-raises grun's with it), the machine profile loading (schema, presets in `gvoice/machine_profiles/`)
and `check_model`."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from grun import fsutil
from grun import limits as _grun

from . import paths, schema
from .errors import GvoiceError

DEFAULT_PROFILE = "steam-deck"
_PRESETS = Path(__file__).resolve().parent / "machine_profiles"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


class LimitError(GvoiceError, _grun.LimitError):
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


timeout_s = _grun.timeout_s
must_abort = _grun.must_abort


def check_memory(free_mb, machine: dict) -> None:
    """Raise `LimitError` if `free_mb` is below ``minFreeMemoryMb`` (to start a job). ``None`` (unknown) passes."""
    try:
        _grun.check_memory(free_mb, machine)
    except _grun.LimitError as exc:
        raise LimitError(exc.code, **exc.params) from None


def check_model(use: str, model: str, machine: dict) -> None:
    """Raise `LimitError` if `model` is not allowed for `use` (``design`` or ``produce``) by the profile."""
    models = machine.get("models") or {}
    allowed = models.get(use)
    if allowed is None:
        return
    allowed = [allowed] if isinstance(allowed, str) else list(allowed)
    if model not in allowed:
        raise LimitError("limit.model", model=model, use=use, allowed=", ".join(allowed))


MEMINFO_ENV = _grun.MEMINFO_ENV
PROC_STATUS_ENV = _grun.PROC_STATUS_ENV
available_memory_mb = _grun.available_memory_mb
total_memory_mb = _grun.total_memory_mb
peak_rss_mb = _grun.peak_rss_mb

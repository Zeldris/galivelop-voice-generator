"""Machine profile loading (D15).

Copiado de gimg@0d02f51 (`limits.py`, D7); cambia: GVOICE_*, GvoiceError, módulo `machine`, sin `LimitError` ni
`check` (en F1 no hay límites de memoria ni de tamaño: la memoria la vigila el motor real, F2)."""
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

"""ProfileLoader (D-12): find, read and check a machine profile.

Adapted from the loaders of gimg and gvoice. `grun` checks only the fields it uses; the application passes its own
full schema as `validate`."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .errors import GrunError

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
OLLAMA_MODES = ("unload", "abort", "ignore")


def _int(value, minimum) -> bool:
    return type(value) is int and value >= minimum


def check(profile) -> list:
    """The problems of the fields `grun` uses, as ``[{"path", "code", "params"}]`` (empty when it is fine)."""
    errors = []

    def bad(path, expected):
        errors.append({"path": path, "code": "machine.field", "params": {"field": path, "expected": expected}})

    if not isinstance(profile, dict):
        bad("", "object")
        return errors
    if not _int(profile.get("timeoutS"), 1):
        bad("timeoutS", "integer >= 1")
    for key in ("minFreeMemoryMb", "watchMemoryMb"):
        if key in profile and not _int(profile[key], 0):
            bad(key, "integer >= 0")
    if "engine" in profile:
        engine = profile["engine"]
        if not isinstance(engine, dict):
            bad("engine", "object")
        else:
            if "ollama" in engine and engine["ollama"] not in OLLAMA_MODES:
                bad("engine.ollama", "|".join(OLLAMA_MODES))
            if "ollamaUrl" in engine and not isinstance(engine["ollamaUrl"], str):
                bad("engine.ollamaUrl", "string")
    return errors


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise GrunError("machine.missing", path=str(path))
    except (OSError, ValueError) as exc:  # a bad encoding or bad JSON is a ValueError
        raise GrunError("machine.unreadable", path=str(path), reason=getattr(exc, "strerror", None) or str(exc))


def _config_ref(config_path):
    """``machineProfile`` of the JSON config file; a missing or unreadable config is no setting."""
    if config_path is None:
        return None
    try:
        with open(config_path, encoding="utf-8") as fh:
            value = json.load(fh).get("machineProfile")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value else None


def load_profile(ref=None, *, presets, env_var, config_path=None, default="steam-deck", validate=None) -> dict:
    """The machine profile: `ref`, else ``$<env_var>``, else ``machineProfile`` of `config_path`, else `default`.
    A reference with ``/`` or ending in ``.json`` is a path; otherwise a name read from ``<presets>/<name>.json``."""
    ref = ref or os.environ.get(env_var) or _config_ref(config_path) or default
    ref = str(ref)
    if "/" in ref or ref.endswith(".json"):
        path = Path(ref)
    else:
        if not NAME_RE.match(ref):
            raise GrunError("machine.bad_name", name=ref)
        path = Path(presets) / (ref + ".json")
    profile = _read_json(path)
    errors = check(profile)
    if errors:
        raise GrunError("machine.invalid", path=str(path), errors=errors)
    if validate is not None:
        validate(profile)
    return profile

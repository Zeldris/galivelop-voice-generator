"""Data and config folders, and the D25 path guard.

Copiado de gimg@fa1076e (D7); adaptado a gvoice (D9)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import GvoiceError, PathError



def _xdg_base(xdg: str):
    """``$<xdg>`` if it is absolute (the XDG spec says to ignore relative values), else ``None``.

    Inside a Flatpak (``FLATPAK_ID`` set, e.g. VS Code on the Deck) the XDG folders point to the sandbox,
    ``~/.var/app/<id>/...``, where the ``gvoice`` of the host never looks: those are ignored, so both sides share
    ``~/.config``, ``~/.local/share`` and ``~/.local/state``."""
    base = os.environ.get(xdg)
    if not base or not os.path.isabs(base):
        return None
    if os.environ.get("FLATPAK_ID"):
        sandbox = Path.home() / ".var" / "app"
        if Path(base) == sandbox or sandbox in Path(base).parents:
            return None
    return Path(base)


def _home_dir(own: str, xdg: str, fallback: tuple) -> Path:
    explicit = os.environ.get(own)
    if explicit:
        return Path(explicit)
    base = _xdg_base(xdg)
    if base is not None:
        return base / "galivelop-voice"
    return Path.home().joinpath(*fallback)


def config_dir() -> Path:
    return _home_dir("GVOICE_CONFIG_HOME", "XDG_CONFIG_HOME", (".config", "galivelop-voice"))


def data_dir() -> Path:
    return _home_dir("GVOICE_DATA_HOME", "XDG_DATA_HOME", (".local", "share", "galivelop-voice"))


def state_dir() -> Path:
    """State shared by the Galivelop generators of one machine (D8): ``$GVOICE_STATE_HOME`` (tests), else
    ``$XDG_STATE_HOME/galivelop``, else ``~/.local/state/galivelop``. Not ``galivelop-voice``: the folder is the
    same for every generator, so they share the machine lock."""
    explicit = os.environ.get("GVOICE_STATE_HOME")
    if explicit:
        return Path(explicit)
    base = _xdg_base("XDG_STATE_HOME")
    if base is not None:
        return base / "galivelop"
    return Path.home() / ".local" / "state" / "galivelop"


def machine_lock_path() -> Path:
    """The machine lock (D8): ``<state>/gpu.lock``."""
    return state_dir() / "gpu.lock"


def models_dir() -> Path:
    """Model files folder: ``$GVOICE_MODELS_HOME`` (e.g. an SD card), else ``<data>/models``."""
    explicit = os.environ.get("GVOICE_MODELS_HOME")
    if explicit:
        return Path(explicit)
    return data_dir() / "models"


def engine_dir() -> Path:
    """Engine build folder: ``<data>/engine``."""
    return data_dir() / "engine"


def check_relative(rel) -> str:
    """Reject anything that is not a plain relative path; return it unchanged."""
    if not isinstance(rel, str):
        raise PathError("path.type")
    if rel == "":
        raise PathError("path.empty")
    if "\x00" in rel:
        raise PathError("path.nul")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in rel):
        raise PathError("path.control")
    if "\\" in rel:
        raise PathError("path.backslash")
    if rel.startswith("/"):
        raise PathError("path.absolute")
    if rel.startswith("~"):
        raise PathError("path.tilde")
    if ".." in rel.split("/"):
        raise PathError("path.dotdot")
    return rel


def inside(root, rel) -> Path:
    """Resolve `rel` under `root` (following links) and require it stays inside.

    The target may not exist yet. Returns the resolved path."""
    check_relative(rel)
    try:
        real_root = Path(root).resolve()
        target = (real_root / rel).resolve()
    except (OSError, RuntimeError):
        raise PathError("path.unresolvable", path=rel)
    if target != real_root and real_root not in target.parents:
        raise PathError("path.outside", path=rel)
    return target


_PROJECT_NAME = None


def project_data_dir(name, code: str = "project.bad_name") -> Path:
    """``<data>/projects/<name>``; `name` must match the name pattern of common.schema.json
    (so ``.``, ``..``, ``a/b`` cannot reach another folder). Raises GvoiceError `code` otherwise."""
    global _PROJECT_NAME
    if _PROJECT_NAME is None:
        from . import schema
        _PROJECT_NAME = re.compile(schema.load_schema("common")["$defs"]["name"]["pattern"])
    if not isinstance(name, str) or not _PROJECT_NAME.search(name) or "\n" in name:
        raise GvoiceError(code, project=str(name))
    return inside(data_dir(), "projects/" + name)


def max_key() -> int:
    """Longest key: the ``maxLength`` of ``key`` in common.schema.json (the one place that says it)."""
    from . import schema
    return schema.load_schema("common")["$defs"]["key"]["maxLength"]


def check_key(key: str) -> str:
    """Length limit of an order key (shape is the order schema's job). Segments need no limit of their own:
    a segment longer than the key limit makes the whole key longer."""
    limit = max_key()
    if len(key) > limit:
        raise GvoiceError("key.too_long", limit=limit)
    return key

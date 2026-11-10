"""Data and config folders, and the D25 path guard.

Copiado de gimg@fa1076e (D7); adaptado a gvoice (D9)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import GvoiceError, PathError

MAX_KEY = 200
MAX_SEGMENT = 100


def _home_dir(own: str, xdg: str, fallback: tuple) -> Path:
    explicit = os.environ.get(own)
    if explicit:
        return Path(explicit)
    base = os.environ.get(xdg)
    if base and os.path.isabs(base):  # the XDG spec says to ignore relative values
        return Path(base) / "galivelop-voice"
    return Path.home().joinpath(*fallback)


def config_dir() -> Path:
    return _home_dir("GVOICE_CONFIG_HOME", "XDG_CONFIG_HOME", (".config", "galivelop-voice"))


def data_dir() -> Path:
    return _home_dir("GVOICE_DATA_HOME", "XDG_DATA_HOME", (".local", "share", "galivelop-voice"))


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


def check_key(key: str) -> str:
    """Length limits of an order key (shape is the order schema's job)."""
    if len(key) > MAX_KEY:
        raise GvoiceError("key.too_long", limit=MAX_KEY)
    for segment in key.split("/"):
        if len(segment) > MAX_SEGMENT:
            raise GvoiceError("key.segment_too_long", limit=MAX_SEGMENT, segment=segment[:20])
    return key

"""Data and config folders, and the D25 path guard.

Adapter over `grun.paths` (R3): the state folder and the machine lock path are grun's (``$GALIVELOP_STATE_HOME``);
the data and config folders are grun's with gvoice's folder name and ``GVOICE_`` prefix; the path guard raises
gvoice's `PathError` (grun raises its own). Project, model and engine folders and the key checks are gvoice's."""
from __future__ import annotations

import os
import re
from pathlib import Path

from grun import paths as _grun

from . import errors
from .errors import GvoiceError, PathError

FOLDER = "galivelop-voice"
ENV_PREFIX = "GVOICE"

def _home(own: str, folder_default: Path, grun_fn) -> Path:
    """``$<own>`` as set (a relative value is used as is, as before R3; grun ignores it), else grun's folder."""
    explicit = os.environ.get(own)
    if explicit:
        return Path(explicit)
    return grun_fn()


def config_dir() -> Path:
    return _home("GVOICE_CONFIG_HOME", None, lambda: _grun.config_dir(FOLDER, ENV_PREFIX))


def data_dir() -> Path:
    return _home("GVOICE_DATA_HOME", None, lambda: _grun.data_dir(FOLDER, ENV_PREFIX))


def state_dir() -> Path:
    """grun's state folder; ``$GALIVELOP_STATE_HOME`` (absolute) wins, else ``$GVOICE_STATE_HOME`` even if relative."""
    galivelop = os.environ.get("GALIVELOP_STATE_HOME")
    if galivelop and os.path.isabs(galivelop):
        return _grun.state_dir()
    return _home("GVOICE_STATE_HOME", None, _grun.state_dir)


def machine_lock_path() -> Path:
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
    try:
        return _grun.check_relative(rel)
    except _grun.PathError as exc:
        raise errors.from_grun(exc) from None


def inside(root, rel) -> Path:
    """Resolve `rel` under `root` (following links) and require it stays inside.

    The target may not exist yet. Returns the resolved path."""
    try:
        return _grun.inside(root, rel)
    except _grun.PathError as exc:
        raise errors.from_grun(exc) from None


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

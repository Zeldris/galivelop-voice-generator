"""Data, config and state folders, the machine-lock path and the path guard.

Adapted from gvoice@8a17618 gvoice/paths.py (per-application folders are parameters; no project, model or
engine folders; D-1 state variable)."""
from __future__ import annotations

import os
from pathlib import Path

from .errors import PathError

STATE_ENV = "GALIVELOP_STATE_HOME"
STATE_ENV_ALIAS = "GVOICE_STATE_HOME"  # TODO(R3): remove the alias when gvoice migrates to grun


def _xdg_base(xdg: str):
    """``$<xdg>`` if it is absolute (the XDG spec says to ignore relative values), else ``None``.

    Inside a Flatpak (``FLATPAK_ID`` set, e.g. VS Code on the Deck) the XDG folders point to the sandbox,
    ``~/.var/app/<id>/...``, where the host applications never look: those are ignored, so both sides share
    ``~/.config``, ``~/.local/share`` and ``~/.local/state``."""
    base = os.environ.get(xdg)
    if not base or not os.path.isabs(base):
        return None
    if os.environ.get("FLATPAK_ID"):
        sandbox = Path.home() / ".var" / "app"
        if Path(base) == sandbox or sandbox in Path(base).parents:
            return None
    return Path(base)


def _absolute_env(*names):
    """The first of the variables `names` set to an absolute path, else ``None`` (a relative value is ignored, as
    the XDG spec says, so the folders never depend on the working directory)."""
    for name in names:
        value = os.environ.get(name)
        if value and os.path.isabs(value):
            return value
    return None


def _home_dir(own: str, xdg: str, folder: str, fallback: tuple) -> Path:
    explicit = _absolute_env(own)
    if explicit:
        return Path(explicit)
    base = _xdg_base(xdg)
    if base is not None:
        return base / folder
    return Path.home().joinpath(*fallback, folder)


def config_dir(folder: str, env_prefix: str) -> Path:
    """Config folder of an application: ``$<env_prefix>_CONFIG_HOME`` (if absolute), else ``$XDG_CONFIG_HOME/<folder>``,
    else ``~/.config/<folder>`` (e.g. ``folder="galivelop-voice"``, ``env_prefix="GVOICE"``)."""
    return _home_dir(env_prefix + "_CONFIG_HOME", "XDG_CONFIG_HOME", folder, (".config",))


def data_dir(folder: str, env_prefix: str) -> Path:
    """Data folder of an application: ``$<env_prefix>_DATA_HOME`` (if absolute), else ``$XDG_DATA_HOME/<folder>``,
    else ``~/.local/share/<folder>``."""
    return _home_dir(env_prefix + "_DATA_HOME", "XDG_DATA_HOME", folder, (".local", "share"))


def state_dir() -> Path:
    """State shared by the Galivelop applications of one machine (D-1): ``$GALIVELOP_STATE_HOME``, else the alias
    ``$GVOICE_STATE_HOME`` (relative values are ignored), else ``$XDG_STATE_HOME/galivelop``, else ``~/.local/state/galivelop``. The folder is
    the same for every application, so they share the machine lock."""
    explicit = _absolute_env(STATE_ENV, STATE_ENV_ALIAS)
    if explicit:
        return Path(explicit)
    base = _xdg_base("XDG_STATE_HOME")
    if base is not None:
        return base / "galivelop"
    return Path.home() / ".local" / "state" / "galivelop"


def machine_lock_path() -> Path:
    """The machine lock: ``<state>/gpu.lock``. Never deleted."""
    return state_dir() / "gpu.lock"


def queue_path(data: Path) -> Path:
    """The queue of an application: ``<data>/queue.json``."""
    return Path(data) / "queue.json"


def queue_lock_path(data: Path) -> Path:
    """Lock of the queue transactions: ``<data>/queue.json.lock`` (the one `fsutil.lock` takes). Never deleted."""
    return Path(data) / "queue.json.lock"


def worker_lock_path(data: Path) -> Path:
    """One worker per application: ``<data>/worker.lock``. Never deleted."""
    return Path(data) / "worker.lock"


def pause_path(data: Path) -> Path:
    """The pause mark: ``<data>/queue.paused``."""
    return Path(data) / "queue.paused"


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

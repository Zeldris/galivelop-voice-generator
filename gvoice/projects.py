"""Project registry and project configuration loading.

Copiado de gimg@0d02f51 (D7); cambia: galivelop-voices.json, GvoiceError, sin plantilla ni manifiesto (solo
`delivery.dir`), y `print_models`."""
from __future__ import annotations

import copy
from pathlib import Path

from . import __version__, fsutil, paths, schema
from .errors import GvoiceError, PathError

CONFIG_FILE = "galivelop-voices.json"


def registry_path() -> Path:
    return paths.config_dir() / "projects.json"


def _read_registry() -> dict:
    try:
        data = fsutil.read_json(registry_path(), default={"projects": {}})
    except (OSError, ValueError):
        raise GvoiceError("project.registry_corrupt", path=str(registry_path()))
    ok = isinstance(data, dict) and isinstance(data.get("projects"), dict)
    if not ok or not all(
        isinstance(v, dict) and isinstance(v.get("root"), str) for v in data["projects"].values()
    ):
        raise GvoiceError("project.registry_corrupt", path=str(registry_path()))
    return data


def _version(text: str) -> tuple:
    return tuple(int(p) for p in text.split("."))


def _forbidden(root: Path, field: str, rel: str) -> None:
    """delivery.dir must not land in .git/ nor on the config file."""
    target = paths.inside(root, rel)
    real_root = root.resolve()
    parts = target.relative_to(real_root).parts
    if any(p.casefold() == ".git" for p in parts):
        raise GvoiceError("project.forbidden_git", field=field, path=rel)
    if len(parts) == 1 and parts[0].casefold() == CONFIG_FILE:
        raise GvoiceError("project.forbidden_config", field=field, path=rel)


def load_config(root) -> dict:
    """Read, validate and complete `<root>/galivelop-voices.json`."""
    root = Path(root)
    path = root / CONFIG_FILE
    try:
        data = fsutil.read_json(path)
    except FileNotFoundError:
        raise GvoiceError("project.config_missing", path=str(path))
    except (OSError, ValueError) as exc:
        raise GvoiceError("project.config_unreadable", path=str(path), reason=str(exc))
    sch = schema.load_schema("project-config")
    errors = schema.validate(data, sch)
    if errors:
        raise GvoiceError("project.config_invalid", errors=errors, path=str(path))
    if _version(data["minVersion"]) > _version(__version__):
        raise GvoiceError(
            "project.version_too_new", required=data["minVersion"], current=__version__
        )
    config = copy.deepcopy(data)
    _forbidden(root, "delivery.dir", config["delivery"]["dir"])
    return config


def list_projects() -> dict:
    return {n: dict(v) for n, v in sorted(_read_registry()["projects"].items())}


def get(name: str) -> dict:
    """Registered project: {"name", "root", "config"}; the config is re-read every time."""
    entry = _read_registry()["projects"].get(name)
    if entry is None:
        raise GvoiceError("project.unknown", name=name)
    return {"name": name, "root": entry["root"], "config": load_config(entry["root"])}


def add(root) -> str:
    """Register the project at `root`; returns its name. Same name, other path: error."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise GvoiceError("project.root_not_dir", path=str(root))
    name = load_config(root)["name"]
    with fsutil.lock(registry_path()):
        data = _read_registry()
        current = data["projects"].get(name)
        if current is not None and current["root"] != str(root):
            raise GvoiceError("project.name_taken", name=name, root=current["root"])
        data["projects"][name] = {"root": str(root)}
        fsutil.write_json(registry_path(), data)
    return name


def remove(name: str) -> None:
    with fsutil.lock(registry_path()):
        data = _read_registry()
        if name not in data["projects"]:
            raise GvoiceError("project.unknown", name=name)
        del data["projects"][name]
        fsutil.write_json(registry_path(), data)


def print_models(config) -> list:
    """Base models to extract a print for: `printModels`, or every `baseModel` of common.schema.json in its order."""
    models = config.get("printModels")
    if models is None:
        models = schema.load_schema("common")["$defs"]["baseModel"]["enum"]
    return list(models)

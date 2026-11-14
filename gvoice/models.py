"""Engine catalogs and model files: load a catalog, check what is installed, download what is missing (D18).

A catalog is data (`gvoice/engines/<engine>.json`, schema `engine-catalog`). Files live in `paths.models_dir()`.
Downloads go to ``<file>.part``, are checked (size, then SHA-256) and renamed atomically, so the final name never
holds a partial or wrong file. Standard library only (D1)."""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import json
import os
import re
import urllib.request
from pathlib import Path

from . import paths, schema
from .errors import GvoiceError

_ENGINES = Path(__file__).resolve().parent / "engines"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
CHUNK = 1024 * 1024
TIMEOUT_S = 30

MISSING, BAD_SIZE, BAD_SHA256, OK, UNCHECKED = "missing", "bad_size", "bad_sha256", "ok", "unchecked"


def _load_file(path: Path, shown: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise GvoiceError("models.catalog_missing", engine=shown)
    except (OSError, ValueError) as exc:
        raise GvoiceError("models.catalog_unreadable", engine=shown, reason=str(exc))
    errors = schema.validate(data, schema.load_schema("engine-catalog"))
    if errors:
        raise GvoiceError("models.catalog_invalid", errors=errors, engine=shown)
    ids = [m["id"] for m in data["models"]]
    if len(set(ids)) != len(ids):
        raise GvoiceError("models.catalog_duplicate", engine=shown)
    return data


def load(engine: str, directory=None) -> dict:
    """The catalog of `engine` (a name, validated so it cannot leave the catalogs folder)."""
    if not isinstance(engine, str) or not _NAME.fullmatch(engine):
        raise GvoiceError("models.catalog_missing", engine=str(engine))
    return _load_file(Path(directory or _ENGINES) / (engine + ".json"), engine)


def model_path(model: dict) -> Path:
    return paths.inside(paths.models_dir(), model["file"])


def _select(catalog: dict, ids) -> list:
    models = catalog["models"]
    if not ids:
        return list(models)
    by_id = {m["id"]: m for m in models}
    for model_id in ids:
        if model_id not in by_id:
            raise GvoiceError("models.unknown_id", id=str(model_id), known=", ".join(by_id))
    return [by_id[i] for i in dict.fromkeys(ids)]


def sha256_of(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _state(model: dict, path: Path, check_hash: bool) -> tuple:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return MISSING, None
    except OSError as exc:
        raise GvoiceError("models.unreadable", path=str(path), reason=str(exc))
    if size != model["bytes"]:
        return BAD_SIZE, size
    if not check_hash:
        return UNCHECKED, size
    try:
        same = sha256_of(path) == model["sha256"]
    except OSError as exc:
        raise GvoiceError("models.unreadable", path=str(path), reason=str(exc))
    return (OK if same else BAD_SHA256), size


def status(catalog: dict, ids=None, check_hash: bool = True) -> list:
    """One dict per model: ``id``, ``file``, ``use``, ``path``, ``state`` (`missing`, `bad_size`, `bad_sha256`,
    `ok`), ``bytes`` (expected) and ``actual`` (size on disk or ``None``). The SHA-256 is read, by blocks, only when
    the size matches; with `check_hash` false a file of the right size is ``unchecked``."""
    found = []
    for model in _select(catalog, ids):
        path = model_path(model)
        state, actual = _state(model, path, check_hash)
        found.append({"id": model["id"], "file": model["file"], "use": model["use"], "path": str(path),
                      "state": state, "bytes": model["bytes"], "actual": actual})
    return found


def _download(model: dict, path: Path, progress) -> None:
    part = path.with_name(path.name + ".part")
    path.parent.mkdir(parents=True, exist_ok=True)
    total, digest, got = model["bytes"], hashlib.sha256(), 0
    try:
        try:
            with urllib.request.urlopen(model["url"], timeout=TIMEOUT_S) as response, open(part, "wb") as out:
                if progress:
                    progress(model["id"], 0, total)
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    got += len(block)
                    if got > total:
                        raise GvoiceError("models.bad_size", id=model["id"], expected=total, actual=">%d" % total)
                    digest.update(block)
                    out.write(block)
                    if progress:
                        progress(model["id"], got, total)
                out.flush()
                os.fsync(out.fileno())
        except (OSError, http.client.HTTPException, ValueError) as exc:  # URLError and timeouts are OSError
            raise GvoiceError("models.download_failed", id=model["id"], url=model["url"], reason=str(exc))
        if got != total:
            raise GvoiceError("models.bad_size", id=model["id"], expected=total, actual=got)
        if digest.hexdigest() != model["sha256"]:
            raise GvoiceError("models.bad_sha256", id=model["id"], expected=model["sha256"],
                              actual=digest.hexdigest())
        os.replace(part, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(part)
        raise


def fetch(catalog: dict, ids=None, progress=None) -> list:
    """Download the models (all, or `ids`) that are missing or wrong; leave the good ones alone.

    `progress(id, done_bytes, total_bytes)` is called at the start (0) and after each block. Returns
    ``[{"id", "path", "action"}]`` with action ``downloaded`` or ``present``. A file that does not match the
    catalog is never left behind: the `.part` is removed and the error says why (`models.bad_size`,
    `models.bad_sha256`, `models.download_failed`). A wrong file already in place is replaced only by a good one."""
    done = []
    for item, model in zip(status(catalog, ids), _select(catalog, ids)):
        path = Path(item["path"])
        if item["state"] == OK:
            done.append({"id": item["id"], "path": item["path"], "action": "present"})
            continue
        _download(model, path, progress)
        done.append({"id": item["id"], "path": item["path"], "action": "downloaded"})
    return done

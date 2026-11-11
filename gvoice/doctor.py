"""`gvoice doctor` (F2.5): diagnose the configured engine, its install, the model files and the machine profile.

Runs no engine process. Each check is a dict ``{"check", "ok", "warning", "code", "params"}``; ``code`` is the suffix
of the ``doctor.<code>`` text. A warning is ``ok`` (it does not fail the run). Models are hashed with sha256 (2-4 GB:
slow) unless `quick`, which only compares sizes."""
from __future__ import annotations

import hashlib
import os

from . import engine as engine_mod, install, limits
from .errors import GvoiceError

CHUNK = 1 << 20


def _check(check, code, ok=True, warning=False, **params) -> dict:
    return {"check": check, "ok": ok, "warning": warning, "code": code, "params": params}


def sha256_of(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file(check, label, path, expected, quick) -> dict:
    size_want, sha_want = expected
    try:
        size = os.path.getsize(path)
    except OSError:
        return _check(check, "file_missing", False, name=label, path=str(path))
    if size != size_want:
        return _check(check, "file_size", False, name=label, path=str(path), size=size, expected=size_want)
    if quick:
        return _check(check, "file_quick", name=label, path=str(path), size=size)
    try:
        sha = sha256_of(path)
    except OSError as exc:
        return _check(check, "file_unreadable", False, name=label, path=str(path), reason=exc.strerror or str(exc))
    if sha != sha_want:
        return _check(check, "file_sha", False, name=label, path=str(path), sha256=sha, expected=sha_want)
    return _check(check, "file_ok", name=label, path=str(path), size=size)


def _installation(profile, lang) -> list:
    checks = []
    try:
        record = install.read_install()
    except GvoiceError as exc:
        return [_check("install", "install_unreadable", False, error=exc.message(lang))]
    if record is None:
        return [_check("install", "install_missing", False, path=str(install.engine_dir()))]
    devices = record["devices"]
    checks.append(_check("install", "install_ok", commit=record["commit"], devices=", ".join(devices) or "-",
                         installed_at=record["installedAt"]))
    if record["commit"] != install.ENGINE_COMMIT:
        checks.append(_check("commit", "commit_differs", True, True, commit=record["commit"],
                             expected=install.ENGINE_COMMIT))
    else:
        checks.append(_check("commit", "commit_ok", commit=record["commit"]))
    for device in devices:
        for program in ("qwen-tts", "qwen-codec"):
            try:
                path = install.binary(program, device)
            except GvoiceError as exc:
                checks.append(_check("binary", "binary_bad_device", False, program=program, device=device,
                                     error=exc.message(lang)))
                continue
            if not path.is_file():
                checks.append(_check("binary", "binary_missing", False, program=program, device=device,
                                     path=str(path)))
            elif not os.access(path, os.X_OK):
                checks.append(_check("binary", "binary_not_executable", False, program=program, device=device,
                                     path=str(path)))
            else:
                checks.append(_check("binary", "binary_ok", program=program, device=device, path=str(path)))
    if profile is not None:
        have = {d.lower() for d in devices}
        cfg = profile.get("engine") or {}
        for role in ("device", "fallbackDevice"):
            name = cfg.get(role)
            if name and name.lower() not in have:
                checks.append(_check("profile_device", "profile_device_missing", True, True, role=role,
                                     device=name, installed=", ".join(devices) or "-"))
    return checks


def run(quick: bool = False, lang: str = "en") -> list:
    try:
        name = engine_mod._configured_engine()
    except GvoiceError as exc:
        return [_check("engine", "engine_unreadable", False, error=exc.message(lang))]
    checks = []
    known = name in ("fake", "qwentts")
    checks.append(_check("engine", "engine_ok" if known else "engine_unknown", known, engine=name))
    profile = None
    try:
        profile = limits.load_machine()
    except GvoiceError as exc:
        checks.append(_check("profile", "profile_bad", False, error=exc.message(lang)))
    else:
        cfg, models = profile.get("engine") or {}, profile.get("models") or {}
        checks.append(_check("profile", "profile_ok", name=profile.get("name", "-"), device=cfg.get("device", "-"),
                             fallback=cfg.get("fallbackDevice") or "-", design=models.get("design", "-"),
                             produce=", ".join(models.get("produce") or []) or "-"))
    if name == "qwentts":
        checks.extend(_installation(profile, lang))
        for model, file in install.MODEL_FILES.items():
            checks.append(_file("model", model, install.model_path(model), install.MODEL_SHA256[file], quick))
        checks.append(_file("codec", "codec", install.codec_path(), install.MODEL_SHA256[install.CODEC_FILE], quick))
    return checks

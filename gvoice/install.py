"""Where the real engine lives: build folders, model files and the install record (F2.1).

Nothing is downloaded or executed here; this module only says where things are and what they should be."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import paths
from .errors import GvoiceError

ENGINE_COMMIT = "5916bf7c79dbb4e66fc059cdc507a79a23a28bb4"

MODEL_FILES = {
    "0.6b-base": "qwen-talker-0.6b-base-Q8_0.gguf",
    "1.7b-base": "qwen-talker-1.7b-base-Q8_0.gguf",
    "1.7b-voicedesign": "qwen-talker-1.7b-voicedesign-Q8_0.gguf",
}
CODEC_FILE = "qwen-tokenizer-12hz-Q8_0.gguf"

# file name -> (size in bytes, sha256); from docs/investigacion/2026-10-25-banco-deck.md
MODEL_SHA256 = {
    "qwen-talker-0.6b-base-Q8_0.gguf": (
        992615488, "d54dbaf10591421fa764ed630d764efa717ae40cd959bd48c66d4eb1af226426"),
    "qwen-talker-1.7b-base-Q8_0.gguf": (
        2079448256, "4b9a33a236908dd9435a42f7a396e38038329d053b704342a6413c08544c4fda"),
    "qwen-talker-1.7b-voicedesign-Q8_0.gguf": (
        2042833824, "575610ab1ddcca4dca6bd9a64bcd859d93bbad8764f9cab24e1dbc0c51f62276"),
    CODEC_FILE: (291150624, "1883beeed99348fc35e23dd225e9082f93f6f8c109330a33d935baa8acdbfd94"),
}

BINARIES = ("qwen-tts", "qwen-codec", "tts-server")
INSTALL_FILE = "install.json"


def engine_dir() -> Path:
    return paths.engine_dir()


def models_dir() -> Path:
    """Same as `paths.models_dir`: ``$GVOICE_MODELS_HOME`` if set, else ``<data>/models``."""
    return paths.models_dir()


def bin_dir(device: str) -> Path:
    """``bin-vulkan`` for a device starting with ``Vulkan`` (any case), ``bin-cpu`` for ``cpu``/``CPU``."""
    name = str(device)
    if name.lower().startswith("vulkan"):
        return engine_dir() / "bin-vulkan"
    if name.lower() == "cpu":
        return engine_dir() / "bin-cpu"
    raise GvoiceError("install.unknown_device", device=name)


def binary(name: str, device: str) -> Path:
    if name not in BINARIES:
        raise GvoiceError("install.unknown_binary", binary=str(name), binaries=", ".join(BINARIES))
    return bin_dir(device) / name


def model_path(name: str) -> Path:
    if name not in MODEL_FILES:
        raise GvoiceError("install.unknown_model", model=str(name), models=", ".join(MODEL_FILES))
    return models_dir() / MODEL_FILES[name]


def codec_path() -> Path:
    return models_dir() / CODEC_FILE


def read_install() -> Optional[dict]:
    """``engine/install.json`` (``{"commit", "devices", "installedAt"}``); None if there is none."""
    path = engine_dir() / INSTALL_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise GvoiceError("install.unreadable", path=str(path), reason=str(exc))
    if (not isinstance(data, dict) or not isinstance(data.get("commit"), str)
            or not isinstance(data.get("installedAt"), str)
            or not isinstance(data.get("devices"), list) or not all(isinstance(d, str) for d in data["devices"])):
        raise GvoiceError("install.unreadable", path=str(path), reason="unexpected content")
    return data

"""Message lookup with es/en texts and fallback.

Kept as its own module on purpose (R3): `grun.i18n` looks texts up only in `grun/locales/` and reads
``GALIVELOP_LANG``, while gvoice needs its own es/en texts (`gvoice/locales/`) and ``GVOICE_LANG``. Same lookup
semantics otherwise. It can go when grun takes a locales folder and a language variable as parameters."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_LOCALES = Path(__file__).parent / "locales"
_cache = {}
FALLBACK = "en"


def available() -> frozenset:
    """Languages that have a texts file in locales/."""
    return frozenset(p.stem for p in _LOCALES.glob("*.json"))


def normalise(value: str) -> str:
    """`es_ES.UTF-8` -> `es`; a language without a texts file -> the fallback."""
    lang = re.split(r"[_.@:-]", value.strip().lower())[0]
    return lang if lang in available() else FALLBACK


def default_lang() -> str:
    explicit = os.environ.get("GVOICE_LANG")
    if explicit:
        return normalise(explicit)
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return normalise(value)
    return FALLBACK


def _load(lang: str) -> dict:
    if lang not in available():
        return {}
    if lang not in _cache:
        path = _LOCALES / (lang + ".json")
        try:
            with open(path, encoding="utf-8") as fh:
                _cache[lang] = json.load(fh)
        except (OSError, ValueError):
            _cache[lang] = {}
    return _cache[lang]


def t(key: str, lang: str | None = None, **params) -> str:
    lang = lang or default_lang()
    for candidate in (lang, FALLBACK):
        text = _load(candidate).get(key)
        if text is not None:
            return text.format(**params)
    return key

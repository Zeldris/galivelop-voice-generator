"""Message lookup with es/en texts and fallback.

Adapted from gvoice@8a17618 gvoice/i18n.py (GVOICE_LANG -> GALIVELOP_LANG, with the old name as an alias)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_LOCALES = Path(__file__).parent / "locales"
_cache = {}
FALLBACK = "en"
LANG_ENV = "GALIVELOP_LANG"
LANG_ENV_ALIAS = "GVOICE_LANG"  # TODO(R3): remove the alias when gvoice migrates to grun


def available() -> frozenset:
    """Languages that have a texts file in locales/."""
    return frozenset(p.stem for p in _LOCALES.glob("*.json"))


def normalise(value: str) -> str:
    """`es_ES.UTF-8` -> `es`; a language without a texts file -> the fallback."""
    lang = re.split(r"[_.@:-]", value.strip().lower())[0]
    return lang if lang in available() else FALLBACK


def default_lang() -> str:
    explicit = os.environ.get(LANG_ENV) or os.environ.get(LANG_ENV_ALIAS)
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


class _Keep(dict):
    """Parameters for `format_map`: a missing name keeps its ``{name}`` placeholder."""

    def __missing__(self, name):
        return "{" + name + "}"


def t(key: str, lang: str | None = None, **params) -> str:
    """Text of `key` in `lang` (else the fallback, else the key) filled with `params`; a placeholder without its
    parameter stays as it is, and a text that cannot be formatted is returned raw."""
    lang = lang or default_lang()
    for candidate in (lang, FALLBACK):
        text = _load(candidate).get(key)
        if text is not None:
            try:
                return text.format_map(_Keep(params))
            except (KeyError, IndexError, ValueError, AttributeError, TypeError):
                return text
    return key

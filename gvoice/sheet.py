"""Design sheet (D11): the instruct for the design model, and the drift warnings.

New in gvoice (no origin in gimg).

`build_instruct(sheet)` writes the keys present, in the order of ``design-sheet.schema.json`` (read from the
schema, not repeated here), as one English sentence ``A voice with gender: male; age: adult; ...; <extra name>:
<text>.`` with the ``extra`` entries last, in the order they are given. Blank values are skipped.

`warnings(sheet)` returns ``[{"code", "params"}]``; it only warns, it never blocks (D11):
- ``sheet.age_missing``: no ``age`` (or a blank one).
- ``sheet.age_minor`` (params ``age``): the age is not an adult one. Decided here: it is not adult if, as whole
  words and ignoring case, it contains one of `MINOR_WORDS` (child, kid, teen, ...), or any whole number below 18
  (``12``, ``under 16``). ``young``, ``adult``, ``young adult`` and ``30s`` are not flagged.
- ``sheet.banned_word`` (params ``word``, ``suggestion``, ``field``): one per distinct word of `BANNED_WORDS` found
  in any value of the sheet (including ``extra``), whole words and ignoring case: ``bright`` matches ``Bright``
  and ``bright-eyed``, not ``brightness``. ``field`` is the first key where it appears, in instruct order.
  Words come in the order of `BANNED_WORDS`.
"""
from __future__ import annotations

import re

from . import i18n, schema
from .errors import GvoiceError

# D11: words that push the model towards a childlike voice, each with the suggestion that replaces it.
# The only place they are written down.
BANNED_WORDS = {
    "bright": "airy",
    "cute": "soft-spoken",
    "small": "soft-spoken",
    "light": "airy",
    "childlike": "breathy",
    "high-pitched": "whispering",
}
MINOR_WORDS = (
    "child", "children", "kid", "kids", "boy", "girl", "teen", "teens", "teenage", "teenager", "adolescent",
    "minor", "juvenile", "infant", "baby", "toddler", "preteen", "tween", "schoolboy", "schoolgirl",
)
ADULT_AGE = 18
_META = ("$schema", "extra")


def _words(text: str, words) -> list:
    return [w for w in words if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(w), text, re.I)]


def keys() -> list:
    """The template keys, in instruct order: the properties of the design sheet schema."""
    return [k for k in schema.load_schema("design-sheet")["properties"] if k not in _META]


def _check(sheet) -> dict:
    errors = schema.validate(sheet, schema.load_schema("design-sheet"))
    if errors:
        raise GvoiceError("sheet.invalid", errors=errors)
    return sheet


def _entries(sheet) -> list:
    """(field, text) pairs in instruct order: the template keys, then extra."""
    found = [(k, sheet[k].strip()) for k in keys() if k in sheet]
    found += [(k, v.strip()) for k, v in sheet.get("extra", {}).items()]
    return [(k, v) for k, v in found if v]


def build_instruct(sheet: dict) -> str:
    _check(sheet)
    parts = ["%s: %s" % (k, v) for k, v in _entries(sheet)]
    return "A voice with %s." % "; ".join(parts) if parts else "A voice."


def _is_minor(age: str) -> bool:
    if _words(age, MINOR_WORDS):
        return True
    return any(int(n) < ADULT_AGE for n in re.findall(r"(?<![A-Za-z0-9])\d+(?![A-Za-z0-9])", age))


def warnings(sheet: dict) -> list:
    _check(sheet)
    found = []
    entries = _entries(sheet)
    age = dict(entries).get("age")
    if age is None:
        found.append({"code": "sheet.age_missing", "params": {}})
    elif _is_minor(age):
        found.append({"code": "sheet.age_minor", "params": {"age": age}})
    for word, suggestion in BANNED_WORDS.items():
        for field, text in entries:
            if _words(text, [word]):
                found.append({"code": "sheet.banned_word",
                              "params": {"word": word, "suggestion": suggestion, "field": field}})
                break
    return found


def message(warning: dict, lang: str | None = None) -> str:
    """The warning as text in `lang` (texts ``warning.<code>``)."""
    return i18n.t("warning." + warning["code"], lang, **warning["params"])

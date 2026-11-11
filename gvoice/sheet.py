"""From a design sheet to the English voice instruction, plus childlike-drift warnings (D11).

New module (not copied from gimg). A sheet is a dict that follows `design-sheet.schema.json`: the 12 template keys
(all optional) and a free-form `extra` map.

`instruction(sheet)` joins the present keys in the fixed order of the schema's `properties` (the single place that
lists them) and then the `extra` entries in their own order, as ``Key: value.`` sentences separated by a space;
absent keys are omitted. `warnings(sheet)` returns `Warning` items (never an error: D11) for

* ``sheet.age_missing``: the sheet says no age;
* ``sheet.age_not_adult``: the age is not clearly adult (see `is_adult`);
* ``sheet.banned_word``: one of `BANNED_WORDS` appears as a whole word, in any field, `extra` values included.

What counts as adult (`is_adult`), because the instruct is free text: the age is lower-cased and cut into words.
A number below 18 (``12 years old``) is not adult. A child word (`child`, `kid`, `teen*`, `boy`, `girl`, `youth*`,
`juvenile`, `minor`, `underage`, `baby`, `infant`, `toddler`, `adolescent`, `tween`, `childlike`, `childish`) is
not adult, even next to an adult word (``child-like adult``). ``young`` is not adult unless it is followed by
``adult`` (``young adult`` is adult; ``young man`` and ``young voice`` are not). Otherwise it is adult when it holds
an adult word (`adult`, `middle-aged`, `elderly`, `old`, `senior`, `mature`, `aged`, `man`, `woman`, a number of 18 or
more, ``20s``/``thirties``...). Anything else (``ageless``) is not adult: only positive evidence silences the warning."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import i18n, schema
from .errors import GvoiceError

BANNED_WORDS = ("bright", "cute", "small", "light", "childlike", "high-pitched")
SUGGESTIONS = ("airy", "breathy", "soft-spoken", "whispering")

_CHILD = re.compile(r"^(child\w*|kids?|teen\w*|boys?|girls?|youth\w*|juveniles?|minors?|underage|babys?|babies|"
                    r"infants?|toddlers?|adolescent\w*|tweens?|preteens?)$")
_ADULT = re.compile(r"^(adults?|middle|aged|elderly|old|older|senior|mature|men|man|women|woman|"
                    r"(twen|thir|for|fif|six|seven|eight|nine)ties|[2-9]0s|"
                    r"(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\w*)$")
_WORD = re.compile(r"[a-z0-9]+")
_BANNED = {w: re.compile(r"(?<![a-z0-9])" + r"[\s-]+".join(map(re.escape, w.split("-"))) + r"(?![a-z0-9])")
           for w in BANNED_WORDS}


@dataclass
class Warning:
    """A non-blocking notice: `code` picks the text ``warning.<code>``, `params` fill it."""
    code: str
    params: dict = field(default_factory=dict)

    def message(self, lang: str | None = None) -> str:
        return i18n.t("warning." + self.code, lang, **self.params)


def _fields(sheet: dict) -> list:
    """The ``(name, value)`` pairs in instruction order: template keys, then `extra`."""
    props = schema.load_schema("design-sheet")["properties"]
    keys = [k for k in props if k not in ("$schema", "extra")]
    pairs = [(k, sheet[k]) for k in keys if k in sheet]
    pairs += list((sheet.get("extra") or {}).items())
    return pairs


def _checked(sheet) -> dict:
    errors = schema.validate(sheet, schema.load_schema("design-sheet"))
    if errors:
        raise GvoiceError("sheet.invalid", errors=errors)
    return sheet


def instruction(sheet: dict) -> str:
    """The English instruction: ``Gender: male. Age: ...`` in the fixed order, absent keys omitted."""
    parts = []
    for name, value in _fields(_checked(sheet)):
        text = value.strip().rstrip(".").strip()
        if text:
            parts.append("%s: %s." % (name[:1].upper() + name[1:], text))
    return " ".join(parts)


def is_adult(age) -> bool:
    """Whether `age` (free text) is clearly an adult age; the rules are in the module docstring."""
    if not isinstance(age, str):
        return False
    words = _WORD.findall(age.lower())
    numbers = [int(w) for w in words if w.isdigit()]
    if any(n < 18 for n in numbers):
        return False
    for i, word in enumerate(words):
        if _CHILD.match(word):
            return False
        if word == "young" and words[i + 1:i + 2] != ["adult"]:
            return False
    return any(_ADULT.match(w) for w in words) or any(n >= 18 for n in numbers)


def banned_words(text: str) -> list:
    """The banned words that appear in `text` as whole words, case-insensitive, in `BANNED_WORDS` order."""
    low = text.lower()
    return [w for w, rx in _BANNED.items() if rx.search(low)]


def warnings(sheet: dict) -> list:
    """The `Warning` items of `sheet`; an empty list when there is nothing to say."""
    out = []
    age = _checked(sheet).get("age")
    if not age or not age.strip():
        out.append(Warning("sheet.age_missing"))
    elif not is_adult(age):
        out.append(Warning("sheet.age_not_adult", {"age": age}))
    suggestions = ", ".join(SUGGESTIONS)
    for name, value in _fields(sheet):
        for word in banned_words(value):
            out.append(Warning("sheet.banned_word", {"word": word, "field": name, "suggestions": suggestions}))
    return out

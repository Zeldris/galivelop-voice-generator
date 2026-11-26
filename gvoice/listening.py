"""The listening sheet of a take (0.4.3): what a person marks after listening, criterion by criterion.

`DEFAULTS` are the five criteria of the research (one place); a project replaces the whole list with
``listening.criteria`` in its configuration. A take stores ``listening: {marks: {<id>: "yes"|"no"}, note, at}``; a
criterion without a mark is "not heard". A "no" on an eliminatory criterion warns when the take is chosen
(``listening.eliminatory_failed``) but never prevents it."""
from __future__ import annotations

from . import i18n, projects
from .errors import GvoiceError

MARKS = ("yes", "no")

# (id, eliminatory); the label of each comes from the text ``listening.criterion.<id>`` of gvoice/locales/.
DEFAULTS = (
    ("theta", True),
    ("accent", True),
    ("clean", True),
    ("tone", False),
    ("stable", False),
)


def default_criteria() -> list:
    """The default criteria as ``{id, eliminatory}`` (no ``label``: the translated text is used)."""
    return [{"id": i, "eliminatory": e} for i, e in DEFAULTS]


def criteria(project: str | None = None) -> list:
    """The effective criteria of `project` (the defaults when it has no ``listening.criteria``, or `project` is
    ``None``): ``{id, eliminatory}`` plus ``label`` when the project gives one."""
    if project is not None:
        custom = (projects.get(project)["config"].get("listening") or {}).get("criteria")
        if custom is not None:
            return [dict(c, eliminatory=bool(c.get("eliminatory"))) for c in custom]
    return default_criteria()


def label(criterion: dict, lang: str | None = None) -> str:
    """The project's own ``label`` as is, else the translated text of a default id (else the id)."""
    if criterion.get("label"):
        return criterion["label"]
    key = "listening.criterion." + criterion["id"]
    text = i18n.t(key, lang)
    return criterion["id"] if text == key else text


def check_ids(project: str, ids) -> None:
    """Raise ``listening.criterion_unknown`` for the first id that is not an effective criterion."""
    known = [c["id"] for c in criteria(project)]
    for i in ids:
        if i not in known:
            raise GvoiceError("listening.criterion_unknown", criterion=str(i), known=", ".join(known))


def eliminatory_failed(project: str, take: dict) -> list:
    """Ids of the eliminatory criteria marked "no" on `take`, in criteria order."""
    marks = (take.get("listening") or {}).get("marks") or {}
    return [c["id"] for c in criteria(project) if c["eliminatory"] and marks.get(c["id"]) == "no"]


def warnings(project: str, take: dict) -> list:
    """``[{code, params}]``: ``listening.eliminatory_failed`` with the ids, when there are any."""
    failed = eliminatory_failed(project, take)
    return [{"code": "listening.eliminatory_failed", "params": {"ids": ", ".join(failed)}}] if failed else []


def view(project: str, take: dict, lang: str | None = None) -> list:
    """One row per effective criterion: ``{id, label, eliminatory, mark}`` (``mark``: yes, no or ``None``)."""
    marks = (take.get("listening") or {}).get("marks") or {}
    return [{"id": c["id"], "label": label(c, lang), "eliminatory": c["eliminatory"], "mark": marks.get(c["id"])}
            for c in criteria(project)]


def summary(project: str, take: dict) -> dict | None:
    """``{yes, no, total, noIds}`` over the effective criteria, or ``None`` when nothing was marked or written."""
    sheet = take.get("listening")
    if not sheet or not (sheet.get("marks") or sheet.get("note")):
        return None
    marks = sheet.get("marks") or {}
    ids = [c["id"] for c in criteria(project)]
    return {"yes": sum(marks.get(i) == "yes" for i in ids), "no": sum(marks.get(i) == "no" for i in ids),
            "total": len(ids), "noIds": [i for i in ids if marks.get(i) == "no"]}

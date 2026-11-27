"""Errors that carry a stable code plus parameters, so any front end can render them.

Adapter over `grun.errors` (R3): `GvoiceError` is a `grun.errors.GrunError` that renders with the texts of gvoice
(`gvoice/locales/`, `gvoice.i18n`) and carries schema errors. `PathError` is also a `grun.errors.PathError`, so code that
catches the grun class catches gvoice's too; `from_grun` turns an error raised inside grun into the gvoice one."""
from __future__ import annotations

from grun import errors as _grun

from . import i18n


class GvoiceError(_grun.GrunError):
    """A user-facing error: `code` picks the text `error.<code>`, `params` fill it."""

    def __init__(self, code: str, errors=(), **params):
        super().__init__(code, **params)
        self.errors = list(errors)  # schema ValidationError items, if any

    def message(self, lang: str | None = None) -> str:
        from . import schema

        text = i18n.t("error." + self.code, lang, **self.params)
        lines = [schema.format_error(e, lang) for e in self.errors]
        return "\n".join([text] + lines)

    def __str__(self):
        return "%s %r" % (self.code, self.params)


class PathError(GvoiceError, _grun.PathError):
    """A path from outside (project file, order) failed the D25 guard."""


def from_grun(exc: _grun.GrunError) -> GvoiceError:
    """The gvoice error with the code and parameters of an error raised by grun (rendered with gvoice's texts)."""
    cls = PathError if isinstance(exc, _grun.PathError) else GvoiceError
    return cls(exc.code, **exc.params)

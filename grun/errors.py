"""Errors that carry a stable code plus parameters, so any front end can render them.

Adapted from gvoice@8a17618 gvoice/errors.py (GvoiceError -> GrunError, no schema errors)."""
from __future__ import annotations

from . import i18n


class GrunError(Exception):
    """A user-facing error: `code` picks the text ``error.<code>``, `params` fill it."""

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params

    def message(self, lang: str | None = None) -> str:
        return i18n.t("error." + self.code, lang, **self.params)

    def __str__(self):
        return "%s %r" % (self.code, self.params)


class PathError(GrunError):
    """A path from outside failed the path guard (`grun.paths.inside`)."""

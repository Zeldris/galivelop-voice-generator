"""Language variants of a voice (``locale`` of a ``voice`` order).

Each locale gives the engine's language name and a fixed English phrase for the instruct. The phrase is fixed, not
free text: the same words must reach every take of every voice of that locale, so a variant never depends on how the
author phrased the ``accent`` field. A line has no locale of its own: it uses the one of its voice's reference take.
"""
LOCALES = {
    "es-ES": ("Spanish", "Castilian Spanish from Spain, peninsular pronunciation with distinción "
                         "(θ for z/ce/ci), not Latin American"),
    "es-419": ("Spanish", "Latin American Spanish, seseo (z/ce/ci pronounced as s), not Castilian from Spain"),
    "en-US": ("English", "American English, General American pronunciation"),
    "en-GB": ("English", "British English, Received Pronunciation, not American"),
}


def _entry(locale):
    if locale not in LOCALES:
        raise ValueError("unknown locale: %r" % (locale,))  # the order schema keeps others out
    return LOCALES[locale]


def language(locale):
    """The engine's language name of `locale`, or ``None`` for no locale (the engine's default)."""
    return None if locale is None else _entry(locale)[0]


def phrase(locale) -> str:
    """The fixed instruct phrase of `locale`."""
    return _entry(locale)[1]

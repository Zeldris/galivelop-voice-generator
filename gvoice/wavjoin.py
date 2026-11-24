"""Sentence splitting and WAV joining for ``split`` lines (0.3.0 C3).

A line with ``split: true`` is spoken sentence by sentence, each one a call to the engine, and the pieces are joined
with a silence between them (`GAP_MS`). Long texts then keep the engine's intonation per sentence instead of
drifting. Only the standard library (D1): PCM WAVs read and written with `wave`."""

import re
import wave
from pathlib import Path

from . import fsutil
from .errors import GvoiceError

GAP_MS = 450  # silence between two sentences

# A sentence ends at . ! ? … (several allowed, plus closing quotes or brackets) followed by a blank or the end.
_SENTENCE = re.compile(r"""[^\n]+?(?:[.!?…]+["'”’»)\]]*(?=\s|$)|$)""")


def split_sentences(text: str) -> list:
    """The sentences of `text`, stripped and without empty ones; a line break also ends one. A text without a
    sentence end gives one piece."""
    pieces = (m.group().strip() for line in (text or "").split("\n") for m in _SENTENCE.finditer(line))
    return [p for p in pieces if p]


def join(sources, output, gap_ms: int = GAP_MS) -> int:
    """Join the PCM WAVs `sources` into `output` with `gap_ms` of silence between them; returns the length in ms.

    They must share channels, sample width and rate (``engine.split_format`` otherwise: a mix would be noise).
    `output` is written atomically and must not be one of the sources."""
    sources = [Path(s) for s in sources]
    if not sources:
        raise GvoiceError("engine.split_format", path="", reason="no pieces")
    frames, params = [], None
    for source in sources:
        try:
            with wave.open(str(source), "rb") as w:
                got = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                data = w.readframes(w.getnframes())
        except (wave.Error, EOFError, OSError) as exc:
            raise GvoiceError("engine.split_format", path=str(source), reason=str(exc))
        if params is not None and got != params:
            raise GvoiceError("engine.split_format", path=str(source),
                              reason="%s differs from %s" % (got, params))
        params = got
        frames.append(data)
    channels, width, rate = params
    silence = b"\x00" * (channels * width * (rate * gap_ms // 1000))
    body = silence.join(frames)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with fsutil.atomic_output(out) as tmp:
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(body)
    return int(round(len(body) / (channels * width) * 1000 / rate))

"""Checks without listening (0.4.2): metrics of a take's audio and non-blocking warnings, stdlib only.

`analyze(source, text)` reads a PCM 16-bit WAV (mono or stereo; `source` is a path or a binary file object) and returns
the metrics: ``audioMs``, ``chars`` (characters of the text, runs of whitespace counted as one space, ends trimmed),
``msPerChar``, ``peakDbfs``, ``rmsDbfs`` (of the voiced windows only), ``clippedRatio`` (samples at -32768 or +-32767),
``leadingSilenceMs``, ``longestInnerSilenceMs`` and ``trailingSilenceMs``. A window is 20 ms of all channels; it is
silent when its RMS is below ``silenceDbfs``. Levels are floored at `FLOOR_DBFS` (digital silence) so they are always
JSON numbers. With no voiced window at all the whole audio counts as leading silence. The work is done per window and
per chunk with C-speed builtins (``sum(map(mul, ...))``, ``max``, ``count``), never sample by sample in Python.

`warnings(metrics, thresholds)` gives ``{"code", "params"}`` items (``take.too_fast``, ``take.too_slow``,
``take.long_silence``, ``take.trailing_silence``, ``take.clipping``, ``take.too_quiet``; text in the locales as
``warning.<code>``). They never block anything.

`for_take` is what a take stores: ``{"sha256", "checks"}``; ``checks`` is the metrics plus ``warnings``, or, when the
audio cannot be analysed, ``{"error": "<code>"}`` (the take is recorded all the same).

Thresholds: `DEFAULTS` is the single place for their values; the project configuration (``checks`` in
``project-config.schema.json``) overrides them field by field. The values are a first guess, **por afinar en la Deck**
(listening to real takes)."""
from __future__ import annotations

import array
import hashlib
import math
import operator
import sys
import wave

from . import projects

DEFAULTS = {
    "silenceDbfs": -50,          # a 20 ms window with RMS below this is silence
    "msPerCharMin": 35,          # below: the speech is too fast
    "msPerCharMax": 180,         # above: too slow
    "innerSilenceMaxMs": 1200,   # longest silence between voiced stretches
    "trailingSilenceMaxMs": 1500,
    "clippedRatioMax": 0.001,    # share of samples at full scale
    "rmsDbfsMin": -40,           # RMS of the voiced windows below this: too quiet
}
METRICS = ("audioMs", "chars", "msPerChar", "peakDbfs", "rmsDbfs", "clippedRatio", "leadingSilenceMs",
           "longestInnerSilenceMs", "trailingSilenceMs")  # the keys `analyze` returns, in display order
WINDOW_MS = 20
FLOOR_DBFS = -120.0
FULL_SCALE = 32768.0
UNREADABLE = "take.analysis_unreadable"
UNSUPPORTED = "take.analysis_unsupported"


class ChecksError(ValueError):
    """The audio cannot be analysed; `code` is what a take stores in ``checks.error``."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def thresholds(project: str | None = None) -> dict:
    """`DEFAULTS` over the project's ``checks`` (a new dict); only the defaults when `project` is ``None``."""
    out = dict(DEFAULTS)
    if project is not None:
        out.update(projects.get(project)["config"].get("checks") or {})
    return out


def _db(value: float) -> float:
    return FLOOR_DBFS if value <= 0 else max(FLOOR_DBFS, round(20 * math.log10(value / FULL_SCALE), 1))


def _samples(source) -> tuple:
    """``(samples, channels, rate)``: every sample, little-endian 16-bit, channels interleaved."""
    try:
        with wave.open(source if hasattr(source, "read") else str(source), "rb") as w:
            chans, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            if width != 2 or chans not in (1, 2) or rate < 1:
                raise ChecksError(UNSUPPORTED, "only PCM 16-bit mono or stereo")
            data = w.readframes(w.getnframes())
    except (wave.Error, EOFError, OSError) as exc:
        raise ChecksError(UNREADABLE, str(exc)) from exc
    samples = array.array("h")
    samples.frombytes(data[:len(data) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples, chans, rate


def analyze(source, text: str, limits: dict | None = None) -> dict:
    """The metrics of the WAV `source` (path or file object) said to speak `text`; `ChecksError` if unreadable."""
    silence = dict(DEFAULTS, **(limits or {}))["silenceDbfs"]
    samples, chans, rate = _samples(source)
    frames = len(samples) // chans
    samples = samples[:frames * chans]
    step = max(1, rate * WINDOW_MS // 1000)  # frames per window
    voiced = []  # per window: (first frame, end frame) when voiced, else None
    voiced_sq = voiced_n = 0
    limit_sq = (FULL_SCALE * 10 ** (silence / 20)) ** 2
    for start in range(0, frames, step):
        win = samples[start * chans:min(start + step, frames) * chans]
        sq = sum(map(operator.mul, win, win))
        if sq / len(win) >= limit_sq:
            voiced.append((start, min(start + step, frames)))
            voiced_sq += sq
            voiced_n += len(win)
        else:
            voiced.append(None)
    peak = max(max(samples), -min(samples)) if samples else 0
    clipped = samples.count(32767) + samples.count(-32768) if samples else 0

    def ms(n):
        return n * 1000 // rate

    stretches = [v for v in voiced if v]
    if stretches:
        leading = ms(stretches[0][0])
        trailing = ms(frames - stretches[-1][1])
        inner = max((b[0] - a[1] for a, b in zip(stretches, stretches[1:])), default=0)
    else:
        leading, trailing, inner = ms(frames), 0, 0
    inner = ms(inner)
    chars = len(" ".join(text.split()))
    audio_ms = ms(frames)
    return {
        "audioMs": audio_ms, "chars": chars,
        "msPerChar": round(audio_ms / chars, 1) if chars else None,
        "peakDbfs": _db(peak),
        "rmsDbfs": _db(math.sqrt(voiced_sq / voiced_n)) if voiced_n else FLOOR_DBFS,
        "clippedRatio": round(clipped / len(samples), 6) if samples else 0.0,
        "leadingSilenceMs": leading, "longestInnerSilenceMs": inner, "trailingSilenceMs": trailing,
    }


def warnings(metrics: dict, limits: dict | None = None) -> list:
    """The warnings (``[{"code", "params"}]``) of `metrics` against `limits` (`DEFAULTS` for what is missing)."""
    t = dict(DEFAULTS, **(limits or {}))
    out = []

    def add(code, **params):
        out.append({"code": code, "params": params})

    mpc = metrics["msPerChar"]
    if mpc is not None and mpc < t["msPerCharMin"]:
        add("take.too_fast", value=mpc, limit=t["msPerCharMin"])
    if mpc is not None and mpc > t["msPerCharMax"]:
        add("take.too_slow", value=mpc, limit=t["msPerCharMax"])
    if metrics["longestInnerSilenceMs"] > t["innerSilenceMaxMs"]:
        add("take.long_silence", value=metrics["longestInnerSilenceMs"], limit=t["innerSilenceMaxMs"])
    if metrics["trailingSilenceMs"] > t["trailingSilenceMaxMs"]:
        add("take.trailing_silence", value=metrics["trailingSilenceMs"], limit=t["trailingSilenceMaxMs"])
    if metrics["clippedRatio"] > t["clippedRatioMax"]:
        add("take.clipping", value=round(metrics["clippedRatio"] * 100, 3), limit=round(t["clippedRatioMax"] * 100, 3))
    if metrics["rmsDbfs"] < t["rmsDbfsMin"]:
        add("take.too_quiet", value=metrics["rmsDbfs"], limit=t["rmsDbfsMin"])
    return out


def checks_of(source, text: str, limits: dict | None = None) -> dict:
    """What a take stores as ``checks``: the metrics plus ``warnings``, or ``{"error": code}`` if unreadable."""
    try:
        metrics = analyze(source, text, limits)
    except ChecksError as exc:
        return {"error": exc.code}
    return dict(metrics, warnings=warnings(metrics, limits))


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def for_take(project: str, path, text: str) -> dict:
    """``{"sha256", "checks"}`` of the audio file `path` of a take of `project` saying `text`. Never raises for a
    bad WAV (``checks`` is then ``{"error": code}``); an unreadable file is an `OSError` (the caller's file)."""
    return {"sha256": sha256_of(path), "checks": checks_of(path, text, thresholds(project))}

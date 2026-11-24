"""Effect chain -> ffmpeg `-af` filter graph (D12) and its application to a WAV file.

Only the cleaning steps and the simple ones are compiled here (F3 brings the rest): highpass, lowpass, equalizer,
gain, denoise, dereverb, trimSilence and loudnorm. Any other type raises ``effects.unsupported``.

`dereverb` has no exact ffmpeg counterpart: it is a soft downward expander (`agate`) that cuts the reverb tail in
the gaps between words; it does not remove the reverb that sits on top of speech."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import struct
from pathlib import Path

from . import fsutil, schema
from .errors import GvoiceError

DEFAULT_TRUE_PEAK = -1.5
DEFAULT_LRA = 11.0
PRESETS = Path(__file__).resolve().parent / "effect_presets"
_PRESET_NAME = re.compile(r"[a-z0-9_-]+")
_SUPPORTED = ("highpass", "lowpass", "equalizer", "gain", "denoise", "dereverb", "trimSilence", "loudnorm")


def _n(value) -> str:
    """A number as ffmpeg wants it: no trailing zeros, no exponent."""
    return ("%.4f" % value).rstrip("0").rstrip(".")


def _finite(measured: dict) -> bool:
    """Whether every loudnorm measure used by the second pass is a finite number."""
    try:
        return all(math.isfinite(float(measured[k]))
                   for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"))
    except (KeyError, TypeError, ValueError):
        return False


def _step(step: dict, measured: dict | None) -> str:
    kind = step["type"]
    if kind not in _SUPPORTED:
        raise GvoiceError("effects.unsupported", type=kind)
    if kind in ("highpass", "lowpass"):
        return "%s=f=%s" % (kind, _n(step["freqHz"]))
    if kind == "equalizer":
        return "equalizer=f=%s:width_type=o:w=%s:g=%s" % (
            _n(step["freqHz"]), _n(step["widthOctaves"]), _n(step["gainDb"]))
    if kind == "gain":
        return "volume=%sdB" % _n(step["gainDb"])
    if kind == "denoise":
        # afftdn: nr is the reduction in dB (0.01..97); tn=1:tr=1 track the noise floor by themselves, at any level.
        return "afftdn=nr=%s:nf=-45:tn=1:tr=1" % _n(max(0.01, 30 * step["strength"]))
    if kind == "dereverb":
        s = step["strength"]
        # Expander above the room tone: ratio 1.5..6, release 300..60 ms so the tail is cut sooner.
        return "agate=threshold=0.01:ratio=%s:attack=5:release=%s:knee=4" % (_n(1.5 + 4.5 * s), _n(300 - 240 * s))
    if kind == "trimSilence":
        margin = _n(step.get("marginMs", 100) / 1000)
        one = "silenceremove=start_periods=1:start_threshold=%sdB:start_silence=%s:detection=peak" % (
            _n(step["thresholdDb"]), margin)
        return "%s,areverse,%s,areverse" % (one, one)
    text = "loudnorm=I=%s:TP=%s:LRA=%s" % (_n(step["targetLufs"]), _n(step.get("truePeakDb", DEFAULT_TRUE_PEAK)),
                                          _n(step.get("lra", DEFAULT_LRA)))
    if measured is None or not _finite(measured):
        # No second pass: silent input measures "-inf"/"inf", which loudnorm rejects. The first-pass form
        # (dynamic, no measures) is the only one that works there, and on silence it changes nothing.
        return text
    return text + ":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true" % (
        measured["input_i"], measured["input_tp"], measured["input_lra"], measured["input_thresh"],
        measured["target_offset"])


def validate(chain: dict) -> None:
    errors = schema.validate(chain, schema.load_schema("effect-chain"))
    if errors:
        raise GvoiceError("effects.invalid", errors=errors)


def compile_chain(chain: dict, measured: dict | None = None, upto: int | None = None) -> str:
    """The `-af` string of a validated chain. `measured` are the loudnorm measures of the first pass; `upto`
    keeps only the first steps (used to measure what loudnorm will receive)."""
    steps = chain["steps"][:upto]
    return ",".join(_step(s, measured) for s in steps)


def load_chain(source: str) -> dict:
    """A preset name (`lectura`) or a path to a chain JSON file."""
    path = Path(source).expanduser()
    if not path.is_file() and _PRESET_NAME.fullmatch(source):  # an existing file wins over a preset
        preset = PRESETS / (source + ".json")
        if preset.is_file():
            path = preset
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise GvoiceError("effects.unreadable", path=source, reason=str(exc))


def presets() -> list:
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise GvoiceError("effects.no_ffmpeg")
    return found


def _run(args: list) -> str:
    try:
        done = subprocess.run([_ffmpeg(), "-hide_banner", "-nostdin", "-y"] + args, capture_output=True,
                              text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise GvoiceError("effects.failed", reason=str(exc))
    if done.returncode != 0:
        raise GvoiceError("effects.failed", reason=(done.stderr.strip().splitlines() or ["?"])[-1])
    return done.stderr


def _measure(src: Path, filters: str) -> dict:
    text = _run(["-i", str(src), "-af", filters, "-f", "null", "-"])
    found = re.findall(r"\{[^{}]*\}", text, re.S)
    try:
        return json.loads(found[-1])
    except (IndexError, ValueError):
        raise GvoiceError("effects.failed", reason="loudnorm")


def _rate(src: Path) -> int | None:
    """Sample rate from the ``fmt `` chunk of a RIFF/WAVE file (any format: PCM, float, extensible), or ``None``."""
    try:
        with open(src, "rb") as fh:
            head = fh.read(12)
            if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return None
            while True:
                chunk = fh.read(8)
                if len(chunk) < 8:
                    return None
                name, size = struct.unpack("<4sI", chunk)
                if name == b"fmt " and size >= 8:
                    body = fh.read(8)
                    return struct.unpack("<HHI", body[:8])[2] or None if len(body) == 8 else None
                fh.seek(size + (size & 1), 1)
    except (OSError, struct.error):
        return None


def apply(chain: dict, src, dst) -> str:
    """Validate and run `chain` over the WAV `src`, writing `dst`; returns the `-af` used. loudnorm runs in two
    passes (measure, then linear) so the result lands on the target loudness."""
    validate(chain)
    src, dst = Path(src), Path(dst)
    compile_chain(chain)  # raises effects.unsupported (the only check of the supported types) before any ffmpeg run
    if not src.is_file():
        raise GvoiceError("effects.unreadable", path=str(src), reason="not a file")
    if dst.name in ("", ".", "..") or dst.is_dir():
        raise GvoiceError("effects.bad_output", path=str(dst))
    if dst.suffix.lower() != ".wav":
        raise GvoiceError("effects.bad_extension", path=str(dst))
    dst = Path(os.path.realpath(dst))  # a symlink as output: write to its target, so the link and its mode stay
    if src.resolve() == dst.resolve() or (dst.exists() and os.path.samefile(src, dst)):
        raise GvoiceError("effects.same_file", path=str(src))
    kinds = [s["type"] for s in chain["steps"]]
    if kinds.count("loudnorm") > 1:
        raise GvoiceError("effects.many_loudnorm")
    measured = None
    if "loudnorm" in kinds:
        upto = kinds.index("loudnorm") + 1
        measured = _measure(src, compile_chain(chain, upto=upto) + ":print_format=json")
    filters = compile_chain(chain, measured)
    rate = _rate(src)
    if rate:  # always the source rate: loudnorm resamples to 192 kHz and the output must not depend on it
        filters += ",aresample=%d" % rate
    with fsutil.atomic_output(dst) as tmp:
        _run(["-i", str(src), "-af", filters, "-c:a", "pcm_s16le", "-f", "wav", str(tmp)])
    return filters

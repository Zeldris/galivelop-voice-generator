"""Voice engines. F1 has only the fake one; the real `qwen-tts` wrapper arrives in F2.

Copiado de gimg@0d02f51 (D7); cambia: GVOICE_*, tres operaciones (`design`, `speak`, `extract_print`) con
sus jobs en vez de `generate`, WAV PCM y huellas de prueba en vez de PNG, `EngineResult` con `audio_ms` y
`device` (D16), y la espera/timeout/cancelación pasan a `_wait`.

Environment: ``GVOICE_ENGINE`` picks the engine (default ``fake``). The fake engine reads
``GVOICE_FAKE_DELAY`` (seconds to wait) and ``GVOICE_FAKE_FAIL`` (fail with that message)."""
from __future__ import annotations

import hashlib
import io
import math
import os
import struct
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import fsutil
from .errors import GvoiceError

FAKE_VERSION = "fake-1"
SAMPLE_RATE = 24000
FAKE_MS_PER_CHAR = 60  # fake audio lasts this many ms per character of text (at least one character)
FAKE_BASE_HZ = 200  # the tone is FAKE_BASE_HZ + seed % FAKE_SPAN_HZ
FAKE_SPAN_HZ = 600
_AMPLITUDE = 8000
_TICK_S = 0.02


@dataclass
class DesignJob:
    instruct: str
    text: str
    seed: int
    model: str
    output: str  # absolute path of the .wav
    device: str = "cpu"
    timeout_s: Optional[float] = None


@dataclass
class SpeakJob:
    text: str
    seed: int
    model: str
    spk: str  # absolute path of the print's .spk
    rvq: str  # absolute path of the print's .rvq
    output: str  # absolute path of the .wav
    device: str = "cpu"
    timeout_s: Optional[float] = None


@dataclass
class PrintJob:
    reference: str  # absolute path of the reference .wav
    reference_text: str
    model: str
    spk: str  # output
    rvq: str  # output
    device: str = "cpu"
    timeout_s: Optional[float] = None


@dataclass
class EngineResult:
    duration_ms: int
    engine_version: str
    device: str
    load_ms: Optional[int] = None
    audio_ms: Optional[int] = None


class EngineError(Exception):
    """The engine failed; `message` is for the log and the queue entry."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


TIMEOUT_MESSAGE = "timeout"


class EngineTimeout(EngineError):
    """The job ran past `job.timeout_s`; the message is always `TIMEOUT_MESSAGE`."""

    def __init__(self):
        super().__init__(TIMEOUT_MESSAGE)


class Cancelled(Exception):
    """`should_cancel()` returned true while generating (or while waiting for the machine lock)."""


class Engine:
    provider = ""

    def design(self, job: DesignJob, should_cancel: Callable[[], bool]) -> EngineResult:
        raise NotImplementedError

    def speak(self, job: SpeakJob, should_cancel: Callable[[], bool]) -> EngineResult:
        raise NotImplementedError

    def extract_print(self, job: PrintJob, should_cancel: Callable[[], bool]) -> EngineResult:
        raise NotImplementedError


def fake_duration_ms(text: str) -> int:
    return max(len(text), 1) * FAKE_MS_PER_CHAR


def fake_frequency(seed: int) -> int:
    return FAKE_BASE_HZ + seed % FAKE_SPAN_HZ


def wav_bytes(seed: int, duration_ms: int) -> bytes:
    """A valid 16-bit mono PCM WAV at 24 kHz: a sine tone whose frequency comes from the seed."""
    freq = fake_frequency(seed)
    frames = SAMPLE_RATE * duration_ms // 1000
    step = 2 * math.pi * freq / SAMPLE_RATE
    data = struct.pack("<%dh" % frames, *(int(_AMPLITUDE * math.sin(step * i)) for i in range(frames)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(data)
    return buf.getvalue()


def print_bytes(kind: str, model: str, reference: bytes) -> bytes:
    """Deterministic test print: depends on the kind (`spk`/`rvq`), the model and the reference's content."""
    digest = hashlib.sha256(b"\0".join((kind.encode(), model.encode(), reference))).hexdigest()
    return ("GVOICE-FAKE-%s\n%s\n" % (kind.upper(), digest)).encode()


def _write(path, data: bytes) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), prefix="." + out.name + ".", suffix=".tmp")
    try:
        fsutil.honour_umask(fd)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class FakeEngine(Engine):
    provider = "fake"

    def __init__(self, delay_s: float = 0, fail_with: Optional[str] = None):
        self.delay_s = delay_s
        self.fail_with = fail_with

    def _wait(self, start: float, timeout_s, should_cancel) -> None:
        end = start + self.delay_s
        limit = None if timeout_s is None else start + timeout_s
        while True:
            if should_cancel():
                raise Cancelled()
            now = time.monotonic()
            if limit is not None and now >= limit and end > limit:
                raise EngineTimeout()
            left = end - now
            if left <= 0:
                break
            if limit is not None and end > limit:
                left = min(left, limit - now)
            time.sleep(min(_TICK_S, left))
        if self.fail_with:
            raise EngineError(self.fail_with)

    def _result(self, start, job, audio_ms=None) -> EngineResult:
        return EngineResult(duration_ms=int((time.monotonic() - start) * 1000), engine_version=FAKE_VERSION,
                            device=job.device, load_ms=0, audio_ms=audio_ms)

    def _audio(self, job, text) -> int:
        if not isinstance(job.seed, int) or isinstance(job.seed, bool) or job.seed < 0:
            raise EngineError("invalid seed %r" % (job.seed,))
        ms = fake_duration_ms(text)
        _write(job.output, wav_bytes(job.seed, ms))
        return ms

    def design(self, job: DesignJob, should_cancel) -> EngineResult:
        start = time.monotonic()
        self._wait(start, job.timeout_s, should_cancel)
        return self._result(start, job, self._audio(job, job.text))

    def speak(self, job: SpeakJob, should_cancel) -> EngineResult:
        start = time.monotonic()
        self._wait(start, job.timeout_s, should_cancel)
        for path in (job.spk, job.rvq):
            if not Path(path).is_file():
                raise EngineError("missing print file: %s" % path)
        return self._result(start, job, self._audio(job, job.text))

    def extract_print(self, job: PrintJob, should_cancel) -> EngineResult:
        start = time.monotonic()
        self._wait(start, job.timeout_s, should_cancel)
        try:
            reference = Path(job.reference).read_bytes()
        except OSError as exc:
            raise EngineError("cannot read the reference: %s" % exc)
        _write(job.spk, print_bytes("spk", job.model, reference))
        _write(job.rvq, print_bytes("rvq", job.model, reference))
        return self._result(start, job)


def get_engine() -> Engine:
    """The engine named by ``GVOICE_ENGINE`` (default ``fake``)."""
    name = os.environ.get("GVOICE_ENGINE") or "fake"
    if name != "fake":
        raise GvoiceError("engine.unknown", engine=name)
    try:
        delay = float(os.environ.get("GVOICE_FAKE_DELAY") or 0)
    except ValueError:
        raise GvoiceError("engine.bad_delay", value=os.environ["GVOICE_FAKE_DELAY"])
    if not math.isfinite(delay) or delay < 0:
        raise GvoiceError("engine.bad_delay", value=os.environ["GVOICE_FAKE_DELAY"])
    return FakeEngine(delay_s=delay, fail_with=os.environ.get("GVOICE_FAKE_FAIL") or None)

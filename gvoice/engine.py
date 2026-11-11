"""Voice engines: the interface and the fake one (F1); the real `qwen-tts` wrapper arrives in F2.

Copiado de gimg@fa1076e (D7); adaptado a gvoice: three operations instead of one image (D10) and the result carries
what D16 asks for the log (device, seed, engine commit and model).

* `design`: instruction (from the sheet) + test text + seed -> a take (a ``.wav``).
* `line`: voice print (``.spk`` + ``.rvq``) + text + seed -> the line audio (a ``.wav``).
* `voiceprint`: reference ``.wav`` + its text + base model -> the ``.spk`` and ``.rvq`` files.

Engine choice: ``GVOICE_ENGINE``, else ``"engine"`` of ``<config>/config.json``, else ``fake``; the only value for now
is ``fake``. The fake engine reads ``GVOICE_FAKE_DELAY`` (seconds to wait) and ``GVOICE_FAKE_FAIL`` (fail with that
message). Its audio is PCM 16-bit mono 24 kHz, deterministic by seed and text, and as long as the text is."""
from __future__ import annotations

import hashlib
import io
import math
import os
import struct
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import fsutil, paths
from .errors import GvoiceError

FAKE_VERSION = "fake-1"
FAKE_COMMIT = "fake"
SAMPLE_RATE = 24000
FAKE_MS_PER_CHAR = 60  # audio length per character of text
FAKE_MIN_MS = 100
_TICK_S = 0.02


@dataclass
class DesignJob:
    instruction: str  # English, from ``sheet.instruction``
    text: str  # the test text
    seed: int
    output: str  # absolute path of the ``.wav``
    model: Optional[str] = None
    device: Optional[str] = None
    machine: dict = field(default_factory=dict)
    timeout_s: Optional[float] = None
    language: str = "auto"  # label for ``qwen-tts --lang``, from the project config


@dataclass
class LineJob:
    spk: str  # absolute path of the voice print
    rvq: str
    text: str
    seed: int
    output: str
    model: Optional[str] = None
    device: Optional[str] = None
    machine: dict = field(default_factory=dict)
    timeout_s: Optional[float] = None
    language: str = "auto"  # label for ``qwen-tts --lang``, from the project config
    ref_text: str = ""  # what the reference take says (``qwen-tts --ref-text``)


@dataclass
class PrintJob:
    reference: str  # absolute path of the reference ``.wav``
    text: str  # what the reference says
    model: str  # the base model the print is for
    spk: str  # absolute output paths
    rvq: str
    device: Optional[str] = None
    machine: dict = field(default_factory=dict)
    timeout_s: Optional[float] = None


@dataclass
class EngineResult:
    duration_ms: int
    engine_version: str
    device: Optional[str] = None  # D16: the same seed gives other takes on other devices
    seed: Optional[int] = None
    engine_commit: Optional[str] = None
    model: Optional[str] = None
    audio_ms: Optional[int] = None  # length of the audio written, if any
    load_ms: Optional[int] = None
    min_free_mb: Optional[int] = None
    command: Optional[list] = None
    backend: Optional[str] = None


class EngineError(Exception):
    """The engine failed; `message` is for the log and the queue entry. With a `code` (and its `params`) the worker
    stores that code, so the front end shows the translated ``error.<code>`` text instead of ``engine.failed``."""

    def __init__(self, message: str, code: Optional[str] = None, **params):
        super().__init__(message)
        self.message = message
        self.code = code
        self.params = params


TIMEOUT_MESSAGE = "timeout"


class EngineTimeout(EngineError):
    """The job ran past `job.timeout_s`; the message is always `TIMEOUT_MESSAGE`."""

    def __init__(self):
        super().__init__(TIMEOUT_MESSAGE)


class Cancelled(Exception):
    """`should_cancel()` returned true while generating."""


class Engine:
    provider = ""

    def design(self, job: DesignJob, should_cancel: Callable[[], bool]) -> EngineResult:
        raise NotImplementedError

    def line(self, job: LineJob, should_cancel: Callable[[], bool]) -> EngineResult:
        raise NotImplementedError

    def voiceprint(self, job: PrintJob, should_cancel: Callable[[], bool]) -> EngineResult:
        raise NotImplementedError


def _digest(*parts) -> bytes:
    h = hashlib.sha256()
    for part in parts:
        data = part if isinstance(part, bytes) else str(part).encode("utf-8")
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.digest()


def wav_bytes(seed_material: bytes, text: str) -> bytes:
    """PCM 16-bit mono 24 kHz: a tone whose pitch, vibrato and phase come from `seed_material`, as long as `text`."""
    ms = max(FAKE_MIN_MS, FAKE_MS_PER_CHAR * len(text))
    frames = SAMPLE_RATE * ms // 1000
    freq = 110 + int.from_bytes(seed_material[0:2], "big") % 300
    vib = 2 + seed_material[2] % 6
    phase = int.from_bytes(seed_material[3:5], "big") / 65536 * 2 * math.pi
    samples = []
    for i in range(frames):
        t = i / SAMPLE_RATE
        fade = min(1.0, i / 240, (frames - 1 - i) / 240)
        value = math.sin(2 * math.pi * freq * t + phase + 3 * math.sin(2 * math.pi * vib * t))
        samples.append(int(9000 * fade * value))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return buf.getvalue()


def _write_atomic(path, data: bytes) -> None:
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


def _device(job) -> str:
    return job.device or (job.machine.get("engine") or {}).get("device") or "cpu"


class FakeEngine(Engine):
    provider = "fake"

    def __init__(self, delay_s: float = 0, fail_with: Optional[str] = None):
        self.delay_s = delay_s
        self.fail_with = fail_with

    def _wait(self, job, should_cancel) -> float:
        start = time.monotonic()
        end = start + self.delay_s
        limit = None if job.timeout_s is None else start + job.timeout_s
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
        return start

    def _result(self, start, job, seed=None, model=None, audio_ms=None) -> EngineResult:
        return EngineResult(duration_ms=int((time.monotonic() - start) * 1000), engine_version=FAKE_VERSION,
                            device=_device(job), seed=seed, engine_commit=FAKE_COMMIT, model=model,
                            audio_ms=audio_ms, load_ms=0, backend="fake")

    def design(self, job: DesignJob, should_cancel) -> EngineResult:
        start = self._wait(job, should_cancel)
        model = job.model or "1.7b-voicedesign"
        data = wav_bytes(_digest("design", model, _device(job), job.seed, job.instruction, job.text), job.text)
        _write_atomic(job.output, data)
        return self._result(start, job, job.seed, model, _audio_ms(job.text))

    def line(self, job: LineJob, should_cancel) -> EngineResult:
        start = self._wait(job, should_cancel)
        try:
            spk, rvq = Path(job.spk).read_bytes(), Path(job.rvq).read_bytes()
        except OSError:
            missing = job.spk if not Path(job.spk).is_file() else job.rvq
            raise EngineError("voice print missing: %s" % missing, "engine.print_missing", path=missing)
        model = job.model or "0.6b-base"
        data = wav_bytes(_digest("line", model, _device(job), job.seed, spk, rvq, job.text), job.text)
        _write_atomic(job.output, data)
        return self._result(start, job, job.seed, model, _audio_ms(job.text))

    def voiceprint(self, job: PrintJob, should_cancel) -> EngineResult:
        start = self._wait(job, should_cancel)
        try:
            audio = Path(job.reference).read_bytes()
        except OSError:
            raise EngineError("cannot read %s" % job.reference, "engine.reference_unreadable", path=job.reference)
        key = hashlib.sha256(audio).hexdigest()
        _write_atomic(job.spk, b"FAKE-SPK\n" + _digest("spk", key, job.model).hex().encode() + b"\n")
        _write_atomic(job.rvq, b"FAKE-RVQ\n" + b"".join(_digest("rvq", key, job.model, i).hex().encode() + b"\n"
                                                         for i in range(8)))
        return self._result(start, job, None, job.model)


def _audio_ms(text: str) -> int:
    return max(FAKE_MIN_MS, FAKE_MS_PER_CHAR * len(text))


def _configured_engine() -> str:
    """``GVOICE_ENGINE``, else ``"engine"`` of ``<config>/config.json``, else ``fake``."""
    name = os.environ.get("GVOICE_ENGINE")
    if name:
        return name
    config_file = paths.config_dir() / "config.json"
    try:
        config = fsutil.read_json(config_file, {})
    except (OSError, ValueError) as exc:
        raise GvoiceError("machine.config_unreadable", path=str(config_file), reason=str(exc))
    value = config.get("engine") if isinstance(config, dict) else None
    return value if isinstance(value, str) and value else "fake"


def check_configured() -> None:
    """Raise the error `get_engine` raises for an unknown configured engine, without building anything. The
    submitting commands call it so a job is never queued for an engine that cannot run it."""
    name = _configured_engine()
    if name != "fake":
        raise GvoiceError("engine.unknown", engine=name)


def get_engine() -> Engine:
    """The engine named by ``GVOICE_ENGINE`` or the config file (default ``fake``); see the module docstring."""
    check_configured()
    try:
        delay = float(os.environ.get("GVOICE_FAKE_DELAY") or 0)
    except ValueError:
        raise GvoiceError("engine.bad_delay", value=os.environ["GVOICE_FAKE_DELAY"])
    if not math.isfinite(delay) or delay < 0:
        raise GvoiceError("engine.bad_delay", value=os.environ["GVOICE_FAKE_DELAY"])
    return FakeEngine(delay_s=delay, fail_with=os.environ.get("GVOICE_FAKE_FAIL") or None)

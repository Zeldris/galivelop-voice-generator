"""The real engine: `qwen-tts` and `qwen-codec` of qwentts.cpp, one process per attempt (D15, D18).

* `design`: ``qwen-tts`` with the VoiceDesign model and ``--instruct``; the text goes through stdin.
* `line`: ``qwen-tts`` with the Base model of the job and the voice print (``--ref-spk``, ``--ref-rvq``) plus
  ``--ref-text``, which is the PATH of a text file with the reference transcription (the engine reads the file).
* `voiceprint`: ``qwen-codec`` writes ``.spk`` and ``.rvq`` NEXT TO its input ``.wav``, so it works on a copy inside a
  temporary folder and the results are moved to the job paths afterwards.

Layout: binaries are ``<engine>/bin-vulkan/`` (devices named ``Vulkan*``) or ``<engine>/bin-cpu/`` (any other device),
with ``<engine>`` = `paths.engine_dir()`. ``GVOICE_QWENTTS_BIN`` names one folder that replaces both (tests). Models
come from the catalog (`models`) by id; the codec is the catalog model whose use is ``codec``.

Everything the engine writes goes to a temporary folder next to the output (same filesystem) and is moved onto the job
paths only after the ``.wav`` was read back with `wave`: `audio_ms` always comes from the file (a failed, cancelled or
timed-out attempt leaves nothing at the job paths). The process runs in its own session: cancelling, the time limit
(`job.timeout_s`, for the whole job including the fallback) and any error raised by `on_tick` kill its whole group.

Device (D16): the profile's ``engine.device``. If the process dies at startup (exit code other than 0, no output
file, within `STARTUP_WINDOW_S`) it is repeated ONCE on ``engine.fallbackDevice``, and the device that produced the
result is in `EngineResult.device`. A failure with an output file, after the window or with exit 0 never falls back.

Memory watchdog (F2.3): `on_tick(proc)` is called every `TICK_S` while the process runs; it may raise `EngineError`,
which kills the process and ends the attempt (and, not being a startup failure, never triggers the fallback)."""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable, Optional

from . import fsutil, limits, models, paths
from .engine import (Cancelled, DesignJob, Engine, EngineError, EngineResult, EngineTimeout, LineJob, PrintJob,
                     _device)
from .errors import GvoiceError

ENGINE = "qwentts"
BIN_ENV = "GVOICE_QWENTTS_BIN"
TTS_BIN, CODEC_BIN = "qwen-tts", "qwen-codec"
DEFAULT_LANGUAGE = "Spanish"  # when neither the job nor the project says one
DEFAULT_DESIGN_MODEL, DEFAULT_BASE_MODEL = "1.7b-voicedesign", "0.6b-base"
TICK_S = 0.05
KILL_GRACE_S = 1.0
STARTUP_WINDOW_S = 30.0  # a device that cannot be opened fails fast; later deaths are not the device's fault
STDERR_LINES, STDERR_CHARS = 15, 1500


def device_arg(device: str) -> str:
    """The name the engine's ``--device`` takes: ``CPU`` for the profile's ``cpu``, anything else as it is."""
    return "CPU" if device.lower() == "cpu" else device


def bin_dir(device: str) -> Path:
    override = os.environ.get(BIN_ENV)
    if override:
        return Path(override)
    return paths.engine_dir() / ("bin-vulkan" if device.lower().startswith("vulkan") else "bin-cpu")


def binary(name: str, device: str) -> Path:
    return bin_dir(device) / name


def _catalog_model(catalog: dict, model_id: str) -> dict:
    for model in catalog["models"]:
        if model["id"] == model_id:
            return model
    raise GvoiceError("models.unknown_id", id=model_id, known=", ".join(m["id"] for m in catalog["models"]))


def _codec_id(catalog: dict) -> str:
    for model in catalog["models"]:
        if model["use"] == "codec":
            return model["id"]
    raise GvoiceError("models.unknown_id", id="codec", known=", ".join(m["id"] for m in catalog["models"]))


def check_installed(machine: dict) -> None:
    """Raise `GvoiceError` if the binaries of the profile's device, or the models it needs (the codec, the design
    model and the production model, the first of ``models.produce``), are not there. Sizes only, no SHA-256."""
    device = _device(DesignJob("", "", 0, "", machine=machine))
    for name in (TTS_BIN, CODEC_BIN):
        path = binary(name, device)
        if not (path.is_file() and os.access(path, os.X_OK)):
            raise GvoiceError("engine.binary_missing", path=str(path))
    catalog = models.load(ENGINE)
    wanted = {_codec_id(catalog)}
    chosen = machine.get("models") or {}
    produce = chosen.get("produce")
    produce = [produce] if isinstance(produce, str) else (produce or [])
    for value in (chosen.get("design"), produce[0] if produce else None):
        if value:
            wanted.add(value)
    for item in models.status(catalog, sorted(wanted), check_hash=False):
        if item["state"] not in (models.OK, models.UNCHECKED):
            raise GvoiceError("engine.model_missing", id=item["id"], path=item["path"], state=item["state"])


def read_wav_ms(path) -> int:
    """Length in ms of the ``.wav`` at `path`, read with `wave`; `EngineError` ``engine.bad_audio`` if absent,
    unreadable or empty."""
    try:
        with wave.open(str(path), "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
    except (OSError, EOFError, wave.Error) as exc:
        reason = "missing" if isinstance(exc, FileNotFoundError) else "unreadable: %s" % exc
        raise EngineError("the engine wrote no usable audio (%s)" % reason, "engine.bad_audio", reason=reason)
    if frames <= 0 or rate <= 0:
        raise EngineError("the engine wrote no usable audio (empty)", "engine.bad_audio", reason="empty")
    return round(frames * 1000 / rate)


def _tail(path) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = "\n".join(text.strip().splitlines()[-STDERR_LINES:])
    return text[-STDERR_CHARS:]


def _kill_group(proc: subprocess.Popen) -> None:
    """SIGTERM to the process group, a short grace, then SIGKILL, and reap the leader."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        pass
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)  # also whatever the leader left behind
    proc.wait()


class _Run:
    """The outcome of one process: exit code, how long it lived and the tail of its stderr."""

    def __init__(self, argv, code, seconds, stderr):
        self.argv, self.code, self.seconds, self.stderr = argv, code, seconds, stderr


class QwenTtsEngine(Engine):
    provider = "qwentts"

    def __init__(self, on_tick: Optional[Callable[[subprocess.Popen], None]] = None):
        self.on_tick = on_tick
        self.catalog = models.load(ENGINE)

    # -- the process -------------------------------------------------------------------------------------------

    def _spawn_wait(self, argv, stdin_text, deadline, should_cancel, workdir: Path) -> _Run:
        stdin_file, err_file = workdir / "stdin.txt", workdir / "stderr.txt"
        stdin_file.write_text(stdin_text or "", encoding="utf-8")
        started = time.monotonic()
        with open(stdin_file, "rb") as sin, open(err_file, "wb") as serr:
            try:
                proc = subprocess.Popen(argv, stdin=sin, stdout=subprocess.DEVNULL, stderr=serr,
                                        start_new_session=True)
            except OSError as exc:
                raise EngineError("cannot start %s: %s" % (argv[0], exc))
            try:
                while True:
                    code = proc.poll()
                    if code is not None:
                        break
                    if should_cancel():
                        raise Cancelled()
                    if deadline is not None and time.monotonic() >= deadline:
                        raise EngineTimeout()
                    if self.on_tick is not None:
                        self.on_tick(proc)  # F2.3: the memory watchdog; may raise EngineError
                    time.sleep(TICK_S)
            finally:
                if proc.poll() is None:
                    _kill_group(proc)
                else:  # the leader is gone; its children must not outlive it
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.killpg(proc.pid, signal.SIGKILL)
        return _Run(argv, code, time.monotonic() - started, _tail(err_file))

    def _attempts(self, job, build, stdin_text, produced, should_cancel, work: Path):
        """Run `build(device)` on the profile's device and, if the process dies at startup, once on the fallback.
        Returns ``(run, device)`` of the attempt that counts. `produced()` says whether outputs exist."""
        machine = job.machine or {}
        device = _device(job)
        fallback = (machine.get("engine") or {}).get("fallbackDevice")
        devices = [device]
        if fallback and fallback.lower() != device.lower():
            devices.append(fallback)
        timeout = job.timeout_s if job.timeout_s is not None else machine.get("timeoutS")
        deadline = None if timeout is None else time.monotonic() + timeout
        first, note = None, ""
        for position, current in enumerate(devices):
            argv = build(device_arg(current))
            if not (Path(argv[0]).is_file() and os.access(argv[0], os.X_OK)):
                if first is None:
                    raise EngineError("%s is not installed" % argv[0], "engine.binary_missing", path=argv[0])
                break  # no binary for the fallback: the first failure is the one to report
            run = self._spawn_wait(argv, stdin_text, deadline, should_cancel, work)
            startup_failure = run.code != 0 and not produced() and run.seconds <= STARTUP_WINDOW_S
            if not startup_failure or position == len(devices) - 1:
                if note and run.code != 0:
                    run.stderr += note
                return run, current
            note = "\n(it had failed at startup on %s: %s)" % (device_arg(current), run.stderr.replace("\n", " | "))
            first = (run, current)
        return first

    def _result(self, started, job, device, seed, model, run, audio_ms=None) -> EngineResult:
        return EngineResult(duration_ms=int((time.monotonic() - started) * 1000),
                            engine_version="%s-%s" % (ENGINE, self.catalog["commit"][:7]), device=device_arg(device),
                            seed=seed, engine_commit=self.catalog["commit"], model=model, audio_ms=audio_ms,
                            backend=ENGINE, command=list(run.argv))

    def _fail(self, run, device) -> EngineError:
        return EngineError("%s exited with code %s on %s: %s" % (os.path.basename(run.argv[0]), run.code, device_arg(device),
                                                                  run.stderr or "(no stderr)"))

    def _model(self, model_id: str) -> str:
        path = models.model_path(_catalog_model(self.catalog, model_id))
        if not path.is_file():
            raise EngineError("model %s is not installed: %s" % (model_id, path), "engine.model_missing",
                              id=model_id, path=str(path), state=models.MISSING)
        return str(path)

    @contextlib.contextmanager
    def _workdir(self, near):
        near = Path(near)
        near.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(dir=str(near.parent), prefix=".qwentts-"))
        try:
            yield work
        finally:
            shutil.rmtree(work, ignore_errors=True)

    # -- the operations ----------------------------------------------------------------------------------------

    def _tts(self, job, model_id, extra_args, text, should_cancel, seed) -> EngineResult:
        """The part design and line share: run `qwen-tts` into a temporary wav, read it, move it onto the output."""
        started = time.monotonic()
        model, codec = self._model(model_id), self._model(_codec_id(self.catalog))
        language = job.language or DEFAULT_LANGUAGE
        with self._workdir(job.output) as work:
            wav = work / "out.wav"

            def build(dev):
                return [str(binary(TTS_BIN, dev)), "--model", model, "--codec", codec] + extra_args(work) + [
                    "--lang", language, "--seed", str(seed), "--device", dev, "-o", str(wav)]

            run, device = self._attempts(job, build, text, wav.is_file, should_cancel, work)
            if run.code != 0:
                raise self._fail(run, device)
            audio_ms = read_wav_ms(wav)
            try:
                os.replace(wav, job.output)
            except OSError as exc:
                raise EngineError("cannot move the audio to %s: %s" % (job.output, exc))
        return self._result(started, job, device, seed, model_id, run, audio_ms)

    def design(self, job: DesignJob, should_cancel) -> EngineResult:
        model_id = job.model or (job.machine.get("models") or {}).get("design") or DEFAULT_DESIGN_MODEL
        return self._tts(job, model_id, lambda work: ["--instruct", job.instruction], job.text, should_cancel, job.seed)

    def line(self, job: LineJob, should_cancel) -> EngineResult:
        for path in (job.spk, job.rvq):
            if not Path(path).is_file():
                raise EngineError("voice print missing: %s" % path, "engine.print_missing", path=path)
        if not job.reference_text:
            raise EngineError("the reference text is missing", "engine.no_reference_text")

        def extra(work):
            ref_text = work / "ref.txt"
            ref_text.write_text(job.reference_text, encoding="utf-8")
            return ["--ref-spk", job.spk, "--ref-rvq", job.rvq, "--ref-text", str(ref_text)]

        return self._tts(job, job.model or DEFAULT_BASE_MODEL, extra, job.text, should_cancel, job.seed)

    def voiceprint(self, job: PrintJob, should_cancel) -> EngineResult:
        started = time.monotonic()
        tokenizer, talker = self._model(_codec_id(self.catalog)), self._model(job.model)
        if not Path(job.reference).is_file():
            raise EngineError("cannot read %s" % job.reference, "engine.reference_unreadable", path=job.reference)
        with self._workdir(job.spk) as work:
            ref = work / "ref.wav"
            try:
                shutil.copyfile(job.reference, ref)
            except OSError:
                raise EngineError("cannot read %s" % job.reference, "engine.reference_unreadable",
                                  path=job.reference)
            made = (work / "ref.spk", work / "ref.rvq")

            def build(dev):
                return [str(binary(CODEC_BIN, dev)), "--model", tokenizer, "--talker", talker, "-i", str(ref),
                        "--device", dev]

            run, device = self._attempts(job, build, "", lambda: any(p.is_file() for p in made), should_cancel,
                                         work)
            if run.code != 0:
                raise self._fail(run, device)
            for path in made:
                if not path.is_file() or path.stat().st_size == 0:
                    raise EngineError("the engine wrote no %s" % path.suffix, "engine.print_not_written",
                                      path=str(path.suffix))
            moved = []
            try:
                for src, dst in zip(made, (job.spk, job.rvq)):
                    Path(dst).parent.mkdir(parents=True, exist_ok=True)
                    os.replace(src, dst)
                    moved.append(dst)
            except OSError as exc:
                for dst in moved:
                    with contextlib.suppress(OSError):
                        os.unlink(dst)
                raise EngineError("cannot move the voice print: %s" % exc)
        return self._result(started, job, device, None, job.model, run)

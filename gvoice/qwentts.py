"""The real engine (F2.3): `QwenEngine` wraps the ``qwen-tts`` and ``qwen-codec`` programs of qwentts.cpp.

One process per attempt (D15), run through `runner.run` (memory, time and cancel watch). Mapping:

* `design`  -> ``qwen-tts --model <design model> --codec <codec> --instruct <instruction> --lang <language>
  --seed <seed> --device <device> -o <tmp>.wav``, the test text on stdin; the wav is then moved onto ``job.output``.
* `line`    -> ``qwen-tts --model <base model> --codec <codec> --ref-spk <spk> --ref-rvq <rvq> --ref-text <file>
  --lang ... --seed ... --device ... -o <tmp>.wav``, the line text on stdin. ``--ref-text`` is a PATH: ``job.ref_text``
  is written to a temp file.
* `voiceprint` -> ``qwen-codec --model <codec> --talker <base model> -i <tmp>/ref.wav --device <device>`` on a copy of
  the reference take; it writes ``ref.rvq`` and ``ref.spk`` next to the input and they are moved to ``job.rvq`` and
  ``job.spk``.

Temp files live in a ``TemporaryDirectory`` next to the destination (same filesystem, so the final move is an atomic
``os.replace``) and are always removed.

Device: ``job.device`` or the machine profile's ``engine.device``. A non-zero exit on it is retried once on
``engine.fallbackDevice`` (if set and different); the timeout counts from the start of the first attempt. A timeout,
a cancel or a `limits.LimitError` propagate untouched, with no fallback. A non-zero exit on the last device is
``engine.exit`` with the tail of stderr. The device is passed to the program as ggml names it: ``cpu`` (any case)
becomes ``CPU``; ``Vulkan0`` goes as is. `EngineResult.device` keeps the name the profile uses.

The programs come from `install.binary`; ``LD_LIBRARY_PATH`` starts with their folder as a safety net besides rpath."""
from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable

from . import install, runner
from .engine import DesignJob, Engine, EngineError, EngineResult, EngineTimeout, LineJob, PrintJob, _device

DEFAULT_DESIGN_MODEL = "1.7b-voicedesign"
DEFAULT_LINE_MODEL = "0.6b-base"
STDERR_CHARS = 2000


def _cli_device(device: str) -> str:
    """ggml device names are case sensitive: the CPU one is ``CPU``."""
    return "CPU" if str(device).lower() == "cpu" else str(device)


def _backend(device: str) -> str:
    return "vulkan" if str(device).lower().startswith("vulkan") else "cpu"


def _devices(job) -> list:
    first = _device(job)
    devices = [first]
    fallback = (job.machine.get("engine") or {}).get("fallbackDevice")
    if fallback and fallback != first:
        devices.append(fallback)
    return devices


def _audio_ms(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as wav:
            return int(wav.getnframes() * 1000 / wav.getframerate())
    except (wave.Error, EOFError, OSError, ZeroDivisionError) as exc:
        raise EngineError("unreadable audio %s: %s" % (path, exc), "engine.bad_audio", path=str(path))


def _place(src: Path, dst) -> None:
    """Copy `src` next to `dst` and `os.replace` it (atomic even across filesystems)."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dst.parent), prefix="." + dst.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
        os.replace(tmp, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class QwenEngine(Engine):
    provider = "qwentts"

    def _run(self, job, program, build, stdin_text, should_cancel, start):
        """Run `program` on each device in turn; `build(device_name_for_cli)` gives the arguments after the binary.
        Returns ``(device, argv, RunResult)`` of the first run that exits with 0."""
        last = None
        for device in _devices(job):
            binary = install.binary(program, device)
            argv = [str(binary)] + [str(a) for a in build(_cli_device(device))]
            old = os.environ.get("LD_LIBRARY_PATH")
            env = {"LD_LIBRARY_PATH": os.pathsep.join([str(binary.parent)] + ([old] if old else []))}
            timeout = job.timeout_s
            if timeout is not None:
                timeout -= time.monotonic() - start
                if timeout <= 0:
                    raise EngineTimeout()
            res = runner.run(argv, stdin_text=stdin_text, env=env, machine=job.machine, timeout_s=timeout,
                             should_cancel=should_cancel)
            if res.returncode == 0:
                return device, argv, res
            last = (device, res)
        device, res = last
        tail = res.stderr[-STDERR_CHARS:]
        raise EngineError(tail, "engine.exit", returncode=res.returncode, device=device, stderr=tail)

    def _result(self, start, device, argv, res, seed, model, audio_ms) -> EngineResult:
        commit = (install.read_install() or {}).get("commit") or ""
        return EngineResult(
            duration_ms=int((time.monotonic() - start) * 1000), engine_version="qwentts-" + commit[:7],
            device=device, seed=seed, engine_commit=commit or None, model=model, audio_ms=audio_ms, load_ms=None,
            min_free_mb=res.min_free_mb, command=[str(a) for a in argv], backend=_backend(device))

    def _synthesize(self, job, extra, text, model, should_cancel) -> EngineResult:
        start = time.monotonic()
        out = Path(job.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(out.parent), prefix=".gvoice-") as tmp:
            wav = Path(tmp) / "out.wav"
            args = extra(Path(tmp))

            def build(device):
                return (["--model", install.model_path(model), "--codec", install.codec_path()] + args
                        + ["--lang", job.language, "--seed", job.seed, "--device", device, "-o", wav])

            device, argv, res = self._run(job, "qwen-tts", build, text, should_cancel, start)
            if not wav.is_file():
                raise EngineError("the engine wrote no audio at %s" % wav, "engine.output_missing", path=str(wav))
            audio_ms = _audio_ms(wav)
            os.replace(wav, out)
        return self._result(start, device, argv, res, job.seed, model, audio_ms)

    def design(self, job: DesignJob, should_cancel: Callable[[], bool]) -> EngineResult:
        model = job.model or DEFAULT_DESIGN_MODEL
        return self._synthesize(job, lambda tmp: ["--instruct", job.instruction], job.text, model, should_cancel)

    def line(self, job: LineJob, should_cancel: Callable[[], bool]) -> EngineResult:
        for path in (job.spk, job.rvq):
            if not Path(path).is_file():
                raise EngineError("voice print missing: %s" % path, "engine.print_missing", path=str(path))
        model = job.model or DEFAULT_LINE_MODEL

        def extra(tmp: Path):
            ref = tmp / "ref.txt"
            ref.write_text(job.ref_text, encoding="utf-8")
            return ["--ref-spk", job.spk, "--ref-rvq", job.rvq, "--ref-text", ref]

        return self._synthesize(job, extra, job.text, model, should_cancel)

    def voiceprint(self, job: PrintJob, should_cancel: Callable[[], bool]) -> EngineResult:
        start = time.monotonic()
        spk_out, rvq_out = Path(job.spk), Path(job.rvq)
        spk_out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(spk_out.parent), prefix=".gvoice-") as tmp:
            ref = Path(tmp) / "ref.wav"
            try:
                shutil.copyfile(job.reference, ref)
            except OSError:
                raise EngineError("cannot read %s" % job.reference, "engine.reference_unreadable",
                                  path=job.reference)

            def build(device):
                return ["--model", install.codec_path(), "--talker", install.model_path(job.model), "-i", ref,
                        "--device", device]

            device, argv, res = self._run(job, "qwen-codec", build, None, should_cancel, start)
            made = {name: Path(tmp) / ("ref." + name) for name in ("spk", "rvq")}
            for path in made.values():
                if not path.is_file():
                    raise EngineError("the engine wrote no %s" % path.name, "engine.output_missing", path=str(path))
            _place(made["spk"], spk_out)
            _place(made["rvq"], rvq_out)
        return self._result(start, device, argv, res, None, job.model, None)

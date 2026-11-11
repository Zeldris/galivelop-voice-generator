import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import engine, install, limits, orders, queue
from gvoice.engine import DesignJob, EngineError, EngineTimeout, GvoiceError, LineJob, PrintJob
from gvoice.qwentts import QwenEngine
from tests.test_worker import WorkerBase

FAKE = """#!%s
import json, os, sys, time, wave
argv = sys.argv[1:]
opts = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith("-")}
prog = os.path.basename(sys.argv[0])
device = opts.get("--device")
rec = {"prog": prog, "argv": sys.argv, "device": device, "env": os.environ.get("LD_LIBRARY_PATH"),
       "stdin": sys.stdin.read()}
if opts.get("--ref-text"):
    rec["ref_text"] = open(opts["--ref-text"], encoding="utf-8").read()
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps(rec) + "\\n")
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
if device in os.environ.get("FAKE_FAIL_DEVICES", "").split(","):
    sys.stderr.write("boom on " + device + "\\n")
    sys.exit(3)
if prog == "qwen-tts":
    if os.environ.get("FAKE_BAD_WAV"):
        open(opts["-o"], "wb").write(b"not a wav")
    else:
        with wave.open(opts["-o"], "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(b"\\0\\0" * 12000)
else:
    base = opts["-i"].rsplit(".", 1)[0]
    if not os.environ.get("FAKE_NO_OUTPUT"):
        open(base + ".spk", "wb").write(b"SPK")
        open(base + ".rvq", "wb").write(b"RVQ")
"""

MACHINE = {"minFreeMemoryMb": 0, "watchMemoryMb": 0, "timeoutS": 60,
           "engine": {"device": "Vulkan0", "fallbackDevice": "cpu"}}


def install_fake(devices=("Vulkan0", "cpu")):
    for device in devices:
        for name in ("qwen-tts", "qwen-codec"):
            path = install.binary(name, device)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(FAKE % sys.executable)
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
    (install.engine_dir() / "install.json").write_text(json.dumps(
        {"commit": install.ENGINE_COMMIT, "devices": list(devices), "installedAt": "2026-11-11T00:00:00Z"}))


def clean_env():
    for var in ("GVOICE_ENGINE", "GVOICE_MODELS_HOME", "LD_LIBRARY_PATH", "FAKE_FAIL_DEVICES", "FAKE_SLEEP",
                "FAKE_BAD_WAV", "FAKE_NO_OUTPUT"):
        os.environ.pop(var, None)


class QwenBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.log = self.tmp / "calls.jsonl"
        env = mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": str(self.tmp / "data"), "FAKE_LOG": str(self.log),
                                           "GVOICE_CONFIG_HOME": str(self.tmp / "cfg")})
        env.start()
        self.addCleanup(env.stop)
        clean_env()
        install_fake()
        self.out = self.tmp / "out"
        self.out.mkdir()

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def design_job(self, **kw):
        args = dict(instruction="A warm voice", text="Hola mundo", seed=11, output=str(self.out / "d.wav"),
                    machine=MACHINE, language="Spanish", timeout_s=30)
        args.update(kw)
        return DesignJob(**args)


def flag(argv, name):
    return argv[argv.index(name) + 1]


class CommandTests(QwenBase):
    def test_design(self):
        job = self.design_job()
        res = QwenEngine().design(job, lambda: False)
        call, = self.calls()
        argv = call["argv"]
        self.assertEqual(argv[0], str(install.binary("qwen-tts", "Vulkan0")))
        self.assertEqual(flag(argv, "--model"), str(install.model_path("1.7b-voicedesign")))
        self.assertEqual(flag(argv, "--codec"), str(install.codec_path()))
        self.assertEqual((flag(argv, "--instruct"), flag(argv, "--lang"), flag(argv, "--seed"),
                          flag(argv, "--device")), ("A warm voice", "Spanish", "11", "Vulkan0"))
        self.assertEqual(call["stdin"], "Hola mundo")
        self.assertEqual(call["env"], str(install.bin_dir("Vulkan0")))
        self.assertEqual((res.device, res.backend, res.seed, res.audio_ms), ("Vulkan0", "vulkan", 11, 500))
        self.assertEqual((res.model, res.engine_version, res.engine_commit),
                         ("1.7b-voicedesign", "qwentts-" + install.ENGINE_COMMIT[:7], install.ENGINE_COMMIT))
        self.assertEqual(res.command, argv)
        self.assertIsNone(res.load_ms)
        self.assertTrue(Path(job.output).is_file())
        self.assertEqual(os.listdir(self.out), ["d.wav"])  # temp dir gone

    def test_ld_library_path_is_prepended(self):
        os.environ["LD_LIBRARY_PATH"] = "/somewhere"
        QwenEngine().design(self.design_job(), lambda: False)
        self.assertEqual(self.calls()[0]["env"], "%s:/somewhere" % install.bin_dir("Vulkan0"))

    def test_line(self):
        spk, rvq = self.tmp / "a.spk", self.tmp / "a.rvq"
        spk.write_bytes(b"s")
        rvq.write_bytes(b"r")
        job = LineJob(spk=str(spk), rvq=str(rvq), text="Una frase", seed=7, output=str(self.out / "l.wav"),
                      model="0.6b-base", machine=MACHINE, language="Spanish", ref_text="Texto de ñoño")
        res = QwenEngine().line(job, lambda: False)
        call, = self.calls()
        argv = call["argv"]
        self.assertEqual(flag(argv, "--model"), str(install.model_path("0.6b-base")))
        self.assertEqual((flag(argv, "--ref-spk"), flag(argv, "--ref-rvq"), flag(argv, "--lang"),
                          flag(argv, "--seed")), (str(spk), str(rvq), "Spanish", "7"))
        self.assertEqual(call["ref_text"], "Texto de ñoño")
        self.assertEqual(call["stdin"], "Una frase")
        self.assertEqual((res.audio_ms, res.model), (500, "0.6b-base"))
        self.assertEqual(os.listdir(self.out), ["l.wav"])

    def test_line_missing_print(self):
        job = LineJob(spk=str(self.tmp / "no.spk"), rvq=str(self.tmp / "no.rvq"), text="x", seed=1,
                      output=str(self.out / "l.wav"), machine=MACHINE)
        with self.assertRaises(EngineError) as ctx:
            QwenEngine().line(job, lambda: False)
        self.assertEqual(ctx.exception.code, "engine.print_missing")
        self.assertFalse(self.log.exists())

    def test_voiceprint(self):
        ref = self.tmp / "take.wav"
        ref.write_bytes(b"WAV")
        job = PrintJob(reference=str(ref), text="hola", model="0.6b-base", spk=str(self.out / "p/x.spk"),
                       rvq=str(self.out / "p/x.rvq"), machine=MACHINE)
        res = QwenEngine().voiceprint(job, lambda: False)
        call, = self.calls()
        argv = call["argv"]
        self.assertEqual(argv[0], str(install.binary("qwen-codec", "Vulkan0")))
        self.assertEqual((flag(argv, "--model"), flag(argv, "--talker")),
                         (str(install.codec_path()), str(install.model_path("0.6b-base"))))
        self.assertEqual(Path(flag(argv, "-i")).name, "ref.wav")
        self.assertEqual((self.out / "p/x.spk").read_bytes(), b"SPK")
        self.assertEqual((self.out / "p/x.rvq").read_bytes(), b"RVQ")
        self.assertEqual(sorted(os.listdir(self.out / "p")), ["x.rvq", "x.spk"])  # no temp dir left
        self.assertFalse(Path(flag(argv, "-i")).exists())
        self.assertEqual((res.model, res.audio_ms, res.seed), ("0.6b-base", None, None))

    def test_voiceprint_output_missing(self):
        os.environ["FAKE_NO_OUTPUT"] = "1"
        ref = self.tmp / "take.wav"
        ref.write_bytes(b"WAV")
        job = PrintJob(reference=str(ref), text="hola", model="0.6b-base", spk=str(self.out / "x.spk"),
                       rvq=str(self.out / "x.rvq"), machine=MACHINE)
        with self.assertRaises(EngineError) as ctx:
            QwenEngine().voiceprint(job, lambda: False)
        self.assertEqual(ctx.exception.code, "engine.output_missing")
        self.assertEqual(os.listdir(self.out), [])

    def test_bad_audio(self):
        os.environ["FAKE_BAD_WAV"] = "1"
        with self.assertRaises(EngineError) as ctx:
            QwenEngine().design(self.design_job(), lambda: False)
        self.assertEqual(ctx.exception.code, "engine.bad_audio")
        self.assertEqual(os.listdir(self.out), [])


class FallbackTests(QwenBase):
    def test_fallback_to_cpu(self):
        os.environ["FAKE_FAIL_DEVICES"] = "Vulkan0"
        res = QwenEngine().design(self.design_job(), lambda: False)
        calls = self.calls()
        self.assertEqual([(c["device"], c["argv"][0]) for c in calls],
                         [("Vulkan0", str(install.binary("qwen-tts", "Vulkan0"))),
                          ("CPU", str(install.binary("qwen-tts", "cpu")))])  # ggml names the CPU "CPU"
        self.assertEqual((res.device, res.backend), ("cpu", "cpu"))
        self.assertEqual(res.command, calls[1]["argv"])
        self.assertTrue(Path(self.out / "d.wav").is_file())

    def test_failure_on_both(self):
        os.environ["FAKE_FAIL_DEVICES"] = "Vulkan0,CPU"
        with self.assertRaises(EngineError) as ctx:
            QwenEngine().design(self.design_job(), lambda: False)
        err = ctx.exception
        self.assertEqual((err.code, err.params["returncode"], err.params["device"]), ("engine.exit", 3, "cpu"))
        self.assertIn("boom on CPU", err.message)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(os.listdir(self.out), [])

    def test_no_fallback_without_one(self):
        os.environ["FAKE_FAIL_DEVICES"] = "Vulkan0"
        machine = dict(MACHINE, engine={"device": "Vulkan0"})
        with self.assertRaises(EngineError):
            QwenEngine().design(self.design_job(machine=machine), lambda: False)
        self.assertEqual(len(self.calls()), 1)

    def test_timeout_has_no_fallback(self):
        os.environ["FAKE_SLEEP"] = "5"
        with self.assertRaises(EngineTimeout):
            QwenEngine().design(self.design_job(timeout_s=0.5), lambda: False)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(os.listdir(self.out), [])

    def test_timeout_counts_from_the_first_attempt(self):
        os.environ["FAKE_FAIL_DEVICES"] = "Vulkan0"
        os.environ["FAKE_SLEEP"] = "0.6"
        with self.assertRaises(EngineTimeout):
            QwenEngine().design(self.design_job(timeout_s=1.0), lambda: False)
        self.assertEqual(len(self.calls()), 2)

    def test_limit_error_propagates(self):
        machine = dict(MACHINE, minFreeMemoryMb=10 ** 9)
        with mock.patch("gvoice.limits.available_memory_mb", return_value=1000):
            with self.assertRaises(limits.LimitError):
                QwenEngine().design(self.design_job(machine=machine), lambda: False)
        self.assertFalse(self.log.exists())

    def test_cancel(self):
        os.environ["FAKE_SLEEP"] = "5"
        with self.assertRaises(engine.Cancelled):
            QwenEngine().design(self.design_job(), lambda: True)
        self.assertLessEqual(len(self.calls()) if self.log.exists() else 0, 1)  # no second attempt
        self.assertEqual(os.listdir(self.out), [])


class SelectionTests(QwenBase):
    def test_get_engine(self):
        os.environ["GVOICE_ENGINE"] = "qwentts"
        self.assertIsInstance(engine.get_engine(), QwenEngine)

    def test_get_engine_from_config(self):
        cfg = self.tmp / "cfg"
        cfg.mkdir()
        (cfg / "config.json").write_text(json.dumps({"engine": "qwentts"}))
        self.assertIsInstance(engine.get_engine(), QwenEngine)

    def test_not_installed(self):
        os.environ["GVOICE_ENGINE"] = "qwentts"
        (install.engine_dir() / "install.json").unlink()
        for call in (engine.check_configured, engine.get_engine):
            with self.assertRaises(GvoiceError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, "engine.not_installed")


class WorkerTests(WorkerBase):
    def test_voice_take_with_the_fake_binaries(self):
        install_fake(("Vulkan0",))
        log = self.tmp / "calls.jsonl"
        env = mock.patch.dict(os.environ, {"FAKE_LOG": str(log)})
        env.start()
        self.addCleanup(env.stop)
        clean_env()
        machine = dict(limits.load_machine(), minFreeMemoryMb=0, watchMemoryMb=0)
        orders.submit(self.p, self.voice())
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator", seed=7))
        with mock.patch("gvoice.limits.load_machine", return_value=machine):
            self.assertEqual(self.run_worker(once=True, engine=QwenEngine()), 1)
        entry, = queue.list_entries()
        self.assertEqual((entry["state"], entry.get("error")), ("done", None))
        attempt = orders.get(self.p, "narrator")["attempts"][0]
        self.assertTrue(orders.attempt_audio(self.p, "narrator", attempt).is_file())
        self.assertEqual(attempt["audioMs"], 500)
        call, = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(call["prog"], "qwen-tts")


if __name__ == "__main__":
    unittest.main()

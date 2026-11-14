import json
import os
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from gvoice import engine, engine_qwentts, limits, models
from gvoice.errors import GvoiceError

FAKE = str(Path(__file__).resolve().parent / "fake_qwentts.py")
NEVER = lambda: False
VARS = ("FAKE_QT_FAIL_DEVICE", "FAKE_QT_HANG", "FAKE_QT_NOWAV", "FAKE_QT_BADWAV", "FAKE_QT_CRASH",
        "FAKE_QT_LATE_FAIL_S", "GVOICE_ENGINE", "GVOICE_MACHINE_PROFILE")


def wav_ms(path):
    with wave.open(str(path), "rb") as w:
        return round(w.getnframes() * 1000 / w.getframerate())


class QwenTtsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, mode in (("qwen-tts", "tts"), ("qwen-codec", "codec")):
            script = self.bin / name
            script.write_text('#!/bin/sh\nexec "%s" "%s" %s "$@"\n' % (sys.executable, FAKE, mode))
            script.chmod(0o755)
        self.log = self.tmp / "calls.jsonl"
        env = {"GVOICE_DATA_HOME": str(self.tmp / "data"), "GVOICE_MODELS_HOME": str(self.tmp / "models"),
               "GVOICE_CONFIG_HOME": str(self.tmp / "config"), engine_qwentts.BIN_ENV: str(self.bin),
               "FAKE_QT_LOG": str(self.log), "FAKE_QT_PIDFILE": str(self.tmp / "pid")}
        env.update({v: "" for v in VARS})
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        self.catalog = models.load("qwentts")
        self.install_models()
        self.machine = limits.load_machine("steam-deck")
        self.eng = engine_qwentts.QwenTtsEngine()
        self.out = self.tmp / "out"

    def install_models(self, skip=()):
        (self.tmp / "models").mkdir(exist_ok=True)
        for model in self.catalog["models"]:
            if model["id"] not in skip:
                with open(models.model_path(model), "wb") as fh:
                    fh.truncate(model["bytes"])  # sparse: only the size is checked without the hash

    def mp(self, model_id):
        return str(models.model_path(next(m for m in self.catalog["models"] if m["id"] == model_id)))

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def machine_with(self, **kw):
        machine = dict(self.machine)
        machine.update(kw)
        return machine

    def design(self, **kw):
        kw.setdefault("machine", self.machine)
        job = engine.DesignJob(instruction="Gender: male.", text="hello", seed=11, output=str(self.out / "a.wav"), **kw)
        return job

    def make_print(self, **kw):
        ref = self.tmp / "ref.wav"
        with wave.open(str(ref), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 2400)
        kw.setdefault("machine", self.machine)
        return engine.PrintJob(reference=str(ref), text="Reference words.", model="0.6b-base",
                               spk=str(self.tmp / "prints" / "0.6b-base.spk"),
                               rvq=str(self.tmp / "prints" / "0.6b-base.rvq"), **kw)

    def error(self, fn):
        with self.assertRaises(engine.EngineError) as cm:
            fn()
        return cm.exception

    def leftovers(self):
        return sorted(p.name for d in (self.out, self.tmp / "prints") if d.exists() for p in d.iterdir())

    # -- commands ----------------------------------------------------------------------------------------------

    def test_design_command_and_result(self):
        job = self.design()
        result = self.eng.design(job, NEVER)
        call, = self.calls()
        argv = call["argv"]
        wav = argv[argv.index("-o") + 1]
        self.assertEqual(argv, ["--model", self.mp("1.7b-voicedesign"), "--codec", self.mp("tokenizer-12hz"),
                                "--instruct", "Gender: male.", "--lang", "Spanish", "--seed", "11",
                                "--device", "Vulkan0", "-o", wav])
        self.assertEqual((call["mode"], call["stdin"]), ("tts", "hello"))
        self.assertEqual(Path(wav).parent.parent, Path(job.output).parent)  # next to the output: same filesystem
        self.assertEqual(wav_ms(job.output), 500)
        self.assertEqual((result.audio_ms, result.device, result.seed, result.model), (500, "Vulkan0", 11,
                                                                                       "1.7b-voicedesign"))
        self.assertEqual((result.engine_commit, result.backend), (self.catalog["commit"], "qwentts"))
        self.assertEqual(result.command[1:3], ["--model", self.mp("1.7b-voicedesign")])
        self.assertEqual(self.leftovers(), ["a.wav"])

    def test_language_of_the_job(self):
        self.eng.design(self.design(language="English"), NEVER)
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--lang") + 1], "English")

    def test_line_command(self):
        pj = self.make_print()
        self.eng.voiceprint(pj, NEVER)
        self.log.unlink()
        job = engine.LineJob(spk=pj.spk, rvq=pj.rvq, text="a line", seed=7, output=str(self.out / "l.wav"),
                             model="0.6b-base", machine=self.machine, reference_text="Reference words.")
        seen = {}
        real = engine_qwentts.QwenTtsEngine._spawn_wait

        def spy(this, argv, stdin_text, *a):
            seen["ref_text"] = Path(argv[argv.index("--ref-text") + 1]).read_text()  # the file exists while it runs
            return real(this, argv, stdin_text, *a)

        with mock.patch.object(engine_qwentts.QwenTtsEngine, "_spawn_wait", spy):
            result = self.eng.line(job, NEVER)
        call, = self.calls()
        argv = call["argv"]
        ref_text, wav = argv[argv.index("--ref-text") + 1], argv[argv.index("-o") + 1]
        self.assertEqual(argv, ["--model", self.mp("0.6b-base"), "--codec", self.mp("tokenizer-12hz"),
                                "--ref-spk", pj.spk, "--ref-rvq", pj.rvq, "--ref-text", ref_text, "--lang", "Spanish",
                                "--seed", "7", "--device", "Vulkan0", "-o", wav])
        self.assertEqual(call["stdin"], "a line")
        self.assertEqual(seen["ref_text"], "Reference words.")  # a PATH to the transcription, not the text
        self.assertNotEqual(ref_text, "Reference words.")
        self.assertEqual((result.audio_ms, result.model), (600, "0.6b-base"))
        self.assertEqual(self.leftovers(), ["0.6b-base.rvq", "0.6b-base.spk", "l.wav"])

    def test_line_needs_print_and_reference_text(self):
        job = engine.LineJob(spk=str(self.tmp / "no.spk"), rvq=str(self.tmp / "no.rvq"), text="x", seed=1,
                             output=str(self.out / "l.wav"), machine=self.machine, reference_text="r")
        exc = self.error(lambda: self.eng.line(job, NEVER))
        self.assertEqual((exc.code, exc.params), ("engine.print_missing", {"path": job.spk}))
        pj = self.make_print()
        self.eng.voiceprint(pj, NEVER)
        job = engine.LineJob(spk=pj.spk, rvq=pj.rvq, text="x", seed=1, output=str(self.out / "l.wav"),
                             machine=self.machine)
        self.assertEqual(self.error(lambda: self.eng.line(job, NEVER)).code, "engine.no_reference_text")
        self.assertEqual(len(self.calls()), 1)  # only the print: nothing was launched

    def test_voiceprint_works_in_a_temp_folder_and_moves_the_files(self):
        pj = self.make_print()
        result = self.eng.voiceprint(pj, NEVER)
        call, = self.calls()
        argv = call["argv"]
        ref = argv[argv.index("-i") + 1]
        self.assertEqual(argv, ["--model", self.mp("tokenizer-12hz"), "--talker", self.mp("0.6b-base"), "-i", ref,
                                "--device", "Vulkan0"])
        self.assertNotEqual(ref, pj.reference)  # a copy, so nothing is written next to the take
        self.assertEqual(Path(ref).parent.parent, Path(pj.spk).parent)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir() if p.suffix in (".spk", ".rvq")), [])
        self.assertEqual((Path(pj.spk).stat().st_size, Path(pj.rvq).stat().st_size), (4096, 4444))
        self.assertEqual(self.leftovers(), ["0.6b-base.rvq", "0.6b-base.spk"])
        self.assertEqual((result.device, result.model, result.audio_ms), ("Vulkan0", "0.6b-base", None))

    def test_voiceprint_missing_reference(self):
        pj = self.make_print()
        os.unlink(pj.reference)
        exc = self.error(lambda: self.eng.voiceprint(pj, NEVER))
        self.assertEqual(exc.code, "engine.reference_unreadable")

    # -- device ------------------------------------------------------------------------------------------------

    def test_fallback_once_and_device_in_result(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        result = self.eng.design(self.design(), NEVER)
        devices = [c["argv"][c["argv"].index("--device") + 1] for c in self.calls()]
        self.assertEqual(devices, ["Vulkan0", "CPU"])
        self.assertEqual(result.device, "CPU")
        self.assertEqual(result.command[result.command.index("--device") + 1], "CPU")
        self.assertEqual(wav_ms(self.out / "a.wav"), 500)

    def test_fallback_for_the_print_too(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        result = self.eng.voiceprint(self.make_print(), NEVER)
        self.assertEqual((result.device, len(self.calls())), ("CPU", 2))
        self.assertTrue((self.tmp / "prints" / "0.6b-base.spk").is_file())

    def test_no_second_fallback_when_both_fail(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        machine = self.machine_with(engine={"device": "Vulkan0", "fallbackDevice": "Vulkan0"})
        exc = self.error(lambda: self.eng.design(self.design(machine=machine), NEVER))
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("failed to open device Vulkan0", exc.message)
        self.assertIn("exited with code 3 on Vulkan0", exc.message)

    def test_both_devices_failing_reports_both(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0,CPU"
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual(len(self.calls()), 2)  # one repetition, not more
        self.assertIn("exited with code 3 on CPU", exc.message)
        self.assertIn("it had failed at startup on Vulkan0", exc.message)
        self.assertEqual(self.leftovers(), [])

    def test_no_fallback_without_one_or_on_the_fallback_device(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "CPU"
        machine = self.machine_with(engine={"device": "cpu"})
        self.error(lambda: self.eng.design(self.design(machine=machine), NEVER))
        self.assertEqual([c["argv"][c["argv"].index("--device") + 1] for c in self.calls()], ["CPU"])

    def test_no_fallback_when_the_failure_is_not_the_device(self):
        os.environ["FAKE_QT_CRASH"] = "1"  # wrote a (broken) output file and exited 1
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("exited with code 1 on Vulkan0", exc.message)
        self.assertIn("boom: kaput", exc.message)
        self.assertEqual(self.leftovers(), [])

    def test_no_fallback_after_the_startup_window(self):
        os.environ["FAKE_QT_LATE_FAIL_S"] = "0.3"
        with mock.patch.object(engine_qwentts, "STARTUP_WINDOW_S", 0.1):
            exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual(len(self.calls()), 1)  # died after the window: not a device failure
        self.assertIn("out of memory", exc.message)

    def test_exit_zero_without_wav_is_an_error_not_a_fallback(self):
        os.environ["FAKE_QT_NOWAV"] = "1"
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual((exc.code, exc.params), ("engine.bad_audio", {"reason": "missing"}))
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.leftovers(), [])

    def test_unreadable_wav(self):
        os.environ["FAKE_QT_BADWAV"] = "1"
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual(exc.code, "engine.bad_audio")
        self.assertTrue(exc.params["reason"].startswith("unreadable:"))
        self.assertEqual(self.leftovers(), [])

    def test_print_not_written(self):
        os.environ["FAKE_QT_NOWAV"] = "1"
        exc = self.error(lambda: self.eng.voiceprint(self.make_print(), NEVER))
        self.assertEqual((exc.code, exc.params), ("engine.print_not_written", {"path": ".spk"}))
        self.assertEqual(self.leftovers(), [])

    def test_stderr_tail_in_the_error(self):
        os.environ["FAKE_QT_CRASH"] = "1"
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertIn("noise 39", exc.message)
        self.assertNotIn("noise 0\n", exc.message)  # only the last lines
        self.assertLessEqual(len(exc.message), engine_qwentts.STDERR_CHARS + 200)

    # -- cancel and time limit -----------------------------------------------------------------------------------

    def wait_pid(self):
        pidfile = self.tmp / "pid"
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if pidfile.exists() and pidfile.read_text():
                return int(pidfile.read_text())
            time.sleep(0.02)
        self.fail("the fake did not start")

    def assertDead(self, pid):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            try:  # a zombie child of init in a container still answers kill(0); check its state
                if "Z" in Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()[0]:
                    return
            except OSError:
                return
            time.sleep(0.02)
        self.fail("process %d is still alive" % pid)

    def test_cancel_kills_the_group(self):
        os.environ["FAKE_QT_HANG"] = "1"
        flag = threading.Event()
        threading.Timer(0.3, flag.set).start()
        started = time.monotonic()
        with self.assertRaises(engine.Cancelled):
            self.eng.design(self.design(), flag.is_set)
        self.assertLess(time.monotonic() - started, 3)
        self.assertDead(self.wait_pid())  # the grandchild too
        self.assertEqual(self.leftovers(), [])

    def test_timeout_kills_the_group(self):
        os.environ["FAKE_QT_HANG"] = "1"
        job = self.design(machine=self.machine_with(timeoutS=1))
        job.timeout_s = 0.3
        exc = self.error(lambda: self.eng.design(job, NEVER))
        self.assertIsInstance(exc, engine.EngineTimeout)
        self.assertEqual(exc.message, engine.TIMEOUT_MESSAGE)
        self.assertDead(self.wait_pid())
        self.assertEqual(self.leftovers(), [])

    def test_timeout_from_the_profile_when_the_job_has_none(self):
        os.environ["FAKE_QT_HANG"] = "1"
        job = self.design(machine=self.machine_with(timeoutS=0.3))
        self.assertIsInstance(self.error(lambda: self.eng.design(job, NEVER)), engine.EngineTimeout)

    def test_cancel_during_a_print_leaves_nothing(self):
        os.environ["FAKE_QT_HANG"] = "1"
        flag = threading.Event()
        threading.Timer(0.3, flag.set).start()
        with self.assertRaises(engine.Cancelled):
            self.eng.voiceprint(self.make_print(), flag.is_set)
        self.assertDead(self.wait_pid())
        self.assertEqual(self.leftovers(), [])

    def test_on_tick_hook_can_abort(self):
        os.environ["FAKE_QT_HANG"] = "1"

        def tick(proc):
            if (self.tmp / "pid").exists() and (self.tmp / "pid").read_text():  # once the fake is running
                raise engine.EngineError("memory", "limit.memory_abort")

        eng = engine_qwentts.QwenTtsEngine(on_tick=tick)
        exc = self.error(lambda: eng.design(self.design(), NEVER))
        self.assertEqual(exc.code, "limit.memory_abort")
        self.assertDead(self.wait_pid())
        self.assertEqual(len(self.calls()), 1)  # an abort is not a device failure

    # -- installed -------------------------------------------------------------------------------------------------

    def test_missing_model_at_run_time(self):
        os.unlink(self.mp("1.7b-voicedesign"))
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual((exc.code, exc.params["id"]), ("engine.model_missing", "1.7b-voicedesign"))
        self.assertEqual(self.calls(), [])

    def test_missing_binary_at_run_time(self):
        os.unlink(self.bin / "qwen-tts")
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual((exc.code, exc.params), ("engine.binary_missing", {"path": str(self.bin / "qwen-tts")}))

    def test_bin_dir_layout(self):
        del os.environ[engine_qwentts.BIN_ENV]
        base = Path(os.environ["GVOICE_DATA_HOME"]) / "engine"
        self.assertEqual(engine_qwentts.binary("qwen-tts", "Vulkan0"), base / "bin-vulkan" / "qwen-tts")
        self.assertEqual(engine_qwentts.binary("qwen-codec", "cpu"), base / "bin-cpu" / "qwen-codec")

    def test_check_configured_and_get_engine(self):
        os.environ["GVOICE_ENGINE"] = "qwentts"
        engine.check_configured()
        self.assertIsInstance(engine.get_engine(), engine_qwentts.QwenTtsEngine)
        self.assertEqual(engine.get_engine().provider, "qwentts")

    def test_check_configured_without_binaries(self):
        os.environ["GVOICE_ENGINE"] = "qwentts"
        os.environ[engine_qwentts.BIN_ENV] = str(self.tmp / "nowhere")
        with self.assertRaises(GvoiceError) as cm:
            engine.check_configured()
        self.assertEqual((cm.exception.code, cm.exception.params["path"]),
                         ("engine.binary_missing", str(self.tmp / "nowhere" / "qwen-tts")))
        os.unlink(self.bin / "qwen-codec")
        os.environ[engine_qwentts.BIN_ENV] = str(self.bin)
        with self.assertRaises(GvoiceError) as cm:
            engine.get_engine()
        self.assertEqual(cm.exception.params["path"], str(self.bin / "qwen-codec"))

    def test_check_configured_without_models(self):
        os.environ["GVOICE_ENGINE"] = "qwentts"
        for missing in ("tokenizer-12hz", "1.7b-voicedesign", "0.6b-base"):
            self.install_models()
            os.unlink(self.mp(missing))
            with self.assertRaises(GvoiceError) as cm:
                engine.check_configured()
            self.assertEqual((cm.exception.code, cm.exception.params["id"], cm.exception.params["state"]),
                             ("engine.model_missing", missing, "missing"))
        self.install_models()
        with open(self.mp("0.6b-base"), "wb") as fh:
            fh.write(b"short")
        with self.assertRaises(GvoiceError) as cm:
            engine.check_configured()
        self.assertEqual(cm.exception.params["state"], "bad_size")

    def test_not_needed_models_do_not_block(self):
        os.environ["GVOICE_ENGINE"] = "qwentts"
        os.unlink(self.mp("1.7b-base"))  # the second production model is optional
        engine.check_configured()

    def test_fake_stays_the_default(self):
        self.assertIsInstance(engine.get_engine(), engine.FakeEngine)

    def test_new_errors_are_translated(self):
        for lang in ("es", "en"):
            for code, params in (("engine.binary_missing", {"path": "p"}),
                                 ("engine.model_missing", {"id": "m", "path": "p", "state": "missing"}),
                                 ("engine.no_reference_text", {}), ("engine.bad_audio", {"reason": "empty"}),
                                 ("engine.print_not_written", {"path": ".spk"})):
                self.assertNotIn("error.", GvoiceError(code, **params).message(lang))


if __name__ == "__main__":
    unittest.main()

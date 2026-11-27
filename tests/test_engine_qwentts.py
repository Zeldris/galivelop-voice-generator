import contextlib
import json
import os
import signal
import subprocess
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
        "FAKE_QT_LATE_FAIL_S", "FAKE_QT_SLEEP_S", "FAKE_QT_KILL_SELF", "GRUN_MEMINFO", "GRUN_PROC_STATUS", "GALIVELOP_STATE_HOME", "GVOICE_ENGINE", "GVOICE_MACHINE_PROFILE")


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
        self.assertEqual(result.device, "cpu")  # as the profile writes it (common.schema.json); "CPU" only in argv
        self.assertEqual(result.command[result.command.index("--device") + 1], "CPU")
        self.assertEqual(wav_ms(self.out / "a.wav"), 500)

    def test_fallback_for_the_print_too(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        result = self.eng.voiceprint(self.make_print(), NEVER)
        self.assertEqual((result.device, len(self.calls())), ("cpu", 2))
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

    def test_no_fallback_when_the_process_dies_by_a_signal(self):
        os.environ["FAKE_QT_KILL_SELF"] = "1"  # the OOM killer's SIGKILL, say
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("exited with code -9 on Vulkan0", exc.message)

    def test_fallback_needs_the_start_memory_again(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        self.meminfo(2000)  # above watchMemoryMb (no abort), below minFreeMemoryMb
        exc = self.error(lambda: self.watched().design(self.design(), NEVER))
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("exited with code 3 on Vulkan0", exc.message)  # the error of the first attempt
        self.assertIn("failed to open device Vulkan0", exc.message)
        self.assertIn("no retry on CPU: free memory is 2000 MB, below the 4096 MB", exc.message)
        self.assertEqual(self.leftovers(), [])

    def test_fallback_with_enough_memory_and_a_watch(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        self.meminfo(6000)
        result = self.watched().design(self.design(), NEVER)
        self.assertEqual((result.device, len(self.calls())), ("cpu", 2))

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

    # -- orphans ------------------------------------------------------------------------------------------------

    def test_an_orphaned_engine_keeps_the_machine_lock(self):
        from gvoice import machine_lock
        os.environ["GALIVELOP_STATE_HOME"] = str(self.tmp / "state")
        os.environ["FAKE_QT_HANG"] = "1"
        code = ("from gvoice import engine, engine_qwentts, machine_lock, limits\n"
                "job = engine.DesignJob(instruction='x', text='hi', seed=1, output=%r, machine=limits.load_machine('steam-deck'))\n"
                "with machine_lock.hold():\n"
                "    engine_qwentts.QwenTtsEngine().design(job, lambda: False)\n" % str(self.out / "a.wav"))
        worker = subprocess.Popen([sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parent.parent))
        self.addCleanup(worker.wait)
        self.addCleanup(worker.kill)
        orphan_group = None
        try:
            sleeper = self.wait_pid()  # the fake's child: same session as the engine
            orphan_group = os.getpgid(sleeper)
            self.assertTrue(machine_lock.busy())
            worker.kill()  # SIGKILL: no finally runs, the worker's own descriptor closes
            worker.wait()
            time.sleep(0.2)
            self.assertTrue(machine_lock.busy())  # the engine, alive in its own session, still holds the lock
            self.assertIsNone(self.waits_for_lock())
        finally:
            if orphan_group:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(orphan_group, signal.SIGKILL)
        end = time.monotonic() + 3
        while machine_lock.busy() and time.monotonic() < end:
            time.sleep(0.02)
        self.assertFalse(machine_lock.busy())  # it is free again once the orphan is gone

    def waits_for_lock(self):
        """A new job asking for the lock while the orphan lives is told to wait: it gives up on cancel."""
        from gvoice import machine_lock
        with self.assertRaises(machine_lock.WaitCancelled):
            with machine_lock.hold(should_cancel=lambda: True):
                pass

    # -- memory watchdog (F2.3) -------------------------------------------------------------------------------------

    def meminfo(self, mb):
        path = self.tmp / "meminfo"
        path.write_text("MemTotal: 16000000 kB\nMemAvailable: %d kB\nBuffers: 1 kB\n" % (mb * 1024))
        os.environ["GRUN_MEMINFO"] = str(path)

    def watched(self):
        return engine_qwentts.QwenTtsEngine(watch_memory=True)

    def test_aborts_below_the_watch_threshold_with_code_and_values(self):
        os.environ["FAKE_QT_HANG"] = "1"
        self.meminfo(1000)
        exc = self.error(lambda: self.watched().design(self.design(), NEVER))
        self.assertIsInstance(exc, engine.EngineError)
        self.assertEqual((exc.code, exc.params), ("engine.low_memory", {"free": 1000, "min": 1536}))
        self.assertIn("1000", exc.message)
        self.assertIn("1536", exc.message)
        self.assertEqual(self.leftovers(), [])

    def free_sequence(self, *values):
        """`limits.available_memory_mb` giving these values one per sample and then the last one: no clock involved."""
        seen = []

        def read(*_args):
            seen.append(1)
            return values[min(len(seen), len(values)) - 1]

        patch = mock.patch.object(limits, "available_memory_mb", read)
        patch.start()
        self.addCleanup(patch.stop)
        return seen

    def fast_watch(self):
        patch = mock.patch.object(engine_qwentts, "WATCH_S", 0.02)
        patch.start()
        self.addCleanup(patch.stop)

    def test_aborts_when_memory_drops_while_running(self):
        os.environ["FAKE_QT_HANG"] = "1"
        self.fast_watch()
        seen = self.free_sequence(5000, 5000, 900)
        exc = self.error(lambda: self.watched().design(self.design(), NEVER))
        self.assertEqual((exc.code, exc.params["free"]), ("engine.low_memory", 900))
        self.assertGreaterEqual(len(seen), 3)  # sampled while running, not at the start only
        self.assertDead(self.wait_pid())
        self.assertEqual(len(self.calls()), 1)  # an abort is not a device failure: no fallback

    def test_a_failure_carries_the_memory_figures(self):
        os.environ["FAKE_QT_HANG"] = "1"
        status = self.tmp / "status"
        status.write_text("VmHWM:\t  1048576 kB\n")
        os.environ["GRUN_PROC_STATUS"] = str(status)
        self.meminfo(1000)
        exc = self.error(lambda: self.watched().design(self.design(), NEVER))
        self.assertEqual(exc.stats, {"min_free_mb": 1000, "peak_rss_mb": 1024})

    def test_timeout_and_cancel_carry_the_memory_figures(self):
        os.environ["FAKE_QT_HANG"] = "1"
        self.meminfo(6000)
        job = self.design()
        job.timeout_s = 0.3
        exc = self.error(lambda: self.watched().design(job, NEVER))
        self.assertIsInstance(exc, engine.EngineTimeout)
        self.assertEqual(exc.stats["min_free_mb"], 6000)
        asked = iter(range(100))  # false on the first check (the first sample is taken), true after
        with self.assertRaises(engine.Cancelled) as cm:
            self.watched().design(self.design(), lambda: next(asked) > 1)
        self.assertEqual(cm.exception.stats["min_free_mb"], 6000)

    def test_a_failed_exit_carries_the_figures_and_unwatched_ones_none(self):
        os.environ["FAKE_QT_CRASH"] = "1"
        self.meminfo(6000)
        exc = self.error(lambda: self.watched().design(self.design(), NEVER))
        self.assertEqual(exc.stats["min_free_mb"], 6000)
        self.assertIsNone(self.error(lambda: self.eng.design(self.design(), NEVER)).stats)

    def no_wait4(self):
        """`os.wait4` as if it gave no usage (ru_maxrss 0): the sampled VmHWM stays."""
        real = os.wait4

        def wait4(pid, options):
            got = real(pid, options)
            return got if got[0] == 0 else (got[0], got[1], mock.Mock(ru_maxrss=0))

        patch = mock.patch.object(os, "wait4", wait4)
        patch.start()
        self.addCleanup(patch.stop)

    def test_enough_memory_does_not_abort_and_reports_the_lowest_and_the_sampled_peak(self):
        os.environ["FAKE_QT_SLEEP_S"] = "0.6"
        self.fast_watch()
        self.free_sequence(6000, 3000, 4000)
        self.no_wait4()
        status = self.tmp / "status"
        status.write_text("Name:\tqwen-tts\nVmHWM:\t  2097152 kB\nVmRSS:\t 1 kB\n")
        os.environ["GRUN_PROC_STATUS"] = str(status)
        result = self.watched().design(self.design(), NEVER)
        self.assertEqual((result.min_free_mb, result.peak_rss_mb), (3000, 2048))

    def test_peak_rss_is_the_exact_one_of_wait4(self):
        os.environ["FAKE_QT_SLEEP_S"] = "0.3"
        self.meminfo(6000)
        status = self.tmp / "status"
        status.write_text("VmHWM:\t  2097152 kB\n")  # the sampled one, lower than the real peak
        os.environ["GRUN_PROC_STATUS"] = str(status)
        real = os.wait4

        def wait4(pid, options):
            got = real(pid, options)
            return got if got[0] == 0 else (got[0], got[1], mock.Mock(ru_maxrss=3 * 1024 * 1024))

        with mock.patch.object(os, "wait4", wait4):
            result = self.watched().design(self.design(), NEVER)
        self.assertEqual(result.peak_rss_mb, 3072)
        self.assertEqual(len(self.calls()), 1)

    def test_wait4_keeps_the_exit_code_and_signals_of_popen(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        machine = self.machine_with(engine={"device": "Vulkan0"})
        exc = self.error(lambda: self.eng.design(self.design(machine=machine), NEVER))
        self.assertIn("exited with code 3", exc.message)
        os.environ["FAKE_QT_FAIL_DEVICE"] = ""
        os.environ["FAKE_QT_KILL_SELF"] = "1"
        exc = self.error(lambda: self.eng.design(self.design(), NEVER))
        self.assertIn("exited with code -9", exc.message)

    def test_peak_rss_of_the_real_process(self):
        os.environ["FAKE_QT_SLEEP_S"] = "0.3"
        self.meminfo(6000)
        result = self.watched().design(self.design(), NEVER)
        self.assertIsInstance(result.peak_rss_mb, int)
        self.assertGreater(result.peak_rss_mb, 0)

    def test_unreadable_sources_give_none_and_no_abort(self):
        os.environ["FAKE_QT_SLEEP_S"] = "0.3"
        os.environ["GRUN_MEMINFO"] = str(self.tmp / "nope")
        os.environ["GRUN_PROC_STATUS"] = str(self.tmp / "nope2")
        self.no_wait4()
        result = self.watched().design(self.design(), NEVER)
        self.assertEqual((result.min_free_mb, result.peak_rss_mb), (None, None))

    def test_without_the_watchdog_nothing_is_reported(self):
        os.environ["FAKE_QT_SLEEP_S"] = "0.3"
        self.meminfo(10)  # would abort if watched
        result = self.eng.design(self.design(), NEVER)
        self.assertEqual((result.min_free_mb, result.peak_rss_mb), (None, None))

    def test_the_watch_samples_at_its_interval(self):
        now = [0.0]
        watch = engine_qwentts.MemoryWatch(self.machine, interval_s=0.5, clock=lambda: now[0])
        proc = mock.Mock(pid=os.getpid())
        self.meminfo(3000)
        watch(proc)
        self.meminfo(2000)
        now[0] = 0.3
        watch(proc)
        self.assertEqual(watch.min_free_mb, 3000)  # not sampled yet
        now[0] = 0.6
        watch(proc)
        self.assertEqual(watch.min_free_mb, 2000)

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

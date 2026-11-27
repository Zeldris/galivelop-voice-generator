import contextlib
import io
import json
import os
import re
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from gvoice import bench, cli, engine, engine_qwentts, limits, machine_lock, models

FAKE = str(Path(__file__).resolve().parent / "fake_qwentts.py")
ENV_VARS = ("FAKE_QT_FAIL_DEVICE", "FAKE_QT_HANG", "FAKE_QT_NOWAV", "FAKE_QT_BADWAV", "FAKE_QT_CRASH",
            "FAKE_QT_LATE_FAIL_S", "FAKE_QT_SLEEP_S", "FAKE_QT_KILL_SELF", "GRUN_PROC_STATUS",
            "GVOICE_MACHINE_PROFILE", "GVOICE_FAKE_DELAY", "GVOICE_FAKE_FAIL")


class BenchBase(unittest.TestCase):
    engine_name = "fake"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, mode in (("qwen-tts", "tts"), ("qwen-codec", "codec")):
            script = self.bin / name
            script.write_text('#!/bin/sh\nexec "%s" "%s" %s "$@"\n' % (sys.executable, FAKE, mode))
            script.chmod(0o755)
        self.meminfo = self.tmp / "meminfo"
        self.meminfo.write_text("MemTotal: 16000000 kB\nMemAvailable: 8000000 kB\n")
        self.log = self.tmp / "calls.jsonl"
        env = {"GVOICE_DATA_HOME": str(self.tmp / "data"), "GVOICE_MODELS_HOME": str(self.tmp / "models"),
               "GVOICE_CONFIG_HOME": str(self.tmp / "config"), "GALIVELOP_STATE_HOME": str(self.tmp / "state"),
               engine_qwentts.BIN_ENV: str(self.bin), "FAKE_QT_LOG": str(self.log), "GVOICE_LANG": "en",
               "GVOICE_ENGINE": self.engine_name, "GRUN_MEMINFO": str(self.meminfo)}
        env.update({v: "" for v in ENV_VARS})
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        self.catalog = models.load("qwentts")
        self.install_models()
        self.machine = limits.load_machine("steam-deck")
        self.out = self.tmp / "out"

    def install_models(self, skip=()):
        (self.tmp / "models").mkdir(exist_ok=True)
        for model in self.catalog["models"]:
            if model["id"] not in skip:
                with open(models.model_path(model), "wb") as fh:
                    fh.truncate(model["bytes"])

    def bench(self, *args, lang="en"):
        """Run `gvoice bench` through the CLI: ``(code, stdout, stderr)``."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["bench", "--lang", lang, "--out", str(self.out)] + list(args))
        return code, out.getvalue(), err.getvalue()

    def doc(self):
        return json.loads((self.out / "bench.json").read_text(encoding="utf-8"))

    def keys(self, doc=None):
        return [(r["step"], r["model"], r["device"], r["phrase"]) for r in (doc or self.doc())["rows"]]

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []


class FakeEngineMatrixTests(BenchBase):
    def test_full_matrix_and_files(self):
        code, stdout, _ = self.bench()
        self.assertEqual(code, 0)
        doc = self.doc()
        self.assertEqual(self.keys(doc), [
            ("design", "1.7b-voicedesign", "Vulkan0", "short"), ("design", "1.7b-voicedesign", "Vulkan0", "long"),
            ("print", "0.6b-base", "Vulkan0", "take"), ("print", "1.7b-base", "Vulkan0", "take"),
            ("produce", "0.6b-base", "Vulkan0", "short"), ("produce", "0.6b-base", "Vulkan0", "long"),
            ("produce", "1.7b-base", "Vulkan0", "short"), ("produce", "1.7b-base", "Vulkan0", "long")])
        self.assertTrue(doc["ok"] and not doc["cancelled"])
        self.assertTrue(all(r["status"] == "ok" for r in doc["rows"]))
        for row in doc["rows"]:
            for name in row["files"]:
                self.assertTrue((self.out / name).is_file(), name)
        self.assertEqual(sorted(p.name for p in self.out.glob("*.spk")),
                         ["print-Vulkan0-0.6b-base.spk", "print-Vulkan0-1.7b-base.spk"])
        self.assertTrue((self.out / "bench.md").is_file())
        self.assertIn("| Step | Model | Dev. | Phrase |", stdout)
        self.assertIn("Bench written to %s" % self.out, stdout)

    def test_filtered_by_steps_models_and_devices(self):
        code, _, _ = self.bench("--steps", "design")
        self.assertEqual(self.keys(), [("design", "1.7b-voicedesign", "Vulkan0", "short"),
                                       ("design", "1.7b-voicedesign", "Vulkan0", "long")])
        code, _, _ = self.bench("--steps", "design,print,produce", "--models", "1.7b-base", "--devices",
                                "Vulkan0,cpu")
        self.assertEqual(code, 0)
        self.assertEqual(self.keys(), [
            ("design", "1.7b-voicedesign", "Vulkan0", "short"), ("design", "1.7b-voicedesign", "Vulkan0", "long"),
            ("print", "1.7b-base", "Vulkan0", "take"),
            ("produce", "1.7b-base", "Vulkan0", "short"), ("produce", "1.7b-base", "Vulkan0", "long"),
            ("design", "1.7b-voicedesign", "cpu", "short"), ("design", "1.7b-voicedesign", "cpu", "long"),
            ("print", "1.7b-base", "cpu", "take"),
            ("produce", "1.7b-base", "cpu", "short"), ("produce", "1.7b-base", "cpu", "long")])
        self.assertEqual({r["device"] for r in self.doc()["rows"]}, {"Vulkan0", "cpu"})

    def test_later_steps_reuse_the_files_of_an_earlier_run(self):
        self.assertEqual(self.bench("--steps", "design,print")[0], 0)
        code, _, _ = self.bench("--steps", "produce", "--models", "0.6b-base")
        self.assertEqual(code, 0)
        self.assertEqual(self.keys(), [("produce", "0.6b-base", "Vulkan0", "short"),
                                       ("produce", "0.6b-base", "Vulkan0", "long")])

    def test_steps_without_their_input_are_skipped_with_the_reason(self):
        code, stdout, _ = self.bench("--steps", "print,produce")
        self.assertEqual(code, 1)
        rows = self.doc()["rows"]
        self.assertEqual({r["status"] for r in rows}, {"skipped"})
        self.assertEqual({r["code"] for r in rows}, {"bench.missing_input"})
        self.assertIn("design-Vulkan0-s7-long.wav", rows[0]["message"])
        self.assertIn("skipped (bench.missing_input)", stdout)

    def test_seed_default_and_option_go_to_the_rows_and_names(self):
        self.bench("--steps", "design")
        self.assertEqual({r["seed"] for r in self.doc()["rows"]}, {7})
        self.bench("--steps", "design", "--seed", "21")
        self.assertEqual({r["seed"] for r in self.doc()["rows"]}, {21})
        self.assertTrue((self.out / "design-Vulkan0-s21-long.wav").is_file())

    def test_default_out_is_under_the_data_folder(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["bench", "--steps", "design", "--json"]), 0)
        doc = json.loads(out.getvalue())
        folder = Path(doc["out"])
        self.assertEqual(folder.parent, self.tmp / "data" / "bench")
        self.assertRegex(folder.name, r"^\d{4}-\d\d-\d\d-\d{6}$")
        self.assertTrue((folder / "bench.json").is_file())
        self.assertEqual(len(doc["rows"]), 2)

    def test_bad_options_say_why(self):
        code, _, err = self.bench("--steps", "design,paint")
        self.assertEqual(code, 1)
        self.assertIn("unknown steps in --steps: paint", err)
        code, _, err = self.bench("--devices", ",")
        self.assertEqual(code, 1)
        self.assertIn("--devices cannot be empty", err)
        self.assertFalse((self.out / "bench.json").exists())


class FailureTests(BenchBase):
    def run_bench(self, eng, steps=bench.STEPS, devices=("Vulkan0",), models=("0.6b-base", "1.7b-base")):
        with contextlib.redirect_stderr(io.StringIO()):
            return bench.run(eng, self.machine, list(models), list(devices), list(steps), 7, self.out, "en")

    def test_failed_design_skips_what_depends_on_it_and_the_rest_goes_on(self):
        class DesignFailsOnCpu(engine.FakeEngine):
            def design(self, job, should_cancel):
                if job.device == "cpu":
                    raise engine.EngineError("no design on the cpu today", "engine.bad_audio", reason="x")
                return super().design(job, should_cancel)

        doc = self.run_bench(DesignFailsOnCpu(), devices=("cpu", "Vulkan0"), models=("0.6b-base",))
        by = {(r["step"], r["device"], r["phrase"]): r for r in doc["rows"]}
        self.assertEqual(by[("design", "cpu", "short")]["status"], "failed")
        self.assertEqual(by[("design", "cpu", "short")]["code"], "engine.bad_audio")
        self.assertEqual(by[("design", "cpu", "short")]["message"], "no design on the cpu today")
        for key in (("print", "cpu", "take"), ("produce", "cpu", "short"), ("produce", "cpu", "long")):
            self.assertEqual((by[key]["status"], by[key]["code"]), ("skipped", "bench.missing_input"), key)
        for key in (("design", "Vulkan0", "long"), ("print", "Vulkan0", "take"), ("produce", "Vulkan0", "long")):
            self.assertEqual(by[key]["status"], "ok", key)
        self.assertFalse(doc["ok"])
        self.assertEqual(sum(r["status"] == "ok" for r in doc["rows"]), 5)

    def test_failed_and_cancelled_rows_keep_their_time(self):
        class SlowFail(engine.FakeEngine):
            def design(self, job, should_cancel):
                time.sleep(0.02)
                raise engine.EngineError("boom", "engine.failed")

        failed = self.run_bench(SlowFail(), steps=("design",))["rows"][0]
        self.assertEqual(failed["status"], "failed")
        self.assertIsNotNone(failed["wall_s"])
        self.assertGreaterEqual(failed["wall_s"], 0.02)

        class SlowCancel(engine.FakeEngine):
            def design(self, job, should_cancel):
                time.sleep(0.02)
                raise engine.Cancelled()

        cancelled = self.run_bench(SlowCancel(), steps=("design",))["rows"][0]
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertGreaterEqual(cancelled["wall_s"], 0.02)

    def test_failed_step_leaves_no_stale_file_for_the_next_one(self):
        self.run_bench(engine.FakeEngine(), steps=("design",))
        self.assertTrue((self.out / "design-Vulkan0-s7-long.wav").is_file())
        doc = self.run_bench(engine.FakeEngine(fail_with="boom"), steps=("design", "print"))
        self.assertEqual([r["status"] for r in doc["rows"]], ["failed", "failed", "skipped", "skipped"])
        self.assertEqual(doc["rows"][0]["message"], "boom")
        self.assertEqual(doc["rows"][0]["code"], "engine.failed")

    def test_exit_code_and_table_through_the_cli_with_one_model_missing(self):
        # 1.7b-base is not installed: its print fails (model_missing), its produce is skipped, the 0.6b rows are fine
        os.environ["GVOICE_ENGINE"] = "qwentts"
        (self.tmp / "models" / models.model_path(next(m for m in self.catalog["models"]
                                                      if m["id"] == "1.7b-base")).name).unlink(missing_ok=True)
        code, stdout, _ = self.bench()
        self.assertEqual(code, 1)
        rows = {(r["step"], r["model"], r["phrase"]): r for r in self.doc()["rows"]}
        failed = rows[("print", "1.7b-base", "take")]
        self.assertEqual((failed["status"], failed["code"]), ("failed", "engine.model_missing"))
        self.assertIn("model 1.7b-base is not installed", failed["message"])
        self.assertEqual(rows[("produce", "1.7b-base", "long")]["status"], "skipped")
        self.assertEqual(rows[("produce", "0.6b-base", "long")]["status"], "ok")
        self.assertRegex(stdout, r"\| Print \| 1\.7b-base \| Vulkan0 \| long take \| .* \| failed \(engine\.model_missing\) \|")
        self.assertRegex(stdout, r"\| Produce s7 \| 1\.7b-base \| Vulkan0 \| long \| - \| - \| - \| - \| - \| skipped")

    def test_cancel_with_sigint_stops_cleanly_and_writes_the_files(self):
        class Interrupted(engine.FakeEngine):
            def design(self, job, should_cancel):
                signal.raise_signal(signal.SIGINT)  # handled by the bench: a flag, not an exception
                if should_cancel():
                    raise engine.Cancelled()
                return super().design(job, should_cancel)

        before = signal.getsignal(signal.SIGINT)
        doc = self.run_bench(Interrupted())
        self.assertIs(signal.getsignal(signal.SIGINT), before)
        self.assertTrue(doc["cancelled"] and not doc["ok"])
        self.assertEqual([(r["step"], r["status"]) for r in doc["rows"]], [("design", "cancelled")])
        self.assertEqual(self.doc()["cancelled"], True)
        self.assertIn("cancelled", (self.out / "bench.md").read_text())
        self.assertFalse(machine_lock.busy())

    def test_cancel_exit_code_is_130(self):
        class Interrupted(engine.FakeEngine):
            def design(self, job, should_cancel):
                signal.raise_signal(signal.SIGINT)
                return super().design(job, should_cancel)

        with mock.patch.object(engine, "get_engine", lambda: Interrupted()):
            code, _, _ = self.bench()
        self.assertEqual(code, 130)  # the second step sees the flag
        self.assertEqual(len(self.doc()["rows"]), 1)


class LockTests(BenchBase):
    def test_machine_lock_is_held_during_the_whole_bench(self):
        seen = []

        class Spy(engine.FakeEngine):
            def _wait(self, job, should_cancel):
                seen.append(machine_lock.busy())
                return super()._wait(job, should_cancel)

        self.assertFalse(machine_lock.busy())
        with contextlib.redirect_stderr(io.StringIO()):
            doc = bench.run(Spy(), self.machine, ["0.6b-base"], ["Vulkan0"], list(bench.STEPS), 7, self.out, "en")
        self.assertEqual(len(seen), 5)
        self.assertEqual(set(seen), {True})
        self.assertTrue(doc["ok"])
        self.assertFalse(machine_lock.busy())  # released at the end

    def test_a_busy_machine_makes_the_bench_wait_and_say_so(self):
        err = io.StringIO()
        result = {}

        def go():
            with contextlib.redirect_stderr(err):
                result["doc"] = bench.run(engine.FakeEngine(), self.machine, ["0.6b-base"], ["Vulkan0"],
                                          ["design"], 7, self.out, "en")

        with machine_lock.hold():
            thread = threading.Thread(target=go)
            thread.start()
            deadline = time.monotonic() + 5
            while "machine is busy" not in err.getvalue() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertIn("the machine is busy with another generator", err.getvalue())
            self.assertNotIn("doc", result)
        thread.join(10)
        self.assertEqual(len(result["doc"]["rows"]), 2)


class QwenTtsBenchTests(BenchBase):
    engine_name = "qwentts"

    def test_matrix_with_the_real_engine_wrapper(self):
        code, stdout, _ = self.bench("--models", "0.6b-base")
        self.assertEqual(code, 0, stdout)
        doc = self.doc()
        self.assertEqual(len(doc["rows"]), 5)
        self.assertEqual(doc["engine"], "qwentts")
        self.assertEqual(doc["engineCommit"], self.catalog["commit"])
        short, long_ = doc["rows"][0], doc["rows"][1]
        self.assertEqual((short["audio_s"], long_["audio_s"]), (len(bench.PHRASES["short"]) / 10,
                                                                len(bench.PHRASES["long"]) / 10))
        for row in doc["rows"]:
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["min_free_mb"], 7812)  # from GRUN_MEMINFO, sampled by the memory watch
            self.assertIsInstance(row["peak_rss_mb"], int)
        self.assertIsNone(doc["rows"][2]["audio_s"])  # the print has no audio
        calls = self.calls()
        self.assertEqual([c["mode"] for c in calls], ["tts", "tts", "codec", "tts", "tts"])
        self.assertEqual(calls[0]["stdin"], bench.PHRASES["short"])
        argv = calls[0]["argv"]
        self.assertEqual(argv[argv.index("--seed") + 1], "7")
        produce = calls[3]["argv"]
        self.assertIn("--ref-spk", produce)
        self.assertIn(self.out.name, produce[produce.index("--ref-spk") + 1])

    def test_a_forced_device_never_falls_back(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        code, _, _ = self.bench("--steps", "design", "--devices", "Vulkan0")
        self.assertEqual(code, 1)
        rows = self.doc()["rows"]
        self.assertEqual([r["status"] for r in rows], ["failed", "failed"])
        self.assertEqual(rows[0]["code"], "engine.failed")
        self.assertIn("failed to open device Vulkan0", rows[0]["message"])
        # the profile's fallbackDevice (cpu) was never tried, and the row says the device it was asked for
        self.assertEqual({c["argv"][c["argv"].index("--device") + 1] for c in self.calls()}, {"Vulkan0"})
        self.assertEqual({r["device"] for r in rows}, {"Vulkan0"})

    def test_without_no_fallback_the_engine_still_falls_back(self):
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        job = engine.DesignJob(instruction="x", text="hi", seed=1, output=str(self.tmp / "a.wav"),
                               machine=self.machine)
        result = engine_qwentts.QwenTtsEngine().design(job, lambda: False)
        self.assertEqual(result.device, "cpu")
        os.environ["FAKE_QT_FAIL_DEVICE"] = "Vulkan0"
        job = engine.DesignJob(instruction="x", text="hi", seed=1, output=str(self.tmp / "b.wav"),
                               machine=self.machine, no_fallback=True, device="Vulkan0")
        with self.assertRaises(engine.EngineError) as cm:
            engine_qwentts.QwenTtsEngine().design(job, lambda: False)
        self.assertIn("failed to open device Vulkan0", cm.exception.message)

    def test_json_output(self):
        code, stdout, _ = self.bench("--steps", "design", "--json")
        self.assertEqual(code, 0)
        data = json.loads(stdout)
        self.assertEqual(data["rows"], self.doc()["rows"])
        self.assertEqual(data["steps"], ["design"])


class TableTests(BenchBase):
    def sample(self):
        row = {"step": "design", "seed": 11, "model": "1.7B VoiceDesign", "device": "CPU", "phrase": "long",
               "wall_s": 66.1, "audio_s": 16.16, "rtf": 66.1 / 16.16, "peak_rss_mb": 4689, "min_free_mb": 2325,
               "status": "ok", "code": None, "message": None, "files": []}
        printed = dict(row, step="print", seed=None, phrase="take", wall_s=5.8, audio_s=None, rtf=None,
                       peak_rss_mb=None, min_free_mb=None)
        failed = dict(row, step="produce", seed=7, phrase="short", wall_s=None, audio_s=None, rtf=None,
                      peak_rss_mb=None, min_free_mb=None, status="failed", code="engine.low_memory")
        return {"date": "2026-11-14T10:00:00+01:00", "engine": "qwentts", "engineVersion": "qwentts-5916bf7",
                "engineCommit": "5916bf7abc", "machine": {"profile": "steam-deck", "cpu": "AMD Test", "memory_mb": 15000},
                "seed": 7, "rows": [row, printed, failed]}

    def test_rows_use_the_comma_decimal_and_dash(self):
        lines = bench.render(self.sample(), "es").splitlines()
        self.assertIn("| Paso | Modelo | Disp. | Frase | Pared s | Audio s | RTF | Pico RSS MB | Mín. MemAvail MB | Estado |",
                      lines)
        self.assertIn("| Diseño s11 | 1.7B VoiceDesign | CPU | larga | 66,1 | 16,16 | 4,09 | 4689 | 2325 | ok |", lines)
        self.assertIn("| Fijar | 1.7B VoiceDesign | CPU | toma larga | 5,8 | - | - | - | - | ok |", lines)
        self.assertIn("| Producir s7 | 1.7B VoiceDesign | CPU | corta | - | - | - | - | - | fallo (engine.low_memory) |",
                      lines)
        head = "\n".join(lines[:8])
        for text in ("2026-11-14T10:00:00+01:00", "qwentts qwentts-5916bf7", "5916bf7abc", "steam-deck", "AMD Test",
                     "15000 MB"):
            self.assertIn(text, head)

    def test_english_headers_and_status(self):
        text = bench.render(self.sample(), "en")
        self.assertIn("| Step | Model | Dev. | Phrase | Wall s | Audio s | RTF | Peak RSS MB | Min. MemAvail MB | Status |",
                      text)
        self.assertIn("failed (engine.low_memory)", text)

    def test_rtf_is_wall_over_audio_and_prints_have_none(self):
        class Slow(engine.FakeEngine):
            def design(self, job, should_cancel):
                time.sleep(0.05)
                return super().design(job, should_cancel)

        with contextlib.redirect_stderr(io.StringIO()):
            doc = bench.run(Slow(), self.machine, ["0.6b-base"], ["Vulkan0"], list(bench.STEPS), 7, self.out, "en")
        design = doc["rows"][0]
        self.assertGreaterEqual(design["wall_s"], 0.05)
        self.assertAlmostEqual(design["rtf"], design["wall_s"] / design["audio_s"])
        self.assertAlmostEqual(design["audio_s"], engine._audio_ms(bench.PHRASES["short"]) / 1000)
        printed = doc["rows"][2]
        self.assertEqual((printed["step"], printed["audio_s"], printed["rtf"]), ("print", None, None))
        self.assertIsNone(printed["peak_rss_mb"])  # the fake engine measures no memory
        table = (self.out / "bench.md").read_text(encoding="utf-8")
        self.assertRegex(table, r"\| Print \| 0\.6b-base \| Vulkan0 \| long take \| \d+,\d \| - \| - \| - \| - \| ok \|")
        self.assertRegex(table, r"\| Design s7 \| 1\.7b-voicedesign \| Vulkan0 \| short \| \d+,\d \| \d+,\d\d \| \d+,\d\d \|")

    def test_machine_memory_comes_from_gvoice_meminfo(self):
        self.assertEqual(bench.machine_info(self.machine)["memory_mb"], 15625)  # 16000000 kB of the fake meminfo
        self.meminfo.write_text("MemAvailable: 8000000 kB\n")
        self.assertIsNone(bench.machine_info(self.machine)["memory_mb"])

    def test_bench_texts_exist_in_both_languages(self):
        from gvoice import i18n
        for lang in ("es", "en"):
            for key in ("bench.title", "bench.col.step", "bench.step.print", "bench.phrase.take",
                        "bench.status.cancelled", "cli.cmd.bench", "error.bench.bad_steps"):
                self.assertNotEqual(i18n.t(key, lang, steps="a", allowed="b", option="o", code="c"), key, (lang, key))


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import engine, machine_lock
from tests.test_cli import CliBase
from tests.test_qwentts import MACHINE, clean_env, install_fake

PROFILE = dict(MACHINE, name="bench-test", models={"design": "1.7b-voicedesign",
                                                   "produce": ["0.6b-base", "1.7b-base"]})


def bench_dirs(data: Path):
    return sorted((data / "bench").iterdir())


class BenchBase(CliBase):
    def use_qwen(self):
        clean_env()
        os.environ["GVOICE_ENGINE"] = "qwentts"
        os.environ["FAKE_LOG"] = str(self.tmp / "calls.jsonl")
        install_fake()
        profile = self.tmp / "profile.json"
        profile.write_text(json.dumps(PROFILE))
        os.environ["GVOICE_MACHINE_PROFILE"] = str(profile)

    def calls(self):
        return [json.loads(line) for line in (self.tmp / "calls.jsonl").read_text().splitlines()]


class FakeEngineBench(BenchBase):
    def test_table_files_and_json(self):
        data = self.js("bench")
        folder, = bench_dirs(self.tmp / "data")
        self.assertEqual(data["path"], str(folder))
        self.assertEqual((data["engine"], data["seed"], data["quick"]), ("fake", 11, False))
        # steam-deck profile: 2 devices x (design + 2 models x (print + 2 lines))
        rows = data["rows"]
        self.assertEqual(len(rows), 2 * (1 + 2 * 3))
        self.assertEqual({r["device"] for r in rows}, {"Vulkan0", "cpu"})
        self.assertEqual([r["task"] for r in rows[:7]],
                         ["design", "print", "line-short", "line-long", "print", "line-short", "line-long"])
        self.assertEqual([r["model"] for r in rows[:7]], ["1.7b-voicedesign"] + ["0.6b-base"] * 3 + ["1.7b-base"] * 3)
        self.assertTrue(all(r["error"] is None and r["peak_rss_mb"] is None for r in rows))
        long_row = rows[3]
        self.assertGreater(long_row["audio_ms"], rows[2]["audio_ms"])
        self.assertEqual(long_row["rtf"], round(long_row["duration_ms"] / long_row["audio_ms"], 3))
        self.assertIsNone(rows[1]["audio_ms"])  # a print has no audio...
        self.assertIsNone(rows[1]["rtf"])  # ...so no RTF
        saved = json.loads((folder / "bench.json").read_text())
        self.assertEqual(saved["rows"], rows)
        md = (folder / "bench.md").read_text()
        self.assertIn("| task | model | device | duration_ms | audio_ms | rtf | min_free_mb | peak_rss_mb | error |", md)
        self.assertEqual(md.count("| line-long | "), 4)
        wavs = sorted(p.name for p in folder.glob("*.wav"))
        self.assertEqual(len(wavs), 2 + 2 * 2 * 2)
        self.assertIn("design-1.7b-voicedesign-vulkan0.wav", wavs)
        self.assertTrue((folder / "0.6b-base-cpu.spk").is_file() and (folder / "1.7b-base-cpu.rvq").is_file())

    def test_text_output_lists_path_and_table(self):
        out = self.ok("bench", "--quick")
        folder, = bench_dirs(self.tmp / "data")
        self.assertIn("Bench finished: %s" % folder, out)
        self.assertIn("| line-short | 0.6b-base | Vulkan0 |", out)
        self.assertNotIn("cpu", out.split("Bench finished")[1])

    def test_quick_and_seed_alias(self):
        data = self.js("bench", "--rapido", "--semilla", "5")
        self.assertEqual((data["seed"], data["quick"]), (5, True))
        self.assertEqual({(r["device"], r["model"]) for r in data["rows"]},
                         {("Vulkan0", "1.7b-voicedesign"), ("Vulkan0", "0.6b-base")})
        self.assertEqual(len(data["rows"]), 4)

    def test_forced_device_gets_no_fallback(self):
        seen = []
        real = engine.FakeEngine.design

        def spy(eng, job, should_cancel):
            seen.append((job.device, job.machine["engine"]))
            return real(eng, job, should_cancel)

        with mock.patch.object(engine.FakeEngine, "design", spy):
            self.ok("bench")
        self.assertEqual(seen, [("Vulkan0", {"device": "Vulkan0"}), ("cpu", {"device": "cpu"})])

    def test_holds_the_machine_lock_the_whole_time(self):
        busy = []
        real = engine.FakeEngine

        def spy(name):
            original = getattr(real, name)

            def wrapper(eng, job, should_cancel):
                busy.append(machine_lock.busy())
                return original(eng, job, should_cancel)
            return wrapper

        with mock.patch.multiple(real, design=spy("design"), voiceprint=spy("voiceprint"), line=spy("line")):
            self.ok("bench", "--quick")
        self.assertEqual(busy, [True] * 4)
        self.assertFalse(machine_lock.busy())

    def test_ctrl_c_exits_130_and_frees_the_lock(self):
        with mock.patch.object(engine.FakeEngine, "line", side_effect=KeyboardInterrupt):
            code, out, err = self.run_cli("bench", "--quick")
        self.assertEqual(code, 130)
        self.assertFalse(machine_lock.busy())

    def test_unknown_engine_is_an_error(self):
        os.environ["GVOICE_ENGINE"] = "nope"
        self.fails("bench", message="nope")

    def test_spanish_text(self):
        out = self.ok("--lang", "es", "bench", "--quick")
        self.assertIn("Banco terminado:", out)


class QwenBench(BenchBase):
    def setUp(self):
        super().setUp()
        self.use_qwen()

    def test_runs_the_binaries_on_each_device_once(self):
        data = self.js("bench", "--quick")
        self.assertEqual(len(data["rows"]), 4)
        self.assertTrue(all(r["error"] is None for r in data["rows"]))
        self.assertTrue(all(r["min_free_mb"] is None or isinstance(r["min_free_mb"], int) for r in data["rows"]))
        calls = self.calls()
        self.assertEqual([(c["prog"], c["device"]) for c in calls],
                         [("qwen-tts", "Vulkan0"), ("qwen-codec", "Vulkan0"),
                          ("qwen-tts", "Vulkan0"), ("qwen-tts", "Vulkan0")])
        self.assertEqual(data["rows"][0]["audio_ms"], 500)

    def test_both_devices_and_all_models(self):
        data = self.js("bench")
        self.assertEqual(len(data["rows"]), 14)
        self.assertEqual({c["device"] for c in self.calls()}, {"Vulkan0", "CPU"})
        self.assertEqual({r["device"] for r in data["rows"]}, {"Vulkan0", "cpu"})

    def test_a_failed_measure_is_a_row_and_does_not_stop_the_rest(self):
        os.environ["FAKE_FAIL_DEVICES"] = "Vulkan0"
        data = self.js("bench")
        vulkan = [r for r in data["rows"] if r["device"] == "Vulkan0"]
        self.assertEqual(len(vulkan), 7)
        self.assertIn("boom on Vulkan0", vulkan[0]["error"])  # the design, failed on its own device: no fallback
        self.assertIsNone(vulkan[0]["audio_ms"])
        self.assertTrue(all(r["error"] for r in vulkan))
        self.assertEqual([r["error"] for r in vulkan[1:3]], ["no design take to fix", "no voice print"])
        cpu = [r for r in data["rows"] if r["device"] == "cpu"]
        self.assertEqual(len(cpu), 7)
        self.assertTrue(all(r["error"] is None for r in cpu))
        # the failure on Vulkan0 never ran on CPU by itself: every CPU call belongs to the CPU phase
        self.assertEqual(sum(1 for c in self.calls() if c["device"] == "Vulkan0"), 1)
        md = (bench_dirs(self.tmp / "data")[0] / "bench.md").read_text()
        self.assertIn("boom on Vulkan0", md)

    def test_text_mode_counts_failed_measures(self):
        os.environ["FAKE_FAIL_DEVICES"] = "Vulkan0"
        out = self.ok("bench", "--quick")
        self.assertIn("4 measures failed.", out)

    def test_device_not_installed_is_skipped(self):
        for path in (self.tmp / "data" / "engine").glob("install.json"):
            path.unlink()
        install_fake(devices=("Vulkan0",))
        data = self.js("bench")
        self.assertEqual({r["device"] for r in data["rows"]}, {"Vulkan0"})


class LimitErrorTests(unittest.TestCase):
    def test_a_memory_limit_is_a_row_and_does_not_stop_the_rest(self):
        from gvoice import bench, engine
        from gvoice.limits import LimitError

        class Eng(engine.FakeEngine):
            def design(self, job, should_cancel):
                if job.device == "Vulkan0":
                    raise LimitError("limit.memory_abort", free=100, watch=1536)
                return super().design(job, should_cancel)

        machine = {"name": "t", "timeoutS": 60, "models": {"design": "1.7b-voicedesign", "produce": ["0.6b-base"]},
                   "engine": {"device": "Vulkan0", "fallbackDevice": "cpu"}}
        with tempfile.TemporaryDirectory() as tmp:
            rows = bench.run(Eng(), machine, tmp)
        self.assertEqual(len(rows), 8)
        self.assertIn("1536", rows[0]["error"])
        self.assertTrue(all(r["error"] is None for r in rows if r["device"] == "cpu"))

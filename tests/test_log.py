import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import engine, log
from gvoice.errors import GvoiceError

SPEC = {"seed": 5, "model": "0.6b-base", "device": "Vulkan0", "text": "Hello"}
MACHINE = {"name": "steam-deck"}


def line(duration, op=log.OP_LINE, model="0.6b-base", device="Vulkan0", provider="fake", **extra):
    d = {"gen_ai.provider.name": provider, "gen_ai.operation.name": op, "gen_ai.request.model": model,
         "app.voice.device": device, "app.duration_ms": duration}
    d.update(extra)
    return d


class LogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GVOICE_CONFIG_HOME": str(self.tmp / "c"),
                                           "GVOICE_DATA_HOME": str(self.tmp / "d")})
        env.start()
        self.addCleanup(env.stop)

    def put(self, *records):
        for r in records:
            log.append("proj", r)

    def test_record_carries_min_free_and_peak_rss_when_known(self):
        res = engine.EngineResult(duration_ms=1, engine_version="v", min_free_mb=3100, peak_rss_mb=2048)
        rec = log.record_for("voices/orc", "line", SPEC, MACHINE, "qwentts", result=res)
        self.assertEqual((rec["app.voice.min_free_mb"], rec["app.voice.peak_rss_mb"]), (3100, 2048))
        rec = log.record_for("voices/orc", "line", SPEC, MACHINE, "qwentts", result=engine.EngineResult(1, "v"))
        self.assertNotIn("app.voice.peak_rss_mb", rec)
        self.assertNotIn("app.voice.min_free_mb", rec)

    def test_record_success_has_the_d16_fields(self):
        res = engine.EngineResult(duration_ms=120, engine_version="fake-1", device="Vulkan0", seed=5,
                                  engine_commit="abc123", model="0.6b-base", audio_ms=300, load_ms=0, backend="fake")
        rec = log.record_for("voices/orc", "line", SPEC, MACHINE, "fake", result=res, ts="2026-01-01T00:00:00Z")
        self.assertEqual(rec, {
            "ts": "2026-01-01T00:00:00Z", "gen_ai.operation.name": "speech_generation",
            "gen_ai.provider.name": "fake", "gen_ai.request.model": "0.6b-base", "app.task": "line",
            "app.machine_profile": "steam-deck", "app.duration_ms": 120, "app.load_ms": 0,
            "app.voice.key": "voices/orc", "app.voice.seed": 5, "app.voice.device": "Vulkan0",
            "app.voice.engine_commit": "abc123", "app.voice.engine_version": "fake-1",
            "app.voice.text_chars": 5, "app.voice.audio_ms": 300, "app.voice.backend": "fake"})

    def test_result_wins_over_spec(self):
        res = engine.EngineResult(duration_ms=1, engine_version="v", device="cpu", seed=9, model="1.7b-base")
        rec = log.record_for("k", "t", SPEC, MACHINE, "fake", result=res)
        self.assertEqual((rec["app.voice.device"], rec["app.voice.seed"], rec["gen_ai.request.model"]),
                         ("cpu", 9, "1.7b-base"))

    def test_record_error_and_no_nulls(self):
        rec = log.record_for("k", "t", {"seed": 0}, MACHINE, "fake", error="boom", operation=log.OP_DESIGN)
        self.assertEqual(rec["app.error"], "boom")
        self.assertEqual(rec["gen_ai.operation.name"], "voice_design")
        self.assertNotIn("app.duration_ms", rec)
        self.assertEqual(rec["app.voice.seed"], 0)  # zero is kept
        self.assertNotIn(None, rec.values())
        self.assertRegex(rec["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_operations(self):
        self.assertEqual((log.OP_DESIGN, log.OP_LINE, log.OP_PRINT),
                         ("voice_design", "speech_generation", "voice_print"))
        self.assertEqual(log.record_for("k", "t", SPEC, MACHINE, "fake")["gen_ai.operation.name"],
                         "speech_generation")

    def test_append_writes_jsonl(self):
        self.put({"a": 1}, {"b": "é"})
        path = self.tmp / "d" / "projects" / "proj" / "log.jsonl"
        self.assertEqual([json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()],
                         [{"a": 1}, {"b": "é"}])

    def test_bad_project(self):
        for bad in ("../x", "a/b", "", "/etc"):
            with self.assertRaises(GvoiceError) as cm:
                log.append(bad, {})
            self.assertIn(cm.exception.code, ("log.bad_project", "path.dotdot"))

    def test_bad_project_names(self):
        for bad in (".", "..", "A", "-x", "a\n", "a b"):
            with self.assertRaises(GvoiceError) as cm:
                log.log_path(bad)
            self.assertEqual(cm.exception.code, "log.bad_project", bad)
            self.assertEqual(cm.exception.params, {"project": bad})
            self.assertIn(bad, cm.exception.message("en"))

    def test_estimate_none(self):
        self.assertIsNone(log.estimate("proj", "fake", log.OP_LINE, "0.6b-base", "Vulkan0"))

    def test_estimate_median_odd_even(self):
        self.put(line(100), line(300), line(200))
        self.assertEqual(log.estimate("proj", "fake", log.OP_LINE, "0.6b-base", "Vulkan0"), 200)
        self.put(line(1000))
        self.assertEqual(log.estimate("proj", "fake", log.OP_LINE, "0.6b-base", "Vulkan0"), 250)

    def test_estimate_filters(self):
        self.put(line(100), line(900, op=log.OP_DESIGN), line(900, model="1.7b-base"), line(900, device="cpu"),
                 line(900, provider="qwen"), line(900, **{"app.error": "x"}), line(True))
        self.assertEqual(log.estimate("proj", "fake", log.OP_LINE, "0.6b-base", "Vulkan0"), 100)
        self.assertEqual(log.estimate("proj", "fake", log.OP_DESIGN, "0.6b-base", "Vulkan0"), 900)
        self.assertEqual(log.estimate("proj", "fake", log.OP_LINE, "1.7b-base", "Vulkan0"), 900)
        self.assertEqual(log.estimate("proj", "fake", log.OP_LINE, "0.6b-base", "cpu"), 900)
        self.assertIsNone(log.estimate("proj", "fake", log.OP_PRINT, "0.6b-base", "Vulkan0"))

    def test_estimate_skips_malformed(self):
        self.put(line(100))
        path = self.tmp / "d" / "projects" / "proj" / "log.jsonl"
        with open(path, "a") as fh:
            fh.write("{not json\n[1]\n\n" + json.dumps(line("x")) + "\n")
        self.put(line(300))
        self.assertEqual(log.estimate("proj", "fake", log.OP_LINE, "0.6b-base", "Vulkan0"), 200)


if __name__ == "__main__":
    unittest.main()

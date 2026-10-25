# Copiado de gimg@0d02f51 (D7); cambia: speech_generation, app.audio.*, estimado por motor/tarea/modelo/dispositivo.
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import engine, log
from gvoice.errors import GvoiceError

MACHINE = {"name": "steam-deck"}


def line(duration, task="speak", model="0.6b-base", device="Vulkan0", provider="fake", **extra):
    d = {"gen_ai.provider.name": provider, "app.task": task, "gen_ai.request.model": model,
         "app.audio.device": device, "app.duration_ms": duration}
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

    def estimate(self, **kw):
        args = dict(provider="fake", task="speak", model="0.6b-base", device="Vulkan0")
        args.update(kw)
        return log.estimate("proj", **args)

    def test_record_success(self):
        res = engine.EngineResult(duration_ms=500, engine_version="fake-1", device="Vulkan0", load_ms=3,
                                  audio_ms=250)
        rec = log.record_for("speak", "npc/hello", MACHINE, "fake", "0.6b-base", seed=5, text_chars=12,
                             device="cpu", result=res, ts="2026-01-01T00:00:00Z")
        self.assertEqual(rec, {
            "ts": "2026-01-01T00:00:00Z", "gen_ai.operation.name": "speech_generation",
            "gen_ai.provider.name": "fake", "gen_ai.request.model": "0.6b-base", "app.task": "speak",
            "app.machine_profile": "steam-deck", "app.duration_ms": 500, "app.load_ms": 3,
            "app.audio.key": "npc/hello", "app.audio.seed": 5, "app.audio.device": "Vulkan0",
            "app.audio.text_chars": 12, "app.audio.audio_ms": 250, "app.audio.engine_version": "fake-1",
            "app.audio.rtf": 2.0})

    def test_record_print_has_no_audio_fields(self):
        res = engine.EngineResult(duration_ms=40, engine_version="fake-1", device="cpu", load_ms=0)
        rec = log.record_for("print", "voz", MACHINE, "fake", "1.7b-base", result=res)
        self.assertEqual(rec["app.task"], "print")
        for k in ("app.audio.audio_ms", "app.audio.rtf", "app.audio.seed", "app.audio.text_chars"):
            self.assertNotIn(k, rec)
        self.assertNotIn(None, rec.values())

    def test_rtf_is_rounded_and_needs_audio(self):
        res = engine.EngineResult(duration_ms=100, engine_version="v", device="cpu", audio_ms=300)
        self.assertEqual(log.record_for("design", "k", MACHINE, "fake", "m", result=res)["app.audio.rtf"], 0.333)
        res = engine.EngineResult(duration_ms=100, engine_version="v", device="cpu", audio_ms=0)
        self.assertNotIn("app.audio.rtf", log.record_for("design", "k", MACHINE, "fake", "m", result=res))

    def test_record_error_and_no_nulls(self):
        rec = log.record_for("design", "k", MACHINE, "fake", "m", seed=0, device="cpu", error="boom")
        self.assertEqual(rec["app.error"], "boom")
        self.assertEqual(rec["app.audio.device"], "cpu")
        self.assertNotIn("app.duration_ms", rec)
        self.assertEqual(rec["app.audio.seed"], 0)  # zero is kept
        self.assertNotIn(None, rec.values())
        self.assertRegex(rec["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_append_writes_jsonl(self):
        self.put({"a": 1}, {"b": "é"})
        path = self.tmp / "d" / "projects" / "proj" / "log.jsonl"
        self.assertEqual([json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()],
                         [{"a": 1}, {"b": "é"}])

    def test_bad_project(self):
        for bad in ("../x", "a/b", "", "/etc", ".", "..", "A", "-x", "a\n", "a b"):
            with self.assertRaises(GvoiceError) as cm:
                log.log_path(bad)
            self.assertIn(cm.exception.code, ("log.bad_project", "path.dotdot", "path.absolute"), bad)
            self.assertNotIn("error.", cm.exception.message("es"))

    def test_estimate_none(self):
        self.assertIsNone(self.estimate())

    def test_estimate_median_odd_even(self):
        self.put(line(100), line(300), line(200))
        self.assertEqual(self.estimate(), 200)
        self.put(line(1000))
        self.assertEqual(self.estimate(), 250)

    def test_estimate_filters(self):
        self.put(line(100), line(900, task="design"), line(900, model="1.7b-base"), line(900, provider="qwen"),
                 line(900, device="cpu"), line(900, **{"app.error": "x"}))
        self.assertEqual(self.estimate(), 100)
        self.assertEqual(self.estimate(task="design"), 900)
        self.assertEqual(self.estimate(model="1.7b-base"), 900)
        self.assertEqual(self.estimate(provider="qwen"), 900)
        self.assertEqual(self.estimate(device="cpu"), 900)
        self.assertIsNone(self.estimate(task="print"))

    def test_estimate_skips_malformed(self):
        self.put(line(100))
        path = self.tmp / "d" / "projects" / "proj" / "log.jsonl"
        with open(path, "a") as fh:
            fh.write("{not json\n[1]\n\n" + json.dumps(line("x")) + "\n" + json.dumps(line(True)) + "\n")
        self.put(line(300))
        self.assertEqual(self.estimate(), 200)

    def test_estimate_from_records(self):
        res = engine.EngineResult(duration_ms=700, engine_version="v", device="Vulkan0", audio_ms=300)
        self.put(log.record_for("speak", "k", MACHINE, "fake", "0.6b-base", result=res))
        self.assertEqual(self.estimate(), 700)


if __name__ == "__main__":
    unittest.main()

import array
import io
import json
import math
import time
import unittest
import wave

from gvoice import checks, engine, orders, queue, replay, schema as S, worker
from gvoice.errors import GvoiceError
from tests.test_cli import CONFIG, PROJECT, VOICE as CLI_VOICE, CliBase
from tests.test_orders import make_wav
from tests.test_worker import WorkerBase

RATE = 16000


def wav(*segments, rate=RATE, channels=1, width=2):
    """A WAV in memory from ``("tone", ms, amplitude)``, ``("sil", ms)`` and ``("flat", ms, value)`` segments."""
    samples = array.array("h")
    for seg in segments:
        frames = rate * seg[1] // 1000
        if seg[0] == "tone":
            samples.extend(int(seg[2] * math.sin(2 * math.pi * 220 * i / rate)) for i in range(frames))
        elif seg[0] == "flat":
            samples.extend([seg[2]] * frames)
        else:
            samples.extend([0] * frames)
    if channels == 2:
        stereo = array.array("h")
        for v in samples:
            stereo.extend((v, v))
        samples = stereo
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    buf.seek(0)
    return buf


TEN_CHARS = "0123456789"


class MetricsTests(unittest.TestCase):
    def test_silences_levels_and_length(self):
        m = checks.analyze(wav(("sil", 500), ("tone", 1000, 10000), ("sil", 2000), ("tone", 1000, 10000),
                               ("sil", 1000)), "Hola   mundo ")
        self.assertEqual((m["audioMs"], m["chars"]), (5500, 10))  # "Hola mundo"
        self.assertEqual(m["msPerChar"], 550.0)
        self.assertEqual((m["leadingSilenceMs"], m["longestInnerSilenceMs"], m["trailingSilenceMs"]), (500, 2000, 1000))
        self.assertAlmostEqual(m["peakDbfs"], -10.3, delta=0.2)  # 10000 / 32768
        self.assertAlmostEqual(m["rmsDbfs"], -13.3, delta=0.3)  # of the voiced windows only: peak - 3 dB
        self.assertEqual(m["clippedRatio"], 0.0)

    def test_clipping_counts_full_scale_samples(self):
        m = checks.analyze(wav(("flat", 1000, 32767)), TEN_CHARS)
        self.assertEqual(m["clippedRatio"], 1.0)
        m = checks.analyze(wav(("flat", 500, -32768), ("flat", 500, 100)), TEN_CHARS)
        self.assertEqual(m["clippedRatio"], 0.5)

    def test_stereo_and_all_silence(self):
        m = checks.analyze(wav(("tone", 1000, 8000), ("sil", 500), channels=2), TEN_CHARS)
        self.assertEqual((m["audioMs"], m["trailingSilenceMs"]), (1500, 500))
        m = checks.analyze(wav(("sil", 1000)), TEN_CHARS)
        self.assertEqual((m["leadingSilenceMs"], m["trailingSilenceMs"], m["rmsDbfs"], m["peakDbfs"]),
                         (1000, 0, checks.FLOOR_DBFS, checks.FLOOR_DBFS))

    def test_empty_text_has_no_speed(self):
        m = checks.analyze(wav(("tone", 1000, 8000)), "  ")
        self.assertEqual((m["chars"], m["msPerChar"]), (0, None))
        self.assertEqual(checks.warnings(m), [])

    def test_unreadable_and_unsupported_audio(self):
        with self.assertRaises(checks.ChecksError) as ctx:
            checks.analyze(io.BytesIO(b"not a wav"), "x")
        self.assertEqual(ctx.exception.code, checks.UNREADABLE)
        with self.assertRaises(checks.ChecksError) as ctx:
            checks.analyze(wav(("sil", 100), width=1), "x")
        self.assertEqual(ctx.exception.code, checks.UNSUPPORTED)
        self.assertEqual(checks.checks_of(io.BytesIO(b"junk"), "x"), {"error": checks.UNREADABLE})

    def test_fast_on_minutes(self):
        data = wav(("tone", 120000, 9000), ("sil", 2000), rate=24000)
        start = time.monotonic()
        m = checks.analyze(data, "x" * 2000)
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(m["audioMs"], 122000)


class WarningTests(unittest.TestCase):
    def codes(self, metrics_wav, text, limits=None):
        m = checks.analyze(metrics_wav, text, limits)
        return [w["code"] for w in checks.warnings(m, limits)]

    def test_each_warning(self):
        text = "x" * 35  # 35 characters: 60 ms per character is 2100 ms of audio
        self.assertEqual(self.codes(wav(("tone", 100, 9000)), TEN_CHARS), ["take.too_fast"])  # 10 ms/char
        self.assertEqual(self.codes(wav(("tone", 3000, 9000)), TEN_CHARS), ["take.too_slow"])  # 300 ms/char
        self.assertEqual(self.codes(wav(("tone", 300, 9000), ("sil", 1500), ("tone", 300, 9000)), text),
                         ["take.long_silence"])
        self.assertEqual(self.codes(wav(("tone", 100, 9000), ("sil", 2000)), text), ["take.trailing_silence"])
        self.assertEqual(self.codes(wav(("flat", 2100, 32767)), text), ["take.clipping"])
        self.assertEqual(self.codes(wav(("tone", 2100, 200)), text), ["take.too_quiet"])  # about -47 dBFS RMS

    def test_clean_take_and_params(self):
        self.assertEqual(self.codes(wav(("tone", 600, 9000)), "x" * 10), [])
        found = checks.warnings(checks.analyze(wav(("tone", 3000, 9000)), TEN_CHARS))
        self.assertEqual(found, [{"code": "take.too_slow", "params": {"value": 300.0, "limit": 180}}])

    def test_thresholds_change_the_result(self):
        audio = ("tone", 300, 9000), ("sil", 1500), ("tone", 300, 9000)
        self.assertEqual(self.codes(wav(*audio), "x" * 35), ["take.long_silence"])
        self.assertEqual(self.codes(wav(*audio), "x" * 35, {"innerSilenceMaxMs": 3000}), [])
        self.assertEqual(self.codes(wav(("tone", 600, 9000)), TEN_CHARS, {"msPerCharMin": 100}), ["take.too_fast"])
        # a higher silence level turns a quiet tone into silence
        self.assertEqual(checks.analyze(wav(("tone", 600, 200)), TEN_CHARS, {"silenceDbfs": -40})["leadingSilenceMs"],
                         600)

    def test_every_code_has_texts(self):
        from gvoice import i18n
        for code in ("too_fast", "too_slow", "long_silence", "trailing_silence", "clipping", "too_quiet"):
            for lang in ("es", "en"):
                text = i18n.t("warning.take." + code, lang, value=1, limit=2)
                self.assertNotIn("warning.take", text)


class SchemaTests(unittest.TestCase):
    def errors(self, checks_value):
        config = json.loads(CONFIG)
        config["checks"] = checks_value
        return [(e.path, e.code) for e in S.validate(config, S.load_schema("project-config"))]

    def test_checks_in_the_project_config(self):
        self.assertEqual(self.errors({"silenceDbfs": -45, "msPerCharMax": 200, "clippedRatioMax": 0.01}), [])
        self.assertEqual(self.errors({"clippedRatioMax": 2}), [("/checks/clippedRatioMax", "maximum")])
        self.assertEqual(self.errors({"nope": 1}), [("/checks/nope", "additionalProperties")])
        self.assertEqual(set(S.load_schema("project-config")["properties"]["checks"]["properties"]),
                         set(checks.DEFAULTS))


class JunkEngine(engine.FakeEngine):
    """Writes something that is not a WAV."""

    def design(self, job, should_cancel):
        result = super().design(job, should_cancel)
        with open(job.output, "wb") as fh:
            fh.write(b"junk")
        return result


class TakeChecksTests(WorkerBase):
    def make_voice(self, **kw):
        orders.submit(self.p, self.voice())
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator", seed=7))
        self.run_worker(**kw)
        return self.attempt("narrator", 1)

    def test_take_records_checks_and_sha256(self):
        take = self.make_voice()
        audio = orders.attempt_audio(self.p, "narrator", take)
        self.assertEqual(take["sha256"], checks.sha256_of(audio))
        c = take["checks"]
        self.assertEqual(c["warnings"], [])
        self.assertEqual(c["audioMs"], take["audioMs"])
        self.assertAlmostEqual(c["msPerChar"], 60, delta=1)

    def test_project_thresholds_reach_the_warnings(self):
        self.write_config(checks={"msPerCharMin": 100})
        c = self.make_voice()["checks"]
        self.assertEqual([w["code"] for w in c["warnings"]], ["take.too_fast"])
        self.assertEqual(c["warnings"][0]["params"]["limit"], 100)

    def test_a_bad_wav_is_recorded_with_its_error(self):
        orders.submit(self.p, self.voice())
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator", seed=7))
        self.assertEqual(self.run_worker(engine=JunkEngine()), 1)
        take = self.attempt("narrator", 1)
        self.assertEqual(take["checks"], {"error": checks.UNREADABLE})
        self.assertEqual(len(take["sha256"]), 64)
        self.assertEqual(queue.list_entries()[0]["state"], "done")

    def test_an_analysis_that_blows_up_does_not_break_the_worker(self):
        from unittest import mock
        with mock.patch.object(checks, "for_take", side_effect=RuntimeError("boom")):
            take = self.make_voice()
        self.assertEqual(take["checks"], {"error": "take.analysis_failed"})

    def test_sample_take_has_checks_and_sha256(self):
        orders.submit(self.p, {"type": "voice", "key": "s", "locale": "es-ES", "sample": {
            "audio": make_wav(self.tmp / "s.wav", ms=1000, value=0), "text": "Amanece.", "source": "own",
            "license": "CC0-1.0"}})
        take = self.attempt("s", 1)
        self.assertEqual(len(take["sha256"]), 64)
        self.assertEqual(take["checks"]["leadingSilenceMs"], 1000)
        self.assertIn("take.too_quiet", [w["code"] for w in take["checks"]["warnings"]])


class ReplayTests(CliBase):
    def setUp(self):
        super().setUp()
        self.add_project()
        self.ok("order", "submit", PROJECT, self.write_order("v.json", CLI_VOICE))
        self.ok("work")
        self.path = next((self.tmp / "data").glob("projects/*/orders/narrator/@/order.json"))

    def edit(self, change):
        data = json.loads(self.path.read_text())
        change(data["attempts"][0])
        self.path.write_text(json.dumps(data))

    def leftovers(self):
        return list(self.path.parent.rglob(".replay-*"))

    def test_same_audio_exits_0_and_stores_the_replay(self):
        code, out, err = self.run_cli("take", "replay", PROJECT, "narrator", "1")
        self.assertEqual((code, err), (0, ""))
        take = orders.get(PROJECT, "narrator")["attempts"][0]
        self.assertIn("identical (%s)" % take["sha256"], out)
        self.assertTrue(take["replay"]["same"])
        self.assertEqual((take["replay"]["sha256"], take["replay"]["device"]), (take["sha256"], take["device"]))
        self.assertEqual(self.leftovers(), [])
        self.assertIn("replay (", self.ok("order", "show", PROJECT, "narrator"))

    def test_different_audio_exits_1(self):
        self.edit(lambda a: a.update(sha256="0" * 64))
        code, out, err = self.run_cli("--json", "take", "replay", PROJECT, "narrator", "1")
        self.assertEqual((code, err), (1, ""))
        found = json.loads(out)
        self.assertEqual((found["same"], found["expected"]), (False, "0" * 64))
        self.assertFalse(orders.get(PROJECT, "narrator")["attempts"][0]["replay"]["same"])
        code, out, _ = self.run_cli("take", "replay", PROJECT, "narrator", "1")
        self.assertEqual(code, 1)
        self.assertIn("DIFFERENT", out)
        self.assertIn("0" * 64, out)

    def test_a_take_without_sha256_is_compared_with_its_stored_audio(self):
        self.edit(lambda a: a.pop("sha256"))
        self.assertEqual(self.run_cli("take", "replay", PROJECT, "narrator", "1")[0], 0)
        self.edit(lambda a: a.pop("sha256", None))
        audio = next(self.path.parent.rglob("audio.wav"))
        audio.write_bytes(audio.read_bytes() + b"\0\0")
        self.assertEqual(self.run_cli("take", "replay", PROJECT, "narrator", "1")[0], 1)

    def test_replay_uses_the_stored_parameters(self):
        self.edit(lambda a: a["sampling"].update(temperature=0.123))
        self.assertEqual(self.run_cli("take", "replay", PROJECT, "narrator", "1")[0], 1)  # other sampling, other audio

    def test_a_sample_cannot_be_replayed(self):
        self.ok("order", "submit", PROJECT, self.write_order("s.json", {"type": "voice", "key": "s", "locale": "es-ES",
                "sample": {"audio": make_wav(self.tmp / "s.wav"), "text": "Hola.", "source": "own",
                           "license": "CC0-1.0"}}))
        with self.assertRaises(GvoiceError) as ctx:
            replay.replay(PROJECT, "s", 1)
        self.assertEqual(ctx.exception.code, "take.replay_sample")
        code, out, err = self.run_cli("take", "replay", PROJECT, "s", "1")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("human sample", err)
        code, _, err = self.run_cli("--lang", "es", "take", "replay", PROJECT, "s", "1")
        self.assertIn("muestra humana", err)

    def test_an_engine_failure_exits_2_and_cleans_up(self):
        import os
        os.environ["GVOICE_FAKE_FAIL"] = "boom"
        code, _, err = self.run_cli("take", "replay", PROJECT, "narrator", "1")
        self.assertEqual(code, 2)
        self.assertEqual(self.leftovers(), [])
        self.assertNotIn("replay", orders.get(PROJECT, "narrator")["attempts"][0])

    def test_unknown_take(self):
        self.assertEqual(self.run_cli("take", "replay", PROJECT, "narrator", "9")[0], 2)

    def test_order_show_prints_warnings_translated(self):
        config = json.loads(CONFIG)
        config["checks"] = {"msPerCharMin": 100}
        (self.root / "galivelop-voices.json").write_text(json.dumps(config))
        self.ok("order", "submit", PROJECT, self.write_order("v2.json", CLI_VOICE, key="other"))
        self.ok("work")
        self.assertIn("warning: The take is very fast (", self.ok("order", "show", PROJECT, "other"))
        self.assertIn("aviso: La toma es muy rápida", self.ok("--lang", "es", "order", "show", PROJECT, "other"))
        a = self.js("order", "show", PROJECT, "other")["attempts"][0]
        self.assertEqual(a["checks"]["warnings"][0]["code"], "take.too_fast")


class ReplayLineTests(WorkerBase):
    def test_a_line_take_replays_the_same(self):
        self.voice_done()
        orders.submit(self.p, self.line())
        queue.enqueue(self.p, "narrator/intro-01", orders.attempt_specs(self.p, "narrator/intro-01", seed=3))
        self.run_worker()
        found = replay.replay(self.p, "narrator/intro-01", 1, engine=engine.FakeEngine())
        self.assertTrue(found["same"])
        self.assertEqual(found["sha256"], self.attempt("narrator/intro-01", 1)["sha256"])


if __name__ == "__main__":
    unittest.main()

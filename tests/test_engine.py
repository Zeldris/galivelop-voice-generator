import os
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from gvoice import engine
from gvoice.errors import GvoiceError

NEVER = lambda: False


def wav_info(path):
    with wave.open(str(path), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()


class FakeEngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.fake = engine.FakeEngine()

    def design(self, name="a.wav", seed=7, text="Hello there, traveller.", instruction="Gender: male.", **kw):
        job = engine.DesignJob(instruction=instruction, text=text, seed=seed, output=str(self.tmp / "sub" / name), **kw)
        return job, self.fake.design(job, NEVER)

    def make_print(self, model="0.6b-base", seed=1, text="Reference text"):
        ref, _ = self.design("ref.wav", seed=seed, text=text)
        job = engine.PrintJob(reference=ref.output, text=text, model=model,
                              spk=str(self.tmp / "p" / (model + ".spk")), rvq=str(self.tmp / "p" / (model + ".rvq")))
        return job, self.fake.voiceprint(job, NEVER)

    def line(self, pj, name="l.wav", seed=3, text="A line.", **kw):
        job = engine.LineJob(spk=pj.spk, rvq=pj.rvq, text=text, seed=seed, output=str(self.tmp / name), **kw)
        return job, self.fake.line(job, NEVER)

    def test_design_writes_pcm16_mono_24k_wav_and_no_temp_left(self):
        job, res = self.design()
        ch, width, rate, frames = wav_info(job.output)
        self.assertEqual((ch, width, rate), (1, 2, 24000))
        self.assertEqual(frames, 24000 * res.audio_ms // 1000)
        self.assertEqual(os.listdir(self.tmp / "sub"), ["a.wav"])

    def test_same_seed_and_text_same_bytes_other_seed_other_audio(self):
        a, _ = self.design("a.wav", seed=1)
        b, _ = self.design("b.wav", seed=1)
        c, _ = self.design("c.wav", seed=2)
        d, _ = self.design("d.wav", seed=1, text="Another text.")
        read = lambda j: Path(j.output).read_bytes()
        self.assertEqual(read(a), read(b))
        self.assertNotEqual(read(a), read(c))
        self.assertNotEqual(read(a), read(d))

    def test_duration_proportional_to_text(self):
        short, _ = self.design("s.wav", text="x" * 10)
        long, _ = self.design("l.wav", text="x" * 100)
        self.assertEqual(wav_info(long.output)[3], 10 * wav_info(short.output)[3])
        empty, _ = self.design("e.wav", text="")
        self.assertGreater(wav_info(empty.output)[3], 0)

    def test_result_carries_d16_fields(self):
        _, res = self.design(model="1.7b-voicedesign", device="Vulkan0")
        self.assertEqual((res.device, res.seed, res.model, res.engine_commit, res.engine_version),
                         ("Vulkan0", 7, "1.7b-voicedesign", engine.FAKE_COMMIT, engine.FAKE_VERSION))
        self.assertIsInstance(res.duration_ms, int)

    def test_device_defaults_from_machine_profile_then_cpu(self):
        _, res = self.design(machine={"engine": {"device": "Vulkan0"}})
        self.assertEqual(res.device, "Vulkan0")
        _, res = self.design()
        self.assertEqual(res.device, "cpu")

    def test_other_device_other_take_like_the_real_engine(self):
        a, _ = self.design("a.wav", device="cpu")
        b, _ = self.design("b.wav", device="Vulkan0")
        self.assertNotEqual(Path(a.output).read_bytes(), Path(b.output).read_bytes())

    def test_voiceprint_files_depend_on_audio_and_model(self):
        pj, res = self.make_print()
        spk, rvq = Path(pj.spk).read_bytes(), Path(pj.rvq).read_bytes()
        self.assertTrue(spk.startswith(b"FAKE-SPK\n"))
        self.assertTrue(rvq.startswith(b"FAKE-RVQ\n"))
        self.assertEqual(res.model, "0.6b-base")
        again, _ = self.make_print()
        self.assertEqual(Path(again.spk).read_bytes(), spk)
        other_model, _ = self.make_print(model="1.7b-base")
        self.assertNotEqual(Path(other_model.spk).read_bytes(), spk)
        self.assertNotEqual(Path(other_model.rvq).read_bytes(), rvq)
        other_audio, _ = self.make_print(seed=2)
        self.assertNotEqual(Path(other_audio.spk).read_bytes(), spk)

    def test_line_is_deterministic_and_depends_on_print_seed_and_text(self):
        pj, _ = self.make_print()
        a, res = self.line(pj, "a.wav")
        b, _ = self.line(pj, "b.wav")
        self.assertEqual(Path(a.output).read_bytes(), Path(b.output).read_bytes())
        self.assertEqual(wav_info(a.output)[:3], (1, 2, 24000))
        self.assertEqual((res.seed, res.engine_commit), (3, engine.FAKE_COMMIT))
        self.assertNotEqual(Path(self.line(pj, "c.wav", seed=4)[0].output).read_bytes(), Path(a.output).read_bytes())
        self.assertNotEqual(Path(self.line(pj, "d.wav", text="Other.")[0].output).read_bytes(),
                            Path(a.output).read_bytes())
        other, _ = self.make_print(seed=9)
        self.assertNotEqual(Path(self.line(other, "e.wav")[0].output).read_bytes(), Path(a.output).read_bytes())

    def test_line_without_print_says_which_one(self):
        job = engine.LineJob(spk=str(self.tmp / "no.spk"), rvq=str(self.tmp / "no.rvq"), text="t", seed=1,
                             output=str(self.tmp / "o.wav"))
        with self.assertRaises(engine.EngineError) as cm:
            self.fake.line(job, NEVER)
        self.assertEqual(cm.exception.code, "engine.print_missing")
        self.assertEqual(cm.exception.params, {"path": str(self.tmp / "no.spk")})
        self.assertFalse((self.tmp / "o.wav").exists())

    def test_voiceprint_without_reference(self):
        job = engine.PrintJob(reference=str(self.tmp / "no.wav"), text="t", model="0.6b-base",
                              spk=str(self.tmp / "a.spk"), rvq=str(self.tmp / "a.rvq"))
        with self.assertRaises(engine.EngineError) as cm:
            self.fake.voiceprint(job, NEVER)
        self.assertEqual(cm.exception.code, "engine.reference_unreadable")
        self.assertFalse((self.tmp / "a.spk").exists())

    def test_cancel_during_delay(self):
        job = engine.DesignJob(instruction="i", text="t", seed=1, output=str(self.tmp / "a.wav"))
        flag = threading.Event()
        threading.Timer(0.1, flag.set).start()
        start = time.monotonic()
        with self.assertRaises(engine.Cancelled):
            engine.FakeEngine(delay_s=5).design(job, flag.is_set)
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(Path(job.output).exists())

    def test_delay_is_measured(self):
        job = engine.DesignJob(instruction="i", text="t", seed=1, output=str(self.tmp / "a.wav"))
        self.assertGreaterEqual(engine.FakeEngine(delay_s=0.1).design(job, NEVER).duration_ms, 90)

    def test_fail_with_in_the_three_operations(self):
        pj, _ = self.make_print()
        bad = engine.FakeEngine(fail_with="boom")
        jobs = [(bad.design, engine.DesignJob(instruction="i", text="t", seed=1, output=str(self.tmp / "f.wav"))),
                (bad.line, engine.LineJob(spk=pj.spk, rvq=pj.rvq, text="t", seed=1, output=str(self.tmp / "g.wav"))),
                (bad.voiceprint, engine.PrintJob(reference=str(self.tmp / "sub" / "ref.wav"), text="t",
                                                 model="0.6b-base", spk=str(self.tmp / "h.spk"),
                                                 rvq=str(self.tmp / "h.rvq")))]
        for op, job in jobs:
            with self.assertRaises(engine.EngineError) as cm:
                op(job, NEVER)
            self.assertEqual(cm.exception.message, "boom")
        self.assertEqual(sorted(p.name for p in self.tmp.glob("[fgh].*")), [])

    def test_timeout(self):
        job = engine.DesignJob(instruction="i", text="t", seed=1, output=str(self.tmp / "a.wav"), timeout_s=0.1)
        t0 = time.monotonic()
        with self.assertRaises(engine.EngineError) as cm:
            engine.FakeEngine(delay_s=5).design(job, NEVER)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertEqual(cm.exception.message, engine.TIMEOUT_MESSAGE)
        self.assertIsInstance(cm.exception, engine.EngineTimeout)
        self.assertFalse(Path(job.output).exists())

    def test_no_timeout_when_fast(self):
        job = engine.DesignJob(instruction="i", text="t", seed=1, output=str(self.tmp / "a.wav"), timeout_s=5)
        engine.FakeEngine(delay_s=0.05).design(job, NEVER)
        self.assertTrue(Path(job.output).exists())

    def test_mode_honours_umask(self):
        old = os.umask(0o022)
        try:
            job, _ = self.design()
        finally:
            os.umask(old)
        self.assertEqual(os.stat(job.output).st_mode & 0o777, 0o644)

    def test_base_engine_operations_are_not_implemented(self):
        for op in ("design", "line", "voiceprint"):
            with self.assertRaises(NotImplementedError):
                getattr(engine.Engine(), op)(None, NEVER)


class GetEngineTests(unittest.TestCase):
    def env(self, **kw):
        patch = mock.patch.dict(os.environ, kw)
        patch.start()
        self.addCleanup(patch.stop)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.env(GVOICE_CONFIG_HOME=str(self.tmp))
        for k in ("GVOICE_ENGINE", "GVOICE_FAKE_DELAY", "GVOICE_FAKE_FAIL"):
            self.env(**{k: ""})

    def code(self):
        with self.assertRaises(GvoiceError) as cm:
            engine.get_engine()
        return cm.exception

    def test_default_fake(self):
        e = engine.get_engine()
        self.assertIsInstance(e, engine.FakeEngine)
        self.assertEqual(e.provider, "fake")

    def test_unknown_names_the_engine(self):
        self.env(GVOICE_ENGINE="qwen")
        exc = self.code()
        self.assertEqual((exc.code, exc.params), ("engine.unknown", {"engine": "qwen"}))
        self.assertIn("qwen", exc.message("en"))

    def test_config_file_engine(self):
        (self.tmp / "config.json").write_text('{"engine": "other"}')
        self.assertEqual(self.code().code, "engine.unknown")

    def test_corrupt_config(self):
        (self.tmp / "config.json").write_text("{nope")
        self.assertEqual(self.code().code, "machine.config_unreadable")

    def test_knobs(self):
        self.env(GVOICE_FAKE_DELAY="0.5", GVOICE_FAKE_FAIL="x")
        e = engine.get_engine()
        self.assertEqual((e.delay_s, e.fail_with), (0.5, "x"))

    def test_bad_delay_values(self):
        for bad in ("nan", "inf", "-1", "-inf", "abc"):
            self.env(GVOICE_FAKE_DELAY=bad)
            exc = self.code()
            self.assertEqual((exc.code, exc.params), ("engine.bad_delay", {"value": bad}), bad)

    def test_messages_translated(self):
        for lang in ("es", "en"):
            for code, params in (("engine.unknown", {"engine": "x"}), ("engine.bad_delay", {"value": "x"}),
                                 ("engine.print_missing", {"path": "p"}),
                                 ("engine.reference_unreadable", {"path": "p"})):
                self.assertNotIn("error.", GvoiceError(code, **params).message(lang))


if __name__ == "__main__":
    unittest.main()

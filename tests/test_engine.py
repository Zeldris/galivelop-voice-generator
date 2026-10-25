# Copiado de gimg@0d02f51 (D7); cambia: WAV y huellas de prueba en vez de PNG, tres operaciones, GVOICE_*.
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


def never():
    return False


class FakeEngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def design(self, name="a.wav", seed=7, text="hola mundo", device="cpu", **kw):
        return engine.DesignJob(instruct="calm", text=text, seed=seed, model="1.7b-voicedesign",
                                output=str(self.tmp / "sub" / name), device=device, **kw)

    def reference(self, content=b"ref", name="ref.wav"):
        path = self.tmp / name
        path.write_bytes(content)
        return path

    def print_job(self, model="0.6b-base", ref=None, name="p"):
        return engine.PrintJob(reference=str(ref or self.reference()), reference_text="hi", model=model,
                               spk=str(self.tmp / "prints" / (name + ".spk")),
                               rvq=str(self.tmp / "prints" / (name + ".rvq")))

    def read_wav(self, path):
        with wave.open(str(path), "rb") as w:
            frames = w.readframes(w.getnframes())
            return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes(), frames

    def zero_crossings(self, frames):
        import struct
        samples = struct.unpack("<%dh" % (len(frames) // 2), frames)
        return sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b)

    def test_wav_header_rate_and_duration(self):
        job = self.design(text="x" * 10)
        res = engine.FakeEngine().design(job, never)
        channels, width, rate, nframes, _ = self.read_wav(job.output)
        self.assertEqual((channels, width, rate), (1, 2, 24000))
        self.assertEqual(nframes, 24000 * 10 * engine.FAKE_MS_PER_CHAR // 1000)
        self.assertEqual(res.audio_ms, 10 * engine.FAKE_MS_PER_CHAR)
        self.assertEqual(res.engine_version, "fake-1")
        self.assertEqual(res.device, "cpu")
        self.assertIsInstance(res.duration_ms, int)
        self.assertEqual(os.listdir(self.tmp / "sub"), ["a.wav"])  # no temp left

    def test_duration_is_proportional_to_text(self):
        short, long_ = self.design("s.wav", text="x" * 5), self.design("l.wav", text="x" * 20)
        for j in (short, long_):
            engine.FakeEngine().design(j, never)
        self.assertEqual(self.read_wav(long_.output)[3], 4 * self.read_wav(short.output)[3])

    def test_empty_text_has_minimum_duration(self):
        job = self.design(text="")
        self.assertEqual(engine.FakeEngine().design(job, never).audio_ms, engine.FAKE_MS_PER_CHAR)

    def test_frequency_comes_from_seed(self):
        a, b = self.design("a.wav", seed=0, text="x" * 20), self.design("b.wav", seed=300, text="x" * 20)
        for j in (a, b):
            engine.FakeEngine().design(j, never)
        seconds = 20 * engine.FAKE_MS_PER_CHAR / 1000
        for job, seed in ((a, 0), (b, 300)):
            freq = self.zero_crossings(self.read_wav(job.output)[4]) / seconds
            self.assertAlmostEqual(freq, engine.fake_frequency(seed), delta=2)
        self.assertNotEqual(engine.fake_frequency(0), engine.fake_frequency(300))

    def test_same_seed_same_bytes_other_seed_other_bytes(self):
        a, b, c = self.design("a.wav", 1), self.design("b.wav", 1), self.design("c.wav", 2)
        for j in (a, b, c):
            engine.FakeEngine().design(j, never)
        read = lambda j: Path(j.output).read_bytes()
        self.assertEqual(read(a), read(b))
        self.assertNotEqual(read(a), read(c))

    def test_result_device_is_the_jobs(self):
        res = engine.FakeEngine().design(self.design(device="Vulkan0"), never)
        self.assertEqual(res.device, "Vulkan0")

    def test_bad_seed(self):
        for bad in (-1, True, "3", None):
            with self.assertRaises(engine.EngineError):
                engine.FakeEngine().design(self.design(seed=bad), never)

    def test_extract_print_is_deterministic(self):
        e = engine.FakeEngine()
        a, b = self.print_job(name="a"), self.print_job(name="b")
        res = e.extract_print(a, never)
        e.extract_print(b, never)
        self.assertIsNone(res.audio_ms)
        self.assertEqual(res.device, "cpu")
        for ext in ("spk", "rvq"):
            self.assertEqual(Path(getattr(a, ext)).read_bytes(), Path(getattr(b, ext)).read_bytes())
        self.assertNotEqual(Path(a.spk).read_bytes(), Path(a.rvq).read_bytes())
        self.assertEqual(sorted(os.listdir(self.tmp / "prints")), ["a.rvq", "a.spk", "b.rvq", "b.spk"])

    def test_print_depends_on_reference_content_and_model(self):
        e = engine.FakeEngine()
        base = self.print_job(name="base")
        other_ref = self.print_job(ref=self.reference(b"other", "other.wav"), name="oref")
        other_model = self.print_job(model="1.7b-base", name="omodel")
        for j in (base, other_ref, other_model):
            e.extract_print(j, never)
        for other in (other_ref, other_model):
            for ext in ("spk", "rvq"):
                self.assertNotEqual(Path(getattr(base, ext)).read_bytes(), Path(getattr(other, ext)).read_bytes())

    def test_print_missing_reference(self):
        job = self.print_job(ref=self.tmp / "nope.wav")
        with self.assertRaises(engine.EngineError):
            engine.FakeEngine().extract_print(job, never)
        self.assertFalse(Path(job.spk).exists())

    def test_speak_needs_the_print(self):
        e = engine.FakeEngine()
        pj = self.print_job()
        out = self.tmp / "line.wav"
        sj = engine.SpeakJob(text="hola", seed=3, model="0.6b-base", spk=pj.spk, rvq=pj.rvq, output=str(out))
        with self.assertRaises(engine.EngineError):
            e.speak(sj, never)
        self.assertFalse(out.exists())
        e.extract_print(pj, never)
        res = e.speak(sj, never)
        self.assertEqual(self.read_wav(out)[2], 24000)
        self.assertEqual(res.audio_ms, 4 * engine.FAKE_MS_PER_CHAR)

    def test_cancel_during_delay(self):
        job = self.design()
        flag = threading.Event()
        threading.Timer(0.1, flag.set).start()
        start = time.monotonic()
        with self.assertRaises(engine.Cancelled):
            engine.FakeEngine(delay_s=5).design(job, flag.is_set)
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(Path(job.output).exists())

    def test_delay_is_measured(self):
        res = engine.FakeEngine(delay_s=0.1).design(self.design(), never)
        self.assertGreaterEqual(res.duration_ms, 90)

    def test_fail_with(self):
        job = self.design()
        with self.assertRaises(engine.EngineError) as cm:
            engine.FakeEngine(fail_with="boom").design(job, never)
        self.assertEqual(cm.exception.message, "boom")
        self.assertFalse(Path(job.output).exists())
        pj = self.print_job()
        with self.assertRaises(engine.EngineError):
            engine.FakeEngine(fail_with="boom").extract_print(pj, never)
        self.assertFalse(Path(pj.spk).exists())

    def test_timeout(self):
        job = self.design(timeout_s=0.1)
        t0 = time.monotonic()
        with self.assertRaises(engine.EngineError) as cm:
            engine.FakeEngine(delay_s=5).design(job, never)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertEqual(cm.exception.message, engine.TIMEOUT_MESSAGE)
        self.assertIsInstance(cm.exception, engine.EngineTimeout)
        self.assertFalse(Path(job.output).exists())

    def test_timeout_in_every_operation(self):
        e = engine.FakeEngine(delay_s=5)
        pj = self.print_job()
        pj.timeout_s = 0.05
        with self.assertRaises(engine.EngineTimeout):
            e.extract_print(pj, never)
        sj = engine.SpeakJob(text="a", seed=1, model="0.6b-base", spk=pj.spk, rvq=pj.rvq,
                             output=str(self.tmp / "x.wav"), timeout_s=0.05)
        with self.assertRaises(engine.EngineTimeout):
            e.speak(sj, never)

    def test_no_timeout_when_fast(self):
        job = self.design(timeout_s=5)
        engine.FakeEngine(delay_s=0.05).design(job, never)
        self.assertTrue(Path(job.output).exists())

    def test_files_honour_umask(self):
        job = self.design()
        old = os.umask(0o022)
        try:
            engine.FakeEngine().design(job, never)
        finally:
            os.umask(old)
        self.assertEqual(os.stat(job.output).st_mode & 0o777, 0o644)


class GetEngineTests(unittest.TestCase):
    def env(self, **kw):
        patch = mock.patch.dict(os.environ, kw)
        patch.start()
        self.addCleanup(patch.stop)

    def setUp(self):
        for k in ("GVOICE_ENGINE", "GVOICE_FAKE_DELAY", "GVOICE_FAKE_FAIL"):
            self.env(**{k: ""})

    def test_default_fake(self):
        e = engine.get_engine()
        self.assertIsInstance(e, engine.FakeEngine)
        self.assertEqual(e.provider, "fake")

    def test_unknown(self):
        self.env(GVOICE_ENGINE="qwen-tts")
        with self.assertRaises(GvoiceError) as cm:
            engine.get_engine()
        self.assertEqual(cm.exception.code, "engine.unknown")
        self.assertIn("qwen-tts", cm.exception.message("en"))

    def test_knobs(self):
        self.env(GVOICE_FAKE_DELAY="0.5", GVOICE_FAKE_FAIL="x")
        e = engine.get_engine()
        self.assertEqual((e.delay_s, e.fail_with), (0.5, "x"))

    def test_bad_delay_values(self):
        for bad in ("nan", "inf", "-1", "-inf", "abc"):
            self.env(GVOICE_FAKE_DELAY=bad)
            with self.assertRaises(GvoiceError) as cm:
                engine.get_engine()
            self.assertEqual(cm.exception.code, "engine.bad_delay", bad)
            self.assertIn("GVOICE_FAKE_DELAY", cm.exception.message("es"))


if __name__ == "__main__":
    unittest.main()

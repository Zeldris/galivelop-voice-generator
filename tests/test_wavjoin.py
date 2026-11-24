import tempfile
import unittest
import wave
from pathlib import Path

from gvoice import wavjoin
from gvoice.errors import GvoiceError


def write_wav(path, ms, rate=24000, width=2, channels=1):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\x01" * (channels * width * (rate * ms // 1000)))


class SplitTests(unittest.TestCase):
    def test_sentences_and_line_breaks(self):
        self.assertEqual(wavjoin.split_sentences("Hola. ¿Qué tal? Bien...\nAdiós"),
                         ["Hola.", "¿Qué tal?", "Bien...", "Adiós"])

    def test_closing_quote_stays_with_its_sentence(self):
        self.assertEqual(wavjoin.split_sentences('Dijo «sí.» Y se fue.'), ["Dijo «sí.»", "Y se fue."])

    def test_no_sentence_end_is_one_piece(self):
        self.assertEqual(wavjoin.split_sentences("  sin punto final "), ["sin punto final"])
        self.assertEqual(wavjoin.split_sentences("3.5 metros"), ["3.5 metros"])
        self.assertEqual(wavjoin.split_sentences("  \n "), [])


class JoinTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def test_join_puts_the_silence_between_pieces(self):
        a, b, out = self.dir / "a.wav", self.dir / "b.wav", self.dir / "o.wav"
        write_wav(a, 1000)
        write_wav(b, 500)
        self.assertEqual(wavjoin.join([a, b], out), 1000 + wavjoin.GAP_MS + 500)
        with wave.open(str(out), "rb") as w:
            self.assertEqual(w.getnframes(), 24 * (1000 + wavjoin.GAP_MS + 500))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["a.wav", "b.wav", "o.wav"])

    def test_other_rate_is_refused_with_its_reason(self):
        a, b = self.dir / "a.wav", self.dir / "b.wav"
        write_wav(a, 200)
        write_wav(b, 200, rate=16000)
        with self.assertRaises(GvoiceError) as ctx:
            wavjoin.join([a, b], self.dir / "o.wav")
        self.assertEqual(ctx.exception.code, "engine.split_format")
        self.assertIn("differs", ctx.exception.params["reason"])
        self.assertFalse((self.dir / "o.wav").exists())

    def test_not_a_wav_is_refused(self):
        a = self.dir / "a.wav"
        a.write_bytes(b"nope")
        with self.assertRaises(GvoiceError) as ctx:
            wavjoin.join([a], self.dir / "o.wav")
        self.assertEqual(ctx.exception.code, "engine.split_format")


if __name__ == "__main__":
    unittest.main()

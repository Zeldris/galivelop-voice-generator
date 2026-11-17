"""gvoice/peaks.py: bucket rules, sample widths, channels and the failures."""
import random
import struct
import tempfile
import time
import unittest
import wave
from pathlib import Path

from gvoice import peaks as pk


def write_wav(path, frames_bytes, width=2, chans=1, rate=1000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(chans)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames_bytes)


def pcm16(values):
    return struct.pack(f"<{len(values)}h", *values)


def reference_peaks(data, width, chans, n):
    """The original frame-by-frame rules, as a slow oracle: max abs over the channels of the frames of each bucket."""
    total = len(data) // (width * chans)
    if width == 1:
        vals = [abs(b - 128) for b in data]
    else:
        vals = [abs(int.from_bytes(data[i:i + width], "little", signed=True)) for i in range(0, len(data), width)]
    scale = 2 ** (8 * width - 1)
    out = []
    for b in range(n):
        lo, hi = b * total // n, (b + 1) * total // n
        m = max(vals[lo * chans:hi * chans], default=0)
        out.append(min(1.0, ((2000 * m + scale) // (2 * scale)) / 1000))
    return out


class PeaksTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def wav(self, data, name="a.wav", **kw):
        p = self.dir / name
        write_wav(p, data, **kw)
        return p

    def test_constants(self):
        self.assertEqual((pk.DEFAULT_N, pk.MIN_N, pk.MAX_N), (400, 16, 2000))

    def test_mono16_known_values(self):
        vals = [0] * 32
        vals[0], vals[17], vals[31] = 16384, -32768, 8192
        r = pk.peaks(self.wav(pcm16(vals)), 16)  # 2 frames per bucket
        self.assertEqual(len(r["peaks"]), 16)
        self.assertEqual(r["peaks"][0], 0.5)
        self.assertEqual(r["peaks"][8], 1.0)
        self.assertEqual(r["peaks"][15], 0.25)
        self.assertEqual(sum(1 for x in r["peaks"] if x), 3)

    def test_default_n_and_audio_ms(self):
        r = pk.peaks(self.wav(pcm16([100] * 1500), rate=1000))
        self.assertEqual((len(r["peaks"]), r["audioMs"]), (400, 1500))
        self.assertEqual(pk.peaks(self.wav(pcm16([1] * 7), "b.wav", rate=3), 16)["audioMs"], 7 * 1000 // 3)

    def test_stereo_takes_max_across_channels(self):
        frames = [(100, -16384), (-32768, 0)] + [(0, 0)] * 30
        data = pcm16([v for f in frames for v in f])
        r = pk.peaks(self.wav(data, chans=2), 16)
        self.assertEqual(r["peaks"][0], 1.0)  # frames 0 and 1: max(|-16384|, |-32768|)
        self.assertEqual(r["audioMs"], 32)
        data = pcm16([v for f in [(100, -16384)] + [(0, 0)] * 31 for v in f])
        self.assertEqual(pk.peaks(self.wav(data, "c.wav", chans=2), 16)["peaks"][0], 0.5)

    def test_8bit_unsigned_centered_on_128(self):
        data = bytes([128] * 32)
        data = bytes([192]) + data[1:]  # +64 -> 0.5 of 128
        data = data[:2] + bytes([0]) + data[3:]  # -128 -> 1.0
        r = pk.peaks(self.wav(data, width=1), 16)
        self.assertEqual(r["peaks"][0], 0.5)
        self.assertEqual(r["peaks"][1], 1.0)
        self.assertEqual(r["peaks"][2], 0.0)

    def test_24bit(self):
        def s24(v):
            return v.to_bytes(3, "little", signed=True)
        vals = [0] * 32
        vals[4], vals[5] = 2 ** 22, -(2 ** 23)
        r = pk.peaks(self.wav(b"".join(s24(v) for v in vals), width=3), 16)
        self.assertEqual(r["peaks"][2], 1.0)
        vals = [0] * 32
        vals[0] = 2 ** 22
        self.assertEqual(pk.peaks(self.wav(b"".join(s24(v) for v in vals), "d.wav", width=3), 16)["peaks"][0], 0.5)

    def test_32bit(self):
        data = struct.pack("<32i", *([2 ** 30] + [0] * 31))
        self.assertEqual(pk.peaks(self.wav(data, width=4), 16)["peaks"][0], 0.5)

    def test_fewer_frames_than_buckets_leave_empty_buckets_at_zero(self):
        r = pk.peaks(self.wav(pcm16([32767, 16384, 8192])), 16)
        self.assertEqual(len(r["peaks"]), 16)
        self.assertEqual(sorted(x for x in r["peaks"] if x), [0.25, 0.5, 1.0])
        self.assertEqual(r["peaks"].count(0.0), 13)
        self.assertEqual(pk.peaks(self.wav(b"", "e.wav"), 16)["peaks"], [0.0] * 16)

    def test_buckets_cover_every_frame_when_not_divisible(self):
        vals = [0] * 35
        vals[34] = 32768 - 1
        self.assertEqual(pk.peaks(self.wav(pcm16(vals)), 16)["peaks"][15], 1.0)

    def test_rounding_is_half_up(self):
        vals = [0] * 16
        vals[0] = 2048  # 2048/32768 = 0.0625 exactly: half-up gives 0.063 (Python's round() would give 0.062)
        self.assertEqual(pk.peaks(self.wav(pcm16(vals)), 16)["peaks"][0], 0.063)

    def test_reads_across_chunks(self):
        vals = [0] * (pk._CHUNK_FRAMES * 2 + 5)
        vals[pk._CHUNK_FRAMES + 3] = 16384
        vals[-1] = -32768
        r = pk.peaks(self.wav(pcm16(vals)), 16)
        self.assertEqual((max(r["peaks"]), r["peaks"][-1]), (1.0, 1.0))
        self.assertEqual(r["peaks"][8], 0.5)

    def test_matches_the_frame_by_frame_rules_for_every_width_and_chunk_edge(self):
        rng = random.Random(7)
        for width, chans, frames, n in [(1, 1, 50, 16), (2, 2, 301, 16), (3, 2, 77, 20), (4, 1, 500, 33), (2, 3, 1000, 2000),
                                        (2, 1, 5, 16), (3, 1, 1000, 16)]:
            lim = 2 ** (8 * width - 1)
            data = bytes(rng.randrange(256) for _ in range(frames * chans * width))
            p = self.wav(data, f"r{width}{chans}{frames}.wav", width=width, chans=chans)
            want = reference_peaks(data, width, chans, n)
            for chunk in (7, 64, pk._CHUNK_FRAMES):  # buckets that end inside, at and across a chunk
                old, pk._CHUNK_FRAMES = pk._CHUNK_FRAMES, chunk
                try:
                    got = pk.peaks(p, n)["peaks"]
                finally:
                    pk._CHUNK_FRAMES = old
                self.assertEqual(got, want, (width, chans, frames, n, chunk))
            self.assertLessEqual(max(want), 1.0 if lim else 0)

    def test_a_minute_of_48khz_stereo_is_fast(self):
        data = struct.pack("<2h", 1000, -2000) * (48000 * 60)
        p = self.wav(data, "long.wav", chans=2, rate=48000)
        t0 = time.perf_counter()
        r = pk.peaks(p, 400)
        self.assertLess(time.perf_counter() - t0, 1.0)  # ~0.2 s (~0.85 s on the Deck); the per-frame loop took ~1.3 s
        self.assertEqual((r["audioMs"], r["peaks"][0], len(r["peaks"])), (60000, 0.061, 400))  # 2000/32768 = 0.0610

    def test_n_limits_have_a_clear_message(self):
        p = self.wav(pcm16([0] * 40))
        for bad in (15, 2001, 0, -1, 16.0, "16", None, True):
            with self.assertRaises(ValueError) as cm:
                pk.peaks(p, bad)
            self.assertNotIsInstance(cm.exception, pk.PeaksError)
            self.assertIn("between 16 and 2000", str(cm.exception))
            self.assertIn(repr(bad), str(cm.exception))
        self.assertEqual(len(pk.peaks(p, 16)["peaks"]), 16)
        self.assertEqual(len(pk.peaks(p, 2000)["peaks"]), 2000)

    def test_float_wav_fails_naming_the_path(self):
        p = self.dir / "float.wav"
        data = struct.pack("<32f", *([0.5] * 32))
        fmt = struct.pack("<HHIIHH", 3, 1, 1000, 4000, 4, 32)
        p.write_bytes(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<I", 16) + fmt
                      + b"data" + struct.pack("<I", len(data)) + data)
        with self.assertRaises(pk.PeaksError) as cm:
            pk.peaks(p, 16)
        self.assertIn(str(p), str(cm.exception))
        self.assertIsInstance(cm.exception, ValueError)

    def test_broken_or_missing_file_fails_naming_the_path(self):
        bad = self.dir / "bad.wav"
        bad.write_bytes(b"not a wav at all")
        gone = self.dir / "gone.wav"
        for p in (bad, gone):
            with self.assertRaises(pk.PeaksError) as cm:
                pk.peaks(p, 16)
            self.assertIn(str(p), str(cm.exception))


if __name__ == "__main__":
    unittest.main()

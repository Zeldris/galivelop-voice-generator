import array
import json
import math
import random
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from gvoice import cli, effects, i18n, schema as S
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
RATE = 24000
HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def chain(*steps):
    return {"name": "t", "steps": list(steps)}


def make_voice(path, noise=0.0002, lead=0.5, voice=3.0, tail=0.5):
    """Fake voice: a 150 Hz tone with harmonics, 4 Hz amplitude modulated, between two stretches of silence, all
    over white noise of the given RMS."""
    rng = random.Random(7)
    total = int(RATE * (lead + voice + tail))
    samples = array.array("h")
    for i in range(total):
        t = i / RATE
        value = rng.gauss(0, noise)
        if lead <= t < lead + voice:
            env = 0.6 + 0.4 * math.sin(2 * math.pi * 4 * t)
            value += 0.1 * env * sum(math.sin(2 * math.pi * 150 * k * t) / k for k in (1, 2, 3))
        samples.append(int(max(-1, min(1, value)) * 32767))
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(samples.tobytes())


def read(path):
    with wave.open(str(path), "rb") as fh:
        return array.array("h", fh.readframes(fh.getnframes())).tolist(), fh.getframerate()


def rms(values):
    return math.sqrt(sum(v * v for v in values) / len(values)) / 32768


def lufs(path):
    done = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                          capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", done.stderr)[-1])


class Compile(unittest.TestCase):
    def test_simple_steps(self):
        cases = [
            ({"type": "highpass", "freqHz": 80}, "highpass=f=80"),
            ({"type": "lowpass", "freqHz": 7500.5}, "lowpass=f=7500.5"),
            ({"type": "equalizer", "freqHz": 200, "widthOctaves": 1, "gainDb": -3},
             "equalizer=f=200:width_type=o:w=1:g=-3"),
            ({"type": "gain", "gainDb": 2.5}, "volume=2.5dB"),
        ]
        for step, expected in cases:
            self.assertEqual(effects.compile_chain(chain(step)), expected)

    def test_cleaning_steps(self):
        self.assertEqual(effects.compile_chain(chain({"type": "denoise", "strength": 0.5})),
                         "afftdn=nr=15:nf=-45:tn=1:tr=1")
        self.assertEqual(effects.compile_chain(chain({"type": "denoise", "strength": 0})),
                         "afftdn=nr=0.01:nf=-45:tn=1:tr=1")
        self.assertEqual(effects.compile_chain(chain({"type": "dereverb", "strength": 1})),
                         "agate=threshold=0.01:ratio=6:attack=5:release=60:knee=4")
        trim = effects.compile_chain(chain({"type": "trimSilence", "thresholdDb": -50, "marginMs": 150}))
        one = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.15:detection=peak"
        self.assertEqual(trim, "%s,areverse,%s,areverse" % (one, one))
        self.assertEqual(effects.compile_chain(chain({"type": "loudnorm", "targetLufs": -16})),
                         "loudnorm=I=-16:TP=-1.5:LRA=11")

    def test_loudnorm_second_pass_uses_the_measures(self):
        measured = {"input_i": "-24.1", "input_tp": "-3.0", "input_lra": "4.2", "input_thresh": "-35.0",
                    "target_offset": "0.3"}
        text = effects.compile_chain(chain({"type": "loudnorm", "targetLufs": -16, "truePeakDb": -2}), measured)
        self.assertEqual(text, "loudnorm=I=-16:TP=-2:LRA=11:measured_I=-24.1:measured_TP=-3.0:measured_LRA=4.2:"
                               "measured_thresh=-35.0:offset=0.3:linear=true")

    def test_loudnorm_second_pass_is_skipped_when_a_measure_is_not_finite(self):
        # Silent input: ffmpeg measures "-inf" and loudnorm rejects it as a measured_* value.
        step = chain({"type": "loudnorm", "targetLufs": -16})
        for bad in ("-inf", "inf", "nan"):
            measured = {"input_i": bad, "input_tp": "-inf", "input_lra": "0.00", "input_thresh": "-70.00",
                        "target_offset": "inf"}
            self.assertEqual(effects.compile_chain(step, measured), "loudnorm=I=-16:TP=-1.5:LRA=11")

    def test_apply_with_silent_measures_runs_the_plain_loudnorm(self):
        silent = {"input_i": "-inf", "input_tp": "-inf", "input_lra": "0.00", "input_thresh": "-inf",
                  "target_offset": "inf"}
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.wav"
            write_wav_header(src, rate=RATE, fmt=1, bits=16)
            with mock.patch.object(effects, "_measure", return_value=silent), \
                    mock.patch.object(effects, "_run") as run:
                filters = effects.apply(chain({"type": "loudnorm", "targetLufs": -16}), src, Path(tmp) / "b.wav")
        self.assertNotIn("measured_", filters)
        self.assertNotIn("measured_", " ".join(run.call_args[0][0]))

    def test_steps_join_in_order(self):
        text = effects.compile_chain(chain({"type": "highpass", "freqHz": 80}, {"type": "gain", "gainDb": 1}))
        self.assertEqual(text, "highpass=f=80,volume=1dB")

    def test_unsupported_types_say_why_in_both_languages(self):
        for step in ({"type": "pitch", "semitones": 2}, {"type": "saturation", "drive": 0.3}):
            with self.assertRaises(GvoiceError) as caught:
                effects.compile_chain(chain(step))
            self.assertEqual(caught.exception.code, "effects.unsupported")
            self.assertIn("F3", caught.exception.message("es"))
            self.assertIn(step["type"], caught.exception.message("en"))
            self.assertIn("arrives in F3", caught.exception.message("en"))

    def test_apply_rejects_an_invalid_chain_before_running_ffmpeg(self):
        with self.assertRaises(GvoiceError) as caught:
            effects.apply(chain({"type": "denoise"}), "a.wav", "b.wav")
        self.assertEqual(caught.exception.code, "effects.invalid")

    def test_apply_rejects_two_loudnorm(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.wav"
            src.write_bytes(b"")
            step = {"type": "loudnorm", "targetLufs": -16}
            with self.assertRaises(GvoiceError) as caught:
                effects.apply(chain(step, step), src, Path(tmp) / "b.wav")
            self.assertEqual(caught.exception.code, "effects.many_loudnorm")


def write_wav_header(path, rate, fmt, bits, extensible=False):
    """A WAV with an empty data chunk and the given fmt: 1 PCM, 3 IEEE float, or extensible (a `wave`-unreadable one)."""
    tag = 0xFFFE if extensible else fmt
    body = struct.pack("<HHIIHH", tag, 1, rate, rate * bits // 8, bits // 8, bits)
    if extensible:
        body += struct.pack("<HHI", 22, bits, 4) + struct.pack("<H", fmt) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    data = b"WAVE" + b"fmt " + struct.pack("<I", len(body)) + body + b"LIST" + struct.pack("<I", 3) + b"abc\x00" \
        + b"data" + struct.pack("<I", 0)
    Path(path).write_bytes(b"RIFF" + struct.pack("<I", len(data)) + data)


class Rate(unittest.TestCase):
    def test_rate_is_read_from_any_wav_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, kw in (("pcm", dict(fmt=1, bits=16)), ("float", dict(fmt=3, bits=32)),
                             ("ext", dict(fmt=3, bits=32, extensible=True))):
                path = Path(tmp) / (name + ".wav")
                write_wav_header(path, rate=24000, **kw)
                self.assertEqual(effects._rate(path), 24000, name)
            (Path(tmp) / "x.wav").write_bytes(b"not a wav at all")
            self.assertIsNone(effects._rate(Path(tmp) / "x.wav"))

    def test_apply_always_pins_the_output_to_the_source_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.wav"
            write_wav_header(src, rate=24000, fmt=3, bits=32)  # float: `wave` cannot read it
            with mock.patch.object(effects, "_run") as run:
                filters = effects.apply(chain({"type": "gain", "gainDb": 1}), src, Path(tmp) / "b.wav")
        self.assertEqual(filters, "volume=1dB,aresample=24000")
        self.assertIn("volume=1dB,aresample=24000", run.call_args[0][0])


class Schema(unittest.TestCase):
    def errors(self, step):
        return sorted((e.path, e.code) for e in S.validate(chain(step), S.load_schema("effect-chain")))

    def test_new_steps_require_and_admit_only_their_own_parameters(self):
        self.assertEqual(self.errors({"type": "denoise", "strength": 0.5}), [])
        self.assertEqual(self.errors({"type": "trimSilence", "thresholdDb": -50}), [])
        self.assertEqual(self.errors({"type": "loudnorm", "targetLufs": -16, "truePeakDb": -1.5, "lra": 7}), [])
        self.assertNotEqual(self.errors({"type": "denoise"}), [])
        self.assertNotEqual(self.errors({"type": "denoise", "strength": 2}), [])
        self.assertNotEqual(self.errors({"type": "dereverb", "strength": 0.5, "lra": 7}), [])
        self.assertNotEqual(self.errors({"type": "trimSilence", "marginMs": 10}), [])
        self.assertNotEqual(self.errors({"type": "loudnorm", "targetLufs": 3}), [])
        self.assertNotEqual(self.errors({"type": "loudnorm", "targetLufs": -16, "strength": 1}), [])


class Preset(unittest.TestCase):
    def test_lectura_is_valid_and_ordered_without_colouring(self):
        data = json.loads((ROOT / "gvoice" / "effect_presets" / "lectura.json").read_text(encoding="utf-8"))
        self.assertEqual(S.validate(data, S.load_schema("effect-chain")), [])
        self.assertEqual([s["type"] for s in data["steps"]], ["denoise", "dereverb", "trimSilence", "loudnorm"])
        self.assertEqual(data["steps"][-1]["targetLufs"], -16)
        self.assertIn("lectura", effects.presets())
        self.assertEqual(effects.load_chain("lectura"), data)

    def test_load_chain_from_a_path_and_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps(chain({"type": "gain", "gainDb": 1})), encoding="utf-8")
            self.assertEqual(effects.load_chain(str(path))["steps"][0]["type"], "gain")
            with self.assertRaises(GvoiceError) as caught:
                effects.load_chain(str(Path(tmp) / "nope.json"))
            self.assertEqual(caught.exception.code, "effects.unreadable")

    def test_effect_texts_exist_in_both_languages(self):
        for code in ("unsupported", "invalid", "unreadable", "no_ffmpeg", "failed", "many_loudnorm"):
            for lang in ("es", "en"):
                self.assertNotEqual(i18n.t("error.effects." + code, lang, type="x", path="x", reason="x"),
                                    "error.effects." + code)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is not installed")
class WithFfmpeg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_trim_silence_cuts_start_and_end_keeping_the_margin(self):
        src, dst = self.dir / "in.wav", self.dir / "out.wav"
        make_voice(src)
        effects.apply(chain({"type": "trimSilence", "thresholdDb": -50, "marginMs": 100}), src, dst)
        values, rate = read(dst)
        self.assertEqual(rate, RATE)
        self.assertAlmostEqual(len(values) / rate, 3.0 + 0.2, delta=0.1)  # 3 s of voice + 100 ms each side
        self.assertGreater(rms(values[: rate // 20]), 0)  # the margin is still there, not cut to nothing

    def test_denoise_lowers_the_background_noise(self):
        src, dst = self.dir / "in.wav", self.dir / "out.wav"
        make_voice(src, noise=0.01)
        effects.apply(chain({"type": "denoise", "strength": 1}), src, dst)
        before, _ = read(src)
        after, _ = read(dst)
        gap = slice(int(RATE * 0.1), int(RATE * 0.4))
        self.assertLess(rms(after[gap]), rms(before[gap]) * 0.5)

    def test_dereverb_gates_the_gaps_but_keeps_the_voice(self):
        src, dst = self.dir / "in.wav", self.dir / "out.wav"
        make_voice(src, noise=0.003)
        effects.apply(chain({"type": "dereverb", "strength": 1}), src, dst)
        before, _ = read(src)
        after, _ = read(dst)
        gap, speech = slice(int(RATE * 0.1), int(RATE * 0.4)), slice(RATE, RATE * 3)
        self.assertLess(rms(after[gap]), rms(before[gap]) * 0.5)
        self.assertGreater(rms(after[speech]), rms(before[speech]) * 0.8)

    def test_loudnorm_lands_on_the_target_within_one_lu(self):
        src, dst = self.dir / "in.wav", self.dir / "out.wav"
        make_voice(src)
        self.assertLess(abs(lufs(src) + 16), 99)
        self.assertGreater(abs(lufs(src) + 16), 3)  # the source is not already there
        effects.apply(chain({"type": "loudnorm", "targetLufs": -16}), src, dst)
        self.assertAlmostEqual(lufs(dst), -16, delta=1)
        self.assertEqual(read(dst)[1], RATE)

    def test_lectura_preset_end_to_end(self):
        src, dst = self.dir / "in.wav", self.dir / "out.wav"
        make_voice(src, noise=0.004)
        filters = effects.apply(effects.load_chain("lectura"), src, dst)
        self.assertTrue(filters.startswith("afftdn="))
        values, rate = read(dst)
        self.assertLess(len(values) / rate, 3.6)
        self.assertAlmostEqual(lufs(dst), -16, delta=1)

    def test_cli_fx_apply_json(self):
        src, dst = self.dir / "in.wav", self.dir / "out.wav"
        make_voice(src)
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["fx", "apply", "lectura", str(src), str(dst), "--json", "--lang", "en"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual((data["chain"], data["output"]), ("lectura", str(dst)))
        self.assertIn("loudnorm=", data["filter"])
        self.assertTrue(dst.is_file())

    def test_cli_unsupported_step_exits_1_with_the_reason(self):
        import contextlib
        import io
        path = self.dir / "c.json"
        path.write_text(json.dumps(chain({"type": "pitch", "semitones": 2})), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(["fx", "apply", str(path), "a.wav", "b.wav", "--lang", "es"])
        self.assertEqual(code, 1)
        self.assertIn("F3", err.getvalue())


if __name__ == "__main__":
    unittest.main()

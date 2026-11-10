import json
import unittest
from pathlib import Path

from gvoice import sheet
from gvoice.errors import GvoiceError

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "design-sheet.json"
KEYS = ["gender", "age", "pitch", "speed", "volume", "clarity", "fluency", "accent", "texture", "emotion",
        "tone", "personality"]


def codes(s):
    return [w.code for w in sheet.warnings(s)]


class InstructionTests(unittest.TestCase):
    def test_fixed_order_whatever_the_dict_order(self):
        s = {"personality": "p", "gender": "g", "tone": "t", "age": "adult"}
        self.assertEqual(sheet.instruction(s), "Gender: g. Age: adult. Tone: t. Personality: p.")

    def test_all_twelve_keys_in_template_order_then_extra(self):
        s = {k: "v-" + k for k in reversed(KEYS)}
        s["extra"] = {"zeta": "z", "alpha": "a"}
        want = " ".join("%s: v-%s." % (k.capitalize(), k) for k in KEYS) + " Zeta: z. Alpha: a."
        self.assertEqual(sheet.instruction(s), want)

    def test_absent_keys_omitted_and_empty_sheet(self):
        self.assertEqual(sheet.instruction({"pitch": "low"}), "Pitch: low.")
        self.assertEqual(sheet.instruction({}), "")

    def test_trailing_period_not_doubled_and_schema_key_ignored(self):
        self.assertEqual(sheet.instruction({"$schema": "x", "tone": "calm."}), "Tone: calm.")

    def test_example_sheet(self):
        s = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        text = sheet.instruction(s)
        self.assertTrue(text.startswith("Gender: male. Age: middle-aged adult. Pitch: low."))
        self.assertTrue(text.endswith("Breathing: audible between sentences."))
        self.assertEqual(sheet.warnings(s), [])

    def test_invalid_sheet_says_why(self):
        with self.assertRaises(GvoiceError) as cm:
            sheet.instruction({"age": ""})
        self.assertEqual(cm.exception.code, "sheet.invalid")
        self.assertIn("age", cm.exception.message("en"))
        with self.assertRaises(GvoiceError) as cm:
            sheet.warnings({"colour": "red"})
        self.assertEqual(cm.exception.code, "sheet.invalid")
        self.assertIn("colour", cm.exception.message("en"))


class AdultTests(unittest.TestCase):
    def test_adult_ages(self):
        for age in ("adult", "young adult", "middle-aged adult", "elderly", "Elderly woman", "old man", "senior",
                    "30s", "in his thirties", "35 years old", "18", "mature", "man"):
            self.assertTrue(sheet.is_adult(age), age)

    def test_not_adult_ages(self):
        for age in ("teen", "teenager", "child", "kid", "young", "young man", "young voice", "12 years old",
                    "17", "girl", "childlike adult", "underage", "ageless", "", "   ", None, 30):
            self.assertFalse(sheet.is_adult(age), repr(age))

    def test_age_warnings(self):
        self.assertEqual(codes({}), ["sheet.age_missing"])
        self.assertEqual(codes({"pitch": "low"}), ["sheet.age_missing"])
        for age in ("teen", "child", "young"):
            ws = sheet.warnings({"age": age})
            self.assertEqual([w.code for w in ws], ["sheet.age_not_adult"])
            self.assertEqual(ws[0].params, {"age": age})
        for age in ("young adult", "elderly", "adult"):
            self.assertEqual(codes({"age": age}), [])


class BannedWordTests(unittest.TestCase):
    def test_each_word_is_reported_with_field_and_suggestions(self):
        for word in sheet.BANNED_WORDS:
            ws = sheet.warnings({"age": "adult", "tone": "a %s voice" % word})
            self.assertEqual([w.code for w in ws], ["sheet.banned_word"], word)
            self.assertEqual(ws[0].params["word"], word)
            self.assertEqual(ws[0].params["field"], "tone")
            for s in ("airy", "breathy", "soft-spoken", "whispering"):
                self.assertIn(s, ws[0].params["suggestions"])

    def test_whole_word_only_and_any_case(self):
        self.assertEqual(codes({"age": "adult", "tone": "Lightly, delightful, brighten, smaller"}), [])
        self.assertEqual(codes({"age": "adult", "tone": "BRIGHT"}), ["sheet.banned_word"])
        self.assertEqual(codes({"age": "adult", "tone": "high-pitched"}), ["sheet.banned_word"])
        self.assertEqual(codes({"age": "adult", "tone": "High Pitched"}), ["sheet.banned_word"])
        self.assertEqual(codes({"age": "adult", "pitch": "high", "tone": "pitched"}), [])

    def test_extra_values_are_checked(self):
        ws = sheet.warnings({"age": "adult", "extra": {"mood": "cute and small"}})
        self.assertEqual([(w.params["word"], w.params["field"]) for w in ws], [("cute", "mood"), ("small", "mood")])

    def test_age_field_can_trip_both(self):
        ws = sheet.warnings({"age": "childlike"})
        self.assertEqual([w.code for w in ws], ["sheet.age_not_adult", "sheet.banned_word"])


class MessageTests(unittest.TestCase):
    def test_messages_are_translated_and_different(self):
        s = {"age": "teen", "tone": "cute"}
        for w in sheet.warnings(s) + [sheet.Warning("sheet.age_missing")]:
            es, en = w.message("es"), w.message("en")
            self.assertNotIn("warning.", es)
            self.assertNotIn("warning.", en)
            self.assertNotEqual(es, en)
        self.assertIn("airy", sheet.warnings(s)[1].message("en"))
        self.assertIn("cute", sheet.warnings(s)[1].message("es"))


if __name__ == "__main__":
    unittest.main()

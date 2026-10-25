# Ficha de diseño (D11): sin origen en gimg.
import json
import unittest
from pathlib import Path

from gvoice import schema, sheet
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
FULL = json.loads((ROOT / "examples" / "design-sheet.json").read_text())
FULL.pop("$schema")


def codes(s):
    return [(w["code"], w["params"]) for w in sheet.warnings(s)]


class InstructTests(unittest.TestCase):
    def test_keys_come_from_the_schema(self):
        props = list(schema.load_schema("design-sheet")["properties"])
        self.assertEqual(sheet.keys(), [k for k in props if k not in ("$schema", "extra")])
        self.assertEqual(len(sheet.keys()), 12)

    def test_order_is_the_schema_order_not_the_dict_order(self):
        shuffled = {k: FULL[k] for k in reversed(list(FULL))}
        text = sheet.build_instruct(shuffled)
        self.assertEqual(text, sheet.build_instruct(FULL))
        positions = [text.index("%s: " % k) for k in sheet.keys()]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(text.startswith("A voice with gender: male; age: middle-aged adult; pitch: low;"))

    def test_extra_goes_last_in_given_order(self):
        text = sheet.build_instruct({"extra": {"b": "two", "a": "one"}, "tone": "calm", "gender": "female"})
        self.assertEqual(text, "A voice with gender: female; tone: calm; b: two; a: one.")

    def test_only_present_keys_and_blanks_skipped(self):
        self.assertEqual(sheet.build_instruct({"pitch": "low"}), "A voice with pitch: low.")
        self.assertEqual(sheet.build_instruct({"pitch": "  low "}), "A voice with pitch: low.")
        self.assertEqual(sheet.build_instruct({}), "A voice.")
        self.assertEqual(sheet.build_instruct({"extra": {}}), "A voice.")

    def test_full_example(self):
        text = sheet.build_instruct(FULL)
        self.assertTrue(text.endswith("personality: precise and formal; breathing: audible between sentences."))

    def test_invalid_sheet(self):
        for bad in ({"pitch": ""}, {"nope": "x"}, {"extra": {"a": ""}}, [], {"age": 5}):
            for fn in (sheet.build_instruct, sheet.warnings):
                with self.assertRaises(GvoiceError) as cm:
                    fn(bad)
                self.assertEqual(cm.exception.code, "sheet.invalid")
                self.assertTrue(cm.exception.errors)


class WarningTests(unittest.TestCase):
    def test_no_warning_for_the_example(self):
        self.assertEqual(codes(FULL), [])

    def test_age_missing(self):
        self.assertEqual(codes({"pitch": "low"}), [("sheet.age_missing", {})])
        self.assertEqual(codes({}), [("sheet.age_missing", {})])
        self.assertEqual(codes({"age": "   "}), [("sheet.age_missing", {})])

    def test_age_adult_values(self):
        for age in ("adult", "young adult", "middle-aged adult", "elderly", "30s", "in his 40s", "18", "35 years old",
                    "young", "old man"):
            self.assertEqual(codes({"age": age}), [], age)

    def test_age_minor_values(self):
        for age in ("child", "Teenager", "teen", "a young boy", "girl", "12", "17 years old", "under 16",
                    "kid", "adolescent", "mid-teens", "baby", "child-like"):
            self.assertEqual(codes({"age": age}), [("sheet.age_minor", {"age": age})], age)

    def test_banned_words_whole_words_any_case(self):
        self.assertEqual(codes({"age": "adult", "tone": "Bright"}), [(
            "sheet.banned_word", {"word": "bright", "suggestion": "airy", "field": "tone"})])
        for ok in ("brightness", "delight", "smaller", "lighthouse", "accuter", "cuteness", "highly pitched"):
            self.assertEqual(codes({"age": "adult", "tone": ok}), [], ok)
        self.assertEqual(len(codes({"age": "adult", "tone": "light-hearted"})), 1)
        self.assertEqual(len(codes({"age": "adult", "pitch": "HIGH-PITCHED"})), 1)

    def test_each_banned_word_has_its_warning_with_a_suggestion(self):
        for word, suggestion in sheet.BANNED_WORDS.items():
            self.assertEqual(codes({"age": "adult", "texture": "very %s sound" % word}), [
                ("sheet.banned_word", {"word": word, "suggestion": suggestion, "field": "texture"})], word)
        self.assertEqual(set(sheet.BANNED_WORDS), {"bright", "cute", "small", "light", "childlike", "high-pitched"})
        self.assertEqual(set(sheet.BANNED_WORDS.values()) - {"airy", "breathy", "soft-spoken", "whispering"}, set())

    def test_banned_word_once_per_sheet_with_first_field_and_extra_is_scanned(self):
        result = codes({"age": "adult", "tone": "cute", "emotion": "cute", "extra": {"x": "small voice"}})
        self.assertEqual(result, [
            ("sheet.banned_word", {"word": "cute", "suggestion": "soft-spoken", "field": "emotion"}),
            ("sheet.banned_word", {"word": "small", "suggestion": "soft-spoken", "field": "x"})])

    def test_age_and_words_together_age_first(self):
        result = codes({"age": "childlike teen", "tone": "bright"})
        self.assertEqual([c for c, _ in result], ["sheet.age_minor", "sheet.banned_word", "sheet.banned_word"])
        self.assertEqual([p.get("word") for _, p in result[1:]], ["bright", "childlike"])

    def test_warnings_do_not_block_and_do_not_change_the_sheet(self):
        s = {"tone": "bright"}
        sheet.warnings(s)
        self.assertEqual(s, {"tone": "bright"})
        self.assertIn("bright", sheet.build_instruct(s))

    def test_messages_in_both_languages(self):
        for s in ({}, {"age": "child", "tone": "cute"}):
            for w in sheet.warnings(s):
                for lang in ("es", "en"):
                    text = sheet.message(w, lang)
                    self.assertNotIn("warning.", text)
        es = sheet.message(sheet.warnings({"age": "adult", "tone": "cute"})[0], "es")
        en = sheet.message(sheet.warnings({"age": "adult", "tone": "cute"})[0], "en")
        self.assertNotEqual(es, en)
        self.assertIn("soft-spoken", en)


if __name__ == "__main__":
    unittest.main()

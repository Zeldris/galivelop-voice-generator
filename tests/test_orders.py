import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import engine, orders, paths, projects
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
VOICE = json.loads((ROOT / "examples" / "order-voice.json").read_text())
LINE = json.loads((ROOT / "examples" / "order-line.json").read_text())
CONFIG = json.loads((ROOT / "examples" / "galivelop-voices.json").read_text())


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {
            "GVOICE_CONFIG_HOME": str(self.tmp / "cfg"), "GVOICE_DATA_HOME": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = self.tmp / "world"
        root.mkdir()
        cfg = copy.deepcopy(CONFIG)
        cfg.pop("$schema", None)
        cfg["name"] = "world"
        (root / projects.CONFIG_FILE).write_text(json.dumps(cfg))
        projects.add(root)
        self.p = "world"

    def voice(self, **changes):
        order = copy.deepcopy(VOICE)
        order.pop("$schema")
        order.update(changes)
        return order

    def line(self, key="narrator/intro-01", **changes):
        order = copy.deepcopy(LINE)
        order.pop("$schema")
        order.update(key=key, **changes)
        return order

    def take(self, key="narrator", seed=1, **result):
        """A finished voice take (as the worker adds it)."""
        spec = orders.attempt_specs(self.p, key, seed=seed)[0]
        spec["result"] = engine.EngineResult(duration_ms=5, engine_version="fake-1", audio_ms=900, **result)
        return orders.add_attempt(self.p, key, spec)

    def fixed_voice(self):
        orders.submit(self.p, self.voice())
        first = self.take()
        orders.choose(self.p, "narrator", first)
        return first

    def made_line(self, key="narrator/intro-01", seed=3):
        spec = orders.attempt_specs(self.p, key, seed=seed)[0]
        spec["result"] = {"audio_ms": 500}
        return orders.add_attempt(self.p, key, spec)

    def code(self, call, *args, **kw):
        with self.assertRaises(GvoiceError) as cm:
            call(*args, **kw)
        return cm.exception


class SubmitTests(Base):
    def test_create_voice(self):
        rec = orders.submit(self.p, self.voice())
        self.assertEqual((rec["key"], rec["type"], rec["attempts"], rec["chosen"], rec["chosenHistory"]),
                         ("narrator", "voice", [], None, []))
        self.assertEqual(rec["seed"], 1234)
        self.assertTrue((self.tmp / "data/projects/world/orders/narrator/@/order.json").is_file())

    def test_warnings_returned_not_stored_not_blocking(self):
        sheet = dict(self.voice()["designSheet"], age="12 years old", tone="cute")
        rec = orders.submit(self.p, self.voice(designSheet=sheet))
        self.assertEqual({w["code"] for w in rec["warnings"]}, {"sheet.age_not_adult", "sheet.banned_word"})
        self.assertNotIn("warnings", orders.get(self.p, "narrator"))
        self.assertEqual(orders.submit(self.p, self.voice())["warnings"], [])

    def test_resubmit_keeps_attempts_chosen_and_replaces_fields(self):
        orders.submit(self.p, self.voice())
        first = self.take()
        orders.choose(self.p, "narrator", first)
        created = orders.get(self.p, "narrator")["createdAt"]
        again = self.voice(testText="Another test.")
        del again["seed"]
        rec = orders.submit(self.p, again)
        self.assertEqual(rec["testText"], "Another test.")
        self.assertIsNone(rec["seed"])
        self.assertEqual([a["id"] for a in rec["attempts"]], [first])
        self.assertEqual(rec["chosen"], first)
        self.assertEqual(rec["createdAt"], created)

    def test_resubmit_other_type_rejected(self):
        self.fixed_voice()
        err = self.code(orders.submit, self.p, self.line(key="narrator"))
        self.assertEqual(err.code, "order.type_changed")
        self.assertEqual((err.params["type"], err.params["new"]), ("voice", "line"))

    def test_invalid_order_has_reasons(self):
        bad = self.voice()
        del bad["testText"]
        err = self.code(orders.submit, self.p, bad)
        self.assertEqual(err.code, "order.invalid")
        self.assertIn("testText", err.message("en"))

    def test_voice_with_line_fields_rejected(self):
        err = self.code(orders.submit, self.p, self.voice(text="x"))
        self.assertEqual(err.code, "order.invalid")

    def test_key_limit(self):
        err = self.code(orders.submit, self.p, self.voice(key="a" * 101))
        self.assertEqual(err.code, "order.invalid")
        self.assertIn("100", err.message("en"))

    def test_unknown_project(self):
        self.assertEqual(self.code(orders.submit, "nope", self.voice()).code, "project.unknown")

    def test_unknown_order(self):
        self.assertEqual(self.code(orders.get, self.p, "ghost").code, "order.unknown")
        self.assertFalse((self.tmp / "data/projects/world/orders/ghost").exists())

    def test_corrupt_order(self):
        orders.submit(self.p, self.voice())
        (self.tmp / "data/projects/world/orders/narrator/@/order.json").write_text("{not json")
        self.assertEqual(self.code(orders.get, self.p, "narrator").code, "order.corrupt")


class LineRuleTests(Base):
    def test_line_needs_voice_order(self):
        err = self.code(orders.submit, self.p, self.line())
        self.assertEqual(err.code, "order.voice_unknown")
        self.assertIn("narrator", err.message("es"))

    def test_voice_must_be_a_voice_order(self):
        self.fixed_voice()
        orders.submit(self.p, self.line())
        err = self.code(orders.submit, self.p, self.line(key="x", voice="narrator/intro-01"))
        self.assertEqual(err.code, "order.voice_unknown")

    def test_line_without_fixed_voice_rejected_with_reason(self):
        orders.submit(self.p, self.voice())
        self.take()  # a take, but none chosen
        err = self.code(orders.submit, self.p, self.line())
        self.assertEqual(err.code, "order.voice_not_fixed")
        self.assertIn("narrator", err.message("en"))
        self.assertNotEqual(err.message("en"), err.message("es"))
        self.assertEqual(orders.list_orders(self.p, type="line"), [])

    def test_line_after_voice_unfixed_by_undo_rejected(self):
        first = self.fixed_voice()
        orders.undo(self.p, "narrator")
        self.assertEqual(self.code(orders.submit, self.p, self.line()).code, "order.voice_not_fixed")
        self.assertEqual(first, 1)

    def test_line_ok_and_resubmit(self):
        self.fixed_voice()
        rec = orders.submit(self.p, self.line())
        self.assertEqual((rec["type"], rec["voice"], rec["text"]), ("line", "narrator", LINE["text"]))
        made = self.made_line()
        rec = orders.submit(self.p, self.line(text="Changed."))
        self.assertEqual(rec["text"], "Changed.")
        self.assertEqual([a["id"] for a in rec["attempts"]], [made])

    def test_line_key_may_be_nested_under_voice_key(self):
        self.fixed_voice()
        orders.submit(self.p, self.line())
        self.assertEqual([r["key"] for r in orders.list_orders(self.p)], ["narrator", "narrator/intro-01"])

    def test_line_attempt_specs_carry_reference(self):
        first = self.fixed_voice()
        orders.submit(self.p, self.line())
        specs = orders.attempt_specs(self.p, "narrator/intro-01", 2)
        self.assertEqual([s["reference"] for s in specs], [first, first])
        self.assertEqual(specs[0]["text"], LINE["text"])
        self.assertEqual([s["seed"] for s in specs], [7, 8])

    def test_attempt_specs_need_fixed_voice(self):
        self.fixed_voice()
        orders.submit(self.p, self.line())
        orders.undo(self.p, "narrator")
        self.assertEqual(self.code(orders.attempt_specs, self.p, "narrator/intro-01").code, "order.voice_not_fixed")

    def test_add_attempt_reference_must_exist(self):
        self.fixed_voice()
        orders.submit(self.p, self.line())
        spec = dict(orders.attempt_specs(self.p, "narrator/intro-01")[0], reference=99)
        self.assertEqual(self.code(orders.add_attempt, self.p, "narrator/intro-01", spec).code,
                         "order.reference_unknown")


class SpecTests(Base):
    def test_voice_specs(self):
        orders.submit(self.p, self.voice())
        specs = orders.attempt_specs(self.p, "narrator", 3)
        self.assertEqual([s["seed"] for s in specs], [1234, 1235, 1236])
        self.assertTrue(specs[0]["instruction"].startswith("Gender: male. Age: middle-aged adult."))
        self.assertEqual(specs[0]["text"], VOICE["testText"])

    def test_seed_override_and_random(self):
        orders.submit(self.p, self.voice())
        self.assertEqual(orders.attempt_specs(self.p, "narrator", seed=5)[0]["seed"], 5)
        order = self.voice()
        del order["seed"]
        orders.submit(self.p, order)
        seeds = {s["seed"] for s in orders.attempt_specs(self.p, "narrator", 20)}
        self.assertGreater(len(seeds), 1)
        self.assertTrue(all(0 <= s < 2 ** 32 for s in seeds))

    def test_seed_range_and_count(self):
        orders.submit(self.p, self.voice(seed=2 ** 32 - 1))
        self.assertEqual(self.code(orders.attempt_specs, self.p, "narrator", 2).code, "order.seed_range")
        self.assertEqual(self.code(orders.attempt_specs, self.p, "narrator", 0).code, "order.count_invalid")
        self.assertEqual(self.code(orders.attempt_specs, self.p, "narrator", 51).code, "order.count_invalid")
        self.assertEqual(self.code(orders.attempt_specs, self.p, "narrator", seed=-1).code, "order.invalid")


class AttemptTests(Base):
    def test_add_attempt_stores_take_and_d16_metadata(self):
        orders.submit(self.p, self.voice())
        n = self.take(device="Vulkan0", seed=1234, engine_commit="abc", model="0.6b-base")
        att = orders.get(self.p, "narrator")["attempts"][0]
        self.assertEqual(n, 1)
        self.assertEqual((att["state"], att["seed"], att["note"]), ("new", 1234, ""))
        self.assertEqual((att["device"], att["engineVersion"], att["engineCommit"], att["model"]),
                         ("Vulkan0", "fake-1", "abc", "0.6b-base"))
        self.assertEqual((att["durationMs"], att["audioMs"]), (5, 900))
        self.assertTrue(att["instruction"].startswith("Gender: male."))
        self.assertEqual(att["audio"], "attempts/1/audio.wav")
        self.assertEqual(orders.attempt_audio(self.p, "narrator", att),
                         self.tmp / "data/projects/world/orders/narrator/@/attempts/1/audio.wav")

    def test_ids_sequential_and_entry_idempotent(self):
        orders.submit(self.p, self.voice())
        spec = orders.attempt_specs(self.p, "narrator")[0]
        a = orders.add_attempt(self.p, "narrator", spec, entry_id=7)
        b = orders.add_attempt(self.p, "narrator", spec, entry_id=7)
        c = orders.add_attempt(self.p, "narrator", spec, entry_id=8)
        self.assertEqual((a, b, c), (1, 1, 2))
        att = orders.attempt_for_entry(self.p, "narrator", 8)
        self.assertEqual((att["id"], att["audio"]), (2, "attempts/q8/audio.wav"))
        self.assertIsNone(orders.attempt_for_entry(self.p, "narrator", 99))
        self.assertTrue(str(orders.pending_audio_path(self.p, "narrator", 8)).endswith("attempts/q8/.pending.wav"))

    def test_bad_specs(self):
        orders.submit(self.p, self.voice())
        err = self.code(orders.add_attempt, self.p, "narrator", {"seed": 1, "text": "x"})
        self.assertEqual((err.code, err.params["missing"]), ("order.spec_invalid", "instruction"))
        spec = orders.attempt_specs(self.p, "narrator")[0]
        self.assertEqual(self.code(orders.add_attempt, self.p, "narrator", spec, entry_id=0).code,
                         "order.spec_invalid")
        self.assertEqual(self.code(orders.add_attempt, self.p, "narrator", dict(spec, seed=-3)).code,
                         "order.invalid")

    def test_states(self):
        orders.submit(self.p, self.voice())
        n = self.take()
        self.assertEqual(orders.mark(self.p, "narrator", n, "candidate")["state"], "candidate")
        self.assertEqual(orders.mark(self.p, "narrator", n, "discarded")["state"], "discarded")
        err = self.code(orders.mark, self.p, "narrator", n, "bogus")
        self.assertEqual((err.code, err.params["state"]), ("order.state_invalid", "bogus"))
        self.assertEqual(self.code(orders.mark, self.p, "narrator", 9, "new").code, "order.attempt_unknown")
        self.assertEqual(self.code(orders.mark, self.p, "narrator", True, "new").code, "order.attempt_unknown")

    def test_chosen_cannot_be_discarded(self):
        orders.submit(self.p, self.voice())
        n = self.take()
        orders.choose(self.p, "narrator", n)
        self.assertEqual(self.code(orders.mark, self.p, "narrator", n, "discarded").code, "order.discard_chosen")
        self.assertEqual(orders.get(self.p, "narrator")["attempts"][0]["state"], "new")

    def test_discarded_cannot_be_chosen(self):
        orders.submit(self.p, self.voice())
        n = self.take()
        orders.mark(self.p, "narrator", n, "discarded")
        self.assertEqual(self.code(orders.choose, self.p, "narrator", n).code, "order.choose_discarded")

    def test_attempt_without_audio_cannot_be_chosen(self):
        orders.submit(self.p, self.voice())
        n = orders.add_attempt(self.p, "narrator", orders.attempt_specs(self.p, "narrator")[0])
        self.assertEqual(self.code(orders.choose, self.p, "narrator", n).code, "order.choose_no_audio")

    def test_note(self):
        orders.submit(self.p, self.voice())
        n = self.take()
        self.assertEqual(orders.note(self.p, "narrator", n, "too nasal")["note"], "too nasal")
        self.assertEqual(orders.note(self.p, "narrator", n, "")["note"], "")
        self.assertEqual(self.code(orders.note, self.p, "narrator", n, 5).code, "order.note_invalid")

    def test_list_filters(self):
        self.fixed_voice()
        orders.submit(self.p, self.line())
        orders.submit(self.p, self.voice(key="orc"))
        self.assertEqual([r["key"] for r in orders.list_orders(self.p)], ["narrator", "narrator/intro-01", "orc"])
        self.assertEqual([r["key"] for r in orders.list_orders(self.p, type="voice")], ["narrator", "orc"])
        self.assertEqual([r["key"] for r in orders.list_orders(self.p, type="voice", chosen=False)], ["orc"])
        self.assertEqual([r["key"] for r in orders.list_orders(self.p, chosen=True)], ["narrator"])
        self.assertEqual(self.code(orders.list_orders, self.p, type="sound").code, "order.type_invalid")


class ChooseStackTests(Base):
    def setUp(self):
        super().setUp()
        orders.submit(self.p, self.voice())
        self.a, self.b, self.c = self.take(seed=1), self.take(seed=2), self.take(seed=3)

    def chosen(self):
        rec = orders.get(self.p, "narrator")
        return rec["chosen"], rec["chosenHistory"]

    def test_stack(self):
        self.assertEqual(orders.choose(self.p, "narrator", self.a), {"old": None, "new": self.a})
        self.assertEqual(orders.choose(self.p, "narrator", self.b), {"old": self.a, "new": self.b})
        self.assertEqual(orders.choose(self.p, "narrator", self.c), {"old": self.b, "new": self.c})
        self.assertEqual(self.chosen(), (self.c, [None, self.a, self.b]))
        self.assertEqual(orders.undo(self.p, "narrator"), {"old": self.c, "new": self.b})
        self.assertEqual(orders.undo(self.p, "narrator"), {"old": self.b, "new": self.a})
        self.assertEqual(orders.undo(self.p, "narrator"), {"old": self.a, "new": None})
        self.assertEqual(self.chosen(), (None, []))
        err = self.code(orders.undo, self.p, "narrator")
        self.assertEqual(err.code, "order.history_empty")

    def test_choosing_the_chosen_pushes_nothing(self):
        orders.choose(self.p, "narrator", self.a)
        self.assertEqual(orders.choose(self.p, "narrator", self.a), {"old": self.a, "new": self.a})
        self.assertEqual(self.chosen(), (self.a, [None]))

    def test_undo_to_discarded_refused_and_keeps_stack(self):
        orders.choose(self.p, "narrator", self.a)
        orders.choose(self.p, "narrator", self.b)
        orders.mark(self.p, "narrator", self.a, "discarded")
        self.assertEqual(self.code(orders.undo, self.p, "narrator").code, "order.undo_discarded")
        self.assertEqual(self.chosen(), (self.b, [None, self.a]))

    def test_unknown_attempt_does_not_change_stack(self):
        orders.choose(self.p, "narrator", self.a)
        self.assertEqual(self.code(orders.choose, self.p, "narrator", 42).code, "order.attempt_unknown")
        self.assertEqual(self.chosen(), (self.a, [None]))


class PrintTests(Base):
    def test_missing_prints_per_model(self):
        orders.submit(self.p, self.voice())
        n = self.take()
        self.assertEqual(orders.missing_prints(self.p, "narrator", n), ["0.6b-base", "1.7b-base"])
        att = orders.get(self.p, "narrator")["attempts"][0]
        spk, rvq = orders.print_paths(self.p, "narrator", att, "0.6b-base")
        self.assertEqual(spk, self.tmp / "data/projects/world/orders/narrator/@/attempts/1/prints/0.6b-base.spk")
        self.assertEqual(rvq.name, "0.6b-base.rvq")
        spk.parent.mkdir(parents=True)
        spk.write_bytes(b"x")  # only one of the two files: still missing
        self.assertEqual(orders.missing_prints(self.p, "narrator", n), ["0.6b-base", "1.7b-base"])
        rvq.write_bytes(b"x")
        self.assertEqual(orders.missing_prints(self.p, "narrator", n), ["1.7b-base"])
        for ext in ("spk", "rvq"):
            (spk.parent / ("1.7b-base." + ext)).write_bytes(b"x")
        self.assertEqual(orders.missing_prints(self.p, "narrator", n), [])

    def test_uses_the_project_print_models(self):
        cfg = json.loads((self.tmp / "world" / projects.CONFIG_FILE).read_text())
        cfg["printModels"] = ["1.7b-base"]
        (self.tmp / "world" / projects.CONFIG_FILE).write_text(json.dumps(cfg))
        orders.submit(self.p, self.voice())
        self.assertEqual(orders.missing_prints(self.p, "narrator", self.take()), ["1.7b-base"])

    def test_missing_prints_only_for_voice(self):
        self.fixed_voice()
        orders.submit(self.p, self.line())
        n = self.made_line()
        err = self.code(orders.missing_prints, self.p, "narrator/intro-01", n)
        self.assertEqual((err.code, err.params["expected"]), ("order.wrong_type", "voice"))

    def test_set_prints_records_metadata(self):
        orders.submit(self.p, self.voice())
        n = self.take()
        res = engine.EngineResult(duration_ms=9, engine_version="fake-1", device="cpu", engine_commit="c1")
        att = orders.set_prints(self.p, "narrator", n, "1.7b-base", res)
        meta = att["prints"]["1.7b-base"]
        self.assertEqual((meta["device"], meta["engineVersion"], meta["engineCommit"], meta["durationMs"]),
                         ("cpu", "fake-1", "c1", 9))
        self.assertEqual(list(orders.get(self.p, "narrator")["attempts"][0]["prints"]), ["1.7b-base"])

    def test_bad_model_and_traversal(self):
        orders.submit(self.p, self.voice())
        n = self.take()
        err = self.code(orders.set_prints, self.p, "narrator", n, "../x")
        self.assertEqual(err.code, "order.print_model")
        att = orders.get(self.p, "narrator")["attempts"][0]
        self.assertEqual(self.code(orders.print_paths, self.p, "narrator", att, "9b").code, "order.print_model")

    def test_undo_keeps_prints_of_the_previous_reference(self):
        """Undo goes back to a reference whose prints are still there: nothing to redo."""
        orders.submit(self.p, self.voice())
        a, b = self.take(seed=1), self.take(seed=2)
        orders.choose(self.p, "narrator", a)
        att = orders.get(self.p, "narrator")["attempts"][0]
        for m in ("0.6b-base", "1.7b-base"):
            for path in orders.print_paths(self.p, "narrator", att, m):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
        orders.choose(self.p, "narrator", b)
        self.assertEqual(orders.missing_prints(self.p, "narrator", b), ["0.6b-base", "1.7b-base"])
        orders.undo(self.p, "narrator")
        self.assertEqual(orders.missing_prints(self.p, "narrator", a), [])


class StaleTests(Base):
    def setUp(self):
        super().setUp()
        self.ref1 = self.fixed_voice()
        orders.submit(self.p, self.line())
        orders.submit(self.p, self.line(key="narrator/intro-02", text="Second."))
        orders.submit(self.p, self.line(key="narrator/intro-03", text="Third."))

    def test_not_stale_while_reference_is_the_same(self):
        n = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n)
        self.assertEqual(orders.get(self.p, "narrator/intro-01")["attempts"][0]["reference"], self.ref1)
        self.assertFalse(orders.is_stale(self.p, "narrator/intro-01"))
        self.assertEqual(orders.stale_lines(self.p, "narrator"), [])

    def test_no_chosen_is_not_stale(self):
        self.made_line()
        self.assertFalse(orders.is_stale(self.p, "narrator/intro-01"))

    def test_stale_after_voice_reference_changes(self):
        n1 = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n1)
        n2 = self.made_line("narrator/intro-02")
        orders.choose(self.p, "narrator/intro-02", n2)
        self.made_line("narrator/intro-03")  # made, never chosen
        new_ref = self.take(seed=9)
        orders.choose(self.p, "narrator", new_ref)
        self.assertTrue(orders.is_stale(self.p, "narrator/intro-01"))
        self.assertEqual(orders.stale_lines(self.p, "narrator"), ["narrator/intro-01", "narrator/intro-02"])
        # the stored line is untouched: it is computed, not saved
        self.assertNotIn("stale", orders.get(self.p, "narrator/intro-01"))
        # a new attempt made with the new reference, once chosen, is current
        fresh = self.made_line()
        self.assertEqual(orders.get(self.p, "narrator/intro-01")["attempts"][1]["reference"], new_ref)
        orders.choose(self.p, "narrator/intro-01", fresh)
        self.assertFalse(orders.is_stale(self.p, "narrator/intro-01"))
        self.assertEqual(orders.stale_lines(self.p, "narrator"), ["narrator/intro-02"])

    def test_back_to_old_reference_by_undo_is_current_again(self):
        n1 = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n1)
        orders.choose(self.p, "narrator", self.take(seed=9))
        self.assertTrue(orders.is_stale(self.p, "narrator/intro-01"))
        orders.undo(self.p, "narrator")
        self.assertFalse(orders.is_stale(self.p, "narrator/intro-01"))

    def test_voice_chosen_pointing_to_a_missing_attempt_makes_lines_stale_without_error(self):
        n1 = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n1)
        orders._modify(self.p, "narrator", lambda rec: rec.update(chosen=999))
        self.assertTrue(orders.is_stale(self.p, "narrator/intro-01"))
        self.assertEqual(orders.stale_lines(self.p, "narrator"), ["narrator/intro-01"])

    def test_voice_unfixed_makes_chosen_lines_stale(self):
        n1 = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n1)
        orders.undo(self.p, "narrator")
        self.assertIsNone(orders.reference(self.p, "narrator"))
        self.assertTrue(orders.is_stale(self.p, "narrator/intro-01"))

    def test_other_voices_lines_are_not_listed(self):
        orders.submit(self.p, self.voice(key="orc"))
        orc = self.take("orc", seed=4)
        orders.choose(self.p, "orc", orc)
        orders.submit(self.p, self.line(key="orc/grunt", voice="orc", text="Grr."))
        spec = orders.attempt_specs(self.p, "orc/grunt")[0]
        spec["result"] = {"audio_ms": 100}
        orders.choose(self.p, "orc/grunt", orders.add_attempt(self.p, "orc/grunt", spec))
        orders.choose(self.p, "narrator", self.take(seed=9))
        self.assertEqual(orders.stale_lines(self.p, "narrator"), [])
        self.assertEqual(orders.stale_lines(self.p, "orc"), [])

    def test_is_stale_only_for_lines(self):
        err = self.code(orders.is_stale, self.p, "narrator")
        self.assertEqual((err.code, err.params["expected"]), ("order.wrong_type", "line"))
        self.assertEqual(self.code(orders.reference, self.p, "narrator/intro-01").code, "order.voice_unknown")

    def test_voice_locale_change_with_the_same_take_leaves_lines_current(self):
        # lines are spoken with the locale of their reference take: regenerating them would give the same, so
        # marking them stale would leave them stale forever (they stay current until another take is chosen)
        n = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n)
        orders.submit(self.p, self.voice(locale="es-ES"))  # same reference take, another language
        self.assertFalse(orders.is_stale(self.p, "narrator/intro-01"))
        self.assertEqual(orders.stale_lines(self.p, "narrator"), [])

    def test_line_take_in_another_locale_than_its_reference_is_stale(self):
        n = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n)
        orders._modify(self.p, "narrator/intro-01",  # e.g. a take edited by hand or from another version
                       lambda o: o["attempts"][0].__setitem__("locale", "es-419"))
        self.assertTrue(orders.is_stale(self.p, "narrator/intro-01"))
        self.assertEqual(orders.stale_lines(self.p, "narrator"), ["narrator/intro-01"])

    def test_old_take_without_locale_matches_a_voice_without_it(self):
        n = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n)
        self.assertNotIn("locale", orders.get(self.p, "narrator/intro-01")["attempts"][0])
        self.assertFalse(orders.is_stale(self.p, "narrator/intro-01"))

    def test_resubmitted_with_another_voice_is_stale_even_with_the_same_take_id(self):
        n1 = self.made_line()
        orders.choose(self.p, "narrator/intro-01", n1)
        orders.submit(self.p, self.voice(key="orc"))
        orc_take = self.take("orc", seed=4)
        self.assertEqual(orc_take, self.ref1)  # same take id, other voice
        orders.choose(self.p, "orc", orc_take)
        self.assertFalse(orders.is_stale(self.p, "narrator/intro-01"))
        orders.submit(self.p, self.line(voice="orc"))
        self.assertTrue(orders.is_stale(self.p, "narrator/intro-01"))
        self.assertEqual(orders.stale_lines(self.p, "orc"), ["narrator/intro-01"])
        self.assertEqual(orders.stale_lines(self.p, "narrator"), [])
        self.assertEqual(orders.get(self.p, "narrator/intro-01")["attempts"][0]["voice"], "narrator")

    def test_attempt_reference_is_checked_against_the_specs_voice(self):
        orders.submit(self.p, self.voice(key="orc"))
        orc_take = self.take("orc", seed=4)
        orders.choose(self.p, "orc", orc_take)
        self.take("orc", seed=5)  # take 2 exists only in orc
        orders.submit(self.p, self.line(voice="orc"))
        spec = {"seed": 1, "text": "x", "voice": "narrator", "reference": 2}
        err = self.code(orders.add_attempt, self.p, "narrator/intro-01", spec)
        self.assertEqual((err.code, err.params["voice"]), ("order.reference_unknown", "narrator"))
        spec["reference"] = self.ref1
        attempt_id = orders.add_attempt(self.p, "narrator/intro-01", spec)
        self.assertEqual(orders.get(self.p, "narrator/intro-01")["attempts"][attempt_id - 1]["voice"], "narrator")

    def test_attempt_specs_of_a_line_carry_its_voice(self):
        spec, = orders.attempt_specs(self.p, "narrator/intro-01")
        self.assertEqual((spec["voice"], spec["reference"]), ("narrator", self.ref1))


class SchemaDataTests(Base):
    def test_limits_come_from_the_schema(self):
        import importlib
        from gvoice import schema
        common = schema.load_schema("common")["$defs"]
        self.assertEqual(orders.SEED_LIMIT, common["seed"]["maximum"] + 1)
        self.assertEqual(list(projects.DEFAULT_PRINT_MODELS), common["baseModel"]["enum"])
        # a changed schema changes the constants: they are read from it, not copied
        changed = schema.load_schema("common")
        changed["$defs"]["seed"]["maximum"] = 99
        changed["$defs"]["baseModel"]["enum"] = ["x-base"]
        self.addCleanup(importlib.reload, projects)
        self.addCleanup(importlib.reload, orders)
        with mock.patch.object(schema, "load_schema", return_value=changed):
            importlib.reload(orders)
            importlib.reload(projects)
            self.assertEqual(orders.SEED_LIMIT, 100)
            self.assertEqual(projects.DEFAULT_PRINT_MODELS, ("x-base",))

    def test_check_count(self):
        for bad in (0, 51, True, "2"):
            self.assertEqual(self.code(orders.check_count, bad).code, "order.count_invalid")
        err = self.code(orders.check_count, 2, orders.SEED_LIMIT - 1)
        self.assertEqual(err.code, "order.seed_range")
        orders.check_count(1, orders.SEED_LIMIT - 1)


if __name__ == "__main__":
    unittest.main()

# Copiado de gimg@0d02f51 (D7); cambia: tipos voice y line con (project, type, key), sin perfil ni imágenes, audio .wav,
# model y count, y casos nuevos (voz y modelo del proyecto, clave reservada, mismo key en los dos tipos).
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import orders, paths, projects
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "galivelop-voices.json").read_text())
SHEET = {"gender": "male", "age": "adult", "pitch": "low"}


class OrderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {
            "GVOICE_CONFIG_HOME": str(self.tmp / "cfg"), "GVOICE_DATA_HOME": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = self.tmp / "proj"
        root.mkdir()
        self.cfg = copy.deepcopy(EXAMPLE)
        self.cfg.pop("$schema", None)
        self.cfg["name"] = "proj"
        self.cfg["voices"]["a/b"] = {}
        self.cfg["printModels"] = ["1.7b-base", "0.6b-base"]
        self.write_cfg()
        projects.add(root)

    def write_cfg(self):
        (self.tmp / "proj" / "galivelop-voices.json").write_text(json.dumps(self.cfg))

    def vorder(self, **changes):
        data = {"key": "narrator", "type": "voice", "testText": "Hello there.", "designSheet": dict(SHEET)}
        data.update(changes)
        return data

    def lorder(self, **changes):
        data = {"key": "narrator/intro", "type": "line", "voice": "narrator", "text": "Long ago."}
        data.update(changes)
        return data

    def code(self, fn, *args, **kwargs):
        with self.assertRaises(GvoiceError) as cm:
            fn(*args, **kwargs)
        return cm.exception.code

    def vspec(self, n=1, **extra):
        spec = {"seed": n, "instruct": "A voice.", "testText": "t%d" % n, "model": "design-1", "device": "cpu"}
        spec.update(extra)
        return spec

    def lspec(self, n=1, **extra):
        spec = {"seed": n, "text": "x%d" % n, "model": "1.7b-base", "device": "Vulkan0", "voiceReference": 1}
        spec.update(extra)
        return spec

    def new_voice(self, attempts=0, **changes):
        orders.submit("proj", self.vorder(**changes))
        for n in range(1, attempts + 1):
            orders.add_attempt("proj", "voice", changes.get("key", "narrator"), self.vspec(n))

    def new_line(self, attempts=0, **changes):
        orders.submit("proj", self.lorder(**changes))
        for n in range(1, attempts + 1):
            orders.add_attempt("proj", "line", changes.get("key", "narrator/intro"), self.lspec(n))

    # storage and submit
    def test_create_and_paths(self):
        rec = orders.submit("proj", self.vorder(seed=5, count=3))
        self.assertEqual((rec["chosen"], rec["chosenHistory"], rec["attempts"], rec["type"]), (None, [], [], "voice"))
        self.assertEqual((rec["seed"], rec["testText"], rec["designSheet"]), (5, "Hello there.", SHEET))
        self.assertNotIn("count", rec)
        self.assertRegex(rec["createdAt"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        f = self.tmp / "data" / "projects" / "proj" / "orders" / "voice" / "narrator" / "order.json"
        self.assertTrue(f.is_file())
        self.assertEqual(orders.get("proj", "voice", "narrator"), rec)
        att = {"audio": "attempts/3.wav"}
        self.assertEqual(orders.attempt_audio("proj", "voice", "narrator", att), f.parent / "attempts" / "3.wav")
        self.assertEqual(orders.pending_audio_path("proj", "voice", "narrator", 4),
                         f.parent / "attempts" / ".pending-4.wav")
        self.assertEqual(orders.entry_audio_name(4), "attempts/q4.wav")

    def test_line_record_has_model_and_voice(self):
        rec = orders.submit("proj", self.lorder(model="0.6b-base"))
        self.assertEqual((rec["voice"], rec["text"], rec["model"], rec["seed"]),
                         ("narrator", "Long ago.", "0.6b-base", None))
        self.assertNotIn("designSheet", rec)
        self.assertIsNone(orders.submit("proj", self.lorder())["model"])  # resolved when attempts are made

    def test_resubmit_keeps_attempts_and_updates(self):
        self.new_line(attempts=2, seed=1)
        orders.choose("proj", "line", "narrator/intro", 2)
        first = orders.get("proj", "line", "narrator/intro")
        rec = orders.submit("proj", self.lorder(text="Other.", model="0.6b-base"))
        self.assertEqual((rec["text"], rec["model"], rec["seed"]), ("Other.", "0.6b-base", None))
        self.assertEqual(rec["attempts"], first["attempts"])
        self.assertEqual((rec["chosen"], rec["chosenHistory"]), (2, [None]))
        self.assertEqual(rec["createdAt"], first["createdAt"])

    def test_resubmit_voice_keeps_attempts(self):
        self.new_voice(attempts=1, seed=3)
        orders.choose("proj", "voice", "narrator", 1)
        rec = orders.submit("proj", self.vorder(testText="New.", designSheet={"age": "old adult"}))
        self.assertEqual((rec["testText"], rec["designSheet"], rec["seed"]), ("New.", {"age": "old adult"}, None))
        self.assertEqual((len(rec["attempts"]), rec["chosen"]), (1, 1))

    def test_resubmit_with_other_type_is_another_order(self):
        # the same key under the other type neither replaces nor reads the first one
        self.new_voice(attempts=1)
        orders.submit("proj", self.lorder(key="narrator"))
        self.assertEqual(len(orders.get("proj", "voice", "narrator")["attempts"]), 1)
        self.assertEqual(orders.get("proj", "line", "narrator")["attempts"], [])
        self.assertEqual([(o["type"], o["key"]) for o in orders.list_orders("proj")],
                         [("line", "narrator"), ("voice", "narrator")])
        self.assertEqual(self.code(orders.get, "proj", "line", "orc"), "order.unknown")

    def test_resubmit_cannot_switch_the_type_of_a_stored_order(self):
        self.new_voice()
        file = paths.data_dir() / "projects/proj/orders/voice/narrator/order.json"
        data = json.loads(file.read_text())
        file.write_text(json.dumps(dict(data, type="line")))  # folder says voice, record says line
        self.assertEqual(self.code(orders.get, "proj", "voice", "narrator"), "order.corrupt")
        self.assertEqual(self.code(orders.submit, "proj", self.vorder()), "order.corrupt")
        self.assertEqual(self.code(orders.list_orders, "proj"), "order.corrupt")

    def test_slash_keys(self):
        self.new_voice(key="a/b")
        orders.submit("proj", self.lorder(key="a/b", voice="a/b"))
        self.assertTrue((paths.data_dir() / "projects/proj/orders/voice/a/b/order.json").is_file())
        self.assertEqual(orders.get("proj", "line", "a/b")["voice"], "a/b")

    def test_nested_keys_do_not_collide(self):
        orders.submit("proj", self.lorder(key="x"))
        orders.submit("proj", self.lorder(key="x/y", text="inner"))
        self.assertEqual(orders.get("proj", "line", "x")["text"], "Long ago.")
        self.assertEqual(orders.get("proj", "line", "x/y")["text"], "inner")

    def test_reserved_attempts_segment(self):
        for key in ("x/attempts", "x/attempts/y"):
            err = self.code(orders.submit, "proj", self.lorder(key=key))
            self.assertEqual(err, "order.key_reserved", key)
        self.assertEqual(orders.submit("proj", self.lorder(key="attempts"))["key"], "attempts")

    def test_bad_keys_everywhere(self):
        self.new_voice(attempts=1)
        for key in ("a//b", "a/./b", "../x", "/a", "A B", "a/", "x" * 101, "", 5):
            for fn, args in [(orders.get, ()), (orders.choose, (1,)), (orders.pending_audio_path, (1,)),
                             (orders.attempt_for_entry, (1,)), (orders.attempt_audio, ({"audio": "attempts/1.wav"},)),
                             (orders.mark, (1, "new")), (orders.note, (1, "x")), (orders.undo, ()),
                             (orders.add_attempt, (self.vspec(),)), (orders.attempt_specs, ())]:
                self.assertEqual(self.code(fn, "proj", "voice", key, *args), "order.invalid", (fn, key))
        self.assertEqual(self.code(orders.submit, "proj", self.lorder(key="../x")), "order.invalid")

    def test_bad_type(self):
        for bad in ("sound", "", None, "Voice"):
            self.assertEqual(self.code(orders.get, "proj", bad, "narrator"), "order.type_invalid", bad)
            self.assertEqual(self.code(orders.list_orders, "proj", bad), "order.type_invalid") if bad else None
        self.assertEqual(self.code(orders.submit, "proj", self.lorder(type="sound")), "order.invalid")

    def test_bad_project_name_in_paths(self):
        for bad in (".", "..", "a/b", "A"):
            self.assertEqual(self.code(orders.pending_audio_path, bad, "voice", "narrator", 1),
                             "project.bad_name", bad)

    def test_submit_failures(self):
        self.assertEqual(self.code(orders.submit, "proj", {"key": "a"}), "order.invalid")
        self.assertEqual(self.code(orders.submit, "proj", self.lorder(text="")), "order.invalid")
        self.assertEqual(self.code(orders.submit, "proj", self.vorder(count=0)), "order.invalid")
        self.assertEqual(self.code(orders.submit, "proj", self.vorder(model="1.7b-base")), "order.invalid")
        self.assertEqual(self.code(orders.submit, "nope", self.vorder()), "project.unknown")
        err = None
        try:
            orders.submit("proj", self.vorder(seed=-1))
        except GvoiceError as exc:
            err = exc
        self.assertTrue(err.errors)

    def test_unknown_voice(self):
        for order in (self.vorder(key="ghost"), self.lorder(voice="ghost")):
            with self.assertRaises(GvoiceError) as cm:
                orders.submit("proj", order)
            self.assertEqual((cm.exception.code, cm.exception.params.get("voice")), ("order.unknown_voice", "ghost"))
        self.assertFalse((paths.data_dir() / "projects/proj/orders").exists())

    def test_model_outside_print_models(self):
        self.cfg["printModels"] = ["0.6b-base"]
        self.write_cfg()
        with self.assertRaises(GvoiceError) as cm:
            orders.submit("proj", self.lorder(model="1.7b-base"))
        self.assertEqual((cm.exception.code, cm.exception.params), (
            "order.model_not_allowed", {"model": "1.7b-base", "allowed": "0.6b-base"}))
        self.assertEqual(orders.submit("proj", self.lorder(model="0.6b-base"))["model"], "0.6b-base")
        self.assertEqual(self.code(orders.submit, "proj", self.lorder(model="9b-base")), "order.invalid")

    def test_model_default_is_first_print_model_or_first_base(self):
        self.new_line(seed=1)
        self.assertEqual(orders.attempt_specs("proj", "line", "narrator/intro")[0]["model"], "1.7b-base")
        del self.cfg["printModels"]
        self.write_cfg()
        self.assertEqual(orders.attempt_specs("proj", "line", "narrator/intro")[0]["model"], "0.6b-base")

    # attempt specs
    def test_seeds_from_order_seed(self):
        self.new_voice(seed=10)
        seeds = lambda *a, **k: [s["seed"] for s in orders.attempt_specs("proj", "voice", "narrator", *a, **k)]
        self.assertEqual(seeds(3), [10, 11, 12])
        self.assertEqual(seeds(2, seed=100), [100, 101])
        self.assertEqual(seeds(), [10])

    def test_seed_zero_is_a_seed(self):
        self.new_voice(seed=0)
        self.assertEqual([s["seed"] for s in orders.attempt_specs("proj", "voice", "narrator", 2)], [0, 1])

    def test_random_seeds_without_seed(self):
        self.new_line()
        seeds = [s["seed"] for s in orders.attempt_specs("proj", "line", "narrator/intro", 20)]
        self.assertEqual(len(seeds), 20)
        self.assertTrue(all(0 <= s < 2 ** 32 for s in seeds))
        self.assertGreater(len(set(seeds)), 1)

    def test_spec_content_per_type(self):
        self.new_voice(seed=1)
        self.assertEqual(orders.attempt_specs("proj", "voice", "narrator")[0], {
            "seed": 1, "instruct": "A voice with gender: male; age: adult; pitch: low.", "testText": "Hello there."})
        self.new_line(seed=2, model="0.6b-base")
        self.assertEqual(orders.attempt_specs("proj", "line", "narrator/intro")[0], {
            "seed": 2, "text": "Long ago.", "model": "0.6b-base", "voice": "narrator"})

    def test_specs_do_not_change_the_order(self):
        self.new_voice(seed=3)
        before = orders.get("proj", "voice", "narrator")
        orders.attempt_specs("proj", "voice", "narrator", 5, seed=9)
        self.assertEqual(orders.get("proj", "voice", "narrator"), before)

    def test_count_out_of_range(self):
        self.new_voice()
        for bad in (0, 21, -1, True, "2", 1.5, None):
            with self.assertRaises(GvoiceError) as cm:
                orders.attempt_specs("proj", "voice", "narrator", bad)
            self.assertEqual((cm.exception.code, cm.exception.params), ("order.count_invalid", {"min": 1, "max": 20}), bad)
        self.assertEqual(len(orders.attempt_specs("proj", "voice", "narrator", 20)), 20)
        self.assertEqual(len(orders.attempt_specs("proj", "voice", "narrator", 1)), 1)

    def test_spec_failures(self):
        self.new_voice()
        f = orders.attempt_specs
        self.assertEqual(self.code(f, "proj", "voice", "narrator", 1, seed=-1), "order.invalid")
        self.assertEqual(self.code(f, "proj", "voice", "zz"), "order.unknown")
        self.assertEqual(self.code(f, "nope", "voice", "narrator"), "project.unknown")

    def test_specs_check_the_project_again(self):
        self.new_line()
        self.cfg["voices"].pop("narrator")
        self.write_cfg()
        self.assertEqual(self.code(orders.attempt_specs, "proj", "line", "narrator/intro"), "order.unknown_voice")
        self.cfg["voices"]["narrator"] = {}
        self.cfg["printModels"] = ["0.6b-base"]
        self.write_cfg()
        orders.submit("proj", self.lorder(model="0.6b-base"))
        self.cfg["printModels"] = ["1.7b-base"]
        self.write_cfg()
        self.assertEqual(self.code(orders.attempt_specs, "proj", "line", "narrator/intro"), "order.model_not_allowed")

    # attempts, states, notes
    def test_add_voice_attempt(self):
        self.new_voice()
        ids = [orders.add_attempt("proj", "voice", "narrator", self.vspec(n)) for n in (1, 2, 3)]
        self.assertEqual(ids, [1, 2, 3])
        att = orders.get("proj", "voice", "narrator")["attempts"][1]
        self.assertEqual(att["audio"], "attempts/2.wav")
        self.assertEqual({k: v for k, v in att.items() if k != "createdAt"}, {
            "id": 2, "state": "new", "seed": 2, "instruct": "A voice.", "testText": "t2", "model": "design-1",
            "device": "cpu", "audio": "attempts/2.wav", "note": ""})
        self.assertRegex(att["createdAt"], r"^\d{4}-")

    def test_add_line_attempt(self):
        self.new_line()
        orders.add_attempt("proj", "line", "narrator/intro", self.lspec(engine="fake", engineVersion="1"))
        att = orders.get("proj", "line", "narrator/intro")["attempts"][0]
        self.assertEqual((att["voiceReference"], att["text"], att["model"], att["device"]), (1, "x1", "1.7b-base", "Vulkan0"))
        self.assertEqual((att["engine"], att["engineVersion"]), ("fake", "1"))
        self.assertNotIn("instruct", att)

    def test_add_attempt_failures(self):
        self.new_voice()
        self.new_line()
        add = orders.add_attempt
        self.assertEqual(self.code(add, "proj", "voice", "narrator", {"seed": 1}), "order.spec_invalid")
        self.assertEqual(self.code(add, "proj", "voice", "narrator", self.lspec()), "order.spec_invalid")
        self.assertEqual(self.code(add, "proj", "line", "narrator/intro", self.vspec()), "order.spec_invalid")
        no_ref = self.lspec()
        del no_ref["voiceReference"]
        with self.assertRaises(GvoiceError) as cm:
            add("proj", "line", "narrator/intro", no_ref)
        self.assertEqual((cm.exception.code, cm.exception.params), ("order.spec_invalid", {"missing": "voiceReference"}))
        self.assertEqual(self.code(add, "proj", "voice", "zz", self.vspec()), "order.unknown")
        self.assertEqual(self.code(add, "proj", "voice", "narrator", "x"), "order.spec_invalid")
        for bad in ({"seed": "1"}, {"seed": -1}, {"seed": 2 ** 32}, {"instruct": ""}, {"testText": 3},
                    {"model": ""}, {"device": "GPU 0"}, {"device": 1}):
            self.assertEqual(self.code(add, "proj", "voice", "narrator", self.vspec(**bad)), "order.invalid", bad)
        for bad in ({"voiceReference": 0}, {"voiceReference": True}, {"voiceReference": "1"}, {"text": ""},
                    {"model": "9b-base"}):
            self.assertEqual(self.code(add, "proj", "line", "narrator/intro", self.lspec(**bad)), "order.invalid", bad)
        self.cfg["printModels"] = ["0.6b-base"]
        self.write_cfg()
        self.assertEqual(self.code(add, "proj", "line", "narrator/intro", self.lspec()), "order.model_not_allowed")
        self.assertEqual(orders.get("proj", "voice", "narrator")["attempts"], [])

    def test_mark_and_note(self):
        self.new_voice(attempts=2)
        m = lambda i, s: orders.mark("proj", "voice", "narrator", i, s)
        self.assertEqual(m(1, "candidate")["state"], "candidate")
        self.assertEqual(m(1, "discarded")["state"], "discarded")
        self.assertEqual(m(1, "new")["state"], "new")
        self.assertEqual(orders.note("proj", "voice", "narrator", 2, "nice")["note"], "nice")
        self.assertEqual(orders.get("proj", "voice", "narrator")["attempts"][1]["note"], "nice")
        self.assertEqual(orders.note("proj", "voice", "narrator", 2, "")["note"], "")
        self.assertEqual(self.code(m, 1, "bogus"), "order.state_invalid")
        self.assertEqual(self.code(m, 9, "new"), "order.attempt_unknown")
        self.assertEqual(self.code(orders.note, "proj", "voice", "narrator", 9, "x"), "order.attempt_unknown")
        self.assertEqual(self.code(orders.note, "proj", "voice", "narrator", 1, 5), "order.note_invalid")

    def test_cannot_discard_chosen_nor_choose_discarded(self):
        self.new_line(attempts=2)
        k = "narrator/intro"
        orders.mark("proj", "line", k, 2, "discarded")
        self.assertEqual(self.code(orders.choose, "proj", "line", k, 2), "order.choose_discarded")
        orders.choose("proj", "line", k, 1)
        self.assertEqual(self.code(orders.mark, "proj", "line", k, 1, "discarded"), "order.discard_chosen")
        self.assertEqual(orders.mark("proj", "line", k, 1, "candidate")["state"], "candidate")
        orders.undo("proj", "line", k)
        self.assertEqual(orders.mark("proj", "line", k, 1, "discarded")["state"], "discarded")

    # choose and undo
    def test_choose_undo_stack(self):
        self.new_voice(attempts=3)
        c = lambda i: orders.choose("proj", "voice", "narrator", i)
        self.assertEqual(c(1), {"old": None, "new": 1})
        self.assertEqual(c(3), {"old": 1, "new": 3})
        self.assertEqual(c(3), {"old": 3, "new": 3})  # no push when unchanged
        rec = orders.get("proj", "voice", "narrator")
        self.assertEqual((rec["chosen"], rec["chosenHistory"]), (3, [None, 1]))
        self.assertEqual(orders.undo("proj", "voice", "narrator"), {"old": 3, "new": 1})
        self.assertEqual(orders.undo("proj", "voice", "narrator"), {"old": 1, "new": None})
        rec = orders.get("proj", "voice", "narrator")
        self.assertEqual((rec["chosen"], rec["chosenHistory"]), (None, []))
        self.assertEqual(self.code(c, 9), "order.attempt_unknown")
        self.assertEqual(self.code(orders.undo, "proj", "voice", "zz"), "order.unknown")

    def test_undo_with_empty_stack(self):
        self.new_voice(attempts=1)
        with self.assertRaises(GvoiceError) as cm:
            orders.undo("proj", "voice", "narrator")
        self.assertEqual((cm.exception.code, cm.exception.params), (
            "order.history_empty", {"order": "narrator", "type": "voice"}))

    def test_undo_rejects_discarded(self):
        self.new_voice(attempts=2)
        orders.choose("proj", "voice", "narrator", 1)
        orders.choose("proj", "voice", "narrator", 2)
        orders.mark("proj", "voice", "narrator", 1, "discarded")
        before = orders.get("proj", "voice", "narrator")
        with self.assertRaises(GvoiceError) as cm:
            orders.undo("proj", "voice", "narrator")
        self.assertEqual((cm.exception.code, cm.exception.params), ("order.undo_discarded", {"attempt": 1}))
        self.assertEqual(orders.get("proj", "voice", "narrator"), before)
        orders.mark("proj", "voice", "narrator", 1, "candidate")
        self.assertEqual(orders.undo("proj", "voice", "narrator"), {"old": 2, "new": 1})

    def test_undo_to_null_allowed_even_if_all_discarded(self):
        self.new_voice(attempts=1)
        orders.choose("proj", "voice", "narrator", 1)
        self.assertEqual(orders.undo("proj", "voice", "narrator"), {"old": 1, "new": None})

    def test_bool_is_not_attempt_id(self):
        self.new_voice(attempts=1)
        self.assertEqual(self.code(orders.choose, "proj", "voice", "narrator", True), "order.attempt_unknown")

    # entries
    def test_add_attempt_for_entry_is_idempotent(self):
        self.new_voice()
        add = lambda n, **kw: orders.add_attempt("proj", "voice", "narrator", self.vspec(n), **kw)
        first, again, other, plain = add(1, entry_id=7), add(1, entry_id=7), add(2, entry_id=8), add(3)
        self.assertEqual((first, again, other, plain), (1, 1, 2, 3))
        attempts = orders.get("proj", "voice", "narrator")["attempts"]
        self.assertEqual([(a["audio"], a.get("queueEntry")) for a in attempts],
                         [("attempts/q7.wav", 7), ("attempts/q8.wav", 8), ("attempts/3.wav", None)])
        self.assertEqual(orders.attempt_for_entry("proj", "voice", "narrator", 8)["id"], 2)
        self.assertIsNone(orders.attempt_for_entry("proj", "voice", "narrator", 9))
        folder = orders.pending_audio_path("proj", "voice", "narrator", 7).parent
        self.assertEqual(orders.attempt_audio("proj", "voice", "narrator", attempts[0]), folder / "q7.wav")
        for bad in (0, -1, True, "7", 1.5):
            self.assertEqual(self.code(add, 4, entry_id=bad), "order.spec_invalid", bad)

    def test_attempt_audio_stays_inside_order_folder(self):
        self.new_voice()
        for audio in ("../order.json", "/etc/x", "attempts/../../x"):
            self.assertIn(self.code(orders.attempt_audio, "proj", "voice", "narrator", {"audio": audio}),
                          ("path.dotdot", "path.absolute", "path.outside"), audio)

    # listing
    def test_list_orders_filters(self):
        self.new_voice(attempts=1, key="orc")
        self.new_voice()
        self.new_line(key="narrator/b")
        self.new_line(key="narrator/a")
        orders.choose("proj", "voice", "orc", 1)
        keys = lambda **kw: [(o["type"], o["key"]) for o in orders.list_orders("proj", **kw)]
        self.assertEqual(keys(), [("line", "narrator/a"), ("line", "narrator/b"), ("voice", "narrator"), ("voice", "orc")])
        self.assertEqual(keys(type_="line"), [("line", "narrator/a"), ("line", "narrator/b")])
        self.assertEqual(keys(chosen=True), [("voice", "orc")])
        self.assertEqual(keys(chosen=False, type_="voice"), [("voice", "narrator")])
        self.assertEqual(self.code(orders.list_orders, "nope"), "project.unknown")

    def test_list_empty_project(self):
        self.assertEqual(orders.list_orders("proj"), [])

    def test_corrupt_order(self):
        self.new_voice()
        file = paths.data_dir() / "projects/proj/orders/voice/narrator/order.json"
        file.write_text("{nope")
        self.assertEqual(self.code(orders.get, "proj", "voice", "narrator"), "order.corrupt")
        good = {"key": "narrator", "type": "voice", "attempts": [], "chosen": None, "chosenHistory": []}
        for bad in ({k: v for k, v in good.items() if k != "type"}, {k: v for k, v in good.items() if k != "chosen"},
                    dict(good, attempts="x"), dict(good, key="orc")):
            file.write_text(json.dumps(bad))
            self.assertEqual(self.code(orders.list_orders, "proj"), "order.corrupt")

    def test_messages_in_both_languages(self):
        self.new_voice(attempts=2)
        orders.choose("proj", "voice", "narrator", 1)
        calls = [(orders.undo, ("proj", "voice", "zz")), (orders.get, ("proj", "sound", "a")),
                 (orders.submit, ("proj", self.lorder(voice="ghost"))),
                 (orders.attempt_specs, ("proj", "voice", "narrator", 0)),
                 (orders.submit, ("proj", self.lorder(key="a/attempts"))),
                 (orders.submit, ("proj", self.lorder(model="9b-base"))),
                 (orders.mark, ("proj", "voice", "narrator", 1, "discarded")),
                 (orders.mark, ("proj", "voice", "narrator", 1, "x")),
                 (orders.mark, ("proj", "voice", "narrator", 7, "new")),
                 (orders.note, ("proj", "voice", "narrator", 1, 3)),
                 (orders.add_attempt, ("proj", "voice", "narrator", {})),
                 (orders.undo, ("proj", "voice", "orc"))]
        for fn, args in calls:
            for lang in ("es", "en"):
                with self.assertRaises(GvoiceError) as cm:
                    fn(*args)
                self.assertNotIn("error.", cm.exception.message(lang), cm.exception.code)

    def test_more_messages(self):
        self.new_voice(attempts=2)
        orders.mark("proj", "voice", "narrator", 2, "discarded")
        orders.choose("proj", "voice", "narrator", 1)
        orders.undo("proj", "voice", "narrator")
        self.cfg["printModels"] = ["0.6b-base"]
        self.write_cfg()
        for fn, args in [(orders.undo, ("proj", "voice", "narrator")),
                         (orders.choose, ("proj", "voice", "narrator", 2)),
                         (orders.submit, ("proj", self.lorder(model="1.7b-base")))]:
            for lang in ("es", "en"):
                with self.assertRaises(GvoiceError) as cm:
                    fn(*args)
                self.assertNotIn("error.", cm.exception.message(lang), cm.exception.code)


if __name__ == "__main__":
    unittest.main()

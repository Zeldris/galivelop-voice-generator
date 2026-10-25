# Tests de F1.5: `voices` (elegir, deshacer, huellas, estado y la puerta de `line`) y los hallazgos de la revisión
# de F1.4 que cierra (la huella ligada a la referencia actual, el modelo vigente, un solo nombre de archivo).
import json
import unittest

from gvoice import engine, fsutil, orders, projects, queue, voices, worker
from tests.test_worker import StubEngine, WorkerBase

MODELS = ["0.6b-base", "1.7b-base"]


class VoicesBase(WorkerBase):
    def setUp(self):
        super().setUp()
        for _ in range(3):
            self.take()

    def prints_dir(self):
        return self.voice_dir() / "prints"

    def print_names(self):
        folder = self.prints_dir()
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def choose_and_run(self, take_id):
        result = voices.choose("proj", "narrator", take_id)
        worker.run()
        return result

    def set_config(self, **changes):
        path = self.projects["proj"] / "galivelop-voices.json"
        cfg = json.loads(path.read_text())
        cfg.update(changes)
        path.write_text(json.dumps(cfg))

    def new_line(self, key="narrator/intro", text="Long ago."):
        orders.submit("proj", {"key": key, "type": "line", "voice": "narrator", "text": text})

    def speak(self, key="narrator/intro"):
        """Queue and run the line; returns the id of its attempt."""
        specs = orders.attempt_specs("proj", "line", key)
        entry = queue.enqueue_attempts("proj", "line", key, specs)[0]
        worker.run()
        done = queue.get(entry["id"])
        self.assertEqual(done["state"], "done", done["error"])
        return done["attemptId"]


class ChooseTests(VoicesBase):
    def test_choose_copies_the_take_and_queues_a_print_per_model(self):
        result = voices.choose("proj", "narrator", 2)
        self.assertEqual((result["old"], result["new"]), (None, 2))
        self.assertEqual([(e["kind"], e["voice"], e["model"], e["reference"]) for e in result["prints"]],
                         [("print", "narrator", m, 2) for m in MODELS])
        folder = self.voice_dir()
        take = orders.get("proj", "voice", "narrator")["attempts"][1]
        source = orders.attempt_audio("proj", "voice", "narrator", take)
        self.assertEqual((folder / "reference.wav").read_bytes(), source.read_bytes())
        self.assertEqual((folder / "reference.txt").read_text(), "Hello there.")
        self.assertEqual(json.loads((folder / "reference.json").read_text())["reference"], 2)
        self.assertEqual(orders.get("proj", "voice", "narrator")["chosen"], 2)
        self.assertEqual(self.leftovers(), [])

    def test_choose_then_work_leaves_the_prints_up_to_date(self):
        self.choose_and_run(2)
        self.assertEqual(self.print_names(), sorted(m + e for m in MODELS for e in (".json", ".rvq", ".spk")))
        marker = json.loads((self.prints_dir() / "0.6b-base.json").read_text())
        self.assertEqual(marker["reference"], 2)
        self.assertEqual(voices.status("proj", "narrator")["prints"], MODELS)
        self.assertEqual(self.print_names().count("print.json"), 0)  # one name: <model>.json

    def test_the_reference_text_is_the_test_text_of_the_take(self):
        voices.choose("proj", "narrator", 1)
        self.assertEqual((self.voice_dir() / "reference.txt").read_text(), "Hello there.")

    def test_choose_twice_before_the_first_print_runs(self):
        first = voices.choose("proj", "narrator", 1)["prints"]
        second = voices.choose("proj", "narrator", 2)["prints"]
        self.assertEqual({queue.get(e["id"])["state"] for e in first}, {"cancelled"})
        self.assertEqual({queue.get(e["id"])["state"] for e in second}, {"queued"})
        worker.run()
        marker = json.loads((self.prints_dir() / "0.6b-base.json").read_text())
        self.assertEqual(marker["reference"], 2)
        self.assertEqual(voices.status("proj", "narrator")["prints"], MODELS)

    def test_choose_twice_while_the_first_print_is_stale_in_the_queue(self):
        # a print of an old reference that was not cancelled (queued by hand) ends as stale, not as done
        voices.choose("proj", "narrator", 1)
        old = queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        voices.choose("proj", "narrator", 2)
        worker.run()
        entry = queue.get(old["id"])
        self.assertEqual(entry["state"], "cancelled")
        self.assertEqual(voices.status("proj", "narrator")["prints"], MODELS)

    def test_choosing_the_same_take_again_queues_nothing_new_while_pending(self):
        first = voices.choose("proj", "narrator", 1)["prints"]
        again = voices.choose("proj", "narrator", 1)
        self.assertEqual(again["prints"], [])
        self.assertEqual({queue.get(e["id"])["state"] for e in first}, {"queued"})

    def test_choosing_the_same_take_again_repairs_an_interrupted_choose(self):
        self.choose_and_run(1)
        (self.voice_dir() / "reference.wav").unlink()
        (self.voice_dir() / "reference.json").unlink()
        result = voices.choose("proj", "narrator", 1)
        self.assertEqual(result["prints"], [])  # the prints are those of take 1: still up to date
        self.assertTrue((self.voice_dir() / "reference.wav").is_file())

    def test_choosing_a_reference_with_up_to_date_prints_queues_nothing(self):
        self.choose_and_run(1)
        self.assertEqual(voices.choose("proj", "narrator", 1)["prints"], [])

    def test_only_the_print_models_of_the_project(self):
        self.set_config(printModels=["1.7b-base"])
        self.assertEqual([e["model"] for e in voices.choose("proj", "narrator", 1)["prints"]], ["1.7b-base"])

    def test_a_voice_without_a_voice_order(self):
        self.assertEqual(self.code(voices.choose, "proj", "orc", 1), "order.unknown")
        self.assertEqual(self.code(voices.undo, "proj", "orc"), "order.unknown")
        self.assertEqual(self.code(queue.enqueue_print, "proj", "orc", "0.6b-base", 1), "order.unknown")
        self.assertEqual(queue.list_entries(), [])
        self.assertFalse((self.voice_dir("orc")).exists())

    def test_a_voice_not_in_the_project(self):
        self.assertEqual(self.code(voices.choose, "proj", "ghost", 1), "order.unknown_voice")
        self.assertEqual(self.code(voices.status, "proj", "ghost"), "order.unknown_voice")
        self.assertEqual(self.code(voices.choose, "proj", "../x", 1), "order.unknown_voice")

    def test_a_take_that_does_not_exist(self):
        for bad in (99, 0, "1", None, True):
            self.assertEqual(self.code(voices.choose, "proj", "narrator", bad), "order.attempt_unknown", bad)
        self.assertEqual(self.code(queue.enqueue_print, "proj", "narrator", "0.6b-base", 99),
                         "order.attempt_unknown")
        self.assertEqual(orders.get("proj", "voice", "narrator")["chosen"], None)
        self.assertEqual(queue.list_entries(), [])
        self.assertFalse(self.voice_dir().exists())

    def test_a_discarded_take(self):
        orders.mark("proj", "voice", "narrator", 2, "discarded")
        self.assertEqual(self.code(voices.choose, "proj", "narrator", 2), "order.choose_discarded")
        self.assertEqual(queue.list_entries(), [])

    def test_a_take_without_audio_is_refused_and_the_choice_is_not_made(self):
        take = orders.get("proj", "voice", "narrator")["attempts"][1]
        orders.attempt_audio("proj", "voice", "narrator", take).unlink()
        self.assertEqual(self.code(voices.choose, "proj", "narrator", 2), "voice.take_audio_missing")
        self.assertEqual(orders.get("proj", "voice", "narrator")["chosen"], None)
        self.assertEqual(queue.list_entries(), [])


class StaleReferenceTests(VoicesBase):
    """Finding 1 of the F1.4 review: a print is only marked up to date if its reference is still the current one."""

    def test_a_print_of_a_replaced_reference_ends_stale_and_touches_nothing(self):
        self.fix_voice(reference=1)
        before = {p.name: p.read_bytes() for p in self.prints_dir().iterdir()}
        old = queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        self.write_reference(reference=2)  # another take is chosen before the print runs
        worker.run(engine=StubEngine(AssertionError("the engine must not run")))
        entry = queue.get(old["id"])
        self.assertEqual((entry["state"], entry["error"]["code"]), ("cancelled", "voice.print_stale"))
        self.assertIn("ya no es la toma 1", queue.error_text(entry, "es"))
        self.assertIn("is no longer take 1", queue.error_text(entry, "en"))
        self.assertEqual({p.name: p.read_bytes() for p in self.prints_dir().iterdir()}, before)
        self.assertEqual(self.lines()[-1]["app.task"], "print")  # only the first, real print was logged
        self.assertEqual(len(self.lines()), 1)
        self.assertFalse(voices.is_up_to_date("proj", "narrator", "0.6b-base"))  # the old print is not up to date

    def test_the_reference_changes_while_the_engine_runs(self):
        self.write_reference(reference=1)
        entry = queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        test = self

        class Replace(engine.FakeEngine):
            def extract_print(self, job, should_cancel):
                result = super().extract_print(job, should_cancel)
                test.write_reference(reference=2)
                return result

        worker.run(engine=Replace())
        done = queue.get(entry["id"])
        self.assertEqual((done["state"], done["error"]["code"]), ("cancelled", "voice.print_stale"))
        self.assertEqual(self.print_names(), [])  # what the engine wrote is discarded
        self.assertFalse(voices.is_up_to_date("proj", "narrator", "0.6b-base"))

    def test_a_print_with_the_reference_removed(self):
        self.write_reference(reference=1)
        entry = queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        (self.voice_dir() / "reference.json").unlink()
        worker.run(engine=StubEngine(AssertionError("the engine must not run")))
        self.assertEqual(queue.get(entry["id"])["error"]["code"], "voice.print_stale")


class UndoTests(VoicesBase):
    def test_undo_to_the_previous_take(self):
        self.choose_and_run(1)
        self.choose_and_run(2)
        result = voices.undo("proj", "narrator")
        self.assertEqual((result["old"], result["new"]), (2, 1))
        self.assertEqual(json.loads((self.voice_dir() / "reference.json").read_text())["reference"], 1)
        self.assertEqual([e["model"] for e in result["prints"]], MODELS)
        worker.run()
        self.assertEqual(voices.status("proj", "narrator")["prints"], MODELS)

    def test_undo_to_none_removes_the_reference_and_the_prints(self):
        self.choose_and_run(1)
        result = voices.undo("proj", "narrator")
        self.assertEqual((result["old"], result["new"], result["prints"]), (1, None, []))
        self.assertEqual(self.print_names(), [])
        self.assertEqual([p.name for p in self.voice_dir().iterdir() if p.is_file()], ["reference.json.lock"])
        status = voices.status("proj", "narrator")
        self.assertEqual((status["reference"], status["prints"]), (None, []))

    def test_undo_to_none_with_half_the_prints_done(self):
        voices.choose("proj", "narrator", 1)
        worker.run(once=True)  # only the first print
        self.assertEqual(self.print_names(), ["0.6b-base.json", "0.6b-base.rvq", "0.6b-base.spk"])
        voices.undo("proj", "narrator")
        self.assertEqual(self.print_names(), [])
        self.assertEqual([e["state"] for e in queue.list_entries()], ["done", "cancelled"])
        worker.run()
        self.assertEqual(self.print_names(), [])
        self.assertEqual(voices.status("proj", "narrator")["prints"], [])

    def test_undo_to_none_while_a_print_runs(self):
        entry = voices.choose("proj", "narrator", 1)["prints"][0]
        class Undo(engine.FakeEngine):
            def extract_print(self, job, should_cancel):
                result = super().extract_print(job, should_cancel)
                voices.undo("proj", "narrator")
                return result

        worker.run(engine=Undo())
        self.assertIn(queue.get(entry["id"])["state"], ("cancelled",))
        self.assertEqual(self.print_names(), [])
        self.assertIsNone(voices.reference_id("proj", "narrator"))

    def test_choose_and_undo_while_a_print_runs_queues_it_again(self):
        voices.choose("proj", "narrator", 1)

        class ChooseAndUndo(engine.FakeEngine):
            def extract_print(self, job, should_cancel):
                result = super().extract_print(job, should_cancel)
                if not getattr(self, "done", False):
                    self.done = True
                    voices.choose("proj", "narrator", 2)  # asks the running print of 1 to cancel
                    voices.undo("proj", "narrator")  # back to 1: its print must be queued again
                return result

        worker.run(engine=ChooseAndUndo())
        self.assertEqual(voices.reference_id("proj", "narrator"), 1)
        for model in projects.print_models(projects.get("proj")["config"]):
            self.assertTrue(voices.is_up_to_date("proj", "narrator", model), model)

    def test_nothing_to_undo(self):
        self.assertEqual(self.code(voices.undo, "proj", "narrator"), "order.history_empty")

    def test_undo_to_a_take_without_audio_keeps_the_history(self):
        voices.choose("proj", "narrator", 1)
        voices.choose("proj", "narrator", 2)
        take = orders.get("proj", "voice", "narrator")["attempts"][0]
        orders.attempt_audio("proj", "voice", "narrator", take).unlink()
        self.assertEqual(self.code(voices.undo, "proj", "narrator"), "voice.take_audio_missing")
        self.assertEqual(orders.get("proj", "voice", "narrator")["chosen"], 2)


class FailedPrintTests(VoicesBase):
    def test_a_failed_print_leaves_the_voice_with_a_reference_but_no_prints(self):
        voices.choose("proj", "narrator", 1)
        worker.run(engine=engine.FakeEngine(fail_with="boom"))
        self.assertEqual([e["state"] for e in queue.list_entries()], ["failed", "failed"])
        self.assertEqual(self.print_names(), [])
        status = voices.status("proj", "narrator")
        self.assertEqual((status["reference"], status["prints"]), (1, []))
        self.new_line()
        specs = orders.attempt_specs("proj", "line", "narrator/intro")
        self.assertEqual(self.code(queue.enqueue_attempts, "proj", "line", "narrator/intro", specs),
                         "line.voice_not_fixed")

    def test_a_cancelled_print_leaves_no_prints(self):
        entries = voices.choose("proj", "narrator", 1)["prints"]
        queue.cancel(entries[0]["id"])
        worker.run()
        self.assertEqual(voices.status("proj", "narrator")["prints"], ["1.7b-base"])
        self.assertEqual(self.print_names(), ["1.7b-base.json", "1.7b-base.rvq", "1.7b-base.spk"])

    def test_choosing_again_after_a_failure_queues_the_missing_prints(self):
        voices.choose("proj", "narrator", 1)
        worker.run(engine=engine.FakeEngine(fail_with="boom"))
        again = voices.choose("proj", "narrator", 1)
        self.assertEqual([e["model"] for e in again["prints"]], MODELS)
        worker.run()
        self.assertEqual(voices.status("proj", "narrator")["prints"], MODELS)


class ModelTests(VoicesBase):
    """Finding 2: the model must still be a print model when the worker runs, and cannot leave ``prints/``."""

    def test_a_print_model_removed_after_queueing(self):
        entries = voices.choose("proj", "narrator", 1)["prints"]
        self.set_config(printModels=["1.7b-base"])
        worker.run(engine=StubEngine(AssertionError("the engine must not run for the removed model")))
        removed = queue.get(entries[0]["id"])
        self.assertEqual((removed["state"], removed["error"]["code"]), ("failed", "order.model_not_allowed"))
        self.assertIn("0.6b-base", queue.error_text(removed, "es"))
        self.assertEqual(self.print_names(), [])

    def test_a_print_model_removed_from_the_config_keeps_the_other_print(self):
        voices.choose("proj", "narrator", 1)
        self.set_config(printModels=["1.7b-base"])
        worker.run()
        self.assertEqual([e["state"] for e in queue.list_entries()], ["failed", "done"])
        self.assertEqual(self.print_names(), ["1.7b-base.json", "1.7b-base.rvq", "1.7b-base.spk"])

    def test_a_line_model_removed_after_queueing(self):
        self.choose_and_run(1)
        self.new_line()
        entry = queue.enqueue_attempts("proj", "line", "narrator/intro",
                                       orders.attempt_specs("proj", "line", "narrator/intro"))[0]
        self.set_config(printModels=["1.7b-base"])
        worker.run(engine=StubEngine(AssertionError("the engine must not run")))
        failed = queue.get(entry["id"])
        self.assertEqual((failed["state"], failed["error"]["code"]), ("failed", "order.model_not_allowed"))

    def test_the_model_name_cannot_leave_the_prints_folder(self):
        for bad in ("../x", "a/b", "", "0.6b-base/../../x", "..", None):
            self.assertEqual(self.code(voices.print_files, "proj", "narrator", bad), "order.model_not_allowed", bad)
        for bad in ("../x", "a/b", "", ".."):
            self.assertEqual(self.code(voices.voice_dir, "proj", bad), "order.unknown_voice", bad)

    def test_a_hand_edited_print_entry_with_a_path_as_model(self):
        self.write_reference()
        entry = queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        path = queue.queue_path()
        data = json.loads(path.read_text())
        data["entries"][0]["model"] = "../../../../escape"
        path.write_text(json.dumps(data))
        worker.run(engine=StubEngine(AssertionError("the engine must not run")))
        self.assertEqual(queue.get(entry["id"])["error"]["code"], "order.model_not_allowed")
        self.assertEqual(list(self.tmp.rglob("escape*")), [])


class GateAndStatusTests(VoicesBase):
    def test_status_of_a_voice_without_a_reference(self):
        self.assertEqual(voices.status("proj", "narrator"),
                         {"voice": "narrator", "reference": None, "prints": [], "staleLines": []})
        self.assertEqual(voices.status("proj", "orc")["reference"], None)  # not even a voice order

    def test_the_line_gate_at_enqueue(self):
        self.new_line()
        specs = orders.attempt_specs("proj", "line", "narrator/intro")
        self.assertEqual(self.code(queue.enqueue_attempts, "proj", "line", "narrator/intro", specs),
                         "line.voice_not_fixed")
        self.assertEqual(queue.list_entries(), [])
        self.choose_and_run(1)
        self.assertEqual(len(queue.enqueue_attempts("proj", "line", "narrator/intro", specs)), 1)

    def test_the_gate_error_is_translated(self):
        self.new_line()
        specs = orders.attempt_specs("proj", "line", "narrator/intro")
        with self.assertRaises(Exception) as cm:
            queue.enqueue_attempts("proj", "line", "narrator/intro", specs)
        self.assertEqual((cm.exception.code, cm.exception.params), ("line.voice_not_fixed",
                                                                    {"voice": "narrator", "model": "0.6b-base"}))
        error = queue.make_error(cm.exception.code, **cm.exception.params)
        self.assertIn("no tiene una huella al día", queue.error_text(error, "es"))

    def test_the_gate_when_the_reference_changed_after_queueing(self):
        self.choose_and_run(1)
        self.new_line()
        entry = queue.enqueue_attempts("proj", "line", "narrator/intro",
                                       orders.attempt_specs("proj", "line", "narrator/intro"))[0]
        voices.choose("proj", "narrator", 2)  # the prints of take 2 are still queued
        worker.run(once=True)  # the line is first in the queue
        failed = queue.get(entry["id"])
        self.assertEqual((failed["state"], failed["error"]["code"]), ("failed", "line.voice_not_fixed"))

    def test_the_gate_for_the_model_of_the_line(self):
        self.set_config(printModels=["1.7b-base", "0.6b-base"])
        self.choose_and_run(1)
        orders.submit("proj", {"key": "narrator/big", "type": "line", "voice": "narrator", "text": "x",
                               "model": "0.6b-base"})
        self.assertEqual(len(queue.enqueue_attempts("proj", "line", "narrator/big",
                                                    orders.attempt_specs("proj", "line", "narrator/big"))), 1)
        (self.prints_dir() / "0.6b-base.rvq").unlink()
        specs = orders.attempt_specs("proj", "line", "narrator/big")
        self.assertEqual(self.code(queue.enqueue_attempts, "proj", "line", "narrator/big", specs),
                         "line.voice_not_fixed")

    def test_a_line_records_the_reference_and_goes_stale_when_the_voice_changes(self):
        self.choose_and_run(1)
        self.new_line()
        self.new_line("narrator/outro", "The end.")
        for key in ("narrator/intro", "narrator/outro"):
            attempt = self.speak(key)
            self.assertEqual(self.attempts("line", key)[attempt - 1]["voiceReference"], 1)
            orders.choose("proj", "line", key, attempt)
        self.assertEqual(voices.status("proj", "narrator")["staleLines"], [])
        self.choose_and_run(2)
        status = voices.status("proj", "narrator")
        self.assertEqual(status["reference"], 2)
        self.assertEqual(status["prints"], MODELS)
        self.assertEqual(status["staleLines"], [{"key": "narrator/intro", "chosen": 1, "voiceReference": 1},
                                                {"key": "narrator/outro", "chosen": 1, "voiceReference": 1}])
        attempt = self.speak("narrator/intro")  # redone with the new reference
        self.assertEqual(self.attempts("line", "narrator/intro")[attempt - 1]["voiceReference"], 2)
        self.assertEqual([x["key"] for x in voices.status("proj", "narrator")["staleLines"]],
                         ["narrator/intro", "narrator/outro"])  # nothing is regenerated by itself; not chosen yet
        orders.choose("proj", "line", "narrator/intro", attempt)
        self.assertEqual([x["key"] for x in voices.status("proj", "narrator")["staleLines"]], ["narrator/outro"])
        voices.undo("proj", "narrator")  # back to take 1: the old line is fine, the new one is stale
        status = voices.status("proj", "narrator")
        self.assertEqual([x["key"] for x in status["staleLines"]], ["narrator/intro"])
        self.assertEqual(self.attempts("line", "narrator/outro")[0]["voiceReference"], 1)

    def test_lines_of_other_voices_and_unchosen_lines_are_not_listed(self):
        self.choose_and_run(1)
        self.new_line()
        self.speak()  # not chosen
        self.choose_and_run(2)
        self.assertEqual(voices.status("proj", "narrator")["staleLines"], [])

    def test_undo_to_none_makes_every_chosen_line_stale(self):
        self.choose_and_run(1)
        self.new_line()
        orders.choose("proj", "line", "narrator/intro", self.speak())
        voices.undo("proj", "narrator")
        status = voices.status("proj", "narrator")
        self.assertEqual((status["reference"], [x["key"] for x in status["staleLines"]]), (None, ["narrator/intro"]))

    def test_the_marker_is_named_after_the_model(self):
        self.assertEqual(voices.print_files("proj", "narrator", "0.6b-base")[2].name, "0.6b-base.json")


if __name__ == "__main__":
    unittest.main()

import copy
import fcntl
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import engine, orders, paths, projects, queue
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
VOICE = json.loads((ROOT / "examples" / "order-voice.json").read_text())
LINE = json.loads((ROOT / "examples" / "order-line.json").read_text())
CONFIG = json.loads((ROOT / "examples" / "galivelop-voices.json").read_text())


def closed_url() -> str:
    """The address of an Ollama that is not there (a worker looks for one before every job), so a test never talks to
    the one of the machine it runs on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return "http://127.0.0.1:%d" % sock.getsockname()[1]


class QueueBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {
            "GVOICE_CONFIG_HOME": str(self.tmp / "cfg"), "GVOICE_DATA_HOME": str(self.tmp / "data"),
            "GALIVELOP_STATE_HOME": str(self.tmp / "state"), "GRUN_OLLAMA_URL": closed_url()})
        env.start()
        self.addCleanup(env.stop)
        for var in ("GVOICE_MACHINE_PROFILE", "GVOICE_ENGINE", "GVOICE_FAKE_DELAY", "GVOICE_FAKE_FAIL"):
            os.environ.pop(var, None)
        self.p = "world"
        self.root = self.tmp / "world"
        self.root.mkdir()
        self.write_config()
        projects.add(self.root)

    def write_config(self, **changes):
        cfg = copy.deepcopy(CONFIG)
        cfg.pop("$schema", None)
        cfg["name"] = "world"
        cfg.update(changes)
        (self.root / projects.CONFIG_FILE).write_text(json.dumps(cfg))

    def hold_worker_lock(self):
        """Pretend a worker is alive: hold ``worker.lock`` in this process (a second open() fails, as in a worker)."""
        queue.worker_lock_path().parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(queue.worker_lock_path()), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(os.close, fd)

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

    def take(self, key="narrator", seed=1, prints=()):
        """A finished voice take with its audio (as the worker leaves it); `prints`: the models it already has."""
        spec = orders.attempt_specs(self.p, key, seed=seed)[0]
        spec["result"] = engine.EngineResult(duration_ms=5, engine_version="fake-1", audio_ms=900)
        take = orders.add_attempt(self.p, key, spec)
        attempt = next(a for a in orders.get(self.p, key)["attempts"] if a["id"] == take)
        audio = orders.attempt_audio(self.p, key, attempt)
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"RIFF")
        for model in prints:
            for path in orders.print_paths(self.p, key, attempt, model):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
        return take

    def code(self, fn, *args, **kwargs):
        with self.assertRaises(GvoiceError) as cm:
            fn(*args, **kwargs)
        return cm.exception

    def push(self, key="narrator", count=1, **kw):
        """Queue `count` takes of voice `key` (the order is created on first use)."""
        try:
            orders.get(self.p, key)
        except GvoiceError:
            orders.submit(self.p, self.voice(key=key))
        return queue.enqueue(self.p, key, orders.attempt_specs(self.p, key, count, **kw))


class QueueTests(QueueBase):
    def test_enqueue_voice_fields(self):
        entries = self.push(count=2, seed=10)
        self.assertEqual([e["id"] for e in entries], [1, 2])
        first = entries[0]
        self.assertEqual((first["kind"], first["state"], first["seed"], first["project"], first["key"]),
                         ("voice", "queued", 10, "world", "narrator"))
        self.assertEqual((first["pid"], first["attemptId"], first["error"], first["cancelRequested"]),
                         (None, None, None, False))
        self.assertEqual(entries[1]["seed"], 11)
        self.assertTrue(first["instruction"].startswith("Gender"))
        self.assertEqual(first["text"], VOICE["testText"])
        self.assertEqual(queue.get(2), entries[1])
        self.assertTrue((self.tmp / "data" / "queue.json").is_file())

    def test_enqueue_line_fields(self):
        self.take_fixed()
        orders.submit(self.p, self.line())
        entry = queue.enqueue(self.p, "narrator/intro-01", orders.attempt_specs(self.p, "narrator/intro-01"))[0]
        self.assertEqual((entry["kind"], entry["reference"], entry["text"]), ("line", 1, LINE["text"]))
        self.assertNotIn("instruction", entry)

    def take_fixed(self):
        orders.submit(self.p, self.voice())
        take = self.take()
        orders.choose(self.p, "narrator", take)
        return take

    def test_unknown_order_not_queued(self):
        spec = [{"seed": 1, "text": "t", "instruction": "i"}]
        self.assertEqual(self.code(queue.enqueue, self.p, "nope", spec).code, "order.unknown")
        self.assertEqual(queue.list_entries(), [])

    def test_incomplete_spec_not_queued(self):
        orders.submit(self.p, self.voice())
        exc = self.code(queue.enqueue, self.p, "narrator", [{"seed": 1, "text": "t", "instruction": "i"}, {"seed": 2}])
        self.assertEqual((exc.code, exc.params["missing"]), ("order.spec_invalid", "text, instruction"))
        self.assertEqual(queue.list_entries(), [])  # nothing half queued

    def test_line_refused_if_production_model_has_no_print(self):
        # the profile produces with 0.6b-base; the project only prints 1.7b-base
        self.take_fixed()
        self.write_config(printModels=["1.7b-base"])
        orders.submit(self.p, self.line())
        exc = self.code(queue.enqueue, self.p, "narrator/intro-01", orders.attempt_specs(self.p, "narrator/intro-01"))
        self.assertEqual((exc.code, exc.params["model"], exc.params["models"]),
                         ("queue.model_not_printed", "0.6b-base", "1.7b-base"))
        self.assertEqual(queue.list_entries(), [])

    def test_submit_order_line_refused_before_it_is_stored(self):
        self.take_fixed()
        self.write_config(printModels=["1.7b-base"])
        self.assertEqual(self.code(queue.submit_order, self.p, self.line()).code, "queue.model_not_printed")
        self.assertEqual(self.code(orders.get, self.p, "narrator/intro-01").code, "order.unknown")

    def test_production_model_without_one_in_the_profile(self):
        # the schema demands a produce list, so a profile without one only comes from code
        exc = self.code(queue.production_model, self.p, {"name": "p", "models": {"design": "1.7b-voicedesign"}})
        self.assertEqual((exc.code, exc.params["profile"]), ("queue.no_production_model", "p"))
        self.assertEqual(queue.production_model(self.p), "0.6b-base")
        self.assertEqual(queue.production_model(self.p, {"models": {"produce": ["1.7b-base"]}}), "1.7b-base")

    def test_fifo(self):
        self.push("narrator")
        self.push("orc")
        self.push("narrator")
        order = []
        while True:
            entry = queue.claim()
            if entry is None:
                break
            order.append((entry["id"], entry["key"]))
            self.assertEqual((entry["state"], entry["pid"]), ("running", os.getpid()))
            self.assertIsNotNone(entry["startedAt"])
            queue.finish(entry["id"], "done", attempt_id=1)
        self.assertEqual(order, [(1, "narrator"), (2, "orc"), (3, "narrator")])
        self.assertIsNone(queue.next_queued())

    def test_next_queued_does_not_take(self):
        self.push(count=2)
        self.assertEqual(queue.next_queued()["id"], 1)
        self.assertEqual(queue.next_queued()["id"], 1)
        self.assertEqual(queue.claim()["id"], 1)
        self.assertEqual(queue.next_queued()["id"], 2)

    def test_list_filter(self):
        self.hold_worker_lock()
        self.push(count=3)
        queue.claim()
        self.assertEqual([e["id"] for e in queue.list_entries(["queued"])], [2, 3])
        self.assertEqual([e["id"] for e in queue.list_entries(("running", "queued"))], [1, 2, 3])
        self.assertEqual(queue.list_entries(["done"]), [])

    def test_cancel_queued(self):
        self.push(count=2)
        entry = queue.cancel(1)
        self.assertEqual((entry["state"], entry["cancelRequested"]), ("cancelled", False))
        self.assertIsNotNone(entry["finishedAt"])
        self.assertEqual(queue.claim()["id"], 2)  # the cancelled one is skipped

    def test_cancel_running_requests(self):
        self.hold_worker_lock()
        self.push()
        queue.claim()
        self.assertFalse(queue.is_cancel_requested(1))
        entry = queue.cancel(1)
        self.assertEqual((entry["state"], entry["cancelRequested"]), ("running", True))
        self.assertTrue(queue.is_cancel_requested(1))

    def test_cancel_terminal_and_unknown(self):
        self.push()
        queue.claim()
        queue.finish(1, "done", attempt_id=1)
        exc = self.code(queue.cancel, 1)
        self.assertEqual((exc.code, exc.params["state"]), ("queue.not_cancellable", "done"))
        self.assertEqual(self.code(queue.cancel, 99).code, "queue.unknown")
        self.assertEqual(self.code(queue.cancel, "1").code, "queue.unknown")

    def test_clear_cancels_only_queued_of_the_project(self):
        self.hold_worker_lock()
        self.push(count=3)
        queue.claim()
        self.assertEqual([e["id"] for e in queue.clear("other")], [])
        self.assertEqual([e["id"] for e in queue.clear(self.p)], [2, 3])
        self.assertEqual(queue.get(1)["state"], "running")

    def test_finish_rules(self):
        self.push()
        self.assertEqual(self.code(queue.finish, 1, "done").code, "queue.not_running")  # still queued
        queue.claim()
        self.assertEqual(self.code(queue.finish, 1, "running").code, "queue.bad_state")
        entry = queue.finish(1, "failed", error="engine.timeout")
        self.assertEqual((entry["state"], entry["error"]), ("failed", {"code": "engine.timeout", "params": {}}))
        self.assertIsNone(entry["pid"])

    def test_recovery_without_worker_lock(self):
        self.push(count=2)
        queue.claim()  # pid is this live process: the pid is irrelevant, only the worker lock counts
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["pid"], entry["startedAt"]), ("queued", None, None))
        self.assertEqual(json.loads((self.tmp / "data" / "queue.json").read_text())["entries"][0]["state"], "queued")
        self.assertEqual(queue.claim()["id"], 1)  # first again, FIFO kept

    def test_recovery_with_cancel_requested(self):
        self.push()
        queue.claim()
        queue.cancel(1)
        self.assertEqual(queue.get(1)["state"], "cancelled")

    def test_live_worker_lock_keeps_running(self):
        self.push()
        queue.claim()
        self.hold_worker_lock()
        for read in (lambda: queue.get(1), lambda: queue.list_entries()[0]):
            self.assertEqual(read()["state"], "running")

    def test_claim_and_finish_do_not_recover(self):
        self.push(count=2)
        queue.claim()
        self.assertEqual(queue.claim()["id"], 2)  # entry 1 is still running, not handed out again
        queue.finish(1, "done", attempt_id=1)

    def test_recover_orphans_is_for_the_lock_owner(self):
        self.push()
        queue.claim()
        self.hold_worker_lock()  # as the worker does; the others leave it alone
        self.assertEqual(queue.get(1)["state"], "running")
        queue.recover_orphans()
        self.assertEqual(queue.get(1)["state"], "queued")

    def test_recovery_deletes_pending_audio(self):
        self.push()
        queue.claim()
        pending = orders.pending_audio_path(self.p, "narrator", 1)
        pending.parent.mkdir(parents=True)
        pending.write_bytes(b"half")
        pending.with_name(pending.name + ".abc.tmp").write_bytes(b"half")
        self.assertEqual(queue.get(1)["state"], "queued")
        self.assertFalse(pending.parent.exists())  # the audio, its temporary file and the empty folder

    def test_recovery_keeps_the_folder_of_a_take_that_has_audio(self):
        self.push()
        queue.claim()
        pending = orders.pending_audio_path(self.p, "narrator", 1)
        pending.parent.mkdir(parents=True)
        (pending.parent / "audio.wav").write_bytes(b"done")
        queue.get(1)
        self.assertTrue((pending.parent / "audio.wav").is_file())

    def test_a_queue_json_of_the_old_format_is_read_as_it_is(self):
        """D-10: the file of gimg/gvoice (``nextId``, ``entries``; no ``position``, no ``orphanCount``) is neither
        migrated nor rewritten by a read; its entries are taken in id order and the next id goes on."""
        old = {"nextId": 4, "entries": [
            {"id": 1, "kind": "voice", "project": "world", "key": "narrator", "seed": 1, "text": "t", "state": "done",
             "pid": None, "enqueuedAt": "2026-01-01T00:00:00Z", "startedAt": "2026-01-01T00:00:01Z",
             "finishedAt": "2026-01-01T00:00:02Z", "error": None, "attemptId": 1, "cancelRequested": False,
             "instruction": "i"},
            {"id": 3, "kind": "prints", "project": "world", "key": "narrator", "seed": None, "text": None, "take": 1,
             "state": "queued", "pid": None, "enqueuedAt": "2026-01-01T00:00:03Z", "startedAt": None,
             "finishedAt": None, "error": None, "attemptId": None, "cancelRequested": False},
            {"id": 2, "kind": "voice", "project": "world", "key": "narrator", "seed": 2, "text": "t",
             "state": "queued", "pid": None, "enqueuedAt": "2026-01-01T00:00:02Z", "startedAt": None,
             "finishedAt": None, "error": None, "attemptId": None, "cancelRequested": False, "instruction": "i"}]}
        path = self.tmp / "data" / "queue.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(old))
        before = path.read_bytes()
        self.assertEqual([e["id"] for e in queue.list_entries()], [1, 3, 2])  # file order
        self.assertEqual(queue.get(1), old["entries"][0])
        self.assertEqual(path.read_bytes(), before)  # read, not migrated
        self.assertEqual(queue.entry_view(old["entries"][0], "en"), old["entries"][0])
        self.assertEqual(queue.next_queued()["id"], 2)  # no position: by id, as a queue.json of gimg was always taken
        self.assertEqual(queue.claim()["id"], 2)
        self.hold_worker_lock()
        orders.submit(self.p, self.voice())
        self.assertEqual(self.push()[0]["id"], 4)  # nextId goes on
        self.assertEqual(json.loads(path.read_text())["nextId"], 5)

    def test_a_worker_that_dies_twice_with_the_entry_fails_it(self):
        """grun (D-5): the first orphaning requeues, the second closes the entry as ``queue.orphaned`` (before, a
        job that kills its worker was requeued for ever); the pending audio is deleted both times."""
        self.push()
        pending = orders.pending_audio_path(self.p, "narrator", 1)
        for round_ in (1, 2):
            self.assertEqual(queue.claim()["id"], 1)
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_bytes(b"half")
            entry = queue.get(1)  # no worker lock: recovery
            self.assertFalse(pending.parent.exists(), round_)
            self.assertEqual(entry["orphanCount"], round_)
        self.assertEqual((entry["state"], entry["pid"], entry["startedAt"]), ("failed", None, None))
        self.assertEqual(entry["error"], {"code": "queue.orphaned", "params": {"id": 1, "count": 2}})
        self.assertIsNone(queue.claim())
        self.assertIn("2 times", queue.error_text(entry, "en"))
        self.assertIn("2 veces", queue.error_text(entry, "es"))

    def test_errors_of_grun_come_out_as_gvoice_errors_with_gvoice_texts(self):
        self.push()
        queue.claim()
        exc = self.code(queue.finish, 1, "cancelled")  # grun: a running entry is cancelled only after a cancel request
        self.assertEqual((exc.code, exc.params), ("queue.invalid_transition",
                                                  {"id": 1, "from_state": "running", "to_state": "cancelled"}))
        self.assertIn("running", exc.message("en"))
        self.assertIn("no puede pasar de", exc.message("es"))
        self.assertEqual(self.code(queue.get, "x").code, "queue.unknown")

    def test_takes_are_not_batches(self):
        self.assertTrue(all("batch" not in e for e in self.push(count=3)))

    def test_prune_keeps_last_200_terminal(self):
        for _ in range(5):
            self.push(count=41)
            while (entry := queue.claim()) is not None:
                queue.finish(entry["id"], "done", attempt_id=1)
        self.assertEqual(len(queue.list_entries()), 200)
        self.assertEqual(queue.list_entries()[0]["id"], 6)  # 205 made, the first 5 pruned

    def test_corrupt_queue(self):
        path = self.tmp / "data" / "queue.json"
        for text in ("{not json", '{"nextId": 1, "entries": "x"}',
                     '{"nextId": 1, "entries": [{"id": 1, "state": "paused", "kind": "voice"}]}'):  # (an unknown ``kind`` is grun's business no more)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            exc = self.code(queue.list_entries)
            self.assertEqual((exc.code, exc.params["path"]), ("queue.corrupt", str(path)))

    def test_error_text(self):
        error = queue.make_error("limit.model", model="x", use="design", allowed="y")
        self.assertIn("\"x\"", queue.error_text(error, "es"))
        self.assertEqual(queue.error_text(None), "")
        self.assertEqual(queue.error_text({"code": "no.such.code", "params": {}}, "en"), "no.such.code")
        self.assertEqual(queue.error_text({"code": "limit.model", "params": {}}, "en"), "limit.model")  # missing params
        self.assertEqual(queue.error_text("plain"), "plain")
        entry = {"state": "failed", "error": queue.make_error("engine.timeout")}
        self.assertEqual(queue.entry_view(entry, "en")["errorText"], "the engine ran past the time limit")

    def test_worker_alive_is_a_pure_read(self):
        self.assertFalse(queue.worker_alive())
        self.assertFalse((self.tmp / "data").exists())
        self.hold_worker_lock()
        self.assertTrue(queue.worker_alive())


class ServiceTests(QueueBase):
    """Choosing a voice take queues the ``prints`` job (D10)."""

    def voice_with_takes(self, *prints_per_take):
        orders.submit(self.p, self.voice())
        return [self.take(seed=i + 1, prints=prints) for i, prints in enumerate(prints_per_take)]

    def test_submit_order_stores_and_queues(self):
        record, entries = queue.submit_order(self.p, self.voice(), count=2)
        self.assertEqual((record["key"], [e["kind"] for e in entries]), ("narrator", ["voice", "voice"]))
        self.assertEqual([e["seed"] for e in entries], [1234, 1235])
        self.assertIn("warnings", record)

    def test_invalid_count_leaves_the_stored_order_unchanged(self):
        orders.submit(self.p, self.voice())
        before = orders.get(self.p, "narrator")
        for bad in (0, 51):
            err = self.code(queue.submit_order, self.p, self.voice(testText="Changed."), bad)
            self.assertEqual(err.code, "order.count_invalid")
        err = self.code(queue.submit_order, self.p, self.voice(testText="Changed.", seed=2 ** 32 - 1), 2)
        self.assertEqual(err.code, "order.seed_range")
        self.assertEqual(orders.get(self.p, "narrator"), before)
        self.assertEqual(queue.list_entries(), [])

    def test_queued_line_keeps_the_voice_it_was_made_for(self):
        orders.submit(self.p, self.voice())
        orders.choose(self.p, "narrator", self.take())
        orders.submit(self.p, self.voice(key="orc"))
        orders.choose(self.p, "orc", self.take("orc", seed=4))
        orders.submit(self.p, self.line())
        entry, = queue.new_takes(self.p, "narrator/intro-01")
        self.assertEqual((entry["voice"], entry["reference"]), ("narrator", 1))
        orders.submit(self.p, self.line(voice="orc"))
        self.assertEqual(queue.get(entry["id"])["voice"], "narrator")

    def test_unknown_engine_queues_nothing(self):
        orders.submit(self.p, self.voice())
        take = self.take()
        before = orders.get(self.p, "narrator")
        with mock.patch.dict(os.environ, {"GVOICE_ENGINE": "nope"}):
            for call in (lambda: queue.submit_order(self.p, self.voice(testText="Changed."), 1),
                         lambda: queue.new_takes(self.p, "narrator", 1),
                         lambda: queue.choose(self.p, "narrator", take)):
                err = self.code(call)
                self.assertEqual((err.code, err.params["engine"]), ("engine.unknown", "nope"))
        self.assertEqual(orders.get(self.p, "narrator"), before)  # not even chosen
        self.assertEqual(queue.list_entries(), [])

    def test_new_takes(self):
        orders.submit(self.p, self.voice())
        self.assertEqual([e["seed"] for e in queue.new_takes(self.p, "narrator", 2, seed=50)], [50, 51])
        self.assertEqual(self.code(queue.new_takes, self.p, "narrator", 0).code, "order.count_invalid")

    def test_choose_queues_one_prints_job_with_the_take(self):
        first, = self.voice_with_takes(())
        result = queue.choose(self.p, "narrator", first)
        self.assertEqual((result["old"], result["new"]), (None, first))
        job, = result["entries"]
        self.assertEqual((job["kind"], job["take"], job["key"], job["state"]), ("prints", first, "narrator", "queued"))
        self.assertEqual(orders.get(self.p, "narrator")["chosen"], first)

    def test_choose_with_every_print_queues_nothing(self):
        first, = self.voice_with_takes(("0.6b-base", "1.7b-base"))
        self.assertEqual(queue.choose(self.p, "narrator", first)["entries"], [])
        self.assertEqual(queue.list_entries(), [])

    def test_choose_with_one_print_missing_still_queues(self):
        first, = self.voice_with_takes(("0.6b-base",))
        self.assertEqual(len(queue.choose(self.p, "narrator", first)["entries"]), 1)

    def test_choosing_again_does_not_duplicate_the_job(self):
        first, = self.voice_with_takes(())
        queue.choose(self.p, "narrator", first)
        again = queue.choose(self.p, "narrator", first)
        self.assertEqual((again["old"], again["new"], again["entries"]), (first, first, []))
        self.assertEqual(len(queue.list_entries()), 1)
        # a job that finished without making the prints (it failed) is queued again
        queue.claim()
        queue.finish(1, "failed", error="engine.failed")
        self.assertEqual(len(queue.choose(self.p, "narrator", first)["entries"]), 1)

    def test_a_running_job_also_counts_as_queued(self):
        first, = self.voice_with_takes(())
        queue.choose(self.p, "narrator", first)
        self.hold_worker_lock()
        queue.claim()
        self.assertIsNone(queue.enqueue_prints(self.p, "narrator", first))

    def test_choose_refused_queues_nothing(self):
        first, = self.voice_with_takes(())
        orders.mark(self.p, "narrator", first, "discarded")
        self.assertEqual(self.code(queue.choose, self.p, "narrator", first).code, "order.choose_discarded")
        self.assertEqual(queue.list_entries(), [])

    def test_undo_to_a_take_without_its_prints_queues_the_job(self):
        first, second = self.voice_with_takes((), ("0.6b-base", "1.7b-base"))
        queue.choose(self.p, "narrator", first)
        queue.cancel(1)
        queue.choose(self.p, "narrator", second)  # complete: nothing queued
        self.assertEqual(len(queue.list_entries()), 1)
        result = queue.undo(self.p, "narrator")
        self.assertEqual((result["old"], result["new"]), (second, first))
        job, = result["entries"]
        self.assertEqual((job["kind"], job["take"]), ("prints", first))

    def test_undo_to_a_take_with_all_its_prints_queues_nothing(self):
        first, second = self.voice_with_takes(("0.6b-base", "1.7b-base"), ())
        queue.choose(self.p, "narrator", first)
        queue.choose(self.p, "narrator", second)
        self.assertEqual(len(queue.list_entries()), 1)  # the second one's job
        self.assertEqual(queue.undo(self.p, "narrator")["entries"], [])
        self.assertEqual(len(queue.list_entries()), 1)

    def test_undo_to_nothing_queues_nothing(self):
        first, = self.voice_with_takes(("0.6b-base", "1.7b-base"))
        queue.choose(self.p, "narrator", first)
        result = queue.undo(self.p, "narrator")
        self.assertEqual((result["new"], result["entries"]), (None, []))

    def test_undo_with_empty_history_fails(self):
        self.voice_with_takes(())
        self.assertEqual(self.code(queue.undo, self.p, "narrator").code, "order.history_empty")

    def test_choosing_a_line_take_queues_no_prints(self):
        self.voice_with_takes(("0.6b-base", "1.7b-base"))
        orders.choose(self.p, "narrator", 1)
        orders.submit(self.p, self.line())
        spec = orders.attempt_specs(self.p, "narrator/intro-01")[0]
        spec["result"] = {"audio_ms": 500}
        take = orders.add_attempt(self.p, "narrator/intro-01", spec)
        self.assertEqual(queue.choose(self.p, "narrator/intro-01", take)["entries"], [])

    def test_the_prints_of_a_voice_go_before_the_lines_asked_for_after_it(self):
        first, = self.voice_with_takes(())
        queue.choose(self.p, "narrator", first)
        orders.submit(self.p, self.line())
        line = queue.new_takes(self.p, "narrator/intro-01", 2)
        self.assertEqual([queue.claim()["kind"] for _ in range(3)], ["prints", "line", "line"])
        self.assertEqual(line[0]["id"], 2)

    def test_prints_of_a_take_that_does_not_exist(self):
        orders.submit(self.p, self.voice())
        self.assertEqual(self.code(queue.enqueue_prints, self.p, "narrator", 9).code, "order.attempt_unknown")
        self.assertEqual(queue.list_entries(), [])


FIXTURE = ROOT / "tests" / "fixtures" / "queue-views-main.json"
NEW_FIELDS = ("position", "orphanCount")  # what grun adds to an entry (invariant 13: they may appear, nothing else)


class ApiShapeTests(QueueBase):
    """Invariant 13 (grun): the entries that ``gvoice queue list --json`` / ``/api/queue`` give, and that the
    interface reads, keep the shape the ``main`` branch gave before gvoice moved onto `grun.queue`.
    ``tests/fixtures/queue-views-main.json`` was produced by `gvoice/queue.py` of ``origin/main`` (8a17618): one entry
    of each kind in each state (``cr`` is a running one with ``cancelRequested``)."""
    NOW = "2026-01-01T00:00:00Z"
    ROLES = ("running", "done", "failed", "cancelled", "cr")

    def views(self) -> dict:
        """The scenario: 5 entries of each kind taken (ids 1-5 voice, 6-10 line, 11-15 prints, one per role) and one
        more of each kept ``queued`` (16-18). Returns ``{"<kind>-<state>": entry_view}``; the pid is ``"<pid>"``."""
        self.hold_worker_lock()
        orders.submit(self.p, self.voice())
        takes = [self.take(seed=i + 1) for i in range(6)]
        orders.choose(self.p, "narrator", takes[0])
        orders.submit(self.p, self.line())
        queue.new_takes(self.p, "narrator", 5)
        queue.new_takes(self.p, "narrator/intro-01", 5)
        for take in takes[:5]:
            queue.enqueue_prints(self.p, "narrator", take)
        for _ in range(15):
            queue.claim()
        for entry_id in range(1, 16):
            role = self.ROLES[(entry_id - 1) % 5]
            if role == "done":
                queue.finish(entry_id, "done", attempt_id=1)
            elif role == "failed":
                queue.finish(entry_id, "failed", error=queue.make_error("engine.failed", message="boom"))
            elif role == "cancelled":
                queue.cancel(entry_id)
                queue.finish(entry_id, "cancelled")
            elif role == "cr":
                queue.cancel(entry_id)
        queue.new_takes(self.p, "narrator", 1)
        queue.new_takes(self.p, "narrator/intro-01", 1)
        queue.enqueue_prints(self.p, "narrator", takes[5])
        views = {}
        for entry in queue.list_entries():
            state = "cr" if entry["cancelRequested"] and entry["state"] == "running" else entry["state"]
            view = queue.entry_view(entry, "en")
            if view["pid"] == os.getpid():
                view["pid"] = "<pid>"
            views["%s-%s" % (entry["kind"], state)] = view
        return views

    def test_entry_view_keeps_the_shape_of_main(self):
        with mock.patch("grun.queue._now", return_value=self.NOW):
            views = self.views()
        expected = json.loads(FIXTURE.read_text())
        self.assertEqual(sorted(views), sorted(expected))
        self.assertEqual(len(expected), 18)
        for name, want in expected.items():
            got = views[name]
            self.assertEqual({k: v for k, v in got.items() if k not in NEW_FIELDS}, want, name)

    def test_the_fields_grun_adds_are_the_documented_ones(self):
        with mock.patch("grun.queue._now", return_value=self.NOW):
            views = self.views()
        for name, got in views.items():
            self.assertEqual(got.get("orphanCount"), 0, name)
            self.assertIsInstance(got["position"], int, name)
            self.assertNotIn("batch", got, name)  # a take is not a batch: the interface shows entries one by one


if __name__ == "__main__":
    unittest.main()

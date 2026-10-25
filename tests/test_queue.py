# Copiado de gimg@0d02f51 (D7); cambia: entradas con `kind` (attempt / print), (project, type, key) en vez de
# (key, profile), audio .wav, sin límites de imagen, estimado por motor/tarea/modelo/dispositivo.
import copy
import fcntl
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import log, orders, projects, queue, sheet
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "galivelop-voices.json").read_text())
SHEET = {"gender": "male", "age": "adult", "pitch": "low"}


class QueueBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {
            "GVOICE_CONFIG_HOME": str(self.tmp / "cfg"), "GVOICE_DATA_HOME": str(self.tmp / "data"),
            "XDG_STATE_HOME": str(self.tmp / "state"), "GVOICE_ENGINE": "fake"})
        env.start()
        self.addCleanup(env.stop)
        for var in ("GVOICE_MACHINE_PROFILE", "GVOICE_FAKE_DELAY", "GVOICE_FAKE_FAIL"):
            os.environ.pop(var, None)
        self.projects = {}
        for name in ("proj", "other"):
            self.add_project(name)

    def hold_worker_lock(self):
        """Pretend a worker is alive: hold ``worker.lock`` in this process (a second open() fails, as in a worker)."""
        queue.worker_lock_path().parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(queue.worker_lock_path()), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(os.close, fd)

    def add_project(self, name):
        root = self.tmp / name
        root.mkdir()
        cfg = copy.deepcopy(EXAMPLE)
        cfg.pop("$schema", None)
        cfg["name"] = name
        (root / "galivelop-voices.json").write_text(json.dumps(cfg))
        projects.add(root)
        self.projects[name] = root
        return root

    def code(self, fn, *args, **kwargs):
        with self.assertRaises(GvoiceError) as cm:
            fn(*args, **kwargs)
        return cm.exception.code

    def push(self, project="proj", type_="voice", key="narrator", count=1, **kw):
        """Queue `count` attempts of a voice order (created if missing) or of a line of `narrator`."""
        try:
            orders.get(project, type_, key)
        except GvoiceError:
            if type_ == "voice":
                orders.submit(project, {"key": key, "type": "voice", "testText": "Hello there.",
                                        "designSheet": dict(SHEET)})
            else:
                orders.submit(project, {"key": key, "type": "line", "voice": "narrator", "text": "Long ago."})
        return queue.enqueue_attempts(project, type_, key, orders.attempt_specs(project, type_, key, count, **kw))


class QueueTests(QueueBase):
    def test_enqueue_fields(self):
        entries = self.push(count=2, seed=10)
        self.assertEqual([e["id"] for e in entries], [1, 2])
        first = entries[0]
        self.assertEqual((first["state"], first["kind"], first["seed"], first["project"], first["type"], first["key"]),
                         ("queued", "attempt", 10, "proj", "voice", "narrator"))
        self.assertEqual((first["pid"], first["attemptId"], first["error"], first["cancelRequested"]),
                         (None, None, None, False))
        self.assertEqual(entries[1]["seed"], 11)
        self.assertEqual(first["params"], {"instruct": sheet.build_instruct(SHEET), "testText": "Hello there."})
        self.assertEqual(queue.get(2), entries[1])
        self.assertTrue((self.tmp / "data" / "queue.json").is_file())

    def test_enqueue_line_params(self):
        entry = self.push(type_="line", key="narrator/intro", seed=3)[0]
        self.assertEqual((entry["type"], entry["params"]),
                         ("line", {"text": "Long ago.", "model": "0.6b-base", "voice": "narrator"}))

    def test_enqueue_print_fields(self):
        entry = queue.enqueue_print("proj", "narrator", "1.7b-base", 2)
        self.assertEqual((entry["kind"], entry["state"], entry["voice"], entry["model"], entry["reference"]),
                         ("print", "queued", "narrator", "1.7b-base", 2))
        self.assertNotIn("key", entry)
        self.assertEqual(queue.get(entry["id"]), entry)

    def test_enqueue_print_refused(self):
        for args, code in ((("proj", "ghost", "0.6b-base", 1), "order.unknown_voice"),
                           (("proj", "narrator", "9b-base", 1), "order.model_not_allowed"),
                           (("proj", "narrator", "0.6b-base", 0), "order.spec_invalid"),
                           (("proj", "narrator", "0.6b-base", True), "order.spec_invalid"),
                           (("nope", "narrator", "0.6b-base", 1), "project.unknown")):
            self.assertEqual(self.code(queue.enqueue_print, *args), code, args)
        self.assertEqual(queue.list_entries(), [])

    def test_unknown_order_not_queued(self):
        spec = [{"seed": 1, "instruct": "i", "testText": "t"}]
        self.assertEqual(self.code(queue.enqueue_attempts, "proj", "voice", "narrator", spec), "order.unknown")
        self.assertEqual(queue.list_entries(), [])

    def test_incomplete_spec_queues_nothing(self):
        self.push()
        specs = [{"seed": 1, "instruct": "i", "testText": "t"}, {"seed": 2, "instruct": "i"}]
        with self.assertRaises(GvoiceError) as cm:
            queue.enqueue_attempts("proj", "voice", "narrator", specs)
        self.assertEqual((cm.exception.code, cm.exception.params["missing"]), ("order.spec_invalid", "testText"))
        self.assertEqual(len(queue.list_entries()), 1)  # only the one from push

    def test_bad_machine_profile_at_enqueue(self):
        self.push()
        with mock.patch.dict(os.environ, {"GVOICE_MACHINE_PROFILE": "nope"}):
            self.assertEqual(self.code(self.push, count=1), "machine.missing")
        self.assertEqual(len(queue.list_entries()), 1)

    def test_fifo_across_projects(self):
        self.push("proj")
        self.push("other")
        self.push("proj", key="orc")
        order = []
        while True:
            entry = queue.claim()
            if entry is None:
                break
            order.append((entry["id"], entry["project"]))
            self.assertEqual((entry["state"], entry["pid"]), ("running", os.getpid()))
            self.assertIsNotNone(entry["startedAt"])
            queue.finish(entry["id"], "done", attempt_id=1)
        self.assertEqual(order, [(1, "proj"), (2, "other"), (3, "proj")])
        self.assertIsNone(queue.next_queued())

    def test_empty_queue(self):
        self.assertIsNone(queue.claim())
        self.assertIsNone(queue.next_queued())
        self.assertEqual(queue.list_entries(), [])
        self.assertEqual(self.code(queue.get, 1), "queue.unknown")

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
        self.assertEqual(queue.claim()["id"], 2)

    def test_cancel_running_requests(self):
        self.hold_worker_lock()
        self.push()
        queue.claim()
        entry = queue.cancel(1)
        self.assertEqual((entry["state"], entry["cancelRequested"]), ("running", True))
        self.assertTrue(queue.is_cancel_requested(1))
        queue.finish(1, "cancelled")
        self.assertEqual(queue.get(1)["state"], "cancelled")

    def test_is_cancel_requested_never_recovers(self):
        self.push()
        queue.claim()  # running, and no worker holds the lock: a recovering read would re-queue it
        self.assertFalse(queue.is_cancel_requested(1))
        raw = json.loads((self.tmp / "data" / "queue.json").read_text())
        self.assertEqual(raw["entries"][0]["state"], "running")
        self.assertEqual(self.code(queue.is_cancel_requested, 99), "queue.unknown")

    def test_error_text_renders_schema_errors(self):
        from gvoice import schema
        err = queue.make_error("order.invalid", [schema.ValidationError("/text", "maxLength", {"limit": 4000})])
        self.assertEqual(err["errors"], [{"path": "/text", "code": "maxLength", "params": {"limit": 4000}}])
        text = queue.error_text(err, "en")
        self.assertEqual(text.splitlines()[0], "the order is not valid")
        self.assertIn("/text: must be at most 4000 characters", text)
        self.assertNotIn("errors", queue.make_error("x"))
        for odd in (None, "x", [1], [{"path": 1}], [{"path": "/a", "code": "nope", "params": 3}]):
            self.assertEqual(queue.error_text({"code": "order.invalid", "params": {}, "errors": odd}, "en")
                             .splitlines()[0], "the order is not valid")

    def test_cancel_terminal_and_unknown(self):
        self.push()
        queue.claim()
        queue.finish(1, "failed", error="boom")
        self.assertEqual(self.code(queue.cancel, 1), "queue.not_cancellable")
        self.assertEqual(self.code(queue.cancel, 99), "queue.unknown")
        self.assertEqual(self.code(queue.get, "1"), "queue.unknown")

    def test_finish_rules(self):
        self.push()
        self.assertEqual(self.code(queue.finish, 1, "done"), "queue.not_running")  # still queued
        queue.claim()
        self.assertEqual(self.code(queue.finish, 1, "queued"), "queue.bad_state")
        entry = queue.finish(1, "failed", error=queue.make_error("engine.failed", message="x"))
        self.assertEqual((entry["state"], entry["error"], entry["pid"]),
                         ("failed", {"code": "engine.failed", "params": {"message": "x"}}, None))
        self.assertIsNotNone(entry["finishedAt"])

    def test_recovery_without_worker_lock(self):
        self.push(count=2)
        queue.claim()  # pid is this live process: the pid is irrelevant, only the worker lock counts
        path = self.tmp / "data" / "queue.json"
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["pid"], entry["startedAt"]), ("queued", None, None))
        self.assertEqual(json.loads(path.read_text())["entries"][0]["state"], "queued")  # persisted
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
        self.assertEqual(queue.get(1)["pid"], os.getpid())

    def test_enqueue_also_recovers(self):
        self.push()
        queue.claim()
        self.push(key="orc")
        self.assertEqual(queue.list_entries()[0]["state"], "queued")

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

    def test_recovery_deletes_pending_files(self):
        self.push()
        queue.claim()
        pending = orders.pending_audio_path("proj", "voice", "narrator", 1)
        pending.parent.mkdir(parents=True)
        other = pending.parent / ".pending-2.wav"
        for f in (pending, other):
            f.write_bytes(b"x")
        queue.list_entries()
        self.assertFalse(pending.exists())
        self.assertTrue(other.exists())  # only the recovered entries' files

    def test_recovery_of_a_print_entry(self):
        entry = queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        queue.claim()
        self.assertEqual(queue.get(entry["id"])["state"], "queued")

    def test_error_text(self):
        error = queue.make_error("engine.failed", message="boom")
        self.assertIn("boom", queue.error_text(error, "en"))
        self.assertNotEqual(queue.error_text(error, "es"), queue.error_text(error, "en"))
        self.push()
        queue.claim()
        entry = queue.finish(1, "failed", error=error)
        self.assertEqual(queue.error_text(entry, "en"), queue.error_text(error, "en"))
        self.assertEqual(queue.error_text(queue.make_error("nope.code")), "nope.code")  # unknown: the code
        self.assertEqual(queue.error_text(None), "")

    def test_error_text_odd_shapes(self):
        self.assertEqual(queue.error_text("timeout boom"), "timeout boom")
        self.assertEqual(queue.error_text({"params": {}}), "{'params': {}}")
        self.assertEqual(queue.error_text({"code": "nope.code", "params": [1]}), "nope.code")
        self.assertEqual(json.loads(json.dumps(queue.make_error("x", obj=Path("/a")))),
                         {"code": "x", "params": {"obj": "/a"}})

    def test_prune_keeps_last_200_terminal(self):
        total = queue.KEEP_TERMINAL + 15
        entries = [{"id": i, "kind": "attempt", "project": "proj", "type": "voice", "key": "narrator",
                    "state": "done", "seed": i, "params": {}} for i in range(1, total + 1)]
        entries.append(dict(entries[0], id=total + 1, state="queued"))
        (self.tmp / "data").mkdir(exist_ok=True)
        (self.tmp / "data" / "queue.json").write_text(json.dumps({"nextId": total + 2, "entries": entries}))
        listed = queue.list_entries()
        self.assertEqual(len(listed), queue.KEEP_TERMINAL + 1)
        self.assertEqual(listed[0]["id"], 16)  # the oldest were dropped
        self.assertEqual(listed[-1]["state"], "queued")  # non terminal never dropped
        self.assertEqual(self.push()[0]["id"], total + 2)  # ids keep growing

    def test_corrupt_queue(self):
        (self.tmp / "data").mkdir(exist_ok=True)
        queue_file = self.tmp / "data" / "queue.json"
        queue_file.write_text("{nope")
        self.assertEqual(self.code(queue.list_entries), "queue.corrupt")
        queue_file.write_text(json.dumps({"nextId": 2, "entries": [{"id": 1, "state": "queued"}]}))  # no kind
        self.assertEqual(self.code(queue.list_entries), "queue.corrupt")

    def test_tasks_and_models(self):
        voice = self.push()[0]
        line = self.push(type_="line", key="narrator/intro")[0]
        prn = queue.enqueue_print("proj", "narrator", "1.7b-base", 1)
        profile = {"models": {"design": "1.7b-voicedesign"}}
        self.assertEqual([queue.task_of(e) for e in (voice, line, prn)], ["design", "speak", "print"])
        self.assertEqual([queue.model_of(e, profile) for e in (voice, line, prn)],
                         ["1.7b-voicedesign", "0.6b-base", "1.7b-base"])

    def test_estimate_for(self):
        entry = self.push()[0]
        self.assertIsNone(queue.estimate_for(entry))
        base = {"gen_ai.provider.name": "fake", "app.task": "design", "gen_ai.request.model": "1.7b-voicedesign",
                "app.audio.device": "Vulkan0"}
        for ms in (100, 300, 200):
            log.append("proj", dict(base, **{"app.duration_ms": ms}))
        log.append("proj", dict(base, **{"app.duration_ms": 9999, "app.audio.device": "cpu"}))  # other device
        log.append("proj", dict(base, **{"app.duration_ms": 1, "app.task": "speak"}))  # other task
        self.assertEqual(queue.estimate_for(entry), 200)
        self.assertIsNone(queue.estimate_for(entry, provider="qwen-tts"))

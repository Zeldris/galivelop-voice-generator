# Copiado de gimg@0d02f51 (D7); cambia: entradas attempt (voice, line) y print, audio .wav, candado de la máquina
# alrededor del motor, comprobación de que el pedido y la voz siguen en el proyecto, y casos nuevos (cancelar
# esperando el candado, candado solo alrededor del motor, pedido o voz borrados, huellas).
import fcntl
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from gvoice import engine, log, machinelock, orders, projects, queue, worker
from gvoice.errors import GvoiceError
from tests.test_queue import QueueBase


class StubEngine(engine.Engine):
    provider = "fake"

    def __init__(self, error=None):
        self.error = error

    def design(self, job, should_cancel):
        raise self.error

    speak = extract_print = design


def hold_machine_lock(test):
    """Hold the machine lock from this test (another generator is using the GPU); returns a release function."""
    fd = machinelock._open()
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {"open": True}

    def release():
        if state["open"]:
            state["open"] = False
            os.close(fd)

    test.addCleanup(release)
    return release


def wait_for(test, check, seconds=5):
    deadline = time.monotonic() + seconds
    while not check() and time.monotonic() < deadline:
        time.sleep(0.01)
    test.assertTrue(check(), "timed out")


class WorkerBase(QueueBase):
    def lines(self, project="proj"):
        path = log.log_path(project)
        if not path.exists():
            return []
        return [json.loads(x) for x in path.read_text().splitlines()]

    def leftovers(self):
        return [p for p in (self.tmp / "data" / "projects").rglob("*")
                if p.is_file() and p.suffix == ".tmp" or p.name.startswith(".pending")]

    def attempts(self, type_="voice", key="narrator", project="proj"):
        return orders.get(project, type_, key)["attempts"]

    def voice_dir(self, voice="narrator", project="proj"):
        return self.tmp / "data" / "projects" / project / "voices" / voice

    def write_reference(self, voice="narrator", text="Hello there."):
        folder = self.voice_dir(voice)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "reference.wav").write_bytes(engine.wav_bytes(5, 200))
        (folder / "reference.txt").write_text(text, encoding="utf-8")

    def fix_voice(self, model="0.6b-base", reference=1):
        """Queue and run the print of narrator for `model`, as choosing a reference will (F1.5)."""
        self.write_reference()
        entry = queue.enqueue_print("proj", "narrator", model, reference)
        worker.run()
        self.assertEqual(queue.get(entry["id"])["state"], "done")
        return entry

    def run_in_thread(self, **kw):
        thread = threading.Thread(target=worker.run, kwargs=kw)
        thread.start()
        self.addCleanup(thread.join, 10)
        return thread


class AttemptTests(WorkerBase):
    def test_success_voice(self):
        self.push(count=2, seed=7)
        self.assertEqual(worker.run(), 2)
        for n in (1, 2):
            entry = queue.get(n)
            self.assertEqual((entry["state"], entry["attemptId"], entry["error"]), ("done", n, None))
        attempts = self.attempts()
        self.assertEqual([a["id"] for a in attempts], [1, 2])
        self.assertEqual(attempts[1]["seed"], 8)
        a = attempts[0]
        self.assertEqual((a["audio"], a["queueEntry"], a["state"], a["engine"], a["engineVersion"], a["device"],
                          a["model"], a["testText"]),
                         ("attempts/q1.wav", 1, "new", "fake", engine.FAKE_VERSION, "Vulkan0",
                          "1.7b-voicedesign", "Hello there."))
        with wave.open(str(orders.attempt_audio("proj", "voice", "narrator", a))) as w:
            self.assertEqual((w.getframerate(), w.getnchannels()), (24000, 1))
            self.assertEqual(w.getnframes(), 24000 * len("Hello there.") * engine.FAKE_MS_PER_CHAR // 1000)
        names = {p.name for p in orders.pending_audio_path("proj", "voice", "narrator", 1).parent.iterdir()}
        self.assertEqual(names, {"q1.wav", "q2.wav"})  # no temp left
        lines = self.lines()
        self.assertEqual(len(lines), 2)
        first = lines[0]
        self.assertNotIn("app.error", first)
        self.assertEqual((first["gen_ai.provider.name"], first["app.task"], first["app.audio.key"],
                          first["app.audio.seed"], first["app.machine_profile"], first["app.audio.device"],
                          first["gen_ai.request.model"], first["app.audio.text_chars"],
                          first["app.audio.engine_version"], first["app.audio.audio_ms"]),
                         ("fake", "design", "narrator", 7, "steam-deck", "Vulkan0", "1.7b-voicedesign", 12,
                          engine.FAKE_VERSION, 12 * engine.FAKE_MS_PER_CHAR))
        self.assertIn("app.duration_ms", first)
        self.assertIn("app.audio.rtf", first)

    def test_empty_queue(self):
        self.assertEqual(worker.run(), 0)
        self.assertEqual(worker.run(once=True), 0)
        self.assertEqual(self.lines(), [])

    def test_once(self):
        self.push(count=3)
        self.assertEqual(worker.run(once=True), 1)
        self.assertEqual([e["state"] for e in queue.list_entries()], ["done", "queued", "queued"])
        self.assertEqual(worker.run(), 2)

    def test_fifo_across_projects(self):
        self.push("proj")
        self.push("other")
        worker.run()
        self.assertEqual([(e["project"], e["state"]) for e in queue.list_entries()],
                         [("proj", "done"), ("other", "done")])
        self.assertEqual(len(self.lines("proj")), 1)
        self.assertEqual(len(self.lines("other")), 1)

    def test_engine_from_env(self):
        self.push()
        with mock.patch.dict(os.environ, {"GVOICE_FAKE_FAIL": "out of vram"}):
            worker.run()
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]),
                         ("failed", {"code": "engine.failed", "params": {"message": "out of vram"}}))

    def test_engine_failure(self):
        self.push()
        worker.run(engine=engine.FakeEngine(fail_with="boom"))
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"], entry["attemptId"]),
                         ("failed", {"code": "engine.failed", "params": {"message": "boom"}}, None))
        self.assertEqual(self.attempts(), [])
        self.assertEqual(self.lines()[0]["app.error"], "the engine failed: boom")
        self.assertEqual(self.lines()[0]["app.task"], "design")
        self.assertNotIn("app.duration_ms", self.lines()[0])
        self.assertEqual(self.leftovers(), [])

    def test_timeout_from_engine(self):
        self.push()
        worker.run(engine=StubEngine(engine.EngineTimeout()))
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]), ("failed", {"code": "engine.timeout", "params": {}}))
        self.assertEqual(self.lines()[0]["app.error"], queue.error_text(entry["error"], "en"))

    def test_real_timeout_from_the_machine_profile(self):
        profile = self.tmp / "short.json"
        profile.write_text(json.dumps({"name": "short", "minFreeMemoryMb": 1, "watchMemoryMb": 1, "timeoutS": 1,
                                       "engine": {"device": "cpu"},
                                       "models": {"design": "1.7b-voicedesign", "produce": ["0.6b-base"]}}))
        self.push()
        started = time.monotonic()
        with mock.patch.dict(os.environ, {"GVOICE_MACHINE_PROFILE": str(profile), "GVOICE_FAKE_DELAY": "30"}):
            worker.run()
        self.assertLess(time.monotonic() - started, 10)
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "engine.timeout"))
        self.assertEqual(self.attempts(), [])
        self.assertEqual(self.leftovers(), [])

    def test_timeout_s_and_device_come_from_machine(self):
        seen = []

        class Spy(engine.FakeEngine):
            def design(self, job, should_cancel):
                seen.append((job.timeout_s, job.device, job.model))
                return super().design(job, should_cancel)

        self.push()
        worker.run(engine=Spy())
        self.assertEqual(seen, [(900, "Vulkan0", "1.7b-voicedesign")])

    def test_unexpected_error_fails_entry_and_continues(self):
        self.push(count=2)
        worker.run(engine=StubEngine(ValueError("bug")))
        self.assertEqual([(e["state"], e["error"]) for e in queue.list_entries()],
                         [("failed", {"code": "worker.unexpected", "params": {"message": "ValueError: bug"}})] * 2)

    def test_machine_profile_rechecked_at_run(self):
        self.push()
        with mock.patch.dict(os.environ, {"GVOICE_MACHINE_PROFILE": "nope"}):
            worker.run()
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "machine.missing"))
        self.assertEqual(self.attempts(), [])

    # ---- cancelling: in the queue, waiting for the machine lock, during the engine, after it

    def test_cancelled_queued_is_skipped(self):
        self.push(count=2)
        queue.cancel(1)
        self.assertEqual(worker.run(), 1)
        self.assertEqual([e["state"] for e in queue.list_entries()], ["cancelled", "done"])
        self.assertEqual(len(self.lines()), 1)

    def test_cancel_running_during_the_engine(self):
        self.push()
        thread = self.run_in_thread(engine=engine.FakeEngine(delay_s=5))
        wait_for(self, lambda: queue.get(1)["state"] == "running")
        started = time.monotonic()
        queue.cancel(1)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertLess(time.monotonic() - started, 2)
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["attemptId"]), ("cancelled", None))
        self.assertEqual(self.attempts(), [])
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.leftovers(), [])

    def test_cancel_while_waiting_for_the_machine_lock(self):
        release = hold_machine_lock(self)
        self.push(count=2)

        class Spy(engine.FakeEngine):
            calls = 0

            def design(self, job, should_cancel):
                Spy.calls += 1
                return super().design(job, should_cancel)

        thread = self.run_in_thread(engine=Spy())
        wait_for(self, lambda: queue.get(1)["state"] == "running")
        time.sleep(0.3)  # it is waiting for the lock, not running the engine
        self.assertEqual(Spy.calls, 0)
        self.assertEqual(queue.get(1)["state"], "running")
        started = time.monotonic()
        queue.cancel(1)
        wait_for(self, lambda: queue.get(1)["state"] == "cancelled")
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(Spy.calls, 0)
        self.assertEqual(self.attempts(), [])
        self.assertEqual(self.lines(), [])
        release()  # the second entry then gets the lock and runs
        thread.join(10)
        self.assertEqual(queue.get(2)["state"], "done")
        self.assertEqual(Spy.calls, 1)

    def test_waits_for_the_machine_lock_then_runs(self):
        release = hold_machine_lock(self)
        self.push()
        thread = self.run_in_thread()
        wait_for(self, lambda: queue.get(1)["state"] == "running")
        time.sleep(0.3)
        self.assertEqual(self.attempts(), [])
        release()
        thread.join(10)
        self.assertEqual(queue.get(1)["state"], "done")
        self.assertEqual(len(self.attempts()), 1)

    def test_machine_lock_only_around_the_engine(self):
        held = []

        def free():  # another process could take the lock now?
            fd = machinelock._open()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                return False
            finally:
                os.close(fd)

        class Spy(engine.FakeEngine):
            def design(self, job, should_cancel):
                held.append(("engine", not free()))
                return super().design(job, should_cancel)

        real_add = orders.add_attempt

        def add(*args, **kwargs):
            held.append(("add_attempt", not free()))
            return real_add(*args, **kwargs)

        held.append(("before", not free()))
        self.push()
        with mock.patch.object(orders, "add_attempt", side_effect=add):
            worker.run(engine=Spy())
        held.append(("after", not free()))
        self.assertEqual(held, [("before", False), ("engine", True), ("add_attempt", False), ("after", False)])

    def test_machine_lock_released_when_the_engine_fails(self):
        self.push()
        worker.run(engine=StubEngine(RuntimeError("bug")))
        fd = machinelock._open()
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # would raise if the worker still held it

    def test_cancel_requested_after_generation_leaves_no_audio(self):
        self.push()

        class Late(engine.FakeEngine):
            def design(self, job, should_cancel):
                result = super().design(job, lambda: False)
                queue.cancel(1)
                return result

        worker.run(engine=Late())
        self.assertEqual(queue.get(1)["state"], "cancelled")
        self.assertEqual(self.attempts(), [])
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.leftovers(), [])

    # ---- one worker at a time, dead workers

    def test_second_worker_refused_same_process(self):
        worker.lock_path().parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(worker.lock_path()), os.O_RDWR | os.O_CREAT)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        self.push()
        self.assertEqual(self.code(worker.run), "worker.already_running")
        self.assertEqual(queue.get(1)["state"], "queued")  # nothing was taken

    def test_two_workers_at_once_in_two_processes(self):
        self.push(count=2)
        code = ("from gvoice import worker, engine\n"
                "worker.run(engine=engine.FakeEngine(delay_s=3))\n")
        proc = subprocess.Popen([sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parent.parent),
                                env=dict(os.environ))
        try:
            wait_for(self, lambda: queue.get(1)["state"] == "running", 10)
            self.assertEqual(queue.get(1)["pid"], proc.pid)
            self.assertEqual(self.code(worker.run), "worker.already_running")
            queue.cancel(1)
            queue.cancel(2)
            proc.wait(10)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        self.assertEqual([queue.get(n)["state"] for n in (1, 2)], ["cancelled", "cancelled"])
        self.assertEqual(worker.run(), 0)  # the lock is free again

    def test_lock_released_after_run(self):
        worker.run()
        worker.run()

    def test_worker_killed_midway_leaves_a_running_entry_that_runs_again(self):
        self.push()
        code = ("from gvoice import worker, engine\n"
                "worker.run(engine=engine.FakeEngine(delay_s=30))\n")
        proc = subprocess.Popen([sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parent.parent),
                                env=dict(os.environ))
        try:
            wait_for(self, lambda: queue.get(1)["state"] == "running", 10)
            proc.kill()
            proc.wait(10)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(queue.get(1)["state"], "queued")  # the worker lock died with it: recovered on read
        self.assertEqual(worker.run(), 1)
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["attemptId"]), ("done", 1))

    def test_dead_worker_entry_is_run_again(self):
        self.push()
        queue.claim()  # its pid is this live process: only the worker lock decides
        self.assertEqual(worker.run(), 1)
        self.assertEqual(queue.get(1)["state"], "done")

    def test_worker_recovers_and_deletes_pending_before_its_loop(self):
        self.push()
        queue.claim()
        pending = orders.pending_audio_path("proj", "voice", "narrator", 1)
        pending.parent.mkdir(parents=True)
        pending.write_bytes(b"half")
        seen = []

        class Spy(engine.FakeEngine):
            def design(self, job, should_cancel):
                seen.append(Path(job.output).exists())
                return super().design(job, should_cancel)

        worker.run(engine=Spy())
        self.assertEqual(seen, [False])
        self.assertEqual(queue.get(1)["state"], "done")
        self.assertEqual(self.leftovers(), [])

    def test_crash_after_add_attempt_does_not_duplicate(self):
        self.push()
        with mock.patch.object(queue, "finish", side_effect=KeyboardInterrupt):  # a hard stop, not an Exception
            with self.assertRaises(KeyboardInterrupt):
                worker.run()
        self.assertEqual(len(self.attempts()), 1)
        self.assertEqual(queue.get(1)["state"], "queued")  # recovery: the worker is gone
        worker.run(engine=StubEngine(AssertionError("the engine must not run again")))
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["attemptId"], entry["error"]), ("done", 1, None))
        attempts = self.attempts()
        self.assertEqual([(a["id"], a["queueEntry"]) for a in attempts], [(1, 1)])
        self.assertTrue(orders.attempt_audio("proj", "voice", "narrator", attempts[0]).is_file())
        self.assertEqual(len(self.lines()), 1)

    def test_failing_finish_done_keeps_loop_and_writes_no_failure_line(self):
        self.push(count=2)
        real = queue.finish
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args[0])
            if len(calls) == 1:
                raise GvoiceError("queue.corrupt", path="x")
            return real(*args, **kwargs)

        with mock.patch.object(queue, "finish", side_effect=flaky):
            self.assertEqual(worker.run(), 2)
        self.assertEqual(calls, [1, 2])
        lines = self.lines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all("app.error" not in x for x in lines))
        self.assertEqual(queue.get(2)["state"], "done")
        self.assertEqual(queue.get(1)["state"], "queued")  # was left running; the next recovery re-queues it
        worker.run()
        self.assertEqual(len(self.attempts()), 2)  # no duplicate for entry 1
        self.assertEqual(queue.get(1)["state"], "done")

    def test_failing_finish_in_failure_handler_keeps_loop(self):
        self.push(count=2)
        real = queue.finish
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args[0])
            if len(calls) == 1:
                raise GvoiceError("queue.corrupt", path="x")
            return real(*args, **kwargs)

        with mock.patch.object(queue, "finish", side_effect=flaky):
            self.assertEqual(worker.run(engine=engine.FakeEngine(fail_with="boom")), 2)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(queue.get(2)["error"]["code"], "engine.failed")

    def test_schema_errors_survive_in_the_entry_error(self):
        from gvoice import schema
        self.push()
        boom = GvoiceError("order.invalid", errors=[schema.ValidationError("/text", "maxLength", {"limit": 4000})])
        worker.run(engine=StubEngine(boom))
        entry = queue.get(1)
        self.assertEqual(entry["error"]["errors"][0]["path"], "/text")
        self.assertIn("/text: must be at most 4000 characters", queue.error_text(entry, "en"))

    def finish_message(self, lang):
        self.push()
        with mock.patch.object(queue, "finish", side_effect=GvoiceError("queue.corrupt", path="x")), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            worker.run(lang=lang, once=True)
        return err.getvalue()

    def test_worker_messages_use_the_given_language(self):
        self.assertIn("could not finish queue entry 1", self.finish_message("en"))

    def test_worker_messages_in_spanish(self):
        self.assertIn("no se pudo cerrar la entrada 1", self.finish_message("es"))

    def test_failing_log_line_does_not_fail_the_entry(self):
        self.push()
        with mock.patch.object(log, "append", side_effect=OSError("disk full")):
            worker.run()
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["attemptId"], entry["error"]), ("done", 1, None))

    def test_add_attempt_failure_leaves_no_audio(self):
        self.push()
        with mock.patch.object(orders, "add_attempt", side_effect=GvoiceError("order.corrupt", path="x")):
            worker.run()
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "order.corrupt"))
        self.assertEqual(self.leftovers(), [])
        self.assertEqual([p.name for p in orders.pending_audio_path("proj", "voice", "narrator", 1).parent.iterdir()],
                         [])

    def test_estimate_after_runs(self):
        entry = self.push(count=3)[0]
        self.assertIsNone(queue.estimate_for(entry))
        worker.run()
        estimate = queue.estimate_for(entry)
        self.assertIsNotNone(estimate)
        durations = sorted(x["app.duration_ms"] for x in self.lines())
        self.assertEqual(estimate, durations[1])
        worker.run(engine=engine.FakeEngine(fail_with="x"))  # errors do not count
        self.assertEqual(queue.estimate_for(entry), estimate)


class GoneTests(WorkerBase):
    """The order or the voice may disappear between enqueue and run."""

    def failed(self, code):
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", code))
        self.assertIsNone(entry["attemptId"])
        self.assertEqual(self.leftovers(), [])
        return entry

    def test_order_deleted_between_enqueue_and_run(self):
        self.push()
        shutil.rmtree(orders._order_dir("proj", "voice", "narrator"))
        self.assertEqual(worker.run(), 1)
        entry = self.failed("order.unknown")
        self.assertIn("narrator", queue.error_text(entry, "en"))
        self.assertIn("no existe el pedido", queue.error_text(entry, "es"))
        self.assertEqual(self.lines()[0]["app.error"], queue.error_text(entry, "en"))

    def test_one_deleted_order_does_not_stop_the_others(self):
        self.push(key="narrator")
        self.push(key="orc")
        shutil.rmtree(orders._order_dir("proj", "voice", "narrator"))
        worker.run()
        self.assertEqual([e["state"] for e in queue.list_entries()], ["failed", "done"])

    def set_voices(self, voices):
        root = self.projects["proj"]
        cfg = json.loads((root / "galivelop-voices.json").read_text())
        cfg["voices"] = voices
        (root / "galivelop-voices.json").write_text(json.dumps(cfg))

    def test_voice_removed_from_the_project(self):
        self.push()
        self.set_voices({"orc": {}})
        worker.run()
        entry = self.failed("order.unknown_voice")
        self.assertIn("narrator", queue.error_text(entry, "es"))

    def test_voice_of_a_line_removed_from_the_project(self):
        self.push(type_="line", key="narrator/intro")
        self.set_voices({"orc": {}})
        worker.run()
        self.failed("order.unknown_voice")

    def test_voice_of_a_print_removed_from_the_project(self):
        self.write_reference()
        queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        self.set_voices({"orc": {}})
        worker.run()
        self.failed("order.unknown_voice")

    def test_project_removed(self):
        self.push()
        projects.remove("proj")
        worker.run()
        self.failed("project.unknown")
        self.assertEqual([x["app.error"] for x in self.lines()], ['no registered project is named "proj"'])

    def test_gone_check_runs_before_the_machine_lock_and_the_engine(self):
        hold_machine_lock(self)  # if the worker waited for the lock the thread would not end
        self.push()
        shutil.rmtree(orders._order_dir("proj", "voice", "narrator"))
        thread = self.run_in_thread(engine=StubEngine(AssertionError("the engine must not run")))
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.failed("order.unknown")


class LineAndPrintTests(WorkerBase):
    def test_line_without_a_print_fails_and_is_translated(self):
        self.push(type_="line", key="narrator/intro")
        worker.run()
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]),
                         ("failed", {"code": "worker.voice_not_fixed",
                                     "params": {"voice": "narrator", "model": "0.6b-base"}}))
        self.assertIn("no tiene una huella al día", queue.error_text(entry, "es"))
        self.assertIn("no up-to-date print", queue.error_text(entry, "en"))
        self.assertEqual(self.lines()[0]["app.task"], "speak")
        self.assertEqual(self.attempts("line", "narrator/intro"), [])

    def test_print_then_line(self):
        self.fix_voice("0.6b-base", reference=4)
        folder = self.voice_dir() / "prints"
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["0.6b-base.json", "0.6b-base.rvq", "0.6b-base.spk"])
        marker = json.loads((folder / "0.6b-base.json").read_text())
        self.assertEqual((marker["reference"], marker["device"], marker["engineVersion"]),
                         (4, "Vulkan0", engine.FAKE_VERSION))
        self.assertIn("createdAt", marker)
        self.assertEqual(self.lines()[0]["app.task"], "print")
        self.assertEqual(self.lines()[0]["app.audio.key"], "narrator")
        self.assertEqual(self.lines()[0]["gen_ai.request.model"], "0.6b-base")
        self.push(type_="line", key="narrator/intro", seed=9)
        worker.run()
        entry = queue.get(2)
        self.assertEqual((entry["state"], entry["attemptId"]), ("done", 1), entry["error"])
        a = self.attempts("line", "narrator/intro")[0]
        self.assertEqual((a["voiceReference"], a["model"], a["text"], a["seed"], a["device"], a["engine"],
                          a["audio"], a["state"]),
                         (4, "0.6b-base", "Long ago.", 9, "Vulkan0", "fake", "attempts/q2.wav", "new"))
        last = self.lines()[1]
        self.assertEqual((last["app.task"], last["app.audio.key"], last["app.audio.text_chars"]),
                         ("speak", "narrator/intro", 9))

    def test_line_for_a_model_without_a_print(self):
        self.fix_voice("1.7b-base")  # the line asks for the first print model, 0.6b-base
        self.push(type_="line", key="narrator/intro")
        worker.run()
        self.assertEqual(queue.get(2)["error"]["code"], "worker.voice_not_fixed")

    def test_line_with_a_print_without_marker_fails(self):
        self.fix_voice()
        (self.voice_dir() / "prints" / "0.6b-base.json").unlink()
        self.push(type_="line", key="narrator/intro")
        worker.run()
        self.assertEqual(queue.get(2)["error"]["code"], "worker.voice_not_fixed")

    def test_print_without_a_reference_fails_and_touches_nothing(self):
        self.fix_voice()
        (self.voice_dir() / "reference.wav").unlink()
        queue.enqueue_print("proj", "narrator", "0.6b-base", 2)
        worker.run()
        entry = queue.get(2)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "worker.reference_missing"))
        self.assertTrue((self.voice_dir() / "prints" / "0.6b-base.json").is_file())  # the old print is intact

    def test_print_engine_failure_discards_the_files(self):
        self.write_reference()
        queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        worker.run(engine=engine.FakeEngine(fail_with="boom"))
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "engine.failed"))
        self.assertFalse((self.voice_dir() / "prints" / "0.6b-base.json").exists())
        self.assertEqual(list((self.voice_dir() / "prints").glob("*")), [])
        self.assertEqual(self.lines()[0]["app.error"], "the engine failed: boom")

    def test_failed_reprint_does_not_leave_the_old_marker(self):
        self.fix_voice(reference=1)
        queue.enqueue_print("proj", "narrator", "0.6b-base", 2)
        worker.run(engine=engine.FakeEngine(fail_with="boom"))
        self.assertEqual(list((self.voice_dir() / "prints").glob("*")), [])
        self.push(type_="line", key="narrator/intro")
        worker.run()
        self.assertEqual(queue.get(3)["error"]["code"], "worker.voice_not_fixed")

    def test_cancel_a_print_during_the_engine(self):
        self.write_reference()
        queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        thread = self.run_in_thread(engine=engine.FakeEngine(delay_s=5))
        wait_for(self, lambda: queue.get(1)["state"] == "running")
        queue.cancel(1)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(queue.get(1)["state"], "cancelled")
        self.assertEqual(list((self.voice_dir() / "prints").glob("*")), [])
        self.assertEqual(self.lines(), [])

    def test_cancel_a_print_waiting_for_the_machine_lock(self):
        hold_machine_lock(self)
        self.write_reference()
        queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        thread = self.run_in_thread()
        wait_for(self, lambda: queue.get(1)["state"] == "running")
        time.sleep(0.2)
        queue.cancel(1)
        wait_for(self, lambda: queue.get(1)["state"] == "cancelled")
        thread.join(5)
        self.assertEqual(self.lines(), [])

    def test_print_takes_the_machine_lock_around_the_engine(self):
        seen = []

        class Spy(engine.FakeEngine):
            def extract_print(self, job, should_cancel):
                fd = machinelock._open()
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    seen.append("free")
                except BlockingIOError:
                    seen.append("held")
                finally:
                    os.close(fd)
                return super().extract_print(job, should_cancel)

        self.write_reference()
        queue.enqueue_print("proj", "narrator", "0.6b-base", 1)
        worker.run(engine=Spy())
        self.assertEqual(seen, ["held"])


if __name__ == "__main__":
    unittest.main()

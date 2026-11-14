import io
import os
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from gvoice import engine, limits, log, machine_lock, orders, paths, queue, worker
from gvoice.errors import GvoiceError
from tests.test_machine_lock import HOLDER, ROOT
from tests.test_queue import QueueBase


def log_lines(project="world"):
    return list(log._lines(log.log_path(project)))


class WorkerBase(QueueBase):
    def run_worker(self, **kw):
        return worker.run(engine=kw.pop("engine", engine.FakeEngine()), lang="en", **kw)

    def attempt(self, key, take):
        return next(a for a in orders.get(self.p, key)["attempts"] if a["id"] == take)

    def voice_done(self):
        """A voice take made by the worker and chosen, its prints made too; returns the take id."""
        orders.submit(self.p, self.voice())
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator", seed=7))
        self.run_worker()
        take = orders.get(self.p, "narrator")["attempts"][0]["id"]
        queue.choose(self.p, "narrator", take)
        self.run_worker()
        return take

    def foreign_holder(self):
        path = paths.machine_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(path)], stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc


class VoiceTakeTests(WorkerBase):
    def test_voice_take_in_arrival_order(self):
        self.push("narrator", count=2, seed=5)
        self.assertEqual(self.run_worker(), 2)
        entries = queue.list_entries()
        self.assertEqual([(e["id"], e["state"], e["attemptId"]) for e in entries], [(1, "done", 1), (2, "done", 2)])
        attempts = orders.get(self.p, "narrator")["attempts"]
        self.assertEqual([a["seed"] for a in attempts], [5, 6])
        for a in attempts:
            self.assertTrue(orders.attempt_audio(self.p, "narrator", a).is_file())
        self.assertLessEqual(entries[0]["finishedAt"], entries[1]["finishedAt"])
        self.assertLessEqual(entries[0]["startedAt"], entries[1]["startedAt"])

    def test_no_pending_leftovers(self):
        self.push()
        self.run_worker()
        self.assertFalse(orders.pending_audio_path(self.p, "narrator", 1).exists())
        self.assertTrue(orders.attempt_audio(self.p, "narrator", orders.get(self.p, "narrator")["attempts"][0]).is_file())

    def test_once_handles_one(self):
        self.push(count=2)
        self.assertEqual(self.run_worker(once=True), 1)
        self.assertEqual([e["state"] for e in queue.list_entries()], ["done", "queued"])

    def test_empty_queue(self):
        self.assertEqual(self.run_worker(), 0)

    def test_d16_log_line(self):
        self.push(seed=42)
        self.run_worker()
        line, = log_lines()
        self.assertEqual(line["gen_ai.operation.name"], log.OP_DESIGN)
        self.assertEqual(line["gen_ai.provider.name"], "fake")
        self.assertEqual(line["gen_ai.request.model"], "1.7b-voicedesign")
        self.assertEqual((line["app.task"], line["app.voice.key"], line["app.voice.seed"]), ("voice", "narrator", 42))
        self.assertEqual(line["app.machine_profile"], "steam-deck")
        self.assertEqual(line["app.voice.device"], "Vulkan0")
        self.assertEqual(line["app.voice.engine_commit"], engine.FAKE_COMMIT)
        self.assertNotIn("app.error", line)

    def test_engine_failure_is_recorded_with_its_reason(self):
        self.push()
        self.run_worker(engine=engine.FakeEngine(fail_with="boom"))
        entry = queue.get(1)
        self.assertEqual(entry["state"], "failed")
        self.assertIn("boom", queue.error_text(entry["error"], "en"))
        self.assertEqual(orders.get(self.p, "narrator")["attempts"], [])
        line, = log_lines()
        self.assertIn("boom", line["app.error"])
        self.assertFalse(orders.pending_audio_path(self.p, "narrator", 1).exists())

    def test_one_failure_does_not_stop_the_next(self):
        self.push(count=2)
        real = engine.FakeEngine.design
        calls = []

        def flaky(self_, job, should_cancel):
            calls.append(1)
            if len(calls) == 1:
                raise engine.EngineError("first")
            return real(self_, job, should_cancel)

        with mock.patch.object(engine.FakeEngine, "design", flaky):
            self.assertEqual(self.run_worker(), 2)
        self.assertEqual([e["state"] for e in queue.list_entries()], ["failed", "done"])

    def test_timeout(self):
        self.push()
        machine = dict(limits.load_machine(), timeoutS=1)
        with mock.patch("gvoice.limits.load_machine", return_value=machine):
            self.run_worker(engine=engine.FakeEngine(delay_s=5))
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "engine.timeout"))

    def test_unexpected_exception_fails_the_entry_not_the_loop(self):
        self.push(count=2)
        real = engine.FakeEngine.design
        calls = []

        def bad(self_, job, should_cancel):
            calls.append(1)
            if len(calls) == 1:
                raise ZeroDivisionError("bug")
            return real(self_, job, should_cancel)

        with mock.patch.object(engine.FakeEngine, "design", bad):
            self.assertEqual(self.run_worker(), 2)
        first = queue.get(1)
        self.assertEqual((first["state"], first["error"]["code"]), ("failed", "worker.unexpected"))
        self.assertEqual(queue.get(2)["state"], "done")

    def test_order_removed_fails_the_entry(self):
        self.push()
        with mock.patch.object(orders, "get", side_effect=GvoiceError("order.unknown", key="narrator")):
            self.run_worker()
        self.assertEqual(queue.get(1)["error"]["code"], "order.unknown")

    def test_a_take_already_stored_is_not_made_twice(self):
        # a worker that died between add_attempt and finish: recovery requeues, the retry adds nothing
        self.push()
        with mock.patch.object(queue, "finish", side_effect=GvoiceError("queue.unknown", id=1)):
            self.run_worker()
        self.assertEqual(len(orders.get(self.p, "narrator")["attempts"]), 1)
        self.run_worker()  # entry 1 is running without a live worker: recovered and redone
        self.assertEqual(len(orders.get(self.p, "narrator")["attempts"]), 1)
        self.assertEqual(queue.get(1)["state"], "done")


class CancelTests(WorkerBase):
    def test_cancel_while_the_engine_runs(self):
        self.push()
        thread = threading.Thread(target=self.run_worker, kwargs={"engine": engine.FakeEngine(delay_s=10)})
        thread.start()
        for _ in range(100):
            if queue.get(1)["state"] == "running":
                break
            time.sleep(0.02)
        time.sleep(0.2)
        queue.cancel(1)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(queue.get(1)["state"], "cancelled")
        self.assertEqual(orders.get(self.p, "narrator")["attempts"], [])
        self.assertEqual(log_lines(), [])

    def test_cancel_while_waiting_for_the_machine(self):
        self.foreign_holder()
        self.push()
        thread = threading.Thread(target=self.run_worker)
        thread.start()
        for _ in range(100):
            if queue.get(1)["state"] == "running":
                break
            time.sleep(0.02)
        time.sleep(0.2)
        self.assertEqual(queue.get(1)["state"], "running")
        queue.cancel(1)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(queue.get(1)["state"], "cancelled")

    def test_cancelled_queued_entry_is_skipped(self):
        self.push(count=2)
        queue.cancel(1)
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual([e["state"] for e in queue.list_entries()], ["cancelled", "done"])


class SingleWorkerTests(WorkerBase):
    def test_second_worker_is_refused(self):
        self.push()
        self.hold_worker_lock()
        with self.assertRaises(GvoiceError) as cm:
            self.run_worker()
        self.assertEqual(cm.exception.code, "worker.already_running")
        self.assertEqual(queue.get(1)["state"], "queued")

    def test_two_processes_one_wins(self):
        code = ("from gvoice import worker, engine\n"
                "import sys\n"
                "try:\n"
                "    worker.run(engine=engine.FakeEngine(delay_s=1.5))\n"
                "except Exception as e:\n"
                "    print(getattr(e, 'code', e)); sys.exit(3)\n")
        self.push()
        env = dict(os.environ)
        first = subprocess.Popen([sys.executable, "-c", code], env=env, cwd=str(ROOT), stdout=subprocess.PIPE,
                                 text=True)
        self.addCleanup(first.stdout.close)
        self.addCleanup(first.wait)
        self.addCleanup(first.kill)
        for _ in range(200):
            if queue.worker_alive():
                break
            time.sleep(0.02)
        second = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                                cwd=str(ROOT))
        self.assertEqual((second.returncode, second.stdout.strip()), (3, "worker.already_running"))
        first.wait(10)
        self.assertEqual(queue.get(1)["state"], "done")

    def test_restart_after_a_crash_resumes(self):
        self.push(count=2)
        queue.claim()  # a worker that took entry 1 and died: running, no worker lock
        self.assertEqual(self.run_worker(), 2)
        self.assertEqual([e["state"] for e in queue.list_entries()], ["done", "done"])

    def test_killed_worker_leaves_no_lock_and_the_job_is_redone(self):
        code = ("from gvoice import worker, engine\n"
                "worker.run(engine=engine.FakeEngine(delay_s=30))\n")
        self.push()
        proc = subprocess.Popen([sys.executable, "-c", code], env=dict(os.environ), cwd=str(ROOT))
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        for _ in range(250):
            if machine_lock.busy():
                break
            time.sleep(0.02)
        self.assertTrue(machine_lock.busy())
        self.assertTrue(queue.worker_alive())
        proc.kill()
        proc.wait()
        self.assertFalse(machine_lock.busy())  # the kernel let go of both locks
        self.assertFalse(queue.worker_alive())
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(queue.get(1)["state"], "done")


class MachineLockTests(WorkerBase):
    def test_busy_lock_makes_the_job_wait_not_fail(self):
        proc = self.foreign_holder()
        self.push()
        thread = threading.Thread(target=self.run_worker)
        thread.start()
        time.sleep(0.5)
        self.assertEqual(queue.get(1)["state"], "running")
        self.assertEqual(orders.get(self.p, "narrator")["attempts"], [])
        proc.kill()
        proc.wait()
        thread.join(10)
        self.assertEqual(queue.get(1)["state"], "done")
        self.assertEqual(len(orders.get(self.p, "narrator")["attempts"]), 1)

    def test_the_lock_is_held_during_the_engine_and_freed_after(self):
        self.push()
        seen = []
        real = engine.FakeEngine.design

        def spy(self_, job, should_cancel):
            seen.append(machine_lock.busy())
            return real(self_, job, should_cancel)

        with mock.patch.object(engine.FakeEngine, "design", spy):
            self.run_worker()
        self.assertEqual(seen, [True])
        self.assertFalse(machine_lock.busy())

    def test_the_lock_is_freed_after_a_failure(self):
        self.push()
        self.run_worker(engine=engine.FakeEngine(fail_with="x"))
        self.assertFalse(machine_lock.busy())

    def test_unwritable_state_folder_fails_the_job_with_its_reason(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        self.push()
        with mock.patch.dict(os.environ, {"GVOICE_STATE_HOME": str(blocker / "sub")}):
            self.run_worker()
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "machine_lock.unavailable"))
        self.assertIn("gpu.lock", queue.error_text(entry["error"], "en"))


class PrintsTests(WorkerBase):
    def test_choosing_makes_a_print_per_model(self):
        take = self.voice_done()
        attempt = self.attempt("narrator", take)
        self.assertEqual(orders.missing_prints(self.p, "narrator", take), [])
        for model in ("0.6b-base", "1.7b-base"):
            for path in orders.print_paths(self.p, "narrator", attempt, model):
                self.assertTrue(path.is_file(), path)
        jobs = [e for e in queue.list_entries() if e["kind"] == "prints"]
        self.assertEqual([(e["state"], e["take"]) for e in jobs], [("done", take)])
        lines = [l for l in log_lines() if l["gen_ai.operation.name"] == log.OP_PRINT]
        self.assertEqual(sorted(l["gen_ai.request.model"] for l in lines), ["0.6b-base", "1.7b-base"])
        self.assertTrue(all(l["app.task"] == "prints" and l["app.voice.engine_commit"] for l in lines))

    def test_only_the_missing_print_is_made(self):
        orders.submit(self.p, self.voice())
        take = self.take(prints=("0.6b-base",))
        orders.choose(self.p, "narrator", take)
        queue.enqueue_prints(self.p, "narrator", take)
        self.run_worker()
        lines = [l for l in log_lines() if l["gen_ai.operation.name"] == log.OP_PRINT]
        self.assertEqual([l["gen_ai.request.model"] for l in lines], ["1.7b-base"])

    def test_failing_print_is_logged_and_nothing_is_stored(self):
        orders.submit(self.p, self.voice())
        take = self.take()
        queue.choose(self.p, "narrator", take)
        self.run_worker(engine=engine.FakeEngine(fail_with="no gpu"))
        entry = queue.get(1)
        self.assertEqual(entry["state"], "failed")
        self.assertIn("no gpu", queue.error_text(entry["error"], "en"))
        self.assertEqual(orders.missing_prints(self.p, "narrator", take),
                         ["0.6b-base", "1.7b-base"])
        line, = log_lines()
        self.assertIn("no gpu", line["app.error"])

    def test_prints_job_for_a_take_that_vanished(self):
        orders.submit(self.p, self.voice())
        take = self.take()
        queue.choose(self.p, "narrator", take)
        with mock.patch.object(orders, "missing_prints", side_effect=GvoiceError("order.attempt_unknown", take=take)):
            self.run_worker()
        self.assertEqual(queue.get(1)["error"]["code"], "order.attempt_unknown")

    def test_prints_job_with_no_audio(self):
        orders.submit(self.p, self.voice())
        take = self.take()
        queue.choose(self.p, "narrator", take)
        os.remove(orders.attempt_audio(self.p, "narrator", self.attempt("narrator", take)))
        self.run_worker()
        self.assertEqual(queue.get(1)["error"]["code"], "worker.take_without_audio")


    def test_set_prints_failure_is_logged(self):
        orders.submit(self.p, self.voice())
        take = self.take()
        queue.choose(self.p, "narrator", take)
        boom = GvoiceError("order.attempt_unknown", attempt=take, order="narrator")
        with mock.patch.object(orders, "set_prints", side_effect=boom):
            self.run_worker()
        self.assertEqual(queue.get(1)["state"], "failed")
        line, = log_lines()
        self.assertEqual(line["gen_ai.operation.name"], log.OP_PRINT)
        self.assertIn(queue.error_text(queue.make_error(boom.code, **boom.params), "en"), line["app.error"])


class LineTests(WorkerBase):
    def test_line_take_uses_the_print_of_the_production_model(self):
        self.voice_done()
        orders.submit(self.p, self.line())
        queue.enqueue(self.p, "narrator/intro-01", orders.attempt_specs(self.p, "narrator/intro-01", seed=3))
        self.run_worker()
        entry = [e for e in queue.list_entries() if e["kind"] == "line"][0]
        self.assertEqual(entry["state"], "done")
        attempt = orders.get(self.p, "narrator/intro-01")["attempts"][0]
        self.assertEqual(attempt["seed"], 3)
        line = log_lines()[-1]
        self.assertEqual((line["gen_ai.operation.name"], line["gen_ai.request.model"], line["app.task"]),
                         (log.OP_LINE, "0.6b-base", "line"))

    def test_line_job_carries_the_text_of_the_reference_take(self):
        take = self.voice_done()
        orders.submit(self.p, self.line())
        queue.enqueue(self.p, "narrator/intro-01", orders.attempt_specs(self.p, "narrator/intro-01", seed=3))
        seen = []

        class Spy(engine.FakeEngine):
            def line(self, job, should_cancel):
                seen.append(job)
                return super().line(job, should_cancel)

        self.run_worker(engine=Spy())
        self.assertEqual([j.reference_text for j in seen], [self.attempt("narrator", take)["text"]])
        self.assertTrue(seen[0].reference_text)

    def test_line_uses_the_voice_it_was_queued_for(self):
        self.voice_done()
        orders.submit(self.p, self.voice(key="orc"))
        orders.choose(self.p, "orc", self.take("orc", seed=4))  # same take id 1, no prints
        orders.submit(self.p, self.line())
        entry, = queue.new_takes(self.p, "narrator/intro-01")
        orders.submit(self.p, self.line(voice="orc"))  # resubmitted before the worker runs
        self.run_worker()
        self.assertEqual(queue.get(entry["id"])["state"], "done")
        attempt = orders.get(self.p, "narrator/intro-01")["attempts"][0]
        self.assertEqual((attempt["voice"], attempt["reference"]), ("narrator", 1))

    def test_line_fails_with_its_reason_without_the_print(self):
        orders.submit(self.p, self.voice())
        take = self.take()
        orders.choose(self.p, "narrator", take)  # chosen, but its prints were never made
        orders.submit(self.p, self.line())
        queue.enqueue(self.p, "narrator/intro-01", orders.attempt_specs(self.p, "narrator/intro-01"))
        self.run_worker()
        entry = queue.get(1)
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "worker.print_missing"))
        self.assertEqual(entry["error"]["params"]["model"], "0.6b-base")
        self.assertIn("0.6b-base", queue.error_text(entry["error"], "en"))
        self.assertEqual(orders.get(self.p, "narrator/intro-01")["attempts"], [])
        line, = log_lines()
        self.assertEqual(line["gen_ai.operation.name"], log.OP_LINE)
        self.assertIn("0.6b-base", line["app.error"])

    def test_line_fails_if_the_model_is_not_in_print_models(self):
        self.voice_done()
        orders.submit(self.p, self.line())
        queue.enqueue(self.p, "narrator/intro-01", orders.attempt_specs(self.p, "narrator/intro-01"))
        self.write_config(printModels=["1.7b-base"])  # changed after queueing
        self.run_worker()
        entry = [e for e in queue.list_entries() if e["kind"] == "line"][0]
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "queue.model_not_printed"))

    def test_line_of_a_voice_with_no_chosen_take_is_refused_on_submit(self):
        orders.submit(self.p, self.voice())
        self.assertEqual(self.code(orders.submit, self.p, self.line()).code, "order.voice_not_fixed")


if __name__ == "__main__":
    unittest.main()


class MemoryTests(WorkerBase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.dict(os.environ, {"GVOICE_MEMINFO": str(self.tmp_meminfo())})
        patch.start()
        self.addCleanup(patch.stop)
        poll = mock.patch.object(worker, "MEMORY_POLL_S", 0.05)
        poll.start()
        self.addCleanup(poll.stop)
        self.set_free(2000)

    def tmp_meminfo(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return os.path.join(tmp.name, "meminfo")

    def set_free(self, mb):
        with open(os.environ["GVOICE_MEMINFO"], "w") as fh:
            fh.write("MemAvailable: %d kB\n" % (mb * 1024))

    def watching_engine(self):
        eng = engine.FakeEngine()
        eng.watches_memory = True
        return eng

    def start(self):
        self.push()
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            thread = threading.Thread(target=self.run_worker, kwargs={"engine": self.watching_engine()})
            thread.start()
            time.sleep(0.4)
        return thread, err

    def test_low_memory_makes_the_job_wait_and_it_starts_when_memory_rises(self):
        thread, err = self.start()
        self.assertEqual(queue.get(1)["state"], "running")
        self.assertTrue(thread.is_alive())
        self.assertEqual(orders.get(self.p, "narrator")["attempts"], [])
        self.assertIn("waiting for memory", err.getvalue())
        self.assertIn("2000 MB", err.getvalue())
        self.assertIn("4096 MB", err.getvalue())
        self.assertEqual(err.getvalue().count("waiting for memory"), 1)
        self.set_free(8000)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(queue.get(1)["state"], "done")
        self.assertEqual(len(orders.get(self.p, "narrator")["attempts"]), 1)

    def test_the_wait_holds_the_machine_lock(self):
        thread, _ = self.start()
        self.assertTrue(machine_lock.busy())
        queue.cancel(1)
        thread.join(5)
        self.assertFalse(machine_lock.busy())

    def test_cancel_while_waiting_for_memory(self):
        thread, _ = self.start()
        queue.cancel(1)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(queue.get(1)["state"], "cancelled")
        self.assertEqual(orders.get(self.p, "narrator")["attempts"], [])
        self.assertEqual(log_lines(), [])

    def test_the_fake_engine_does_not_wait(self):
        self.push()
        self.run_worker()
        self.assertEqual(queue.get(1)["state"], "done")

    def test_unknown_memory_does_not_wait(self):
        os.environ["GVOICE_MEMINFO"] = os.environ["GVOICE_MEMINFO"] + ".missing"
        self.push()
        self.run_worker(engine=self.watching_engine())
        self.assertEqual(queue.get(1)["state"], "done")

    def test_low_memory_error_of_the_engine_is_the_reason_of_the_entry(self):
        class Aborting(engine.FakeEngine):
            def design(self, job, should_cancel):
                raise engine.EngineError("memory fell", "engine.low_memory", free=900, min=1536)

        self.push()
        self.run_worker(engine=Aborting())
        entry = queue.get(1)
        self.assertEqual(entry["state"], "failed")
        self.assertEqual(entry["error"]["code"], "engine.low_memory")
        self.assertEqual(entry["error"]["params"], {"free": 900, "min": 1536})
        self.assertIn("900 MB", queue.error_text(entry["error"], "en"))
        self.assertIn("900 MB", queue.error_text(entry["error"], "es"))
        self.assertIn("900 MB", log_lines()[0]["app.error"])

    def test_stats_of_the_result_reach_the_log_line(self):
        class Measured(engine.FakeEngine):
            def design(self, job, should_cancel):
                result = super().design(job, should_cancel)
                result.min_free_mb, result.peak_rss_mb = 3100, 2048
                return result

        self.push()
        self.run_worker(engine=Measured())
        line = log_lines()[0]
        self.assertEqual((line["app.voice.min_free_mb"], line["app.voice.peak_rss_mb"]), (3100, 2048))

    def test_start_deletes_the_workdirs_a_killed_run_left(self):
        base = paths.project_data_dir(self.p) / "attempts" / "q3"
        stale = [base / ".qwentts-abc123", paths.project_data_dir(self.p) / "voices" / ".qwentts-zz"]
        for d in stale:
            d.mkdir(parents=True)
            (d / "out.wav").write_bytes(b"x")
        keep = base / "audio.wav"
        keep.write_bytes(b"x")
        other = base / "qwentts-not-hidden"
        other.mkdir()
        self.assertEqual(self.run_worker(), 0)
        for d in stale:
            self.assertFalse(d.exists(), d)
        self.assertTrue(keep.is_file())
        self.assertTrue(other.is_dir())

    def test_a_failed_job_logs_the_memory_figures_of_the_engine(self):
        class Dies(engine.FakeEngine):
            def design(self, job, should_cancel):
                exc = engine.EngineError("exited with code -9")
                exc.stats = {"min_free_mb": 1700, "peak_rss_mb": 5000}
                raise exc

        self.set_free(8000)
        self.push()
        self.run_worker(engine=Dies())
        line, = log_lines()
        self.assertIn("exited with code -9", line["app.error"])
        self.assertEqual((line["app.voice.min_free_mb"], line["app.voice.peak_rss_mb"]), (1700, 5000))

    def test_a_failed_print_logs_the_memory_figures_too(self):
        class Dies(engine.FakeEngine):
            def voiceprint(self, job, should_cancel):
                exc = engine.EngineError("no gpu")
                exc.stats = {"min_free_mb": 1800, "peak_rss_mb": 4000}
                raise exc

        orders.submit(self.p, self.voice())
        take = self.take()
        queue.choose(self.p, "narrator", take)
        self.set_free(8000)
        self.run_worker(engine=Dies())
        line, = log_lines()
        self.assertIn("no gpu", line["app.error"])
        self.assertEqual((line["app.voice.min_free_mb"], line["app.voice.peak_rss_mb"]), (1800, 4000))

    def test_start_keeps_the_workdirs_while_the_machine_lock_is_held(self):
        stale = paths.project_data_dir(self.p) / "attempts" / "q3" / ".qwentts-live"
        stale.mkdir(parents=True)
        (stale / "out.wav").write_bytes(b"x")
        self.foreign_holder()  # an orphaned engine (or the image generator) holds the machine
        self.assertEqual(self.run_worker(), 0)
        self.assertTrue(stale.is_dir())

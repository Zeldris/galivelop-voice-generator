import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from gvoice import engine, machinelock
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent

HOLDER = """
import sys
from gvoice import machinelock
with machinelock.hold():
    print("held", flush=True)
    sys.stdin.readline()
"""


class LockTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.state = self.tmp / "state"
        env = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.state)})
        env.start()
        self.addCleanup(env.stop)

    def spawn(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.Popen([sys.executable, "-c", HOLDER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                text=True, env=env, cwd=str(self.tmp))
        self.addCleanup(lambda: (proc.poll() is None and proc.kill(), proc.wait(), proc.stdin.close(),
                                 proc.stdout.close()))
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc

    def test_path_follows_xdg_state_home(self):
        self.assertEqual(machinelock.lock_path(), self.state / "galivelop" / "gpu.lock")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": ""}):
            self.assertEqual(machinelock.lock_path(), Path.home() / ".local/state/galivelop/gpu.lock")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "relative"}):
            self.assertEqual(machinelock.lock_path(), Path.home() / ".local/state/galivelop/gpu.lock")

    def test_creates_folder_0700_and_file(self):
        with machinelock.hold():
            pass
        self.assertEqual(os.stat(self.state / "galivelop").st_mode & 0o777, 0o700)
        self.assertTrue((self.state / "galivelop" / "gpu.lock").is_file())

    def test_free_lock_is_taken_without_waiting(self):
        t0 = time.monotonic()
        with machinelock.hold():
            pass
        self.assertLess(time.monotonic() - t0, 1)

    def test_released_after_block_and_after_error(self):
        for _ in range(2):
            with self.assertRaises(ZeroDivisionError):
                with machinelock.hold():
                    1 / 0
        with machinelock.hold():
            pass

    def test_second_process_waits_until_released(self):
        proc = self.spawn()
        entered = threading.Event()

        def waiter():
            with machinelock.hold(poll_s=0.01):
                entered.set()

        thread = threading.Thread(target=waiter)
        thread.start()
        self.assertFalse(entered.wait(0.5))  # the other process still holds it
        proc.stdin.write("\n")
        proc.stdin.flush()
        self.assertTrue(entered.wait(5))
        thread.join(5)
        self.assertEqual(proc.wait(5), 0)

    def test_cancel_while_waiting(self):
        proc = self.spawn()
        flag = threading.Event()
        threading.Timer(0.2, flag.set).start()
        t0 = time.monotonic()
        with self.assertRaises(engine.Cancelled):
            with machinelock.hold(flag.is_set, poll_s=0.01):
                self.fail("must not enter")
        self.assertLess(time.monotonic() - t0, 3)
        self.assertIsNone(proc.poll())  # the holder still has it
        proc.stdin.write("\n")
        proc.stdin.flush()
        proc.wait(5)
        with machinelock.hold():  # and the cancelled waiter left nothing locked
            pass

    def test_cancelled_is_the_engines(self):
        self.assertIs(machinelock.Cancelled, engine.Cancelled)

    def code(self):
        with self.assertRaises(GvoiceError) as cm:
            with machinelock.hold():
                self.fail("must not enter")
        return cm.exception

    def test_symlinked_folder_refused(self):
        real = self.tmp / "elsewhere"
        real.mkdir()
        self.state.mkdir()
        (self.state / "galivelop").symlink_to(real)
        exc = self.code()
        self.assertEqual(exc.code, "machinelock.symlink")
        self.assertIn(str(self.state / "galivelop"), exc.message("en"))
        self.assertEqual(os.listdir(real), [])

    def test_symlinked_file_refused(self):
        folder = self.state / "galivelop"
        folder.mkdir(parents=True)
        target = self.tmp / "target"
        target.write_text("x")
        (folder / "gpu.lock").symlink_to(target)
        self.assertEqual(self.code().code, "machinelock.symlink")

    def test_dangling_symlinked_file_refused(self):
        folder = self.state / "galivelop"
        folder.mkdir(parents=True)
        (folder / "gpu.lock").symlink_to(self.tmp / "missing")
        self.assertEqual(self.code().code, "machinelock.symlink")
        self.assertFalse((self.tmp / "missing").exists())

    def test_folder_of_another_user_refused(self):
        self.state.mkdir()
        (self.state / "galivelop").mkdir()
        with mock.patch("os.geteuid", return_value=os.geteuid() + 1):
            self.assertEqual(self.code().code, "machinelock.foreign")

    def test_file_of_another_user_refused(self):
        folder = self.state / "galivelop"
        folder.mkdir(parents=True)
        (folder / "gpu.lock").write_text("")
        calls = []

        def fake_geteuid():
            calls.append(1)
            return os.getuid() if len(calls) == 1 else os.getuid() + 1  # folder ok, file foreign

        with mock.patch("os.geteuid", side_effect=fake_geteuid):
            self.assertEqual(self.code().code, "machinelock.foreign")

    def test_folder_that_is_a_file_refused(self):
        self.state.mkdir()
        (self.state / "galivelop").write_text("x")
        self.assertEqual(self.code().code, "machinelock.not_dir")

    def test_messages_translated(self):
        for lang in ("es", "en"):
            for code in ("symlink", "foreign", "not_dir", "not_file", "unusable"):
                text = GvoiceError("machinelock." + code, path="/p", reason="r").message(lang)
                self.assertNotIn("error.", text)


if __name__ == "__main__":
    unittest.main()

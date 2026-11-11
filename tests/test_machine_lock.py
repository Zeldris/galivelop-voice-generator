import fcntl
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from gvoice import machine_lock, paths
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
HOLDER = (
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "time.sleep(60)\n")


class LockBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GVOICE_STATE_HOME": str(self.tmp / "state")})
        env.start()
        self.addCleanup(env.stop)

    def holder(self):
        """Another process holding the machine lock; killed on cleanup."""
        path = paths.machine_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(path)], stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc


class PathTests(LockBase):
    def test_gvoice_variable_wins(self):
        self.assertEqual(paths.machine_lock_path(), self.tmp / "state" / "gpu.lock")

    def test_xdg_then_home(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.tmp / "xdg")}):
            os.environ.pop("GVOICE_STATE_HOME")
            self.assertEqual(paths.machine_lock_path(), self.tmp / "xdg" / "galivelop" / "gpu.lock")
            os.environ["XDG_STATE_HOME"] = "relative/dir"  # not absolute: ignored
            self.assertEqual(paths.machine_lock_path(), Path.home() / ".local/state/galivelop/gpu.lock")
            os.environ.pop("XDG_STATE_HOME")
            self.assertEqual(paths.state_dir(), Path.home() / ".local/state/galivelop")


class HoldTests(LockBase):
    def test_creates_the_missing_state_folder(self):
        self.assertFalse((self.tmp / "state").exists())
        with machine_lock.hold():
            self.assertTrue(paths.machine_lock_path().is_file())
            self.assertTrue(machine_lock.busy())
        self.assertFalse(machine_lock.busy())
        self.assertTrue(paths.machine_lock_path().is_file())  # never deleted

    def test_busy_is_a_pure_read(self):
        self.assertFalse(machine_lock.busy())
        self.assertFalse((self.tmp / "state").exists())

    def test_released_on_error(self):
        with self.assertRaises(RuntimeError):
            with machine_lock.hold():
                raise RuntimeError("boom")
        self.assertFalse(machine_lock.busy())

    def test_unwritable_state_folder(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {"GVOICE_STATE_HOME": str(blocker / "sub")}):
            with self.assertRaises(GvoiceError) as cm:
                with machine_lock.hold():
                    self.fail("must not get the lock")
        self.assertEqual(cm.exception.code, "machine_lock.unavailable")
        self.assertEqual(cm.exception.params["path"], str(blocker / "sub" / "gpu.lock"))
        self.assertTrue(cm.exception.params["reason"])

    def test_busy_lock_waits_then_proceeds(self):
        proc = self.holder()
        self.assertTrue(machine_lock.busy())
        waited = []
        got = threading.Event()

        def take():
            with machine_lock.hold(on_wait=lambda: waited.append(1), poll_s=0.01):
                got.set()

        thread = threading.Thread(target=take)
        thread.start()
        time.sleep(0.3)
        self.assertFalse(got.is_set())  # still waiting: it did not fail
        self.assertEqual(waited, [1])  # told once
        proc.kill()
        proc.wait()
        thread.join(5)
        self.assertTrue(got.is_set())

    def test_wait_is_cancellable(self):
        self.holder()
        cancel = threading.Event()
        threading.Timer(0.2, cancel.set).start()
        start = time.monotonic()
        with self.assertRaises(machine_lock.WaitCancelled):
            with machine_lock.hold(cancel.is_set, poll_s=0.01):
                self.fail("must not get the lock")
        self.assertLess(time.monotonic() - start, 3)

    def test_process_dying_with_the_lock_frees_it(self):
        proc = self.holder()
        self.assertTrue(machine_lock.busy())
        proc.kill()  # SIGKILL: no chance to clean up
        proc.wait()
        self.assertFalse(machine_lock.busy())
        with machine_lock.hold():
            pass

    def test_lock_is_exclusive_between_two_holds_in_one_process(self):
        with machine_lock.hold():
            fd = os.open(str(paths.machine_lock_path()), os.O_RDWR)
            self.addCleanup(os.close, fd)
            with self.assertRaises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == "__main__":
    unittest.main()

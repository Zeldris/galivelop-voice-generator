import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from gvoice import engine, limits, runner

MACHINE = {"name": "t", "minFreeMemoryMb": 100, "watchMemoryMb": 50, "timeoutS": 9}
POLL = 0.02


def py(code):
    return [sys.executable, "-c", code]


class RunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.meminfo = self.tmp / "meminfo"
        self.set_free(1000)

    def set_free(self, mb):
        self.meminfo.write_text(f"MemTotal: 9999999 kB\nMemAvailable: {mb * 1024} kB\n")

    def go(self, argv, **kw):
        kw.setdefault("machine", MACHINE)
        return runner.run(argv, meminfo=str(self.meminfo), poll_s=POLL, **kw)

    def test_normal_exit_captures_output_and_stdin(self):
        r = self.go(py("import sys; t=sys.stdin.read(); print('in:'+t); sys.stderr.write('warn')"),
                    stdin_text="hola ñ")
        self.assertEqual((r.returncode, r.stdout.strip(), r.stderr), (0, "in:hola ñ", "warn"))
        self.assertEqual(r.min_free_mb, 1000)
        self.assertGreaterEqual(r.wall_ms, 0)

    def test_env_is_merged_over_the_environment(self):
        r = self.go(py("import os; print(os.environ['GV_X'], 'PATH' in os.environ)"), env={"GV_X": "1"})
        self.assertEqual(r.stdout.strip(), "1 True")

    def test_nonzero_exit_is_returned_not_raised(self):
        r = self.go(py("import sys; sys.stderr.write('boom'); sys.exit(3)"))
        self.assertEqual((r.returncode, r.stderr), (3, "boom"))

    def test_output_is_cut_to_the_last_64_kib(self):
        r = self.go(py("import sys; sys.stdout.write('a'*100000 + 'END')"))
        self.assertEqual(len(r.stdout), runner.TAIL_BYTES)
        self.assertTrue(r.stdout.endswith("END"))

    def test_timeout(self):
        t = time.monotonic()
        with self.assertRaises(engine.EngineTimeout) as cm:
            self.go(py("import time; time.sleep(30)"), timeout_s=0.2)
        self.assertEqual(cm.exception.message, engine.TIMEOUT_MESSAGE)
        self.assertLess(time.monotonic() - t, 5)

    def test_cancel(self):
        calls = []

        def cancel():
            calls.append(1)
            return len(calls) > 3

        with self.assertRaises(engine.Cancelled):
            self.go(py("import time; time.sleep(30)"), should_cancel=cancel)

    def test_memory_too_low_to_start(self):
        self.set_free(10)
        with self.assertRaises(limits.LimitError) as cm:
            self.go(py("print(1)"))
        self.assertEqual(cm.exception.code, "limit.memory")

    def test_memory_abort_while_running(self):
        calls = []

        def cancel():
            calls.append(1)
            if len(calls) > 2:
                self.set_free(20)  # memory falls while the engine runs
            return False

        with self.assertRaises(limits.LimitError) as cm:
            self.go(py("import time; time.sleep(30)"), should_cancel=cancel)
        self.assertEqual(cm.exception.code, "limit.memory_abort")
        self.assertEqual(cm.exception.params["free"], 20)
        self.assertEqual(cm.exception.params["watch"], 50)

    def test_process_group_is_dead_after_timeout(self):
        pidfile = self.tmp / "grandchild"
        code = ("import subprocess, sys, time\n"
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                f"open({str(pidfile)!r}, 'w').write(str(p.pid))\n"
                "time.sleep(60)\n")
        with self.assertRaises(engine.EngineTimeout):
            self.go(py(code), timeout_s=1.0)
        pid = int(pidfile.read_text())
        for _ in range(100):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_binary_missing(self):
        with self.assertRaises(engine.EngineError) as cm:
            self.go([str(self.tmp / "nope")])
        self.assertEqual(cm.exception.code, "engine.binary_missing")
        self.assertEqual(cm.exception.params["path"], str(self.tmp / "nope"))


if __name__ == "__main__":
    unittest.main()

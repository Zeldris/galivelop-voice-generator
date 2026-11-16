"""A fake `qwen-tts` / `qwen-codec` for the tests: ``python fake_qwentts.py tts|codec <args>``.

It parses the same arguments, records every call as a JSON line in ``$FAKE_QT_LOG`` (argv, stdin, cwd) and writes real
files: a PCM ``.wav`` of 100 ms per character of stdin for ``tts`` (``-o``), and ``<stem>.spk`` / ``<stem>.rvq``
next to the input for ``codec`` (``-i``). Failures on demand, by environment:

* ``FAKE_QT_FAIL_DEVICE=<name>[,<name>]``: with ``--device`` one of them, stderr ``failed to open device`` and exit 3, no files.
* ``FAKE_QT_KILL_SELF=1``: SIGKILL itself right away (like the OOM killer), no files.
* ``FAKE_QT_HANG=1``: start a ``sleep`` child (its pid in ``$FAKE_QT_PIDFILE``) and sleep, writing nothing.
* ``FAKE_QT_NOWAV=1``: exit 0 and write nothing.
* ``FAKE_QT_BADWAV=1``: write garbage to the output and exit 0.
* ``FAKE_QT_CRASH=1``: write a garbage output, noise on stderr and exit 1.
* ``FAKE_QT_SLEEP_S=<s>``: sleep that long before doing the work (a slow but successful run).
* ``FAKE_QT_LATE_FAIL_S=<s>``: sleep, then stderr ``out of memory`` and exit 1, no files."""
import json
import os
import signal
import subprocess
import sys
import time
import wave

RATE = 24000


def main(argv):
    mode, args = argv[0], argv[1:]
    opts = {}
    i = 0
    while i < len(args):
        opts[args[i]] = args[i + 1] if i + 1 < len(args) else None
        i += 2
    stdin = sys.stdin.read()
    log = os.environ.get("FAKE_QT_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"mode": mode, "argv": args, "stdin": stdin, "cwd": os.getcwd()}) + "\n")
    if opts.get("--device") in os.environ.get("FAKE_QT_FAIL_DEVICE", "").split(","):
        sys.stderr.write("loading\nfailed to open device %s\n" % opts.get("--device"))
        return 3
    if os.environ.get("FAKE_QT_KILL_SELF"):
        os.kill(os.getpid(), signal.SIGKILL)
    if os.environ.get("FAKE_QT_HANG"):
        child = subprocess.Popen(["sleep", "30"])
        with open(os.environ["FAKE_QT_PIDFILE"], "w") as fh:
            fh.write(str(child.pid))
        time.sleep(30)
        return 0
    if os.environ.get("FAKE_QT_SLEEP_S"):
        time.sleep(float(os.environ["FAKE_QT_SLEEP_S"]))
    late = os.environ.get("FAKE_QT_LATE_FAIL_S")
    if late:
        time.sleep(float(late))
        sys.stderr.write("out of memory\n")
        return 1
    if os.environ.get("FAKE_QT_NOWAV"):
        return 0
    if mode == "tts":
        out = opts["-o"]
        if os.environ.get("FAKE_QT_BADWAV") or os.environ.get("FAKE_QT_CRASH"):
            with open(out, "wb") as fh:
                fh.write(b"this is not a wav")
        if os.environ.get("FAKE_QT_CRASH"):
            sys.stderr.write("".join("noise %d\n" % n for n in range(40)) + "boom: kaput\n")
            return 1
        if os.environ.get("FAKE_QT_BADWAV"):
            return 0
        frames = RATE * 100 * len(stdin) // 1000
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"\x01\x00" * frames)
        return 0
    stem = os.path.splitext(opts["-i"])[0]
    with open(stem + ".spk", "wb") as fh:
        fh.write(b"S" * 4096)
    with open(stem + ".rvq", "wb") as fh:
        fh.write(b"R" * 4444)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

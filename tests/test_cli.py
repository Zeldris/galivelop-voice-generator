import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import __version__, cli, queue

ROOT = Path(__file__).resolve().parent.parent
CONFIG = (ROOT / "examples" / "galivelop-voices.json").read_text()
VOICE = json.loads((ROOT / "examples" / "order-voice.json").read_text())
LINE = json.loads((ROOT / "examples" / "order-line.json").read_text())
PROJECT = "example-world"


class CliBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {
            "GVOICE_CONFIG_HOME": str(self.tmp / "cfg"), "GVOICE_DATA_HOME": str(self.tmp / "data"),
            "GVOICE_STATE_HOME": str(self.tmp / "state"), "GVOICE_ENGINE": "fake", "GVOICE_LANG": "en"})
        env.start()
        self.addCleanup(env.stop)
        for name in ("GVOICE_MACHINE_PROFILE", "GVOICE_DEBUG", "GVOICE_FAKE_FAIL", "GVOICE_FAKE_DELAY"):
            os.environ.pop(name, None)
        self.root = self.tmp / "proj"
        self.root.mkdir()
        (self.root / "galivelop-voices.json").write_text(CONFIG)
        self.write_order("voice.json", VOICE)
        self.write_order("line.json", LINE)

    def write_order(self, name, order, **changes):
        path = self.tmp / name
        path.write_text(json.dumps(dict(order, **changes)))
        return str(path)

    def run_cli(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if stdin is None:
                code = cli.main(list(argv))
            else:
                with mock.patch.object(sys, "stdin", io.StringIO(stdin)):
                    code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv, **kw):
        code, out, err = self.run_cli(*argv, **kw)
        self.assertEqual((code, err), (0, ""), argv)
        return out

    def js(self, *argv, **kw):
        return json.loads(self.ok("--json", *argv, **kw))

    def fails(self, *argv, message, lang=None, **kw):
        if lang:
            argv = ("--lang", lang) + argv
        code, out, err = self.run_cli(*argv, **kw)
        self.assertEqual((code, out), (1, ""), argv)
        self.assertIn(message, err)

    def add_project(self):
        self.ok("project", "add", str(self.root))


class ProjectTests(CliBase):
    def test_add_list_remove(self):
        self.assertIn("No projects", self.ok("project", "list"))
        self.assertIn(PROJECT, self.ok("project", "add", str(self.root)))
        self.assertEqual(self.js("project", "list"), [{"name": PROJECT, "root": str(self.root)}])
        self.assertIn(PROJECT, self.ok("project", "list"))
        self.assertIn(PROJECT, self.ok("project", "remove", PROJECT))
        self.assertEqual(self.js("project", "list"), [])

    def test_unknown_project_says_so_in_both_languages(self):
        self.fails("order", "list", "nope", message='no registered project is named "nope"')
        self.fails("order", "list", "nope", message="nope", lang="es")
        self.fails("project", "remove", "nope", message="nope")


class OrderTests(CliBase):
    def test_submit_shows_the_sheet_warnings(self):
        self.add_project()
        sheet = dict(VOICE["designSheet"], age="child", texture="a boy's voice")
        path = self.write_order("kid.json", VOICE, key="kid", designSheet=sheet)
        text = self.ok("order", "submit", PROJECT, path)
        self.assertIn("warning:", text)
        self.assertIn("child", text)
        self.assertIn("Queued 1 entries: 1.", text)
        data = self.js("order", "submit", PROJECT, path)
        self.assertEqual(data["order"]["key"], "kid")
        self.assertTrue(data["warnings"])
        self.assertTrue(all(w["code"] and w["message"] for w in data["warnings"]))
        self.assertEqual(data["entries"][0]["kind"], "voice")
        es = self.ok("--lang", "es", "order", "submit", PROJECT, path)
        self.assertIn("aviso:", es)

    def test_a_clean_sheet_has_no_warning_and_count_queues_more(self):
        self.add_project()
        out = self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE), "--count", "3")
        self.assertNotIn("warning", out)
        self.assertIn("Queued 3 entries", out)

    def test_submit_from_stdin(self):
        self.add_project()
        out = self.js("order", "submit", PROJECT, "-", stdin=json.dumps(VOICE))
        self.assertEqual(len(out["entries"]), 1)

    def test_list_and_show(self):
        self.add_project()
        self.assertIn("No orders", self.ok("order", "list", PROJECT))
        self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE))
        self.ok("work")
        self.assertIn("narrator [voice]", self.ok("order", "list", PROJECT))
        self.assertEqual([o["key"] for o in self.js("order", "list", PROJECT, "--unchosen")], ["narrator"])
        self.assertEqual(self.js("order", "list", PROJECT, "--chosen"), [])
        self.assertEqual(self.js("order", "list", PROJECT, "--type", "line"), [])
        text = self.ok("order", "show", PROJECT, "narrator")
        self.assertIn("Test text: " + VOICE["testText"], text)
        self.assertIn("Instruction:", text)
        self.assertIn("#1 [new] seed 1234", text)
        self.assertIn("voice prints: none", text)
        self.assertEqual(self.js("order", "show", PROJECT, "narrator")["attempts"][0]["id"], 1)
        self.fails("order", "show", PROJECT, "ghost", message='order "ghost" does not exist')

    def test_a_line_needs_a_fixed_voice(self):
        self.add_project()
        self.fails("order", "submit", PROJECT, self.write_order("l.json", LINE), message='"narrator" is not a voice')
        self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE))
        self.fails("order", "submit", PROJECT, self.write_order("l.json", LINE), message="has no reference yet")
        self.assertEqual(self.js("queue", "list")[0]["key"], "narrator")  # the failed line queued nothing

    def test_invalid_order_file(self):
        self.add_project()
        bad = self.tmp / "bad.json"
        bad.write_text("{not json")
        self.fails("order", "submit", PROJECT, str(bad), message="could not read the order")
        self.fails("order", "submit", PROJECT, str(self.tmp / "missing.json"), message="could not read the order")
        bad.write_text(json.dumps({"key": "x"}))
        self.fails("order", "submit", PROJECT, str(bad), message="not valid")
        self.fails("order", "submit", PROJECT, str(bad), message="no es válido", lang="es")


class AttemptTests(CliBase):
    def setUp(self):
        super().setUp()
        self.add_project()
        self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE))
        self.ok("work")

    def test_new_mark_note(self):
        out = self.js("attempt", "new", PROJECT, "narrator", "--count", "2", "--seed", "5")
        self.assertEqual([e["seed"] for e in out["entries"]], [5, 6])
        self.assertEqual(len(out["entries"]), 2)
        self.assertIn("Queued 1 entries", self.ok("attempt", "new", PROJECT, "narrator"))
        self.assertIn("state candidate", self.ok("attempt", "mark", PROJECT, "narrator", "1", "candidate"))
        self.assertEqual(self.js("attempt", "note", PROJECT, "narrator", "1", "too dry")["note"], "too dry")
        self.assertIn("note: too dry", self.ok("order", "show", PROJECT, "narrator"))
        self.assertIn("note saved", self.ok("attempt", "note", PROJECT, "narrator", "1", ""))

    def test_bad_state_is_a_usage_error_and_unknown_take_fails(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["attempt", "mark", PROJECT, "narrator", "1", "great"]), 2)
        self.assertIn("invalid choice", err.getvalue())
        self.fails("attempt", "mark", PROJECT, "narrator", "9", "candidate", message="9")

    def test_choose_a_voice_queues_its_prints_and_undo_goes_back(self):
        out = self.ok("choose", PROJECT, "narrator", "1")
        self.assertIn("Chose take 1 (before: none).", out)
        self.assertIn("Queued 1 entries", out)
        data = self.js("choose", PROJECT, "narrator", "1")
        self.assertEqual((data["old"], data["new"], data["entries"]), (1, 1, []))  # no duplicate prints job
        self.assertIn("Undone: now none (before: 1)", self.ok("undo", PROJECT, "narrator"))
        self.fails("undo", PROJECT, "narrator", message="nothing to undo")

    def test_choose_a_take_without_audio_says_why(self):
        self.ok("attempt", "new", PROJECT, "narrator")  # queued, not worked
        self.ok("attempt", "mark", PROJECT, "narrator", "1", "discarded")
        self.fails("choose", PROJECT, "narrator", "1", message="discarded")


class QueueTests(CliBase):
    def test_list_cancel_and_failed_entry(self):
        self.add_project()
        self.assertIn("The queue is empty", self.ok("queue", "list"))
        self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE))
        self.assertRegex(self.ok("queue", "list"), r"#1 queued voice  example-world/narrator  seed 1234")
        self.assertIn("Entry 1: cancelled", self.ok("queue", "cancel", "1"))
        self.fails("queue", "cancel", "1", message="cannot be cancelled")
        self.fails("queue", "cancel", "99", message="99")
        self.assertEqual(self.js("queue", "list", "--state", "cancelled")[0]["id"], 1)
        self.ok("attempt", "new", PROJECT, "narrator")
        with mock.patch.dict(os.environ, {"GVOICE_FAKE_FAIL": "boom"}):
            self.assertIn("Processed 1 entries", self.ok("work"))
        text = self.ok("queue", "list", "--state", "failed")
        self.assertIn("failed voice", text)
        self.assertIn("boom", text)
        self.assertIn("boom", self.js("queue", "list", "--state", "failed")[0]["errorText"])

    def test_work_once_and_json(self):
        self.add_project()
        self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE), "--count", "2")
        self.assertEqual(self.js("work", "--once"), {"processed": 1})
        self.assertEqual(self.js("work"), {"processed": 1})
        self.assertEqual(self.js("work"), {"processed": 0})

    def test_worker_already_running(self):
        import fcntl
        queue.worker_lock_path().parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(queue.worker_lock_path()), os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.fails("work", message="a worker is already running")

    def test_work_passes_the_language(self):
        with mock.patch("gvoice.cli.worker.run", return_value=0) as run:
            self.ok("--lang", "es", "work")
        self.assertEqual(run.call_args.kwargs["lang"], "es")


class GeneralTests(CliBase):
    def test_languages_differ(self):
        es = self.ok("--lang", "es", "project", "list")
        en = self.ok("--lang", "en", "project", "list")
        self.assertNotEqual(es, en)
        self.assertIn("No hay proyectos", es)
        self.assertNotEqual(self.help_text("es", "work"), self.help_text("en", "work"))

    def help_text(self, lang, cmd):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--lang", lang, cmd, "--help"]), 0)
        return out.getvalue()

    def test_usage_error_exits_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["choose", "p", "k", "notanumber"]), 2)
            self.assertEqual(cli.main([]), 2)
        self.assertIn("invalid int value", err.getvalue())

    def test_unexpected_error_is_short_unless_debug(self):
        with mock.patch("gvoice.cli.projects.list_projects", side_effect=RuntimeError("kaput")):
            code, _out, err = self.run_cli("project", "list")
            self.assertEqual((code, err), (1, "unexpected error: RuntimeError: kaput\n"))
            with mock.patch.dict(os.environ, {"GVOICE_DEBUG": "1"}):
                code, _out, err = self.run_cli("project", "list")
        self.assertIn("Traceback", err)
        self.assertIn("unexpected error", err)

    def test_version(self):
        self.assertEqual(self.ok("version").strip(), __version__)


class ProcessTests(unittest.TestCase):
    def test_python_m_gvoice_version(self):
        done = subprocess.run([sys.executable, "-m", "gvoice", "version"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout.strip(), done.stderr), (0, __version__, ""))


class LocaleCoverageTests(unittest.TestCase):
    def test_every_cli_key_exists_in_both_languages(self):
        source = (ROOT / "gvoice" / "cli.py").read_text()
        keys = set(re.findall(r'"(cli\.[a-z_.]+)"', source))
        self.assertTrue(keys)
        for lang in ("es", "en"):
            texts = json.loads((ROOT / "gvoice" / "locales" / (lang + ".json")).read_text(encoding="utf-8"))
            for key in keys:
                self.assertTrue(key in texts or "error." + key in texts, (lang, key))


if __name__ == "__main__":
    unittest.main()

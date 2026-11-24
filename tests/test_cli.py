import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from gvoice import __version__, cli, models, queue
from gvoice.errors import GvoiceError

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

    def test_show_instruction_carries_the_locale_phrase(self):
        self.add_project()
        self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE, locale="es-ES"))
        self.assertIn("Locale: Castilian Spanish", self.ok("order", "show", PROJECT, "narrator"))

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


class ModelsTests(CliBase):
    """`gvoice models` over a made-up catalog (a local one, two tiny files), never the real downloads."""

    def setUp(self):
        super().setUp()
        self.files = {"a": b"a" * 100, "b": b"b" * 50}
        self.catalog = {"engine": "qwentts", "repo": "https://example.com/e", "commit": "0" * 40, "models": [
            {"id": i, "file": i + ".gguf", "url": "https://example.com/" + i, "bytes": len(d),
             "sha256": hashlib.sha256(d).hexdigest(), "use": "base"} for i, d in self.files.items()]}
        patch = mock.patch.object(models, "load", side_effect=self._load)
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = self.tmp / "data" / "models"

    def _load(self, engine):
        if engine != "qwentts":
            raise GvoiceError("models.catalog_missing", engine=engine)
        return self.catalog

    def place(self, name, data):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / (name + ".gguf")).write_bytes(data)

    def test_list_does_not_hash_and_exits_zero(self):
        self.place("a", b"x" * 100)
        out = self.ok("models", "list")
        self.assertIn("a (base): size matches, sha256 not checked", out)
        self.assertIn("b (base): missing", out)
        self.assertEqual({i["id"]: i["state"] for i in self.js("models", "list")},
                         {"a": "unchecked", "b": "missing"})

    def test_verify_exits_one_unless_everything_is_ok(self):
        self.place("a", self.files["a"])
        code, out, err = self.run_cli("--json", "models", "verify")
        self.assertEqual(code, 1)
        self.assertEqual({i["id"]: i["state"] for i in json.loads(out)}, {"a": "ok", "b": "missing"})
        self.place("b", b"y" * 50)
        code, out, _ = self.run_cli("models", "verify")
        self.assertEqual(code, 1)
        self.assertIn("b (base): wrong sha256", out)
        self.place("b", b"y" * 7)
        self.assertIn("wrong size", self.run_cli("models", "verify")[1])
        self.place("b", self.files["b"])
        code, out, err = self.run_cli("models", "verify", "--lang", "es")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("b (base): ok", out)

    def test_verify_only_the_given_ids(self):
        self.place("a", self.files["a"])
        self.assertEqual(self.run_cli("models", "verify", "a")[0], 0)

    def test_fetch_downloads_through_the_core(self):
        with mock.patch.object(models, "fetch", return_value=[
                {"id": "a", "path": "/p/a", "action": "downloaded"}, {"id": "b", "path": "/p/b", "action": "present"}
        ]) as fetch:
            out = self.ok("models", "fetch", "a", "b")
            self.assertEqual(fetch.call_args.args[:2], (self.catalog, ["a", "b"]))
            self.assertIn("a: downloaded to /p/a", out)
            self.assertIn("b: already in /p/b", out)
            self.assertEqual(self.js("models", "fetch")[0]["action"], "downloaded")

    def test_fetch_end_to_end_from_a_local_server(self):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(h):
                h.send_response(200)
                h.send_header("Content-Length", "100")
                h.end_headers()
                h.wfile.write(b"x" * 100)  # not the catalog content: sha256 mismatch

            def log_message(h, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.catalog["models"][0]["url"] = "http://127.0.0.1:%d/a" % server.server_address[1]
        self.fails("models", "fetch", "a", message="sha256 different from the catalog")
        self.fails("models", "fetch", "a", message="sha256", lang="es")
        self.assertEqual(list(self.dir.iterdir()) if self.dir.exists() else [], [])

    def test_unknown_id_and_unknown_engine(self):
        self.fails("models", "verify", "nope", message='unknown model "nope"')
        self.fails("models", "list", "--engine", "other", message='no catalog for the engine "other"')


class CloneTests(CliBase):
    def setUp(self):
        super().setUp()
        self.add_project()
        self.clip = self.wav(self.root / "clips" / "voz.wav")
        self.text = self.tmp / "voz.txt"
        self.text.write_text("  Hola a todos.\n", encoding="utf-8")

    def wav(self, path, seconds=4):
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\x10\x00" * 8000 * seconds)
        return path

    def clone(self, *extra, clip=None):
        return ("voice", "clone", PROJECT, "lector", str(clip or self.clip), "--text", str(self.text)) + extra

    def test_clone_makes_take_one_from_the_clip(self):
        out = self.ok(*self.clone())
        self.assertIn('Voice "lector" from clip clips/voz.wav: 1 take(s).', out)
        order = self.js("order", "show", PROJECT, "lector")
        self.assertEqual(order["clip"], {"audio": "clips/voz.wav", "text": "Hola a todos."})
        take, = order["attempts"]
        self.assertEqual((take["origin"], take["seed"], take["audioMs"]), ("clip", None, 4000))
        self.assertEqual(self.js("queue", "list"), [])  # nothing to generate: no engine needed either

    def test_import_print_makes_a_chosen_take_without_audio(self):
        spk = self.root / "lectora.spk"
        spk.write_bytes(b"FAKE-SPK\nabc\n")
        out = self.ok("voice", "import-print", PROJECT, "lectora", str(spk), "--model", "0.6b-base",
                      "--locale", "es-ES", "--source", "mezcla")
        self.assertIn('Voice "lectora" from print lectora.spk (0.6b-base): 1 take(s), chosen.', out)
        order = self.js("order", "show", PROJECT, "lectora")
        self.assertEqual((order["print"], order["chosen"], order["attempts"][0]["origin"]),
                         ({"spk": "lectora.spk", "model": "0.6b-base", "source": "mezcla"}, 1, "print"))
        self.assertEqual(self.js("queue", "list"), [])
        self.fails("voice", "import-print", PROJECT, "x", str(self.root / "nope.spk"), "--model", "0.6b-base",
                   message="does not exist in the project or is empty")

    def test_relative_clip_resolves_from_the_cwd(self):
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        self.ok("voice", "clone", PROJECT, "lector", "clips/../clips/voz.wav", "--text", str(self.text))
        self.assertEqual(self.js("order", "show", PROJECT, "lector")["clip"]["audio"], "clips/voz.wav")

    def test_locale_and_source_reach_the_order_and_json(self):
        got = self.js(*self.clone("--locale", "es-ES", "--source", "grabación propia"))
        self.assertEqual(got["entries"], [])
        self.assertEqual(got["order"]["clip"]["source"], "grabación propia")
        self.assertEqual(got["order"]["locale"], "es-ES")
        self.assertEqual(self.js("order", "show", PROJECT, "lector")["locale"], "es-ES")

    def test_same_clip_twice_adds_no_take(self):
        self.ok(*self.clone())
        self.ok(*self.clone())
        self.assertEqual(len(self.js("order", "show", PROJECT, "lector")["attempts"]), 1)

    def test_clip_outside_the_project_is_refused_with_its_code(self):
        outside = self.wav(self.tmp / "fuera.wav")
        with self.assertRaises(GvoiceError) as ctx:  # the typed error is what main() prints
            cli._voice(cli._build("en").parse_args(self.clone(clip=outside)), cli._Out("en", False))
        self.assertEqual(ctx.exception.code, "order.clip_outside")
        self.fails(*self.clone(clip=outside), message="is outside the project")
        self.fails(*self.clone(clip=outside), message="fuera del proyecto", lang="es")
        self.assertEqual(self.js("order", "list", PROJECT), [])

    def test_a_link_out_of_the_project_is_outside(self):
        outside = self.wav(self.tmp / "fuera.wav")
        link = self.root / "enlace.wav"
        link.symlink_to(outside)
        self.fails(*self.clone(clip=link), message="is outside the project")

    def test_empty_text_is_a_schema_error(self):
        self.text.write_text(" \n ", encoding="utf-8")
        code, out, err = self.run_cli(*self.clone())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("/clip/text: must be at least 1 characters long", err)
        self.assertEqual(self.js("order", "list", PROJECT), [])

    def test_unreadable_text(self):
        self.fails("voice", "clone", PROJECT, "lector", str(self.clip), "--text", str(self.tmp / "nope.txt"),
                   message="could not read the clip text")
        self.text.write_bytes(b"\xff\xfe\x00bad")
        self.fails(*self.clone(), message="could not read the clip text")

    def test_text_option_is_required(self):
        code, _, err = self.run_cli("voice", "clone", PROJECT, "lector", str(self.clip))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

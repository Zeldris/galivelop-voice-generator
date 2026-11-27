import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import fsutil
from gvoice import projects
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "galivelop-voices.json").read_text())
CONFIG = "galivelop-voices.json"


class ProjectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {
            "GVOICE_CONFIG_HOME": str(self.tmp / "cfg"), "GVOICE_DATA_HOME": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)

    def make(self, name="proj", **changes):
        root = self.tmp / name
        root.mkdir(exist_ok=True)
        cfg = copy.deepcopy(EXAMPLE)
        cfg.pop("$schema", None)
        cfg["name"] = name
        for key, value in changes.items():
            if value is None:
                cfg.pop(key, None)
            else:
                cfg[key] = value
        (root / CONFIG).write_text(json.dumps(cfg))
        return root

    def code(self, fn, *args):
        with self.assertRaises(GvoiceError) as cm:
            fn(*args)
        return cm.exception

    def test_print_models_default_d14_when_missing(self):
        cfg = projects.load_config(self.make(printModels=None))
        self.assertEqual(cfg["printModels"], ["0.6b-base", "1.7b-base"])

    def test_print_models_default_is_not_shared_between_loads(self):
        root = self.make(printModels=None)
        projects.load_config(root)["printModels"].append("x")
        self.assertEqual(projects.load_config(root)["printModels"], ["0.6b-base", "1.7b-base"])

    def test_explicit_print_models_kept(self):
        cfg = projects.load_config(self.make(printModels=["1.7b-base"]))
        self.assertEqual(cfg["printModels"], ["1.7b-base"])

    def test_missing_and_bad_json(self):
        root = self.tmp / "empty"
        root.mkdir()
        self.assertEqual(self.code(projects.load_config, root).code, "project.config_missing")
        (root / CONFIG).write_text("{nope")
        self.assertEqual(self.code(projects.load_config, root).code, "project.config_unreadable")

    def test_schema_errors_listed_and_translated(self):
        err = self.code(projects.load_config, self.make(voices={}))
        self.assertEqual(err.code, "project.config_invalid")
        self.assertEqual([e.code for e in err.errors], ["minProperties"])
        self.assertIn("/voices", err.message("en"))
        self.assertIn("no es válido", err.message("es"))

    def test_unknown_print_model_rejected_by_schema(self):
        err = self.code(projects.load_config, self.make(printModels=["9b-base"]))
        self.assertEqual(err.code, "project.config_invalid")
        self.assertEqual([(e.path, e.code) for e in err.errors], [("/printModels/0", "enum")])

    def test_min_version(self):
        err = self.code(projects.load_config, self.make(minVersion="99.0.0"))
        self.assertEqual(err.code, "project.version_too_new")
        self.assertEqual(err.params["required"], "99.0.0")
        projects.load_config(self.make("ok", minVersion="0.1.0"))
        # numeric, not lexical: 0.10.0 > 0.9.0
        with mock.patch.object(projects, "__version__", "0.9.0"):
            self.assertEqual(
                self.code(projects.load_config, self.make("n", minVersion="0.10.0")).code,
                "project.version_too_new")

    def test_delivery_guards(self):
        cases = [
            ({"delivery": {"dir": ".git"}}, "project.forbidden_git"),
            ({"delivery": {"dir": ".git/voices"}}, "project.forbidden_git"),
            ({"delivery": {"dir": "a/.GIT/x"}}, "project.forbidden_git"),
            ({"delivery": {"dir": CONFIG}}, "project.forbidden_config"),
            ({"delivery": {"dir": "Galivelop-Voices.JSON"}}, "project.forbidden_config"),
            ({"delivery": {"dir": "a/../x"}}, "project.config_invalid"),
            ({"delivery": {"dir": "/abs"}}, "project.config_invalid"),
        ]
        for i, (change, code) in enumerate(cases):
            with self.subTest(change=change):
                err = self.code(projects.load_config, self.make("c%d" % i, **change))
                self.assertEqual(err.code, code)

    def test_delivery_symlink_into_git_or_outside(self):
        root = self.make("lnk")
        (root / ".git").mkdir()
        os.symlink(root / ".git", root / "sneaky")
        (root / CONFIG).write_text(json.dumps(dict(EXAMPLE, name="lnk", delivery={"dir": "sneaky"})))
        self.assertEqual(self.code(projects.load_config, root).code, "project.forbidden_git")
        os.symlink(self.tmp, root / "away")
        (root / CONFIG).write_text(json.dumps(dict(EXAMPLE, name="lnk", delivery={"dir": "away/v"})))
        self.assertEqual(self.code(projects.load_config, root).code, "path.outside")

    def test_registry_add_get_list_remove(self):
        a, b = self.make("alpha"), self.make("beta")
        self.assertEqual(projects.list_projects(), {})
        self.assertEqual(projects.add(a), "alpha")
        projects.add(b)
        projects.add(a)  # same name, same path: fine
        self.assertEqual(list(projects.list_projects()), ["alpha", "beta"])
        got = projects.get("alpha")
        self.assertEqual(got["root"], str(a))
        self.assertEqual(got["config"]["name"], "alpha")
        projects.remove("alpha")
        self.assertEqual(list(projects.list_projects()), ["beta"])
        self.assertEqual(self.code(projects.get, "alpha").code, "project.unknown")
        self.assertEqual(self.code(projects.remove, "alpha").code, "project.unknown")

    def test_same_name_other_path(self):
        a = self.make("alpha")
        other = self.tmp / "elsewhere"
        other.mkdir()
        (other / CONFIG).write_text((a / CONFIG).read_text())
        projects.add(a)
        err = self.code(projects.add, other)
        self.assertEqual(err.code, "project.name_taken")
        self.assertEqual(err.params["root"], str(a))

    def test_add_invalid_does_not_register(self):
        root = self.make("bad", voices={})
        self.assertEqual(self.code(projects.add, root).code, "project.config_invalid")
        self.assertEqual(projects.list_projects(), {})
        self.assertEqual(self.code(projects.add, self.tmp / "nope").code, "project.root_not_dir")

    def test_config_reread_each_time(self):
        root = self.make("alpha")
        projects.add(root)
        self.assertEqual(projects.get("alpha")["config"]["delivery"]["dir"], "uploads/voices")
        cfg = json.loads((root / CONFIG).read_text())
        cfg["delivery"]["dir"] = "other"
        (root / CONFIG).write_text(json.dumps(cfg))
        self.assertEqual(projects.get("alpha")["config"]["delivery"]["dir"], "other")

    def test_corrupt_registry(self):
        fsutil.write_json(projects.registry_path(), {"projects": {"x": 3}})
        self.assertEqual(self.code(projects.list_projects).code, "project.registry_corrupt")
        projects.registry_path().write_text('{"projects": {', encoding="utf-8")
        self.assertEqual(self.code(projects.list_projects).code, "project.registry_corrupt")


class ErrorMessageTests(unittest.TestCase):
    def test_every_error_code_used_has_text_in_both_languages(self):
        import re
        from gvoice import i18n
        # the codes grun raises on behalf of gvoice (path guard, machine lock, limits, queue) need gvoice's texts too
        src = "".join((ROOT / d / f).read_text() for d, f in (("gvoice", "projects.py"), ("grun", "paths.py"),
                                                              ("grun", "machine_lock.py"), ("grun", "limits.py"),
                                                              ("grun", "queue.py")))
        codes = set(re.findall(r'(?:Error|GvoiceError|make_error)\(\s*"([a-z_.]+)"', src))
        self.assertLessEqual({"queue.bad_item", "queue.invalid_transition", "queue.orphaned"}, codes)
        self.assertGreater(len(codes), 15)
        for code in codes:
            for lang in ("es", "en"):
                self.assertNotEqual(i18n.t("error." + code, lang, path="p", name="n", field="f", reason="r",
                                          required="1", current="0", root="r", limit=1, segment="s",
                                          project="p", free=1, min=2, index=0, to="up", allowed="a", progress="p",
                                          states="s", state="queued", id=1, from_state="a", to_state="b",
                                          count=2),
                                 "error." + code, (lang, code))

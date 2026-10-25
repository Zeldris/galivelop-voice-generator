# Copiado de gimg@0d02f51 (D7); cambia: galivelop-voices.json, GVOICE_*, sin plantilla ni manifiesto, y print_models.
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import fsutil, projects, schema
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

    def test_load_returns_validated_config(self):
        cfg = projects.load_config(self.make(delivery={"dir": "out"}))
        self.assertEqual(cfg["delivery"], {"dir": "out"})
        self.assertEqual(sorted(cfg["voices"]), ["narrator", "orc"])

    def test_missing_and_bad_json(self):
        root = self.tmp / "empty"
        root.mkdir()
        self.assertEqual(self.code(projects.load_config, root).code, "project.config_missing")
        (root / CONFIG).write_text("{nope")
        self.assertEqual(self.code(projects.load_config, root).code, "project.config_unreadable")

    def test_not_an_object(self):
        root = self.tmp / "list"
        root.mkdir()
        (root / CONFIG).write_text("[]")
        self.assertEqual(self.code(projects.load_config, root).code, "project.config_invalid")

    def test_schema_errors_listed_and_translated(self):
        err = self.code(projects.load_config, self.make(voices={}))
        self.assertEqual(err.code, "project.config_invalid")
        self.assertEqual([e.code for e in err.errors], ["minProperties"])
        self.assertIn("/voices", err.message("en"))
        self.assertIn("no es válido", err.message("es"))

    def test_delivery_is_required(self):
        err = self.code(projects.load_config, self.make(delivery=None))
        self.assertEqual(err.code, "project.config_invalid")
        self.assertEqual([(e.path, e.code) for e in err.errors], [("", "required")])

    def test_unknown_print_model_rejected(self):
        err = self.code(projects.load_config, self.make(printModels=["9b-base"]))
        self.assertEqual(err.code, "project.config_invalid")
        self.assertEqual([e.code for e in err.errors], ["enum"])

    def test_repeated_print_model_rejected(self):
        err = self.code(projects.load_config, self.make(printModels=["0.6b-base", "0.6b-base"]))
        self.assertEqual(err.code, "project.config_invalid")
        self.assertEqual([e.code for e in err.errors], ["uniqueItems"])

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
            ({"delivery": {"dir": "galivelop-voices.json"}}, "project.forbidden_config"),
            ({"delivery": {"dir": "."}}, "project.forbidden_root"),
            ({"delivery": {"dir": "Galivelop-Voices.JSON"}}, "project.forbidden_config"),
            ({"delivery": {"dir": "a/../galivelop-voices.json"}}, "project.config_invalid"),
            ({"delivery": {"dir": "/etc"}}, "project.config_invalid"),
            ({"delivery": {"dir": "~/x"}}, "project.config_invalid"),
            ({"delivery": {"dir": "a\\b"}}, "project.config_invalid"),
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

    def test_registry_lives_in_config_dir(self):
        self.assertEqual(projects.registry_path(), self.tmp / "cfg" / "projects.json")
        projects.add(self.make("alpha"))
        self.assertTrue((self.tmp / "cfg" / "projects.json").is_file())

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

    def test_add_too_new_does_not_register(self):
        root = self.make("new", minVersion="99.0.0")
        self.assertEqual(self.code(projects.add, root).code, "project.version_too_new")
        self.assertEqual(projects.list_projects(), {})

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
        projects.registry_path().write_text("[]", encoding="utf-8")
        self.assertEqual(self.code(projects.list_projects).code, "project.registry_corrupt")


class PrintModelsTests(unittest.TestCase):
    def base_models(self):
        return schema.load_schema("common")["$defs"]["baseModel"]["enum"]

    def test_explicit_print_models(self):
        self.assertEqual(projects.print_models({"printModels": ["1.7b-base"]}), ["1.7b-base"])

    def test_explicit_order_kept(self):
        self.assertEqual(
            projects.print_models({"printModels": ["1.7b-base", "0.6b-base"]}), ["1.7b-base", "0.6b-base"])

    def test_default_is_the_schema_enum_in_order(self):
        got = projects.print_models({})
        self.assertEqual(got, self.base_models())
        self.assertEqual(got, ["0.6b-base", "1.7b-base"])  # D14

    def test_default_follows_the_schema(self):
        fake = {"$defs": {"baseModel": {"enum": ["x-base", "y-base"]}}}
        with mock.patch.object(projects.schema, "load_schema", return_value=fake):
            self.assertEqual(projects.print_models({}), ["x-base", "y-base"])

    def test_returns_a_copy(self):
        cfg = {"printModels": ["0.6b-base"]}
        projects.print_models(cfg).append("z")
        self.assertEqual(cfg["printModels"], ["0.6b-base"])
        projects.print_models({}).append("z")
        self.assertEqual(projects.print_models({}), self.base_models())

    def test_loaded_example_without_print_models(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg.pop("printModels")
        self.assertEqual(schema.validate(cfg, schema.load_schema("project-config")), [])
        self.assertEqual(projects.print_models(cfg), self.base_models())

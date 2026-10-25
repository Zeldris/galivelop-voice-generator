# Copiado de gimg@0d02f51 (`test_limits.py`, D7); cambia: GVOICE_*, módulo `machine`, sin pruebas de `check`.
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import machine
from gvoice.errors import GvoiceError

MIN = {"name": "tiny", "minFreeMemoryMb": 1, "watchMemoryMb": 1, "timeoutS": 9,
       "engine": {"device": "cpu"}, "models": {"design": "1.7b-voicedesign", "produce": ["0.6b-base"]}}


class LoadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GVOICE_CONFIG_HOME": str(self.tmp / "cfg"),
                                           "GVOICE_DATA_HOME": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GVOICE_MACHINE_PROFILE", None)

    def code(self, *args):
        with self.assertRaises(GvoiceError) as cm:
            machine.load_machine(*args)
        return cm.exception.code

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data))
        return str(path)

    def test_default_is_steam_deck(self):
        m = machine.load_machine()
        self.assertEqual(m["name"], "steam-deck")
        self.assertEqual(m["engine"]["device"], "Vulkan0")
        self.assertGreater(m["timeoutS"], 0)

    def test_env_preset_beats_config(self):
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": "nope"})
        with mock.patch.dict(os.environ, {"GVOICE_MACHINE_PROFILE": "steam-deck"}):
            self.assertEqual(machine.load_machine()["name"], "steam-deck")

    def test_env_path(self):
        p = self.write(self.tmp / "m.json", MIN)
        with mock.patch.dict(os.environ, {"GVOICE_MACHINE_PROFILE": p}):
            self.assertEqual(machine.load_machine()["name"], "tiny")

    def test_config_used_when_no_env(self):
        p = self.write(self.tmp / "m.json", MIN)
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": p})
        self.assertEqual(machine.load_machine()["name"], "tiny")

    def test_config_unknown_preset(self):
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": "nope"})
        self.assertEqual(self.code(), "machine.missing")

    def test_corrupt_config_json_is_translated(self):
        (self.tmp / "cfg").mkdir()
        (self.tmp / "cfg" / "config.json").write_text("{nope")
        with self.assertRaises(GvoiceError) as cm:
            machine.load_machine()
        self.assertEqual(cm.exception.code, "machine.config_unreadable")
        self.assertIn(str(self.tmp / "cfg" / "config.json"), cm.exception.message("en"))

    def test_tilde_unresolvable(self):
        with mock.patch.dict(os.environ, {"HOME": ""}), mock.patch(
                "pathlib.Path.expanduser", side_effect=RuntimeError("no home")):
            self.assertEqual(self.code("~nobody/x.json"), "machine.unreadable")

    def test_tilde_expanded(self):
        self.write(self.tmp / "home" / "m.json", MIN)
        with mock.patch.dict(os.environ, {"HOME": str(self.tmp / "home")}):
            self.assertEqual(machine.load_machine("~/m.json")["name"], "tiny")

    def test_control_chars_in_path(self):
        for bad in ("a\x00/b.json", "a\n/b.json", "a/\x1bb.json"):
            self.assertEqual(self.code(bad), "machine.bad_path")

    def test_bad_names(self):
        for bad in ("UPPER", "-x", "a b", "x\n"):
            self.assertEqual(self.code(bad), "machine.bad_name", bad)

    def test_path_forms_are_files_not_presets(self):
        self.assertEqual(self.code("../x"), "machine.missing")
        self.assertEqual(self.code("a/b"), "machine.missing")

    def test_invalid_json(self):
        p = self.write(self.tmp / "m.json", "{nope")
        self.assertEqual(self.code(p), "machine.unreadable")

    def test_invalid_schema(self):
        p = self.write(self.tmp / "m.json", {"name": "x"})
        with self.assertRaises(GvoiceError) as cm:
            machine.load_machine(p)
        self.assertEqual(cm.exception.code, "machine.invalid")
        self.assertTrue(cm.exception.errors)

    def test_non_string_config_value(self):
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": 3})
        self.assertEqual(self.code(), "machine.bad_name")

    def test_messages_translated(self):
        for lang in ("es", "en"):
            for ref in ("nope", "UPPER", "a\x00.json"):
                try:
                    machine.load_machine(ref)
                except GvoiceError as exc:
                    self.assertNotIn("error.", exc.message(lang))


if __name__ == "__main__":
    unittest.main()

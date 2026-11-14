import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import limits
from gvoice.errors import GvoiceError

STEAM = {"name": "steam-deck", "minFreeMemoryMb": 4096, "watchMemoryMb": 1536, "timeoutS": 900,
         "models": {"design": "1.7b-voicedesign", "produce": ["0.6b-base", "1.7b-base"]}}
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
            limits.load_machine(*args)
        return cm.exception.code

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data))
        return str(path)

    def test_default_is_steam_deck_with_its_limits(self):
        m = limits.load_machine()
        self.assertEqual((m["name"], limits.timeout_s(m)), ("steam-deck", 900))
        self.assertEqual(m["watchMemoryMb"], 1536)

    def test_corrupt_config_json_is_translated(self):
        (self.tmp / "cfg").mkdir()
        (self.tmp / "cfg" / "config.json").write_text("{nope")
        with self.assertRaises(GvoiceError) as cm:
            limits.load_machine()
        self.assertEqual(cm.exception.code, "machine.config_unreadable")
        self.assertIn(str(self.tmp / "cfg" / "config.json"), cm.exception.message("en"))

    def test_tilde_unresolvable(self):
        with mock.patch("pathlib.Path.expanduser", side_effect=RuntimeError("no home")):
            self.assertEqual(self.code("~nobody/x.json"), "machine.unreadable")

    def test_tilde_expanded(self):
        self.write(self.tmp / "home" / "m.json", MIN)
        with mock.patch.dict(os.environ, {"HOME": str(self.tmp / "home")}):
            self.assertEqual(limits.load_machine("~/m.json")["name"], "tiny")

    def test_control_chars_in_path(self):
        for bad in ("a\x00/b.json", "a\n/b.json", "a/\x1bb.json"):
            self.assertEqual(self.code(bad), "machine.bad_path")

    def test_env_preset_beats_config(self):
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": "nope"})
        with mock.patch.dict(os.environ, {"GVOICE_MACHINE_PROFILE": "steam-deck"}):
            self.assertEqual(limits.load_machine()["name"], "steam-deck")

    def test_env_path(self):
        p = self.write(self.tmp / "m.json", MIN)
        with mock.patch.dict(os.environ, {"GVOICE_MACHINE_PROFILE": p}):
            self.assertEqual(limits.load_machine()["name"], "tiny")

    def test_config_used_when_no_env(self):
        p = self.write(self.tmp / "m.json", MIN)
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": p})
        self.assertEqual(limits.load_machine()["name"], "tiny")

    def test_config_unknown_preset(self):
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": "nope"})
        self.assertEqual(self.code(), "machine.missing")

    def test_bad_names(self):
        for bad in ("UPPER", "-x", "a b", "x\n"):
            self.assertEqual(self.code(bad), "machine.bad_name", bad)

    def test_path_forms_are_files_not_presets(self):
        self.assertEqual(self.code("../x"), "machine.missing")
        self.assertEqual(self.code("a/b"), "machine.missing")

    def test_invalid_json(self):
        self.assertEqual(self.code(self.write(self.tmp / "m.json", "{nope")), "machine.unreadable")

    def test_invalid_schema_says_what_is_missing(self):
        with self.assertRaises(GvoiceError) as cm:
            limits.load_machine(self.write(self.tmp / "m.json", {"name": "x"}))
        self.assertEqual(cm.exception.code, "machine.invalid")
        self.assertIn("minFreeMemoryMb", cm.exception.message("en"))

    def test_non_string_config_value(self):
        self.write(self.tmp / "cfg" / "config.json", {"machineProfile": 3})
        self.assertEqual(self.code(), "machine.bad_name")

    def test_messages_translated(self):
        for lang in ("es", "en"):
            try:
                limits.load_machine("nope")
            except GvoiceError as exc:
                self.assertNotIn("error.", exc.message(lang))


class CheckTests(unittest.TestCase):
    def test_memory_start_limit(self):
        limits.check_memory(4096, STEAM)
        with self.assertRaises(limits.LimitError) as cm:
            limits.check_memory(4095, STEAM)
        self.assertIsInstance(cm.exception, GvoiceError)
        self.assertEqual((cm.exception.code, cm.exception.params), ("limit.memory", {"free": 4095, "min": 4096}))
        limits.check_memory(None, STEAM)  # unknown passes
        limits.check_memory(1, {})  # no limit in the profile

    def test_abort_below_watch_memory(self):
        self.assertFalse(limits.must_abort(1536, STEAM))
        self.assertTrue(limits.must_abort(1535, STEAM))
        self.assertFalse(limits.must_abort(None, STEAM))
        self.assertFalse(limits.must_abort(1, {}))

    def test_models_by_use(self):
        limits.check_model("design", "1.7b-voicedesign", STEAM)
        limits.check_model("produce", "1.7b-base", STEAM)
        with self.assertRaises(limits.LimitError) as cm:
            limits.check_model("produce", "1.7b-base", MIN)
        self.assertEqual(cm.exception.code, "limit.model")
        self.assertEqual(cm.exception.params, {"model": "1.7b-base", "use": "produce", "allowed": "0.6b-base"})
        with self.assertRaises(limits.LimitError) as cm:
            limits.check_model("design", "0.6b-base", STEAM)
        self.assertEqual(cm.exception.params["allowed"], "1.7b-voicedesign")
        limits.check_model("produce", "anything", {})  # no models in the profile

    def test_meminfo_and_proc_status_paths_come_from_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            info, status = Path(tmp) / "m", Path(tmp) / "s{pid}"
            info.write_text("MemAvailable: 3145728 kB\n")
            Path(tmp, "s42").write_text("VmHWM:\t 1048576 kB\n")
            with mock.patch.dict(os.environ, {limits.MEMINFO_ENV: str(info), limits.PROC_STATUS_ENV: str(status)}):
                self.assertEqual(limits.available_memory_mb(), 3072)
                self.assertEqual(limits.peak_rss_mb(42), 1024)
                self.assertIsNone(limits.peak_rss_mb(43))

    def test_available_memory(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "meminfo"
            p.write_text("MemTotal: 999 kB\nMemAvailable:    2097152 kB\n")
            self.assertEqual(limits.available_memory_mb(str(p)), 2048)
            p.write_text("MemTotal: 999 kB\n")
            self.assertIsNone(limits.available_memory_mb(str(p)))
            p.write_text("MemAvailable: lots kB\n")
            self.assertIsNone(limits.available_memory_mb(str(p)))
            self.assertIsNone(limits.available_memory_mb(str(Path(d) / "nope")))

    def test_messages(self):
        for lang in ("es", "en"):
            for code, params in (("limit.memory", {"free": 1, "min": 2}),
                                 ("limit.model", {"model": "m", "use": "u", "allowed": "a"})):
                self.assertNotIn("error.", limits.LimitError(code, **params).message(lang))


if __name__ == "__main__":
    unittest.main()

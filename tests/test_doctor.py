import hashlib
import json
import os
import stat
from unittest import mock

from gvoice import install
from tests.test_bench import PROFILE
from tests.test_cli import CliBase
from tests.test_qwentts import clean_env, install_fake


def small_models():
    """Tiny stand-ins for the model files, with their size and sha256 patched into `install.MODEL_SHA256`."""
    table = {}
    install.models_dir().mkdir(parents=True, exist_ok=True)
    for n, name in enumerate(list(install.MODEL_FILES.values()) + [install.CODEC_FILE]):
        data = (b"model-%d-" % n) * (n + 3)
        (install.models_dir() / name).write_bytes(data)
        table[name] = (len(data), hashlib.sha256(data).hexdigest())
    return table


class DoctorBase(CliBase):
    def setUp(self):
        super().setUp()
        clean_env()
        os.environ["GVOICE_ENGINE"] = "qwentts"
        profile = self.tmp / "profile.json"
        profile.write_text(json.dumps(PROFILE))
        os.environ["GVOICE_MACHINE_PROFILE"] = str(profile)
        install_fake()
        patch = mock.patch.dict(install.MODEL_SHA256, small_models())
        patch.start()
        self.addCleanup(patch.stop)

    def diagnose(self, *argv, code=None):
        got, out, err = self.run_cli("--json", "doctor", *argv)
        self.assertEqual(err, "")
        if code is not None:
            self.assertEqual(got, code, out)
        return json.loads(out)

    def failed(self, checks):
        return [c for c in checks if not c["ok"]]

    def warned(self, checks):
        return [c for c in checks if c["ok"] and c["warning"]]


class DoctorTests(DoctorBase):
    def test_all_good(self):
        checks = self.diagnose(code=0)
        self.assertEqual(self.failed(checks), [])
        self.assertEqual(self.warned(checks), [])
        kinds = [c["check"] for c in checks]
        self.assertEqual(kinds.count("model"), 3)
        self.assertEqual(kinds.count("codec"), 1)
        self.assertEqual(kinds.count("binary"), 4)
        self.assertEqual(checks[0]["engine"], "qwentts")
        profile = next(c for c in checks if c["check"] == "profile")
        self.assertEqual((profile["name"], profile["device"], profile["fallback"], profile["design"]),
                         ("bench-test", "Vulkan0", "cpu", "1.7b-voicedesign"))
        commit = next(c for c in checks if c["check"] == "commit")
        self.assertEqual(commit["code"], "commit_ok")
        self.assertTrue(all(isinstance(c["message"], str) and c["message"] for c in checks))
        self.assertTrue(all(c["code"] == "file_ok" for c in checks if c["check"] in ("model", "codec")))

    def test_text_output(self):
        out = self.ok("doctor")
        self.assertIn("[ok] configured engine: qwentts", out)
        self.assertIn("[ok] 0.6b-base: correct", out)
        self.assertTrue(out.rstrip().endswith("All good."))

    def test_spanish_text(self):
        out = self.ok("--lang", "es", "doctor")
        self.assertIn("[ok] motor configurado: qwentts", out)
        self.assertTrue(out.rstrip().endswith("Todo en orden."))

    def test_missing_model(self):
        install.model_path("1.7b-base").unlink()
        checks = self.diagnose(code=1)
        bad, = self.failed(checks)
        self.assertEqual((bad["check"], bad["code"], bad["name"]), ("model", "file_missing", "1.7b-base"))
        code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] 1.7b-base: does not exist", out)
        self.assertIn("1 checks failed.", out)

    def test_wrong_size(self):
        install.codec_path().write_bytes(b"short")
        bad, = self.failed(self.diagnose(code=1))
        self.assertEqual((bad["check"], bad["code"], bad["size"]), ("codec", "file_size", 5))
        self.assertEqual(bad["expected"], install.MODEL_SHA256[install.CODEC_FILE][0])

    def test_bad_sha256(self):
        path = install.model_path("0.6b-base")
        data = bytearray(path.read_bytes())
        data[0] ^= 1  # same size, other content
        path.write_bytes(bytes(data))
        bad, = self.failed(self.diagnose(code=1))
        self.assertEqual((bad["check"], bad["code"], bad["name"]), ("model", "file_sha", "0.6b-base"))
        self.assertEqual(bad["sha256"], hashlib.sha256(bytes(data)).hexdigest())
        self.assertNotEqual(bad["sha256"], bad["expected"])

    def test_quick_skips_the_hash_but_checks_the_size(self):
        path = install.model_path("0.6b-base")
        data = bytearray(path.read_bytes())
        data[0] ^= 1
        path.write_bytes(bytes(data))
        with mock.patch("gvoice.doctor.sha256_of", side_effect=AssertionError("hashed")):
            checks = self.diagnose("--quick", code=0)
            self.assertEqual(self.failed(checks), [])
            checks = self.diagnose("--rapido", code=0)
        self.assertEqual({c["code"] for c in checks if c["check"] in ("model", "codec")}, {"file_quick"})
        path.write_bytes(b"x")
        bad, = self.failed(self.diagnose("--quick", code=1))
        self.assertEqual(bad["code"], "file_size")

    def test_install_missing(self):
        (install.engine_dir() / "install.json").unlink()
        checks = self.diagnose(code=1)
        bad, = self.failed(checks)
        self.assertEqual((bad["check"], bad["code"]), ("install", "install_missing"))
        self.assertEqual(bad["path"], str(install.engine_dir()))
        self.assertIn("instalar.sh", bad["message"])
        self.assertNotIn("binary", [c["check"] for c in checks])  # nothing to look for without the record

    def test_install_unreadable(self):
        (install.engine_dir() / "install.json").write_text("{not json")
        bad, = self.failed(self.diagnose(code=1))
        self.assertEqual(bad["code"], "install_unreadable")
        self.assertIn("install.json", bad["error"])

    def test_missing_binary(self):
        install.binary("qwen-codec", "cpu").unlink()
        bad, = self.failed(self.diagnose(code=1))
        self.assertEqual((bad["check"], bad["code"], bad["program"], bad["device"]),
                         ("binary", "binary_missing", "qwen-codec", "cpu"))

    def test_binary_not_executable(self):
        path = install.binary("qwen-tts", "Vulkan0")
        path.chmod(path.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        if os.access(path, os.X_OK):
            self.skipTest("running as a user that can execute anything")
        bad, = self.failed(self.diagnose(code=1))
        self.assertEqual((bad["code"], bad["program"], bad["device"]), ("binary_not_executable", "qwen-tts", "Vulkan0"))

    def test_profile_device_not_installed_is_a_warning(self):
        for name in ("qwen-tts", "qwen-codec"):
            install.binary(name, "Vulkan0").unlink()
        (install.engine_dir() / "install.json").write_text(json.dumps(
            {"commit": install.ENGINE_COMMIT, "devices": ["cpu"], "installedAt": "2026-11-11T00:00:00Z"}))
        checks = self.diagnose(code=0)  # a warning is not a failure
        self.assertEqual(self.failed(checks), [])
        warn, = self.warned(checks)
        self.assertEqual((warn["check"], warn["code"], warn["role"], warn["device"]),
                         ("profile_device", "profile_device_missing", "device", "Vulkan0"))
        out = self.ok("doctor")
        self.assertIn("[warning] the profile's device (Vulkan0) is not in the install", out)
        self.assertIn("All good, with 1 warnings.", out)

    def test_other_commit_is_a_warning(self):
        (install.engine_dir() / "install.json").write_text(json.dumps(
            {"commit": "abc123", "devices": ["Vulkan0", "cpu"], "installedAt": "2026-11-11T00:00:00Z"}))
        warn, = self.warned(self.diagnose(code=0))
        self.assertEqual((warn["code"], warn["commit"], warn["expected"]),
                         ("commit_differs", "abc123", install.ENGINE_COMMIT))

    def test_bad_profile_fails(self):
        (self.tmp / "profile.json").write_text("{}")
        checks = self.diagnose(code=1)
        bad, = self.failed(checks)
        self.assertEqual((bad["check"], bad["code"]), ("profile", "profile_bad"))

    def test_starts_no_engine_process(self):
        log = self.tmp / "calls.jsonl"
        os.environ["FAKE_LOG"] = str(log)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("started a process")):
            self.diagnose(code=0)
        self.assertFalse(log.exists())


class FakeEngineDoctor(CliBase):
    def test_fake_engine_checks_only_engine_and_profile(self):
        got = json.loads(self.ok("--json", "doctor"))
        self.assertEqual([c["check"] for c in got], ["engine", "profile"])
        self.assertTrue(all(c["ok"] for c in got))

    def test_unknown_engine_fails(self):
        os.environ["GVOICE_ENGINE"] = "nope"
        code, out, err = self.run_cli("--json", "doctor")
        self.assertEqual(code, 1)
        engine_check = json.loads(out)[0]
        self.assertEqual((engine_check["code"], engine_check["engine"], engine_check["ok"]),
                         ("engine_unknown", "nope", False))

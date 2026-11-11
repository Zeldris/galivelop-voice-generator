import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import install, schema
from gvoice.errors import GvoiceError


class InstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name).resolve() / "data"
        env = mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": str(self.data)})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GVOICE_MODELS_HOME", None)

    def code(self, fn, *args):
        with self.assertRaises(GvoiceError) as cm:
            fn(*args)
        return cm.exception

    def test_engine_and_models_dirs(self):
        self.assertEqual(install.engine_dir(), self.data / "engine")
        self.assertEqual(install.models_dir(), self.data / "models")

    def test_bin_dir_by_device(self):
        for device in ("Vulkan0", "vulkan0", "VULKAN1"):
            self.assertEqual(install.bin_dir(device), self.data / "engine" / "bin-vulkan")
        for device in ("cpu", "CPU"):
            self.assertEqual(install.bin_dir(device), self.data / "engine" / "bin-cpu")
        self.assertEqual(self.code(install.bin_dir, "cuda").code, "install.unknown_device")

    def test_binary(self):
        self.assertEqual(install.binary("qwen-tts", "Vulkan0"), self.data / "engine" / "bin-vulkan" / "qwen-tts")
        self.assertEqual(install.binary("tts-server", "CPU"), self.data / "engine" / "bin-cpu" / "tts-server")
        self.assertEqual(self.code(install.binary, "rm", "CPU").code, "install.unknown_binary")

    def test_model_files_and_checksums(self):
        self.assertEqual(install.model_path("1.7b-voicedesign"),
                         self.data / "models" / "qwen-talker-1.7b-voicedesign-Q8_0.gguf")
        self.assertEqual(install.model_path("0.6b-base").name, "qwen-talker-0.6b-base-Q8_0.gguf")
        self.assertEqual(install.model_path("1.7b-base").name, "qwen-talker-1.7b-base-Q8_0.gguf")
        self.assertEqual(set(install.MODEL_SHA256), set(install.MODEL_FILES.values()) | {install.CODEC_FILE})
        for size, digest in install.MODEL_SHA256.values():
            self.assertGreater(size, 0)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(install.MODEL_SHA256[install.CODEC_FILE][0], 291150624)

    def test_model_names_match_the_schema(self):
        names = set(schema.load_schema("common")["$defs"]["baseModel"]["enum"]) | {"1.7b-voicedesign"}
        self.assertEqual(set(install.MODEL_FILES), names)

    def test_unknown_model(self):
        err = self.code(install.model_path, "9b-base")
        self.assertEqual(err.code, "install.unknown_model")
        self.assertIn("9b-base", err.message("en"))
        self.assertIn("modelo desconocido", err.message("es"))

    def test_read_install_missing_is_none(self):
        self.assertIsNone(install.read_install())

    def test_read_install(self):
        record = {"commit": install.ENGINE_COMMIT, "devices": ["Vulkan0", "CPU"],
                  "installedAt": "2026-11-11T10:00:00Z"}
        (self.data / "engine").mkdir(parents=True)
        (self.data / "engine" / "install.json").write_text(json.dumps(record))
        self.assertEqual(install.read_install(), record)

    def test_read_install_broken(self):
        (self.data / "engine").mkdir(parents=True)
        path = self.data / "engine" / "install.json"
        for content in ("{not json", "[]", json.dumps({"commit": "x"})):
            with self.subTest(content=content):
                path.write_text(content)
                err = self.code(install.read_install)
                self.assertEqual(err.code, "install.unreadable")
                self.assertIn(str(path), err.message("en"))

    def test_commit(self):
        self.assertEqual(install.ENGINE_COMMIT, "5916bf7c79dbb4e66fc059cdc507a79a23a28bb4")


if __name__ == "__main__":
    unittest.main()

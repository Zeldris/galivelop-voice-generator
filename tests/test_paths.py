import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import paths
from gvoice.errors import GvoiceError, PathError


class FolderTests(unittest.TestCase):
    def env(self, **kw):
        base = {k: "" for k in ("GVOICE_CONFIG_HOME", "GVOICE_DATA_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME")}
        base.update(kw)
        return mock.patch.dict(os.environ, base)

    def test_explicit_wins(self):
        with self.env(GVOICE_CONFIG_HOME="/a", XDG_CONFIG_HOME="/x", GVOICE_DATA_HOME="/b", XDG_DATA_HOME="/y"):
            self.assertEqual(paths.config_dir(), Path("/a"))
            self.assertEqual(paths.data_dir(), Path("/b"))

    def test_xdg(self):
        with self.env(XDG_CONFIG_HOME="/x", XDG_DATA_HOME="/y"):
            self.assertEqual(paths.config_dir(), Path("/x/galivelop-voice"))
            self.assertEqual(paths.data_dir(), Path("/y/galivelop-voice"))

    def test_relative_xdg_ignored(self):
        with self.env(HOME="/h", XDG_CONFIG_HOME="rel", XDG_DATA_HOME="./rel"):
            self.assertEqual(paths.config_dir(), Path("/h/.config/galivelop-voice"))
            self.assertEqual(paths.data_dir(), Path("/h/.local/share/galivelop-voice"))

    def test_home_fallback(self):
        with self.env(HOME="/h"):
            self.assertEqual(paths.config_dir(), Path("/h/.config/galivelop-voice"))
            self.assertEqual(paths.data_dir(), Path("/h/.local/share/galivelop-voice"))


class EngineModelsTests(unittest.TestCase):
    def test_engine_and_models_under_data(self):
        with mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": "/d", "GVOICE_MODELS_HOME": ""}):
            self.assertEqual(paths.engine_dir(), Path("/d/engine"))
            self.assertEqual(paths.models_dir(), Path("/d/models"))

    def test_models_home_wins(self):
        with mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": "/d", "GVOICE_MODELS_HOME": "/sd"}):
            self.assertEqual(paths.models_dir(), Path("/sd"))


class ProjectDataDirTests(unittest.TestCase):
    def test_valid_name_and_rejections(self):
        with mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": "/d"}):
            self.assertEqual(paths.project_data_dir("my-game"), Path("/d/projects/my-game"))
            for bad in ("..", ".", "a/b", "A", "", None, "ok\n"):
                with self.subTest(bad=bad):
                    with self.assertRaises(GvoiceError) as cm:
                        paths.project_data_dir(bad)
                    self.assertEqual(cm.exception.code, "project.bad_name")
                    self.assertEqual(cm.exception.params["project"], str(bad))


class InsideTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.root = self.tmp / "root"
        self.root.mkdir()
        self.outside = self.tmp / "outside"
        self.outside.mkdir()

    def reason(self, rel, root=None):
        with self.assertRaises(PathError) as cm:
            paths.inside(root or self.root, rel)
        return cm.exception.code

    def test_rejections_with_reason(self):
        cases = [
            ("/etc/passwd", "path.absolute"),
            ("~", "path.tilde"),
            ("~/x", "path.tilde"),
            ("..", "path.dotdot"),
            ("../x", "path.dotdot"),
            ("a/../x", "path.dotdot"),
            ("a/..", "path.dotdot"),
            ("a\\b", "path.backslash"),
            ("a\x00b", "path.nul"),
            ("a\nb", "path.control"),
            ("a\tb", "path.control"),
            ("a\x7fb", "path.control"),
            ("", "path.empty"),
            (None, "path.type"),
        ]
        for rel, code in cases:
            with self.subTest(rel=rel):
                self.assertEqual(self.reason(rel), code)

    def test_dots_inside_names_are_fine(self):
        self.assertEqual(paths.inside(self.root, "a..b/c"), self.root / "a..b" / "c")

    def test_nonexistent_target(self):
        self.assertEqual(paths.inside(self.root, "new/dir/x.wav"), self.root / "new/dir/x.wav")

    def test_symlink_outside_rejected(self):
        os.symlink(self.outside, self.root / "link")
        self.assertEqual(self.reason("link/x.wav"), "path.outside")
        self.assertEqual(self.reason("link"), "path.outside")

    def test_symlink_to_file_outside_rejected(self):
        (self.outside / "f").write_text("x")
        os.symlink(self.outside / "f", self.root / "flink")
        self.assertEqual(self.reason("flink"), "path.outside")

    def test_symlink_inside_ok(self):
        (self.root / "real").mkdir()
        os.symlink(self.root / "real", self.root / "alias")
        self.assertEqual(paths.inside(self.root, "alias/x.wav"), self.root / "real" / "x.wav")

    def test_root_is_symlink(self):
        link = self.tmp / "rootlink"
        os.symlink(self.root, link)
        self.assertEqual(paths.inside(link, "a/x.wav"), self.root / "a" / "x.wav")
        os.symlink(self.outside, self.root / "out")
        self.assertEqual(self.reason("out/x", root=link), "path.outside")

    def test_symlink_loop(self):
        os.symlink(self.root / "b", self.root / "a")
        os.symlink(self.root / "a", self.root / "b")
        # Depending on the Python version the loop raises or resolves in place;
        # either way the guard never lets a path out of the root.
        try:
            target = paths.inside(self.root, "a/x")
        except PathError as exc:
            self.assertEqual(exc.code, "path.unresolvable")
        else:
            self.assertIn(self.root, target.parents)

    def test_root_itself(self):
        self.assertEqual(paths.inside(self.root, "."), self.root)

    def test_error_message_translated(self):
        err = PathError("path.dotdot")
        self.assertIn("..", err.message("es"))
        self.assertNotEqual(err.message("es"), err.message("en"))


class KeyTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(paths.check_key("a/" + "b" * 100), "a/" + "b" * 100)

    def test_segment_too_long(self):
        with self.assertRaises(GvoiceError) as cm:
            paths.check_key("a/" + "b" * 101)
        self.assertEqual(cm.exception.code, "key.segment_too_long")

    def test_key_too_long(self):
        key = "/".join(["b" * 50] * 5)  # 254 chars, segments fine
        with self.assertRaises(GvoiceError) as cm:
            paths.check_key(key)
        self.assertEqual(cm.exception.code, "key.too_long")

# Copiado de gimg@0d02f51 (D7); cambia: GVOICE_*, carpetas galivelop-voice, project_data_dir en vez de check_key.
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gvoice import paths
from gvoice.errors import GvoiceError, PathError
from gvoice.schema import load_schema


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
            ("a\rb", "path.control"),
            ("~user/x", "path.tilde"),
            ("//etc", "path.absolute"),
            ("a/b/../../..", "path.dotdot"),
            ("C:\\x", "path.backslash"),
            (b"a", "path.type"),
            (5, "path.type"),
            ("", "path.empty"),
            (None, "path.type"),
        ]
        for rel, code in cases:
            with self.subTest(rel=rel):
                self.assertEqual(self.reason(rel), code)

    def test_dots_inside_names_are_fine(self):
        self.assertEqual(paths.inside(self.root, "a..b/c"), self.root / "a..b" / "c")

    def test_nonexistent_target(self):
        self.assertEqual(paths.inside(self.root, "new/dir/x.png"), self.root / "new/dir/x.png")

    def test_symlink_outside_rejected(self):
        os.symlink(self.outside, self.root / "link")
        self.assertEqual(self.reason("link/x.png"), "path.outside")
        self.assertEqual(self.reason("link"), "path.outside")

    def test_symlink_to_file_outside_rejected(self):
        (self.outside / "f").write_text("x")
        os.symlink(self.outside / "f", self.root / "flink")
        self.assertEqual(self.reason("flink"), "path.outside")

    def test_symlink_inside_ok(self):
        (self.root / "real").mkdir()
        os.symlink(self.root / "real", self.root / "alias")
        self.assertEqual(paths.inside(self.root, "alias/x.png"), self.root / "real" / "x.png")

    def test_root_is_symlink(self):
        link = self.tmp / "rootlink"
        os.symlink(self.root, link)
        self.assertEqual(paths.inside(link, "a/x.png"), self.root / "a" / "x.png")
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


class ProjectDataDirTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": "/data"})
        env.start()
        self.addCleanup(env.stop)

    def test_valid_name(self):
        self.assertEqual(paths.project_data_dir("my-game2"), Path("/data/projects/my-game2"))

    def test_bad_names_with_code(self):
        for name in ("", ".", "..", "a/b", "../x", "A", "-a", "a b", "a\n", "a\x00", None, 3):
            with self.subTest(name=name):
                with self.assertRaises(GvoiceError) as cm:
                    paths.project_data_dir(name)
                self.assertEqual(cm.exception.code, "project.bad_name")

    def test_custom_code(self):
        with self.assertRaises(GvoiceError) as cm:
            paths.project_data_dir("..", "order.bad_project")
        self.assertEqual(cm.exception.code, "order.bad_project")

    def test_pattern_comes_from_common_schema(self):
        # the guard uses the schema's name pattern, not its own copy
        pattern = load_schema("common")["$defs"]["name"]["pattern"]
        self.assertTrue(pattern.startswith("^") and pattern.endswith("$"))
        self.assertEqual(paths._PROJECT_NAME.pattern, pattern)

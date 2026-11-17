# Copiado de gimg@47bd0a9 (D7), adaptado a gvoice.
"""Si la rama toca `gvoice/`, «[Sin publicar]» / «[Unreleased]» de los CHANGELOG tiene alguna entrada (REVIEW.md).

La lógica es pura (`unreleased_problem`, texto + rutas -> motivo o None) y se prueba con textos de ejemplo; la prueba
del repo solo añade la llamada a git. Casos límite: sin git o sin `origin/main` y clon superficial sin merge-base se
saltan con motivo; HEAD en `origin/main` o un diff sin `gvoice/` pasan; una release recién numerada (`releases.py bump`
mueve las entradas a la versión nueva y deja vacío lo sin publicar) pasa si esa versión aún no está en `origin/main` y
ningún archivo de `gvoice/` cambió después del commit del bump (el último que tocó `gvoice/__init__.py`).
`origin/main` está en el CI: `check.yml` hace checkout con `fetch-depth: 0`."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import releases

ROOT = Path(__file__).resolve().parent.parent
FILES = {"es": "CHANGELOG.es.md", "en": "CHANGELOG.md"}
_HEADING = re.compile(r"^## \[([^\]]+)\]")


def has_entries(text, version):
    """Hay alguna línea `- …` en la sección `## [version]`, antes del siguiente `## [`."""
    inside = False
    for line in text.splitlines():
        found = _HEADING.match(line)
        if found:
            if inside:
                return False
            inside = found.group(1) == version
        elif inside and line.startswith("- "):
            return True
    return False


def unreleased_problem(text, base_text, paths, changed_after_bump=False):
    """El motivo por el que el CHANGELOG `text` no vale para los cambios `paths`, o None.

    `base_text` es el CHANGELOG de `origin/main` (None si no se tiene). `changed_after_bump`: algo de `gvoice/`
    cambió después del commit del bump; entonces la excepción de la release recién numerada no vale."""
    if not any(p.startswith("gvoice/") for p in paths):
        return None
    unreleased = next((m.group(1) for m in map(_HEADING.match, text.splitlines()) if m
                       and releases._UNRELEASED.match(m.group(0))), None)
    if unreleased is None:
        return "no tiene la sección «[Sin publicar]» / «[Unreleased]»"
    if has_entries(text, unreleased):
        return None
    newest = next((m.group(1) for m in map(_HEADING.match, text.splitlines()) if m and m.group(1) != unreleased), None)
    if newest and not changed_after_bump and base_text is not None and releases.section(base_text, newest) is None:
        return None  # release recién numerada: sus entradas están en la versión nueva
    return "la sección «[%s]» no tiene ninguna entrada (`- …`) y la rama toca gvoice/" % unreleased


def git(*args, cwd=ROOT):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def changed_after_bump(cwd=ROOT):
    """Si algún archivo de `gvoice/` cambió después del último commit que tocó `gvoice/__init__.py` (el bump)."""
    bump = git("log", "-1", "--format=%H", "--", "gvoice/__init__.py", cwd=cwd).stdout.strip()
    return bool(bump) and git("diff", "--quiet", f"{bump}..HEAD", "--", "gvoice/", cwd=cwd).returncode != 0


class PureLogic(unittest.TestCase):
    FULL = "# C\n\n## [Unreleased]\n\n### Added\n\n- Algo.\n\n## [0.4.0] - 2026-11-05\n\n- Viejo.\n"
    EMPTY = "# C\n\n## [Unreleased]\n\n## [0.4.0] - 2026-11-05\n\n- Viejo.\n"
    BUMPED = "# C\n\n## [Unreleased]\n\n## [0.5.0] - 2026-11-12\n\n- Nuevo.\n\n## [0.4.0] - 2026-11-05\n\n- Viejo.\n"
    GIMG = ["gvoice/ui/app.js"]

    def test_entry_passes(self):
        self.assertIsNone(unreleased_problem(self.FULL, self.FULL, self.GIMG))

    def test_empty_section_fails_with_its_reason(self):
        problem = unreleased_problem(self.EMPTY, self.EMPTY, self.GIMG)
        self.assertIn("no tiene ninguna entrada", problem)
        self.assertIn("[Unreleased]", problem)

    def test_entries_of_the_next_version_do_not_count(self):
        self.assertIn("ninguna entrada", unreleased_problem(self.EMPTY, self.FULL, self.GIMG))

    def test_without_gvoice_changes_passes(self):
        self.assertIsNone(unreleased_problem(self.EMPTY, self.EMPTY, ["docs/x.md", "tests/test_x.py"]))
        self.assertIsNone(unreleased_problem(self.EMPTY, self.EMPTY, []))

    def test_fresh_release_passes_only_if_version_is_new_in_base(self):
        self.assertIsNone(unreleased_problem(self.BUMPED, self.EMPTY, self.GIMG))
        self.assertIn("ninguna entrada", unreleased_problem(self.BUMPED, self.BUMPED, self.GIMG))

    def test_fresh_release_does_not_excuse_changes_made_after_the_bump(self):
        self.assertIsNone(unreleased_problem(self.BUMPED, self.EMPTY, self.GIMG, False))
        self.assertIn("ninguna entrada", unreleased_problem(self.BUMPED, self.EMPTY, self.GIMG, True))

    def test_missing_section_fails(self):
        self.assertIn("no tiene la sección", unreleased_problem("# C\n\n## [0.4.0]\n\n- x\n", None, self.GIMG))

    def test_spanish_heading(self):
        self.assertIn("[Sin publicar]", unreleased_problem(self.EMPTY.replace("Unreleased", "Sin publicar"), None, self.GIMG))


class ChangedAfterBump(unittest.TestCase):
    def test_only_gvoice_changes_after_the_commit_that_touched_init_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def commit(name, text, message):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                git("add", "-A", cwd=root)
                done = git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message, cwd=root)
                self.assertEqual(done.returncode, 0, done.stderr)
            git("init", "-q", cwd=root)
            commit("gvoice/__init__.py", '__version__ = "0.1.0"\n', "bump")
            self.assertFalse(changed_after_bump(root))
            commit("docs/x.md", "x", "docs")
            self.assertFalse(changed_after_bump(root))
            commit("gvoice/other.py", "x = 1\n", "code after the bump")
            self.assertTrue(changed_after_bump(root))
            commit("gvoice/__init__.py", '__version__ = "0.2.0"\n', "next bump")
            self.assertFalse(changed_after_bump(root))


class RepoChangelogs(unittest.TestCase):
    def test_branch_touching_gvoice_has_unreleased_entries(self):
        try:
            if git("rev-parse", "--git-dir").returncode != 0:
                self.skipTest("no hay git")
            if git("rev-parse", "--verify", "--quiet", "origin/main").returncode != 0:
                self.skipTest("no hay origin/main (git fetch origin main)")
            base = git("merge-base", "origin/main", "HEAD")
        except OSError:
            self.skipTest("no hay git")
        if base.returncode != 0 or not base.stdout.strip():
            self.skipTest("clon superficial: sin merge-base con origin/main")
        paths = git("diff", "--name-only", base.stdout.strip(), "HEAD", "--", "gvoice/").stdout.split()
        for name in FILES.values():
            shown = git("show", "origin/main:" + name)
            problem = unreleased_problem((ROOT / name).read_text(encoding="utf-8"),
                                         shown.stdout if shown.returncode == 0 else "", paths, changed_after_bump())  # aún sin CHANGELOG en main: todo es nuevo
            self.assertIsNone(problem, "%s: %s" % (name, problem))


if __name__ == "__main__":
    unittest.main()

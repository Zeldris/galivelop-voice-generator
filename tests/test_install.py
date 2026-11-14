"""instalar.sh (D17): the commands it would run (--dry-run) per environment, and a real run with fake tools."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from gvoice import models

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "instalar.sh"
CATALOG = models.load("qwentts")
SDK = "org.freedesktop.Sdk//25.08"


def install(args, env_kind=None, extra=None, data=None, path=None):
    env = dict(os.environ)
    for key in ("GVOICE_INSTALL_ENV", "GVOICE_INSTALL_SDK", "GVOICE_INSTALL_SPIRV", "FLATPAK_ID", "GVOICE_MODELS_HOME"):
        env.pop(key, None)
    env["GVOICE_DATA_HOME"] = str(data)
    if env_kind:
        env["GVOICE_INSTALL_ENV"] = env_kind
    if path:
        env["PATH"] = path
    env.update(extra or {})
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, cwd=ROOT)


class DryRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name) / "data"
        self.engine = self.data / "engine"

    def dry(self, *args, env_kind="native", extra=None):
        result = install(["--dry-run", *args], env_kind, extra, self.data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.data.exists(), "--dry-run must not touch the disk")
        return [line[len("DRY-RUN: "):] for line in result.stdout.splitlines() if line.startswith("DRY-RUN: ")]

    def test_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_steamos_builds_in_the_sdk(self):
        lines = self.dry(env_kind="steamos", extra={"GVOICE_INSTALL_SDK": "missing"})
        self.assertEqual(lines[0], f"flatpak --user install -y --noninteractive flathub {SDK}")
        build = [x for x in lines if "cmake" in x and "--command=cmake" in x]
        self.assertTrue(build)
        for line in lines:
            if "--command=" in line:
                self.assertTrue(line.startswith(f"flatpak run --user --filesystem={self.engine} --command="), line)
                self.assertIn(f" {SDK} ", line)
        git = [x for x in lines if "--command=git" in x]
        self.assertTrue(any(f"checkout {CATALOG['commit']}" in x for x in git))
        self.assertTrue(any(f"clone {CATALOG['repo']} {self.engine}/src" in x for x in git))
        self.assertTrue(any("submodule update --init --recursive" in x for x in git))

    def test_steamos_skips_sdk_install_when_present(self):
        lines = self.dry(env_kind="steamos", extra={"GVOICE_INSTALL_SDK": "present"})
        self.assertFalse(any("install" in x and "flathub" in x for x in lines))

    def test_steamos_vulkan_uses_local_spirv_headers(self):
        lines = self.dry(env_kind="steamos")
        prefix = self.engine / "deps" / "prefix"
        vulkan = [x for x in lines if "-DGGML_VULKAN=ON" in x]
        self.assertEqual(len(vulkan), 1)
        self.assertIn(f"-DCMAKE_PREFIX_PATH={prefix}", vulkan[0])
        self.assertIn(f"-DCMAKE_CXX_FLAGS=-I{prefix}/include", vulkan[0])
        install_line = [x for x in lines if f"-DCMAKE_INSTALL_PREFIX={prefix}" in x]
        self.assertEqual(len(install_line), 1)
        self.assertLess(lines.index(install_line[0]), lines.index(vulkan[0]))
        self.assertTrue(any("KhronosGroup/SPIRV-Headers" in x for x in lines))

    def test_cpu_has_no_blas_and_no_vulkan(self):
        lines = self.dry()
        cpu = [x for x in lines if f"-B {self.engine}/bin-cpu" in x]
        self.assertEqual(len(cpu), 1)
        self.assertIn("-DGGML_BLAS=OFF", cpu[0])
        self.assertNotIn("GGML_VULKAN", cpu[0])
        self.assertNotIn("GGML_BLAS=ON", "\n".join(lines))

    def test_rpath_origin_reaches_cmake_literally(self):
        for kind in ("native", "steamos", "flatpak"):
            lines = self.dry(env_kind=kind)
            configure = [x for x in lines if " -S " in x and "-DGGML_BLAS=OFF" in x]
            self.assertEqual(len(configure), 2, kind)
            for line in configure:
                # printf %q shows the dollar escaped: a shell reading this line passes a literal $ORIGIN
                self.assertIn("-DCMAKE_BUILD_RPATH=\\$ORIGIN", line)
                self.assertIn("-DCMAKE_INSTALL_RPATH=\\$ORIGIN", line)

    def test_native_runs_without_flatpak(self):
        lines = self.dry(env_kind="native")
        self.assertFalse(any("flatpak" in x for x in lines))
        self.assertTrue(any(x.startswith(f"git clone {CATALOG['repo']} ") for x in lines))
        self.assertTrue(any(x.startswith(f"git -C {self.engine}/src checkout {CATALOG['commit']}") for x in lines))

    def test_native_uses_system_spirv_headers_when_forced(self):
        lines = self.dry(env_kind="native", extra={"GVOICE_INSTALL_SPIRV": "system"})
        vulkan = [x for x in lines if "-DGGML_VULKAN=ON" in x]
        self.assertEqual(len(vulkan), 1)
        self.assertNotIn("CMAKE_PREFIX_PATH", vulkan[0])
        self.assertFalse(any("SPIRV-Headers" in x for x in lines))

    def test_inside_flatpak_builds_directly_and_probes_on_the_host(self):
        lines = self.dry(env_kind="flatpak")
        self.assertFalse(any(x.startswith("flatpak run") or "install" in x and "flathub" in x for x in lines))
        probes = [x for x in lines if "qwen-tts --help" in x]
        self.assertEqual(probes, [f"flatpak-spawn --host {self.engine}/bin-cpu/qwen-tts --help",
                                  f"flatpak-spawn --host {self.engine}/bin-vulkan/qwen-tts --help"])

    def test_flatpak_detected_from_flatpak_id(self):
        result = install(["--dry-run"], None, {"FLATPAK_ID": "com.visualstudio.code"}, self.data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("flatpak-spawn --host", result.stdout)

    def test_native_and_steamos_probe_directly(self):
        for kind in ("native", "steamos"):
            lines = self.dry(env_kind=kind)
            self.assertIn(f"{self.engine}/bin-cpu/qwen-tts --help", lines)
            self.assertFalse(any("flatpak-spawn" in x for x in lines))

    def test_cpu_only_skips_vulkan(self):
        lines = self.dry("--cpu-only", env_kind="steamos")
        joined = "\n".join(lines)
        self.assertNotIn("GGML_VULKAN", joined)
        self.assertNotIn("SPIRV", joined)
        self.assertNotIn("bin-vulkan", joined)
        self.assertIn("bin-cpu", joined)

    def test_models_are_fetched_and_verified_unless_skipped(self):
        lines = self.dry()
        fetch = [i for i, x in enumerate(lines) if x.endswith("-m gvoice models fetch")]
        verify = [i for i, x in enumerate(lines) if x.endswith("-m gvoice models verify")]
        self.assertEqual((len(fetch), len(verify)), (1, 1))
        self.assertLess(fetch[0], verify[0])
        skipped = "\n".join(self.dry("--skip-models"))
        self.assertNotIn("models fetch", skipped)
        self.assertNotIn("models verify", skipped)

    def test_final_message_says_how_to_activate_the_engine(self):
        result = install(["--dry-run"], "native", None, self.data)
        self.assertIn("GVOICE_ENGINE=qwentts", result.stdout)
        self.assertIn('"engine": "qwentts"', result.stdout)

    def test_unknown_option_fails_with_its_message(self):
        result = install(["--nope"], "native", None, self.data)
        self.assertEqual(result.returncode, 2)
        self.assertIn("opcion desconocida: --nope", result.stderr)

    def test_unknown_environment_fails_with_its_message(self):
        result = install(["--dry-run"], "windows", None, self.data)
        self.assertEqual(result.returncode, 1)
        self.assertIn("GVOICE_INSTALL_ENV=windows no vale", result.stderr)

    def test_no_compiler_and_no_flatpak_fails_clearly(self):
        bindir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(bindir, ignore_errors=True))
        for tool in ("bash", "dirname", "python3"):
            real = subprocess.run(["bash", "-c", f"command -v {tool}"], capture_output=True, text=True).stdout.strip()
            (bindir / tool).symlink_to(real)
        result = install(["--dry-run"], None, None, self.data, path=str(bindir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no hay compilador", result.stderr)


FAKE_CMAKE = r"""#!/bin/sh
echo "$@" >> "$FAKE_LOG/cmake.log"
for a in "$@"; do printf '%s\n' "$a" >> "$FAKE_LOG/cmake.args"; done
if [ "$1" = "--build" ]; then
  mkdir -p "$2"
  for n in qwen-tts qwen-codec tts-server; do
    printf '#!/bin/sh\n%s\n' "${FAKE_TTS_BODY:-echo usage: qwen-tts}" > "$2/$n"; chmod +x "$2/$n"
  done
  : > "$2/libggml.so"
fi
exit 0
"""
FAKE_GIT = r"""#!/bin/sh
echo "git $@" >> "$FAKE_LOG/git.log"
if [ "$1" = "clone" ]; then mkdir -p "$3/.git"; fi
exit 0
"""


class FakeToolsTests(unittest.TestCase):
    """A real run (no --dry-run) with fake git/cmake/g++ on the PATH: what reaches the tools, and idempotence."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.data, self.log, self.bin = base / "data", base / "log", base / "bin"
        self.log.mkdir()
        self.bin.mkdir()
        for name, body in (("cmake", FAKE_CMAKE), ("git", FAKE_GIT), ("g++", "#!/bin/sh\nexit 0\n")):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)

    def run_install(self, *args, body=None):
        extra = {"FAKE_LOG": str(self.log), "GVOICE_INSTALL_SPIRV": "system"}
        if body:
            extra["FAKE_TTS_BODY"] = body
        return install(["--skip-models", *args], "native", extra, self.data, path=f"{self.bin}:{os.environ['PATH']}")

    def test_real_run_installs_binaries_and_passes_origin_literally(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for folder in ("bin-cpu", "bin-vulkan"):
            for name in ("qwen-tts", "qwen-codec", "tts-server", "libggml.so"):
                self.assertTrue((self.data / "engine" / folder / name).exists(), f"{folder}/{name}")
        args = (self.log / "cmake.args").read_text().splitlines()
        self.assertIn("-DCMAKE_BUILD_RPATH=$ORIGIN", args)
        self.assertIn("-DCMAKE_INSTALL_RPATH=$ORIGIN", args)
        self.assertIn("GVOICE_ENGINE=qwentts", result.stdout)
        self.assertIn(f"checkout {CATALOG['commit']}", (self.log / "git.log").read_text())

    def test_second_run_does_not_clone_again(self):
        self.assertEqual(self.run_install("--cpu-only").returncode, 0)
        self.assertEqual(self.run_install("--cpu-only").returncode, 0)
        git = (self.log / "git.log").read_text().splitlines()
        self.assertEqual(len([x for x in git if x.startswith("git clone")]), 1)
        self.assertEqual(len([x for x in git if " fetch " in x]), 1)

    def test_binary_that_does_not_start_fails_with_a_clear_message(self):
        result = self.run_install("--cpu-only", body="echo 'qwen-tts: error while loading shared libraries: libggml.so' >&2; exit 127")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no arranca", result.stderr)
        self.assertIn("error while loading shared libraries", result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Tests de instalar.sh (D17): solo sintaxis, ayuda, --plan y opciones; nunca compilan ni descargan."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "instalar.sh"
BASH = shutil.which("bash")


def _stub_dir(parent: Path, name: str, programas) -> Path:
    d = parent / name
    d.mkdir()
    for p in programas:
        f = d / p
        f.write_text("#!/bin/sh\nexit 0\n")
        f.chmod(0o755)
    return d


class InstalarTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.data = self.tmp / "datos"

    def run_script(self, *args, path_dirs=(), extra_env=None):
        """Corre instalar.sh con un PATH que solo tiene los stubs (y un directorio con bash/coreutils mínimos)."""
        # PATH controlado: enlaces a lo imprescindible, sin cmake/c++/flatpak salvo los stubs.
        base = self.tmp / "base"
        if not base.exists():
            base.mkdir()
            for prog in ("bash", "cat", "dirname", "date", "env", "grep", "cut", "getconf", "sh"):
                real = shutil.which(prog)
                if real:
                    (base / prog).symlink_to(real)
        env = {
            "PATH": os.pathsep.join([str(p) for p in path_dirs] + [str(base)]),
            "HOME": str(self.tmp / "home"),
            "GVOICE_DATA_HOME": str(self.data),
            "GVOICE_FLATPAK_INFO": str(self.tmp / "no-existe"),
        }
        env.update(extra_env or {})
        return subprocess.run([BASH, str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def test_sintaxis(self):
        r = subprocess.run([BASH, "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ayuda_menciona_cada_opcion(self):
        for flag in ("--help", "--ayuda"):
            r = self.run_script(flag)
            self.assertEqual(r.returncode, 0, r.stderr)
            for opcion in ("--ayuda", "--help", "--solo-cpu", "--sin-modelos", "--plan"):
                self.assertIn(opcion, r.stdout)

    def test_opcion_desconocida_falla_con_su_mensaje(self):
        r = self.run_script("--nada")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("opción desconocida: --nada", r.stderr)

    def test_plan_directo_con_compilador(self):
        cc = _stub_dir(self.tmp, "cc", ["cmake", "c++"])
        r = self.run_script("--plan", path_dirs=[cc])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sitio de compilación: directo", r.stdout)
        self.assertIn(str(self.data), r.stdout)
        self.assertIn("5916bf7c79dbb4e66fc059cdc507a79a23a28bb4", r.stdout)
        self.assertIn("Vulkan", r.stdout)
        self.assertFalse(self.data.exists(), "--plan no debe crear nada")

    def test_plan_flatpak_sin_compilador(self):
        fp = _stub_dir(self.tmp, "fp", ["flatpak"])
        r = self.run_script("--plan", path_dirs=[fp])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sitio de compilación: flatpak-sdk", r.stdout)
        self.assertIn("org.freedesktop.Sdk//25.08", r.stdout)
        self.assertFalse(self.data.exists())

    def test_plan_sin_compilador_ni_flatpak(self):
        r = self.run_script("--plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sitio de compilación: ninguno", r.stdout)
        self.assertIn("se detendría", r.stdout)
        self.assertFalse(self.data.exists())

    def test_plan_en_sandbox_usa_el_compilador_del_sdk(self):
        cc = _stub_dir(self.tmp, "cc", ["cmake", "c++", "flatpak"])
        info = self.tmp / "flatpak-info"
        info.write_text("[Application]\n")
        r = self.run_script("--plan", path_dirs=[cc], extra_env={"GVOICE_FLATPAK_INFO": str(info)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sitio de compilación: sandbox-sdk", r.stdout)
        self.assertIn("flatpak-spawn --host", r.stdout)

    def test_plan_sin_compilador_en_sandbox_no_anida_flatpak(self):
        fp = _stub_dir(self.tmp, "fp", ["flatpak"])
        info = self.tmp / "flatpak-info"
        info.write_text("[Application]\n")
        r = self.run_script("--plan", path_dirs=[fp], extra_env={"GVOICE_FLATPAK_INFO": str(info)})
        self.assertIn("sitio de compilación: ninguno", r.stdout)

    def test_plan_solo_cpu_y_sin_modelos_omiten_pasos(self):
        cc = _stub_dir(self.tmp, "cc", ["cmake", "c++"])
        r = self.run_script("--plan", "--solo-cpu", "--sin-modelos", path_dirs=[cc])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("omitido: --solo-cpu", r.stdout)
        self.assertIn("omitido: --sin-modelos", r.stdout)
        self.assertNotIn("qwen-talker-0.6b-base-Q8_0.gguf", r.stdout)

    def test_plan_respeta_xdg_data_home(self):
        cc = _stub_dir(self.tmp, "cc", ["cmake", "c++"])
        xdg = self.tmp / "xdg"
        r = self.run_script("--plan", path_dirs=[cc], extra_env={"GVOICE_DATA_HOME": "", "XDG_DATA_HOME": str(xdg)})
        self.assertIn(f"{xdg}/galivelop-voice", r.stdout)

    def test_sin_compilador_ni_flatpak_se_detiene_con_mensaje(self):
        r = self.run_script()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no hay compilador de C++ con cmake ni flatpak", r.stderr)
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()

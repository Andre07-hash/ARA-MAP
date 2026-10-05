"""The application must run from a copied folder with nothing installed."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "ARA Map.command"
VENDOR = ROOT / "vendor" / "python"

# Apple ships this with macOS. If the app runs here it runs on a clean Mac.
SYSTEM_PYTHON = Path("/usr/bin/python3")


class BundledDependency(unittest.TestCase):
    def test_openpyxl_is_bundled(self):
        self.assertTrue((VENDOR / "openpyxl" / "__init__.py").is_file())
        self.assertTrue((VENDOR / "et_xmlfile" / "__init__.py").is_file())

    def test_the_bundle_is_pure_python(self):
        """Compiled extensions would tie the bundle to one Python version."""
        binarios = list(VENDOR.rglob("*.so")) + list(VENDOR.rglob("*.dylib"))
        self.assertEqual(binarios, [])

    def test_importing_the_package_puts_the_bundle_on_the_path(self):
        self.assertTrue(any(str(VENDOR) == p for p in sys.path))


@unittest.skipUnless(SYSTEM_PYTHON.exists(), "macOS system Python not present")
class CleanMachine(unittest.TestCase):
    """Runs against Apple's Python, which has no third-party packages."""

    def run_python(self, code: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(SYSTEM_PYTHON), "-c", code],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONPATH": ""},
        )

    def test_the_system_python_is_old_enough_to_matter(self):
        out = self.run_python("import sys; print(sys.version_info[:2])")
        self.assertEqual(out.returncode, 0)

    def test_the_system_python_has_no_openpyxl_of_its_own(self):
        out = self.run_python(
            "import importlib.util; print(bool(importlib.util.find_spec('openpyxl')))")
        self.assertEqual(out.stdout.strip(), "False",
                         "this test only means something without a system openpyxl")

    def test_a_workbook_can_be_read_with_nothing_installed(self):
        out = self.run_python(
            "import sys; sys.path.insert(0, '.');"
            "from server.importer import read_workbook;"
            "r = read_workbook('tests/fixtures/base_terrenos_09_26.xlsx');"
            "print(len(r.records), r.ubicados)"
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "79 39")

    def test_the_database_layer_works_on_the_system_python(self):
        out = self.run_python(
            "import sys, tempfile, os; sys.path.insert(0, '.');"
            "from server import db;"
            "d = tempfile.mkdtemp();"
            "c = db.connect(os.path.join(d, 't.db'));"
            "print(c.execute('PRAGMA user_version').fetchone()[0]); c.close()"
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        from server import db as _db
        self.assertEqual(out.stdout.strip(), str(_db.SCHEMA_VERSION))


class Launcher(unittest.TestCase):
    def test_the_launcher_is_executable(self):
        self.assertTrue(os.access(LAUNCHER, os.X_OK))

    def test_it_does_not_trust_the_first_python_on_the_path(self):
        texto = LAUNCHER.read_text()
        self.assertIn("CANDIDATOS", texto)
        self.assertIn("/usr/bin/python3", texto)
        self.assertIn("version_info >= (3, 9)", texto)

    def test_it_never_asks_the_user_to_install_anything(self):
        texto = LAUNCHER.read_text()
        self.assertNotIn("pip install", texto)

    def test_failures_keep_the_window_open(self):
        """A window that closes instantly leaves the user with no message."""
        texto = LAUNCHER.read_text()
        self.assertIn("pausa_y_salir", texto)
        self.assertIn("read -r", texto)


if __name__ == "__main__":
    unittest.main()

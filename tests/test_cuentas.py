"""scripts/cuentas.py: explicit-target account provisioning with hidden prompts."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import auth, db

SCRIPT = Path(__file__).parents[1] / "scripts" / "cuentas.py"
spec = importlib.util.spec_from_file_location("cuentas", SCRIPT)
cuentas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cuentas)
ESQUEMA = Path(__file__).parents[1] / "scripts" / "esquema.py"
spec = importlib.util.spec_from_file_location("esquema", ESQUEMA)
esquema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(esquema)

CLAVE = "una-clave-bastante-larga"


class Provisioning(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "cuentas.db"
        self.env = patch.dict(os.environ, {"ARA_MAP_DB": str(Path(self._dir.name) / "no-usar.db")})
        self.env.start()
        os.environ.pop("ARA_MAP_DATABASE_URL", None)

    def tearDown(self):
        self.env.stop()
        self._dir.cleanup()

    def run_script(self, *argv, answers=(CLAVE, CLAVE)):
        respuestas = iter(answers)
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            cuentas.main(list(argv), ask=lambda _prompt: next(respuestas))
        return salida.getvalue()

    def login(self, usuario, clave=CLAVE):
        with db.session(self.path) as conn:
            return auth.login(conn, usuario, clave)[0]

    def test_refuses_to_run_without_an_explicit_target(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cuentas.main(["crear", "ana", "Ana"], ask=lambda _p: CLAVE)
        with self.assertRaises(SystemExit) as caught:
            cuentas.main(["--url-env", "ARA_VARIABLE_QUE_NO_EXISTE", "listar"])
        self.assertIn("no está definida", str(caught.exception))
        self.assertFalse(Path(os.environ["ARA_MAP_DB"]).exists())  # no default database touched
        self.assertNotIn("load_dotenv", SCRIPT.read_text())

    def test_passwords_are_never_arguments(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cuentas.main(["--sqlite", str(self.path), "crear", "ana", "Ana", "--password", "x"])

    def test_create_reset_deactivate_and_list(self):
        salida = self.run_script("--sqlite", str(self.path), "crear", "Ana", "Ana López")
        self.assertIn("ana", salida)
        self.assertNotIn(CLAVE, salida)
        token = self.login("ana")
        self.assertTrue(token)

        self.run_script("--sqlite", str(self.path), "restablecer", "ana",
                        answers=("otra-clave-muy-larga",) * 2)
        with db.session(self.path) as conn:
            self.assertIsNone(auth.user_for_token(conn, token))  # old session ended
        self.assertIsNone(self.login("ana"))
        self.assertTrue(self.login("ana", "otra-clave-muy-larga"))

        self.run_script("--sqlite", str(self.path), "desactivar", "ana")
        self.assertIsNone(self.login("ana", "otra-clave-muy-larga"))
        self.assertIn("desactivada", self.run_script("--sqlite", str(self.path), "listar"))
        self.run_script("--sqlite", str(self.path), "reactivar", "ana")
        self.assertTrue(self.login("ana", "otra-clave-muy-larga"))

        with db.session(self.path) as conn:
            columnas = {r[1] for r in conn.execute("PRAGMA table_info(team_user)")}
            guardado = conn.execute("SELECT password_hash FROM team_user").fetchone()[0]
        self.assertNotIn("role", " ".join(columnas))
        self.assertTrue(guardado.startswith("pbkdf2_sha256$600000$"))

    def test_password_from_stdin_for_automation(self):
        with patch("sys.stdin", io.StringIO(CLAVE + "\n")), contextlib.redirect_stdout(io.StringIO()):
            cuentas.main(["--sqlite", str(self.path), "--password-stdin", "crear", "ana", "Ana"],
                         ask=lambda _p: self.fail("must not prompt"))
        self.assertTrue(self.login("ana"))

    def test_schema_command_needs_a_named_target(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            esquema.main([])
        with self.assertRaises(SystemExit) as caught:
            esquema.main(["--url-env", "ARA_VARIABLE_QUE_NO_EXISTE"])
        self.assertIn("no está definida", str(caught.exception))
        self.assertNotIn("load_dotenv", ESQUEMA.read_text())

    def test_bad_input_changes_nothing(self):
        for argv, answers, mensaje in (
            (("crear", "ana", "Ana"), (CLAVE, "distinta-clave-larga"), "no coinciden"),
            (("crear", "ana", "Ana"), ("corta", "corta"), "al menos"),
            (("crear", "a", "Ana"), (CLAVE, CLAVE), "3 a 64"),
            (("restablecer", "nadie"), (CLAVE, CLAVE), "No existe"),
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as caught:
                self.run_script("--sqlite", str(self.path), *argv, answers=answers)
            self.assertIn(mensaje, str(caught.exception))
        self.run_script("--sqlite", str(self.path), "crear", "ana", "Ana")
        with self.assertRaises(SystemExit) as caught:
            self.run_script("--sqlite", str(self.path), "crear", "ANA", "Otra")
        self.assertIn("Ya existe", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

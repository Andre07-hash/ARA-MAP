"""Shared helpers: an isolated database per test case."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "base_terrenos_09_26.xlsx"
TEST_PASSWORD = "contraseña-de-prueba-larga"


def create_user(conn, login="ana", nombre="Ana Prueba", rol="admin"):
    """A fictional team account. Few PBKDF2 rounds: only tests use these.

    An administrator unless told otherwise, which is the opposite of the
    application's own default (operator). The suites written before roles
    existed exercise the legacy workspace and the unscoped inventory, which
    are administrator routes now; what an operator may and may not do is
    tested with explicit rol="operador" accounts (tests/test_roles_y_bases.py).
    """
    from server import auth
    return auth.create_user(conn, login, nombre, TEST_PASSWORD, iterations=1000, rol=rol)


def session_cookie(conn, login="ana"):
    """A Cookie header value for a fresh session of an existing account."""
    from server import auth
    token, _, _ = auth.login(conn, login, TEST_PASSWORD)
    assert token, "login failed"
    return f"{auth.COOKIE}={token}"


class TempDatabase(unittest.TestCase):
    """Points ARA_MAP_DB at a throwaway file for the duration of one test."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._dir.name) / "prueba.db"
        self._previous = os.environ.get("ARA_MAP_DB")
        os.environ["ARA_MAP_DB"] = str(self.db_path)

        from server import db
        self.conn = db.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if self._previous is None:
            os.environ.pop("ARA_MAP_DB", None)
        else:
            os.environ["ARA_MAP_DB"] = self._previous
        self._dir.cleanup()

    def load_fixture(self, nombre="Base de prueba"):
        """Import the real workbook into the temp database."""
        from server.importer import read_workbook
        from server.repo import bases, terrenos
        from server.validation import validate_all

        result = read_workbook(FIXTURE)
        findings = validate_all(result.records)
        base_id = bases.create(self.conn, nombre, "prueba.xlsx", result.hoja)
        terrenos.insert(self.conn, base_id, result.records, findings)
        return base_id, result

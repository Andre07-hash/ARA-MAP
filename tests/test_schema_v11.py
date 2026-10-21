"""Schema 10 -> 11: each account stores the header logo it sees (team_user.marca).

The same checks run on SQLite and, when ARA_MAP_TEST_DATABASE_URL is set, on a
disposable Postgres schema. Each backend takes a schema-10 database with
fictional accounts, upgrades it twice and checks that every account keeps the
logo it saw before: Dewa for the «tyrag» login, ARA for everyone else.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import auth, db, postgres
from tests.test_schema_v9 import AHORA, URL

LOGINS = ("tyrag", "ana", "beto")


def poblar_v10(conn):
    """Fictional schema-10 accounts, written as schema-10 SQL (no marca)."""
    for login, rol in zip(LOGINS, ("admin", "admin", "operador")):
        conn.execute(
            "INSERT INTO team_user (id, login, display_name, password_hash, active,"
            " credential_revision, rol, created_at, updated_at) VALUES (?, ?, ?, 'x', 1, 1, ?, ?, ?)",
            (str(uuid.uuid4()), login, login.capitalize() + " Prueba", rol, AHORA, AHORA))


def cuentas(conn):
    return {r["login"]: (r["rol"], r["marca"]) for r in
            conn.execute("SELECT login, rol, marca FROM team_user").fetchall()}


class V11Checks:
    """The backend provides ``despues`` (accounts after two upgrades),
    ``version_actual()`` and ``confirmar(fn)`` (run fn(conn) and commit)."""

    def test_existing_accounts_keep_their_logo_and_their_role(self):
        self.assertEqual(self.version_actual(), db.SCHEMA_VERSION)
        self.assertEqual(self.despues, {"tyrag": ("admin", "dewa"), "ana": ("admin", "ara"),
                                        "beto": ("operador", "ara")})

    def test_the_column_rejects_an_unknown_logo(self):
        with self.assertRaises(self.integridad):
            self.confirmar(lambda conn: conn.execute(
                "UPDATE team_user SET marca = 'otra' WHERE login = 'ana'"))

    def test_a_later_upgrade_never_overwrites_a_stored_choice(self):
        self.confirmar(lambda conn: conn.execute(
            "UPDATE team_user SET marca = 'ara' WHERE login = 'tyrag'"))
        try:
            self.migrar()
            self.assertEqual(self.confirmar(cuentas)["tyrag"], ("admin", "ara"))
        finally:
            self.confirmar(lambda conn: conn.execute(
                "UPDATE team_user SET marca = 'dewa' WHERE login = 'tyrag'"))

    def test_a_new_account_gets_the_logo_it_is_given(self):
        def crear(conn):
            auth.create_user(conn, "nueva", "Nueva Prueba", "x", iterations=1000)
            auth.create_user(conn, "otra", "Otra Prueba", "x", iterations=1000, marca="dewa")
            with self.assertRaises(auth.AccountError):
                auth.create_user(conn, "mala", "Mala Prueba", "x", iterations=1000, marca="Dewa")
            return cuentas(conn)
        try:
            creadas = self.confirmar(crear)
            self.assertEqual((creadas["nueva"], creadas["otra"]),
                             (("operador", "ara"), ("operador", "dewa")))
            self.assertNotIn("mala", creadas)
        finally:
            def borrar(conn):
                ids = "SELECT id FROM team_user WHERE login IN ('nueva', 'otra')"
                conn.execute(f"DELETE FROM team_user_event WHERE user_id IN ({ids})")
                conn.execute(f"DELETE FROM team_user WHERE id IN ({ids})")
            self.confirmar(borrar)


class SchemaV11Sqlite(V11Checks, unittest.TestCase):
    integridad = sqlite3.IntegrityError

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "v10.db"
        with db.session(cls.path) as conn:  # a current database, taken back to schema 10
            conn.execute("ALTER TABLE team_user DROP COLUMN marca")
            conn.execute("PRAGMA user_version = 10")
            poblar_v10(conn)
        for _ in range(2):  # the second run must change nothing
            with db.session(cls.path) as conn:
                cls.despues = cuentas(conn)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def migrar(self):
        with db.session(self.path):
            pass

    def confirmar(self, fn):
        conn = db.connect(self.path)
        try:
            conn.execute("BEGIN")
            try:
                resultado = fn(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            return resultado
        finally:
            conn.close()

    def version_actual(self):
        return self.confirmar(lambda conn: conn.execute("PRAGMA user_version").fetchone()[0])

    def test_the_upgrade_backed_up_the_schema_10_file(self):
        respaldos = list(db.backup_dir(self.path).glob("*.db"))
        self.assertEqual(len(respaldos), 1)
        copia = sqlite3.connect(respaldos[0])
        try:
            self.assertEqual(copia.execute("PRAGMA user_version").fetchone()[0], 10)
            columnas = {r[1] for r in copia.execute("PRAGMA table_info(team_user)")}
        finally:
            copia.close()
        self.assertNotIn("marca", columnas)


@unittest.skipUnless(URL, "ARA_MAP_TEST_DATABASE_URL no está definida")
class SchemaV11Postgres(V11Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.integridad = psycopg.IntegrityError
        cls.schema = "test_ara_v11_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            # A fresh workspace through the normal path, taken back to schema 10.
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
            conn.raw.execute(
                "ALTER TABLE team_user DROP COLUMN marca;"
                "UPDATE workspace_metadata SET value = '10' WHERE key = 'schema_version';",
                prepare=False)
        with postgres.session() as conn:
            assert postgres.schema_version(conn) == 10
            poblar_v10(conn)
        for _ in range(2):  # the second run must change nothing
            cls.migrar()
            with postgres.session() as conn:
                cls.despues = cuentas(conn)

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    @staticmethod
    def migrar():
        with postgres.session() as conn:
            postgres.migrate(conn)

    def confirmar(self, fn):
        with postgres.session() as conn:
            return fn(conn)

    def version_actual(self):
        return self.confirmar(postgres.schema_version)


if __name__ == "__main__":
    unittest.main()

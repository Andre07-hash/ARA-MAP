"""Folder schema: SQLite upgrades, fresh installs, generated Postgres DDL, and
who may change folders. Temporary files and in-process servers only."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import app as app_module
from server import db, postgres
from tests.support import TempDatabase, create_user, session_cookie
from tests.test_migration import build_v1

# The schema as version 4 shipped it: today's, minus folders.
SCHEMA_V4 = re.sub(r"--[^\n]*", "", db.SCHEMA)
SCHEMA_V4 = re.sub(r"CREATE TABLE IF NOT EXISTS carpeta \(.*?\);", "", SCHEMA_V4, flags=re.S)
SCHEMA_V4 = re.sub(r",\s*\n\s*carpeta_id[^\n]*", "", SCHEMA_V4)


def build_v4(path: Path) -> None:
    assert "carpeta" not in SCHEMA_V4
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V4)
    conn.executescript("""
        INSERT INTO base (id, nombre, importado_en) VALUES (1, 'Agosto', 't1'), (2, 'Borrada', 't1');
        INSERT INTO terreno (id, base_id, orden, terreno, lat, lon, clave_dedupe)
          VALUES (1, 1, 1, 'El Mirador', 20.7, -103.4, 'el mirador');
        INSERT INTO mapa (id, nombre, tipo, creado_en, actualizado_en, config_json, nombre_sigue_base)
          VALUES (1, 'Agosto', 'simple', 't2', 't3', '{"basemap": "satelite"}', 1),
                 (2, 'Huérfano', 'simple', 't2', 't4', '{}', 0);
        INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre, color)
          VALUES (1, 0, 1, 'Agosto', '#2a78d6'), (2, 0, NULL, 'Borrada', '#eb6834');
        INSERT INTO mapa_terreno (mapa_id, capa_orden, terreno_id, orden, terreno, lat, clave_dedupe)
          VALUES (1, 0, 1, 1, 'El Mirador', 20.7, 'el mirador'),
                 (2, 0, NULL, 1, 'Congelado', 21.0, 'congelado');
        PRAGMA user_version = 4;
    """)
    conn.commit()
    conn.close()


def dump(conn, table):
    columns = [c for c in (r[1] for r in conn.execute(f"PRAGMA table_info({table})"))
               if c != "carpeta_id"]
    return [tuple(r) for r in conn.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid")]


class SqliteUpgrade(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "v4.db"

    def tearDown(self):
        self._dir.cleanup()

    def test_v4_upgrade_keeps_everything_and_starts_unfiled(self):
        build_v4(self.path)
        raw = sqlite3.connect(self.path)
        antes = {t: dump(raw, t) for t in ("base", "terreno", "mapa", "mapa_capa", "mapa_terreno")}
        raw.close()

        conn = db.connect(self.path)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            for table, rows in antes.items():
                self.assertEqual(dump(conn, table), rows, table)
            for table in ("base", "mapa"):
                nulls = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE carpeta_id IS NULL").fetchone()[0]
                total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(nulls, total)
            indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            self.assertTrue({"idx_base_carpeta", "idx_mapa_carpeta"} <= indexes)
        finally:
            conn.close()

        # The upgrade was backed up first, next to the database.
        self.assertEqual(len(list((self.path.parent / "respaldos").glob("v4-*.db"))), 1)

        # Running it again changes nothing.
        conn = db.connect(self.path)
        try:
            for table, rows in antes.items():
                self.assertEqual(dump(conn, table), rows, table)
        finally:
            conn.close()

    def test_v1_databases_still_upgrade_all_the_way(self):
        build_v1(self.path)
        conn = db.connect(self.path)
        try:
            self.assertIn("carpeta_id", {r[1] for r in conn.execute("PRAGMA table_info(base)")})
            self.assertIn("carpeta_id", {r[1] for r in conn.execute("PRAGMA table_info(mapa)")})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mapa_terreno").fetchone()[0], 3)
        finally:
            conn.close()

    def test_fresh_install(self):
        conn = db.connect(self.path)
        try:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(carpeta)")}
            self.assertEqual(columns, {"id", "tipo", "nombre", "nombre_clave", "creado_en", "actualizado_en"})
            self.assertIn("AUTOINCREMENT", conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'carpeta'").fetchone()[0])
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO carpeta (tipo, nombre, nombre_clave, creado_en, actualizado_en)"
                             " VALUES ('terrenos', 'x', 'x', 't', 't')")
        finally:
            conn.close()

    def test_a_deleted_folder_row_unfiles_through_the_foreign_key(self):
        conn = db.connect(self.path)
        try:
            conn.execute("INSERT INTO carpeta (id, tipo, nombre, nombre_clave, creado_en, actualizado_en)"
                         " VALUES (7, 'bases', 'X', 'x', 't', 't')")
            conn.execute("INSERT INTO base (nombre, importado_en, carpeta_id) VALUES ('B', 't', 7)")
            conn.execute("DELETE FROM carpeta WHERE id = 7")
            self.assertIsNone(conn.execute("SELECT carpeta_id FROM base").fetchone()[0])
        finally:
            conn.close()


class PostgresSchema(unittest.TestCase):
    def test_tables_in_dependency_order_with_generated_ids(self):
        self.assertEqual(postgres.TABLES[0], "carpeta")
        self.assertLess(postgres.TABLES.index("carpeta"), postgres.TABLES.index("base"))
        self.assertIn("carpeta", postgres.ID_TABLES)

    def test_fresh_schema_has_folders_but_no_index_that_breaks_old_tables(self):
        ddl = postgres.schema_sql()
        self.assertIn("CREATE TABLE IF NOT EXISTS carpeta", ddl)
        self.assertLess(ddl.index("TABLE IF NOT EXISTS carpeta"), ddl.index("TABLE IF NOT EXISTS base"))
        self.assertEqual(ddl.count("carpeta_id     INTEGER REFERENCES carpeta(id) ON DELETE SET NULL"), 2)
        self.assertNotIn("AUTOINCREMENT", ddl)
        # setup_cloud.py runs this against existing workspaces too, before its
        # "already seeded" check: nothing in it may need the new columns.
        self.assertNotIn("idx_base_carpeta", ddl)

    def test_upgrade_is_explicit_and_repeatable(self):
        sql = postgres.migrate_sql()
        for statement in ("CREATE TABLE IF NOT EXISTS carpeta",
                          "ALTER TABLE base ADD COLUMN IF NOT EXISTS carpeta_id",
                          "ALTER TABLE mapa ADD COLUMN IF NOT EXISTS carpeta_id",
                          "CREATE INDEX IF NOT EXISTS idx_base_carpeta",
                          "CREATE INDEX IF NOT EXISTS idx_mapa_carpeta",
                          "ON CONFLICT (key) DO UPDATE"):
            self.assertIn(statement, sql)
        self.assertIn(f"'{db.SCHEMA_VERSION}'", sql)
        self.assertLess(sql.index("carpeta ("), sql.index("ALTER TABLE base"))

    def test_the_sqlite_schema_translates_where_sqlite_would_not_care(self):
        # SQLite accepts a forward reference; Postgres does not.
        self.assertLess(db.SCHEMA.index("TABLE IF NOT EXISTS carpeta"), db.SCHEMA.index("TABLE IF NOT EXISTS base"))


class ReadOnlyLocal(TempDatabase):
    def setUp(self):
        super().setUp()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        # Every legacy route needs a session now. Read-only mode cannot create
        # one (the file is immutable), so the session is made beforehand.
        create_user(self.conn)
        self.cookie = session_cookie(self.conn)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def call(self, method, path, body=None, anonymous=False):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json",
                     **({} if anonymous else {"Cookie": self.cookie})})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_viewers_browse_but_cannot_change_folders(self):
        self.assertEqual(self.call("POST", "/api/carpetas", {"tipo": "bases", "nombre": "A"})[0], 200)
        # Read-only mode opens the file as immutable, as published; it does not
        # read the write-ahead log, so settle it into the file first.
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with patch.dict(os.environ, {"ARA_MAP_READ_ONLY": "1"}):
            status, body = self.call("GET", "/api/carpetas?tipo=bases")
            self.assertEqual((status, len(body["carpetas"])), (200, 1))
            # Anonymous viewers no longer browse legacy folders, and nobody can
            # sign in against an immutable file.
            self.assertEqual(self.call("GET", "/api/carpetas?tipo=bases", anonymous=True)[0], 401)
            self.assertEqual(self.call("POST", "/api/login", {"username": "ana", "password": "x"},
                                       anonymous=True)[0], 403)
            for method, path, payload in (
                ("POST", "/api/carpetas", {"tipo": "bases", "nombre": "B"}),
                ("PATCH", "/api/carpetas/1", {"nombre": "C"}),
                ("DELETE", "/api/carpetas/1", None),
                ("PATCH", "/api/bases/1/carpeta", {"carpeta_id": None}),
                ("PATCH", "/api/mapas/1/carpeta", {"carpeta_id": None}),
            ):
                with self.subTest(method=method, path=path):
                    status, body = self.call(method, path, payload)
                    self.assertEqual(status, 403)
                    self.assertIn("solo consulta", body["error"])
        self.assertEqual(self.call("GET", "/api/carpetas?tipo=bases")[1]["carpetas"][0]["nombre"], "A")


class CloudAccess(unittest.TestCase):
    def test_anonymous_folder_writes_are_rejected(self):
        with patch.dict(os.environ, {"ARA_MAP_EDIT_PASSWORD": "pw", "ARA_MAP_PUBLIC_EDIT": "0"}):
            spec = importlib.util.spec_from_file_location(
                "cloud_adapter_folders", Path(__file__).parents[1] / "api" / "index.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                for method, path in (("POST", "/api/carpetas"), ("PATCH", "/api/carpetas/1"),
                                     ("DELETE", "/api/carpetas/1"), ("PATCH", "/api/bases/1/carpeta"),
                                     ("PATCH", "/api/mapas/1/carpeta")):
                    with self.subTest(method=method, path=path):
                        connection = HTTPConnection("127.0.0.1", httpd.server_port)
                        connection.request(method, path, body="{}", headers={"Host": "ara-map.vercel.app"})
                        response = connection.getresponse()
                        self.assertEqual(response.status, 401)
                        response.read()
                        connection.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()

"""Schema 8 -> 9: work bases, grants, roles and custom columns.

The same checks run on SQLite and, when ARA_MAP_TEST_DATABASE_URL is set, on a
disposable Postgres schema. Each backend builds a synthetic schema-8 database
with fictional data, upgrades it twice and compares it with what was there.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import auth, db, inventario, postgres
from server.importer import read_workbook
from server.repo import bases, mapas, terrenos
from server.repo import inventario as repo
from server.validation import validate_all
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
FIXTURE = Path(__file__).parent / "fixtures" / "base_terrenos_08_26_sintetica.xlsx"

V8_TABLES = ("team_user", "inventory_terrain", "inventory_revision", "inventory_event",
             "inventory_operation_result", "base", "terreno", "incidencia", "mapa", "mapa_capa",
             "mapa_terreno")
V9_TABLES = ("maestra_base", "maestra_base_acceso", "inventory_column", "team_user_event",
             "maestra_base_event")
AHORA = "2026-10-08T00:00:00+00:00"


def poblar(conn):
    """Fictional schema-8 content: accounts, an edited terrain, a legacy base and a saved map."""
    for login in ("ana", "beto"):
        auth.create_user(conn, login, login.capitalize() + " Prueba", TEST_PASSWORD, iterations=1000)
    ana = dict(conn.execute("SELECT id, display_name FROM team_user WHERE login = 'ana'").fetchone())
    terreno = repo.create(conn, {"terreno": "Lote ficticio", "asking_price": 100, "moneda": "MXN"},
                          ana, str(uuid.uuid4()), "hash")["terreno"]
    repo.update(conn, terreno["id"], terreno["version"], {"estado": "Jalisco"}, (), ana)
    leido = read_workbook(FIXTURE)
    base_id = bases.create(conn, "Base importada ficticia", "ficticia.xlsx", leido.hoja)
    terrenos.insert(conn, base_id, leido.records, validate_all(leido.records))
    mapas.create(conn, "Mapa ficticio", "simple",
                 [{"base_id": base_id, "color": "#123456", "visible": True}])


def foto(conn, tablas):
    return {t: sorted((dict(r) for r in conn.execute(f"SELECT * FROM {t}").fetchall()), key=repr)
            for t in tablas}


class V9Checks:
    """Mixed into one TestCase per backend. The backend provides abrir(),
    version(), ``antes`` (schema-8 rows) and ``despues`` (rows right after)."""

    def fila(self, conn, sql, params=()):
        return dict(conn.execute(sql, params).fetchone())

    def usuario(self, conn, login="ana"):
        return self.fila(conn, "SELECT id FROM team_user WHERE login = ?", (login,))["id"]

    def nueva_base(self, conn, nombre="Base Ejemplo"):
        base_id, ana = str(uuid.uuid4()), self.usuario(conn)
        conn.execute("INSERT INTO maestra_base (id, nombre, created_at, created_by, updated_at,"
                     " updated_by) VALUES (?, ?, ?, ?, ?, ?)", (base_id, nombre, AHORA, ana, AHORA, ana))
        return base_id

    def nueva_columna(self, conn, base_id, tipo="texto", nombre="Folio"):
        columna_id, ana = str(uuid.uuid4()), self.usuario(conn)
        conn.execute("INSERT INTO inventory_column (id, base_id, nombre, tipo, orden, created_at,"
                     " created_by, updated_at, updated_by) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
                     (columna_id, base_id, nombre, tipo, AHORA, ana, AHORA, ana))
        return columna_id

    def rechaza(self, sql, params=()):
        """The statement must break a constraint, and leave the session usable."""
        with self.abrir() as conn, self.assertRaises(self.integridad), db.transaction(conn):
            conn.execute(sql, params)

    # -- the upgrade itself ----------------------------------------------------

    def test_the_version_is_9(self):
        self.assertEqual((db.SCHEMA_VERSION, self.version()), (9, 9))

    def test_existing_rows_keep_every_value_they_had(self):
        for tabla, filas in self.antes.items():
            self.assertTrue(filas or tabla == "incidencia", tabla)
            ahora = [{k: fila[k] for k in filas[0]} for fila in self.despues[tabla]] if filas else []
            self.assertEqual(sorted(ahora, key=repr), filas, tabla)

    def test_nobody_is_promoted_and_nothing_is_assigned(self):
        self.assertEqual({u["rol"] for u in self.despues["team_user"]}, {"operador"})
        self.assertEqual({t["base_id"] for t in self.despues["inventory_terrain"]}, {None})
        self.assertEqual(len(self.despues["inventory_revision"]), 2)
        for revision in self.despues["inventory_revision"]:
            self.assertEqual((revision["base_id"], revision["tipo_terreno"], revision["custom_json"]),
                             (None, None, "{}"))
        for tabla in V9_TABLES:
            self.assertEqual(self.despues[tabla], [], tabla)

    # -- existing behaviour ----------------------------------------------------

    def test_existing_accounts_still_sign_in(self):
        with self.abrir() as conn:
            token, user, _ = auth.login(conn, "beto", TEST_PASSWORD)
        self.assertTrue(token)
        self.assertNotIn("rol", user)

    def test_existing_code_reads_and_edits_a_migrated_record(self):
        with self.abrir() as conn:
            ana = self.fila(conn, "SELECT id, display_name FROM team_user WHERE login = 'ana'")
            antes = repo.all_records(conn)[0]
            despues = repo.update(conn, antes["id"], antes["version"],
                                  {"municipio": "Zapopan"}, (), ana)
            guardado = repo.get(conn, antes["id"])
            revision = self.fila(conn, "SELECT base_id, tipo_terreno, custom_json FROM"
                                 " inventory_revision WHERE id = ?", (guardado["draft_revision_id"],))
        self.assertEqual(guardado["draft"]["municipio"], "Zapopan")
        self.assertEqual(guardado["version"], antes["version"] + 1)
        self.assertTrue(despues)
        self.assertEqual(revision, {"base_id": None, "tipo_terreno": None, "custom_json": "{}"})

    def test_the_new_fields_are_not_exposed_by_existing_output(self):
        nuevos = {"base_id", "tipo_terreno", "custom_json", "custom", "rol"}
        with self.abrir() as conn:
            registro = repo.all_records(conn)[0]
        self.assertFalse(nuevos & set(registro))
        self.assertFalse(nuevos & set(registro["draft"]))
        self.assertFalse(nuevos & set(inventario.EDITABLE))
        self.assertFalse(nuevos & set(inventario.PUBLIC_QUERY))

    # -- what the new storage accepts ------------------------------------------

    def test_two_empty_bases_each_hold_their_own_column_of_the_same_name(self):
        with self.abrir() as conn:
            una, otra = self.nueva_base(conn, "Base Uno"), self.nueva_base(conn, "Base Dos")
            for base_id, tipo in ((una, "opcion"), (otra, "fecha")):
                self.nueva_columna(conn, base_id, tipo)
            columnas = [self.fila(conn, "SELECT nombre, tipo, opciones_json, version, retired_at"
                                  " FROM inventory_column WHERE base_id = ?", (b,)) for b in (una, otra)]
            base = self.fila(conn, "SELECT version, archived_at FROM maestra_base WHERE id = ?", (una,))
            terrenos_en_base = self.fila(conn, "SELECT COUNT(*) AS n FROM inventory_terrain"
                                         " WHERE base_id IN (?, ?)", (una, otra))["n"]
        self.assertEqual(base, {"version": 1, "archived_at": None})
        self.assertEqual(terrenos_en_base, 0)
        self.assertEqual(columnas, [
            {"nombre": "Folio", "tipo": "opcion", "opciones_json": "[]", "version": 1, "retired_at": None},
            {"nombre": "Folio", "tipo": "fecha", "opciones_json": "[]", "version": 1, "retired_at": None}])

    def test_a_revoked_grant_stays_in_the_account_history(self):
        with self.abrir() as conn:
            base_id, ana, beto = self.nueva_base(conn), self.usuario(conn), self.usuario(conn, "beto")
            conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                         " VALUES (?, ?, ?, ?)", (base_id, beto, AHORA, ana))
            for accion, actor in (("acceso_otorgado", ana), ("acceso_revocado", None)):
                conn.execute("INSERT INTO team_user_event (id, user_id, action, base_id, actor_id,"
                             " actor_name, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (str(uuid.uuid4()), beto, accion, base_id, actor, "Ana Prueba", AHORA))
            conn.execute("DELETE FROM maestra_base_acceso WHERE base_id = ?", (base_id,))
            historia = conn.execute("SELECT action FROM team_user_event WHERE base_id = ?"
                                    " ORDER BY action", (base_id,)).fetchall()
        self.assertEqual([h["action"] for h in historia], ["acceso_otorgado", "acceso_revocado"])

    # -- what it refuses -------------------------------------------------------

    def test_a_role_outside_the_two_is_refused(self):
        self.rechaza("UPDATE team_user SET rol = 'jefe' WHERE login = 'beto'")

    def test_a_column_type_outside_the_four_is_refused(self):
        with self.abrir() as conn:
            base_id, ana = self.nueva_base(conn), self.usuario(conn)
        self.rechaza("INSERT INTO inventory_column (id, base_id, nombre, tipo, orden, created_at,"
                     " created_by, updated_at, updated_by) VALUES ('x', ?, 'Plano', 'archivo', 1,"
                     " ?, ?, ?, ?)", (base_id, AHORA, ana, AHORA, ana))

    def test_a_grant_cannot_be_given_twice(self):
        with self.abrir() as conn:
            base_id, ana = self.nueva_base(conn), self.usuario(conn)
            otorgar = ("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                       " VALUES (?, ?, ?, ?)", (base_id, ana, AHORA, ana))
            conn.execute(*otorgar)
        self.rechaza(*otorgar)

    def test_references_to_a_base_that_does_not_exist_are_refused(self):
        with self.abrir() as conn:
            base_id, ana = self.nueva_base(conn), self.usuario(conn)
        self.rechaza("UPDATE inventory_terrain SET base_id = 'no-existe'")
        self.rechaza("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                     " VALUES ('no-existe', ?, ?, ?)", (ana, AHORA, ana))
        self.rechaza("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                     " VALUES (?, 'nadie', ?, ?)", (base_id, AHORA, ana))

    def test_a_base_or_account_in_use_cannot_be_deleted(self):
        with self.abrir() as conn:
            ana = self.usuario(conn)
            con_terreno, con_columna, con_acceso = (self.nueva_base(conn) for _ in range(3))
            terreno = self.fila(conn, "SELECT id FROM inventory_terrain LIMIT 1")["id"]
            conn.execute("UPDATE inventory_terrain SET base_id = ? WHERE id = ?", (con_terreno, terreno))
            columna = self.nueva_columna(conn, con_columna)
            conn.execute("INSERT INTO maestra_base_event (id, base_id, column_id, version, action,"
                         " actor_id, actor_name, at) VALUES (?, ?, ?, 1, 'columna_creada', ?, 'Ana', ?)",
                         (str(uuid.uuid4()), con_columna, columna, ana, AHORA))
            conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                         " VALUES (?, ?, ?, ?)", (con_acceso, self.usuario(conn, "beto"), AHORA, ana))
        for base_id in (con_terreno, con_columna, con_acceso):
            self.rechaza("DELETE FROM maestra_base WHERE id = ?", (base_id,))
        self.rechaza("DELETE FROM inventory_column WHERE id = ?", (columna,))
        self.rechaza("DELETE FROM team_user WHERE login = 'beto'")
        with self.abrir() as conn:
            quedan = self.fila(conn, "SELECT COUNT(*) AS n FROM inventory_terrain WHERE id = ?",
                               (terreno,))["n"]
            conn.execute("UPDATE inventory_terrain SET base_id = NULL WHERE id = ?", (terreno,))
        self.assertEqual(quedan, 1)

    def test_a_definition_has_one_event_per_version(self):
        with self.abrir() as conn:
            base_id, ana = self.nueva_base(conn), self.usuario(conn)
            columna = self.nueva_columna(conn, base_id)
            evento = ("INSERT INTO maestra_base_event (id, base_id, column_id, version, action,"
                      " actor_id, actor_name, at) VALUES (?, ?, ?, 1, 'cambio', ?, 'Ana', ?)")
            # Version 1 of the base and version 1 of its column are different things.
            for column_id in (None, columna):
                conn.execute(evento, (str(uuid.uuid4()), base_id, column_id, ana, AHORA))
        for column_id in (None, columna):
            self.rechaza(evento, (str(uuid.uuid4()), base_id, column_id, ana, AHORA))


class SchemaV9Sqlite(V9Checks, unittest.TestCase):
    integridad = sqlite3.IntegrityError

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "v8.db"
        # The v8 definitions are still the first thing a v9 database runs; the
        # assertion below fails if someone later edits a v9 column into them.
        v8 = sqlite3.connect(cls.path, isolation_level=None)
        v8.row_factory = sqlite3.Row
        v8.execute("PRAGMA foreign_keys = ON")
        v8.executescript(db.SCHEMA + db.INVENTORY_SCHEMA + db.FOLDER_INDEXES)
        v8.execute("PRAGMA user_version = 8")
        tablas = {r[0] for r in v8.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert not tablas & set(V9_TABLES)
        for tabla, columna, _ in db.V9_COLUMNS:
            assert columna not in {r[1] for r in v8.execute(f"PRAGMA table_info({tabla})")}
        poblar(v8)
        cls.antes = foto(v8, V8_TABLES)
        v8.close()
        for _ in range(2):  # the second run must change nothing
            with db.session(cls.path) as conn:
                cls.despues = foto(conn, V8_TABLES + V9_TABLES)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def abrir(self):
        return db.session(self.path)

    def version(self):
        with self.abrir() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]

    def test_the_upgrade_took_exactly_one_backup(self):
        self.assertEqual(len(list(db.backup_dir(self.path).glob("*.db"))), 1)


@unittest.skipUnless(URL, "No Postgres test connection configured")
class SchemaV9Postgres(V9Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.integridad = psycopg.IntegrityError
        cls.schema = "test_ara_v9_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
            # Back to schema 8: no work-base tables, none of their columns.
            conn.raw.execute(
                f"DROP TABLE {', '.join(V9_TABLES)} CASCADE;"
                + "".join(f"ALTER TABLE {t} DROP COLUMN {c};" for t, c, _ in db.V9_COLUMNS)
                + "UPDATE workspace_metadata SET value = '8' WHERE key = 'schema_version';",
                prepare=False)
        with postgres.session() as conn:
            assert postgres.schema_version(conn) == 8
            poblar(conn)
            cls.antes = foto(conn, V8_TABLES)
            assert "rol" not in cls.antes["team_user"][0]
            assert "custom_json" not in cls.antes["inventory_revision"][0]
        for _ in range(2):  # the second run must change nothing
            with postgres.session() as conn:
                postgres.migrate(conn)
            with postgres.session() as conn:
                cls.despues = foto(conn, V8_TABLES + V9_TABLES)

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def abrir(self):
        return db.session()

    def version(self):
        with self.abrir() as conn:
            return postgres.schema_version(conn)

    def test_the_backup_carries_the_work_base_tables(self):
        import json
        with self.abrir() as conn:
            self.nueva_base(conn, "Base Respaldada")
        postgres.backup()
        with self.abrir() as conn:
            payload = json.loads(conn.execute(
                "SELECT payload FROM workspace_backup ORDER BY id DESC LIMIT 1").fetchone()["payload"])
        self.assertTrue(set(V9_TABLES) <= set(payload))
        self.assertIn("Base Respaldada", [b["nombre"] for b in payload["maestra_base"]])


if __name__ == "__main__":
    unittest.main()

"""Upgrading a database created before saved maps became snapshots."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from server import db
from server.repo import mapas

# The schema exactly as version 1 shipped it: mapa_capa cascaded from base,
# carried no base name, and there was no frozen terrain table.
SCHEMA_V1 = """
CREATE TABLE base (
  id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, archivo_origen TEXT,
  hoja TEXT, importado_en TEXT NOT NULL, notas TEXT
);
CREATE TABLE terreno (
  id INTEGER PRIMARY KEY,
  base_id INTEGER NOT NULL REFERENCES base(id) ON DELETE CASCADE,
  id_origen INTEGER, orden INTEGER NOT NULL, terreno TEXT NOT NULL,
  estado TEXT, municipio TEXT, direccion TEXT,
  superficie_m2 REAL, superficie_ha REAL, afectaciones_pct REAL,
  afectaciones_m2 REAL, asking_price REAL, asking_m2 REAL,
  lat REAL, lon REAL, clave_dedupe TEXT NOT NULL, extra_json TEXT
);
CREATE TABLE incidencia (
  id INTEGER PRIMARY KEY,
  terreno_id INTEGER NOT NULL REFERENCES terreno(id) ON DELETE CASCADE,
  severidad TEXT NOT NULL, codigo TEXT NOT NULL, mensaje TEXT NOT NULL
);
CREATE TABLE mapa (
  id INTEGER PRIMARY KEY, nombre TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('simple', 'comparacion')),
  creado_en TEXT NOT NULL, config_json TEXT
);
CREATE TABLE mapa_capa (
  mapa_id INTEGER NOT NULL REFERENCES mapa(id) ON DELETE CASCADE,
  base_id INTEGER NOT NULL REFERENCES base(id) ON DELETE CASCADE,
  color TEXT NOT NULL, orden INTEGER NOT NULL,
  visible INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (mapa_id, base_id)
);
PRAGMA user_version = 1;
"""


def build_v1(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1)
    conn.execute("INSERT INTO base (id, nombre, importado_en) VALUES (1, 'Agosto', 'x')")
    conn.execute("INSERT INTO base (id, nombre, importado_en) VALUES (2, 'Septiembre', 'x')")
    for terreno_id, base_id, nombre, lat in (
        (1, 1, "El Mirador", 20.7), (2, 1, "Sin coords", None), (3, 2, "La Loma", 20.8),
    ):
        conn.execute(
            "INSERT INTO terreno (id, base_id, orden, terreno, lat, lon, clave_dedupe)"
            " VALUES (?, ?, 1, ?, ?, ?, ?)",
            (terreno_id, base_id, nombre, lat, -103.4 if lat else None, nombre.lower()),
        )
    conn.execute(
        "INSERT INTO incidencia (terreno_id, severidad, codigo, mensaje)"
        " VALUES (2, 'aviso', 'SIN_COORDENADAS', 'Sin coordenadas.')")
    conn.execute(
        "INSERT INTO mapa (id, nombre, tipo, creado_en, config_json)"
        " VALUES (1, 'Comparación vieja', 'comparacion', 'x', '{\"basemap\": \"claro\"}')")
    for base_id, color, orden in ((1, "#2a78d6", 0), (2, "#eb6834", 1)):
        conn.execute(
            "INSERT INTO mapa_capa (mapa_id, base_id, color, orden, visible)"
            " VALUES (1, ?, ?, ?, 1)", (base_id, color, orden))
    conn.commit()
    conn.close()


class MigrateV1ToV2(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "v1.db"
        build_v1(self.path)
        self.conn = db.connect(self.path)   # runs the migration

    def tearDown(self):
        self.conn.close()
        self._dir.cleanup()

    def test_the_version_is_bumped(self):
        self.assertEqual(
            self.conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)

    def test_the_new_tables_exist(self):
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("mapa_terreno", tables)

    def test_existing_layers_survive_with_their_base_names(self):
        capas = mapas.get(self.conn, 1)["capas"]
        self.assertEqual([c["nombre"] for c in capas], ["Agosto", "Septiembre"])
        self.assertEqual([c["color"] for c in capas], ["#2a78d6", "#eb6834"])

    def test_old_maps_are_snapshotted_during_the_upgrade(self):
        filas = mapas.terrenos(self.conn, 1)
        self.assertEqual({f["terreno"] for f in filas},
                         {"El Mirador", "Sin coords", "La Loma"})

    def test_findings_are_carried_into_the_snapshot(self):
        fila = next(f for f in mapas.terrenos(self.conn, 1) if f["terreno"] == "Sin coords")
        self.assertEqual([i["codigo"] for i in fila["incidencias"]], ["SIN_COORDENADAS"])

    def test_the_saved_view_config_is_preserved(self):
        self.assertEqual(mapas.get(self.conn, 1)["config"], {"basemap": "claro"})

    def test_an_upgraded_map_now_survives_base_deletion(self):
        from server.repo import bases
        bases.delete(self.conn, 1)
        capas = mapas.get(self.conn, 1)["capas"]
        self.assertEqual(len(capas), 2)
        self.assertEqual(len(mapas.terrenos(self.conn, 1)), 3)

    def test_migrating_twice_changes_nothing(self):
        db.migrate(self.conn)
        self.assertEqual(len(mapas.terrenos(self.conn, 1)), 3)
        self.assertEqual(len(mapas.get(self.conn, 1)["capas"]), 2)


class MigrateV2ToV3(unittest.TestCase):
    """A v2 database handed out reusable source ids; v3 must stop that."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "v2.db"
        build_v1(self.path)
        # Bring it to v2 the way a real installation would have got there.
        primera = db.connect(self.path)
        primera.close()
        # Then undo the v3 step so the upgrade has something to do.
        crudo = sqlite3.connect(self.path)
        crudo.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE base_v2 (
              id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, archivo_origen TEXT,
              hoja TEXT, importado_en TEXT NOT NULL, notas TEXT
            );
            INSERT INTO base_v2 SELECT id, nombre, archivo_origen, hoja, importado_en, notas FROM base;
            DROP TABLE base;
            ALTER TABLE base_v2 RENAME TO base;
            PRAGMA user_version = 2;
        """)
        crudo.commit()
        crudo.close()
        self.conn = db.connect(self.path)   # runs the v3 migration

    def tearDown(self):
        self.conn.close()
        self._dir.cleanup()

    def test_the_version_advances(self):
        self.assertEqual(
            self.conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)

    def test_existing_bases_keep_their_ids(self):
        filas = self.conn.execute("SELECT id, nombre FROM base ORDER BY id").fetchall()
        self.assertEqual([(r["id"], r["nombre"]) for r in filas],
                         [(1, "Agosto"), (2, "Septiembre")])

    def test_saved_maps_still_point_at_the_right_sources(self):
        capas = mapas.get(self.conn, 1)["capas"]
        self.assertEqual([c["nombre"] for c in capas], ["Agosto", "Septiembre"])
        self.assertTrue(all(c["base_existe"] for c in capas))

    def test_terrains_survive_the_table_rebuild(self):
        total = self.conn.execute("SELECT COUNT(*) FROM terreno").fetchone()[0]
        self.assertEqual(total, 3)

    def test_ids_are_no_longer_reused_afterwards(self):
        from server.repo import bases
        nueva = bases.create(self.conn, "Octubre", None, None)
        bases.delete(self.conn, nueva)
        otra = bases.create(self.conn, "Noviembre", None, None)
        self.assertNotEqual(otra, nueva)


class MigrateV3ToV4(unittest.TestCase):
    """Names: raw source text separated from version text, plus a title mode."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "v3.db"
        build_v1(self.path)
        primera = db.connect(self.path)   # brings it to the current version
        primera.close()

        # Undo the v4 step, and recreate what v3 actually stored: a combined
        # "source · version" string with no separate version column.
        crudo = sqlite3.connect(self.path)
        crudo.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE mapa_v3 (
              id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, tipo TEXT NOT NULL,
              creado_en TEXT NOT NULL, actualizado_en TEXT, config_json TEXT
            );
            INSERT INTO mapa_v3 SELECT id, nombre, tipo, creado_en, actualizado_en, config_json FROM mapa;
            DROP TABLE mapa;
            ALTER TABLE mapa_v3 RENAME TO mapa;

            CREATE TABLE capa_v3 (
              mapa_id INTEGER NOT NULL, orden INTEGER NOT NULL, base_id INTEGER,
              base_nombre TEXT NOT NULL, color TEXT NOT NULL,
              visible INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (mapa_id, orden)
            );
            INSERT INTO capa_v3 SELECT mapa_id, orden, base_id, base_nombre, color, visible FROM mapa_capa;
            DROP TABLE mapa_capa;
            ALTER TABLE capa_v3 RENAME TO mapa_capa;

            UPDATE mapa_capa SET base_nombre = 'Agosto · Mapa viejo' WHERE base_id = 1;
            INSERT INTO mapa (id, nombre, tipo, creado_en, config_json)
              VALUES (2, 'Agosto', 'simple', 'x', '{}');
            INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre, color, visible)
              VALUES (2, 0, 1, 'Agosto', '#1', 1);
            INSERT INTO mapa (id, nombre, tipo, creado_en, config_json)
              VALUES (3, 'Título del cliente', 'simple', 'x', '{}');
            INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre, color, visible)
              VALUES (3, 0, 2, 'Septiembre', '#1', 1);
            PRAGMA user_version = 3;
        """)
        crudo.commit()
        crudo.close()
        self.conn = db.connect(self.path)   # runs the v4 migration

    def tearDown(self):
        self.conn.close()
        self._dir.cleanup()

    def test_the_version_advances(self):
        self.assertEqual(
            self.conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)

    def test_the_new_columns_exist(self):
        self.assertIn("nombre_sigue_base",
                      {r[1] for r in self.conn.execute("PRAGMA table_info(mapa)")})
        self.assertIn("version_etiqueta",
                      {r[1] for r in self.conn.execute("PRAGMA table_info(mapa_capa)")})

    def test_a_combined_legacy_label_is_split_only_where_unambiguous(self):
        fila = self.conn.execute(
            "SELECT base_nombre, version_etiqueta FROM mapa_capa"
            " WHERE mapa_id = 1 AND base_id = 1").fetchone()
        self.assertEqual(fila["base_nombre"], "Agosto")
        self.assertEqual(fila["version_etiqueta"], "Mapa viejo")

    def test_the_display_label_is_unchanged_by_the_split(self):
        capa = next(c for c in mapas.get(self.conn, 1)["capas"] if c["base_id"] == 1)
        self.assertEqual(capa["nombre"], "Agosto · Mapa viejo")

    def test_a_default_title_is_inferred_as_following(self):
        self.assertTrue(mapas.get(self.conn, 2)["nombre_sigue_base"])

    def test_a_custom_title_is_left_as_custom(self):
        self.assertFalse(mapas.get(self.conn, 3)["nombre_sigue_base"])

    def test_a_rename_after_migrating_behaves_as_expected(self):
        from server.repo import bases
        bases.rename(self.conn, 1, "Agosto Nuevo")
        self.assertEqual(mapas.get(self.conn, 2)["nombre"], "Agosto Nuevo")
        capa = next(c for c in mapas.get(self.conn, 1)["capas"] if c["base_id"] == 1)
        self.assertEqual(capa["nombre"], "Agosto Nuevo · Mapa viejo")

    def test_running_the_migration_twice_changes_nothing(self):
        db.migrate(self.conn)
        self.assertTrue(mapas.get(self.conn, 2)["nombre_sigue_base"])
        self.assertFalse(mapas.get(self.conn, 3)["nombre_sigue_base"])
        capa = next(c for c in mapas.get(self.conn, 1)["capas"] if c["base_id"] == 1)
        self.assertEqual(capa["nombre"], "Agosto · Mapa viejo")


class FreshDatabase(unittest.TestCase):
    def test_a_new_database_starts_at_the_current_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "nueva.db")
            try:
                self.assertEqual(
                    conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

"""Schema v6 (import formats, import records, assistance usage): upgrade paths."""

from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from server import db, postgres

NUEVAS = ("formato_importacion", "importacion", "uso_ia")

# Version 5 as shipped: today's schema without the v6 tables.
SCHEMA_V5 = re.sub(r"--[^\n]*", "", db.SCHEMA)
for _tabla in NUEVAS:
    SCHEMA_V5 = re.sub(rf"CREATE TABLE IF NOT EXISTS {_tabla} \(.*?\);", "", SCHEMA_V5, flags=re.S)
    SCHEMA_V5 = re.sub(rf"CREATE INDEX IF NOT EXISTS \w+ ON {_tabla}\(.*?\);", "", SCHEMA_V5)


class UpgradeFromFolders(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "v5.db"
        conn = sqlite3.connect(self.path)
        conn.executescript(SCHEMA_V5 + db.FOLDER_INDEXES)
        conn.executescript("""
            INSERT INTO carpeta (id, tipo, nombre, nombre_clave, creado_en, actualizado_en)
              VALUES (1, 'bases', 'Clientes', 'clientes', 't', 't');
            INSERT INTO base (id, nombre, importado_en, carpeta_id) VALUES (1, 'Agosto', 't', 1);
            INSERT INTO terreno (id, base_id, orden, terreno, clave_dedupe) VALUES (1, 1, 1, 'A', 'a');
            INSERT INTO mapa (id, nombre, tipo, creado_en, actualizado_en) VALUES (1, 'M', 'simple', 't', 't2');
            INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre, color) VALUES (1, 0, 1, 'Agosto', '#111');
            INSERT INTO mapa_terreno (mapa_id, capa_orden, orden, terreno, clave_dedupe) VALUES (1, 0, 1, 'A', 'a');
            PRAGMA user_version = 5;
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        self._dir.cleanup()

    def dump(self, conn):
        """Every row's content. The currency column the upgrade adds is left out
        here and checked on its own: it must arrive empty, never guessed."""
        conn.row_factory = sqlite3.Row
        return {t: [tuple(v for k, v in zip(r.keys(), r) if k != "moneda")
                    for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                for t in ("carpeta", "base", "terreno", "mapa", "mapa_capa", "mapa_terreno")}

    def test_upgrade_adds_tables_and_changes_no_content(self):
        raw = sqlite3.connect(self.path)
        antes = self.dump(raw)
        raw.close()
        conn = db.connect(self.path)
        try:
            self.assertEqual(self.dump(conn), antes)
            tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue(set(NUEVAS) <= tablas)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            for tabla in ("terreno", "mapa_terreno"):
                self.assertIn("moneda", {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")})
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE moneda IS NOT NULL")
                                 .fetchone()[0], 0)
        finally:
            conn.close()
        self.assertEqual(len(list((self.path.parent / "respaldos").glob("v5-*.db"))), 1)
        conn = db.connect(self.path)  # again: harmless
        conn.close()


class PostgresDDL(unittest.TestCase):
    def test_new_tables_in_backups_ids_and_upgrade(self):
        # The legacy tables keep their order; v8's inventory tables follow them.
        self.assertEqual(postgres.LEGACY_TABLES[-2:], ("formato_importacion", "importacion"))
        self.assertEqual(postgres.TABLES[:len(postgres.LEGACY_TABLES)], postgres.LEGACY_TABLES)
        self.assertTrue({"formato_importacion", "importacion", "uso_ia"} <= postgres.ID_TABLES)
        self.assertNotIn("uso_ia", postgres.TABLES)
        sql = postgres.migrate_sql()
        orden = [sql.index(f"CREATE TABLE IF NOT EXISTS {t} (") for t in
                 ("carpeta", "formato_importacion", "importacion", "uso_ia", "borrador_importacion")]
        self.assertEqual(orden, sorted(orden))
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_uso_ia_mes", sql)
        self.assertNotIn("AUTOINCREMENT", sql)
        self.assertIn("DOUBLE PRECISION", sql)

    def test_drafts_exist_only_in_the_cloud_schema(self):
        self.assertIn("borrador_importacion", postgres.schema_sql())
        self.assertNotIn("borrador_importacion", db.SCHEMA)
        self.assertNotIn("borrador_importacion", postgres.TABLES)



class CloudAccess(unittest.TestCase):
    """Drafts, samples and formats are for editors only -- even to read."""

    def test_anonymous_cannot_analyze_prepare_or_list_formats(self):
        import importlib.util
        import os
        import threading
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch

        with patch.dict(os.environ, {"ARA_MAP_EDIT_PASSWORD": "pw", "ARA_MAP_PUBLIC_EDIT": "0"}):
            spec = importlib.util.spec_from_file_location(
                "cloud_adapter_asistente", Path(__file__).parents[1] / "api" / "index.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                for method, path in (("POST", "/api/importar/analizar"), ("POST", "/api/importar/preparar"),
                                     ("GET", "/api/formatos"), ("PATCH", "/api/formatos/1"),
                                     ("DELETE", "/api/formatos/1")):
                    with self.subTest(method=method, path=path):
                        conexion = HTTPConnection("127.0.0.1", httpd.server_port)
                        conexion.request(method, path, body="{}", headers={"Host": "ara-map.vercel.app"})
                        respuesta = conexion.getresponse()
                        self.assertEqual(respuesta.status, 401)
                        respuesta.read()
                        conexion.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()

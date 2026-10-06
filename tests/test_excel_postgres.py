"""Connected workbooks on a real, disposable Postgres, through the cloud
adapter (api/index.py): the "local real Postgres" evidence category.

Runs only when ARA_MAP_TEST_DATABASE_URL names a disposable database; the
class works in its own schema and drops it. The provider is the in-memory
fake from excel_support -- no Microsoft call is made.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
import unittest
import uuid
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import auth, db, postgres
from server.api import excel as api_excel
from server.repo import excel as repo
from server.repo import terrenos as repo_terrenos
from tests.excel_support import BASICO, Drive, crear_cuenta, fila, libro
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
CONFIG = {"hoja": "Registro Análisis", "columna_id": "ID", "moneda": "USD"}


@unittest.skipUnless(URL, "No Postgres test connection configured")
class ExcelPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.schema = "test_ara_excel_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
        spec = importlib.util.spec_from_file_location(
            "cloud_adapter_excel", Path(__file__).parents[1] / "api" / "index.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def setUp(self):
        with postgres.session() as conn:
            conn.raw.execute(
                "TRUNCATE excel_ejecucion, excel_version_fila, excel_identidad, excel_version,"
                " excel_configuracion, excel_fuente, excel_credencial, excel_autorizacion, excel_cuenta,"
                " inventory_operation_result, mapa_terreno, mapa_capa, mapa, incidencia, terreno, base,"
                " team_session, team_login_failure, team_user CASCADE")
            users = {n: auth.create_user(conn, n, n.capitalize(), TEST_PASSWORD, iterations=1000)
                     for n in ("ana", "beto")}
            self.cuenta = crear_cuenta(conn, users["ana"]["id"])
        self.jars = {n: self.login(n) for n in ("ana", "beto")}
        self.drive = Drive()
        self.archivo = self.drive.agregar("item-1", libro(BASICO))
        patcher = patch.object(api_excel, "FABRICA", self.drive)
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self, name):
        c = HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=30)
        c.request("POST", "/api/login", json.dumps({"username": name, "password": TEST_PASSWORD}),
                  {"Host": "ara.example"})
        r = c.getresponse()
        r.read()
        c.close()
        return {"Cookie": r.getheader("Set-Cookie").split(";")[0]}

    def call(self, method, path, body=None, user="ana", headers=None):
        c = HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=60)
        h = {"Host": "ara.example", **(headers or {}), **(self.jars[user] if user else {})}
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        result = r.status, json.loads(r.read())
        c.close()
        return result

    def key(self):
        return {"Idempotency-Key": f"pg-{uuid.uuid4()}"}

    def conectar(self):
        status, body = self.call("POST", "/api/excel/fuentes", {
            "cuenta_id": self.cuenta, "drive_id": "drive-ficticio", "item_id": "item-1",
            "nombre": "Conectada", **CONFIG}, headers=self.key())
        self.assertEqual(status, 200, body)
        return body["fuente"]

    def actualizar(self, fid, user="ana", headers=None, **body):
        return self.call("POST", f"/api/excel/fuentes/{fid}/actualizar", body, user,
                         headers=headers or self.key())

    def terrenos(self, base_id):
        return {t["terreno"]: t for t in self.call("GET", f"/api/bases/{base_id}/terrenos")[1]["terrenos"]}

    def test_schema_v9_and_pgcrypto(self):
        with db.session() as conn:
            self.assertEqual(postgres.schema_version(conn), 9)
            self.assertIsNotNone(conn.execute(
                "SELECT to_regprocedure('public.pgp_sym_encrypt(text,text)') AS f").fetchone()["f"])
            tablas = {r["table_name"] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")}
        self.assertTrue(set(postgres.EXCEL_TABLES) | {"excel_credencial", "excel_autorizacion"} <= tablas)

    def test_connect_edit_identity_and_history(self):
        f = self.conectar()
        antes = self.terrenos(f["base_id"])
        self.archivo.poner(libro([fila("A-001", "Lote Alfa", 1_500_000), fila("A-002", "Lote Beta", 2_000_000),
                                  fila("A-003", "Lote Delta")]))
        status, r = self.actualizar(f["id"], "beto")
        self.assertEqual((status, r["ejecucion"]["estado"]), (200, "ok"))
        self.assertEqual(r["ejecucion"]["conteos"],
                         {"agregados": 1, "actualizados": 1, "eliminados": 1, "sin_cambio": 1})
        despues = self.terrenos(f["base_id"])
        self.assertEqual(despues["Lote Alfa"]["id"], antes["Lote Alfa"]["id"])
        v1 = self.call("GET", f"/api/excel/fuentes/{f['id']}/versiones/{f['version_activa']['id']}")[1]
        self.assertEqual([r["clave"] for r in v1["filas"]], ["A-001", "A-002", "007"])
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "sin_cambios")

    def test_no_session_is_held_during_the_download(self):
        """The workspace advisory lock must not be held while the provider is
        busy: another employee's request completes meanwhile."""
        f = self.conectar()
        self.archivo.poner(libro(BASICO[:2]))
        self.archivo.esperar = threading.Event()
        self.archivo.descargando.clear()
        resultado = {}
        hilo = threading.Thread(target=lambda: resultado.update(a=self.actualizar(f["id"])))
        hilo.start()
        self.assertTrue(self.archivo.descargando.wait(10))
        inicio = time.monotonic()
        status, _ = self.call("GET", "/api/bases", user="beto")
        self.assertEqual(status, 200)
        self.assertLess(time.monotonic() - inicio, 5)
        status, body = self.actualizar(f["id"], "beto")  # second refresh: refused, not queued
        self.assertEqual((status, body["detalle"]["code"]), (409, "en_curso"))
        self.archivo.esperar.set()
        hilo.join(20)
        self.assertEqual(resultado["a"][1]["ejecucion"]["estado"], "ok")

    def test_stale_worker_is_fenced_on_separate_connections(self):
        f = self.conectar()
        with db.session() as conn:
            uid = conn.execute("SELECT id FROM team_user WHERE login = 'ana'").fetchone()["id"]
            a = repo.reclamar(conn, repo.fuente(conn, f["id"]), "actualizacion", "pg-worker-a", "h", uid)
            conn.execute("UPDATE excel_ejecucion SET lease_hasta = 0 WHERE id = ?", (a["id"],))
        self.archivo.poner(libro(BASICO[:1]))
        b = self.actualizar(f["id"], "beto")[1]
        self.assertEqual(b["ejecucion"]["estado"], "ok")
        from server.excel import lectura
        from server.excel.proveedor import Metadatos
        lect = lectura.leer(libro(BASICO), lectura.Configuracion(**CONFIG))
        with db.session() as conn, self.assertRaises(repo.SinPropiedadError):
            repo.activar(conn, a["id"], lect, Metadatos("x", None, None, 1, None, None, None), "s")
        with db.session() as conn:
            self.assertEqual(repo.ejecucion(conn, a["id"])["estado"], "interrumpida")
        self.assertEqual(set(self.terrenos(f["base_id"])), {"Lote Alfa"})

    def test_partial_materialization_rolls_back(self):
        f = self.conectar()
        antes = self.terrenos(f["base_id"])
        self.archivo.poner(libro([fila("A-001", "Alfa cambiado"), fila("A-002", "Beta cambiado")]))
        original = repo_terrenos.update_from_record
        llamadas = []

        def falla(conn, *a, **k):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise RuntimeError("fallo a mitad")
            return original(conn, *a, **k)

        with patch.object(repo_terrenos, "update_from_record", falla):
            r = self.actualizar(f["id"])[1]
        self.assertEqual(r["ejecucion"]["error"]["codigo"], "interno")
        self.assertEqual(self.terrenos(f["base_id"]), antes)
        with db.session() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM excel_version").fetchone()["n"], 1)

    def test_connect_replay_and_write_guard(self):
        clave = {"Idempotency-Key": "pg-conectar-una-vez"}
        body = {"cuenta_id": self.cuenta, "drive_id": "drive-ficticio", "item_id": "item-1",
                "nombre": "Conectada", **CONFIG}
        a = self.call("POST", "/api/excel/fuentes", body, headers=clave)[1]
        b = self.call("POST", "/api/excel/fuentes", body, headers=clave)[1]
        self.assertEqual(a["fuente"]["id"], b["fuente"]["id"])
        with db.session() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM base").fetchone()["n"], 1)
        base = a["fuente"]["base_id"]
        self.assertEqual(self.call("DELETE", f"/api/bases/{base}", headers={"Origin": "https://ara.example"})[0], 409)
        self.assertEqual(self.call("POST", f"/api/bases/{base}/terrenos", {"terreno": "x"})[0], 409)

    def test_upgrade_from_schema_8_is_additive_and_repeatable(self):
        """Simulates a v8 workspace (v9 is purely additive: drop the v9 tables
        and set version 8), then upgrades twice."""
        f = self.conectar()
        with postgres.session() as conn:
            conn.raw.execute("DROP TABLE excel_ejecucion, excel_version_fila, excel_identidad, excel_version,"
                             " excel_configuracion, excel_fuente, excel_credencial, excel_autorizacion,"
                             " excel_cuenta CASCADE")
            conn.execute("UPDATE workspace_metadata SET value = '8' WHERE key = 'schema_version'")
            legado = conn.execute("SELECT COUNT(*) AS n FROM terreno").fetchone()["n"]
        for _ in range(2):
            with postgres.session() as conn:
                postgres.migrate(conn)
        with postgres.session() as conn:
            self.assertEqual(postgres.schema_version(conn), 9)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM terreno").fetchone()["n"], legado)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM excel_fuente").fetchone()["n"], 0)
        self.assertTrue(f["id"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(URL, "No Postgres test connection configured")
class MigracionAEsquema9(unittest.TestCase):
    """Schema 8 -> 9 with the real migration script, checked against what
    schema 9 specifically adds (not only a moving SCHEMA_VERSION)."""

    TABLAS_9 = {"excel_cuenta", "excel_credencial", "excel_autorizacion", "excel_fuente", "excel_configuracion",
                "excel_version", "excel_identidad", "excel_version_fila", "excel_ejecucion"}

    def setUp(self):
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.esquema = "test_ara_v8_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{self.esquema}"')
        self.url = make_conninfo(URL, options=f"-c search_path={self.esquema}")
        with patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": self.url}), postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
            auth.create_user(conn, "ana", "Ana", TEST_PASSWORD, iterations=1000)
        # Exactly a schema-8 workspace: everything except what 9 adds.
        with psycopg.connect(self.url) as conn:
            conn.execute("DROP TABLE " + ", ".join(sorted(self.TABLAS_9)) + " CASCADE")
            conn.execute("UPDATE workspace_metadata SET value = '8' WHERE key = 'schema_version'")
            conn.execute("INSERT INTO base (id, nombre, importado_en) VALUES (1, 'Agosto', 't')")
            conn.execute("INSERT INTO terreno (id, base_id, orden, terreno, clave_dedupe) VALUES (1, 1, 1, 'Norte', 'n')")

    def tearDown(self):
        import psycopg
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{self.esquema}" CASCADE')

    def script(self, *args):
        import subprocess
        import sys
        entorno = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "ARA_MAP_DATABASE_URL")}
        entorno["ARA_MAP_V8_URL"] = self.url
        return subprocess.run([sys.executable, "scripts/migrate_cloud.py", "--url-env", "ARA_MAP_V8_URL", *args],
                              cwd=Path(__file__).parents[1], env=entorno, capture_output=True, text=True,
                              timeout=120)

    def test_8_to_9_adds_the_connector_keeps_data_and_repeats_safely(self):
        import psycopg
        self.assertEqual(self.script("--check").returncode, 1)
        for _ in range(2):
            salida = self.script()
            self.assertEqual(salida.returncode, 0, salida.stderr)
        with psycopg.connect(self.url) as conn:
            version = conn.execute("SELECT value FROM workspace_metadata WHERE key = 'schema_version'").fetchone()[0]
            tablas = {r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (self.esquema,))}
            datos = conn.execute("SELECT b.nombre, t.terreno FROM terreno t JOIN base b ON b.id = t.base_id").fetchall()
            indices = {r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname = %s",
                                                  (self.esquema,))}
            cascadas = conn.execute(
                "SELECT COUNT(*) FROM information_schema.referential_constraints r"
                " JOIN information_schema.table_constraints t ON t.constraint_name = r.constraint_name"
                " AND t.constraint_schema = r.constraint_schema"
                " WHERE r.constraint_schema = %s AND t.table_name LIKE 'excel_%%' AND r.delete_rule = 'CASCADE'",
                (self.esquema,)).fetchone()[0]
            pgcrypto = conn.execute("SELECT to_regprocedure('public.pgp_sym_encrypt(text,text,text)')").fetchone()[0]
        self.assertEqual(version, "9")
        self.assertTrue(self.TABLAS_9 <= tablas)
        self.assertEqual(datos, [("Agosto", "Norte")])
        self.assertTrue(any("en_curso" in i for i in indices), indices)   # one running refresh per source
        self.assertEqual(cascadas, 0)                                     # history is never cascaded away
        self.assertIsNotNone(pgcrypto)
        self.assertEqual(self.script("--check").returncode, 0)
        # Content backups never carry credentials or pending sign-ins.
        self.assertFalse({"excel_credencial", "excel_autorizacion"} & set(postgres.TABLES))
        self.assertTrue({"excel_fuente", "excel_version_fila", "excel_identidad"} <= set(postgres.TABLES))
        # The existing base is ordinary: every action stays available.
        with patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": self.url}), postgres.session() as conn:
            self.assertFalse(repo.conectada(conn, 1))

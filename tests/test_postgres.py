"""Optional real Postgres integration checks in a disposable, isolated schema.

ARA_MAP_TEST_DATABASE_URL must be set explicitly. Never writes existing tables.
"""
import concurrent.futures
import json
import os
import unittest
import uuid
from unittest.mock import patch

from server import db, postgres
from server.api import importar
from server.importer import read_workbook
from server.repo import bases, mapas, terrenos
from server.router import Request
from server.staging import Staging
from server.validation import validate_all
from tests.support import FIXTURE as REAL_FIXTURE

FIXTURE = REAL_FIXTURE.with_name("base_terrenos_08_26_sintetica.xlsx")


@unittest.skipUnless(os.environ.get("ARA_MAP_TEST_DATABASE_URL"), "No Postgres test connection configured")
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.url = os.environ["ARA_MAP_TEST_DATABASE_URL"]
        cls.schema = "test_ara_" + uuid.uuid4().hex
        with psycopg.connect(cls.url) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(cls.url, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.env.stop()
        with psycopg.connect(cls.url) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def setUp(self):
        with postgres.session() as conn:
            conn.raw.execute("TRUNCATE borrador_importacion, uso_ia, importacion, formato_importacion, carpeta, base, terreno, incidencia, mapa, mapa_capa, mapa_terreno, pending_import, workspace_backup RESTART IDENTITY CASCADE")
        self.result = read_workbook(FIXTURE)
        self.findings = validate_all(self.result.records)

    def seed(self, name="Test base"):
        with db.session() as conn:
            base_id = bases.create(conn, name, "test.xlsx", self.result.hoja)
            terrenos.insert(conn, base_id, self.result.records, self.findings)
        return base_id

    def test_snapshots_rename_refresh_and_delete(self):
        base_id = self.seed()
        with db.session() as conn:
            self.assertEqual(bases.get(conn, base_id)["conteo"], len(self.result.records))
            map_id = mapas.create(conn, "Test base", "simple", [{"base_id": base_id, "color": "#abcdef", "visible": True}], sigue_base=True)
        with db.session() as conn:
            bases.rename(conn, base_id, "Renamed")
            self.assertEqual(mapas.get(conn, map_id)["nombre"], "Renamed")
            mapas.refresh_snapshot(conn, map_id)
            mapas.update(conn, map_id, config={"zoom": 9})
        with db.session() as conn:
            self.assertEqual(mapas.get(conn, map_id)["config"], {"zoom": 9})
            bases.delete(conn, base_id)
        with db.session() as conn:
            self.assertEqual(len(mapas.terrenos(conn, map_id)), len(self.result.records))
            self.assertFalse(mapas.get(conn, map_id)["capas"][0]["base_existe"])

    def test_cross_instance_import_and_single_use_token(self):
        pending = Staging().put("test.xlsx", "Cloud import", self.result, self.findings)
        loaded = Staging().take(pending.token)
        self.assertEqual(loaded.resultado, self.result)
        self.assertEqual(loaded.incidencias, {k: tuple(v) for k, v in self.findings.items()})
        self.assertIsNone(Staging().take(pending.token))
        pending = Staging().put("test.xlsx", "Cloud import", self.result, self.findings)
        response = importar.confirm(Request(method="POST", path="/api/importar/confirmar", query={}, params={}, body=json.dumps({"token": pending.token}).encode(), headers={}))
        with db.session() as conn:
            self.assertEqual(bases.get(conn, response["base"]["id"])["conteo"], len(self.result.records))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM workspace_backup").fetchone()[0], 1)

    def test_csv_preview_confirm_through_postgres_staging(self):
        body = (b"Terreno,Estado,Municipio,Afectaciones %,X,Y,Vendedor\n"
                b"Predio Nube,Jalisco,Tala,10%,20.653,-103.701,Fulano\n"
                b"Predio Raro,Jalisco,Tala,,\"19,4326\",-99,\n")
        preview = importar.preview(Request(method="POST", path="/api/importar/vista-previa",
                                           query={"csv_decimal": ["dot"]}, params={}, body=body,
                                           headers={"X-Archivo": "nube.csv"}))
        with db.session() as conn:
            self.assertEqual(bases.listing(conn), [])
        response = importar.confirm(Request(method="POST", path="/api/importar/confirmar", query={}, params={},
                                            body=json.dumps({"token": preview["token"]}).encode(), headers={}))
        with db.session() as conn:
            base = bases.get(conn, response["base"]["id"])
            self.assertEqual((base["conteo"], base["ubicados"], base["hoja"]), (2, 1, "CSV"))
            rows = {r["terreno"]: r for r in terrenos.for_base(conn, base["id"])}
        self.assertAlmostEqual(rows["Predio Nube"]["afectaciones_pct"], 0.10)
        self.assertEqual(rows["Predio Nube"]["extra"], {"Vendedor": "Fulano"})
        self.assertIsNone(rows["Predio Raro"]["lat"])

    def test_folders_move_delete_and_backup(self):
        from server.api import carpetas as api_carpetas
        from server.repo import carpetas as repo_carpetas
        from server.web_util import ApiError

        def call(handler, **kwargs):
            body = json.dumps(kwargs.pop("json_body")).encode() if "json_body" in kwargs else b""
            return handler(Request(method="POST", path="/x", query=kwargs.pop("query", {}),
                                   params=kwargs.pop("params", {}), body=body, headers={}))

        base_id = self.seed()
        carpeta = call(api_carpetas.create, json_body={"tipo": "bases", "nombre": "Nube Norte"})["carpeta"]
        with self.assertRaises(ApiError) as caught:
            call(api_carpetas.create, json_body={"tipo": "bases", "nombre": "nube  NORTE"})
        self.assertEqual(caught.exception.status, 409)
        with db.session() as conn:
            self.assertTrue(repo_carpetas.assign(conn, "bases", base_id, carpeta["id"]))
        listado = call(api_carpetas.listing, query={"tipo": ["bases"]})
        self.assertEqual((listado["carpetas"][0]["conteo"], listado["sin_carpeta"]), (1, 0))

        postgres.backup()
        with db.session() as conn:
            payload = json.loads(conn.execute("SELECT payload FROM workspace_backup ORDER BY id DESC LIMIT 1").fetchone()["payload"])
        self.assertEqual(payload["carpeta"][0]["nombre"], "Nube Norte")
        self.assertEqual(payload["base"][0]["carpeta_id"], carpeta["id"])

        out = call(api_carpetas.remove, params={"id": str(carpeta["id"])})
        self.assertEqual(out["trasladados"], 1)
        with db.session() as conn:
            self.assertIsNone(bases.get(conn, base_id)["carpeta_id"])
            self.assertEqual(bases.get(conn, base_id)["conteo"], len(self.result.records))

    def test_upgrading_a_workspace_from_before_folders(self):
        import re

        import psycopg
        from psycopg.conninfo import make_conninfo

        from tests.test_carpetas_migration import SCHEMA_V4
        schema = "test_ara_old_" + uuid.uuid4().hex
        with psycopg.connect(self.url) as conn:
            conn.execute(f'CREATE SCHEMA "{schema}"')
        try:
            url = make_conninfo(self.url, options=f"-c search_path={schema}")
            with patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": url}):
                with postgres.session() as conn:
                    conn.raw.execute(postgres._to_postgres(SCHEMA_V4), prepare=False)
                    conn.execute("INSERT INTO base (nombre, importado_en) VALUES ('Vieja', 't')")
                    conn.execute("INSERT INTO mapa (nombre, tipo, creado_en, actualizado_en) VALUES ('M', 'simple', 't', 't2')")
                    self.assertIsNone(postgres.schema_version(conn))
                for _ in range(2):  # idempotent
                    with postgres.session() as conn:
                        postgres.migrate(conn)
                with postgres.session() as conn:
                    self.assertEqual(postgres.schema_version(conn), db.SCHEMA_VERSION)
                    base = conn.execute("SELECT nombre, carpeta_id FROM base").fetchone()
                    mapa = conn.execute("SELECT actualizado_en, carpeta_id FROM mapa").fetchone()
                self.assertEqual((base["nombre"], base["carpeta_id"]), ("Vieja", None))
                self.assertEqual((mapa["actualizado_en"], mapa["carpeta_id"]), ("t2", None))
                self.assertTrue(re.search(r"carpeta", postgres.migrate_sql()))
        finally:
            with psycopg.connect(self.url) as conn:
                conn.execute(f'DROP SCHEMA "{schema}" CASCADE')

    def test_assistant_drafts_formats_and_usage(self):
        from server.asistente.borradores import Borradores, RevisionObsoleta
        from server.repo import formatos
        store = Borradores()
        borrador = store.crear("rejilla-empaquetada", {"decisiones": {}})
        self.assertEqual(store.leer(borrador.token).estado, {"decisiones": {}})
        self.assertEqual(store.guardar(borrador.token, 0, {"decisiones": {"decimal": "dot"}}), 1)
        with self.assertRaises(RevisionObsoleta):
            store.guardar(borrador.token, 0, {})
        store.borrar(borrador.token)
        self.assertIsNone(store.leer(borrador.token))
        with db.session() as conn:
            primero = formatos.recordar(conn, "F", [["terreno", 1]], {"asignaciones": [["terreno", 1, "terreno"]]}, 1)
            igual = formatos.recordar(conn, "F", [["terreno", 1]], {"asignaciones": [["terreno", 1, "terreno"]]}, 1)
            otro = formatos.recordar(conn, "F", [["terreno", 1]], {"asignaciones": [["terreno", 1, "extra"]]}, 1)
            self.assertEqual((primero[2], igual[2], otro[2]), ("nuevo", "reutilizado", "nueva_version"))
            self.assertEqual(len(formatos.activos(conn)), 1)

    def test_currency_and_row_decisions_survive_a_serialized_draft(self):
        """A draft crosses workers as text: its evidence and decisions ride along."""
        from server.api import asistente as api_asistente
        from tests.test_asistente_monedas import en_dolares

        libro = api_asistente.analizar(self._peticion(en_dolares(), {"X-Archivo": "dolares.xlsx"}))
        # Every later request re-reads the draft from Postgres, not from memory.
        seguido = api_asistente.preparar(self._peticion(json_body={
            "borrador": libro["borrador"], "revision": libro["revision"],
            "correcciones": {"decimal": "comma"}}))
        self.assertEqual((seguido["vista_previa"]["con_precio"], seguido["vista_previa"]["moneda"]), (4, "USD"))
        importar.confirm(self._peticion(json_body={"token": seguido["vista_previa"]["token"],
                                                   "nombre": "Dolares", "recordar_formato": False}))

        nota = (b"Terreno,Precio MXN,Superficie m2,Latitud,Longitud\n"
                b"FICTICIO Encino,1200000,2400,19.4326,-99.1332\n"
                b"NOTA: valores sujetos a revision,,,,\n")
        r = api_asistente.analizar(self._peticion(nota, {"X-Archivo": "nota.csv"}))
        self.assertEqual(r["vista_previa"]["excluidas"][0]["motivo"], "NOTA")
        indice = r["vista_previa"]["excluidas"][0]["indice"]
        restaurada = api_asistente.preparar(self._peticion(json_body={
            "borrador": r["borrador"], "revision": r["revision"], "correcciones": {"incluir": [indice]}}))
        self.assertEqual(restaurada["vista_previa"]["conteo"], 2)
        importar.confirm(self._peticion(json_body={"token": restaurada["vista_previa"]["token"],
                                                   "nombre": "Nota", "recordar_formato": False}))
        with db.session() as conn:
            filas = conn.execute("SELECT terreno, asking_price, moneda FROM terreno ORDER BY id").fetchall()
        self.assertEqual([(f["terreno"], f["asking_price"], f["moneda"]) for f in filas],
                         [("FICTICIO Encino", 1200000.0, "USD"), ("FICTICIO Roble", 2500000.0, "USD"),
                          ("FICTICIO Cedro", 3750000.0, "USD"), ("FICTICIO Fresno", 4800000.0, "USD"),
                          ("FICTICIO Encino", 1200000.0, "MXN"),
                          ("NOTA: valores sujetos a revision", None, None)])

    def _peticion(self, body=b"", headers=None, params=None, query=None, json_body=None):
        if json_body is not None:
            body = json.dumps(json_body).encode()
        return Request(method="POST", path="/x", query=query or {}, params=params or {},
                       body=body, headers=headers or {})

    def test_late_confirmation_after_a_corrected_import_is_refused(self):
        """Supervisor R2a ordering on real Postgres: every request has its own connection."""
        from server.api import asistente as api_asistente
        from server.web_util import ApiError
        viejo = api_asistente.analizar(self._peticion(b"Terreno,Precio MXN\nNorte,1000000\n", {"X-Archivo": "c.csv"}))
        col = viejo["interpretacion"]["columnas"][1]["id"]
        original = importar._vigente

        def intercalar(pending):
            nuevo = api_asistente.preparar(self._peticion(json_body={
                "borrador": viejo["borrador"], "revision": viejo["revision"],
                "correcciones": {"columnas": {col: "extra"}}}))
            with patch.object(importar, "_vigente", original):
                importar.confirm(self._peticion(json_body={"token": nuevo["vista_previa"]["token"]}))
            original(pending)

        with patch.object(importar, "_vigente", side_effect=intercalar), self.assertRaises(ApiError) as caught:
            importar.confirm(self._peticion(json_body={"token": viejo["vista_previa"]["token"]}))
        self.assertIn(caught.exception.status, (409, 410))
        with db.session() as conn:
            precios = [r["asking_price"] for r in conn.execute("SELECT asking_price FROM terreno").fetchall()]
        self.assertEqual(precios, [None])

    def test_failed_commit_cleanup_does_not_wait_for_the_workspace_lock(self):
        """Supervisor R2b: cleanup runs after the business session released the lock."""
        import time as reloj

        from server.api import asistente as api_asistente
        from server.asistente.borradores import borradores
        r = api_asistente.analizar(self._peticion(b"Terreno,Precio MXN\nNorte,1000000\n", {"X-Archivo": "c.csv"}))
        inicio = reloj.monotonic()
        with patch.object(importar.repo_terrenos, "insert", side_effect=RuntimeError("injected write failure")), \
                self.assertRaisesRegex(RuntimeError, "injected write failure"):
            importar.confirm(self._peticion(json_body={"token": r["vista_previa"]["token"]}))
        self.assertLess(reloj.monotonic() - inicio, 10, "cleanup waited on the workspace lock")
        self.assertIsNone(borradores.leer(r["borrador"]))
        with db.session() as conn:
            for tabla in ("base", "terreno", "formato_importacion", "importacion"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"], 0, tabla)

    def test_rollback_and_concurrent_ids(self):
        with self.assertRaises(RuntimeError), db.session() as conn:
            bases.create(conn, "Must rollback", None, None)
            raise RuntimeError("rollback")
        with db.session() as conn:
            self.assertEqual(bases.listing(conn), [])
        def create_base(name):
            with db.session() as conn:
                return bases.create(conn, name, None, None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(create_base, ["A", "B", "C", "D"]))
        self.assertEqual(len(set(ids)), 4)
        with db.session() as conn:
            self.assertEqual(len(bases.listing(conn)), 4)

    def test_empty_base_counts(self):
        with db.session() as conn:
            base_id = bases.create(conn, "Empty", None, None)
            row = bases.get(conn, base_id)
            self.assertEqual((row["conteo"], row["sin_coordenadas"], row["ubicados"]), (0, 0, 0))

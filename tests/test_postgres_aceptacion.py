"""Cloud-path acceptance on a real, disposable Postgres (SUPERVISOR_REVIEW_03.md).

Runs only when ARA_MAP_TEST_DATABASE_URL is set; each class works in its own
uniquely named schema and drops it afterwards. Never points at production.

    ARA_MAP_TEST_DATABASE_URL=postgresql://... python -m unittest tests.test_postgres_aceptacion -v
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import db, postgres
from server.api import asistente as api_asistente
from server.api import importar
from server.asistente import ia
from server.asistente.borradores import borradores
from server.repo import bases
from server.router import Request
from server.web_util import ApiError

RAIZ = Path(__file__).resolve().parents[1]
URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
# An explicit currency, so these tests about ordering and failures need no
# currency question.
CSV = b"Terreno,Precio MXN\nNorte,1000000\n"
TABLAS_NEGOCIO = ("carpeta", "base", "terreno", "incidencia", "mapa", "mapa_capa", "mapa_terreno",
                  "formato_importacion", "importacion")


def peticion(body=b"", headers=None, params=None, query=None, json_body=None):
    if json_body is not None:
        body = json.dumps(json_body).encode()
    return Request(method="POST", path="/x", query=query or {}, params=params or {},
                   body=body, headers=headers or {})


def con_esquema(esquema: str) -> str:
    from psycopg.conninfo import make_conninfo
    return make_conninfo(URL, options=f"-c search_path={esquema}")


@unittest.skipUnless(URL, "No disposable Postgres configured (ARA_MAP_TEST_DATABASE_URL)")
class EsquemaDesechable(unittest.TestCase):
    """A fresh, current schema per class; every business table emptied per test."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.esquema = "test_ara_acept_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.esquema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": con_esquema(cls.esquema),
                                          "ARA_MAP_IA_PROVEEDOR": ""})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.esquema}" CASCADE')

    def setUp(self):
        with postgres.session() as conn:
            conn.raw.execute("TRUNCATE borrador_importacion, uso_ia, pending_import, workspace_backup, "
                             + ", ".join(TABLAS_NEGOCIO) + " RESTART IDENTITY CASCADE")
        self.addCleanup(ia.fijar_proveedor, None)

    def contar(self, tabla):
        with db.session() as conn:
            return conn.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"]

    def analizar(self, contenido=CSV, base_id=None):
        return api_asistente.analizar(peticion(contenido, {"X-Archivo": "c.csv"},
                                               query={"base_id": [str(base_id)]} if base_id else {}))

    def preparar(self, r, correcciones):
        return api_asistente.preparar(peticion(json_body={
            "borrador": r["borrador"], "revision": r["revision"], "correcciones": correcciones}))

    def nueva_base(self, nombre="Destino"):
        with db.session() as conn:
            return bases.create(conn, nombre, None, None)


class ConfirmacionTardia(EsquemaDesechable):
    """R2a ordering, each request on its own connection, new base and append."""

    def ordenar(self, commit, base_id=None):
        viejo = self.analizar(base_id=base_id)
        col = viejo["interpretacion"]["columnas"][1]["id"]
        original = importar._vigente

        def intercalar(pending):
            nuevo = self.preparar(viejo, {"columnas": {col: "extra"}})
            with patch.object(importar, "_vigente", original):
                commit(nuevo)
            original(pending)

        with patch.object(importar, "_vigente", side_effect=intercalar), self.assertRaises(ApiError) as caught:
            commit(viejo)
        self.assertIn(caught.exception.status, (409, 410))
        with db.session() as conn:
            precios = [r["asking_price"] for r in conn.execute("SELECT asking_price FROM terreno").fetchall()]
        self.assertEqual(precios, [None])

    def test_new_base(self):
        self.ordenar(lambda r: importar.confirm(peticion(json_body={"token": r["vista_previa"]["token"],
                                                                     "recordar_formato": False})))
        self.assertEqual(self.contar("base"), 1)

    def test_append(self):
        base_id = self.nueva_base()
        self.ordenar(lambda r: importar.append(peticion(params={"id": base_id}, json_body={
            "token": r["vista_previa"]["token"], "recordar_formato": False,
            "resoluciones": {"0": "actualizar"}})), base_id=base_id)
        self.assertEqual(self.contar("base"), 1)

    def test_threaded_confirm_and_correction_on_separate_connections(self):
        for _ in range(10):
            r = self.analizar()
            col = r["interpretacion"]["columnas"][1]["id"]
            salida, barrera = {}, threading.Barrier(2)

            def confirmar(r=r, salida=salida, barrera=barrera):
                barrera.wait()
                try:
                    salida["confirmada"] = importar.confirm(peticion(json_body={
                        "token": r["vista_previa"]["token"], "recordar_formato": False}))
                except ApiError as error:
                    salida["confirmada_error"] = error.status

            def corregir(r=r, col=col, salida=salida, barrera=barrera):
                barrera.wait()
                try:
                    salida["corregida"] = self.preparar(r, {"columnas": {col: "extra"}})
                except ApiError as error:
                    salida["corregida_error"] = error.status

            hilos = [threading.Thread(target=confirmar), threading.Thread(target=corregir)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
            self.assertFalse("confirmada" in salida and "corregida" in salida, salida)
            self.assertTrue("confirmada" in salida or "corregida" in salida, salida)


class FallasSinResiduos(EsquemaDesechable):
    """Injected failures: nothing partial, prompt cleanup, and the workspace keeps working."""

    def fallar_y_seguir(self, commit, falla, base_id=None):
        r = self.analizar(base_id=base_id)
        inicio = time.monotonic()
        with falla, self.assertRaisesRegex(RuntimeError, "injected"):
            commit(r, recordar=True)
        self.assertLess(time.monotonic() - inicio, 10, "cleanup waited on the workspace lock")
        self.assertIsNone(borradores.leer(r["borrador"]))
        self.assertEqual((self.contar("terreno"), self.contar("formato_importacion"), self.contar("importacion")),
                         (0, 0, 0))
        # The workspace is not left locked or dirty: the next import goes through.
        salida = commit(self.analizar(base_id=base_id), recordar=True)
        self.assertEqual(self.contar("terreno"), 1)
        self.assertEqual((self.contar("formato_importacion"), self.contar("importacion")), (1, 1))
        return salida

    def fallas(self):
        return {
            "escritura": lambda: patch.object(importar.repo_terrenos, "insert",
                                              side_effect=RuntimeError("injected write")),
            "procedencia": lambda: patch.object(importar.repo_formatos, "registrar_importacion",
                                                side_effect=RuntimeError("injected provenance")),
            "respaldo": lambda: patch.object(importar.db, "backup", side_effect=RuntimeError("injected backup")),
        }

    def test_new_base(self):
        def commit(r, recordar):
            return importar.confirm(peticion(json_body={"token": r["vista_previa"]["token"],
                                                        "recordar_formato": recordar}))
        for nombre, falla in self.fallas().items():
            with self.subTest(falla=nombre):
                self.setUp()
                self.fallar_y_seguir(commit, falla())
                self.assertEqual(self.contar("base"), 1)

    def test_append(self):
        for nombre, falla in self.fallas().items():
            with self.subTest(falla=nombre):
                self.setUp()
                base_id = self.nueva_base()

                def commit(r, recordar, base_id=base_id):
                    return importar.append(peticion(params={"id": base_id}, json_body={
                        "token": r["vista_previa"]["token"], "recordar_formato": recordar}))
                self.fallar_y_seguir(commit, falla(), base_id=base_id)


class PresupuestoEntreConexiones(EsquemaDesechable):
    """Reservations serialized by Postgres alone: the in-process lock is removed."""

    def setUp(self):
        super().setUp()
        entorno = {"ARA_MAP_IA_PROVEEDOR": "openai", "ARA_MAP_IA_MODELO": "prueba", "ARA_MAP_IA_CLAVE": "x",
                   "ARA_MAP_IA_COSTO_ENTRADA_USD_MTOK": "1", "ARA_MAP_IA_COSTO_SALIDA_USD_MTOK": "4",
                   "ARA_MAP_IA_LIMITE_MENSUAL_USD": "5"}
        parche = patch.dict(os.environ, entorno)
        parche.start()
        self.addCleanup(parche.stop)
        sin_candado = patch.object(ia, "_reserva_lock", contextlib.nullcontext())
        sin_candado.start()
        self.addCleanup(sin_candado.stop)
        from tests.test_asistente_ia import interpretacion
        self.interp, self.pendientes = interpretacion()
        config = ia.configuracion()[0]
        usuario = json.dumps(ia.solicitud(self.interp.columnas, self.interp.asignaciones, self.pendientes, config),
                             ensure_ascii=False)
        ids = [c.id for c in self.interp.columnas if c.id in self.pendientes]
        libres = [k for k in ia.C.CAMPOS if k not in set(self.interp.asignaciones.values())]
        self.maximo = ia.costo_maximo(ia.SISTEMA, usuario, config, ia.esquema(ids, libres))

    def gasto(self):
        with db.session() as conn:
            return float(conn.execute("SELECT COALESCE(SUM(costo_usd), 0) AS s FROM uso_ia").fetchone()["s"])

    def test_concurrent_callers_cannot_share_the_last_of_the_budget(self):
        rechazadas = threading.Semaphore(0)
        llamadas = []

        class EnVuelo:
            nombre = "en-vuelo"

            def sugerir(self, *args):
                llamadas.append(1)
                for _ in range(5):
                    rechazadas.acquire(timeout=15)
                return ia.Respuesta({"asignaciones": [], "advertencias": []}, None, None)

        ia.fijar_proveedor(EnVuelo())
        estados, barrera = [], threading.Barrier(6)

        def llamar():
            barrera.wait()
            estado = ia.sugerir(self.interp.columnas, self.interp.asignaciones, self.pendientes).estado
            estados.append(estado)
            if estado != "ok_uso_desconocido" and estado != "ok":
                rechazadas.release()

        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": str(self.maximo * 1.5)}):
            hilos = [threading.Thread(target=llamar) for _ in range(6)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
        self.assertEqual(len(llamadas), 1, estados)
        self.assertEqual(sorted(estados), ["ok"] + ["presupuesto"] * 5)
        # Unknown usage settled at the full reservation, persisted in Postgres.
        self.assertAlmostEqual(self.gasto(), self.maximo)
        with db.session() as conn:
            self.assertEqual(conn.execute("SELECT estado FROM uso_ia").fetchone()["estado"], "ok_uso_desconocido")

    def test_known_usage_replaces_the_reservation(self):
        ia.fijar_proveedor(type("P", (), {"nombre": "p", "sugerir": lambda self, *a: ia.Respuesta(
            {"asignaciones": [], "advertencias": []}, 1000, 100)})())
        self.assertEqual(ia.sugerir(self.interp.columnas, self.interp.asignaciones, self.pendientes).estado, "ok")
        self.assertAlmostEqual(self.gasto(), (1000 * 1 + 100 * 4) / 1e6)


@unittest.skipUnless(URL, "No disposable Postgres configured (ARA_MAP_TEST_DATABASE_URL)")
class MigracionDesdeEspacioExistente(unittest.TestCase):
    """The real migration script against a folder-enabled (v5) workspace with data."""

    def setUp(self):
        import psycopg

        from tests.test_asistente_migracion import SCHEMA_V5
        self.esquema = "test_ara_v5_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{self.esquema}"')
        self.url = con_esquema(self.esquema)
        extras = """
            CREATE TABLE pending_import (token TEXT PRIMARY KEY, payload TEXT NOT NULL, created DOUBLE PRECISION NOT NULL);
            CREATE TABLE workspace_backup (id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              created TIMESTAMPTZ NOT NULL DEFAULT now(), payload TEXT NOT NULL);
            CREATE TABLE workspace_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO workspace_metadata VALUES ('seeded', 't'), ('schema_version', '5');
        """
        datos = """
            INSERT INTO carpeta (id, tipo, nombre, nombre_clave, creado_en, actualizado_en)
              VALUES (1, 'bases', 'Clientes', 'clientes', 't', 't'), (2, 'mapas', 'Informes', 'informes', 't', 't');
            INSERT INTO base (id, nombre, importado_en, carpeta_id) VALUES (1, 'Agosto', 't', 1), (2, 'Suelta', 't', NULL);
            INSERT INTO terreno (id, base_id, orden, terreno, lat, lon, asking_price, clave_dedupe, extra_json)
              VALUES (1, 1, 1, 'Norte', 19.5, -99.1, 1000000, 'norte', '{"Vendedor": "X"}'),
                     (2, 2, 1, 'Sur', NULL, NULL, NULL, 'sur', NULL);
            INSERT INTO incidencia (terreno_id, severidad, codigo, mensaje) VALUES (2, 'aviso', 'SIN_COORDENADAS', 'x');
            INSERT INTO mapa (id, nombre, tipo, creado_en, actualizado_en, config_json, nombre_sigue_base, carpeta_id)
              VALUES (1, 'Agosto', 'simple', 't', 't2', '{"basemap": "satelite"}', 1, 2);
            INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre, color) VALUES (1, 0, 1, 'Agosto', '#111');
            INSERT INTO mapa_terreno (mapa_id, capa_orden, terreno_id, orden, terreno, lat, clave_dedupe)
              VALUES (1, 0, 1, 1, 'Norte', 19.5, 'norte');
        """
        # Explicit ids, then sequences advanced past them -- exactly what
        # setup_cloud.py does when it seeds a workspace.
        secuencias = "".join(
            f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT MAX(id) FROM {t}));"
            for t in ("carpeta", "base", "terreno", "mapa"))
        with psycopg.connect(self.url) as conn:
            conn.execute(postgres._to_postgres(SCHEMA_V5), prepare=False)
            conn.execute(db.FOLDER_INDEXES, prepare=False)
            conn.execute(extras, prepare=False)
            conn.execute(datos, prepare=False)
            conn.execute(secuencias, prepare=False)

    def tearDown(self):
        import psycopg
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{self.esquema}" CASCADE')

    def volcar(self):
        """Every row's content, without the currency column the upgrade adds
        (checked separately: it must arrive empty, never guessed)."""
        import psycopg
        tablas = ("carpeta", "base", "terreno", "incidencia", "mapa", "mapa_capa", "mapa_terreno")
        volcado = {}
        with psycopg.connect(self.url) as conn:
            for t in tablas:
                cursor = conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2")
                columnas = [d.name for d in cursor.description]
                volcado[t] = [tuple(v for c, v in zip(columnas, r) if c != "moneda") for r in cursor.fetchall()]
        return volcado

    def script(self, *args):
        entorno = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "ARA_MAP_DATABASE_URL")}
        entorno["ARA_MAP_ACEPTACION_URL"] = self.url
        return subprocess.run([sys.executable, "scripts/migrate_cloud.py", "--url-env", "ARA_MAP_ACEPTACION_URL",
                               *args], cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120)

    def test_upgrade_preserves_everything_reaches_current_and_can_run_again(self):
        antes = self.volcar()
        self.assertEqual(self.script("--check").returncode, 1)          # v5: not yet current
        for _ in range(2):
            salida = self.script()
            self.assertEqual(salida.returncode, 0, salida.stderr)
            self.assertIn(f"version {db.SCHEMA_VERSION}", salida.stdout)
        self.assertEqual(self.volcar(), antes)
        import psycopg
        with psycopg.connect(self.url) as conn:
            for tabla in ("terreno", "mapa_terreno"):
                # Existing prices and snapshots are never stamped with a currency.
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE moneda IS NOT NULL")
                                 .fetchone()[0], 0, tabla)
            with self.assertRaises(psycopg.errors.CheckViolation):
                conn.execute("UPDATE terreno SET moneda = 'EUR' WHERE id = 1")
        self.assertEqual(self.script("--check").returncode, 0)
        import psycopg
        with psycopg.connect(self.url) as conn:
            nuevas = {r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (self.esquema,))}
            respaldos = conn.execute("SELECT payload FROM workspace_backup ORDER BY id").fetchall()
        self.assertTrue({"formato_importacion", "importacion", "uso_ia", "borrador_importacion"} <= nuevas)
        # A backup was taken before each run, and the first holds the pre-upgrade data.
        self.assertEqual(len(respaldos), 2)
        primero = json.loads(respaldos[0][0])
        self.assertEqual([b["nombre"] for b in primero["base"]], ["Agosto", "Suelta"])
        self.assertEqual(primero["carpeta"][0]["nombre"], "Clientes")

    def test_the_upgraded_workspace_is_usable(self):
        self.assertEqual(self.script().returncode, 0)
        with patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": self.url, "ARA_MAP_IA_PROVEEDOR": ""}):
            r = api_asistente.analizar(peticion(CSV, {"X-Archivo": "c.csv"}))
            base = importar.confirm(peticion(json_body={"token": r["vista_previa"]["token"]}))["base"]
            self.assertEqual(base["conteo"], 1)
            with db.session() as conn:
                self.assertEqual(conn.execute("SELECT carpeta_id FROM base WHERE id = 1").fetchone()["carpeta_id"], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM formato_importacion").fetchone()["n"], 1)


class ComparacionesEnLaNube(EsquemaDesechable):
    """Found by running the browser suite on Postgres: merges must keep distinct layers."""

    def test_merging_two_different_saved_maps_keeps_both_layers(self):
        from server.api import mapas as api_mapas
        from tests.support import FIXTURE
        ids = []
        for archivo, nombre in ((FIXTURE.with_name("base_terrenos_08_26_sintetica.xlsx"), "Agosto"),
                                (FIXTURE, "Septiembre")):
            p = importar.preview(peticion(archivo.read_bytes(), {"X-Archivo": "f.xlsx"}))
            ids.append(importar.confirm(peticion(json_body={"token": p["token"], "nombre": nombre}))["base"]["id"])
        mapas_ids = [api_mapas.create(peticion(json_body={
            "nombre": f"M{i}", "tipo": "simple", "capas": [{"base_id": b, "color": "#111111"}]}))["mapa"]["id"]
            for i, b in enumerate(ids)]
        plan = api_mapas.plan_merge(peticion(json_body={"mapa_ids": mapas_ids}))
        self.assertEqual((plan["total"], plan["duplicadas"]), (2, []))
        mapa = api_mapas.merge(peticion(json_body={"nombre": "Comparación", "mapa_ids": mapas_ids}))["mapa"]
        self.assertEqual([c["base_nombre"] for c in mapa["capas"]], ["Agosto", "Septiembre"])
        # A genuinely identical snapshot is still recognized as a duplicate.
        otra = api_mapas.create(peticion(json_body={
            "nombre": "Otra vez", "tipo": "simple", "capas": [{"base_id": ids[0], "color": "#111111"}]}))["mapa"]["id"]
        plan = api_mapas.plan_merge(peticion(json_body={"mapa_ids": [mapas_ids[0], otra]}))
        self.assertEqual((plan["total"], len(plan["duplicadas"])), (1, 1))

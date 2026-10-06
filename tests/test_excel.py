"""Connected workbooks, local fixture category: real HTTP handler, throwaway
SQLite, fictional generated workbooks and an in-memory provider in place of
OneDrive. These tests do NOT exercise Microsoft; see test_excel_postgres.py
for the Postgres engine and the release report for hosted/real evidence.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from unittest.mock import patch

from server import db
from server.api import excel as api_excel
from server.excel import lectura
from server.excel.proveedor import ProveedorError
from server.repo import excel as repo
from server.repo import terrenos as repo_terrenos
from tests.excel_support import BASICO, ENCABEZADO, Drive, crear_cuenta, fila, libro
from tests.test_inventario import InventoryServer

CONFIG = {"hoja": "Registro Análisis", "columna_id": "ID", "moneda": "USD"}


class ExcelServer(InventoryServer):
    def setUp(self):
        super().setUp()
        self.drive = Drive()
        patcher = patch.object(api_excel, "FABRICA", self.drive)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cuenta = crear_cuenta(self.conn, self.users["ana"]["id"])
        self.archivo = self.drive.agregar("item-1", libro(BASICO))

    def key(self):
        return {"Idempotency-Key": f"k-{uuid.uuid4()}"}

    def conectar(self, item="item-1", headers=None, **cambios):
        body = {"cuenta_id": self.cuenta, "drive_id": "drive-ficticio", "item_id": item,
                "nombre": "Terrenos conectados", **CONFIG, **cambios}
        return self.call("POST", "/api/excel/fuentes", body, headers=headers or self.key())

    def fuente(self):
        status, body = self.conectar()
        self.assertEqual(status, 200, body)
        return body["fuente"]

    def actualizar(self, fid, user="ana", headers=None, **body):
        return self.call("POST", f"/api/excel/fuentes/{fid}/actualizar", body, user,
                         headers=headers or self.key())

    def terrenos(self, base_id):
        return {t["terreno"]: t for t in self.call("GET", f"/api/bases/{base_id}/terrenos")[1]["terrenos"]}

    def identidad(self, fid, clave):
        return self.conn.execute("SELECT * FROM excel_identidad WHERE fuente_id = ? AND clave = ?",
                                 (fid, clave)).fetchone()


class FirstConnection(ExcelServer):
    def test_preview_then_connect_creates_one_live_base(self):
        status, prev = self.call("POST", "/api/excel/vista-previa",
                                 {"cuenta_id": self.cuenta, "drive_id": "drive-ficticio", "item_id": "item-1"})
        self.assertEqual(status, 200, prev)
        self.assertEqual((prev["hoja"], prev["filas"], prev["id_sugerido"]), ("Registro Análisis", 3, "ID"))
        self.assertTrue(next(c for c in prev["columnas"] if c["encabezado"] == "ID")["puede_ser_id"])
        self.assertFalse(next(c for c in prev["columnas"] if c["encabezado"] == "Estado")["puede_ser_id"])

        f = self.fuente()
        self.assertEqual((f["estado"], f["version_activa"]["numero"], f["version_activa"]["filas"]),
                         ("activa", 1, 3))
        self.assertEqual(f["configuracion"]["columna_id"], "ID")
        self.assertEqual(f["cuenta"]["conectada_por"]["display_name"], "Ana")
        self.assertEqual(f["ultima_ejecucion"]["conteos"],
                         {"agregados": 3, "actualizados": 0, "eliminados": 0, "sin_cambio": 0})
        live = self.terrenos(f["base_id"])
        self.assertEqual(set(live), {"Lote Alfa", "Lote Beta", "Lote Gamma"})
        self.assertEqual({t["moneda"] for t in live.values()}, {"USD"})
        # The exact text ID, leading zeros kept.
        self.assertIsNotNone(self.identidad(f["id"], "007"))
        self.assertIsNone(self.identidad(f["id"], "7"))
        self.assertEqual(len(self.call("GET", "/api/bases")[1]["bases"]), 1)

    def test_anonymous_gets_nothing(self):
        f = self.fuente()
        for method, path in (("GET", "/api/excel/fuentes"), ("GET", f"/api/excel/fuentes/{f['id']}"),
                             ("POST", f"/api/excel/fuentes/{f['id']}/actualizar"),
                             ("POST", "/api/excel/fuentes"), ("POST", "/api/excel/vista-previa")):
            status, body = self.call(method, path, {}, None, headers=self.key())
            self.assertEqual((status, body["detalle"]["code"]), (401, "unauthenticated"), path)

    def test_invalid_data_creates_nothing(self):
        self.drive.agregar("malo", libro([fila("A", "Uno"), fila("A", "Dos")]))
        status, body = self.conectar(item="malo")
        self.assertEqual((status, body["detalle"]["code"]), (422, "datos_invalidos"))
        self.assertEqual(body["detalle"]["problemas"][0]["codigo"], "id_duplicado")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM excel_fuente").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM base").fetchone()[0], 0)

    def test_one_workbook_one_source(self):
        self.fuente()
        status, body = self.conectar(nombre="Otra")
        self.assertEqual((status, body["detalle"]["code"]), (409, "ya_conectada"))


class Refresh(ExcelServer):
    def test_saved_edit_updates_in_place_with_counts(self):
        f = self.fuente()
        antes = self.terrenos(f["base_id"])
        self.archivo.poner(libro([fila("A-001", "Lote Alfa", 1_500_000), fila("A-002", "Lote Beta", 2_000_000),
                                  fila("A-003", "Lote Delta", 4_000_000)]))
        status, r = self.actualizar(f["id"], "beto")
        self.assertEqual(status, 200, r)
        self.assertEqual(r["ejecucion"]["estado"], "ok")
        self.assertEqual(r["ejecucion"]["iniciada_por"], self.users["beto"]["id"])
        self.assertEqual(r["ejecucion"]["conteos"],
                         {"agregados": 1, "actualizados": 1, "eliminados": 1, "sin_cambio": 1})
        despues = self.terrenos(f["base_id"])
        self.assertEqual(despues["Lote Alfa"]["id"], antes["Lote Alfa"]["id"])  # same terrain row
        self.assertEqual(despues["Lote Alfa"]["asking_price"], 1_500_000)
        self.assertNotIn("Lote Gamma", despues)
        self.assertEqual(len(self.call("GET", "/api/bases")[1]["bases"]), 1)  # no new base
        self.assertEqual(r["fuente"]["version_activa"]["numero"], 2)

    def test_stable_identity_reorder_insert_rename_remove_readd(self):
        f = self.fuente()
        ids = {t["terreno"]: t["id"] for t in self.terrenos(f["base_id"]).values()}
        alfa = self.identidad(f["id"], "A-001")["id"]
        # Reorder, insert before an existing row, rename one terrain.
        self.archivo.poner(libro([fila("N-1", "Nuevo primero"), fila("007", "Lote Gamma", 3_000_000),
                                  fila("A-002", "Lote Beta renombrado", 2_000_000), fila("A-001", "Lote Alfa")]))
        r = self.actualizar(f["id"])[1]
        self.assertEqual(r["ejecucion"]["conteos"],
                         {"agregados": 1, "actualizados": 1, "eliminados": 0, "sin_cambio": 2})
        live = self.terrenos(f["base_id"])
        self.assertEqual(live["Lote Beta renombrado"]["id"], ids["Lote Beta"])
        self.assertEqual(live["Lote Alfa"]["id"], ids["Lote Alfa"])
        self.assertEqual([t["terreno"] for t in sorted(live.values(), key=lambda t: t["orden"])],
                         ["Nuevo primero", "Lote Gamma", "Lote Beta renombrado", "Lote Alfa"])
        # Remove A-001, then bring it back with other values.
        self.archivo.poner(libro([fila("N-1", "Nuevo primero"), fila("007", "Lote Gamma", 3_000_000),
                                  fila("A-002", "Lote Beta renombrado", 2_000_000)]))
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["conteos"]["eliminados"], 1)
        borrada = self.identidad(f["id"], "A-001")
        self.assertEqual((borrada["id"], borrada["terreno_id"], borrada["eliminada_en_version"]), (alfa, None, 3))
        self.archivo.poner(libro([fila("A-001", "Lote Alfa vuelve", 9_000_000), fila("N-1", "Nuevo primero"),
                                  fila("007", "Lote Gamma", 3_000_000), fila("A-002", "Lote Beta renombrado", 2_000_000)]))
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["conteos"]["agregados"], 1)
        vuelta = self.identidad(f["id"], "A-001")
        self.assertEqual((vuelta["id"], vuelta["eliminada_en_version"], vuelta["primera_version"]), (alfa, None, 1))
        # Its previous values are still in history.
        versiones = self.call("GET", f"/api/excel/fuentes/{f['id']}/versiones")[1]["versiones"]
        self.assertEqual([v["numero"] for v in versiones], [4, 3, 2, 1])
        v1 = self.call("GET", f"/api/excel/fuentes/{f['id']}/versiones/{versiones[-1]['id']}")[1]
        self.assertEqual(
            [(r["clave"], r["datos"]["terreno"], r["datos"]["asking_price"]) for r in v1["filas"]],
            [("A-001", "Lote Alfa", 1_000_000), ("A-002", "Lote Beta", 2_000_000), ("007", "Lote Gamma", 3_000_000)])
        self.assertEqual({r["identidad_id"] for r in v1["filas"] if r["clave"] == "A-001"}, {alfa})

    def test_version_one_is_reconstructed_exactly_after_many_edits(self):
        f = self.fuente()
        v1_id = f["version_activa"]["id"]
        with db.session() as conn:
            original = repo.filas_de_version(conn, v1_id)
        for n in range(3):
            self.archivo.poner(libro([fila("A-001", f"Lote Alfa {n}", 1_000_000 + n)]))
            self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "ok")
        with db.session() as conn:
            self.assertEqual(repo.filas_de_version(conn, v1_id), original)
        expected = [lectura.normalizar(r.record) for r in lectura.leer(
            libro(BASICO), lectura.Configuracion(**CONFIG)).filas]
        self.assertEqual([r["datos"] for r in original], expected)

    def test_no_change_and_reorder_only_are_not_new_versions(self):
        f = self.fuente()
        time.sleep(1.1)  # timestamps have one-second resolution
        r = self.actualizar(f["id"])[1]
        self.assertEqual(r["ejecucion"]["estado"], "sin_cambios")
        self.assertGreater(r["fuente"]["ultima_revision_en"], f["ultima_revision_en"])
        self.archivo.poner(libro(list(reversed(BASICO))))  # different bytes, same business content
        r = self.actualizar(f["id"])[1]
        self.assertEqual(r["ejecucion"]["estado"], "sin_cambios")
        self.assertEqual(r["fuente"]["version_activa"]["numero"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM excel_version").fetchone()[0], 1)

    def test_changed_interpretation_is_reevaluated(self):
        f = self.fuente()
        status, body = self.call("POST", f"/api/excel/fuentes/{f['id']}/configuracion",
                                 {"generacion": f["generacion"], **CONFIG, "moneda": "MXN"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["fuente"]["configuracion"]["numero"], 2)
        r = self.actualizar(f["id"])[1]  # same bytes, new configuration
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["conteos"]["actualizados"]), ("ok", 3))
        self.assertEqual({t["moneda"] for t in self.terrenos(f["base_id"]).values()}, {"MXN"})
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "sin_cambios")
        status, body = self.call("POST", f"/api/excel/fuentes/{f['id']}/configuracion",
                                 {"generacion": f["generacion"], **CONFIG})
        self.assertEqual((status, body["detalle"]["code"]), (409, "conflict"))  # stale generation

    def test_unknown_currency_stays_unknown_and_currency_column_is_honoured(self):
        self.drive.agregar("monedas", libro(
            [fila("1", "Uno") + ["USD"], fila("2", "Dos") + ["pesos"], fila("3", "Tres") + [None]],
            encabezado=ENCABEZADO + ["Moneda"]))
        status, body = self.conectar(item="monedas", moneda="columna", columna_moneda="Moneda")
        self.assertEqual(status, 200, body)
        live = self.terrenos(body["fuente"]["base_id"])
        self.assertEqual({k: t["moneda"] for k, t in live.items()}, {"Uno": "USD", "Dos": "MXN", "Tres": None})


class InvalidInput(ExcelServer):
    def assert_rejected(self, f, contenido, codigo, problema=None):
        antes = self.terrenos(f["base_id"])
        self.archivo.poner(contenido)
        r = self.actualizar(f["id"])[1]
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["error"]["codigo"]), ("error", codigo))
        if problema:
            self.assertIn(problema, {p["codigo"] for p in r["ejecucion"]["problemas"]})
            self.assertTrue(all(p["fila"] for p in r["ejecucion"]["problemas"]))
        self.assertEqual(self.terrenos(f["base_id"]), antes)
        self.assertEqual(r["fuente"]["version_activa"]["numero"], 1)
        self.assertEqual(r["fuente"]["ultimo_error"]["codigo"], codigo)
        return r

    def test_every_invalid_input_keeps_the_last_good_version(self):
        f = self.fuente()
        self.assert_rejected(f, libro(BASICO + [fila(None, "Sin ID")]), "datos_invalidos", "id_faltante")
        self.assert_rejected(f, libro(BASICO + [fila("A-001", "Repetido")]), "datos_invalidos", "id_duplicado")
        self.assert_rejected(f, libro(BASICO + [fila("X-9", None)]), "datos_invalidos", "sin_nombre")
        malo = fila("X-9", "Precio ilegible")
        malo[5] = "un millón"
        self.assert_rejected(f, libro(BASICO + [malo]), "datos_invalidos", "numero_ilegible")
        self.assert_rejected(f, b"esto no es un xlsx", "archivo_invalido")
        self.assert_rejected(f, libro(BASICO, hoja="Otra"), "hoja_faltante")
        sin_id = [h if h != "ID" else "Clave" for h in ENCABEZADO]
        self.assert_rejected(f, libro(BASICO, encabezado=sin_id), "columna_id_faltante")
        with patch.object(lectura, "MAX_EXPANDIDO", 1000):
            self.assert_rejected(f, libro(BASICO), "demasiado_grande")
        with patch.object(lectura, "MAX_BYTES", 100):
            r = self.actualizar(f["id"])[1]
            self.assertEqual(r["ejecucion"]["error"]["codigo"], "demasiado_grande")

    def test_unsupported_currency_value_blocks(self):
        self.drive.agregar("eur", libro([fila("1", "Uno") + ["EUR"]], encabezado=ENCABEZADO + ["Moneda"]))
        status, body = self.conectar(item="eur", moneda="columna", columna_moneda="Moneda")
        self.assertEqual((status, body["detalle"]["problemas"][0]["codigo"]), (422, "moneda_no_admitida"))


class EmptyCandidate(ExcelServer):
    def test_empty_requires_review_bound_to_the_candidate(self):
        f = self.fuente()
        self.archivo.poner(libro([]))
        r = self.actualizar(f["id"])[1]
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["error"]["codigo"]), ("revision", "vacio"))
        candidato = r["ejecucion"]["candidato"]
        self.assertEqual(len(self.terrenos(f["base_id"])), 3)
        # A confirmation for another candidate does not empty anything.
        r = self.actualizar(f["id"], confirmar_vacio="otro-candidato")[1]
        self.assertEqual(r["ejecucion"]["estado"], "revision")
        # If the file changes after review, the old confirmation no longer applies.
        self.archivo.poner(libro([], hoja="Registro Análisis", otras_hojas=("Nueva",)))
        r = self.actualizar(f["id"], confirmar_vacio=candidato)[1]
        self.assertEqual(r["ejecucion"]["estado"], "revision")
        candidato = r["ejecucion"]["candidato"]
        r = self.actualizar(f["id"], confirmar_vacio=candidato)[1]
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["conteos"]["eliminados"]), ("ok", 3))
        self.assertEqual(self.terrenos(f["base_id"]), {})
        self.assertEqual(self.conn.execute("SELECT vacia_confirmada FROM excel_version WHERE numero = 2"
                                           ).fetchone()[0], 1)

    def test_failures_are_never_an_empty_file(self):
        f = self.fuente()
        for codigo in ("reconectar", "sin_permiso", "no_encontrado", "no_disponible"):
            self.archivo.falla = ProveedorError(codigo, f"falla {codigo}")
            r = self.actualizar(f["id"])[1]
            self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["error"]["codigo"]), ("error", codigo))
            self.assertEqual(len(self.terrenos(f["base_id"])), 3)
        self.archivo.falla = None
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "sin_cambios")


class Replay(ExcelServer):
    def test_refresh_replay_and_conflicting_key(self):
        f = self.fuente()
        self.archivo.poner(libro(BASICO[:2]))
        clave = {"Idempotency-Key": "repetir-actualizacion-1"}
        primero = self.actualizar(f["id"], headers=clave)[1]
        self.archivo.poner(libro(BASICO[:1]))  # even if the file moved on
        segundo = self.actualizar(f["id"], headers=clave)[1]
        self.assertTrue(segundo["repeticion"])
        self.assertEqual(segundo["ejecucion"], primero["ejecucion"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM excel_ejecucion").fetchone()[0], 2)
        status, body = self.actualizar(f["id"], headers=clave, confirmar_vacio="x")
        self.assertEqual((status, body["detalle"]["code"]), (409, "idempotency_conflict"))
        status, body = self.call("POST", f"/api/excel/fuentes/{f['id']}/actualizar", {})
        self.assertEqual((status, body["detalle"]["code"]), (422, "idempotency_key_required"))

    def test_connect_replay_never_duplicates(self):
        clave = {"Idempotency-Key": "conectar-una-vez"}
        status, a = self.conectar(headers=clave)
        status2, b = self.conectar(headers=clave)
        self.assertEqual((status, status2), (200, 200))
        self.assertEqual(a["fuente"]["id"], b["fuente"]["id"])
        self.assertTrue(b["repeticion"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM base").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM excel_version").fetchone()[0], 1)
        status, body = self.conectar(headers=clave, nombre="Otro nombre")
        self.assertEqual((status, body["detalle"]["code"]), (409, "idempotency_conflict"))

    def test_connect_retry_after_a_failed_commit_succeeds_once(self):
        clave = {"Idempotency-Key": "conectar-tras-fallo"}
        with patch.object(repo, "activar", side_effect=RuntimeError("fallo a mitad")):
            self.assertEqual(self.conectar(headers=clave)[0], 500)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM base").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM inventory_operation_result").fetchone()[0], 0)
        self.assertEqual(self.conectar(headers=clave)[0], 200)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM excel_fuente").fetchone()[0], 1)


class Concurrency(ExcelServer):
    def test_simultaneous_refresh_is_refused_while_one_runs(self):
        f = self.fuente()
        self.archivo.poner(libro(BASICO[:2]))
        self.archivo.esperar = threading.Event()
        self.archivo.descargando.clear()
        resultado = {}
        hilo = threading.Thread(target=lambda: resultado.update(a=self.actualizar(f["id"])))
        hilo.start()
        self.assertTrue(self.archivo.descargando.wait(5))
        status, body = self.actualizar(f["id"], "beto")
        self.assertEqual((status, body["detalle"]["code"]), (409, "en_curso"))
        self.assertTrue(self.call("GET", f"/api/excel/fuentes/{f['id']}")[1]["fuente"]["en_curso"])
        self.archivo.esperar.set()
        hilo.join(10)
        self.assertEqual(resultado["a"][1]["ejecucion"]["estado"], "ok")

    def test_a_stale_worker_cannot_overwrite_a_newer_run(self):
        f = self.fuente()
        self.archivo.poner(libro(BASICO[:2]))
        self.archivo.esperar = threading.Event()
        self.archivo.descargando.clear()
        resultado = {}
        hilo = threading.Thread(target=lambda: resultado.update(a=self.actualizar(f["id"])))
        hilo.start()
        self.assertTrue(self.archivo.descargando.wait(5))
        a_id = self.conn.execute("SELECT id FROM excel_ejecucion WHERE estado = 'en_curso'").fetchone()[0]
        # A's lease runs out while it is still working.
        self.conn.execute("UPDATE excel_ejecucion SET lease_hasta = 0 WHERE id = ?", (a_id,))
        # B starts (A is marked interrupted) and completes with a newer file.
        self.archivo.esperar.set()
        self.archivo.esperar = None
        hilo.join(10)  # A returns: fenced out
        b = self.actualizar(f["id"], "beto")[1]
        self.assertEqual(resultado["a"][1]["ejecucion"]["estado"], "interrumpida")
        self.assertEqual(b["ejecucion"]["estado"], "ok")
        self.assertEqual(b["fuente"]["version_activa"]["numero"], 2)

    def test_stale_worker_returning_after_b_completed_changes_nothing(self):
        f = self.fuente()
        with db.session() as conn:
            fuente = repo.fuente(conn, f["id"])
            a = repo.reclamar(conn, fuente, "actualizacion", "worker-a", "h", self.users["ana"]["id"])
            conn.execute("UPDATE excel_ejecucion SET lease_hasta = 0 WHERE id = ?", (a["id"],))
        self.archivo.poner(libro(BASICO[:1]))
        b = self.actualizar(f["id"], "beto")[1]
        self.assertEqual(b["ejecucion"]["estado"], "ok")
        lect = lectura.leer(libro(BASICO[:2]), lectura.Configuracion(**CONFIG))
        from server.excel.proveedor import Metadatos
        meta = Metadatos("x.xlsx", None, None, 1, None, None, None)
        with db.session() as conn:
            with self.assertRaises(repo.SinPropiedadError):
                repo.activar(conn, a["id"], lect, meta, "sha")
            self.assertFalse(repo.terminar(conn, a["id"], "error", codigo="x"))
            self.assertEqual(repo.ejecucion(conn, a["id"])["estado"], "interrumpida")
            self.assertEqual(repo.ejecucion(conn, b["ejecucion"]["id"])["estado"], "ok")
        self.assertEqual(set(self.terrenos(f["base_id"])), {"Lote Alfa"})

    def test_a_configuration_change_fences_a_running_refresh(self):
        f = self.fuente()
        self.archivo.poner(libro(BASICO[:2]))
        self.archivo.esperar = threading.Event()
        self.archivo.descargando.clear()
        resultado = {}
        hilo = threading.Thread(target=lambda: resultado.update(a=self.actualizar(f["id"])))
        hilo.start()
        self.assertTrue(self.archivo.descargando.wait(5))
        with db.session() as conn:
            repo.cambiar_configuracion(conn, f["id"], f["generacion"],
                                       lectura.Configuracion(**{**CONFIG, "moneda": "MXN"}), self.users["beto"]["id"])
        self.archivo.esperar.set()
        hilo.join(10)
        self.assertEqual(resultado["a"][1]["ejecucion"]["estado"], "conflicto")
        self.assertEqual(len(self.terrenos(f["base_id"])), 3)


class Failures(ExcelServer):
    def test_a_dead_worker_leaves_old_data_and_is_recovered(self):
        f = self.fuente()
        with db.session() as conn:
            run = repo.reclamar(conn, repo.fuente(conn, f["id"]), "actualizacion", "muerto-1", "h",
                                self.users["ana"]["id"])
            conn.execute("UPDATE excel_ejecucion SET lease_hasta = 0 WHERE id = ?", (run["id"],))
        detalle = self.call("GET", f"/api/excel/fuentes/{f['id']}")[1]["fuente"]
        self.assertEqual((detalle["en_curso"], detalle["ultima_ejecucion"]["estado"]), (False, "interrumpida"))
        self.assertEqual(len(self.terrenos(f["base_id"])), 3)
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "sin_cambios")

    def test_file_changing_mid_download_is_retried_or_rejected(self):
        f = self.fuente()
        self.archivo.poner(libro(BASICO[:2]))
        self.archivo.cambiar_durante_descarga = 1
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "ok")
        self.archivo.poner(libro(BASICO[:1]))
        self.archivo.cambiar_durante_descarga = 10
        r = self.actualizar(f["id"])[1]
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["error"]["codigo"]),
                         ("conflicto", "archivo_cambiando"))
        self.assertEqual(len(self.terrenos(f["base_id"])), 2)

    def test_partial_materialization_rolls_back_completely(self):
        f = self.fuente()
        antes = self.terrenos(f["base_id"])
        self.archivo.poner(libro([fila("A-001", "Alfa cambiado"), fila("A-002", "Beta cambiado"),
                                  fila("Z-1", "Nuevo")]))
        original = repo_terrenos.update_from_record
        llamadas = []

        def falla(conn, *a, **k):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise RuntimeError("SECRETO fallo a mitad")
            return original(conn, *a, **k)

        with patch.object(repo_terrenos, "update_from_record", falla), patch("traceback.print_exc"):
            r = self.actualizar(f["id"])[1]
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["error"]["codigo"]), ("error", "interno"))
        self.assertNotIn("SECRETO", json.dumps(r))
        self.assertEqual(self.terrenos(f["base_id"]), antes)
        for tabla, n in (("excel_version", 1), ("excel_identidad", 3), ("excel_version_fila", 3)):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], n, tabla)
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "ok")


class FrozenMapsAndWrites(ExcelServer):
    def test_saved_maps_never_change(self):
        f = self.fuente()
        status, body = self.call("POST", "/api/mapas", {
            "nombre": "Mapa fechado", "tipo": "simple",
            "capas": [{"base_id": f["base_id"], "color": "#2a78d6"}], "config": {}})
        self.assertEqual(status, 200, body)
        mapa_id = body["mapa"]["id"]
        antes = self.call("GET", f"/api/mapas/{mapa_id}/terrenos")[1]
        self.archivo.poner(libro([fila("A-001", "Alfa cambiado", 5), fila("Z-1", "Nuevo")]))
        self.assertEqual(self.actualizar(f["id"])[1]["ejecucion"]["estado"], "ok")
        self.assertEqual(self.call("GET", f"/api/mapas/{mapa_id}/terrenos")[1], antes)

    def test_server_refuses_writes_to_a_connected_base_but_not_to_others(self):
        f = self.fuente()
        base = f["base_id"]
        status, body = self.call("POST", f"/api/bases/{base}/terrenos", {"terreno": "Manual"})
        self.assertEqual((status, body["detalle"]["code"]), (409, "fuente_conectada"))
        status, body = self.call("DELETE", f"/api/bases/{base}")
        self.assertEqual((status, body["detalle"]["code"]), (409, "fuente_conectada"))
        status, body = self.call("POST", f"/api/bases/{base}/adjuntar", {"token": "x"})
        self.assertEqual((status, body["detalle"]["code"]), (409, "fuente_conectada"))
        # Disconnecting keeps the base, its data and history protected.
        status, body = self.call("POST", f"/api/excel/fuentes/{f['id']}/desconectar", {"generacion": f["generacion"]})
        self.assertEqual((status, body["fuente"]["estado"]), (200, "desconectada"))
        self.assertEqual(self.call("DELETE", f"/api/bases/{base}")[0], 409)
        self.assertEqual(self.actualizar(f["id"])[1]["detalle"]["code"], "no_activa")
        status, body = self.call("POST", f"/api/excel/fuentes/{f['id']}/reconectar",
                                 {"generacion": body["fuente"]["generacion"]})
        self.assertEqual((status, body["fuente"]["estado"]), (200, "activa"))
        self.assertEqual(body["fuente"]["version_activa"]["numero"], 1)
        # Renaming is application metadata and stays allowed.
        self.assertEqual(self.call("PATCH", f"/api/bases/{base}", {"nombre": "Renombrada"})[0], 200)
        # An ordinary base keeps every action.
        with db.session() as conn:
            from server.repo import bases as repo_bases
            otra = repo_bases.create(conn, "Base normal", None, None)
        self.assertEqual(self.call("POST", f"/api/bases/{otra}/terrenos", {"terreno": "Manual"})[0], 200)
        self.assertEqual(self.call("DELETE", f"/api/bases/{otra}")[0], 200)


class Schema(ExcelServer):
    def test_v9_tables_and_backup_policy(self):
        tablas = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"excel_cuenta", "excel_credencial", "excel_autorizacion", "excel_fuente",
                         "excel_configuracion", "excel_version", "excel_identidad", "excel_version_fila",
                         "excel_ejecucion"} <= tablas)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 9)
        from server import postgres
        self.assertNotIn("excel_credencial", postgres.TABLES)
        self.assertNotIn("excel_autorizacion", postgres.TABLES)
        self.assertIn("excel_version_fila", postgres.TABLES)

    def test_a_version_cannot_cross_sources(self):
        import sqlite3
        f = self.fuente()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO excel_version (id, fuente_id, numero, configuracion_id, ejecucion_id, sha256,"
                " contenido_huella, filas, activada_en) VALUES ('v', ?, 9, 'otra-config', 'r', 's', 'c', 0, 'x')",
                (f["id"],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE excel_ejecucion SET agregados = -1")

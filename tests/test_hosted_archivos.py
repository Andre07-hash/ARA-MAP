"""The employee file workflow through the hosted entry point and Team B's adapter.

The real hosted handler, the real `storage3` SDK and `AlmacenSupabase`, over
Team B's fake of the provider (an httpx mock transport): what the application
and the adapter do together. Nothing here reaches Supabase, so the provider's
real collision, freshness, quota and full-size behaviour stay hosted gates.
Skipped where the hosted lock (requirements-hosted.txt) is not installed.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import almacen_supabase, db, hosted, recuperacion
from server.almacen import AlmacenEnMemoria
from server.api import archivos as api
from server.repo import maestra
from tests.archivos_http_harness import Cliente, Servidor
from tests.support import TempDatabase, create_user, session_cookie
from tests.test_archivos_http import kmz

HOST = "piloto.example.test"
MIB = 1024 * 1024
SDK = importlib.util.find_spec("storage3") and importlib.util.find_spec("httpx")


ENTORNO = {almacen_supabase.ENV_URL: "https://ficticio.example.test",
           almacen_supabase.ENV_KEY: "clave-ficticia-de-prueba",
           almacen_supabase.ENV_BUCKET: "adjuntos-ficticios"}
spec = importlib.util.spec_from_file_location(
    "restaurar_archivos", Path(__file__).parents[1] / "scripts" / "restaurar_archivos.py")
restaurar_archivos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restaurar_archivos)


def orden(funcion, argumentos):
    """Run a command's main(); returns (exit code, everything it printed)."""
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
        try:
            codigo = funcion(argumentos)
        except SystemExit as exc:
            codigo = int(exc.code or 0)
    return codigo, salida.getvalue()


class _Flujo(TempDatabase):
    """The hosted handler with fictional accounts, one base and one terrain row."""

    def almacen(self):
        raise NotImplementedError

    def setUp(self):
        super().setUp()
        api.configurar_almacen(self.almacen)
        self.addCleanup(api.configurar_almacen, None)
        for parche in (patch.object(hosted.HostedHandler, "_database_ready", lambda self: True),
                       patch.object(hosted.HostedHandler, "HOST_PUBLICO", HOST),
                       patch.object(hosted.HostedHandler, "log_message", lambda *a: None),
                       patch("server.almacen_supabase._registro")):
            parche.start()
            self.addCleanup(parche.stop)
        with db.session() as conn:
            ada = create_user(conn, "ada", "Ada Ficticia", rol="admin")
            olga = create_user(conn, "olga", "Olga Ficticia", rol="operador")
            create_user(conn, "otto", "Otto Ficticio", rol="operador")
            self.cookies = {n: session_cookie(conn, n) for n in ("ada", "olga", "otto")}
            base = maestra.crear(conn, "Base Ficticia", ada)["id"]
            conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                         " VALUES (?, ?, ?, ?)", (base, olga["id"], db.now(), ada["id"]))
            self.terreno = str(uuid.uuid4())  # an existing row with no X/Y
            conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                         " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                         (self.terreno, base, db.now(), ada["id"], db.now(), ada["id"]))
        self.servidor = Servidor(hosted.HostedHandler)
        self.addCleanup(self.servidor.cerrar)
        self.c = Cliente(self.servidor.port, self.servidor.port)

    def pedir(self, metodo, ruta, quien="olga", datos=None, cuerpo=None, tipo=None, clave=False):
        cabeceras = {"Host": HOST, "Origin": f"https://{HOST}"}
        if tipo:
            cabeceras["Content-Type"] = tipo
        if clave:
            cabeceras["Idempotency-Key"] = str(uuid.uuid4())
        status, h, crudo = self.c.pedir(metodo, ruta, cookie=self.cookies[quien], datos=datos,
                                        cuerpo=cuerpo, cabeceras=cabeceras)
        if h.get("Content-Type", "").startswith("application/json"):
            return status, json.loads(crudo), h
        return status, crudo, h

    def subir(self, contenido, tipo, completar=True):
        s, inicio, _ = self.pedir("POST", f"/api/inventario/terrenos/{self.terreno}/archivos", datos={
            "tipo": tipo, "nombre_original": f"ficticio.{tipo}", "tamano_declarado": len(contenido),
            "sha256_declarado": hashlib.sha256(contenido).hexdigest()}, clave=True)
        self.assertEqual(s, 200, inicio)
        s, r, _ = self.pedir("PUT", f"/api/archivos/versiones/{inicio['version_id']}/contenido",
                             cuerpo=contenido, tipo="application/octet-stream")
        self.assertEqual(s, 200, r)
        if not completar:
            return inicio, None
        s, r, _ = self.pedir("POST", f"/api/archivos/versiones/{inicio['version_id']}/completar")
        self.assertEqual(s, 200, r)
        return inicio, r


class InicioConAlmacenNoConstruible(_Flujo):
    """Settings are complete but the store cannot be built (here: the SDK is
    not importable). Needs no SDK, so it also runs in CI and on Python 3.9."""

    def almacen(self):
        return self.memoria

    def setUp(self):
        self.memoria = AlmacenEnMemoria()
        super().setUp()

    def iniciar(self, quien="olga", clave=None, contenido=b"%PDF-1.7\nficticio"):
        cabeceras = {"Host": HOST, "Origin": f"https://{HOST}", "Idempotency-Key": clave or str(uuid.uuid4())}
        status, _, crudo = self.c.pedir("POST", f"/api/inventario/terrenos/{self.terreno}/archivos",
                                        cookie=self.cookies[quien], cabeceras=cabeceras, datos={
            "tipo": "pdf", "nombre_original": "ficticio.pdf", "tamano_declarado": len(contenido),
            "sha256_declarado": hashlib.sha256(contenido).hexdigest()})
        return status, json.loads(crudo)

    def pendientes(self):
        with db.session() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM archivo_version").fetchone()["n"]

    def test_start_is_503_without_a_new_pending_row_and_keeps_authorization_and_replay(self):
        s, primero = self.iniciar(clave="clave-ficticia-de-replay")   # while the store works
        self.assertEqual((s, self.pendientes()), (200, 1))

        def sin_sdk(nombre):
            raise ImportError(nombre)

        with patch.object(hosted.HostedHandler, "HOST_PUBLICO", HOST), \
                patch("server.almacen_supabase.importlib.import_module", sin_sdk):
            hosted.configurar({"ARA_MAP_DATABASE_URL": "postgresql://ficticio",
                               "ARA_MAP_HOST_PUBLICO": HOST, **ENTORNO})
            s, error = self.iniciar()                                   # authorized, new request
            self.assertEqual((s, error["detalle"]["code"]), (503, "almacen_no_configurado"))
            self.assertEqual(self.pendientes(), 1)                      # nothing was inserted
            self.assertEqual(self.iniciar("otto")[0], 404)              # the denial still comes first
            self.assertEqual(self.c.pedir("POST", f"/api/inventario/terrenos/{self.terreno}/archivos",
                                          cabeceras={"Host": HOST}, datos={})[0], 401)
            s, repetido = self.iniciar(clave="clave-ficticia-de-replay")  # the earlier answer, replayed
            self.assertEqual((s, repetido["version_id"]), (200, primero["version_id"]))
            s, conflicto = self.iniciar(clave="clave-ficticia-de-replay", contenido=b"%PDF-1.7\notro")
            self.assertEqual((s, conflicto["detalle"]["code"]), (409, "idempotencia_conflictiva"))
            self.assertEqual(self.pendientes(), 1)


@unittest.skipUnless(SDK, "needs the hosted lock: pip install -r requirements-hosted.txt")
class FlujoConAdaptador(_Flujo):
    def almacen(self):
        return self.tienda

    def setUp(self):
        from tests.test_almacen_supabase import CorteError, ProveedorFalso, almacen_sdk

        self.corte = CorteError
        self.sdk = almacen_sdk
        self.falso = ProveedorFalso
        self.proveedor = ProveedorFalso()
        self.tienda = almacen_sdk(self.proveedor)
        super().setUp()

    def test_attach_kmz_select_and_activate_the_boundary(self):
        inicio, completo = self.subir(kmz("ambiguo_tres_lotes"), "kmz")
        self.assertEqual((completo["intento"]["resultado"], completo["aplicada"]),
                         ("requiere_seleccion", False))
        vid = inicio["version_id"]
        s, elegido, _ = self.pedir("POST", f"/api/archivos/versiones/{vid}/procesar",
                                   datos={"seleccion": [1]}, clave=True)
        self.assertEqual(s, 200, elegido)
        s, activo, _ = self.pedir("POST", f"/api/archivos/{inicio['archivo_id']}/activar", datos={
            "version_id": vid, "geometria_id": elegido["geometria_id"],
            "expected_revision": completo["archivo"]["revision"]}, clave=True)
        self.assertEqual(s, 200, activo)
        gid = elegido["geometria_id"]
        self.assertEqual(activo["archivo"]["geometria_activa_id"], gid)
        # An invalid replacement leaves that boundary active.
        _, malo = self.subir(kmz("solo_lineas"), "kmz")
        self.assertFalse(malo["aplicada"])
        s, meta, _ = self.pedir("POST", "/api/archivos/geometrias/metadatos", datos={"ids": [gid]})
        self.assertTrue(meta["geometrias"][gid]["activa"])
        # The provider holds one write-once final object per completed version, as octets only.
        finales = [k for k in self.proveedor.objetos if "/final/" in k or k.startswith("final/")]
        self.assertEqual(len(finales), 2)

    def test_pdf_above_four_mebibytes_round_trips_and_stays_private(self):
        pdf = b"%PDF-1.7\n" + bytes(range(256)) * (5 * MIB // 256)
        inicio, _ = self.subir(pdf, "pdf")
        s, bajado, h = self.pedir("GET", f"/api/archivos/versiones/{inicio['version_id']}/descarga")
        self.assertEqual((s, bajado), (200, pdf))
        self.assertEqual(h["Cache-Control"], "private, no-store")
        self.assertEqual(h["Strict-Transport-Security"], "max-age=31536000")
        self.assertEqual(self.pedir("GET", f"/api/archivos/versiones/{inicio['version_id']}/descarga", "ada")[0], 200)
        self.assertEqual(self.pedir("GET", f"/api/archivos/versiones/{inicio['version_id']}/descarga", "otto")[0], 404)
        # Every provider request carried the server credential; no answer to a browser did.
        self.assertTrue(self.proveedor.vistas)
        self.assertTrue(all("authorization" in v for v in self.proveedor.vistas))
        s, lista, h = self.pedir("GET", f"/api/inventario/terrenos/{self.terreno}/archivos")
        self.assertNotIn("Bearer", str(lista) + str(h))
        self.assertNotIn("final/", str(lista))

    def test_a_provider_outage_is_a_retryable_storage_error_and_loses_nothing(self):
        pdf = b"%PDF-1.7\nficticio"
        inicio, _ = self.subir(pdf, "pdf")
        ruta = f"/api/archivos/versiones/{inicio['version_id']}/descarga"
        self.proveedor.fallar("bajar", "corte")
        s, error, _ = self.pedir("GET", ruta)
        self.assertEqual((s, error["detalle"]["code"], error["detalle"].get("reintentar")),
                         (503, "almacen_no_disponible", True))
        self.assertNotIn("supabase", str(error).lower())
        self.assertEqual(self.pedir("GET", ruta)[:2], (200, pdf))  # nothing was lost

    def test_export_through_the_real_factory_then_restore_and_verify(self):
        """B's exporter on --almacen-entorno -> A's upload -> the final verification.

        The store reaches both commands as the application's does: the three
        settings, fabrica_desde_entorno, then the factory. Only the transport
        is the fake provider.
        """
        pdf = b"%PDF-1.7\n" + bytes(range(256)) * 4096
        self.subir(pdf, "pdf")
        self.subir(kmz("poligono_simple"), "kmz")
        exportado = Path(self._dir.name) / "exportado"
        respaldo = Path(self._dir.name) / "respaldo.db"   # the verifier reads a backup, not the live file
        with contextlib.closing(sqlite3.connect(self.db_path)) as vivo, \
                contextlib.closing(sqlite3.connect(respaldo)) as copia:
            vivo.backup(copia)
        destino = self.falso()   # the restore target: a second, empty bucket
        construidos = []

        from tests import test_almacen_supabase as falso

        entorno = {almacen_supabase.ENV_URL: falso.URL, almacen_supabase.ENV_KEY: falso.CLAVE,
                   almacen_supabase.ENV_BUCKET: falso.BUCKET}
        real = almacen_supabase._construir

        def construir_en(proveedor):
            def construir(url_api, clave, bucket, transporte=None):
                construidos.append((url_api, bucket))   # what the factory itself passes on
                return real(url_api, clave, bucket, transporte=falso.transporte_http(proveedor))
            return patch.object(almacen_supabase, "_construir", construir)

        manifiesto = ["--manifiesto", str(exportado / "manifiesto.json"), "--almacen-entorno"]
        with patch.dict(os.environ, entorno), patch("server.almacen_supabase._registro"):
            with construir_en(self.proveedor):
                codigo, informe = orden(recuperacion.main, ["--sqlite", str(respaldo), "--almacen-entorno",
                                                            "--exportar", str(exportado)])
            self.assertEqual(codigo, 0, informe)
            finales = json.loads((exportado / "manifiesto.json").read_text())["finales"]
            self.assertEqual(len(finales), 2)
            self.assertEqual(construidos, [(falso.URL + "/storage/v1", falso.BUCKET)])
            with construir_en(destino):
                self.assertEqual(orden(recuperacion.main, manifiesto + ["--restauracion"])[0], 1)  # empty target
                codigo, informe = orden(restaurar_archivos.main, [str(exportado), "--almacen-entorno"])
                self.assertEqual(codigo, 0, informe)
                self.assertIn("Subidos: 2", informe)
                codigo, informe = orden(recuperacion.main, manifiesto + ["--restauracion"])
                self.assertEqual(codigo, 0, informe)                     # sizes and SHA-256 verified
                self.assertEqual(set(destino.objetos), set(self.proveedor.objetos) - {
                    k for k in self.proveedor.objetos if "temporal/" in k})

                # "Already there" is a size check only. An object of the right size
                # and the wrong bytes passes the upload and fails the verification.
                clave = next(k for k in destino.objetos if k.endswith(finales[0]["clave"]))
                destino.objetos[clave] = bytes(len(destino.objetos[clave]))
                codigo, informe = orden(restaurar_archivos.main, [str(exportado), "--almacen-entorno"])
                self.assertEqual(codigo, 0)
                self.assertIn("ya estaban: 2", informe)
                codigo, informe = orden(recuperacion.main, manifiesto + ["--restauracion"])
                self.assertEqual(codigo, 1, informe)


if __name__ == "__main__":
    unittest.main()

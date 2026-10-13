"""The employee file workflow through the hosted entry point and Team B's adapter.

The real hosted handler, the real `storage3` SDK and `AlmacenSupabase`, over
Team B's fake of the provider (an httpx mock transport): what the application
and the adapter do together. Nothing here reaches Supabase, so the provider's
real collision, freshness, quota and full-size behaviour stay hosted gates.
Skipped where the hosted lock (requirements-hosted.txt) is not installed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
import uuid
from unittest.mock import patch

from server import db, hosted
from server.api import archivos as api
from server.repo import maestra
from tests.archivos_http_harness import Cliente, Servidor
from tests.support import TempDatabase, create_user, session_cookie
from tests.test_archivos_http import kmz

HOST = "piloto.example.test"
MIB = 1024 * 1024
SDK = importlib.util.find_spec("storage3") and importlib.util.find_spec("httpx")


@unittest.skipUnless(SDK, "needs the hosted lock: pip install -r requirements-hosted.txt")
class FlujoConAdaptador(TempDatabase):
    def setUp(self):
        super().setUp()
        from tests.test_almacen_supabase import CorteError, ProveedorFalso, almacen_sdk

        self.corte = CorteError
        self.proveedor = ProveedorFalso()
        api.configurar_almacen(lambda: almacen_sdk(self.proveedor))
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


if __name__ == "__main__":
    unittest.main()

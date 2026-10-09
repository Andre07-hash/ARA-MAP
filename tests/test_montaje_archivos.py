"""Round 3 checkpoint C1: the attachment routes as mounted in the application.

One unmodified production Handler on one loopback port, the routes as
``server/app.py`` registers them, and the local disk store wired the way
``serve()`` wires it (``configurar_archivos``), in a temporary folder. Nothing
here adds a route, patches the dispatcher or uses an in-memory store.
"""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from pathlib import Path
from unittest.mock import patch

from server import app as app_module
from server import auth, db
from server.api import archivos as api
from server.repo import maestra
from tests.archivos_http_harness import Cliente, Servidor
from tests.support import TempDatabase, create_user, session_cookie
from tests.test_archivos_http import PDF
from tests.test_despachador_cuerpos import OCULTA


class Montaje(TempDatabase):
    def setUp(self):
        super().setUp()
        self.addCleanup(api.configurar_almacen, None)
        self.raiz = Path(self._dir.name) / "archivos"       # the database's sibling folder
        with patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": ""}):
            os.environ.pop("ARA_MAP_ARCHIVOS", None)
            self.linea = app_module.configurar_archivos()
        silencio = patch.object(app_module.Handler, "log_message", lambda *a: None)
        silencio.start()
        self.addCleanup(silencio.stop)
        with db.session() as conn:
            ada = create_user(conn, "ada", "Ada Ficticia", rol="admin")
            olga = create_user(conn, "olga", "Olga Ficticia", rol="operador")
            create_user(conn, "otto", "Otto Ficticio", rol="operador")
            self.cookies = {n: session_cookie(conn, n) for n in ("ada", "olga", "otto")}
            base = maestra.crear(conn, "Base Ficticia", ada)["id"]
            conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                         " VALUES (?, ?, ?, ?)", (base, olga["id"], db.now(), ada["id"]))
            self.terreno = str(uuid.uuid4())
            conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                         " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                         (self.terreno, base, db.now(), ada["id"], db.now(), ada["id"]))
        self.servidor = Servidor(app_module.Handler)
        self.addCleanup(self.servidor.cerrar)
        self.c = Cliente(self.servidor.port, self.servidor.port)

    def j(self, metodo, ruta, quien="olga", datos=None, clave=None):
        return self.c.json(metodo, ruta, cookie=self.cookies[quien] if quien else None, datos=datos,
                           cabeceras={"Idempotency-Key": clave} if clave else None)

    def subir_pdf(self, quien="olga"):
        s, inicio = self.j("POST", f"/api/inventario/terrenos/{self.terreno}/archivos", quien,
                           {"tipo": "pdf", "nombre_original": "plano ficticio.pdf",
                            "tamano_declarado": len(PDF),
                            "sha256_declarado": hashlib.sha256(PDF).hexdigest()}, str(uuid.uuid4()))
        self.assertEqual(s, 200, inicio)
        vid = inicio["version_id"]
        s, r = self.c.json("PUT", f"/api/archivos/versiones/{vid}/contenido", cookie=self.cookies[quien],
                           cuerpo=PDF, cabeceras={"Content-Type": "application/pdf"})
        self.assertEqual(s, 200, r)
        s, r = self.j("POST", f"/api/archivos/versiones/{vid}/completar", quien)
        self.assertEqual(s, 200, r)
        return vid

    # -- registry ------------------------------------------------------------------

    def test_the_application_registers_exactly_the_attachment_table_in_order(self):
        montadas = self._rutas()
        esperadas = [tuple(r) for r in api.RUTAS]
        self.assertEqual(montadas[-len(esperadas):], esperadas)       # after every earlier route
        self.assertEqual(len(esperadas), 15)
        self.assertTrue(all(cap for *_, cap in esperadas))
        for metodo, ruta, _h, _cap in api.RUTAS:
            self.assertFalse(auth.is_public(metodo, ruta.replace(":", "x")), ruta)

    def _rutas(self):
        """(method, pattern as written, handler, capability) of every mounted route."""
        return [(r.method, r.path, r.handler, r.capacidad) for r in app_module.router.routes]

    def test_every_route_refuses_anonymous_and_capability_less_callers(self):
        x = str(uuid.uuid4())
        for metodo, ruta, _h, _cap in api.RUTAS:
            concreta = ruta.replace(":gid", x).replace(":iid", x).replace(":vid", x) \
                           .replace(":aid", x).replace(":id", x)
            with self.subTest(ruta=ruta):
                s, r = self.j(metodo, concreta, quien=None)
                self.assertEqual((s, r["detalle"]["code"]), (401, "unauthenticated"))

    # -- store wiring ----------------------------------------------------------------

    def test_local_startup_creates_only_the_sibling_folder_owner_only(self):
        self.assertEqual(self.linea, str(self.raiz))
        self.assertTrue(self.raiz.is_dir())
        self.assertEqual(stat.S_IMODE(self.raiz.stat().st_mode), 0o700)

    def test_a_postgres_database_gets_no_store_unless_one_is_named(self):
        with patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": "postgresql://ficticio.invalid/x"}):
            os.environ.pop("ARA_MAP_ARCHIVOS", None)
            self.assertIsNone(app_module.raiz_de_archivos())
            self.assertIn("sin configurar", app_module.configurar_archivos())
            self.assertIsNone(api._fabrica)
            explicita = Path(self._dir.name) / "nombrada"
            with patch.dict(os.environ, {"ARA_MAP_ARCHIVOS": str(explicita)}):
                self.assertEqual(app_module.configurar_archivos(), str(explicita))
            self.assertTrue(explicita.is_dir())

    def test_an_unusable_folder_wires_nothing_and_content_routes_answer_503(self):
        falta = Path(self._dir.name) / "no-existe" / "archivos"       # the parent is never created
        with patch.dict(os.environ, {"ARA_MAP_ARCHIVOS": str(falta)}):
            self.assertIn("NO DISPONIBLES", app_module.configurar_archivos())
        self.assertFalse(falta.parent.exists())
        self.assertIsNone(api._fabrica)
        s, inicio = self.j("POST", f"/api/inventario/terrenos/{self.terreno}/archivos", "olga",
                           {"tipo": "pdf", "nombre_original": "a.pdf", "tamano_declarado": len(PDF),
                            "sha256_declarado": hashlib.sha256(PDF).hexdigest()}, str(uuid.uuid4()))
        self.assertEqual(s, 200, inicio)
        s, r = self.c.json("PUT", f"/api/archivos/versiones/{inicio['version_id']}/contenido",
                           cookie=self.cookies["olga"], cuerpo=PDF,
                           cabeceras={"Content-Type": "application/pdf"})
        self.assertEqual((s, r["detalle"]["code"]), (503, "almacen_no_configurado"))

    # -- binary answers ----------------------------------------------------------------

    def test_a_download_is_the_exact_bytes_with_private_headers_from_disk(self):
        vid = self.subir_pdf()
        en_disco = [p for p in self.raiz.rglob("*") if p.is_file()]
        self.assertTrue(any(p.read_bytes() == PDF for p in en_disco))
        s, h, cuerpo = self.c.pedir("GET", f"/api/archivos/versiones/{vid}/descarga",
                                    cookie=self.cookies["olga"])
        self.assertEqual((s, cuerpo), (200, PDF))
        self.assertEqual(h["Content-Type"], "application/pdf")
        self.assertEqual(h["Content-Length"], str(len(PDF)))
        self.assertEqual(h["Cache-Control"], "private, no-store")
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h["Content-Security-Policy"], "default-src 'none'; sandbox")
        self.assertIn("attachment", h["Content-Disposition"])
        self.assertIn("plano%20ficticio.pdf", h["Content-Disposition"])
        # Another administrator session reads the same stored bytes; no grant, nothing.
        self.assertEqual(self.c.pedir("GET", f"/api/archivos/versiones/{vid}/descarga",
                                      cookie=self.cookies["ada"])[2], PDF)
        s, _h, cuerpo = self.c.pedir("GET", f"/api/archivos/versiones/{vid}/descarga",
                                     cookie=self.cookies["otto"])
        self.assertEqual(s, 404)
        self.assertNotIn(PDF[:8], cuerpo)

    # -- read-only mode and framing ------------------------------------------------------

    def test_read_only_mode_allows_the_metadata_post_and_no_mutation(self):
        vid = self.subir_pdf()
        with db.session() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with patch.dict(os.environ, {"ARA_MAP_READ_ONLY": "1"}):
            s, r = self.j("POST", "/api/archivos/geometrias/metadatos", datos={"ids": [str(uuid.uuid4())]})
            self.assertEqual((s, r["geometrias"]), (200, {}))
            for metodo, ruta in (("POST", f"/api/inventario/terrenos/{self.terreno}/archivos"),
                                 ("PUT", f"/api/archivos/versiones/{vid}/contenido"),
                                 ("POST", f"/api/archivos/versiones/{vid}/completar"),
                                 ("POST", f"/api/archivos/versiones/{vid}/cancelar"),
                                 ("POST", f"/api/archivos/versiones/{vid}/procesar"),
                                 ("POST", f"/api/archivos/{vid}/activar"),
                                 ("POST", f"/api/archivos/{vid}/retirar")):
                with self.subTest(ruta=ruta):
                    s, r = self.j(metodo, ruta, datos={})
                    self.assertEqual((s, r["error"]), (403, "ARA Map está en modo de solo consulta."))

    def test_malformed_framing_on_an_attachment_route_is_one_400_and_a_close(self):
        import re
        import socket
        ruta = f"/api/archivos/versiones/{uuid.uuid4()}/contenido".encode()
        n = str(len(OCULTA)).encode()
        for nombre, cabeceras in {
                "two lengths": b"Content-Length: 0\r\nContent-Length: " + n,
                "empty length": b"Content-Length: ",
                "chunked": b"Transfer-Encoding: chunked\r\nContent-Length: " + n,
                "signed": b"Content-Length: +" + n,
                "more than 12 digits": b"Content-Length: " + n.rjust(20, b"0")}.items():
            with self.subTest(nombre), socket.create_connection(("127.0.0.1", self.servidor.port),
                                                               timeout=2) as sock:
                sock.sendall(b"PUT " + ruta + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nCookie: "
                             + self.cookies["olga"].encode() + b"\r\nContent-Type: application/pdf\r\n"
                             + cabeceras + b"\r\n\r\n" + OCULTA)
                datos = b""
                while True:
                    trozo = sock.recv(65536)      # ends only if the server closes
                    if not trozo:
                        break
                    datos += trozo
                self.assertEqual(re.findall(rb"HTTP/1\.[01] (\d{3})", datos), [b"400"])

"""Packet 2B: attachment HTTP handlers and bounded geometry delivery.

HTTP HARNESS EVIDENCE, NOT APPLICATION-MOUNTED ENDPOINT ACCEPTANCE: routes are
registered temporarily on the real router (tests/archivos_http_harness.py).
Every request goes over a real loopback connection with a real cookie session
through the real dispatcher; the same checks run on SQLite and on a disposable
Postgres schema.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import tempfile
import threading
import unittest
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from server import app as app_module
from server import archivos, auth, db, postgres
from server.almacen import AlmacenEnMemoria
from server.api import archivos as api
from server.repo import maestra
from tests.archivos_http_harness import Cliente, HandlerBinario, Servidor, rutas_registradas
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
FIXTURES = Path(__file__).parent / "fixtures"
PDF = (FIXTURES / "archivos" / "ficticio.pdf").read_bytes()
CHUNK = archivos.GEOMETRY_CHUNK


def kmz_de_kml(kml: bytes) -> bytes:
    """Deterministic bytes: a fixed member timestamp, so equal input gives an equal KMZ."""
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("doc.kml", date_time=(2026, 10, 9, 0, 0, 0)), kml,
                    compress_type=zipfile.ZIP_DEFLATED)
    return salida.getvalue()


def kmz(nombre: str) -> bytes:
    return kmz_de_kml((FIXTURES / "kmz" / f"{nombre}.kml").read_bytes())


def kml_limite(partes: int = 20_000, por_parte: int = 5) -> bytes:
    """A fictional KMZ at the parser's 100,000-vertex limit, with long coordinates.

    One placemark, `partes` small closed squares (5 positions each), every
    coordinate written with 15+ decimals so the stored GeoJSON is as long as
    finite encodings get for this vertex count.
    """
    poligonos = []
    lado = 0.000123456789012345
    for k in range(partes):
        x = -100.4 + (k % 200) * 0.000391234567890123
        y = 20.6 + (k // 200) * 0.000391234567890123
        anillo = [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado), (x, y)][:por_parte]
        coords = " ".join(f"{a:.15f},{b:.15f}" for a, b in anillo)
        poligonos.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}"
                         "</coordinates></LinearRing></outerBoundaryIs></Polygon>")
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><kml xmlns=\"http://www.opengis.net/kml/2.2\">"
            "<Document><Placemark><name>Límite ficticio</name><MultiGeometry>"
            + "".join(poligonos) + "</MultiGeometry></Placemark></Document></kml>").encode("utf-8")


class Reloj:
    def __init__(self) -> None:
        self.valor = datetime.now(timezone.utc).replace(microsecond=0)
        self.lock = threading.Lock()

    def __call__(self) -> datetime:
        with self.lock:
            return self.valor

    def avanzar(self, segundos: int) -> None:
        with self.lock:
            self.valor += timedelta(seconds=segundos)


class HTTPChecks:
    """Shared matrix; subclasses choose SQLite or disposable Postgres."""

    def setUp(self) -> None:
        self.preparar_bd()
        self.reloj = Reloj()
        real_now = archivos._now
        reloj = self.reloj
        reemplazo = patch.object(archivos, "_now", lambda _r=None: real_now(reloj))
        reemplazo.start()
        self.addCleanup(reemplazo.stop)
        silencio = patch.object(app_module.Handler, "log_message", lambda *a: None)
        silencio.start()
        self.addCleanup(silencio.stop)
        self.store = AlmacenEnMemoria()
        api.configurar_almacen(lambda: self.store)
        self.addCleanup(api.configurar_almacen, None)
        with db.session() as conn:
            self.users = {
                login: auth.create_user(conn, login, f"{login.capitalize()} Ficticia", TEST_PASSWORD,
                                        iterations=1000, rol=rol)
                for login, rol in (("ana", "admin"), ("beto", "admin"),
                                   ("olga", "operador"), ("omar", "operador"))}
            self.tokens = {}
            for login in self.users:
                token, _, _ = auth.login(conn, login, TEST_PASSWORD)
                self.tokens[login] = token
            self.base = maestra.crear(conn, "Base Ficticia", self.users["ana"])["id"]
            self.base2 = maestra.crear(conn, "Segunda Base Ficticia", self.users["ana"])["id"]
            for base in (self.base, self.base2):
                self._conceder(conn, base, "olga")
            self.terreno = self._terreno(conn, self.base)
            self.terreno2 = self._terreno(conn, self.base2)
            self.ajeno = self._terreno(conn, None)          # unassigned: administrators only
        self.rutas = rutas_registradas()
        self.rutas.__enter__()
        self.addCleanup(self.rutas.__exit__, None, None, None)
        self.json_srv = Servidor(app_module.Handler)
        self.bin_srv = Servidor(HandlerBinario)
        self.addCleanup(self.json_srv.cerrar)
        self.addCleanup(self.bin_srv.cerrar)
        self.c = Cliente(self.json_srv.port, self.bin_srv.port)

    # -- fixtures --------------------------------------------------------------

    def preparar_bd(self) -> None:
        raise NotImplementedError

    def _conceder(self, conn, base, login) -> None:
        conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                     " VALUES (?, ?, ?, ?)", (base, self.users[login]["id"], db.now(),
                                              self.users["ana"]["id"]))

    def _terreno(self, conn, base_id) -> str:
        tid = str(uuid.uuid4())
        now = db.now()
        conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                     " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                     (tid, base_id, now, self.users["ana"]["id"], now, self.users["ana"]["id"]))
        return tid

    def sql(self, statement, params=()):
        with db.escritura() as conn:
            conn.execute(statement, params)

    def filas(self, tabla, where="1=1", params=()):
        with db.session() as conn:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {tabla} WHERE {where}", params)]

    def cookie(self, login: str) -> str:
        return f"{auth.COOKIE}={self.tokens[login]}"

    def version_terreno(self, tid):
        return self.filas("inventory_terrain", "id = ?", (tid,))[0]["version"]

    # -- HTTP helpers ------------------------------------------------------------

    def j(self, metodo, ruta, login="ana", datos=None, clave=None, cabeceras=None):
        h = dict(cabeceras or {})
        if clave:
            h["Idempotency-Key"] = clave
        return self.c.json(metodo, ruta, cookie=self.cookie(login) if login else None,
                           datos=datos, cabeceras=h)

    def iniciar(self, contenido, tipo="pdf", login="ana", terreno=None, nombre=None, clave=None,
                tamano=None, sha=None):
        return self.j("POST", f"/api/inventario/terrenos/{terreno or self.terreno}/archivos", login,
                      {"tipo": tipo, "nombre_original": nombre or f"ficticio.{tipo}",
                       "tamano_declarado": len(contenido) if tamano is None else tamano,
                       "sha256_declarado": sha or hashlib.sha256(contenido).hexdigest()},
                      clave or str(uuid.uuid4()))

    def subir(self, vid, contenido, login="ana", tipo_contenido="application/octet-stream"):
        return self.c.json("PUT", f"/api/archivos/versiones/{vid}/contenido",
                           cookie=self.cookie(login), cuerpo=contenido,
                           cabeceras={"Content-Type": tipo_contenido})

    def completar(self, vid, login="ana"):
        return self.j("POST", f"/api/archivos/versiones/{vid}/completar", login)

    def archivo_completo(self, contenido, tipo="pdf", login="ana", terreno=None, nombre=None):
        s, inicio = self.iniciar(contenido, tipo, login, terreno, nombre)
        self.assertEqual(s, 200, inicio)
        s, r = self.subir(inicio["version_id"], contenido, login)
        self.assertEqual(s, 200, r)
        s, r = self.completar(inicio["version_id"], login)
        self.assertEqual(s, 200, r)
        return inicio, r

    def bajar(self, ruta, login="ana"):
        return self.c.pedir("GET", ruta, cookie=self.cookie(login) if login else None, binario=True)

    def geometria_completa(self, gid, login="ana"):
        """Reassemble a geometry from its chunks as the future client would."""
        partes, desde, cabeceras = [], 0, []
        while True:
            s, h, cuerpo = self.bajar(f"/api/archivos/geometrias/{gid}/contenido?desde={desde}", login)
            self.assertEqual(s, 200, cuerpo[:200])
            cabeceras.append(h)
            partes.append(cuerpo)
            if h["X-Geometria-Final"] == "1":
                self.assertEqual(h["X-Geometria-Siguiente"], "fin")
                break
            desde = int(h["X-Geometria-Siguiente"])
        datos = b"".join(partes)
        self.assertEqual(len(datos), int(cabeceras[0]["X-Geometria-Bytes"]))
        self.assertEqual(hashlib.sha256(datos).hexdigest(), cabeceras[0]["X-Geometria-Sha256"])
        return datos, cabeceras

    # -- round trips -------------------------------------------------------------

    def test_pdf_round_trip_download_identity_replay_and_terrain_independence(self):
        version_antes = self.version_terreno(self.terreno)
        inicio, completo = self.archivo_completo(PDF, nombre='Avalúo "final"\r\n.pdf'
                                                 .replace("\r\n", ""))
        self.assertTrue(completo["aplicada"])
        self.assertFalse(completo["limpieza_pendiente"])
        s, replay = self.completar(inicio["version_id"])
        self.assertEqual((s, replay["replay"], replay["version"]), (200, True, completo["version"]))
        s, h, cuerpo = self.bajar(f"/api/archivos/versiones/{inicio['version_id']}/descarga")
        self.assertEqual(s, 200)
        self.assertEqual(cuerpo, PDF)
        self.assertEqual(h["Content-Type"], "application/pdf")
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h["Cache-Control"], "private, no-store")
        self.assertEqual(h["X-Archivo-Sha256"], hashlib.sha256(PDF).hexdigest())
        self.assertTrue(h["Content-Disposition"].startswith('attachment; filename="Avaluo _final_.pdf"'))
        self.assertIn("filename*=UTF-8''Aval%C3%BAo%20%22final%22.pdf", h["Content-Disposition"])
        s, lista = self.j("GET", f"/api/inventario/terrenos/{self.terreno}/archivos")
        self.assertEqual(s, 200)
        self.assertEqual([a["id"] for a in lista["archivos"]], [inicio["archivo_id"]])
        s, versiones = self.j("GET", f"/api/archivos/{inicio['archivo_id']}/versiones")
        self.assertEqual(versiones["versiones"][0]["id"], inicio["version_id"])
        s, hist = self.j("GET", f"/api/archivos/{inicio['archivo_id']}/historial")
        self.assertEqual(s, 200)
        self.assertTrue(all("privado" in e for e in hist["eventos"]))
        self.assertEqual(self.version_terreno(self.terreno), version_antes)
        serializado = json.dumps([inicio, completo, lista, versiones, hist])
        for secreto in ("temporal/", "final/", self.tokens["ana"]):
            self.assertNotIn(secreto, serializado)

    def test_kmz_single_candidate_activates_and_geometry_reassembles_exactly(self):
        inicio, completo = self.archivo_completo(kmz("poligono_con_hueco"), "kmz")
        gid = completo["archivo"]["geometria_activa_id"]
        self.assertTrue(gid)
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", datos={"ids": [gid]})
        self.assertEqual(s, 200)
        d = meta["geometrias"][gid]
        self.assertEqual(meta["no_disponibles"], [])
        self.assertTrue(d["activa"])
        self.assertGreater(d["huecos"], 0)
        datos, _ = self.geometria_completa(gid)
        guardado = self.filas("geometria", "id = ?", (gid,))[0]
        self.assertEqual(datos, guardado["geojson"].encode("utf-8"))
        self.assertEqual(d["bytes"], len(datos))
        self.assertEqual(json.loads(datos)["type"], "MultiPolygon")
        self.assertNotIn("nombre", json.dumps(meta))

    def test_kmz_multi_candidate_selection_and_explicit_activation(self):
        inicio, completo = self.archivo_completo(kmz("ambiguo_tres_lotes"), "kmz")
        vid = inicio["version_id"]
        self.assertEqual(completo["intento"]["resultado"], "requiere_seleccion")
        self.assertFalse(completo["aplicada"])
        s, intentos = self.j("GET", f"/api/archivos/versiones/{vid}/intentos")
        self.assertEqual(s, 200)
        self.assertEqual(intentos["intentos"][0]["candidatos"], 3)
        s, detalle = self.j("GET", f"/api/archivos/intentos/{intentos['intentos'][0]['id']}")
        self.assertEqual(len(detalle["resultado_detalle"]["candidatos"]), 3)
        s, elegido = self.j("POST", f"/api/archivos/versiones/{vid}/procesar", datos={"seleccion": [1]},
                            clave="seleccion-ficticia-1")
        self.assertEqual(s, 200, elegido)
        s, replay = self.j("POST", f"/api/archivos/versiones/{vid}/procesar", datos={"seleccion": [1]},
                           clave="seleccion-ficticia-1")
        self.assertTrue(replay["replay"])
        s, conflicto = self.j("POST", f"/api/archivos/versiones/{vid}/procesar", datos={"seleccion": [2]},
                              clave="seleccion-ficticia-1")
        self.assertEqual((s, conflicto["detalle"]["code"]), (409, "idempotencia_conflictiva"))
        s, activo = self.j("POST", f"/api/archivos/{inicio['archivo_id']}/activar",
                           datos={"version_id": vid, "geometria_id": elegido["geometria_id"],
                                  "expected_revision": completo["archivo"]["revision"]},
                           clave="activar-ficticio-1")
        self.assertEqual(s, 200, activo)
        self.assertEqual(activo["archivo"]["geometria_activa_id"], elegido["geometria_id"])
        s, stale = self.j("POST", f"/api/archivos/{inicio['archivo_id']}/activar",
                          datos={"version_id": vid, "geometria_id": elegido["geometria_id"],
                                 "expected_revision": completo["archivo"]["revision"]},
                          clave="activar-ficticio-2")
        self.assertEqual((s, stale["detalle"]["code"]), (409, "revision_conflictiva"))

    def test_retained_version_activation_and_failed_replacement_keep_layout(self):
        uno, r1 = self.archivo_completo(kmz("poligono_simple"), "kmz")
        g1 = r1["archivo"]["geometria_activa_id"]
        dos, r2 = self.archivo_completo(kmz("solo_lineas"), "kmz")
        self.assertFalse(r2["aplicada"])
        self.assertEqual(r2["archivo"]["geometria_activa_id"], g1)
        s, inicio3 = self.iniciar(kmz("multiparte"), "kmz")
        self.subir(inicio3["version_id"], b"PK\x03\x04 no es un kmz completo")
        s, fallo = self.completar(inicio3["version_id"])
        self.assertEqual(fallo["version"]["estado"], "fallido")
        self.assertEqual(fallo["archivo"]["geometria_activa_id"], g1)
        cuatro, r4 = self.archivo_completo(kmz("multiparte"), "kmz")
        g4 = r4["archivo"]["geometria_activa_id"]
        self.assertNotEqual(g4, g1)
        s, r = self.j("POST", f"/api/archivos/{uno['archivo_id']}/activar",
                      datos={"version_id": uno["version_id"], "geometria_id": g1,
                             "expected_revision": r4["archivo"]["revision"]}, clave="retenida-1")
        self.assertEqual(s, 200, r)
        self.assertEqual(r["archivo"]["geometria_activa_id"], g1)
        self.assertEqual(self.version_terreno(self.terreno), 1)

    def test_cancel_retire_and_retired_content_stays_readable(self):
        s, pendiente = self.iniciar(PDF)
        self.subir(pendiente["version_id"], PDF)
        s, cancelado = self.j("POST", f"/api/archivos/versiones/{pendiente['version_id']}/cancelar")
        self.assertEqual((s, cancelado["estado"], cancelado["limpieza_pendiente"]), (200, "cancelado", False))
        s, otra = self.j("POST", f"/api/archivos/versiones/{pendiente['version_id']}/cancelar")
        self.assertEqual((s, otra["detalle"]["code"]), (409, "subida_no_pendiente"))
        inicio, completo = self.archivo_completo(kmz("poligono_simple"), "kmz")
        s, retirado = self.j("POST", f"/api/archivos/{inicio['archivo_id']}/retirar",
                             datos={"expected_revision": completo["archivo"]["revision"]}, clave="retirar-1")
        self.assertEqual(s, 200, retirado)
        s, replay = self.j("POST", f"/api/archivos/{inicio['archivo_id']}/retirar",
                           datos={"expected_revision": completo["archivo"]["revision"]}, clave="retirar-1")
        self.assertTrue(replay["replay"])
        s, h, cuerpo = self.bajar(f"/api/archivos/versiones/{inicio['version_id']}/descarga")
        self.assertEqual(s, 200)
        gid = completo["archivo"]["geometria_activa_id"]
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", datos={"ids": [gid]})
        self.assertFalse(meta["geometrias"][gid]["activa"])
        self.geometria_completa(gid)


    # -- authorization and non-disclosure ------------------------------------------

    def _recursos(self, terreno, login="ana"):
        """A finalized KMZ (version, attachment, attempt, geometry) in `terreno`."""
        inicio, completo = self.archivo_completo(kmz("poligono_simple"), "kmz", login=login, terreno=terreno)
        return {"vid": inicio["version_id"], "aid": inicio["archivo_id"],
                "iid": completo["intento"]["id"], "gid": completo["archivo"]["geometria_activa_id"],
                "rev": completo["archivo"]["revision"]}

    def _llamadas(self, r):
        """Every resource-addressed route, as (label, method, path, body, binary)."""
        return [
            ("contenido", "PUT", f"/api/archivos/versiones/{r['vid']}/contenido", b"%PDF-", False),
            ("completar", "POST", f"/api/archivos/versiones/{r['vid']}/completar", None, False),
            ("cancelar", "POST", f"/api/archivos/versiones/{r['vid']}/cancelar", None, False),
            ("procesar", "POST", f"/api/archivos/versiones/{r['vid']}/procesar", {"seleccion": None}, False),
            ("intentos", "GET", f"/api/archivos/versiones/{r['vid']}/intentos", None, False),
            ("descarga", "GET", f"/api/archivos/versiones/{r['vid']}/descarga", None, True),
            ("activar", "POST", f"/api/archivos/{r['aid']}/activar",
             {"version_id": r["vid"], "geometria_id": r["gid"], "expected_revision": r["rev"]}, False),
            ("retirar", "POST", f"/api/archivos/{r['aid']}/retirar", {"expected_revision": r["rev"]}, False),
            ("historial", "GET", f"/api/archivos/{r['aid']}/historial", None, False),
            ("versiones", "GET", f"/api/archivos/{r['aid']}/versiones", None, False),
            ("intento", "GET", f"/api/archivos/intentos/{r['iid']}", None, False),
            ("fragmento", "GET", f"/api/archivos/geometrias/{r['gid']}/contenido?desde=0", None, True),
        ]

    def _llamar(self, login, metodo, ruta, cuerpo, binario):
        h = {"Idempotency-Key": "clave-ficticia-" + uuid.uuid4().hex}
        datos = None
        if isinstance(cuerpo, dict):
            datos = cuerpo
        elif cuerpo is not None:
            h["Content-Type"] = "application/pdf"
        return self.c.pedir(metodo, ruta, cookie=self.cookie(login) if login else None,
                            cuerpo=cuerpo if isinstance(cuerpo, bytes) else None, datos=datos,
                            cabeceras=h, binario=binario)

    def test_missing_and_out_of_scope_ids_are_byte_identical_on_every_route(self):
        fuera = self._recursos(self.ajeno)                  # admin-only terrain
        dentro = self._recursos(self.terreno)
        falso = {k: str(uuid.uuid4()) for k in ("vid", "aid", "iid", "gid")} | {"rev": 2}
        antes = {t: self.filas(t) for t in ("archivo", "archivo_version", "archivo_intento",
                                            "archivo_evento", "archivo_trabajo")}
        for (etiqueta, metodo, ruta, cuerpo, binario), (_, _, ruta_falsa, _, _), (_, _, ruta_dentro, _, _) \
                in zip(self._llamadas(fuera), self._llamadas(falso), self._llamadas(dentro)):
            with self.subTest(ruta=etiqueta):
                s1, _, b1 = self._llamar("olga", metodo, ruta, cuerpo, binario)        # out of scope
                s2, _, b2 = self._llamar("olga", metodo, ruta_falsa, cuerpo, binario)  # missing
                s3, _, b3 = self._llamar("omar", metodo, ruta_dentro, cuerpo, binario)  # no grant
                self.assertEqual((s1, b1), (404, b2))
                self.assertEqual((s3, b3), (404, b2))
                self.assertEqual(json.loads(b2), {"error": "El archivo no existe.",
                                                  "detalle": {"code": "not_found"}})
        for tabla, filas in antes.items():
            self.assertEqual(self.filas(tabla), filas, tabla)

    def test_dead_sessions_get_401_before_any_resource_check(self):
        r = self._recursos(self.terreno, login="olga")
        falso = {k: str(uuid.uuid4()) for k in ("vid", "aid", "iid", "gid")} | {"rev": 2}
        cambios = {
            "logout": lambda: self.sql("UPDATE team_session SET revoked_at = ? WHERE token_hash = ?",
                                       (db.now(), auth._token_hash(self.tokens["olga"]))),
            "expired": lambda: self.sql("UPDATE team_session SET expires_at = 0 WHERE token_hash = ?",
                                        (auth._token_hash(self.tokens["olga"]),)),
            "role": lambda: self.sql("UPDATE team_user SET rol = 'admin', credential_revision ="
                                     " credential_revision + 1 WHERE id = ?", (self.users["olga"]["id"],)),
            "deactivated": lambda: self.sql("UPDATE team_user SET active = 0 WHERE id = ?",
                                            (self.users["olga"]["id"],)),
        }
        for nombre, cambio in cambios.items():
            with self.subTest(cambio=nombre):
                self.sql("UPDATE team_user SET active = 1, rol = 'operador' WHERE id = ?",
                         (self.users["olga"]["id"],))
                with db.session() as conn:
                    self.tokens["olga"], _, _ = auth.login(conn, "olga", TEST_PASSWORD)
                cambio()
                respuestas = set()
                for (etq, metodo, ruta, cuerpo, binario), (_, _, falsa, _, _) in zip(
                        self._llamadas(r), self._llamadas(falso)):
                    for destino in (ruta, falsa):
                        s, _, b = self._llamar("olga", metodo, destino, cuerpo, binario)
                        self.assertEqual(s, 401, (nombre, etq))
                        respuestas.add(b)
                s, _, b = self.c.pedir("POST", "/api/archivos/geometrias/metadatos", cookie=self.cookie("olga"),
                                       datos={"ids": [r["gid"]]})
                self.assertEqual(s, 401)
                respuestas.add(b)
                self.assertEqual(len(respuestas), 1, "one identical unauthenticated answer")
        s, _, b = self.c.pedir("GET", f"/api/archivos/{r['aid']}/historial")
        self.assertEqual(s, 401)

    def test_grants_bases_admins_and_archive_policy(self):
        r1 = self._recursos(self.terreno, login="olga")
        r2 = self._recursos(self.terreno2, login="olga")    # second granted base
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", "olga",
                         {"ids": [r1["gid"], r2["gid"]]})
        self.assertEqual(sorted(meta["geometrias"]), sorted([r1["gid"], r2["gid"]]))
        s, _ = self.j("GET", f"/api/archivos/{r1['aid']}/historial", "beto")   # another admin
        self.assertEqual(s, 200)
        # Archived terrain: reads stay, writes are refused in scope.
        self.sql("UPDATE inventory_terrain SET archived_at = ? WHERE id = ?", (db.now(), self.terreno))
        s, h, _ = self.bajar(f"/api/archivos/versiones/{r1['vid']}/descarga", "olga")
        self.assertEqual(s, 200)
        s, err = self.iniciar(PDF, login="olga")
        self.assertEqual((s, err["detalle"]["code"]), (409, "terreno_archivado"))
        s, err = self.j("POST", f"/api/archivos/{r1['aid']}/retirar", "olga", {"expected_revision": r1["rev"]},
                        "retirar-archivado")
        self.assertEqual((s, err["detalle"]["code"]), (409, "terreno_archivado"))
        # Archived base: closed to operators (non-disclosing), readable by admins.
        self.sql("UPDATE inventory_terrain SET archived_at = NULL WHERE id = ?", (self.terreno,))
        self.sql("UPDATE maestra_base SET archived_at = ? WHERE id = ?", (db.now(), self.base))
        s, h, b = self.bajar(f"/api/archivos/versiones/{r1['vid']}/descarga", "olga")
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (404, "not_found"))
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", "olga", {"ids": [r1["gid"], r2["gid"]]})
        self.assertEqual((list(meta["geometrias"]), meta["no_disponibles"]), ([r2["gid"]], [r1["gid"]]))
        s, h, _ = self.bajar(f"/api/archivos/versiones/{r1['vid']}/descarga", "ana")
        self.assertEqual(s, 200)
        s, err = self.j("POST", f"/api/archivos/{r1['aid']}/retirar", "ana", {"expected_revision": r1["rev"]},
                        "retirar-base-archivada")
        self.assertEqual((s, err["detalle"]["code"]), (409, "base_archivada"))

    def test_pending_upload_stays_private_over_http(self):
        secreto = "privado-ficticio.pdf"
        s, pendiente = self.iniciar(PDF, login="olga", nombre=secreto)
        self.subir(pendiente["version_id"], PDF, "olga")
        for login in ("ana", "beto"):
            s, lista = self.j("GET", f"/api/inventario/terrenos/{self.terreno}/archivos", login)
            s, hist = self.j("GET", f"/api/archivos/{pendiente['archivo_id']}/historial", login)
            s, vers = self.j("GET", f"/api/archivos/{pendiente['archivo_id']}/versiones", login)
            s1, _, b1 = self.c.pedir("GET", f"/api/archivos/versiones/{pendiente['version_id']}/intentos",
                                     cookie=self.cookie(login))
            s2, _, b2 = self.bajar(f"/api/archivos/versiones/{pendiente['version_id']}/descarga", login)
            self.assertEqual((s1, s2), (404, 404))
            serializado = json.dumps([lista, hist, vers]) + b1.decode() + b2.decode()
            for valor in (secreto, pendiente["version_id"], self.users["olga"]["id"]):
                self.assertNotIn(valor, serializado, login)
        s, propia = self.j("GET", f"/api/archivos/{pendiente['archivo_id']}/versiones", "olga")
        self.assertEqual(propia["versiones"][0]["nombre_original"], secreto)

    # -- upload boundaries -----------------------------------------------------------

    def test_declared_and_actual_size_type_and_hash_boundaries(self):
        cero = hashlib.sha256(b"").hexdigest()
        for tipo, maximo in (("pdf", archivos.PDF_MAX), ("kmz", archivos.KMZ_MAX)):
            s, ok = self.iniciar(b"", tipo, tamano=maximo, sha=cero)
            self.assertEqual(s, 200, ok)
            s, err = self.iniciar(b"", tipo, tamano=maximo + 1, sha=cero)
            self.assertEqual((s, err["detalle"]["code"]), (400, "tamano_invalido"))
        # Actual KMZ body one byte over its type limit (inside the global body limit).
        s, inicio = self.iniciar(b"x", "kmz", tamano=1)
        s, err = self.subir(inicio["version_id"], b"P" * (archivos.KMZ_MAX + 1))
        self.assertEqual((s, err["detalle"]["code"]), (413, "tamano_excedido"))
        # Above the dispatcher's MAX_BODY: refused before the handler, body unread.
        s, inicio_pdf = self.iniciar(b"x", "pdf", tamano=1)
        with socket.create_connection(("127.0.0.1", self.json_srv.port), timeout=10) as sock:
            sock.sendall((f"PUT /api/archivos/versiones/{inicio_pdf['version_id']}/contenido HTTP/1.1\r\n"
                          f"Host: 127.0.0.1\r\nCookie: {self.cookie('ana')}\r\nContent-Type: application/pdf\r\n"
                          f"Content-Length: {app_module.MAX_BODY + 1}\r\n\r\n").encode())
            primera = sock.recv(65536).split(b"\r\n", 1)[0]
        self.assertIn(b" 413 ", primera)       # refused from Content-Length alone; body never read
        # Declared size +1 versus actual, wrong hash, wrong signature: terminal "fallido".
        for nombre, contenido, declarado, sha, codigo in (
                ("mas-uno", PDF, len(PDF) + 1, None, "tamano_no_coincide"),
                ("hash", PDF, None, hashlib.sha256(b"otro").hexdigest(), "sha256_no_coincide"),
                ("firma", b"no es un pdf", None, None, "firma_invalida")):
            with self.subTest(caso=nombre):
                s, inicio = self.iniciar(contenido, tamano=declarado, sha=sha)
                self.subir(inicio["version_id"], contenido)
                s, r = self.completar(inicio["version_id"])
                self.assertEqual((s, r["version"]["estado"], r["version"]["error"]["codigo"]),
                                 (200, "fallido", codigo))
                self.assertFalse(r["limpieza_pendiente"])
        # Equality: an exact declared size completes.
        inicio, r = self.archivo_completo(PDF)
        self.assertEqual(r["version"]["tamano"], len(PDF))

    def test_malformed_requests_are_controlled(self):
        s, inicio = self.iniciar(PDF)
        vid = inicio["version_id"]
        casos = [
            ("multipart", lambda: self.subir(vid, b"--x\r\n", tipo_contenido="multipart/form-data; boundary=x"),
             415, "tipo_contenido_invalido"),
            ("json-body", lambda: self.subir(vid, b"{}", tipo_contenido="application/json"),
             415, "tipo_contenido_invalido"),
            ("bad-json", lambda: self.c.json("POST", f"/api/inventario/terrenos/{self.terreno}/archivos",
                                             cookie=self.cookie("ana"), cuerpo=b"{no",
                                             cabeceras={"Idempotency-Key": "k" * 10}),
             400, "cuerpo_invalido"),
            ("no-key", lambda: self.c.json("POST", f"/api/inventario/terrenos/{self.terreno}/archivos",
                                           cookie=self.cookie("ana"),
                                           datos={"tipo": "pdf", "nombre_original": "a.pdf",
                                                  "tamano_declarado": 1, "sha256_declarado": "0" * 64}),
             400, "idempotencia_invalida"),
            ("bad-name", lambda: self.iniciar(PDF, nombre="../x.pdf"), 400, "nombre_invalido"),
            ("bad-type", lambda: self.iniciar(PDF, tipo="exe"), 400, "tipo_invalido"),
            ("cursor", lambda: self.j("GET", f"/api/inventario/terrenos/{self.terreno}/archivos?cursor=x"),
             400, "cursor_invalido"),
            ("limite-0", lambda: self.j("GET", f"/api/archivos/{inicio['archivo_id']}/historial?limite=0"),
             400, "limite_invalido"),
            ("limite-101", lambda: self.j("GET", f"/api/archivos/{inicio['archivo_id']}/versiones?limite=101"),
             400, "limite_invalido"),
            ("limite-abc", lambda: self.j("GET", f"/api/inventario/terrenos/{self.terreno}/archivos?limite=abc"),
             400, "limite_invalido"),
            ("version-cursor", lambda: self.j("GET", f"/api/archivos/{inicio['archivo_id']}/versiones?cursor=-1"),
             400, "cursor_invalido"),
            ("seleccion", lambda: self.j("POST", f"/api/archivos/versiones/{vid}/procesar",
                                         datos={"seleccion": "1"}, clave="sel-ficticia"),
             400, "seleccion_invalida"),
            ("revision", lambda: self.j("POST", f"/api/archivos/{inicio['archivo_id']}/retirar",
                                        datos={"expected_revision": "1"}, clave="rev-ficticia"),
             400, "revision_invalida"),
        ]
        for nombre, llamada, estado, codigo in casos:
            with self.subTest(caso=nombre):
                s, r = llamada()
                self.assertEqual((s, r["detalle"]["code"]), (estado, codigo))

    def test_truncated_upload_stages_nothing(self):
        s, inicio = self.iniciar(PDF)
        clave_temporal = self.filas("archivo_version", "id = ?", (inicio["version_id"],))[0]["clave_temporal"]
        with socket.create_connection(("127.0.0.1", self.json_srv.port), timeout=10) as sock:
            cabecera = (f"PUT /api/archivos/versiones/{inicio['version_id']}/contenido HTTP/1.1\r\n"
                        f"Host: 127.0.0.1\r\nCookie: {self.cookie('ana')}\r\n"
                        "Content-Type: application/pdf\r\nContent-Length: 1000\r\n\r\n")
            sock.sendall(cabecera.encode() + PDF[:10])
            sock.shutdown(socket.SHUT_WR)               # the client disconnects mid-body
            respuesta = b""
            while True:
                parte = sock.recv(65536)
                if not parte:
                    break
                respuesta += parte
        self.assertIn(b" 400 ", respuesta.split(b"\r\n", 1)[0])
        self.assertIn(b"cuerpo_incompleto", respuesta)
        self.assertIsNone(self.store.tamano_de(clave_temporal))

    # -- geometry metadata -------------------------------------------------------------

    def test_geometry_metadata_batch_order_dedupe_and_validation(self):
        mio = self._recursos(self.terreno, login="olga")
        ajeno = self._recursos(self.ajeno)
        falta = str(uuid.uuid4())
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", "olga",
                         {"ids": [falta, mio["gid"], ajeno["gid"], mio["gid"].upper(), falta]})
        self.assertEqual(s, 200)
        self.assertEqual(list(meta["geometrias"]), [mio["gid"]])
        self.assertEqual(meta["no_disponibles"], [falta, ajeno["gid"]])
        d = meta["geometrias"][mio["gid"]]
        self.assertEqual(set(d), {"id", "archivo_id", "archivo_version_id", "terreno_id", "intento_id",
                                  "bbox", "punto_interior", "partes", "huecos", "vertices",
                                  "area_aproximada_m2", "utilizable", "activa", "bytes", "sha256",
                                  "fragmento_bytes", "fragmentos", "creado_en"})
        cincuenta = [str(uuid.uuid4()) for _ in range(50)]
        s, r = self.j("POST", "/api/archivos/geometrias/metadatos", "olga", {"ids": cincuenta})
        self.assertEqual((s, len(r["no_disponibles"])), (200, 50))
        for nombre, cuerpo, estado, codigo in (
                ("51", {"ids": cincuenta + [str(uuid.uuid4())]}, 400, "ids_invalidos"),
                ("empty", {"ids": []}, 400, "ids_invalidos"),
                ("not-list", {"ids": "x"}, 400, "ids_invalidos"),
                ("not-uuid", {"ids": ["x" * 36]}, 400, "ids_invalidos"),
                ("number", {"ids": [5]}, 400, "ids_invalidos"),
                ("oversized", {"ids": [mio["gid"]], "relleno": "x" * 17000}, 413, "solicitud_demasiado_grande")):
            with self.subTest(caso=nombre):
                s, r = self.j("POST", "/api/archivos/geometrias/metadatos", "olga", cuerpo)
                self.assertEqual((s, r["detalle"]["code"]), (estado, codigo))
        # The worst-case envelope (50 authorized descriptors) stays under 128 KiB.
        with db.session() as conn:
            row = archivos.repo.geometry_resource(conn, mio["gid"])
        largo = dict(row, area_aproximada_m2=-1.2345678901234567e300, bbox_oeste=-179.99999999999997,
                     bbox_sur=-89.99999999999997, bbox_este=-179.99999999999997, bbox_norte=-89.99999999999997,
                     punto_lon=-179.99999999999997, punto_lat=-89.99999999999997, partes=10**9,
                     huecos=10**9, vertices=10**9, bytes_geojson=16 * 1024 * 1024)
        sobre = {"geometrias": {str(uuid.uuid4()): archivos._geometry_meta(dict(largo, id=str(uuid.uuid4())))
                                for _ in range(50)}, "no_disponibles": []}
        self.assertLess(len(json.dumps(sobre, ensure_ascii=False).encode()), archivos.GEOMETRY_META_RESPONSE_MAX)

    def test_metadata_post_needs_its_read_only_exemption(self):
        mio = self._recursos(self.terreno)
        if not URL or not os.environ.get("ARA_MAP_DATABASE_URL"):
            with db.session() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with patch.dict(os.environ, {"ARA_MAP_READ_ONLY": "1"}):
            s, r = self.j("POST", "/api/archivos/geometrias/metadatos", datos={"ids": [mio["gid"]]})
            self.assertEqual(s, 403)
            with patch.object(app_module, "READ_ONLY_POSTS", app_module.READ_ONLY_POSTS | api.POSTS_DE_LECTURA):
                s, r = self.j("POST", "/api/archivos/geometrias/metadatos", datos={"ids": [mio["gid"]]})
                self.assertEqual((s, list(r["geometrias"])), (200, [mio["gid"]]))
                s, r = self.completar(mio["vid"])
                self.assertEqual(s, 403)

    # -- geometry chunks -----------------------------------------------------------------

    def _reemplazar_geojson(self, gid, texto):
        cuerpo = texto.encode("utf-8")
        self.sql("UPDATE geometria SET geojson = ?, bytes_geojson = ?, sha256_geojson = ? WHERE id = ?",
                 (texto, len(cuerpo), hashlib.sha256(cuerpo).hexdigest(), gid))
        return cuerpo

    def _geojson_de(self, objetivo_bytes, relleno="1"):
        """A valid MultiPolygon text of exactly `objetivo_bytes` UTF-8 bytes."""
        cabeza = '{"type":"MultiPolygon","coordinates":[[[[-100.4,20.6],[-100.3,20.6],[-100.3,20.7],[-100.4,20.6]]]],"x":"'
        cola = '"}'
        resto = objetivo_bytes - len(cabeza.encode()) - len(cola.encode())
        return cabeza + relleno * (resto // len(relleno.encode())) + cola

    def test_chunks_are_exact_bytes_across_utf8_boundaries_and_offsets_are_strict(self):
        r = self._recursos(self.terreno, login="olga")
        cabeza = self._geojson_de(0)[:-2]
        # Place a two-byte "é" so that it straddles the first chunk boundary.
        antes = CHUNK - 1 - len(cabeza.encode())
        texto = cabeza + "a" * antes + "é" + "b" * (CHUNK // 2) + '"}'
        cuerpo = self._reemplazar_geojson(r["gid"], texto)
        datos, cabeceras = self.geometria_completa(r["gid"], "olga")
        self.assertEqual(datos, cuerpo)
        self.assertEqual(len(cabeceras), 2)
        self.assertEqual(cabeceras[0]["X-Geometria-Longitud"], str(CHUNK))
        self.assertEqual(cabeceras[0]["Cache-Control"], "private, no-store")
        self.assertEqual(cabeceras[0]["Content-Type"], "application/octet-stream")
        s, _, primero = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde=0", "olga")
        self.assertEqual(primero[-1:], "é".encode()[:1])            # a byte, not a decoded string
        self.assertEqual(json.loads(datos.decode("utf-8"))["type"], "MultiPolygon")
        for desde in ("1", str(CHUNK - 1), "-1", "abc", "+0", str(2 * CHUNK), str(16 * 1024 * 1024),
                      "9999999999"):
            with self.subTest(desde=desde):
                s, _, b = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde={desde}", "olga")
                self.assertEqual((s, json.loads(b)["detalle"]["code"]), (400, "desplazamiento_invalido"))

    def test_serialization_ceiling_and_corrupt_bodies(self):
        r = self._recursos(self.terreno)
        tope = self._reemplazar_geojson(r["gid"], self._geojson_de(archivos.GEOMETRY_BODY_MAX))
        datos, cabeceras = self.geometria_completa(r["gid"])
        self.assertEqual((len(datos), len(cabeceras)), (archivos.GEOMETRY_BODY_MAX, 32))
        self.assertEqual(datos, tope)
        self._reemplazar_geojson(r["gid"], self._geojson_de(archivos.GEOMETRY_BODY_MAX + 1))
        s, _, b = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde=0")
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (503, "geometria_inconsistente"))
        # Same length, different bytes: middle chunks still match the stored text,
        # but the final chunk is refused, so the object never looks complete.
        bueno = self._reemplazar_geojson(r["gid"], self._geojson_de(3 * CHUNK))
        self.sql("UPDATE geometria SET geojson = ? WHERE id = ?",
                 (bueno.decode().replace("1", "2", 1), r["gid"]))
        s, _, _ = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde={CHUNK}")
        self.assertEqual(s, 200)
        s, _, b = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde={2 * CHUNK}")
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (503, "geometria_inconsistente"))
        # Different length from the recorded one: every chunk is refused.
        self.sql("UPDATE geometria SET geojson = ? WHERE id = ?", (bueno.decode() + " ", r["gid"]))
        s, _, b = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde=0")
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (503, "geometria_inconsistente"))

    def test_replacement_retirement_and_revocation_between_chunks(self):
        r = self._recursos(self.terreno, login="olga")
        original = self._reemplazar_geojson(r["gid"], self._geojson_de(3 * CHUNK + 17))
        s, h0, c0 = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde=0", "olga")
        nuevo, completo = self.archivo_completo(kmz("multiparte"), "kmz", login="olga")   # replaces the layer
        self.assertNotEqual(completo["archivo"]["geometria_activa_id"], r["gid"])
        s, h1, c1 = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde={CHUNK}", "olga")
        self.assertEqual(s, 200)
        self.j("POST", f"/api/archivos/{r['aid']}/retirar", "olga",
               {"expected_revision": completo["archivo"]["revision"]}, "retirar-entre-trozos")
        s, h2, c2 = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde={2 * CHUNK}", "olga")
        self.assertEqual(s, 200)
        self.assertEqual(c0 + c1 + c2, original[:3 * CHUNK])
        self.sql("DELETE FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?",
                 (self.base, self.users["olga"]["id"]))
        s, _, b = self.bajar(f"/api/archivos/geometrias/{r['gid']}/contenido?desde={3 * CHUNK}", "olga")
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (404, "not_found"))

    def test_parser_limit_geometry_is_delivered_within_the_bounds(self):
        contenido = kmz_de_kml(kml_limite())
        inicio, completo = self.archivo_completo(contenido, "kmz", nombre="limite-ficticio.kmz")
        self.assertEqual(completo["intento"]["resultado"], "listo", completo["intento"])
        gid = completo["archivo"]["geometria_activa_id"]
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", datos={"ids": [gid]})
        d = meta["geometrias"][gid]
        self.assertEqual((d["vertices"], d["partes"]), (100_000, 20_000))
        self.assertLess(d["bytes"], archivos.GEOMETRY_BODY_MAX)
        datos, cabeceras = self.geometria_completa(gid)
        self.assertEqual(len(cabeceras), d["fragmentos"])
        self.assertEqual(len(json.loads(datos)["coordinates"]), 20_000)
        self.medidas_limite = {"kmz_bytes": len(contenido), "geojson_bytes": d["bytes"],
                               "fragmentos": d["fragmentos"]}

    # -- races, busy and ambiguous completion ------------------------------------------

    def test_scope_loss_during_slow_completion_writes_nothing(self):
        s, inicio = self.iniciar(PDF, login="olga")
        self.subir(inicio["version_id"], PDF, "olga")
        real = archivos._verify_final

        def lento(*args, **kwargs):
            resultado = real(*args, **kwargs)
            self.sql("DELETE FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?",
                     (self.base, self.users["olga"]["id"]))
            return resultado

        with patch.object(archivos, "_verify_final", lento):
            s, r = self.completar(inicio["version_id"], "olga")
        self.assertEqual((s, r["detalle"]["code"]), (404, "not_found"))
        v = self.filas("archivo_version", "id = ?", (inicio["version_id"],))[0]
        self.assertEqual(v["estado"], "subiendo")
        self.assertEqual(self.filas("archivo_evento", "archivo_version_id = ? AND accion <> 'subida_iniciada'",
                                    (inicio["version_id"],)), [])
        self.assertEqual(list(self.store.listar("final/")), [])

    def test_finalization_boundary_first_then_revocation_then_denied_replay(self):
        s, inicio = self.iniciar(PDF, login="olga")
        self.subir(inicio["version_id"], PDF, "olga")
        dentro, seguir = threading.Event(), threading.Event()
        revocada = {}
        real = archivos.repo.finish_available

        def frontera(*args, **kwargs):
            resultado = real(*args, **kwargs)
            dentro.set()
            seguir.wait(10)
            return resultado

        def revocar():
            dentro.wait(10)
            try:
                with db.escritura() as conn:
                    conn.execute("DELETE FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?",
                                 (self.base, self.users["olga"]["id"]))
                revocada["despues"] = completado.is_set()
            except Exception as exc:  # recorded below
                revocada["error"] = exc

        completado = threading.Event()
        hilo = threading.Thread(target=revocar)
        hilo.start()
        with patch.object(archivos.repo, "finish_available", frontera):
            temporizador = threading.Timer(0.3, seguir.set)
            temporizador.start()
            s, r = self.completar(inicio["version_id"], "olga")
            completado.set()
        hilo.join(15)
        self.assertEqual((s, r["version"]["estado"]), (200, "disponible"))
        self.assertNotIn("error", revocada)
        self.assertTrue(revocada["despues"], "the revocation waited for the finalization boundary")
        s, r = self.completar(inicio["version_id"], "olga")
        self.assertEqual((s, r["detalle"]["code"]), (404, "not_found"))

    def test_cancellation_and_retirement_racing_slow_work(self):
        s, inicio = self.iniciar(PDF, login="olga")
        self.subir(inicio["version_id"], PDF, "olga")
        real = archivos._verify_final

        def con_cancelacion(*args, **kwargs):
            resultado = real(*args, **kwargs)
            s2, c = self.j("POST", f"/api/archivos/versiones/{inicio['version_id']}/cancelar", "olga")
            self.assertEqual(s2, 200)
            return resultado

        with patch.object(archivos, "_verify_final", con_cancelacion):
            s, r = self.completar(inicio["version_id"], "olga")
        self.assertEqual((s, r["detalle"]["code"]), (409, "lease_perdido"))
        self.assertEqual(self.filas("archivo_version", "id = ?", (inicio["version_id"],))[0]["estado"], "cancelado")
        self.assertEqual(list(self.store.listar("final/")), [])
        # Retirement while a reprocess is parsing: the attempt is history only.
        uno, completo = self.archivo_completo(kmz("ambiguo_tres_lotes"), "kmz", login="olga")
        real_intento = archivos._attempt        # runs after parsing, outside any transaction
        retiro = []

        def con_retiro(*args, **kwargs):
            resultado = real_intento(*args, **kwargs)
            retiro.append(self.j("POST", f"/api/archivos/{uno['archivo_id']}/retirar", "olga",
                                 {"expected_revision": completo["archivo"]["revision"]}, "retiro-carrera"))
            return resultado

        with patch.object(archivos, "_attempt", con_retiro):
            s, sel = self.j("POST", f"/api/archivos/versiones/{uno['version_id']}/procesar", "olga",
                            {"seleccion": [0]}, "proceso-carrera")
        self.assertEqual(s, 200, sel)
        self.assertEqual(retiro[0][0], 200, retiro)
        self.assertIsNotNone(sel["archivo"]["retirado_en"])
        s, act = self.j("POST", f"/api/archivos/{uno['archivo_id']}/activar", "olga",
                        {"version_id": uno["version_id"], "geometria_id": sel["geometria_id"],
                         "expected_revision": sel["archivo"]["revision"]}, "activar-retirado")
        self.assertEqual((s, act["detalle"]["code"]), (409, "revision_conflictiva"))

    def test_busy_is_controlled_and_never_retried(self):
        s, inicio = self.iniciar(PDF)
        self.subir(inicio["version_id"], PDF)
        llamadas = {"n": 0}

        @contextmanager
        def ocupado(path=None):
            llamadas["n"] += 1
            raise db.OcupadoError()
            yield  # pragma: no cover

        with patch.object(db, "escritura", ocupado):
            s, r = self.completar(inicio["version_id"])
        self.assertEqual((s, r["detalle"]["code"], llamadas["n"]), (503, "ocupado", 1))
        s, r = self.completar(inicio["version_id"])
        self.assertEqual((s, r["version"]["estado"]), (200, "disponible"))

    def test_ambiguous_completion_is_resolved_by_replay(self):
        s, inicio = self.iniciar(PDF)
        self.subir(inicio["version_id"], PDF)
        real = db.escritura
        n = {"v": 0}

        @contextmanager
        def ambiguo(path=None):
            n["v"] += 1
            with real(path) as conn:
                yield conn
            if n["v"] == 2:
                raise RuntimeError("fictional acknowledgement loss")

        with patch.object(db, "escritura", ambiguo), patch("traceback.print_exc"):
            s, r = self.completar(inicio["version_id"])
        self.assertEqual((s, r["detalle"]["code"]), (500, "internal"))
        s, r = self.completar(inicio["version_id"])
        self.assertEqual((s, r["replay"], r["version"]["estado"]), (200, True, "disponible"))
        self.assertEqual(len(self.filas("archivo_version")), 1)
        self.assertEqual(len(list(self.store.listar("final/"))), 1)
        s, _, cuerpo = self.bajar(f"/api/archivos/versiones/{inicio['version_id']}/descarga")
        self.assertEqual(cuerpo, PDF)

    def test_store_not_configured_is_controlled(self):
        api.configurar_almacen(None)
        s, inicio = self.iniciar(PDF)
        s, r = self.subir(inicio["version_id"], PDF)
        self.assertEqual((s, r["detalle"]["code"]), (503, "almacen_no_configurado"))
        api.configurar_almacen(lambda: self.store)

    def test_cross_resource_ids_retry_deadline_and_busy_lease(self):
        uno, r1 = self.archivo_completo(kmz("ambiguo_tres_lotes"), "kmz")
        otro, r2 = self.archivo_completo(PDF)
        s, sel = self.j("POST", f"/api/archivos/versiones/{uno['version_id']}/procesar", datos={"seleccion": [0]},
                        clave="cruce-sel")
        cruces = [
            ("version-of-other-attachment", {"version_id": otro["version_id"], "geometria_id": sel["geometria_id"]},
             uno["archivo_id"], 404, "not_found"),
            ("attempt-id-as-version", {"version_id": sel["intento"]["id"], "geometria_id": sel["geometria_id"]},
             uno["archivo_id"], 404, "not_found"),
            ("geometry-of-other-version", {"version_id": uno["version_id"], "geometria_id": str(uuid.uuid4())},
             uno["archivo_id"], 409, "version_no_activable"),
            ("pdf-with-geometry", {"version_id": otro["version_id"], "geometria_id": sel["geometria_id"]},
             otro["archivo_id"], 409, "version_no_activable"),
        ]
        for nombre, cuerpo, aid, estado, codigo in cruces:
            with self.subTest(caso=nombre):
                s, r = self.j("POST", f"/api/archivos/{aid}/activar", datos={**cuerpo, "expected_revision": 1},
                              clave="cruce-" + nombre)
                self.assertEqual((s, r["detalle"]["code"]), (estado, codigo))
        for ruta in (f"/api/archivos/versiones/{sel['geometria_id']}/descarga",
                     f"/api/archivos/geometrias/{uno['version_id']}/contenido?desde=0"):
            s, _, b = self.bajar(ruta)
            self.assertEqual((s, json.loads(b)["detalle"]["code"]), (404, "not_found"))
        # KMZ download identity.
        s, h, b = self.bajar(f"/api/archivos/versiones/{uno['version_id']}/descarga")
        self.assertEqual((s, b, h["Content-Type"]), (200, kmz("ambiguo_tres_lotes"),
                                                     "application/vnd.google-earth.kmz"))
        # Storage outage during completion: retryable, then a full retry succeeds.
        s, inicio = self.iniciar(PDF)
        self.subir(inicio["version_id"], PDF)
        self.store.inyectar_falla("copiar")
        s, r = self.completar(inicio["version_id"])
        self.assertEqual((s, r["detalle"]["code"], r["detalle"]["reintentar"]), (503, "almacen_no_disponible", True))
        s, r = self.completar(inicio["version_id"])
        self.assertEqual((s, r["version"]["estado"]), (200, "disponible"))
        # A failed version is not downloadable, exactly like a missing one.
        s, mal = self.iniciar(b"no es un pdf")
        self.subir(mal["version_id"], b"no es un pdf")
        self.completar(mal["version_id"])
        s, _, b = self.bajar(f"/api/archivos/versiones/{mal['version_id']}/descarga")
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (404, "not_found"))
        # A live lease held by another completion: busy, never retried for the caller.
        s, ocupada = self.iniciar(PDF)
        self.subir(ocupada["version_id"], PDF)
        real = archivos._verify_final
        visto = []

        def segunda(*args, **kwargs):
            visto.append(self.completar(ocupada["version_id"]))
            return real(*args, **kwargs)

        with patch.object(archivos, "_verify_final", segunda):
            s, r = self.completar(ocupada["version_id"])
        self.assertEqual((s, r["version"]["estado"]), (200, "disponible"))
        self.assertEqual((visto[0][0], visto[0][1]["detalle"]["code"]), (409, "procesamiento_en_curso"))
        self.assertTrue(visto[0][1]["detalle"]["reintentar_despues_de"])
        # Completion deadline (60 min, equality expired) over HTTP.
        s, tarde = self.iniciar(PDF)
        self.subir(tarde["version_id"], PDF)
        self.reloj.avanzar(archivos.COMPLETE_SECONDS)
        s, r = self.completar(tarde["version_id"])
        self.assertEqual((s, r["detalle"]["code"]), (409, "subida_expirada"))
        s, r = self.subir(tarde["version_id"], PDF)
        self.assertEqual((s, r["detalle"]["code"]), (409, "subida_no_pendiente"))


class Disposicion(unittest.TestCase):
    """Content-Disposition stays one safe header whatever the stored name holds.

    The lifecycle already refuses control characters at start (nombre_invalido);
    this is the defense in depth for names that reach the header builder.
    """

    def test_control_characters_never_reach_the_header(self) -> None:
        h = api.disposicion("a\r\nSet-Cookie: x=1.pdf", "pdf")
        self.assertNotIn("\r", h)
        self.assertNotIn("\n", h)
        self.assertEqual(h, "attachment; filename=\"aSet-Cookie: x=1.pdf\"; "
                            "filename*=UTF-8''aSet-Cookie%3A%20x%3D1.pdf")

    def test_quotes_backslashes_and_separators_are_replaced_in_the_fallback(self) -> None:
        self.assertEqual(api.disposicion('x"y\\z;w.pdf', "pdf"),
                         "attachment; filename=\"x_y_z_w.pdf\"; filename*=UTF-8''x%22y%5Cz%3Bw.pdf")

    def test_unicode_keeps_its_utf8_form_and_gets_an_ascii_fallback(self) -> None:
        self.assertEqual(api.disposicion("地図", "kmz"),
                         "attachment; filename=\"archivo.kmz\"; filename*=UTF-8''%E5%9C%B0%E5%9B%B3")
        self.assertEqual(api.disposicion("...", "pdf"),
                         "attachment; filename=\"archivo.pdf\"; filename*=UTF-8''...")
        self.assertTrue(api.disposicion("Plano.KMZ", "kmz").startswith('attachment; filename="Plano.KMZ";'))
        self.assertTrue(api.disposicion("reporte", "pdf").startswith('attachment; filename="reporte.pdf";'))


class HTTPSQLite(HTTPChecks, unittest.TestCase):
    def preparar_bd(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        entorno = patch.dict(os.environ, {"ARA_MAP_DB": str(Path(self._dir.name) / "http.db")})
        entorno.start()
        self.addCleanup(entorno.stop)
        os.environ.pop("ARA_MAP_DATABASE_URL", None)


@unittest.skipUnless(URL, "No Postgres test connection configured")
class HTTPPostgres(HTTPChecks, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import psycopg
        from psycopg.conninfo import make_conninfo

        cls.schema = "test_ara_http_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.entorno = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.entorno.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

    @classmethod
    def tearDownClass(cls) -> None:
        import psycopg

        cls.entorno.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def preparar_bd(self) -> None:
        with postgres.session() as conn:
            rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
                                " AND tablename <> 'workspace_metadata'").fetchall()
            names = [row["tablename"] for row in rows]
            if names:
                conn.raw.execute("TRUNCATE " + ", ".join(f'"{n}"' for n in names)
                                 + " RESTART IDENTITY CASCADE")


if __name__ == "__main__":
    unittest.main()

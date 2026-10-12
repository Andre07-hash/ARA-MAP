"""M1 synthetic integration through the REAL cloud entry (api/index.py).

The Vercel handler class, unchanged, over a disposable Postgres schema, with
Team B's S3 store (fabrica_desde_entorno) against a local moto S3/STS server.
Credentials come from STS web identity with the token of each request's
`x-vercel-oidc-token` header. The header-to-ContextVar handoff is Team A's
(api/index.py is A-owned): this test stands it in with a subclass doing exactly
what the contract asks (fijar_token_oidc before dispatch, reset in finally).

Full-size files: a 25 MiB PDF (9 parts) and a 20 MiB KMZ (7 parts), every
request body under the entry's 4 MiB cap and every download response at most
3 MiB. Runs only with boto3, moto and ARA_MAP_TEST_DATABASE_URL (an isolated
development environment); skipped otherwise. moto is not AWS and this is not
Vercel: hosted OIDC delivery, spoofed headers, real IAM and checksum
enforcement remain hosted gates.
"""

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import json
import os
import sys
import threading
import unittest
import uuid
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import almacen_s3, archivos, auth, db, postgres
from server.api import archivos as api_archivos
from server.repo import maestra
from tests.support import TEST_PASSWORD
from tests.test_archivos import FIXTURES

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
TIENE_SDK = all(importlib.util.find_spec(m) is not None for m in ("boto3", "moto", "psycopg"))
RAIZ = Path(__file__).resolve().parents[1]
MiB = 1024 * 1024
BUCKET = "ara-archivos-nube-prueba"
ROL = "arn:aws:iam::123456789012:role/ara-map-preview"
CAP_PETICION = 4 * MiB


def pdf_completo() -> bytes:
    cabeza = b"%PDF-1.4\n% ficticio de prueba\n"
    relleno = hashlib.sha256(b"pdf").digest() * (archivos.PDF_MAX // 32 + 1)
    return (cabeza + relleno)[:archivos.PDF_MAX]


def kmz_de(nombre: str, total: int | None = None) -> bytes:
    """A KMZ from a fixture KML; with `total`, padded with a stored member to exactly that size."""
    kml = (FIXTURES / "kmz" / f"{nombre}.kml").read_bytes()

    def construir(relleno: int) -> bytes:
        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w") as zf:
            zf.writestr(zipfile.ZipInfo("doc.kml"), kml, compress_type=zipfile.ZIP_DEFLATED)
            if relleno:
                zf.writestr(zipfile.ZipInfo("files/relleno.bin"), b"\0" * relleno,
                            compress_type=zipfile.ZIP_STORED)
        return salida.getvalue()
    if total is None:
        return construir(0)
    sin = len(construir(1))
    datos = construir(total - sin + 1)
    assert len(datos) == total, (len(datos), total)
    return datos


@unittest.skipUnless(URL and TIENE_SDK,
                     "needs ARA_MAP_TEST_DATABASE_URL, boto3, moto and psycopg (isolated dev env)")
class NubeM1(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import psycopg
        from moto.server import ThreadedMotoServer
        from psycopg.conninfo import make_conninfo

        cls.esquema = "test_ara_nube_m1_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.esquema}"')
        cls.entorno = patch.dict(os.environ, {
            "ARA_MAP_DATABASE_URL": make_conninfo(URL, options=f"-c search_path={cls.esquema}"),
            # No AWS keys: S3 is reached only with STS credentials from the OIDC token.
            "AWS_ACCESS_KEY_ID": "", "AWS_SECRET_ACCESS_KEY": "", "AWS_DEFAULT_REGION": "us-east-1"})
        cls.entorno.start()
        os.environ.pop("AWS_ACCESS_KEY_ID")
        os.environ.pop("AWS_SECRET_ACCESS_KEY")
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
        cls.moto = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
        cls.moto.start()
        cls.endpoint = f"http://127.0.0.1:{cls.moto.get_host_and_port()[1]}"
        import boto3
        crudo = boto3.client("s3", endpoint_url=cls.endpoint, region_name="us-east-1",
                             aws_access_key_id="admin", aws_secret_access_key="admin")
        crudo.create_bucket(Bucket=BUCKET)
        crudo.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        cls.crudo = crudo
        cls.config = {almacen_s3.VARIABLE_BUCKET: BUCKET, almacen_s3.VARIABLE_REGION: "us-east-1",
                      almacen_s3.VARIABLE_ROL: ROL, almacen_s3.VARIABLE_ENDPOINT: cls.endpoint}
        spec = importlib.util.spec_from_file_location("vercel_index", RAIZ / "api" / "index.py")
        cls.index = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.index)

        class ConTokenOIDC(cls.index.handler):          # stands in for A's handoff
            def _dispatch(self, method):
                marca = almacen_s3.fijar_token_oidc(self.headers.get("x-vercel-oidc-token"))
                try:
                    return super()._dispatch(method)
                finally:
                    almacen_s3.restablecer_token_oidc(marca)

            def log_message(self, *args):
                pass
        cls.Handler = ConTokenOIDC
        cls._sembrar()
        cls.servidor = cls._arrancar()

    @classmethod
    def tearDownClass(cls) -> None:
        import psycopg
        cls.servidor.shutdown()
        cls.moto.stop()
        api_archivos.configurar_almacen(None)
        cls.entorno.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.esquema}" CASCADE')

    @classmethod
    def _arrancar(cls) -> ThreadingHTTPServer:
        """One "deployment": a fresh store factory and server instance."""
        api_archivos.configurar_almacen(almacen_s3.fabrica_desde_entorno(cls.config))
        servidor = ThreadingHTTPServer(("127.0.0.1", 0), cls.Handler)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        cls.puerto = servidor.server_address[1]
        return servidor

    @classmethod
    def _sembrar(cls) -> None:
        with db.escritura() as conn:
            cls.cuentas = {login: auth.create_user(conn, login, f"{login.capitalize()} Ficticia",
                                                   TEST_PASSWORD, iterations=1000, rol=rol)
                           for login, rol in (("ana", "admin"), ("olga", "operador"),
                                              ("omar", "operador"), ("otto", "operador"))}
            base = maestra.crear(conn, "Base Ficticia Nube", cls.cuentas["ana"])["id"]
            ahora = db.now()
            for login in ("olga", "omar"):
                conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                             " VALUES (?, ?, ?, ?)", (base, cls.cuentas[login]["id"], ahora,
                                                     cls.cuentas["ana"]["id"]))
            cls.terreno = str(uuid.uuid4())
            revision = str(uuid.uuid4())
            conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                         " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                         (cls.terreno, base, ahora, cls.cuentas["ana"]["id"], ahora,
                          cls.cuentas["ana"]["id"]))
            conn.execute("INSERT INTO inventory_revision (id, inventory_id, revision_number, terreno,"
                         " estado, municipio, lat, lon, base_id, created_at, created_by)"
                         " VALUES (?, ?, 1, 'Lote Ficticio Nube', 'Querétaro', 'Municipio Ficticio',"
                         " NULL, NULL, ?, ?, ?)", (revision, cls.terreno, base, ahora,
                                                  cls.cuentas["ana"]["id"]))
            conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?",
                         (revision, cls.terreno))

    # -- HTTP --------------------------------------------------------------------------

    def setUp(self) -> None:
        self.galletas: dict[str, str] = {}
        self.cuerpos_enviados: list[int] = []
        self.respuestas_binarias: list[int] = []

    def pedir(self, metodo, ruta, cuerpo=b"", login="olga", tipo="application/json",
              token="token-oidc-ficticio", clave=None):
        if login and login not in self.galletas:
            self.galletas[login] = self._entrar(login)
        cabeceras = {"Content-Type": tipo, "Content-Length": str(len(cuerpo))}
        if login:
            cabeceras["Cookie"] = self.galletas[login]
        if token:
            cabeceras["x-vercel-oidc-token"] = token
        if clave:
            cabeceras["Idempotency-Key"] = clave
        self.cuerpos_enviados.append(len(cuerpo))
        c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=120)
        c.request(metodo, ruta, body=cuerpo, headers=cabeceras)
        r = c.getresponse()
        datos = r.read()
        c.close()
        return r.status, dict(r.getheaders()), datos

    def j(self, metodo, ruta, datos=None, **kw):
        s, h, b = self.pedir(metodo, ruta, json.dumps(datos).encode() if datos is not None else b"", **kw)
        return s, json.loads(b) if b[:1] in (b"{", b"[") else b

    def _entrar(self, login):
        c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=30)
        cuerpo = json.dumps({"username": login, "password": TEST_PASSWORD}).encode()
        c.request("POST", "/api/login", body=cuerpo, headers={"Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        c.close()
        self.assertEqual(r.status, 200)
        return r.getheader("Set-Cookie").split(";", 1)[0]

    def subir(self, datos: bytes, tipo: str, login="olga", nombre=None) -> dict:
        s, inicio = self.j("POST", f"/api/inventario/terrenos/{self.terreno}/archivos", {
            "tipo": tipo, "nombre_original": nombre or f"ficticio.{tipo}",
            "tamano_declarado": len(datos), "sha256_declarado": hashlib.sha256(datos).hexdigest()},
            login=login, clave=str(uuid.uuid4()))
        self.assertEqual(s, 200, inicio)
        transferencia = inicio["transferencia"]
        parte = transferencia["parte_bytes"]
        for i in range(transferencia["partes"]):
            pieza = datos[i * parte:(i + 1) * parte]
            s, h, b = self.pedir("PUT", f"/api/archivos/versiones/{inicio['version_id']}/contenido"
                                 f"?parte={i}", pieza, login=login, tipo="application/octet-stream")
            self.assertEqual(s, 200, b[:300])
        s, completo = self.j("POST", f"/api/archivos/versiones/{inicio['version_id']}/completar",
                             login=login)
        self.assertEqual(s, 200, completo)
        return completo

    def bajar(self, version_id: str, login="olga") -> tuple[int, bytes]:
        datos, desde = b"", 0
        while True:
            s, h, b = self.pedir("GET", f"/api/archivos/versiones/{version_id}/descarga?desde={desde}",
                                 login=login)
            if s != 200:
                return s, b
            self.respuestas_binarias.append(len(b))
            self.assertEqual((h["Content-Type"], h["X-Archivo-Desde"], int(h["X-Archivo-Longitud"])),
                             ("application/octet-stream", str(desde), len(b)))
            datos += b
            if h["X-Archivo-Siguiente"] == "fin":
                self.assertEqual(hashlib.sha256(datos).hexdigest(), h["X-Archivo-Sha256"])
                return 200, datos
            desde = int(h["X-Archivo-Siguiente"])

    def assert_tamanos(self):
        self.assertTrue(self.cuerpos_enviados)
        self.assertLessEqual(max(self.cuerpos_enviados), CAP_PETICION)
        if self.respuestas_binarias:
            self.assertLessEqual(max(self.respuestas_binarias), archivos.PARTE_BYTES)

    # -- journeys ------------------------------------------------------------------------

    def test_a_full_size_pdf_round_trip_reads_whole_objects_per_slice(self):
        datos = pdf_completo()
        completo = self.subir(datos, "pdf")
        self.assertEqual(completo["version"]["estado"], "disponible")
        lecturas = []
        real = almacen_s3.AlmacenS3.leer

        def contar(this, clave, limite, bloque=65536):
            lectura = real(this, clave, limite, bloque)
            lecturas.append(lectura.tamano)
            return lectura
        with patch.object(almacen_s3.AlmacenS3, "leer", contar):
            s, bajado = self.bajar(completo["version"]["id"])
        self.assertEqual((s, bajado == datos), (200, True))
        self.assertEqual((len(lecturas), sum(lecturas)), (9, 9 * archivos.PDF_MAX))   # 225 MiB
        # Another authorized session reads the same bytes; an ungranted account cannot.
        self.assertEqual(self.bajar(completo["version"]["id"], login="omar")[1], datos)
        s, b = self.bajar(completo["version"]["id"], login="otto")
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (404, "not_found"))
        self.assert_tamanos()

    def test_a_full_size_kmz_activates_and_gives_a_boundary_without_xy(self):
        datos = kmz_de("poligono_simple", archivos.KMZ_MAX)
        self.assertEqual(len(datos), 20 * MiB)
        completo = self.subir(datos, "kmz")
        self.assertEqual((completo["version"]["estado"], completo["intento"]["resultado"],
                          completo["aplicada"]), ("disponible", "listo", True))
        s, terreno = self.j("GET", f"/api/inventario/terrenos/{self.terreno}")
        self.assertEqual(s, 200, terreno)
        ubicacion = terreno["terreno"]["ubicacion"]
        self.assertEqual((ubicacion["modo"], ubicacion["xy"]), ("geometria", "sin_dato"))
        geometria = ubicacion["geometria"]["id"]
        self.assertEqual(self.bajar(completo["version"]["id"])[1], datos)
        # Database geometry stays private to the scope.
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", {"ids": [geometria]}, login="otto")
        self.assertEqual(meta["no_disponibles"], [geometria])
        # An invalid replacement keeps the active boundary.
        roto = b"PK\x03\x04 no es un kmz completo"
        fallo = self.subir(roto + b"\0" * 100, "kmz")
        self.assertEqual(fallo["archivo"]["geometria_activa_id"], geometria)
        s, terreno = self.j("GET", f"/api/inventario/terrenos/{self.terreno}")
        self.assertEqual(terreno["terreno"]["ubicacion"]["geometria"]["id"], geometria)
        # Explicit selection and activation of a multi-candidate KMZ.
        varios = self.subir(kmz_de("ambiguo_tres_lotes"), "kmz")
        self.assertEqual((varios["intento"]["resultado"], varios["aplicada"]),
                         ("requiere_seleccion", False))
        s, sel = self.j("POST", f"/api/archivos/versiones/{varios['version']['id']}/procesar",
                        {"seleccion": [0]}, clave=str(uuid.uuid4()))
        self.assertEqual(s, 200, sel)
        s, act = self.j("POST", f"/api/archivos/{varios['archivo']['id']}/activar",
                        {"version_id": varios["version"]["id"], "geometria_id": sel["geometria_id"],
                         "expected_revision": varios["archivo"]["revision"]}, clave=str(uuid.uuid4()))
        self.assertEqual(s, 200, act)
        self.assertEqual(act["archivo"]["geometria_activa_id"], sel["geometria_id"])
        self.assert_tamanos()

    def test_missing_identity_and_a_new_deployment(self):
        completo = self.subir(b"%PDF-1.4 ficticio pequeno", "pdf")
        version = completo["version"]["id"]
        # "Redeploy": a new server and a fresh factory (no warm credentials) over
        # the same database and bucket.
        anterior = type(self).servidor
        anterior.shutdown()
        type(self).servidor = self._arrancar()
        self.galletas.clear()
        # The first exchange needs the request's OIDC token.
        s, h, b = self.pedir("GET", f"/api/archivos/versiones/{version}/descarga", token=None)
        self.assertEqual((s, json.loads(b)["detalle"]["code"]), (503, "almacen_no_configurado"), b)
        self.assertEqual(self.bajar(version), (200, b"%PDF-1.4 ficticio pequeno"))
        s, historial = self.j("GET", f"/api/archivos/{completo['archivo']['id']}/historial")
        self.assertEqual(s, 200)
        self.assertTrue(historial["eventos"])
        # Warm instance: the project identity's credentials serve later requests.
        s, _h, _b = self.pedir("GET", f"/api/archivos/versiones/{version}/descarga", token=None)
        self.assertEqual(s, 200)

    def test_out_of_scope_requests_do_not_reach_a_broken_store(self):
        completo = self.subir(b"%PDF-1.4 ambito", "pdf")
        version = completo["version"]["id"]
        roto = almacen_s3.fabrica_desde_entorno({**self.config, almacen_s3.VARIABLE_ROL: "malo"})
        api_archivos.configurar_almacen(roto)
        try:
            s, b = self.bajar(version, login="otto")
            self.assertEqual((s, json.loads(b)["detalle"]["code"]), (404, "not_found"))
            s, b = self.bajar(version)
            self.assertEqual((s, json.loads(b)["detalle"]["code"]), (503, "almacen_no_configurado"))
        finally:
            api_archivos.configurar_almacen(almacen_s3.fabrica_desde_entorno(self.config))


if __name__ == "__main__":
    sys.exit(unittest.main())

"""Microsoft connector on a real, disposable Postgres, through the cloud
adapter, against a LOCAL FAKE Microsoft (tests/fake_microsoft.py). This is
local evidence of the OAuth/credential/Graph logic; it is not evidence that
the real Microsoft services, app registration or a real workbook work.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import threading
import unittest
import uuid
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import auth, db, postgres
from server.api import excel as api_excel
from server.excel import microsoft
from tests.excel_support import BASICO, fila, libro
from tests.fake_microsoft import FakeMicrosoft
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
CONFIG = {"hoja": "Registro Análisis", "columna_id": "ID", "moneda": "USD"}


@unittest.skipUnless(URL, "No Postgres test connection configured")
class MicrosoftPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.fake = FakeMicrosoft()
        cls.schema = "test_ara_ms_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {
            "ARA_MAP_DATABASE_URL": make_conninfo(URL, options=f"-c search_path={cls.schema}"),
            "ARA_MAP_MS_CLIENT_ID": cls.fake.client_id, "ARA_MAP_MS_CLIENT_SECRET": cls.fake.secret,
            "ARA_MAP_MS_REDIRECT_URI": "https://ara.example/api/microsoft/callback",
            "ARA_MAP_MS_TEST_HOST": cls.fake.host,
            "ARA_MAP_TOKEN_KEY": "clave-de-prueba-ficticia-de-32-caracteres-o-mas",
            "ARA_MAP_TOKEN_KEY_VERSION": "prueba-1"})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
        spec = importlib.util.spec_from_file_location(
            "cloud_adapter_ms", Path(__file__).parents[1] / "api" / "index.py")
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
        cls.fake.cerrar()
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def setUp(self):
        with postgres.session() as conn:
            conn.raw.execute(
                "TRUNCATE excel_ejecucion, excel_version_fila, excel_identidad, excel_version,"
                " excel_configuracion, excel_fuente, excel_credencial, excel_autorizacion, excel_cuenta,"
                " inventory_operation_result, terreno, base, team_session, team_login_failure, team_user CASCADE")
            for n in ("ana", "beto"):
                auth.create_user(conn, n, n.capitalize(), TEST_PASSWORD, iterations=1000)
        self.fake.usuarios.clear()
        self.fake.archivos.clear()
        self.fake.carpetas.clear()
        self.fake.cola_status.clear()
        self.fake.redirigir_a = None
        self.fake.descargas_con_bearer = 0
        self.fake.usuario("dueno", "Dueño Ficticio")
        self.archivo = self.fake.archivo("dueno", "item-libro", "Terrenos.xlsx", libro(BASICO))
        self.jars = {n: self.login(n) for n in ("ana", "beto")}
        # The real Microsoft provider (not the in-memory fake) is under test.
        self.assertIs(api_excel.FABRICA, microsoft.fabrica)

    # -- HTTP helpers -------------------------------------------------------------
    def raw(self, method, path, body=None, headers=None):
        c = HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=60)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": "ara.example", **(headers or {})})
        r = c.getresponse()
        datos = r.read()
        c.close()
        return r.status, datos, {k.lower(): v for k, v in r.getheaders()}

    def call(self, method, path, body=None, user="ana", headers=None):
        status, datos, _ = self.raw(method, path, body, {**(headers or {}), **(self.jars[user] if user else {})})
        return status, json.loads(datos) if datos else None

    def login(self, name):
        status, _, h = self.raw("POST", "/api/login", {"username": name, "password": TEST_PASSWORD})
        self.assertEqual(status, 200)
        return {"Cookie": h["set-cookie"].split(";")[0]}

    def iniciar(self, user="ana"):
        status, _, h = self.raw("POST", "/api/microsoft/conectar", None, self.jars[user])
        self.assertEqual(status, 200)
        body = json.loads(_)
        cookie = h["set-cookie"]
        return body["url"], cookie.split(";")[0], cookie

    def volver(self, query, flujo):
        """Microsoft redirects the browser back: no session cookie (Strict)."""
        status, _, h = self.raw("GET", "/api/microsoft/callback?" + "&".join(f"{k}={v}" for k, v in query.items()),
                                headers={"Cookie": flujo} if flujo else {})
        return status, h

    def conectar_cuenta(self, user="ana", usuario_ms="dueno"):
        url, flujo, _ = self.iniciar(user)
        status, h = self.volver(self.fake.autorizar(url, usuario_ms), flujo)
        self.assertEqual((status, h["location"]), (303, "/#/bases?excel=conectado"))
        cuentas = self.call("GET", "/api/microsoft/estado")[1]["cuentas"]
        return next(c for c in cuentas if c["correo"] == f"{usuario_ms}@example.com")

    def conectar_fuente(self, cuenta, item="item-libro", drive="drive-dueno"):
        status, body = self.call("POST", "/api/excel/fuentes", {
            "cuenta_id": cuenta["id"], "drive_id": drive, "item_id": item, "nombre": "Conectada", **CONFIG},
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"})
        self.assertEqual(status, 200, body)
        return body["fuente"]

    def actualizar(self, fid, user="ana"):
        return self.call("POST", f"/api/excel/fuentes/{fid}/actualizar", {}, user,
                         headers={"Idempotency-Key": f"k-{uuid.uuid4()}"})[1]

    def cuentas_en_bd(self):
        with db.session() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM excel_cuenta").fetchone()["n"]

    # -- tests ----------------------------------------------------------------------
    def test_first_connection_end_to_end(self):
        estado = self.call("GET", "/api/microsoft/estado")[1]
        self.assertEqual(estado["conector"], {"disponible": True, "motivo": None})
        url, flujo, cookie = self.iniciar()
        for parte in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/api/microsoft/callback", "Max-Age=600"):
            self.assertIn(parte, cookie)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("scope=offline_access+User.Read+Files.Read", url)
        status, h = self.volver(self.fake.autorizar(url, "dueno"), flujo)
        self.assertEqual((status, h["location"]), (303, "/#/bases?excel=conectado"))
        self.assertEqual((h["cache-control"], h["referrer-policy"]), ("no-store", "no-referrer"))
        self.assertIn("Max-Age=0", h["set-cookie"])
        cuenta = self.call("GET", "/api/microsoft/estado")[1]["cuentas"][0]
        self.assertEqual((cuenta["tipo"], cuenta["requiere_reconexion"], cuenta["conectada_por"]["display_name"]),
                         ("personal", False, "Ana"))
        with db.session() as conn:
            cifrado = conn.execute("SELECT token_cifrado FROM excel_credencial").fetchone()["token_cifrado"]
        self.assertFalse(any(rt in cifrado for rt in self.fake.renovaciones))
        self.assertNotIn("token", json.dumps(self.call("GET", "/api/microsoft/estado")[1]).lower())

        lista = self.call("GET", f"/api/microsoft/cuentas/{cuenta['id']}/archivos")[1]["elementos"]
        self.assertEqual({(e["nombre"], e["carpeta"]) for e in lista}, {("Terrenos.xlsx", False), ("Documentos", True)})
        status, prev = self.call("POST", "/api/excel/vista-previa",
                                 {"cuenta_id": cuenta["id"], "drive_id": "drive-dueno", "item_id": "item-libro"})
        self.assertEqual((status, prev["id_sugerido"]), (200, "ID"))
        self.assertTrue(prev["archivo"]["web_url"].startswith("https://onedrive.live.com/"))

        f = self.conectar_fuente(cuenta)
        self.assertEqual(f["version_activa"]["filas"], 3)
        # Another employee edits the same workbook; Beto refreshes.
        self.archivo.poner(libro([fila("A-001", "Lote Alfa", 1_500_000), *BASICO[1:]]))
        r = self.actualizar(f["id"], "beto")
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["conteos"]["actualizados"]), ("ok", 1))
        self.assertGreater(self.fake.descargas, 0)
        self.assertEqual(self.fake.descargas_con_bearer, 0)  # the bearer never left Graph
        self.assertNotIn("/descarga/", json.dumps(r))

    def test_callback_defences(self):
        url, flujo, _ = self.iniciar()
        q = self.fake.autorizar(url, "dueno")
        self.assertEqual(self.volver({**q, "state": "otro"}, flujo)[1]["location"], "/#/bases?excel=error")
        self.assertEqual(self.volver(q, None)[1]["location"], "/#/bases?excel=error")
        self.assertEqual(self.volver(q, "ara_ms_flujo=" + "x" * 40)[1]["location"], "/#/bases?excel=error")
        self.assertEqual(self.cuentas_en_bd(), 0)
        self.assertEqual(self.volver(q, flujo)[1]["location"], "/#/bases?excel=conectado")
        self.assertEqual(self.volver(q, flujo)[1]["location"], "/#/bases?excel=error")  # replay
        self.assertEqual(self.cuentas_en_bd(), 1)
        # Expired.
        url, flujo, _ = self.iniciar()
        with db.session() as conn:
            conn.execute("UPDATE excel_autorizacion SET expira = 0")
        self.assertEqual(self.volver(self.fake.autorizar(url, "dueno"), flujo)[1]["location"], "/#/bases?excel=error")
        # Cancelled at Microsoft.
        url, flujo, _ = self.iniciar()
        estado_oauth = self.fake.autorizar(url, "dueno")["state"]
        self.assertEqual(self.volver({"error": "access_denied", "state": estado_oauth}, flujo)[1]["location"],
                         "/#/bases?excel=cancelado")
        # The callback is anonymous but only ever redirects.
        status, cuerpo, _ = self.raw("GET", "/api/microsoft/callback")
        self.assertEqual((status, cuerpo), (303, b""))

    def test_logout_during_flow_and_during_exchange_attach_nothing(self):
        url, flujo, _ = self.iniciar()
        q = self.fake.autorizar(url, "dueno")
        self.raw("POST", "/api/logout", None, self.jars["ana"])
        self.assertEqual(self.volver(q, flujo)[1]["location"], "/#/bases?excel=error")
        self.jars["ana"] = self.login("ana")
        url, flujo, _ = self.iniciar()
        q = self.fake.autorizar(url, "dueno")
        original = microsoft.canjear_codigo

        def y_mientras_tanto_se_desactiva(*a, **k):
            with db.session() as conn:
                auth.set_active(conn, "ana", False)
            return original(*a, **k)

        with patch.object(microsoft, "canjear_codigo", y_mientras_tanto_se_desactiva):
            self.assertEqual(self.volver(q, flujo)[1]["location"], "/#/bases?excel=error")
        self.assertEqual(self.cuentas_en_bd(), 0)

    def test_concurrent_callback_replay_attaches_once(self):
        url, flujo, _ = self.iniciar()
        q = self.fake.autorizar(url, "dueno")
        resultados = []
        hilos = [threading.Thread(target=lambda: resultados.append(self.volver(q, flujo)[1]["location"]))
                 for _ in range(3)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(20)
        self.assertEqual(sorted(resultados), ["/#/bases?excel=conectado"] + ["/#/bases?excel=error"] * 2)
        self.assertEqual(self.cuentas_en_bd(), 1)

    def test_account_switch_and_reconnect_same_account(self):
        primera = self.conectar_cuenta("ana", "dueno")
        self.fake.usuario("otra", "Otra Persona", tipo="business")
        segunda = self.conectar_cuenta("beto", "otra")
        self.assertNotEqual(primera["id"], segunda["id"])
        self.assertEqual(segunda["tipo"], "organizacion")
        de_nuevo = self.conectar_cuenta("beto", "dueno")
        self.assertEqual(de_nuevo["id"], primera["id"])
        self.assertEqual(de_nuevo["conectada_por"]["display_name"], "Beto")
        self.assertEqual(self.cuentas_en_bd(), 2)

    def test_revoked_grant_keeps_data_and_reconnects(self):
        cuenta = self.conectar_cuenta()
        f = self.conectar_fuente(cuenta)
        self.fake.usuarios["dueno"]["revocado"] = True
        r = self.actualizar(f["id"])
        self.assertEqual((r["ejecucion"]["estado"], r["ejecucion"]["error"]["codigo"]), ("error", "reconectar"))
        self.assertTrue(r["fuente"]["cuenta"]["requiere_reconexion"])
        self.assertEqual(r["fuente"]["version_activa"]["filas"], 3)
        self.fake.usuarios["dueno"]["revocado"] = False
        self.conectar_cuenta()
        self.archivo.poner(libro(BASICO[:2]))
        r = self.actualizar(f["id"])
        self.assertEqual((r["ejecucion"]["estado"], r["fuente"]["version_activa"]["numero"]), ("ok", 2))

    def test_token_refresh_is_serialized_across_two_sources(self):
        cuenta = self.conectar_cuenta()
        segundo = self.fake.archivo("dueno", "item-dos", "Otro.xlsx", libro(BASICO))
        f1, f2 = self.conectar_fuente(cuenta), self.conectar_fuente(cuenta, item="item-dos")
        self.archivo.poner(libro(BASICO[:2]))
        segundo.poner(libro(BASICO[:1]))
        with db.session() as conn:
            antes = conn.execute("SELECT generacion FROM excel_credencial").fetchone()["generacion"]
        usadas = self.fake.renovaciones_usadas
        resultados = {}
        hilos = [threading.Thread(target=lambda k=k, fid=fid: resultados.update({k: self.actualizar(fid, k)}))
                 for k, fid in (("ana", f1["id"]), ("beto", f2["id"]))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(60)
        self.assertEqual({k: v["ejecucion"]["estado"] for k, v in resultados.items()}, {"ana": "ok", "beto": "ok"})
        with db.session() as conn:
            fila_cred = conn.execute("SELECT generacion, ocupada_por FROM excel_credencial").fetchone()
        self.assertEqual(self.fake.renovaciones_usadas - usadas, 2)
        self.assertEqual((fila_cred["generacion"], fila_cred["ocupada_por"]), (antes + 2, None))
        self.assertEqual(self.actualizar(f1["id"])["ejecucion"]["estado"], "sin_cambios")  # latest token works

    def test_throttling_errors_and_redirect_policy(self):
        cuenta = self.conectar_cuenta()
        f = self.conectar_fuente(cuenta)
        self.archivo.poner(libro(BASICO[:2]))
        self.fake.cola_status[:] = [(429, {"Retry-After": "0"})]
        self.assertEqual(self.actualizar(f["id"])["ejecucion"]["estado"], "ok")
        self.fake.cola_status[:] = [(503, {"Retry-After": "0"})] * 50  # endless 503s: bounded retries
        r = self.actualizar(f["id"])
        self.assertEqual(r["ejecucion"]["error"]["codigo"], "no_disponible")
        self.assertEqual(50 - len(self.fake.cola_status), 1 + microsoft.MAX_REINTENTOS)
        self.fake.cola_status.clear()
        self.fake.redirigir_a = "http://evil.example/descarga/x"
        self.archivo.poner(libro(BASICO[:1]))
        r = self.actualizar(f["id"])
        self.assertEqual(r["ejecucion"]["error"]["codigo"], "no_disponible")
        self.assertNotIn("evil", json.dumps(r))
        self.fake.redirigir_a = None
        del self.fake.archivos[("drive-dueno", "item-libro")]
        r = self.actualizar(f["id"])
        self.assertEqual(r["ejecucion"]["error"]["codigo"], "no_encontrado")
        self.assertEqual(r["fuente"]["version_activa"]["numero"], 2)
        self.assertEqual(self.fake.descargas_con_bearer, 0)

    def test_restores_require_reconnect_and_dr_invalidation(self):
        cuenta = self.conectar_cuenta()
        f = self.conectar_fuente(cuenta)
        # Content restore: postgres.TABLES has no credentials, so they are absent.
        payload = {}
        with postgres.session() as conn:
            for tabla in postgres.TABLES:
                payload[tabla] = [dict(r) for r in conn.execute(f"SELECT * FROM {tabla}")]
            conn.execute("DELETE FROM excel_credencial")
        self.assertNotIn("excel_credencial", payload)
        self.assertEqual(len(payload["excel_version_fila"]), 3)
        estado = self.call("GET", f"/api/excel/fuentes/{f['id']}")[1]["fuente"]
        self.assertTrue(estado["cuenta"]["requiere_reconexion"])
        self.assertEqual(self.actualizar(f["id"])["ejecucion"]["error"]["codigo"], "reconectar")
        self.conectar_cuenta()
        self.assertEqual(self.actualizar(f["id"])["ejecucion"]["estado"], "sin_cambios")
        # Private DR restore: invalidate sessions, pending flows, credentials.
        self.iniciar()
        from scripts import invalidar_restauracion
        with patch.dict(os.environ, {"RESTAURADA_URL": os.environ["ARA_MAP_DATABASE_URL"]}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(invalidar_restauracion.main(["--url-env", "RESTAURADA_URL", "--olvidar-credenciales"]), 0)
        self.assertEqual(self.call("GET", "/api/excel/fuentes")[0], 401)
        with db.session() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM excel_autorizacion").fetchone()["n"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM excel_credencial").fetchone()["n"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM excel_version").fetchone()["n"], 1)

    def test_missing_or_changed_key_disables_safely(self):
        cuenta = self.conectar_cuenta()
        f = self.conectar_fuente(cuenta)
        with patch.dict(os.environ, {"ARA_MAP_TOKEN_KEY_VERSION": "prueba-2"}):
            r = self.actualizar(f["id"])
            self.assertEqual(r["ejecucion"]["error"]["codigo"], "reconectar")
        with patch.dict(os.environ, {"ARA_MAP_TOKEN_KEY": ""}):
            estado = self.call("GET", "/api/microsoft/estado")[1]["conector"]
            self.assertFalse(estado["disponible"])
            self.assertEqual(self.call("POST", "/api/microsoft/conectar")[1]["detalle"]["code"], "no_configurado")
            self.assertEqual(self.call("GET", "/api/bases")[0], 200)  # the rest of the app is unaffected
            self.assertEqual(self.call("GET", f"/api/bases/{f['base_id']}/terrenos")[0], 200)


if __name__ == "__main__":
    unittest.main()

"""The hosted entry point (server/hosted.py) through a proxy-shaped request path.

The platform's proxy ends TLS and forwards plain HTTP with the public Host, so
these tests speak plain HTTP to the real hosted handler with that Host. The
signed-in cases run on a throwaway SQLite file by patching only the readiness
check, as tests/test_cloud.py does; the refusal to start without Postgres is
tested on the configuration itself.
"""
import json
import re
import socket
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import hosted
from server.almacen import AlmacenNoConfiguradoError
from server.api import archivos as api_archivos
from tests.support import TEST_PASSWORD, TempDatabase, create_user

HOST = "piloto.example.test"
MIB = 1024 * 1024


class Configuracion(unittest.TestCase):
    def test_refuses_to_start_without_postgres(self):
        with self.assertRaises(SystemExit) as salida:
            hosted.configuracion({"ARA_MAP_HOST_PUBLICO": HOST, "ARA_MAP_DB": "/tmp/x.db"})
        self.assertIn("nunca usa un archivo SQLite", str(salida.exception))

    def test_refuses_to_start_without_one_plain_public_host(self):
        for valor in (None, "", "https://piloto.example.test", "piloto.example.test/ruta",
                      "a b", "*.example.test", "piloto.example.test:443"):
            entorno = {"ARA_MAP_DATABASE_URL": "postgresql://ficticio"}
            if valor is not None:
                entorno["ARA_MAP_HOST_PUBLICO"] = valor
            with self.subTest(valor=valor), self.assertRaises(SystemExit):
                hosted.configuracion(entorno)

    def test_host_and_port_come_from_the_environment_only(self):
        entorno = {"ARA_MAP_DATABASE_URL": "postgresql://ficticio", "PORT": "10123",
                   "ARA_MAP_HOST_PUBLICO": " Piloto.Example.Test "}
        self.assertEqual(hosted.configuracion(entorno), (HOST, 10123))
        del entorno["ARA_MAP_HOST_PUBLICO"]
        entorno["RENDER_EXTERNAL_HOSTNAME"] = "otro.example.test"  # set by the platform
        self.assertEqual(hosted.configuracion(entorno), ("otro.example.test", 10123))
        for puerto in ("0", "70000", "80a", ""):
            with self.subTest(puerto=puerto), self.assertRaises(SystemExit):
                hosted.configuracion({**entorno, "PORT": puerto})

    def test_refuses_a_database_at_another_schema_version(self):
        class Sesion:
            def __enter__(self):
                return object()

            def __exit__(self, *_):
                return False

        with patch("server.hosted.postgres.session", Sesion), \
                patch("server.hosted.postgres.schema_version", return_value=9), \
                self.assertRaises(SystemExit) as salida:
            hosted.comprobar_esquema()
        self.assertIn("scripts/esquema.py", str(salida.exception))
        with patch("server.hosted.postgres.session", Sesion), \
                patch("server.hosted.postgres.schema_version", return_value=hosted.db.SCHEMA_VERSION):
            hosted.comprobar_esquema()

    def configurado(self, **almacen):
        entorno = {"ARA_MAP_DATABASE_URL": "postgresql://ficticio", "ARA_MAP_HOST_PUBLICO": HOST,
                   "ARA_MAP_ARCHIVOS": "/tmp/no-se-usa", **almacen}
        self.addCleanup(api_archivos.configurar_almacen, None)
        with patch.object(hosted.HostedHandler, "HOST_PUBLICO", ""):
            hosted.configurar(entorno)

    def test_no_byte_store_is_wired_from_the_host_disk(self):
        self.configurado()
        with self.assertRaises(AlmacenNoConfiguradoError):
            api_archivos._almacen_actual()

    def test_incomplete_or_malformed_storage_settings_defer_to_a_file_error(self):
        # Starting never fails on them, and nothing but file content is affected.
        for almacen in ({"ARA_MAP_ARCHIVOS_SUPABASE_URL": "https://ficticio.example.test"},
                        {"ARA_MAP_ARCHIVOS_SUPABASE_URL": "http://ficticio.example.test",
                         "ARA_MAP_ARCHIVOS_SUPABASE_KEY": "clave-ficticia",
                         "ARA_MAP_ARCHIVOS_SUPABASE_BUCKET": "piloto"},
                        {"ARA_MAP_ARCHIVOS_SUPABASE_URL": "https://ficticio.example.test",
                         "ARA_MAP_ARCHIVOS_SUPABASE_KEY": "clave ficticia",
                         "ARA_MAP_ARCHIVOS_SUPABASE_BUCKET": "Piloto Con Espacios"}):
            with self.subTest(almacen=sorted(almacen)), patch("server.almacen_supabase._registro"):
                self.configurado(**almacen)
                with self.assertRaises(AlmacenNoConfiguradoError):
                    api_archivos._almacen_actual()

    def test_complete_settings_wire_the_private_store_without_any_provider_call(self):
        completo = {"ARA_MAP_ARCHIVOS_SUPABASE_URL": "https://ficticio.example.test",
                    "ARA_MAP_ARCHIVOS_SUPABASE_KEY": "clave-ficticia",
                    "ARA_MAP_ARCHIVOS_SUPABASE_BUCKET": "piloto-ficticio"}
        with patch("server.almacen_supabase._construir", return_value="el almacén") as construir:
            self.configurado(**completo)
            construir.assert_not_called()  # nothing is built at start
            self.assertEqual(api_archivos._almacen_actual(), "el almacén")
        construir.assert_called_once_with("https://ficticio.example.test/storage/v1", "clave-ficticia",
                                          "piloto-ficticio")


class Despliegue(unittest.TestCase):
    """The reviewed deployment files say what the checklist promises."""

    raiz = Path(__file__).parents[1]

    def test_blueprint_is_free_manual_and_holds_no_secret(self):
        texto = (self.raiz / "render.yaml").read_text(encoding="utf-8")
        for linea in ("plan: free", 'autoDeployTrigger: "off"', "startCommand: python -m server.hosted",
                      "healthCheckPath: /healthz", "buildCommand: pip install -r requirements-hosted.txt"):
            self.assertIn(linea, texto)
        self.assertNotIn("disk:", texto)
        claves = re.findall(r"- key: (\S+)\n\s+(value|sync): (\S+)", texto)
        self.assertEqual([c for c in claves if c[1] == "value"], [("PYTHON_VERSION", "value", "3.12.15")])
        self.assertEqual({c[0] for c in claves if c[1:] == ("sync", "false")},
                         {"ARA_MAP_DATABASE_URL", "ARA_MAP_HOST_PUBLICO", "ARA_MAP_ARCHIVOS_SUPABASE_URL",
                          "ARA_MAP_ARCHIVOS_SUPABASE_KEY", "ARA_MAP_ARCHIVOS_SUPABASE_BUCKET"})

    def test_hosted_requirements_are_exact_pins(self):
        lineas = [linea for linea in (self.raiz / "requirements-hosted.txt").read_text().splitlines()
                  if linea and not linea.lstrip().startswith("#")]
        for directa in ("psycopg==3.3.6", "storage3==2.32.0", "httpx==0.28.1"):
            self.assertIn(directa, lineas)
        for linea in lineas:
            self.assertRegex(linea, r"^[A-Za-z0-9_.\[\]-]+==[0-9][0-9A-Za-z.]*$")

    def test_vercel_settings_are_untouched(self):
        vercel = json.loads((self.raiz / "vercel.json").read_text())
        self.assertEqual(vercel["git"], {"deploymentEnabled": False})


class Hospedado(TempDatabase):
    def setUp(self):
        super().setUp()
        create_user(self.conn, "ana", "Ana")
        self.parches = [patch.object(hosted.HostedHandler, "_database_ready", lambda self: True),
                        patch.object(hosted.HostedHandler, "HOST_PUBLICO", HOST),
                        patch("sys.stderr")]
        for parche in self.parches:
            parche.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), hosted.HostedHandler)
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.hilo.join()
        for parche in self.parches:
            parche.stop()
        super().tearDown()

    def request(self, method, path, body=None, headers=None):
        conexion = HTTPConnection("127.0.0.1", self.httpd.server_port)
        conexion.request(method, path, body=body, headers={"Host": HOST, **(headers or {})})
        respuesta = conexion.getresponse()
        resultado = respuesta.status, respuesta.read(), dict(respuesta.getheaders())
        conexion.close()
        return resultado

    def login(self, headers=None):
        return self.request("POST", "/api/login",
                            json.dumps({"username": "ana", "password": TEST_PASSWORD}), headers)

    def answering(self, handler):
        ruta = (handler, {"path": "/api/config", "query": {}, "params": {}, "capacidad": None})
        return patch("server.app.router.resolve", return_value=ruta)

    def test_only_the_public_host_is_served(self):
        self.assertEqual(self.request("GET", "/api/config")[0], 200)
        self.assertEqual(self.request("GET", "/api/config", headers={"Host": HOST.upper() + ":443"})[0], 200)
        for host in ("otro.example.test", "localhost", "127.0.0.1", "", HOST + ".evil.test"):
            with self.subTest(host=host):
                self.assertEqual(self.request("GET", "/api/config", headers={"Host": host})[0], 403)

    def test_forwarded_headers_choose_nothing(self):
        falsos = {"X-Forwarded-Host": HOST, "X-Forwarded-Proto": "https", "Forwarded": f"host={HOST}"}
        self.assertEqual(self.request("GET", "/api/config", headers={"Host": "otro.example.test", **falsos})[0], 403)
        ajeno = {"Origin": "https://otro.example.test", "X-Forwarded-Host": "otro.example.test",
                 "X-Forwarded-Origin": f"https://{HOST}"}
        self.assertEqual(self.login(ajeno)[0], 403)

    def test_writes_need_this_portals_https_origin(self):
        self.assertEqual(self.login({"Origin": f"https://{HOST}"})[0], 200)
        self.assertEqual(self.login()[0], 200)  # no Origin: not a browser
        for origen in (f"http://{HOST}", "https://otro.example.test", f"https://{HOST}.evil.test",
                       f"https://{HOST}:8443", "null"):
            with self.subTest(origen=origen):
                status, body, _ = self.login({"Origin": origen})
                self.assertEqual((status, json.loads(body)["error"]),
                                 (403, "Petición rechazada: origen externo."))

    def test_cookie_and_transport_headers(self):
        status, _, headers = self.login()
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        for marca in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
            self.assertIn(marca, cookie)
        self.assertEqual(headers["Strict-Transport-Security"], "max-age=31536000")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(json.loads(self.request("GET", "/api/config")[1])["cloud"], True)

    def test_private_routes_and_the_app_shell(self):
        self.assertEqual(self.request("GET", "/api/inventario/terrenos")[0], 401)
        self.assertEqual(self.request("GET", "/api/no-existe")[0], 401)
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<html", body.lower())
        self.assertEqual(self.request("GET", "/../server/hosted.py")[0], 403)  # only web/ is served

    def test_read_only_mode_still_refuses_writes(self):
        with patch.dict("os.environ", {"ARA_MAP_READ_ONLY": "1"}):
            self.assertEqual(self.login()[0], 403)

    def test_health_answers_any_host_without_the_database(self):
        with patch("server.app.db.session", side_effect=AssertionError("no database for a probe")):
            status, body, _ = self.request("GET", "/healthz", headers={"Host": "10.0.0.7:10000"})
        self.assertEqual((status, body), (200, b"ok\n"))
        self.assertEqual(self.request("POST", "/healthz", headers={"Host": "10.0.0.7"})[0], 403)

    def test_whole_file_bodies_up_to_the_application_ceiling(self):
        with self.answering(lambda request: {"bytes": len(request.body)}):
            for megas in (20, 25):
                with self.subTest(megas=megas):
                    status, body, _ = self.request("POST", "/api/login", bytes(megas * MIB))
                    self.assertEqual((status, json.loads(body)), (200, {"bytes": megas * MIB}))
            status, _, _ = self.request("POST", "/api/login", b"",
                                        {"Content-Length": str(25 * MIB + 1)})
            self.assertEqual(status, 413)

    def test_malformed_and_incomplete_lengths(self):
        with self.answering(lambda request: {"bytes": len(request.body)}):
            for cabeceras in ("Content-Length: 5x", "Content-Length: -1", "Content-Length: 3\r\nContent-Length: 3",
                              "Transfer-Encoding: chunked"):
                with self.subTest(cabeceras=cabeceras):
                    self.assertEqual(self.crudo(f"POST /api/login HTTP/1.1\r\nHost: {HOST}\r\n{cabeceras}\r\n\r\nabc"), 400)
            # Ten bytes declared, five sent, then the client stops sending: the
            # handler sees the short body and nothing waits forever.
            respuesta = self.crudo(f"POST /api/login HTTP/1.1\r\nHost: {HOST}\r\nContent-Length: 10\r\n\r\nabcde",
                                   completa=True)
        self.assertIn(b'{"bytes": 5}', respuesta.replace(b'":5', b'": 5'))

    def crudo(self, texto, completa=False):
        with socket.create_connection(("127.0.0.1", self.httpd.server_port), timeout=10) as s:
            s.sendall(texto.encode("latin-1"))
            s.shutdown(socket.SHUT_WR)
            datos = b""
            while True:
                trozo = s.recv(65536)
                if not trozo:
                    break
                datos += trozo
        return datos if completa else int(datos.split(b" ", 2)[1])

    def test_requests_in_flight_are_bounded(self):
        dentro, soltar = threading.Event(), threading.Event()

        def lenta(request):
            dentro.set()
            soltar.wait(10)
            return {"ok": True}

        with patch.object(hosted.HostedHandler, "_cupo", threading.BoundedSemaphore(1)), \
                patch("server.hosted.ESPERA_DE_CUPO", 0.2), self.answering(lenta):
            primera = threading.Thread(target=self.request, args=("GET", "/api/config"))
            primera.start()
            self.assertTrue(dentro.wait(10))
            status, body, _ = self.request("GET", "/api/config")
            self.assertEqual((status, json.loads(body)["detalle"]), (503, {"code": "ocupado"}))
            self.assertEqual(self.request("GET", "/healthz")[0], 200)  # the probe never queues
            soltar.set()
            primera.join()
            self.assertEqual(self.request("GET", "/api/config")[0], 200)


if __name__ == "__main__":
    unittest.main()

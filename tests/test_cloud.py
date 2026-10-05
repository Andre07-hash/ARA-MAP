"""The cloud adapter (api/index.py) under the shared sign-in policy.

Replaces the shared-password tests: the editor password, its signed cookie and
the ARA_MAP_PUBLIC_EDIT bypass are gone. Individual accounts and server-side
sessions are checked here through the real cloud handler. Without Postgres the
adapter refuses to touch any database (503); the signed-in cases run it on a
throwaway SQLite file by patching only that readiness check.
"""
import importlib.util
import json
import os
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import auth, db
from tests.support import TEST_PASSWORD, TempDatabase, create_user


def load_adapter():
    spec = importlib.util.spec_from_file_location("cloud_adapter", Path(__file__).parents[1] / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CloudServer:
    def start(self, handler):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.httpd.server_port)
        connection.request(method, path, body=body, headers={"Host": "ara-map.vercel.app", **(headers or {})})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result


class AnonymousWithoutDatabase(CloudServer, unittest.TestCase):
    """No database configured: anonymous callers are refused before any lookup."""

    def setUp(self):
        self.env = patch.dict(os.environ, {"ARA_MAP_PUBLIC_EDIT": "1", "ARA_MAP_DATABASE_URL": ""})
        self.env.start()
        self.start(load_adapter().handler)

    def tearDown(self):
        self.stop()
        self.env.stop()

    def test_anonymous_cannot_read_or_write_the_workspace(self):
        # Formerly only writes were refused; legacy reads and the export were
        # anonymous. Now every non-allowlisted API route is 401.
        for method, path in [("GET", "/api/bases"), ("GET", "/api/bases/1/terrenos"),
                             ("GET", "/api/mapas/1/terrenos"), ("GET", "/api/carpetas"),
                             ("POST", "/api/exportar"), ("DELETE", "/api/bases/1"),
                             ("PATCH", "/api/bases/1"), ("POST", "/api/mapas"),
                             ("POST", "/api/importar/confirmar"), ("GET", "/api/inventario/terrenos"),
                             ("GET", "/api/cualquier-cosa")]:
            with self.subTest(method=method, path=path):
                status, body, headers = self.request(method, path, "{}")
                self.assertEqual(status, 401)
                self.assertEqual(json.loads(body)["detalle"]["code"], "unauthenticated")
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_public_edit_bypass_no_longer_exists(self):
        # Replaces test_public_edit_requires_explicit_setting: the variable is
        # set to "1" in setUp and grants nothing.
        self.assertEqual(self.request("DELETE", "/api/bases/1")[0], 401)
        config = json.loads(self.request("GET", "/api/config")[1])
        self.assertEqual(config, {"readOnly": True, "cloud": True, "authRequired": True,
                                  "maxUploadBytes": 4 * 1024 * 1024})

    def test_anonymous_cannot_preview_a_csv(self):
        status, body, _ = self.request("POST", "/api/importar/vista-previa?csv_decimal=dot",
                                       b"Terreno\nPredio A\n", {"X-Archivo": "t.csv"})
        self.assertEqual(status, 401)
        self.assertIn("Inicia sesión", json.loads(body)["error"])

    def test_without_postgres_nothing_falls_back_to_a_local_file(self):
        for method, path in [("GET", "/api/session"), ("POST", "/api/login")]:
            with self.subTest(path=path):
                self.assertEqual(self.request(method, path, "{}")[0], 503)
        self.assertEqual(self.request("GET", "/api/bases", headers={"Cookie": f"{auth.COOKIE}={'x' * 43}"})[0], 503)


class SignedIn(CloudServer, TempDatabase):
    def setUp(self):
        super().setUp()
        create_user(self.conn, "ana", "Ana")
        create_user(self.conn, "beto", "Beto")
        module = load_adapter()
        self.ready = patch.object(module.handler, "_database_ready", lambda self: True)
        self.ready.start()
        self.start(module.handler)

    def tearDown(self):
        self.stop()
        self.ready.stop()
        super().tearDown()

    def login(self, username="ana", password=TEST_PASSWORD, headers=None):
        return self.request("POST", "/api/login", json.dumps({"username": username, "password": password}),
                            headers)

    def cookie(self, username="ana"):
        status, _, headers = self.login(username)
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";")[0]

    def test_login_cookie_session_and_logout(self):
        status, body, _ = self.login(password="wrong-password-123")
        self.assertEqual((status, json.loads(body)["error"]), (401, "Usuario o contraseña incorrectos."))
        status, _, headers = self.request("POST", "/api/login",
                                          json.dumps({"username": "nadie", "password": "x"}))
        self.assertEqual(status, 401)  # same answer for an unknown account
        status, body, headers = self.login(" ANA ")
        self.assertEqual(status, 200)
        user = json.loads(body)["user"]
        self.assertEqual(set(user), {"id", "display_name"})
        cookie = headers["Set-Cookie"]
        for attribute in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(attribute, cookie)
        jar = {"Cookie": cookie.split(";")[0]}
        self.assertEqual(json.loads(self.request("GET", "/api/session", headers=jar)[1]),
                         {"authenticated": True, "user": user})
        self.assertFalse(json.loads(self.request("GET", "/api/config", headers=jar)[1])["readOnly"])
        self.assertEqual(self.request("GET", "/api/bases", headers=jar)[0], 200)
        status, _, headers = self.request("POST", "/api/logout", headers=jar)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        # The server-side session is revoked, not just the browser cookie.
        self.assertEqual(self.request("GET", "/api/bases", headers=jar)[0], 401)
        self.assertEqual(json.loads(self.request("GET", "/api/session", headers=jar)[1]),
                         {"authenticated": False})
        self.assertEqual(self.request("POST", "/api/logout")[0], 200)  # idempotent

    def test_forged_expired_and_cross_origin_sessions(self):
        self.assertEqual(self.request("GET", "/api/bases",
                                      headers={"Cookie": f"{auth.COOKIE}={'A' * 43}"})[0], 401)
        jar = {"Cookie": self.cookie()}
        self.conn.execute("UPDATE team_session SET expires_at = 0")
        self.assertEqual(self.request("GET", "/api/bases", headers=jar)[0], 401)
        self.assertEqual(self.login(headers={"Origin": "https://unrelated.example"})[0], 403)
        jar = {"Cookie": self.cookie()}
        self.assertEqual(self.request("POST", "/api/mapas", "{}",
                                      {**jar, "Origin": "https://unrelated.example"})[0], 403)

    def test_password_reset_and_deactivation_end_sessions(self):
        jar = {"Cookie": self.cookie()}
        with db.session() as conn:
            auth.set_password(conn, "ana", "otra-contraseña-larga")
        self.assertEqual(self.request("GET", "/api/bases", headers=jar)[0], 401)
        self.assertEqual(self.login()[0], 401)
        jar = {"Cookie": self.cookie("beto")}
        with db.session() as conn:
            auth.set_active(conn, "beto", False)
        self.assertEqual(self.request("GET", "/api/bases", headers=jar)[0], 401)
        self.assertEqual(self.login("beto")[0], 401)

    def test_failed_logins_are_throttled_per_account(self):
        for _ in range(auth.MAX_FAILURES):
            self.assertEqual(self.login(password="mal-mal-mal-mal")[0], 401)
        status, body, _ = self.login()  # even the right password, for a while
        self.assertEqual((status, json.loads(body)["detalle"]["code"]), (429, "rate_limited"))
        self.assertEqual(self.login("beto")[0], 200)  # other accounts unaffected

    def test_cloud_upload_limit_applies_to_csv(self):
        jar = {"Cookie": self.cookie()}
        status, body, _ = self.request(
            "POST", "/api/importar/vista-previa", b"",
            {**jar, "X-Archivo": "t.csv", "Content-Length": str(4 * 1024 * 1024 + 1)})
        self.assertEqual(status, 413)
        self.assertIn("4 MB", json.loads(body)["error"])

    def test_oversized_login_body_is_refused(self):
        self.assertEqual(self.request("POST", "/api/login", "x" * 5000)[0], 413)


if __name__ == "__main__":
    unittest.main()

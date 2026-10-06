"""Server tests: static serving, routing and the local-only guards.

These run a real ThreadingHTTPServer in a background thread and talk to it over
HTTP, because the guards being checked live in the request handler itself.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import app as app_module
from tests.support import TempDatabase, create_user, session_cookie


class ServerCase(TempDatabase):
    """A running local server and a signed-in team user.

    Since the inventory release every API route except the public allowlist
    needs a session, locally too, so these legacy-route tests sign in first.
    Anonymous behaviour is asserted separately in AnonymousAccess.
    """

    def setUp(self):
        super().setUp()
        create_user(self.conn)
        self.cookie = session_cookie(self.conn)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def fetch(self, path, *, method="GET", body=None, headers=None, anonymous=False):
        cabeceras = {} if anonymous else {"Cookie": self.cookie}
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method, data=body, headers={**cabeceras, **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)


class StaticFiles(ServerCase):
    def test_the_index_page_is_served(self):
        status, body, headers = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"ARA Map", body)

    def test_modules_and_styles_are_served(self):
        for path, expected in (
            ("/components/app.js", "javascript"),
            ("/styles/global.css", "text/css"),
            ("/vendor/leaflet.js", "javascript"),
        ):
            with self.subTest(path=path):
                status, _, headers = self.fetch(path)
                self.assertEqual(status, 200)
                self.assertIn(expected, headers["Content-Type"])

    def test_responses_refuse_content_type_sniffing(self):
        _, _, headers = self.fetch("/")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_an_unknown_page_falls_back_to_the_app(self):
        status, body, _ = self.fetch("/cualquier-cosa")
        self.assertEqual(status, 200)
        self.assertIn(b"ARA Map", body)

    def test_a_path_cannot_escape_the_web_directory(self):
        for attempt in (
            "/../server/db.py",
            "/../../etc/passwd",
            "/%2e%2e/%2e%2e/server/app.py",
        ):
            with self.subTest(attempt=attempt):
                status, body, _ = self.fetch(attempt)
                self.assertNotIn(b"sqlite3", body)
                self.assertNotIn(b"SCHEMA_VERSION", body)


class LocalOnly(ServerCase):
    def test_a_foreign_host_header_is_refused(self):
        status, _, _ = self.fetch("/", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)

    def test_loopback_hosts_are_accepted(self):
        for host in ("localhost:1234", "127.0.0.1:1234"):
            with self.subTest(host=host):
                status, _, _ = self.fetch("/api/bases", headers={"Host": host})
                self.assertEqual(status, 200)

    def test_a_foreign_origin_cannot_change_anything(self):
        """A page on another site must not be able to write through the browser.

        The Host header is not enough: a browser sending a cross-site request to
        localhost still sets Host correctly. Origin is what distinguishes it.
        """
        status, _, _ = self.fetch(
            "/api/mapas", method="POST", body=b"{}",
            headers={"Content-Type": "text/plain", "Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)

    def test_the_apps_own_origin_is_accepted(self):
        status, _, _ = self.fetch(
            "/api/mapas", method="POST", body=b"{}",
            headers={"Content-Type": "application/json",
                     "Origin": f"http://localhost:{self.port}"},
        )
        self.assertNotEqual(status, 403)

    def test_a_request_without_an_origin_still_works(self):
        """curl, the e2e suite and same-origin GETs send no Origin at all."""
        status, _, _ = self.fetch("/api/bases")
        self.assertEqual(status, 200)


class AnonymousAccess(ServerCase):
    """Replaces the old assumption that anyone on loopback may read and write:
    loopback is not an employee identity (INTEGRATION_DECISIONS §3)."""

    def test_legacy_reads_and_exports_need_a_session(self):
        for method, path in (("GET", "/api/bases"), ("GET", "/api/bases/1"),
                             ("GET", "/api/bases/1/terrenos"), ("GET", "/api/mapas"),
                             ("GET", "/api/mapas/1"), ("GET", "/api/mapas/1/terrenos"),
                             ("GET", "/api/carpetas"), ("GET", "/api/formatos"),
                             ("POST", "/api/exportar"), ("POST", "/api/importar/vista-previa"),
                             ("GET", "/api/inventario/terrenos"), ("GET", "/api/no-existe"),
                             ("GET", "/api/bases/"), ("GET", "/api")):
            with self.subTest(method=method, path=path):
                status, body, headers = self.fetch(path, method=method, body=b"{}"
                                                   if method == "POST" else None, anonymous=True)
                self.assertEqual(status, 401)
                self.assertEqual(json.loads(body)["detalle"]["code"], "unauthenticated")
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_an_old_shared_password_cookie_grants_nothing(self):
        status, _, _ = self.fetch("/api/bases", anonymous=True,
                                  headers={"Cookie": "ara_editor=9999999999.abc.def"})
        self.assertEqual(status, 401)

    def test_the_allowlist_answers_anonymously(self):
        for path in ("/api/config", "/api/session", "/api/publico/terrenos"):
            with self.subTest(path=path):
                self.assertEqual(self.fetch(path, anonymous=True)[0], 200)
        self.assertEqual(self.fetch("/api/publico/terrenos/abc", anonymous=True)[0], 404)

    def test_static_files_stay_public(self):
        self.assertEqual(self.fetch("/", anonymous=True)[0], 200)


class ApiRouting(ServerCase):
    def test_anonymous_login_failure_has_a_generic_error(self):
        with patch("server.api.sesion.db.session", side_effect=RuntimeError("PRIVATE-SQL")), \
                patch("traceback.print_exc") as logged:
            status, body, _ = self.fetch("/api/login", method="POST", anonymous=True,
                                         body=b'{"username":"ana","password":"fictional"}')
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body)["detalle"], {"code": "internal"})
        self.assertNotIn(b"PRIVATE-SQL", body)
        logged.assert_called_once_with()

    def test_a_json_endpoint_answers(self):
        status, body, headers = self.fetch("/api/bases")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body), {"bases": []})

    def test_an_unknown_api_route_is_404_json(self):
        status, body, _ = self.fetch("/api/no-existe")
        self.assertEqual(status, 404)
        self.assertIn("error", json.loads(body))

    def test_the_wrong_method_is_405(self):
        status, _, _ = self.fetch("/api/bases", method="DELETE")
        self.assertEqual(status, 405)

    def test_a_handler_error_becomes_a_clean_message(self):
        status, body, _ = self.fetch("/api/bases/999")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"], "La base no existe.")

    def test_a_non_numeric_id_is_a_clean_404(self):
        """/api/bases/abc is a bad URL, not a crash: no stack trace, no 500."""
        status, body, _ = self.fetch("/api/bases/abc")
        self.assertEqual(status, 404)
        mensaje = json.loads(body)["error"]
        self.assertIn("error", json.loads(body))
        self.assertNotIn("int()", mensaje)
        self.assertNotIn("Error inesperado", mensaje)

    def test_a_malformed_body_is_reported_not_crashed(self):
        status, body, _ = self.fetch(
            "/api/mapas", method="POST", body=b"{roto",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))

    def test_the_full_import_flow_over_http(self):
        from tests.support import FIXTURE

        status, body, _ = self.fetch(
            "/api/importar/vista-previa", method="POST",
            body=FIXTURE.read_bytes(),
            headers={"Content-Type": "application/octet-stream",
                     "X-Archivo": "Base%20Terrenos%2009.26.xlsx"},
        )
        self.assertEqual(status, 200)
        preview = json.loads(body)
        self.assertEqual(preview["conteo"], 79)

        status, body, _ = self.fetch(
            "/api/importar/confirmar", method="POST",
            body=json.dumps({"token": preview["token"], "nombre": "Septiembre"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["base"]["conteo"], 79)

        status, body, _ = self.fetch("/api/bases")
        self.assertEqual([b["nombre"] for b in json.loads(body)["bases"]], ["Septiembre"])


class PortSelection(unittest.TestCase):
    def test_a_busy_port_is_skipped(self):
        busy = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        port = busy.server_address[1]
        try:
            self.assertNotEqual(app_module.find_port(port), port)
        finally:
            busy.server_close()

    def test_a_free_port_is_taken_as_is(self):
        probe = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        port = probe.server_address[1]
        probe.server_close()
        self.assertEqual(app_module.find_port(port), port)


if __name__ == "__main__":
    unittest.main()

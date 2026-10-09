"""A refused request's body is never read as the next request (R2-A1).

Raw sockets against the real dispatcher: one connection, one POST whose
declared body is itself a well-formed request for the public /api/config. If
the server answers the refusal and then that smuggled request, the unread body
was reinterpreted as HTTP framing. Every refusal that returns without reading
the body must answer once and close.
"""

from __future__ import annotations

import os
import re
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import app as app_module
from server import db
from tests.support import TEST_PASSWORD, TempDatabase, create_user, session_cookie

OCULTA = b"GET /api/config HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"


class Cuerpos(TempDatabase):
    def setUp(self):
        super().setUp()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()
        self.addCleanup(self.bajar)
        with db.session() as conn:
            create_user(conn, "ada", "Ada Ficticia", rol="admin")
            create_user(conn, "olga", "Olga Ficticia", rol="operador")
            self.cookies = {n: session_cookie(conn, n) for n in ("ada", "olga")}

    def bajar(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.hilo.join(timeout=5)

    def enviar(self, crudo, espera=1.5):
        """(status of every response on the connection, whether the server closed it)."""
        datos, cerrada = b"", False
        with socket.create_connection(self.httpd.server_address, timeout=espera) as sock:
            sock.sendall(crudo)
            try:
                while True:
                    trozo = sock.recv(65536)
                    if not trozo:
                        cerrada = True
                        break
                    datos += trozo
            except socket.timeout:
                pass
        return [int(s) for s in re.findall(rb"HTTP/1\.[01] (\d{3})", datos)], cerrada

    def post(self, ruta="/api/logout", cabeceras=(), cuerpo=OCULTA, metodo="POST", largo=None):
        lineas = [f"{metodo} {ruta} HTTP/1.1".encode(), *cabeceras]
        if not any(c.lower().startswith(b"host:") for c in cabeceras):
            lineas.append(b"Host: 127.0.0.1")
        if largo is not False:
            lineas.append(b"Content-Length: " + str(len(cuerpo) if largo is None else largo).encode())
        return b"\r\n".join(lineas) + b"\r\n\r\n" + cuerpo

    def test_a_refusal_answers_once_and_closes_whatever_the_body_holds(self):
        ada, olga = (b"Cookie: " + self.cookies[n].encode() for n in ("ada", "olga"))
        casos = {
            "invalid Host": (self.post(cabeceras=(b"Host: example.invalid",)), 403),
            "foreign Origin": (self.post(cabeceras=(b"Origin: https://example.invalid",)), 403),
            "no session, private route": (self.post("/api/maestra/bases"), 401),
            "garbage session": (self.post("/api/maestra/bases",
                                          (b"Cookie: ara_sesion=" + b"x" * 43,)), 401),
            "capability the role lacks": (self.post("/api/maestra/bases", (olga,)), 403),
            "unknown API route": (self.post("/api/no-existe", (ada,)), 404),
            "method the route lacks": (self.post("/api/maestra/bases", (ada,), metodo="DELETE"), 405),
            "body over the limit": (self.post("/api/logout", largo=app_module.MAX_BODY + 1), 413),
            "a page request carrying a body": (self.post("/", metodo="GET"), 200),
            "chunked body, which is not read": (self.post(
                cabeceras=(b"Transfer-Encoding: chunked",), largo=False,
                cuerpo=b"0\r\n\r\n" + OCULTA), 400),
            "negative length": (self.post(largo=-1), 400),
            "length that is not a number": (self.post(largo="abc"), 400),
        }
        for nombre, (peticion, esperado) in casos.items():
            with self.subTest(nombre):
                self.assertEqual(self.enviar(peticion), ([esperado], True))

    def test_ambiguous_framing_is_refused_once_before_the_body(self):
        """R2-A5: repeated or empty Content-Length and any Transfer-Encoding
        field. Anonymous login would answer 401 and keep the connection."""
        n = str(len(OCULTA)).encode()
        cl, te = b"Content-Length: ", b"Transfer-Encoding: "
        casos = {
            "0 then the real length": (cl + b"0", cl + n),
            "the real length then 0": (cl + n, cl + b"0"),
            "the same length twice": (cl + n, cl + n),
            "empty length": (cl,),
            "empty length then a real one": (cl, cl + n),
            "a real length then an empty one": (cl + n, cl),
            "comma-combined lengths": (cl + b"0, " + n,),
            "comma-combined equal lengths": (cl + n + b", " + n,),
            "length with a trailing comma": (cl + n + b",",),
            "0, empty encoding, chunked": (cl + b"0", te, te + b"chunked"),
            "chunked, empty encoding, 0": (te + b"chunked", te, cl + b"0"),
            "empty encoding and a length": (te, cl + n),
            "a length and an empty encoding": (cl + n, te),
            "chunked and a length": (te + b"chunked", cl + n),
            "a length and chunked": (cl + n, te + b"chunked"),
            "identity encoding and a length": (te + b"identity", cl + n),
            "empty encoding alone": (te,),
        }
        for nombre, cabeceras in casos.items():
            with self.subTest(nombre):
                self.assertEqual(self.enviar(self.post("/api/login", cabeceras, largo=False)),
                                 ([400], True))

    def test_absent_and_zero_lengths_are_still_an_empty_body(self):
        ver = OCULTA
        for nombre, largo in (("absent", False), ("zero", 0)):
            with self.subTest(nombre):
                self.assertEqual(self.enviar(self.post("/api/logout", cuerpo=b"", largo=largo) + ver),
                                 ([200, 200], True))

    def test_read_only_mode_refuses_once_and_closes(self):
        with patch.dict(os.environ, {"ARA_MAP_READ_ONLY": "1"}):
            self.assertEqual(self.enviar(self.post()), ([403], True))
            self.assertEqual(self.enviar(self.post("/api/maestra/bases")), ([403], True))

    def test_requests_whose_body_was_read_keep_the_connection(self):
        """The repair must not cost ordinary keep-alive: two real requests on
        one connection are both answered, in order."""
        ada = b"Cookie: " + self.cookies["ada"].encode()
        crear = self.post("/api/maestra/bases", (ada, b"Content-Type: application/json"),
                          cuerpo=b'{"nombre": "Base Ficticia"}')
        invalida = self.post("/api/maestra/bases", (ada,), cuerpo=b'{"nombre": ""}')
        login_malo = self.post("/api/login", cuerpo=(
            '{"username": "ada", "password": "no-es-' + TEST_PASSWORD + '"}').encode())
        ver = b"GET /api/config HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
        self.assertEqual(self.enviar(crear + ver), ([200, 200], True))
        self.assertEqual(self.enviar(invalida + ver), ([422, 200], True))    # read, then refused
        self.assertEqual(self.enviar(login_malo + ver), ([401, 200], True))
        self.assertEqual(self.enviar(ver.replace(b"Connection: close\r\n", b"") + ver), ([200, 200], True))
        with db.session() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM maestra_base").fetchone()["n"], 1)


if __name__ == "__main__":
    unittest.main()

"""The release write freeze (scripts/congelar_escrituras.py) on a real,
disposable Postgres DATABASE created for this test, through two cloud-adapter
instances standing in for the new and an old deployment."""

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

from server import auth, postgres
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")


@unittest.skipUnless(URL, "No Postgres test connection configured")
class WriteFreeze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        cls.nombre = "ara_congelar_" + uuid.uuid4().hex[:12]
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{cls.nombre}"')
        cls.url = make_conninfo(URL, dbname=cls.nombre)
        assert conninfo_to_dict(cls.url)["dbname"] == cls.nombre
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": cls.url, "OBJETIVO_CONGELAR": cls.url})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
            auth.create_user(conn, "ana", "Ana", TEST_PASSWORD, iterations=1000)
        cls.servidores = []
        for _ in range(2):   # the new deployment and an old one, same database
            spec = importlib.util.spec_from_file_location(
                f"adaptador_{uuid.uuid4().hex}", Path(__file__).parents[1] / "api" / "index.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.handler)
            hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
            hilo.start()
            cls.servidores.append((httpd, hilo))

    @classmethod
    def tearDownClass(cls):
        import psycopg
        for httpd, hilo in cls.servidores:
            httpd.shutdown()
            httpd.server_close()
            hilo.join()
        cls.env.stop()
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                         (cls.nombre,))
            conn.execute(f'DROP DATABASE "{cls.nombre}"')

    def tearDown(self):
        self.script("desactivar")   # never leave the database frozen

    def script(self, accion):
        from scripts import congelar_escrituras
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(congelar_escrituras.main(["--url-env", "OBJETIVO_CONGELAR", accion]), 0)
        return dict(linea.split(": ", 1) for linea in salida.getvalue().strip().splitlines())

    def call(self, method, path, body=None, cookie=None, servidor=0):
        c = HTTPConnection("127.0.0.1", self.servidores[servidor][0].server_port, timeout=30)
        headers = {"Host": "ara.example", **({"Cookie": cookie} if cookie else {})}
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        r = c.getresponse()
        datos = r.read()
        c.close()
        return r.status, (json.loads(datos) if datos else None), {k.lower(): v for k, v in r.getheaders()}

    def login(self, servidor=0):
        status, _, h = self.call("POST", "/api/login", {"username": "ana", "password": TEST_PASSWORD},
                                 servidor=servidor)
        self.assertEqual(status, 200)
        return h["set-cookie"].split(";")[0]

    def test_freeze_stops_writes_from_every_deployment_and_keeps_reads(self):
        nueva, vieja = self.login(0), self.login(1)
        self.assertEqual(self.call("POST", "/api/carpetas", {"tipo": "bases", "nombre": "Antes"}, nueva)[0], 200)
        self.assertEqual(self.script("estado")["congelada"], "False")

        activado = self.script("activar")
        self.assertEqual((activado["congelada"], activado["actualizaciones_en_curso"]), ("True", "0"))
        for servidor, cookie in ((0, nueva), (1, vieja)):
            status, body, h = self.call("POST", "/api/carpetas", {"tipo": "bases", "nombre": "Durante"},
                                        cookie, servidor)
            self.assertEqual((status, body["detalle"]["code"], h["retry-after"]), (503, "mantenimiento", "300"))
            self.assertEqual(self.call("GET", "/api/session", None, cookie, servidor)[1]["user"]["display_name"], "Ana")
            self.assertEqual(self.call("GET", "/api/bases", None, cookie, servidor)[0], 200)
            self.assertEqual(self.call("GET", "/api/carpetas?tipo=bases", None, cookie, servidor)[0], 200)
        self.assertEqual(self.call("POST", "/api/login", {"username": "ana", "password": TEST_PASSWORD})[0], 503)

        # The release's own migration session overrides the freeze for itself only.
        import psycopg
        from psycopg.conninfo import make_conninfo
        with psycopg.connect(make_conninfo(self.url, options="-c default_transaction_read_only=off")) as c:
            c.execute("UPDATE workspace_metadata SET value = value WHERE key = 'schema_version'")

        self.assertEqual(self.script("desactivar")["congelada"], "False")
        self.assertEqual(self.call("POST", "/api/carpetas", {"tipo": "bases", "nombre": "Después"}, nueva)[0], 200)
        nombres = {c["nombre"] for c in self.call("GET", "/api/carpetas?tipo=bases", None, nueva)[1]["carpetas"]}
        self.assertEqual(nombres, {"Antes", "Después"})

    def test_requires_an_explicit_target(self):
        from scripts import congelar_escrituras
        with patch.dict(os.environ, {"SIN_DEFINIR": ""}), self.assertRaises(SystemExit):
            congelar_escrituras.main(["--url-env", "SIN_DEFINIR", "estado"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            congelar_escrituras.main(["activar"])


if __name__ == "__main__":
    unittest.main()

"""Stage 1 inventory and accounts on a real, disposable Postgres.

Runs only when ARA_MAP_TEST_DATABASE_URL names a disposable database; each run
works in its own schema and drops it. Concurrency uses separate connections.
"""

from __future__ import annotations

import importlib.util
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
from server.repo import inventario as repo
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")


@unittest.skipUnless(URL, "No Postgres test connection configured")
class InventarioPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.schema = "test_ara_inv_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
        with postgres.session() as conn:
            postgres.migrate(conn)  # twice: idempotent

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def setUp(self):
        with postgres.session() as conn:
            conn.raw.execute("TRUNCATE inventory_operation_result, inventory_event, inventory_revision,"
                             " inventory_terrain, team_session, team_login_failure, team_user,"
                             " workspace_backup CASCADE")
            self.actors = [dict(auth.create_user(conn, n, n.capitalize(), TEST_PASSWORD, iterations=1000),
                                display_name=n.capitalize()) for n in ("ana", "beto", "carla")]

    def create(self, fields=None, key=None):
        with db.session() as conn:
            return repo.create(conn, fields or {"terreno": "Lote"}, self.actors[0],
                               key or str(uuid.uuid4()), "hash")["terreno"]

    def count(self, table):
        with db.session() as conn:
            return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]

    def test_schema_is_v8_with_the_pointer_constraints(self):
        with db.session() as conn:
            self.assertEqual(postgres.schema_version(conn), db.SCHEMA_VERSION)
            nombres = {r["conname"] for r in conn.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'inventory_terrain'::regclass")}
        self.assertTrue({"fk_inventory_draft", "fk_inventory_published"} <= nombres)

    def test_a_pointer_cannot_name_another_records_revision(self):
        import psycopg
        a, b = self.create({"terreno": "A"}), self.create({"terreno": "B"})
        with self.assertRaises(psycopg.errors.ForeignKeyViolation), db.session() as conn:
            conn.execute("UPDATE inventory_terrain SET published_revision_id = ? WHERE id = ?",
                         (b["draft_revision_id"], a["id"]))
        self.assertIsNone(self.get(a["id"])["published_revision_id"])

    def get(self, inventory_id):
        with db.session() as conn:
            return repo.get(conn, inventory_id)

    def test_create_edit_conflict_and_history(self):
        t = self.create({"terreno": "Lote", "asking_m2": 122.5, "moneda": "USD"}, key="pg-clave-1")
        with db.session() as conn:
            again = repo.create(conn, {"terreno": "Lote", "asking_m2": 122.5, "moneda": "USD"},
                                self.actors[1], "pg-clave-1", "hash")
        self.assertEqual(again["terreno"]["id"], t["id"])
        with db.session() as conn:
            repo.update(conn, t["id"], 1, {"terreno": "Lote 2"}, (), self.actors[1])
        with self.assertRaises(repo.ConflictError), db.session() as conn:
            repo.update(conn, t["id"], 1, {"terreno": "Lote 3"}, (), self.actors[2])
        reread = self.get(t["id"])
        self.assertEqual((reread["version"], reread["draft"]["terreno"]), (2, "Lote 2"))
        self.assertEqual(reread["draft"]["asking_m2"], 122.5)
        with db.session() as conn:
            eventos, total, _ = repo.history(conn, t["id"], None, 10)
        self.assertEqual([(e["version"], e["actor"]["display_name"]) for e in eventos],
                         [(2, "Beto"), (1, "Ana")])
        self.assertEqual(self.count("inventory_revision"), 2)

    def test_simultaneous_saves_on_separate_connections_have_one_winner(self):
        t = self.create()
        resultados = []
        barrera = threading.Barrier(3)

        def guardar(actor):
            barrera.wait()
            try:
                with db.session() as conn:
                    repo.update(conn, t["id"], 1, {"terreno": actor["display_name"]}, (), actor)
                resultados.append("ok")
            except repo.ConflictError:
                resultados.append("conflict")

        hilos = [threading.Thread(target=guardar, args=(a,)) for a in self.actors]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sorted(resultados), ["conflict", "conflict", "ok"])
        self.assertEqual((self.count("inventory_event"), self.get(t["id"])["version"]), (2, 2))

    def test_concurrent_same_key_creates_once(self):
        ids = []
        barrera = threading.Barrier(3)

        def crear():
            barrera.wait()
            with db.session() as conn:
                ids.append(repo.create(conn, {"terreno": "X"}, self.actors[0], "pg-carrera", "h")["terreno"]["id"])

        hilos = [threading.Thread(target=crear) for _ in range(3)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual((len(set(ids)), self.count("inventory_terrain")), (1, 1))

    def test_backup_carries_inventory_and_accounts_not_sessions(self):
        self.create()
        with db.session() as conn:
            auth.login(conn, "ana", TEST_PASSWORD)
        postgres.backup()
        with db.session() as conn:
            payload = json.loads(conn.execute(
                "SELECT payload FROM workspace_backup ORDER BY id DESC LIMIT 1").fetchone()["payload"])
        self.assertEqual(len(payload["inventory_terrain"]), 1)
        self.assertEqual(len(payload["team_user"]), 3)
        self.assertNotIn("team_session", payload)

    def test_schema_command_creates_and_repeats_on_an_empty_target(self):
        import contextlib
        import io

        import psycopg
        from psycopg.conninfo import make_conninfo
        spec = importlib.util.spec_from_file_location(
            "esquema_pg", Path(__file__).parents[1] / "scripts" / "esquema.py")
        esquema = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(esquema)
        vacio = "test_ara_vacio_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{vacio}"')
        try:
            with patch.dict(os.environ, {"ARA_ESQUEMA_PRUEBA": make_conninfo(URL, options=f"-c search_path={vacio}")}), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(esquema.main(["--url-env", "ARA_ESQUEMA_PRUEBA", "--check"]), 1)
                for _ in range(2):
                    self.assertEqual(esquema.main(["--url-env", "ARA_ESQUEMA_PRUEBA"]), 0)
                self.assertEqual(esquema.main(["--url-env", "ARA_ESQUEMA_PRUEBA", "--check"]), 0)
        finally:
            with psycopg.connect(URL) as conn:
                conn.execute(f'DROP SCHEMA "{vacio}" CASCADE')

    def test_the_cloud_adapter_end_to_end(self):
        spec = importlib.util.spec_from_file_location(
            "cloud_adapter_pg", Path(__file__).parents[1] / "api" / "index.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def call(method, path, body=None, headers=None):
            connection = HTTPConnection("127.0.0.1", httpd.server_port)
            connection.request(method, path, body=json.dumps(body) if body is not None else None,
                               headers={"Host": "ara.example", **(headers or {})})
            response = connection.getresponse()
            result = response.status, json.loads(response.read()), dict(response.getheaders())
            connection.close()
            return result

        try:
            self.assertEqual(call("GET", "/api/bases")[0], 401)
            self.assertEqual(call("POST", "/api/login", {"username": "ana", "password": "mal"})[0], 401)
            self.assertEqual(self.count("team_login_failure"), 1)  # committed despite the 401
            jars = {}
            for nombre in ("ana", "beto"):
                status, _, headers = call("POST", "/api/login", {"username": nombre, "password": TEST_PASSWORD})
                self.assertEqual(status, 200)
                self.assertIn("Secure", headers["Set-Cookie"])
                jars[nombre] = {"Cookie": headers["Set-Cookie"].split(";")[0]}
            status, body, _ = call("POST", "/api/inventario/terrenos", {"terreno": "Nube"},
                                   {**jars["ana"], "Idempotency-Key": "nube-clave-1"})
            self.assertEqual(status, 200)
            tid = body["terreno"]["id"]
            status, body, _ = call("PATCH", f"/api/inventario/terrenos/{tid}",
                                   {"expected_version": 1, "changes": {"terreno": "Nube B"}}, jars["beto"])
            self.assertEqual((status, body["terreno"]["updated_by"]["display_name"]), (200, "Beto"))
            status, body, _ = call("PATCH", f"/api/inventario/terrenos/{tid}",
                                   {"expected_version": 1, "changes": {"terreno": "Nube A"}}, jars["ana"])
            self.assertEqual((status, body["detalle"]["code"]), (409, "conflict"))
            status, body, _ = call("GET", "/api/inventario/terrenos", headers=jars["ana"])
            self.assertEqual((status, body["total"]), (200, 1))
            self.assertEqual(call("POST", "/api/logout", headers=jars["ana"])[0], 200)
            self.assertEqual(call("GET", "/api/inventario/terrenos", headers=jars["ana"])[0], 401)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()

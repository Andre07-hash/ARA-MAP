"""Stage 2 on a real, disposable Postgres, through the cloud adapter.

Runs only when ARA_MAP_TEST_DATABASE_URL names a disposable database; the
class works in its own schema and drops it. Every request goes through
api/index.py, so the Postgres session, advisory lock and generic-error paths
are the deployed ones.
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
from tests.test_inventario import COMPLETO

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
NOT_FOUND = {"error": "Terreno no encontrado.", "detalle": {"code": "not_found"}}


@unittest.skipUnless(URL, "No Postgres test connection configured")
class PublicacionPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.schema = "test_ara_pub_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
        spec = importlib.util.spec_from_file_location(
            "cloud_adapter_pub", Path(__file__).parents[1] / "api" / "index.py")
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
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def setUp(self):
        with postgres.session() as conn:
            conn.raw.execute("TRUNCATE inventory_operation_result, inventory_event, inventory_revision,"
                             " inventory_terrain, team_session, team_login_failure, team_user CASCADE")
            for n in ("ana", "beto"):
                auth.create_user(conn, n, n.capitalize(), TEST_PASSWORD, iterations=1000)
        self.jars = {n: self.login(n) for n in ("ana", "beto")}

    def call(self, method, path, body=None, user="ana", headers=None):
        connection = HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=30)
        cabeceras = {"Host": "ara.example", **(headers or {})}
        if user:
            cabeceras.update(self.jars[user])
        connection.request(method, path, body=json.dumps(body) if body is not None else None,
                           headers=cabeceras)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def login(self, name, password=TEST_PASSWORD, client="198.51.100.1"):
        connection = HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=30)
        connection.request("POST", "/api/login", json.dumps({"username": name, "password": password}),
                           {"Host": "ara.example", "X-Forwarded-For": client})
        response = connection.getresponse()
        response.read()
        connection.close()
        if response.status != 200:
            return response.status
        return {"Cookie": response.getheader("Set-Cookie").split(";")[0]}

    def create(self, **changes):
        status, body = self.call("POST", "/api/inventario/terrenos", {**COMPLETO, **changes},
                                 headers={"Idempotency-Key": f"pg-{uuid.uuid4()}"})
        self.assertEqual(status, 200, body)
        return body["terreno"]

    def act(self, t, action, version=None, revision_id=None, user="ana"):
        body = {"expected_version": version or t["version"]}
        if action == "publicar":
            body["revision_id"] = revision_id or t["draft_revision_id"]
        return self.call("POST", f"/api/inventario/terrenos/{t['id']}/{action}", body, user)

    def test_preview_publish_public_catalog_and_withdrawal(self):
        t = self.create()
        status, preview = self.call("GET", f"/api/inventario/terrenos/{t['id']}/vista-publica"
                                           f"?revision_id={t['draft_revision_id']}")
        self.assertEqual((status, preview["blockers"], preview["terreno"]["published_at"]), (200, [], None))
        status, body = self.act(t, "publicar", user="beto")
        self.assertEqual(status, 200, body)
        published = body["terreno"]
        status, detail = self.call("GET", f"/api/publico/terrenos/{t['id']}", user=None)
        self.assertEqual(status, 200)
        self.assertEqual({**detail["terreno"], "published_at": None}, preview["terreno"])
        self.assertEqual(detail["terreno"]["published_at"], published["published_at"])
        self.assertNotIn("SENTINEL", json.dumps(detail))
        status, listing = self.call("GET", "/api/publico/terrenos?estado=Jalisco", user=None)
        self.assertEqual((status, listing["total"], listing["terrenos"]), (200, 1, [detail["terreno"]]))

        # A saved draft stays private; the public result keeps the published revision.
        status, body = self.call("PATCH", f"/api/inventario/terrenos/{t['id']}",
                                 {"expected_version": 2, "changes": {"availability": "sold"}})
        sold = body["terreno"]
        self.assertTrue(sold["has_pending_changes"])
        self.assertEqual(self.call("GET", f"/api/publico/terrenos/{t['id']}", user=None)[1]["terreno"]
                         ["availability"], "available")
        # CON-02: the stale publish loses with no partial change.
        status, body = self.act(t, "publicar", version=2, revision_id=t["draft_revision_id"])
        self.assertEqual((status, body["detalle"]["code"]), (409, "conflict"))
        status, body = self.act(sold, "publicar", revision_id=t["draft_revision_id"])
        self.assertEqual((status, body["detalle"]["code"]), (409, "revision_changed"))
        self.assertEqual(self.act(sold, "publicar")[0], 200)
        self.assertEqual(self.call("GET", f"/api/publico/terrenos/{t['id']}", user=None), (404, NOT_FOUND))
        self.assertEqual(self.call("GET", "/api/publico/terrenos", user=None)[1]["total"], 0)

    def test_unpublish_archive_restore_and_uniform_404(self):
        t = self.act(self.create(), "publicar")[1]["terreno"]
        u = self.act(t, "despublicar")[1]["terreno"]
        self.assertEqual(u["publication_state"], "unpublished")
        self.assertEqual(self.call("GET", f"/api/publico/terrenos/{t['id']}", user=None), (404, NOT_FOUND))
        p = self.act(u, "publicar")[1]["terreno"]
        a = self.act(p, "archivar")[1]["terreno"]
        self.assertEqual((a["publication_state"], a["published_revision_id"]), ("archived", None))
        self.assertEqual(self.act(a, "restaurar", version=a["version"] - 1)[1]["detalle"]["code"], "conflict")
        r = self.act(a, "restaurar")[1]["terreno"]
        self.assertEqual((r["publication_state"], r["public_visible"]), ("unpublished", False))
        draft = self.create(terreno="Borrador")
        for tid in (t["id"], draft["id"], str(uuid.uuid4()), "x"):
            self.assertEqual(self.call("GET", f"/api/publico/terrenos/{tid}", user=None), (404, NOT_FOUND))
        self.assertEqual(self.call("GET", "/api/publico/terrenos?contacto=x", user=None)[0], 422)
        with db.session() as conn:
            eventos, total, _ = repo.history(conn, t["id"], None, 20)
        self.assertEqual([e["action"] for e in eventos],
                         ["restore", "archive", "publish", "unpublish", "publish", "create"])

    def test_simultaneous_publishes_on_separate_connections_have_one_winner(self):
        t = self.create()
        results = []
        barrier = threading.Barrier(3)

        def go(user):
            barrier.wait()
            results.append(self.act(t, "publicar", user=user)[0])

        threads = [threading.Thread(target=go, args=(u,)) for u in ("ana", "beto", "ana")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [200, 409, 409])
        with db.session() as conn:
            self.assertEqual(repo.get(conn, t["id"])["version"], 2)
            eventos, total, _ = repo.history(conn, t["id"], None, 10)
        self.assertEqual(total, 2)

    def test_generic_500_and_login_throttle_per_client(self):
        with patch.object(repo, "public_records", side_effect=RuntimeError("SECRETO-PG")):
            status, body = self.call("GET", "/api/publico/terrenos", user=None)
        self.assertEqual((status, body["detalle"]), (500, {"code": "internal"}))
        self.assertNotIn("SECRETO", json.dumps(body))
        for _ in range(auth.MAX_FAILURES):
            self.assertEqual(self.login("ana", "incorrecta", client="203.0.113.50"), 401)
        self.assertEqual(self.login("ana", client="203.0.113.50"), 429)
        self.assertIsInstance(self.login("ana", client="203.0.113.51"), dict)
        self.assertEqual(self.call("GET", "/api/config", user=None)[1]["readOnly"], False)

    def test_a_v8_workspace_without_the_client_column_gains_it(self):
        with postgres.session() as conn:
            conn.raw.execute("DROP INDEX IF EXISTS idx_team_login_failure_client")
            conn.raw.execute("ALTER TABLE team_login_failure DROP COLUMN client")
        with postgres.session() as conn:
            postgres.migrate(conn)
        with postgres.session() as conn:
            postgres.migrate(conn)  # twice: idempotent
            columns = {r["column_name"] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?"
                " AND table_schema = current_schema()", ("team_login_failure",))}
        self.assertIn("client", columns)
        self.assertEqual(self.login("ana", "incorrecta"), 401)


if __name__ == "__main__":
    unittest.main()

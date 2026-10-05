"""Tests for the HTTP plumbing: routing, payloads, staging and the database."""

from __future__ import annotations

import json
import unittest

from server import db
from server.router import Request, Router
from server.staging import Staging
from server.web_util import ApiError, encode, parse_json, require
from tests.support import TempDatabase


class Routing(unittest.TestCase):
    def setUp(self):
        self.router = Router()
        self.router.add("GET", "/api/bases", lambda r: "listing")
        self.router.add("GET", "/api/bases/:id", lambda r: "detail")
        self.router.add("POST", "/api/bases/:id/adjuntar", lambda r: "append")

    def test_matches_a_static_path(self):
        handler, ctx = self.router.resolve("GET", "/api/bases")
        self.assertEqual(handler(None), "listing")
        self.assertEqual(ctx["params"], {})

    def test_captures_a_path_parameter(self):
        handler, ctx = self.router.resolve("GET", "/api/bases/42")
        self.assertEqual(ctx["params"], {"id": "42"})

    def test_parses_the_query_string(self):
        _, ctx = self.router.resolve("GET", "/api/bases/7?base_id=3&x=1")
        self.assertEqual(ctx["query"]["base_id"], ["3"])

    def test_ignores_a_trailing_slash(self):
        handler, _ = self.router.resolve("GET", "/api/bases/")
        self.assertEqual(handler(None), "listing")

    def test_reports_a_known_path_with_the_wrong_method(self):
        handler, other = self.router.resolve("DELETE", "/api/bases")
        self.assertIsNone(handler)
        self.assertTrue(other)

    def test_reports_an_unknown_path(self):
        handler, other = self.router.resolve("GET", "/nada")
        self.assertIsNone(handler)
        self.assertFalse(other)

    def test_a_parameter_does_not_swallow_a_slash(self):
        handler, _ = self.router.resolve("GET", "/api/bases/7/extra")
        self.assertIsNone(handler)


class RequestHelpers(unittest.TestCase):
    def make(self, query=None, params=None):
        return Request("GET", "/x", query or {}, params or {}, b"", {})

    def test_param_is_returned_as_an_integer(self):
        self.assertEqual(self.make(params={"id": "12"}).param("id"), 12)

    def test_query_returns_the_first_value_or_the_default(self):
        request = self.make(query={"base_id": ["3", "4"]})
        self.assertEqual(request.q("base_id"), "3")
        self.assertIsNone(request.q("falta"))
        self.assertEqual(request.q("falta", "x"), "x")


class Payloads(unittest.TestCase):
    def test_encode_keeps_accents_readable(self):
        self.assertIn("México", encode({"estado": "México"}).decode())

    def test_encode_handles_tuples_and_sets(self):
        self.assertEqual(json.loads(encode({"a": (1, 2)}))["a"], [1, 2])

    def test_an_empty_body_is_an_empty_payload(self):
        self.assertEqual(parse_json(b""), {})

    def test_malformed_json_is_reported_clearly(self):
        with self.assertRaises(ApiError) as caught:
            parse_json(b"{nope")
        self.assertIn("inválido", caught.exception.mensaje)

    def test_a_non_object_payload_is_rejected(self):
        with self.assertRaises(ApiError):
            parse_json(b"[1,2]")

    def test_require_returns_the_values_in_order(self):
        self.assertEqual(require({"a": 1, "b": 2}, "a", "b"), (1, 2))

    def test_require_names_every_missing_field(self):
        with self.assertRaises(ApiError) as caught:
            require({"a": 1}, "a", "b", "c")
        self.assertIn("b", caught.exception.mensaje)
        self.assertIn("c", caught.exception.mensaje)

    def test_an_empty_string_counts_as_missing(self):
        with self.assertRaises(ApiError):
            require({"nombre": ""}, "nombre")

    def test_api_error_carries_its_status(self):
        self.assertEqual(ApiError("x", 404).status, 404)
        self.assertEqual(ApiError("x").status, 400)


class PendingImports(unittest.TestCase):
    def test_a_token_is_single_use(self):
        staging = Staging()
        pending = staging.put("a.xlsx", "a", "resultado", {})
        self.assertIsNotNone(staging.take(pending.token))
        self.assertIsNone(staging.take(pending.token))

    def test_an_unknown_token_is_none(self):
        self.assertIsNone(Staging().take("no-existe"))

    def test_the_oldest_pending_import_is_evicted(self):
        staging = Staging()
        tokens = [staging.put(f"{i}.xlsx", str(i), None, {}).token for i in range(12)]
        surviving = [t for t in tokens if staging.take(t) is not None]
        self.assertLessEqual(len(surviving), 8)
        self.assertNotIn(tokens[0], surviving)

    def test_the_payload_comes_back_intact(self):
        staging = Staging()
        pending = staging.put("base.xlsx", "base", ["registro"], {1: "hallazgo"})
        recovered = staging.take(pending.token)
        self.assertEqual(recovered.resultado, ["registro"])
        self.assertEqual(recovered.incidencias, {1: "hallazgo"})


class Database(TempDatabase):
    def test_the_schema_is_created_on_first_connect(self):
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"base", "terreno", "incidencia", "mapa", "mapa_capa"} <= tables)

    def test_foreign_keys_are_enforced(self):
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_migrating_twice_is_harmless(self):
        db.migrate(self.conn)
        db.migrate(self.conn)
        self.assertEqual(
            self.conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)

    def test_backing_up_a_missing_database_is_not_an_error(self):
        self.assertIsNone(db.backup(self.db_path.parent / "no-existe.db"))

    def test_a_backup_lands_beside_its_own_database(self):
        """A test database must never write into the production folder."""
        destino = db.backup(self.db_path)
        self.assertIsNotNone(destino)
        self.assertEqual(destino.parent, self.db_path.parent / "respaldos")
        self.assertTrue(destino.parent.is_relative_to(self.db_path.parent))

    def test_a_backup_restores_the_data(self):
        self.conn.execute(
            "INSERT INTO base (nombre, importado_en) VALUES ('Antes', 'x')")
        copia = db.backup(self.db_path)

        self.conn.execute("DELETE FROM base")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM base").fetchone()[0], 0)

        import shutil
        self.conn.close()
        shutil.copy2(copia, self.db_path)
        self.conn = db.connect(self.db_path)
        self.assertEqual(
            self.conn.execute("SELECT nombre FROM base").fetchone()["nombre"], "Antes")

    def test_the_map_type_is_constrained(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO mapa (nombre, tipo, creado_en) VALUES ('x', 'otro', 'ahora')")


if __name__ == "__main__":
    unittest.main()

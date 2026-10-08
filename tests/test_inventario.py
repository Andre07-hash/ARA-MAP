"""Stage 1 inventory: equal team accounts, permanent ids, version-checked
drafts, idempotent creation, history and the internal list contract.

Runs the real local HTTP handler (so the shared sign-in policy is exercised)
on a throwaway SQLite file with fictional users.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import app as app_module
from server import db, inventario
from server.repo import inventario as repo
from tests.support import TempDatabase, create_user, session_cookie

COMPLETO = {"terreno": "Lote Ñandú", "estado": "Jalisco", "municipio": "Zapopan",
            "superficie_m2": 12000, "superficie_ha": 1.2, "lat": 20.7, "lon": -103.4,
            "asking_price": 1470000, "asking_m2": 122.5, "moneda": "USD",
            "availability": "available", "contacto": "SENTINEL-CONTACTO",
            "notas_internas": "SENTINEL-NOTA"}


class InventoryServer(TempDatabase):
    def setUp(self):
        super().setUp()
        self.users = {n: create_user(self.conn, n, n.capitalize()) for n in ("ana", "beto", "carla")}
        self.cookies = {n: session_cookie(self.conn, n) for n in self.users}
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def call(self, method, path, body=None, user="ana", headers=None):
        cabeceras = {"Content-Type": "application/json", **(headers or {})}
        if user:
            cabeceras["Cookie"] = self.cookies[user]
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None, headers=cabeceras)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def create(self, fields=None, user="ana", key=None):
        return self.call("POST", "/api/inventario/terrenos", fields if fields is not None else {"terreno": "Lote"},
                         user, {"Idempotency-Key": key or f"k-{uuid.uuid4()}"})

    def patch(self, tid, version, changes, user="ana", **extra):
        return self.call("PATCH", f"/api/inventario/terrenos/{tid}",
                         {"expected_version": version, "changes": changes, **extra}, user)

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class EqualTeamAccess(InventoryServer):
    def test_three_users_create_edit_and_reopen_each_others_records(self):
        status, body = self.create(COMPLETO, "ana")
        self.assertEqual(status, 200)
        t = body["terreno"]
        self.assertEqual((t["version"], t["publication_state"], t["public_visible"]), (1, "draft", False))
        self.assertEqual(t["created_by"]["display_name"], "Ana")

        status, body = self.patch(t["id"], 1, {"terreno": "Lote Renombrado"}, "beto")
        self.assertEqual(status, 200)
        status, body = self.patch(t["id"], 2, {"notas_internas": "otra nota"}, "carla")
        self.assertEqual((status, body["terreno"]["version"]), (200, 3))

        # A fresh read by the creator sees everyone's saved values, same id.
        status, body = self.call("GET", f"/api/inventario/terrenos/{t['id']}", user="ana")
        reread = body["terreno"]
        self.assertEqual((reread["id"], reread["version"]), (t["id"], 3))
        self.assertEqual(reread["draft"]["terreno"], "Lote Renombrado")
        self.assertEqual(reread["draft"]["notas_internas"], "otra nota")
        self.assertEqual(reread["updated_by"]["display_name"], "Carla")

        status, body = self.call("GET", f"/api/inventario/terrenos/{t['id']}/historial", user="beto")
        self.assertEqual([(e["version"], e["action"], e["actor"]["display_name"]) for e in body["eventos"]],
                         [(3, "update", "Carla"), (2, "update", "Beto"), (1, "create", "Ana")])
        self.assertEqual(body["eventos"][1]["changes"],
                         {"terreno": {"before": "Lote Ñandú", "after": "Lote Renombrado"}})

    def test_actor_and_server_fields_cannot_be_sent(self):
        for campo in ("id", "version", "created_by", "updated_by", "actor_id", "published_revision_id",
                      "draft_revision_id", "price_confirmed_by", "extra_json"):
            with self.subTest(campo=campo):
                status, body = self.create({"terreno": "X", campo: "spoof"})
                self.assertEqual(status, 422)
                self.assertIn(campo, body["detalle"]["fields"])
        _, body = self.create()
        status, body = self.patch(body["terreno"]["id"], 1, {"updated_by": self.users["beto"]["id"]})
        self.assertEqual(status, 422)
        self.assertEqual(self.count("inventory_terrain"), 1)

    def test_signed_out_and_anonymous_get_nothing(self):
        _, body = self.create(COMPLETO)
        tid = body["terreno"]["id"]
        for method, path in (("GET", "/api/inventario/terrenos"), ("GET", f"/api/inventario/terrenos/{tid}"),
                             ("GET", f"/api/inventario/terrenos/{tid}/historial"),
                             ("PATCH", f"/api/inventario/terrenos/{tid}"), ("POST", "/api/inventario/terrenos")):
            with self.subTest(method=method, path=path):
                status, body = self.call(method, path, {} if method != "GET" else None, user=None)
                self.assertEqual(status, 401)
                self.assertNotIn("SENTINEL", json.dumps(body))
        status, body = self.call("GET", f"/api/publico/terrenos/{tid}", user=None)
        self.assertEqual(status, 404)
        status, body = self.call("GET", "/api/publico/terrenos", user=None)
        self.assertEqual(body["total"], 0)  # Stage 1: nothing can be published yet


class CreateIdempotency(InventoryServer):
    def test_key_is_required_and_nothing_is_created_without_it(self):
        status, body = self.call("POST", "/api/inventario/terrenos", {"terreno": "Sin clave"})
        self.assertEqual((status, body["detalle"]["code"]), (422, "idempotency_key_required"))
        self.assertEqual(self.count("inventory_terrain"), 0)

    def test_same_key_replays_and_different_body_conflicts(self):
        _, first = self.create({"terreno": "Uno"}, key="clave-fija-1")
        _, again = self.create({"terreno": "Uno"}, "beto", key="clave-fija-1")
        self.assertEqual(again, first)
        status, body = self.create({"terreno": "Dos"}, key="clave-fija-1")
        self.assertEqual((status, body["detalle"]["code"]), (409, "idempotency_conflict"))
        self.assertEqual((self.count("inventory_terrain"), self.count("inventory_event")), (1, 1))

    def test_concurrent_same_key_creates_one_record(self):
        resultados = []
        barrera = threading.Barrier(4)

        def crear():
            barrera.wait()
            resultados.append(self.create({"terreno": "Carrera"}, key="clave-carrera"))

        hilos = [threading.Thread(target=crear) for _ in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual({s for s, _ in resultados}, {200})
        self.assertEqual(len({b["terreno"]["id"] for _, b in resultados}), 1)
        self.assertEqual(self.count("inventory_terrain"), 1)

    def test_a_failure_mid_create_leaves_nothing(self):
        with patch.object(repo, "_event", side_effect=RuntimeError("falla simulada")):
            status, _ = self.create({"terreno": "Fallido"}, key="clave-falla")
        self.assertEqual(status, 500)
        for tabla in ("inventory_terrain", "inventory_revision", "inventory_event",
                      "inventory_operation_result"):
            self.assertEqual(self.count(tabla), 0, tabla)
        status, body = self.create({"terreno": "Fallido"}, key="clave-falla")  # retry works
        self.assertEqual(status, 200)


class VersionChecks(InventoryServer):
    def test_stale_save_is_a_recoverable_conflict_with_no_partial_change(self):
        _, body = self.create(COMPLETO)
        tid = body["terreno"]["id"]
        self.assertEqual(self.patch(tid, 1, {"asking_price": 1500000}, "ana")[0], 200)
        revisiones = self.count("inventory_revision")
        status, body = self.patch(tid, 1, {"notas_internas": "de Beto"}, "beto")
        self.assertEqual(status, 409)
        self.assertEqual(body["detalle"]["code"], "conflict")
        self.assertEqual(body["detalle"]["current_version"], 2)
        self.assertEqual(body["detalle"]["terreno"]["draft"]["asking_price"], 1500000)
        self.assertEqual((self.count("inventory_revision"), self.count("inventory_event")), (revisiones, 2))
        # Beto reloads and deliberately saves against the current version.
        status, body = self.patch(tid, 2, {"notas_internas": "de Beto"}, "beto")
        self.assertEqual((status, body["terreno"]["version"]), (200, 3))
        self.assertEqual(body["terreno"]["draft"]["asking_price"], 1500000)

    def test_simultaneous_saves_of_one_version_have_one_winner(self):
        _, body = self.create(COMPLETO)
        tid = body["terreno"]["id"]
        resultados = {}
        barrera = threading.Barrier(3)

        def guardar(usuario):
            barrera.wait()
            resultados[usuario] = self.patch(tid, 1, {"terreno": f"De {usuario}"}, usuario)[0]

        hilos = [threading.Thread(target=guardar, args=(u,)) for u in self.users]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sorted(resultados.values()), [200, 409, 409])
        self.assertEqual(self.count("inventory_event"), 2)

    def test_a_failure_mid_save_rolls_everything_back(self):
        _, body = self.create(COMPLETO)
        tid = body["terreno"]["id"]
        with patch.object(repo, "_event", side_effect=RuntimeError("falla simulada")):
            self.assertEqual(self.patch(tid, 1, {"terreno": "Nunca"})[0], 500)
        _, body = self.call("GET", f"/api/inventario/terrenos/{tid}")
        self.assertEqual((body["terreno"]["version"], body["terreno"]["draft"]["terreno"]), (1, "Lote Ñandú"))
        self.assertEqual((self.count("inventory_revision"), self.count("inventory_event")), (1, 1))

    def test_an_unchanged_save_creates_no_version(self):
        _, body = self.create(COMPLETO)
        status, body = self.patch(body["terreno"]["id"], 1, {"terreno": "Lote Ñandú"})
        self.assertEqual((status, body["terreno"]["version"]), (200, 1))
        self.assertEqual(self.count("inventory_revision"), 1)

    def test_revisions_are_immutable_and_pointers_stay_within_a_record(self):
        _, a = self.create({"terreno": "A"})
        _, b = self.create({"terreno": "B"})
        a, b = a["terreno"], b["terreno"]
        self.patch(a["id"], 1, {"terreno": "A2"})
        primera = self.conn.execute("SELECT terreno FROM inventory_revision WHERE id = ?",
                                    (a["draft_revision_id"],)).fetchone()[0]
        self.assertEqual(primera, "A")
        with self.assertRaises(sqlite3.IntegrityError), db.transaction(self.conn):  # B's revision is not A's
            self.conn.execute("UPDATE inventory_terrain SET published_revision_id = ? WHERE id = ?",
                              (b["draft_revision_id"], a["id"]))

    def test_confirmations_are_explicit_and_survive_ordinary_edits(self):
        _, body = self.create(COMPLETO)
        tid = body["terreno"]["id"]
        self.assertEqual(body["terreno"]["confirmations"], {"price": None, "availability": None})
        codes = {r["code"] for r in body["terreno"]["attention"]}
        self.assertEqual(codes & {"price_unconfirmed", "availability_unconfirmed"},
                         {"price_unconfirmed", "availability_unconfirmed"})
        _, body = self.patch(tid, 1, {}, "beto", confirm=["price"])
        stamp = body["terreno"]["confirmations"]["price"]
        self.assertEqual(stamp["by"]["display_name"], "Beto")
        _, body = self.patch(tid, 2, {"public_description": "Nuevo texto"}, "carla")
        self.assertEqual(body["terreno"]["confirmations"]["price"], stamp)
        self.assertIsNone(body["terreno"]["confirmations"]["availability"])


class FieldValidation(InventoryServer):
    def test_invalid_values_are_422_and_change_nothing(self):
        _, body = self.create(COMPLETO)
        tid = body["terreno"]["id"]
        for changes, campo in (({"superficie_m2": -1}, "superficie_m2"), ({"lat": 91}, "lat"),
                               ({"asking_price": "mucho"}, "asking_price"), ({"moneda": "EUR"}, "moneda"),
                               ({"availability": "vendido"}, "availability"),
                               ({"price_on_request": "si"}, "price_on_request"),
                               ({"terreno": 5}, "terreno"), ({"lon": float("inf")}, "lon"),
                               ({"moneda": None, "asking_price": 5}, "moneda")):
            with self.subTest(changes=changes):
                status, body = self.patch(tid, 1, changes)
                self.assertEqual(status, 422)
                self.assertEqual(body["detalle"]["code"], "validation_failed")
                self.assertIn(campo, body["detalle"]["fields"])
        for version in ("1", True, None, 0):
            self.assertEqual(self.patch(tid, version, {"terreno": "Y"})[0], 422)
        self.assertEqual(self.count("inventory_revision"), 1)

    def test_nonfinite_numbers_are_rejected(self):
        raw = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}/api/inventario/terrenos", method="POST",
            data=b'{"terreno": "N", "superficie_m2": NaN}',
            headers={"Cookie": self.cookies["ana"], "Idempotency-Key": "clave-nan-2"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(raw, timeout=10)
        with caught.exception as error:
            self.assertEqual(error.code, 422)

    def test_incomplete_drafts_save_and_unknowns_stay_null(self):
        status, body = self.create({})
        self.assertEqual(status, 200)
        draft = body["terreno"]["draft"]
        self.assertTrue(all(draft[n] is None for n in ("terreno", "moneda", "asking_price", "lat")))
        self.assertEqual((draft["availability"], draft["price_on_request"]), ("unknown", False))
        # Half or swapped pairs are drafts, not save errors (§9); they block publication.
        for coords in ({"lat": 20.5}, {"lat": -20.7, "lon": 103.4}, {"lat": 40.4, "lon": -3.7}):
            status, body = self.create({"terreno": "C", **coords})
            self.assertEqual(status, 200, coords)
            self.assertIn("location_invalid", {r["code"] for r in body["terreno"]["attention"]})
        status, body = self.create({"terreno": "=HYPERLINK(\"x\")", "asking_m2": 122.5, "moneda": "USD"})
        self.assertEqual(body["terreno"]["draft"]["terreno"], "=HYPERLINK(\"x\")")  # literal text
        self.assertEqual(body["terreno"]["draft"]["asking_m2"], 122.5)  # cents kept


class InternalList(InventoryServer):
    def seed(self, n, **fields):
        actor = {"id": self.users["ana"]["id"], "display_name": "Ana"}
        ids = []
        for i in range(n):
            datos = {**fields, "terreno": f"T{i}"}
            body = repo.create(self.conn, datos, actor, f"seed-{uuid.uuid4()}", "h")
            ids.append(body["terreno"]["id"])
        return ids

    def test_251_records_page_without_gaps_or_duplicates(self):
        ids = self.seed(251)
        for limit, pages in ((None, 3), ("250", 2)):
            vistos, cursor, paginas = [], None, 0
            while True:
                query = "&".join(p for p in (f"limit={limit}" if limit else "",
                                             f"cursor={cursor}" if cursor else "") if p)
                status, body = self.call("GET", f"/api/inventario/terrenos?{query}")
                self.assertEqual(status, 200)
                self.assertEqual(body["total"], 251)
                vistos += [t["id"] for t in body["terrenos"]]
                paginas += 1
                cursor = body["next_cursor"]
                if not cursor:
                    break
            self.assertEqual((paginas, vistos), (pages, sorted(ids)))

    def test_filters_facets_and_mixed_currency(self):
        self.seed(2, estado="Jalisco", municipio="Zapopan", asking_price=100, moneda="USD", superficie_m2=10)
        self.seed(1, estado="Jalisco", municipio="Tlajomulco", asking_price=100, moneda="MXN")
        self.seed(1, estado="Nuevo León", municipio="García", asking_price=100)  # unknown currency
        _, body = self.call("GET", "/api/inventario/terrenos?estado=Jalisco&estado=Nuevo%20Le%C3%B3n&limit=1")
        self.assertEqual((body["total"], len(body["terrenos"])), (4, 1))
        self.assertEqual(body["facets"]["estados"], ["Jalisco", "Nuevo León"])
        self.assertEqual(body["facets"]["monedas"], ["MXN", "USD"])
        _, body = self.call("GET", "/api/inventario/terrenos?estado=Jalisco")
        self.assertEqual(body["facets"]["municipios"], ["Tlajomulco", "Zapopan"])
        _, body = self.call("GET", "/api/inventario/terrenos?moneda=USD&price_min=50&price_max=150")
        self.assertEqual(body["total"], 2)  # MXN and unknown currency left out
        _, body = self.call("GET", "/api/inventario/terrenos?q=garcia")
        self.assertEqual(body["total"], 1)  # accent-insensitive
        _, body = self.call("GET", "/api/inventario/terrenos?area_min_m2=5")
        self.assertEqual(body["total"], 2)
        _, body = self.call("GET", "/api/inventario/terrenos?attention=false")
        self.assertEqual(body["total"], 0)
        _, body = self.call("GET", "/api/inventario/terrenos?publication_state=draft&availability=unknown")
        self.assertEqual(body["total"], 4)

    def test_invalid_filters_are_422(self):
        for query in ("price_min=5", "limit=251", "limit=0", "moneda=EUR", "contacto=x",
                      "publication_state=vendido", "attention=quizas", "area_min_m2=abc"):
            with self.subTest(query=query):
                self.assertEqual(self.call("GET", f"/api/inventario/terrenos?{query}")[0], 422)

    def test_history_pages_newest_first(self):
        tid = self.seed(1)[0]
        for version in range(1, 5):
            self.patch(tid, version, {"terreno": f"Nombre {version}"})
        _, body = self.call("GET", f"/api/inventario/terrenos/{tid}/historial?limit=2")
        self.assertEqual(([e["version"] for e in body["eventos"]], body["total"]), ([5, 4], 5))
        _, body = self.call("GET", f"/api/inventario/terrenos/{tid}/historial?limit=2&cursor={body['next_cursor']}")
        self.assertEqual([e["version"] for e in body["eventos"]], [3, 2])
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{uuid.uuid4()}/historial")[0], 404)
        self.assertEqual(self.call("GET", "/api/inventario/terrenos/no-es-uuid")[0], 404)


class PublicationRules(unittest.TestCase):
    def codes(self, **draft):
        return {b["code"] for b in inventario.publication_blockers({**inventario.empty_draft(), **draft})}

    def test_contract_v1_gate(self):
        listo = {k: v for k, v in COMPLETO.items() if k in inventario.EDITABLE}
        self.assertEqual(self.codes(**listo), set())
        self.assertEqual(self.codes(), {"name_required", "location_invalid", "area_required",
                                        "availability_unknown", "price_required"})
        self.assertEqual(self.codes(**{**listo, "lat": 40.4, "lon": -3.7}), {"location_invalid"})
        self.assertEqual(self.codes(**{**listo, "moneda": None}), {"currency_required"})
        self.assertEqual(self.codes(**{**listo, "price_on_request": True}), {"price_conflict"})
        self.assertEqual(self.codes(**{**listo, "price_on_request": True, "asking_price": None,
                                       "asking_m2": None, "moneda": None}), set())

    def test_inconsistent_prices_warn_without_correction(self):
        draft = {**inventario.empty_draft(), "terreno": "X", "superficie_m2": 1000,
                 "asking_price": 1000, "asking_m2": 50, "moneda": "MXN"}
        self.assertIn("PRECIO_INCONSISTENTE", {w["code"] for w in inventario.warnings(draft)})
        self.assertEqual(draft["asking_price"], 1000)


class SchemaV8(TempDatabase):
    def legacy_digest(self):
        return {t: [tuple(r) for r in self.conn.execute(f"SELECT * FROM {t} ORDER BY 1")]
                for t in ("base", "terreno", "incidencia", "mapa", "mapa_capa", "mapa_terreno")}

    def test_v7_file_upgrades_additively_with_a_backup_and_repeats_safely(self):
        from server.repo import mapas
        base_id, _ = self.load_fixture()
        mapas.create(self.conn, "Mapa", "simple", [{"base_id": base_id, "color": "#123456", "visible": True}])
        create_user(self.conn)
        session_cookie(self.conn)
        antes = self.legacy_digest()
        # Back to a v7 file: no inventory or account tables.
        for tabla in ("inventory_operation_result", "inventory_event", "inventory_terrain",
                      "inventory_revision", "team_session", "team_login_failure", "team_user"):
            self.conn.execute(f"DROP TABLE {tabla}")
        self.conn.execute("PRAGMA user_version = 7")
        self.conn.close()
        for _ in range(2):
            self.conn = db.connect(self.db_path)
            self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            self.assertEqual(self.legacy_digest(), antes)
            self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM inventory_terrain").fetchone()[0], 0)
            self.conn.close()
        respaldos = list(db.backup_dir(self.db_path).glob("*.db"))
        self.assertEqual(len(respaldos), 1)  # only the real upgrade took one
        self.conn = db.connect(self.db_path)

    def test_backups_carry_accounts_but_not_sessions(self):
        create_user(self.conn)
        session_cookie(self.conn)
        copia = sqlite3.connect(db.backup(self.db_path))
        try:
            self.assertEqual(copia.execute("SELECT COUNT(*) FROM team_user").fetchone()[0], 1)
            self.assertEqual(copia.execute("SELECT COUNT(*) FROM team_session").fetchone()[0], 0)
        finally:
            copia.close()


if __name__ == "__main__":
    unittest.main()

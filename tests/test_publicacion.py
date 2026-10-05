"""Stage 2: publication lifecycle, the saved-draft preview and the real public
catalog, plus the carried-forward fixes (generic 500, login throttle keyed by
login and client, config.readOnly).

Runs the real local HTTP handler on a throwaway SQLite file with fictional
users. The catalog must only ever show the revision the published pointer
names, through the one PublicTerrain serializer.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from unittest.mock import patch

from server import auth, inventario
from server.repo import inventario as repo
from tests.support import TEST_PASSWORD, TempDatabase, create_user
from tests.test_inventario import COMPLETO, InventoryServer

PUBLIC_KEYS = set(inventario.PUBLIC_FIELDS)
SENTINELS = ("SENTINEL-CONTACTO", "SENTINEL-NOTA")


class PublicationServer(InventoryServer):
    def anon(self, path):
        return self.call("GET", path, user=None)

    def publishable(self, **changes):
        status, body = self.create({**COMPLETO, **changes})
        self.assertEqual(status, 200, body)
        return body["terreno"]

    def preview(self, terreno, user="ana", revision_id=None):
        rid = revision_id or terreno["draft_revision_id"]
        return self.call("GET", f"/api/inventario/terrenos/{terreno['id']}/vista-publica"
                         f"?revision_id={rid}", user=user)

    def act(self, terreno, action, user="ana", version=None, revision_id=None):
        body = {"expected_version": version or terreno["version"]}
        if action == "publicar":
            body["revision_id"] = revision_id or terreno["draft_revision_id"]
        return self.call("POST", f"/api/inventario/terrenos/{terreno['id']}/{action}", body, user)

    def publish(self, terreno, user="ana"):
        status, body = self.act(terreno, "publicar", user)
        self.assertEqual(status, 200, body)
        return body["terreno"]

    def internal(self, tid):
        return self.call("GET", f"/api/inventario/terrenos/{tid}")[1]["terreno"]

    def assert_no_private(self, body):
        text = json.dumps(body, ensure_ascii=False)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, text)
        for private in ("contacto", "notas_internas", "source_extra", "confirmations",
                        "created_by", "updated_by", "draft", "attention"):
            self.assertNotIn(f'"{private}"', text)

    def assert_withdrawn(self, tid):
        status, body = self.anon(f"/api/publico/terrenos/{tid}")
        self.assertEqual((status, body), (404, NOT_FOUND))
        self.assertNotIn(tid, [t["id"] for t in self.anon("/api/publico/terrenos?limit=250")[1]["terrenos"]])


NOT_FOUND = {"error": "Terreno no encontrado.", "detalle": {"code": "not_found"}}


class PublishAndPreview(PublicationServer):
    def test_preview_equals_the_published_result_except_the_commit_time(self):
        t = self.publishable()
        status, preview = self.preview(t)
        self.assertEqual(status, 200)
        self.assertEqual({k: preview[k] for k in ("id", "version", "revision_id", "preview")},
                         {"id": t["id"], "version": 1, "revision_id": t["draft_revision_id"],
                          "preview": True})
        self.assertEqual(preview["blockers"], [])
        self.assertEqual(set(preview["terreno"]), PUBLIC_KEYS)
        self.assertIsNone(preview["terreno"]["published_at"])
        self.assert_no_private(preview["terreno"])

        published = self.publish(t)
        self.assertEqual((published["version"], published["publication_state"],
                          published["public_visible"], published["has_pending_changes"]),
                         (2, "published", True, False))
        self.assertEqual(published["published_revision_id"], t["draft_revision_id"])
        self.assertIsNotNone(published["published_at"])

        status, detail = self.anon(f"/api/publico/terrenos/{t['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(set(detail), {"terreno"})
        public = detail["terreno"]
        self.assertEqual(public["published_at"], published["published_at"])
        self.assertEqual({**public, "published_at": None}, preview["terreno"])
        self.assertEqual((public["asking_m2"], public["moneda"]), (122.5, "USD"))
        self.assert_no_private(detail)

        status, listing = self.anon("/api/publico/terrenos")
        self.assertEqual(status, 200)
        self.assertEqual(listing["terrenos"], [public])
        self.assertEqual((listing["total"], listing["next_cursor"]), (1, None))
        self.assertEqual(listing["facets"], {"estados": ["Jalisco"], "municipios": ["Zapopan"],
                                             "monedas": ["USD"]})
        self.assert_no_private(listing)

        eventos = self.call("GET", f"/api/inventario/terrenos/{t['id']}/historial")[1]["eventos"]
        self.assertEqual([(e["version"], e["action"]) for e in eventos], [(2, "publish"), (1, "create")])
        self.assertEqual(eventos[0]["after_revision_id"], t["draft_revision_id"])

    def test_a_saved_draft_stays_private_until_it_is_published(self):
        t = self.publish(self.publishable())
        status, body = self.patch(t["id"], 2, {"asking_m2": 130.25, "estado": "Colima",
                                               "notas_internas": "SENTINEL-NOTA otra"}, "beto")
        self.assertEqual(status, 200)
        edited = body["terreno"]
        self.assertTrue(edited["has_pending_changes"])
        self.assertEqual(edited["pending_changes"]["asking_m2"], {"published": 122.5, "draft": 130.25})
        self.assertNotIn("notas_internas", edited["pending_changes"])
        public = self.anon(f"/api/publico/terrenos/{t['id']}")[1]["terreno"]
        self.assertEqual((public["asking_m2"], public["estado"], public["revision_id"]),
                         (122.5, "Jalisco", t["published_revision_id"]))
        # Filters and facets read the published revision, never the draft.
        self.assertEqual(self.anon("/api/publico/terrenos?estado=Colima")[1]["total"], 0)
        self.assertEqual(self.anon("/api/publico/terrenos?estado=Jalisco")[1]["total"], 1)
        self.assertEqual(self.anon("/api/publico/terrenos")[1]["facets"]["estados"], ["Jalisco"])

        again = self.publish(edited, "carla")
        public = self.anon(f"/api/publico/terrenos/{t['id']}")[1]["terreno"]
        self.assertEqual((public["asking_m2"], public["estado"], public["revision_id"]),
                         (130.25, "Colima", edited["draft_revision_id"]))
        self.assertEqual((again["version"], again["has_pending_changes"], again["updated_by"]["display_name"]),
                         (4, False, "Carla"))

    def test_a_private_only_edit_leaves_nothing_pending(self):
        t = self.publish(self.publishable())
        body = self.patch(t["id"], 2, {"contacto": "SENTINEL-CONTACTO 2"})[1]["terreno"]
        self.assertFalse(body["has_pending_changes"])
        self.assertEqual(body["pending_changes"], {})

    def test_the_publication_gate_blocks_and_changes_nothing(self):
        status, body = self.create({"terreno": "Incompleto", "lat": 40.7, "lon": -74.0})
        t = body["terreno"]
        status, preview = self.preview(t)
        self.assertEqual(status, 200)
        self.assertEqual({b["code"] for b in preview["blockers"]},
                         {"location_invalid", "area_required", "availability_unknown", "price_required"})
        status, body = self.act(t, "publicar")
        self.assertEqual((status, body["detalle"]["code"]), (422, "publication_blocked"))
        self.assertEqual({b["code"] for b in body["detalle"]["blockers"]},
                         {b["code"] for b in preview["blockers"]})
        reread = self.internal(t["id"])
        self.assertEqual((reread["version"], reread["publication_state"]), (1, "draft"))
        self.assertEqual(self.anon("/api/publico/terrenos")[1]["total"], 0)

    def test_price_on_request_and_negotiation_are_public(self):
        t = self.publishable(asking_price=None, asking_m2=None, moneda=None,
                             price_on_request=True, availability="negotiation")
        self.publish(t)
        public = self.anon(f"/api/publico/terrenos/{t['id']}")[1]["terreno"]
        self.assertEqual((public["price_on_request"], public["availability"], public["asking_price"]),
                         (True, "negotiation", None))
        status, body = self.create({**COMPLETO, "price_on_request": True})
        status, body = self.act(body["terreno"], "publicar")
        self.assertIn("price_conflict", {b["code"] for b in body["detalle"]["blockers"]})

    def test_inconsistent_prices_warn_in_preview_without_correction(self):
        t = self.publishable(asking_price=999)
        preview = self.preview(t)[1]
        self.assertIn("PRECIO_INCONSISTENTE", {w["code"] for w in preview["warnings"]})
        self.assertEqual((preview["terreno"]["asking_price"], preview["terreno"]["asking_m2"]), (999, 122.5))

    def test_preview_rejects_other_revisions_and_parameters(self):
        t = self.publishable()
        old = t["draft_revision_id"]
        edited = self.patch(t["id"], 1, {"terreno": "Lote nuevo"})[1]["terreno"]
        status, body = self.preview(t, revision_id=old)
        self.assertEqual((status, body["detalle"]["code"]), (409, "revision_changed"))
        self.assertEqual(body["detalle"]["current_version"], 2)
        other = self.publishable(terreno="Otro")
        self.assertEqual(self.preview(t, revision_id=other["draft_revision_id"])[0], 404)
        self.assertEqual(self.preview(edited)[0], 200)
        status, body = self.call("GET", f"/api/inventario/terrenos/{t['id']}/vista-publica")
        self.assertEqual((status, body["revision_id"]), (200, edited["draft_revision_id"]))
        status, body = self.call("GET", f"/api/inventario/terrenos/{t['id']}/vista-publica?campos=contacto")
        self.assertEqual(status, 422)
        self.assertEqual(self.anon(f"/api/inventario/terrenos/{t['id']}/vista-publica")[0], 401)


class StalePublish(PublicationServer):
    """CON-02: Publish refers to the exact reviewed revision and version."""

    def test_a_stale_version_is_409_with_no_change(self):
        t = self.publishable()
        self.patch(t["id"], 1, {"asking_m2": 150}, "beto")
        status, body = self.act(t, "publicar")
        self.assertEqual((status, body["detalle"]["code"], body["detalle"]["current_version"]),
                         (409, "conflict", 2))
        reread = self.internal(t["id"])
        self.assertEqual((reread["version"], reread["publication_state"]), (2, "draft"))
        self.assertEqual(self.anon("/api/publico/terrenos")[1]["total"], 0)

    def test_a_reviewed_revision_that_is_no_longer_the_draft_is_409(self):
        t = self.publishable()
        edited = self.patch(t["id"], 1, {"asking_m2": 150}, "beto")[1]["terreno"]
        status, body = self.act(t, "publicar", version=edited["version"],
                                revision_id=t["draft_revision_id"])
        self.assertEqual((status, body["detalle"]["code"]), (409, "revision_changed"))
        self.assertEqual(self.internal(t["id"])["version"], 2)
        self.assertEqual(self.anon(f"/api/publico/terrenos/{t['id']}")[0], 404)

    def test_publish_racing_a_save_has_one_winner(self):
        t = self.publishable()
        results = {}
        barrier = threading.Barrier(2)

        def run(name, fn):
            barrier.wait()
            results[name] = fn()[0]

        threads = [threading.Thread(target=run, args=("publish", lambda: self.act(t, "publicar"))),
                   threading.Thread(target=run, args=("save", lambda: self.patch(
                       t["id"], 1, {"asking_m2": 1.5}, "beto")))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results.values()), [200, 409])
        reread = self.internal(t["id"])
        self.assertEqual(reread["version"], 2)
        public = self.anon(f"/api/publico/terrenos/{t['id']}")
        if results["publish"] == 200:
            self.assertEqual(public[1]["terreno"]["asking_m2"], 122.5)
        else:
            self.assertEqual(public[0], 404)

    def test_a_failure_mid_publish_rolls_everything_back(self):
        t = self.publishable()
        original = repo._event

        def failing(conn, *args, **kwargs):
            if args[2] == "publish":
                raise RuntimeError("SECRETO-TABLA inventory_event")
            return original(conn, *args, **kwargs)

        with patch.object(repo, "_event", failing):
            status, body = self.act(t, "publicar")
        self.assertEqual((status, body), (500, {
            "error": "Ocurrió un error inesperado. Inténtalo de nuevo; si se repite, avisa al equipo.",
            "detalle": {"code": "internal"}}))
        reread = self.internal(t["id"])
        self.assertEqual((reread["version"], reread["published_revision_id"]), (1, None))
        self.assertEqual(self.anon("/api/publico/terrenos")[1]["total"], 0)
        self.assertEqual(self.publish(t)["version"], 2)


class Lifecycle(PublicationServer):
    def test_sold_saves_privately_then_leaves_the_catalog_on_publish(self):
        t = self.publish(self.publishable())
        sold = self.patch(t["id"], 2, {"availability": "sold"})[1]["terreno"]
        self.assertTrue(sold["public_visible"])  # still the published available revision
        self.assertEqual(sold["pending_changes"]["availability"], {"published": "available", "draft": "sold"})
        self.assertEqual(self.anon(f"/api/publico/terrenos/{t['id']}")[0], 200)
        warnings = {w["code"] for w in self.preview(sold)[1]["warnings"]}
        self.assertIn("leaves_catalog", warnings)
        after = self.publish(sold)
        self.assertEqual((after["publication_state"], after["public_visible"]), ("published", False))
        self.assert_withdrawn(t["id"])
        # The history keeps it, and republishing as available brings it back.
        back = self.patch(t["id"], after["version"], {"availability": "available"})[1]["terreno"]
        self.publish(back)
        self.assertEqual(self.anon(f"/api/publico/terrenos/{t['id']}")[0], 200)

    def test_withdrawn_behaves_like_sold(self):
        t = self.publish(self.publishable())
        w = self.patch(t["id"], 2, {"availability": "withdrawn"})[1]["terreno"]
        self.publish(w)
        self.assert_withdrawn(t["id"])

    def test_unpublish_withdraws_now_and_keeps_the_draft(self):
        t = self.publish(self.publishable())
        status, body = self.act(t, "despublicar", "beto")
        self.assertEqual(status, 200)
        u = body["terreno"]
        self.assertEqual((u["version"], u["publication_state"], u["public_visible"],
                          u["published_revision_id"], u["published_at"]),
                         (3, "unpublished", False, None, None))
        self.assertEqual(u["draft"]["terreno"], COMPLETO["terreno"])
        self.assert_withdrawn(t["id"])
        status, body = self.act(u, "despublicar")
        self.assertEqual((status, body["detalle"]["code"]), (409, "invalid_state"))
        self.assertEqual(self.publish(u)["publication_state"], "published")

    def test_archive_withdraws_and_restore_never_republishes(self):
        t = self.publish(self.publishable())
        a = self.act(t, "archivar", "carla")[1]["terreno"]
        self.assertEqual((a["publication_state"], a["public_visible"], a["published_revision_id"]),
                         ("archived", False, None))
        self.assertIsNotNone(a["archived_at"])
        self.assert_withdrawn(t["id"])
        listing = self.call("GET", "/api/inventario/terrenos")[1]
        self.assertEqual(listing["total"], 0)
        self.assertEqual(self.call("GET", "/api/inventario/terrenos?include_archived=true")[1]["total"], 1)
        self.assertEqual(self.act(a, "publicar")[1]["detalle"]["code"], "invalid_state")
        self.assertEqual(self.act(a, "archivar")[1]["detalle"]["code"], "invalid_state")
        r = self.act(a, "restaurar", "beto")[1]["terreno"]
        self.assertEqual((r["publication_state"], r["archived_at"], r["public_visible"]),
                         ("unpublished", None, False))
        self.assert_withdrawn(t["id"])
        self.assertEqual(self.act(r, "restaurar")[1]["detalle"]["code"], "invalid_state")
        eventos = self.call("GET", f"/api/inventario/terrenos/{t['id']}/historial")[1]["eventos"]
        self.assertEqual([e["action"] for e in eventos], ["restore", "archive", "publish", "create"])
        self.assertEqual([e["actor"]["display_name"] for e in eventos[:2]], ["Beto", "Carla"])

    def test_a_never_published_draft_restores_as_a_draft(self):
        t = self.publishable()
        a = self.act(t, "archivar")[1]["terreno"]
        r = self.act(a, "restaurar")[1]["terreno"]
        self.assertEqual(r["publication_state"], "draft")

    def test_every_transition_is_version_checked(self):
        t = self.publish(self.publishable())  # version 2
        for action in ("despublicar", "archivar"):
            status, body = self.act(t, action, version=1)
            self.assertEqual((status, body["detalle"]["code"]), (409, "conflict"), action)
        a = self.act(t, "archivar")[1]["terreno"]  # version 3
        status, body = self.act(a, "restaurar", version=2)
        self.assertEqual((status, body["detalle"]["code"]), (409, "conflict"))
        self.assertEqual(self.internal(t["id"])["version"], 3)
        eventos = self.call("GET", f"/api/inventario/terrenos/{t['id']}/historial")[1]["total"]
        self.assertEqual(eventos, 3)

    def test_bodies_are_validated(self):
        t = self.publishable()
        base = f"/api/inventario/terrenos/{t['id']}"
        for action, body in (("publicar", {"expected_version": 1}),
                             ("publicar", {"expected_version": "1", "revision_id": t["draft_revision_id"]}),
                             ("despublicar", {"expected_version": 1, "revision_id": "x"}),
                             ("archivar", {}),
                             ("restaurar", {"expected_version": 1, "actor": "beto"})):
            status, answer = self.call("POST", f"{base}/{action}", body)
            self.assertEqual((status, answer["detalle"]["code"]), (422, "validation_failed"), (action, body))
        missing = f"/api/inventario/terrenos/{uuid.uuid4()}/archivar"
        self.assertEqual(self.call("POST", missing, {"expected_version": 1})[0], 404)

    def test_anonymous_lifecycle_calls_are_401(self):
        t = self.publishable()
        for action in ("publicar", "despublicar", "archivar", "restaurar"):
            status, body = self.call("POST", f"/api/inventario/terrenos/{t['id']}/{action}",
                                     {"expected_version": 1, "revision_id": t["draft_revision_id"]}, None)
            self.assertEqual((status, body["detalle"]["code"]), (401, "unauthenticated"))
        self.assertEqual(self.internal(t["id"])["version"], 1)

    def test_internal_list_filters_by_lifecycle_fields(self):
        visible = self.publish(self.publishable(terreno="Visible"))
        pending = self.publish(self.publishable(terreno="Pendiente"))
        self.patch(pending["id"], 2, {"asking_m2": 10})
        sold = self.publish(self.publishable(terreno="Vendido", availability="sold"))
        self.publishable(terreno="Borrador")

        def names(query):
            body = self.call("GET", f"/api/inventario/terrenos?{query}")[1]
            return sorted(t["draft"]["terreno"] for t in body["terrenos"])

        self.assertEqual(names("public_visible=true"), ["Pendiente", "Visible"])
        self.assertEqual(names("public_visible=false"), ["Borrador", "Vendido"])
        self.assertEqual(names("has_pending_changes=true"), ["Pendiente"])
        self.assertEqual(names("publication_state=published"), ["Pendiente", "Vendido", "Visible"])
        self.assertEqual(names("publication_state=draft"), ["Borrador"])
        self.assertEqual(sold["public_visible"], False)
        self.assertEqual(visible["public_visible"], True)
        self.assertEqual(self.call("GET", "/api/inventario/terrenos?public_visible=si")[0], 422)


class PublicCatalog(PublicationServer):
    def test_uniform_404_for_every_nonpublic_id(self):
        draft = self.publishable(terreno="Borrador")
        sold = self.publish(self.publishable(terreno="Vendido", availability="sold"))
        unpublished = self.act(self.publish(self.publishable(terreno="Retirado")), "despublicar")[1]["terreno"]
        archived = self.act(self.publish(self.publishable(terreno="Archivado")), "archivar")[1]["terreno"]
        for tid in (draft["id"], sold["id"], unpublished["id"], archived["id"], str(uuid.uuid4()),
                    "no-es-uuid", "1", draft["draft_revision_id"]):
            with self.subTest(tid=tid):
                self.assertEqual(self.anon(f"/api/publico/terrenos/{tid}"), (404, NOT_FOUND))
        self.assertEqual(self.anon("/api/publico/terrenos")[1]["total"], 0)

    def test_private_and_unknown_selectors_are_422(self):
        self.publish(self.publishable())
        for query in ("campos=contacto&include_private=1", "contacto=x", "publication_state=draft",
                      "include_archived=true", "availability=sold", "attention=true",
                      "notas_internas=x", "limit=251", "price_min=1", "moneda=EUR"):
            with self.subTest(query=query):
                status, body = self.anon(f"/api/publico/terrenos?{query}")
                self.assertEqual((status, body["detalle"]["code"]), (422, "validation_failed"))
                # Only the caller's own rejected key is echoed, never data.
                self.assertFalse(any(s in json.dumps(body) for s in SENTINELS))
        self.assertEqual(self.anon(f"/api/publico/terrenos/{uuid.uuid4()}?x=1")[0], 422)

    def test_filters_facets_and_mixed_currency_on_published_fields(self):
        specs = [("A", "Jalisco", "Zapopan", "USD", 100.0, 1000), ("B", "Jalisco", "Tlaquepaque", "MXN", 2000.0, 5000),
                 ("C", "Colima", "Manzanillo", "USD", 300.0, 20000), ("D", "Colima", "Colima", None, None, 8000)]
        for name, estado, municipio, moneda, m2, area in specs:
            extra = ({"asking_m2": m2, "asking_price": m2 * area, "moneda": moneda} if moneda
                     else {"asking_m2": None, "asking_price": None, "moneda": None, "price_on_request": True})
            self.publish(self.publishable(terreno=f"Lote {name}", estado=estado, municipio=municipio,
                                          superficie_m2=area, superficie_ha=area / 10000, **extra))

        def names(query):
            status, body = self.anon(f"/api/publico/terrenos?{query}")
            self.assertEqual(status, 200, body)
            return sorted(t["terreno"][-1] for t in body["terrenos"]), body

        self.assertEqual(names("estado=Jalisco&estado=Colima&municipio=Zapopan&municipio=Colima")[0], ["A", "D"])
        self.assertEqual(names("moneda=USD&price_basis=per_m2&price_min=50&price_max=200")[0], ["A"])
        self.assertEqual(names("moneda=USD")[0], ["A", "C"])
        self.assertEqual(names("area_min_m2=5000&area_max_m2=10000")[0], ["B", "D"])
        self.assertEqual(names("q=MANZANILLO")[0], ["C"])
        _, body = names("estado=Colima")
        self.assertEqual(body["facets"]["estados"], ["Colima", "Jalisco"])
        self.assertEqual(body["facets"]["municipios"], ["Colima", "Manzanillo"])
        self.assertEqual(body["facets"]["monedas"], ["MXN", "USD"])

    def test_251_published_records_page_without_gaps_or_duplicates(self):
        for n in range(251):
            t = self.publishable(terreno=f"Lote {n:03d}")
            self.publish(t)
        self.publishable(terreno="Sin publicar")
        seen, cursor, pages = [], None, 0
        while True:
            body = self.anon("/api/publico/terrenos?limit=100" + (f"&cursor={cursor}" if cursor else ""))[1]
            pages += 1
            self.assertEqual(body["total"], 251)
            seen += [t["id"] for t in body["terrenos"]]
            cursor = body["next_cursor"]
            if not cursor:
                break
        self.assertEqual((pages, len(seen), len(set(seen))), (3, 251, 251))
        self.assertEqual(seen, sorted(seen))
        default = self.anon("/api/publico/terrenos")[1]
        self.assertEqual(len(default["terrenos"]), 100)

    def test_responses_are_not_cached(self):
        import urllib.request
        t = self.publish(self.publishable())
        for path in ("/api/publico/terrenos", f"/api/publico/terrenos/{t['id']}"):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}") as r:
                self.assertEqual(r.headers["Cache-Control"], "no-store")


class CarryForwards(PublicationServer):
    def test_unexpected_errors_are_generic(self):
        with patch.object(repo, "all_records", side_effect=RuntimeError("SECRETO /ruta/tabla")):
            status, body = self.call("GET", "/api/inventario/terrenos")
        self.assertEqual(status, 500)
        self.assertEqual(body["detalle"], {"code": "internal"})
        self.assertNotIn("SECRETO", json.dumps(body))
        with patch.object(repo, "public_records", side_effect=RuntimeError("SECRETO")):
            status, body = self.anon("/api/publico/terrenos")
        self.assertEqual((status, body["detalle"]), (500, {"code": "internal"}))
        self.assertNotIn("SECRETO", json.dumps(body))

    def test_config_read_only_reflects_only_the_setting(self):
        self.assertFalse(self.anon("/api/config")[1]["readOnly"])
        self.assertFalse(self.call("GET", "/api/config")[1]["readOnly"])
        with patch.dict(os.environ, {"ARA_MAP_READ_ONLY": "1"}):
            self.assertTrue(self.anon("/api/config")[1]["readOnly"])


class LoginThrottle(TempDatabase):
    """O-7: keyed by login and client, shared through the database."""

    def setUp(self):
        super().setUp()
        create_user(self.conn, "ana", "Ana")
        create_user(self.conn, "beto", "Beto")

    def attempt(self, login, password, client):
        token, _, throttled = auth.login(self.conn, login, password, client=client)
        return "throttled" if throttled else ("ok" if token else "bad")

    def test_a_stranger_cannot_lock_out_a_known_account(self):
        for _ in range(auth.MAX_FAILURES):
            self.assertEqual(self.attempt("ana", "mal", "203.0.113.9"), "bad")
        self.assertEqual(self.attempt("ana", TEST_PASSWORD, "203.0.113.9"), "throttled")
        self.assertEqual(self.attempt("ana", TEST_PASSWORD, "198.51.100.4"), "ok")
        self.assertEqual(self.attempt("beto", TEST_PASSWORD, "203.0.113.9"), "ok")
        stored = {r[0] for r in self.conn.execute("SELECT client FROM team_login_failure")}
        self.assertNotIn("203.0.113.9", stored)  # hashed, not the raw address

    def test_a_client_spraying_many_logins_is_paused(self):
        for n in range(auth.MAX_CLIENT_FAILURES):
            self.assertEqual(self.attempt(f"usuario{n}", "mal", "203.0.113.7"), "bad")
        self.assertEqual(self.attempt("ana", TEST_PASSWORD, "203.0.113.7"), "throttled")
        self.assertEqual(self.attempt("ana", TEST_PASSWORD, "203.0.113.8"), "ok")

    def test_success_clears_only_that_pair(self):
        for _ in range(3):
            self.attempt("ana", "mal", "203.0.113.1")
            self.attempt("ana", "mal", "203.0.113.2")
        self.assertEqual(self.attempt("ana", TEST_PASSWORD, "203.0.113.1"), "ok")
        for _ in range(2):
            self.attempt("ana", "mal", "203.0.113.2")
        self.assertEqual(self.attempt("ana", TEST_PASSWORD, "203.0.113.2"), "throttled")

    def test_a_v8_file_without_the_client_column_gains_it(self):
        from server import db
        self.conn.execute("DROP INDEX IF EXISTS idx_team_login_failure_client")
        self.conn.execute("ALTER TABLE team_login_failure DROP COLUMN client")
        self.conn.close()
        self.conn = db.connect()
        self.assertEqual(self.attempt("ana", "mal", "203.0.113.1"), "bad")
        self.assertEqual(self.attempt("ana", TEST_PASSWORD, "203.0.113.1"), "ok")


class CloudClientIdentity(TempDatabase):
    def test_the_cloud_adapter_keys_on_the_vercel_forwarded_address(self):
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("cloud_adapter_id", Path(__file__).parents[1] / "api" / "index.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = module.handler.__new__(module.handler)
        handler.client_address = ("10.0.0.1", 1234)
        for header, expected in (("203.0.113.5, 10.1.1.1", "203.0.113.5"), ("no-es-ip", "10.0.0.1"),
                                 ("", "10.0.0.1"), ("2001:db8::1", "2001:db8::1")):
            handler.headers = {"X-Forwarded-For": header}
            self.assertEqual(handler._client_id(), expected)

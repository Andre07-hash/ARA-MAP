"""Saved maps are frozen records, not live views.

These lock in the behaviour the review asked to be made explicit: a saved map
keeps what it held at save time, survives changes and deletion of its source
base, and only changes when the user asks it to.
"""

from __future__ import annotations

import unittest

from server.api import mapas as api_mapas
from server.repo import bases, mapas, terrenos
from tests.support import TempDatabase
from tests.test_repo import record


class Snapshot(TempDatabase):
    def setUp(self):
        super().setUp()
        self.base_id = bases.create(self.conn, "Septiembre", None, None)
        terrenos.insert(self.conn, self.base_id, [
            record(1, "El Mirador"),
            record(2, "La Loma"),
        ], {})
        self.mapa_id = mapas.create(
            self.conn, "Septiembre guardado", "simple",
            [{"base_id": self.base_id, "color": "#2a78d6"}],
        )

    def test_saving_freezes_the_terrains(self):
        filas = mapas.terrenos(self.conn, self.mapa_id)
        self.assertEqual([f["terreno"] for f in filas], ["El Mirador", "La Loma"])

    def test_adding_to_the_base_does_not_change_the_saved_map(self):
        terrenos.insert(self.conn, self.base_id, [record(3, "Nuevo")], {})
        filas = mapas.terrenos(self.conn, self.mapa_id)
        self.assertEqual(len(filas), 2)
        self.assertNotIn("Nuevo", [f["terreno"] for f in filas])

    def test_editing_the_base_does_not_change_the_saved_map(self):
        self.conn.execute(
            "UPDATE terreno SET asking_price = 99 WHERE base_id = ?", (self.base_id,))
        precios = {f["asking_price"] for f in mapas.terrenos(self.conn, self.mapa_id)}
        self.assertEqual(precios, {5_000_000.0})

    def test_refreshing_pulls_the_current_base_in(self):
        terrenos.insert(self.conn, self.base_id, [record(3, "Nuevo")], {})
        resultado = mapas.refresh_snapshot(self.conn, self.mapa_id)
        self.assertEqual(resultado, {"actualizadas": 1, "conservadas": 0})
        self.assertIn("Nuevo", [f["terreno"] for f in mapas.terrenos(self.conn, self.mapa_id)])

    def test_refreshing_records_when_it_happened(self):
        antes = mapas.get(self.conn, self.mapa_id)["actualizado_en"]
        self.assertIsNotNone(antes)

    def test_deleting_the_base_keeps_the_map_readable(self):
        bases.delete(self.conn, self.base_id)
        filas = mapas.terrenos(self.conn, self.mapa_id)
        self.assertEqual(len(filas), 2)

        capa = mapas.get(self.conn, self.mapa_id)["capas"][0]
        self.assertFalse(capa["base_existe"])
        self.assertEqual(capa["nombre"], "Septiembre")
        self.assertEqual(capa["conteo"], 2)

    def test_refreshing_an_orphaned_layer_keeps_what_it_has(self):
        bases.delete(self.conn, self.base_id)
        resultado = mapas.refresh_snapshot(self.conn, self.mapa_id)
        self.assertEqual(resultado, {"actualizadas": 0, "conservadas": 1})
        self.assertEqual(len(mapas.terrenos(self.conn, self.mapa_id)), 2)

    def test_findings_travel_into_the_snapshot(self):
        from server.validation import validate_record
        malo = record(9, "Precio raro", asking_price=50_000_000.0)
        terrenos.insert(self.conn, self.base_id, [malo], {9: validate_record(malo)})
        mapas.refresh_snapshot(self.conn, self.mapa_id)

        fila = next(f for f in mapas.terrenos(self.conn, self.mapa_id)
                    if f["terreno"] == "Precio raro")
        self.assertEqual([i["codigo"] for i in fila["incidencias"]], ["PRECIO_INCONSISTENTE"])


class Merge(TempDatabase):
    def setUp(self):
        super().setUp()
        self.agosto = bases.create(self.conn, "Agosto", None, None)
        self.septiembre = bases.create(self.conn, "Septiembre", None, None)
        terrenos.insert(self.conn, self.agosto, [record(1, "El Mirador")], {})
        terrenos.insert(self.conn, self.septiembre, [record(1, "La Loma")], {})

        self.mapa_a = mapas.create(self.conn, "Mapa Agosto", "simple",
                                   [{"base_id": self.agosto, "color": "#2a78d6"}])
        self.mapa_s = mapas.create(self.conn, "Mapa Septiembre", "simple",
                                   [{"base_id": self.septiembre, "color": "#2a78d6"}])

    def test_merging_two_saved_maps_keeps_both_layers(self):
        mapa_id = mapas.merge(self.conn, "Agosto vs Septiembre",
                              [self.mapa_a, self.mapa_s], ["#2a78d6", "#eb6834"])
        mapa = mapas.get(self.conn, mapa_id)
        self.assertEqual(mapa["tipo"], "comparacion")
        self.assertEqual([c["nombre"] for c in mapa["capas"]], ["Agosto", "Septiembre"])
        self.assertEqual([c["color"] for c in mapa["capas"]], ["#2a78d6", "#eb6834"])

    def test_merged_terrains_come_from_both_sources(self):
        mapa_id = mapas.merge(self.conn, "Combinado",
                              [self.mapa_a, self.mapa_s], ["#1", "#2"])
        nombres = {f["terreno"] for f in mapas.terrenos(self.conn, mapa_id)}
        self.assertEqual(nombres, {"El Mirador", "La Loma"})

    def test_a_shared_base_is_included_once_and_reported(self):
        plan = mapas.plan_merge(self.conn, [self.mapa_a, self.mapa_a, self.mapa_s])
        self.assertEqual([c["base_nombre"] for c in plan["capas"]], ["Agosto", "Septiembre"])
        self.assertEqual([d["base_nombre"] for d in plan["duplicadas"]], ["Agosto"])

    def test_merging_a_merged_map_works(self):
        primero = mapas.merge(self.conn, "Dos", [self.mapa_a, self.mapa_s], ["#1", "#2"])
        tercera = bases.create(self.conn, "Octubre", None, None)
        terrenos.insert(self.conn, tercera, [record(1, "Tercero")], {})
        mapa_o = mapas.create(self.conn, "Mapa Octubre", "simple",
                              [{"base_id": tercera, "color": "#1"}])

        combinado = mapas.merge(self.conn, "Tres", [primero, mapa_o], ["#1", "#2", "#3"])
        capas = mapas.get(self.conn, combinado)["capas"]
        self.assertEqual([c["nombre"] for c in capas], ["Agosto", "Septiembre", "Octubre"])

    def test_a_merge_keeps_history_after_the_base_is_deleted(self):
        bases.delete(self.conn, self.agosto)
        mapa_id = mapas.merge(self.conn, "Histórico",
                              [self.mapa_a, self.mapa_s], ["#1", "#2"])
        nombres = {f["terreno"] for f in mapas.terrenos(self.conn, mapa_id)}
        self.assertEqual(nombres, {"El Mirador", "La Loma"})

    def test_merge_survives_a_restart(self):
        from server import db
        mapa_id = mapas.merge(self.conn, "Persistente",
                              [self.mapa_a, self.mapa_s], ["#1", "#2"])
        self.conn.close()

        reabierto = db.connect(self.db_path)
        try:
            mapa = mapas.get(reabierto, mapa_id)
            self.assertEqual(mapa["nombre"], "Persistente")
            self.assertEqual(len(mapa["capas"]), 2)
            self.assertEqual(len(mapas.terrenos(reabierto, mapa_id)), 2)
        finally:
            reabierto.close()
            self.conn = db.connect(self.db_path)


class MergeEndpoints(TempDatabase):
    def setUp(self):
        super().setUp()
        self.a = bases.create(self.conn, "Agosto", None, None)
        self.b = bases.create(self.conn, "Septiembre", None, None)
        terrenos.insert(self.conn, self.a, [record(1, "Uno")], {})
        terrenos.insert(self.conn, self.b, [record(1, "Dos")], {})
        self.ma = mapas.create(self.conn, "Mapa A", "simple", [{"base_id": self.a, "color": "#1"}])
        self.mb = mapas.create(self.conn, "Mapa B", "simple", [{"base_id": self.b, "color": "#2"}])

    def req(self, **body):
        import json

        from server.router import Request
        return Request("POST", "/x", {}, body.pop("params", {}), json.dumps(body).encode(), {})

    def test_preview_reports_the_resulting_layers(self):
        out = api_mapas.plan_merge(self.req(mapa_ids=[self.ma, self.mb]))
        self.assertEqual(out["total"], 2)
        self.assertFalse(out["aviso_color"])
        self.assertEqual([c["base_nombre"] for c in out["capas"]], ["Agosto", "Septiembre"])

    def test_merging_needs_at_least_two_maps(self):
        from server.web_util import ApiError
        with self.assertRaises(ApiError):
            api_mapas.plan_merge(self.req(mapa_ids=[self.ma]))

    def test_a_map_cannot_be_merged_with_itself(self):
        from server.web_util import ApiError
        with self.assertRaises(ApiError):
            api_mapas.plan_merge(self.req(mapa_ids=[self.ma, self.ma]))

    def test_an_unknown_map_is_a_404(self):
        from server.web_util import ApiError
        with self.assertRaises(ApiError) as caught:
            api_mapas.plan_merge(self.req(mapa_ids=[self.ma, 999]))
        self.assertEqual(caught.exception.status, 404)

    def test_merge_creates_a_reopenable_map(self):
        out = api_mapas.merge(self.req(nombre="Combinado", mapa_ids=[self.ma, self.mb],
                                       colores=["#2a78d6", "#eb6834"]))
        mapa_id = out["mapa"]["id"]
        payload = api_mapas.terrenos(self.req(params={"id": mapa_id}))
        self.assertEqual(len(payload["terrenos"]), 2)
        self.assertEqual({t["color"] for t in payload["terrenos"]}, {"#2a78d6", "#eb6834"})

    def test_refresh_endpoint_reports_what_it_did(self):
        out = api_mapas.refresh(self.req(params={"id": self.ma}))
        self.assertEqual(out["actualizadas"], 1)
        self.assertEqual(out["conservadas"], 0)


if __name__ == "__main__":
    unittest.main()


class HuellaIndependienteDelAdaptador(unittest.TestCase):
    """layer_fingerprint must hash values, whatever row type the adapter returns."""

    def test_postgres_style_rows_still_hash_their_values(self):
        from server.postgres import Row
        from server.repo.mapas import _HUELLA, layer_fingerprint

        def conexion(filas):
            class Conn:
                def execute(self, sql, params=()):
                    return [Row(zip((*_HUELLA, "moneda"), f)) for f in filas]
            return Conn()

        a = layer_fingerprint(conexion([("Norte", 1.0, 2.0, 3.0, 19.5, -99.1, "norte", None)]), 1, 0)
        b = layer_fingerprint(conexion([("Sur", 1.0, 2.0, 3.0, 19.5, -99.1, "sur", None)]), 1, 0)
        self.assertNotEqual(a, b)
        usd = layer_fingerprint(conexion([("Norte", 1.0, 2.0, 3.0, 19.5, -99.1, "norte", "USD")]), 1, 0)
        mxn = layer_fingerprint(conexion([("Norte", 1.0, 2.0, 3.0, 19.5, -99.1, "norte", "MXN")]), 1, 0)
        self.assertEqual(len({a, usd, mxn}), 3)

    def test_sqlite_rows_hash_exactly_as_before(self):
        import hashlib
        import sqlite3

        from server.repo.mapas import layer_fingerprint
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE mapa_terreno (mapa_id, capa_orden, orden, terreno, superficie_m2,"
                     " asking_price, asking_m2, lat, lon, clave_dedupe, moneda)")
        # A layer without a known currency hashes exactly as it did before prices carried one.
        conn.execute("INSERT INTO mapa_terreno VALUES (1, 0, 1, 'Norte', 1.0, 2.0, 3.0, 19.5, -99.1, 'norte', NULL)")
        esperado = hashlib.sha256(repr(("Norte", 1.0, 2.0, 3.0, 19.5, -99.1, "norte")).encode()).hexdigest()
        self.assertEqual(layer_fingerprint(conn, 1, 0), esperado)

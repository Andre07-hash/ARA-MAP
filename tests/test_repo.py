"""Repository tests: storage round-trips and cascade behaviour."""

from __future__ import annotations

import unittest

from server.importer import TerrainRecord
from server.repo import bases, mapas, terrenos
from server.validation import validate_record
from tests.support import TempDatabase


def record(orden=1, terreno="El Mirador", **kw):
    base = dict(orden=orden, fila=orden + 1, terreno=terreno, estado="Jalisco",
                municipio="Zapopan", superficie_m2=10_000.0, superficie_ha=1.0,
                asking_price=5_000_000.0, asking_m2=500.0, lat=20.7, lon=-103.4)
    return TerrainRecord(**{**base, **kw})


class Bases(TempDatabase):
    def test_a_new_base_starts_empty(self):
        base_id = bases.create(self.conn, "Septiembre", "s.xlsx", "Hoja")
        stored = bases.get(self.conn, base_id)
        self.assertEqual(stored["nombre"], "Septiembre")
        self.assertEqual(stored["conteo"], 0)
        self.assertEqual(stored["ubicados"], 0)
        self.assertEqual(stored["sin_ubicacion"], 0)

    def test_counts_reflect_what_was_stored(self):
        base_id, result = self.load_fixture()
        stored = bases.get(self.conn, base_id)
        self.assertEqual(stored["conteo"], 79)
        self.assertEqual(stored["ubicados"], 39)
        self.assertEqual(stored["sin_ubicacion"], 40)

    def test_listing_is_newest_first(self):
        bases.create(self.conn, "Primera", None, None)
        bases.create(self.conn, "Segunda", None, None)
        self.assertEqual([b["nombre"] for b in bases.listing(self.conn)],
                         ["Segunda", "Primera"])

    def test_unknown_base_is_none(self):
        self.assertIsNone(bases.get(self.conn, 999))

    def test_rename(self):
        base_id = bases.create(self.conn, "Viejo", None, None)
        bases.rename(self.conn, base_id, "Nuevo")
        self.assertEqual(bases.get(self.conn, base_id)["nombre"], "Nuevo")

    def test_unique_name_suffixes_instead_of_colliding(self):
        bases.create(self.conn, "Base", None, None)
        self.assertEqual(bases.unique_name(self.conn, "Base"), "Base (2)")
        bases.create(self.conn, "Base (2)", None, None)
        self.assertEqual(bases.unique_name(self.conn, "Base"), "Base (3)")

    def test_unique_name_leaves_a_free_name_alone(self):
        self.assertEqual(bases.unique_name(self.conn, "Libre"), "Libre")

    def test_deleting_a_base_removes_its_terrains(self):
        base_id, _ = self.load_fixture()
        bases.delete(self.conn, base_id)
        self.assertEqual(terrenos.for_base(self.conn, base_id), [])
        self.assertIsNone(bases.get(self.conn, base_id))


class Terrenos(TempDatabase):
    def test_insert_returns_one_id_per_record(self):
        base_id = bases.create(self.conn, "B", None, None)
        ids = terrenos.insert(self.conn, base_id, [record(1), record(2, "Otro")], {})
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)

    def test_orden_continues_across_appends(self):
        base_id = bases.create(self.conn, "B", None, None)
        terrenos.insert(self.conn, base_id, [record(1)], {})
        self.assertEqual(terrenos.next_orden(self.conn, base_id), 2)
        terrenos.insert(self.conn, base_id, [record(1, "Segundo")], {})
        self.assertEqual([t["orden"] for t in terrenos.for_base(self.conn, base_id)], [1, 2])

    def test_findings_are_stored_and_returned(self):
        base_id = bases.create(self.conn, "B", None, None)
        bad = record(1, asking_price=50_000_000.0)
        terrenos.insert(self.conn, base_id, [bad], {1: validate_record(bad)})
        stored = terrenos.for_base(self.conn, base_id)[0]
        self.assertEqual([i["codigo"] for i in stored["incidencias"]], ["PRECIO_INCONSISTENTE"])

    def test_ubicado_is_derived_on_read(self):
        base_id = bases.create(self.conn, "B", None, None)
        terrenos.insert(self.conn, base_id, [record(1), record(2, "Sin", lat=None, lon=None)], {})
        stored = terrenos.for_base(self.conn, base_id)
        self.assertEqual([t["ubicado"] for t in stored], [True, False])

    def test_unmapped_columns_survive_the_round_trip(self):
        base_id = bases.create(self.conn, "B", None, None)
        terrenos.insert(self.conn, base_id, [record(1, extra={"Vendedor": "Ana"})], {})
        self.assertEqual(terrenos.for_base(self.conn, base_id)[0]["extra"], {"Vendedor": "Ana"})

    def test_update_replaces_values_and_findings(self):
        base_id = bases.create(self.conn, "B", None, None)
        [terreno_id] = terrenos.insert(self.conn, base_id, [record(1)], {})
        revised = record(1, asking_price=7_000_000.0, asking_m2=700.0)
        terrenos.update_from_record(self.conn, terreno_id, revised, ())
        stored = terrenos.for_base(self.conn, base_id)[0]
        self.assertEqual(stored["asking_price"], 7_000_000.0)
        self.assertEqual(stored["incidencias"], [])

    def test_for_bases_spans_several_bases(self):
        a = bases.create(self.conn, "A", None, None)
        b = bases.create(self.conn, "B", None, None)
        terrenos.insert(self.conn, a, [record(1)], {})
        terrenos.insert(self.conn, b, [record(1, "Otro")], {})
        self.assertEqual(len(terrenos.for_bases(self.conn, [a, b])), 2)
        self.assertEqual(terrenos.for_bases(self.conn, []), [])

    def test_dedupe_rows_carry_every_field_an_append_can_change(self):
        """Comparing content requires the content, not just id and price."""
        base_id = bases.create(self.conn, "B", None, None)
        terrenos.insert(self.conn, base_id, [record(1)], {})
        row = terrenos.dedupe_rows(self.conn, base_id)[0]
        self.assertEqual(
            set(row),
            {"id", "clave_dedupe", *terrenos.CAMPOS_COMPARABLES},
        )
        for campo in ("lat", "lon", "direccion", "asking_m2"):
            self.assertIn(campo, row)


class Mapas(TempDatabase):
    def setUp(self):
        super().setUp()
        self.a = bases.create(self.conn, "Agosto", None, None)
        self.b = bases.create(self.conn, "Septiembre", None, None)

    def test_a_saved_map_keeps_its_layers_in_order(self):
        mapa_id = mapas.create(self.conn, "Comparación", "comparacion",
                               [{"base_id": self.a, "color": "#2a78d6"},
                                {"base_id": self.b, "color": "#eb6834"}])
        stored = mapas.get(self.conn, mapa_id)
        self.assertEqual([c["nombre"] for c in stored["capas"]], ["Agosto", "Septiembre"])
        self.assertEqual([c["color"] for c in stored["capas"]], ["#2a78d6", "#eb6834"])

    def test_config_round_trips_as_json(self):
        mapa_id = mapas.create(self.conn, "M", "simple",
                               [{"base_id": self.a, "color": "#2a78d6"}],
                               {"basemap": "satelite"})
        self.assertEqual(mapas.get(self.conn, mapa_id)["config"], {"basemap": "satelite"})

    def test_update_replaces_layers_wholesale(self):
        mapa_id = mapas.create(self.conn, "M", "comparacion",
                               [{"base_id": self.a, "color": "#1"},
                                {"base_id": self.b, "color": "#2"}])
        mapas.update(self.conn, mapa_id, capas=[{"base_id": self.b, "color": "#3"}])
        capas = mapas.get(self.conn, mapa_id)["capas"]
        self.assertEqual([c["base_id"] for c in capas], [self.b])

    def test_update_renames_without_touching_layers(self):
        mapa_id = mapas.create(self.conn, "Antes", "simple",
                               [{"base_id": self.a, "color": "#1"}])
        mapas.update(self.conn, mapa_id, nombre="Después")
        stored = mapas.get(self.conn, mapa_id)
        self.assertEqual(stored["nombre"], "Después")
        self.assertEqual(len(stored["capas"]), 1)

    def test_deleting_a_base_leaves_the_saved_map_intact(self):
        """A saved map is frozen, so losing its source must not empty it."""
        mapa_id = mapas.create(self.conn, "M", "comparacion",
                               [{"base_id": self.a, "color": "#1"},
                                {"base_id": self.b, "color": "#2"}])
        bases.delete(self.conn, self.a)

        capas = mapas.get(self.conn, mapa_id)["capas"]
        self.assertEqual(len(capas), 2)
        # The layer keeps its name and terrains. Its source id is cleared so a
        # later import cannot inherit it and be mistaken for the original.
        huerfana = next(c for c in capas if c["nombre"] == "Agosto")
        self.assertIsNone(huerfana["base_id"])
        self.assertFalse(huerfana["base_existe"])

    def test_deleting_a_map_leaves_the_bases_alone(self):
        mapa_id = mapas.create(self.conn, "M", "simple", [{"base_id": self.a, "color": "#1"}])
        mapas.delete(self.conn, mapa_id)
        self.assertIsNone(mapas.get(self.conn, mapa_id))
        self.assertIsNotNone(bases.get(self.conn, self.a))

    def test_unknown_map_is_none(self):
        self.assertIsNone(mapas.get(self.conn, 999))


if __name__ == "__main__":
    unittest.main()

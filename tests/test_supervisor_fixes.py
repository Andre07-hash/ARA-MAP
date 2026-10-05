"""Regressions for the defects found in the supervisor review of 21 Sep 2026.

Each test reproduces the reported failure exactly as written, so a return of
any of them fails the build rather than the next review.
"""

from __future__ import annotations

import unittest

from server import db
from server.importer import (
    RejectedRow,
    TerrainRecord,
    _build_record,
    map_headers,
    read_workbook,
)
from server.matching import Disposition, classify
from server.repo import bases, mapas, terrenos
from server.validation import (
    UBICACION_INVALIDA,
    UBICACION_SIN_DATO,
    UBICACION_VALIDA,
    location_state,
    sql_ubicacion_valida,
    validate_record,
)
from tests.support import FIXTURE, TempDatabase


def rec(orden=1, nombre="El Mirador", **kw) -> TerrainRecord:
    base = dict(
        orden=orden, fila=orden + 1, terreno=nombre, estado="Jalisco",
        municipio="Zapopan", superficie_m2=10_000.0, superficie_ha=1.0,
        asking_price=5_000_000.0, asking_m2=500.0, lat=20.7, lon=-103.4,
    )
    return TerrainRecord(**{**base, **kw})


class SourceIdentityIsNotReused(TempDatabase):
    """#1 P1 - a saved map reconnected to an unrelated source."""

    def test_a_deleted_base_id_is_never_handed_out_again(self):
        bases.create(self.conn, "A", None, None)
        segunda = bases.create(self.conn, "B", None, None)
        bases.delete(self.conn, segunda)
        tercera = bases.create(self.conn, "C", None, None)
        self.assertNotEqual(tercera, segunda)

    def test_deleting_a_base_disconnects_it_from_saved_layers(self):
        base_id = bases.create(self.conn, "Fuente B", None, None)
        terrenos.insert(self.conn, base_id, [rec(1, "Uno")], {})
        mapa_id = mapas.create(
            self.conn, "Mapa de B", "simple", [{"base_id": base_id, "color": "#1"}])

        bases.delete(self.conn, base_id)
        capa = mapas.get(self.conn, mapa_id)["capas"][0]
        self.assertIsNone(capa["base_id"])
        self.assertFalse(capa["base_existe"])
        self.assertEqual(capa["nombre"], "Fuente B")

    def test_the_exact_reported_reproduction(self):
        """Delete the source, import an unrelated workbook, then refresh."""
        bases.create(self.conn, "Relleno", None, None)
        vieja = bases.create(self.conn, "Fuente vieja", None, None)
        terrenos.insert(self.conn, vieja, [rec(1, "Uno")], {})
        mapa_id = mapas.create(
            self.conn, "Mapa", "simple", [{"base_id": vieja, "color": "#1"}])

        bases.delete(self.conn, vieja)
        ajena = bases.create(self.conn, "Sin relación", None, None)
        terrenos.insert(
            self.conn, ajena, [rec(i, f"Ajeno {i}") for i in range(1, 80)], {})

        antes = mapas.get(self.conn, mapa_id)["conteo"]
        resultado = mapas.refresh_snapshot(self.conn, mapa_id)
        despues = mapas.get(self.conn, mapa_id)["conteo"]

        self.assertEqual(antes, 1)
        self.assertEqual(despues, 1, "the map absorbed an unrelated source")
        self.assertEqual(resultado, {"actualizadas": 0, "conservadas": 1})
        self.assertEqual(
            [t["terreno"] for t in mapas.terrenos(self.conn, mapa_id)], ["Uno"])


class AppendComparesContent(TempDatabase):
    """#2 P1 - coordinate corrections discarded as duplicates."""

    def setUp(self):
        super().setUp()
        self.base_id = bases.create(self.conn, "Base", None, None)

    def classify_one(self, stored, incoming):
        terrenos.insert(self.conn, self.base_id, [stored], {})
        return classify([incoming], terrenos.dedupe_rows(self.conn, self.base_id))[0]

    def test_adding_missing_coordinates_is_a_change_not_a_duplicate(self):
        decision = self.classify_one(
            rec(lat=None, lon=None), rec(lat=20.7, lon=-103.4))
        self.assertEqual(decision.disposition, Disposition.CONFLICTO)
        self.assertEqual(
            {d.campo for d in decision.diferencias}, {"lat", "lon"})

    def test_the_old_and_new_values_are_both_reported(self):
        decision = self.classify_one(
            rec(lat=None, lon=None), rec(lat=20.7, lon=-103.4))
        lat = next(d for d in decision.diferencias if d.campo == "lat")
        self.assertIsNone(lat.anterior)
        self.assertEqual(lat.nuevo, 20.7)

    def test_every_editable_field_is_compared(self):
        for campo, viejo, nuevo in (
            ("direccion", "Calle 1", "Calle 2"),
            ("asking_m2", 500.0, 650.0),
            ("afectaciones_pct", None, 0.4),
            ("afectaciones_m2", 0.0, 1200.0),
            ("lat", 20.7, 21.9),
        ):
            with self.subTest(campo=campo):
                self.conn.execute("DELETE FROM terreno WHERE base_id = ?", (self.base_id,))
                decision = self.classify_one(
                    rec(**{campo: viejo}), rec(**{campo: nuevo}))
                self.assertEqual(decision.disposition, Disposition.CONFLICTO)
                self.assertIn(campo, {d.campo for d in decision.diferencias})

    def test_an_identical_row_is_still_a_duplicate(self):
        decision = self.classify_one(rec(), rec())
        self.assertEqual(decision.disposition, Disposition.DUPLICADA)
        self.assertEqual(decision.diferencias, ())

    def test_the_real_workbook_appended_to_itself_reports_no_changes(self):
        resultado = read_workbook(FIXTURE)
        base_id = bases.create(self.conn, "Real", None, None)
        terrenos.insert(self.conn, base_id, resultado.records, {})

        decisiones = classify(resultado.records, terrenos.dedupe_rows(self.conn, base_id))
        conflictos = [d for d in decisiones if d.disposition is Disposition.CONFLICTO]
        self.assertEqual(conflictos, [], "identical data reported as changed")

    def test_an_update_actually_stores_the_new_coordinates(self):
        stored = rec(lat=None, lon=None)
        terrenos.insert(self.conn, self.base_id, [stored], {})
        [fila] = terrenos.for_base(self.conn, self.base_id)

        terrenos.update_from_record(
            self.conn, fila["id"], rec(lat=20.7, lon=-103.4), ())
        actualizado = terrenos.for_base(self.conn, self.base_id)[0]
        self.assertEqual(actualizado["lat"], 20.7)
        self.assertTrue(actualizado["ubicado"])


class MergeKeepsDistinctVersions(TempDatabase):
    """#4 P1 - merging different snapshots of one source dropped a version."""

    def setUp(self):
        super().setUp()
        self.base_id = bases.create(self.conn, "Fuente", None, None)
        terrenos.insert(self.conn, self.base_id, [rec(1, "Uno")], {})
        self.mapa_a = mapas.create(
            self.conn, "Mapa A", "simple", [{"base_id": self.base_id, "color": "#1"}])
        terrenos.insert(self.conn, self.base_id, [rec(2, "Dos")], {})
        self.mapa_b = mapas.create(
            self.conn, "Mapa B", "simple", [{"base_id": self.base_id, "color": "#1"}])

    def test_two_versions_of_one_source_both_survive(self):
        plan = mapas.plan_merge(self.conn, [self.mapa_a, self.mapa_b])
        self.assertEqual(len(plan["capas"]), 2)
        self.assertEqual(plan["duplicadas"], [])

    def test_the_versions_are_labelled_so_they_can_be_told_apart(self):
        plan = mapas.plan_merge(self.conn, [self.mapa_a, self.mapa_b])
        etiquetas = [c["etiqueta"] for c in plan["capas"]]
        self.assertEqual(etiquetas, ["Fuente · Mapa A", "Fuente · Mapa B"])
        self.assertTrue(all(c["es_version"] for c in plan["capas"]))

    def test_the_merged_map_holds_both_versions(self):
        mapa_id = mapas.merge(
            self.conn, "Historia", [self.mapa_a, self.mapa_b], ["#1", "#2"])
        mapa = mapas.get(self.conn, mapa_id)
        self.assertEqual(len(mapa["capas"]), 2)
        self.assertEqual([c["conteo"] for c in mapa["capas"]], [1, 2])

    def test_selection_order_does_not_change_what_is_kept(self):
        al_derecho = mapas.plan_merge(self.conn, [self.mapa_a, self.mapa_b])
        al_reves = mapas.plan_merge(self.conn, [self.mapa_b, self.mapa_a])
        self.assertEqual(len(al_derecho["capas"]), len(al_reves["capas"]))
        self.assertEqual(
            sum(c["conteo"] for c in al_derecho["capas"]),
            sum(c["conteo"] for c in al_reves["capas"]),
        )

    def test_genuinely_identical_layers_still_collapse(self):
        gemelo = mapas.create(
            self.conn, "Mapa B bis", "simple", [{"base_id": self.base_id, "color": "#1"}])
        plan = mapas.plan_merge(self.conn, [self.mapa_b, gemelo])
        self.assertEqual(len(plan["capas"]), 1)
        self.assertEqual(len(plan["duplicadas"]), 1)
        self.assertEqual(plan["duplicadas"][0]["igual_a"], "Mapa B")


class EveryRowIsAccountedFor(TempDatabase):
    """#5 P1 - incomplete rows disappeared without being reported."""

    def build(self, fila):
        mapped, unknown = map_headers(
            ["ID", "Terreno", "Estado", "Municipio", "Superficie m2", "X", "Y"])
        return _build_record(fila, mapped, unknown, 1, 3)

    def test_a_row_with_data_but_no_name_is_rejected_not_dropped(self):
        resultado = self.build((2, None, "Jalisco", "Tala", 50_000, 20.6, -103.7))
        self.assertIsInstance(resultado, RejectedRow)
        self.assertEqual(resultado.fila, 3)
        self.assertEqual(resultado.motivo, "SIN_NOMBRE")

    def test_the_rejection_says_what_the_row_held(self):
        resultado = self.build((2, None, "Jalisco", "Tala", 50_000, 20.6, -103.7))
        self.assertIn("Jalisco", resultado.resumen)
        self.assertIn("Tala", resultado.resumen)

    def test_a_genuinely_blank_row_is_not_reported(self):
        self.assertIsNone(self.build((None, None, None, None, None, None, None)))

    def test_accepted_plus_rejected_accounts_for_every_row(self):
        resultado = read_workbook(FIXTURE)
        self.assertEqual(
            resultado.filas_con_datos,
            len(resultado.records) + len(resultado.rechazadas))
        self.assertEqual(len(resultado.records), 79)


class ImpossibleCoordinatesAreNotMapReady(TempDatabase):
    """#6 P2 - invalid coordinates counted as located."""

    def test_the_reported_pair_is_classified_as_invalid(self):
        self.assertEqual(location_state(-103.7, 20.6), UBICACION_INVALIDA)

    def test_the_three_states_are_distinct(self):
        self.assertEqual(location_state(20.7, -103.4), UBICACION_VALIDA)
        self.assertEqual(location_state(None, None), UBICACION_SIN_DATO)
        self.assertEqual(location_state(48.85, 2.35), UBICACION_INVALIDA)

    def test_an_invalid_pair_is_not_plottable(self):
        terreno = rec(lat=-103.7, lon=20.6)
        self.assertFalse(terreno.ubicado)
        self.assertEqual(terreno.ubicacion, UBICACION_INVALIDA)

    def test_the_original_values_are_kept_not_swapped(self):
        terreno = rec(lat=-103.7, lon=20.6)
        self.assertEqual(terreno.lat, -103.7)
        self.assertEqual(terreno.lon, 20.6)
        self.assertIn("COORD_INVERTIDA", [f.codigo for f in validate_record(terreno)])

    def test_counts_separate_missing_from_impossible(self):
        base_id = bases.create(self.conn, "Base", None, None)
        terrenos.insert(self.conn, base_id, [
            rec(1, "Buena"),
            rec(2, "Falta", lat=None, lon=None),
            rec(3, "Imposible", lat=-103.7, lon=20.6),
        ], {})
        base = bases.get(self.conn, base_id)
        self.assertEqual(base["conteo"], 3)
        self.assertEqual(base["ubicados"], 1)
        self.assertEqual(base["sin_coordenadas"], 1)
        self.assertEqual(base["ubicacion_invalida"], 1)

    def test_an_invalid_terrain_is_held_back_from_the_map(self):
        base_id = bases.create(self.conn, "Base", None, None)
        terrenos.insert(self.conn, base_id, [rec(1, "Imposible", lat=-103.7, lon=20.6)], {})
        fila = terrenos.for_base(self.conn, base_id)[0]
        self.assertFalse(fila["ubicado"])
        self.assertEqual(fila["ubicacion"], UBICACION_INVALIDA)

    def test_snapshots_apply_the_same_rule(self):
        base_id = bases.create(self.conn, "Base", None, None)
        terrenos.insert(self.conn, base_id, [
            rec(1, "Buena"), rec(2, "Imposible", lat=-103.7, lon=20.6)], {})
        mapa_id = mapas.create(
            self.conn, "M", "simple", [{"base_id": base_id, "color": "#1"}])
        self.assertEqual(mapas.get(self.conn, mapa_id)["capas"][0]["ubicados"], 1)

    def test_the_sql_predicate_agrees_with_the_python_rule(self):
        """The counts are computed in SQL; they must not drift from the rule."""
        casos = [
            (20.7, -103.4), (None, None), (20.7, None), (-103.7, 20.6),
            (48.85, 2.35), (14.0, -118.5), (33.0, -86.0), (13.9, -100.0),
            (0.0, 0.0), (32.9, -87.0),
        ]
        base_id = bases.create(self.conn, "Base", None, None)
        terrenos.insert(
            self.conn, base_id,
            [rec(i, f"T{i}", lat=lat, lon=lon) for i, (lat, lon) in enumerate(casos, 1)],
            {})

        filas = self.conn.execute(
            f"SELECT lat, lon, {sql_ubicacion_valida()} AS valida FROM terreno"
            " WHERE base_id = ? ORDER BY orden", (base_id,)).fetchall()

        for fila in filas:
            with self.subTest(lat=fila["lat"], lon=fila["lon"]):
                esperado = location_state(fila["lat"], fila["lon"]) == UBICACION_VALIDA
                self.assertEqual(bool(fila["valida"]), esperado)


class SchemaUpgrade(unittest.TestCase):
    """The identity fix must reach databases created before it."""

    def test_the_schema_version_advanced(self):
        self.assertGreaterEqual(db.SCHEMA_VERSION, 3)


if __name__ == "__main__":
    unittest.main()

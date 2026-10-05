"""Tests for identity and append classification."""

from __future__ import annotations

import unittest
from pathlib import Path

from server.importer import TerrainRecord, read_workbook
from server.matching import (
    Disposition,
    classify,
    dedupe_key,
    same_area,
)

FIXTURE = Path(__file__).parent / "fixtures" / "base_terrenos_09_26.xlsx"


def make(terreno="El Mirador", estado="Jalisco", municipio="Zapopan",
         superficie_m2=10_000.0, asking_price=5_000_000.0, orden=1) -> TerrainRecord:
    return TerrainRecord(
        orden=orden, fila=orden + 1, terreno=terreno, estado=estado,
        municipio=municipio, superficie_m2=superficie_m2, asking_price=asking_price,
    )


def existing(id, record):
    return {
        "id": id,
        "clave_dedupe": record.clave_dedupe,
        "superficie_m2": record.superficie_m2,
        "asking_price": record.asking_price,
    }


class DedupeKey(unittest.TestCase):
    def test_ignores_accents_and_case(self):
        self.assertEqual(
            dedupe_key("Tecámac 26", "Estado de México", "Tecámac"),
            dedupe_key("TECAMAC 26", "estado de mexico", "tecamac"),
        )

    def test_distinguishes_different_municipalities(self):
        self.assertNotEqual(
            dedupe_key("El Mirador", "Jalisco", "Zapopan"),
            dedupe_key("El Mirador", "Jalisco", "Tala"),
        )

    def test_tolerates_missing_parts(self):
        self.assertEqual(dedupe_key("X", None, None), "x||")


class AreaComparison(unittest.TestCase):
    def test_identical_areas_match(self):
        self.assertTrue(same_area(260_000.0, 260_000.0))

    def test_survey_level_rounding_matches(self):
        # 260,000 vs 260,076 is the real Tecamac 26 pair: 0.03% apart.
        self.assertTrue(same_area(260_000.0, 260_076.0))

    def test_genuinely_different_parcels_do_not_match(self):
        # The real Tecamac 93 pair: 45 Ha vs 93 Ha.
        self.assertFalse(same_area(450_000.0, 930_000.0))

    def test_two_missing_areas_match_but_one_does_not(self):
        self.assertTrue(same_area(None, None))
        self.assertFalse(same_area(None, 100.0))


class Classify(unittest.TestCase):
    def test_an_unseen_terrain_is_new(self):
        result = classify([make()], [])
        self.assertEqual(result[0].disposition, Disposition.NUEVA)

    def test_an_identical_terrain_is_a_duplicate(self):
        record = make()
        result = classify([record], [existing(7, record)])
        self.assertEqual(result[0].disposition, Disposition.DUPLICADA)
        self.assertEqual(result[0].existing_id, 7)

    def test_the_same_terrain_at_a_new_price_is_a_conflict(self):
        old = make(asking_price=5_000_000.0)
        new = make(asking_price=6_000_000.0)
        result = classify([new], [existing(7, old)])
        self.assertEqual(result[0].disposition, Disposition.CONFLICTO)
        self.assertEqual(result[0].existing_id, 7)
        self.assertIn("Asking Price", result[0].reason)
        self.assertEqual([d.campo for d in result[0].diferencias], ["asking_price"])

    def test_same_name_different_size_is_a_separate_parcel(self):
        small = make(terreno="Tecámac 93", superficie_m2=450_000.0)
        large = make(terreno="Tecámac 93", superficie_m2=930_000.0)
        result = classify([large], [existing(7, small)])
        self.assertEqual(result[0].disposition, Disposition.NUEVA)

    def test_a_file_repeating_a_row_reports_the_second_as_duplicate(self):
        record = make()
        result = classify([record, record], [])
        self.assertEqual(
            [r.disposition for r in result],
            [Disposition.NUEVA, Disposition.DUPLICADA],
        )

    def test_classification_does_not_mutate_its_inputs(self):
        record = make()
        store = [existing(7, record)]
        snapshot = [dict(row) for row in store]
        classify([record], store)
        self.assertEqual(store, snapshot)


class AppendingTheRealWorkbook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = read_workbook(FIXTURE).records

    def test_appending_the_same_file_twice_adds_nothing(self):
        stored = [existing(i, r) for i, r in enumerate(self.records, start=1)]
        result = classify(self.records, stored)
        self.assertEqual(
            [r for r in result if r.disposition is Disposition.NUEVA], []
        )

    def test_importing_into_an_empty_base_keeps_both_tecamac_93_parcels(self):
        result = classify(self.records, [])
        new_count = sum(1 for r in result if r.disposition is Disposition.NUEVA)
        # 79 rows, of which the Tecamac 26 pair is one true duplicate.
        self.assertEqual(new_count, 78)

    def test_the_tecamac_26_pair_is_reported_rather_than_silently_kept(self):
        result = classify(self.records, [])
        dupes = [r for r in result if r.disposition is not Disposition.NUEVA]
        self.assertEqual(len(dupes), 1)
        self.assertEqual(self.records[dupes[0].incoming_index].terreno, "Tecámac 26")


if __name__ == "__main__":
    unittest.main()

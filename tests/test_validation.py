"""Validation tests. Findings must describe problems, never change values."""

from __future__ import annotations

import unittest
from pathlib import Path

from server.importer import ParseNote, TerrainRecord, read_workbook
from server.validation import (
    AVISO,
    ERROR,
    summarize,
    validate_all,
    validate_record,
)

FIXTURE = Path(__file__).parent / "fixtures" / "base_terrenos_09_26.xlsx"


def make(**overrides) -> TerrainRecord:
    """A clean, fully-valid terrain, with fields overridden per test."""
    base = dict(
        orden=1,
        fila=2,
        terreno="Terreno de prueba",
        estado="Jalisco",
        municipio="Zapopan",
        superficie_m2=10_000.0,
        superficie_ha=1.0,
        asking_price=5_000_000.0,
        asking_m2=500.0,
        lat=20.7,
        lon=-103.4,
    )
    return TerrainRecord(**{**base, **overrides})


def codes(record) -> set[str]:
    return {f.codigo for f in validate_record(record)}


class CleanRecord(unittest.TestCase):
    def test_a_correct_terrain_produces_no_findings(self):
        self.assertEqual(validate_record(make()), ())


class Coordinates(unittest.TestCase):
    def test_missing_coordinates_is_an_aviso_not_an_error(self):
        findings = validate_record(make(lat=None, lon=None))
        self.assertEqual([f.codigo for f in findings], ["SIN_COORDENADAS"])
        self.assertEqual(findings[0].severidad, AVISO)

    def test_one_missing_coordinate_still_counts_as_unplaced(self):
        self.assertIn("SIN_COORDENADAS", codes(make(lon=None)))

    def test_swapped_x_and_y_is_detected(self):
        # Zapopan written the other way around.
        findings = validate_record(make(lat=-103.4, lon=20.7))
        self.assertEqual([f.codigo for f in findings], ["COORD_INVERTIDA"])
        self.assertEqual(findings[0].severidad, ERROR)

    def test_coordinates_outside_mexico_are_an_error(self):
        self.assertIn("COORD_FUERA_MEXICO", codes(make(lat=48.85, lon=2.35)))

    def test_border_coordinates_are_accepted(self):
        self.assertEqual(codes(make(lat=14.0, lon=-118.5)), set())
        self.assertEqual(codes(make(lat=33.0, lon=-86.0)), set())


class Surface(unittest.TestCase):
    def test_hectares_must_match_square_metres(self):
        findings = validate_record(make(superficie_ha=5.0))
        self.assertEqual([f.codigo for f in findings], ["SUPERFICIE_INCONSISTENTE"])

    def test_sub_metre_rounding_is_tolerated(self):
        self.assertEqual(codes(make(superficie_m2=10_000.5, superficie_ha=1.0)), set())

    def test_missing_side_skips_the_check(self):
        self.assertEqual(codes(make(superficie_ha=None)), set())


class Price(unittest.TestCase):
    def test_price_must_reconcile_with_unit_price_times_area(self):
        self.assertIn("PRECIO_INCONSISTENTE", codes(make(asking_price=50_000_000.0)))

    def test_two_percent_drift_is_tolerated(self):
        self.assertEqual(codes(make(asking_price=5_050_000.0)), set())

    def test_a_ten_times_typo_is_called_out_explicitly(self):
        findings = validate_record(make(asking_price=50_000_000.0))
        self.assertIn("10×", findings[0].mensaje)

    def test_missing_price_skips_the_check(self):
        self.assertEqual(codes(make(asking_price=None)), set())

    def test_a_zero_price_is_flagged_rather_than_reconciling_with_itself(self):
        # 0 == 0 x area, so the consistency rule alone would let this through.
        self.assertIn("PRECIO_CERO", codes(make(asking_price=0.0, asking_m2=0.0)))


class Afectaciones(unittest.TestCase):
    def test_more_than_half_affected_is_flagged(self):
        self.assertIn("AFECTACION_ALTA", codes(make(afectaciones_pct=0.85)))

    def test_a_small_afectacion_is_not_flagged(self):
        self.assertEqual(codes(make(afectaciones_pct=0.12)), set())

    def test_a_whole_number_percentage_is_flagged_as_a_format_problem(self):
        self.assertIn("AFECTACION_FORMATO", codes(make(afectaciones_pct=85.0)))


class MissingFields(unittest.TestCase):
    def test_missing_estado_and_municipio_are_reported(self):
        findings = validate_record(make(estado=None, municipio=None))
        self.assertEqual([f.codigo for f in findings], ["CAMPO_FALTANTE"] * 2)


class NonNumeric(unittest.TestCase):
    def test_a_rejected_cell_becomes_a_finding(self):
        record = make(asking_m2=None, asking_price=None,
                      notes=(ParseNote("asking_m2", "SD"),))
        findings = validate_record(record)
        self.assertEqual(findings[0].codigo, "VALOR_NO_NUMERICO")
        self.assertIn("SD", findings[0].mensaje)


class AcrossRows(unittest.TestCase):
    def test_duplicates_are_flagged_on_both_rows(self):
        rows = (
            make(orden=1, fila=2, terreno="Tecámac 26"),
            make(orden=2, fila=3, terreno="Tecamac 26"),  # differs only by accent
        )
        results = validate_all(rows)
        self.assertIn("DUPLICADO_EN_BASE", {f.codigo for f in results[1]})
        self.assertIn("DUPLICADO_EN_BASE", {f.codigo for f in results[2]})

    def test_same_name_in_a_different_municipality_is_not_a_duplicate(self):
        rows = (
            make(orden=1, fila=2, terreno="El Mirador", municipio="Zapopan"),
            make(orden=2, fila=3, terreno="El Mirador", municipio="Tala"),
        )
        results = validate_all(rows)
        self.assertEqual(results[1], ())
        self.assertEqual(results[2], ())


class AgainstTheRealWorkbook(unittest.TestCase):
    """Locks in the findings actually present in Base Terrenos 09.26."""

    @classmethod
    def setUpClass(cls):
        cls.records = read_workbook(FIXTURE).records
        cls.findings = validate_all(cls.records)

    def test_summary_matches_the_known_state_of_the_file(self):
        self.assertEqual(
            summarize(self.findings),
            {
                "SIN_COORDENADAS": 40,
                "DUPLICADO_EN_BASE": 4,
                "VALOR_NO_NUMERICO": 3,
                "AFECTACION_ALTA": 2,
                "CAMPO_FALTANTE": 1,
                "PRECIO_CERO": 1,
                "PRECIO_INCONSISTENTE": 1,
            },
        )

    def test_marcenas_is_the_only_price_error(self):
        flagged = [
            r.terreno
            for r in self.records
            if any(f.codigo == "PRECIO_INCONSISTENTE" for f in self.findings[r.orden])
        ]
        self.assertEqual(flagged, ["Marceñas"])

    def test_no_coordinate_errors_in_the_real_data(self):
        for record in self.records:
            for finding in self.findings[record.orden]:
                self.assertNotIn(
                    finding.codigo, ("COORD_FUERA_MEXICO", "COORD_INVERTIDA")
                )


if __name__ == "__main__":
    unittest.main()

"""Importer tests, anchored on the real Base Terrenos 09.26 workbook."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from server.errors import WorkbookError
from server.importer import (
    TerrainRecord,
    map_headers,
    read_workbook,
)
from server.validation import MEXICO_LAT, MEXICO_LON

FIXTURE = Path(__file__).parent / "fixtures" / "base_terrenos_09_26.xlsx"


class ReadRealWorkbook(unittest.TestCase):
    """The numbers here were verified by hand against the source file."""

    @classmethod
    def setUpClass(cls):
        cls.result = read_workbook(FIXTURE)

    def test_finds_the_named_sheet(self):
        self.assertEqual(self.result.hoja, "Registro Análisis")

    def test_reads_every_terrain_and_skips_the_blank_row(self):
        # 80 rows follow the header; the last one is empty.
        self.assertEqual(len(self.result.records), 79)

    def test_recognizes_every_column(self):
        # The trailing empty column N carries no header and is ignored rather
        # than reported as unrecognized.
        self.assertEqual(self.result.columnas_no_reconocidas, ())
        self.assertEqual(self.result.columnas_faltantes, ())

    def test_maps_header_with_trailing_space(self):
        # The workbook's header is 'Dirección ' with a trailing space.
        first = self.result.records[0]
        self.assertTrue(first.direccion.startswith("Carretera Zumpango-Jilotzingo"))

    def test_x_is_latitude_and_y_is_longitude(self):
        first = self.result.records[0]
        self.assertAlmostEqual(first.lat, 19.8179452790226)
        self.assertAlmostEqual(first.lon, -99.0874491437001)

    def test_every_plotted_terrain_lands_inside_mexico(self):
        # Regression guard: swapping lat/lon would put these in the Indian Ocean.
        for record in self.result.records:
            if not record.ubicado:
                continue
            with self.subTest(terreno=record.terreno):
                self.assertTrue(MEXICO_LAT[0] <= record.lat <= MEXICO_LAT[1])
                self.assertTrue(MEXICO_LON[0] <= record.lon <= MEXICO_LON[1])

    def test_counts_located_and_unplaced(self):
        self.assertEqual(self.result.ubicados, 39)
        self.assertEqual(self.result.sin_ubicacion, 40)

    def test_sd_becomes_null_and_is_reported(self):
        sd_rows = [r for r in self.result.records if r.notes]
        self.assertEqual(len(sd_rows), 3)
        for record in sd_rows:
            with self.subTest(terreno=record.terreno):
                self.assertIsNone(record.asking_m2)
                self.assertEqual(record.notes[0].campo, "asking_m2")
                self.assertEqual(record.notes[0].valor, "SD")

    def test_preserves_both_tecamac_93_parcels(self):
        parcels = [r for r in self.result.records if r.terreno == "Tecámac 93"]
        self.assertEqual(len(parcels), 2)
        self.assertEqual(
            sorted(p.superficie_ha for p in parcels), [45.0, 93.0]
        )

    def test_orden_is_sequential_and_fila_points_at_the_spreadsheet(self):
        self.assertEqual([r.orden for r in self.result.records[:3]], [1, 2, 3])
        # Row 1 is the header, so the first record sits on spreadsheet row 2.
        self.assertEqual(self.result.records[0].fila, 2)

    def test_id_origen_is_kept_but_is_not_the_identity(self):
        first = self.result.records[0]
        self.assertEqual(first.id_origen, 1)
        self.assertNotIn(str(first.id_origen), first.clave_dedupe)


class HeaderMapping(unittest.TestCase):
    def test_ignores_columns_without_a_header(self):
        mapped, unknown = map_headers(["Terreno", None, "Estado", ""])
        self.assertEqual(mapped, {0: "terreno", 2: "estado"})
        self.assertEqual(unknown, {})

    def test_accepts_accent_and_superscript_variants(self):
        mapped, _ = map_headers(["Terreno", "Superficie m²", "Direccion"])
        self.assertEqual(mapped[1], "superficie_m2")
        self.assertEqual(mapped[2], "direccion")

    def test_keeps_unrecognized_columns_for_reporting(self):
        _, unknown = map_headers(["Terreno", "Vendedor"])
        self.assertEqual(unknown, {1: "Vendedor"})

    def test_second_column_claiming_a_taken_field_is_not_silently_used(self):
        mapped, unknown = map_headers(["Terreno", "Nombre"])
        self.assertEqual(mapped, {0: "terreno"})
        self.assertEqual(unknown, {1: "Nombre"})


class Failures(unittest.TestCase):
    def test_missing_file_raises_a_readable_error(self):
        with self.assertRaises(WorkbookError) as caught:
            read_workbook("/no/such/file.xlsx")
        self.assertIn("No se encontró", str(caught.exception))


class RecordBehaviour(unittest.TestCase):
    def test_ubicado_requires_both_coordinates(self):
        base = dict(orden=1, fila=2, terreno="X")
        self.assertFalse(TerrainRecord(**base).ubicado)
        self.assertFalse(TerrainRecord(**base, lat=19.0).ubicado)
        self.assertTrue(TerrainRecord(**base, lat=19.0, lon=-99.0).ubicado)

    def test_records_are_immutable(self):
        record = TerrainRecord(orden=1, fila=2, terreno="X")
        with self.assertRaises(FrozenInstanceError):
            record.terreno = "Y"


if __name__ == "__main__":
    unittest.main()

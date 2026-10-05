"""CSV reader tests. Every record here is fictional."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

from server.csv_importer import CSV_SHEET, CsvError, read_csv_bytes
from server.csv_numbers import parse_id, parse_number
from server.validation import validate_record

HEADER = ("ID,Terreno,Estado,Municipio,Dirección,Superficie m2,Superficie Ha,"
          "Afectaciones %,Afectaciones m2,Asking Price,Asking $/m2,X,Y")
TEMPLATE = (
    HEADER + "\n"
    '1,Predio Prueba Norte,Estado de México,Tecámac,"Av. Central 120, Colonia Centro",'
    "25000,2.5,10%,2500,12500000,500,19.713,-98.968\n"
    "2,Predio Prueba Sur,Jalisco,Tala,Camino Rural 8,40000,4,0,0,12000000,300,20.653,-103.701\n"
)


def read(text: str, **kwargs):
    return read_csv_bytes(text.encode("utf-8"), **kwargs)


def by_name(result):
    return {r.terreno: r for r in result.records}


class BasicReader(unittest.TestCase):
    def assert_template(self, result):
        self.assertEqual(result.hoja, CSV_SHEET)
        self.assertEqual(len(result.records), 2)
        norte = by_name(result)["Predio Prueba Norte"]
        self.assertEqual(norte.id_origen, 1)
        self.assertEqual(norte.estado, "Estado de México")
        self.assertEqual(norte.municipio, "Tecámac")
        self.assertEqual(norte.direccion, "Av. Central 120, Colonia Centro")
        self.assertEqual(norte.superficie_m2, 25000)
        self.assertEqual(norte.superficie_ha, 2.5)
        self.assertAlmostEqual(norte.afectaciones_pct, 0.10)
        self.assertEqual(norte.asking_price, 12_500_000)
        # X is latitude and Y is longitude in these files, never the GIS way round.
        self.assertEqual((norte.lat, norte.lon), (19.713, -98.968))
        self.assertTrue(norte.ubicado)
        self.assertEqual(norte.notes, ())
        self.assertEqual(result.columnas_no_reconocidas, ())
        self.assertEqual(result.columnas_faltantes, ())

    def test_comma_separated_template(self):
        self.assert_template(read(TEMPLATE))

    def test_the_shipped_template_is_this_template(self):
        shipped = Path(__file__).parents[1] / "web" / "assets" / "plantilla-terrenos.csv"
        self.assert_template(read_csv_bytes(shipped.read_bytes()))

    def test_semicolon_separated_with_bom_and_crlf(self):
        text = (HEADER.replace(",", ";") + "\r\n"
                '1;Predio Prueba Norte;Estado de México;Tecámac;"Av. Central 120, Colonia Centro";'
                "25000;2.5;10%;2500;12500000;500;19.713;-98.968\r\n"
                "2;Predio Prueba Sur;Jalisco;Tala;Camino Rural 8;40000;4;0;0;12000000;300;20.653;-103.701\r\n")
        self.assert_template(read_csv_bytes(b"\xef\xbb\xbf" + text.encode()))

    def test_reordered_columns_and_aliases(self):
        text = ("Longitud,Latitud,Nombre,Domicilio,Precio\n"
                "-98.968,19.713,Predio Prueba Norte,Av. Central 120,12500000\n")
        record = read(text).records[0]
        self.assertEqual((record.terreno, record.direccion), ("Predio Prueba Norte", "Av. Central 120"))
        self.assertEqual((record.lat, record.lon, record.asking_price), (19.713, -98.968, 12_500_000))

    def test_fila_is_the_physical_line(self):
        result = read(TEMPLATE)
        self.assertEqual([r.fila for r in result.records], [2, 3])
        self.assertEqual([r.orden for r in result.records], [1, 2])

    def test_excel_sep_directive_is_honoured_and_not_counted(self):
        result = read("sep=;\nTerreno;X;Y\nPredio A;19,5;-99\n", decimal_mode="comma")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].fila, 3)
        self.assertEqual(result.records[0].lat, 19.5)

    def test_unknown_columns_are_kept_as_extra(self):
        result = read("Terreno,Vendedor\nPredio A,Fulano\n")
        self.assertEqual(result.columnas_no_reconocidas, ("Vendedor",))
        self.assertEqual(dict(result.records[0].extra), {"Vendedor": "Fulano"})

    def test_second_alias_for_a_taken_field_becomes_extra(self):
        result = read("Terreno,Nombre\nPredio A,Otro nombre\n")
        self.assertEqual(result.records[0].terreno, "Predio A")
        self.assertEqual(dict(result.records[0].extra), {"Nombre": "Otro nombre"})


class Quoting(unittest.TestCase):
    def test_escaped_quotes(self):
        record = read('Terreno,Dirección\n"Predio ""El Alto""","Calle 1, Lote 2"\n').records[0]
        self.assertEqual(record.terreno, 'Predio "El Alto"')
        self.assertEqual(record.direccion, "Calle 1, Lote 2")

    def test_multiline_field_reports_its_first_line(self):
        text = 'Terreno,Dirección,X,Y\n\n"Predio A","Camino\nRural\n8",19.7,-99.0\nPredio B,Calle 2,19.8,-99.1\n'
        result = read(text)
        a, b = result.records
        self.assertEqual(a.direccion, "Camino Rural 8")  # clean_text folds whitespace
        self.assertEqual((a.fila, b.fila), (3, 6))

    def test_unclosed_quote_fails_the_file(self):
        with self.assertRaises(CsvError) as caught:
            read('Terreno,Estado\n"Predio A,Jalisco\nPredio B,Tala\n')
        self.assertIn("comilla", str(caught.exception))

    def test_text_after_closing_quote_fails_the_file(self):
        with self.assertRaises(CsvError) as caught:
            read('Terreno,Estado\n"Predio A"x,Jalisco\n')
        self.assertIn("línea 2", str(caught.exception))


class MinimalAndEmpty(unittest.TestCase):
    def test_only_terreno_is_enough(self):
        result = read("Terreno\nPredio Solo\n")
        self.assertEqual(len(result.records), 1)
        self.assertFalse(result.records[0].ubicado)
        self.assertIn("lat", result.columnas_faltantes)

    def test_one_column_value_with_a_quoted_comma(self):
        self.assertEqual(read('Terreno\n"Predio, Norte"\n').records[0].terreno, "Predio, Norte")

    def test_blank_records_are_not_counted(self):
        result = read("\n\nTerreno,Estado\n\n,\nPredio A,Jalisco\n  \n")
        self.assertEqual(result.filas_con_datos, 1)
        self.assertEqual(result.records[0].fila, 6)

    def test_empty_file(self):
        for content in (b"", b"\n\n", b"\xef\xbb\xbf"):
            with self.subTest(content=content), self.assertRaises(CsvError):
                read_csv_bytes(content)

    def test_header_only(self):
        with self.assertRaises(CsvError) as caught:
            read("Terreno,Estado\n")
        self.assertIn("encabezados", str(caught.exception))

    def test_nameless_rows_are_rejected_with_their_line(self):
        result = read("Terreno,Estado\nPredio A,Jalisco\n,Sonora\nSD,SD\n")
        self.assertEqual(len(result.records), 1)
        self.assertEqual([(r.fila, r.motivo) for r in result.rechazadas],
                         [(3, "SIN_NOMBRE"), (4, "SIN_NOMBRE")])
        self.assertIn("Sonora", result.rechazadas[0].resumen)
        self.assertEqual(result.filas_con_datos, len(result.records) + len(result.rechazadas))


class HeadersAndShape(unittest.TestCase):
    def assert_fails(self, text, fragment):
        with self.assertRaises(CsvError) as caught:
            read(text)
        self.assertIn(fragment, str(caught.exception))

    def test_missing_terreno(self):
        self.assert_fails("Estado,Municipio\nJalisco,Tala\n", "obligatoria «Terreno»")

    def test_duplicate_header(self):
        self.assert_fails("Terreno,Estado,estado\nA,Jalisco,Jalisco\n", "repite el encabezado")

    def test_data_under_an_unnamed_header(self):
        self.assert_fails("Terreno,,Estado\nA,dato,Jalisco\n", "no tiene encabezado")

    def test_empty_unnamed_trailing_column_is_fine(self):
        self.assertEqual(read("Terreno,Estado,\nA,Jalisco,\n").records[0].estado, "Jalisco")

    def test_too_many_fields(self):
        self.assert_fails("Terreno,Estado\nA,Jalisco\nB,Calle 1, Lote 2\n",
                          "3 columnas en la línea 3; se esperaban 2")

    def test_too_few_fields(self):
        self.assert_fails("Terreno,Estado,Municipio\nA,Jalisco\n",
                          "2 columnas en la línea 2; se esperaban 3")

    def test_unquoted_semicolon_in_a_semicolon_file_is_not_shifted(self):
        self.assert_fails("Terreno;Dirección;X\nA;Calle 1; Lote 2;19.7\n", "línea 2")


class Encoding(unittest.TestCase):
    def test_windows_1252_is_refused_with_a_useful_message(self):
        with self.assertRaises(CsvError) as caught:
            read_csv_bytes("Terreno,Municipio\nPredio,Tecámac\n".encode("cp1252"))
        self.assertIn("CSV UTF-8", str(caught.exception))

    def test_utf16_is_refused(self):
        with self.assertRaises(CsvError):
            read_csv_bytes("Terreno\nPredio\n".encode("utf-16"))

    def test_an_excel_file_renamed_csv_is_refused(self):
        with self.assertRaises(CsvError) as caught:
            read_csv_bytes(b"PK\x03\x04rest-of-zip")
        self.assertIn("libro de Excel", str(caught.exception))

    def test_unknown_decimal_mode(self):
        with self.assertRaises(CsvError):
            read("Terreno\nA\n", decimal_mode="space")


class Numbers(unittest.TestCase):
    def num(self, raw, mode="dot", field="superficie_m2"):
        return parse_number(field, raw, mode)

    def test_dot_mode(self):
        for raw, expected in [("1234.56", 1234.56), ("1,234.56", 1234.56), ("1,234", 1234.0),
                              ("0", 0.0), ("-98.968", -98.968), (".5", 0.5), ("1.5e3", 1500.0)]:
            with self.subTest(raw=raw):
                self.assertEqual(self.num(raw), (expected, None))

    def test_comma_mode(self):
        for raw, expected in [("1234,56", 1234.56), ("1.234,56", 1234.56), ("1.234", 1234.0),
                              ("-98,968", -98.968), ("1,5e3", 1500.0)]:
            with self.subTest(raw=raw):
                self.assertEqual(self.num(raw, "comma"), (expected, None))

    def test_bad_grouping_is_reported_not_rescaled(self):
        for raw, mode in [("19,4326", "dot"), ("1,23.4", "dot"), ("12,34,567", "dot"),
                          ("1.5", "comma"), ("1.234.5", "comma"), ("1 234", "dot"), ("12abc", "dot")]:
            with self.subTest(raw=raw, mode=mode):
                value, note = self.num(raw, mode)
                self.assertIsNone(value)
                self.assertEqual(note.valor, raw)
                self.assertIn("decimal", note.motivo)

    def test_percent_only_in_afectaciones(self):
        pct = "afectaciones_pct"
        self.assertEqual(self.num("10%", field=pct)[0], 0.10)
        self.assertEqual(self.num("0.5%", field=pct)[0], 0.005)
        self.assertEqual(self.num("0,5 %", "comma", pct)[0], 0.005)
        self.assertEqual(self.num("0.10", field=pct)[0], 0.10)
        self.assertEqual(self.num("10", field=pct)[0], 10.0)  # flagged by validation, not divided
        value, note = self.num("10%", field="superficie_m2")
        self.assertIsNone(value)
        self.assertIn("%", note.motivo)

    def test_dollar_only_in_prices(self):
        self.assertEqual(self.num("$12,500,000", field="asking_price")[0], 12_500_000)
        self.assertEqual(self.num("$ 500.50", field="asking_m2")[0], 500.5)
        self.assertEqual(self.num("-$5", field="asking_price")[0], -5)
        self.assertIsNone(self.num("$5", field="lat")[0])
        self.assertIsNone(self.num("$1,23", field="asking_price")[0])
        self.assertIsNone(self.num("$12x", field="asking_price")[0])

    def test_empty_and_sentinels(self):
        self.assertEqual(self.num(""), (None, None))
        self.assertEqual(self.num("   "), (None, None))
        value, note = self.num("SD")
        self.assertIsNone(value)
        self.assertEqual((note.valor, note.motivo), ("SD", None))

    def test_non_finite_values_never_pass(self):
        for raw in ("NaN", "inf", "-Infinity", "1e999"):
            with self.subTest(raw=raw):
                value, note = self.num(raw)
                self.assertIsNone(value)
                self.assertIsNotNone(note)

    def test_formulas_are_text(self):
        for raw in ("=1+1", "=SUM(A1:A2)", "@SUM(A1)", "+A1"):
            with self.subTest(raw=raw):
                value, note = self.num(raw)
                self.assertIsNone(value)
                self.assertEqual(note.valor, raw)

    def test_ids(self):
        self.assertEqual(parse_id("7", "dot"), (7, None))
        self.assertEqual(parse_id("", "dot"), (None, None))
        for raw in ("1.5", "abc", "1e999"):
            with self.subTest(raw=raw):
                value, note = parse_id(raw, "dot")
                self.assertIsNone(value)
                self.assertEqual((note.campo, note.valor), ("id_origen", raw))


class FindingsFromCsv(unittest.TestCase):
    def test_numeric_problems_keep_the_terrain_and_explain_themselves(self):
        text = ("ID,Terreno,Estado,Municipio,X,Y,Afectaciones %\n"
                "1.5,Predio A,Jalisco,Tala,\"19,4326\",-99.1,10\n")
        record = read(text).records[0]
        self.assertEqual(record.terreno, "Predio A")
        self.assertIsNone(record.id_origen)
        self.assertIsNone(record.lat)
        self.assertFalse(record.ubicado)

        mensajes = {f.codigo: [] for f in validate_record(record)}
        for f in validate_record(record):
            mensajes[f.codigo].append(f.mensaje)
        numericos = " ".join(mensajes["VALOR_NO_NUMERICO"])
        self.assertIn("«19,4326»", numericos)
        self.assertIn("X (latitud)", numericos)
        self.assertIn("línea 2", numericos)
        self.assertIn("punto decimal", numericos)
        self.assertIn("«1.5»", numericos)
        self.assertIn("AFECTACION_FORMATO", mensajes)
        self.assertIn("SIN_COORDENADAS", mensajes)

    def test_mixed_rows_reconcile(self):
        text = ("Terreno,Estado,Municipio,X,Y,Asking Price\n"
                "Ubicado,Jalisco,Tala,20.6,-103.7,100\n"
                ",Jalisco,Tala,20.6,-103.7,100\n"
                "Sin coordenadas,Jalisco,Tala,,,100\n"
                "Invertido,Jalisco,Tala,-103.7,20.6,100\n"
                "Precio raro,Jalisco,Tala,20.6,-103.7,cien\n")
        result = read(text)
        self.assertEqual(result.filas_con_datos, 5)
        self.assertEqual((len(result.records), len(result.rechazadas)), (4, 1))
        self.assertEqual((result.ubicados, result.sin_coordenadas, result.ubicacion_invalida), (2, 1, 1))
        raro = by_name(result)["Precio raro"]
        self.assertEqual([(n.campo, n.valor) for n in raro.notes], [("asking_price", "cien")])
        self.assertTrue(all(math.isfinite(r.lat) for r in result.records if r.lat is not None))


if __name__ == "__main__":
    unittest.main()

"""Reading a file's shape: which separator, and which row is the header.

Fictional data only. A tab-separated export is a table, not one long name, and
a header that sits below a page of notes has to be reachable -- automatically
when nothing else looks like one, and by its printed row number otherwise.
"""

from __future__ import annotations

import io
import unittest

from openpyxl import Workbook

from server.asistente.detectar import interpretar
from server.asistente.rejilla import leer
from server.csv_importer import read_csv_bytes
from server.web_util import ApiError
from tests.test_asistente_api import AsistenteCase

COLUMNAS = ("Terreno", "Precio", "Superficie m2", "Latitud", "Longitud")
TERRENOS = (
    ("FICTICIO Encino", 1200000, 2400, 19.4326, -99.1332),
    ("FICTICIO Roble", 2500000, 5000, 20.6736, -103.344),
    ("FICTICIO Cedro", 3750000, 7500, 25.6866, -100.3161),
    ("FICTICIO Fresno", 4800000, 9600, 20.5888, -100.3899),
)


def separado(separador, terminador="\r\n"):
    filas = [COLUMNAS, *TERRENOS]
    return terminador.join(separador.join(str(v) for v in fila) for fila in filas).encode() + b"\r\n"


def libro(en_fila):
    """A workbook written row by row, so blank rows really are blank rows."""
    wb = Workbook()
    for numero, valores in en_fila.items():
        for columna, valor in enumerate(valores, start=1):
            wb.active.cell(row=numero, column=columna, value=valor)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def notas(cuantas, desde=1):
    return {desde + i: (f"Nota ficticia {i + 1}",) for i in range(cuantas)}


def tabla(desde):
    return {desde + i: fila for i, fila in enumerate((COLUMNAS, *TERRENOS))}


class Separadores(unittest.TestCase):
    def test_a_tab_separated_export_is_read_as_columns(self):
        rejilla = leer(separado("\t"), "x.csv")
        self.assertEqual([h.id for h in rejilla.hojas], ["csv:\t"])
        self.assertEqual(rejilla.hojas[0].filas[0], COLUMNAS)
        self.assertEqual(len(rejilla.hojas[0].filas), 5)

    def test_a_tab_directive_is_honoured(self):
        rejilla = leer(b"sep=\t\r\n" + separado("\t"), "x.csv")
        self.assertEqual([h.id for h in rejilla.hojas], ["csv:\t"])

    def test_commas_and_semicolons_still_win_on_their_own_files(self):
        self.assertEqual([h.id for h in leer(separado(","), "x.csv").hojas], ["csv:,"])
        self.assertEqual([h.id for h in leer(separado(";"), "x.csv").hojas], ["csv:;"])

    def test_a_one_column_list_of_names_is_one_table_not_three(self):
        rejilla = leer(b"Terreno\nFICTICIO Encino\nFICTICIO Roble\n", "x.csv")
        self.assertEqual(len(rejilla.hojas), 1)
        self.assertEqual(rejilla.hojas[0].filas, (("Terreno",), ("FICTICIO Encino",), ("FICTICIO Roble",)))

    def test_quoted_values_with_line_breaks_survive_the_choice(self):
        crudo = b'Terreno,Direccion\n"FICTICIO Encino","Calle 1\nCol. Centro"\n'
        hoja = leer(crudo, "x.csv").hojas[0]
        self.assertEqual(hoja.filas[1], ("FICTICIO Encino", "Calle 1\nCol. Centro"))
        self.assertEqual(hoja.lineas, (1, 2))

    def test_a_tab_inside_a_comma_file_does_not_take_over(self):
        rejilla = leer(b"Terreno,Notas\nFICTICIO Encino,uno\tdos\n", "x.csv")
        self.assertEqual([h.id for h in rejilla.hojas], ["csv:,"])

    def test_the_legacy_reader_accepts_tabs_too(self):
        resultado = read_csv_bytes(separado("\t"))
        self.assertEqual([r.terreno for r in resultado.records], [t[0] for t in TERRENOS])
        self.assertEqual(resultado.records[0].asking_price, 1200000)


class Encabezados(unittest.TestCase):
    def test_a_header_below_a_page_of_notes_is_found_and_offered(self):
        rejilla = leer(libro({**notas(55), **tabla(56)}), "x.xlsx")
        interp = interpretar(rejilla, {})
        self.assertEqual(interp.encabezado, 55)
        self.assertIn(55, interp.encabezados[:50])

    def test_a_header_in_the_first_rows_still_wins(self):
        rejilla = leer(libro({**tabla(1), **notas(60, desde=10)}), "x.xlsx")
        self.assertEqual(interpretar(rejilla, {}).encabezado, 0)

    def test_blank_rows_keep_the_printed_row_number_honest(self):
        hoja = leer(libro(tabla(3)), "x.xlsx").hojas[0]
        self.assertEqual(hoja.lineas, (3, 4, 5, 6, 7))


class Correcciones(AsistenteCase):
    def test_the_header_can_be_named_by_the_row_number_printed_in_the_file(self):
        r = self.analizar("notas.xlsx", libro({**notas(55), **tabla(60)}))
        corregida = self.preparar(r, correcciones={"encabezado_linea": 60})
        self.assertEqual(corregida["interpretacion"]["encabezado"], {"indice": 55, "linea": 60})
        self.assertEqual(corregida["vista_previa"]["conteo"], 4)
        self.assertEqual(corregida["vista_previa"]["con_precio"], 4)
        self.assertEqual(self.confirmar(corregida, recordar_formato=False)["base"]["conteo"], 4)

    def test_blank_rows_before_the_header_do_not_shift_the_choice(self):
        r = self.analizar("blancos.xlsx", libro({**notas(3, desde=2), **tabla(9)}))
        corregida = self.preparar(r, correcciones={"encabezado_linea": 9})
        self.assertEqual(corregida["interpretacion"]["encabezado"], {"indice": 3, "linea": 9})
        self.assertEqual([f["terreno"] for f in corregida["vista_previa"]["filas"]],
                         [t[0] for t in TERRENOS])

    def test_naming_an_empty_row_is_refused_and_says_where_the_data_is(self):
        r = self.analizar("blancos.xlsx", libro({**notas(3, desde=2), **tabla(9)}))
        with self.assertRaises(ApiError) as fallo:
            self.preparar(r, correcciones={"encabezado_linea": 7})
        self.assertIn("no tiene datos", str(fallo.exception))
        self.assertIn("9", str(fallo.exception))

    def test_the_offered_rows_carry_the_number_the_user_sees(self):
        r = self.analizar("blancos.xlsx", libro({**notas(3, desde=2), **tabla(9)}))
        ofrecidas = {e["indice"]: e["linea"] for e in r["interpretacion"]["encabezados"]}
        self.assertEqual(ofrecidas, {0: 2, 1: 3, 2: 4, 3: 9, 4: 10, 5: 11, 6: 12, 7: 13})
        self.assertEqual(r["interpretacion"]["hoja"]["ultima_linea"], 13)

    def test_a_tab_separated_file_previews_and_imports(self):
        r = self.analizar("tabulado.csv", separado("\t"))
        self.assertEqual(r["estado"], "vista_previa", r.get("error"))
        self.assertEqual(len(r["interpretacion"]["columnas"]), 5)
        self.assertEqual((r["vista_previa"]["conteo"], r["vista_previa"]["con_precio"]), (4, 4))
        self.assertEqual(self.confirmar(r, recordar_formato=False)["base"]["conteo"], 4)


if __name__ == "__main__":
    unittest.main()

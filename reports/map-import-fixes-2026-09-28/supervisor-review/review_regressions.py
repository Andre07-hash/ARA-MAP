"""Independent follow-up checks. Fictional data; disposable SQLite; AI off.

Run from project root with .venv-dev/bin/python <this-file> -v.
These assert desired behavior and deliberately fail on the reviewed revision.
"""
import io
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
for key in list(os.environ):
    if key.startswith('ARA_MAP_IA_') or key in ('DATABASE_URL', 'ARA_MAP_DATABASE_URL', 'ARA_MAP_TEST_DATABASE_URL'):
        os.environ.pop(key, None)

from openpyxl import Workbook
from tests.test_asistente_api import AsistenteCase
from tests.test_asistente_monedas import en_dolares


def two_sheets():
    wb = Workbook()
    for n in range(2):
        ws = wb.active if n == 0 else wb.create_sheet()
        ws.title = f'Table{n}'
        ws.append(['Terreno', 'Precio', 'Superficie m2', 'Latitud', 'Longitud'])
        for j in range(3):
            ws.append([f'Fictional {n}-{j}', 1000000, 1000, 19 + j / 10, -99])
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


class Followup(AsistenteCase):
    def currency_case(self, fmt):
        r = self.analizar('fictional-currency.xlsx', en_dolares(fmt))
        self.assertEqual(r['estado'], 'vista_previa')
        self.confirmar(r, recordar_formato=False)
        prices = [x[0] for x in self.conn.execute('SELECT asking_price FROM terreno')]
        self.assertEqual(prices, [None] * 4, 'Foreign currency became stored MXN prices')

    def test_control_quoted_usd_is_blocked(self):
        self.currency_case('"USD "#,##0.00')

    def test_adjacent_escaped_usd_is_blocked(self):
        self.currency_case(r'\U\S\D\ #,##0.00')

    def test_unquoted_pound_is_blocked(self):
        self.currency_case('£#,##0.00')

    def test_exclusion_does_not_move_to_another_worksheet(self):
        r = self.analizar('two-sheets.xlsx', two_sheets())
        r = self.preparar(r, correcciones={'hoja': 'sheet:0'})
        r = self.preparar(r, correcciones={'excluir': [1]})
        self.assertEqual(r['vista_previa']['conteo'], 2)
        r = self.preparar(r, correcciones={'hoja': 'sheet:1'})
        self.confirmar(r, recordar_formato=False)
        names = [x[0] for x in self.conn.execute('SELECT terreno FROM terreno ORDER BY orden')]
        self.assertEqual(names, [f'Fictional 1-{i}' for i in range(3)])

    def test_last_removed_row_keeps_a_recoverable_preview(self):
        r = self.analizar('one.csv', b'Terreno,Precio,Latitud,Longitud\nFictional single,1200000,19,-99\n')
        r = self.preparar(r, correcciones={'excluir': [1]})
        self.assertIn('vista_previa', r, 'Removing the final row hides every restore control')
        self.assertEqual(r['vista_previa']['conteo'], 0)
        self.assertEqual(r['vista_previa']['excluidas'][0]['indice'], 1)
        r = self.preparar(r, correcciones={'incluir': [1]})
        self.assertEqual(self.confirmar(r, recordar_formato=False)['base']['conteo'], 1)


if __name__ == '__main__':
    unittest.main()

"""Desired safety outcomes. Five cases fail on the reviewed application.

Run from the repository root. No production database or paid provider used.
"""
import os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
for k in ('DATABASE_URL','ARA_MAP_DATABASE_URL','ARA_MAP_TEST_DATABASE_URL'):os.environ.pop(k,None)
from tests.test_asistente_api import AsistenteCase
FILES=Path(__file__).resolve().parents[1]/'files'

class ImportSafety(AsistenteCase):
    def upload(self,name):return self.analizar(name,(FILES/name).read_bytes())

    def test_control_normal_xlsx_preserves_four_rows(self):
        r=self.upload('MapTest1.xlsx')
        self.assertEqual(r['vista_previa']['conteo'],4)
        self.assertEqual(self.confirmar(r,recordar_formato=False)['base']['conteo'],4)

    def test_control_real_total_row_is_excluded(self):
        r=self.upload('MapTest7.csv')
        self.assertEqual(r['vista_previa']['conteo'],4)
        self.assertEqual(len(r['vista_previa']['excluidas']),1)

    def test_excel_currency_format_cannot_be_relabelled_mxn(self):
        r=self.upload('MapTest20.xlsx')
        if r['estado']!='vista_previa':return
        self.assertTrue(all(x['asking_price'] is None for x in r['vista_previa']['filas']),
                        'Explicit USD number-format metadata was discarded; prices became MXN.')

    def test_real_terrain_starting_total_is_not_discarded(self):
        r=self.upload('MapTest22.csv')
        if r['estado']!='vista_previa':return
        self.assertIn('Total FICTICIO Encino',[x['terreno'] for x in r['vista_previa']['filas']])

    def test_suspicious_footer_is_not_accepted_without_review(self):
        r=self.upload('MapTest23.csv')
        if r['estado']!='vista_previa':return
        self.assertEqual(r['vista_previa']['conteo'],4,
                         'A notes footer is offered as a fifth terrain without a row-classification question.')

    def test_tab_csv_is_parsed_or_rejected_before_name_mapping(self):
        from server.web_util import ApiError
        try:r=self.upload('MapTest29.csv')
        except ApiError as e:
            self.assertEqual(e.status,400);return
        self.assertGreaterEqual(len(r['interpretacion']['columnas']),5,
                                'Tab-delimited rows were collapsed into one apparent name column.')

    def test_real_header_after_row50_is_selectable(self):
        r=self.upload('MapTest35.xlsx')
        self.assertIn(55,[x['indice'] for x in r['interpretacion']['encabezados']],
                      'The correction dropdown cannot reach the real header at physical row 56.')

if __name__=='__main__':unittest.main()

"""Expected outcomes for every fictional fixture. DISPOSABLE experiment tests.

    python3 -I test_kmz_experiment.py      (from this folder)

Lives outside tests/ on purpose: it is report evidence, not part of the suite.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import kmz_experiment as k  # noqa: E402
import make_fixtures  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="kmz-fixtures-"))
make_fixtures.main(TMP)


def run(nombre: str, **kw):
    return k.procesar((TMP / nombre).read_bytes(), nombre, **kw)


def codigos(res):
    return {a["codigo"] for a in res.get("avisos", [])}


class Aceptados(unittest.TestCase):
    def test_poligono_simple(self):
        r = run("01_poligono_simple.kmz")
        self.assertEqual(r["estado"], "listo")
        g = r["geometria"]
        self.assertEqual(g["geojson"]["type"], "MultiPolygon")
        self.assertEqual((g["partes"], g["huecos"]), (1, 0))
        # bbox is [west, south, east, north] in KML/GeoJSON lon,lat order.
        self.assertAlmostEqual(g["bbox"][0], -100.4)
        self.assertAlmostEqual(g["bbox"][1], 20.6)
        # The symbol point is [lat, lon]: X stays latitude.
        self.assertAlmostEqual(g["punto_simbolo"][0], 20.6015, places=6)
        self.assertAlmostEqual(g["punto_simbolo"][1], -100.398, places=6)
        # ~417 m x ~333 m at this latitude.
        self.assertTrue(130_000 < g["area_calculada_m2"] < 145_000, g["area_calculada_m2"])
        self.assertTrue(r["utilizable"])

    def test_hueco_resta_area(self):
        g = run("02_poligono_con_hueco.kmz")["geometria"]
        self.assertEqual(g["huecos"], 1)
        lleno = k._area_anillo(g["geojson"]["coordinates"][0][0])
        self.assertLess(g["area_calculada_m2"], lleno)

    def test_multiparte_es_un_terreno(self):
        r = run("03_multiparte.kmz")
        self.assertEqual(r["estado"], "listo")
        self.assertEqual(r["geometria"]["partes"], 2)

    def test_mixto_conserva_contorno_e_informa_lo_ignorado(self):
        r = run("07_mixto_contorno_y_caminos.kmz")
        self.assertEqual(r["estado"], "listo")
        self.assertIn("KML_CONTENIDO_IGNORADO", codigos(r))

    def test_altitud_se_descarta_con_aviso(self):
        r = run("10_altitud_3d.kmz")
        self.assertEqual(r["estado"], "listo")
        self.assertIn("KML_ALTITUD_DESCARTADA", codigos(r))
        self.assertTrue(all(len(p) == 2 for p in r["geometria"]["geojson"]["coordinates"][0][0]))

    def test_kml_suelto_tambien(self):
        self.assertEqual(run("01_poligono_simple.kml")["estado"], "listo")

    def test_doc_kml_gana_y_avisa_de_los_demas(self):
        r = run("20_kmz_con_imagen_y_files.kmz")
        self.assertEqual(r["estado"], "listo")
        self.assertEqual(r["documento"], "doc.kml")
        self.assertIn("KMZ_KML_ADICIONALES", codigos(r))


class Ambiguos(unittest.TestCase):
    def test_nunca_elige_el_primero(self):
        r = run("04_ambiguo_varios_lotes.kmz")
        self.assertEqual(r["estado"], "requiere_eleccion")
        self.assertNotIn("geometria", r)
        self.assertEqual([c["nombre"] for c in r["candidatos"]], ["Lote A", "Lote B", "Lote C"])
        self.assertEqual(r["candidatos"][0]["carpeta"], ["Ficticio", "Lotes ficticios"])

    def test_eleccion_explicita_de_uno(self):
        r = run("04_ambiguo_varios_lotes.kmz", eleccion=[1])
        self.assertEqual(r["estado"], "listo")
        self.assertEqual(r["geometria"]["partes"], 1)

    def test_eleccion_explicita_de_todos_como_un_terreno(self):
        r = run("04_ambiguo_varios_lotes.kmz", eleccion=[0, 1, 2])
        self.assertEqual(r["geometria"]["partes"], 3)

    def test_eleccion_invalida(self):
        r = run("04_ambiguo_varios_lotes.kmz", eleccion=[7])
        self.assertEqual(r["estado"], "requiere_eleccion")
        self.assertEqual(r["error"]["codigo"], "ELECCION_INVALIDA")


class Rechazados(unittest.TestCase):
    CASOS = {
        "05_solo_puntos.kmz": "KML_SIN_POLIGONOS",
        "06_solo_lineas.kmz": "KML_SIN_POLIGONOS",
        "08_enlace_de_red.kmz": "KML_SIN_POLIGONOS",
        "09_entidades_dtd.kmz": "KML_DTD_NO_PERMITIDA",
        "11_orden_invertido.kmz": "KML_COORDENADAS_INVALIDAS",
        "12_anillo_corto.kmz": "KML_ANILLO_INVALIDO",
        "13_xml_roto.kmz": "KML_XML_INVALIDO",
        "21_kmz_varios_kml_sin_doc.kmz": "KMZ_VARIOS_KML",
        "22_kmz_sin_kml.kmz": "KMZ_SIN_KML",
        "23_kmz_expansion_excesiva.kmz": "KMZ_EXPANSION_EXCESIVA",
        "24_no_es_zip.kmz": "KMZ_NO_ES_ZIP",
        "25_overlay_sin_contorno.kmz": "KML_SIN_POLIGONOS",
    }

    def test_cada_caso_falla_con_su_codigo_y_mensaje(self):
        for nombre, codigo in self.CASOS.items():
            with self.subTest(nombre):
                r = run(nombre)
                self.assertEqual(r["estado"], "fallido")
                self.assertEqual(r["error"]["codigo"], codigo)
                self.assertTrue(r["error"]["mensaje"])

    def test_solo_puntos_dice_que_encontro(self):
        self.assertIn("Point", run("05_solo_puntos.kmz")["error"]["mensaje"])


class NoUtilizables(unittest.TestCase):
    def test_fuera_de_mexico_se_guarda_pero_no_ubica(self):
        r = run("14_fuera_de_mexico.kmz")
        self.assertEqual(r["estado"], "listo")
        self.assertFalse(r["utilizable"])
        self.assertIn("GEOMETRIA_FUERA_DE_MEXICO", codigos(r))


if __name__ == "__main__":
    unittest.main(verbosity=2)

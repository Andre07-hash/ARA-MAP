"""A bare KML document through the same reader and rules as a KMZ's KML.

Every document is a fictional fixture from tests/fixtures/kmz/ (or a small
synthetic variant). The KMZ side packages the very same bytes in memory, so
any difference between the two results is the package's own.
"""

from __future__ import annotations

import codecs
import json
import unittest
from unittest import mock

from server import kmz
from tests.test_kmz import CLAVES, FIXTURES, documento, empaquetar, kml, kmz_de

NOMBRES = sorted(p.stem for p in FIXTURES.glob("*.kml"))


class MismoResultado(unittest.TestCase):
    """procesar_kml(doc) == procesar_kmz(KMZ with doc) for every fixture."""

    def test_todas_las_fixtures_sin_seleccion(self):
        self.assertGreaterEqual(len(NOMBRES), 35)
        for nombre in NOMBRES:
            with self.subTest(nombre):
                directo = kmz.procesar_kml(kml(nombre))
                self.assertEqual(set(directo), CLAVES)
                self.assertEqual(directo, kmz.procesar_kmz(kmz_de(nombre)))
                json.dumps(directo)

    def test_selecciones_validas_e_invalidas(self):
        varios = [n for n in NOMBRES
                  if kmz.procesar_kml(kml(n))["estado"] == kmz.REQUIERE_SELECCION]
        self.assertIn("ambiguo_tres_lotes", varios)
        self.assertIn("lotes_uno_invalido", varios)
        for nombre in varios:
            for seleccion in ([0], [1], [0, 1], [0, 1, 2], [], [7], [0, 0], "0", [True]):
                with self.subTest(nombre, seleccion=seleccion):
                    self.assertEqual(kmz.procesar_kml(kml(nombre), seleccion),
                                     kmz.procesar_kmz(kmz_de(nombre), seleccion))

    def test_contorno_simple_huecos_y_varias_partes(self):
        for nombre, partes, huecos in (("poligono_simple", 1, 0), ("poligono_con_hueco", 1, 1),
                                       ("multiparte", 2, 0)):
            with self.subTest(nombre):
                r = kmz.procesar_kml(kml(nombre))
                self.assertEqual(r["estado"], kmz.LISTO)
                self.assertEqual((r["geometria"]["partes"], r["geometria"]["huecos"]),
                                 (partes, huecos))
                self.assertTrue(r["ubicacion"]["utilizable"])

    def test_varios_contornos_piden_eleccion_y_la_eleccion_une_partes(self):
        r = kmz.procesar_kml(kml("ambiguo_tres_lotes"))
        self.assertEqual((r["estado"], r["geometria"]), (kmz.REQUIERE_SELECCION, None))
        elegido = kmz.procesar_kml(kml("ambiguo_tres_lotes"), [0, 2])
        self.assertEqual(elegido["estado"], kmz.LISTO)
        self.assertEqual(elegido["seleccion"], [0, 2])
        self.assertEqual(elegido["geometria"]["partes"], 2)

    def test_solo_el_paquete_avisa_de_sus_archivos_adicionales(self):
        texto = kml("poligono_simple")
        paquete = kmz.procesar_kmz(empaquetar([("doc.kml", texto), ("files/foto.png", b"x")]))
        directo = kmz.procesar_kml(texto)
        self.assertIn("KMZ_ARCHIVOS_ADICIONALES", [a["codigo"] for a in paquete["avisos"]])
        paquete["avisos"] = [a for a in paquete["avisos"]
                             if a["codigo"] != "KMZ_ARCHIVOS_ADICIONALES"]
        self.assertEqual(directo, paquete)


class Rechazos(unittest.TestCase):
    def codigo(self, datos, seleccion=None):
        r = kmz.procesar_kml(datos, seleccion)
        self.assertEqual(set(r), CLAVES)
        self.assertEqual(r["estado"], kmz.RECHAZADO)
        self.assertIsNone(r["geometria"])
        return r["error"]["codigo"]

    def test_documentos_invalidos_e_inseguros(self):
        for nombre, codigo in (("xml_roto", "KML_XML_INVALIDO"),
                               ("entidades_dtd", "KML_DTD_NO_PERMITIDA"),
                               ("entidad_externa", "KML_DTD_NO_PERMITIDA"),
                               ("solo_puntos", "KML_SIN_CONTORNO"),
                               ("documento_vacio", "KML_SIN_CONTORNO"),
                               ("monio_autointerseccion", "GEOMETRIA_AUTOINTERSECCION")):
            with self.subTest(nombre):
                self.assertEqual(self.codigo(kml(nombre)), codigo)

    def test_enlace_externo_no_se_descarga(self):
        r = kmz.procesar_kml(kml("enlace_de_red"))
        self.assertIn("KML_ENLACE_EXTERNO", [a["codigo"] for a in r["avisos"]])

    def test_no_es_xml(self):
        self.assertEqual(self.codigo(b"%PDF-1.7 no es un mapa"), "KML_XML_INVALIDO")
        self.assertEqual(self.codigo(b""), "KML_XML_INVALIDO")

    def test_un_paquete_no_se_lee_como_kml(self):
        self.assertEqual(self.codigo(kmz_de("poligono_simple")), "KML_ES_PAQUETE")

    def test_limite_de_bytes_igual_al_del_kml_dentro_del_kmz(self):
        self.assertEqual(kmz.MAX_KML_BYTES, 16 * 1024 * 1024)
        texto = kml("poligono_simple")
        with mock.patch.object(kmz, "MAX_KML_BYTES", len(texto)):
            self.assertEqual(kmz.procesar_kml(texto)["estado"], kmz.LISTO)
        with mock.patch.object(kmz, "MAX_KML_BYTES", len(texto) - 1):
            self.assertEqual(self.codigo(texto), "KML_DEMASIADO_GRANDE")
            # The same document inside a KMZ meets the same limit.
            self.assertEqual(kmz.procesar_kmz(kmz_de("poligono_simple"))["error"]["codigo"],
                             "KML_DEMASIADO_GRANDE")

    def test_limites_de_lectura_compartidos(self):
        hondo = documento("<Folder>" * (kmz.MAX_PROFUNDIDAD + 1)
                          + "</Folder>" * (kmz.MAX_PROFUNDIDAD + 1))
        self.assertEqual(self.codigo(hondo), "KML_DEMASIADO_ANIDADO")
        with mock.patch.object(kmz, "MAX_ELEMENTOS", 10):
            self.assertEqual(self.codigo(kml("ambiguo_tres_lotes")), "KML_DEMASIADOS_ELEMENTOS")
        with mock.patch.object(kmz, "MAX_VERTICES", 4):
            self.assertEqual(self.codigo(kml("poligono_simple")), "KML_DEMASIADOS_VERTICES")


class Codificaciones(unittest.TestCase):
    def nombre(self, datos):
        r = kmz.procesar_kml(datos)
        self.assertEqual(r["estado"], kmz.LISTO, r["error"])
        self.assertEqual(r, kmz.procesar_kmz(empaquetar([("doc.kml", datos)])))
        return r["candidatos"][0]["nombre"]

    def texto(self):
        return kml("poligono_simple").decode().replace("Predio Ficticio Uno", "Predio Ñandú Año")

    def test_utf8_con_y_sin_bom_y_sin_declaracion(self):
        t = self.texto()
        sin_declaracion = t.split("?>", 1)[1].lstrip()
        for datos in (t.encode(), codecs.BOM_UTF8 + t.encode(), sin_declaracion.encode()):
            with self.subTest(datos[:12]):
                self.assertEqual(self.nombre(datos), "Predio Ñandú Año")

    def test_utf16_con_bom(self):
        t = self.texto().replace("UTF-8", "UTF-16")
        for codec, bom in (("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE)):
            with self.subTest(codec):
                self.assertEqual(self.nombre(bom + t.encode(codec)), "Predio Ñandú Año")

    def test_latin1_y_windows_1252_declaradas(self):
        for codificacion in ("ISO-8859-1", "windows-1252"):
            with self.subTest(codificacion):
                t = self.texto().replace("UTF-8", codificacion)
                self.assertEqual(self.nombre(t.encode("cp1252")), "Predio Ñandú Año")

    def test_codificacion_desconocida(self):
        datos = kml("poligono_simple").replace(b'encoding="UTF-8"', b'encoding="UTF-Y"')
        self.assertEqual(kmz.procesar_kml(datos)["error"]["codigo"],
                         "KML_CODIFICACION_NO_SOPORTADA")


class Despacho(unittest.TestCase):
    def test_procesar_contorno_decide_por_el_contenido(self):
        texto = kml("poligono_simple")
        self.assertEqual(kmz.procesar_contorno(texto), kmz.procesar_kml(texto))
        self.assertEqual(kmz.procesar_contorno(kmz_de("poligono_simple")),
                         kmz.procesar_kmz(kmz_de("poligono_simple")))
        # A KMZ entry point keeps refusing a bare document, as before.
        self.assertEqual(kmz.procesar_kmz(texto)["error"]["codigo"], "KMZ_NO_ES_ZIP")


if __name__ == "__main__":
    unittest.main()

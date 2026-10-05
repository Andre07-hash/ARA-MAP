"""Which rows are terrains: summaries, footers, and the user's own decision.

Fictional data only. A name is never enough to delete a record: «Total
FICTICIO Encino» is a terrain, and a real summary is recognized by having no
location and by adding the other rows up.
"""

from __future__ import annotations

import unittest

from server import db
from server.asistente.plan import ImportPlan, PlanError, construir, validar
from server.asistente.rejilla import leer
from server.web_util import ApiError
from tests.test_asistente_api import AsistenteCase

CABECERA = "Terreno,Precio,Superficie m2,Latitud,Longitud"
TERRENOS = [
    "FICTICIO Encino,1200000,2400,19.4326,-99.1332",
    "FICTICIO Roble,2500000,5000,20.6736,-103.344",
    "FICTICIO Cedro,3750000,7500,25.6866,-100.3161",
    "FICTICIO Fresno,4800000,9600,20.5888,-100.3899",
]
SUMA = "12250000,24500"     # the four prices and the four areas


def csv(*filas, cabecera=CABECERA):
    return ("\n".join([cabecera, *filas]) + "\n").encode()


def base():
    return csv(*TERRENOS)


class Clasificacion(AsistenteCase):
    """What the preview keeps and what it sets aside, with its reason."""

    def vista(self, contenido, nombre="filas.csv"):
        respuesta = self.analizar(nombre, contenido)
        self.assertEqual(respuesta["estado"], "vista_previa", respuesta.get("error"))
        return respuesta["vista_previa"]

    def nombres(self, vista):
        return [f["terreno"] for f in vista["filas"]]

    def test_a_terrain_whose_name_starts_with_total_is_imported(self):
        vista = self.vista(csv(f"Total {TERRENOS[0]}", *TERRENOS[1:]))
        self.assertIn("Total FICTICIO Encino", self.nombres(vista))
        self.assertEqual((vista["conteo"], vista["excluidas"]), (4, []))

    def test_total_and_subtotal_alone_can_be_terrain_names(self):
        for nombre in ("Total", "Subtotal", "Total general"):
            with self.subTest(nombre=nombre):
                vista = self.vista(csv(f"{nombre},1200000,2400,19.4326,-99.1332", *TERRENOS[1:]))
                self.assertIn(nombre, self.nombres(vista))
                self.assertEqual(vista["excluidas"], [])

    def test_a_real_summary_row_is_excluded_because_its_figures_add_up(self):
        vista = self.vista(csv(*TERRENOS, f"TOTAL,{SUMA},,"))
        self.assertEqual(self.nombres(vista), [t.split(",")[0] for t in TERRENOS])
        excluida = vista["excluidas"][0]
        self.assertEqual((excluida["motivo"], excluida["fila"], excluida["indice"]), ("TOTALES", 6, 5))
        self.assertIn("suma de las demás filas", excluida["resumen"])

    def test_a_named_summary_without_any_terrain_data_is_excluded_too(self):
        vista = self.vista(csv(*TERRENOS, "TOTAL,999,111,,"))
        self.assertEqual(vista["conteo"], 4)
        self.assertIn("no tiene ubicación", vista["excluidas"][0]["resumen"])

    def test_a_totals_like_name_with_figures_that_do_not_add_up_is_kept(self):
        """Erring towards keeping a record: the exclusion would be the damage."""
        vista = self.vista(csv(*TERRENOS, "Total de la zona norte,999,111,,"))
        self.assertIn("Total de la zona norte", self.nombres(vista))
        self.assertEqual(vista["excluidas"], [])

    def test_a_totals_like_name_whose_figures_do_add_up_is_excluded(self):
        vista = self.vista(csv(*TERRENOS, f"Total de la zona norte,{SUMA},,"))
        self.assertEqual(vista["conteo"], 4)
        self.assertEqual(vista["excluidas"][0]["motivo"], "TOTALES")

    def test_a_summary_row_that_has_a_municipality_is_treated_as_a_terrain(self):
        vista = self.vista(csv(f"TOTAL,Jalisco,{SUMA}", *[f"{t.split(',')[0]},Jalisco,{t.split(',')[1]},{t.split(',')[2]}"
                                                          for t in TERRENOS],
                               cabecera="Terreno,Estado,Precio,Superficie m2"))
        self.assertIn("TOTAL", self.nombres(vista))

    def test_a_footer_note_is_set_aside_with_a_reason(self):
        vista = self.vista(csv(*TERRENOS, "NOTA: valores sujetos a revisión,,,,"))
        self.assertEqual(vista["conteo"], 4)
        excluida = vista["excluidas"][0]
        self.assertEqual((excluida["motivo"], excluida["indice"]), ("NOTA", 5))
        self.assertIn("lo único escrito en la fila", excluida["resumen"])

    def test_a_note_word_with_real_data_beside_it_is_a_terrain(self):
        vista = self.vista(csv(*TERRENOS, "Nota Verde,900000,1800,19.1,-99.1"))
        self.assertIn("Nota Verde", self.nombres(vista))
        self.assertEqual(vista["excluidas"], [])

    def test_a_terrain_with_nothing_but_a_name_is_still_imported(self):
        vista = self.vista(csv(*TERRENOS, "FICTICIO Sauce,,,,"))
        self.assertIn("FICTICIO Sauce", self.nombres(vista))
        self.assertEqual(vista["excluidas"], [])

    def test_a_repeated_header_row_is_still_excluded(self):
        vista = self.vista(csv(TERRENOS[0], CABECERA, *TERRENOS[1:]))
        self.assertEqual(vista["conteo"], 4)
        self.assertEqual(vista["excluidas"][0]["motivo"], "ENCABEZADO_REPETIDO")


class Decisiones(AsistenteCase):
    """The manager's own include/exclude decisions, all the way to storage."""

    def guardados(self):
        with db.session() as conn:
            return [f["terreno"] for f in conn.execute("SELECT terreno FROM terreno ORDER BY id").fetchall()]

    def test_an_excluded_footer_can_be_restored_and_is_then_imported(self):
        r = self.analizar("nota.csv", csv(*TERRENOS, "NOTA: valores sujetos a revisión,,,,"))
        indice = r["vista_previa"]["excluidas"][0]["indice"]
        restaurada = self.preparar(r, correcciones={"incluir": [indice]})
        self.assertEqual(restaurada["vista_previa"]["conteo"], 5)
        self.assertEqual(restaurada["interpretacion"]["incluir"], [indice])
        self.assertEqual(self.confirmar(restaurada, recordar_formato=False)["base"]["conteo"], 5)
        self.assertIn("NOTA: valores sujetos a revisión", self.guardados())

    def test_a_restored_row_survives_a_later_correction(self):
        r = self.analizar("nota.csv", csv(*TERRENOS, "NOTA: valores sujetos a revisión,,,,"))
        indice = r["vista_previa"]["excluidas"][0]["indice"]
        restaurada = self.preparar(r, correcciones={"incluir": [indice]})
        despues = self.preparar(restaurada, correcciones={"decimal": "comma"})
        self.assertEqual(despues["vista_previa"]["conteo"], 5)
        self.assertEqual(despues["interpretacion"]["incluir"], [indice])

    def test_a_row_can_be_removed_from_the_preview_by_its_own_number(self):
        r = self.analizar("base.csv", base())
        fila = r["vista_previa"]["filas"][1]
        self.assertEqual((fila["fila"], fila["indice"]), (3, 2))
        quitada = self.preparar(r, correcciones={"excluir": [fila["indice"]]})
        self.assertEqual(quitada["vista_previa"]["conteo"], 3)
        self.assertEqual(quitada["vista_previa"]["excluidas"][0]["motivo"], "EXCLUIDA")
        self.confirmar(quitada, recordar_formato=False)
        self.assertNotIn("FICTICIO Roble", self.guardados())

    def test_naming_a_row_on_one_list_takes_it_off_the_other(self):
        r = self.analizar("base.csv", base())
        indice = r["vista_previa"]["filas"][0]["indice"]
        quitada = self.preparar(r, correcciones={"excluir": [indice]})
        self.assertEqual(quitada["interpretacion"]["excluir"], [indice])
        devuelta = self.preparar(quitada, correcciones={"incluir": [indice]})
        self.assertEqual(devuelta["interpretacion"]["excluir"], [])
        self.assertEqual(devuelta["vista_previa"]["conteo"], 4)

    def test_only_data_rows_can_be_named(self):
        for correccion in ({"excluir": [0]}, {"incluir": [0]}, {"excluir": [99]}):
            with self.subTest(correccion=correccion):
                r = self.analizar("base.csv", base())
                self.assertIn("filas de datos", self.preparar(r, correcciones=correccion)["error"])

    def test_a_row_cannot_be_included_and_excluded_at_once(self):
        rejilla = leer(base(), "base.csv")
        plan = ImportPlan(sha256=rejilla.sha256, hoja_id="csv:,", encabezado=0, decimal="dot",
                          asignaciones={"csv:,/column:0": "terreno"}, excluir=(2,), incluir=(2,))
        with self.assertRaisesRegex(PlanError, "incluida y excluida"):
            validar(plan, rejilla)

    def test_a_malformed_row_list_is_refused(self):
        r = self.analizar("base.csv", base())
        with self.assertRaises(ApiError):
            self.preparar(r, correcciones={"incluir": ["dos"]})

    def test_the_plan_carries_the_decision(self):
        rejilla = leer(csv(*TERRENOS, f"TOTAL,{SUMA},,"), "base.csv")
        asignaciones = {f"csv:,/column:{i}": d for i, d in enumerate(
            ("terreno", "asking_price", "superficie_m2", "lat", "lon"))}
        plan = ImportPlan(sha256=rejilla.sha256, hoja_id="csv:,", encabezado=0, decimal="dot",
                          asignaciones=asignaciones, moneda="MXN")
        self.assertEqual(len(construir(plan, rejilla).resultado.records), 4)
        con_total = ImportPlan(**{**plan.to_dict(), "asignaciones": asignaciones, "incluir": (5,)})
        self.assertEqual(len(construir(con_total, rejilla).resultado.records), 5)


if __name__ == "__main__":
    unittest.main()

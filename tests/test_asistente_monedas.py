"""Currency evidence: Excel number formats are read, kept and obeyed.

Fictional data only. A price column formatted in dollars must reach the map
as dollars -- never as pesos -- in the preview and in what is stored; a bare
amount's currency is asked, never guessed; and the evidence has to survive
the packed draft that carries a file between requests.
"""

from __future__ import annotations

import io
import unittest

from openpyxl import Workbook

from server import db
from server.asistente.campos import moneda_formato, nombre_moneda
from server.asistente.detectar import interpretar
from server.asistente.perfil import perfilar
from server.asistente.plan import PlanError, construir
from server.asistente.rejilla import Hoja, leer
from tests.test_asistente_api import AsistenteCase

FILAS = [
    ("Terreno", "Precio", "Superficie m2", "Latitud", "Longitud"),
    ("FICTICIO Encino", 1200000, 2400, 19.4326, -99.1332),
    ("FICTICIO Roble", 2500000, 5000, 20.6736, -103.344),
    ("FICTICIO Cedro", 3750000, 7500, 25.6866, -100.3161),
    ("FICTICIO Fresno", 4800000, 9600, 20.5888, -100.3899),
]
PRECIOS = ("B2", "B3", "B4", "B5")


def libro(filas=FILAS, formatos=None, hoja="Terrenos"):
    """A workbook in memory, with a number format on the named cells."""
    wb = Workbook()
    wb.active.title = hoja
    for fila in filas:
        wb.active.append(fila)
    for celda, formato in (formatos or {}).items():
        wb.active[celda].number_format = formato
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def en_dolares(formato='"USD "#,##0.00'):
    return libro(formatos=dict.fromkeys(PRECIOS, formato))


class Formatos(unittest.TestCase):
    """What a number format does and does not declare."""

    def test_quoted_codes_and_locale_sections_declare_a_currency(self):
        self.assertEqual(moneda_formato('"USD "#,##0.00'), "USD")
        self.assertEqual(moneda_formato('#,##0.00" EUR"'), "EUR")
        self.assertEqual(moneda_formato("[$€-2]#,##0.00"), "EUR")
        self.assertEqual(moneda_formato('[$-409]#,##0.00;[RED]-"USD "#,##0.00'), "USD")

    def test_the_numeric_pattern_itself_declares_nothing(self):
        for formato in ("General", "#,##0.00", "0.00%", "dd/mm/yyyy", "0.00E+00", '0.00" ha"', ""):
            self.assertIsNone(moneda_formato(formato), formato)

    def test_a_bare_dollar_sign_declares_no_currency(self):
        # "$" is written for dollars and pesos alike, with or without a locale.
        for formato in ("$#,##0.00", r"\$#,##0", "[$$-409]#,##0.00", "[$$-80A]#,##0.00", '"$"#,##0'):
            self.assertIsNone(moneda_formato(formato), formato)

    def test_an_explicit_peso_code_declares_pesos(self):
        self.assertEqual(moneda_formato('"MXN "#,##0.00'), "MXN")

    def test_currencies_are_named_for_the_user(self):
        self.assertEqual(nombre_moneda(("USD",)), "dólares (USD)")
        self.assertEqual(nombre_moneda(("MXN",)), "pesos (MXN)")
        self.assertEqual(nombre_moneda(("EUR",)), "EUR")
        self.assertEqual(nombre_moneda(("USD", "EUR")), "USD y EUR")
        self.assertEqual(nombre_moneda(()), "")


class Rejilla(unittest.TestCase):
    """The grid keeps the evidence, and the packed draft carries it along."""

    def test_the_grid_records_which_cells_are_in_a_foreign_currency(self):
        hoja = leer(en_dolares(), "x.xlsx").hojas[0]
        self.assertEqual(hoja.monedas, tuple((f, 1, "USD") for f in (1, 2, 3, 4)))
        self.assertEqual(hoja.monedas_de(1, [1, 2, 3, 4]), ("USD",))
        self.assertEqual(hoja.monedas_de(0, [1, 2, 3, 4]), ())

    def test_only_the_rows_asked_about_count(self):
        hoja = leer(libro(formatos={"B2": '"USD "#,##0.00'}), "x.xlsx").hojas[0]
        self.assertEqual(hoja.monedas_de(1, [1]), ("USD",))
        self.assertEqual(hoja.monedas_de(1, [2, 3, 4]), ())

    def test_an_empty_cell_formatted_in_dollars_is_not_evidence(self):
        filas = [FILAS[0], ("FICTICIO Encino", None, 2400, 19.4326, -99.1332)]
        hoja = leer(libro(filas, {"B2": '"USD "#,##0.00'}), "x.xlsx").hojas[0]
        self.assertEqual(hoja.monedas, ())

    def test_a_column_whose_evidence_was_truncated_carries_it_throughout(self):
        hoja = Hoja(id="sheet:0", nombre="H", filas=(), lineas=(), monedas_truncadas=((1, "USD"),))
        self.assertEqual(hoja.monedas_de(1, []), ("USD",))

    def test_the_packed_draft_keeps_the_currency_of_every_cell(self):
        original = leer(en_dolares(), "x.xlsx")
        vuelta = type(original).desempaquetar(original.empaquetar())
        self.assertEqual(vuelta.hojas[0].monedas, original.hojas[0].monedas)
        self.assertEqual(vuelta, original)

    def test_an_older_draft_without_the_field_still_unpacks(self):
        import base64
        import json
        import zlib
        crudo = {"formato": "csv", "archivo": "x.csv", "sha256": "a", "version": 1,
                 "hojas": [{"id": "csv:,", "nombre": "CSV", "filas": [["Terreno"], ["Norte"]],
                            "lineas": [1, 2], "separador": ",", "formulas_sin_valor": []}]}
        texto = base64.b64encode(zlib.compress(json.dumps(crudo).encode())).decode()
        self.assertEqual(type(leer(b"Terreno\nNorte\n", "x.csv")).desempaquetar(texto).hojas[0].monedas, ())


class Columnas(unittest.TestCase):
    """The profile sees the evidence, whatever wrote it."""

    def perfil(self, contenido):
        rejilla = leer(contenido, "x.xlsx")
        return {c.etiqueta: c for c in perfilar(rejilla.hojas[0], 0)}

    def test_a_dollar_formatted_column_profiles_as_usd(self):
        columna = self.perfil(en_dolares())["Precio"]
        self.assertEqual(columna.monedas, ("USD",))
        self.assertEqual(columna.monedas_formato, ("USD",))
        self.assertEqual(columna.moneda, "USD")

    def test_a_euro_formatted_column_profiles_as_eur(self):
        self.assertEqual(self.perfil(en_dolares("[$€-2]#,##0.00"))["Precio"].monedas, ("EUR",))

    def test_one_foreign_cell_among_pesos_is_enough(self):
        columna = self.perfil(libro(formatos={"B4": '"USD "#,##0.00'}))["Precio"]
        self.assertEqual(columna.monedas, ("USD",))

    def test_a_column_mixing_two_currencies_names_both(self):
        columna = self.perfil(libro(formatos={"B2": '"USD "#,##0.00',
                                              "B4": "[$€-2]#,##0.00"}))["Precio"]
        self.assertEqual(set(columna.monedas), {"USD", "EUR"})

    def test_bare_formats_declare_nothing_and_peso_codes_declare_mxn(self):
        for formato in ("$#,##0.00", "[$$-409]#,##0.00", "#,##0.00"):
            self.assertEqual(self.perfil(libro(formatos=dict.fromkeys(PRECIOS, formato)))["Precio"].monedas,
                             (), formato)
        self.assertEqual(self.perfil(libro(formatos=dict.fromkeys(PRECIOS, '"MXN "#,##0.00')))["Precio"].monedas,
                         ("MXN",))

    def test_the_text_of_a_column_is_still_read_too(self):
        filas = [FILAS[0], ("FICTICIO Encino", "USD 1,200,000", 2400, 19.4326, -99.1332)]
        self.assertEqual(self.perfil(libro(filas))["Precio"].monedas, ("USD",))


class Importacion(AsistenteCase):
    """Preview and stored records, through the real handlers.

    Prices are stored in USD or MXN with that currency, never converted. A bare
    amount's currency is asked; an explicit marker decides it; anything else
    stays additional data.
    """

    moneda = None   # these tests answer the currency question themselves

    def precios_guardados(self):
        with db.session() as conn:
            return [(f["asking_price"], f["moneda"]) for f in
                    conn.execute("SELECT asking_price, moneda FROM terreno ORDER BY orden").fetchall()]

    def responder_moneda(self, r, codigo):
        pregunta = next(p for p in r["preguntas"] if p["id"] == "moneda")
        opcion = next(o["indice"] for o in pregunta["opciones"] if f"({codigo})" in o["etiqueta"])
        return self.preparar(r, [{"pregunta": "moneda", "opcion": opcion}])

    def test_a_dollar_formatted_price_is_stored_in_dollars(self):
        r = self.analizar("dolares-formato.xlsx", en_dolares())
        self.assertEqual(r["estado"], "vista_previa")
        vista = r["vista_previa"]
        self.assertEqual((vista["conteo"], vista["con_precio"], vista["moneda"]), (4, 4, "USD"))
        self.assertEqual(vista["moneda_origen"], "archivo")
        self.assertEqual({f["moneda"] for f in vista["filas"]}, {"USD"})
        self.assertEqual(vista["monedas_no_admitidas"], [])
        self.confirmar(r, recordar_formato=False)
        self.assertEqual(self.precios_guardados(),
                         [(1200000.0, "USD"), (2500000.0, "USD"), (3750000.0, "USD"), (4800000.0, "USD")])

    def test_unmarked_prices_are_asked_never_guessed(self):
        for formato in ("$#,##0.00", "[$$-409]#,##0.00", "#,##0.00"):
            with self.subTest(formato=formato):
                r = self.analizar("sin-marca.xlsx", libro(formatos=dict.fromkeys(PRECIOS, formato)))
                self.assertEqual(r["estado"], "preguntas")
                self.assertEqual([p["id"] for p in r["preguntas"]], ["moneda"])
                self.assertIsNone(r["preguntas"][0]["sugerida"])
                self.assertNotIn("vista_previa", r)

    def test_the_answer_is_the_currency_stored(self):
        for codigo in ("USD", "MXN"):
            with self.subTest(codigo=codigo):
                r = self.responder_moneda(self.analizar("sin-marca.xlsx", libro()), codigo)
                self.assertEqual((r["vista_previa"]["moneda"], r["vista_previa"]["moneda_origen"]),
                                 (codigo, "usuario"))
                self.confirmar(r, recordar_formato=False)
                self.assertEqual({m for _, m in self.precios_guardados()}, {codigo})
                with db.session() as conn:
                    conn.execute("DELETE FROM terreno")
                    conn.execute("DELETE FROM base")

    def test_not_importing_prices_is_an_answer_too(self):
        r = self.analizar("sin-marca.xlsx", libro())
        pregunta = r["preguntas"][0]
        opcion = next(o["indice"] for o in pregunta["opciones"] if o["etiqueta"].startswith("No importar"))
        r = self.preparar(r, [{"pregunta": "moneda", "opcion": opcion}])
        self.assertEqual((r["vista_previa"]["con_precio"], r["vista_previa"]["moneda"]), (0, None))

    def test_peso_markers_import_as_pesos_without_a_question(self):
        r = self.analizar("pesos.xlsx", libro(formatos=dict.fromkeys(PRECIOS, '"MXN "#,##0.00')))
        self.assertEqual((r["vista_previa"]["moneda"], r["vista_previa"]["con_precio"]), ("MXN", 4))

    def test_a_euro_price_is_kept_as_additional_data_and_explained(self):
        r = self.analizar("euros.xlsx", en_dolares("[$€-2]#,##0.00"))
        columna = next(c for c in r["interpretacion"]["columnas"] if c["etiqueta"] == "Precio")
        self.assertEqual((columna["destino"], columna["monedas"]), ("extra", ["EUR"]))
        self.assertIn("formato de celda de Excel", columna["motivo"])
        self.assertTrue(any("USD o MXN" in a for a in r["interpretacion"]["avisos"]))
        vista = r["vista_previa"]
        self.assertEqual(vista["con_precio"], 0)
        self.assertEqual(vista["monedas_no_admitidas"][0]["monedas"], ["EUR"])
        self.assertIn({"columna": "Precio", "valor": "1200000"}, vista["filas"][0]["originales"])

    def test_one_marked_cell_decides_the_whole_column(self):
        r = self.analizar("mixta.xlsx", libro(formatos={"B4": '"USD "#,##0.00'}))
        self.assertEqual((r["vista_previa"]["moneda"], r["vista_previa"]["con_precio"]), ("USD", 4))

    def test_a_column_in_two_currencies_names_both_and_is_not_a_price(self):
        for formatos in ({"B2": '"USD "#,##0.00', "B4": "[$€-2]#,##0.00"},
                         {"B2": '"USD "#,##0.00', "B4": '"MXN "#,##0.00'}):
            with self.subTest(formatos=formatos):
                r = self.analizar("dos.xlsx", libro(formatos=formatos))
                self.assertEqual(r["vista_previa"]["con_precio"], 0)
                self.assertEqual(len(r["vista_previa"]["monedas_no_admitidas"][0]["monedas"]), 2)

    def test_an_explicit_choice_cannot_relabel_a_euro_column_as_a_price(self):
        r = self.analizar("euros.xlsx", en_dolares("[$€-2]#,##0.00"))
        columna = next(c for c in r["interpretacion"]["columnas"] if c["etiqueta"] == "Precio")["id"]
        respuesta = self.preparar(r, correcciones={"columnas": {columna: "asking_price"}})
        self.assertNotIn("vista_previa", respuesta)

    def test_the_evidence_survives_a_later_correction_on_the_draft(self):
        r = self.analizar("dolares-formato.xlsx", en_dolares())
        siguiente = self.preparar(r, correcciones={"decimal": "comma"})
        self.assertEqual(siguiente["vista_previa"]["moneda"], "USD")
        self.confirmar(siguiente, recordar_formato=False)
        self.assertEqual({m for _, m in self.precios_guardados()}, {"USD"})

    def test_a_correction_cannot_contradict_the_file(self):
        r = self.analizar("dolares-formato.xlsx", en_dolares())
        siguiente = self.preparar(r, correcciones={"moneda": "MXN"})
        self.assertEqual(siguiente["vista_previa"]["moneda"], "USD")
        self.assertTrue(any("respeta lo que dice el archivo" in a for a in siguiente["interpretacion"]["avisos"]))

    def test_a_remembered_currency_is_reused_but_never_over_the_file(self):
        primero = self.responder_moneda(self.analizar("pesos.xlsx", libro()), "MXN")
        self.confirmar(primero, recordar_formato=True)
        igual = self.analizar("pesos-2.xlsx", libro(FILAS[:3]))
        self.assertEqual((igual["vista_previa"]["moneda"], igual["vista_previa"]["moneda_origen"]),
                         ("MXN", "formato"))
        dolares = self.analizar("dolares-formato.xlsx", en_dolares())
        self.assertEqual((dolares["vista_previa"]["moneda"], dolares["vista_previa"]["moneda_origen"]),
                         ("USD", "archivo"))

    def test_a_currency_exclusion_is_not_remembered_as_a_choice(self):
        r = self.analizar("euros.xlsx", en_dolares("[$€-2]#,##0.00"))
        self.confirmar(r, recordar_formato=True)
        with db.session() as conn:
            config = conn.execute("SELECT config_json FROM formato_importacion").fetchone()["config_json"]
        self.assertNotIn('"precio"', config)
        siguiente = self.analizar("dolares-formato.xlsx", en_dolares())
        self.assertEqual((siguiente["vista_previa"]["moneda"], siguiente["vista_previa"]["con_precio"]), ("USD", 4))

    def test_the_plan_refuses_the_relabelling_even_without_the_service(self):
        from server.asistente.plan import ImportPlan
        rejilla = leer(en_dolares(), "x.xlsx")
        interp = interpretar(rejilla, {})
        columna = next(c for c in interp.columnas if c.etiqueta == "Precio")
        for moneda in ("MXN", None):
            plan = ImportPlan(sha256=rejilla.sha256, hoja_id=interp.hoja.id, encabezado=0, decimal="dot",
                              asignaciones={**interp.asignaciones, columna.id: "asking_price"}, moneda=moneda)
            with self.subTest(moneda=moneda), self.assertRaises(PlanError):
                construir(plan, rejilla)

    def test_a_moneda_column_is_evidence_and_is_checked_row_by_row(self):
        filas = [(*FILAS[0], "Moneda"), *((*f, "USD") for f in FILAS[1:])]
        r = self.analizar("con-moneda.xlsx", libro(filas))
        self.assertEqual((r["vista_previa"]["moneda"], r["vista_previa"]["con_precio"]), ("USD", 4))
        mezclada = [*filas[:-1], (*FILAS[-1], "MXN")]
        r = self.analizar("con-moneda.xlsx", libro(mezclada))
        self.assertEqual(r["vista_previa"]["con_precio"], 0)
        self.assertTrue(any("mezclan" in a for a in r["interpretacion"]["avisos"]))
        rara = [*filas[:-1], (*FILAS[-1], "sin confirmar")]
        r = self.analizar("con-moneda.xlsx", libro(rara))
        self.assertIn("sin confirmar", r["error"])


class FormatoAnterior(AsistenteCase):
    """A format saved when dollars were refused must not keep hiding prices."""

    moneda = None

    def formato_anterior(self, destino_precio="extra"):
        return {"id": 99, "nombre": "Formato de «viejo»", "version": 1, "decimal": "dot", "hoja": "CSV",
                "asignaciones": [["terreno", 1, "terreno"], ["precio", 1, destino_precio],
                                 ["superficie m2", 1, "superficie_m2"], ["latitud", 1, "lat"],
                                 ["longitud", 1, "lon"]]}

    def test_its_price_exclusion_is_asked_again_not_applied(self):
        rejilla = leer(libro(), "x.xlsx")
        interp = interpretar(rejilla, {}, [self.formato_anterior()])
        ids = [p.id for p in interp.preguntas]
        self.assertIn("moneda", ids)
        pregunta = next(p for p in interp.preguntas if p.id.startswith("columna:"))
        self.assertIn("dato adicional", pregunta.detalle)
        self.assertIsNone(interp.plan())

    def test_answering_restores_the_price(self):
        rejilla = leer(libro(), "x.xlsx")
        columna = next(c for c in interpretar(rejilla, {}).columnas if c.etiqueta == "Precio").id
        interp = interpretar(rejilla, {"columnas": {columna: "asking_price"}, "moneda": "USD"},
                             [self.formato_anterior()])
        plan = interp.plan()
        self.assertIsNotNone(plan)
        self.assertEqual(sum(r.asking_price is not None for r in construir(plan, rejilla).resultado.records), 4)

    def test_a_current_format_keeps_a_deliberate_exclusion(self):
        actual = {**self.formato_anterior(), "moneda": None}
        interp = interpretar(leer(libro(), "x.xlsx"), {}, [actual])
        self.assertEqual(interp.preguntas, ())
        self.assertNotIn("asking_price", interp.asignaciones.values())


class Agregar(AsistenteCase):
    """600 USD and 600 MXN are different prices, never a duplicate."""

    moneda = None

    def test_the_same_amount_in_another_currency_is_a_conflict(self):
        r = self.analizar("pesos.xlsx", libro(formatos=dict.fromkeys(PRECIOS, '"MXN "#,##0.00')))
        base_id = self.confirmar(r, recordar_formato=False)["base"]["id"]
        r = self.analizar("dolares-formato.xlsx", en_dolares(), base_id=base_id)
        clasificacion = r["vista_previa"]["clasificacion"]
        self.assertEqual((clasificacion["duplicadas"], clasificacion["conflictos"]), (0, 4))
        self.assertEqual({d["campo"] for c in clasificacion["detalle"] for d in c["diferencias"]}, {"moneda"})


if __name__ == "__main__":
    unittest.main()

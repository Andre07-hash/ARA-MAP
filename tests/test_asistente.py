"""Import assistant: structure, detection, questions and plans. Fictional data."""

from __future__ import annotations

import io
import unittest
from dataclasses import replace
from pathlib import Path

from openpyxl import Workbook

from server.asistente import rejilla as R  # noqa: N812 - short alias for a vocabulary module
from server.asistente.detectar import fusionar, interpretar
from server.asistente.perfil import perfilar
from server.asistente.plan import ImportPlan, PlanError, construir
from server.csv_importer import read_csv_bytes
from server.importer import read_workbook
from tests.support import FIXTURE

A = Path(__file__).parent / "fixtures" / "asistente"
TEMPLATE_CSV = Path(__file__).parents[1] / "web" / "assets" / "plantilla-terrenos.csv"
# The fictional fixtures write bare amounts that were always meant as pesos;
# their currency is answered up front, like a user would.
MXN = {"moneda": "MXN"}


def cargar(nombre: str) -> R.Rejilla:
    return R.leer((A / nombre).read_bytes(), nombre)


def por_etiqueta(interp):
    return {c.visible: interp.asignaciones[c.id] for c in interp.columnas}


def responder(rejilla, interp, decisiones, pregunta_id, opcion):
    pregunta = next(p for p in interp.preguntas if p.id == pregunta_id)
    decisiones = fusionar(decisiones, pregunta.opciones[opcion].decision)
    return decisiones, interpretar(rejilla, decisiones)


def libro_bytes(hojas):
    wb = Workbook()
    wb.remove(wb.active)
    for titulo, filas in hojas:
        hoja = wb.create_sheet(titulo)
        for fila in filas:
            hoja.append(fila)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class Estructura(unittest.TestCase):
    def test_unknown_headers_reach_mapping_instead_of_failing(self):
        rejilla = R.leer(b"Alpha,Beta\nuno,2\n", "x.csv")
        self.assertEqual(len(rejilla.hojas), 1)
        self.assertEqual(rejilla.hojas[0].filas, (("Alpha", "Beta"), ("uno", "2")))

    def test_semicolon_is_chosen_by_shape_not_by_names(self):
        rejilla = R.leer(b"Uno;Dos;Tres\na;1,5;x\nb;2,5;y\n", "x.csv")
        self.assertEqual([h.id for h in rejilla.hojas], ["csv:;"])

    def test_two_consistent_readings_are_both_offered(self):
        rejilla = R.leer(b"a,b;c,d\n1,2;3,4\n", "x.csv")
        self.assertEqual({h.id for h in rejilla.hojas}, {"csv:,", "csv:;"})

    def test_sep_directive_and_physical_lines_survive(self):
        rejilla = R.leer(b'sep=;\n\nNombre;Nota\n"A";"dos\nlineas"\nB;x\n', "x.csv")
        hoja = rejilla.hojas[0]
        self.assertEqual(hoja.lineas, (3, 4, 6))
        self.assertEqual(hoja.filas[1][1], "dos\nlineas")

    def test_structural_errors_stay_errors(self):
        for contenido, nombre, fragmento in (
            (b'A,B\n"x,1\n', "x.csv", "comilla"),
            ("A\ncafé\n".encode("cp1252"), "x.csv", "UTF-8"),
            (b"PK\x03\x04zip", "x.csv", "libro de Excel"),
            (b"no soy excel", "x.xlsx", "Excel"),
            (b"x", "x.numbers", "Formato no admitido"),
        ):
            with self.subTest(nombre=nombre), self.assertRaises(R.EstructuraError) as caught:
                R.leer(contenido, nombre)
            self.assertIn(fragmento, str(caught.exception))

    def test_excel_keeps_types_rows_and_sheets(self):
        rejilla = R.leer(libro_bytes([("Vacía", []), ("Datos", [["T", "N"], [None], ["a", 12.5]])]), "x.xlsx")
        self.assertEqual([h.nombre for h in rejilla.hojas], ["Datos"])
        self.assertEqual(rejilla.hojas[0].filas, (("T", "N"), ("a", 12.5)))
        self.assertEqual(rejilla.hojas[0].lineas, (1, 3))

    def test_formula_without_cached_result_is_reported(self):
        rejilla = cargar("formula_sin_valor.xlsx")
        self.assertEqual(rejilla.hojas[0].formulas_sin_valor, ("D2",))

    def test_bounds(self):
        filas = "\n".join(f"a{i}" for i in range(12)).encode()
        original = R.MAX_FILAS
        R.MAX_FILAS = 10
        try:
            with self.assertRaises(R.EstructuraError):
                R.leer(b"T\n" + filas, "x.csv")
        finally:
            R.MAX_FILAS = original

    def test_packed_grid_is_lossless(self):
        rejilla = cargar("desconocido_titulos.xlsx")
        self.assertEqual(R.Rejilla.desempaquetar(rejilla.empaquetar()), rejilla)


class PosicionesYDuplicados(unittest.TestCase):
    def test_duplicate_and_blank_headings_stay_separate(self):
        rejilla = cargar("duplicados.xlsx")
        columnas = perfilar(rejilla.hojas[0], 0)
        self.assertEqual([c.visible for c in columnas],
                         ["Terreno", "Precio (1)", "Precio (2)", "(sin encabezado, columna D)", "Estado"])
        self.assertEqual(len({c.id for c in columnas}), 5)
        self.assertEqual(columnas[2].muestras[:2], ("500", "450"))  # not overwritten by the first "Precio"

    def test_two_candidate_price_columns_need_an_explicit_choice(self):
        rejilla = cargar("duplicados.xlsx")
        interp = interpretar(rejilla, MXN)
        self.assertEqual([p.id for p in interp.preguntas], ["duplicado:asking_price"])
        self.assertIsNone(interp.plan())
        decisiones, interp = responder(rejilla, interp, MXN, "duplicado:asking_price", 0)
        etiquetas = por_etiqueta(interp)
        self.assertEqual((etiquetas["Precio (1)"], etiquetas["Precio (2)"]), ("asking_price", "extra"))
        record = construir(interp.plan(), rejilla).resultado.records[0]
        self.assertEqual(record.asking_price, 12_500_000)
        self.assertEqual(record.extra["Precio (2)"], "500")
        self.assertEqual(record.extra["(sin encabezado, columna D)"], "Lote 1")


class Demostraciones(unittest.TestCase):
    """The three journeys the brief asks to demonstrate."""

    def test_familiar_file_goes_straight_to_a_plan(self):
        rejilla = cargar("familiar_reordenado.csv")
        interp = interpretar(rejilla, MXN)
        self.assertEqual(interp.preguntas, ())
        self.assertFalse(interp.necesita_ia)
        resultado = construir(interp.plan(), rejilla).resultado
        self.assertEqual((len(resultado.records), resultado.ubicados), (4, 4))
        self.assertEqual((resultado.records[0].lat, resultado.records[0].lon), (20.653, -103.701))

    def test_unfamiliar_layout_is_read_without_questions(self):
        rejilla = cargar("desconocido_titulos.xlsx")
        interp = interpretar(rejilla, {})
        self.assertEqual(interp.preguntas, ())
        self.assertEqual(interp.hoja.nombre, "Terrenos")
        self.assertEqual(interp.hoja.lineas[interp.encabezado], 3)
        self.assertEqual(por_etiqueta(interp), {
            "Nombre comercial": "terreno", "Entidad": "estado", "Municipio": "municipio",
            "Área del predio (ha)": "superficie_ha", "Valor de venta MXN": "asking_price",
            "Latitud": "lat", "Longitud": "lon", "Contacto": "extra"})
        construido = construir(interp.plan(), rejilla)
        self.assertEqual(construido.preambulo, (1, 2))
        self.assertEqual([(e.fila, e.motivo) for e in construido.excluidas], [(8, "TOTALES")])
        registros = construido.resultado.records
        self.assertEqual(len(registros), 4)
        self.assertEqual((registros[0].superficie_ha, registros[0].superficie_m2), (2.5, None))  # never put ha into m²
        self.assertEqual(construido.filas_datos, 5)

    def test_ambiguous_file_asks_exactly_one_question(self):
        rejilla = cargar("ambiguo_valor.csv")
        interp = interpretar(rejilla, {})
        self.assertEqual([p.texto for p in interp.preguntas], ["¿Qué representa la columna «Valor»?"])
        self.assertIn("12500000", interp.preguntas[0].detalle)
        decisiones, interp = responder(rejilla, interp, {}, interp.preguntas[0].id, 0)
        # Once «Valor» is a price, its unmarked amounts need a currency.
        self.assertEqual([p.id for p in interp.preguntas], ["moneda"])
        decisiones, interp = responder(rejilla, interp, decisiones, "moneda", 1)
        self.assertEqual(interp.preguntas, ())
        record = construir(interp.plan(), rejilla).resultado.records[0]
        self.assertEqual((record.asking_price, record.moneda), (12_500_000, "MXN"))


class Equivalencia(unittest.TestCase):
    def test_original_ara_workbook_builds_identical_records(self):
        # The real workbook's prices are US dollars (confirmed by the
        # supervisor); its "[$$-409]" format alone does not say so, so it asks.
        rejilla = R.leer(FIXTURE.read_bytes(), "b.xlsx")
        self.assertEqual([p.id for p in interpretar(rejilla, {}).preguntas], ["moneda"])
        interp = interpretar(rejilla, {"moneda": "USD"})
        self.assertEqual(interp.preguntas, ())
        construido = construir(interp.plan(), rejilla)
        legado = read_workbook(FIXTURE)
        registros = construido.resultado.records
        self.assertEqual(construido.resultado.hoja, legado.hoja)
        self.assertEqual([replace(r, moneda=None) for r in registros], list(legado.records))
        con_precio = [r for r in registros if r.asking_price is not None or r.asking_m2 is not None]
        self.assertEqual({r.moneda for r in con_precio}, {"USD"})
        self.assertEqual({r.moneda for r in registros if r not in con_precio}, {None})

    def test_original_ara_csv_template_builds_identical_values(self):
        rejilla = R.leer(TEMPLATE_CSV.read_bytes(), "p.csv")
        interp = interpretar(rejilla, MXN)
        self.assertEqual(interp.preguntas, ())
        nuevos = construir(interp.plan(), rejilla).resultado.records
        antiguos = read_csv_bytes(TEMPLATE_CSV.read_bytes()).records
        self.assertEqual([replace(r, moneda=None) for r in nuevos], list(antiguos))


class Salvaguardas(unittest.TestCase):
    def test_gis_order_xy_is_asked_never_swapped_silently(self):
        rejilla = cargar("coordenadas_gis.csv")
        interp = interpretar(rejilla, {})
        self.assertEqual([p.id for p in interp.preguntas], ["coordenadas"])
        self.assertEqual(por_etiqueta(interp)["X"], "lat")  # ARA's default stays visible
        _, interp = responder(rejilla, interp, {}, "coordenadas", 0)
        record = construir(interp.plan(), rejilla).resultado.records[0]
        self.assertEqual((record.lat, record.lon), (20.653, -103.701))

    def test_keeping_the_ara_convention_is_honoured_and_flagged_per_row(self):
        rejilla = cargar("coordenadas_gis.csv")
        _, interp = responder(rejilla, interpretar(rejilla, {}), {}, "coordenadas", 1)
        record = construir(interp.plan(), rejilla).resultado.records[0]
        self.assertEqual((record.lat, record.lon), (-103.701, 20.653))
        self.assertFalse(record.ubicado)

    def test_legacy_xy_with_decimal_commas_keep_their_coordinates(self):
        csv = b"Terreno;X;Y\nA;20,653;-103,701\nB;19,713;-98,968\n"
        rejilla = R.leer(csv, "x.csv")
        interp = interpretar(rejilla, {})
        self.assertEqual((por_etiqueta(interp)["X"], por_etiqueta(interp)["Y"]), ("lat", "lon"))
        self.assertEqual((interp.decimal, interp.preguntas), ("comma", ()))
        record = construir(interp.plan(), rejilla).resultado.records[0]
        self.assertEqual((record.lat, record.lon), (20.653, -103.701))

    def test_ambiguous_numbers_show_both_readings(self):
        rejilla = cargar("decimal_ambiguo.csv")
        interp = interpretar(rejilla, MXN)
        pregunta = interp.preguntas[0]
        self.assertEqual(pregunta.id, "decimal")
        self.assertIn("1250 o 1.25", pregunta.texto)
        _, interp = responder(rejilla, interp, MXN, "decimal", 1)
        self.assertEqual(construir(interp.plan(), rejilla).resultado.records[0].superficie_m2, 1.25)
        _, interp = responder(rejilla, interpretar(rejilla, MXN), MXN, "decimal", 0)
        self.assertEqual(construir(interp.plan(), rejilla).resultado.records[0].superficie_m2, 1250)

    def test_typed_excel_numbers_ignore_the_text_convention(self):
        rejilla = R.leer(libro_bytes([("T", [["Terreno", "Superficie m2"], ["A", 1234.5]])]), "x.xlsx")
        interp = interpretar(rejilla, {"decimal": "comma"})
        self.assertEqual(construir(interp.plan(), rejilla).resultado.records[0].superficie_m2, 1234.5)

    def test_dollars_stay_dollars_and_never_become_pesos(self):
        rejilla = cargar("dolares.csv")
        interp = interpretar(rejilla, {"moneda": "MXN"})   # an answer cannot override the file
        self.assertEqual(por_etiqueta(interp)["Precio (USD)"], "asking_price")
        self.assertEqual((interp.moneda, interp.moneda_origen, interp.preguntas), ("USD", "archivo", ()))
        registros = construir(interp.plan(), rejilla).resultado.records
        self.assertEqual({r.moneda for r in registros if r.asking_price is not None}, {"USD"})
        with self.assertRaises(PlanError):
            construir(replace(interp.plan(), moneda="MXN"), rejilla)

    def test_projected_coordinates_are_kept_and_explained(self):
        interp = interpretar(cargar("utm.csv"), {})
        self.assertEqual(interp.preguntas, ())
        self.assertEqual((por_etiqueta(interp)["Norte"], por_etiqueta(interp)["Este"]), ("extra", "extra"))
        self.assertTrue(any("UTM" in a for a in interp.avisos))

    def test_two_tables_are_offered_and_the_choice_is_used(self):
        rejilla = cargar("dos_tablas.xlsx")
        interp = interpretar(rejilla, MXN)
        self.assertEqual(interp.preguntas[0].id, "hoja")
        opcion = next(i for i, o in enumerate(interp.preguntas[0].opciones) if "Agosto" in o.etiqueta)
        _, interp = responder(rejilla, interp, MXN, "hoja", opcion)
        self.assertEqual(len(construir(interp.plan(), rejilla).resultado.records), 2)

    def test_formula_without_value_and_repeated_header_are_accounted_for(self):
        rejilla = cargar("formula_sin_valor.xlsx")
        interp = interpretar(rejilla, MXN)
        self.assertTrue(any("fórmula" in a for a in interp.avisos))
        construido = construir(interp.plan(), rejilla)
        self.assertEqual([e.motivo for e in construido.excluidas], ["ENCABEZADO_REPETIDO"])
        self.assertIsNone(construido.resultado.records[0].asking_price)  # unknown, never zero

    def test_missing_names_partial_coordinates_and_exclusions_are_counted(self):
        csv = (b"Terreno,Latitud,Longitud\nA,20.6,-103.7\n,20.6,-103.7\nC,20.6,\nD,20.6,-103.7\n"
               b"Totales,,\n")
        rejilla = R.leer(csv, "x.csv")
        interp = interpretar(rejilla, {"excluir": [4]})
        construido = construir(interp.plan(excluir=[4]), rejilla)
        resultado = construido.resultado
        self.assertEqual([r.terreno for r in resultado.records], ["A", "C"])
        self.assertEqual([r.fila for r in resultado.rechazadas], [3])
        self.assertEqual(sorted((e.fila, e.motivo) for e in construido.excluidas),
                         [(5, "EXCLUIDA"), (6, "TOTALES")])
        self.assertEqual(construido.filas_datos, 5)
        self.assertEqual((resultado.ubicados, resultado.sin_coordenadas), (1, 1))

    def test_csv_rows_must_match_the_header_width(self):
        rejilla = R.leer(b"Terreno,Estado\nA,Jalisco\nB,Calle 1, Lote 2\n", "x.csv")
        with self.assertRaises(PlanError) as caught:
            construir(interpretar(rejilla, {}).plan(), rejilla)
        self.assertIn("línea 3", str(caught.exception))

    def test_no_name_column_asks_and_cannot_be_forced(self):
        rejilla = R.leer(b"Alfa,Beta\nuno,dos\n", "x.csv")
        interp = interpretar(rejilla, {})
        self.assertEqual(interp.preguntas[0].id, "campo:terreno")
        _, interp = responder(rejilla, interp, {}, "campo:terreno", len(interp.preguntas[0].opciones) - 1)
        with self.assertRaises(PlanError):
            construir(interp.plan(), rejilla)


class Decisiones(unittest.TestCase):
    def test_user_choices_win_over_names(self):
        rejilla = cargar("familiar_reordenado.csv")
        interp = interpretar(rejilla, {})
        precio = next(c.id for c in interp.columnas if c.visible == "Asking Price")
        interp = interpretar(rejilla, {"columnas": {precio: "extra"}})
        self.assertEqual(interp.asignaciones[precio], "extra")
        self.assertEqual(interp.origenes[precio].fuente, "usuario")

    def test_user_choice_takes_a_field_from_another_column(self):
        rejilla = cargar("familiar_reordenado.csv")
        interp = interpretar(rejilla, {})
        municipio = next(c.id for c in interp.columnas if c.visible == "Municipio")
        interp = interpretar(rejilla, {"columnas": {municipio: "estado"}, **MXN})
        self.assertEqual(interp.preguntas, ())
        self.assertEqual(por_etiqueta(interp)["Estado"], "extra")

    def test_header_row_can_be_chosen_outside_the_suggestion(self):
        rejilla = cargar("desconocido_titulos.xlsx")
        interp = interpretar(rejilla, {"encabezado": 0})
        self.assertEqual(interp.encabezado, 0)
        self.assertEqual(interp.preguntas[0].id, "campo:terreno")


class Formatos(unittest.TestCase):
    FORMATO = {"id": 7, "nombre": "Broker", "version": 1, "decimal": "comma", "hoja": None,
               "asignaciones": [["desarrollo", 1, "terreno"], ["mpio", 1, "municipio"],
                                ["precio pedido mxn", 1, "asking_price"], ["lat dec", 1, "lat"],
                                ["lon dec", 1, "lon"], ["telefono contacto", 1, "extra"]]}

    def test_a_confirmed_format_is_reused_even_when_reordered(self):
        csv = (b"Precio pedido MXN,Lon. dec,Desarrollo,Lat. dec,Mpio.\n"
               b"12500000,\"-103,701\",Alfa,\"20,653\",Tala\n")
        rejilla = R.leer(csv, "x.csv")
        interp = interpretar(rejilla, {}, [self.FORMATO])
        self.assertEqual(interp.formato["id"], 7)
        self.assertEqual(interp.preguntas, ())
        self.assertFalse(interp.necesita_ia)
        record = construir(interp.plan(), rejilla).resultado.records[0]
        self.assertEqual((record.terreno, record.lat, record.asking_price), ("Alfa", 20.653, 12_500_000))

    def test_a_missing_column_makes_the_format_incompatible(self):
        rejilla = R.leer(b"Desarrollo,Mpio.\nAlfa,Tala\n", "x.csv")
        interp = interpretar(rejilla, {}, [self.FORMATO])
        self.assertIsNone(interp.formato)
        self.assertEqual(interp.preguntas[0].id, "campo:terreno")

    def test_disagreeing_formats_are_not_chosen_by_recency(self):
        otro = {**self.FORMATO, "id": 8, "asignaciones": [
            *self.FORMATO["asignaciones"][:2], ["precio pedido mxn", 1, "asking_m2"],
            *self.FORMATO["asignaciones"][3:]]}
        rejilla = cargar("desconocido_ia.csv")
        interp = interpretar(rejilla, {}, [self.FORMATO, otro])
        self.assertIsNone(interp.formato)
        self.assertTrue(any("no están de acuerdo" in a for a in interp.avisos))


class PropuestaAutomatica(unittest.TestCase):
    def setUp(self):
        self.rejilla = cargar("desconocido_ia.csv")
        self.base = interpretar(self.rejilla, {})
        self.ids = {c.visible: c.id for c in self.base.columnas}

    def propuesta(self, **pares):
        return {"asignaciones": [{"columna": self.ids.get(k, k), "campo": v, "motivo": "x"}
                                 for k, v in pares.items()], "advertencias": []}

    def test_supported_suggestions_are_applied(self):
        interp = interpretar(self.rejilla, {}, (), self.propuesta(
            Desarrollo="terreno", **{"Lat. dec": "lat", "Lon. dec": "lon", "Precio pedido MXN": "asking_price"}))
        etiquetas = por_etiqueta(interp)
        self.assertEqual((etiquetas["Desarrollo"], etiquetas["Lat. dec"]), ("terreno", "lat"))
        self.assertEqual(interp.origenes[self.ids["Desarrollo"]].fuente, "ia")

    def test_unsupported_suggestion_becomes_a_question_not_a_fact(self):
        # A price proposed for the latitude column: its header and values say otherwise.
        interp = interpretar(self.rejilla, {}, (), self.propuesta(
            Desarrollo="terreno", **{"Lat. dec": "asking_price"}))
        self.assertEqual(por_etiqueta(interp)["Lat. dec"], "extra")
        pregunta = next(p for p in interp.preguntas if p.id == f"columna:{self.ids['Lat. dec']}")
        self.assertEqual(pregunta.opciones[pregunta.sugerida].etiqueta, "Precio total")

    def test_unknown_ids_and_fields_are_ignored(self):
        interp = interpretar(self.rejilla, {}, (), self.propuesta(
            **{"csv:,/column:99": "terreno", "Desarrollo": "inventado"}))
        self.assertEqual(por_etiqueta(interp)["Desarrollo"], "extra")

    def test_never_overrides_names_formats_or_the_user(self):
        rejilla = cargar("ambiguo_valor.csv")
        base = interpretar(rejilla, {})
        ids = {c.visible: c.id for c in base.columnas}
        propuesta = {"asignaciones": [{"columna": ids["Terreno"], "campo": "estado", "motivo": "x"},
                                      {"columna": ids["Valor"], "campo": "asking_price", "motivo": "x"}],
                     "advertencias": []}
        interp = interpretar(rejilla, {"columnas": {ids["Estado"]: "extra"}}, (), propuesta)
        self.assertEqual(interp.asignaciones[ids["Terreno"]], "terreno")
        self.assertEqual(interp.asignaciones[ids["Estado"]], "extra")
        # A price ambiguity is still asked; the suggestion only preselects.
        pregunta = next(p for p in interp.preguntas if p.id == f"columna:{ids['Valor']}")
        self.assertEqual(pregunta.sugerida, 0)
        self.assertEqual(interp.asignaciones[ids["Valor"]], "extra")


class Plan(unittest.TestCase):
    def test_plan_is_bound_to_the_file_and_validated(self):
        rejilla = cargar("familiar_reordenado.csv")
        plan = interpretar(rejilla, MXN).plan()
        otro = R.leer(b"Terreno\nA\n", "y.csv")
        with self.assertRaises(PlanError):
            construir(plan, otro)
        malos = [
            {**plan.to_dict(), "asignaciones": {**plan.asignaciones, "csv:,/column:50": "lat"}},
            {**plan.to_dict(), "asignaciones": {**plan.asignaciones, "csv:,/column:1": "terreno"}},
            {**plan.to_dict(), "decimal": "space"},
            {**plan.to_dict(), "asignaciones": {**plan.asignaciones, "csv:,/column:1": "inventado"}},
            {**plan.to_dict(), "excluir": [0]},
            {**plan.to_dict(), "moneda": None},
            {**plan.to_dict(), "moneda": "EUR"},
            {**plan.to_dict(), "version": 1},
        ]
        for datos in malos:
            with self.subTest(datos=datos), self.assertRaises(PlanError):
                construir(ImportPlan(**{k: v for k, v in datos.items()}), rejilla)


if __name__ == "__main__":
    unittest.main()

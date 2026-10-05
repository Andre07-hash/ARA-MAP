"""Supervisor review R1-R5 (reports/import-assistant-handoff-2026-09-24/SUPERVISOR_REVIEW.md).

The reviewer's own cases are kept verbatim in the report folder and repeated
here so that normal verification runs them; the rest are stronger controls
for each finding. Fictional data, temporary SQLite, fake providers only.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import replace
from unittest.mock import patch

from server.asistente import ia
from server.asistente.detectar import fusionar, interpretar
from server.asistente.plan import PlanError, construir
from server.asistente.rejilla import leer
from server.web_util import ApiError
from tests.test_api import req
from tests.test_asistente_api import AsistenteCase, Contador
from tests.test_asistente_ia import OPENAI_ENV, Transporte, interpretacion, respuesta_openai

DUPLICADOS = b"Terreno,Precio,Precio,Latitud,Longitud\nNorte,1000000,500,19.5,-99.1\n"
DUPLICADOS_INVERTIDOS = b"Terreno,Precio,Precio,Latitud,Longitud\nNorte,500,1000000,19.5,-99.1\n"


def responder(case, r, pregunta_id, etiqueta_parcial):
    pregunta = next(p for p in r["preguntas"] if p["id"] == pregunta_id)
    opcion = next(o["indice"] for o in pregunta["opciones"] if etiqueta_parcial in o["etiqueta"])
    return case.preparar(r, [{"pregunta": pregunta_id, "opcion": opcion}])


# ----------------------------------------------------------------------- R1

class R1FormatosConEncabezadosRepetidos(AsistenteCase):
    def recordar_precios(self):
        r = self.analizar("original.csv", DUPLICADOS)
        cols = r["interpretacion"]["columnas"]
        r = self.preparar(r, correcciones={"columnas": {cols[1]["id"]: "asking_price", cols[2]["id"]: "asking_m2"}})
        self.confirmar(r)

    def test_reviewer_case_reordered_duplicates_require_reconfirmation(self):
        self.recordar_precios()
        segundo = self.analizar("reordenado.csv", DUPLICADOS_INVERTIDOS)
        self.assertEqual([p["id"] for p in segundo["preguntas"]], ["formato-repetidas:precio"])
        self.assertIsNone(segundo["preguntas"][0]["sugerida"])   # nothing preselected
        self.assertEqual(segundo["interpretacion"]["formato"]["nombre"], "Formato de «original»")

    def test_the_answer_decides_and_unique_columns_still_come_from_the_format(self):
        self.recordar_precios()
        r = responder(self, self.analizar("reordenado.csv", DUPLICADOS_INVERTIDOS),
                      "formato-repetidas:precio", "Al revés")
        fila = r["vista_previa"]["filas"][0]
        self.assertEqual((fila["asking_price"], fila["asking_m2"]), (1_000_000, 500))
        self.assertEqual((fila["lat"], fila["lon"]), (19.5, -99.1))

        r = responder(self, self.analizar("mismo.csv", DUPLICADOS), "formato-repetidas:precio", "Como la vez anterior")
        fila = r["vista_previa"]["filas"][0]
        self.assertEqual((fila["asking_price"], fila["asking_m2"]), (1_000_000, 500))

    def test_keeping_both_as_additional_data(self):
        self.recordar_precios()
        r = responder(self, self.analizar("x.csv", DUPLICADOS_INVERTIDOS), "formato-repetidas:precio", "Conservar ambas")
        self.assertIsNone(r["vista_previa"]["filas"][0]["asking_price"])

    def test_three_same_named_columns_are_asked_one_by_one(self):
        csv = b"Terreno,Dato,Dato,Dato\nNorte,1000000,500,25000\n"
        r = self.analizar("tres.csv", csv)
        cols = r["interpretacion"]["columnas"]
        r = self.preparar(r, correcciones={"columnas": {
            cols[1]["id"]: "asking_price", cols[2]["id"]: "asking_m2", cols[3]["id"]: "superficie_m2"}})
        self.confirmar(r)
        segundo = self.analizar("tres.csv", csv)
        self.assertEqual(len(segundo["preguntas"]), 3)
        self.assertTrue(all(p["sugerida"] is None for p in segundo["preguntas"]))

    def test_same_named_columns_the_format_kept_as_extra_need_no_question(self):
        csv = b"Terreno,Nota,Nota\nNorte,a,b\n"
        self.confirmar(self.analizar("notas.csv", csv))
        r = self.analizar("notas.csv", b"Terreno,Nota,Nota\nSur,b,a\n")
        self.assertEqual(r["estado"], "vista_previa")

    def test_blank_headings_are_never_taken_from_a_format(self):
        csv = b"Terreno,,Precio\nNorte,x,1000000\n"
        self.confirmar(self.analizar("blancos.csv", csv))
        r = self.analizar("blancos.csv", b"Terreno,,Precio\nSur,y,2000000\n")
        blanca = next(c for c in r["interpretacion"]["columnas"] if not c["etiqueta"])
        self.assertEqual((blanca["destino"], blanca["origen"]), ("extra", "predeterminado"))
        self.assertEqual(r["vista_previa"]["filas"][0]["asking_price"], 2_000_000)


# ----------------------------------------------------------------------- R2

class R2ConfirmacionAtomica(AsistenteCase):
    def test_reviewer_case_correction_during_confirmation_is_refused(self):
        old = self.analizar("race.csv", b"Terreno,Precio\nNorte,1000000\n")
        col = old["interpretacion"]["columnas"][1]["id"]
        corregidas, rechazadas = [], []

        def concurrente():
            try:
                corregidas.append(self.preparar(old, correcciones={"columnas": {col: "extra"}}))
            except ApiError as error:
                rechazadas.append(error.status)

        with patch("server.api.importar.db.backup", side_effect=concurrente):
            base = self.confirmar(old, recordar_formato=False)["base"]
        self.assertEqual((corregidas, rechazadas), ([], [409]))
        self.assertEqual(api_terrenos_precio(base["id"]), [1_000_000])

    def test_confirming_an_older_preview_after_a_correction_writes_nothing(self):
        old = self.analizar("race.csv", b"Terreno,Precio\nNorte,1000000\n")
        col = old["interpretacion"]["columnas"][1]["id"]
        self.preparar(old, correcciones={"columnas": {col: "extra"}})
        self.assertIn(self.status_of(lambda: self.confirmar(old)), (409, 410))
        self.assertEqual(self.bases(), [])

    def carrera(self, confirmar):
        """Start a confirmation and a correction together, many times over."""
        resultados = []
        for i in range(25):
            r = self.analizar(f"c{i}.csv", b"Terreno,Precio\nNorte,1000000\n")
            col = r["interpretacion"]["columnas"][1]["id"]
            salida = {}
            barrera = threading.Barrier(2)

            def confirmar_hilo(r=r, barrera=barrera, salida=salida):
                barrera.wait()
                try:
                    salida["confirmada"] = confirmar(r)
                except ApiError as error:
                    salida["confirmada_error"] = error.status

            def corregir_hilo(r=r, col=col, barrera=barrera, salida=salida):
                barrera.wait()
                try:
                    salida["corregida"] = self.preparar(r, correcciones={"columnas": {col: "extra"}})
                except ApiError as error:
                    salida["corregida_error"] = error.status

            hilos = [threading.Thread(target=confirmar_hilo), threading.Thread(target=corregir_hilo)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
            resultados.append(salida)
        return resultados

    def test_concurrent_new_base_confirm_and_correction_never_both_succeed(self):
        for salida in self.carrera(lambda r: self.confirmar(r, recordar_formato=False)):
            self.assertFalse("confirmada" in salida and "corregida" in salida, salida)
            self.assertTrue("confirmada" in salida or "corregida" in salida, salida)

    def test_concurrent_append_and_correction_never_both_succeed(self):
        from server.api import importar as api_importar
        from server.repo import bases as repo_bases
        base_id = repo_bases.create(self.conn, "Destino", None, None)

        def agregar(r):
            return api_importar.append(req(params={"id": base_id}, json_body={"token": r["vista_previa"]["token"]}))

        original = self.analizar

        def analizar_en_base(nombre, contenido=None, base_id=base_id):
            return original(nombre, contenido, base_id=base_id)

        self.analizar = analizar_en_base
        exitos = 0
        for salida in self.carrera(agregar):
            self.assertFalse("confirmada" in salida and "corregida" in salida, salida)
            exitos += "confirmada" in salida
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM terreno").fetchone()[0], min(exitos, 1))


def api_terrenos_precio(base_id):
    from server.api import bases as api_bases
    return [t["asking_price"] for t in api_bases.terrenos(req(params={"id": base_id}))["terrenos"]]


# ----------------------------------------------------------------------- R3

class R3MonedaExtranjera(AsistenteCase):
    # Prices are kept in USD or MXN, with their currency, never converted.
    DOLARES = ("Precio US$", "Precio USD", "Precio (USD)", "Precio en dólares")
    PESOS = ("Precio MXN", "Precio en pesos")
    SIN_MARCA = ("Precio", "Precio ($)", "Asking Price")
    NO_ADMITIDAS = ("Precio EUR", "Precio €", "Precio CAD", "Precio £")

    def como_precio(self, csv):
        rejilla = leer(csv, "m.csv")
        return interpretar(rejilla, {"columnas": {interpretar(rejilla, {}).columnas[1].id: "asking_price"}})

    def construir_como_precio(self, csv, moneda=None):
        rejilla = leer(csv, "moneda.csv")
        inicial = interpretar(rejilla, {})
        decisiones = {"columnas": {inicial.columnas[1].id: "asking_price"}}
        interp = interpretar(rejilla, {**decisiones, "moneda": moneda} if moneda else decisiones)
        plan = interp.plan()
        if plan is None:
            raise PlanError("; ".join(p.texto for p in interp.preguntas))
        return construir(plan if moneda is None else replace(plan, moneda=moneda), rejilla)

    def test_explicit_dollars_and_pesos_are_kept_in_their_currency(self):
        for encabezados, codigo in ((self.DOLARES, "USD"), (self.PESOS, "MXN")):
            for encabezado in encabezados:
                with self.subTest(encabezado=encabezado):
                    csv = f"Terreno,{encabezado}\nNorte,1000000\n".encode()
                    interp = self.como_precio(csv)
                    self.assertEqual((interp.moneda, interp.preguntas), (codigo, ()))
                    record = construir(interp.plan(), leer(csv, "m.csv")).resultado.records[0]
                    self.assertEqual((record.asking_price, record.moneda), (1_000_000, codigo))
                    # ...and never relabelled into the other currency, even explicitly
                    otra = "MXN" if codigo == "USD" else "USD"
                    with self.assertRaises(PlanError):
                        self.construir_como_precio(csv, otra)

    def test_unsupported_currencies_are_never_saved_as_prices(self):
        for encabezado in self.NO_ADMITIDAS:
            with self.subTest(encabezado=encabezado):
                csv = f"Terreno,{encabezado}\nNorte,1000000\n".encode()
                interp = interpretar(leer(csv, "m.csv"), {})
                self.assertEqual(interp.asignaciones[interp.columnas[1].id], "extra")
                for moneda in ("USD", "MXN"):
                    with self.assertRaises(PlanError):
                        self.construir_como_precio(csv, moneda)

    def test_currency_in_any_cell_counts_not_just_samples(self):
        filas = "".join(f"P{i},{1000 + i}\n" for i in range(20))
        con_dolar = f"Terreno,Precio\n{filas}P99,USD 1200\n".encode()
        self.assertEqual(interpretar(leer(con_dolar, "m.csv"), {}).moneda, "USD")
        with self.assertRaises(PlanError):
            self.construir_como_precio(con_dolar, "MXN")
        with self.assertRaises(PlanError):
            self.construir_como_precio(f"Terreno,Precio\n{filas}P99,EUR 1200\n".encode(), "USD")

    def test_unmarked_prices_ask_and_then_import(self):
        for encabezado in self.SIN_MARCA:
            with self.subTest(encabezado=encabezado):
                csv = f"Terreno,{encabezado}\nNorte,1000000\n".encode()
                self.assertEqual([p.id for p in self.como_precio(csv).preguntas], ["moneda"])
                record = self.construir_como_precio(csv, "MXN").resultado.records[0]
                self.assertEqual((record.asking_price, record.moneda), (1_000_000, "MXN"))

    def test_a_text_column_mentioning_a_currency_is_not_demoted(self):
        interp = interpretar(leer(b"Terreno,Direcci\xc3\xb3n\nNorte,Frente a la casa de cambio USD\n", "d.csv"), {})
        self.assertEqual(interp.asignaciones[interp.columnas[1].id], "direccion")

    def test_saved_formats_and_suggestions_cannot_relabel_currency(self):
        formato = {"id": 1, "nombre": "F", "version": 1, "decimal": None, "hoja": None,
                   "asignaciones": [["terreno", 1, "terreno"], ["precio eur", 1, "asking_price"]]}
        rejilla = leer(b"Terreno,Precio EUR\nNorte,1000000\n", "f.csv")
        interp = interpretar(rejilla, {}, [formato])
        self.assertEqual(interp.asignaciones[interp.columnas[1].id], "extra")
        propuesta = {"asignaciones": [{"columna": interp.columnas[1].id, "campo": "asking_price", "motivo": "x"}],
                     "advertencias": []}
        interp = interpretar(rejilla, {}, (), propuesta)
        self.assertEqual(interp.asignaciones[interp.columnas[1].id], "extra")


# ----------------------------------------------------------------------- R4

class R4Presupuesto(AsistenteCase):
    def setUp(self):
        super().setUp()
        self.env_ia = patch.dict(os.environ, OPENAI_ENV)
        self.env_ia.start()
        self.addCleanup(self.env_ia.stop)

    def usos(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM uso_ia ORDER BY id").fetchall()]

    def maximo(self, interp, pendientes):
        config = ia.configuracion()[0]
        usuario = json.dumps(ia.solicitud(interp.columnas, interp.asignaciones, pendientes, config), ensure_ascii=False)
        ids = [c.id for c in interp.columnas if c.id in pendientes]
        libres = [k for k in ia.C.CAMPOS if k not in set(interp.asignaciones.values())]
        esquema = ia.esquema(ids, libres)
        bytes_ = len((ia.SISTEMA + usuario + json.dumps(esquema, ensure_ascii=False)).encode())
        return ia.costo_maximo(ia.SISTEMA, usuario, config, esquema), bytes_

    def test_reviewer_case_usage_above_the_old_estimate_is_refused_before_calling(self):
        interp, pendientes = interpretacion()
        config = ia.configuracion()[0]
        usuario = json.dumps(ia.solicitud(interp.columnas, interp.asignaciones, pendientes, config), ensure_ascii=False)
        tope = ia.estimar_costo(ia.SISTEMA, usuario, config) * 1.01
        proveedor = Contador(respuesta=lambda _: {"asignaciones": [], "advertencias": []})
        ia.fijar_proveedor(proveedor)
        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": str(tope)}):
            resultado = ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
        self.assertEqual((resultado.estado, proveedor.llamadas), ("presupuesto", 0))
        self.assertLessEqual(sum(u["costo_usd"] for u in self.usos()), tope)

    def test_any_usage_within_the_byte_bound_fits_the_reservation(self):
        interp, pendientes = interpretacion()
        maximo, bytes_ = self.maximo(interp, pendientes)
        config = ia.configuracion()[0]
        # The worst a byte-level tokenizer can report, plus the full output allowance.
        ia.fijar_proveedor(ia.ProveedorOpenAI(Transporte(respuesta_openai(
            {"asignaciones": [], "advertencias": []}, uso=(bytes_ + ia.SOBRECARGA_TOKENS, config.max_salida)))))
        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": str(maximo)}):
            self.assertEqual(ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado, "ok")
        self.assertLessEqual(self.usos()[0]["costo_usd"], maximo + 1e-12)

    def test_usage_above_the_reservation_is_recorded_whole_and_flagged(self):
        interp, pendientes = interpretacion()
        maximo, bytes_ = self.maximo(interp, pendientes)
        ia.fijar_proveedor(ia.ProveedorOpenAI(Transporte(respuesta_openai(
            {"asignaciones": [], "advertencias": []}, uso=(bytes_ * 10, 800)))))
        with self.assertLogs("ara.ia", level="WARNING"):
            ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
        uso = self.usos()[0]
        self.assertGreater(uso["costo_usd"], maximo)          # never clipped or hidden
        self.assertTrue(uso["estado"].endswith("_sobre_reserva"))

    def test_missing_or_invalid_usage_keeps_the_reservation(self):
        interp, pendientes = interpretacion()
        maximo, _ = self.maximo(interp, pendientes)
        contenido = json.dumps({"asignaciones": [], "advertencias": []})
        for usage in (None, {}, {"prompt_tokens": -5, "completion_tokens": 10},
                      {"prompt_tokens": "100", "completion_tokens": 10}, {"prompt_tokens": 1.5, "completion_tokens": 1}):
            with self.subTest(usage=usage):
                self.conn.execute("DELETE FROM uso_ia")
                cuerpo = {"choices": [{"message": {"content": contenido}}]}
                if usage is not None:
                    cuerpo["usage"] = usage
                ia.fijar_proveedor(ia.ProveedorOpenAI(Transporte(json.dumps(cuerpo).encode())))
                self.assertEqual(ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado, "ok")
                uso = self.usos()[0]
                self.assertAlmostEqual(uso["costo_usd"], maximo)
                self.assertEqual(uso["estado"], "ok_uso_desconocido")

    def test_failures_keep_or_release_reservations_as_appropriate(self):
        import io
        import urllib.error
        interp, pendientes = interpretacion()
        maximo, _ = self.maximo(interp, pendientes)
        casos = [
            (Transporte(error=TimeoutError()), "tiempo", maximo),
            (Transporte(error=urllib.error.HTTPError("u", 500, "e", {}, io.BytesIO())), "error", maximo),
            (Transporte(respuesta=b"no-json"), "invalido", maximo),
            (Transporte(error=urllib.error.HTTPError("u", 429, "r", {}, io.BytesIO())), "limite", 0.0),
            (Transporte(respuesta=respuesta_openai(None, uso=(100, 5), refusal="no")), "rechazo", 100e-6 + 20e-6),
        ]
        for transporte, estado, costo in casos:
            with self.subTest(estado=estado):
                self.conn.execute("DELETE FROM uso_ia")
                ia.fijar_proveedor(ia.ProveedorOpenAI(transporte))
                self.assertEqual(ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado, estado)
                self.assertAlmostEqual(self.usos()[0]["costo_usd"], costo)

    def test_simultaneous_calls_cannot_share_the_last_of_the_budget(self):
        interp, pendientes = interpretacion()
        maximo, _ = self.maximo(interp, pendientes)
        estados = []
        rechazadas = threading.Semaphore(0)

        class EnVuelo:
            """Stays in flight until the other three callers have been answered."""
            nombre = "en-vuelo"
            llamadas = 0

            def sugerir(self, *args):
                EnVuelo.llamadas += 1
                for _ in range(3):
                    rechazadas.acquire(timeout=10)
                return ia.Respuesta({"asignaciones": [], "advertencias": []}, 10, 10)

        proveedor = EnVuelo()
        ia.fijar_proveedor(proveedor)
        barrera = threading.Barrier(4)

        def llamar():
            barrera.wait()
            estado = ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado
            estados.append(estado)
            if estado != "ok":
                rechazadas.release()

        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": str(maximo * 1.5)}):
            hilos = [threading.Thread(target=llamar) for _ in range(4)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
        self.assertEqual(sorted(estados), ["ok", "presupuesto", "presupuesto", "presupuesto"])
        self.assertEqual(proveedor.llamadas, 1)

    def test_spending_survives_a_restart(self):
        interp, pendientes = interpretacion()
        maximo, _ = self.maximo(interp, pendientes)
        ia.fijar_proveedor(ia.ProveedorOpenAI(Transporte(json.dumps(
            {"choices": [{"message": {"content": json.dumps({"asignaciones": [], "advertencias": []})}}]}).encode())))
        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": str(maximo * 1.5)}):
            ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
            # A new process sees only the database: read it the way a fresh one would.
            fresca = sqlite3.connect(self.db_path)
            self.assertAlmostEqual(fresca.execute("SELECT SUM(costo_usd) FROM uso_ia").fetchone()[0], maximo)
            fresca.close()
            self.assertEqual(ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado, "presupuesto")


# ----------------------------------------------------------------------- R5

class R5RespuestasMalformadas(AsistenteCase):
    def test_reviewer_case_malformed_field_falls_back_through_analysis(self):
        ia.fijar_proveedor(Contador(respuesta=lambda _: {"asignaciones": [
            {"columna": [], "campo": "terreno", "motivo": "malformed"}], "advertencias": []}))
        r = self.analizar("desconocido_ia.csv")
        self.assertEqual(r["estado"], "preguntas")
        self.assertEqual(r["interpretacion"]["automatico"]["estado"], "invalido")

    def test_malformed_shapes_all_fall_back(self):
        malos = [
            {"asignaciones": [{"columna": {}, "campo": "terreno", "motivo": "x"}], "advertencias": []},
            {"asignaciones": [{"columna": None, "campo": "terreno", "motivo": "x"}], "advertencias": []},
            {"asignaciones": [{"columna": 5, "campo": "terreno", "motivo": "x"}], "advertencias": []},
            {"asignaciones": [{"columna": "csv:,/column:0", "campo": [], "motivo": "x"}], "advertencias": []},
            {"asignaciones": [{"columna": "csv:,/column:0", "campo": None, "motivo": "x"}], "advertencias": []},
            {"asignaciones": [{"columna": "csv:,/column:0", "campo": "terreno", "motivo": None}], "advertencias": []},
            {"asignaciones": {}, "advertencias": []},
            {"asignaciones": [], "advertencias": [1]},
            {"asignaciones": [], "advertencias": None},
            [], None, "texto", 7,
        ]
        for malo in malos:
            with self.subTest(malo=malo):
                ia.fijar_proveedor(Contador(respuesta=lambda _, m=malo: m))
                r = self.analizar("desconocido_ia.csv")
                self.assertEqual(r["estado"], "preguntas")
                self.assertEqual(r["interpretacion"]["automatico"]["estado"], "invalido")

    def test_a_provider_bug_is_a_fallback_and_is_logged_without_content(self):
        class Roto:
            nombre = "roto"

            def sugerir(self, *args):
                raise ValueError("Predio Delta 55 0000 0003")

        ia.fijar_proveedor(Roto())
        with self.assertLogs("ara.ia", level="ERROR") as registro:
            r = self.analizar("desconocido_ia.csv")
        self.assertEqual(r["interpretacion"]["automatico"]["estado"], "error")
        self.assertNotIn("Predio", " ".join(registro.output))
        self.assertIn("ValueError", " ".join(registro.output))

    def test_merge_helper_ignores_unknown_keys_it_is_given(self):
        # fusionar is only ever fed server-built decisions; still, lists merge as sets.
        self.assertEqual(fusionar({"sin_campo": ["a"]}, {"sin_campo": ["a", "b"]})["sin_campo"], ["a", "b"])

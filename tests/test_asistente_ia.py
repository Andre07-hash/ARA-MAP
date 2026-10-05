"""Automatic assistance, tested with stubs only: no network, no credentials."""

from __future__ import annotations

import io
import json
import os
import urllib.error
from pathlib import Path
from unittest.mock import patch

from server.asistente import ia
from server.asistente import rejilla as R  # noqa: N812 - short alias for a vocabulary module
from server.asistente.detectar import interpretar
from tests.support import TempDatabase

A = Path(__file__).parent / "fixtures" / "asistente"
OPENAI_ENV = {"ARA_MAP_IA_PROVEEDOR": "openai", "ARA_MAP_IA_MODELO": "modelo-de-prueba",
              "ARA_MAP_IA_CLAVE": "sk-prueba", "ARA_MAP_IA_LIMITE_MENSUAL_USD": "5",
              "ARA_MAP_IA_COSTO_ENTRADA_USD_MTOK": "1", "ARA_MAP_IA_COSTO_SALIDA_USD_MTOK": "4",
              "ARA_MAP_DATABASE_URL": "", "DATABASE_URL": ""}
SIN_IA = {k: "" for k in OPENAI_ENV}


def interpretacion():
    rejilla = R.leer((A / "desconocido_ia.csv").read_bytes(), "desconocido_ia.csv")
    interp = interpretar(rejilla, {})
    pendientes = {c.id for c in interp.columnas if interp.origenes[c.id].fuente == "predeterminado"}
    return interp, pendientes


def respuesta_openai(contenido, uso=(1200, 150), refusal=None):
    mensaje = {"role": "assistant", "content": json.dumps(contenido) if contenido is not None else None}
    if refusal:
        mensaje["refusal"] = refusal
    return json.dumps({"choices": [{"message": mensaje}],
                       "usage": {"prompt_tokens": uso[0], "completion_tokens": uso[1]}}).encode()


class Transporte:
    def __init__(self, respuesta=None, error=None):
        self.respuesta, self.error, self.peticiones = respuesta, error, []

    def __call__(self, peticion, tiempo):
        self.peticiones.append((peticion, tiempo))
        if self.error:
            raise self.error
        return self.respuesta


class IACase(TempDatabase):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, OPENAI_ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(ia.fijar_proveedor, None)

    def con_transporte(self, transporte):
        proveedor = ia.ProveedorOpenAI(transporte)
        ia.fijar_proveedor(proveedor)
        return proveedor

    def usos(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM uso_ia ORDER BY id").fetchall()]


class Configuracion(IACase):
    def test_off_by_default_and_says_so(self):
        with patch.dict(os.environ, SIN_IA):
            config, faltan = ia.configuracion()
        self.assertIsNone(config)
        self.assertIn("ARA_MAP_IA_PROVEEDOR", faltan[0])

    def test_each_missing_setting_is_named(self):
        with patch.dict(os.environ, {"ARA_MAP_IA_MODELO": "", "ARA_MAP_IA_CLAVE": "", "OPENAI_API_KEY": "",
                                     "ARA_MAP_IA_LIMITE_MENSUAL_USD": "",
                                     "ARA_MAP_IA_COSTO_ENTRADA_USD_MTOK": ""}):
            config, faltan = ia.configuracion()
        texto = " ".join(faltan)
        self.assertIsNone(config)
        for nombre in ("ARA_MAP_IA_MODELO", "ARA_MAP_IA_CLAVE", "ARA_MAP_IA_LIMITE_MENSUAL_USD",
                       "ARA_MAP_IA_COSTO_ENTRADA_USD_MTOK"):
            self.assertIn(nombre, texto)

    def test_no_spending_limit_means_no_calls(self):
        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": "0"}):
            self.assertIsNone(ia.configuracion()[0])

    def test_complete_configuration(self):
        config, faltan = ia.configuracion()
        self.assertEqual((config.proveedor, config.modelo, config.limite_mensual_usd), ("openai", "modelo-de-prueba", 5.0))
        self.assertEqual(faltan, [])


class Solicitud(IACase):
    def test_only_headers_summaries_and_few_short_samples_leave(self):
        interp, pendientes = interpretacion()
        config = ia.configuracion()[0]
        datos = ia.solicitud(interp.columnas, interp.asignaciones, pendientes, config)
        texto = json.dumps(datos, ensure_ascii=False)
        porcolumna = {c["encabezado"]: c for c in datos["columnas"]}
        self.assertEqual(porcolumna["Teléfono contacto"]["muestras"], [])   # contact data withheld
        self.assertLessEqual(len(porcolumna["Desarrollo"]["muestras"]), 3)
        self.assertNotIn("Predio Delta", texto)                           # 4th row never sent
        self.assertNotIn("55 0000 000", texto)
        self.assertEqual(porcolumna["Lat. dec"]["resumen"]["tipo"], "número")

    def test_resolved_columns_send_no_samples(self):
        rejilla = R.leer((A / "ambiguo_valor.csv").read_bytes(), "a.csv")
        interp = interpretar(rejilla, {})
        valor = next(c.id for c in interp.columnas if c.visible == "Valor")
        datos = ia.solicitud(interp.columnas, interp.asignaciones, {valor}, ia.configuracion()[0])
        terreno = next(c for c in datos["columnas"] if c["encabezado"] == "Terreno")
        self.assertEqual(set(terreno), {"id", "encabezado", "ya_identificada_como"})
        self.assertNotIn("Predio", json.dumps([c for c in datos["columnas"] if c["id"] != valor]))

    def test_samples_can_be_turned_off(self):
        interp, pendientes = interpretacion()
        with patch.dict(os.environ, {"ARA_MAP_IA_MUESTRAS": "0"}):
            datos = ia.solicitud(interp.columnas, interp.asignaciones, pendientes, ia.configuracion()[0])
        self.assertTrue(all(c.get("muestras", []) == [] for c in datos["columnas"]))


class Validacion(IACase):
    IDS = {"c:0", "c:1"}
    CAMPOS = {"terreno", "lat"}

    def test_well_formed(self):
        propuesta = ia.validar({"asignaciones": [{"columna": "c:0", "campo": "terreno", "motivo": "m"},
                                                 {"columna": "c:1", "campo": "desconocido", "motivo": "?"}],
                                "advertencias": ["a"]}, self.IDS, self.CAMPOS)
        self.assertEqual(propuesta["asignaciones"], [{"columna": "c:0", "campo": "terreno", "motivo": "m"}])

    def test_malformed_responses_are_rejected(self):
        malas = [
            [], {"asignaciones": []}, {"asignaciones": [], "advertencias": [], "extra": 1},
            {"asignaciones": [{"columna": "c:9", "campo": "terreno", "motivo": ""}], "advertencias": []},
            {"asignaciones": [{"columna": "c:0", "campo": "borrar_base", "motivo": ""}], "advertencias": []},
            {"asignaciones": [{"columna": "c:0", "campo": "terreno"}], "advertencias": []},
            {"asignaciones": "todo", "advertencias": []},
        ]
        for mala in malas:
            with self.subTest(mala=mala), self.assertRaises(ia.FallaIAError):
                ia.validar(mala, self.IDS, self.CAMPOS)


class OpenAI(IACase):
    def test_request_shape_and_successful_parse(self):
        interp, pendientes = interpretacion()
        ids = {c.visible: c.id for c in interp.columnas}
        transporte = Transporte(respuesta_openai({
            "asignaciones": [{"columna": ids["Desarrollo"], "campo": "terreno", "motivo": "nombre"}],
            "advertencias": []}))
        self.con_transporte(transporte)
        resultado = ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
        self.assertEqual(resultado.estado, "ok")
        self.assertEqual(resultado.propuesta["asignaciones"][0]["campo"], "terreno")

        peticion, tiempo = transporte.peticiones[0]
        cuerpo = json.loads(peticion.data)
        self.assertEqual(peticion.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(peticion.get_header("Authorization"), "Bearer sk-prueba")
        self.assertEqual(cuerpo["model"], "modelo-de-prueba")
        self.assertTrue(cuerpo["response_format"]["json_schema"]["strict"])
        esquema = cuerpo["response_format"]["json_schema"]["schema"]
        enum = esquema["properties"]["asignaciones"]["items"]["properties"]["columna"]["enum"]
        self.assertEqual(set(enum), pendientes)
        self.assertIn("DATO", cuerpo["messages"][0]["content"])
        self.assertEqual(tiempo, 20.0)

        uso = self.usos()[0]
        self.assertEqual((uso["estado"], uso["tokens_entrada"], uso["tokens_salida"]), ("ok", 1200, 150))
        self.assertAlmostEqual(uso["costo_usd"], (1200 * 1 + 150 * 4) / 1e6)

    def test_failures_become_fallback_states(self):
        interp, pendientes = interpretacion()
        casos = [
            (Transporte(error=urllib.error.HTTPError("u", 429, "rate", {}, io.BytesIO())), "limite"),
            (Transporte(error=urllib.error.HTTPError("u", 500, "err", {}, io.BytesIO())), "error"),
            (Transporte(error=TimeoutError()), "tiempo"),
            (Transporte(respuesta=b"{no es json"), "invalido"),
            (Transporte(respuesta=respuesta_openai(None, refusal="no")), "rechazo"),
            (Transporte(respuesta=respuesta_openai({"asignaciones": [{"columna": "inventada", "campo": "terreno",
                                                                      "motivo": ""}], "advertencias": []})),
             "invalido"),
        ]
        for transporte, estado in casos:
            with self.subTest(estado=estado):
                self.con_transporte(transporte)
                resultado = ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
                self.assertEqual((resultado.estado, resultado.propuesta), (estado, None))
        self.assertTrue(all(u["estado"] != "reservado" for u in self.usos()))

    def test_nothing_about_the_file_is_logged(self):
        interp, pendientes = interpretacion()
        self.con_transporte(Transporte(respuesta=b"{no es json"))
        with self.assertLogs("ara.ia", level="WARNING") as registro:
            ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
        texto = " ".join(registro.output)
        self.assertNotIn("Desarrollo", texto)
        self.assertNotIn("Predio", texto)


class Presupuesto(IACase):
    def test_monthly_cap_is_enforced_before_calling(self):
        interp, pendientes = interpretacion()
        transporte = Transporte(respuesta_openai({"asignaciones": [], "advertencias": []}))
        self.con_transporte(transporte)
        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": "0.000001"}):
            resultado = ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
        self.assertEqual(resultado.estado, "presupuesto")
        self.assertEqual(transporte.peticiones, [])

    def test_spend_accumulates_and_persists(self):
        interp, pendientes = interpretacion()
        self.con_transporte(Transporte(respuesta_openai({"asignaciones": [], "advertencias": []},
                                                        uso=(1_000_000, 0))))
        with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": "1.5", "ARA_MAP_IA_MAX_SALIDA": "1"}):
            self.assertEqual(ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado, "ok")
            # $1.00 spent; the next worst case would pass $1.50 only if its estimate did.
            self.assertAlmostEqual(sum(u["costo_usd"] for u in self.usos()), 1.0)
            with patch.object(ia, "costo_maximo", return_value=0.6):
                self.assertEqual(ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado, "presupuesto")

    def test_hourly_limit(self):
        interp, pendientes = interpretacion()
        self.con_transporte(Transporte(respuesta_openai({"asignaciones": [], "advertencias": []})))
        with patch.dict(os.environ, {"ARA_MAP_IA_MAX_POR_HORA": "2"}):
            estados = [ia.sugerir(interp.columnas, interp.asignaciones, pendientes).estado for _ in range(3)]
        self.assertEqual(estados, ["ok", "ok", "limite"])


class Simulado(IACase):
    def test_simulated_provider_is_labelled_and_costs_nothing(self):
        interp, pendientes = interpretacion()
        with patch.dict(os.environ, {"ARA_MAP_IA_PROVEEDOR": "simulado", "ARA_MAP_IA_LIMITE_MENSUAL_USD": "0"}):
            resultado = ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
        self.assertEqual((resultado.estado, resultado.proveedor), ("ok", "simulado"))
        self.assertTrue(all("(simulado)" in a["motivo"] for a in resultado.propuesta["asignaciones"]))
        self.assertEqual(self.usos()[0]["costo_usd"], 0)

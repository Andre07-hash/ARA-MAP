"""Search and comparison over the master table (issue #69), through the real
HTTP dispatcher with real sessions.

SIMULATED PROVIDER ONLY: the real Anthropic adapter runs over a transport that
returns scripted, fictional Messages API bodies, one per call. No network, no
key, no spend. Fictional accounts and terrains (tests/test_roles_y_bases.py).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import uuid
from pathlib import Path
from unittest.mock import patch

from server import auth, postgres
from server.asistente import terreno as asistente
from tests.test_asistente_terreno import CLAVE, ENTORNO, NEGOCIO, mensaje
from tests.test_roles_y_bases import URL, Escenario, cuenta, filas, nuevo

BUSCAR = "/api/asistente-terreno/buscar"
RESULTADOS = "/api/asistente-terreno/resultados"
COMPARAR = "/api/asistente-terreno/comparar"
PREGUNTA = "Busca terrenos industriales en Jalisco de más de 10,000 m²"


def interpretacion(filtros, condiciones=None, aclaracion=None):
    """What the model is asked to return for a search, as its text."""
    if condiciones is None:
        condiciones = [{"texto": k, "filtro": "superficie" if k.startswith("superficie") else
                        "precio" if k.startswith("precio") or k == "moneda" else
                        "orden" if k == "descendente" else k} for k in filtros]
    return json.dumps({"condiciones": condiciones, "filtros": filtros, "aclaracion": aclaracion},
                      ensure_ascii=False)


class Guion:
    """The transport: one scripted answer per call, every request recorded."""

    def __init__(self, *textos, durante=None, error=None):
        self.textos, self.durante, self.error, self.peticiones = list(textos), durante, error, []

    def __call__(self, peticion, tiempo):
        self.peticiones.append(json.loads(peticion.data))
        if self.durante:
            self.durante()
        if self.error:
            raise self.error
        return mensaje(self.textos.pop(0)) if self.textos else mensaje("Resumen ficticio (simulado).")

    def enviado(self, n=-1):
        return self.peticiones[n]["messages"][0]["content"]


class Casos(Escenario):
    def preparar(self):
        self.levantar()
        self.addCleanup(asistente.fijar_proveedor, None)
        self.entorno(ENTORNO)
        # 23 matches: 8 unassigned, 15 in Base Uno; and others that must not match.
        self.coinciden = [self.nuevo_terreno(i, base=None if i < 8 else self.b1) for i in range(23)]
        self.nuevo_terreno(90, superficie_m2=9999)                         # too small
        self.nuevo_terreno(91, estado="Colima")                            # elsewhere
        self.nuevo_terreno(92, tipo_terreno="Agrícola")                    # another type
        self.nuevo_terreno(93, superficie_m2=None, superficie_ha=5)        # area only in ha

    def entorno(self, valores):
        entorno = patch.dict(os.environ, valores)
        entorno.start()
        self.addCleanup(entorno.stop)

    def nuevo_terreno(self, n, base=None, **campos):
        datos = {"terreno": f"Lote Ficticio {n:02d}", "estado": "Jalisco", "municipio": "Zapopan",
                 "tipo_terreno": "Industrial", "superficie_m2": 10000 + n * 100,
                 "notas_internas": "NOTA-SECRETA", "contacto": "CONTACTO-SECRETO",
                 "direccion": "DIRECCION-SECRETA", "lat": 20.5, "lon": -103.4, **campos}
        ruta = f"/api/maestra/bases/{base}/terrenos" if base else "/api/inventario/terrenos"
        return self.ok(self.call("POST", ruta, datos,
                                 headers={"Idempotency-Key": f"clave-{nuevo()}"}))["terreno"]["id"]

    def guion(self, *textos, **kw):
        guion = Guion(*textos, **kw)
        asistente.fijar_proveedor(asistente.ProveedorAnthropic(guion))
        return guion

    def buscar(self, pregunta=PREGUNTA, user="ada"):
        return self.call("POST", BUSCAR, {"pregunta": pregunta}, user)

    def codigo(self, respuesta, status, code):
        self.assertEqual((respuesta[0], respuesta[1]["detalle"]["code"]), (status, code), respuesta)

    def negocio(self):
        return {t: filas(t) for t in NEGOCIO}

    def elegir(self, *ids):
        return {"terrenos": [{"id": i, "version": self.version(i)} for i in ids]}

    # -- search ------------------------------------------------------------------

    def test_search_covers_the_whole_inventory_page_by_page(self):
        guion = self.guion(interpretacion({"tipo_terreno": ["industriales"], "estado": ["jalisco"],
                                           "superficie_m2_min": 10000}))
        antes = self.negocio()
        primera = self.ok(self.buscar())
        self.assertEqual((primera["estado"], primera["origen"], primera["total"]),
                         ("resultados", "modelo", 23))
        self.assertEqual(primera["filtros"], {"tipo_terreno": ["Industrial"], "estado": ["Jalisco"],
                                              "superficie_m2_min": 10000.0})
        self.assertEqual([c["texto"] for c in primera["criterios"]], [
            "Estado: Jalisco", "Tipo de terreno: Industrial",
            "Superficie registrada: al menos 10,000 m²"])
        vistos, pagina = [], primera
        while True:
            self.assertLessEqual(len(pagina["terrenos"]), 10)
            self.assertEqual(pagina["total"], 23)       # the real total, on every page
            vistos += [t["terreno_id"] for t in pagina["terrenos"]]
            if not pagina["next_cursor"]:
                break
            pagina = self.ok(self.call("POST", RESULTADOS, {"filtros": pagina["filtros"],
                                                            "cursor": pagina["next_cursor"]}))
            self.assertEqual(pagina["origen"], "reglas")
        self.assertEqual(sorted(vistos), sorted(self.coinciden))
        self.assertEqual(len(guion.peticiones), 1)      # paging never asks the model again
        sin_base = [t for t in primera["terrenos"] if t["base_id"] is None]
        self.assertTrue(sin_base, "unassigned terrains are part of the master table")
        resultado = primera["terrenos"][0]
        self.assertEqual(set(resultado), {"terreno_id", "version", "nombre", "base_id", "campos_usados"})
        self.assertEqual(self.negocio(), antes)

        # Only the question and the fixed instructions reach the provider.
        cuerpo = guion.peticiones[0]
        self.assertEqual(cuerpo["messages"][0]["content"],
                         '<peticion>"Busca terrenos industriales en Jalisco de más de 10,000 m²"</peticion>')
        todo = json.dumps(cuerpo, ensure_ascii=False)
        for nada in ("Lote Ficticio", "Zapopan", "Colima", "NOTA", "CONTACTO", "DIRECCION",
                     self.coinciden[0], self.b1, CLAVE):
            self.assertNotIn(nada, todo)

    def test_combined_filters_price_order_and_zero_results(self):
        self.ok(self.patch(self.coinciden[0], {"moneda": "MXN", "asking_m2": 900,
                                               "availability": "available"}, "ada"))
        self.ok(self.patch(self.coinciden[1], {"moneda": "USD", "asking_m2": 50,
                                               "availability": "available"}, "ada"))
        self.guion(interpretacion({"municipio": ["zapopan"], "precio_max": 1000, "moneda": "MXN",
                                   "precio_base": "por_m2", "disponibilidad": ["available"],
                                   "orden": "superficie_m2", "descendente": True}))
        cuerpo = self.ok(self.buscar("Disponibles en Zapopan a menos de 1000 MXN por m²"))
        self.assertEqual([t["terreno_id"] for t in cuerpo["terrenos"]], [self.coinciden[0]])
        self.assertEqual(cuerpo["total"], 1)
        self.assertIn("Precio por m²: como máximo MXN 1,000", [c["texto"] for c in cuerpo["criterios"]])
        self.assertIn("Orden: Superficie (m²), descendente", [c["texto"] for c in cuerpo["criterios"]])

        self.guion(interpretacion({"estado": ["Jalisco"], "superficie_m2_min": 1e9}))
        vacio = self.ok(self.buscar("Terrenos en Jalisco de más de mil millones de m²"))
        self.assertEqual((vacio["estado"], vacio["total"], vacio["terrenos"], vacio["next_cursor"]),
                         ("resultados", 0, [], None))

    def test_what_cannot_run_exactly_is_a_clarification_never_a_list(self):
        casos = [
            (interpretacion({}, [{"texto": "cerca del mar", "filtro": None}]), "modelo", "«cerca del mar»"),
            (interpretacion({"estado": ["Jalisco"]}, [{"texto": "en Jalisco", "filtro": "estado"},
                                                      {"texto": "de 5 hectáreas", "filtro": None}]),
             "modelo", "«de 5 hectáreas»"),
            (interpretacion({}, [], aclaracion="¿Te refieres a precio total o por m²?"), "modelo",
             "precio total o por m²"),
            (interpretacion({}, []), "reglas", "al menos un criterio"),
            (interpretacion({"orden": "superficie_m2"}), "reglas", "al menos un criterio"),
            (interpretacion({"estado": ["Narnia"]}), "reglas", "«Narnia»"),
            (interpretacion({"estado": ["Jal"]}), "reglas", "parecidos: Jalisco"),
            (interpretacion({"precio_max": 5, "precio_base": "total"}), "reglas", "moneda"),
            (interpretacion({"precio_max": 5, "moneda": "MXN"}), "reglas", "total o por m²"),
            (interpretacion({"moneda": "MXN"}), "reglas", "precio mínimo o máximo"),
            (interpretacion({"superficie_m2_min": 9, "superficie_m2_max": 1}), "reglas", "mínimo es mayor"),
        ]
        antes = self.negocio()
        for texto, origen, frase in casos:
            with self.subTest(frase=frase):
                self.guion(texto)
                cuerpo = self.ok(self.buscar("algo"))
                self.assertEqual((cuerpo["estado"], cuerpo["origen"]), ("aclaracion", origen))
                self.assertIn(frase, cuerpo["aclaracion"])
                self.assertNotIn("terrenos", cuerpo)
                self.assertNotIn("total", cuerpo)
        self.assertEqual(self.negocio(), antes)

    def test_a_malformed_interpretation_is_rejected_whole(self):
        malos = [
            "no es json", "```json\n[]\n```",
            json.dumps({"condiciones": [], "filtros": {}, "aclaracion": None, "sql": "DROP"}),
            interpretacion({"estado": ["Jalisco"], "codigo": "x"}),
            interpretacion({"orden": "superficie_m2; DROP TABLE"}),
            interpretacion({"precio_base": ["total"]}),
            interpretacion({"moneda": {"a": 1}}),
            interpretacion({"superficie_m2_min": "10000"}),
            interpretacion({"superficie_m2_min": -1}),
            interpretacion({"superficie_m2_min": True}),
            interpretacion({"estado": "Jalisco"}),
            interpretacion({"estado": []}),
            interpretacion({"disponibilidad": ["vendida"]}),
            # A condition named without its filter, or a filter without a condition.
            interpretacion({}, [{"texto": "en Jalisco", "filtro": "estado"}]),
            interpretacion({"estado": ["Jalisco"]}, []),
            interpretacion({}, [{"texto": "x", "filtro": "base"}]),
        ]
        for texto in malos:
            with self.subTest(texto=texto[:50]):
                self.guion(texto)
                self.codigo(self.buscar("algo"), 503, "chat_respuesta_invalida")
        # A fenced but valid object is accepted.
        self.guion("```json\n" + interpretacion({"estado": ["Jalisco"]}) + "\n```")
        self.assertEqual(self.ok(self.buscar("En Jalisco"))["total"], 26)  # all but Colima

    def test_pages_are_checked_again_on_the_server(self):
        self.guion(interpretacion({"estado": ["Jalisco"]}))
        primera = self.ok(self.buscar("En Jalisco"))
        casos = [
            {"filtros": primera["filtros"]},
            {"filtros": primera["filtros"], "cursor": ""},
            {"filtros": primera["filtros"], "cursor": "no-es-cursor"},
            {"filtros": {**primera["filtros"], "sql": "x"}, "cursor": primera["next_cursor"]},
            {"filtros": {"estado": ["Narnia"]}, "cursor": primera["next_cursor"]},
            {"filtros": primera["filtros"], "cursor": primera["next_cursor"], "pregunta": "x"},
        ]
        for cuerpo in casos:
            with self.subTest(cuerpo=str(cuerpo)[:60]):
                self.codigo(self.call("POST", RESULTADOS, cuerpo), 422, "validation_failed")

    def test_search_is_for_administrators_and_off_by_default(self):
        guion = self.guion()
        for ruta, cuerpo in ((BUSCAR, {"pregunta": "x"}),
                             (RESULTADOS, {"filtros": {"estado": ["Jalisco"]}, "cursor": "x"}),
                             (COMPARAR, self.elegir(*self.coinciden[:2]))):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.call("POST", ruta, cuerpo, user=None)[0], 401)
                self.codigo(self.call("POST", ruta, cuerpo, "olga"), 403, "forbidden")
                self.codigo(self.call("POST", ruta, cuerpo, "otto"), 403, "forbidden")
        self.entorno({"ARA_MAP_CHAT_HABILITADO": ""})
        self.codigo(self.buscar(), 503, "chat_deshabilitado")
        self.codigo(self.call("POST", COMPARAR, self.elegir(*self.coinciden[:2])), 503, "chat_deshabilitado")
        self.assertEqual(guion.peticiones, [])
        self.entorno({"ARA_MAP_CHAT_HABILITADO": "1", "ARA_MAP_CHAT_CLAVE": ""})
        self.codigo(self.buscar(), 503, "chat_no_configurado")
        for cuerpo in ({}, {"pregunta": ""}, {"pregunta": "x" * 501}, {"pregunta": "x", "filtros": {}}):
            self.codigo(self.call("POST", BUSCAR, cuerpo), 422, "validation_failed")

    def test_a_session_ended_while_interpreting_gets_nothing(self):
        token = self.cookies["ada"].split("=", 1)[1]
        self.guion(interpretacion({"estado": ["Jalisco"]}),
                   durante=lambda: cuenta(lambda c: auth.logout(c, token)))
        self.assertEqual(self.buscar()[0], 401)

    # -- comparison ----------------------------------------------------------------

    def test_two_terrains_compared_from_their_allowed_fields(self):
        a, b = self.coinciden[0], self.coinciden[9]
        self.ok(self.patch(a, {"asking_price": 1500000, "moneda": "MXN", "availability": "available"}, "ada"))
        guion = self.guion("El terreno A tiene precio registrado; el B no. (simulado)")
        antes = self.negocio()
        cuerpo = self.ok(self.call("POST", COMPARAR, self.elegir(a, b)))
        self.assertEqual(self.negocio(), antes)
        self.assertEqual([(t["alias"], t["terreno_id"], t["nombre"], t["base_id"]) for t in cuerpo["terrenos"]],
                         [("A", a, "Lote Ficticio 00", None), ("B", b, "Lote Ficticio 09", self.b1)])
        valores = {f["campo"]: f["valores"] for f in cuerpo["filas"]}
        self.assertEqual([f["etiqueta"] for f in cuerpo["filas"]], [
            "Estado", "Municipio", "Tipo de terreno", "Superficie (m²)", "Superficie (ha)",
            "Precio total", "Precio por m²", "Moneda", "Precio a consultar", "Disponibilidad"])
        self.assertEqual(valores["superficie_m2"], ["10,000 m²", "10,900 m²"])
        self.assertEqual(valores["asking_price"], ["MXN 1,500,000", "Sin información registrada"])
        self.assertEqual(valores["superficie_ha"], ["Sin información registrada"] * 2)
        self.assertEqual(valores["availability"], ["Disponible", "Sin información registrada"])
        self.assertEqual(cuerpo["advertencias"], [])
        self.assertEqual(cuerpo["resumen"], {"estado": "ok", "origen": "modelo",
                                             "texto": "El terreno A tiene precio registrado; el B no. (simulado)"})
        enviado = guion.enviado()
        datos = json.loads(enviado.split("<datos>")[1].split("</datos>")[0])
        self.assertEqual(set(datos["terrenos"]), {"Terreno A", "Terreno B"})
        self.assertEqual(datos["terrenos"]["Terreno A"]["campos"]["Precio total"], "MXN 1,500,000")
        todo = json.dumps(guion.peticiones, ensure_ascii=False)
        for nada in ("Lote Ficticio", a, b, self.b1, "Base Uno", "NOTA", "CONTACTO", "DIRECCION",
                     "20.5", "103.4", CLAVE):
            self.assertNotIn(nada, todo)

    def test_three_terrains_with_different_currencies_and_units(self):
        a, b, c = self.coinciden[2], self.coinciden[3], self.nuevo_terreno(94, superficie_m2=None,
                                                                             superficie_ha=2.5)
        self.ok(self.patch(a, {"asking_price": 100, "moneda": "USD"}, "ada"))
        self.ok(self.patch(b, {"asking_price": 2000, "moneda": "MXN"}, "ada"))
        self.guion()
        cuerpo = self.ok(self.call("POST", COMPARAR, self.elegir(a, b, c)))
        valores = {f["campo"]: f["valores"] for f in cuerpo["filas"]}
        self.assertEqual(valores["asking_price"], ["USD 100", "MXN 2,000", "Sin información registrada"])
        self.assertEqual(valores["superficie_m2"], ["10,200 m²", "10,300 m²", "Sin información registrada"])
        self.assertEqual(valores["superficie_ha"][2], "2.5 ha")
        self.assertEqual(cuerpo["advertencias"], [
            "Los precios están en monedas distintas (MXN, USD); no se comparan como equivalentes.",
            "Algunas superficies sólo están registradas en hectáreas y otras en m²; no se convierten."])
        self.assertEqual([t["alias"] for t in cuerpo["terrenos"]], ["A", "B", "C"])

    def test_same_names_stay_distinguishable(self):
        a = self.nuevo_terreno(95, terreno="Lote Repetido")
        b = self.nuevo_terreno(96, terreno="Lote Repetido", base=self.b2, municipio="Guadalajara")
        self.guion()
        cuerpo = self.ok(self.call("POST", COMPARAR, self.elegir(a, b)))
        self.assertEqual([(t["nombre"], t["terreno_id"], t["base_id"]) for t in cuerpo["terrenos"]],
                         [("Lote Repetido", a, None), ("Lote Repetido", b, self.b2)])
        self.assertEqual({f["campo"]: f["valores"] for f in cuerpo["filas"]}["municipio"],
                         ["Zapopan", "Guadalajara"])

    def test_the_selection_is_validated_before_anything(self):
        guion = self.guion()
        uno, dos, tres, cuatro = self.coinciden[:4]
        casos = [
            ({"terrenos": []}, 422), (self.elegir(uno), 422), (self.elegir(uno, dos, tres, cuatro), 422),
            ({"terrenos": [{"id": uno, "version": 1}, {"id": uno, "version": 1}]}, 422),
            ({"terrenos": [{"id": "no-uuid", "version": 1}, {"id": dos, "version": 1}]}, 422),
            ({"terrenos": [{"id": uno, "version": "1"}, {"id": dos, "version": 1}]}, 422),
            ({"terrenos": [{"id": uno, "version": 1, "nombre": "x"}, {"id": dos, "version": 1}]}, 422),
            ({"terrenos": [uno, dos]}, 422),
            ({**self.elegir(uno, dos), "pregunta": "x"}, 422),
            ({"terrenos": [{"id": str(uuid.uuid4()), "version": 1}, {"id": dos, "version": 1}]}, 404),
            ({"terrenos": [{"id": uno, "version": 99}, {"id": dos, "version": 1}]}, 409),
        ]
        for cuerpo, status in casos:
            with self.subTest(cuerpo=str(cuerpo)[:70]):
                self.assertEqual(self.call("POST", COMPARAR, cuerpo)[0], status)
        self.assertEqual(guion.peticiones, [])

    def test_changes_while_summarizing_discard_the_whole_answer(self):
        cambios = {
            "editado": (lambda b: self.ok(self.patch(b, {"estado": "Colima"}, "alan")), 409),
            "borrado": (lambda b: self.ok(self.call("POST", f"/api/inventario/terrenos/{b}/borrar",
                                                    {"expected_version": self.version(b)}, "alan")), 404),
            "sesion": (lambda b: cuenta(lambda c: auth.logout(c, self.cookies["ada"].split("=", 1)[1])), 401),
        }
        for n, (nombre, (cambio, status)) in enumerate(cambios.items()):
            with self.subTest(cambio=nombre):
                a, b = self.coinciden[10 + 2 * n], self.coinciden[11 + 2 * n]
                cuerpo = self.elegir(a, b)
                cambio = (lambda f, b: lambda: f(b))(cambio, b)
                self.guion(durante=cambio)
                respuesta = self.call("POST", COMPARAR, cuerpo)
                self.assertEqual(respuesta[0], status, respuesta)
                self.assertNotIn("simulado", json.dumps(respuesta[1]))

    def test_a_failed_summary_still_shows_the_factual_table(self):
        a, b = self.coinciden[6], self.coinciden[7]
        self.guion(error=urllib.error.URLError("timed out"))
        cuerpo = self.ok(self.call("POST", COMPARAR, self.elegir(a, b)))
        self.assertEqual(cuerpo["resumen"]["estado"], "error")
        self.assertEqual(cuerpo["resumen"]["code"], "chat_tiempo")
        self.assertNotIn("texto", cuerpo["resumen"])
        self.assertEqual(len(cuerpo["filas"]), 10)

    def test_interpretation_and_summaries_share_the_limits(self):
        self.entorno({"ARA_MAP_CHAT_MAX_POR_HORA": "1"})
        self.guion(interpretacion({"estado": ["Jalisco"]}))
        self.ok(self.buscar("En Jalisco"))
        cuerpo = self.ok(self.call("POST", COMPARAR, self.elegir(*self.coinciden[:2])))
        self.assertEqual(cuerpo["resumen"]["code"], "chat_limite")
        self.codigo(self.buscar("En Jalisco"), 429, "chat_limite")
        self.assertEqual([u["estado"] for u in filas("uso_ia")], ["ok"])


class BusquedaSqlite(Casos, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.entorno({"ARA_MAP_DB": str(Path(self._dir.name) / "prueba.db"),
                      "ARA_MAP_DATABASE_URL": "", "DATABASE_URL": ""})
        self.preparar()


@unittest.skipUnless(URL, "No Postgres test connection configured")
class BusquedaPostgres(Casos, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.schema = "test_ara_busqueda_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {
            "ARA_MAP_DATABASE_URL": make_conninfo(URL, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def setUp(self):
        with postgres.session() as conn:
            conn.raw.execute("TRUNCATE team_user, team_login_failure, uso_ia CASCADE")
        self.preparar()



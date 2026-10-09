"""Base-local custom columns and their values (round 2, packet 2A).

Through the real HTTP dispatcher with real sessions, on SQLite and (when
ARA_MAP_TEST_DATABASE_URL is set) on a disposable Postgres schema. The fixture
is the one of tests/test_roles_y_bases.py: administrators ada and alan;
operators olga (Base Uno), omar (Base Uno and Base Dos), otto (no grant); t1
in Base Uno, t2 in Base Dos, t0 unassigned, ta archived in Base Uno, t3 in the
archived base.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import columnas, postgres
from server.api import columnas as api_columnas
from server.api import inventario as api_inventario
from server.api import maestra as api_maestra
from server.web_util import encode
from tests.test_roles_y_bases import URL, Escenario, filas, nuevo

BASE_NO_EXISTE = (404, {"error": "La base de trabajo no existe.", "detalle": {"code": "not_found"}})
TERRENO_NO_EXISTE = (404, {"error": "El terreno no existe.", "detalle": {"code": "not_found"}})
DESCONOCIDA = "Columna desconocida o retirada."
SECRETO = "VALOR-SOLO-DE-BASE-UNO"


class Columnas(Escenario):
    """The checks. Mixed into one TestCase per backend."""

    def ruta(self, base, columna=None, accion=None):
        partes = [f"/api/maestra/bases/{base}/columnas"]
        if columna:
            partes.append(columna.split(":")[-1])
        if accion:
            partes.append(accion)
        return "/".join(partes)

    def crear(self, base, nombre, tipo="texto", user="ada", key=None, **extra):
        return self.call("POST", self.ruta(base), {"nombre": nombre, "tipo": tipo, **extra}, user,
                         {"Idempotency-Key": key or f"clave-{nuevo()}"})

    def columna(self, base, nombre, tipo="texto", **extra):
        return self.ok(self.crear(base, nombre, tipo, **extra))["columna"]

    def lista(self, base, user="ada", retiradas=False):
        return self.call("GET", self.ruta(base) + ("?retiradas=1" if retiradas else ""), user=user)

    def nombres(self, base, **kwargs):
        return [c["nombre"] for c in self.ok(self.lista(base, **kwargs))["columnas"]]

    def actual(self, col):
        return next(c for c in self.ok(self.lista(col["base_id"], retiradas=True))["columnas"]
                    if c["id"] == col["id"])

    def cambiar(self, col, user="ada", accion=None, **cuerpo):
        cuerpo.setdefault("expected_version", self.actual(col)["version"])
        return self.call("POST" if accion else "PATCH", self.ruta(col["base_id"], col["id"], accion),
                         cuerpo, user)

    def guardar(self, terreno, custom, user="olga", cambios=None, version=None):
        cuerpo = {"expected_version": version or self.version(terreno), "custom": custom}
        if cambios is not None:
            cuerpo["changes"] = cambios
        return self.call("PATCH", f"/api/inventario/terrenos/{terreno}", cuerpo, user)

    def ver(self, terreno, user="olga", sufijo=""):
        return self.call("GET", f"/api/inventario/terrenos/{terreno}{sufijo}", user=user)

    def guardado(self, terreno):
        """The custom map the terrain's current revision stores, whole."""
        fila = filas("inventory_revision", "id = (SELECT draft_revision_id FROM inventory_terrain"
                     " WHERE id = ?)", (terreno,))[0]
        return json.loads(fila["custom_json"])

    def huella(self, terreno):
        return (self.version(terreno), self.cuenta("inventory_revision", "inventory_id = ?", (terreno,)),
                self.cuenta("inventory_event", "inventory_id = ?", (terreno,)))

    def transferir(self, terreno, base):
        return self.ok(self.call("POST", f"/api/inventario/terrenos/{terreno}/transferir",
                                 {"expected_version": self.version(terreno), "base_id": base}))

    # -- 1. definitions ----------------------------------------------------------

    def test_definitions_are_created_listed_and_idempotent_per_actor_and_base(self):
        terrenos = filas("inventory_terrain")
        status, body = self.crear(self.b1, "  Uso   de suelo ", key="clave-columna-01", user="olga")
        col = body["columna"]
        self.assertEqual(status, 200)
        self.assertEqual(columnas.id_de_clave(col["id"]), col["id"][7:])
        self.assertEqual({k: col[k] for k in ("base_id", "nombre", "tipo", "opciones", "orden",
                                              "version", "retirada")},
                         {"base_id": self.b1, "nombre": "Uso de suelo", "tipo": "texto",
                          "opciones": [], "orden": 1, "version": 1, "retirada": False})
        # The same key and body: the same definition, however many times.
        self.assertEqual(self.crear(self.b1, "Uso de suelo", key="clave-columna-01", user="olga")[1], body)
        status, otro = self.crear(self.b1, "Otra cosa", key="clave-columna-01", user="olga")
        self.assertEqual((status, otro["detalle"]["code"]), (409, "idempotency_conflict"))
        self.assertEqual(self.nombres(self.b1), ["Uso de suelo"])
        # The key is one actor's in one base: elsewhere it is another key.
        self.assertEqual(self.crear(self.b2, "Uso de suelo", key="clave-columna-01", user="omar")[0], 200)
        status, body = self.crear(self.b1, "Uso de suelo", key="clave-columna-01", user="omar")
        self.assertEqual((status, body["detalle"]["code"]), (409, "nombre_duplicado"))
        self.assertEqual(self.crear(self.b1, "Corredor", key="clave-columna-01", user="omar")[0], 200)

        tipos = [self.columna(self.b1, "Avance", "numero"), self.columna(self.b1, "Visita", "fecha"),
                 self.columna(self.b1, "Etapa", "opcion", opciones=[" En  curso ", "Cerrado"])]
        self.assertEqual([c["orden"] for c in tipos], [3, 4, 5])
        self.assertEqual(tipos[2]["opciones"], ["En curso", "Cerrado"])
        self.assertEqual(self.nombres(self.b1, user="olga"),
                         ["Uso de suelo", "Corredor", "Avance", "Visita", "Etapa"])
        self.assertEqual(self.nombres(self.b2, user="omar"), ["Uso de suelo"])

        # One audit event per definition version, with the actor; no terrain was touched.
        eventos = filas("maestra_base_event", "column_id = ?", (col["id"][7:],))
        self.assertEqual([(e["version"], e["action"], e["actor_id"], e["base_id"]) for e in eventos],
                         [(1, "columna_crear", self.ids["olga"], self.b1)])
        self.assertEqual(filas("inventory_terrain"), terrenos)
        self.assertEqual({b["version"] for b in filas("maestra_base") if b["id"] in (self.b1, self.b2)},
                         {2})  # the grants of the fixture; column changes do not move a base's version

    def test_definition_input_is_bounded_and_the_type_is_fixed(self):
        malos = (({"nombre": "", "tipo": "texto"}, "nombre"),
                 ({"nombre": "x" * 101, "tipo": "texto"}, "nombre"),
                 ({"nombre": 7, "tipo": "texto"}, "nombre"),
                 ({"nombre": "municipio", "tipo": "texto"}, "nombre"),     # a core column's label
                 ({"nombre": "ASKING $/M2", "tipo": "numero"}, "nombre"),
                 ({"nombre": "A", "tipo": "archivo"}, "tipo"),
                 ({"nombre": "A", "tipo": "kmz"}, "tipo"),
                 ({"nombre": "A"}, "tipo"),
                 ({"nombre": "A", "tipo": "opcion"}, "opciones"),
                 ({"nombre": "A", "tipo": "opcion", "opciones": []}, "opciones"),
                 ({"nombre": "A", "tipo": "opcion", "opciones": ["a", "a"]}, "opciones"),
                 ({"nombre": "A", "tipo": "opcion", "opciones": ["a", 3]}, "opciones"),
                 ({"nombre": "A", "tipo": "opcion", "opciones": ["x" * 101]}, "opciones"),
                 ({"nombre": "A", "tipo": "opcion", "opciones": [str(n) for n in range(101)]}, "opciones"),
                 ({"nombre": "A", "tipo": "texto", "opciones": ["a"]}, "opciones"),
                 ({"nombre": "A", "tipo": "texto", "id": nuevo()}, "id"),
                 ({"nombre": "A", "tipo": "texto", "base_id": self.b2}, "base_id"))
        for cuerpo, campo in malos:
            status, body = self.call("POST", self.ruta(self.b1), cuerpo, "ada",
                                     {"Idempotency-Key": f"clave-{nuevo()}"})
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [campo]), cuerpo)
        self.assertEqual(self.call("POST", self.ruta(self.b1), {"nombre": "A", "tipo": "texto"})[1]
                         ["detalle"]["code"], "idempotency_key_required")
        self.assertEqual(self.nombres(self.b1), [])

        col = self.columna(self.b1, "Etapa", "opcion", opciones=["Uno", "Dos"])
        for cuerpo, campo in (({"tipo": "texto"}, "tipo"), ({"id": nuevo()}, "id"),
                              ({"nombre": "Estado"}, "nombre"), ({"posicion": -1}, "posicion"),
                              ({"posicion": True}, "posicion"), ({"opciones": "Uno"}, "opciones"),
                              ({"expected_version": "1"}, "expected_version")):
            status, body = self.cambiar(col, **cuerpo)
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [campo]), cuerpo)
        # Choices are added after the existing ones; none is removed, renamed or reordered.
        for opciones in (["Uno"], ["Dos", "Uno"], ["Uno", "DOS"], ["Uno", "Tres", "Dos"]):
            status, body = self.cambiar(col, opciones=opciones)
            self.assertEqual((status, body["detalle"]["code"]), (409, "opciones_solo_se_agregan"))
        status, body = self.cambiar(col, opciones=["Uno", "Dos", "Tres"])
        self.assertEqual((status, body["columna"]["opciones"], body["columna"]["version"]),
                         (200, ["Uno", "Dos", "Tres"], 2))
        texto = self.columna(self.b1, "Nota")
        status, body = self.cambiar(texto, opciones=["a"])
        self.assertEqual((status, body["detalle"]["code"]), (409, "sin_opciones"))
        self.assertEqual(self.actual(col)["tipo"], "opcion")

        # A base holds a bounded number of live columns; retiring one makes room.
        for n in range(columnas.MAX_COLUMNAS - 2):
            self.columna(self.b1, f"Columna {n}")
        status, body = self.crear(self.b1, "Una de más")
        self.assertEqual((status, body["detalle"]["code"]), (409, "limite_columnas"))
        self.ok(self.cambiar(texto, accion="retirar"))
        self.assertEqual(self.crear(self.b1, "Una de más")[0], 200)
        status, body = self.cambiar(texto, accion="restaurar")
        self.assertEqual((status, body["detalle"]["code"]), (409, "limite_columnas"))

    def test_rename_order_retire_and_restore_are_versioned_and_audited(self):
        a, b, c = (self.columna(self.b1, n) for n in ("Alfa", "Beta", "Gama"))
        status, body = self.cambiar(b, user="olga", nombre="Beta dos")
        self.assertEqual((status, body["columna"]["nombre"], body["columna"]["version"],
                          body["columna"]["id"]), (200, "Beta dos", 2, b["id"]))
        # A stale version changes nothing and reports the definition as it is.
        status, body = self.cambiar(b, nombre="Tarde", expected_version=1)
        self.assertEqual((status, body["detalle"]["code"], body["detalle"]["columna"]["nombre"]),
                         (409, "conflict", "Beta dos"))
        # The same name is not a change; another column's name is refused, accents and case aside.
        self.assertEqual(self.cambiar(b, nombre="Beta dos")[1]["columna"]["version"], 2)
        status, body = self.cambiar(b, nombre="ALFÁ")
        self.assertEqual((status, body["detalle"]["code"]), (409, "nombre_duplicado"))

        # Moving one column gives that one a new version; the others keep theirs.
        status, body = self.cambiar(c, posicion=0)
        self.assertEqual((status, body["columna"]["version"]), (200, 2))
        self.assertEqual(self.nombres(self.b1), ["Gama", "Alfa", "Beta dos"])
        self.assertEqual([self.actual(x)["version"] for x in (a, b)], [1, 2])
        self.assertEqual(self.cambiar(c, posicion=0)[1]["columna"]["version"], 2)
        self.ok(self.cambiar(c, posicion=40, nombre="Gama final"))
        self.assertEqual(self.nombres(self.b1), ["Alfa", "Beta dos", "Gama final"])

        status, body = self.cambiar(a, accion="retirar", user="olga")
        self.assertEqual((status, body["columna"]["retirada"], body["columna"]["version"]), (200, True, 2))
        self.assertEqual(self.nombres(self.b1), ["Beta dos", "Gama final"])
        self.assertEqual(self.nombres(self.b1, retiradas=True, user="olga")[-1], "Alfa")
        for intento, codigo in ((dict(accion="retirar"), "columna_retirada"),
                                (dict(nombre="Otra"), "columna_retirada"),
                                (dict(posicion=1), "columna_retirada")):
            status, body = self.cambiar(a, **intento)
            self.assertEqual((status, body["detalle"]["code"]), (409, codigo))
        # Its name is free while it is retired, and blocks its return while taken.
        nueva = self.columna(self.b1, "Alfa")
        status, body = self.cambiar(a, accion="restaurar")
        self.assertEqual((status, body["detalle"]["code"]), (409, "nombre_duplicado"))
        self.ok(self.cambiar(nueva, nombre="Alfa nueva"))
        status, body = self.cambiar(a, accion="restaurar")
        self.assertEqual((status, body["columna"]["retirada"], body["columna"]["id"],
                          body["columna"]["version"]), (200, False, a["id"], 3))
        status, body = self.cambiar(a, accion="restaurar")
        self.assertEqual((status, body["detalle"]["code"]), (409, "columna_no_retirada"))

        eventos = filas("maestra_base_event", "column_id = ?", (a["id"][7:],))
        self.assertEqual(sorted((e["version"], e["action"], e["actor_id"]) for e in eventos),
                         [(1, "columna_crear", self.ids["ada"]), (2, "columna_retirar", self.ids["olga"]),
                          (3, "columna_restaurar", self.ids["ada"])])
        self.assertTrue(all(e["at"] and e["actor_name"] for e in eventos))
        movida = [json.loads(e["details_json"]) for e in filas(
            "maestra_base_event", "column_id = ? AND version = 3", (c["id"][7:],))]
        self.assertEqual(movida, [{"nombre": {"antes": "Gama", "despues": "Gama final"},
                                   "posicion": {"antes": 0, "despues": 2}}])
        # None of it gave any terrain a new version.
        self.assertEqual({t["version"] for t in filas("inventory_terrain")}, {1})

    def test_definitions_follow_the_base_scope_and_an_archived_base_is_read_only(self):
        col = self.columna(self.b1, "Privada")
        fuera = [self.lista(self.b1, "otto"), self.lista(self.b2, "olga"), self.lista(nuevo()),
                 self.lista(self.b3, "olga"),  # granted, but archived: closed to operators
                 self.crear(self.b1, "X", user="otto"), self.crear(self.b2, "X", user="olga"),
                 self.call("POST", self.ruta(self.b2), {"tipo": 9}, "olga"),
                 self.cambiar(col, "otto", nombre="X", expected_version=1),
                 self.cambiar(col, "otto", accion="retirar", expected_version=1),
                 self.call("PATCH", self.ruta(self.b2, col["id"]), {"expected_version": "x"}, "olga")]
        self.assertEqual({encode(r) for r in fuera}, {encode(BASE_NO_EXISTE)})
        # In scope, a column of another base, or none, is one answer.
        ajena = self.columna(self.b2, "De la dos")
        no_hay = (404, {"error": "La columna no existe.", "detalle": {"code": "not_found"}})
        for ruta in (self.ruta(self.b1, ajena["id"]), self.ruta(self.b1, nuevo()),
                     self.ruta(self.b1) + "/no-es-un-id"):
            self.assertEqual(self.call("PATCH", ruta, {"expected_version": 1, "nombre": "Y"}, "olga"), no_hay)
            self.assertEqual(self.call("POST", ruta + "/retirar", {}, "ada"), no_hay)
        self.assertEqual(self.actual(ajena)["nombre"], "De la dos")

        # An archived base: administrators still read its definitions; nobody changes them.
        self.ok(self.archivar(self.b1))
        self.assertEqual(self.nombres(self.b1), ["Privada"])
        for respuesta in (self.crear(self.b1, "Z"), self.cambiar(col, nombre="Z"),
                          self.cambiar(col, accion="retirar")):
            self.assertEqual((respuesta[0], respuesta[1]["detalle"]["code"]), (409, "base_archivada"))
        self.assertEqual(self.crear(self.b1, "Z", user="olga"), BASE_NO_EXISTE)
        self.ok(self.archivar(self.b1, "restaurar"))
        self.assertEqual(self.cambiar(col, "olga", nombre="Z")[0], 200)

    # -- 2. values ---------------------------------------------------------------

    def test_values_are_validated_by_type_and_saved_as_sent(self):
        texto, numero, fecha, opcion = (
            self.columna(self.b1, "Nota"), self.columna(self.b1, "Avance", "numero"),
            self.columna(self.b1, "Visita", "fecha"),
            self.columna(self.b1, "Etapa", "opcion", opciones=["En curso", "Cerrado"]))
        buenos = {texto["id"]: "  Junto al río  ", numero["id"]: -12.5, fecha["id"]: "2024-02-29",
                  opcion["id"]: "Cerrado"}
        status, body = self.guardar(self.t1, buenos)
        esperado = {**buenos, texto["id"]: "Junto al río"}
        self.assertEqual((status, body["terreno"]["custom"], body["terreno"]["version"]), (200, esperado, 2))
        self.assertEqual(self.guardado(self.t1), esperado)
        self.assertEqual(self.ver(self.t1)[1]["terreno"]["custom"], esperado)
        self.assertEqual(self.guardar(self.t1, {numero["id"]: 7})[1]["terreno"]["custom"][numero["id"]], 7)

        malos = ((numero, "12"), (numero, True), (numero, [1]), (numero, float("inf")),
                 (numero, float("nan")), (numero, 10 ** 400), (texto, 5), (texto, "x" * 2001),
                 (texto, ["a"]), (texto, "a\x00b"), (fecha, "2023-02-29"), (fecha, "2024-2-9"),
                 (fecha, "29/02/2024"), (fecha, "2024-02-29T00:00:00Z"), (fecha, 20240229),
                 (fecha, "2024-13-01"), (opcion, "cerrado"), (opcion, "Otro"), (opcion, 1),
                 (opcion, ["Cerrado"]))
        antes = self.huella(self.t1)
        for col, valor in malos:
            crudo = json.dumps({"expected_version": antes[0], "custom": {col["id"]: valor}})
            status, body = self.call_crudo("PATCH", f"/api/inventario/terrenos/{self.t1}", crudo, "olga")
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [col["id"]]), valor)
        self.assertEqual(self.call("PATCH", f"/api/inventario/terrenos/{self.t1}",
                                   {"expected_version": antes[0], "custom": [1]}, "olga")[1]
                         ["detalle"]["fields"], {"custom": "Se esperaba un objeto con los valores"
                                                 " personalizados."})
        self.assertEqual(self.huella(self.t1), antes)

        # null clears; a key left out keeps its value; nothing is coerced on the way.
        status, body = self.guardar(self.t1, {texto["id"]: None, fecha["id"]: None})
        self.assertEqual(body["terreno"]["custom"], {numero["id"]: 7, opcion["id"]: "Cerrado"})
        self.assertEqual(self.guardado(self.t1), {numero["id"]: 7, opcion["id"]: "Cerrado"})
        self.assertEqual(self.guardar(self.t1, {texto["id"]: "   "})[1]["terreno"]["version"], antes[0] + 1)
        self.assertEqual(self.guardado(self.t1)[numero["id"]], 7.0)  # a double, as core numbers are

    def call_crudo(self, method, path, crudo, user):
        """A body json.dumps writes but call() would not: Infinity and NaN."""
        import urllib.error
        import urllib.request
        peticion = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", method=method,
            data=crudo.encode(), headers={"Content-Type": "application/json",
                                          "Cookie": self.cookies[user]})
        try:
            with urllib.request.urlopen(peticion, timeout=20) as respuesta:
                return respuesta.status, json.loads(respuesta.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def test_only_live_columns_of_the_current_base_accept_a_value(self):
        propia, retirada = self.columna(self.b1, "Propia"), self.columna(self.b1, "Retirada")
        ajena = self.columna(self.b2, "Ajena")
        self.ok(self.guardar(self.t1, {retirada["id"]: "antes de retirarla"}))
        self.ok(self.cambiar(retirada, accion="retirar"))
        antes = self.huella(self.t1)
        # Unknown, retired and another base's column: one answer, even for an administrator.
        for clave in (retirada["id"], ajena["id"], f"custom:{nuevo()}", "custom:no-es-un-id",
                      propia["id"].upper(), "terreno", "core:kmz"):
            for user in ("olga", "ada"):
                status, body = self.guardar(self.t1, {clave: "x"}, user)
                self.assertEqual((status, body["detalle"]["fields"]), (422, {clave: DESCONOCIDA}))
        # An unassigned terrain has no base, so no custom column at all.
        self.assertEqual(self.guardar(self.t0, {propia["id"]: "x"}, "ada")[1]["detalle"]["fields"],
                         {propia["id"]: DESCONOCIDA})
        self.assertEqual(self.huella(self.t1), antes)
        self.assertEqual(self.guardado(self.t1), {retirada["id"]: "antes de retirarla"})
        # Creating still takes core fields only.
        status, body = self.call("POST", f"/api/maestra/bases/{self.b1}/terrenos",
                                 {"custom": {propia["id"]: "x"}}, "olga",
                                 {"Idempotency-Key": "clave-sin-custom-1"})
        self.assertEqual((status, list(body["detalle"]["fields"])), (422, ["custom"]))
        # Out of scope, the answer is the terrain's 404 whatever was sent.
        self.assertEqual(self.guardar(self.t2, {ajena["id"]: 5}, "olga", version=1), TERRENO_NO_EXISTE)
        self.assertEqual(self.guardar(self.t1, {propia["id"]: "x"}, "otto", version=1), TERRENO_NO_EXISTE)

    def test_core_and_custom_changes_are_one_version_or_none(self):
        nota, avance = self.columna(self.b1, "Nota"), self.columna(self.b1, "Avance", "numero")
        antes = self.huella(self.t1)
        status, body = self.guardar(self.t1, {nota["id"]: "primera", avance["id"]: 3},
                                    cambios={"estado": "Jalisco", "superficie_m2": 900})
        t = body["terreno"]
        self.assertEqual((status, t["version"], t["draft"]["estado"], t["custom"]),
                         (200, 2, "Jalisco", {nota["id"]: "primera", avance["id"]: 3}))
        self.assertEqual(self.huella(self.t1), tuple(n + 1 for n in antes))
        evento = filas("inventory_event", "inventory_id = ? AND version = 2", (self.t1,))[0]
        self.assertEqual((evento["action"], evento["actor_id"]), ("update", self.ids["olga"]))
        self.assertEqual(json.loads(evento["details_json"]), {"changes": {
            "estado": {"before": None, "after": "Jalisco"},
            "superficie_m2": {"before": None, "after": 900.0},
            nota["id"]: {"before": None, "after": "primera"},
            avance["id"]: {"before": None, "after": 3.0}}})

        # One bad value of either kind and nothing of the request is saved.
        for custom, cambios, campo in (({nota["id"]: "segunda", avance["id"]: "tres"}, {"estado": "Sonora"},
                                        avance["id"]),
                                       ({nota["id"]: "segunda"}, {"lat": 999}, "lat")):
            status, body = self.guardar(self.t1, custom, cambios=cambios)
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [campo]))
        self.assertEqual(self.huella(self.t1), tuple(n + 1 for n in antes))
        self.assertEqual(self.guardado(self.t1), {nota["id"]: "primera", avance["id"]: 3})

        # The same values again are not a change. A stale version is the 409 with the row as it is.
        self.assertEqual(self.guardar(self.t1, {nota["id"]: "primera"}, cambios={"estado": "Jalisco"})[1]
                         ["terreno"]["version"], 2)
        status, body = self.guardar(self.t1, {nota["id"]: "tarde"}, version=1)
        self.assertEqual((status, body["detalle"]["code"], body["detalle"]["current_version"],
                          body["detalle"]["terreno"]["custom"][nota["id"]]), (409, "conflict", 2, "primera"))
        # A core-only client is untouched, and leaves custom values where they were.
        status, body = self.patch(self.t1, {"municipio": "Zapopan"}, "olga")
        self.assertEqual((status, body["terreno"]["custom"]), (200, {nota["id"]: "primera", avance["id"]: 3}))
        status, body = self.guardar(self.t1, {nota["id"]: None}, cambios={"municipio": "Tala"})
        self.assertEqual(json.loads(filas("inventory_event", "inventory_id = ? AND version = 4",
                                          (self.t1,))[0]["details_json"])["changes"],
                         {"municipio": {"before": "Zapopan", "after": "Tala"},
                          nota["id"]: {"before": "primera", "after": None}})

    # -- 3. the real writer through transfer, retirement and back ----------------

    def test_written_values_and_history_follow_the_current_base(self):
        """Not seeded: every custom value and history entry here was written by
        the PATCH. olga reads Base Uno only; otto is granted Base Dos only."""
        self.ok(self.otorgar(self.b2, "omar", "otto"))
        uno, otra = self.columna(self.b1, "De la uno"), self.columna(self.b1, "Otra de la uno")
        dos = self.columna(self.b2, "De la dos", "numero")
        status, creado = self.call("POST", f"/api/maestra/bases/{self.b1}/terrenos",
                                   {"terreno": "Lote Viajero", "estado": "Jalisco"}, "omar",
                                   {"Idempotency-Key": "clave-viajero-0001"})
        tid = creado["terreno"]["id"]
        self.ok(self.guardar(tid, {uno["id"]: SECRETO, otra["id"]: SECRETO + "-2"}, "olga",
                             cambios={"municipio": "Tala"}))

        def historial(user):
            return self.ok(self.ver(tid, user, "/historial"))["eventos"]

        def campos(user):
            return [sorted(e.get("changes", {})) for e in historial(user)]

        def superficies(user, base):
            """Every place the record can reach that reader, as one text."""
            lista = self.call("GET", f"/api/maestra/bases/{base}/terrenos?q=viajero", user=user)
            viejo = self.guardar(tid, {}, user, cambios={"direccion": "tarde"}, version=1)   # a 409
            replay = self.call("POST", f"/api/maestra/bases/{self.b1}/terrenos",
                               {"terreno": "Lote Viajero", "estado": "Jalisco"}, user,
                               {"Idempotency-Key": "clave-viajero-0001"})
            return encode([self.ver(tid, user), self.ver(tid, user, "/historial"), lista, viejo, replay])

        en_uno = [sorted(["municipio", uno["id"], otra["id"]]), ["estado", "terreno"]]
        self.assertEqual(campos("olga"), en_uno)
        self.assertEqual(historial("olga")[0]["changes"][uno["id"]], {"before": None, "after": SECRETO})
        self.assertIn(SECRETO.encode(), superficies("olga", self.b1))

        # To Base Dos. The source reader loses the record; the destination reader gets the
        # record and its core history, and nothing of Base Uno's columns anywhere.
        self.transferir(tid, self.b2)
        self.assertEqual(self.ver(tid, "olga"), TERRENO_NO_EXISTE)
        self.assertEqual(self.ver(tid, "olga", "/historial"), TERRENO_NO_EXISTE)
        self.assertEqual(self.ver(tid, "otto")[1]["terreno"]["custom"], {})
        self.assertEqual(campos("otto"), [[], ["municipio"], ["estado", "terreno"]])
        visto = superficies("otto", self.b2)
        for oculto in (SECRETO, uno["id"], otra["id"], self.b1):
            self.assertNotIn(oculto.encode(), visto)
        # The creator's replay is re-authorized as before: omar may still see it, olga-like otto never created it.
        self.assertEqual(self.guardar(tid, {uno["id"]: "x"}, "ada")[1]["detalle"]["fields"],
                         {uno["id"]: DESCONOCIDA})

        # A real edit in Base Dos: its own column is written; Base Uno's values ride along untouched.
        status, body = self.guardar(tid, {dos["id"]: 42}, "otto", cambios={"direccion": "Camino 3"})
        self.assertEqual((status, body["terreno"]["custom"]), (200, {dos["id"]: 42}))
        self.assertEqual(self.guardado(tid), {uno["id"]: SECRETO, otra["id"]: SECRETO + "-2", dos["id"]: 42})
        self.assertEqual(campos("otto")[0], sorted(["direccion", dos["id"]]))
        self.assertNotIn(SECRETO.encode(), superficies("otto", self.b2))

        # Back to Base Uno: its values and their history show again; Base Dos's do not.
        self.transferir(tid, self.b1)
        self.assertEqual(self.ver(tid, "olga")[1]["terreno"]["custom"],
                         {uno["id"]: SECRETO, otra["id"]: SECRETO + "-2"})
        self.assertEqual(campos("olga"), [[], ["direccion"], [], *en_uno])
        self.assertNotIn(dos["id"].encode(), superficies("olga", self.b1))
        self.assertEqual(self.ver(tid, "otto"), TERRENO_NO_EXISTE)

        # Retiring one column hides its value and its history entries; the other stays.
        guardado, eventos = self.guardado(tid), filas("inventory_event", "inventory_id = ?", (tid,))
        self.ok(self.cambiar(uno, accion="retirar", user="olga"))
        self.assertEqual(self.ver(tid, "olga")[1]["terreno"]["custom"], {otra["id"]: SECRETO + "-2"})
        self.assertEqual(campos("olga")[3], sorted(["municipio", otra["id"]]))
        visto = superficies("olga", self.b1)
        self.assertNotIn(uno["id"].encode(), visto)
        self.assertNotIn(f'"{SECRETO}"'.encode(), visto)
        # An edit meanwhile keeps the retired column's value stored.
        self.ok(self.guardar(tid, {otra["id"]: "nuevo"}, "olga"))
        self.assertEqual(self.guardado(tid)[uno["id"]], SECRETO)
        # Restored: the same id, the same value, the same history.
        self.ok(self.cambiar(uno, accion="restaurar"))
        self.assertEqual(self.ver(tid, "olga")[1]["terreno"]["custom"],
                         {uno["id"]: SECRETO, otra["id"]: "nuevo"})
        self.assertEqual(campos("olga")[4], en_uno[0])

        # The administrators' audit is whole throughout, and nothing stored was rewritten.
        completo = historial("ada")
        self.assertEqual([sorted(e.get("changes", {})) for e in completo][1:],
                         [[], sorted(["direccion", dos["id"]]), [], *en_uno])
        self.assertEqual(completo[3]["base"], {"before": self.b1, "after": self.b2})
        self.assertEqual([e for e in filas("inventory_event", "inventory_id = ?", (tid,))
                          if e["version"] <= len(eventos)], eventos)
        self.assertEqual({k: v for k, v in self.guardado(tid).items() if k != otra["id"]},
                         {k: v for k, v in guardado.items() if k != otra["id"]})
        # Every stored custom change has the accepted shape: scalar before and after, nothing nested.
        for e in filas("inventory_event", "inventory_id = ?", (tid,)):
            for campo, cambio in json.loads(e["details_json"] or "{}").get("changes", {}).items():
                self.assertEqual(sorted(cambio), ["after", "before"], campo)
                self.assertTrue(all(v is None or isinstance(v, (str, int, float)) for v in cambio.values()))

    # -- 4. races: both orders ---------------------------------------------------

    def carrera(self, modulo, pausado, primero, despues):
        """Hold ``pausado`` (a repo function of an API module) just before it
        writes, inside its transaction and after its authorization, while
        ``despues`` is attempted."""
        dentro, seguir, hecho, resultado = threading.Event(), threading.Event(), threading.Event(), {}
        real = getattr(modulo, pausado)

        def con_barrera(*args, **kwargs):
            dentro.set()
            assert seguir.wait(15)
            return real(*args, **kwargs)

        def uno():
            resultado["primero"] = primero()

        def otro():
            resultado["despues"] = despues()
            hecho.set()
        with patch.object(modulo, pausado, con_barrera):
            a = threading.Thread(target=uno)
            a.start()
            self.assertTrue(dentro.wait(15))
            b = threading.Thread(target=otro)
            b.start()
            self.assertFalse(hecho.wait(0.4))  # it cannot commit under the open boundary
            seguir.set()
            a.join(20)
            b.join(20)
        return resultado["primero"], resultado["despues"]

    def test_a_cell_save_and_a_retirement_are_serialized_in_both_orders(self):
        col = self.columna(self.b1, "Disputada")

        def guardar():
            return self.guardar(self.t1, {col["id"]: SECRETO}, version=1)

        def retirar():
            return self.cambiar(col, accion="retirar", expected_version=1)
        # The retirement holds the boundary: the save waits, then finds no such column.
        retiro, guardada = self.carrera(api_columnas.repo, "retirar", retirar, guardar)
        self.assertEqual((retiro[0], guardada[0], guardada[1]["detalle"]["fields"]),
                         (200, 422, {col["id"]: DESCONOCIDA}))
        self.assertEqual((self.huella(self.t1), self.guardado(self.t1)), ((1, 1, 1), {}))
        self.assertNotIn(SECRETO.encode(), encode(guardada))

        # The save holds the boundary: the retirement waits, then hides a value that was saved whole.
        self.ok(self.cambiar(col, accion="restaurar"))

        def retirar_2():
            return self.cambiar(col, accion="retirar", expected_version=3)
        guardada, retiro = self.carrera(api_inventario.repo, "update", guardar, retirar_2)
        self.assertEqual((guardada[0], retiro[0]), (200, 200))
        self.assertEqual((self.huella(self.t1), self.guardado(self.t1)), ((2, 2, 2), {col["id"]: SECRETO}))
        self.assertEqual(self.ver(self.t1)[1]["terreno"]["custom"], {})

    def test_a_cell_save_and_a_transfer_are_serialized_in_both_orders(self):
        col = self.columna(self.b1, "Disputada")

        def guardar(user="olga", version=1):
            return self.guardar(self.t1, {col["id"]: SECRETO}, user, version=version)

        def transferir(version=1, base=None):
            return self.call("POST", f"/api/inventario/terrenos/{self.t1}/transferir",
                             {"expected_version": version, "base_id": base or self.b2})
        guardada, traslado = self.carrera(api_inventario.repo, "update", guardar, transferir)
        self.assertEqual((guardada[0], traslado[0], traslado[1]["detalle"]["code"]), (200, 409, "conflict"))
        self.assertEqual(self.guardado(self.t1), {col["id"]: SECRETO})

        # The transfer holds: the operator's stale save is out of scope, the administrator's
        # names a column the terrain's base no longer has. Neither writes.
        for user, esperado in (("olga", TERRENO_NO_EXISTE), ("ada", None)):
            traslado, guardada = self.carrera(
                api_inventario.repo, "transferir", lambda: transferir(self.version(self.t1)),
                lambda u=user: self.guardar(self.t1, {col["id"]: "tarde"}, u, version=self.version(self.t1)))
            self.assertEqual(traslado[0], 200)
            if esperado:
                self.assertEqual(guardada, esperado)
            else:
                self.assertEqual((guardada[0], guardada[1]["detalle"]["fields"]),
                                 (422, {col["id"]: DESCONOCIDA}))
            self.assertNotIn(SECRETO.encode(), encode(guardada))
            self.assertEqual(self.guardado(self.t1), {col["id"]: SECRETO})
            self.transferir(self.t1, self.b1)
        self.assertEqual(self.cuenta("inventory_revision", "inventory_id = ?", (self.t1,)),
                         self.version(self.t1))

    def test_a_cell_save_and_a_grant_loss_or_base_archive_are_serialized_in_both_orders(self):
        col = self.columna(self.b1, "Disputada")

        def guardar(user="olga"):
            return self.guardar(self.t1, {col["id"]: SECRETO}, user, version=self.version(self.t1))

        def revocar():
            return self.otorgar(self.b1, "omar")

        def archivar():
            return self.archivar(self.b1)
        # The save first: the grant change and the archive wait, then succeed.
        guardada, revocado = self.carrera(api_inventario.repo, "update", guardar, revocar)
        self.assertEqual((guardada[0], revocado[0], self.version(self.t1)), (200, 200, 2))
        self.ok(self.otorgar(self.b1, "olga", "omar"))
        self.ok(self.guardar(self.t1, {col["id"]: None}))
        guardada, archivado = self.carrera(api_inventario.repo, "update", guardar, archivar)
        self.assertEqual((guardada[0], archivado[0], self.version(self.t1)), (200, 200, 4))
        self.ok(self.archivar(self.b1, "restaurar"))
        self.ok(self.guardar(self.t1, {col["id"]: None}))
        antes = self.huella(self.t1)

        # The grant loss first: her save waits and is then out of scope.
        revocado, guardada = self.carrera(api_maestra.repo, "reemplazar_accesos", revocar, guardar)
        self.assertEqual((revocado[0], guardada), (200, TERRENO_NO_EXISTE))
        self.ok(self.otorgar(self.b1, "olga", "omar"))
        # The archive first: closed to the operator, read-only for the administrator.
        archivado, guardada = self.carrera(api_maestra.repo, "archivar", archivar, guardar)
        self.assertEqual((archivado[0], guardada), (200, TERRENO_NO_EXISTE))
        status, body = guardar("ada")
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))
        self.assertEqual((self.huella(self.t1), self.guardado(self.t1)), (antes, {}))

    def test_concurrent_definition_changes_and_grant_changes_do_not_overwrite(self):
        col = self.columna(self.b1, "Disputada")
        primera, segunda = self.carrera(
            api_columnas.repo, "cambiar",
            lambda: self.cambiar(col, nombre="De ada", expected_version=1),
            lambda: self.cambiar(col, "olga", nombre="De olga", expected_version=1))
        self.assertEqual((primera[0], segunda[0], segunda[1]["detalle"]["code"],
                          segunda[1]["detalle"]["columna"]["nombre"]), (200, 409, "conflict", "De ada"))
        self.assertEqual(self.cuenta("maestra_base_event", "column_id = ?", (col["id"][7:],)), 2)
        # Two creations with one key at once: one definition.
        creadas = self.carrera(
            api_columnas.repo, "crear",
            lambda: self.crear(self.b1, "Gemela", key="clave-gemela-001"),
            lambda: self.crear(self.b1, "Gemela", key="clave-gemela-001"))
        self.assertEqual([r[0] for r in creadas], [200, 200])
        self.assertEqual(creadas[0][1], creadas[1][1])
        self.assertEqual(self.nombres(self.b1).count("Gemela"), 1)

        # Two administrators replacing the grants from the same version: one wins, one is told.
        version = self.base(self.b1)["version"]

        def otorgar(user, *logins):
            return self.call("PUT", f"/api/maestra/bases/{self.b1}/acceso",
                             {"expected_version": version, "usuarios": [self.ids[n] for n in logins]}, user)
        una, otra = self.carrera(api_maestra.repo, "reemplazar_accesos",
                                 lambda: otorgar("ada", "olga"), lambda: otorgar("alan", "otto"))
        self.assertEqual((una[0], otra[0], otra[1]["detalle"]["code"]), (200, 409, "conflict"))
        self.assertEqual([u["login"] for u in self.ok(self.call(
            "GET", f"/api/maestra/bases/{self.b1}/acceso"))["usuarios"]], ["olga"])

    # -- 5. the grant editor's account lookup ------------------------------------

    def test_the_operator_lookup_is_bounded_minimal_and_for_administrators(self):
        status, body = self.call("GET", "/api/maestra/operadores")
        self.assertEqual((status, body["total"]), (200, 3))
        self.assertEqual([sorted(u) for u in body["usuarios"]], [["active", "display_name", "id", "login"]] * 3)
        self.assertEqual([u["login"] for u in body["usuarios"]], ["olga", "omar", "otto"])  # no administrators
        self.assertEqual(self.call("GET", "/api/maestra/operadores?q=OLGA")[1]["usuarios"][0]["id"],
                         self.ids["olga"])
        self.assertEqual(self.call("GET", "/api/maestra/operadores?q=%25")[1]["total"], 0)
        pagina = self.call("GET", "/api/maestra/operadores?limit=2")[1]
        self.assertEqual((len(pagina["usuarios"]), pagina["total"]), (2, 3))
        for malo in ("limit=0", "limit=201", "limit=x", "rol=admin", "q=" + "x" * 101):
            self.assertEqual(self.call("GET", f"/api/maestra/operadores?{malo}")[0], 422, malo)
        for user in ("olga", "otto"):
            status, body = self.call("GET", "/api/maestra/operadores", user=user)
            self.assertEqual((status, body["detalle"]["code"]), (403, "forbidden"))
        self.assertEqual(self.call("GET", "/api/maestra/operadores", user=None)[0], 401)


class ColumnasSqlite(Columnas, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._entorno = patch.dict(os.environ, {"ARA_MAP_DB": str(Path(self._dir.name) / "prueba.db")})
        self._entorno.start()
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        self.addCleanup(self._dir.cleanup)
        self.addCleanup(self._entorno.stop)
        self.levantar()


@unittest.skipUnless(URL, "No Postgres test connection configured")
class ColumnasPostgres(Columnas, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.schema = "test_ara_columnas_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
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
            conn.raw.execute("TRUNCATE team_user, team_login_failure CASCADE")
        self.levantar()


if __name__ == "__main__":
    unittest.main()

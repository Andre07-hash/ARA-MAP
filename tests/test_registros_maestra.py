"""The scoped terrain-record backend (round 1, packet 1A).

Through the real HTTP dispatcher with real sessions, on SQLite and (when
ARA_MAP_TEST_DATABASE_URL is set) on a disposable Postgres schema. The fixture
is the one of tests/test_roles_y_bases.py: administrators ada and alan;
operators olga (Base Uno), omar (Base Uno and Base Dos), otto (no grant); t1
in Base Uno, t2 in Base Dos, t0 unassigned, ta archived in Base Uno, t3 in the
archived base.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.parse
import uuid
from pathlib import Path
from unittest.mock import patch

from server import auth, db, inventario, postgres
from server.api import inventario as api_inventario
from server.repo import inventario as repo
from server.web_util import encode
from tests.test_roles_y_bases import URL, Escenario, filas, nuevo, sql

NO_EXISTE = (404, {"error": "El terreno no existe.", "detalle": {"code": "not_found"}})
BASE_NO_EXISTE = (404, {"error": "La base de trabajo no existe.", "detalle": {"code": "not_found"}})
ARCHIVOS = ("archivo", "archivo_version", "archivo_intento", "geometria", "archivo_evento")
CAMPOS = {"tipo_terreno": "Industrial", "terreno": "Lote Ñandú", "estado": "Jalisco",
          "municipio": "Zapopan", "superficie_m2": 12000, "superficie_ha": 1.2,
          "afectaciones_pct": 0.125, "asking_price": 1470000, "asking_m2": 122.5,
          "notas_internas": "Comentario ficticio", "lat": 20.7, "lon": -103.4}


class Registros(Escenario):
    """The checks. Mixed into one TestCase per backend."""

    def en_base(self, base, cuerpo=None, user="olga", key=None):
        return self.call("POST", f"/api/maestra/bases/{base}/terrenos", {} if cuerpo is None else cuerpo,
                         user, {"Idempotency-Key": key or f"clave-{nuevo()}"})

    def lista(self, base, query="", user="olga"):
        return self.call("GET", f"/api/maestra/bases/{base}/terrenos" + (f"?{query}" if query else ""),
                         user=user)

    def maestra(self, query=""):
        return self.ok(self.call("GET", "/api/inventario/terrenos" + (f"?{query}" if query else "")))

    def accion(self, terreno, accion, user="olga", **cuerpo):
        return self.call("POST", f"/api/inventario/terrenos/{terreno}/{accion}",
                         {"expected_version": self.version(terreno), **cuerpo}, user)

    def ver(self, terreno, user="olga", sufijo=""):
        return self.call("GET", f"/api/inventario/terrenos/{terreno}{sufijo}", user=user)

    def columna(self, base, nombre):
        cid, ada, ahora = nuevo(), self.ids["ada"], db.now()
        sql(lambda c: c.execute(
            "INSERT INTO inventory_column (id, base_id, nombre, tipo, orden, created_at, created_by,"
            " updated_at, updated_by) VALUES (?, ?, ?, 'texto', 1, ?, ?, ?, ?)",
            (cid, base, nombre, ahora, ada, ahora, ada)))
        return f"custom:{cid}"

    def adjuntos(self, terreno):
        """A valid, activated KMZ attachment graph on a terrain, written straight
        to the tables: this packet depends on none of Team B's lifecycle code."""
        a, v, i, g, ada, ahora = nuevo(), nuevo(), nuevo(), nuevo(), self.ids["ada"], db.now()

        def sembrar(conn):
            conn.execute(
                "INSERT INTO archivo (id, inventory_id, columna_id, tipo, creado_en, creado_por,"
                " actualizado_en, actualizado_por) VALUES (?, ?, 'core:kmz', 'kmz', ?, ?, ?, ?)",
                (a, terreno, ahora, ada, ahora, ada))
            conn.execute(
                "INSERT INTO archivo_version (id, archivo_id, inventory_id, numero, estado,"
                " revision_base, nombre_original, tamano_declarado, sha256_declarado, tamano, sha256,"
                " clave_temporal, clave_final, subida_vence_en, completar_antes_de, aplicada,"
                " iniciado_en, iniciado_por, finalizado_en, finalizado_por, terminado_en)"
                " VALUES (?, ?, ?, 1, 'disponible', 1, 'plano ficticio.kmz', 10, ?, 10, ?, ?, ?, ?, ?, 1,"
                " ?, ?, ?, ?, ?)",
                (v, a, terreno, "a" * 64, "a" * 64, "temporal/" + v, "final/" + v, ahora, ahora,
                 ahora, ada, ahora, ada, ahora))
            conn.execute(
                "INSERT INTO archivo_intento (id, archivo_version_id, numero, origen, resultado,"
                " resultado_json, analizador, geometria_id, creado_en, creado_por)"
                " VALUES (?, ?, 1, 'completar', 'listo', '{}', 'kmz-ficticio', ?, ?, ?)",
                (i, v, g, ahora, ada))
            conn.execute(
                "INSERT INTO geometria (id, archivo_id, archivo_version_id, inventory_id, intento_id,"
                " geojson, bbox_oeste, bbox_sur, bbox_este, bbox_norte, punto_lon, punto_lat, partes,"
                " huecos, vertices, utilizable, bytes_geojson, sha256_geojson, creado_en)"
                " VALUES (?, ?, ?, ?, ?, '{}', -103.5, 20.5, -103.4, 20.6, -103.45, 20.55, 1, 0, 5, 1,"
                " 2, ?, ?)", (g, a, v, terreno, i, "b" * 64, ahora))
            conn.execute("UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ?"
                         " WHERE id = ?", (v, g, a))
        with db.escritura() as conn:
            sembrar(conn)
        return {t: filas(t) for t in ARCHIVOS}

    # -- 1. creating, blank and populated ----------------------------------------

    def test_a_blank_record_is_created_where_authorized_and_nowhere_else(self):
        status, body = self.en_base(self.b1)
        t = body["terreno"]
        self.assertEqual((status, t["version"], t["base_id"], t["custom"], t["publication_state"]),
                         (200, 1, self.b1, {}, "draft"))
        self.assertEqual(t["created_by"], {"id": self.ids["olga"], "display_name": "Olga Ficticia"})
        vacio = dict(inventario.empty_draft())
        self.assertEqual(t["draft"], vacio)
        self.assertTrue(all(v is None for k, v in vacio.items() if k not in ("price_on_request", "availability")))
        revision = filas("inventory_revision", "inventory_id = ?", (t["id"],))[0]
        self.assertEqual((revision["base_id"], revision["custom_json"]), (self.b1, "{}"))
        self.assertEqual(self.en_base(self.b2, user="omar")[0], 200)
        self.assertEqual(self.en_base(self.b1, user="ada")[1]["terreno"]["base_id"], self.b1)

        antes = self.cuenta("inventory_terrain")
        # No grant, another base, an archived base she was granted, a base that does not exist:
        # one answer, whether or not the request was otherwise valid.
        fuera = [self.en_base(self.b1, user="otto"), self.en_base(self.b2), self.en_base(self.b3),
                 self.en_base(nuevo()), self.en_base(nuevo(), user="ada"),
                 self.call("POST", f"/api/maestra/bases/{self.b2}/terrenos", {"lat": 999}, "olga")]
        self.assertEqual({encode(r) for r in fuera}, {encode(BASE_NO_EXISTE)})
        status, body = self.en_base(self.b3, user="ada")
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))
        # The unscoped create is the administrators'; an operator cannot borrow it.
        status, body = self.call("POST", "/api/inventario/terrenos", {"base_id": self.b1}, "olga",
                                 {"Idempotency-Key": "clave-operadora-9"})
        self.assertEqual((status, body["detalle"]["code"]), (403, "forbidden"))
        status, body = self.call("POST", "/api/inventario/terrenos", {}, "ada",
                                 {"Idempotency-Key": "clave-admin-00009"})
        self.assertEqual((status, body["terreno"]["base_id"]), (200, None))
        self.assertEqual(self.cuenta("inventory_terrain"), antes + 1)

    def test_every_core_value_is_optional_and_round_trips(self):
        status, body = self.en_base(self.b1, CAMPOS)
        self.assertEqual(status, 200)
        draft = body["terreno"]["draft"]
        self.assertEqual({k: draft[k] for k in CAMPOS}, CAMPOS)
        self.assertIsNone(draft["moneda"])  # two amounts, currency unknown: saved, not assumed
        self.assertEqual(self.ver(body["terreno"]["id"])[1]["terreno"]["draft"], draft)
        for solo in ({"tipo_terreno": "Agrícola"}, {"asking_price": 5}, {"asking_m2": 0.5},
                     {"notas_internas": "solo un comentario"}, {"lat": 20.5}, {"superficie_ha": 3}):
            status, body = self.en_base(self.b1, solo)
            self.assertEqual(status, 200, solo)
            esperado = {**inventario.empty_draft(), **solo}
            self.assertEqual(body["terreno"]["draft"], esperado)
        # Nothing is derived, converted or guessed from what was sent.
        status, body = self.en_base(self.b1, {"superficie_m2": 10000, "asking_price": 100})
        self.assertEqual([body["terreno"]["draft"][k] for k in ("superficie_ha", "asking_m2", "moneda")],
                         [None, None, None])
        # Validation of what IS sent is unchanged.
        for malo, campo in (({"lat": 91}, "lat"), ({"superficie_m2": -1}, "superficie_m2"),
                            ({"moneda": "EUR"}, "moneda"), ({"tipo_terreno": 7}, "tipo_terreno"),
                            ({"tipo_terreno": "x" * 101}, "tipo_terreno"), ({"archivos": []}, "archivos"),
                            ({"kmz": "x"}, "kmz"), ({"custom": {}}, "custom")):
            status, body = self.en_base(self.b1, malo)
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [campo]))

    def test_the_body_cannot_choose_the_owner_actor_or_role(self):
        antes = self.cuenta("inventory_terrain")
        for campo, valor in (("base_id", self.b2), ("actor_id", self.ids["ada"]), ("rol", "admin"),
                             ("created_by", self.ids["ada"]), ("id", nuevo()), ("version", 9)):
            status, body = self.en_base(self.b1, {"terreno": "X", campo: valor})
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [campo]))
        self.assertEqual(self.cuenta("inventory_terrain"), antes)
        status, body = self.call("POST", f"/api/maestra/bases/{self.b1}/terrenos?base_id={self.b2}",
                                 {"terreno": "Y"}, "olga",
                                 {"Idempotency-Key": "clave-olga-00001", "X-Base-Id": self.b2, "X-Rol": "admin"})
        self.assertEqual((status, body["terreno"]["base_id"], body["terreno"]["created_by"]["id"]),
                         (200, self.b1, self.ids["olga"]))
        self.assertEqual(self.en_base(self.b1, {}, key="corta")[1]["detalle"]["code"], "idempotency_key_required")

    # -- 2. idempotency and concurrent edits --------------------------------------

    def test_a_repeated_key_returns_the_same_record_to_its_owner_only(self):
        _, primero = self.en_base(self.b1, {"terreno": "Uno"}, key="clave-compartida-1")
        tid = primero["terreno"]["id"]
        self.assertEqual(self.en_base(self.b1, {"terreno": "Uno"}, key="clave-compartida-1")[1], primero)
        status, body = self.en_base(self.b1, {"terreno": "Dos"}, key="clave-compartida-1")
        self.assertEqual((status, body["detalle"]["code"]), (409, "idempotency_conflict"))
        self.assertEqual((self.cuenta("inventory_terrain", "id = ?", (tid,)),
                          self.cuenta("inventory_event", "inventory_id = ?", (tid,))), (1, 1))
        # The same key from someone else, or for another base, is another key.
        otros = [self.en_base(self.b1, {"terreno": "Uno"}, "omar", "clave-compartida-1"),
                 self.en_base(self.b2, {"terreno": "Uno"}, "omar", "clave-compartida-1"),
                 self.en_base(self.b1, {"terreno": "Uno"}, "ada", "clave-compartida-1"),
                 self.call("POST", "/api/inventario/terrenos", {"terreno": "Uno"}, "ada",
                           {"Idempotency-Key": "clave-compartida-1"})]
        self.assertEqual({r[0] for r in otros}, {200})
        self.assertEqual(len({r[1]["terreno"]["id"] for r in otros} | {tid}), 5)
        self.assertEqual({r[1]["terreno"]["created_by"]["id"] for r in otros},
                         {self.ids["omar"], self.ids["ada"]})
        self.assertEqual(self.en_base(self.b1, {"terreno": "Uno"}, "otto", "clave-compartida-1"),
                         BASE_NO_EXISTE)
        # A replay answers with the record as it is now, not as it was stored.
        self.patch(tid, {"estado": "Jalisco"}, "omar")
        _, repetida = self.en_base(self.b1, {"terreno": "Uno"}, key="clave-compartida-1")
        self.assertEqual((repetida["terreno"]["version"], repetida["terreno"]["draft"]["estado"]), (2, "Jalisco"))
        almacenado = filas("inventory_operation_result", "idempotency_key = 'clave-compartida-1'")
        self.assertEqual({r["result_json"] for r in almacenado if tid in r["result_json"]},
                         {json.dumps({"id": tid})})  # an id, never a response

    def test_a_replay_is_reauthorized_against_the_record_as_it_is_now(self):
        _, primero = self.en_base(self.b1, {"terreno": "Privado", "notas_internas": "SENTINELA-9"},
                                  key="clave-de-olga-01")
        tid = primero["terreno"]["id"]
        total = self.cuenta("inventory_terrain")
        self.ok(self.accion(tid, "transferir", "ada", base_id=self.b2))
        # Moved out of her base: her own key no longer returns it, and creates nothing.
        self.assertEqual(self.en_base(self.b1, {"terreno": "Privado", "notas_internas": "SENTINELA-9"},
                                      key="clave-de-olga-01"), NO_EXISTE)
        self.ok(self.accion(tid, "transferir", "ada", base_id=self.b1))
        self.assertEqual(self.en_base(self.b1, {"terreno": "Privado", "notas_internas": "SENTINELA-9"},
                                      key="clave-de-olga-01")[1]["terreno"]["id"], tid)
        self.ok(self.otorgar(self.b1, "omar"))  # her grant is gone
        respuesta = self.en_base(self.b1, {"terreno": "Privado", "notas_internas": "SENTINELA-9"},
                                 key="clave-de-olga-01")
        self.assertEqual(respuesta, BASE_NO_EXISTE)
        self.assertNotIn("SENTINELA-9", json.dumps(respuesta))
        self.assertEqual(self.cuenta("inventory_terrain"), total)

    def test_a_key_stored_before_keys_were_scoped_still_replays_for_its_owner(self):
        """Before this packet a create was stored as operation 'create', with
        the hash of the field map alone and a whole response. Such a row must
        keep answering its own retry, with the record as it is now."""
        campos, key = {"terreno": "Registro heredado", "estado": "Jalisco"}, "clave-heredada-01"
        tid = self.ok(self.call("POST", "/api/inventario/terrenos", campos, "ada",
                                {"Idempotency-Key": key}))["terreno"]["id"]
        heredado = hashlib.sha256(json.dumps(campos, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with db.escritura() as conn:
            conn.execute("UPDATE inventory_operation_result SET operation = 'create', request_hash = ?,"
                         " result_json = ? WHERE idempotency_key = ?",
                         (heredado, json.dumps({"terreno": {"id": tid, "draft": {"terreno": "CACHÉ-VIEJA"}}}), key))
        self.ok(self.patch(tid, {"municipio": "Zapopan"}, "ada"))
        antes = [self.cuenta(t) for t in ("inventory_terrain", "inventory_revision", "inventory_event",
                                          "inventory_operation_result")]

        def repetir(cuerpo, user="ada"):
            return self.call("POST", "/api/inventario/terrenos", cuerpo, user, {"Idempotency-Key": key})
        status, body = repetir(campos)
        self.assertEqual((status, body["terreno"]["id"], body["terreno"]["version"],
                          body["terreno"]["draft"]["municipio"]), (200, tid, 2, "Zapopan"), body)
        self.assertNotIn("CACHÉ-VIEJA", json.dumps(body, ensure_ascii=False))
        # The same fields in another order or spacing are the same request, as they were.
        self.assertEqual(repetir({"estado": " Jalisco ", "terreno": "Registro  heredado"})[1]["terreno"]["id"], tid)
        status, body = repetir({**campos, "estado": "Colima"})
        self.assertEqual((status, body["detalle"]["code"]), (409, "idempotency_conflict"))
        self.assertNotIn(tid, json.dumps(body))
        self.assertEqual([self.cuenta(t) for t in ("inventory_terrain", "inventory_revision", "inventory_event",
                                                   "inventory_operation_result")], antes)
        # A scoped hash never matches a stored field-only one, and the other way round.
        with db.escritura() as conn:
            conn.execute("UPDATE inventory_operation_result SET request_hash = ? WHERE idempotency_key = ?",
                         (hashlib.sha256(json.dumps({"base": None, "campos": campos}, sort_keys=True,
                                                    ensure_ascii=False).encode()).hexdigest(), key))
        self.assertEqual(repetir(campos)[0], 409)
        with db.escritura() as conn:
            conn.execute("UPDATE inventory_operation_result SET request_hash = ? WHERE idempotency_key = ?",
                         (heredado, key))
        # Another account with the same key and body gets its own record, never this one.
        ajeno = self.ok(repetir(campos, "alan"))["terreno"]
        self.assertNotEqual(ajeno["id"], tid)
        self.assertEqual(ajeno["created_by"]["id"], self.ids["alan"])
        # In a base the key is another key, for its owner too.
        self.assertNotEqual(self.ok(self.en_base(self.b1, campos, "ada", key))["terreno"]["id"], tid)
        # Demoted, the owner's own retry returns nothing of the record.
        with db.escritura() as conn:
            auth.set_role(conn, "ada", "operador")
        self.assertEqual(repetir(campos)[0], 401)  # her sessions ended with the role
        self.cookies["ada"] = self.entrar("ada")
        respuesta = repetir(campos)
        self.assertEqual((respuesta[0], respuesta[1]["detalle"]["code"]), (403, "forbidden"))
        self.assertNotIn(tid, json.dumps(respuesta))
        self.assertNotIn("heredado", json.dumps(respuesta))

    def test_simultaneous_requests_with_one_key_create_one_record(self):
        resultados, barrera = [], threading.Barrier(4)

        def crear():
            barrera.wait()
            resultados.append(self.en_base(self.b1, {"terreno": "Carrera"}, key="clave-carrera-01"))
        hilos = [threading.Thread(target=crear) for _ in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual({s for s, _ in resultados}, {200})
        (tid,) = {b["terreno"]["id"] for _, b in resultados}
        self.assertEqual((self.cuenta("inventory_revision", "inventory_id = ?", (tid,)),
                          self.cuenta("inventory_event", "inventory_id = ?", (tid,))), (1, 1))

    def test_five_sessions_editing_one_cell_give_one_version_and_four_conflicts(self):
        sesiones = [self.cookies["olga"], self.cookies["omar"], self.cookies["ada"], self.cookies["alan"],
                    self.entrar("omar")]
        resultados, barrera = [], threading.Barrier(len(sesiones))

        def editar(numero, cookie):
            barrera.wait()
            resultados.append(self.call("PATCH", f"/api/inventario/terrenos/{self.t1}", {
                "expected_version": 1, "changes": {"municipio": f"Municipio {numero}"}}, cookie=cookie))
        hilos = [threading.Thread(target=editar, args=par) for par in enumerate(sesiones)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sorted(s for s, _ in resultados), [200, 409, 409, 409, 409])
        ganador = next(b for s, b in resultados if s == 200)["terreno"]
        for status, body in resultados:
            if status == 409:
                self.assertEqual((body["detalle"]["code"], body["detalle"]["current_version"],
                                  body["detalle"]["terreno"]["draft"]["municipio"]),
                                 ("conflict", 2, ganador["draft"]["municipio"]))
        self.assertEqual((self.version(self.t1), self.cuenta("inventory_revision", "inventory_id = ?", (self.t1,)),
                          self.cuenta("inventory_event", "inventory_id = ?", (self.t1,))), (2, 2, 2))
        # Five sessions on five different records do not get in each other's way.
        propios = [self.en_base(self.b1, user="omar")[1]["terreno"]["id"] for _ in sesiones]
        resultados.clear()
        barrera.reset()

        def editar_propio(numero, cookie):
            barrera.wait()
            resultados.append(self.call("PATCH", f"/api/inventario/terrenos/{propios[numero]}", {
                "expected_version": 1, "changes": {"municipio": "Propio"}}, cookie=cookie)[0])
        hilos = [threading.Thread(target=editar_propio, args=par) for par in enumerate(sesiones)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(resultados, [200] * 5)

    # -- 3. lists: scope, filters, order, cursors ---------------------------------

    def sembrar(self, base, user, *registros):
        return [self.ok(self.en_base(base, r, user))["terreno"]["id"] for r in registros]

    def test_a_base_list_holds_only_that_base_in_rows_totals_and_facets(self):
        self.sembrar(self.b1, "olga", {"terreno": "Uno A", "estado": "Jalisco", "municipio": "Zapopan",
                                       "tipo_terreno": "Industrial", "moneda": "USD", "asking_price": 5})
        self.sembrar(self.b2, "omar", {"terreno": "Dos A", "estado": "Colima", "municipio": "Manzanillo",
                                       "tipo_terreno": "Agrícola", "moneda": "MXN", "asking_price": 5})
        self.patch(self.t0, {"estado": "Sonora", "tipo_terreno": "Secreto"}, "ada")
        status, body = self.lista(self.b1)
        self.assertEqual((status, body["total"], sorted(t["draft"]["terreno"] for t in body["terrenos"])),
                         (200, 2, ["Lote 1", "Uno A"]))
        self.assertEqual({t["base_id"] for t in body["terrenos"]}, {self.b1})
        self.assertEqual(body["facets"], {"estados": ["Jalisco"], "municipios": ["Zapopan"],
                                          "monedas": ["USD"], "tipos": ["Industrial"]})
        self.assertEqual(set(body), {"terrenos", "total", "next_cursor", "facets"})
        # Archived records only when asked for.
        self.assertEqual(self.lista(self.b1, "include_archived=true")[1]["total"], 3)
        self.assertEqual([t["id"] for t in self.lista(self.b1, "publication_state=archived")[1]["terrenos"]],
                         [self.ta])
        # Filters cannot widen the scope; neither can asking for another base.
        for query in ("estado=Colima", "estado=Sonora", "q=Dos", "tipo_terreno=Secreto", "moneda=MXN",
                      "q=Lote%203"):
            self.assertEqual(self.lista(self.b1, query)[1]["total"], 0, query)
        status, body = self.lista(self.b1, f"base={self.b2}")
        self.assertEqual((status, list(body["detalle"]["fields"])), (422, ["base"]))
        self.assertEqual(self.lista(self.b2, user="omar")[1]["total"], 2)
        # Out of scope: 404 before the query is even looked at.
        fuera = [self.lista(self.b2), self.lista(self.b3), self.lista(self.b1, user="otto"),
                 self.lista(nuevo()), self.lista(self.b2, "limit=9999&no=existe"),
                 self.lista(nuevo(), user="ada")]
        self.assertEqual({encode(r) for r in fuera}, {encode(BASE_NO_EXISTE)})
        self.assertEqual(self.lista(self.b3, user="ada")[0], 200)  # an administrator may read an archived base

    def test_the_master_table_filters_by_base_type_and_unassigned(self):
        self.sembrar(self.b1, "olga", {"tipo_terreno": "Industrial"}, {"tipo_terreno": "Agrícola"})
        self.sembrar(self.b2, "omar", {"tipo_terreno": "Industrial"})
        todo = self.maestra()
        self.assertEqual((todo["total"], todo["facets"]["tipos"]), (7, ["Agrícola", "Industrial"]))

        def ids(query):
            return self.maestra(query)["total"]
        self.assertEqual([ids(f"base={self.b1}"), ids(f"base={self.b2}"), ids("base=sin_asignar"),
                          ids(f"base={self.b1}&base=sin_asignar"), ids(f"base={self.b3}"),
                          ids(f"base={nuevo()}"), ids("tipo_terreno=Industrial"),
                          ids(f"tipo_terreno=Industrial&base={self.b2}"),
                          ids("tipo_terreno=Industrial&tipo_terreno=Agr%C3%ADcola"),
                          ids(f"base={self.b1}&include_archived=1")], [3, 2, 1, 4, 1, 0, 2, 1, 3, 4])
        self.assertEqual(self.maestra(f"base={self.b2}")["facets"]["tipos"], ["Industrial"])
        status, body = self.call("GET", "/api/inventario/terrenos?base=todas")
        self.assertEqual((status, list(body["detalle"]["fields"])), (422, ["base"]))

    def test_order_missing_values_case_and_accents_are_the_same_on_both_databases(self):
        nombres = ["árbol", "Zeta", "alfa", "Ñandú", "nube", "Árbol 2", None, "ALFA"]
        superficies = [30, None, 10, 20, 10, None, 5, 40]
        nueva = self.crear_base("Base Ordenada")
        ids = self.sembrar(nueva, "ada", *({"terreno": n, "superficie_m2": s}
                                           for n, s in zip(nombres, superficies)))
        por_id = dict(zip(ids, nombres))

        def recorrer(sort, limit=3):
            vistos, cursor = [], None
            while True:
                query = f"sort={sort}&limit={limit}" + (f"&cursor={cursor}" if cursor else "")
                body = self.ok(self.lista(nueva, query, "ada"))
                self.assertEqual(body["total"], 8)
                vistos += [t["id"] for t in body["terrenos"]]
                cursor = body["next_cursor"]
                if not cursor:
                    return vistos
        iguales = sorted(i for i in ids if (por_id[i] or "").lower() == "alfa")
        self.assertEqual([por_id[i] for i in recorrer("terreno")],
                         [por_id[iguales[0]], por_id[iguales[1]], "árbol", "Árbol 2", "Ñandú", "nube", "Zeta", None])
        self.assertEqual(recorrer("terreno")[:2], iguales)  # equal keys: the id decides
        self.assertEqual([por_id[i] for i in recorrer("-terreno")][:5] + [por_id[recorrer("-terreno")[-1]]],
                         ["Zeta", "nube", "Ñandú", "Árbol 2", "árbol", None])  # missing last either way
        area = dict(zip(ids, superficies))
        self.assertEqual([area[i] for i in recorrer("superficie_m2")], [5, 10, 10, 20, 30, 40, None, None])
        self.assertEqual([area[i] for i in recorrer("-superficie_m2", 2)], [40, 30, 20, 10, 10, 5, None, None])
        for sort in ("id", "-id", "terreno", "-superficie_m2", "updated_at", "-updated_at"):
            for limit in (1, 3, 200):
                self.assertEqual(sorted(recorrer(sort, limit)), sorted(ids), (sort, limit))
        self.assertEqual(recorrer("id"), sorted(ids))

        def buscar(q):
            return sorted(por_id[t["id"]] or "" for t in self.ok(self.lista(nueva, f"q={q}", "ada"))["terrenos"])
        self.assertEqual(buscar("arbol"), ["Árbol 2", "árbol"])
        self.assertEqual(buscar("%C3%81RBOL"), ["Árbol 2", "árbol"])
        self.assertEqual(buscar("NANDU"), ["Ñandú"])
        self.assertEqual(buscar("alfa"), ["ALFA", "alfa"])
        self.assertEqual(buscar("%20%20ARBOL%20%202"), ["Árbol 2"])

    def test_query_values_are_values_and_identifiers_are_allowlisted(self):
        nueva = self.crear_base("Base Literal")
        self.sembrar(nueva, "ada", {"terreno": "100% llano"}, {"terreno": "a_b"}, {"terreno": "axb"},
                     {"terreno": "O'Brien; DROP TABLE inventory_terrain; --", "estado": "x' OR '1'='1"},
                     {"terreno": "signo ! final"})

        def total(query):
            return self.ok(self.lista(nueva, query, "ada"))["total"]
        self.assertEqual([total("q=%25"), total("q=_"), total("q=a_b"), total("q=%27"), total("q=%21"),
                          total("q=%25%27%20OR%201%3D1%20--"), total("estado=x%27%20OR%20%271%27%3D%271"),
                          total("estado=x"), total("q=DROP%20TABLE"), total("tipo_terreno=%27%29%20OR%201%3D1--")],
                         [1, 2, 1, 1, 1, 0, 1, 0, 1, 0])  # "_" is also in inventory_terrain
        self.assertEqual(self.cuenta("inventory_terrain"), 10)
        for query, campo in (("sort=id;DROP%20TABLE%20x", "sort"), ("sort=notas_internas", "sort"),
                             ("sort=--id", "sort"), ("sort=d.terreno", "sort"), ("notas_internas=x", "notas_internas"),
                             ("limit=201", "limit"), ("limit=0", "limit"), ("base=x", "base"),
                             ("cursor=no-es-cursor&sort=terreno", "cursor"), ("price_min=1", "moneda")):
            status, body = self.lista(nueva, query, "ada")
            self.assertEqual((status, body["detalle"]["code"]), (422, "validation_failed"), query)
            self.assertIn(campo, body["detalle"]["fields"], query)
        # A cursor is a position in one order; it is not accepted for another.
        cursor = self.ok(self.lista(nueva, "sort=terreno&limit=2", "ada"))["next_cursor"]
        self.assertEqual(json.loads(base64.urlsafe_b64decode(cursor))[0], "terreno")
        self.assertEqual(self.lista(nueva, f"sort=-terreno&cursor={cursor}", "ada")[0], 422)
        # ...and it carries no authority: in another base it selects that base's rows or none.
        self.assertEqual(self.lista(self.b2, f"sort=terreno&cursor={cursor}")[0], 404)
        ajena = self.ok(self.lista(self.b1, f"sort=terreno&cursor={cursor}"))
        self.assertEqual({t["base_id"] for t in ajena["terrenos"]} - {self.b1}, set())
        falso = base64.urlsafe_b64encode(json.dumps(["terreno", "", self.t2]).encode()).decode()
        self.assertEqual({t["base_id"] for t in self.ok(self.lista(self.b1, f"sort=terreno&cursor={falso}"))
                          ["terrenos"]}, {self.b1})

    def test_the_attention_filter_partitions_the_list(self):
        completo = {**CAMPOS, "moneda": "USD", "availability": "available"}
        (tid,) = self.sembrar(self.b1, "olga", completo)
        self.ok(self.patch(tid, {}, "olga", confirm=["price", "availability"]))
        todos, si, no = (self.ok(self.lista(self.b1, q)) for q in ("", "attention=true", "attention=false"))
        self.assertEqual((todos["total"], si["total"], no["total"]), (2, 1, 1))
        self.assertEqual([t["id"] for t in no["terrenos"]], [tid])
        self.assertEqual(no["terrenos"][0]["attention"], [])
        self.assertEqual(self.ok(self.lista(self.b1, "attention=true&limit=1"))["next_cursor"], None)

    def test_the_attention_filter_in_sql_is_the_rule_shown_on_each_record(self):
        """The filter is a SQL predicate; the reasons on a record are Python.
        One record per rule, alone and at its tolerance boundary, on each
        database: the two must agree on every one, page after page."""
        limpio = {**CAMPOS, "moneda": "USD", "availability": "available"}
        ambas, cerca = ["price", "availability"], math.nextafter
        casos = [({}, c) for c in ([], ["price"], ["availability"], ambas)]
        casos += [(cambio, ambas) for cambio in (
            {"terreno": None}, {"lat": None}, {"lat": -20.7, "lon": 103.4}, {"lat": 40},
            {"superficie_m2": None, "superficie_ha": None}, {"superficie_m2": 0, "superficie_ha": 0},
            {"superficie_m2": None}, {"superficie_ha": None}, {"superficie_m2": 0},
            {"availability": "unknown"}, {"availability": "sold"},
            {"asking_price": None, "asking_m2": None}, {"asking_price": None}, {"asking_m2": None},
            {"moneda": None}, {"moneda": "MXN"}, {"estado": None}, {"municipio": None},
            {"asking_price": 0}, {"asking_m2": 0}, {"asking_price": 0, "asking_m2": 0},
            # Area: Ha x 10 000 against m2, one square metre of tolerance.
            {"superficie_ha": 1.2001}, {"superficie_ha": cerca(1.2001, 2)}, {"superficie_ha": cerca(1.2001, 0)},
            {"superficie_ha": 1.1999}, {"superficie_ha": cerca(1.1999, 2)}, {"superficie_ha": cerca(1.1999, 0)},
            {"superficie_ha": 1.3},
            # Price: unit price x m2 against the total, 2 % of the larger one.
            {"asking_price": 1500000}, {"asking_price": cerca(1500000, 2e6)}, {"asking_price": cerca(1500000, 0)},
            {"asking_price": 1440600}, {"asking_price": cerca(1440600, 2e6)}, {"asking_price": cerca(1440600, 0)},
            {"asking_price": 14700000}, {"asking_m2": 125.0}, {"asking_m2": 120.0},
            {"afectaciones_pct": 0.5}, {"afectaciones_pct": cerca(0.5, 1)}, {"afectaciones_pct": 0.85},
            {"afectaciones_pct": 1.5}, {"afectaciones_pct": None},
            # Numbers no database can multiply: flagged, never computed.
            {"asking_price": 1e200, "asking_m2": 1e200}, {"asking_m2": 1e-200, "superficie_m2": 1e-200},
            {"superficie_ha": 1e305}, {"superficie_ha": 1e-150}, {"asking_price": 1.7e308},
            {"asking_price": 1e100, "asking_m2": 1e100, "superficie_m2": 1, "superficie_ha": 1e-4},
            {"asking_price": 1e-100, "asking_m2": 1e-100, "superficie_m2": 1, "superficie_ha": 1e-4},
        )]
        casos += [({"price_on_request": True, **cambio}, ["availability"]) for cambio in (
            {}, {"asking_price": None, "asking_m2": None}, {"asking_price": None})]
        nueva = self.crear_base("Base Atención")
        for cambio, confirmar in casos:
            (tid,) = self.sembrar(nueva, "ada", {**limpio, **cambio})
            if confirmar:
                self.ok(self.patch(tid, {}, "ada", confirm=confirmar))

        def todas(query):
            ids, cursor, total = [], "", None
            while cursor is not None:
                pagina = self.ok(self.lista(nueva, f"{query}&limit=7&cursor={cursor}", "ada"))
                self.assertIn(total, (None, pagina["total"]))
                total, cursor = pagina["total"], pagina["next_cursor"]
                ids += [(t["id"], sorted({r["code"] for r in t["attention"]})) for t in pagina["terrenos"]]
            self.assertEqual(total, len(ids))
            return ids

        for orden in ("id", "-asking_price", "terreno"):
            vistas = todas(f"sort={orden}")
            self.assertEqual(len(vistas), len(casos))
            self.assertEqual(sorted(todas(f"sort={orden}&attention=true")), sorted(v for v in vistas if v[1]))
            self.assertEqual(sorted(todas(f"sort={orden}&attention=false")), sorted(v for v in vistas if not v[1]))
        # Every rule is exercised alone, and some record is beyond each boundary on each side.
        solas = {v[1][0] for v in vistas if len(v[1]) == 1}
        self.assertLessEqual({
            "name_required", "location_invalid", "area_required", "availability_unknown", "price_conflict",
            "price_required", "currency_required", "price_unconfirmed", "availability_unconfirmed",
            "CAMPO_FALTANTE", "SUPERFICIE_INCONSISTENTE", "PRECIO_CERO", "PRECIO_INCONSISTENTE",
            "AFECTACION_ALTA", "AFECTACION_FORMATO"}, solas | {"price_conflict", "area_required"})
        todos_los_codigos = {c for v in vistas for c in v[1]}
        self.assertLessEqual({"price_conflict", "area_required", "VALOR_FUERA_DE_RANGO"}, todos_los_codigos)
        self.assertGreater(sum(1 for v in vistas if not v[1]), 10)

    def test_a_cursor_is_validated_before_it_reaches_the_database(self):
        nueva = self.crear_base("Base Cursores")
        ids = self.sembrar(nueva, "ada", *(
            {"terreno": n, "asking_price": p, "superficie_m2": p}
            for n, p in (("Ébano", 5), ("abeto", None), ("Cedro", 1.7976931348623157e308), (None, 0.5),
                         ("cedro", 5), (None, None), ("Álamo", 1e-300))))

        def cursor(*partes):
            return base64.urlsafe_b64encode(json.dumps(list(partes)).encode()).decode()

        def pedir(sort, c, base=None):
            return self.lista(base or nueva, f"sort={sort}&limit=2&cursor={c}", "ada")
        uno = ids[0]
        malos = [
            # The supervisor's four probes.
            ("asking_price", cursor("asking_price", "not-a-number", uno)),
            ("asking_price", cursor("asking_price", 10**1000, uno)),
            ("terreno", cursor("terreno", 5, uno)),
            ("terreno", cursor("terreno", float("nan"), uno)),
            # Not a number a double can hold, or not finite.
            ("asking_price", cursor("asking_price", float("inf"), uno)),
            ("-asking_price", cursor("-asking_price", float("-inf"), uno)),
            ("asking_price", base64.urlsafe_b64encode(
                f'["asking_price", 1e999, "{uno}"]'.encode()).decode()),
            ("superficie_m2", cursor("superficie_m2", True, uno)),
            ("superficie_m2", cursor("superficie_m2", [1], uno)),
            ("superficie_m2", cursor("superficie_m2", {"a": 1}, uno)),
            # Text that is not text, or that no database stores.
            ("terreno", cursor("terreno", 1.5, uno)), ("updated_at", cursor("updated_at", 5, uno)),
            ("terreno", cursor("terreno", "a\x00b", uno)), ("estado", cursor("estado", "\ud800", uno)),
            # Shape, sort and id.
            ("terreno", "no-es-base64"), ("terreno", "%%%"), ("terreno", "Zm9v"),
            ("terreno", base64.urlsafe_b64encode(b"\xff\xfe").decode()),
            ("terreno", cursor("terreno", "a")), ("terreno", cursor("terreno", "a", uno, "más")),
            ("terreno", base64.urlsafe_b64encode(b'{"sort": "terreno"}').decode()),
            ("terreno", base64.urlsafe_b64encode(b'"terreno"').decode()),
            ("-terreno", cursor("terreno", "a", uno)), ("terreno", cursor("-terreno", "a", uno)),
            ("terreno", cursor("estado", "a", uno)), ("terreno", cursor(["terreno"], "a", uno)),
            ("terreno", cursor("terreno", "a", "no-es-uuid")), ("terreno", cursor("terreno", "a", 5)),
            ("terreno", cursor("terreno", "a", None)), ("terreno", cursor("terreno", "a", uno + "\x00")),
            ("terreno", cursor("terreno", None, "x' OR '1'='1")),
            ("id", "no-es-uuid"), ("id", cursor("id", None, uno)), ("-id", "5"),
        ]
        for sort, c in malos:
            status, body = pedir(sort, urllib.parse.quote(c))
            self.assertEqual((status, body.get("detalle", {}).get("fields")),
                             (422, {"cursor": "Cursor inválido para este orden."}), (sort, c, body))
        # Everything a list can itself emit is accepted: missing values, both ends of a double.
        buenos = [("asking_price", cursor("asking_price", None, uno)),
                  ("asking_price", cursor("asking_price", 1.7976931348623157e308, uno)),
                  ("-asking_price", cursor("-asking_price", -1.7976931348623157e308, uno)),
                  ("asking_price", cursor("asking_price", 5e-324, uno)),
                  ("asking_price", cursor("asking_price", 2**63, uno)),
                  ("asking_price", cursor("asking_price", 0, uno)),
                  ("terreno", cursor("terreno", "", uno)), ("terreno", cursor("terreno", "ñ' OR 1=1 --", uno)),
                  ("terreno", cursor("terreno", None, uno)), ("id", uno), ("id", uno.upper())]
        for sort, c in buenos:
            self.assertEqual(pedir(sort, urllib.parse.quote(c))[0], 200, (sort, c))

        # Valid pagination is untouched: every order, both ways, one pass, no repeats.
        for campo in inventario.SORTS:
            for sort in (campo, "-" + campo):
                vistos, c = [], ""
                while c is not None:
                    pagina = self.ok(pedir(sort, urllib.parse.quote(c)))
                    vistos += [t["id"] for t in pagina["terrenos"]]
                    c = pagina["next_cursor"]
                self.assertEqual((len(vistos), set(vistos)), (len(ids), set(ids)), sort)
                if campo in ("asking_price", "terreno"):  # missing values last, either way
                    claves = [t["draft"][campo] for t in
                              self.ok(self.lista(nueva, f"sort={sort}&limit=200", "ada"))["terrenos"]]
                    self.assertEqual([k is None for k in claves], [False] * 5 + [True] * 2, sort)
        # A cursor from one base selects nothing outside the base it is used in.
        ajeno = self.ok(pedir("terreno", ""))["next_cursor"]
        self.assertEqual({t["base_id"] for t in self.ok(pedir("terreno", ajeno, self.b1))["terrenos"]}
                         - {self.b1}, set())
        self.assertEqual(self.lista(self.b2, f"sort=terreno&cursor={ajeno}")[0], 404)

        # The history cursor is a version number, nothing else.
        for c in ("9" * 40, "%C2%B2", "-1", "1.5", "1e3", "0x10"):
            status, body = self.ver(ids[0], "ada", f"/historial?cursor={c}")
            self.assertEqual((status, body.get("detalle", {}).get("fields")),
                             (422, {"cursor": "Cursor inválido."}), c)
        self.assertEqual(self.ver(ids[0], "ada", "/historial?cursor=999999999999999999")[0], 200)

    # -- 4. archive and restore ---------------------------------------------------

    def test_archiving_is_reversible_and_changes_only_the_archive_state(self):
        adjuntos = self.adjuntos(self.t1)
        antes = self.ver(self.t1)[1]["terreno"]
        status, body = self.accion(self.t1, "archivar")
        t = body["terreno"]
        self.assertEqual((status, t["version"], t["publication_state"], t["draft_revision_id"], t["draft"]),
                         (200, 2, "archived", antes["draft_revision_id"], antes["draft"]))
        self.assertEqual(self.lista(self.b1)[1]["total"], 0)
        self.assertEqual(self.ver(self.t1)[0], 200)  # still readable in scope
        for respuesta, codigo in ((self.patch(self.t1, {"estado": "X"}, "olga"), "terreno_archivado"),
                                  (self.accion(self.t1, "archivar"), "terreno_archivado"),
                                  (self.accion(self.t1, "transferir", "ada", base_id=self.b2), "terreno_archivado")):
            self.assertEqual((respuesta[0], respuesta[1]["detalle"]["code"]), (409, codigo))
        status, body = self.call("POST", f"/api/inventario/terrenos/{self.t1}/restaurar", {"expected_version": 1})
        self.assertEqual((status, body["detalle"]["code"], body["detalle"]["current_version"]), (409, "conflict", 2))
        status, body = self.accion(self.t1, "restaurar", "omar")
        self.assertEqual((status, body["terreno"]["version"], body["terreno"]["publication_state"],
                          body["terreno"]["id"]), (200, 3, "draft", self.t1))
        status, body = self.accion(self.t1, "restaurar")
        self.assertEqual((status, body["detalle"]["code"]), (409, "terreno_no_archivado"))
        self.assertEqual(self.patch(self.t1, {"estado": "Jalisco"}, "olga")[0], 200)
        eventos = self.ver(self.t1, sufijo="/historial")[1]["eventos"]
        self.assertEqual([(e["version"], e["action"], e["actor"]["display_name"]) for e in eventos][-3:], [
            (3, "restore", "Omar Ficticia"), (2, "archive", "Olga Ficticia"), (1, "create", "Ada Ficticia")])
        self.assertEqual(self.cuenta("inventory_revision", "inventory_id = ?", (self.t1,)), 2)  # only the edit
        self.assertEqual({t: filas(t) for t in ARCHIVOS}, adjuntos)

    def test_archive_and_restore_are_refused_out_of_scope_or_in_an_archived_base(self):
        casos = [self.accion(self.t2, "archivar"), self.accion(self.t0, "archivar"),
                 self.accion(self.t3, "restaurar"), self.accion(self.t1, "archivar", "otto"),
                 self.call("POST", f"/api/inventario/terrenos/{nuevo()}/archivar", {"expected_version": 1}, "olga"),
                 self.call("POST", f"/api/inventario/terrenos/{self.t2}/archivar", {"expected_version": "x"}, "olga")]
        self.assertEqual({encode(r) for r in casos}, {encode(NO_EXISTE)})
        for accion in ("archivar", "restaurar"):  # restoring a terrain cannot reopen its base
            status, body = self.accion(self.t3, accion, "ada")
            self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))
        self.assertEqual(self.accion(self.t0, "archivar", "ada")[0], 200)
        for cuerpo in ({}, {"expected_version": 0}, {"expected_version": 1, "motivo": "x"}):
            status, body = self.call("POST", f"/api/inventario/terrenos/{self.t1}/archivar", cuerpo, "olga")
            self.assertEqual((status, body["detalle"]["code"]), (422, "validation_failed"))
        self.assertEqual([self.version(t) for t in (self.t1, self.t2, self.t3)], [1, 1, 1])

    def test_an_operator_cannot_change_what_the_public_sees_by_archiving(self):
        sql(lambda c: c.execute(
            "UPDATE inventory_terrain SET published_revision_id = draft_revision_id, published_at = ?,"
            " first_published_at = ? WHERE id = ?", (db.now(), db.now(), self.t1)))
        status, body = self.accion(self.t1, "archivar")
        self.assertEqual((status, body["detalle"]["code"]), (403, "requiere_admin"))
        self.assertEqual(self.version(self.t1), 1)
        status, body = self.accion(self.t1, "archivar", "ada")
        self.assertEqual((status, body["terreno"]["publication_state"],
                          body["terreno"]["published_revision_id"] is not None), (200, "archived", True))
        self.assertEqual(self.accion(self.t1, "restaurar")[1]["detalle"]["code"], "requiere_admin")
        self.assertEqual(self.accion(self.t1, "restaurar", "ada")[1]["terreno"]["publication_state"], "published")

    # -- 5. transfers --------------------------------------------------------------

    def test_a_transfer_moves_the_one_record_with_its_files_and_history(self):
        adjuntos = self.adjuntos(self.t1)
        self.ok(self.patch(self.t1, {"estado": "Jalisco"}, "olga", confirm=["price"]))
        antes = self.ver(self.t1, "ada")[1]["terreno"]
        status, body = self.accion(self.t1, "transferir", "ada", base_id=self.b2)
        t = body["terreno"]
        self.assertEqual((status, t["id"], t["version"], t["base_id"], t["draft"], t["confirmations"]),
                         (200, self.t1, 3, self.b2, antes["draft"], antes["confirmations"]))
        self.assertNotEqual(t["draft_revision_id"], antes["draft_revision_id"])
        revisiones = filas("inventory_revision", "inventory_id = ?", (self.t1,))
        self.assertEqual(sorted((r["revision_number"], r["base_id"]) for r in revisiones),
                         [(1, self.b1), (2, self.b1), (3, self.b2)])  # earlier revisions are not rewritten
        self.assertEqual(self.cuenta("inventory_terrain"), 5)  # moved, not copied
        self.assertEqual({t: filas(t) for t in ARCHIVOS}, adjuntos)
        # The source-only operator loses it at once; a destination operator has it, history included.
        for respuesta in (self.ver(self.t1), self.ver(self.t1, sufijo="/historial"),
                          self.patch(self.t1, {"estado": "X"}, "olga"), self.accion(self.t1, "archivar"),
                          self.call("PATCH", f"/api/inventario/terrenos/{self.t1}",
                                    {"expected_version": 2, "changes": {"estado": "Tarde"}}, "olga")):
            self.assertEqual(respuesta, NO_EXISTE)
        self.assertEqual(self.lista(self.b1)[1]["total"], 0)
        self.assertEqual(self.lista(self.b2, user="omar")[1]["total"], 2)
        eventos = self.ver(self.t1, "omar", "/historial")[1]["eventos"]
        self.assertEqual([(e["version"], e["action"]) for e in eventos], [(3, "transfer"), (2, "update"), (1, "create")])
        self.assertEqual(eventos[1]["changes"], {"estado": {"before": None, "after": "Jalisco"}})
        self.assertNotIn("base", eventos[0])           # which bases: not for an operator
        self.assertNotIn(self.b1, json.dumps(eventos))
        admin = self.ver(self.t1, "ada", "/historial")[1]["eventos"][0]
        self.assertEqual((admin["base"], admin["actor"]["display_name"]),
                         ({"before": self.b1, "after": self.b2}, "Ada Ficticia"))
        # Same base: nothing happens. No base: administrators only.
        self.assertEqual(self.accion(self.t1, "transferir", "ada", base_id=self.b2)[1]["terreno"]["version"], 3)
        status, body = self.accion(self.t1, "transferir", "alan", base_id=None)
        self.assertEqual((status, body["terreno"]["base_id"], body["terreno"]["version"]), (200, None, 4))
        self.assertEqual(self.ver(self.t1, "omar"), NO_EXISTE)
        self.assertEqual(self.maestra("base=sin_asignar")["total"], 2)

    def test_custom_values_follow_the_base_that_defines_them(self):
        folio, clave = self.columna(self.b1, "Folio"), self.columna(self.b2, "Clave catastral")
        sql(lambda c: c.execute("UPDATE inventory_revision SET custom_json = ? WHERE inventory_id = ?",
                                (json.dumps({folio: "FOLIO-SECRETO-1", clave: "CLAVE-2", "custom:huerfana": "X"}),
                                 self.t1)))

        def custom(user):
            return self.ver(self.t1, user)[1]["terreno"]["custom"]
        self.assertEqual((custom("olga"), custom("ada")), ({folio: "FOLIO-SECRETO-1"}, {folio: "FOLIO-SECRETO-1"}))
        vista = self.ok(self.call("GET", f"/api/inventario/terrenos/{self.t1}/transferir?base_id={self.b2}"))
        self.assertEqual(vista, {
            "terreno": {"id": self.t1, "version": 1}, "origen": self.b1, "destino": self.b2, "sin_cambio": False,
            "acceso": [{"id": self.ids["omar"], "login": "omar", "display_name": "Omar Ficticia", "active": True}],
            "columnas_que_se_ocultan": [{"id": folio, "nombre": "Folio", "con_valor": True}]})
        self.assertEqual(self.version(self.t1), 1)  # the preview changes nothing

        self.ok(self.accion(self.t1, "transferir", "ada", base_id=self.b2))
        self.assertEqual((custom("omar"), custom("ada")), ({clave: "CLAVE-2"}, {clave: "CLAVE-2"}))
        respuestas = [self.ver(self.t1, "omar"), self.ver(self.t1, "omar", "/historial"),
                      self.lista(self.b2, user="omar"), self.patch(self.t1, {"estado": "Colima"}, "omar"),
                      self.call("PATCH", f"/api/inventario/terrenos/{self.t1}",
                                {"expected_version": 1, "changes": {"estado": "Tarde"}}, "omar")]
        self.assertEqual([r[0] for r in respuestas], [200, 200, 200, 200, 409])
        for _, cuerpo in respuestas:  # detail, history, list, edit response, conflict response
            texto = json.dumps(cuerpo)
            self.assertNotIn("FOLIO-SECRETO-1", texto)
            self.assertNotIn(folio, texto)
            self.assertNotIn("Folio", texto)
        # Stored all along, under their own ids, and back in view when the terrain returns.
        guardado = json.loads(filas("inventory_revision", "inventory_id = ?", (self.t1,))[-1]["custom_json"])
        self.assertEqual({r["custom_json"] for r in filas("inventory_revision", "inventory_id = ?", (self.t1,))},
                         {json.dumps({folio: "FOLIO-SECRETO-1", clave: "CLAVE-2", "custom:huerfana": "X"})})
        self.assertEqual(guardado[folio], "FOLIO-SECRETO-1")
        self.ok(self.accion(self.t1, "transferir", "ada", base_id=self.b1))
        self.assertEqual(custom("olga"), {folio: "FOLIO-SECRETO-1"})
        self.ok(self.accion(self.t1, "transferir", "ada", base_id=None))
        self.assertEqual(custom("ada"), {})

    def test_history_shows_custom_changes_of_the_current_base_only(self):
        """Stored history may hold custom-value changes (2A will write them).
        A reader sees those of the terrain's current base's live columns, in
        the one documented shape; the audit itself is never altered."""
        origen, destino, retirada = (self.columna(self.b1, "Folio origen"),
                                     self.columna(self.b2, "Folio destino"), self.columna(self.b2, "Retirada"))
        secreto, otro = "VALOR-SOLO-DE-ORIGEN", "VALOR-DE-DESTINO"
        detalles = {
            "changes": {
                "terreno": {"before": "Antes", "after": "Después"},
                "estado": {"before": None, "after": "Jalisco", "etiqueta": secreto},
                origen: {"before": None, "after": secreto},
                destino: {"before": None, "after": otro},
                retirada: {"before": "x", "after": "VALOR-RETIRADO"},
                # Shapes nothing documents: never passed through.
                "custom_json": {"before": {}, "after": {origen: secreto}},
                "custom": {origen: {"before": None, "after": secreto}},
                "municipio": {"before": {origen: secreto}, "after": [secreto]},
                "direccion": [secreto], "lat": secreto + "-suelto",
                "custom:no-es-uuid": {"before": None, "after": secreto},
                "campo_inventado": {"before": None, "after": secreto},
            },
            "confirmed": ["price", secreto, {"x": secreto}],
            "nota": secreto, "custom": {origen: secreto},
        }
        with db.escritura() as conn:
            conn.execute("UPDATE inventory_revision SET custom_json = ? WHERE inventory_id = ?",
                         (json.dumps({origen: secreto, destino: otro, retirada: "VALOR-RETIRADO"}), self.t1))
            conn.execute("UPDATE inventory_event SET details_json = ? WHERE inventory_id = ? AND version = 1",
                         (json.dumps(detalles), self.t1))

        def primero(user):
            eventos = self.ok(self.ver(self.t1, user, "/historial"))["eventos"]
            return [e for e in eventos if e["version"] == 1][0], json.dumps(eventos, ensure_ascii=False)
        nucleo = {"terreno": {"before": "Antes", "after": "Después"},
                  "estado": {"before": None, "after": "Jalisco"}}
        # In the source base: its own column, the core changes, and nothing undocumented.
        evento, texto = primero("olga")
        self.assertEqual(evento["changes"], {**nucleo, origen: {"before": None, "after": secreto}})
        self.assertEqual(evento["confirmed"], ["price"])
        self.assertEqual(set(evento) - {"id", "version", "action", "at", "actor", "before_revision_id",
                                        "after_revision_id"}, {"changes", "confirmed"})
        self.assertNotIn(otro, texto)
        self.assertNotIn("VALOR-RETIRADO", texto)

        self.ok(self.accion(self.t1, "transferir", "ada", base_id=self.b2))
        self.ok(self.otorgar(self.b1, "olga"))  # omar keeps the destination only
        # The source-only reader has no record; the destination-only reader has no source value.
        self.assertEqual([self.ver(self.t1, "olga", s) for s in ("", "/historial")], [NO_EXISTE] * 2)
        evento, texto = primero("omar")
        self.assertEqual(evento["changes"], {**nucleo, destino: {"before": None, "after": otro},
                                             retirada: {"before": "x", "after": "VALOR-RETIRADO"}})
        self.assertNotIn(secreto, texto)
        self.assertNotIn(self.b1, texto)  # nor where it came from
        with db.escritura() as conn:
            conn.execute("UPDATE inventory_column SET retired_at = ? WHERE id = ?",
                         (db.now(), retirada.split(":")[1]))
        evento, texto = primero("omar")
        self.assertEqual(evento["changes"], {**nucleo, destino: {"before": None, "after": otro}})
        self.assertNotIn("VALOR-RETIRADO", texto)
        # Nothing else he can ask about the record carries it either.
        otras = [self.ver(self.t1, "omar"), self.lista(self.b2, user="omar"),
                 self.lista(self.b2, "q=VALOR-SOLO-DE-ORIGEN", "omar"),
                 self.call("PATCH", f"/api/inventario/terrenos/{self.t1}",
                           {"expected_version": 1, "changes": {"estado": "Colima"}}, "omar"),
                 self.call("POST", f"/api/inventario/terrenos/{self.t1}/archivar", {"expected_version": 1}, "omar")]
        self.assertEqual([r[0] for r in otras], [200, 200, 200, 409, 409])
        self.assertEqual(otras[2][1]["total"], 0)
        self.assertEqual(otras[0][1]["terreno"]["custom"], {destino: otro})
        self.assertNotIn(secreto, json.dumps(otras))
        self.assertNotIn("VALOR-RETIRADO", json.dumps(otras))
        # The administrators' audit is whole, in either place.
        evento, texto = primero("ada")
        self.assertEqual({k: evento[k] for k in detalles}, detalles)
        self.assertIn(self.b1, texto)

        self.ok(self.accion(self.t1, "transferir", "ada", base_id=self.b1))
        # Back in the source base: the value was kept, and its history with it.
        evento, texto = primero("olga")
        self.assertEqual(evento["changes"], {**nucleo, origen: {"before": None, "after": secreto}})
        self.assertNotIn(otro, texto)
        self.assertEqual(self.ok(self.ver(self.t1))["terreno"]["custom"], {origen: secreto})
        self.assertEqual(json.loads(filas("inventory_event", "inventory_id = ? AND version = 1",
                                          (self.t1,))[0]["details_json"]), detalles)
        # The events the writers produce today come through unchanged.
        self.ok(self.patch(self.t1, {"estado": "Sonora", "asking_price": 5.5, "price_on_request": False},
                           "olga", confirm=["availability"]))
        evento = self.ok(self.ver(self.t1, "olga", "/historial"))["eventos"][0]
        self.assertEqual((evento["changes"], evento["confirmed"]),
                         ({"estado": {"before": None, "after": "Sonora"},
                           "asking_price": {"before": None, "after": 5.5}}, ["availability"]))
        self.assertEqual(evento, self.ok(self.ver(self.t1, "ada", "/historial"))["eventos"][0])

    def test_transfers_are_validated_and_administrators_only(self):
        ruta = f"/api/inventario/terrenos/{self.t1}/transferir"
        for user in ("olga", "omar", "otto"):
            for method, cuerpo in (("POST", {"expected_version": 1, "base_id": self.b2}), ("GET", None)):
                status, body = self.call(method, ruta + (f"?base_id={self.b2}" if method == "GET" else ""),
                                         cuerpo, user)
                self.assertEqual((status, body["detalle"]), (403, {"code": "forbidden", "capacidad": "bases.gestionar"}))
        for cuerpo, campo in (({"expected_version": 1}, "base_id"), ({"base_id": self.b2}, "expected_version"),
                              ({"expected_version": 1, "base_id": "no-es-uuid"}, "base_id"),
                              ({"expected_version": 1, "base_id": 7}, "base_id"),
                              ({"expected_version": 1, "base_id": nuevo()}, "base_id"),
                              ({"expected_version": 1, "base_id": self.b2, "actor_id": "x"}, "actor_id")):
            status, body = self.call("POST", ruta, cuerpo)
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [campo]), cuerpo)
        status, body = self.call("POST", ruta, {"expected_version": 1, "base_id": self.b3})
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))  # archived destination
        status, body = self.accion(self.t3, "transferir", "ada", base_id=self.b1)
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))  # archived source
        status, body = self.call("POST", ruta, {"expected_version": 7, "base_id": self.b2})
        self.assertEqual((status, body["detalle"]["code"]), (409, "conflict"))
        self.assertEqual(self.call("POST", f"/api/inventario/terrenos/{nuevo()}/transferir",
                                   {"expected_version": 1, "base_id": self.b2}), NO_EXISTE)
        for query in ("", "?base=x", "?base_id=", f"?base_id={self.b2}&otro=1", "?base_id=no-es-uuid",
                      f"?base_id={nuevo()}"):
            self.assertEqual(self.call("GET", ruta + query)[0], 422, query)
        vista = self.ok(self.call("GET", ruta + "?base_id=sin_asignar"))
        self.assertEqual((vista["destino"], vista["acceso"], vista["sin_cambio"]), (None, [], False))
        self.assertTrue(self.ok(self.call("GET", ruta + f"?base_id={self.b1}"))["sin_cambio"])
        self.assertEqual((self.version(self.t1), self.version(self.t3)), (1, 1))

    def carrera(self, pausado, primero, despues):
        """Hold ``pausado`` (a repo function) just before it writes, inside its
        transaction and after its authorization, while ``despues`` is attempted."""
        dentro, seguir, hecho, resultado = threading.Event(), threading.Event(), threading.Event(), {}
        real = getattr(repo, pausado)

        def con_barrera(*args, **kwargs):
            dentro.set()
            assert seguir.wait(15)
            return real(*args, **kwargs)

        def uno():
            resultado["primero"] = primero()

        def otro():
            resultado["despues"] = despues()
            hecho.set()
        with patch.object(api_inventario.repo, pausado, con_barrera):
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

    def test_a_transfer_and_an_edit_never_both_win_on_one_version(self):
        def editar():
            return self.call("PATCH", f"/api/inventario/terrenos/{self.t1}",
                             {"expected_version": 1, "changes": {"estado": "Jalisco"}}, "olga")

        def transferir():
            return self.call("POST", f"/api/inventario/terrenos/{self.t1}/transferir",
                             {"expected_version": 1, "base_id": self.b2})
        # The edit holds the boundary: the transfer waits, then finds a newer version.
        edicion, traslado = self.carrera("update", editar, transferir)
        self.assertEqual((edicion[0], traslado[0], traslado[1]["detalle"]["code"]), (200, 409, "conflict"))
        self.assertEqual(filas("inventory_terrain", "id = ?", (self.t1,))[0]["base_id"], self.b1)
        # The transfer holds the boundary: the stale edit waits, then is out of scope.
        def transferir_2():
            return self.call("POST", f"/api/inventario/terrenos/{self.t1}/transferir",
                             {"expected_version": 2, "base_id": self.b2})

        def editar_2():
            return self.call("PATCH", f"/api/inventario/terrenos/{self.t1}",
                             {"expected_version": 2, "changes": {"estado": "Colima"}}, "olga")
        traslado, edicion = self.carrera("transferir", transferir_2, editar_2)
        self.assertEqual((traslado[0], edicion), (200, NO_EXISTE))
        self.assertEqual((self.version(self.t1), self.cuenta("inventory_event", "inventory_id = ?", (self.t1,)),
                          self.ver(self.t1, "ada")[1]["terreno"]["draft"]["estado"]), (3, 3, "Jalisco"))

    def test_a_transfer_and_a_change_to_its_destination_are_serialized(self):
        def transferir(version):
            return lambda: self.call("POST", f"/api/inventario/terrenos/{self.t1}/transferir",
                                     {"expected_version": version, "base_id": self.b2})
        # Destination archived first: the transfer is refused and nothing moves.
        self.ok(self.archivar(self.b2))
        status, body = transferir(1)()
        self.assertEqual((status, body["detalle"]["code"], self.version(self.t1)), (409, "base_archivada", 1))
        self.ok(self.archivar(self.b2, "restaurar"))
        # Transfer first: archiving the destination, and revoking its grant, wait for it.
        version_b2 = self.base(self.b2)["version"]
        traslado, archivo = self.carrera("transferir", transferir(1), lambda: self.call(
            "POST", f"/api/maestra/bases/{self.b2}/archivar", {"expected_version": version_b2}))
        self.assertEqual((traslado[0], archivo[0]), (200, 200))
        self.assertEqual(filas("inventory_terrain", "id = ?", (self.t1,))[0]["base_id"], self.b2)
        self.assertEqual(self.ver(self.t1, "omar"), NO_EXISTE)  # its base is archived now
        self.ok(self.archivar(self.b2, "restaurar"))
        version_b1 = self.base(self.b1)["version"]
        traslado, revocacion = self.carrera(
            "transferir",
            lambda: self.call("POST", f"/api/inventario/terrenos/{self.t1}/transferir",
                              {"expected_version": 2, "base_id": self.b1}),
            lambda: self.call("PUT", f"/api/maestra/bases/{self.b1}/acceso",
                              {"expected_version": version_b1, "usuarios": []}))
        self.assertEqual((traslado[0], revocacion[0]), (200, 200))
        self.assertEqual(self.ver(self.t1), NO_EXISTE)       # moved into b1 just before olga lost it
        self.assertEqual(self.ver(self.t1, "ada")[1]["terreno"]["base_id"], self.b1)

    # -- 6. what stays closed -------------------------------------------------------

    def test_public_output_and_operator_limits_are_unchanged(self):
        self.sembrar(self.b1, "olga", CAMPOS)
        self.assertEqual(self.call("GET", "/api/publico/terrenos", user=None)[1],
                         {"terrenos": [], "total": 0, "next_cursor": None,
                          "facets": {"estados": [], "municipios": [], "monedas": []}})
        status, body = self.call("GET", "/api/inventario/terrenos?limit=1", user="olga")
        self.assertEqual((status, body["detalle"]["capacidad"]), (403, "maestra.global"))
        registro = self.lista(self.b1)[1]["terrenos"][0]
        self.assertFalse({"custom_json", "extra_json", "ubicacion", "archivos", "geometria"} & set(registro))
        self.assertFalse({"base_id", "custom", "custom_json"} & set(registro["draft"]))
        self.assertEqual(set(auth.CAPACIDADES["operador"]) & {"maestra.global", "bases.gestionar"}, set())


class RegistrosSqlite(Registros, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._dir.name) / "prueba.db"
        self._entorno = patch.dict(os.environ, {"ARA_MAP_DB": str(self.db_path)})
        self._entorno.start()
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        self.addCleanup(self._dir.cleanup)
        self.addCleanup(self._entorno.stop)
        self.levantar()

    def test_a_page_costs_the_same_number_of_queries_whatever_its_size(self):
        nueva = self.crear_base("Base Medida")
        self.columna(nueva, "Folio")

        def consultas(n):
            q = inventario.parse_query({"limit": [str(n)], "sort": ["terreno"], "q": ["lote"]},
                                       inventario.SCOPED_QUERY)
            with db.session() as conn:
                contadas = []
                conn.set_trace_callback(contadas.append)
                pagina = repo.listar(conn, q, nueva)[0]
                conn.set_trace_callback(None)
            return len(pagina), len(contadas)
        self.sembrar(nueva, "ada", *({"terreno": f"Lote {n}"} for n in range(3)))
        pocas = consultas(2)
        self.sembrar(nueva, "ada", *({"terreno": f"Lote {n}"} for n in range(3, 40)))
        self.assertEqual((pocas, consultas(40)), ((2, pocas[1]), (40, pocas[1])))
        self.assertLessEqual(pocas[1], 7)  # count, page, four facets, custom columns

    def test_the_attention_filter_reads_one_page_and_counts_in_sql(self):
        nueva = self.crear_base("Base Acotada")
        self.sembrar(nueva, "ada", *({"terreno": f"Lote {n}"} for n in range(12)))
        for valor in ("true", "false"):
            q = inventario.parse_query({"limit": ["5"], "attention": [valor]}, inventario.SCOPED_QUERY)
            with db.session() as conn:
                contadas = []
                conn.set_trace_callback(contadas.append)
                pagina, total, siguiente, _ = repo.listar(conn, q, nueva)
                conn.set_trace_callback(None)
            self.assertEqual((len(pagina), total, bool(siguiente)),
                             (5, 12, True) if valor == "true" else (0, 0, False))
            # One COUNT and one page of limit + 1 rows: no statement reads the base's records unbounded.
            registros = [c for c in contadas if "FROM inventory_terrain t" in c and "DISTINCT" not in c]
            self.assertEqual(len(registros), 2, contadas)
            self.assertTrue(registros[0].startswith("SELECT COUNT(*)"))
            self.assertTrue(registros[1].endswith("LIMIT 6"), registros[1][-40:])
            self.assertLessEqual(len(contadas), 7)

    def test_folding_is_one_table_for_both_databases(self):
        self.assertEqual(db.plegar("ÁRBOL Ñandú Çedilla üÜ"), "arbol nandu cedilla uu")
        self.assertIsNone(db.plegar(None))
        with db.session() as conn:
            self.assertEqual(conn.execute("SELECT ara_plegar('ÁRBOL Ñandú') AS v").fetchone()["v"], "arbol nandu")
            self.assertEqual(db.sql_plegar(conn, "x"), "ara_plegar(x)")
        self.assertIsInstance(sqlite3.connect(":memory:"), sqlite3.Connection)


@unittest.skipUnless(URL, "No Postgres test connection configured")
class RegistrosPostgres(Registros, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.schema = "test_ara_registros_" + uuid.uuid4().hex
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

    def test_folding_matches_the_python_table(self):
        texto = "ÁRBOL Ñandú Çedilla üÜ ABC xyz"
        with db.session() as conn:
            fila = conn.execute(f"SELECT {db.sql_plegar(conn, '?')} AS v", (texto,)).fetchone()
        self.assertEqual(fila["v"], db.plegar(texto))


if __name__ == "__main__":
    unittest.main()

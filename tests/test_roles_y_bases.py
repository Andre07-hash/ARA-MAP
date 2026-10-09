"""Roles, work-base access and authorization at the write boundary (A-2/P2).

One behavioural matrix, run through the real HTTP dispatcher with real
sessions, on SQLite and (when ARA_MAP_TEST_DATABASE_URL is set) on a
disposable Postgres schema. Fictional accounts:

    ada, alan   administrators
    olga        operator granted Base Uno (and the archived base)
    omar        operator granted Base Uno and Base Dos
    otto        operator with no grant

    t1 in Base Uno · t2 in Base Dos · t0 unassigned · ta archived, in Base Uno
    t3 in Base Archivada (an archived work base)
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import app as app_module
from server import auth, db, postgres
from server.errors import ApiError
from server.web_util import encode
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
ADMINS, OPERADORES = ("ada", "alan"), ("olga", "omar", "otto")
ADMIN_ONLY = {"maestra.global", "bases.gestionar", "derivados.ver", "derivados.gestionar",
              "usuarios.gestionar"}
AUDITADAS = ("maestra_base", "maestra_base_acceso", "maestra_base_event", "team_user_event")
CONTENIDO = ("inventory_terrain", "inventory_revision", "inventory_event", "inventory_column",
             "maestra_base_acceso", "archivo", "archivo_version", "archivo_evento", "mapa",
             "mapa_terreno")


def nuevo():
    return str(uuid.uuid4())


def sql(fn):
    with db.session() as conn:
        return fn(conn)


def cuenta(fn):
    """An account change, entered like scripts/cuentas.py enters it."""
    with db.escritura() as conn:
        return fn(conn)


def filas(tabla, donde="1 = 1", params=()):
    return sql(lambda c: sorted((dict(r) for r in c.execute(
        f"SELECT * FROM {tabla} WHERE {donde}", params).fetchall()), key=repr))


class Escenario:
    """The shared fixture and HTTP client. A backend adds the database."""

    def levantar(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()
        self.addCleanup(self.bajar)
        with db.session() as conn:
            self.ids = {n: auth.create_user(conn, n, n.capitalize() + " Ficticia", TEST_PASSWORD,
                                            iterations=1000,
                                            rol="admin" if n in ADMINS else "operador")["id"]
                        for n in ADMINS + OPERADORES}
        self.cookies = {n: self.entrar(n) for n in self.ids}
        self.b1, self.b2, self.b3 = (self.crear_base(n) for n in ("Base Uno", "Base Dos", "Base Archivada"))
        self.otorgar(self.b1, "olga", "omar")
        self.otorgar(self.b2, "omar")
        self.otorgar(self.b3, "olga")
        self.t1, self.t2, self.t0, self.ta, self.t3 = (self.crear_terreno(n) for n in "12 a3")

        def asignar(conn):
            for terreno, base in ((self.t1, self.b1), (self.t2, self.b2), (self.ta, self.b1),
                                  (self.t3, self.b3)):
                conn.execute("UPDATE inventory_terrain SET base_id = ? WHERE id = ?", (base, terreno))
                conn.execute("UPDATE inventory_revision SET base_id = ? WHERE inventory_id = ?",
                             (base, terreno))
            conn.execute("UPDATE inventory_terrain SET archived_at = ? WHERE id = ?",
                         (db.now(), self.ta))
        sql(asignar)  # fixture: assignment and terrain archiving have no route in this packet
        self.archivar(self.b3)

    def bajar(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.hilo.join(timeout=5)

    def call(self, method, path, body=None, user="ada", headers=None, cookie=None):
        cabeceras = {"Content-Type": "application/json", **(headers or {})}
        if cookie or user:
            cabeceras["Cookie"] = cookie or self.cookies[user]
        peticion = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None, headers=cabeceras)
        try:
            with urllib.request.urlopen(peticion, timeout=20) as respuesta:
                return respuesta.status, json.loads(respuesta.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def entrar(self, login):
        peticion = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}/api/login", method="POST",
            data=json.dumps({"username": login, "password": TEST_PASSWORD}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(peticion, timeout=20) as respuesta:
            return respuesta.headers["Set-Cookie"].split(";")[0]

    def sesion(self, login):
        """The real validated session behind a user's cookie."""
        token = self.cookies[login].split("=", 1)[1]
        sesion = sql(lambda c: auth.sesion_de_token(c, token))
        self.assertIsNotNone(sesion)
        return sesion

    def ok(self, respuesta):
        self.assertEqual(respuesta[0], 200, respuesta[1])
        return respuesta[1]

    def base(self, base_id):
        return self.ok(self.call("GET", f"/api/maestra/bases/{base_id}/acceso"))["base"]

    def crear_base(self, nombre):
        return self.ok(self.call("POST", "/api/maestra/bases", {"nombre": nombre}))["base"]["id"]

    def otorgar(self, base_id, *logins, user="ada"):
        return self.call("PUT", f"/api/maestra/bases/{base_id}/acceso",
                         {"expected_version": self.base(base_id)["version"],
                          "usuarios": [self.ids[n] for n in logins]}, user)

    def archivar(self, base_id, accion="archivar"):
        return self.call("POST", f"/api/maestra/bases/{base_id}/{accion}",
                         {"expected_version": self.base(base_id)["version"]})

    def crear_terreno(self, nombre):
        return self.ok(self.call("POST", "/api/inventario/terrenos", {"terreno": f"Lote {nombre}"},
                                 headers={"Idempotency-Key": f"clave-{nuevo()}"}))["terreno"]["id"]

    def version(self, terreno):
        return sql(lambda c: c.execute("SELECT version FROM inventory_terrain WHERE id = ?",
                                       (terreno,)).fetchone()["version"])

    def patch(self, terreno, cambios, user, **extra):
        return self.call("PATCH", f"/api/inventario/terrenos/{terreno}",
                         {"expected_version": self.version(terreno), "changes": cambios, **extra}, user)

    def cuenta(self, tabla, donde="1 = 1", params=()):
        return len(filas(tabla, donde, params))


class Matriz(Escenario):
    """The checks. Mixed into one TestCase per backend."""

    # -- 1. routes and capabilities ---------------------------------------------

    def ruta(self, route):
        path = route.path.replace(":bid", nuevo())
        return path.replace(":id", nuevo() if "/inventario/" in path or "/publico/" in path else "999")

    def test_every_registered_route_is_public_or_names_a_real_capability(self):
        todas = set(auth.CAPACIDADES["admin"])
        self.assertEqual(set(auth.CAPACIDADES["operador"]), todas - ADMIN_ONLY)
        sin_capacidad = set()
        for route in app_module.router.routes:
            if route.capacidad is None:
                sin_capacidad.add((route.method, route.path))
            else:
                self.assertIn(route.capacidad, todas, route.path)
                self.assertFalse(auth.is_public(route.method, self.ruta(route)), route.path)
        # Exactly the anonymous allowlist is registered without a capability.
        self.assertEqual(sin_capacidad, {
            ("GET", "/api/config"), ("GET", "/api/session"), ("POST", "/api/login"),
            ("POST", "/api/logout"), ("GET", "/api/publico/terrenos"),
            ("GET", "/api/publico/terrenos/:id")})
        for method, path in sin_capacidad:
            self.assertTrue(auth.is_public(method, path.replace(":id", nuevo())), path)

    def test_the_dispatcher_enforces_each_routes_capability(self):
        vistas = 0
        for route in app_module.router.routes:
            if route.capacidad is None:
                continue
            vistas += 1
            path, cuerpo = self.ruta(route), None if route.method == "GET" else {}
            with self.subTest(method=route.method, path=route.path):
                self.assertEqual(self.call(route.method, path, cuerpo, user=None)[0], 401)
                status, body = self.call(route.method, path, cuerpo, "otto")
                if route.capacidad in ADMIN_ONLY:
                    self.assertEqual((status, body["detalle"]),
                                     (403, {"code": "forbidden", "capacidad": route.capacidad}))
                elif route.path == "/api/maestra/bases":
                    self.assertEqual((status, body["bases"]), (200, []))
                else:  # a record route: an operator with no grant is out of every scope
                    self.assertEqual((status, body["detalle"]["code"]), (404, "not_found"))
                self.assertNotIn(self.call(route.method, path, cuerpo, "ada")[0], (401, 403))
        self.assertGreaterEqual(vistas, 42)

    def test_a_private_route_without_a_capability_is_closed_to_everyone(self):
        llamadas = []
        app_module.router.add("GET", "/api/sin-declarar", lambda r: llamadas.append(1) or {})
        self.addCleanup(app_module.router._routes.pop)
        self.assertEqual(self.call("GET", "/api/sin-declarar", user=None)[0], 401)
        for usuario in ("ada", "olga"):
            status, body = self.call("GET", "/api/sin-declarar", user=usuario)
            self.assertEqual((status, body["detalle"]), (403, {"code": "forbidden", "capacidad": None}))
        self.assertEqual(llamadas, [])

    def test_unknown_api_paths_stay_private_and_the_public_surface_is_unchanged(self):
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            cuerpo = None if method == "GET" else {}
            self.assertEqual(self.call(method, "/api/no-existe", cuerpo, user=None)[0], 401)
            self.assertIn(self.call(method, "/api/no-existe", cuerpo, "olga")[0], (404, 405))
        self.assertEqual(self.call("GET", "/api/session", user=None), (200, {"authenticated": False}))
        self.assertEqual(self.call("GET", "/api/publico/terrenos", user=None)[1]["total"], 0)
        self.assertEqual(self.call("GET", f"/api/publico/terrenos/{self.t1}", user=None)[0], 404)
        self.assertEqual(self.call("GET", "/api/session", cookie="ara_sesion=" + "x" * 43)[1],
                         {"authenticated": False})
        self.assertEqual(self.call("GET", "/api/maestra/bases", cookie="ara_sesion=" + "x" * 43)[0], 401)

    # -- 2. work bases and grants -----------------------------------------------

    def test_an_administrator_creates_renames_archives_and_restores_a_base(self):
        status, body = self.call("POST", "/api/maestra/bases", {"nombre": "  Base   Nueva "})
        base = body["base"]
        self.assertEqual((status, base["nombre"], base["version"], base["archivada"], base["terrenos"],
                          body["usuarios"]), (200, "Base Nueva", 1, False, 0, []))
        bid = base["id"]
        ruta = f"/api/maestra/bases/{bid}"

        status, body = self.call("PATCH", ruta, {"expected_version": 1, "nombre": "Base Renombrada"}, "alan")
        self.assertEqual((status, body["base"]["nombre"], body["base"]["version"]), (200, "Base Renombrada", 2))
        # A stale version changes nothing and reports the current base.
        status, body = self.call("PATCH", ruta, {"expected_version": 1, "nombre": "Tarde"})
        self.assertEqual((status, body["detalle"]["code"], body["detalle"]["base"]["nombre"]),
                         (409, "conflict", "Base Renombrada"))
        # The same name is not a change.
        self.assertEqual(self.call("PATCH", ruta, {"expected_version": 2, "nombre": "Base Renombrada"})[1]
                         ["base"]["version"], 2)

        status, body = self.call("POST", ruta + "/archivar", {"expected_version": 2})
        self.assertEqual((status, body["base"]["archivada"], body["base"]["version"]), (200, True, 3))
        for accion, cuerpo in (("archivar", {"expected_version": 3}),):
            status, body = self.call("POST", f"{ruta}/{accion}", cuerpo)
            self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))
        status, body = self.call("PATCH", ruta, {"expected_version": 3, "nombre": "No"})
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))
        self.assertEqual(self.call("POST", ruta + "/restaurar", {"expected_version": 2})[0], 409)
        status, body = self.call("POST", ruta + "/restaurar", {"expected_version": 3})
        self.assertEqual((status, body["base"]["archivada"], body["base"]["version"]), (200, False, 4))
        status, body = self.call("POST", ruta + "/restaurar", {"expected_version": 4})
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_no_archivada"))

        eventos = filas("maestra_base_event", "base_id = ?", (bid,))
        self.assertEqual(sorted((e["version"], e["action"], e["actor_id"]) for e in eventos), [
            (1, "crear", self.ids["ada"]), (2, "renombrar", self.ids["alan"]),
            (3, "archivar", self.ids["ada"]), (4, "restaurar", self.ids["ada"])])

    def test_base_requests_are_validated_before_anything_changes(self):
        antes = {t: filas(t) for t in AUDITADAS}
        for cuerpo in ({}, {"nombre": "   "}, {"nombre": 7}, {"nombre": "x" * 101},
                       {"nombre": "Bien", "terrenos": 5}):
            status, body = self.call("POST", "/api/maestra/bases", cuerpo)
            self.assertEqual((status, body["detalle"]["code"]), (422, "validation_failed"), cuerpo)
        ruta = f"/api/maestra/bases/{self.b1}"
        for method, path, cuerpo in (
                ("PATCH", ruta, {"nombre": "Sin versión"}),
                ("PATCH", ruta, {"expected_version": "1", "nombre": "Texto"}),
                ("PATCH", ruta, {"expected_version": True, "nombre": "Booleano"}),
                ("POST", ruta + "/archivar", {}),
                ("POST", ruta + "/archivar", {"expected_version": 0}),
                ("PUT", ruta + "/acceso", {"expected_version": 2}),
                ("PUT", ruta + "/acceso", {"expected_version": 2, "usuarios": "todos"}),
                ("PUT", ruta + "/acceso", {"expected_version": 2, "usuarios": ["*"]}),
                ("PUT", ruta + "/acceso", {"expected_version": 2, "usuarios": [7]}),
                ("PUT", ruta + "/acceso", {"expected_version": 2, "usuarios": [], "todos": True})):
            status, body = self.call(method, path, cuerpo)
            self.assertEqual((status, body["detalle"]["code"]), (422, "validation_failed"), cuerpo)
        for method, path in (("PATCH", ""), ("POST", "/archivar"), ("POST", "/restaurar"),
                             ("GET", "/acceso"), ("PUT", "/acceso")):
            cuerpo = None if method == "GET" else {"expected_version": 1, "nombre": "X"}
            if method == "POST":
                cuerpo = {"expected_version": 1}
            if method == "PUT":
                cuerpo = {"expected_version": 1, "usuarios": []}
            status, body = self.call(method, f"/api/maestra/bases/{nuevo()}{path}", cuerpo)
            self.assertEqual((status, body["detalle"]), (404, {"code": "not_found"}))
        self.assertEqual({t: filas(t) for t in AUDITADAS}, antes)

    def test_grants_are_replaced_as_a_whole_with_exact_audit(self):
        bid = self.crear_base("Base de Accesos")
        ruta = f"/api/maestra/bases/{bid}/acceso"
        ids = self.ids
        status, body = self.call("PUT", ruta, {"expected_version": 1, "usuarios": [
            ids["olga"], ids["omar"], ids["olga"].upper()]})  # a repeated id is one grant
        self.assertEqual((status, body["base"]["version"], sorted(u["login"] for u in body["usuarios"])),
                         (200, 2, ["olga", "omar"]))
        self.assertEqual(set(body["usuarios"][0]), {"id", "login", "display_name", "active", "granted_at"})
        # The same set again is not a change: no version, no event.
        self.assertEqual(self.call("PUT", ruta, {"expected_version": 2, "usuarios": [ids["omar"], ids["olga"]]})
                         [1]["base"]["version"], 2)
        # Replace: omar out, otto in.
        status, body = self.call("PUT", ruta, {"expected_version": 2, "usuarios": [ids["olga"], ids["otto"]]}, "alan")
        self.assertEqual((status, body["base"]["version"], sorted(u["login"] for u in body["usuarios"])),
                         (200, 3, ["olga", "otto"]))
        # Stale: nothing changes.
        status, body = self.call("PUT", ruta, {"expected_version": 2, "usuarios": []})
        self.assertEqual((status, body["detalle"]["code"], body["detalle"]["base"]["version"]), (409, "conflict", 3))
        self.assertEqual(self.cuenta("maestra_base_acceso", "base_id = ?", (bid,)), 2)

        historia = [(e["action"], e["user_id"], e["actor_id"], e["actor_name"])
                    for e in filas("team_user_event", "base_id = ?", (bid,))]
        self.assertEqual(sorted(historia), sorted([
            ("acceso_otorgado", ids["olga"], ids["ada"], "Ada Ficticia"),
            ("acceso_otorgado", ids["omar"], ids["ada"], "Ada Ficticia"),
            ("acceso_revocado", ids["omar"], ids["alan"], "Alan Ficticia"),
            ("acceso_otorgado", ids["otto"], ids["alan"], "Alan Ficticia")]))
        eventos = {e["version"]: (e["action"], json.loads(e["details_json"] or "{}"))
                   for e in filas("maestra_base_event", "base_id = ?", (bid,))}
        self.assertEqual(eventos[2], ("acceso", {"otorgados": sorted([ids["olga"], ids["omar"]]), "revocados": []}))
        self.assertEqual(eventos[3], ("acceso", {"otorgados": [ids["otto"]], "revocados": [ids["omar"]]}))
        self.assertEqual(sorted(eventos), [1, 2, 3])

    def test_a_grant_list_with_one_bad_entry_changes_nothing(self):
        bid = self.crear_base("Base Estricta")
        ruta = f"/api/maestra/bases/{bid}/acceso"
        ids = self.ids
        self.ok(self.call("PUT", ruta, {"expected_version": 1, "usuarios": [ids["olga"]]}))
        cuenta(lambda c: auth.set_active(c, "otto", False))
        antes = {t: filas(t) for t in AUDITADAS}
        fantasma = nuevo()
        status, body = self.call("PUT", ruta, {"expected_version": 2, "usuarios": [
            ids["omar"], fantasma, ids["ada"], ids["otto"]]})
        self.assertEqual((status, body["detalle"]["code"]), (422, "validation_failed"))
        self.assertEqual(body["detalle"]["usuarios"], {
            fantasma: "no_existe", ids["ada"]: "no_es_operador", ids["otto"]: "inactivo"})
        self.assertEqual({t: filas(t) for t in AUDITADAS}, antes)

        # An inactive account that already holds a grant may keep it or lose it.
        cuenta(lambda c: auth.set_active(c, "olga", False))
        status, body = self.call("PUT", ruta, {"expected_version": 2, "usuarios": [ids["olga"], ids["omar"]]})
        self.assertEqual((status, sorted(u["login"] for u in body["usuarios"])), (200, ["olga", "omar"]))
        self.assertFalse(next(u for u in body["usuarios"] if u["login"] == "olga")["active"])
        status, body = self.call("PUT", ruta, {"expected_version": 3, "usuarios": []})
        self.assertEqual((status, body["usuarios"], body["base"]["version"]), (200, [], 4))

    def test_archiving_a_base_changes_only_the_base(self):
        sql(lambda c: c.execute(
            "INSERT INTO inventory_column (id, base_id, nombre, tipo, orden, created_at, created_by,"
            " updated_at, updated_by) VALUES (?, ?, 'Folio', 'texto', 1, ?, ?, ?, ?)",
            (nuevo(), self.b1, db.now(), self.ids["ada"], db.now(), self.ids["ada"])))
        antes = {t: filas(t) for t in CONTENIDO}
        publico = self.call("GET", "/api/publico/terrenos", user=None)
        self.ok(self.archivar(self.b1))
        self.assertEqual({t: filas(t) for t in CONTENIDO}, antes)
        self.assertEqual(self.call("GET", "/api/publico/terrenos", user=None), publico)

        # Closed to its operators, read-only for administrators, grants still manageable.
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t1}", user="olga")[0], 404)
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t1}")[0], 200)
        status, body = self.patch(self.t1, {"terreno": "No"}, "ada")
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))
        self.assertEqual(self.otorgar(self.b1, "olga")[0], 200)
        self.assertEqual([b["id"] for b in self.call("GET", "/api/maestra/bases", user="omar")[1]["bases"]],
                         [self.b2])
        self.ok(self.archivar(self.b1, "restaurar"))
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t1}", user="olga")[0], 200)
        self.assertEqual({t: filas(t) for t in CONTENIDO if t != "maestra_base_acceso"},
                         {t: v for t, v in antes.items() if t != "maestra_base_acceso"})

    # -- 3. scope ----------------------------------------------------------------

    def test_each_caller_lists_only_the_bases_it_may_open(self):
        def nombres(user, query=""):
            body = self.ok(self.call("GET", "/api/maestra/bases" + query, user=user))
            self.assertEqual(body["total"], len(body["bases"]))
            return [b["nombre"] for b in body["bases"]]
        self.assertEqual(nombres("ada"), ["Base Dos", "Base Uno"])
        self.assertEqual(nombres("ada", "?archivadas=1"), ["Base Archivada", "Base Dos", "Base Uno"])
        self.assertEqual(nombres("olga"), ["Base Uno"])  # her archived base is closed to her
        self.assertEqual(nombres("olga", "?archivadas=1"), ["Base Uno"])
        self.assertEqual(nombres("omar"), ["Base Dos", "Base Uno"])
        self.assertEqual(nombres("otto"), [])
        uno = next(b for b in self.call("GET", "/api/maestra/bases", user="olga")[1]["bases"])
        self.assertEqual(uno["terrenos"], 1)  # t1; the archived ta is not counted

    def test_an_operator_reaches_only_records_of_her_active_bases(self):
        for sufijo in ("", "/historial"):
            self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t1}{sufijo}", user="olga")[0], 200)
            # Archived terrain, in scope: readable.
            self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.ta}{sufijo}", user="olga")[0], 200)
            respuestas = {nombre: self.call("GET", f"/api/inventario/terrenos/{tid}{sufijo}", user="olga")
                          for nombre, tid in (("otra base", self.t2), ("sin asignar", self.t0),
                                              ("base archivada", self.t3), ("inexistente", nuevo()))}
            # Out of scope and missing are the same answer, to the byte.
            self.assertEqual(set(map(encode, respuestas.values())), {encode(
                (404, {"error": "El terreno no existe.", "detalle": {"code": "not_found"}}))})
        for tid in (self.t1, self.t2, self.t0, self.ta, self.t3):
            self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{tid}")[0], 200)  # administrator
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t2}", user="omar")[0], 200)

    def test_an_operator_edits_only_inside_scope_and_archived_content_is_read_only(self):
        status, body = self.patch(self.t1, {"estado": "Jalisco"}, "olga")
        self.assertEqual((status, body["terreno"]["draft"]["estado"],
                          body["terreno"]["updated_by"]["display_name"]), (200, "Jalisco", "Olga Ficticia"))
        fuera = {n: self.patch(t, {"estado": "X"}, "olga")
                 for n, t in (("otra", self.t2), ("libre", self.t0), ("archivada", self.t3))}
        fuera["inexistente"] = self.call("PATCH", f"/api/inventario/terrenos/{nuevo()}",
                                         {"expected_version": 1, "changes": {"estado": "X"}}, "olga")
        # Even a request that would fail validation learns nothing but 404.
        fuera["inválida"] = self.call("PATCH", f"/api/inventario/terrenos/{self.t2}",
                                      {"expected_version": "mal", "changes": {"rol": "admin"}}, "olga")
        self.assertEqual({r[0] for r in fuera.values()}, {404})
        self.assertEqual(len({encode(r[1]) for r in fuera.values()}), 1)
        status, body = self.patch(self.ta, {"estado": "X"}, "olga")
        self.assertEqual((status, body["detalle"]["code"]), (409, "terreno_archivado"))
        status, body = self.patch(self.t3, {"estado": "X"}, "ada")
        self.assertEqual((status, body["detalle"]["code"]), (409, "base_archivada"))
        self.assertEqual(self.patch(self.t0, {"estado": "Colima"}, "alan")[0], 200)
        self.assertEqual([self.version(t) for t in (self.t1, self.t2, self.t0, self.ta, self.t3)],
                         [2, 1, 2, 1, 1])

    def test_the_master_table_and_the_legacy_workspace_are_administrators_only(self):
        for method, path, cuerpo in (
                ("GET", "/api/inventario/terrenos", None),
                ("GET", f"/api/inventario/terrenos?base={self.b1}&base_id={self.b1}", None),
                ("POST", "/api/inventario/terrenos", {"terreno": "X", "base_id": self.b1}),
                ("GET", "/api/bases", None), ("GET", "/api/mapas", None), ("GET", "/api/carpetas", None),
                ("GET", "/api/formatos", None), ("POST", "/api/exportar", {}),
                ("POST", "/api/importar/vista-previa", {}), ("POST", "/api/carpetas", {"nombre": "X"}),
                ("POST", "/api/maestra/bases", {"nombre": "Mía"}),
                ("GET", f"/api/maestra/bases/{self.b1}/acceso", None),
                ("PUT", f"/api/maestra/bases/{self.b1}/acceso", {"expected_version": 2, "usuarios": []}),
                ("POST", f"/api/maestra/bases/{self.b3}/restaurar", {"expected_version": 3})):
            with self.subTest(method=method, path=path):
                status, body = self.call(method, path, cuerpo, "olga",
                                         {"Idempotency-Key": "clave-operadora-1"})
                self.assertEqual((status, body["detalle"]["code"]), (403, "forbidden"))
        self.assertEqual(self.cuenta("inventory_terrain"), 5)
        self.assertEqual(self.call("GET", "/api/inventario/terrenos")[1]["total"], 4)  # ta is archived

    def test_nothing_the_client_sends_can_grant_role_actor_or_base(self):
        falsos = {"X-Rol": "admin", "X-User": self.ids["ada"], "X-Actor-Id": self.ids["ada"],
                  "X-Base-Id": self.b2, "Authorization": "Bearer admin"}
        self.assertEqual(self.call("GET", "/api/bases", user="olga", headers=falsos)[0], 403)
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t2}", user="olga", headers=falsos)[0], 404)
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t2}?base_id={self.b1}&rol=admin",
                                   user="olga")[0], 404)
        status, body = self.call("PATCH", f"/api/inventario/terrenos/{self.t1}", {
            "expected_version": 1, "changes": {"estado": "Jalisco"}, "rol": "admin",
            "actor_id": self.ids["ada"], "base_id": self.b2, "user": {"id": self.ids["ada"]}}, "olga", falsos)
        self.assertEqual((status, set(body["detalle"]["fields"])), (422, {"rol", "actor_id", "base_id", "user"}))
        for campo in ("base_id", "rol", "custom_json", "custom"):
            status, body = self.patch(self.t1, {campo: "x"}, "olga")
            self.assertEqual((status, list(body["detalle"]["fields"])), (422, [campo]))
        status, body = self.patch(self.t1, {"estado": "Jalisco"}, "olga")
        self.assertEqual((status, body["terreno"]["updated_by"]["id"]), (200, self.ids["olga"]))
        self.assertEqual(self.call("GET", "/api/session", user="olga", headers=falsos)[1]["user"]["rol"], "operador")

    def test_an_edit_keeps_the_fields_it_does_not_touch(self):
        # custom:folio names no column of Base Uno: a value this base does not define.
        sql(lambda c: c.execute(
            "UPDATE inventory_revision SET tipo_terreno = 'Industrial', custom_json = ?"
            " WHERE inventory_id = ?", ('{"custom:folio": "SENTINELA-77"}', self.t1)))
        status, body = self.patch(self.t1, {"municipio": "Zapopan"}, "olga")
        self.assertEqual(status, 200)
        revisiones = filas("inventory_revision", "inventory_id = ?", (self.t1,))
        self.assertEqual(sorted((r["revision_number"], r["base_id"], r["tipo_terreno"], r["custom_json"])
                                for r in revisiones), [
            (1, self.b1, "Industrial", '{"custom:folio": "SENTINELA-77"}'),
            (2, self.b1, "Industrial", '{"custom:folio": "SENTINELA-77"}')])
        # The record reports its type and base; a stored value no current column
        # defines is kept and shown to nobody, administrators included.
        self.assertEqual((body["terreno"]["draft"]["tipo_terreno"], body["terreno"]["base_id"],
                          body["terreno"]["custom"]), ("Industrial", self.b1, {}))
        textos = [json.dumps(body), *(json.dumps(self.call("GET", ruta, user=u)[1]) for u in ("olga", "ada")
                  for ruta in (f"/api/inventario/terrenos/{self.t1}",
                               f"/api/inventario/terrenos/{self.t1}/historial"))]
        textos.append(json.dumps(self.call("GET", "/api/inventario/terrenos")[1]))
        for texto in textos:
            self.assertNotIn("SENTINELA-77", texto)
            self.assertNotIn("custom_json", texto)
        # A terrain with no base keeps none.
        self.patch(self.t0, {"municipio": "Colima"}, "ada")
        self.assertEqual({r["base_id"] for r in filas("inventory_revision", "inventory_id = ?", (self.t0,))}, {None})

    # -- 4. sessions -------------------------------------------------------------

    def test_the_session_reports_role_capabilities_and_scope_and_no_secret(self):
        olga = self.call("GET", "/api/session", user="olga")[1]
        self.assertEqual(olga, {
            "authenticated": True,
            "user": {"id": self.ids["olga"], "display_name": "Olga Ficticia", "rol": "operador"},
            "capacidades": list(auth.CAPACIDADES["operador"]),
            "alcance": {"bases": [{"id": self.b1, "nombre": "Base Uno"}]}})
        self.assertEqual(self.call("GET", "/api/session", user="otto")[1]["alcance"], {"bases": []})
        ada = self.call("GET", "/api/session", user="ada")[1]
        self.assertEqual((ada["user"]["rol"], ada["capacidades"], ada["alcance"]),
                         ("admin", list(auth.CAPACIDADES["admin"]), {"bases": "todas"}))

        sesion = self.sesion("olga")
        token = self.cookies["olga"].split("=", 1)[1]
        secreto = filas("team_user", "id = ?", (self.ids["olga"],))[0]["password_hash"]
        for texto in (json.dumps(olga), encode(sesion).decode(), repr(sesion),
                      encode({"alcance": auth.require_terreno(type("R", (), {"sesion": sesion})(), self.t1,
                                                              "maestra.ver")}).decode()):
            for prohibido in (token, sesion.referencia, secreto, "credential_revision", "password"):
                self.assertNotIn(prohibido, texto)

    def test_a_revoked_grant_takes_effect_on_the_next_request(self):
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t1}", user="olga")[0], 200)
        self.ok(self.otorgar(self.b1, "omar"))  # olga is no longer in the set
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t1}", user="olga")[0], 404)
        self.assertEqual(self.patch(self.t1, {"estado": "X"}, "olga")[0], 404)
        self.assertEqual(self.call("GET", "/api/session", user="olga")[1]["alcance"], {"bases": []})
        self.assertEqual(self.call("GET", "/api/maestra/bases", user="olga")[1]["bases"], [])
        self.ok(self.otorgar(self.b1, "omar", "olga"))
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{self.t1}", user="olga")[0], 200)

    def test_role_change_reset_deactivation_and_logout_end_open_sessions(self):
        cambios = {"olga": lambda c: auth.set_role(c, "olga", "admin"),
                   "omar": lambda c: auth.set_password(c, "omar", TEST_PASSWORD + "-nueva", iterations=1000),
                   "otto": lambda c: auth.set_active(c, "otto", False)}
        for login, cambio in cambios.items():
            self.assertEqual(self.call("GET", "/api/maestra/bases", user=login)[0], 200)
            cuenta(cambio)
            self.assertEqual(self.call("GET", "/api/maestra/bases", user=login)[0], 401)
            self.assertEqual(self.call("GET", "/api/session", user=login)[1], {"authenticated": False})
        # A role change takes a new sign-in, which then carries the new role.
        self.assertEqual(self.call("GET", "/api/bases", cookie=self.entrar("olga"))[0], 200)
        self.assertFalse(cuenta(lambda c: auth.set_role(c, "olga", "admin")))  # no change: sessions survive
        self.ok(self.call("POST", "/api/logout", user="alan"))
        self.assertEqual(self.call("GET", "/api/maestra/bases", user="alan")[0], 401)

    # -- 5. the write boundary (P2) ----------------------------------------------

    def adjuntar(self, sesion, terreno, dentro=None, seguir=None):
        """Team B's documented pattern, around a tiny fictional attachment write."""
        with db.escritura() as conn:
            alcance = auth.reverificar_terreno(conn, sesion, terreno, "archivos.subir")
            if dentro is not None:  # test barrier: authorized, locks held, nothing written yet
                dentro.set()
                self.assertTrue(seguir.wait(15))
            archivo, ahora, actor = nuevo(), db.now(), alcance.actor
            conn.execute(
                "INSERT INTO archivo (id, inventory_id, columna_id, tipo, creado_en, creado_por,"
                " actualizado_en, actualizado_por) VALUES (?, ?, 'core:archivos', 'pdf', ?, ?, ?, ?)",
                (archivo, alcance.terreno_id, ahora, actor["id"], ahora, actor["id"]))
            conn.execute(
                "INSERT INTO archivo_evento (id, archivo_id, inventory_id, accion, base_id, actor_id,"
                " actor_name, at) VALUES (?, ?, ?, 'subida_iniciada', ?, ?, ?, ?)",
                (nuevo(), archivo, alcance.terreno_id, alcance.base_id, actor["id"],
                 actor["display_name"], ahora))
            return archivo

    def escrito(self):
        return self.cuenta("archivo"), self.cuenta("archivo_evento")

    def cambios_de_alcance(self):
        """name -> (change made by someone else, status the pending write then gets)."""
        expirar = "UPDATE team_session SET expires_at = 1 WHERE user_id = ?"
        return {
            "grant revoked": (lambda: self.ok(self.otorgar(self.b1, "omar")), 404),
            "base archived": (lambda: self.ok(self.archivar(self.b1)), 404),
            "role changed": (lambda: cuenta(lambda c: auth.set_role(c, "olga", "admin")), 401),
            "account deactivated": (lambda: cuenta(lambda c: auth.set_active(c, "olga", False)), 401),
            "signed out": (lambda: self.ok(self.call("POST", "/api/logout", user="olga")), 401),
            "password reset": (lambda: cuenta(lambda c: auth.set_password(
                c, "olga", TEST_PASSWORD + "-nueva", iterations=1000)), 401),
            "terrain transferred": (lambda: sql(lambda c: c.execute(
                "UPDATE inventory_terrain SET base_id = ? WHERE id = ?", (self.b2, self.t1))), 404),
            "terrain archived": (lambda: sql(lambda c: c.execute(
                "UPDATE inventory_terrain SET archived_at = ? WHERE id = ?", (db.now(), self.t1))), 409),
            "session expired": (lambda: sql(lambda c: c.execute(expirar, (self.ids["olga"],))), 401),
        }

    def test_the_documented_pattern_writes_with_the_trusted_actor_and_current_base(self):
        sesion = self.sesion("olga")
        peticion = type("Peticion", (), {"sesion": sesion})()
        alcance = auth.require_terreno(peticion, self.t1, "archivos.subir")  # request start
        self.assertEqual((alcance.rol, alcance.terreno_id, alcance.base_id, alcance.actor, alcance.sesion,
                          alcance.terreno_archivado, alcance.base_archivada),
                         ("operador", self.t1, self.b1, {"id": self.ids["olga"], "display_name": "Olga Ficticia"},
                          sesion, False, False))
        archivo = self.adjuntar(sesion, self.t1)
        self.assertEqual(filas("archivo", "id = ?", (archivo,))[0]["creado_por"], self.ids["olga"])
        evento = filas("archivo_evento", "archivo_id = ?", (archivo,))[0]
        self.assertEqual((evento["base_id"], evento["actor_id"]), (self.b1, self.ids["olga"]))
        self.assertEqual(self.version(self.t1), 1)  # an attachment write is not a terrain edit

        # A request object with no validated session, or a made-up one, is not authentication.
        for falsa in (type("Falsa", (), {})(), type("Falsa", (), {"sesion": None})(),
                      type("Falsa", (), {"sesion": {"user_id": self.ids["ada"], "rol": "admin"},
                                         "user": {"id": self.ids["ada"]}})()):
            with self.assertRaises(ApiError) as error:
                auth.require_terreno(falsa, self.t1, "archivos.subir")
            self.assertEqual(error.exception.status, 401)
        inventada = auth.Sesion("0" * 64, self.ids["ada"], "Ada Ficticia", "admin", 1)
        with self.assertRaises(ApiError) as error:
            self.adjuntar(inventada, self.t1)
        self.assertEqual(error.exception.status, 401)
        robada = auth.Sesion(sesion.referencia, self.ids["ada"], "Ada Ficticia", "admin", 1)
        with self.assertRaises(ApiError) as error:  # olga's session cannot be relabelled as ada's
            self.adjuntar(robada, self.t2)
        self.assertEqual(error.exception.status, 401)
        self.assertEqual(self.escrito(), (1, 1))

    def test_scope_lost_before_the_final_check_denies_the_write(self):
        for nombre, (_, esperado) in self.cambios_de_alcance().items():
            with self.subTest(nombre):
                self.reiniciar()
                cambio = self.cambios_de_alcance()[nombre][0]  # bound to this round's fixture
                sesion = self.sesion("olga")
                peticion = type("Peticion", (), {"sesion": sesion})()
                auth.require_terreno(peticion, self.t1, "archivos.subir")  # authorized at request start
                cambio()                                                  # ...then, during the long work
                with self.assertRaises(ApiError) as error:
                    self.adjuntar(sesion, self.t1)
                self.assertEqual(error.exception.status, esperado)
                self.assertEqual(self.escrito(), (0, 0))

    def test_a_scope_change_arriving_after_the_boundary_waits_for_the_write(self):
        for nombre, (_, esperado) in self.cambios_de_alcance().items():
            if nombre == "session expired":
                continue  # the clock is not a writer; nothing to wait for
            with self.subTest(nombre):
                self.reiniciar()
                self.carrera(self.cambios_de_alcance()[nombre][0], esperado)

    def carrera(self, cambio, esperado):
        sesion = self.sesion("olga")
        dentro, seguir, cambiado, resultado = (threading.Event(), threading.Event(),
                                               threading.Event(), {})

        def escribir():
            try:
                resultado["archivo"] = self.adjuntar(sesion, self.t1, dentro, seguir)
            except BaseException as exc:  # noqa: BLE001 - reported by the assertion below
                resultado["error"] = exc

        def cambiar():
            try:
                cambio()
            except BaseException as exc:  # noqa: BLE001
                resultado["error del cambio"] = exc
            cambiado.set()
        escritor = threading.Thread(target=escribir)
        escritor.start()
        self.assertTrue(dentro.wait(15))
        administrador = threading.Thread(target=cambiar)
        administrador.start()
        # The writer holds the boundary: the change cannot commit under it.
        self.assertFalse(cambiado.wait(0.4))
        seguir.set()
        escritor.join(20)
        administrador.join(20)
        self.assertEqual({k: v for k, v in resultado.items() if k != "archivo"}, {})
        self.assertTrue(cambiado.is_set())
        # Serial order "write, then scope change": the write stands, the next one is denied.
        self.assertEqual(self.escrito(), (1, 1))
        with self.assertRaises(ApiError) as error:
            self.adjuntar(sesion, self.t1)
        self.assertEqual(error.exception.status, esperado)
        self.assertEqual(self.escrito(), (1, 1))

    def test_a_write_that_fails_after_authorization_leaves_nothing(self):
        sesion = self.sesion("olga")
        with self.assertRaises(ZeroDivisionError), db.escritura() as conn:
            auth.reverificar_terreno(conn, sesion, self.t1, "archivos.subir")
            conn.execute(
                "INSERT INTO archivo (id, inventory_id, columna_id, tipo, creado_en, creado_por,"
                " actualizado_en, actualizado_por) VALUES (?, ?, 'core:archivos', 'pdf', ?, ?, ?, ?)",
                (nuevo(), self.t1, db.now(), self.ids["olga"], db.now(), self.ids["olga"]))
            raise ZeroDivisionError
        # A deferred foreign key only fails at COMMIT: still nothing, and the next write works.
        with self.assertRaises(self.integridad), db.escritura() as conn:
            auth.reverificar_terreno(conn, sesion, self.t1, "archivos.subir")
            conn.execute(
                "INSERT INTO archivo (id, inventory_id, columna_id, tipo, version_actual_id, creado_en,"
                " creado_por, actualizado_en, actualizado_por)"
                " VALUES (?, ?, 'core:archivos', 'pdf', 'no-existe', ?, ?, ?, ?)",
                (nuevo(), self.t1, db.now(), self.ids["olga"], db.now(), self.ids["olga"]))
        self.assertEqual(self.escrito(), (0, 0))
        self.adjuntar(sesion, self.t1)
        self.assertEqual(self.escrito(), (1, 1))

    def test_capabilities_and_archive_rules_at_the_boundary(self):
        olga, ada = self.sesion("olga"), self.sesion("ada")

        def estado(sesion, terreno, capacidad):
            try:
                with db.escritura() as conn:
                    auth.reverificar_terreno(conn, sesion, terreno, capacidad)
                return 200
            except ApiError as exc:
                return exc.status, exc.detalle["code"]
        casos = {
            (olga, self.t1, "archivos.subir"): 200, (olga, self.t1, "archivos.retirar"): 200,
            (olga, self.t1, "maestra.global"): (403, "forbidden"),   # capability before scope
            (olga, self.t2, "maestra.global"): (403, "forbidden"),
            (olga, self.t2, "archivos.subir"): (404, "not_found"),
            (olga, self.t0, "archivos.ver"): (404, "not_found"),
            (olga, self.t3, "archivos.ver"): (404, "not_found"),     # archived base: closed, not 409
            (olga, self.ta, "archivos.ver"): 200,                    # archived terrain: readable
            (olga, self.ta, "archivos.subir"): (409, "terreno_archivado"),
            (olga, self.ta, "archivos.retirar"): (409, "terreno_archivado"),
            (olga, self.ta, "maestra.editar"): (409, "terreno_archivado"),
            (olga, self.ta, "maestra.archivar"): 200,                # restoring has its own later policy
            (ada, self.t0, "archivos.subir"): 200, (ada, self.t3, "archivos.ver"): 200,
            (ada, self.t3, "archivos.subir"): (409, "base_archivada"),
            (ada, self.t3, "maestra.archivar"): (409, "base_archivada"),
            (ada, nuevo(), "archivos.subir"): (404, "not_found"),
        }
        for (sesion, terreno, capacidad), esperado in casos.items():
            with self.subTest(sesion=sesion, capacidad=capacidad, terreno=terreno):
                self.assertEqual(estado(sesion, terreno, capacidad), esperado)

        def base(sesion, base_id, capacidad):
            try:
                with db.escritura() as conn:
                    auth.reverificar_base(conn, sesion, base_id, capacidad)
                return 200
            except ApiError as exc:
                return exc.status, exc.detalle["code"]
        self.assertEqual([base(olga, self.b1, "maestra.editar"), base(olga, self.b2, "maestra.editar"),
                          base(olga, self.b3, "maestra.ver"), base(olga, nuevo(), "maestra.ver"),
                          base(olga, self.b1, "bases.gestionar"), base(ada, self.b3, "bases.gestionar"),
                          base(ada, self.b3, "maestra.ver"), base(ada, self.b3, "columnas.gestionar")],
                         [200, (404, "not_found"), (404, "not_found"), (404, "not_found"),
                          (403, "forbidden"), 200, 200, (409, "base_archivada")])

    def reiniciar(self):
        """A fresh fixture inside one test, for its subtests."""
        self.bajar()
        self.doCleanups()
        self.limpiar()
        self.levantar()


class RolesSqlite(Matriz, unittest.TestCase):
    integridad = sqlite3.IntegrityError

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._dir.name) / "prueba.db"
        entorno = patch.dict(os.environ, {"ARA_MAP_DB": str(self.db_path)})
        entorno.start()
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        self._entorno = entorno
        self.levantar()

    def tearDown(self):
        self._entorno.stop()
        self._dir.cleanup()

    def limpiar(self):
        for sufijo in ("", "-wal", "-shm"):
            Path(str(self.db_path) + sufijo).unlink(missing_ok=True)

    def test_the_check_refuses_to_run_outside_the_write_boundary(self):
        sesion = self.sesion("olga")
        with db.session() as conn, self.assertRaises(RuntimeError):
            auth.reverificar_terreno(conn, sesion, self.t1, "archivos.subir")
        with db.session() as conn, db.transaction(conn), self.assertRaises(RuntimeError):
            auth.reverificar_terreno(conn, sesion, self.t1, "archivos.subir")  # a SAVEPOINT is not enough
        with db.session() as conn:  # the request-start form needs no write boundary
            self.assertEqual(auth.require_terreno(type("R", (), {"sesion": sesion})(), self.t1,
                                                  "archivos.subir", conn).base_id, self.b1)

    def test_only_lock_failures_are_reported_as_busy(self):
        for mensaje in ("database is locked", "database table is locked"):
            with self.assertRaises(db.OcupadoError), db.session():
                raise sqlite3.OperationalError(mensaje)
        for error in (sqlite3.OperationalError("no such table: nada"), sqlite3.IntegrityError("UNIQUE"),
                      ValueError("otra cosa"), ApiError("no", 404)):
            with self.assertRaises(type(error)), db.session():
                raise error
            with self.assertRaises(type(error)), db.escritura():
                raise error
        status, body = self.call("GET", "/api/maestra/bases")  # an unrelated failure is still a 500
        with patch.object(app_module.api_maestra.repo, "listar", side_effect=sqlite3.OperationalError("otra")), \
                contextlib.redirect_stderr(io.StringIO()):
            status, body = self.call("GET", "/api/maestra/bases")
        self.assertEqual((status, body["detalle"]), (500, {"code": "internal"}))

    def test_a_write_that_cannot_get_its_turn_is_a_clean_503(self):
        ocupante = sqlite3.connect(self.db_path, isolation_level=None)
        ocupante.execute("BEGIN IMMEDIATE")
        real = sqlite3.connect
        try:
            with patch.object(db.sqlite3, "connect", lambda *a, **k: real(*a, **{**k, "timeout": 0.2})):
                status, body = self.patch_sin_leer(self.t1)
        finally:
            ocupante.execute("ROLLBACK")
            ocupante.close()
        self.assertEqual((status, body["detalle"]), (503, {"code": "ocupado"}))
        self.assertEqual((self.version(self.t1), self.cuenta("inventory_event", "inventory_id = ?", (self.t1,))),
                         (1, 1))
        self.assertEqual(self.patch(self.t1, {"estado": "Jalisco"}, "olga")[0], 200)  # retried as a whole

    def test_a_legacy_write_behind_another_writer_is_also_a_clean_503(self):
        # Review F1: the busy answer must not depend on the handler using db.escritura().
        ocupante = sqlite3.connect(self.db_path, isolation_level=None)
        ocupante.execute("BEGIN IMMEDIATE")
        real = sqlite3.connect
        try:
            with patch.object(db.sqlite3, "connect", lambda *a, **k: real(*a, **{**k, "timeout": 0.2})):
                status, body = self.call("POST", "/api/carpetas", {"tipo": "bases", "nombre": "Ocupada"})
                lectura = self.call("GET", "/api/maestra/bases", user="olga")[0]
        finally:
            ocupante.execute("ROLLBACK")
            ocupante.close()
        self.assertEqual((status, body["detalle"]), (503, {"code": "ocupado"}))
        self.assertEqual(lectura, 200)  # readers are not blocked by a writer
        self.assertEqual(self.cuenta("carpeta"), 0)
        self.assertEqual(self.call("POST", "/api/carpetas", {"tipo": "bases", "nombre": "Ocupada"})[0], 200)

    def patch_sin_leer(self, terreno):
        return self.call("PATCH", f"/api/inventario/terrenos/{terreno}",
                         {"expected_version": 1, "changes": {"estado": "Jalisco"}}, "olga")

    # -- the operations command --------------------------------------------------

    def cuentas(self, *args, entrada=TEST_PASSWORD):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cuentas_roles", Path(__file__).parents[1] / "scripts" / "cuentas.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida), \
                patch("sys.stdin", io.StringIO(entrada + "\n")), patch.dict(os.environ):
            try:
                codigo = modulo.main(list(args))
            except SystemExit as exc:
                codigo = exc.code
        return codigo, salida.getvalue()

    def test_the_accounts_command_sets_roles_with_audit_and_no_secrets(self):
        destino = ("--sqlite", str(self.db_path), "--password-stdin")
        # No explicit target, no action.
        self.assertNotEqual(self.cuentas("crear", "nueva", "Nueva Ficticia")[0], 0)
        self.assertNotEqual(self.cuentas("--sqlite", str(self.db_path.parent / "no-existe.db"),
                                         "rol", "olga", "admin")[0], 0)
        self.assertEqual(self.cuenta("team_user"), 5)

        codigo, salida = self.cuentas(*destino, "crear", "nora", "Nora Ficticia")
        self.assertEqual((codigo, "rol operador" in salida), (0, True))
        codigo, salida = self.cuentas(*destino, "crear", "aida", "Aida Ficticia", "--rol", "admin")
        self.assertEqual((codigo, "rol admin" in salida), (0, True))
        self.assertNotEqual(self.cuentas(*destino, "crear", "mala", "Mala Ficticia", "--rol", "jefa")[0], 0)
        self.assertNotEqual(self.cuentas(*destino, "rol", "nadie", "admin")[0], 0)

        # Bootstrap: promote an existing operator; her old session dies, a new sign-in is an admin.
        self.assertEqual(self.call("GET", "/api/bases", user="olga")[0], 403)
        codigo, salida = self.cuentas(*destino, "rol", "olga", "admin")
        self.assertEqual((codigo, "sesiones abiertas se cerraron" in salida), (0, True))
        self.assertEqual(self.call("GET", "/api/bases", user="olga")[0], 401)
        nueva = self.entrar("olga")
        self.assertEqual(self.call("GET", "/api/session", cookie=nueva)[1]["user"]["rol"], "admin")
        self.assertEqual(self.call("GET", "/api/bases", cookie=nueva)[0], 200)
        # Repeating it changes nothing and ends no session.
        codigo, salida = self.cuentas(*destino, "rol", "olga", "admin")
        self.assertEqual((codigo, "no se cambió nada" in salida), (0, True))
        self.assertEqual(self.call("GET", "/api/bases", cookie=nueva)[0], 200)
        # Recovery: demote, and reset a password.
        self.assertEqual(self.cuentas(*destino, "rol", "olga", "operador")[0], 0)
        self.assertEqual(self.call("GET", "/api/bases", cookie=nueva)[0], 401)
        self.assertEqual(self.cuentas(*destino, "restablecer", "omar")[0], 0)
        self.assertEqual(self.cuentas(*destino, "desactivar", "otto")[0], 0)

        codigo, listado = self.cuentas("--sqlite", str(self.db_path), "listar")
        roles = {linea.split("\t")[0]: linea.split("\t")[2:4] for linea in listado.splitlines()}
        self.assertEqual((roles["aida"], roles["nora"], roles["olga"], roles["otto"]),
                         (["admin", "activa"], ["operador", "activa"], ["operador", "activa"],
                          ["operador", "desactivada"]))

        historia = [(e["action"], e["actor_id"], e["actor_name"], json.loads(e["details_json"] or "null"))
                    for e in filas("team_user_event", "user_id = ?", (self.ids["olga"],))
                    if e["base_id"] is None]
        self.assertEqual(sorted(historia, key=repr), sorted([
            ("cuenta_creada", None, auth.ACTOR_CLI, {"rol": "operador"}),
            ("rol_cambiado", None, auth.ACTOR_CLI, {"antes": "operador", "despues": "admin"}),
            ("rol_cambiado", None, auth.ACTOR_CLI, {"antes": "admin", "despues": "operador"})], key=repr))
        acciones = sorted(e["action"] for e in filas("team_user_event", "base_id IS NULL"))
        self.assertEqual(acciones, sorted(["cuenta_creada"] * 7 + ["rol_cambiado"] * 2
                                          + ["contrasena_restablecida", "cuenta_desactivada"]))
        todo = salida + listado + json.dumps(filas("team_user_event"))
        self.assertNotIn(TEST_PASSWORD, todo)
        self.assertNotIn("pbkdf2", todo)


@unittest.skipUnless(URL, "No Postgres test connection configured")
class RolesPostgres(Matriz, unittest.TestCase):
    """Through db.session()/db.escritura(), where the workspace advisory lock
    serializes every transaction: the waiting observed in the shared race
    tests comes from that lock. RowLocksPostgres tests the row locks alone."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.integridad = psycopg.IntegrityError
        cls.schema = "test_ara_roles_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.conninfo = make_conninfo(URL, options=f"-c search_path={cls.schema}")
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": cls.conninfo})
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
        self.limpiar()
        self.levantar()

    def limpiar(self):
        with postgres.session() as conn:
            conn.raw.execute("TRUNCATE team_user, team_login_failure CASCADE")

    def cruda(self):
        """An independent connection to this fixture's schema, with no advisory lock taken."""
        import psycopg
        conexion = psycopg.connect(self.conninfo)
        self.addCleanup(conexion.close)
        return conexion

    def test_waiting_for_the_workspace_lock_ends_in_503_not_a_dropped_connection(self):
        # Review F1. The dispatcher's own sign-in lookup takes the workspace
        # advisory lock before any handler runs; a timeout there used to escape
        # as an unanswered connection. Same lock acquisition, shorter wait.
        antes = {t: filas(t) for t in AUDITADAS + ("team_session", "inventory_terrain")}
        ocupante = self.cruda()
        ocupante.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema()), %s)", (postgres.LOCK_ID,))
        try:
            with patch.object(postgres, "LOCK_TIMEOUT", "300ms"):
                casos = {
                    "administrator write": self.call("POST", "/api/maestra/bases", {"nombre": "Ocupada"}),
                    "operator write": self.patch_fijo("olga"),
                    "operator read": self.call("GET", f"/api/inventario/terrenos/{self.t1}", user="olga"),
                    "legacy read": self.call("GET", "/api/bases"),
                    "session with a cookie": self.call("GET", "/api/session", user="olga"),
                    "sign-in": self.call("POST", "/api/login", {"username": "olga", "password": TEST_PASSWORD},
                                         user=None),
                    "sign-out": self.call("POST", "/api/logout", user="omar"),
                }
                # What needs no database is answered as before.
                self.assertEqual(self.call("GET", "/api/session", user=None), (200, {"authenticated": False}))
                self.assertEqual(self.call("GET", "/api/maestra/bases", user=None)[0], 401)
                self.assertEqual(self.call("GET", "/api/publico/terrenos", user=None)[0], 200)
        finally:
            ocupante.rollback()
        for nombre, (status, body) in casos.items():
            with self.subTest(nombre):
                self.assertEqual((status, body["detalle"]), (503, {"code": "ocupado"}))
        # Nothing was written, no session ended, and the same requests now succeed in full.
        self.assertEqual({t: filas(t) for t in antes}, antes)
        self.assertEqual(self.call("POST", "/api/maestra/bases", {"nombre": "Ocupada"})[0], 200)
        self.assertEqual(self.patch_fijo("olga")[0], 200)
        self.assertEqual(self.call("GET", "/api/maestra/bases", user="omar")[0], 200)

    def test_a_row_lock_inside_the_write_boundary_ends_in_503(self):
        # The other place a write can wait: past the workspace lock, on a row.
        ocupante = self.cruda()
        ocupante.execute("SELECT id FROM inventory_terrain WHERE id = %s FOR UPDATE", (self.t1,))
        try:
            with patch.object(postgres, "LOCK_TIMEOUT", "300ms"):
                status, body = self.patch_fijo("olga")
                otro = self.patch(self.t2, {"estado": "Colima"}, "omar")[0]
        finally:
            ocupante.rollback()
        self.assertEqual((status, body["detalle"]), (503, {"code": "ocupado"}))
        self.assertEqual(otro, 200)  # only the locked terrain was busy
        self.assertEqual((self.version(self.t1), self.cuenta("inventory_event", "inventory_id = ?", (self.t1,))),
                         (1, 1))
        self.assertEqual(self.patch_fijo("olga")[0], 200)

    def patch_fijo(self, user):
        return self.call("PATCH", f"/api/inventario/terrenos/{self.t1}",
                         {"expected_version": 1, "changes": {"estado": "Jalisco"}}, user)

    def test_only_lock_failures_are_reported_as_busy(self):
        import psycopg
        for error in (psycopg.errors.LockNotAvailable(), psycopg.errors.DeadlockDetected(),
                      psycopg.errors.QueryCanceled()):
            with self.assertRaises(db.OcupadoError), db.session():
                raise error
        for error in (psycopg.errors.UniqueViolation(), psycopg.OperationalError("conexión rechazada"),
                      ValueError("otra cosa"), ApiError("no", 404)):
            with self.assertRaises(type(error)), db.session():
                raise error
            with self.assertRaises(type(error)), db.escritura():
                raise error

    def test_the_accounts_command_checks_the_schema_and_never_migrates(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cuentas_pg", Path(__file__).parents[1] / "scripts" / "cuentas.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        def correr(*args):
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida), \
                    patch.dict(os.environ, {"ARA_CUENTAS_PRUEBA": self.conninfo}):
                try:
                    return modulo.main(list(args)), salida.getvalue()
                except SystemExit as exc:
                    return exc.code, salida.getvalue()
        self.assertEqual(correr("--url-env", "ARA_CUENTAS_PRUEBA", "rol", "olga", "admin")[0], 0)
        self.assertEqual(self.call("GET", "/api/maestra/bases", user="olga")[0], 401)
        self.assertNotEqual(correr("--url-env", "ARA_NO_DEFINIDA", "rol", "omar", "admin")[0], 0)
        sql(lambda c: c.execute("UPDATE workspace_metadata SET value = '9' WHERE key = 'schema_version'"))
        try:
            codigo, _ = correr("--url-env", "ARA_CUENTAS_PRUEBA", "rol", "omar", "admin")
            self.assertIn("migra primero", str(codigo))
            self.assertEqual(sql(postgres.schema_version), 9)  # refused, and did not migrate
        finally:
            sql(lambda c: c.execute("UPDATE workspace_metadata SET value = ? WHERE key = 'schema_version'",
                                    (str(db.SCHEMA_VERSION),)))
        self.assertEqual(filas("team_user", "login = 'omar'")[0]["rol"], "operador")


@unittest.skipUnless(URL, "No Postgres test connection configured")
class RowLocksPostgres(Escenario, unittest.TestCase):
    """The row locks on their own: independent connections that never take
    the workspace advisory lock, so any waiting here is a row lock."""

    setUpClass = RolesPostgres.__dict__["setUpClass"]
    tearDownClass = RolesPostgres.__dict__["tearDownClass"]
    limpiar = RolesPostgres.limpiar

    def setUp(self):
        self.limpiar()
        self.levantar()

    def conectar(self, espera="400ms"):
        import psycopg
        cruda = psycopg.connect(self.conninfo, row_factory=postgres.row_factory)
        self.addCleanup(cruda.close)
        cruda.execute(f"SET lock_timeout = '{espera}'")
        cruda.commit()
        return postgres.Connection(cruda)

    def cambios(self):
        return {
            "grant revoked": ("DELETE FROM maestra_base_acceso WHERE base_id = %s AND user_id = %s",
                              (self.b1, self.ids["olga"]), 404),
            "base archived": ("UPDATE maestra_base SET archived_at = 'x' WHERE id = %s", (self.b1,), 404),
            "role changed": ("UPDATE team_user SET rol = 'admin', credential_revision ="
                             " credential_revision + 1 WHERE id = %s", (self.ids["olga"],), 401),
            "account deactivated": ("UPDATE team_user SET active = 0 WHERE id = %s", (self.ids["olga"],), 401),
            "signed out": ("UPDATE team_session SET revoked_at = 'x' WHERE user_id = %s",
                           (self.ids["olga"],), 401),
            "terrain transferred": ("UPDATE inventory_terrain SET base_id = %s WHERE id = %s",
                                    (self.b2, self.t1), 404),
        }

    def test_each_scope_change_waits_for_a_transaction_that_already_checked(self):
        import psycopg
        sesion = self.sesion("olga")
        for nombre in list(self.cambios()):
            sentencia, params, esperado = self.cambios()[nombre]  # this round's fixture ids
            with self.subTest(nombre):
                escritor, administrador = self.conectar(), self.conectar()
                auth.reverificar_terreno(escritor, sesion, self.t1, "archivos.subir")  # FOR SHARE held
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    administrador.raw.execute(sentencia, params)
                administrador.raw.rollback()
                escritor.raw.commit()                      # the write transaction ends...
                administrador.raw.execute(sentencia, params)  # ...and the change goes through
                administrador.raw.commit()
                with self.assertRaises(ApiError) as error:
                    auth.reverificar_terreno(escritor, sesion, self.t1, "archivos.subir")
                self.assertEqual(error.exception.status, esperado)
                escritor.raw.close()
                administrador.raw.close()
                self.bajar()
                self.limpiar()
                self.levantar()
                sesion = self.sesion("olga")

    def test_the_check_waits_for_an_uncommitted_scope_change_then_sees_it(self):
        import psycopg
        sesion = self.sesion("olga")
        for nombre in list(self.cambios()):
            sentencia, params, esperado = self.cambios()[nombre]  # this round's fixture ids
            with self.subTest(nombre):
                escritor, administrador = self.conectar(), self.conectar()
                administrador.raw.execute(sentencia, params)  # not committed yet
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    auth.reverificar_terreno(escritor, sesion, self.t1, "archivos.subir")
                escritor.raw.rollback()
                administrador.raw.commit()
                with self.assertRaises(ApiError) as error:
                    auth.reverificar_terreno(escritor, sesion, self.t1, "archivos.subir")
                self.assertEqual(error.exception.status, esperado)
                escritor.raw.close()
                administrador.raw.close()
                self.bajar()
                self.limpiar()
                self.levantar()
                sesion = self.sesion("olga")

    def test_two_readers_share_and_two_exclusive_writers_queue(self):
        import psycopg
        olga, omar = self.sesion("olga"), self.sesion("omar")
        uno, otro = self.conectar(), self.conectar()
        # Two attachment writers on the same terrain do not block each other at the check.
        auth.reverificar_terreno(uno, olga, self.t1, "archivos.subir")
        auth.reverificar_terreno(otro, omar, self.t1, "archivos.subir")
        uno.raw.rollback()
        otro.raw.rollback()
        # Two writers that will update the terrain row queue instead of deadlocking on an upgrade.
        auth.reverificar_terreno(uno, olga, self.t1, "maestra.editar", exclusivo=True)
        with self.assertRaises(psycopg.errors.LockNotAvailable) as error:
            auth.reverificar_terreno(otro, omar, self.t1, "maestra.editar", exclusivo=True)
        self.assertTrue(postgres.es_bloqueo(error.exception))
        otro.raw.rollback()
        uno.raw.commit()
        auth.reverificar_terreno(otro, omar, self.t1, "maestra.editar", exclusivo=True)
        # The same for two administrators on one base.
        ada, alan = self.sesion("ada"), self.sesion("alan")
        otro.raw.rollback()
        auth.reverificar_base(uno, ada, self.b1, "bases.gestionar", exclusivo=True)
        with self.assertRaises(psycopg.errors.LockNotAvailable):
            auth.reverificar_base(otro, alan, self.b1, "bases.gestionar", exclusivo=True)


if __name__ == "__main__":
    unittest.main()

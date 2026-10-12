"""Pilot load journey: which route puts 100 terrains into the editable master table.

Three routes are driven end to end, through the real HTTP dispatcher with real
sessions (SQLite), with 100 synthetic terrains:

  1. the legacy CSV import            -> fills only `base` / `terreno`;
  2. POST /api/maestra/bases/:bid/terrenos, one request per row
                                      -> fills the master table, no duplicate check;
  3. scripts/cargar_maestra.py        -> the pilot route: one CSV, one base, one
                                         transaction, duplicates skipped.

Fictional accounts: ada (administrator), olga (operator granted the pilot
base), otto (operator with no grant).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from server import app as app_module
from server import auth, db
from tests.support import TEST_PASSWORD
from tests.test_roles_y_bases import Escenario, filas, nuevo, sql

SCRIPT = Path(__file__).parents[1] / "scripts" / "cargar_maestra.py"
spec = importlib.util.spec_from_file_location("cargar_maestra", SCRIPT)
cargar_maestra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cargar_maestra)

# Mexican states and municipalities; the terrains themselves are invented.
LUGARES = (("Jalisco", "Zapopan", 20.72, -103.39), ("Nuevo León", "Apodaca", 25.78, -100.19),
           ("Querétaro", "El Marqués", 20.61, -100.28), ("Yucatán", "Mérida", 20.97, -89.62),
           ("Estado de México", "Tecámac", 19.71, -98.97))
ENCABEZADO = "Terreno,Estado,Municipio,Superficie m2,Asking Price,X,Y"
ESCRITAS = ("inventory_terrain", "inventory_revision", "inventory_event",
            "inventory_operation_result")


def terrenos(n=100):
    """n synthetic terrains as master-table fields. Every seventh has no X/Y.
    X is the latitude and Y the longitude, as in ARA's files."""
    lista = []
    for i in range(1, n + 1):
        estado, municipio, lat, lon = LUGARES[i % len(LUGARES)]
        t = {"terreno": f"Predio Ficticio {i:03d}", "estado": estado, "municipio": municipio,
             "superficie_m2": 1000.0 + 10 * i, "asking_price": 500000.0 + 1000 * i}
        if i % 7:
            t.update(lat=round(lat + i / 10000, 5), lon=round(lon - i / 10000, 5))
        lista.append(t)
    return lista


def como_csv(lista):
    return "\n".join([ENCABEZADO] + [
        ",".join(str(t.get(c, "")) for c in ("terreno", "estado", "municipio", "superficie_m2",
                                             "asking_price", "lat", "lon"))
        for t in lista]) + "\n"


class Piloto(Escenario, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.db_path = Path(self._dir.name) / "piloto.db"
        entorno = patch.dict(os.environ, {"ARA_MAP_DB": str(self.db_path)})
        entorno.start()
        self.addCleanup(entorno.stop)
        os.environ.pop("ARA_MAP_DATABASE_URL", None)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()
        self.addCleanup(self.bajar)
        with db.session() as conn:
            self.ids = {n: auth.create_user(conn, n, n.capitalize() + " Ficticia", TEST_PASSWORD,
                                            iterations=1000, rol=rol)["id"]
                        for n, rol in (("ada", "admin"), ("olga", "operador"),
                                       ("otto", "operador"))}
        self.cookies = {n: self.entrar(n) for n in self.ids}
        self.base_piloto = self.crear_base("Piloto Ficticio")
        self.ok(self.otorgar(self.base_piloto, "olga"))
        self.datos = terrenos()

    # -- helpers ----------------------------------------------------------------

    def en_maestra(self, base_id=None):
        return self.cuenta("inventory_terrain", "base_id = ?", (base_id or self.base_piloto,))

    def escritas(self):
        return {t: self.cuenta(t) for t in ESCRITAS}

    def listar(self, user, consulta="", base_id=None):
        return self.call("GET", f"/api/maestra/bases/{base_id or self.base_piloto}/terrenos"
                         + consulta, user=user)

    def crear_por_http(self, campos, clave, user="ada"):
        return self.call("POST", f"/api/maestra/bases/{self.base_piloto}/terrenos", campos, user,
                         headers={"Idempotency-Key": clave})

    def subir(self, path, cuerpo, user="ada"):
        peticion = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", method="POST", data=cuerpo,
            headers={"X-Archivo": quote("piloto.csv"), "Cookie": self.cookies[user]})
        try:
            with urllib.request.urlopen(peticion, timeout=20) as respuesta:
                return respuesta.status, json.loads(respuesta.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def cargar(self, *extra, datos=None, base=None, admin="ada", texto=None):
        """Run scripts/cargar_maestra.py against this test's database."""
        archivo = Path(self._dir.name) / "carga.csv"
        archivo.write_text(texto if texto is not None else como_csv(datos or self.datos),
                           encoding="utf-8")
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = cargar_maestra.main(["--sqlite", str(self.db_path), "--base",
                                          base or self.base_piloto, "--admin", admin, *extra,
                                          str(archivo)])
        self.assertEqual(codigo, 0)
        return salida.getvalue()

    def comprobar_visibilidad(self):
        """The acceptance check shared by both routes that reach the master table:
        the granted operator pages, filters and edits; the other one sees nothing."""
        # Paged: 100 rows in pages of 40, each row once.
        vistos, cursor = [], ""
        while cursor is not None:
            pagina = self.ok(self.listar("olga", f"?limit=40&sort=terreno{cursor}"))
            self.assertEqual(pagina["total"], 100)
            vistos += pagina["terrenos"]
            cursor = f"&cursor={quote(pagina['next_cursor'])}" if pagina["next_cursor"] else None
        self.assertEqual([t["draft"]["terreno"] for t in vistos],
                         [t["terreno"] for t in self.datos])
        self.assertTrue(all(t["base_id"] == self.base_piloto for t in vistos))
        # X stayed the latitude and Y the longitude; a row without them stays without.
        primero, septimo = vistos[0]["draft"], vistos[6]["draft"]
        self.assertEqual((primero["lat"], primero["lon"]),
                         (self.datos[0]["lat"], self.datos[0]["lon"]))
        self.assertGreater(primero["lat"], 0)
        self.assertLess(primero["lon"], 0)
        self.assertEqual((septimo["lat"], septimo["lon"]), (None, None))
        self.assertEqual(sum(t["ubicacion"]["modo"] == "ninguna" for t in vistos), 14)

        # Filtered: by state, and by search text.
        jalisco = self.ok(self.listar("olga", "?estado=Jalisco&limit=200"))
        self.assertEqual(jalisco["total"], 20)
        self.assertEqual({t["draft"]["estado"] for t in jalisco["terrenos"]}, {"Jalisco"})
        self.assertEqual(self.ok(self.listar("olga", "?q=Ficticio%20042"))["total"], 1)

        # Edited by the granted operator, with history.
        elegido = vistos[41]
        estado, cuerpo = self.patch(elegido["id"], {"direccion": "Calle Inventada 42"}, "olga")
        self.assertEqual(estado, 200, cuerpo)
        self.assertEqual(cuerpo["terreno"]["draft"]["direccion"], "Calle Inventada 42")
        self.assertEqual(cuerpo["terreno"]["version"], 2)
        historial = self.ok(self.call("GET", f"/api/inventario/terrenos/{elegido['id']}/historial",
                                      user="olga"))
        self.assertEqual([e["action"] for e in historial["eventos"]], ["update", "create"])

        # The operator without the grant: no base, no list, no record, no edit.
        self.assertEqual(self.ok(self.call("GET", "/api/maestra/bases", user="otto"))["bases"], [])
        self.assertEqual(self.listar("otto")[0], 404)
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{elegido['id']}",
                                   user="otto")[0], 404)
        self.assertEqual(self.patch(elegido["id"], {"direccion": "No"}, "otto")[0], 404)
        self.assertEqual(self.call("GET", "/api/inventario/terrenos", user="otto")[0], 403)
        # The administrator sees them in the unscoped master table too.
        self.assertEqual(self.ok(self.call(
            "GET", f"/api/inventario/terrenos?base={self.base_piloto}"))["total"], 100)

    # -- 1. the legacy import ------------------------------------------------------

    def test_the_legacy_import_never_reaches_the_master_table(self):
        cuerpo = como_csv(self.datos).encode("utf-8")
        # Administrators only: an operator cannot even preview.
        self.assertEqual(self.subir("/api/importar/vista-previa", cuerpo, "olga")[0], 403)
        estado, vista = self.subir("/api/importar/vista-previa", cuerpo)
        self.assertEqual(estado, 200, vista)
        estado, hecho = self.call("POST", "/api/importar/confirmar", {"token": vista["token"]})
        self.assertEqual(estado, 200, hecho)
        # 100 rows in the legacy workspace, under a legacy integer base id...
        self.assertIsInstance(hecho["base"]["id"], int)
        self.assertEqual(self.cuenta("terreno", "base_id = ?", (hecho["base"]["id"],)), 100)
        # ...and nothing at all in the master table or its work bases.
        self.assertEqual(self.escritas(), dict.fromkeys(ESCRITAS, 0))
        self.assertEqual(self.cuenta("maestra_base"), 1)
        self.assertEqual(self.ok(self.listar("olga"))["total"], 0)

    # -- 2. one HTTP create per row -------------------------------------------------

    def test_creating_row_by_row_over_http_reaches_the_base_but_does_not_dedupe(self):
        claves = [f"piloto-{nuevo()}" for _ in self.datos]
        # A granted operator may create in the base (maestra.editar); so may the admin.
        for i, (campos, clave) in enumerate(zip(self.datos, claves)):
            self.ok(self.crear_por_http(campos, clave, "olga" if i % 2 else "ada"))
        self.assertEqual(self.en_maestra(), 100)
        self.assertEqual(self.crear_por_http(self.datos[0], f"piloto-{nuevo()}", "otto")[0], 404)
        self.comprobar_visibilidad()

        # Retrying with the SAME Idempotency-Key and body returns the same record.
        for i, (campos, clave) in enumerate(zip(self.datos, claves)):
            self.ok(self.crear_por_http(campos, clave, "olga" if i % 2 else "ada"))
        self.assertEqual(self.en_maestra(), 100)
        # The same key with other data is refused...
        self.assertEqual(self.crear_por_http({"terreno": "Otro"}, claves[0])[0], 409)
        # ...but the same terrain under a NEW key is silently a second record:
        # this route has no notion of nombre + estado + municipio + superficie.
        self.ok(self.crear_por_http(self.datos[0], f"piloto-{nuevo()}"))
        self.assertEqual(self.en_maestra(), 101)
        self.assertEqual(self.ok(self.listar("olga", "?q=Ficticio%20001"))["total"], 2)

    # -- 3. scripts/cargar_maestra.py -------------------------------------------------

    def test_dry_run_reports_and_writes_nothing(self):
        salida = self.cargar("--dry-run")
        self.assertIn("SIMULACIÓN: no se escribió nada.", salida)
        self.assertIn("Filas leídas: 100 · se crearían: 100 · omitidas por duplicadas: 0", salida)
        self.assertEqual(self.escritas(), dict.fromkeys(ESCRITAS, 0))

    def test_a_real_run_loads_100_rows_into_the_named_base_with_history(self):
        otra = self.crear_base("Otra Base Ficticia")
        salida = self.cargar(base="Piloto Ficticio")  # by exact name; by id everywhere else
        self.assertIn("Filas leídas: 100 · creadas: 100 · omitidas por duplicadas: 0", salida)
        self.assertEqual(self.en_maestra(), 100)
        self.assertEqual(self.en_maestra(otra), 0)
        self.assertEqual(self.cuenta("inventory_terrain", "base_id IS NULL"), 0)
        # One revision, one "create" event and one idempotency row each, under the
        # named administrator: the same rows a create in the app leaves.
        self.assertEqual(self.escritas(), dict.fromkeys(ESCRITAS, 100))
        self.assertEqual({(e["action"], e["actor_id"], e["actor_name"], e["version"])
                          for e in filas("inventory_event")},
                         {("create", self.ids["ada"], "Ada Ficticia", 1)})
        self.assertEqual({r["base_id"] for r in filas("inventory_revision")}, {self.base_piloto})
        self.assertEqual({t["created_by"] for t in filas("inventory_terrain")}, {self.ids["ada"]})
        # No currency is assumed for the prices.
        self.assertEqual({r["moneda"] for r in filas("inventory_revision")}, {None})
        self.assertEqual(self.base(self.base_piloto)["terrenos"], 100)
        self.comprobar_visibilidad()

    def test_a_rerun_skips_every_duplicate_and_reports_it(self):
        self.cargar()
        antes = self.escritas()
        salida = self.cargar()
        self.assertIn("Filas leídas: 100 · creadas: 0 · omitidas por duplicadas: 100", salida)
        self.assertEqual(salida.count("DUPLICADA línea"), 100)
        self.assertEqual(self.escritas(), antes)

        # Same identity with another price: skipped and reported, never updated.
        # Same name and place with another area: a different parcel, created.
        # A repeat inside the file: only the first is created. Archived still counts.
        archivado = sql(lambda c: c.execute(
            "SELECT t.id, t.version FROM inventory_terrain t JOIN inventory_revision r"
            " ON r.id = t.draft_revision_id WHERE r.terreno = ?",
            ("Predio Ficticio 003",)).fetchone())
        self.ok(self.call("POST", f"/api/inventario/terrenos/{archivado['id']}/archivar",
                          {"expected_version": archivado["version"]}))
        nuevo_predio = {"terreno": "Predio Ficticio 101", "estado": "Jalisco",
                        "municipio": "Zapopan", "superficie_m2": 5000.0}
        mezcla = [{**self.datos[0], "asking_price": 1.0},
                  {**self.datos[1], "superficie_m2": 99999.0},
                  self.datos[2], nuevo_predio, nuevo_predio]
        salida = self.cargar(datos=mezcla)
        self.assertIn("Filas leídas: 5 · creadas: 2 · omitidas por duplicadas: 3", salida)
        self.assertIn("Cambia: Asking Price", salida)
        self.assertIn("ya existe en otra línea de este archivo", salida)
        self.assertEqual(self.en_maestra(), 102)
        precio = sql(lambda c: c.execute(
            "SELECT asking_price FROM inventory_revision WHERE terreno = ?",
            ("Predio Ficticio 001",)).fetchall())
        self.assertEqual([p["asking_price"] for p in precio], [self.datos[0]["asking_price"]])

    def test_an_unknown_ambiguous_or_archived_base_is_refused(self):
        with self.assertRaises(SystemExit) as caso:
            self.cargar(base=nuevo())
        self.assertIn("no existe", str(caso.exception))
        self.crear_base("Piloto Ficticio")  # names are not unique: the id is required then
        with self.assertRaises(SystemExit) as caso:
            self.cargar(base="Piloto Ficticio")
        self.assertIn("no es única", str(caso.exception))
        self.ok(self.archivar(self.base_piloto))
        with self.assertRaises(SystemExit) as caso:
            self.cargar()
        self.assertIn("está archivada", str(caso.exception))
        self.assertEqual(self.escritas(), dict.fromkeys(ESCRITAS, 0))

    def test_only_an_active_administrator_may_be_the_actor(self):
        for login in ("olga", "nadie"):
            with self.assertRaises(SystemExit) as caso:
                self.cargar(admin=login)
            self.assertIn("no es un administrador activo", str(caso.exception))
        with db.escritura() as conn:
            auth.set_active(conn, "ada", False)
        with self.assertRaises(SystemExit):
            self.cargar()
        self.assertEqual(self.escritas(), dict.fromkeys(ESCRITAS, 0))

    def test_one_invalid_row_stops_the_whole_load(self):
        malos = [*self.datos[:10], {**self.datos[10], "lat": 200.0}]
        for extra in ((), ("--dry-run",)):
            with self.assertRaises(SystemExit) as caso:
                self.cargar(*extra, datos=malos)
            self.assertIn("línea 12 (Predio Ficticio 011): lat: La latitud va de -90 a 90.",
                          str(caso.exception))
        self.assertEqual(self.escritas(), dict.fromkeys(ESCRITAS, 0))

    def test_what_the_master_table_cannot_hold_is_reported_not_hidden(self):
        texto = ("Terreno;Estado;Municipio;Superficie m2;Asking Price;X;Y;Corredor\n"
                 "Predio Ficticio A;Jalisco;Zapopan;1.500,5;SD;20,7;-103,4;Persona Inventada\n"
                 ";Jalisco;Zapopan;900;;;;\n")
        salida = self.cargar("--decimales", "comma", "--moneda", "MXN", texto=texto)
        self.assertIn("creadas: 1 · omitidas por duplicadas: 0 · sin nombre (no cargadas): 1",
                      salida)
        self.assertIn("SIN NOMBRE línea 3", salida)
        self.assertIn("«SD» en asking_price no es un número", salida)
        self.assertIn("columnas no cargadas (la tabla maestra no las tiene): Corredor", salida)
        (fila,) = filas("inventory_revision")
        self.assertEqual((fila["superficie_m2"], fila["lat"], fila["lon"]), (1500.5, 20.7, -103.4))
        # --moneda only labels a price that exists.
        self.assertEqual((fila["asking_price"], fila["moneda"]), (None, None))

    def test_the_declared_currency_goes_on_priced_rows_and_survives_a_rerun(self):
        self.cargar("--moneda", "MXN", datos=self.datos[:3])
        self.assertEqual({r["moneda"] for r in filas("inventory_revision")}, {"MXN"})
        salida = self.cargar("--moneda", "MXN", datos=self.datos[:3])
        self.assertIn("creadas: 0 · omitidas por duplicadas: 3", salida)
        self.assertNotIn("Cambia", salida)

    def test_the_command_needs_an_explicit_target(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cargar_maestra.main(["--base", "x", "--admin", "ada", "nada.csv"])
        with self.assertRaises(SystemExit) as caso:
            cargar_maestra.main(["--url-env", "ARA_VARIABLE_QUE_NO_EXISTE", "--base", "x",
                                 "--admin", "ada", "nada.csv"])
        self.assertIn("no está definida", str(caso.exception))
        with self.assertRaises(SystemExit) as caso:
            cargar_maestra.main(["--sqlite", str(Path(self._dir.name) / "no-hay.db"), "--base",
                                 "x", "--admin", "ada", "nada.csv"])
        self.assertIn("No existe", str(caso.exception))
        self.assertFalse((Path(self._dir.name) / "no-hay.db").exists())
        self.assertNotIn("load_dotenv", SCRIPT.read_text())


if __name__ == "__main__":
    unittest.main()

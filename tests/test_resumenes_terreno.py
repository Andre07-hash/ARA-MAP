"""Packet 3A: the private `archivos` and `ubicacion` siblings of a terrain.

Real mounted application over loopback, real sessions, on SQLite and on a
disposable Postgres schema. Terrains are created through the API (so they have
a draft); attachments go through the mounted attachment routes. The fixtures
and HTTP helpers are Team B's (tests/test_archivos_http.py), borrowed without
their tests.
"""

from __future__ import annotations

import unittest
import uuid

from server import db
from tests import test_archivos_http as b  # by module: its TestCases must not be collected here

PDF, URL, kmz = b.PDF, b.URL, b.kmz

DESCRIPTOR = {"id", "archivo_version_id", "utilizable", "bbox", "punto_interior"}
# Names that must never appear as a key anywhere in a terrain row.
PROHIBIDAS = {"geojson", "clave_final", "clave_temporal", "clave", "sha256", "sha256_geojson",
              "candidatos", "url", "coordinates_cuerpo", "features", "geometry"}


def _sin_pruebas(clase: type) -> dict:
    return {k: v for k, v in vars(clase).items() if not k.startswith("test_")}


def claves(valor) -> set:
    if isinstance(valor, dict):
        return set(valor) | {k for v in valor.values() for k in claves(v)}
    if isinstance(valor, list):
        return {k for v in valor for k in claves(v)}
    return set()


class Resumenes:
    locals().update(_sin_pruebas(b.HTTPChecks))      # setUp, sessions, bases, HTTP helpers

    def crear(self, base=None, login="ana", **campos):
        s, r = self.j("POST", f"/api/maestra/bases/{base or self.base}/terrenos", login, campos,
                      str(uuid.uuid4()))
        self.assertEqual(s, 200, r)
        return r["terreno"]

    def ver(self, tid, login="ana"):
        s, r = self.j("GET", f"/api/inventario/terrenos/{tid}", login)
        self.assertEqual(s, 200, r)
        return r["terreno"]

    def lista(self, base=None, login="ana", consulta=""):
        return self.j("GET", f"/api/maestra/bases/{base or self.base}/terrenos{consulta}", login)

    def kmz_activo(self, tid, nombre="poligono_simple", login="ana"):
        _inicio, completo = self.archivo_completo(kmz(nombre), "kmz", login=login, terreno=tid)
        return completo

    # -- shapes ---------------------------------------------------------------------

    def test_a_blank_terrain_has_empty_summary_and_no_location_on_every_surface(self):
        creado = self.crear()
        vacio = {"pdf_total": 0, "pdf_recientes": [], "kmz": None}
        nada = {"modo": "ninguna", "xy": "sin_dato", "geometria": None}
        s, pagina = self.lista()
        s2, maestra = self.j("GET", "/api/inventario/terrenos")
        s3, guardado = self.j("PATCH", f"/api/inventario/terrenos/{creado['id']}",
                              datos={"expected_version": creado["version"], "changes": {"terreno": "Lote Ficticio"}})
        self.assertEqual((s, s2, s3), (200, 200, 200))
        for nombre, t in (("create", creado), ("detail", self.ver(creado["id"])),
                          ("base list", pagina["terrenos"][0]), ("master list", maestra["terrenos"][0]),
                          ("save", guardado["terreno"])):
            with self.subTest(nombre):
                self.assertEqual((t["archivos"], t["ubicacion"]), (vacio, nada))

    def test_xy_alone_locates_as_a_point_and_bad_xy_does_not(self):
        buena = self.crear(lat=20.5, lon=-100.4)
        invertida = self.crear(lat=40.0, lon=-100.4)        # outside Mexico
        self.assertEqual(buena["ubicacion"], {"modo": "punto", "xy": "valida", "geometria": None})
        self.assertEqual(invertida["ubicacion"], {"modo": "ninguna", "xy": "invalida", "geometria": None})

    def test_an_active_boundary_locates_a_terrain_without_xy_and_changes_no_cell(self):
        t = self.crear()
        completo = self.kmz_activo(t["id"])
        gid = completo["archivo"]["geometria_activa_id"]
        self.assertTrue(gid)
        ahora = self.ver(t["id"])
        g = ahora["ubicacion"]["geometria"]
        self.assertEqual((ahora["ubicacion"]["modo"], ahora["ubicacion"]["xy"]), ("geometria", "sin_dato"))
        self.assertEqual(set(g), DESCRIPTOR)
        self.assertEqual((g["id"], g["utilizable"], g["archivo_version_id"]),
                         (gid, True, completo["archivo"]["version_actual_id"]))
        self.assertEqual(len(g["bbox"]), 4)
        self.assertEqual(g["punto_interior"]["type"], "Point")
        lon, lat = g["punto_interior"]["coordinates"]
        self.assertTrue(g["bbox"][0] <= lon <= g["bbox"][2] and g["bbox"][1] <= lat <= g["bbox"][3])
        # X/Y stay blank; the terrain's own version and revision did not move.
        self.assertEqual((ahora["draft"]["lat"], ahora["draft"]["lon"]), (None, None))
        self.assertEqual((ahora["version"], ahora["revision_number"], ahora["updated_at"]),
                         (t["version"], t["revision_number"], t["updated_at"]))
        self.assertEqual(ahora["archivos"]["kmz"]["geometria_activa_id"], gid)
        # A boundary wins over valid X/Y, which stay as they are.
        s, r = self.j("PATCH", f"/api/inventario/terrenos/{t['id']}",
                      datos={"expected_version": t["version"], "changes": {"lat": 20.5, "lon": -100.4}})
        self.assertEqual(s, 200, r)
        self.assertEqual((r["terreno"]["ubicacion"]["modo"], r["terreno"]["ubicacion"]["xy"],
                          r["terreno"]["ubicacion"]["geometria"]["id"], r["terreno"]["draft"]["lat"]),
                         ("geometria", "valida", gid, 20.5))

    def test_rows_carry_no_body_key_or_candidate_and_stay_small(self):
        t = self.crear()
        self.kmz_activo(t["id"])
        self.archivo_completo(PDF, "pdf", terreno=t["id"])
        s, pagina = self.lista()
        fila = pagina["terrenos"][0]
        self.assertEqual(claves(fila) & PROHIBIDAS, set())
        self.assertEqual(claves(fila["ubicacion"]),
                         {"modo", "xy", "geometria", "type", "coordinates"} | DESCRIPTOR)
        self.assertEqual(fila["archivos"]["pdf_total"], 1)
        import json
        self.assertLess(len(json.dumps(fila["archivos"]) + json.dumps(fila["ubicacion"])), 2500)

    # -- lifecycle ---------------------------------------------------------------------

    def test_a_pending_unusable_or_rejected_replacement_keeps_the_previous_boundary(self):
        t = self.crear()
        gid = self.kmz_activo(t["id"])["archivo"]["geometria_activa_id"]
        for nombre in ("fuera_de_mexico", "documento_vacio"):     # valid but unusable; rejected
            with self.subTest(nombre):
                s, inicio = self.iniciar(kmz(nombre), "kmz", terreno=t["id"])
                self.assertEqual(s, 200, inicio)
                # Pending replacement: the old boundary is still the location.
                self.assertEqual(self.ver(t["id"])["ubicacion"]["geometria"]["id"], gid)
                self.assertEqual(self.subir(inicio["version_id"], kmz(nombre))[0], 200)
                s, completo = self.completar(inicio["version_id"])
                self.assertEqual(s, 200, completo)
                self.assertFalse(completo["version"]["aplicada"])
                despues = self.ver(t["id"])
                self.assertEqual((despues["ubicacion"]["modo"], despues["ubicacion"]["geometria"]["id"]),
                                 ("geometria", gid))
                self.assertEqual(despues["version"], t["version"])

    def test_retiring_the_kmz_falls_back_to_valid_xy_or_to_nothing(self):
        con_xy, sin_xy = self.crear(lat=20.5, lon=-100.4), self.crear()
        for t, esperado in ((con_xy, "punto"), (sin_xy, "ninguna")):
            completo = self.kmz_activo(t["id"])
            self.assertEqual(self.ver(t["id"])["ubicacion"]["modo"], "geometria")
            s, r = self.j("POST", f"/api/archivos/{completo['archivo']['id']}/retirar",
                          datos={"expected_revision": completo["archivo"]["revision"]},
                          clave=str(uuid.uuid4()))
            self.assertEqual(s, 200, r)
            ahora = self.ver(t["id"])
            self.assertEqual((ahora["ubicacion"]["modo"], ahora["ubicacion"]["geometria"],
                              ahora["archivos"]["kmz"]), (esperado, None, None))
            self.assertEqual(ahora["version"], t["version"])

    def test_another_accounts_pending_upload_shows_no_metadata_in_a_row(self):
        t = self.crear()
        s, inicio = self.iniciar(PDF, "pdf", login="olga", terreno=t["id"], nombre="secreto-ficticio.pdf")
        self.assertEqual(s, 200, inicio)
        ajena = self.ver(t["id"], "ana")["archivos"]["pdf_recientes"][0]["ultima_version"]
        propia = self.ver(t["id"], "olga")["archivos"]["pdf_recientes"][0]["ultima_version"]
        self.assertEqual(propia["nombre_original"], "secreto-ficticio.pdf")
        for campo in ("id", "nombre_original", "tamano", "tamano_declarado", "numero"):
            self.assertNotIn(campo, ajena)
        s, pagina = self.lista(login="ana")
        fila = next(f for f in pagina["terrenos"] if f["id"] == t["id"])
        self.assertEqual(fila["archivos"]["pdf_recientes"][0]["ultima_version"], ajena)

    # -- scope, counts and bounds --------------------------------------------------------

    def test_scope_decides_every_summary_and_descriptor(self):
        t = self.crear()
        self.kmz_activo(t["id"])
        # omar has no grant: the base, the record and its attachments do not exist for him.
        self.assertEqual(self.lista(login="omar")[0], 404)
        self.assertEqual(self.j("GET", f"/api/inventario/terrenos/{t['id']}", "omar")[0], 404)
        # olga has the grant and sees the boundary; then loses the grant.
        self.assertEqual(self.ver(t["id"], "olga")["ubicacion"]["modo"], "geometria")
        self.sql("DELETE FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?",
                 (self.base, self.users["olga"]["id"]))
        s, r = self.j("GET", f"/api/inventario/terrenos/{t['id']}", "olga")
        self.assertEqual((s, "terreno" in r), (404, False))
        self.assertEqual(self.lista(login="olga")[0], 404)
        # Transferred to a base olga still has: visible there, with its files.
        actual = self.ver(t["id"])
        s, r = self.j("POST", f"/api/inventario/terrenos/{t['id']}/transferir",
                      datos={"expected_version": actual["version"], "base_id": self.base2})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["terreno"]["ubicacion"]["modo"], "geometria")
        s, pagina = self.lista(self.base2, "olga")
        self.assertEqual([f["ubicacion"]["modo"] for f in pagina["terrenos"]], ["geometria"])
        # Unassigned: administrators only.
        actual = self.ver(t["id"])
        s, r = self.j("POST", f"/api/inventario/terrenos/{t['id']}/transferir",
                      datos={"expected_version": actual["version"], "base_id": None})
        self.assertEqual(s, 200, r)
        self.assertEqual(self.j("GET", f"/api/inventario/terrenos/{t['id']}", "olga")[0], 404)
        self.assertEqual(self.lista(self.base2, "olga")[1]["terrenos"], [])

    def test_a_page_is_bounded_and_counted_by_the_server(self):
        ids = [self.crear(terreno=f"Lote Ficticio {n}")["id"] for n in range(3)]
        self.kmz_activo(ids[0])
        s, pagina = self.lista(consulta="?limit=2")
        self.assertEqual((s, pagina["total"], len(pagina["terrenos"])), (200, 3, 2))
        self.assertTrue(all("archivos" in f and "ubicacion" in f for f in pagina["terrenos"]))
        s, resto = self.lista(consulta=f"?limit=2&cursor={pagina['next_cursor']}")
        self.assertEqual((s, len(resto["terrenos"]), resto["next_cursor"]), (200, 1, None))
        vistos = {f["id"]: f["ubicacion"]["modo"] for f in pagina["terrenos"] + resto["terrenos"]}
        self.assertEqual(vistos, {ids[0]: "geometria", ids[1]: "ninguna", ids[2]: "ninguna"})

    def test_a_conflict_answer_carries_the_current_siblings(self):
        t = self.crear()
        self.kmz_activo(t["id"])
        cuerpo = {"expected_version": t["version"], "changes": {"terreno": "Uno"}}
        self.assertEqual(self.j("PATCH", f"/api/inventario/terrenos/{t['id']}", datos=cuerpo)[0], 200)
        s, r = self.j("PATCH", f"/api/inventario/terrenos/{t['id']}", datos=cuerpo)
        self.assertEqual((s, r["detalle"]["terreno"]["ubicacion"]["modo"]), (409, "geometria"))

    def test_the_public_catalog_gains_nothing(self):
        t = self.crear()
        self.kmz_activo(t["id"])
        s, r = self.j("GET", "/api/publico/terrenos", login=None)
        self.assertEqual(s, 200)
        self.assertEqual(claves(r) & {"archivos", "ubicacion", "geometria"}, set())

    def test_no_schema_change(self):
        self.assertEqual(db.SCHEMA_VERSION, 10)


class ResumenesSQLite(Resumenes, unittest.TestCase):
    locals().update(_sin_pruebas(b.HTTPSQLite))


@unittest.skipUnless(URL, "No Postgres test connection configured")
class ResumenesPostgres(Resumenes, unittest.TestCase):
    locals().update(_sin_pruebas(b.HTTPPostgres))


if __name__ == "__main__":
    unittest.main()

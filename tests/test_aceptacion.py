"""The acceptance scenario defined by the supervisor review of 21 Sep 2026.

One uninterrupted run: import a real workbook, reconcile every row, correct a
missing location, verify the detail, save and reopen after a restart, compare
three versions, merge versions of one source, then delete and replace that
source without changing historical provenance.

It is one test on purpose. The point is that the whole chain holds together,
not that each link works in isolation -- the unit tests already cover that.
"""

from __future__ import annotations

import unittest

from server import db
from server.importer import TerrainRecord, read_workbook
from server.matching import Disposition, classify
from server.repo import bases, mapas, terrenos
from server.validation import validate_all
from tests.support import FIXTURE, TempDatabase


def extra(orden: int, nombre: str, m2: float) -> TerrainRecord:
    return TerrainRecord(
        orden=orden, fila=0, terreno=nombre, estado="Jalisco", municipio="Tala",
        superficie_m2=m2, superficie_ha=m2 / 10_000, lat=20.65, lon=-103.70,
    )


class AcceptanceScenario(TempDatabase):
    def test_the_whole_chain(self):
        # 1 - import a real workbook and account for every row.
        resultado = read_workbook(FIXTURE)
        self.assertEqual(
            resultado.filas_con_datos,
            len(resultado.records) + len(resultado.rechazadas),
        )
        base_id = bases.create(self.conn, "Septiembre", "real.xlsx", resultado.hoja)
        terrenos.insert(
            self.conn, base_id, resultado.records, validate_all(resultado.records))

        base = bases.get(self.conn, base_id)
        self.assertEqual(base["conteo"], 79)
        self.assertEqual(
            base["ubicados"] + base["sin_coordenadas"] + base["ubicacion_invalida"],
            base["conteo"],
            "the location counts do not add up to the total",
        )
        ubicados_iniciales = base["ubicados"]

        # 2 - correct a missing location through the append workflow.
        sin_coords = next(
            t for t in terrenos.for_base(self.conn, base_id) if not t["ubicado"])
        corregido = TerrainRecord(
            orden=sin_coords["orden"], fila=0, terreno=sin_coords["terreno"],
            estado=sin_coords["estado"], municipio=sin_coords["municipio"],
            direccion=sin_coords["direccion"],
            superficie_m2=sin_coords["superficie_m2"],
            superficie_ha=sin_coords["superficie_ha"],
            asking_price=sin_coords["asking_price"],
            asking_m2=sin_coords["asking_m2"], lat=25.78, lon=-100.19,
        )
        decision = classify(
            [corregido], terrenos.dedupe_rows(self.conn, base_id))[0]
        self.assertEqual(
            decision.disposition, Disposition.CONFLICTO,
            "a coordinate correction was treated as a duplicate")
        self.assertIn("lat", {d.campo for d in decision.diferencias})
        terrenos.update_from_record(self.conn, decision.existing_id, corregido, ())
        self.assertEqual(
            bases.get(self.conn, base_id)["ubicados"], ubicados_iniciales + 1)

        # 3 - the corrected record reads back correctly.
        detalle = next(
            t for t in terrenos.for_base(self.conn, base_id)
            if t["id"] == decision.existing_id)
        self.assertEqual(detalle["lat"], 25.78)
        self.assertTrue(detalle["ubicado"])

        # 4 - save, and reopen after a restart.
        mapa_v1 = mapas.create(
            self.conn, "Septiembre v1", "simple",
            [{"base_id": base_id, "color": "#2a78d6"}])
        conteo_v1 = mapas.get(self.conn, mapa_v1)["conteo"]

        self.conn.close()
        self.conn = db.connect(self.db_path)
        self.assertEqual(mapas.get(self.conn, mapa_v1)["conteo"], conteo_v1)

        # 5 - three versions of the same source.
        terrenos.insert(self.conn, base_id, [extra(998, "Añadido v2", 5_000)], {})
        mapa_v2 = mapas.create(
            self.conn, "Septiembre v2", "simple",
            [{"base_id": base_id, "color": "#2a78d6"}])
        terrenos.insert(self.conn, base_id, [extra(999, "Añadido v3", 6_000)], {})
        mapa_v3 = mapas.create(
            self.conn, "Septiembre v3", "simple",
            [{"base_id": base_id, "color": "#2a78d6"}])

        # 6 - merge them; all three must survive and be distinguishable.
        plan = mapas.plan_merge(self.conn, [mapa_v1, mapa_v2, mapa_v3])
        self.assertEqual(len(plan["capas"]), 3, "a version was dropped")
        self.assertEqual(plan["duplicadas"], [])

        combinado = mapas.merge(
            self.conn, "Historia", [mapa_v1, mapa_v2, mapa_v3],
            ["#2a78d6", "#eb6834", "#1baf7a"])
        capas = mapas.get(self.conn, combinado)["capas"]
        self.assertEqual(
            [c["conteo"] for c in capas],
            [conteo_v1, conteo_v1 + 1, conteo_v1 + 2])
        self.assertEqual(len({c["nombre"] for c in capas}), 3,
                         "the versions cannot be told apart")

        # 7 - delete and replace the source; history must not move.
        antes = [c["conteo"] for c in capas]
        bases.delete(self.conn, base_id)

        repuesto = read_workbook(FIXTURE)
        nueva = bases.create(self.conn, "Reemplazo", "real.xlsx", repuesto.hoja)
        terrenos.insert(
            self.conn, nueva, repuesto.records, validate_all(repuesto.records))
        self.assertNotEqual(nueva, base_id, "the deleted id was handed out again")

        mapas.refresh_snapshot(self.conn, combinado)
        despues = mapas.get(self.conn, combinado)["capas"]
        self.assertEqual([c["conteo"] for c in despues], antes,
                         "the historical map changed when its source was replaced")
        self.assertTrue(
            all(c["base_id"] is None and not c["base_existe"] for c in despues),
            "a deleted source is still attached to the saved layers")


if __name__ == "__main__":
    unittest.main()

"""Round 2 baseline: accepted 1A records and accepted 1B attachments, composed.

A terrain created through 1A's real route receives an attachment through 1B's
real lifecycle service (1B has no route yet), a cell is edited, the terrain is
transferred and a grant is revoked. Attachment reads and idempotent replays
follow the terrain's current scope; attachment rows stay on the same ids; the
terrain version and the attachment revision count independently.

Test only: no route, screen or domain behaviour is added by this file.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import archivos, postgres
from server.almacen import AlmacenEnMemoria
from server.errors import ApiError
from tests.test_archivos import PDF, kmz
from tests.test_roles_y_bases import URL, Escenario, filas

INMUTABLES = ("archivo_version", "archivo_intento", "geometria")


class Composicion(Escenario):
    """The check. Mixed into one TestCase per backend."""

    def subir(self, terreno, datos, tipo, user, clave):
        sesion = self.sesion(user)
        iniciada = archivos.iniciar(
            sesion, terreno, tipo=tipo, nombre_original=f"ficticio.{tipo}",
            tamano_declarado=len(datos), sha256_declarado=hashlib.sha256(datos).hexdigest(),
            idempotency_key=clave)
        archivos.escribir_temporal(sesion, iniciada["version_id"], [datos], self.almacen)
        return iniciada, archivos.completar(sesion, iniciada["version_id"], self.almacen)

    def negado(self, llamada):
        """Out of scope is the one not-found of a resource that does not exist."""
        with self.assertRaises(ApiError) as error:
            llamada()
        self.assertEqual((error.exception.status, error.exception.detalle["code"]), (404, "not_found"))

    def transferir(self, terreno, base):
        return self.ok(self.call("POST", f"/api/inventario/terrenos/{terreno}/transferir",
                                 {"expected_version": self.version(terreno), "base_id": base}))

    def test_a_created_terrain_keeps_its_attachments_through_edit_transfer_and_revocation(self):
        self.almacen = AlmacenEnMemoria()
        # 1A: a blank terrain created by an operator in her base, through the route.
        tid = self.ok(self.call("POST", f"/api/maestra/bases/{self.b1}/terrenos", {}, "olga",
                                {"Idempotency-Key": "clave-composicion-1"}))["terreno"]["id"]
        self.assertEqual(self.version(tid), 1)

        # 1B: a PDF and a KMZ layout on that terrain, by the same operator.
        pdf_inicio, pdf = self.subir(tid, PDF, "pdf", "olga", "clave-pdf-composicion")
        _, plano = self.subir(tid, kmz("poligono_con_hueco"), "kmz", "olga", "clave-kmz-composicion")
        self.assertTrue(pdf["aplicada"] and plano["aplicada"])
        self.assertIsNotNone(plano["archivo"]["geometria_activa_id"])
        self.assertEqual(self.version(tid), 1)  # files do not move the terrain version
        archivo_id, version_id = pdf["archivo"]["id"], pdf["version"]["id"]
        revisiones = {a["id"]: a["revision"] for a in filas("archivo")}
        fijo = {t: filas(t) for t in INMUTABLES}
        archivo = filas("archivo")

        def igual():
            self.assertEqual({t: filas(t) for t in INMUTABLES}, fijo)
            self.assertEqual(filas("archivo"), archivo)

        def lee(user):
            return {a["id"]: a["version_actual_id"]
                    for a in archivos.listar(self.sesion(user), tid)["archivos"]}

        def repite(user="olga"):
            return archivos.completar(self.sesion(user), pdf_inicio["version_id"], self.almacen)

        def fuera(user):
            sesion = self.sesion(user)
            self.negado(lambda: archivos.listar(sesion, tid))
            self.negado(lambda: archivos.historial(sesion, archivo_id))
            self.negado(lambda: archivos.completar(sesion, version_id, self.almacen))
            self.negado(lambda: archivos.iniciar(
                sesion, tid, tipo="pdf", nombre_original="ficticio.pdf", tamano_declarado=len(PDF),
                sha256_declarado=hashlib.sha256(PDF).hexdigest(),
                idempotency_key="clave-pdf-composicion"))
            self.negado(lambda: archivos.retirar(
                sesion, archivo_id, expected_revision=revisiones[archivo_id],
                idempotency_key="clave-retiro-negado"))

        esperado = lee("olga")
        self.assertEqual(len(esperado), 2)
        self.assertEqual(lee("omar"), esperado)

        # A cell edit: one terrain version, no attachment row or revision touched.
        self.assertEqual(self.patch(tid, {"terreno": "Lote Compuesto"}, "olga")[0], 200)
        self.assertEqual(self.version(tid), 2)
        igual()

        # Transfer to Base Dos: same ids, olga (Base Uno only) loses reads and replays.
        self.transferir(tid, self.b2)
        self.assertEqual(self.version(tid), 3)
        igual()
        fuera("olga")
        self.assertEqual(self.call("GET", f"/api/inventario/terrenos/{tid}", user="olga")[0], 404)
        self.assertEqual(lee("omar"), esperado)
        self.assertEqual(lee("ada"), esperado)

        # Back to Base Uno: her replay returns the same immutable version, creating nothing.
        self.transferir(tid, self.b1)
        repetida = repite()
        self.assertEqual((repetida["replay"], repetida["version"]["id"]), (True, version_id))
        igual()

        # Revoking her grant: denied again; the others still read the same references.
        self.ok(self.otorgar(self.b1, "omar"))
        fuera("olga")
        fuera("otto")
        self.assertEqual(lee("omar"), esperado)
        igual()
        self.ok(self.otorgar(self.b1, "olga", "omar"))
        self.assertEqual(repite()["version"]["id"], version_id)
        self.assertEqual(lee("olga"), esperado)

        # The counters are independent in the other direction too: retiring the PDF moves
        # the attachment revision and leaves the terrain version where the transfers put it.
        retirado = archivos.retirar(self.sesion("olga"), archivo_id,
                                    expected_revision=revisiones[archivo_id],
                                    idempotency_key="clave-retiro-composicion", almacen=self.almacen)
        self.assertEqual(retirado["archivo"]["revision"], revisiones[archivo_id] + 1)
        self.assertEqual(self.version(tid), 4)
        self.assertEqual({t: filas(t) for t in INMUTABLES}, fijo)
        self.assertEqual(len(filas("inventory_revision", "inventory_id = ?", (tid,))), 4)


class ComposicionSqlite(Composicion, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._entorno = patch.dict(os.environ, {"ARA_MAP_DB": str(Path(self._dir.name) / "prueba.db")})
        self._entorno.start()
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        self.addCleanup(self._dir.cleanup)
        self.addCleanup(self._entorno.stop)
        self.levantar()


@unittest.skipUnless(URL, "No Postgres test connection configured")
class ComposicionPostgres(Composicion, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.schema = "test_ara_composicion_" + uuid.uuid4().hex
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

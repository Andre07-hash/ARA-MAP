"""Schema 9 -> 10: attachment storage (archivo and the rows that hang from it).

The same checks run on SQLite and, when ARA_MAP_TEST_DATABASE_URL is set, on a
disposable Postgres schema. Each backend builds a populated schema-9 database
with fictional data, upgrades it twice and then exercises the new constraints.
Every statement runs in a real transaction that is committed, because the
cycle constraints are deferred and only speak at COMMIT.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import db, postgres
from server.repo import inventario as repo
from tests.test_schema_v9 import AHORA, URL, V8_TABLES, V9_TABLES, foto, poblar

V10_TABLES = ("archivo", "archivo_version", "archivo_intento", "geometria", "archivo_evento",
              "archivo_trabajo")
DURABLES = V10_TABLES[:-1]


def nuevo():
    return str(uuid.uuid4())


def insertar(conn, tabla, **valores):
    conn.execute(f"INSERT INTO {tabla} ({', '.join(valores)}) VALUES ({', '.join('?' for _ in valores)})",
                 tuple(valores.values()))
    return valores.get("id")


def poblar_v9(conn):
    """Schema-9 content on top of the schema-8 fixture: a work base with a
    grant, two local columns, an assigned terrain and their history."""
    poblar(conn)
    ana, beto = (conn.execute("SELECT id FROM team_user WHERE login = ?", (n,)).fetchone()["id"]
                 for n in ("ana", "beto"))
    base = nuevo()
    conn.execute("UPDATE team_user SET rol = 'admin' WHERE id = ?", (ana,))
    insertar(conn, "maestra_base", id=base, nombre="Base Ejemplo", created_at=AHORA, created_by=ana,
             updated_at=AHORA, updated_by=ana)
    insertar(conn, "maestra_base_acceso", base_id=base, user_id=beto, granted_at=AHORA, granted_by=ana)
    for orden, (nombre, tipo) in enumerate((("Folio", "texto"), ("Visita", "fecha")), 1):
        columna = insertar(conn, "inventory_column", id=nuevo(), base_id=base, nombre=nombre, tipo=tipo,
                           orden=orden, created_at=AHORA, created_by=ana, updated_at=AHORA, updated_by=ana)
        insertar(conn, "maestra_base_event", id=nuevo(), base_id=base, column_id=columna, version=1,
                 action="columna_creada", actor_id=ana, actor_name="Ana Prueba", at=AHORA)
    insertar(conn, "team_user_event", id=nuevo(), user_id=beto, action="acceso_otorgado", base_id=base,
             actor_id=ana, actor_name="Ana Prueba", at=AHORA)
    conn.execute("UPDATE inventory_terrain SET base_id = ?", (base,))


class V10Checks:
    """Mixed into one TestCase per backend, which provides confirmar(fn): run
    fn(conn) in one transaction and commit it."""

    def rechaza(self, fn):
        with self.assertRaises(self.integridad):
            self.confirmar(fn)

    def sql(self, texto, params=()):
        return lambda conn: conn.execute(texto, params)

    def ana(self, conn):
        return dict(conn.execute("SELECT id, display_name FROM team_user WHERE login = 'ana'").fetchone())

    # -- builders, each returning the new id -----------------------------------

    def terreno(self, conn):
        return repo.create(conn, {"terreno": "Lote ficticio"}, self.ana(conn), nuevo(), "hash")["terreno"]["id"]

    def archivo(self, conn, inv, tipo="kmz", **extra):
        ana = self.ana(conn)["id"]
        valores = dict(id=nuevo(), inventory_id=inv, tipo=tipo,
                       columna_id="core:kmz" if tipo == "kmz" else "core:archivos",
                       creado_en=AHORA, creado_por=ana, actualizado_en=AHORA, actualizado_por=ana)
        return insertar(conn, "archivo", **dict(valores, **extra))

    def version(self, conn, archivo, inv, numero=1, estado="disponible", **extra):
        ana = self.ana(conn)["id"]
        valores = dict(id=nuevo(), archivo_id=archivo, inventory_id=inv, numero=numero, estado=estado,
                       revision_base=1, nombre_original="plano ficticio.kmz", tamano_declarado=10,
                       sha256_declarado="a" * 64, clave_temporal="temporal/" + nuevo(),
                       subida_vence_en=AHORA, completar_antes_de=AHORA, iniciado_en=AHORA, iniciado_por=ana)
        if estado != "subiendo":
            valores.update(terminado_en=AHORA, terminado_por=ana)
        if estado in ("disponible", "fallido"):
            valores.update(finalizado_en=AHORA, finalizado_por=ana, aplicada=0)
        if estado == "disponible":
            valores.update(tamano=10, sha256="a" * 64, clave_final="final/" + nuevo(), aplicada=1,
                           tipo_detectado="application/vnd.google-earth.kmz")
        return insertar(conn, "archivo_version", **dict(valores, **extra))

    def intento(self, conn, version, numero=1, origen="completar", resultado="rechazado", **extra):
        valores = dict(id=nuevo(), archivo_version_id=version, numero=numero, origen=origen,
                       resultado=resultado, resultado_json="{}", analizador="kmz-ficticio",
                       creado_en=AHORA, creado_por=self.ana(conn)["id"])
        return insertar(conn, "archivo_intento", **dict(valores, **extra))

    def geometria(self, conn, archivo, version, inv, intento, **extra):
        valores = dict(id=nuevo(), archivo_id=archivo, archivo_version_id=version, inventory_id=inv,
                       intento_id=intento, geojson='{"type":"MultiPolygon","coordinates":[]}',
                       bbox_oeste=-103.5, bbox_sur=20.5, bbox_este=-103.4, bbox_norte=20.6,
                       punto_lon=-103.45, punto_lat=20.55, partes=1, huecos=0, vertices=5, utilizable=1,
                       bytes_geojson=41, sha256_geojson="b" * 64, creado_en=AHORA)
        return insertar(conn, "geometria", **dict(valores, **extra))

    def listo(self, conn, archivo, version, inv, numero=1, origen="completar", **geometria):
        """A 'listo' attempt and its geometry, which name each other."""
        i, g = nuevo(), nuevo()
        self.intento(conn, version, numero, origen, "listo", id=i, geometria_id=g)
        self.geometria(conn, archivo, version, inv, i, id=g, **geometria)
        return i, g

    def procesada(self, conn, archivo, inv, numero=1):
        """A finalized KMZ version with its one 'listo' attempt and geometry."""
        v = self.version(conn, archivo, inv, numero)
        return (v, *self.listo(conn, archivo, v, inv))

    def kmz(self, versiones=1):
        """Committed: a terrain, its KMZ attachment and N processed versions."""
        def crear(conn):
            inv = self.terreno(conn)
            a = self.archivo(conn, inv)
            return (inv, a, *(self.procesada(conn, a, inv, n) for n in range(1, versiones + 1)))
        return self.confirmar(crear)

    def evento(self, conn, archivo, inv, **extra):
        valores = dict(id=nuevo(), archivo_id=archivo, inventory_id=inv, accion="procesado",
                       actor_id=self.ana(conn)["id"], actor_name="Ana Prueba", at=AHORA)
        return insertar(conn, "archivo_evento", **dict(valores, **extra))

    def cuenta(self, tabla, donde="1 = 1", params=()):
        return self.confirmar(lambda conn: conn.execute(
            f"SELECT COUNT(*) AS n FROM {tabla} WHERE {donde}", params).fetchone()["n"])

    # -- 1. the upgrade --------------------------------------------------------

    def test_schema_9_content_is_unchanged_and_the_new_tables_start_empty(self):
        self.assertEqual((db.SCHEMA_VERSION, self.version_actual()), (10, 10))
        for tabla, filas in self.antes.items():
            self.assertTrue(filas or tabla == "incidencia", tabla)
            self.assertEqual(self.despues[tabla], filas, tabla)
        self.assertEqual(self.antes["team_user"][0].keys() >= {"rol"}, True)
        for tabla in V10_TABLES:
            self.assertEqual(self.despues[tabla], [], tabla)

    # -- 2. what it accepts ----------------------------------------------------

    def test_several_pdfs_an_empty_attachment_and_a_pending_upload_are_valid(self):
        def crear(conn):
            inv = self.terreno(conn)
            uno, dos = self.archivo(conn, inv, "pdf"), self.archivo(conn, inv, "pdf")
            self.version(conn, uno, inv, tipo_detectado="application/pdf")
            pendiente = self.version(conn, dos, inv, estado="subiendo")
            self.archivo(conn, inv, "pdf")  # no upload yet
            return inv, pendiente
        inv, pendiente = self.confirmar(crear)
        self.assertEqual(self.cuenta("archivo", "inventory_id = ? AND version_actual_id IS NULL", (inv,)), 3)
        self.assertEqual(self.cuenta(
            "archivo_version", "id = ? AND clave_final IS NULL AND tamano IS NULL AND aplicada IS NULL"
            " AND terminado_en IS NULL AND finalizado_en IS NULL", (pendiente,)), 1)

    def test_every_terminal_upload_state_is_storable(self):
        def crear(conn):
            inv = self.terreno(conn)
            a = self.archivo(conn, inv)
            for numero, (estado, extra) in enumerate((
                    ("disponible", {}), ("disponible", {"aplicada": 0, "motivo_no_aplicada": "superada"}),
                    ("fallido", {"error_codigo": "sha256"}), ("cancelado", {}),
                    ("expirado", {"terminado_por": None})), 1):
                self.version(conn, a, inv, numero, estado, **extra)
            return a
        self.assertEqual(self.cuenta("archivo_version", "archivo_id = ?", (self.confirmar(crear),)), 5)

    def test_retired_kmzs_accumulate_beside_one_live_kmz(self):
        def crear(conn):
            inv, ana = self.terreno(conn), self.ana(conn)["id"]
            for motivo in ("usuario", "sin_contenido"):
                self.archivo(conn, inv, retirado_en=AHORA, retirado_por=ana, retirado_motivo=motivo)
            self.archivo(conn, inv)
            return inv
        inv = self.confirmar(crear)
        self.assertEqual(self.cuenta("archivo", "inventory_id = ?", (inv,)), 3)
        # A second live KMZ on that terrain is refused; on another terrain it is fine.
        self.rechaza(lambda conn: self.archivo(conn, inv))
        self.confirmar(lambda conn: self.archivo(conn, self.terreno(conn)))

    def test_a_kmz_replacement_is_a_second_version_of_the_same_attachment(self):
        inv, a, (v1, _, g1), (v2, _, g2) = self.kmz(versiones=2)
        activar = "UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ?, revision = revision + 1 WHERE id = ?"
        self.confirmar(self.sql(activar, (v1, g1, a)))
        self.confirmar(self.sql(activar, (v2, g2, a)))
        self.assertEqual(self.cuenta("archivo", "id = ? AND revision = 3 AND geometria_activa_id = ?", (a, g2)), 1)
        self.assertEqual(self.cuenta("inventory_event", "inventory_id = ?", (inv,)), 1)  # only its creation

    # -- 2. what it refuses ----------------------------------------------------

    def test_a_column_and_type_that_do_not_belong_together_are_refused(self):
        inv = self.confirmar(self.terreno)
        for columna, tipo in (("core:archivos", "kmz"), ("core:kmz", "pdf"), ("custom:x", "pdf"),
                              ("core:kmz", "kml")):
            self.rechaza(lambda conn, c=columna, t=tipo: self.archivo(conn, inv, columna_id=c, tipo=t))

    def test_keys_counters_and_sizes_out_of_range_are_refused(self):
        inv, a, (v, _i, _g) = self.kmz()
        casos = (
            lambda c: self.archivo(c, self.terreno(c), id=None),
            lambda c: self.archivo(c, self.terreno(c), revision=0),
            lambda c: self.version(c, a, inv, 2, id=None),
            lambda c: self.version(c, a, inv, 0),
            lambda c: self.version(c, a, inv, 2, revision_base=0),
            lambda c: self.version(c, a, inv, 2, tamano_declarado=-1),
            lambda c: self.version(c, a, inv, 2, tamano=-1),
            lambda c: self.intento(c, v, 0, "reintento"),
            lambda c: self.intento(c, v, 2, "manual"),
            lambda c: self.intento(c, v, 2, "reintento", "en_curso"),
            lambda c: self.evento(c, a, inv, revision=0),
            lambda c: self.evento(c, a, inv, accion="borrado"),
            lambda c: self.archivo(c, self.terreno(c), retirado_en=AHORA),              # no reason
            lambda c: self.archivo(c, self.terreno(c), retirado_motivo="usuario"),      # no date
            lambda c: self.archivo(c, self.terreno(c), retirado_en=AHORA, retirado_motivo="otro"),
            lambda c: self.archivo(c, self.terreno(c), retirado_por=self.ana(c)["id"]),  # not retired
        )
        for numero, caso in enumerate(casos):
            with self.subTest(caso=numero):
                self.rechaza(caso)

    def test_geometry_counts_may_be_zero_but_not_negative(self):
        inv, a, (v, _i, _g) = self.kmz()

        def con(numero, **extra):
            return lambda conn: self.listo(conn, a, v, inv, numero, "seleccion", **extra)
        self.confirmar(con(2, huecos=0, partes=0, vertices=0, bytes_geojson=0))
        for campo in ("huecos", "partes", "vertices", "bytes_geojson"):
            self.rechaza(con(3, **{campo: -1}))
        self.rechaza(con(3, utilizable=2))

    def test_version_and_attempt_numbers_are_unique_within_their_owner(self):
        inv, a, (v, _i, _g) = self.kmz()
        self.rechaza(lambda c: self.version(c, a, inv, 1))
        self.confirmar(lambda c: self.intento(c, v, 2, "reintento"))
        self.rechaza(lambda c: self.intento(c, v, 2, "reintento"))

    def test_owners_that_do_not_exist_or_disagree_are_refused(self):
        inv, a, (v, _i, _g) = self.kmz()
        otro_inv, otro, _ = self.kmz()
        self.rechaza(lambda c: self.archivo(c, "no-existe"))
        self.rechaza(lambda c: self.archivo(c, self.terreno(c), creado_por="nadie"))
        self.rechaza(lambda c: self.version(c, "no-existe", inv, 2))
        self.rechaza(lambda c: self.version(c, a, otro_inv, 2))       # the attachment's other terrain
        self.rechaza(lambda c: self.intento(c, "no-existe", 1))
        # A geometry repeats its version's attachment and terrain, and cannot disagree with them.
        self.rechaza(lambda c: self.listo(c, a, v, inv, 2, "seleccion", inventory_id=otro_inv))
        self.rechaza(lambda c: self.listo(c, a, v, inv, 2, "seleccion", archivo_id=otro))
        self.confirmar(lambda c: self.listo(c, a, v, inv, 2, "seleccion"))

    def test_state_and_outcome_combinations_that_cannot_happen_are_refused(self):
        inv, a, _ = self.kmz()
        ana = self.confirmar(self.ana)["id"]
        casos = {
            "pending with an outcome": ("subiendo", {"aplicada": 0}),
            "pending but terminated": ("subiendo", {"terminado_en": AHORA}),
            "pending but terminated by someone": ("subiendo", {"terminado_por": ana}),
            "pending but finalized": ("subiendo", {"finalizado_en": AHORA, "finalizado_por": ana}),
            "available without an outcome": ("disponible", {"aplicada": None}),
            "available without verified bytes": ("disponible", {"clave_final": None}),
            "available without a size": ("disponible", {"tamano": None}),
            "available without finalization": ("disponible", {"finalizado_en": None, "finalizado_por": None}),
            "available without termination": ("disponible", {"terminado_en": None, "terminado_por": None}),
            "applied with a reason not to": ("disponible", {"motivo_no_aplicada": "superada"}),
            "reason outside the two": ("disponible", {"aplicada": 0, "motivo_no_aplicada": "otro"}),
            "failed but applied": ("fallido", {"aplicada": 1}),
            "failed without an outcome": ("fallido", {"aplicada": None}),
            "failed with a superseded reason": ("fallido", {"motivo_no_aplicada": "retirado"}),
            "cancelled with an outcome": ("cancelado", {"aplicada": 0}),
            "cancelled but finalized": ("cancelado", {"finalizado_en": AHORA, "finalizado_por": ana}),
            "expired with an outcome": ("expirado", {"aplicada": 1}),
            "finalized by nobody": ("disponible", {"finalizado_por": None}),
            "unknown state": ("procesando", {}),
            "outcome outside 0/1": ("disponible", {"aplicada": 2}),
        }
        for nombre, (estado, extra) in casos.items():
            with self.subTest(nombre):
                self.rechaza(lambda c, e=estado, x=extra: self.version(c, a, inv, 9, e, **x))

    def test_a_reason_not_applied_needs_an_explicit_zero_outcome(self):
        # Review F1: with aplicada NULL, "motivo IS NULL OR aplicada = 0" is NULL, which a
        # CHECK accepts. The states whose outcome must be NULL could carry a reason.
        inv, a, _ = self.kmz()
        numero = iter(range(2, 99))
        for estado in ("subiendo", "cancelado", "expirado"):
            for motivo in ("superada", "retirado"):
                with self.subTest(estado=estado, motivo=motivo):
                    self.rechaza(lambda c, e=estado, m=motivo: self.version(
                        c, a, inv, next(numero), e, motivo_no_aplicada=m))
            self.confirmar(lambda c, e=estado: self.version(c, a, inv, next(numero), e))
        for motivo in ("superada", "retirado", None):
            self.confirmar(lambda c, m=motivo: self.version(
                c, a, inv, next(numero), aplicada=0, motivo_no_aplicada=m))
        self.confirmar(lambda c: self.version(c, a, inv, next(numero), "fallido"))
        self.assertEqual(self.cuenta("archivo_version", "archivo_id = ?", (a,)), 8)
        self.assertEqual(self.cuenta("archivo_version", "archivo_id = ? AND aplicada IS NULL"
                                     " AND motivo_no_aplicada IS NOT NULL", (a,)), 0)

    # -- 3. same-version integrity ---------------------------------------------

    def test_the_active_geometry_must_belong_to_the_current_version(self):
        _inv, a, (v1, _, g1), (v2, _, g2) = self.kmz(versiones=2)
        apuntar = "UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ? WHERE id = ?"
        self.rechaza(self.sql(apuntar, (v1, g2, a)))    # same attachment, other version: at COMMIT
        self.rechaza(self.sql(apuntar, (None, g2, a)))  # the MATCH SIMPLE bypass
        self.confirmar(self.sql(apuntar, (v2, g2, a)))
        self.confirmar(self.sql(apuntar, (v1, None, a)))  # a current version with no layout
        self.confirmar(self.sql(apuntar, (v1, g1, a)))

    def test_pointers_cannot_name_another_attachment_or_terrain(self):
        _inv, a, (v, _, g) = self.kmz()
        _otro_inv, otro, (ov, _, og) = self.kmz()
        apuntar = "UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ? WHERE id = ?"
        self.rechaza(self.sql(apuntar, (ov, None, a)))
        self.rechaza(self.sql(apuntar, (ov, og, a)))
        self.rechaza(self.sql(apuntar, (v, og, a)))
        self.rechaza(self.sql(apuntar, ("no-existe", None, a)))
        self.confirmar(self.sql(apuntar, (v, g, a)))
        self.confirmar(self.sql(apuntar, (ov, og, otro)))

    def test_a_pdf_never_has_an_active_geometry(self):
        def crear(conn):
            inv = self.terreno(conn)
            a = self.archivo(conn, inv, "pdf")
            return a, self.procesada(conn, a, inv)
        a, (v, _i, g) = self.confirmar(crear)
        self.rechaza(self.sql("UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ? WHERE id = ?",
                              (v, g, a)))

    def test_an_attempt_and_its_geometry_must_name_each_other(self):
        inv, a, (v1, i1, g1), (v2, i2, g2) = self.kmz(versiones=2)
        # A 'listo' attempt whose geometry never arrives fails at COMMIT...
        self.rechaza(lambda c: self.intento(c, v1, 2, "reintento", "listo", geometria_id=nuevo()))
        # ...as does one that claims another attempt's geometry, of this or another version.
        self.rechaza(lambda c: self.intento(c, v1, 2, "reintento", "listo", geometria_id=g1))
        self.rechaza(lambda c: self.intento(c, v1, 2, "reintento", "listo", geometria_id=g2))
        self.rechaza(self.sql("UPDATE archivo_intento SET geometria_id = ? WHERE id = ?", (g2, i1)))
        # A geometry cannot hang from an attempt of another version, or share an attempt.
        self.rechaza(lambda c: self.listo(c, a, v2, inv, 2, "seleccion", archivo_version_id=v1))
        self.rechaza(lambda c: self.geometria(c, a, v1, inv, i1))
        self.rechaza(lambda c: self.geometria(c, a, v1, inv, "no-existe"))
        # Nor from an attempt that does not name it: a rejected run has no geometry,
        # whichever version the geometry claims.
        rechazado = self.confirmar(lambda c: self.intento(c, v2, 2, "reintento"))
        for version in (v1, v2):
            self.rechaza(lambda c, v=version: self.geometria(c, a, v, inv, rechazado))
        # And an attempt cannot drop or swap the geometry that depends on it.
        self.rechaza(self.sql("UPDATE archivo_intento SET geometria_id = ? WHERE id = ?", (g1, i2)))
        # Only 'listo' carries a geometry, and 'listo' always does.
        self.rechaza(lambda c: self.intento(c, v1, 2, "reintento", "listo"))
        self.rechaza(lambda c: self.intento(c, v1, 2, "reintento", "rechazado", geometria_id=g1))

    # -- 4. audit, completion attempts, leases ---------------------------------

    def test_an_event_cannot_reference_rows_of_another_owner(self):
        inv, a, (v1, i1, g1), (v2, i2, g2) = self.kmz(versiones=2)
        otro_inv, otro, (ov, oi, og) = self.kmz()
        self.confirmar(lambda c: self.evento(c, a, inv))
        self.confirmar(lambda c: self.evento(c, a, inv, archivo_version_id=v1))
        self.confirmar(lambda c: self.evento(c, a, inv, archivo_version_id=v1, intento_id=i1, geometria_id=g1))
        self.confirmar(lambda c: self.evento(c, a, inv, archivo_version_id=v2, geometria_id=g2))
        malos = (
            dict(inventory_id=otro_inv),                                      # not the attachment's terrain
            dict(archivo_version_id=ov),                                      # another attachment's version
            dict(archivo_version_id=v1, intento_id=i2),                       # attempt of another version
            dict(archivo_version_id=v1, intento_id=oi),
            dict(archivo_version_id=v1, geometria_id=g2),                     # geometry of another version
            dict(archivo_version_id=v1, geometria_id=og),
            dict(archivo_version_id=v1, intento_id=i1, geometria_id="no-existe"),
            dict(intento_id=i1),                                              # NULL version: no bypass
            dict(geometria_id=g1),
            dict(intento_id=i1, geometria_id=g1),
            dict(archivo_version_id="no-existe"),
            dict(base_id="no-existe"),
            dict(actor_id="nadie"),
        )
        for numero, extra in enumerate(malos):
            with self.subTest(caso=numero):
                self.rechaza(lambda c, x=extra: self.evento(c, a, inv, **x))
        # Two attempts of one version: an event cannot pair one's id with the other's geometry.
        i1b, _ = self.confirmar(lambda c: self.listo(c, a, v1, inv, 2, "seleccion"))
        self.rechaza(lambda c: self.evento(c, a, inv, archivo_version_id=v1, intento_id=i1b, geometria_id=g1))
        self.assertEqual(self.cuenta("archivo_evento", "archivo_id = ?", (otro,)), 0)

    def test_decision_revisions_are_unique_and_informational_events_repeat(self):
        inv, a, _ = self.kmz()
        for _ in range(3):
            self.confirmar(lambda c: self.evento(c, a, inv, accion="subida_iniciada"))
        self.confirmar(lambda c: self.evento(c, a, inv, accion="capa_activada", revision=2))
        self.rechaza(lambda c: self.evento(c, a, inv, accion="retirado", revision=2))
        self.confirmar(lambda c: self.evento(c, a, inv, accion="retirado", revision=3))
        self.assertEqual(self.cuenta("archivo_evento", "archivo_id = ? AND revision IS NULL", (a,)), 3)

    def test_a_version_has_one_completion_attempt_and_any_number_of_retries(self):
        _inv, _a, (v, _i, _g) = self.kmz()  # its attempt 1 is the completion
        self.rechaza(lambda c: self.intento(c, v, 2, "completar"))
        for numero in (2, 3):
            self.confirmar(lambda c, n=numero: self.intento(c, v, n, "reintento"))
        self.assertEqual(self.cuenta("archivo_intento", "archivo_version_id = ?", (v,)), 3)

    def test_a_version_holds_one_lease_which_can_be_released_and_retaken(self):
        _inv, _a, (v, _i, _g) = self.kmz()

        def tomar(operacion="completar", **extra):
            return lambda c: insertar(c, "archivo_trabajo", **dict(dict(
                archivo_version_id=v, trabajo_id=nuevo(), actor_id=self.ana(c)["id"],
                operacion=operacion, inicio=AHORA, vence_en=AHORA), **extra))
        self.confirmar(tomar())
        self.rechaza(tomar("procesar"))
        self.rechaza(self.sql("DELETE FROM archivo_version WHERE id = ?", (v,)))
        self.confirmar(self.sql("DELETE FROM archivo_trabajo WHERE archivo_version_id = ?", (v,)))
        self.rechaza(tomar(trabajo_id=None))
        self.rechaza(tomar("limpiar"))
        self.rechaza(tomar(archivo_version_id="no-existe"))
        self.confirmar(tomar("activar"))
        self.confirmar(self.sql("DELETE FROM archivo_trabajo WHERE archivo_version_id = ?", (v,)))

    # -- 5. nothing cascades ---------------------------------------------------

    def test_referenced_rows_cannot_be_deleted_and_history_stays(self):
        def crear(conn):
            auth_id = insertar(conn, "team_user", id=nuevo(), login="carla-" + nuevo()[:8],
                               display_name="Carla Prueba", password_hash="x", created_at=AHORA,
                               updated_at=AHORA)
            inv = self.terreno(conn)
            a = self.archivo(conn, inv, creado_por=auth_id)
            v, i, g = self.procesada(conn, a, inv)
            conn.execute("UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ? WHERE id = ?",
                         (v, g, a))
            self.evento(conn, a, inv, archivo_version_id=v, intento_id=i, geometria_id=g)
            return auth_id, inv, a, v, i, g
        usuario, inv, a, v, i, g = self.confirmar(crear)
        for tabla, clave in (("team_user", usuario), ("inventory_terrain", inv), ("archivo", a),
                             ("archivo_version", v), ("archivo_intento", i), ("geometria", g)):
            with self.subTest(tabla):
                self.rechaza(self.sql(f"DELETE FROM {tabla} WHERE id = ?", (clave,)))
        self.assertEqual([self.cuenta(t, "id = ?", (k,)) for t, k in (
            ("archivo", a), ("archivo_version", v), ("archivo_intento", i), ("geometria", g))], [1, 1, 1, 1])
        self.assertEqual(self.cuenta("archivo_evento", "archivo_id = ?", (a,)), 1)

    # -- 6. backup and seed order ----------------------------------------------

    def test_durable_tables_are_backed_up_in_dependency_order_without_leases(self):
        orden = postgres.TABLES
        self.assertEqual(orden[-len(DURABLES):], DURABLES)
        self.assertNotIn("archivo_trabajo", orden)
        self.assertFalse(set(V10_TABLES) & postgres.ID_TABLES)
        for tabla, padres in (("archivo", ("inventory_terrain", "team_user")),
                              ("archivo_evento", ("maestra_base", "geometria"))):
            for padre in padres:
                self.assertLess(orden.index(padre), orden.index(tabla))

    def test_cyclic_attachment_rows_reload_table_by_table_in_backup_order(self):
        inv, a, (v, i, g) = self.kmz()

        def activar_y_dejar_pendiente(conn):
            conn.execute("UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ? WHERE id = ?",
                         (v, g, a))
            self.evento(conn, a, inv, archivo_version_id=v, intento_id=i, geometria_id=g, revision=2,
                        accion="capa_activada")
            pendiente = self.version(conn, a, inv, 2, "subiendo")
            insertar(conn, "archivo_trabajo", archivo_version_id=pendiente, trabajo_id=nuevo(),
                     actor_id=self.ana(conn)["id"], operacion="completar", inicio=AHORA, vence_en=AHORA)
            return pendiente
        pendiente = self.confirmar(activar_y_dejar_pendiente)
        respaldo = self.confirmar(lambda conn: foto(conn, postgres.ATTACHMENT_TABLES))

        def restaurar(conn):
            # What a restore has: the durable tables, no leases, loaded parents first.
            for tabla in reversed(V10_TABLES):
                conn.execute(f"DELETE FROM {tabla}")
            for tabla in postgres.ATTACHMENT_TABLES:
                for fila in respaldo[tabla]:
                    insertar(conn, tabla, **fila)
        self.confirmar(restaurar)
        self.assertEqual(self.confirmar(lambda conn: foto(conn, postgres.ATTACHMENT_TABLES)), respaldo)
        self.assertEqual(self.cuenta("archivo", "id = ? AND geometria_activa_id = ?", (a, g)), 1)
        # The pending upload survives as 'subiendo' with no lease: the next
        # completion may take one, or the deadline expires it.
        self.assertEqual(self.cuenta("archivo_version", "id = ? AND estado = 'subiendo'", (pendiente,)), 1)
        self.assertEqual(self.cuenta("archivo_trabajo"), 0)


class SchemaV10Sqlite(V10Checks, unittest.TestCase):
    integridad = sqlite3.IntegrityError

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "v9.db"
        v9 = sqlite3.connect(cls.path, isolation_level=None)
        v9.row_factory = sqlite3.Row
        v9.execute("PRAGMA foreign_keys = ON")
        v9.executescript(db.SCHEMA + db.INVENTORY_SCHEMA + db.WORK_BASE_SCHEMA + db.FOLDER_INDEXES)
        for tabla, columna, definicion in db.V9_COLUMNS:
            v9.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        v9.executescript(db.V9_INDEXES)
        v9.execute("PRAGMA user_version = 9")
        tablas = {r[0] for r in v9.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert not tablas & set(V10_TABLES)
        poblar_v9(v9)
        cls.antes = foto(v9, V8_TABLES + V9_TABLES)
        v9.close()
        for _ in range(2):  # the second run must change nothing
            with db.session(cls.path) as conn:
                cls.despues = foto(conn, V8_TABLES + V9_TABLES + V10_TABLES)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def confirmar(self, fn):
        conn = db.connect(self.path)
        try:
            conn.execute("BEGIN")
            try:
                resultado = fn(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            return resultado
        finally:
            conn.close()

    def version_actual(self):
        return self.confirmar(lambda conn: conn.execute("PRAGMA user_version").fetchone()[0])

    def test_the_upgrade_took_exactly_one_backup(self):
        self.assertEqual(len(list(db.backup_dir(self.path).glob("*.db"))), 1)

    def test_a_backup_file_drops_leases_and_keeps_everything_durable(self):
        # Review F2: db.backup copies the whole file; a lease must not survive in the copy.
        from tests.support import create_user
        with tempfile.TemporaryDirectory() as tmp:
            self.path = Path(tmp) / "con-arriendo.db"  # shadows the class database for this test
            self.confirmar(create_user)
            inv, a, (v, _i, g) = self.kmz()

            def activar_y_dejar_pendiente(conn):
                conn.execute("UPDATE archivo SET version_actual_id = ?, geometria_activa_id = ?"
                             " WHERE id = ?", (v, g, a))
                pendiente = self.version(conn, a, inv, 2, "subiendo")
                insertar(conn, "archivo_trabajo", archivo_version_id=pendiente, trabajo_id=nuevo(),
                         actor_id=self.ana(conn)["id"], operacion="completar", inicio=AHORA,
                         vence_en="2999-01-01T00:00:00+00:00")
                return pendiente
            pendiente = self.confirmar(activar_y_dejar_pendiente)
            antes = self.confirmar(lambda conn: foto(conn, V10_TABLES))

            copia = sqlite3.connect(db.backup(self.path))
            copia.row_factory = sqlite3.Row
            try:
                respaldo = foto(copia, V10_TABLES)
                self.assertEqual(copia.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                copia.close()
            self.assertEqual(respaldo["archivo_trabajo"], [])
            for tabla in DURABLES:
                self.assertEqual(respaldo[tabla], antes[tabla], tabla)
            self.assertEqual([(f["version_actual_id"], f["geometria_activa_id"]) for f in respaldo["archivo"]],
                             [(v, g)])
            self.assertIn(pendiente, [f["id"] for f in respaldo["archivo_version"] if f["estado"] == "subiendo"])
            # The live database is untouched: same content, lease still held.
            self.assertEqual(self.confirmar(lambda conn: foto(conn, V10_TABLES)), antes)
            self.assertEqual(len(antes["archivo_trabajo"]), 1)

    def test_a_backup_of_an_older_database_has_no_lease_table_to_clear(self):
        # The copy taken before this class's 9 -> 10 upgrade predates the attachment tables.
        (respaldo,) = db.backup_dir(type(self).path).glob("*.db")
        copia = sqlite3.connect(respaldo)
        try:
            tablas = {r[0] for r in copia.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertEqual(copia.execute("PRAGMA user_version").fetchone()[0], 9)
            self.assertTrue(copia.execute("SELECT COUNT(*) FROM maestra_base").fetchone()[0])
        finally:
            copia.close()
        self.assertFalse(tablas & set(V10_TABLES))

    def test_a_new_database_gets_the_attachment_tables(self):
        with tempfile.TemporaryDirectory() as tmp, db.session(Path(tmp) / "nueva.db") as conn:
            tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 10)
        self.assertTrue(set(V10_TABLES) <= tablas)


@unittest.skipUnless(URL, "No Postgres test connection configured")
class SchemaV10Postgres(V10Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.integridad = psycopg.IntegrityError
        cls.schema = "test_ara_v10_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.env = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.env.start()
        with postgres.session() as conn:
            # A fresh workspace through the normal path reaches 10 ...
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)
            assert postgres.schema_version(conn) == 10
            assert conn.execute("SELECT to_regclass('archivo_trabajo') AS t").fetchone()["t"]
            # ... and is then taken back to schema 9: no attachment tables.
            conn.raw.execute(
                f"DROP TABLE {', '.join(V10_TABLES)} CASCADE;"
                "UPDATE workspace_metadata SET value = '9' WHERE key = 'schema_version';", prepare=False)
        with postgres.session() as conn:
            assert postgres.schema_version(conn) == 9
            assert conn.execute("SELECT to_regclass('archivo') AS t").fetchone()["t"] is None
            poblar_v9(conn)
            cls.antes = foto(conn, V8_TABLES + V9_TABLES)
        for _ in range(2):  # the second run must change nothing
            with postgres.session() as conn:
                postgres.migrate(conn)
            with postgres.session() as conn:
                cls.despues = foto(conn, V8_TABLES + V9_TABLES + V10_TABLES)

    @classmethod
    def tearDownClass(cls):
        import psycopg
        cls.env.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def confirmar(self, fn):
        with postgres.session() as conn:  # commits on exit; deferred constraints speak there
            return fn(conn)

    def version_actual(self):
        return self.confirmar(postgres.schema_version)

    def test_the_three_cycle_constraints_exist_and_are_deferred(self):
        filas = self.confirmar(lambda conn: conn.execute(
            "SELECT conname, condeferred FROM pg_constraint WHERE conname LIKE 'fk_archivo_%'"
            " AND connamespace = current_schema()::regnamespace").fetchall())
        self.assertEqual({(f["conname"], f["condeferred"]) for f in filas}, {
            ("fk_archivo_version_actual", True), ("fk_archivo_geometria_activa", True),
            ("fk_archivo_intento_geometria", True)})

    def test_the_backup_carries_the_durable_tables_and_no_lease(self):
        import json
        self.kmz()
        postgres.backup()
        payload = json.loads(self.confirmar(lambda conn: conn.execute(
            "SELECT payload FROM workspace_backup ORDER BY id DESC LIMIT 1").fetchone()["payload"]))
        self.assertTrue(set(DURABLES) <= set(payload))
        self.assertNotIn("archivo_trabajo", payload)
        self.assertTrue(payload["geometria"])


if __name__ == "__main__":
    unittest.main()

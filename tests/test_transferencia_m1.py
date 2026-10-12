"""Hosted transfer contract M1 (Team B): parts, composition, uncertain final
writes, missing parts and deadlines, verified sliced downloads, store
resolution after authorization, and the start's checks.

Real sessions, SQL and the lifecycle, on SQLite and on a disposable Postgres
schema; bytes in the in-memory store (with its fault and uncertainty
injection) or the local-disk store. Synthetic files only.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server import archivos, db
from server.almacen import (
    AlmacenEnMemoria,
    AlmacenLocal,
    AlmacenNoConfiguradoError,
    ColisionError,
    FalloAlmacenError,
    LimiteExcedidoError,
    ObjetoAusenteError,
)
from server.repo import archivos as repo
from tests import test_archivos as base

MiB = 1024 * 1024
PARTE = archivos.PARTE_BYTES


def pdf_de(tamano: int, semilla: int = 1) -> bytes:
    """A synthetic PDF-signed body of exactly `tamano` bytes (not a real PDF)."""
    cabeza = b"%PDF-1.4\n% ficticio\n"
    cuerpo = hashlib.sha256(str(semilla).encode()).digest() * (tamano // 32 + 1)
    return (cabeza + cuerpo)[:tamano]


def _sin_pruebas(clase: type) -> dict:
    return {k: v for k, v in vars(clase).items() if not k.startswith("test_")}


class TransferChecks:
    locals().update(_sin_pruebas(base.LifecycleChecks))   # setUp, sessions, helpers

    # -- helpers ------------------------------------------------------------------

    def start_big(self, data: bytes, key: str | None = None, user: str = "ana"):
        return archivos.iniciar(
            self.sessions[user], self.terrain, tipo="pdf", nombre_original="grande.pdf",
            tamano_declarado=len(data), sha256_declarado=hashlib.sha256(data).hexdigest(),
            idempotency_key=key or str(uuid.uuid4()), bd=self.database, reloj=self.clock)

    def part(self, started, data: bytes, index: int, user: str = "ana", store=None, **kwargs):
        piece = data[index * PARTE:(index + 1) * PARTE]
        return archivos.escribir_temporal(
            self.sessions[user], started["version_id"], [piece[i:i + MiB] for i in
                                                          range(0, len(piece), MiB)],
            store or self.store, parte=index, longitud=len(piece), bd=self.database,
            reloj=self.clock, **kwargs)

    def all_parts(self, started, data: bytes, order=None):
        for i in order or range(archivos.partes_de(len(data))):
            self.part(started, data, i)

    def staging_key(self, started) -> str:
        return self.rows("archivo_version", "id = ?", (started["version_id"],))[0]["clave_temporal"]

    def finals(self, started) -> list[str]:
        return [m.clave for m in self.store.listar(archivos._final_prefix(started["version_id"]))]

    def download_all(self, version_id: str, store=None, user: str = "ana") -> bytes:
        out, desde = b"", 0
        while True:
            r = archivos.descargar(self.sessions[user], version_id, store or self.store,
                                   desde=desde, bd=self.database)
            self.assertLessEqual(r["longitud"], PARTE)
            self.assertEqual((r["desde"], len(r["contenido"])), (desde, r["longitud"]))
            out += r["contenido"]
            if r["siguiente"] is None:
                self.assertEqual(len(out), r["tamano"])
                return out
            desde = r["siguiente"]

    # -- start --------------------------------------------------------------------

    def test_start_reports_the_transfer_and_refuses_empty_files(self):
        data = pdf_de(7 * MiB)
        started = self.start_big(data, key="grande")
        self.assertEqual(started["transferencia"], {"parte_bytes": 3145728, "partes": 3})
        replay = self.start_big(data, key="grande")
        self.assertEqual(replay["version_id"], started["version_id"])
        self.assertEqual(replay["transferencia"], started["transferencia"])
        before = len(self.rows("archivo_version"))
        self.assert_code("archivo_vacio", lambda: archivos.iniciar(
            self.sessions["ana"], self.terrain, tipo="pdf", nombre_original="vacio.pdf",
            tamano_declarado=0, sha256_declarado=hashlib.sha256(b"").hexdigest(),
            idempotency_key="vacio", bd=self.database, reloj=self.clock))
        self.assertEqual(len(self.rows("archivo_version")), before)
        one = self.start_big(b"%", key="un-byte")
        self.assertEqual(one["transferencia"]["partes"], 1)
        exact = self.start_big(pdf_de(3 * PARTE), key="exacto")
        self.assertEqual(exact["transferencia"]["partes"], 3)

    def test_a_new_start_needs_a_buildable_store_but_a_replay_still_replays(self):
        data = pdf_de(10)
        def broken():
            raise AlmacenNoConfiguradoError()
        started = archivos.iniciar(
            self.sessions["ana"], self.terrain, tipo="pdf", nombre_original="a.pdf",
            tamano_declarado=10, sha256_declarado=hashlib.sha256(data).hexdigest(),
            idempotency_key="con-almacen", bd=self.database, reloj=self.clock,
            almacen=lambda: self.store)
        before = len(self.rows("archivo_version"))
        for name, factory, code, retry in (
                ("unconfigured", broken, "almacen_no_configurado", False),
                ("outage", lambda: (_ for _ in ()).throw(FalloAlmacenError()),
                 "almacen_no_disponible", True),
                ("denied", lambda: (_ for _ in ()).throw(FalloAlmacenError(reintentar=False)),
                 "almacen_no_disponible", False)):
            with self.subTest(case=name):
                error = self.assert_code(code, lambda factory=factory, name=name: archivos.iniciar(
                    self.sessions["ana"], self.terrain, tipo="pdf", nombre_original="b.pdf",
                    tamano_declarado=10, sha256_declarado=hashlib.sha256(data).hexdigest(),
                    idempotency_key=f"nuevo-{name}", bd=self.database, reloj=self.clock,
                    almacen=factory))
                self.assertEqual((error.status, error.detalle["reintentar"]), (503, retry))
        self.assertEqual(len(self.rows("archivo_version")), before)
        replay = archivos.iniciar(
            self.sessions["ana"], self.terrain, tipo="pdf", nombre_original="a.pdf",
            tamano_declarado=10, sha256_declarado=hashlib.sha256(data).hexdigest(),
            idempotency_key="con-almacen", bd=self.database, reloj=self.clock, almacen=broken)
        self.assertEqual(replay["version_id"], started["version_id"])
        # Application denials keep precedence over an unbuildable store.
        self.assert_code("not_found", lambda: archivos.iniciar(
            self.sessions["olga"], self.other_terrain, tipo="pdf", nombre_original="c.pdf",
            tamano_declarado=10, sha256_declarado=hashlib.sha256(data).hexdigest(),
            idempotency_key="fuera", bd=self.database, reloj=self.clock, almacen=broken))
        self.assert_code("archivo_vacio", lambda: archivos.iniciar(
            self.sessions["ana"], self.terrain, tipo="pdf", nombre_original="c.pdf",
            tamano_declarado=0, sha256_declarado=hashlib.sha256(b"").hexdigest(),
            idempotency_key="vacio-sin-almacen", bd=self.database, reloj=self.clock,
            almacen=broken))

    # -- parts ----------------------------------------------------------------------

    def test_parts_compose_in_order_whatever_order_and_repeats_they_arrive_in(self):
        data = pdf_de(7 * MiB + 123)
        started = self.start_big(data)
        self.all_parts(started, data, order=[2, 0, 1, 0])          # out of order, part 0 twice
        done = self.complete(started)
        self.assertEqual(done["version"]["estado"], "disponible")
        self.assertEqual(done["version"]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertFalse(done["limpieza_pendiente"])
        key = self.staging_key(started)
        self.assertTrue(all(self.store.tamano_de(k) is None
                            for k in [key] + [f"{key}-{i:02d}" for i in range(3)]))
        self.assertEqual(self.download_all(started["version_id"]), data)

    def test_part_index_and_length_are_exact(self):
        data = pdf_de(7 * MiB)
        started = self.start_big(data)
        vid = started["version_id"]

        def send(piece, index, longitud=None):
            return archivos.escribir_temporal(self.sessions["ana"], vid, [piece], self.store,
                                              parte=index, longitud=longitud,
                                              bd=self.database, reloj=self.clock)
        for name, call in (
                ("negative", lambda: send(b"x", -1)), ("past-the-end", lambda: send(b"x", 3)),
                ("bool", lambda: send(b"x", True)), ("missing-index", lambda: send(b"x", None)),
                ("short-declared", lambda: send(data[:10], 0, 10)),
                ("short-actual", lambda: send(data[:10], 0)),
                ("long-actual", lambda: archivos.escribir_temporal(
                    self.sessions["ana"], vid, [data[:MiB]] * 3 + [b"x"], self.store, parte=0,
                    bd=self.database, reloj=self.clock)),
                ("last-wrong", lambda: send(data[2 * PARTE:], 2, len(data) - 2 * PARTE + 1))):
            with self.subTest(case=name):
                self.assert_code("parte_invalida", call)
        key = self.staging_key(started)
        self.assertTrue(all(self.store.tamano_de(f"{key}-{i:02d}") is None for i in range(3)))
        single = self.start_big(b"%PDF-x")
        archivos.escribir_temporal(self.sessions["ana"], single["version_id"], [b"%PDF-x"],
                                   self.store, bd=self.database, reloj=self.clock)  # index optional
        self.assertEqual(self.complete(single)["version"]["estado"], "disponible")

    def test_parts_respect_owner_scope_deadline_and_a_live_lease(self):
        data = pdf_de(4 * MiB)
        started = self.start_big(data)
        self.assert_code("not_found", lambda: self.part(started, data, 0, user="olga"))
        self.assert_code("not_found", lambda: self.part(started, data, 0, user="beto"))
        with db.escritura(self.database) as conn:
            repo.lease(conn, version_id=started["version_id"], work_id="otro", actor_id=self.users["ana"]["id"],
                       operation="completar", started_at=archivos._now(self.clock),
                       expires_at=archivos._after(archivos._now(self.clock), 60),
                       now=archivos._now(self.clock))
        error = self.assert_code("procesamiento_en_curso", lambda: self.part(started, data, 0))
        self.assertTrue(error.detalle["reintentar"])
        self.clock.advance(61)
        self.part(started, data, 0)
        self.clock.advance(archivos.UPLOAD_SECONDS)
        self.assert_code("subida_expirada", lambda: self.part(started, data, 1))

    def test_missing_parts_are_named_and_retryable_only_before_the_upload_deadline(self):
        data = pdf_de(8 * MiB)
        started = self.start_big(data, key="faltan")
        self.part(started, data, 1)
        error = self.assert_code("contenido_temporal_ausente", lambda: self.complete(started))
        self.assertEqual((error.status, error.detalle["partes_faltantes"], error.detalle["reintentar"]),
                         (409, [0, 2], True))
        self.assertEqual(self.rows("archivo_trabajo"), [])             # the lease was released
        self.part(started, data, 0)
        self.part(started, data, 2)
        self.assertEqual(self.complete(started)["version"]["estado"], "disponible")
        # After the upload deadline: missing parts end the road for this version.
        late = self.start_big(data, key="tarde")
        self.part(late, data, 0)
        self.clock.advance(archivos.UPLOAD_SECONDS + 1)
        error = self.assert_code("contenido_temporal_ausente", lambda: self.complete(late))
        self.assertEqual((error.detalle["partes_faltantes"], error.detalle["reintentar"]), ([1, 2], False))
        self.assert_code("subida_expirada", lambda: self.part(late, data, 1))
        cancelled = archivos.cancelar(self.sessions["ana"], late["version_id"], self.store,
                                      bd=self.database, reloj=self.clock)
        self.assertEqual(cancelled["estado"], "cancelado")
        self.assertIsNone(self.store.tamano_de(self.staging_key(late) + "-00"))
        fresh = self.start_big(data, key="tarde-nuevo")              # a fresh key, a new version
        self.assertNotEqual(fresh["version_id"], late["version_id"])
        self.all_parts(fresh, data)
        self.assertEqual(self.complete(fresh)["version"]["estado"], "disponible")

    def test_cancelling_frees_the_pending_slot_and_reports_every_part_key(self):
        data = pdf_de(4 * MiB)
        pending = [self.start_big(data, key=f"p{i}") for i in range(archivos.PENDING_MAX)]
        self.assert_code("limite_pendientes", lambda: self.start_big(data, key="sexta"))
        self.part(pending[0], data, 0)
        self.part(pending[0], data, 1)
        with patch.object(self.store, "borrar", side_effect=FalloAlmacenError()):
            cancelled = archivos.cancelar(self.sessions["ana"], pending[0]["version_id"],
                                          self.store, bd=self.database, reloj=self.clock)
        self.assertTrue(cancelled["limpieza_pendiente"])                # parts may remain
        self.assertTrue(self.start_big(data, key="sexta")["version_id"])

    def test_a_late_part_write_cannot_change_a_composed_final_object(self):
        data = pdf_de(4 * MiB)
        started = self.start_big(data)
        self.all_parts(started, data)
        key = self.staging_key(started)
        real = self.store.componer

        def compose_then_restage(origenes, destino, limite):
            written = real(origenes, destino, limite)
            self.store.guardar_temporal(f"{key}-00", [b"Z" * MiB] * 3, PARTE)   # lands too late
            return written
        with patch.object(self.store, "componer", side_effect=compose_then_restage):
            done = self.complete(started)
        self.assertEqual(done["version"]["estado"], "disponible")
        self.assertEqual(self.download_all(started["version_id"]), data)

    # -- uncertain final writes and collisions -------------------------------------

    def test_a_final_write_that_landed_but_lost_its_reply_is_retryable_and_cleaned_by_db_proof(self):
        data = pdf_de(4 * MiB)
        started = self.start_big(data)
        self.all_parts(started, data)
        self.store.inyectar_incierto("componer")
        error = self.assert_code("almacen_no_disponible", lambda: self.complete(started))
        self.assertEqual((error.status, error.detalle["reintentar"], error.detalle["limpieza_pendiente"]),
                         (503, True, True))
        self.assertEqual(self.finals(started), [])         # unreferenced by the DB: this nonce removed
        self.assertEqual(self.rows("archivo_version", "id = ?", (started["version_id"],))[0]["estado"],
                         "subiendo")
        self.assertEqual(self.rows("archivo_trabajo"), [])
        done = self.complete(started)                       # a fresh nonce
        self.assertEqual(done["version"]["estado"], "disponible")
        self.assertEqual(len(self.finals(started)), 1)

    def test_an_uncertain_final_write_is_kept_when_the_database_check_fails(self):
        data = pdf_de(4 * MiB)
        started = self.start_big(data)
        self.all_parts(started, data)
        self.store.inyectar_incierto("componer")
        with patch.object(repo, "final_key_referenced", side_effect=RuntimeError("bd caída")):
            error = self.assert_code("almacen_no_disponible", lambda: self.complete(started))
        self.assertTrue(error.detalle["limpieza_pendiente"])
        self.assertEqual(len(self.finals(started)), 1)     # kept: not proven unreferenced

    def test_a_collision_winner_is_never_deleted_and_its_nonce_is_never_reused(self):
        data = pdf_de(4 * MiB)
        started = self.start_big(data)
        self.all_parts(started, data)
        real = self.store.componer
        nonces = []

        def earlier_send_won(origenes, destino, limite):
            nonces.append(destino)
            if len(nonces) == 1:
                real(origenes, destino, limite)            # the first send landed...
                raise ColisionError()                      # ...and the retry met it
            return real(origenes, destino, limite)
        with patch.object(self.store, "componer", side_effect=earlier_send_won), \
                patch.object(self.store, "borrar", wraps=self.store.borrar) as borrar:
            error = self.assert_code("almacen_no_disponible", lambda: self.complete(started))
            self.assertEqual((error.detalle["reintentar"], error.detalle["limpieza_pendiente"]),
                             (True, True))
            self.assertNotIn(nonces[0], [c.args[0] for c in borrar.call_args_list])
            self.assertIsNotNone(self.store.tamano_de(nonces[0]))
            done = self.complete(started)
        self.assertEqual(done["version"]["estado"], "disponible")
        self.assertNotEqual(nonces[0], nonces[1])
        self.assertEqual(self.rows("archivo_version", "id = ?",
                                   (started["version_id"],))[0]["clave_final"], nonces[1])

    def test_definite_store_failures_keep_their_retry_class_and_claim_no_cleanup(self):
        data = pdf_de(10)
        for name, failure, code, retry in (
                ("denied", FalloAlmacenError(reintentar=False), "almacen_no_disponible", False),
                ("unconfigured", AlmacenNoConfiguradoError(), "almacen_no_configurado", False)):
            with self.subTest(case=name):
                started = self.upload(data, key=name)
                self.store.inyectar_error("componer", failure)
                error = self.assert_code(code, lambda started=started: self.complete(started))
                self.assertEqual(error.detalle["reintentar"], retry)
                self.assertNotIn("limpieza_pendiente", error.detalle)
                self.assertEqual(self.finals(started), [])
                self.assertEqual(self.complete(started)["version"]["estado"], "disponible")

    # -- downloads -------------------------------------------------------------------

    def test_each_slice_verifies_the_whole_object_and_returns_at_most_three_mib(self):
        data = pdf_de(8 * MiB + 5)
        started = self.start_big(data)
        self.all_parts(started, data)
        self.complete(started)
        with patch.object(self.store, "leer", wraps=self.store.leer) as leer:
            self.assertEqual(self.download_all(started["version_id"]), data)
        self.assertEqual(leer.call_count, 3)                  # one whole read per slice
        first = archivos.descargar(self.sessions["olga"], started["version_id"], self.store,
                                   bd=self.database)
        self.assertEqual((first["tamano"], first["sha256"], first["siguiente"]),
                         (len(data), hashlib.sha256(data).hexdigest(), PARTE))
        for desde in (-1, 1, PARTE + 1, 3 * PARTE, 10 * PARTE, True, "0"):
            with self.subTest(desde=desde):
                self.assert_code("desplazamiento_invalido", lambda desde=desde: archivos.descargar(
                    self.sessions["ana"], started["version_id"], self.store, desde=desde,
                    bd=self.database))

    def test_corrupt_or_missing_final_bytes_return_nothing(self):
        data = pdf_de(4 * MiB)
        started = self.start_big(data)
        self.all_parts(started, data)
        self.complete(started)
        final = self.rows("archivo_version", "id = ?", (started["version_id"],))[0]["clave_final"]
        corrupted = bytearray(data)
        corrupted[-1] ^= 1
        with self.store._candado:
            self.store._objetos[final] = (bytes(corrupted), 0.0)
        for desde in (0, PARTE):
            self.assert_code("objeto_final_inconsistente", lambda desde=desde: archivos.descargar(
                self.sessions["ana"], started["version_id"], self.store, desde=desde,
                bd=self.database))
        with self.store._candado:
            self.store._objetos[final] = (data + b"x", 0.0)
        self.assert_code("objeto_final_inconsistente", lambda: archivos.descargar(
            self.sessions["ana"], started["version_id"], self.store, bd=self.database))
        self.store.perder(final)
        self.assert_code("contenido_no_disponible", lambda: archivos.descargar(
            self.sessions["ana"], started["version_id"], self.store, bd=self.database))

    # -- precedence: the application decides before any store is resolved --------------

    def test_out_of_scope_requests_never_reach_an_unavailable_store(self):
        data = pdf_de(10)
        done = self.upload(data, key="hecho")
        self.complete(done)
        pending = self.upload(data, key="pendiente")
        calls = []

        def unavailable():
            calls.append(1)
            raise FalloAlmacenError()
        outsider = "beto"     # an administrator who is not the initiator of these uploads
        for name, call, code in (
                ("part", lambda: archivos.escribir_temporal(
                    self.sessions["olga"], pending["version_id"], [data], unavailable,
                    bd=self.database, reloj=self.clock), "not_found"),
                ("part-not-owner", lambda: archivos.escribir_temporal(
                    self.sessions[outsider], pending["version_id"], [data], unavailable,
                    bd=self.database, reloj=self.clock), "not_found"),
                ("complete", lambda: archivos.completar(
                    self.sessions["olga"], pending["version_id"], unavailable,
                    bd=self.database, reloj=self.clock), "not_found"),
                ("download", lambda: archivos.descargar(
                    self.sessions["omar"], done["version_id"], unavailable, bd=self.database),
                 "not_found"),
                ("download-bad-offset", lambda: archivos.descargar(
                    self.sessions["ana"], done["version_id"], unavailable, desde=7,
                    bd=self.database), "desplazamiento_invalido"),
                ("process", lambda: archivos.reprocesar(
                    self.sessions["omar"], done["version_id"], unavailable,
                    idempotency_key="p-1", bd=self.database, reloj=self.clock), "not_found"),
                ("missing-version", lambda: archivos.descargar(
                    self.sessions["ana"], str(uuid.uuid4()), unavailable, bd=self.database),
                 "not_found")):
            with self.subTest(case=name):
                self.assert_code(code, call)
        self.assertEqual(calls, [])
        # In scope, the same store failure is the answer.
        error = self.assert_code("almacen_no_disponible", lambda: archivos.descargar(
            self.sessions["ana"], done["version_id"], unavailable, bd=self.database))
        self.assertEqual(error.status, 503)
        self.assertEqual(len(calls), 1)
        # Cancelling needs no store: it succeeds and reports cleanup as pending.
        cancelled = archivos.cancelar(self.sessions["ana"], pending["version_id"], unavailable,
                                      bd=self.database, reloj=self.clock)
        self.assertTrue(cancelled["limpieza_pendiente"])


class TransferSQLite(TransferChecks, unittest.TestCase):
    def prepare_database(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "m1.db"


@unittest.skipUnless(base.URL, "No Postgres test connection configured")
class TransferPostgres(TransferChecks, unittest.TestCase):
    setUpClass = base.AttachmentLifecyclePostgres.setUpClass
    tearDownClass = base.AttachmentLifecyclePostgres.tearDownClass
    prepare_database = base.AttachmentLifecyclePostgres.prepare_database


class LocalDiskComposition(unittest.TestCase):
    """componer on the local filesystem store: pinning, collisions, limits."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = AlmacenLocal(self.dir.name)
        self.addCleanup(self.store.close)

    def test_compose_pins_sources_and_publishes_create_only(self):
        self.store.guardar_temporal("temporal/a-00", [b"uno-"], 100)
        self.store.guardar_temporal("temporal/a-01", [b"dos"], 100)
        real = AlmacenLocal._copiar_en

        def restage_mid_compose(this, fuentes, directorio, nombre, limite):
            this.guardar_temporal("temporal/a-00", [b"OTRO"], 100)      # after pinning
            return real(this, fuentes, directorio, nombre, limite)
        with patch.object(AlmacenLocal, "_copiar_en", restage_mid_compose):
            self.assertEqual(self.store.componer(["temporal/a-00", "temporal/a-01"],
                                                 "final/v/n1", 100), 7)
        self.assertEqual(b"".join(self.store.leer("final/v/n1", 100)), b"uno-dos")
        with self.assertRaises(ColisionError):
            self.store.componer(["temporal/a-01"], "final/v/n1", 100)
        self.assertEqual(b"".join(self.store.leer("final/v/n1", 100)), b"uno-dos")
        with self.assertRaises(ObjetoAusenteError) as caught:
            self.store.componer(["temporal/a-00", "temporal/zz-01", "temporal/zz-02"],
                                "final/v/n2", 100)
        self.assertEqual(caught.exception.claves, ("temporal/zz-01", "temporal/zz-02"))
        with self.assertRaises(LimiteExcedidoError):
            self.store.componer(["temporal/a-00", "temporal/a-01"], "final/v/n3", 5)
        self.assertIsNone(self.store.tamano_de("final/v/n2"))
        self.assertIsNone(self.store.tamano_de("final/v/n3"))
        for bad in ([], ["final/v/n1"], "temporal/a-00", ["temporal/a-00"] * 65):
            with self.subTest(origenes=bad), self.assertRaises((ValueError, TypeError, Exception)):
                self.store.componer(bad, "final/v/n4", 100)

    def test_memory_store_matches(self):
        memoria = AlmacenEnMemoria()
        memoria.guardar_temporal("temporal/a-00", [b"uno-"], 100)
        memoria.guardar_temporal("temporal/a-01", [b"dos"], 100)
        self.assertEqual(memoria.componer(["temporal/a-00", "temporal/a-01"], "final/v/n1", 100), 7)
        with self.assertRaises(ColisionError):
            memoria.componer(["temporal/a-00"], "final/v/n1", 100)
        with self.assertRaises(ObjetoAusenteError) as caught:
            memoria.componer(["temporal/a-00", "temporal/b-00"], "final/v/n2", 100)
        self.assertEqual(caught.exception.claves, ("temporal/b-00",))


if __name__ == "__main__":
    os.environ.setdefault("ARA_MAP_NO_BROWSER", "1")
    unittest.main()

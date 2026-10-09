"""Attachment lifecycle behavior over real sessions, SQL, storage and parser."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import threading
import unittest
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from server import archivos, auth, db, postgres
from server.almacen import AlmacenEnMemoria, AlmacenLocal
from server.errors import ApiError
from server.repo import maestra
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
FIXTURES = Path(__file__).parent / "fixtures"
PDF = (FIXTURES / "archivos" / "ficticio.pdf").read_bytes()


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
        self.lock = threading.Lock()

    def __call__(self) -> datetime:
        with self.lock:
            return self.value

    def advance(self, seconds: int) -> None:
        with self.lock:
            self.value += timedelta(seconds=seconds)


def kmz(name: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", (FIXTURES / "kmz" / f"{name}.kml").read_bytes())
    return output.getvalue()


class LifecycleChecks:
    database: Path | None = None

    def setUp(self) -> None:
        self.prepare_database()
        self.clock = Clock()
        self.store = AlmacenEnMemoria()
        with db.session(self.database) as conn:
            self.users = {
                login: auth.create_user(
                    conn, login, f"{login.capitalize()} Ficticia", TEST_PASSWORD,
                    iterations=1000, rol=role)
                for login, role in (("ana", "admin"), ("beto", "admin"),
                                    ("olga", "operador"), ("omar", "operador"))
            }
            self.sessions = {}
            for login in self.users:
                token, _, _ = auth.login(conn, login, TEST_PASSWORD)
                self.sessions[login] = auth.sesion_de_token(conn, token)
            self.base = maestra.crear(conn, "Base Ficticia", self.users["ana"])["id"]
            conn.execute(
                "INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                " VALUES (?, ?, ?, ?)",
                (self.base, self.users["olga"]["id"], db.now(), self.users["ana"]["id"]))
            self.terrain = self._terrain(conn, self.base)
            self.other_terrain = self._terrain(conn, None)
            row = conn.execute("SELECT version, updated_at, updated_by FROM inventory_terrain"
                               " WHERE id = ?", (self.terrain,)).fetchone()
            self.terrain_stamp = tuple(row)

    def prepare_database(self) -> None:
        raise NotImplementedError

    def _terrain(self, conn, base_id):
        terrain_id = str(uuid.uuid4())
        now = db.now()
        conn.execute(
            "INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
            " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
            (terrain_id, base_id, now, self.users["ana"]["id"], now,
             self.users["ana"]["id"]))
        return terrain_id

    def rows(self, table: str, where: str = "1=1", params=()):
        with db.session(self.database) as conn:
            return [dict(row) for row in conn.execute(
                f"SELECT * FROM {table} WHERE {where}", params).fetchall()]

    def start(self, data: bytes, kind: str = "pdf", terrain: str | None = None,
              user: str = "ana", key: str | None = None, name: str | None = None):
        return archivos.iniciar(
            self.sessions[user], terrain or self.terrain, tipo=kind,
            nombre_original=name or f"ficticio.{kind}", tamano_declarado=len(data),
            sha256_declarado=hashlib.sha256(data).hexdigest(),
            idempotency_key=key or str(uuid.uuid4()), bd=self.database, reloj=self.clock)

    def upload(self, data: bytes, kind: str = "pdf", terrain: str | None = None,
               user: str = "ana", key: str | None = None, name: str | None = None):
        started = self.start(data, kind, terrain, user, key, name)
        archivos.escribir_temporal(self.sessions[user], started["version_id"],
                                   [data], self.store, bd=self.database, reloj=self.clock)
        return started

    def complete(self, started, user: str = "ana", **kwargs):
        return archivos.completar(self.sessions[user], started["version_id"], self.store,
                                  bd=self.database, reloj=self.clock, **kwargs)

    def assert_code(self, code: str, call) -> ApiError:
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual(caught.exception.detalle["code"], code)
        return caught.exception

    def assert_terrain_untouched(self) -> None:
        with db.session(self.database) as conn:
            row = conn.execute("SELECT version, updated_at, updated_by FROM inventory_terrain"
                               " WHERE id = ?", (self.terrain,)).fetchone()
        self.assertEqual(tuple(row), self.terrain_stamp)

    def test_pdf_happy_path_replay_audit_and_terrain_stability(self):
        started = self.upload(PDF)
        result = self.complete(started)
        replay = self.complete(started)
        self.assertTrue(result["aplicada"])
        self.assertFalse(result["replay"])
        self.assertTrue(replay["replay"])
        self.assertEqual(result["version"]["sha256"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(replay["version"]["id"], result["version"]["id"])
        self.assertEqual(len(self.rows("archivo_version")), 1)
        self.assertEqual([r["accion"] for r in self.rows("archivo_evento")],
                         ["subida_iniciada", "version_disponible", "version_actual_cambiada"])
        serialized = repr(result) + repr(self.rows("archivo_evento"))
        self.assertNotIn("temporal/", serialized)
        self.assertNotIn("final/", serialized)
        self.assertNotIn(self.sessions["ana"].referencia, serialized)
        self.assert_terrain_untouched()

    def test_real_single_candidate_kmz_commits_mutual_rows_and_activates(self):
        started = self.upload(kmz("poligono_con_hueco"), "kmz")
        result = self.complete(started)
        attempt = self.rows("archivo_intento")[0]
        geometry = self.rows("geometria")[0]
        self.assertEqual(attempt["resultado"], "listo")
        self.assertEqual(attempt["geometria_id"], geometry["id"])
        self.assertEqual(geometry["intento_id"], attempt["id"])
        self.assertTrue(result["aplicada"])
        self.assertEqual(result["archivo"]["geometria_activa_id"], geometry["id"])
        self.assertGreater(geometry["huecos"], 0)
        self.assert_terrain_untouched()

    def test_ambiguous_kmz_selection_then_explicit_activation(self):
        started = self.upload(kmz("ambiguo_tres_lotes"), "kmz")
        completed = self.complete(started)
        self.assertEqual(completed["intento"]["resultado"], "requiere_seleccion")
        self.assertFalse(completed["aplicada"])
        selected = archivos.reprocesar(
            self.sessions["ana"], started["version_id"], self.store, seleccion=[1],
            idempotency_key="seleccion-1", bd=self.database, reloj=self.clock)
        replay = archivos.reprocesar(
            self.sessions["ana"], started["version_id"], self.store, seleccion=[1],
            idempotency_key="seleccion-1", bd=self.database, reloj=self.clock)
        self.assertTrue(replay["replay"])
        activated = archivos.activar(
            self.sessions["ana"], started["archivo_id"], version_id=started["version_id"],
            geometria_id=selected["geometria_id"], expected_revision=1,
            idempotency_key="activar-1", bd=self.database, reloj=self.clock)
        self.assertEqual(activated["archivo"]["geometria_activa_id"],
                         selected["geometria_id"])
        self.assertEqual(len(self.rows("archivo_intento")), 2)

    def test_changed_idempotent_start_conflicts_and_actor_scope_is_private(self):
        first = self.start(PDF, key="misma-clave")
        replay = self.start(PDF, key="misma-clave")
        self.assertEqual(first, replay)
        self.assert_code("idempotencia_conflictiva", lambda: archivos.iniciar(
            self.sessions["ana"], self.terrain, tipo="pdf", nombre_original="otro.pdf",
            tamano_declarado=len(PDF), sha256_declarado=hashlib.sha256(PDF).hexdigest(),
            idempotency_key="misma-clave", bd=self.database, reloj=self.clock))
        other = self.start(PDF, user="olga", key="misma-clave")
        self.assertNotEqual(first["version_id"], other["version_id"])

    def test_pending_limit_counts_effective_uploads_and_equality_expires(self):
        starts = [self.start(PDF, key=f"pending-{n}") for n in range(5)]
        self.assert_code("limite_pendientes", lambda: self.start(PDF, key="pending-6"))
        self.clock.advance(archivos.COMPLETE_SECONDS)
        sixth = self.start(PDF, key="pending-after-expiry")
        self.assertTrue(sixth["version_id"])
        self.assert_code("subida_expirada", lambda: self.complete(starts[0]))
        row = self.rows("archivo_version", "id = ?", (starts[0]["version_id"],))[0]
        self.assertEqual(row["estado"], "expirado")

    def test_verification_failure_is_terminal_and_storage_failure_is_retryable(self):
        bad = self.start(PDF)
        altered = PDF + b"x"
        archivos.escribir_temporal(self.sessions["ana"], bad["version_id"], [altered],
                                   self.store, bd=self.database, reloj=self.clock)
        failed = self.complete(bad)
        self.assertEqual(failed["version"]["estado"], "fallido")
        self.assertEqual(failed["version"]["error"]["codigo"], "tamano_no_coincide")
        retry = self.upload(PDF)
        self.store.inyectar_falla("copiar")
        self.assert_code("almacen_no_disponible", lambda: self.complete(retry))
        self.assertEqual(self.rows("archivo_version", "id = ?", (retry["version_id"],))[0]["estado"],
                         "subiendo")
        self.assertEqual(self.complete(retry)["version"]["estado"], "disponible")

    def test_input_boundaries_names_magic_rejection_and_oversized_chunk(self):
        digest = hashlib.sha256(b"").hexdigest()
        for kind, maximum in (("pdf", archivos.PDF_MAX), ("kmz", archivos.KMZ_MAX)):
            accepted = archivos.iniciar(
                self.sessions["ana"], self.terrain, tipo=kind,
                nombre_original=f"limite.{kind}", tamano_declarado=maximum,
                sha256_declarado=digest, idempotency_key=f"exact-{kind}",
                bd=self.database, reloj=self.clock)
            self.assertTrue(accepted["version_id"])
            self.assert_code("tamano_invalido", lambda kind=kind, maximum=maximum: archivos.iniciar(
                self.sessions["ana"], self.terrain, tipo=kind,
                nombre_original=f"exceso.{kind}", tamano_declarado=maximum + 1,
                sha256_declarado=digest, idempotency_key=f"over-{kind}",
                bd=self.database, reloj=self.clock))
        for name in ("", "../escape.pdf", "carpeta/archivo.pdf", "malo\x00.pdf"):
            self.assert_code("nombre_invalido", lambda name=name: archivos.iniciar(
                self.sessions["ana"], self.terrain, tipo="pdf", nombre_original=name,
                tamano_declarado=0, sha256_declarado=digest,
                idempotency_key=str(uuid.uuid4()), bd=self.database, reloj=self.clock))
        pending = self.start(PDF)
        self.assert_code("bloque_invalido", lambda: archivos.escribir_temporal(
            self.sessions["ana"], pending["version_id"], [b"x" * (1024 * 1024 + 1)],
            self.store, bd=self.database, reloj=self.clock))
        wrong = b"not-a-pdf"
        bad = self.upload(wrong)
        self.assertEqual(self.complete(bad)["version"]["error"]["codigo"], "firma_invalida")
        rejected = self.upload(kmz("solo_lineas"), "kmz")
        parsed = self.complete(rejected)
        self.assertEqual(parsed["version"]["estado"], "disponible")
        self.assertEqual(parsed["intento"]["resultado"], "rechazado")

    def test_initiator_only_completion_missing_ids_and_archived_policy(self):
        pending = self.upload(PDF, user="olga")
        denied = self.assert_code("not_found", lambda: self.complete(pending, user="ana"))
        self.assertEqual(denied.status, 404)
        self.assertEqual(self.complete(pending, user="olga")["version"]["estado"], "disponible")
        missing = str(uuid.uuid4())
        self.assertEqual(self.assert_code("not_found", lambda: archivos.completar(
            self.sessions["ana"], missing, self.store,
            bd=self.database, reloj=self.clock)).status, 404)
        with db.escritura(self.database) as conn:
            conn.execute("UPDATE inventory_terrain SET archived_at = ? WHERE id = ?",
                         (db.now(), self.terrain))
        self.assertTrue(archivos.listar(self.sessions["ana"], self.terrain,
                                       bd=self.database, reloj=self.clock))
        self.assert_code("terreno_archivado", lambda: self.start(PDF, key="archived"))

    def test_rejected_replacement_and_stale_parallel_completion_preserve_layout(self):
        initial = self.upload(kmz("poligono_simple"), "kmz")
        active = self.complete(initial)
        active_geometry = active["archivo"]["geometria_activa_id"]
        rejected = self.upload(kmz("solo_lineas"), "kmz", key="rejected")
        rejected_result = self.complete(rejected)
        self.assertFalse(rejected_result["aplicada"])
        self.assertEqual(rejected_result["archivo"]["geometria_activa_id"], active_geometry)
        first = self.upload(kmz("multiparte"), "kmz", key="parallel-1")
        second = self.upload(kmz("poligono_con_hueco"), "kmz", key="parallel-2")
        winner = self.complete(first)
        loser = self.complete(second)
        self.assertTrue(winner["aplicada"])
        self.assertFalse(loser["aplicada"])
        self.assertEqual(loser["motivo_no_aplicada"], "superada")
        self.assertEqual(loser["archivo"]["geometria_activa_id"],
                         winner["archivo"]["geometria_activa_id"])

    def test_cross_version_geometry_and_stale_revision_cannot_activate(self):
        one = self.upload(kmz("ambiguo_tres_lotes"), "kmz", key="one")
        self.complete(one)
        selected_one = archivos.reprocesar(
            self.sessions["ana"], one["version_id"], self.store, seleccion=[0],
            idempotency_key="select-one", bd=self.database, reloj=self.clock)
        two = self.upload(kmz("ambiguo_tres_lotes"), "kmz", key="two")
        self.complete(two)
        selected_two = archivos.reprocesar(
            self.sessions["ana"], two["version_id"], self.store, seleccion=[1],
            idempotency_key="select-two", bd=self.database, reloj=self.clock)
        self.assert_code("version_no_activable", lambda: archivos.activar(
            self.sessions["ana"], one["archivo_id"], version_id=one["version_id"],
            geometria_id=selected_two["geometria_id"], expected_revision=1,
            idempotency_key="cross", bd=self.database, reloj=self.clock))
        archivos.activar(
            self.sessions["ana"], one["archivo_id"], version_id=one["version_id"],
            geometria_id=selected_one["geometria_id"], expected_revision=1,
            idempotency_key="valid", bd=self.database, reloj=self.clock)
        self.assert_code("revision_conflictiva", lambda: archivos.activar(
            self.sessions["ana"], one["archivo_id"], version_id=two["version_id"],
            geometria_id=selected_two["geometria_id"], expected_revision=1,
            idempotency_key="stale", bd=self.database, reloj=self.clock))

    def test_read_only_expiry_projection_does_not_write(self):
        pending = self.start(PDF)
        events_before = len(self.rows("archivo_evento"))
        self.clock.advance(archivos.COMPLETE_SECONDS)
        listing = archivos.listar(self.sessions["ana"], self.terrain,
                                   bd=self.database, reloj=self.clock)
        item = next(row for row in listing if row["id"] == pending["archivo_id"])
        self.assertEqual(item["ultima_version"]["estado"], "expirado")
        self.assertEqual(self.rows("archivo_version", "id = ?", (pending["version_id"],))[0]["estado"],
                         "subiendo")
        self.assertEqual(len(self.rows("archivo_evento")), events_before)

    def test_uncertain_commit_never_deletes_a_referenced_final(self):
        started = self.upload(PDF)
        real = db.escritura
        calls = {"count": 0}

        @contextmanager
        def uncertain(path=None):
            calls["count"] += 1
            with real(path) as conn:
                yield conn
            if calls["count"] == 2:
                raise RuntimeError("fictional acknowledgement loss")

        with patch.object(db, "escritura", uncertain):  # noqa: SIM117 -- Python 3.9
            with self.assertRaisesRegex(RuntimeError, "acknowledgement"):
                self.complete(started)
        version = self.rows("archivo_version", "id = ?", (started["version_id"],))[0]
        self.assertEqual(version["estado"], "disponible")
        self.assertIsNotNone(self.store.tamano_de(version["clave_final"]))
        self.assertEqual(len(list(self.store.listar("final/"))), 1)

    def test_slow_work_has_no_open_write_transaction(self):
        started = self.upload(PDF)
        observed = []

        class Hooks:
            def despues_copia(inner, _version):  # noqa: N805
                with db.escritura(self.database) as conn:
                    observed.append(conn.execute("SELECT COUNT(*) AS n FROM archivo").fetchone()["n"])

        self.complete(started, ganchos=Hooks())
        self.assertEqual(observed, [1])

    def test_live_lease_takeover_fences_late_holder_and_keeps_one_final(self):
        started = self.upload(PDF)
        copied = threading.Event()
        resume = threading.Event()
        errors = []

        class Hooks:
            def despues_copia(self, _version):
                copied.set()
                resume.wait(10)

        def old_holder():
            try:
                self.complete(started, ganchos=Hooks())
            except Exception as exc:  # asserted below
                errors.append(exc)

        thread = threading.Thread(target=old_holder)
        thread.start()
        self.assertTrue(copied.wait(10))
        self.clock.advance(archivos.LEASE_SECONDS)
        winner = self.complete(started)
        resume.set()
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(winner["version"]["estado"], "disponible")
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ApiError)
        self.assertEqual(errors[0].detalle["code"], "lease_perdido")
        self.assertEqual(len(list(self.store.listar("final/"))), 1)

    def test_lease_started_before_completion_deadline_may_finish_after_it(self):
        started = self.upload(PDF)
        self.clock.advance(archivos.COMPLETE_SECONDS - 1)

        class Hooks:
            def despues_copia(inner, _version):  # noqa: N805
                self.clock.advance(120)

        result = self.complete(started, ganchos=Hooks())
        self.assertEqual(result["version"]["estado"], "disponible")

    def test_scope_loss_before_final_transaction_writes_no_outcome(self):
        started = self.upload(PDF, user="olga")

        class Hooks:
            def antes_commit(inner, _version):  # noqa: N805
                with db.escritura(self.database) as conn:
                    conn.execute("UPDATE team_user SET active = 0 WHERE id = ?",
                                 (self.users["olga"]["id"],))

        error = self.assert_code("unauthenticated",
                                 lambda: self.complete(started, user="olga", ganchos=Hooks()))
        self.assertEqual(error.status, 401)
        version = self.rows("archivo_version", "id = ?", (started["version_id"],))[0]
        self.assertEqual(version["estado"], "subiendo")
        self.assertEqual(self.rows("archivo_intento"), [])
        self.assertEqual(len(list(self.store.listar("final/"))), 0)

    def test_every_slow_work_scope_change_is_rechecked_before_finalization(self):
        cases = ("grant", "transfer", "terrain_archive", "base_archive", "deactivate",
                 "role", "logout", "credential", "session_expiry")
        for index, change in enumerate(cases):
            with self.subTest(change=change):
                login = f"scope{index}"
                with db.session(self.database) as conn:
                    user = auth.create_user(
                        conn, login, f"Scope {index} Ficticia", TEST_PASSWORD,
                        iterations=1000, rol="operador")
                    token, _, _ = auth.login(conn, login, TEST_PASSWORD)
                    session = auth.sesion_de_token(conn, token)
                    base = maestra.crear(conn, f"Base Scope {index}", self.users["ana"])["id"]
                    conn.execute(
                        "INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                        " VALUES (?, ?, ?, ?)",
                        (base, user["id"], db.now(), self.users["ana"]["id"]))
                    terrain = self._terrain(conn, base)
                    target = maestra.crear(conn, f"Destino {index}", self.users["ana"])["id"]
                started = archivos.iniciar(
                    session, terrain, tipo="pdf", nombre_original=f"scope-{index}.pdf",
                    tamano_declarado=len(PDF), sha256_declarado=hashlib.sha256(PDF).hexdigest(),
                    idempotency_key=f"scope-{index}", bd=self.database, reloj=self.clock)
                archivos.escribir_temporal(session, started["version_id"], [PDF], self.store,
                                           bd=self.database, reloj=self.clock)

                def mutate(change=change, base=base, user_id=user["id"], terrain=terrain,
                           target=target, session_ref=session.referencia):
                    with db.escritura(self.database) as conn:
                        if change == "grant":
                            conn.execute("DELETE FROM maestra_base_acceso"
                                         " WHERE base_id = ? AND user_id = ?", (base, user_id))
                        elif change == "transfer":
                            conn.execute("UPDATE inventory_terrain SET base_id = ? WHERE id = ?",
                                         (target, terrain))
                        elif change == "terrain_archive":
                            conn.execute("UPDATE inventory_terrain SET archived_at = ? WHERE id = ?",
                                         (db.now(), terrain))
                        elif change == "base_archive":
                            conn.execute("UPDATE maestra_base SET archived_at = ? WHERE id = ?",
                                         (db.now(), base))
                        elif change == "deactivate":
                            conn.execute("UPDATE team_user SET active = 0 WHERE id = ?", (user_id,))
                        elif change == "role":
                            conn.execute("UPDATE team_user SET rol = 'admin', credential_revision ="
                                         " credential_revision + 1 WHERE id = ?", (user_id,))
                        elif change == "logout":
                            conn.execute("UPDATE team_session SET revoked_at = ?"
                                         " WHERE token_hash = ?", (db.now(), session_ref))
                        elif change == "credential":
                            conn.execute("UPDATE team_user SET credential_revision ="
                                         " credential_revision + 1 WHERE id = ?", (user_id,))
                        else:
                            conn.execute("UPDATE team_session SET expires_at = 0"
                                         " WHERE token_hash = ?", (session_ref,))

                class Hooks:
                    def antes_commit(inner, _version):  # noqa: N805
                        mutate()

                with self.assertRaises(ApiError) as caught:
                    archivos.completar(session, started["version_id"], self.store,
                                       bd=self.database, reloj=self.clock, ganchos=Hooks())
                expected = {"terrain_archive": "terreno_archivado"}.get(
                    change, "not_found" if change in ("grant", "transfer", "base_archive")
                    else "unauthenticated")
                self.assertEqual(caught.exception.detalle["code"], expected)
                version = self.rows("archivo_version", "id = ?", (started["version_id"],))[0]
                self.assertEqual(version["estado"], "subiendo")
                self.assertEqual(self.rows("archivo_intento", "archivo_version_id = ?",
                                           (started["version_id"],)), [])
        self.assertEqual(len(list(self.store.listar("final/"))), 0)

    def test_cancel_and_retire_do_not_delete_final_history_or_resurrect(self):
        pending = self.upload(PDF, user="olga")
        cancelled = archivos.cancelar(
            self.sessions["beto"], pending["version_id"], self.store,
            bd=self.database, reloj=self.clock)
        self.assertEqual(cancelled["estado"], "cancelado")
        done = self.upload(kmz("poligono_simple"), "kmz")
        completed = self.complete(done)
        final_key = self.rows("archivo_version", "id = ?", (done["version_id"],))[0]["clave_final"]
        retired = archivos.retirar(
            self.sessions["ana"], done["archivo_id"], expected_revision=2,
            idempotency_key="retirar-1", almacen=self.store,
            bd=self.database, reloj=self.clock)
        self.assertIsNotNone(retired["archivo"]["retirado_en"])
        self.assertIsNone(retired["archivo"]["version_actual_id"])
        self.assertIsNotNone(self.store.tamano_de(final_key))
        replacement = self.start(kmz("poligono_simple"), "kmz", key="new-kmz")
        self.assertNotEqual(replacement["archivo_id"], done["archivo_id"])
        self.assertEqual(completed["version"]["estado"], "disponible")

    def test_other_callers_see_generic_pending_summary_only(self):
        started = self.start(PDF, user="ana", name="secreto-ficticio.pdf")
        listing = archivos.listar(self.sessions["olga"], self.terrain,
                                   bd=self.database, reloj=self.clock)
        self.assertEqual(listing[0]["ultima_version"], {"estado": "subiendo", "propia": False})
        with db.session(self.database) as conn:
            summary = archivos.resumenes_de_archivos(
                conn, [self.terrain, self.other_terrain, str(uuid.uuid4())],
                self.sessions["olga"], reloj=self.clock)
        self.assertEqual(summary["resultados"][self.terrain]["pdf_recientes"][0]["ultima_version"],
                         {"estado": "subiendo", "propia": False})
        self.assertEqual(len(summary["no_disponibles"]), 2)
        self.assertNotIn("secreto-ficticio", repr(summary))
        self.assertTrue(started["version_id"])

    def test_history_is_bounded_and_cursor_stable(self):
        completed = self.complete(self.upload(PDF))
        first = archivos.historial(self.sessions["ana"], completed["archivo"]["id"],
                                   limite=2, bd=self.database)
        self.assertEqual(len(first["eventos"]), 2)
        self.assertIsNotNone(first["cursor_siguiente"])
        second = archivos.historial(
            self.sessions["ana"], completed["archivo"]["id"],
            cursor=first["cursor_siguiente"], limite=2, bd=self.database)
        self.assertTrue(second["eventos"])
        self.assertFalse({e["id"] for e in first["eventos"]}
                         & {e["id"] for e in second["eventos"]})
        self.assert_code("limite_invalido", lambda: archivos.historial(
            self.sessions["ana"], completed["archivo"]["id"], limite=101,
            bd=self.database))

    def test_local_storage_backend_runs_the_same_pdf_lifecycle(self):
        with tempfile.TemporaryDirectory() as root, AlmacenLocal(root) as local:
            started = self.start(PDF)
            archivos.escribir_temporal(self.sessions["ana"], started["version_id"],
                                       [PDF], local, bd=self.database, reloj=self.clock)
            result = archivos.completar(self.sessions["ana"], started["version_id"], local,
                                        bd=self.database, reloj=self.clock)
            self.assertEqual(result["version"]["estado"], "disponible")
            self.assertEqual(len(list(local.listar("final/"))), 1)


class AttachmentLifecycleSQLite(LifecycleChecks, unittest.TestCase):
    def prepare_database(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "attachments.db"


@unittest.skipUnless(URL, "No Postgres test connection configured")
class AttachmentLifecyclePostgres(LifecycleChecks, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import psycopg
        from psycopg.conninfo import make_conninfo

        cls.schema = "test_ara_archivos_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.environment = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.environment.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

    @classmethod
    def tearDownClass(cls) -> None:
        import psycopg

        cls.environment.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def prepare_database(self) -> None:
        self.database = None
        with postgres.session() as conn:
            rows = conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
                " AND tablename <> 'workspace_metadata'").fetchall()
            names = [row["tablename"] for row in rows]
            if names:
                conn.raw.execute("TRUNCATE " + ", ".join(f'"{name}"' for name in names)
                                 + " RESTART IDENTITY CASCADE")


if __name__ == "__main__":
    unittest.main()

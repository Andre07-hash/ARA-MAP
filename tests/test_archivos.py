"""Attachment lifecycle behavior over real sessions, SQL, storage and parser."""

from __future__ import annotations

import copy
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
from types import SimpleNamespace
from unittest.mock import Mock, patch

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


def leaves(value, path="$"):
    """Every scalar of a JSON-like value, with its path."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from leaves(item, f"{path}[{index}]")
    else:
        yield path, value


def leaked_paths(value, texts, numbers):
    """Paths whose value carries hidden metadata.

    Distinctive strings (file name, UUIDs, display name) are searched inside
    every string. A number (a byte count) matches only a whole value, as a
    number or as its decimal text: the same digits inside a public UUID or a
    timestamp are not a leak.
    """
    as_text = {str(number) for number in numbers}
    found = []
    for path, leaf in leaves(value):
        if isinstance(leaf, str):
            if leaf in as_text or any(text in leaf for text in texts):
                found.append(path)
        elif isinstance(leaf, (int, float)) and not isinstance(leaf, bool) and leaf in numbers:
            found.append(path)
    return found


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
                                       bd=self.database, reloj=self.clock)["archivos"])
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
                                   bd=self.database, reloj=self.clock)["archivos"]
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
                                   bd=self.database, reloj=self.clock)["archivos"]
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

    # -- supervisory corrections L1-L6 (2026-10-08 review) -------------------

    def snapshot(self):
        tables = ("archivo", "archivo_version", "archivo_intento", "geometria",
                  "archivo_evento", "archivo_trabajo", "inventory_operation_result")
        return {table: sorted(repr(sorted(row.items())) for row in self.rows(table))
                for table in tables}

    def failure(self, call):
        with self.assertRaises(ApiError) as caught:
            call()
        return (caught.exception.status, caught.exception.mensaje, caught.exception.detalle)

    def completed_pdf(self, user="ana", terrain=None, name=None):
        started = self.upload(PDF, user=user, terrain=terrain, name=name)
        self.complete(started, user=user)
        return started

    def test_l1_missing_and_out_of_scope_resources_are_one_result(self):
        hidden = self.completed_pdf(terrain=self.other_terrain)
        hidden_pending = self.upload(PDF, terrain=self.other_terrain)
        missing = str(uuid.uuid4())
        olga = self.sessions["olga"]
        operations = {
            "escribir_temporal": lambda v, a: archivos.escribir_temporal(
                olga, v, [PDF], self.store, bd=self.database, reloj=self.clock),
            "completar": lambda v, a: archivos.completar(
                olga, v, self.store, bd=self.database, reloj=self.clock),
            "cancelar": lambda v, a: archivos.cancelar(
                olga, v, self.store, bd=self.database, reloj=self.clock),
            "reprocesar": lambda v, a: archivos.reprocesar(
                olga, v, self.store, idempotency_key="k", bd=self.database, reloj=self.clock),
            "activar": lambda v, a: archivos.activar(
                olga, a, version_id=v, expected_revision=2, idempotency_key="k",
                bd=self.database, reloj=self.clock),
            "retirar": lambda v, a: archivos.retirar(
                olga, a, expected_revision=2, idempotency_key="k", almacen=self.store,
                bd=self.database, reloj=self.clock),
            "historial": lambda v, a: archivos.historial(olga, a, bd=self.database),
        }
        before = self.snapshot()
        expected = (404, "El archivo no existe.", {"code": "not_found"})
        for name, call in operations.items():
            with self.subTest(operation=name):
                target = hidden_pending if name in ("escribir_temporal", "cancelar") else hidden
                for version, attachment in ((missing, missing), (None, None),
                                            (target["version_id"], target["archivo_id"])):
                    self.assertEqual(self.failure(
                        lambda c=call, v=version, a=attachment: c(v, a)), expected)
        self.assertEqual(self.snapshot(), before)
        # Real 401 handling stays first: a revoked session learns nothing.
        with db.escritura(self.database) as conn:
            conn.execute("UPDATE team_session SET revoked_at = ? WHERE token_hash = ?",
                         (db.now(), olga.referencia))
        own = self.completed_pdf()
        for name, call in operations.items():
            with self.subTest(revoked=name):
                for version, attachment in ((missing, missing),
                                            (hidden["version_id"], hidden["archivo_id"]),
                                            (own["version_id"], own["archivo_id"])):
                    self.assertEqual(self.failure(
                        lambda c=call, v=version, a=attachment: c(v, a))[0], 401)

    def test_l1_activation_resolves_version_ownership_before_any_lease(self):
        own = self.completed_pdf(user="olga")
        sibling = self.completed_pdf(user="olga", name="hermano-ficticio.pdf")
        hidden = self.upload(PDF, terrain=self.other_terrain)
        self.clock.advance(900)

        def activate(version_id):
            return archivos.activar(self.sessions["olga"], own["archivo_id"],
                                    version_id=version_id, expected_revision=2,
                                    idempotency_key=str(uuid.uuid4()),
                                    bd=self.database, reloj=self.clock)

        expected = (404, "El archivo no existe.", {"code": "not_found"})
        observed = []

        def probe(_version):
            before = self.snapshot()
            for target in (hidden["version_id"], sibling["version_id"], str(uuid.uuid4())):
                observed.append(self.failure(lambda target=target: activate(target)))
            self.assertEqual(self.snapshot(), before)

        # Foreign and sibling versions while each holds a live lease.
        self.complete(hidden, ganchos=SimpleNamespace(despues_lease=probe))
        archivos.activar(self.sessions["olga"], sibling["archivo_id"],
                         version_id=sibling["version_id"], expected_revision=2,
                         idempotency_key="sibling", bd=self.database, reloj=self.clock,
                         )
        with db.escritura(self.database) as conn:
            for version_id, expires in ((sibling["version_id"], "2999-01-01T00:00:00+00:00"),
                                        (hidden["version_id"], "2000-01-01T00:00:00+00:00")):
                conn.execute(
                    "INSERT INTO archivo_trabajo (archivo_version_id, trabajo_id, actor_id,"
                    " operacion, inicio, vence_en) VALUES (?, ?, ?, 'activar', ?, ?)",
                    (version_id, str(uuid.uuid4()), self.users["ana"]["id"],
                     "2000-01-01T00:00:00+00:00", expires))
        before = self.snapshot()
        for target in (hidden["version_id"], sibling["version_id"], str(uuid.uuid4())):
            observed.append(self.failure(lambda target=target: activate(target)))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(observed, [expected] * 6)
        # The caller's own available version still activates.
        self.assertEqual(activate(own["version_id"])["archivo"]["revision"], 3)

    # -- L2 pending privacy: the allowed projection, checked by structure --------------

    def pending_surfaces(self, user, pending):
        """(listing item, history events, summary row) as `user` reads them."""
        session = self.sessions[user]
        listing = archivos.listar(session, self.terrain, bd=self.database,
                                  reloj=self.clock)["archivos"]
        history = archivos.historial(session, pending["archivo_id"], bd=self.database,
                                     reloj=self.clock)["eventos"]
        with db.session(self.database) as conn:
            summary = archivos.resumenes_de_archivos(conn, [self.terrain], session,
                                                     reloj=self.clock)
        item = next(i for i in listing if i["id"] == pending["archivo_id"])
        cell = next(r for r in summary["resultados"][self.terrain]["pdf_recientes"]
                    if r["id"] == pending["archivo_id"])
        return item, history, cell

    def hidden_metadata(self, pending, name, data=PDF):
        """What another account must not learn about `pending` (texts, numbers)."""
        uploader = self.users["ana"]
        return ((name, pending["version_id"], uploader["id"], uploader["display_name"]),
                (len(data),))

    def assert_private_view(self, view, pending, state, hidden):
        """The exact redacted projection, and no hidden value anywhere in the view.

        History must equal the durable events projected field by field: only the
        event id, action and time stay public. Listing and summary carry the
        generic status alone. The leak search then covers every other field of
        the item, events and summary row.
        """
        item, events, cell = view
        generic = {"estado": state, "propia": False}
        durable = sorted(self.rows("archivo_evento", "archivo_id = ?", (pending["archivo_id"],)),
                         key=lambda row: (row["at"], row["id"]), reverse=True)
        self.assertTrue(durable)
        self.assertEqual({row["archivo_version_id"] for row in durable}, {pending["version_id"]})
        self.assertEqual(item["ultima_version"], generic)
        self.assertEqual(cell["ultima_version"], generic)
        self.assertEqual(events, [
            {"id": row["id"], "accion": row["accion"], "revision": None,
             "archivo_version_id": None, "intento_id": None, "geometria_id": None,
             "base_id": None, "actor": None, "at": row["at"], "details": {},
             "privado": True, "version": generic} for row in durable])
        self.assertEqual(leaked_paths(view, *hidden), [], "hidden metadata in the view")

    def test_l2_pending_privacy_is_one_rule_on_every_read_surface(self):
        secret = "privado-ficticio.pdf"
        pending = self.upload(PDF, name=secret)
        hidden = self.hidden_metadata(pending, secret)

        def assert_private(state):
            for user in ("olga", "beto"):  # another operator and another admin
                self.assert_private_view(self.pending_surfaces(user, pending), pending, state,
                                         hidden)
            item, history, cell = self.pending_surfaces("ana", pending)
            listed, summarized = item["ultima_version"], cell["ultima_version"]
            self.assertEqual(listed["estado"], state)
            self.assertEqual(listed["nombre_original"], secret)
            self.assertEqual(listed["tamano_declarado"], len(PDF))
            self.assertEqual(summarized["nombre_original"], secret)
            self.assertEqual(history[0]["details"]["nombre"], secret)
            self.assertEqual(history[0]["actor"]["id"], self.users["ana"]["id"])
            self.assertFalse(history[0]["privado"])

        assert_private("subiendo")
        self.clock.advance(archivos.COMPLETE_SECONDS - 1)
        assert_private("subiendo")
        self.clock.advance(1)          # equality is expired
        assert_private("expirado")
        self.clock.advance(60)
        assert_private("expirado")
        # The durable audit row is untouched; only the projection is redacted.
        stored = self.rows("archivo_evento", "archivo_version_id = ?", (pending["version_id"],))
        self.assertIn(secret, stored[0]["details_json"])

        # A live lease taken before the deadline reads as in progress, still private.
        live = self.upload(PDF, name=secret, key="live")
        self.clock.advance(archivos.COMPLETE_SECONDS - 1)

        def during_lease(_version):
            self.clock.advance(5)
            self.assert_private_view(self.pending_surfaces("olga", live), live, "subiendo",
                                     self.hidden_metadata(live, secret))

        self.complete(live, ganchos=SimpleNamespace(despues_copia=during_lease))

        # Across revocation and transfer: out of scope is absence; back in scope, private.
        target = self.base
        with db.session(self.database) as conn:
            closed = maestra.crear(conn, "Base Cerrada Ficticia", self.users["ana"])["id"]
        for change in ("revoke", "transfer"):
            with self.subTest(change=change), db.escritura(self.database) as conn:
                if change == "revoke":
                    conn.execute("DELETE FROM maestra_base_acceso WHERE base_id = ?"
                                 " AND user_id = ?", (target, self.users["olga"]["id"]))
                else:
                    conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id,"
                                 " granted_at, granted_by) VALUES (?, ?, ?, ?)",
                                 (target, self.users["olga"]["id"], db.now(),
                                  self.users["ana"]["id"]))
                    conn.execute("UPDATE inventory_terrain SET base_id = ? WHERE id = ?",
                                 (closed, self.terrain))
            with self.subTest(change=change):
                self.assert_code("not_found", lambda: archivos.listar(
                    self.sessions["olga"], self.terrain, bd=self.database, reloj=self.clock))
                self.assertEqual(self.failure(lambda: archivos.historial(
                    self.sessions["olga"], pending["archivo_id"], bd=self.database)),
                    (404, "El archivo no existe.", {"code": "not_found"}))
                with db.session(self.database) as conn:
                    summary = archivos.resumenes_de_archivos(
                        conn, [self.terrain], self.sessions["olga"], reloj=self.clock)
                self.assertEqual(summary["no_disponibles"], [self.terrain])
        with db.escritura(self.database) as conn:
            conn.execute("UPDATE inventory_terrain SET base_id = ? WHERE id = ?",
                         (target, self.terrain))
        assert_private("expirado")

    def test_l2_privacy_check_ignores_public_ids_that_contain_hidden_digits(self):
        # Deterministic collision (review R2-B2): every UUID made during the upload,
        # public event ids included, contains the hidden byte count.
        counter = iter(range(1, 1000))

        def collision():
            return uuid.UUID(f"{len(PDF):08d}-0000-4000-8000-{next(counter):012x}")

        secret = "privado-ficticio.pdf"
        with patch("uuid.uuid4", side_effect=collision):
            pending = self.upload(PDF, name=secret)
        view = self.pending_surfaces("olga", pending)
        public_ids = [event["id"] for event in view[1]]
        self.assertTrue(public_ids)
        self.assertTrue(all(str(len(PDF)) in event_id for event_id in public_ids))
        self.assertIn(str(len(PDF)), repr(view))      # the old substring rule failed here
        self.assert_private_view(view, pending, "subiendo", self.hidden_metadata(pending, secret))

    def test_l2_privacy_check_still_detects_real_leaks(self):
        """Negative controls: each injected leak fails, and for its own reason."""
        secret = "privado-ficticio.pdf"
        pending = self.upload(PDF, name=secret)
        hidden = self.hidden_metadata(pending, secret)
        clean = self.pending_surfaces("olga", pending)
        self.assert_private_view(clean, pending, "subiendo", hidden)    # control: passes
        ana = self.users["ana"]

        def leak(item, events, cell, *, where):
            if where == "version size":
                item["ultima_version"]["tamano"] = len(PDF)
            elif where == "item size text":
                item["tamano"] = str(len(PDF))
            elif where == "history name":
                events[0]["details"] = {"nombre": secret}
            elif where == "history actor":
                events[0]["actor"] = {"id": ana["id"], "display_name": ana["display_name"]}
            elif where == "history version id":
                events[0]["archivo_version_id"] = pending["version_id"]
            elif where == "summary version id":
                cell["version_id"] = pending["version_id"]
            elif where == "summary uploader text":
                cell["nota"] = f"Subido por {ana['display_name']}"
            elif where == "nested size":
                cell["extra"] = {"bytes": len(PDF)}

        expected = {
            "version size": f"'tamano': {len(PDF)}",
            "item size text": "'$[0].tamano'",
            "history name": secret,
            "history actor": ana["id"],
            "history version id": pending["version_id"],
            "summary version id": "'$[2].version_id'",
            "summary uploader text": "'$[2].nota'",
            "nested size": "'$[2].extra.bytes'",
        }
        for where, reason in expected.items():
            with self.subTest(leak=where):
                view = copy.deepcopy(clean)
                leak(*view, where=where)
                with self.assertRaises(AssertionError) as caught:
                    self.assert_private_view(view, pending, "subiendo", hidden)
                self.assertIn(reason, str(caught.exception))
        # The finder itself: whole numbers only, distinctive strings anywhere.
        texts, numbers = hidden
        self.assertEqual(leaked_paths({"id": f"{len(PDF):08d}-0000-4000-8000-000000000001",
                                       "at": f"2026-10-08T12:00:00.{len(PDF)}+00:00",
                                       "revision": 1, "privado": True}, texts, numbers), [])
        self.assertEqual(leaked_paths([{"n": float(len(PDF))}, {"s": str(len(PDF))},
                                       {"t": f"x{secret}x"}],
                                      texts, numbers), ["$[0].n", "$[1].s", "$[2].t"])

    def test_l3_completion_reads_the_clock_after_acquiring_its_boundary(self):
        pending = self.upload(PDF)
        real = db.escritura
        calls = {"n": 0}

        @contextmanager
        def slow_boundary(path=None):
            calls["n"] += 1
            with real(path) as conn:
                if calls["n"] == 2:     # time spent acquiring the final boundary
                    self.clock.advance(2)
                yield conn

        with patch.object(db, "escritura", slow_boundary):
            error = self.assert_code("lease_perdido", lambda: self.complete(
                pending, ganchos=SimpleNamespace(
                    antes_commit=lambda _v: self.clock.advance(archivos.LEASE_SECONDS - 2))))
        self.assertEqual(error.status, 409)
        version = self.rows("archivo_version", "id = ?", (pending["version_id"],))[0]
        self.assertEqual(version["estado"], "subiendo")
        self.assertEqual(list(self.store.listar("final/")), [])
        # One second short of the lease it still commits: equality is the edge.
        retry = self.upload(PDF, key="retry")
        calls["n"] = 0
        with patch.object(db, "escritura", slow_boundary):
            done = self.complete(retry, ganchos=SimpleNamespace(
                antes_commit=lambda _v: self.clock.advance(archivos.LEASE_SECONDS - 3)))
        self.assertEqual(done["version"]["estado"], "disponible")

    def test_l3_start_and_failure_boundaries_use_post_acquire_time(self):
        real = db.escritura

        @contextmanager
        def slow_boundary(path=None):
            with real(path) as conn:
                self.clock.advance(7)
                yield conn

        with patch.object(db, "escritura", slow_boundary):
            started = self.start(PDF)
        self.assertEqual(started["subida_vence_en"], "2026-10-08T12:15:07+00:00")
        self.assertEqual(started["completar_antes_de"], "2026-10-08T13:00:07+00:00")
        bad = self.upload(b"not-a-pdf", key="bad")
        self.clock.advance(archivos.COMPLETE_SECONDS - 1)
        with patch.object(db, "escritura", slow_boundary):
            # The lease is taken after the boundary: the deadline has passed by then.
            self.assert_code("subida_expirada", lambda: self.complete(bad))
        self.assertEqual(self.rows("archivo_version", "id = ?", (bad["version_id"],))[0]["estado"],
                         "expirado")

    def test_l3_deadline_with_live_lease_is_in_progress_not_expired(self):
        started = self.upload(PDF)
        self.clock.advance(archivos.COMPLETE_SECONDS - 1)
        seen = []

        def at_deadline(_version):
            self.clock.advance(1)
            with self.assertRaises(ApiError) as caught:
                self.complete(started)
            seen.append(caught.exception)

        result = self.complete(started, ganchos=SimpleNamespace(despues_copia=at_deadline))
        self.assertEqual(seen[0].status, 409)
        self.assertEqual(seen[0].detalle, {"code": "procesamiento_en_curso", "reintentar": True,
                                           "reintentar_despues_de": "2026-10-08T13:02:59+00:00"})
        self.assertEqual(result["version"]["estado"], "disponible")
        self.assertNotIn("subida_expirada", [r["accion"] for r in self.rows("archivo_evento")])

    def test_l3_expired_reprocessing_lease_is_controlled_and_writes_nothing(self):
        started = self.upload(kmz("ambiguo_tres_lotes"), "kmz")
        self.complete(started)
        before = self.snapshot()
        error = self.assert_code("lease_perdido", lambda: archivos.reprocesar(
            self.sessions["ana"], started["version_id"], self.store, seleccion=[0],
            idempotency_key="caducado", bd=self.database, reloj=self.clock,
            ganchos=SimpleNamespace(
                despues_parseo=lambda _v: self.clock.advance(archivos.LEASE_SECONDS))))
        self.assertEqual(error.status, 409)
        after = self.snapshot()
        lease_rows = after.pop("archivo_trabajo")   # the expired lease may linger
        before.pop("archivo_trabajo")
        self.assertEqual(after, before)
        self.assertLessEqual(len(lease_rows), 1)
        retried = archivos.reprocesar(
            self.sessions["ana"], started["version_id"], self.store, seleccion=[0],
            idempotency_key="caducado", bd=self.database, reloj=self.clock)
        self.assertFalse(retried["replay"])
        self.assertEqual(retried["intento"]["resultado"], "listo")

    def test_l3_takeover_while_late_holder_waits_then_commits_first(self):
        started = self.upload(PDF)
        old_copied, old_go = threading.Event(), threading.Event()
        new_copied, new_go = threading.Event(), threading.Event()
        outcomes = {}

        def run(name, copied, go):
            def hook(_version):
                copied.set()
                go.wait(10)
            try:
                outcomes[name] = self.complete(started, ganchos=SimpleNamespace(
                    despues_copia=hook))
            except Exception as exc:  # asserted below
                outcomes[name] = exc

        old = threading.Thread(target=run, args=("old", old_copied, old_go))
        old.start()
        self.assertTrue(old_copied.wait(10))
        self.clock.advance(archivos.LEASE_SECONDS)       # old lease expires while waiting
        new = threading.Thread(target=run, args=("new", new_copied, new_go))
        new.start()
        self.assertTrue(new_copied.wait(10))
        old_go.set()                                     # late holder reaches commit first
        old.join(10)
        new_go.set()
        new.join(10)
        self.assertIsInstance(outcomes["old"], ApiError)
        self.assertEqual(outcomes["old"].detalle["code"], "lease_perdido")
        self.assertEqual(outcomes["new"]["version"]["estado"], "disponible")
        final = self.rows("archivo_version", "id = ?", (started["version_id"],))[0]["clave_final"]
        self.assertEqual([item.clave for item in self.store.listar("final/")], [final])

    def test_l3_reprocessing_takeover_fences_the_late_holder(self):
        started = self.upload(kmz("ambiguo_tres_lotes"), "kmz")
        self.complete(started)
        parsed, go = threading.Event(), threading.Event()
        outcome = {}

        def hook(_version):
            parsed.set()
            go.wait(10)

        def late():
            try:
                archivos.reprocesar(self.sessions["ana"], started["version_id"], self.store,
                                    seleccion=[0], idempotency_key="tarde", bd=self.database,
                                    reloj=self.clock, ganchos=SimpleNamespace(despues_parseo=hook))
            except ApiError as exc:
                outcome["late"] = exc

        thread = threading.Thread(target=late)
        thread.start()
        self.assertTrue(parsed.wait(10))
        self.clock.advance(archivos.LEASE_SECONDS)
        winner = archivos.reprocesar(self.sessions["ana"], started["version_id"], self.store,
                                     seleccion=[1], idempotency_key="ganador",
                                     bd=self.database, reloj=self.clock)
        go.set()
        thread.join(10)
        self.assertEqual(outcome["late"].detalle["code"], "lease_perdido")
        attempts = self.rows("archivo_intento", "archivo_version_id = ? AND origen = 'seleccion'",
                             (started["version_id"],))
        self.assertEqual([a["id"] for a in attempts], [winner["intento"]["id"]])

    def test_l4_listing_is_bounded_paged_and_stable_with_equal_timestamps(self):
        ids = []
        for n in range(105):            # the clock never moves: every creado_en is equal
            started = self.start(PDF, key=f"ciclo-{n}")
            archivos.cancelar(self.sessions["ana"], started["version_id"], self.store,
                              bd=self.database, reloj=self.clock)
            ids.append(started["archivo_id"])
        retired = self.completed_pdf(name="retirado-ficticio.pdf")
        archivos.retirar(self.sessions["ana"], retired["archivo_id"], expected_revision=2,
                         idempotency_key="retirar", bd=self.database, reloj=self.clock)
        ids.append(retired["archivo_id"])
        pages, cursor = [], None
        while True:
            page = archivos.listar(self.sessions["olga"], self.terrain, cursor=cursor,
                                   bd=self.database, reloj=self.clock)
            pages.append([item["id"] for item in page["archivos"]])
            cursor = page["cursor_siguiente"]
            if cursor is None:
                break
        self.assertEqual([len(p) for p in pages], [50, 50, 6])
        listed = [i for p in pages for i in p]
        self.assertEqual(sorted(listed), sorted(ids))
        self.assertEqual(len(set(listed)), len(listed))
        self.assertEqual(listed, sorted(listed, reverse=True))   # id breaks the tie
        largest = archivos.listar(self.sessions["ana"], self.terrain, limite=100,
                                  bd=self.database, reloj=self.clock)
        self.assertEqual(len(largest["archivos"]), 100)
        for bad in (0, 101, True, "50"):
            self.assert_code("limite_invalido", lambda bad=bad: archivos.listar(
                self.sessions["ana"], self.terrain, limite=bad, bd=self.database))
        for bad in ("x", "2026-10-08T12:00:00+00:00|no-uuid", 7):
            self.assert_code("cursor_invalido", lambda bad=bad: archivos.listar(
                self.sessions["ana"], self.terrain, cursor=bad, bd=self.database))
        self.assert_code("not_found", lambda: archivos.listar(
            self.sessions["olga"], self.other_terrain, bd=self.database))

        class Counting:
            def __init__(inner, conn):  # noqa: N805
                inner.conn, inner.calls = conn, 0

            def execute(inner, *args):  # noqa: N805
                inner.calls += 1
                return inner.conn.execute(*args)

        with db.session(self.database) as conn:
            counting = Counting(conn)
            from server.repo import archivos as repo
            rows, _ = repo.list_for_terrain(counting, self.terrain, self.users["ana"]["id"],
                                            "2026-10-08T12:00:00+00:00", None, 100)
        self.assertEqual((len(rows), counting.calls), (100, 1))

    def test_l5_retired_pdfs_do_not_crowd_active_summaries(self):
        active = self.completed_pdf(name="activo-ficticio.pdf")
        retired = []
        for n in range(5):
            self.clock.advance(1)
            started = self.completed_pdf(name=f"retirado-{n}.pdf")
            archivos.retirar(self.sessions["ana"], started["archivo_id"], expected_revision=2,
                             idempotency_key=f"r{n}", bd=self.database, reloj=self.clock)
            retired.append(started["archivo_id"])
        with db.session(self.database) as conn:
            summary = archivos.resumenes_de_archivos(conn, [self.terrain], self.sessions["ana"],
                                                     reloj=self.clock)
        cell = summary["resultados"][self.terrain]
        self.assertEqual(cell["pdf_total"], 1)
        self.assertEqual([r["id"] for r in cell["pdf_recientes"]], [active["archivo_id"]])
        self.assertFalse(cell["pdf_recientes"][0]["retirado"])
        listed = archivos.listar(self.sessions["ana"], self.terrain, bd=self.database,
                                 reloj=self.clock)["archivos"]
        self.assertEqual({i["id"] for i in listed if i["retirado_en"]}, set(retired))
        history = archivos.historial(self.sessions["ana"], retired[0], bd=self.database)
        self.assertIn("retirado", [e["accion"] for e in history["eventos"]])

    def test_l5_summary_replaces_lower_revision_pdf_beside_higher_revision(self):
        low = self.completed_pdf(name="bajo-ficticio.pdf")
        self.clock.advance(1)
        high = self.completed_pdf(name="alto-ficticio.pdf")
        for revision in (2, 3):         # re-select the same version: revision 2 -> 4
            archivos.activar(self.sessions["ana"], high["archivo_id"],
                             version_id=high["version_id"], expected_revision=revision,
                             idempotency_key=f"alto-{revision}", bd=self.database,
                             reloj=self.clock)

        def cells():
            with db.session(self.database) as conn:
                summary = archivos.resumenes_de_archivos(
                    conn, [self.terrain], self.sessions["ana"], reloj=self.clock)
            return {r["id"]: r["revision"] for r in summary["resultados"][self.terrain]["pdf_recientes"]}

        self.assertEqual(cells(), {low["archivo_id"]: 2, high["archivo_id"]: 4})
        archivos.activar(self.sessions["ana"], low["archivo_id"], version_id=low["version_id"],
                         expected_revision=2, idempotency_key="bajo", bd=self.database,
                         reloj=self.clock)
        # The maximum revision is still 4, yet the lower attachment's change shows.
        self.assertEqual(cells(), {low["archivo_id"]: 3, high["archivo_id"]: 4})
        self.assert_terrain_untouched()

    def test_l6_verification_failure_reports_failed_cleanup_and_replay_rechecks(self):
        from server.almacen import FalloAlmacenError
        clean = self.upload(b"not-a-pdf", key="limpio")
        result = self.complete(clean)
        self.assertEqual(result["version"]["estado"], "fallido")
        self.assertFalse(result["limpieza_pendiente"])
        self.assertEqual(list(self.store.listar("final/")), [])
        self.assertEqual(list(self.store.listar("temporal/")), [])
        self.assertFalse(self.complete(clean)["limpieza_pendiente"])

        bad = self.upload(b"not-a-pdf", key="sucio")
        with patch.object(self.store, "borrar", side_effect=FalloAlmacenError()):
            failed = self.complete(bad)
        self.assertEqual(failed["version"]["error"]["codigo"], "firma_invalida")
        self.assertTrue(failed["limpieza_pendiente"])
        leftovers = [item.clave for item in self.store.listar("final/")]
        self.assertEqual(len(leftovers), 1)
        replay = self.complete(bad)
        self.assertTrue(replay["replay"])
        self.assertTrue(replay["limpieza_pendiente"])
        self.assertEqual(replay["version"], failed["version"])
        serialized = repr((failed, replay))
        self.assertNotIn("final/", serialized)
        self.assertNotIn("temporal/", serialized)
        for key in leftovers + [item.clave for item in self.store.listar("temporal/")]:
            self.store.borrar(key)       # stands in for a future safe sweep
        self.assertFalse(self.complete(bad)["limpieza_pendiente"])

    def test_l6_unprovable_reference_keeps_bytes_and_reports_pending(self):
        bad = self.upload(b"not-a-pdf")
        from server.repo import archivos as repo
        with patch.object(repo, "final_key_referenced", side_effect=RuntimeError("db")):
            failed = self.complete(bad)
        self.assertTrue(failed["limpieza_pendiente"])
        self.assertEqual(len(list(self.store.listar("final/"))), 1)

    def test_l6_successful_completion_staging_failure_survives_replay(self):
        from server.almacen import FalloAlmacenError
        started = self.upload(PDF)
        with patch.object(self.store, "borrar", side_effect=FalloAlmacenError()):
            done = self.complete(started)
        self.assertTrue(done["limpieza_pendiente"])
        self.assertTrue(self.complete(started)["limpieza_pendiente"])
        for item in list(self.store.listar("temporal/")):
            self.store.borrar(item.clave)
        replay = self.complete(started)
        self.assertFalse(replay["limpieza_pendiente"])
        final = self.rows("archivo_version", "id = ?", (started["version_id"],))[0]["clave_final"]
        self.assertIsNotNone(self.store.tamano_de(final))   # referenced bytes are never touched

    def test_l6_lost_lease_error_carries_cleanup_status(self):
        from server.almacen import FalloAlmacenError
        started = self.upload(PDF)

        def lose(_version):
            self.clock.advance(archivos.LEASE_SECONDS)
            self.store.borrar = Mock(side_effect=FalloAlmacenError())

        original = self.store.borrar
        try:
            error = self.assert_code("lease_perdido", lambda: self.complete(
                started, ganchos=SimpleNamespace(antes_commit=lose)))
        finally:
            self.store.borrar = original
        self.assertTrue(error.detalle["limpieza_pendiente"])
        self.assertEqual(len(list(self.store.listar("final/"))), 1)

    def test_l6_cancellation_never_claims_an_unattempted_or_failed_cleanup(self):
        from server.almacen import FalloAlmacenError
        cases = {"store": (self.store, None, False), "no_store": (None, None, True),
                 "failure": (self.store, FalloAlmacenError(), True)}
        for name, (store, failure, pending) in cases.items():
            with self.subTest(case=name):
                started = self.upload(PDF, key=name)
                with patch.object(self.store, "borrar", side_effect=failure,
                                  wraps=None if failure else self.store.borrar):
                    cancelled = archivos.cancelar(self.sessions["ana"], started["version_id"],
                                                  store, bd=self.database, reloj=self.clock)
                self.assertEqual(cancelled["limpieza_pendiente"], pending)
                staged = self.rows("archivo_version", "id = ?",
                                   (started["version_id"],))[0]["clave_temporal"]
                self.assertEqual(self.store.tamano_de(staged) is not None, pending)
                self.assert_code("subida_no_pendiente", lambda started=started: archivos.cancelar(
                    self.sessions["ana"], started["version_id"], self.store,
                    bd=self.database, reloj=self.clock))

    def test_l6_retirement_replay_reports_actual_staging_state(self):
        from server.almacen import FalloAlmacenError
        live = self.upload(kmz("poligono_simple"), "kmz")
        self.complete(live)
        pending = self.upload(kmz("poligono_simple"), "kmz", user="olga", key="pendiente")
        staged = self.rows("archivo_version", "id = ?",
                           (pending["version_id"],))[0]["clave_temporal"]

        def retire(store):
            return archivos.retirar(self.sessions["ana"], live["archivo_id"], expected_revision=2,
                                    idempotency_key="retirar", almacen=store,
                                    bd=self.database, reloj=self.clock)

        with patch.object(self.store, "borrar", side_effect=FalloAlmacenError()):
            first = retire(self.store)
        self.assertTrue(first["limpieza_pendiente"])
        self.assertIsNotNone(self.store.tamano_de(staged))
        self.assertTrue(retire(self.store)["limpieza_pendiente"])
        self.assertTrue(retire(None)["limpieza_pendiente"])
        self.store.borrar(staged)
        replay = retire(self.store)
        self.assertTrue(replay["replay"])
        self.assertFalse(replay["limpieza_pendiente"])
        self.assertEqual(replay["archivo"], first["archivo"])
        final = self.rows("archivo_version", "id = ?", (live["version_id"],))[0]["clave_final"]
        self.assertIsNotNone(self.store.tamano_de(final))
        nothing = self.completed_pdf()
        quiet = archivos.retirar(self.sessions["ana"], nothing["archivo_id"], expected_revision=2,
                                 idempotency_key="sin-pendientes", bd=self.database,
                                 reloj=self.clock)
        self.assertFalse(quiet["limpieza_pendiente"])

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

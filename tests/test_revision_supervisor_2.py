"""Second supervisor review, R2a and R2b (SUPERVISOR_REVIEW_02.md).

The reviewer's four cases (kept verbatim in the report folder) are repeated
here so normal verification runs them, followed by stronger controls. The
session-depth checks instrument lock ownership; they are not live Postgres
tests -- those are in tests/test_postgres.py and need a disposable database.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from server import db
from server.api import carpetas as api_carpetas
from server.api import importar
from server.asistente import borradores as modulo_borradores
from server.asistente.borradores import borradores
from server.repo import bases
from server.web_util import ApiError
from tests.support import FIXTURE
from tests.test_api import req
from tests.test_asistente_api import AsistenteCase

CSV = b"Terreno,Precio\nNorte,1000000\n"


class Revision2Case(AsistenteCase):
    def committer(self, append):
        if not append:
            return None, lambda r: self.confirmar(r, recordar_formato=False)
        base_id = bases.create(self.conn, "Destino", None, None)

        def commit(r):
            return importar.append(req(params={"id": base_id}, json_body={
                "token": r["vista_previa"]["token"], "recordar_formato": False,
                "resoluciones": {"0": "actualizar"}}))

        return base_id, commit

    def precios(self):
        return [r[0] for r in self.conn.execute("SELECT asking_price FROM terreno ORDER BY id")]

    def terrenos(self):
        return self.conn.execute("SELECT COUNT(*) FROM terreno").fetchone()[0]


# ---------------------------------------------------------------------- R2a

class R2aConfirmacionTardia(Revision2Case):
    def late_confirmation(self, append):
        """Reviewer's ordering: A takes its token, B corrects, C imports B, A resumes."""
        base_id, commit = self.committer(append)
        old = self.analizar("race.csv", CSV, base_id=base_id)
        col = old["interpretacion"]["columnas"][1]["id"]
        original_claim = importar._vigente
        events = []

        def interleave(pending):
            newer = self.preparar(old, correcciones={"columnas": {col: "extra"}})
            events.append("correction succeeded")
            with patch.object(importar, "_vigente", original_claim):
                commit(newer)
            events.append("corrected confirmation succeeded")
            original_claim(pending)

        error = None
        with patch.object(importar, "_vigente", side_effect=interleave):
            try:
                commit(old)
                events.append("STALE confirmation succeeded")
            except ApiError as caught:
                error = caught.status
        self.assertIn(error, (409, 410), f"{events}; stored prices={self.precios()}")
        self.assertEqual(self.precios(), [None])
        self.assertEqual(len(self.bases()), 1)

    def test_stale_confirmation_after_corrected_commit_is_rejected(self):
        self.late_confirmation(append=False)

    def test_stale_append_after_corrected_commit_is_rejected(self):
        self.late_confirmation(append=True)

    def test_missing_draft_is_stale_not_permission(self):
        r = self.analizar("x.csv", CSV)
        borradores.borrar(r["borrador"])
        self.assertEqual(self.status_of(lambda: self.confirmar(r)), 410)
        self.assertEqual((self.bases(), self.terrenos()), ([], 0))

    def test_expired_draft_is_stale(self):
        r = self.analizar("x.csv", CSV)
        # Drafts outlive previews (60 vs 30 min); force only the draft to have expired.
        with patch.object(modulo_borradores, "TTL_SEGUNDOS", -1):
            self.assertEqual(self.status_of(lambda: self.confirmar(r)), 410)
        self.assertEqual(self.bases(), [])

    def test_evicted_draft_is_stale(self):
        with patch.object(modulo_borradores, "MAX_LOCALES", 1):
            primera = self.analizar("a.csv", CSV)
            self.analizar("b.csv", CSV)   # evicts the first draft
            self.assertIsNone(borradores.leer(primera["borrador"]))
            self.assertEqual(self.status_of(lambda: self.confirmar(primera)), 410)
        self.assertEqual(self.bases(), [])

    def test_a_claimed_draft_refuses_a_second_confirmation(self):
        r = self.analizar("x.csv", CSV)
        pending = importar.staging.take(r["vista_previa"]["token"])
        importar._vigente(pending)                      # first confirmation owns it
        with self.assertRaises(ApiError) as caught:
            importar._vigente(pending)                  # a replay of the same preview
        self.assertEqual(caught.exception.status, 409)

    def test_legacy_previews_without_a_draft_still_confirm(self):
        preview = importar.preview(req(body=FIXTURE.read_bytes(), headers={"X-Archivo": "b.xlsx"}))
        base = importar.confirm(req(json_body={"token": preview["token"], "nombre": "Legado"}))["base"]
        self.assertEqual(base["conteo"], 79)


# ---------------------------------------------------------------------- R2b

class R2bLimpiezaFueraDeLaSesion(Revision2Case):
    def cleanup_after_transaction(self, append, falla=None):
        base_id, commit = self.committer(append)
        preview = self.analizar("failure.csv", CSV, base_id=base_id)
        real_session, real_delete = db.session, borradores.borrar
        active_sessions = 0
        cleanup_depths = []

        @contextmanager
        def tracked_session(*args, **kwargs):
            nonlocal active_sessions
            with real_session(*args, **kwargs) as conn:
                active_sessions += 1
                try:
                    yield conn
                finally:
                    active_sessions -= 1

        def tracked_delete(token):
            cleanup_depths.append(active_sessions)
            return real_delete(token)

        falla = falla or patch.object(importar.repo_terrenos, "insert",
                                      side_effect=RuntimeError("injected write failure"))
        with patch.object(db, "session", tracked_session), \
                patch.object(borradores, "borrar", side_effect=tracked_delete), falla, \
                self.assertRaisesRegex(RuntimeError, "injected"):
            commit(preview)
        self.assertEqual(self.terrenos(), 0)
        self.assertTrue(cleanup_depths, "A failed, claimed draft must be closed")
        self.assertTrue(all(depth == 0 for depth in cleanup_depths), cleanup_depths)
        self.assertIsNone(borradores.leer(preview["borrador"]))
        return preview

    def test_failed_confirmation_cleans_up_after_session_exit(self):
        self.cleanup_after_transaction(append=False)

    def test_failed_append_cleans_up_after_session_exit(self):
        self.cleanup_after_transaction(append=True)

    def profundidades_al_cerrar(self, commit, preview):
        """Session depth at each draft deletion during one commit."""
        depths, activas = [], [0]
        real_session, real_delete = db.session, borradores.borrar

        @contextmanager
        def tracked(*a, **k):
            with real_session(*a, **k) as conn:
                activas[0] += 1
                try:
                    yield conn
                finally:
                    activas[0] -= 1

        def tracked_delete(token):
            depths.append(activas[0])
            return real_delete(token)

        with patch.object(db, "session", tracked), patch.object(borradores, "borrar", side_effect=tracked_delete):
            commit(preview)
        return depths

    def test_successful_commits_also_clean_up_after_session_exit(self):
        for append in (False, True):
            with self.subTest(append=append):
                base_id, commit = self.committer(append)
                preview = self.analizar("ok.csv", CSV, base_id=base_id)
                self.assertEqual(self.profundidades_al_cerrar(commit, preview), [0])

    def test_a_commit_failure_rolls_back_formats_and_records_too(self):
        r = self.analizar("x.csv", CSV)
        with patch.object(importar.repo_formatos, "registrar_importacion",
                          side_effect=RuntimeError("injected provenance failure")), \
                self.assertRaisesRegex(RuntimeError, "injected"):
            self.confirmar(r)   # remembering the format is on by default
        for tabla in ("base", "terreno", "formato_importacion", "importacion"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], 0, tabla)

    def test_backup_failure_after_the_claim_closes_the_draft(self):
        self.cleanup_after_transaction(
            append=False, falla=patch.object(importar.db, "backup", side_effect=RuntimeError("injected backup")))

    def test_the_spent_preview_then_gets_an_understandable_answer(self):
        preview = self.cleanup_after_transaction(append=False)
        self.assertEqual(self.status_of(lambda: self.confirmar(preview)), 410)
        self.assertEqual(self.status_of(lambda: self.preparar(preview)), 410)

    def test_destination_folder_gone_after_validation_is_marked_spent(self):
        carpeta = api_carpetas.create(req(json_body={"tipo": "bases", "nombre": "Efímera"}))["carpeta"]
        r = self.analizar("x.csv", CSV)
        real_require = importar.repo_carpetas.require_folder
        llamadas = []

        def desaparece(conn, tipo, carpeta_id):
            llamadas.append(carpeta_id)
            if len(llamadas) == 2:   # the in-transaction check, after the claim
                conn.execute("DELETE FROM carpeta WHERE id = ?", (carpeta_id,))
            return real_require(conn, tipo, carpeta_id)

        with patch.object(importar.repo_carpetas, "require_folder", side_effect=desaparece), \
                self.assertRaises(ApiError) as caught:
            self.confirmar(r, carpeta_id=carpeta["id"])
        self.assertEqual(caught.exception.status, 404)
        self.assertTrue(caught.exception.detalle["vista_previa_consumida"])
        self.assertIsNone(borradores.leer(r["borrador"]))
        self.assertEqual(self.bases(), [])

    def test_destination_base_gone_before_append_is_marked_spent(self):
        base_id = bases.create(self.conn, "Destino", None, None)
        r = self.analizar("x.csv", CSV, base_id=base_id)
        self.conn.execute("DELETE FROM base WHERE id = ?", (base_id,))
        with self.assertRaises(ApiError) as caught:
            importar.append(req(params={"id": base_id}, json_body={"token": r["vista_previa"]["token"]}))
        self.assertEqual((caught.exception.status, caught.exception.detalle["vista_previa_consumida"]), (404, True))
        self.assertIsNone(borradores.leer(r["borrador"]))

    def test_cleanup_failure_never_masks_the_outcome(self):
        # Success stays success...
        r = self.analizar("x.csv", CSV)
        with patch.object(borradores, "borrar", side_effect=RuntimeError("cleanup broke")), \
                self.assertLogs("ara.importar", level="ERROR") as registro:
            base = self.confirmar(r)["base"]
        self.assertEqual(base["conteo"], 1)
        self.assertIn("RuntimeError", " ".join(registro.output))
        # ...and the still-claimed draft refuses any replay.
        self.assertEqual(self.status_of(lambda: self.preparar(r)), 409)
        # A real failure keeps its own error, not the cleanup's.
        r = self.analizar("y.csv", CSV)
        with patch.object(borradores, "borrar", side_effect=RuntimeError("cleanup broke")), \
                patch.object(importar.repo_terrenos, "insert", side_effect=RuntimeError("injected write")), \
                self.assertLogs("ara.importar", level="ERROR"), \
                self.assertRaisesRegex(RuntimeError, "injected write"):
            self.confirmar(r)

    def test_invalid_input_does_not_spend_the_preview(self):
        r = self.analizar("x.csv", CSV)
        self.assertEqual(self.status_of(lambda: self.confirmar(r, nombre="   ")), 400)
        self.assertEqual(self.status_of(lambda: self.confirmar(r, nombre=5)), 400)
        self.assertEqual(self.confirmar(r, nombre="Válida")["base"]["nombre"], "Válida")

        base_id = bases.create(self.conn, "Destino", None, None)
        r = self.analizar("x.csv", CSV, base_id=base_id)
        malo = req(params={"id": base_id}, json_body={"token": r["vista_previa"]["token"],
                                                      "resoluciones": {"no-es-numero": "actualizar"}})
        with self.assertRaises(ApiError) as caught:
            importar.append(malo)
        self.assertEqual(caught.exception.status, 400)
        salida = importar.append(req(params={"id": base_id}, json_body={"token": r["vista_previa"]["token"]}))
        self.assertEqual(salida["agregados"], 1)

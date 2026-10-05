"""Second independent review: temporary SQLite, fictional data, no network.

Run from the repository root with both cloud database variables unset.
The cleanup cases instrument session lifetime; they are NOT live Postgres tests.
"""

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server import db
from server.api import importar
from server.asistente.borradores import borradores
from server.repo import bases
from server.web_util import ApiError
from tests.test_api import req
from tests.test_asistente_api import AsistenteCase


class Review2Cases(AsistenteCase):
    def committer(self, append):
        if not append:
            return None, lambda r: self.confirmar(r, recordar_formato=False)
        base_id = bases.create(self.conn, "Destino", None, None)

        def commit(r):
            return importar.append(req(params={"id": base_id}, json_body={
                "token": r["vista_previa"]["token"], "recordar_formato": False,
                "resoluciones": {"0": "actualizar"}}))

        return base_id, commit

    def late_confirmation(self, append):
        base_id, commit = self.committer(append)
        old = self.analizar("race.csv", b"Terreno,Precio\nNorte,1000000\n", base_id=base_id)
        col = old["interpretacion"]["columnas"][1]["id"]
        original_claim = importar._vigente
        events = []

        def interleave(pending):
            # The old request already owns its preview token. Pause it before
            # claiming the draft, let correction + new confirmation finish,
            # then resume the ORIGINAL claim code with its original payload.
            newer = self.preparar(old, correcciones={"columnas": {col: "extra"}})
            self.assertIsNone(newer["vista_previa"]["filas"][0]["asking_price"])
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
        prices = [r[0] for r in self.conn.execute("SELECT asking_price FROM terreno ORDER BY id")]
        self.assertIn(error, (409, 410), f"{events}; stored prices={prices}")
        self.assertEqual(prices, [None])
        self.assertEqual(len(self.bases()), 1)

    def test_stale_confirmation_after_corrected_commit_is_rejected(self):
        self.late_confirmation(append=False)

    def test_stale_append_after_corrected_commit_is_rejected(self):
        self.late_confirmation(append=True)

    def cleanup_after_transaction(self, append):
        base_id, commit = self.committer(append)
        preview = self.analizar("failure.csv", b"Terreno,Precio\nNorte,1000000\n", base_id=base_id)
        real_session, real_delete = db.session, borradores.borrar
        active_sessions = 0
        cleanup_depths = []

        @contextmanager
        def tracked_session():
            nonlocal active_sessions
            with real_session() as conn:
                active_sessions += 1
                try:
                    yield conn
                finally:
                    active_sessions -= 1

        def tracked_delete(token):
            # borrar opens its own Postgres session. That session must not
            # acquire the workspace lock while this handler still holds it.
            cleanup_depths.append(active_sessions)
            return real_delete(token)

        with patch.object(db, "session", tracked_session), \
                patch.object(borradores, "borrar", side_effect=tracked_delete), \
                patch.object(importar.repo_terrenos, "insert", side_effect=RuntimeError("injected write failure")):
            with self.assertRaisesRegex(RuntimeError, "injected write failure"):
                commit(preview)

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM terreno").fetchone()[0], 0)
        self.assertTrue(cleanup_depths, "A failed, claimed draft must be closed")
        self.assertTrue(all(depth == 0 for depth in cleanup_depths),
                        f"Draft deletion opens its own session while an outer session is active: {cleanup_depths}")

    def test_failed_confirmation_cleans_up_after_session_exit(self):
        self.cleanup_after_transaction(append=False)

    def test_failed_append_cleans_up_after_session_exit(self):
        self.cleanup_after_transaction(append=True)


if __name__ == "__main__":
    unittest.main()

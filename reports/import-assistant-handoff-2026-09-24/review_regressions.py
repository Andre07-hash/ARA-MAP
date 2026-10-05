"""Independent review cases: fictional data, disposable SQLite, no network.

Run from the repository root:
    python3 reports/import-assistant-handoff-2026-09-24/review_regressions.py -v

These cases express required outcomes and intentionally fail on the reviewed
implementation. No application code or existing assertion is modified.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.asistente import ia
from server.asistente.detectar import interpretar
from server.asistente.plan import PlanError, construir
from server.asistente.rejilla import leer
from server.web_util import ApiError
from tests.test_asistente_api import AsistenteCase
from tests.test_asistente_ia import OPENAI_ENV, interpretacion


class ReviewCases(AsistenteCase):
    def test_control_familiar_file_still_previews_without_questions(self):
        result = self.analizar("control.csv", b"Terreno,Precio,Latitud,Longitud\nNorte,1000000,19.5,-99.1\n")
        self.assertEqual(result["estado"], "vista_previa")
        self.assertEqual(result["vista_previa"]["filas"][0]["asking_price"], 1000000)

    def test_r1_duplicate_header_template_requires_reconfirmation(self):
        first = self.analizar("original.csv", b"Terreno,Precio,Precio,Latitud,Longitud\nNorte,1000000,500,19.5,-99.1\n")
        cols = first["interpretacion"]["columnas"]
        first = self.preparar(first, correcciones={"columnas": {
            cols[1]["id"]: "asking_price", cols[2]["id"]: "asking_m2"}})
        self.confirmar(first)

        second = self.analizar("reordenado.csv", b"Terreno,Precio,Precio,Latitud,Longitud\nNorte,500,1000000,19.5,-99.1\n")
        self.assertTrue(second.get("preguntas"),
                        "Identical duplicated labels cannot establish which price occurrence retained its meaning")

    def test_r2_confirm_and_correction_cannot_both_accept_different_revisions(self):
        old = self.analizar("race.csv", b"Terreno,Precio\nNorte,1000000\n")
        col = old["interpretacion"]["columnas"][1]["id"]
        corrected = []

        # Model another request completing after the old token was taken and
        # checked, but before its transaction writes business data.
        def concurrent_prepare():
            try:
                corrected.append(self.preparar(old, correcciones={"columnas": {col: "extra"}}))
            except ApiError as error:
                self.assertIn(error.status, (409, 410))  # an atomic commit claim may win

        try:
            with patch("server.api.importar.db.backup", side_effect=concurrent_prepare):
                committed = self.confirmar(old, recordar_formato=False)
        except ApiError as error:
            self.assertIn(error.status, (409, 410))  # alternatively, correction may win
            self.assertEqual(self.bases(), [])
            return

        self.assertFalse(bool(corrected),
                         "A newer correction succeeded before an older interpretation was committed")
        self.assertTrue(committed["base"]["id"])

    def check_foreign_price(self, header):
        grid = leer((f"Terreno,{header}\nNorte,1000000\n").encode(), "moneda.csv")
        initial = interpretar(grid, {})
        # Even an explicit field selection must not relabel foreign currency
        # as MXN: the existing model has no currency conversion contract.
        result = interpretar(grid, {"columnas": {initial.columnas[1].id: "asking_price"}})
        if result.plan() is None:
            return
        try:
            built = construir(result.plan(), grid)
        except PlanError:
            return
        self.assertTrue(all(r.asking_price is None for r in built.resultado.records),
                        f"{header} was accepted as an MXN price")

    def test_r3_us_dollar_symbol_cannot_be_saved_as_mxn(self):
        self.check_foreign_price("Precio US$")

    def test_r3_euros_cannot_be_saved_as_mxn(self):
        self.check_foreign_price("Precio EUR")

    def test_r4_usage_above_estimate_cannot_bypass_the_budget(self):
        with patch.dict(os.environ, OPENAI_ENV):
            config, _ = ia.configuracion()
            interp, pending = interpretacion()
            request = json.dumps(ia.solicitud(interp.columnas, interp.asignaciones, pending, config), ensure_ascii=False)
            cap = ia.estimar_costo(ia.SISTEMA, request, config) * 1.01

            class Provider:
                nombre = "review-stub"

                def sugerir(self, *args):
                    # Output stays inside the configured 800-token limit.
                    # Input usage need not equal the characters/3 estimate.
                    return ia.Respuesta({"asignaciones": [], "advertencias": []}, 4000, 800)

            ia.fijar_proveedor(Provider())
            with patch.dict(os.environ, {"ARA_MAP_IA_LIMITE_MENSUAL_USD": str(cap)}):
                ia.sugerir(interp.columnas, interp.asignaciones, pending)
            spent = self.conn.execute("SELECT COALESCE(SUM(costo_usd),0) FROM uso_ia").fetchone()[0]
            self.assertLessEqual(spent, cap,
                                 "Admission relied on an estimate that was not an upper bound; rejecting before calling is allowed")

    def test_r4_missing_usage_does_not_release_a_paid_reservation_as_zero(self):
        with patch.dict(os.environ, OPENAI_ENV):
            interp, pending = interpretacion()
            payload = json.dumps({"choices": [{"message": {"content": json.dumps({
                "asignaciones": [], "advertencias": []})}}]}).encode()
            ia.fijar_proveedor(ia.ProveedorOpenAI(lambda request, timeout: payload))
            ia.sugerir(interp.columnas, interp.asignaciones, pending)
            rows = self.conn.execute("SELECT costo_usd FROM uso_ia").fetchall()
            self.assertTrue(rows)
            self.assertGreater(rows[0]["costo_usd"], 0,
                               "Absent usage is unknown, not proof the provider charged zero")

    def test_r5_malformed_provider_field_falls_back_instead_of_raising(self):
        class Provider:
            nombre = "review-stub"

            def sugerir(self, *args):
                return ia.Respuesta({"asignaciones": [
                    {"columna": [], "campo": "terreno", "motivo": "malformed"}], "advertencias": []}, 10, 10)

        ia.fijar_proveedor(Provider())
        response = self.analizar("desconocido_ia.csv")
        self.assertIn(response["estado"], ("preguntas", "revisar", "vista_previa"))
        self.assertEqual(response["interpretacion"]["automatico"]["estado"], "invalido")


if __name__ == "__main__":
    unittest.main()

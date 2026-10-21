"""scripts/ensayo_claude.py, run end to end with a SIMULATED provider.

The real trial needs the owner's key and spends money; this only checks the
script's own mechanics so that run does not fail on a script bug: isolation
from any hosted database, the five steps through the real routes, the next
page without a model call, and the ledger summary. The model check (free in
real life) is stubbed out and the transport is the fictional one of
tests/e2e/asistente_servidor.py. Nothing here is evidence about Claude.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from server.asistente import terreno

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "tests" / "e2e"))

import asistente_servidor  # noqa: E402
import ensayo_claude  # noqa: E402


class EnsayoSimulado(unittest.TestCase):
    def ejecutar(self, entorno):
        salida = io.StringIO()
        with patch.dict(os.environ, entorno), patch.object(ensayo_claude, "revisar_modelo"), \
                contextlib.redirect_stdout(salida), self.assertRaises(SystemExit) as fin:
            ensayo_claude.main()
        return fin.exception.code, salida.getvalue()

    def test_the_five_steps_run_isolated_and_report_usage_without_content(self):
        terreno.fijar_proveedor(terreno.ProveedorAnthropic(asistente_servidor.transporte_ficticio(None)))
        self.addCleanup(terreno.fijar_proveedor, None)
        codigo, salida = self.ejecutar({
            "ARA_MAP_CHAT_CLAVE": "clave-ficticia-de-prueba",
            # A hosted database must never be used, even if the Terminal has one.
            "ARA_MAP_DATABASE_URL": "postgresql://no-debe-usarse.invalid/x", "DATABASE_URL": "x",
        })
        self.assertEqual(codigo, 0, salida)
        self.assertIn("Resultado: 5/5 pasos correctos con PROVEEDOR SIMULADO", salida)
        self.assertNotIn("Claude real", salida)
        self.assertIn("Página siguiente sin llamar al modelo: HTTP 200. llamadas nuevas al modelo: 0", salida)
        self.assertIn("Superficie registrada: más de 10,000 m²", salida)
        self.assertIn("Total: 4 llamadas", salida)
        for nada in ("clave-ficticia-de-prueba", "proveedor ficticio", "no-debe-usarse"):
            self.assertNotIn(nada, salida)

    def test_without_the_key_nothing_runs(self):
        codigo, salida = self.ejecutar({"ARA_MAP_CHAT_CLAVE": ""})
        self.assertEqual(codigo, 2)
        self.assertIn("export ARA_MAP_CHAT_CLAVE", salida)

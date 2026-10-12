"""Negative controls for R3-A1: break one batched rule at a time in a temporary
copy of server/ and check that tests/test_resumenes_lote.py notices.

    python3 reports/team-b-file-summary-batching-2026-10-12/mutaciones_lote.py

SQLite only (the tests' Postgres class skips without a test URL). Prints one
JSON line per run; exit code 1 if a mutation survives or the control fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
AUTH, REPO = "server/auth.py", "server/repo/archivos.py"
MUTACIONES = {
    "sin comprobar la concesión del operador": [(AUTH, "(base in concedidas and not bases[base])",
                                                 "(not bases[base])")],
    "una base archivada sigue abierta al operador": [(AUTH, "(base in concedidas and not bases[base])",
                                                      "(base in concedidas)")],
    "un terreno sin base es visible para operadores": [(AUTH, "                if admin:\n                    legibles.add(terreno_id)",
                                                        "                legibles.add(terreno_id)")],
    "sin comprobar la sesión": [(AUTH, "    alcance = _verificar(conn, sesion, capacidad)",
                                 "    alcance = Alcance(sesion, sesion.rol, capacidad, None, None, False, False)")],
    "duplicados no se eliminan": [(AUTH, "ids = list(dict.fromkeys(terreno_ids))", "ids = list(terreno_ids)")],
    "cuenta también los retirados": [(REPO, " AND tipo = 'pdf' AND retirado_en IS NULL GROUP BY", " AND tipo = 'pdf' GROUP BY")],
    "sin límite de cinco recientes": [(REPO, ' LIMIT " + str(RECIENTES_PDF)\n', ' LIMIT 1000"\n')],
    "sin desempate por id": [(REPO, "ORDER BY r.creado_en DESC, r.id DESC LIMIT", "ORDER BY r.creado_en DESC, r.id ASC LIMIT"),
                             (REPO, "ORDER BY a.inventory_id, a.creado_en DESC, a.id DESC", "ORDER BY a.inventory_id, a.creado_en DESC, a.id ASC")],
    "un trozo pierde su último terreno": [(REPO, "batch = ids[start:start + LOTE_RESUMENES]", "batch = ids[start:start + LOTE_RESUMENES - 1]")],
}

malos = 0
for nombre in [None, *MUTACIONES]:
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "arbol"
        shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns(".git", "reports", "web", "__pycache__", "node_modules"))
        for archivo, antes, despues in MUTACIONES.get(nombre, []):
            ruta = copia / archivo
            texto = ruta.read_text()
            if antes not in texto:
                raise SystemExit(f"la mutación «{nombre}» no encontró su texto en {archivo}")
            ruta.write_text(texto.replace(antes, despues, 1))
        r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_resumenes_lote"], cwd=copia,
                           capture_output=True, text=True, timeout=600,
                           env={"PATH": "/usr/bin:/bin", "HOME": tmp})
        fallan = sorted({line.split(" (")[0].split(": ", 1)[1] for line in r.stderr.splitlines()
                         if line.startswith(("FAIL: ", "ERROR: "))})
        estado = ("control: pasa" if r.returncode == 0 else "CONTROL FALLA") if nombre is None else \
            ("detectada" if r.returncode != 0 else "SOBREVIVE")
        malos += estado in ("SOBREVIVE", "CONTROL FALLA")
        print(json.dumps({"mutacion": nombre or "ninguna", "resultado": estado, "pruebas_que_fallan": fallan},
                         ensure_ascii=False))
sys.exit(1 if malos else 0)

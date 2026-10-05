"""Score the import assistant's column interpretation on the held-out fixtures.

    python3 scripts/evaluar_asistente.py

For each file in tests/fixtures/asistente/evaluacion, compares the final
assignment of every column with esperado.json and reports:

    correctas   column interpreted exactly as expected
    omitidas    expected a field, left as additional data (safe: visible, correctable)
    erroneas    assigned to a DIFFERENT field than expected (the harmful kind)
    preguntas   questions the manager would be asked before the preview

Two modes: "deterministic" (no automatic assistance -- the offline path), and
"simulated" (the local stand-in provider). The simulated provider is a header
keyword table, NOT a model: its row exercises the pipeline and validation and
says nothing about how a real model would score.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from server.asistente import ia  # noqa: E402
from server.asistente.detectar import interpretar  # noqa: E402
from server.asistente.rejilla import leer  # noqa: E402

CARPETA = RAIZ / "tests" / "fixtures" / "asistente" / "evaluacion"
CONFIG = ia.Config("simulado", None, None, 0.0, 0.0, 0.0, 5.0, 3, 800, 1000)


def evaluar(modo: str) -> list[dict]:
    esperado = json.loads((CARPETA / "esperado.json").read_text(encoding="utf-8"))
    filas = []
    for archivo, campos in esperado.items():
        rejilla = leer((CARPETA / archivo).read_bytes(), archivo)
        interp = interpretar(rejilla, {})
        if modo == "simulado" and interp.necesita_ia:
            pendientes = {c.id for c in interp.columnas if interp.origenes[c.id].fuente in ("predeterminado", "pendiente")}
            usuario = json.dumps(ia.solicitud(interp.columnas, interp.asignaciones, pendientes, CONFIG))
            ids = [c.id for c in interp.columnas if c.id in pendientes]
            libres = [k for k in ia.C.CAMPOS if k not in set(interp.asignaciones.values())]
            respuesta = ia.ProveedorSimulado().sugerir(ia.SISTEMA, usuario, ia.esquema(ids, libres), CONFIG)
            propuesta = ia.validar(respuesta.contenido, set(ids), set(libres))
            interp = interpretar(rejilla, {}, (), propuesta)
        conteo = {"correctas": 0, "omitidas": 0, "erroneas": 0}
        for col in interp.columnas:
            quiere, tiene = campos[col.etiqueta], interp.asignaciones[col.id]
            if tiene == quiere:
                conteo["correctas"] += 1
            elif tiene == "extra":
                conteo["omitidas"] += 1
            else:
                conteo["erroneas"] += 1
        filas.append({"archivo": archivo, "columnas": len(interp.columnas), **conteo,
                      "preguntas": len(interp.preguntas)})
    return filas


def main() -> None:
    for modo in ("deterministico", "simulado"):
        filas = evaluar(modo)
        total = {k: sum(f[k] for f in filas) for k in ("columnas", "correctas", "omitidas", "erroneas", "preguntas")}
        print(f"\n## {modo}\n")
        print("| archivo | columnas | correctas | omitidas | erróneas | preguntas |")
        print("|---|---|---|---|---|---|")
        for f in filas:
            print(f"| {f['archivo']} | {f['columnas']} | {f['correctas']} | {f['omitidas']} | "
                  f"{f['erroneas']} | {f['preguntas']} |")
        print(f"| **total** | {total['columnas']} | {total['correctas']} | {total['omitidas']} | "
              f"{total['erroneas']} | {total['preguntas']} |")
        print(f"\nExactitud por columna: {total['correctas'] / total['columnas']:.0%}; "
              f"asignaciones erróneas: {total['erroneas']}.")


if __name__ == "__main__":
    main()

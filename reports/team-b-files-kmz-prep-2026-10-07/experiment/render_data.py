"""Build render_data.json for render_harness.html from the fictional fixtures.

DISPOSABLE. Three fictional terrains: a boundary with a hole and blank X/Y, a
two-part boundary with blank X/Y, and an X/Y-only terrain drawn exactly as the
current app draws it.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import kmz_experiment as k  # noqa: E402
import make_fixtures  # noqa: E402


def mover(geo: dict, dlon: float) -> dict:
    polis = [[[[x + dlon, y] for x, y in anillo] for anillo in p]
             for p in geo["geojson"]["coordinates"]]
    return k.normalizar(polis)


tmp = Path(tempfile.mkdtemp(prefix="kmz-render-"))
make_fixtures.main(tmp)
hueco = k.procesar((tmp / "02_poligono_con_hueco.kmz").read_bytes(), "x.kmz")["geometria"]
multi = mover(k.procesar((tmp / "03_multiparte.kmz").read_bytes(), "x.kmz")["geometria"], 0.009)

terrenos = [
    {"id": "t-hueco", "terreno": "Predio Ficticio Dos", "lat": None, "lon": None,
     "superficie_m2": None,
     "geometria": {"id": "g-1", "estado": "activa", "utilizable": True, **hueco}},
    {"id": "t-multi", "terreno": "Predio Ficticio Tres", "lat": None, "lon": None,
     "superficie_m2": None,
     "geometria": {"id": "g-2", "estado": "activa", "utilizable": True, **multi}},
    {"id": "t-xy", "terreno": "Predio Ficticio XY", "lat": 20.6075, "lon": -100.3965,
     "superficie_m2": 60000, "geometria": None},
]
(AQUI / "render_data.json").write_text(json.dumps(terrenos, indent=1) + "\n", encoding="utf-8")
print("render_data.json:", len(terrenos), "terrenos")

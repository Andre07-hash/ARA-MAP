"""Write example parser outputs for the supervisor's contract reconciliation.

    python3 reports/team-b-kmz-parser-2026-10-07/ejemplos.py

Inputs are the FICTIONAL fixtures in tests/fixtures/kmz/. Long coordinate
lists are kept whole: these are the exact results procesar_kmz returns.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from server import kmz  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures" / "kmz"
SALIDA = Path(__file__).resolve().parent / "ejemplos"


def paquete(*miembros: tuple[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, fixture in miembros:
            zf.writestr(nombre, (FIXTURES / f"{fixture}.kml").read_bytes())
    return buf.getvalue()


CASOS: dict[str, tuple[bytes, object]] = {
    "01-listo-poligono-con-hueco": (paquete(("doc.kml", "poligono_con_hueco")), None),
    "02-listo-con-avisos": (paquete(("doc.kml", "mixto_contorno_caminos_punto"),
                                    ("files/plano.png", "solo_puntos")), None),
    "03-requiere-seleccion": (paquete(("doc.kml", "ambiguo_tres_lotes")), None),
    "04-seleccion-de-dos-lotes": (paquete(("doc.kml", "ambiguo_tres_lotes")), [0, 2]),
    "05-seleccion-repetida": (paquete(("doc.kml", "ambiguo_tres_lotes")), [0, 0]),
    "06-seleccion-con-flotante": (paquete(("doc.kml", "ambiguo_tres_lotes")), [0.0]),
    "07-seleccion-encimada": (paquete(("doc.kml", "lotes_encimados")), [0, 1]),
    "08-valido-fuera-de-mexico": (paquete(("doc.kml", "fuera_de_mexico")), None),
    "09-rechazado-autointerseccion": (paquete(("doc.kml", "monio_autointerseccion")), None),
    "10-rechazado-vertices-repetidos": (paquete(("doc.kml", "cuatro_copias_mismo_punto")),
                                        None),
    "11-rechazado-sin-contorno": (paquete(("doc.kml", "solo_puntos")), None),
    "12-rechazado-varios-kml": (paquete(("doc.kml", "poligono_simple"),
                                        ("files/otro.kml", "multiparte")), None),
}


def main() -> None:
    SALIDA.mkdir(exist_ok=True)
    for nombre, (datos, seleccion) in CASOS.items():
        resultado = {"_entrada": {"seleccion": seleccion}, **kmz.procesar_kmz(datos, seleccion)}
        (SALIDA / f"{nombre}.json").write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

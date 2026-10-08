"""Generate the FICTIONAL large-KMZ display cases with B-1's exact parser.

Copied unchanged (apart from this docstring) from the display investigation,
PR #16, reports/team-b-display-strategy-2026-10-08/generar_casos.py @ 14254d6.

    python3 -I reports/team-b-boundary-path-drawing-2026-10-08/generar_casos.py <b1-dir> <out-dir>

<b1-dir> is an isolated extraction of the accepted B-1 parser:
    git archive efc362818ba64618dbfc23556db8678cde525336 | tar -x -C <b1-dir>
Each case is written as <out-dir>/<case>.json = {descriptor, cuerpo, procedencia}.
The outputs are 2-4 MB each and are NOT committed; this generator is
deterministic, and manifest.json records counts and SHA-256 of every output.

Every coordinate is invented (open country near 20.6 N, 100.4 W). The parser
validates each body exactly as the application would; nothing is simplified.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import sys
import time
import zipfile
from pathlib import Path

COMMIT_B1 = "efc362818ba64618dbfc23556db8678cde525336"
LON, LAT = -100.40, 20.60
Anillo = list[tuple[float, float]]


def cuadro(x: float, y: float, lado: float) -> Anillo:
    return [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado), (x, y)]


def poligono(anillo: Anillo) -> str:
    texto = " ".join(f"{p:.7f},{q:.7f}" for p, q in anillo)
    return (f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{texto}"
            "</coordinates></LinearRing></outerBoundaryIs></Polygon>")


def kmz(partes: list[Anillo]) -> bytes:
    cuerpo = "".join(poligono(a) for a in partes)
    if len(partes) > 1:
        cuerpo = f"<MultiGeometry>{cuerpo}</MultiGeometry>"
    kml = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2">'
           f"<Document><Placemark><name>Ficticio</name>{cuerpo}</Placemark></Document></kml>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml)
    return buf.getvalue()


def circulo(n: int, radio: float) -> list[Anillo]:
    """One ring of n positions (n - 1 distinct plus the closing one)."""
    anillo = [(LON + radio * math.cos(2 * math.pi * k / (n - 1)),
               LAT + radio * math.sin(2 * math.pi * k / (n - 1))) for k in range(n - 1)]
    return [anillo + [anillo[0]]]


def rejilla(n: int, columnas: int, paso: float, lado: float,
            evitar: tuple[float, float, float, float] | None = None,
            origen: tuple[float, float] = (LON, LAT)) -> list[Anillo]:
    """n squares on a regular grid, skipping cells that touch `evitar`."""
    partes: list[Anillo] = []
    k = 0
    while len(partes) < n:
        x = origen[0] + (k % columnas) * paso
        y = origen[1] + (k // columnas) * paso
        k += 1
        if evitar and not (x + lado < evitar[0] or x > evitar[2]
                           or y + lado < evitar[1] or y > evitar[3]):
            continue
        partes.append(cuadro(x, y, lado))
    return partes


def con_grande(lado_grande: float, n_chicas: int, columnas: int, paso: float,
               lado: float) -> list[Anillo]:
    """One large square centred in a grid of n_chicas small squares around it."""
    ancho = columnas * paso
    filas = math.ceil((n_chicas + (lado_grande / paso + 2) ** 2) / columnas)
    alto = filas * paso
    gx = LON + ancho / 2 - lado_grande / 2
    gy = LAT + alto / 2 - lado_grande / 2
    margen = paso
    grande = cuadro(gx, gy, lado_grande)
    chicas = rejilla(n_chicas, columnas, paso, lado,
                     evitar=(gx - margen, gy - margen,
                             gx + lado_grande + margen, gy + lado_grande + margen))
    return [grande] + chicas


# Case name -> parts. ~0.0009 deg = ~100 m; 0.045 deg = ~5 km at this latitude.
CASOS = {
    # B-2's three limit shapes, rebuilt deterministically.
    "circulo-100k": lambda: circulo(100_000, 0.02),
    "multiparte-20000": lambda: rejilla(20_000, 200, 0.004, 0.0009),
    "grande-mas-19999": lambda: con_grande(0.045, 19_999, 160, 0.0045, 0.0009),
    # Dense all-visible: the same counts packed tightly, so at the outline
    # zoom and one or two levels in, (nearly) every part is on screen.
    "denso-grande-mas-19999": lambda: con_grande(0.02, 19_999, 160, 0.0012, 0.0009),
}


def cargar_parser(directorio: Path):  # type: ignore[no-untyped-def]
    ruta = directorio / "server" / "kmz.py"
    if not ruta.is_file():
        raise SystemExit(f"no B-1 parser at {ruta}")
    sys.path.insert(0, str(directorio))
    spec = importlib.util.spec_from_file_location("server.kmz", ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["server.kmz"] = modulo
    spec.loader.exec_module(modulo)
    return modulo, hashlib.sha256(ruta.read_bytes()).hexdigest()


def main(directorio: Path, salida: Path) -> None:
    kmz_mod, huella = cargar_parser(directorio)
    salida.mkdir(parents=True, exist_ok=True)
    manifiesto = {"parser_commit": COMMIT_B1, "kmz_py_sha256": huella, "casos": {}}
    for nombre, construir in CASOS.items():
        partes = construir()
        datos = kmz(partes)
        t0 = time.perf_counter()
        r = kmz_mod.procesar_kmz(datos)
        segundos = time.perf_counter() - t0
        if r["estado"] != "listo":
            raise SystemExit(f"{nombre}: {r['estado']} {r['error']}")
        g = r["geometria"]
        cuerpo = {k: g[k] for k in ("geojson", "bbox", "punto_interior", "partes",
                                     "huecos", "vertices", "area_aproximada_m2")}
        descriptor = {"id": f"geo-{nombre}", "archivo_version_id": f"version-{nombre}",
                      "utilizable": bool(r["ubicacion"]["utilizable"]),
                      "bbox": g["bbox"], "punto_interior": g["punto_interior"]}
        texto = json.dumps({"descriptor": descriptor, "cuerpo": cuerpo,
                            "procedencia": {"parser_commit": COMMIT_B1,
                                            "kmz_py_sha256": huella}},
                           separators=(",", ":"))
        (salida / f"{nombre}.json").write_text(texto, encoding="utf-8")
        manifiesto["casos"][nombre] = {
            "partes": g["partes"], "huecos": g["huecos"], "vertices": g["vertices"],
            "bbox": g["bbox"], "utilizable": descriptor["utilizable"],
            "kmz_bytes": len(datos), "json_bytes": len(texto.encode()),
            "json_sha256": hashlib.sha256(texto.encode()).hexdigest(),
            "parser_s": round(segundos, 2)}
        print(nombre, json.dumps(manifiesto["casos"][nombre]))
    (salida / "manifest.json").write_text(json.dumps(manifiesto, indent=1) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())

"""Regenerate the FICTIONAL renderer fixture contornos.json with B-1's parser.

    python3 -I tests/js/fixtures/geometria/generar.py <b1-archive-dir>

<b1-archive-dir> is an isolated extraction of the accepted B-1 parser, for
example: git archive efc362818ba64618dbfc23556db8678cde525336 | tar -x -C DIR
The parser is loaded from that directory only; nothing here imports it into
the application. The output records the parser commit and the SHA-256 of the
kmz.py that produced it.

Every name and coordinate is invented: rough shapes in open country inside
Mexico, chosen only to exercise the renderer. Rows follow the shared contract
v1 example: a renderer row carries raw lat/lon (X = latitude, Y = longitude)
and t.geometria, the active descriptor; full bodies are keyed by geometry ID.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
COMMIT_B1 = "efc362818ba64618dbfc23556db8678cde525336"
LON, LAT = -100.40, 20.60


def anillo(x: float, y: float, dx: float, dy: float) -> list[tuple[float, float]]:
    return [(x, y), (x + dx, y), (x + dx, y + dy), (x, y + dy), (x, y)]


def poligono(*anillos: list[tuple[float, float]]) -> str:
    def texto(a: list[tuple[float, float]]) -> str:
        return " ".join(f"{p:.6f},{q:.6f}" for p, q in a)
    huecos = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{texto(h)}</coordinates>"
                     "</LinearRing></innerBoundaryIs>" for h in anillos[1:])
    return (f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{texto(anillos[0])}"
            f"</coordinates></LinearRing></outerBoundaryIs>{huecos}</Polygon>")


def kmz(geometria: str) -> bytes:
    kml = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2">'
           f"<Document><Placemark><name>Ficticio</name>{geometria}</Placemark></Document></kml>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml)
    return buf.getvalue()


# Geometry ID -> the fictional shape it is parsed from.
FORMAS = {
    "geo-simple": poligono(anillo(LON, LAT, 0.004, 0.003)),
    "geo-hueco": poligono(anillo(LON + 0.010, LAT, 0.006, 0.004),
                          anillo(LON + 0.012, LAT + 0.001, 0.002, 0.002)),
    "geo-multiparte": "<MultiGeometry>"
                      + poligono(anillo(LON + 0.020, LAT, 0.003, 0.003))
                      + poligono(anillo(LON + 0.026, LAT, 0.002, 0.003)) + "</MultiGeometry>",
    "geo-u": poligono([(LON, LAT + 0.010), (LON + 0.006, LAT + 0.010),
                       (LON + 0.006, LAT + 0.016), (LON + 0.004, LAT + 0.016),
                       (LON + 0.004, LAT + 0.012), (LON + 0.002, LAT + 0.012),
                       (LON + 0.002, LAT + 0.016), (LON, LAT + 0.016), (LON, LAT + 0.010)]),
    "geo-discrepa": poligono(anillo(LON + 0.010, LAT + 0.010, 0.004, 0.004)),
    "geo-reemplazo-anterior": poligono(anillo(LON + 0.020, LAT + 0.010, 0.004, 0.004)),
    # A newer upload for the same terrain that is still pending: present in the
    # bodies map but NOT the active descriptor, so it must never be drawn.
    "geo-reemplazo-pendiente": poligono(anillo(LON + 0.030, LAT + 0.020, 0.004, 0.004)),
    "geo-sin-cuerpo": poligono(anillo(LON + 0.030, LAT + 0.010, 0.003, 0.003)),
    # Valid shape outside Mexico: parsed, but never an active usable descriptor.
    "geo-fuera": poligono(anillo(-3.70, 40.40, 0.004, 0.003)),
    # Shares its interior point's neighbourhood with an XY terrain (coincidence).
    "geo-coincide": poligono(anillo(LON - 0.010, LAT, 0.002, 0.002)),
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


def main(directorio: Path) -> None:
    kmz_mod, huella = cargar_parser(directorio)
    cuerpos: dict[str, dict] = {}
    descriptores: dict[str, dict] = {}
    for gid, forma in FORMAS.items():
        r = kmz_mod.procesar_kmz(kmz(forma))
        assert r["estado"] == "listo", (gid, r["error"])
        g = r["geometria"]
        cuerpos[gid] = {k: g[k] for k in ("geojson", "bbox", "punto_interior", "partes",
                                           "huecos", "vertices", "area_aproximada_m2")}
        descriptores[gid] = {"id": gid, "archivo_version_id": f"version-{gid}",
                             "utilizable": bool(r["ubicacion"]["utilizable"]),
                             "bbox": g["bbox"], "punto_interior": g["punto_interior"]}

    coincide = descriptores["geo-coincide"]["punto_interior"]["coordinates"]
    filas = [
        {"id": "t-simple", "terreno": "Predio Ficticio Simple", "lat": None, "lon": None,
         "superficie_m2": None, "geometria": descriptores["geo-simple"]},
        {"id": "t-hueco", "terreno": "Predio Ficticio con Hueco", "lat": None, "lon": None,
         "superficie_m2": None, "geometria": descriptores["geo-hueco"]},
        {"id": "t-multiparte", "terreno": "Predio Ficticio Multiparte", "lat": None,
         "lon": None, "superficie_m2": None, "geometria": descriptores["geo-multiparte"]},
        {"id": "t-u", "terreno": "Predio Ficticio en U", "lat": None, "lon": None,
         "superficie_m2": 320000, "geometria": descriptores["geo-u"]},
        {"id": "t-xy", "terreno": "Predio Ficticio Solo XY", "lat": 20.6075, "lon": -100.3965,
         "superficie_m2": 60000, "geometria": None},
        {"id": "t-ninguna", "terreno": "Predio Ficticio Sin Ubicación", "lat": None,
         "lon": None, "superficie_m2": 1000, "geometria": None},
        # Valid X/Y far from its boundary: the boundary wins; X/Y stays as stored.
        {"id": "t-discrepa", "terreno": "Predio Ficticio Discrepante", "lat": 20.70,
         "lon": -100.50, "superficie_m2": 5000, "geometria": descriptores["geo-discrepa"]},
        # A failed/pending replacement: the descriptor is still the old layout.
        {"id": "t-reemplazo", "terreno": "Predio Ficticio Reemplazo", "lat": None,
         "lon": None, "superficie_m2": None, "geometria": descriptores["geo-reemplazo-anterior"]},
        # Active descriptor whose body is not loaded (absent from the map).
        {"id": "t-sin-cuerpo", "terreno": "Predio Ficticio <b>Sin</b> Cuerpo & \"comillas\"",
         "lat": 20.65, "lon": -100.45, "superficie_m2": None,
         "geometria": descriptores["geo-sin-cuerpo"]},
        # Unusable stored geometry is never active: valid X/Y keeps today's marker.
        {"id": "t-no-utilizable", "terreno": "Predio Ficticio No Utilizable", "lat": 20.62,
         "lon": -100.43, "superficie_m2": 8000, "geometria": descriptores["geo-fuera"]},
        {"id": "t-coincide-contorno", "terreno": "Predio Ficticio Coincide A", "lat": None,
         "lon": None, "superficie_m2": None, "geometria": descriptores["geo-coincide"]},
        {"id": "t-coincide-xy", "terreno": "Predio Ficticio Coincide B",
         "lat": coincide[1], "lon": coincide[0], "superficie_m2": 4000, "geometria": None},
    ]
    salida = {
        "_nota": "FICTIONAL renderer fixture. Generated by generar.py with the accepted "
                 "B-1 parser; rows follow shared contract v1 (renderer row: raw lat/lon + "
                 "t.geometria descriptor); bodies keyed by geometry ID. No real data.",
        "_procedencia": {"parser_commit": COMMIT_B1, "kmz_py_sha256": huella,
                         "generador": "tests/js/fixtures/geometria/generar.py"},
        "filas": filas,
        "cuerpos": cuerpos,
    }
    (AQUI / "contornos.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).resolve())

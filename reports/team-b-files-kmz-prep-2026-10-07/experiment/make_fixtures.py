"""Build the FICTIONAL KMZ/KML fixtures used by the Team B experiment.

Every shape, name and coordinate here is invented. None describes a real
terrain, owner or listing. Coordinates fall inside Mexico only so the
"located" rules can be exercised; they are rough rectangles in open country,
not surveyed parcels.

    python3 make_fixtures.py <output-dir>

Writes .kml sources and the .kmz packages built from them. Deterministic:
zip timestamps are fixed so rebuilding gives byte-identical files.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

NS = 'xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2"'
FECHA = (2026, 1, 1, 0, 0, 0)


def anillo(lon: float, lat: float, dlon: float, dlat: float, z: float | None = None) -> str:
    """A closed rectangle as KML coordinates: lon,lat[,alt] tuples."""
    pts = [(lon, lat), (lon + dlon, lat), (lon + dlon, lat + dlat), (lon, lat + dlat), (lon, lat)]
    if z is None:
        return " ".join(f"{a:.6f},{b:.6f}" for a, b in pts)
    return " ".join(f"{a:.6f},{b:.6f},{z:g}" for a, b in pts)


def poligono(exterior: str, *huecos: str, extra: str = "") -> str:
    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{h}</coordinates></LinearRing></innerBoundaryIs>"
        for h in huecos)
    return (f"<Polygon>{extra}<outerBoundaryIs><LinearRing><coordinates>{exterior}"
            f"</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>")


def doc(cuerpo: str, nombre: str = "Ficticio") -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<kml {NS}><Document>'
            f"<name>{nombre}</name>{cuerpo}</Document></kml>\n")


def placemark(nombre: str, geom: str) -> str:
    return f"<Placemark><name>{nombre}</name>{geom}</Placemark>"


# Base point: open country, arbitrary. ~0.004° ≈ 400 m.
LON, LAT = -100.400000, 20.600000

KML = {
    "01_poligono_simple": doc(placemark(
        "Predio Ficticio Uno", poligono(anillo(LON, LAT, 0.004, 0.003)))),
    "02_poligono_con_hueco": doc(placemark(
        "Predio Ficticio Dos", poligono(anillo(LON, LAT, 0.006, 0.004),
                                        anillo(LON + 0.002, LAT + 0.001, 0.001, 0.001)))),
    "03_multiparte": doc(placemark(
        "Predio Ficticio Tres",
        "<MultiGeometry>"
        + poligono(anillo(LON, LAT, 0.003, 0.003))
        + poligono(anillo(LON + 0.005, LAT, 0.002, 0.003))
        + "</MultiGeometry>")),
    "04_ambiguo_varios_lotes": doc(
        "<Folder><name>Lotes ficticios</name>"
        + placemark("Lote A", poligono(anillo(LON, LAT, 0.002, 0.002)))
        + placemark("Lote B", poligono(anillo(LON + 0.0025, LAT, 0.002, 0.002)))
        + placemark("Lote C", poligono(anillo(LON + 0.005, LAT, 0.002, 0.002)))
        + "</Folder>"),
    "05_solo_puntos": doc(
        placemark("Marca ficticia", f"<Point><coordinates>{LON},{LAT}</coordinates></Point>")),
    "06_solo_lineas": doc(placemark(
        "Camino ficticio",
        f"<LineString><coordinates>{LON},{LAT} {LON + 0.01},{LAT + 0.01}</coordinates>"
        "</LineString>")),
    "07_mixto_contorno_y_caminos": doc(
        placemark("Predio Ficticio Siete", poligono(anillo(LON, LAT, 0.004, 0.004)))
        + placemark("Camino interno", f"<LineString><coordinates>{LON},{LAT + 0.002} "
                    f"{LON + 0.004},{LAT + 0.002}</coordinates></LineString>")
        + placemark("Acceso", f"<Point><coordinates>{LON},{LAT}</coordinates></Point>")),
    "08_enlace_de_red": doc(
        "<NetworkLink><name>Remoto ficticio</name><Link>"
        "<href>https://example.invalid/capa.kml</href></Link></NetworkLink>"),
    "09_entidades_dtd": (
        '<?xml version="1.0"?>\n<!DOCTYPE kml [<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        f"<kml {NS}><Document><name>&b;</name></Document></kml>\n"),
    "10_altitud_3d": doc(placemark(
        "Predio Ficticio Diez",
        poligono(anillo(LON, LAT, 0.003, 0.003, z=25),
                 extra="<extrude>1</extrude><altitudeMode>relativeToGround</altitudeMode>"))),
    # X/Y-style mistake: latitude written first. For Mexico this puts a
    # longitude near -100 in the latitude slot, which is out of range.
    "11_orden_invertido": doc(placemark(
        "Predio Ficticio Once",
        poligono(" ".join(f"{b:.6f},{a:.6f}" for a, b in
                          [(LON, LAT), (LON + .004, LAT), (LON + .004, LAT + .003),
                           (LON, LAT + .003), (LON, LAT)])))),
    # In range but outside Mexico: stored, never drawn until reviewed.
    "14_fuera_de_mexico": doc(placemark(
        "Predio Ficticio Catorce", poligono(anillo(-3.700000, 40.400000, 0.004, 0.003)))),
    "12_anillo_corto": doc(placemark(
        "Predio Ficticio Doce",
        poligono(f"{LON},{LAT} {LON + 0.001},{LAT}"))),
    "13_xml_roto": doc(placemark("Roto", "<Polygon><outerBoundaryIs>")),
}


def kmz(destino: Path, miembros: dict[str, bytes]) -> None:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, datos in miembros.items():
            info = zipfile.ZipInfo(nombre, FECHA)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, datos)


def main(salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, texto in KML.items():
        (salida / f"{nombre}.kml").write_text(texto, encoding="utf-8")
        kmz(salida / f"{nombre}.kmz", {"doc.kml": texto.encode("utf-8")})

    simple = KML["01_poligono_simple"].encode("utf-8")
    # Package-level cases.
    kmz(salida / "20_kmz_con_imagen_y_files.kmz",
        {"doc.kml": simple, "files/plano.png": b"\x89PNG ficticio",
         "files/extra.kml": KML["05_solo_puntos"].encode("utf-8")})
    kmz(salida / "21_kmz_varios_kml_sin_doc.kmz",
        {"a.kml": simple, "b.kml": KML["03_multiparte"].encode("utf-8")})
    kmz(salida / "22_kmz_sin_kml.kmz", {"files/plano.png": b"\x89PNG ficticio"})
    # Highly compressible payload: a zip-bomb stand-in (8 MB of spaces).
    kmz(salida / "23_kmz_expansion_excesiva.kmz",
        {"doc.kml": simple[:-8] + b" " * (8 * 1024 * 1024) + simple[-8:]})
    (salida / "24_no_es_zip.kmz").write_bytes(b"esto no es un zip ficticio")
    kmz(salida / "25_overlay_sin_contorno.kmz",
        {"doc.kml": doc("<GroundOverlay><name>Plano</name><Icon><href>files/plano.png"
                        "</href></Icon></GroundOverlay>").encode("utf-8"),
         "files/plano.png": b"\x89PNG ficticio"})


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures"))

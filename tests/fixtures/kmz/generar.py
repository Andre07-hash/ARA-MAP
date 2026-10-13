"""Regenerate the FICTIONAL KML fixtures in this folder.

    python3 tests/fixtures/kmz/generar.py

Every name, shape and coordinate is invented: rough rectangles in open
country, not surveyed parcels, owners or listings. Coordinates sit inside
Mexico only so the location rules can be exercised. The tests package each
document into a KMZ in memory; nothing here is a real company file.
"""

from __future__ import annotations

from pathlib import Path

AQUI = Path(__file__).resolve().parent
NS = 'xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2"'

# Base point in open country; 0.001 degree is roughly 100 m here.
LON, LAT = -100.400000, 20.600000


def coords(puntos: list[tuple[float, float]], z: float | None = None) -> str:
    if z is None:
        return " ".join(f"{x:.6f},{y:.6f}" for x, y in puntos)
    return " ".join(f"{x:.6f},{y:.6f},{z:g}" for x, y in puntos)


def rect(x: float, y: float, dx: float, dy: float) -> list[tuple[float, float]]:
    """A closed counter-clockwise rectangle, [lon, lat] corners."""
    return [(x, y), (x + dx, y), (x + dx, y + dy), (x, y + dy), (x, y)]


def poligono(exterior: str, *huecos: str, extra: str = "") -> str:
    interiores = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{h}</coordinates></LinearRing>"
        "</innerBoundaryIs>" for h in huecos)
    return (f"<Polygon>{extra}<outerBoundaryIs><LinearRing><coordinates>{exterior}"
            f"</coordinates></LinearRing></outerBoundaryIs>{interiores}</Polygon>")


def placemark(nombre: str, geometria: str) -> str:
    return f"<Placemark><name>{nombre}</name>{geometria}</Placemark>"


def documento(cuerpo: str, nombre: str = "Documento ficticio", ns: str = NS) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<kml {ns}><Document>'
            f"<name>{nombre}</name>{cuerpo}</Document></kml>\n")


def punto(x: float, y: float) -> str:
    return f"<Point><coordinates>{x:.6f},{y:.6f}</coordinates></Point>"


def linea(*puntos: tuple[float, float]) -> str:
    return f"<LineString><coordinates>{coords(list(puntos))}</coordinates></LineString>"


R = rect(LON, LAT, 0.004, 0.003)

FIXTURES = {
    # Accepted shapes -------------------------------------------------------
    "poligono_simple": documento(placemark("Predio Ficticio Uno", poligono(coords(R)))),
    "poligono_con_hueco": documento(placemark(
        "Predio Ficticio Dos",
        poligono(coords(rect(LON, LAT, 0.006, 0.004)),
                 coords(rect(LON + 0.002, LAT + 0.001, 0.001, 0.001))))),
    "multiparte": documento(placemark(
        "Predio Ficticio Tres",
        "<MultiGeometry>"
        + poligono(coords(rect(LON, LAT, 0.003, 0.003)))
        + poligono(coords(rect(LON + 0.005, LAT, 0.002, 0.003)))
        + "</MultiGeometry>")),
    # A U shape: the centre of its bounding box falls in the notch, outside.
    "forma_u": documento(placemark("Predio Ficticio en U", poligono(coords([
        (LON, LAT), (LON + 0.006, LAT), (LON + 0.006, LAT + 0.006),
        (LON + 0.004, LAT + 0.006), (LON + 0.004, LAT + 0.002),
        (LON + 0.002, LAT + 0.002), (LON + 0.002, LAT + 0.006),
        (LON, LAT + 0.006), (LON, LAT)])))),
    "mixto_contorno_caminos_punto": documento(
        placemark("Predio Ficticio Siete", poligono(coords(rect(LON, LAT, 0.004, 0.004))))
        + placemark("Camino interno", linea((LON, LAT + 0.002), (LON + 0.004, LAT + 0.002)))
        + placemark("Acceso", punto(LON, LAT))),
    "altitud_3d": documento(placemark(
        "Predio Ficticio Diez",
        poligono(coords(R, z=25),
                 extra="<extrude>1</extrude><altitudeMode>relativeToGround</altitudeMode>"))),
    "sin_espacio_de_nombres": documento(
        placemark("Predio Ficticio Sin Espacio", poligono(coords(R))), ns=""),
    "fuera_de_mexico": documento(placemark(
        "Predio Ficticio Catorce", poligono(coords(rect(-3.700000, 40.400000, 0.004, 0.003))))),
    "punto_repetido_consecutivo": documento(placemark(
        "Predio Ficticio Repetido",
        poligono(coords([R[0], R[1], R[1], R[2], R[3], R[4]])))),

    # Several candidates ----------------------------------------------------
    "ambiguo_tres_lotes": documento(
        "<Folder><name>Lotes ficticios</name>"
        + placemark("Lote A", poligono(coords(rect(LON, LAT, 0.002, 0.002))))
        + placemark("Lote B", poligono(coords(rect(LON + 0.0025, LAT, 0.002, 0.002))))
        + placemark("Lote C", poligono(coords(rect(LON + 0.005, LAT, 0.002, 0.002))))
        + "</Folder>"),
    "lotes_contiguos": documento(
        placemark("Lote Norte", poligono(coords(rect(LON, LAT + 0.002, 0.002, 0.002))))
        + placemark("Lote Sur", poligono(coords(rect(LON, LAT, 0.002, 0.002))))),
    "lotes_encimados": documento(
        placemark("Lote Uno", poligono(coords(rect(LON, LAT, 0.003, 0.003))))
        + placemark("Lote Dos", poligono(coords(rect(LON + 0.002, LAT + 0.002, 0.003, 0.003))))),
    "lotes_copia": documento(
        placemark("Lote Original", poligono(coords(R)))
        + placemark("Lote Copia", poligono(coords(R)))),
    "lotes_uno_invalido": documento(
        placemark("Lote Bueno", poligono(coords(R)))
        + placemark("Lote Moño", poligono(coords([
            (LON, LAT), (LON + 0.004, LAT + 0.003), (LON, LAT + 0.003),
            (LON + 0.004, LAT), (LON, LAT)])))),

    # Invalid shapes (supervisor probes first) -------------------------------
    "cuatro_copias_mismo_punto": documento(placemark(
        "Predio Ficticio Degenerado", poligono(coords([(LON, LAT)] * 4)))),
    "monio_autointerseccion": documento(placemark("Predio Ficticio Moño", poligono(coords([
        (LON, LAT), (LON + 0.004, LAT + 0.003), (LON, LAT + 0.003),
        (LON + 0.004, LAT), (LON, LAT)])))),
    "anillo_abierto": documento(placemark("Predio Ficticio Abierto", poligono(coords(R[:-1])))),
    "anillo_corto": documento(placemark(
        "Predio Ficticio Corto", poligono(coords([(LON, LAT), (LON + 0.001, LAT), (LON, LAT)])))),
    "colineal_sin_area": documento(placemark("Predio Ficticio Línea", poligono(coords([
        (LON, LAT), (LON + 0.001, LAT), (LON + 0.002, LAT), (LON, LAT)])))),
    "pico_de_retroceso": documento(placemark("Predio Ficticio Pico", poligono(coords([
        (LON, LAT), (LON + 0.004, LAT), (LON + 0.006, LAT), (LON + 0.004, LAT),
        (LON + 0.004, LAT + 0.003), (LON, LAT + 0.003), (LON, LAT)])))),
    "hueco_fuera": documento(placemark(
        "Predio Ficticio Hueco Fuera",
        poligono(coords(R), coords(rect(LON + 0.01, LAT, 0.001, 0.001))))),
    "hueco_toca_borde": documento(placemark(
        "Predio Ficticio Hueco Toca",
        poligono(coords(R), coords(rect(LON, LAT + 0.001, 0.001, 0.001))))),
    "hueco_cruza_borde": documento(placemark(
        "Predio Ficticio Hueco Cruza",
        poligono(coords(R), coords(rect(LON - 0.0005, LAT + 0.001, 0.001, 0.001))))),
    "huecos_anidados": documento(placemark(
        "Predio Ficticio Huecos Anidados",
        poligono(coords(rect(LON, LAT, 0.006, 0.006)),
                 coords(rect(LON + 0.001, LAT + 0.001, 0.004, 0.004)),
                 coords(rect(LON + 0.002, LAT + 0.002, 0.001, 0.001))))),
    "dos_bordes_exteriores": documento(placemark(
        "Predio Ficticio Doble Exterior",
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>" + coords(R)
        + "</coordinates></LinearRing></outerBoundaryIs><outerBoundaryIs><LinearRing>"
        "<coordinates>" + coords(rect(LON + 0.01, LAT, 0.001, 0.001))
        + "</coordinates></LinearRing></outerBoundaryIs></Polygon>")),
    "multiparte_encimada": documento(placemark(
        "Predio Ficticio Partes Encimadas",
        "<MultiGeometry>" + poligono(coords(rect(LON, LAT, 0.003, 0.003)))
        + poligono(coords(rect(LON + 0.001, LAT + 0.001, 0.003, 0.003))) + "</MultiGeometry>")),

    # Files with no usable boundary ------------------------------------------
    "solo_puntos": documento(placemark("Marca ficticia", punto(LON, LAT))),
    "solo_lineas": documento(placemark(
        "Camino ficticio", linea((LON, LAT), (LON + 0.01, LAT + 0.01)))),
    "enlace_de_red": documento(
        "<NetworkLink><name>Remoto ficticio</name><Link>"
        "<href>https://example.invalid/capa.kml</href></Link></NetworkLink>"),
    "superposicion_de_imagen": documento(
        "<GroundOverlay><name>Plano ficticio</name><Icon><href>files/plano.png</href></Icon>"
        "</GroundOverlay>"),
    "documento_vacio": documento(""),

    # Malformed text ----------------------------------------------------------
    "entidades_dtd": (
        '<?xml version="1.0"?>\n<!DOCTYPE kml [<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        f"<kml {NS}><Document><name>&b;</name></Document></kml>\n"),
    "entidad_externa": (
        '<?xml version="1.0"?>\n<!DOCTYPE kml [<!ENTITY x SYSTEM "file:///etc/hostname">]>'
        f"<kml {NS}><Document><name>&x;</name></Document></kml>\n"),
    "xml_roto": documento(placemark("Roto", "<Polygon><outerBoundaryIs>")),
    # Latitude written first: Mexican longitudes are out of range as latitude.
    "orden_invertido": documento(placemark(
        "Predio Ficticio Once", poligono(" ".join(f"{y:.6f},{x:.6f}" for x, y in R)))),
    "coordenada_con_espacio": documento(placemark(
        "Predio Ficticio Espacios",
        poligono(" ".join(f"{x:.6f}, {y:.6f}" for x, y in R)))),
    "coordenada_con_guion_bajo": documento(placemark(
        "Predio Ficticio Guion", poligono(coords(R).replace("-100.400000", "-100.400_000", 1)))),
    "coordenada_nan": documento(placemark(
        "Predio Ficticio NaN", poligono(coords(R).replace("20.600000", "nan", 1)))),
}


def main() -> None:
    for nombre, texto in FIXTURES.items():
        (AQUI / f"{nombre}.kml").write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    main()

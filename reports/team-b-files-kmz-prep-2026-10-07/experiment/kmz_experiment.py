"""DISPOSABLE feasibility experiment: bounded KMZ/KML -> normalized boundary.

Not application code. It lives in this report folder to support the Team B
preparation report and must not be imported by ``server/``. The production
module is proposed in the report (``server/kmz.py``) and will be written under
the supervisor's implementation packet, with its own tests.

Standard library only, Python 3.9 compatible, so the same approach can run in
the local Mac app and on Vercel without a new dependency.

Output geometry is GeoJSON, whose positions are [longitude, latitude] -- the
same order as KML. ARA's X/Y columns are latitude/longitude; this module never
reads or writes them.
"""

from __future__ import annotations

import io
import json
import math
import sys
import xml.parsers.expat
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import Element, TreeBuilder

# --------------------------------------------------------------------- limits
# Proposed defaults; the real values are decided with sample files (Phase 4).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024        # the KMZ as uploaded
MAX_ENTRIES = 500                           # members in the archive
MAX_KML_BYTES = 20 * 1024 * 1024            # the expanded KML document
MAX_TOTAL_EXPANDED = 60 * 1024 * 1024       # sum of declared member sizes
MAX_RATIO = 200                             # expanded / compressed, per member
MAX_VERTICES = 200_000                      # across every kept polygon
MAX_PLACEMARKS = 5_000
MAX_DEPTH = 64                              # XML nesting

# Same bounds as server/validation.py, so "located" means the same thing for a
# boundary as for an X/Y pair.
MEXICO_LAT = (14.0, 33.0)
MEXICO_LON = (-118.5, -86.0)

EARTH_RADIUS_M = 6_378_137.0


class KmzError(Exception):
    """A file that cannot produce a boundary. ``codigo`` is stable; ``mensaje``
    is the plain-language Spanish text an employee sees."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass
class Candidato:
    """One placemark that carries at least one polygon."""
    indice: int
    nombre: str | None
    carpeta: list[str]
    poligonos: list[list[list[list[float]]]]   # GeoJSON MultiPolygon coordinates
    vertices: int


@dataclass
class Resultado:
    estado: str                                 # listo | requiere_eleccion
    candidatos: list[Candidato]
    avisos: list[dict[str, str]] = field(default_factory=list)
    ignorados: dict[str, int] = field(default_factory=dict)
    documento: str = ""


# ------------------------------------------------------------------ archive

def leer_paquete(datos: bytes, nombre: str) -> tuple[bytes, str, list[dict[str, str]]]:
    """Return (kml bytes, member name, warnings) from a .kmz or a bare .kml."""
    if len(datos) > MAX_UPLOAD_BYTES:
        raise KmzError("ARCHIVO_DEMASIADO_GRANDE",
                       "El archivo supera el tamaño máximo permitido para un KMZ.")
    if nombre.lower().endswith(".kml"):
        return datos, nombre, []
    if not zipfile.is_zipfile(io.BytesIO(datos)):
        raise KmzError("KMZ_NO_ES_ZIP",
                       "El archivo no es un KMZ válido (no es un paquete comprimido).")

    avisos: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(datos)) as zf:
        miembros = zf.infolist()
        if len(miembros) > MAX_ENTRIES:
            raise KmzError("KMZ_DEMASIADOS_ARCHIVOS",
                           "El KMZ contiene demasiados archivos internos.")
        total = 0
        for m in miembros:
            total += m.file_size
            if m.compress_size and m.file_size / max(m.compress_size, 1) > MAX_RATIO:
                raise KmzError("KMZ_EXPANSION_EXCESIVA",
                               "El KMZ se expande de forma anómala y no se procesó.")
        if total > MAX_TOTAL_EXPANDED:
            raise KmzError("KMZ_EXPANSION_EXCESIVA",
                           "El contenido del KMZ es demasiado grande al descomprimirlo.")

        kmls = [m for m in miembros
                if not m.is_dir() and m.filename.lower().endswith(".kml")]
        if not kmls:
            raise KmzError("KMZ_SIN_KML", "El KMZ no contiene ningún documento KML.")
        # Google's convention: one root document, normally doc.kml. Several
        # documents with no doc.kml is ambiguous -- never take the first.
        raiz = [m for m in kmls if "/" not in m.filename]
        doc = [m for m in raiz if m.filename.lower() == "doc.kml"]
        if doc:
            elegido = doc[0]
        elif len(raiz) == 1:
            elegido = raiz[0]
        elif len(kmls) == 1:
            elegido = kmls[0]
        else:
            raise KmzError("KMZ_VARIOS_KML",
                           "El KMZ contiene varios documentos KML y no indica cuál usar.")
        if len(kmls) > 1:
            avisos.append({"codigo": "KMZ_KML_ADICIONALES",
                           "mensaje": "Se usó el documento principal; los demás KML "
                                      "del paquete no se procesaron."})
        if elegido.file_size > MAX_KML_BYTES:
            raise KmzError("KML_DEMASIADO_GRANDE", "El documento KML es demasiado grande.")
        # Read in bounded chunks: the declared size is not trusted.
        buf = bytearray()
        with zf.open(elegido) as fh:
            while True:
                trozo = fh.read(64 * 1024)
                if not trozo:
                    break
                buf.extend(trozo)
                if len(buf) > MAX_KML_BYTES:
                    raise KmzError("KML_DEMASIADO_GRANDE",
                                   "El documento KML es demasiado grande.")
        return bytes(buf), elegido.filename, avisos


# ---------------------------------------------------------------------- XML

def parsear_xml(datos: bytes) -> Element:
    """Parse with expat directly so any DTD or entity declaration is refused.

    That closes entity-expansion ("billion laughs") and external-entity
    attacks without a third-party parser.
    """
    builder = TreeBuilder()
    parser = xml.parsers.expat.ParserCreate(namespace_separator="}")
    profundidad = [0]

    def rechazar_dtd(*_args: Any) -> None:
        raise KmzError("KML_DTD_NO_PERMITIDA",
                       "El KML contiene declaraciones no permitidas (DTD/entidades).")

    def inicio(nombre: str, attrs: dict[str, str]) -> None:
        profundidad[0] += 1
        if profundidad[0] > MAX_DEPTH:
            raise KmzError("KML_DEMASIADO_ANIDADO", "El KML está anidado en exceso.")
        builder.start(_local(nombre), attrs)

    def fin(nombre: str) -> None:
        profundidad[0] -= 1
        builder.end(_local(nombre))

    parser.StartDoctypeDeclHandler = rechazar_dtd
    parser.EntityDeclHandler = rechazar_dtd
    parser.ExternalEntityRefHandler = rechazar_dtd
    parser.StartElementHandler = inicio
    parser.EndElementHandler = fin
    parser.CharacterDataHandler = builder.data
    try:
        parser.Parse(datos, True)
    except xml.parsers.expat.ExpatError as exc:
        raise KmzError("KML_XML_INVALIDO",
                       f"El KML no es XML válido (línea {exc.lineno}).") from None
    return builder.close()


def _local(nombre: str) -> str:
    # Namespaces vary (KML 2.0/2.1/2.2, gx:, none). Match on local names.
    return nombre.rsplit("}", 1)[-1]


# ------------------------------------------------------------------ geometry

NO_SOPORTADO = ("Point", "LineString", "GroundOverlay", "ScreenOverlay",
                "PhotoOverlay", "Model", "Track", "MultiTrack", "NetworkLink")


def extraer(raiz: Element, documento: str = "") -> Resultado:
    avisos: list[dict[str, str]] = []
    ignorados: dict[str, int] = {}
    candidatos: list[Candidato] = []
    placemarks = 0
    vertices_total = 0
    altitud = False

    def recorrer(nodo: Element, carpeta: list[str]) -> None:
        nonlocal placemarks, vertices_total, altitud
        for hijo in nodo:
            tag = hijo.tag
            if tag in ("Folder", "Document"):
                recorrer(hijo, [*carpeta, _texto(hijo, "name") or tag])
            elif tag == "Placemark":
                placemarks += 1
                if placemarks > MAX_PLACEMARKS:
                    raise KmzError("KML_DEMASIADOS_ELEMENTOS",
                                   "El KML tiene demasiados elementos para procesarse.")
                polis: list[list[list[list[float]]]] = []
                for geom in hijo.iter():
                    if geom.tag == "Polygon":
                        poli, z = _poligono(geom)
                        altitud = altitud or z or _extruido(geom)
                        polis.append(poli)
                    elif geom.tag in NO_SOPORTADO:
                        ignorados[geom.tag] = ignorados.get(geom.tag, 0) + 1
                if polis:
                    n = sum(len(anillo) for p in polis for anillo in p)
                    vertices_total += n
                    if vertices_total > MAX_VERTICES:
                        raise KmzError("KML_DEMASIADOS_VERTICES",
                                       "El contorno es demasiado complejo para procesarse.")
                    candidatos.append(Candidato(len(candidatos), _texto(hijo, "name"),
                                                carpeta, polis, n))
            elif tag in NO_SOPORTADO:
                # Overlays and network links outside placemarks. A link is
                # recorded, never fetched.
                ignorados[tag] = ignorados.get(tag, 0) + 1
            else:
                recorrer(hijo, carpeta)

    recorrer(raiz, [])

    if ignorados.get("NetworkLink"):
        avisos.append({"codigo": "KML_ENLACE_EXTERNO",
                       "mensaje": "El archivo enlaza contenido externo; no se descargó."})
    if altitud:
        avisos.append({"codigo": "KML_ALTITUD_DESCARTADA",
                       "mensaje": "Se usó el contorno en 2D; la altura del archivo no "
                                  "se muestra."})
    otros = {k: v for k, v in ignorados.items() if k != "NetworkLink"}
    if candidatos and otros:
        avisos.append({"codigo": "KML_CONTENIDO_IGNORADO",
                       "mensaje": "Se ignoraron elementos que no son contornos: "
                                  + ", ".join(f"{v} {k}" for k, v in sorted(otros.items()))})

    if not candidatos:
        if ignorados:
            raise KmzError("KML_SIN_POLIGONOS",
                           "El archivo no contiene un contorno de terreno (solo "
                           + ", ".join(sorted(ignorados)) + ").")
        raise KmzError("KML_SIN_POLIGONOS", "El archivo no contiene un contorno de terreno.")

    estado = "listo" if len(candidatos) == 1 else "requiere_eleccion"
    return Resultado(estado, candidatos, avisos, ignorados, documento)


def _texto(nodo: Element, tag: str) -> str | None:
    for hijo in nodo:
        if hijo.tag == tag and hijo.text and hijo.text.strip():
            return hijo.text.strip()
    return None


def _extruido(poligono: Element) -> bool:
    for hijo in poligono:
        if hijo.tag == "extrude" and (hijo.text or "").strip() == "1":
            return True
        if hijo.tag == "altitudeMode" and (hijo.text or "").strip() not in ("", "clampToGround"):
            return True
    return False


def _poligono(nodo: Element) -> tuple[list[list[list[float]]], bool]:
    exterior: list[list[float]] | None = None
    huecos: list[list[list[float]]] = []
    z = False
    for hijo in nodo:
        if hijo.tag in ("outerBoundaryIs", "innerBoundaryIs"):
            for anillo in hijo.iter("LinearRing"):
                coords, tiene_z = _anillo(anillo)
                z = z or tiene_z
                if hijo.tag == "outerBoundaryIs":
                    if exterior is not None:
                        raise KmzError("KML_ANILLO_INVALIDO",
                                       "Un polígono del KML tiene más de un borde exterior.")
                    exterior = coords
                else:
                    huecos.append(coords)
    if exterior is None:
        raise KmzError("KML_ANILLO_INVALIDO", "Un polígono del KML no tiene borde exterior.")
    return [exterior, *huecos], z


def _anillo(nodo: Element) -> tuple[list[list[float]], bool]:
    texto = ""
    for hijo in nodo:
        if hijo.tag == "coordinates":
            texto = hijo.text or ""
    puntos: list[list[float]] = []
    z = False
    for tupla in texto.split():
        partes = tupla.split(",")
        if len(partes) not in (2, 3):
            raise KmzError("KML_COORDENADAS_INVALIDAS",
                           "El KML tiene coordenadas con un formato inválido.")
        try:
            lon, lat = float(partes[0]), float(partes[1])
            if len(partes) == 3 and float(partes[2]) != 0:
                z = True
        except ValueError:
            raise KmzError("KML_COORDENADAS_INVALIDAS",
                           "El KML tiene coordenadas que no son números.") from None
        # KML order is longitude, latitude. Never swap silently.
        if not (math.isfinite(lon) and math.isfinite(lat)
                and -180 <= lon <= 180 and -90 <= lat <= 90):
            raise KmzError("KML_COORDENADAS_INVALIDAS",
                           "El KML tiene coordenadas fuera de rango.")
        puntos.append([lon, lat])
    if puntos and puntos[0] != puntos[-1]:
        puntos.append(list(puntos[0]))      # close the ring; the original is kept
    if len(puntos) < 4:
        raise KmzError("KML_ANILLO_INVALIDO",
                       "Un contorno del KML tiene menos de tres vértices.")
    return puntos, z


# ----------------------------------------------------------- normalization

def normalizar(polis: list[list[list[list[float]]]]) -> dict[str, Any]:
    """The geometry-version payload for one chosen boundary."""
    lons = [p[0] for poli in polis for anillo in poli for p in anillo]
    lats = [p[1] for poli in polis for anillo in poli for p in anillo]
    bbox = [min(lons), min(lats), max(lons), max(lats)]
    area = sum(_area_anillo(poli[0]) - sum(_area_anillo(h) for h in poli[1:])
               for poli in polis)
    dentro = (MEXICO_LAT[0] <= bbox[1] and bbox[3] <= MEXICO_LAT[1]
              and MEXICO_LON[0] <= bbox[0] and bbox[2] <= MEXICO_LON[1])
    mayor = max(polis, key=lambda p: _area_anillo(p[0]))
    return {
        "geojson": {"type": "MultiPolygon", "coordinates": polis},
        "bbox": bbox,                                 # [oeste, sur, este, norte]
        # A representative point for the zoomed-out symbol ONLY. Never written
        # into X/Y. Proposed: the centre of the largest part's bounding box;
        # production should use a point guaranteed inside (pole of
        # inaccessibility) for L- or U-shaped parcels.
        "punto_simbolo": _centro_caja(mayor[0]),     # [lat, lon], Leaflet order
        "area_calculada_m2": round(area, 1),
        "partes": len(polis),
        "huecos": sum(len(p) - 1 for p in polis),
        "vertices": sum(len(a) for p in polis for a in p),
        "dentro_de_mexico": dentro,
    }


def _centro_caja(anillo: list[list[float]]) -> list[float]:
    lons = [p[0] for p in anillo]
    lats = [p[1] for p in anillo]
    return [(min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2]


def _area_anillo(anillo: list[list[float]]) -> float:
    """Spherical ring area in m² (same approximation Leaflet.draw/Turf use)."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(anillo, anillo[1:]):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(total * EARTH_RADIUS_M ** 2 / 2)


# ---------------------------------------------------------------- pipeline

def procesar(datos: bytes, nombre: str, eleccion: list[int] | None = None) -> dict[str, Any]:
    """Full pipeline as the proposed `completar` step would run it.

    ``eleccion`` models the explicit user choice for an ambiguous file: the
    candidate indices to combine into one terrain boundary.
    """
    try:
        kml, miembro, avisos_paquete = leer_paquete(datos, nombre)
        res = extraer(parsear_xml(kml), miembro)
    except KmzError as exc:
        return {"estado": "fallido", "error": {"codigo": exc.codigo, "mensaje": exc.mensaje}}

    avisos = avisos_paquete + res.avisos
    resumen = [{"indice": c.indice, "nombre": c.nombre, "carpeta": c.carpeta,
                "partes": len(c.poligonos), "vertices": c.vertices,
                "area_calculada_m2": normalizar(c.poligonos)["area_calculada_m2"]}
               for c in res.candidatos]

    if res.estado == "requiere_eleccion" and eleccion is None:
        return {"estado": "requiere_eleccion", "documento": miembro,
                "candidatos": resumen, "avisos": avisos}

    indices = eleccion if eleccion is not None else [0]
    if not indices or any(i not in range(len(res.candidatos)) for i in indices):
        return {"estado": "requiere_eleccion", "documento": miembro, "candidatos": resumen,
                "avisos": avisos, "error": {"codigo": "ELECCION_INVALIDA",
                                            "mensaje": "La selección no corresponde al archivo."}}
    polis = [p for i in indices for p in res.candidatos[i].poligonos]
    geometria = normalizar(polis)
    if not geometria["dentro_de_mexico"]:
        avisos.append({"codigo": "GEOMETRIA_FUERA_DE_MEXICO",
                       "mensaje": "El contorno cae fuera de México; se guardó pero no se "
                                  "dibuja hasta revisarlo."})
    return {"estado": "listo", "documento": miembro, "candidatos": resumen,
            "eleccion": indices, "geometria": geometria, "avisos": avisos,
            "utilizable": geometria["dentro_de_mexico"]}


if __name__ == "__main__":
    for ruta in sys.argv[1:]:
        with open(ruta, "rb") as fh:
            salida = procesar(fh.read(), ruta)
        if "geometria" in salida:
            salida["geometria"]["geojson"] = f"<{salida['geometria']['vertices']} vértices>"
        print(ruta.rsplit("/", 1)[-1], json.dumps(salida, ensure_ascii=False))

"""KMZ layout files -> one validated terrain boundary.

A pure function over bytes: no database, network, filesystem, identity or UI.
Nothing in the application imports this module yet; wiring it to uploads, the
attachment tables and the map is later work under the shared contract.

    procesar_kmz(datos, seleccion=None) -> dict

The result's ``estado`` is a PROCESSING outcome, kept apart from any future
attachment/persistence state:

- ``listo``: one validated boundary is returned in ``geometria``.
- ``requiere_seleccion``: several placemarks carry polygons. Nothing is chosen
  on the employee's behalf; the caller passes ``seleccion`` (candidate indices)
  and processes again.
- ``rechazado``: no boundary can come from this file. ``error`` says why.

Coordinate orders, stated once because ARA's X/Y are latitude/longitude:

- KML text and every GeoJSON position here are ``[longitude, latitude]``.
- ``bbox`` is ``[west, south, east, north]`` in degrees.
- ``punto_interior`` is a GeoJSON Point (``[longitude, latitude]``) inside a
  filled part and outside its holes, for a zoomed-out symbol only.
- Stored X/Y are never read or written here. ``area_aproximada_m2`` is a
  spherical approximation and never stands in for Superficie or HA.

Geometry is returned exactly as written in the file (ring order, winding and
repeated points included) apart from dropping altitude, which is reported.
Invalid shapes are rejected, never repaired.
"""

from __future__ import annotations

import io
import math
import re
import struct
import xml.parsers.expat
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .validation import MEXICO_LAT, MEXICO_LON

LISTO = "listo"
REQUIERE_SELECCION = "requiere_seleccion"
RECHAZADO = "rechazado"

# Limits. Each is enforced while reading, before the work it guards.
MAX_KMZ_BYTES = 20 * 1024 * 1024    # the package as uploaded
MAX_ENTRADAS = 1000                 # members listed in the ZIP directory
MAX_KML_BYTES = 16 * 1024 * 1024    # the one KML document, decompressed
MAX_PROFUNDIDAD = 64                # XML element nesting
MAX_ELEMENTOS = 500_000             # XML elements in the document
MAX_CANDIDATOS = 500                # placemarks that carry polygons
MAX_VERTICES = 100_000              # polygon positions, across the document
MAX_TOKEN = 128                     # characters in one "lon,lat[,alt]" tuple
MAX_NOMBRE = 200                    # characters kept from a <name>

# Validation work allowed, per segment plus a fixed base: grid registrations
# and edge comparisons. A shape needing more is reported as too complex to
# validate rather than accepted unchecked or left running.
_REGISTROS_POR_SEGMENTO = 32
_REGISTROS_BASE = 200_000
_PARES_POR_SEGMENTO = 64
_PARES_BASE = 500_000

# Below this planar ring area (degrees²; about 0.01 m² in Mexico) a ring is
# treated as having no area.
_AREA_MINIMA_GRADOS2 = 1e-12
_RADIO_TIERRA_M = 6_378_137.0
# A point this close to a ring (degrees; about 0.01 mm) counts as on it when
# deciding whether parts overlap.
_TOLERANCIA_GRADOS = 1e-10

_NUMERO = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")

# KML elements that are not a terrain boundary. Recorded and reported, never
# drawn, and never fetched (NetworkLink, overlay icons, models).
_IGNORADOS = frozenset({
    "Point", "LineString", "LinearRing", "GroundOverlay", "ScreenOverlay",
    "PhotoOverlay", "Model", "Track", "MultiTrack", "NetworkLink",
})
_CONTENEDORES = frozenset({"Document", "Folder"})
_BORDES = frozenset({"outerBoundaryIs", "innerBoundaryIs"})

Posicion = tuple[float, float]
Anillo = list[Posicion]
Poligono = list[Anillo]          # [exterior, *huecos]


class KmzError(Exception):
    """A stable machine code plus the plain-language Spanish message."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje

    def como_dict(self) -> dict[str, str]:
        return {"codigo": self.codigo, "mensaje": self.mensaje}


# ---------------------------------------------------------------- entry point

def procesar_kmz(datos: bytes, seleccion: object = None) -> dict[str, Any]:
    """Process one KMZ package. Never raises for bad input or a bad selection."""
    avisos: list[dict[str, str]] = []
    try:
        kml, adicionales = leer_paquete(datos)
        lectura = _leer_kml(kml)
    except KmzError as exc:
        return _resultado(RECHAZADO, error=exc)

    if adicionales:
        avisos.append(_aviso("KMZ_ARCHIVOS_ADICIONALES",
                             "El KMZ trae archivos adicionales (imágenes u otros); "
                             "no se usan para el contorno."))
    avisos.extend(lectura.avisos())
    ignorados = dict(sorted(lectura.ignorados.items()))
    candidatos = [_describir(c) for c in lectura.candidatos]

    if not candidatos:
        contenido = ", ".join(ignorados) if ignorados else "ningún elemento de mapa"
        return _resultado(RECHAZADO, avisos=avisos, ignorados=ignorados, error=KmzError(
            "KML_SIN_CONTORNO",
            f"El archivo no contiene un contorno de terreno (contiene: {contenido})."))

    base: dict[str, Any] = {"avisos": avisos, "ignorados": ignorados,
                            "candidatos": candidatos}

    if not any(c["valido"] for c in candidatos):
        if len(candidatos) == 1:
            unico = candidatos[0]["error"]
            error = KmzError(unico["codigo"], unico["mensaje"])
        else:
            error = KmzError("KML_SIN_CONTORNO_VALIDO",
                             "Ninguno de los contornos del archivo es válido.")
        return _resultado(RECHAZADO, error=error, **base)

    if len(candidatos) == 1 and seleccion is None:
        return _con_geometria([0], lectura, **base)

    if seleccion is None:
        return _resultado(REQUIERE_SELECCION, **base)

    try:
        indices = _validar_seleccion(seleccion, len(candidatos))
        for i in indices:
            error = candidatos[i]["error"]
            if error:
                raise KmzError("SELECCION_CONTORNO_INVALIDO",
                               f"El contorno «{candidatos[i]['nombre'] or i + 1}» no es válido: "
                               f"{error['mensaje']}")
    except KmzError as exc:
        return _resultado(REQUIERE_SELECCION, error=exc, **base)
    return _con_geometria(indices, lectura, **base)


def _con_geometria(indices: list[int], lectura: _Lectura,
                   **base: Any) -> dict[str, Any]:
    poligonos = [p for i in indices for p in lectura.candidatos[i].poligonos]
    if len(indices) > 1:
        # Each candidate is valid alone; the combination must not overlap.
        error = validar_poligonos(poligonos)
        if error:
            return _resultado(REQUIERE_SELECCION, error=error, **base)

    geometria = normalizar(poligonos)
    dentro = _dentro_de_mexico(geometria["bbox"])
    avisos = list(base.pop("avisos"))
    if not dentro:
        avisos.append(_aviso("GEOMETRIA_FUERA_DE_MEXICO",
                             "El contorno es válido pero cae fuera de México; se conserva "
                             "y no se usa para ubicar el terreno hasta revisarlo."))
    return _resultado(LISTO, seleccion=indices, geometria=geometria, avisos=avisos,
                      ubicacion={"dentro_de_mexico": dentro, "utilizable": dentro}, **base)


def _resultado(estado: str, *, error: KmzError | None = None,
               avisos: list[dict[str, str]] | None = None,
               ignorados: dict[str, int] | None = None,
               candidatos: list[dict[str, Any]] | None = None,
               seleccion: list[int] | None = None,
               geometria: dict[str, Any] | None = None,
               ubicacion: dict[str, bool] | None = None) -> dict[str, Any]:
    """Every result has the same keys, so callers never probe for them."""
    return {
        "estado": estado,
        "error": error.como_dict() if error else None,
        "avisos": avisos or [],
        "ignorados": ignorados or {},
        "candidatos": candidatos or [],
        "seleccion": seleccion,
        "geometria": geometria,
        "ubicacion": ubicacion,
    }


def _aviso(codigo: str, mensaje: str) -> dict[str, str]:
    return {"codigo": codigo, "mensaje": mensaje}


def _validar_seleccion(seleccion: object, total: int) -> list[int]:
    """Distinct in-range integers. Booleans, floats and strings are refused."""
    if not isinstance(seleccion, (list, tuple)):
        raise KmzError("SELECCION_INVALIDA", "La selección debe ser una lista de contornos.")
    if not seleccion:
        raise KmzError("SELECCION_INVALIDA", "Elige al menos un contorno.")
    if len(seleccion) > total:
        raise KmzError("SELECCION_INVALIDA", "La selección tiene más contornos que el archivo.")
    if any(type(i) is not int for i in seleccion):
        raise KmzError("SELECCION_INVALIDA", "La selección contiene valores que no son contornos.")
    indices = [int(i) for i in seleccion]
    if len(set(indices)) != len(indices):
        raise KmzError("SELECCION_INVALIDA", "La selección repite un contorno.")
    if any(i < 0 or i >= total for i in indices):
        raise KmzError("SELECCION_INVALIDA", "La selección no corresponde a este archivo.")
    return indices


# -------------------------------------------------------------------- package

_EOCD = b"PK\x05\x06"
_EOCD64_LOCALIZADOR = b"PK\x06\x07"
_EOCD_FORMATO = "<4s4H2LH"
_EOCD_TAMANO = struct.calcsize(_EOCD_FORMATO)


def leer_paquete(datos: bytes) -> tuple[bytes, bool]:
    """Return (the KML document, whether other members exist).

    Nothing is extracted to disk: the one KML member is decompressed into
    memory under a byte cap, and every other member is ignored unread.
    """
    if len(datos) > MAX_KMZ_BYTES:
        raise KmzError("KMZ_DEMASIADO_GRANDE",
                       "El archivo supera el tamaño máximo permitido para un KMZ.")
    _revisar_directorio(datos)
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as zf:
            miembros = [m for m in zf.infolist() if not m.is_dir()]
            kmls = [m for m in miembros if m.filename.lower().endswith(".kml")]
            if not kmls:
                raise KmzError("KMZ_SIN_KML", "El KMZ no contiene ningún documento KML.")
            if len(kmls) > 1:
                # Including duplicate names. A doc.kml name is not proof that
                # the other documents are irrelevant.
                raise KmzError("KMZ_VARIOS_KML",
                               "El KMZ contiene varios documentos KML; no se puede saber "
                               "cuál describe el terreno.")
            return _leer_miembro(zf, kmls[0]), len(miembros) > 1
    except KmzError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, EOFError, OSError,
            ValueError, struct.error, NotImplementedError, RuntimeError) as exc:
        raise KmzError("KMZ_DANADO", "El KMZ está dañado o incompleto.") from exc


def _revisar_directorio(datos: bytes) -> None:
    """Check the ZIP end record before zipfile reads the whole directory."""
    inicio = max(0, len(datos) - (_EOCD_TAMANO + 0xFFFF))
    pos = datos.rfind(_EOCD, inicio)
    if pos < 0 or len(datos) - pos < _EOCD_TAMANO:
        if datos[:4] == b"PK\x03\x04":
            raise KmzError("KMZ_DANADO", "El KMZ está dañado o incompleto.")
        raise KmzError("KMZ_NO_ES_ZIP",
                       "El archivo no es un KMZ válido (no es un paquete comprimido).")
    _, disco, disco_dir, en_disco, total, tam_dir, ini_dir, _ = struct.unpack(
        _EOCD_FORMATO, datos[pos:pos + _EOCD_TAMANO])
    if (pos >= 20 and datos[pos - 20:pos - 16] == _EOCD64_LOCALIZADOR) \
            or total == 0xFFFF or ini_dir == 0xFFFFFFFF or disco or disco_dir \
            or en_disco != total:
        raise KmzError("KMZ_NO_SOPORTADO",
                       "El KMZ usa un formato de compresión extendido o dividido que no se admite.")
    if total > MAX_ENTRADAS:
        raise KmzError("KMZ_DEMASIADAS_ENTRADAS",
                       "El KMZ contiene demasiados archivos internos.")
    if tam_dir > pos:
        raise KmzError("KMZ_DANADO", "El KMZ está dañado o incompleto.")


def _leer_miembro(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.flag_bits & 0x1:
        raise KmzError("KMZ_CIFRADO", "El KMZ está protegido con contraseña.")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise KmzError("KMZ_COMPRESION_NO_SOPORTADA",
                       "El KMZ usa un tipo de compresión que no se admite.")
    if info.file_size > MAX_KML_BYTES:
        raise KmzError("KML_DEMASIADO_GRANDE", "El documento KML es demasiado grande.")
    buf = bytearray()
    with zf.open(info) as fh:
        while True:
            trozo = fh.read(64 * 1024)
            if not trozo:
                break
            buf.extend(trozo)
            if len(buf) > MAX_KML_BYTES:  # the declared size is not trusted
                raise KmzError("KML_DEMASIADO_GRANDE", "El documento KML es demasiado grande.")
    return bytes(buf)


# ------------------------------------------------------------------------ KML

@dataclass
class _Candidato:
    indice: int
    nombre: str | None
    carpeta: list[str]
    poligonos: list[Poligono]
    error: KmzError | None


@dataclass
class _Lectura:
    candidatos: list[_Candidato] = field(default_factory=list)
    ignorados: dict[str, int] = field(default_factory=dict)
    altitud: bool = False

    def avisos(self) -> list[dict[str, str]]:
        avisos = []
        if self.ignorados.get("NetworkLink"):
            avisos.append(_aviso("KML_ENLACE_EXTERNO",
                                 "El archivo enlaza contenido externo; no se descargó."))
        otros = {k: v for k, v in sorted(self.ignorados.items()) if k != "NetworkLink"}
        if self.candidatos and otros:
            avisos.append(_aviso("KML_CONTENIDO_IGNORADO",
                                 "Se ignoraron elementos que no son contornos: "
                                 + ", ".join(f"{v} {k}" for k, v in otros.items()) + "."))
        if self.altitud:
            avisos.append(_aviso("KML_ALTITUD_DESCARTADA",
                                 "El archivo trae alturas o volumen; el contorno se usa en 2D."))
        return avisos


def _leer_kml(datos: bytes) -> _Lectura:
    """Parse with expat, refusing any DTD, and enforce limits while parsing."""
    lector = _LectorKml()
    parser = xml.parsers.expat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(xml.parsers.expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.buffer_text = False
    parser.StartDoctypeDeclHandler = _rechazar_dtd
    parser.EntityDeclHandler = _rechazar_dtd
    parser.ExternalEntityRefHandler = _rechazar_entidad_externa
    parser.StartElementHandler = lector.inicio
    parser.EndElementHandler = lector.fin
    parser.CharacterDataHandler = lector.texto
    try:
        parser.Parse(datos, True)
    except xml.parsers.expat.ExpatError as exc:
        raise KmzError("KML_XML_INVALIDO",
                       f"El KML no es XML válido (línea {exc.lineno}).") from None
    except (LookupError, ValueError):
        # An unknown or undecodable declared encoding (UnicodeError is a ValueError).
        raise KmzError("KML_CODIFICACION_NO_SOPORTADA",
                       "El KML declara una codificación de texto que no se admite.") from None
    return lector.lectura


def _rechazar_dtd(*_args: object) -> None:
    raise KmzError("KML_DTD_NO_PERMITIDA",
                   "El KML contiene declaraciones no permitidas (DTD o entidades).")


def _rechazar_entidad_externa(_contexto: str, _base: str | None, _sistema: str | None,
                              _publico: str | None) -> int:
    # Unreachable while DTDs are refused; kept so no external entity is ever
    # resolved if that ever changes.
    _rechazar_dtd()
    return 0


def _local(nombre: str) -> str:
    # KML 2.0/2.1/2.2, gx: and un-namespaced files all occur: match local names.
    return nombre.rsplit("}", 1)[-1]


class _LectorKml:
    """A streaming state machine over expat events.

    Only polygon coordinates inside a Placemark are kept, and they are parsed
    as they arrive, so the vertex limit stops the work before a full
    coordinate list exists.
    """

    def __init__(self) -> None:
        self.lectura = _Lectura()
        self.pila: list[str] = []
        self.elementos = 0
        self.vertices = 0
        self.carpetas: list[list[str | None]] = []   # one [name] per open container
        self.placemark: dict[str, Any] | None = None
        self.poligono: dict[str, Any] | None = None
        self.borde: str | None = None
        self.anillo: Anillo | None = None
        self.coordenadas = False
        self.resto = ""
        self.texto_de: str | None = None
        self.texto_buf: list[str] = []
        self.omitir: int | None = None   # depth of a subtree being skipped

    # -- events

    def inicio(self, nombre: str, _attrs: dict[str, str]) -> None:
        tag = _local(nombre)
        padre = self.pila[-1] if self.pila else None
        self.pila.append(tag)
        self.elementos += 1
        if len(self.pila) > MAX_PROFUNDIDAD:
            raise KmzError("KML_DEMASIADO_ANIDADO", "El KML está anidado en exceso.")
        if self.elementos > MAX_ELEMENTOS:
            raise KmzError("KML_DEMASIADOS_ELEMENTOS",
                           "El KML tiene demasiados elementos para procesarse.")
        if self.omitir is not None:
            return

        if tag in _CONTENEDORES:
            self.carpetas.append([None])
        elif tag == "Placemark":
            if self.placemark is None:
                self.placemark = {"nombre": None, "poligonos": [], "error": None}
            else:
                # Not valid KML. Its content belongs to no candidate.
                self._omitir("Placemark anidado")
        elif tag == "Polygon":
            if self.placemark is None or self.poligono is not None:
                self._omitir("Polygon")
            else:
                self.poligono = {"exterior": None, "huecos": [], "error": None}
        elif tag in _BORDES and padre == "Polygon" and self.poligono is not None:
            self.borde = tag
        elif tag == "LinearRing" and padre in _BORDES and self.borde is not None:
            if self.anillo is not None:
                self._error_poligono("KML_POLIGONO_INCOMPLETO",
                                     "Un borde del polígono tiene más de un anillo.")
            self.anillo = []
        elif tag == "coordinates" and padre == "LinearRing" and self.anillo is not None:
            if self.anillo:
                self._error_poligono("KML_POLIGONO_INCOMPLETO",
                                     "Un anillo del polígono tiene varias listas de coordenadas.")
            self.coordenadas = True
            self.resto = ""
        elif tag in _IGNORADOS:
            self._ignorar(tag)
        elif tag == "name" and padre in ("Placemark", *_CONTENEDORES):
            self.texto_de, self.texto_buf = "name", []
        elif tag in ("extrude", "altitudeMode") and padre == "Polygon":
            self.texto_de, self.texto_buf = tag, []

    def texto(self, datos: str) -> None:
        if self.coordenadas:
            self._coordenadas(datos)
        elif self.texto_de is not None and sum(map(len, self.texto_buf)) < MAX_NOMBRE:
            self.texto_buf.append(datos)

    def fin(self, nombre: str) -> None:
        tag = self.pila.pop()
        if self.omitir is not None:
            if len(self.pila) < self.omitir:
                self.omitir = None
            return
        padre = self.pila[-1] if self.pila else None
        if self.texto_de == tag:
            self._fin_texto(tag, padre)
        if tag == "coordinates" and self.coordenadas:
            self._coordenadas(" ")
            self.coordenadas = False
        elif tag == "LinearRing" and self.anillo is not None and padre in _BORDES:
            self._fin_anillo()
        elif tag in _BORDES and padre == "Polygon":
            self.borde = None
        elif tag == "Polygon" and self.poligono is not None and padre != "Polygon":
            self._fin_poligono()
        elif tag == "Placemark" and self.placemark is not None:
            self._fin_placemark()
        elif tag in _CONTENEDORES:
            self.carpetas.pop()

    # -- helpers

    def _ignorar(self, tag: str) -> None:
        self.lectura.ignorados[tag] = self.lectura.ignorados.get(tag, 0) + 1

    def _omitir(self, tag: str) -> None:
        """Record the element and skip everything inside it."""
        self._ignorar(tag)
        self.omitir = len(self.pila)

    def _fin_texto(self, tag: str, padre: str | None) -> None:
        texto = " ".join("".join(self.texto_buf).split())[:MAX_NOMBRE] or None
        self.texto_de, self.texto_buf = None, []
        if tag == "name":
            if padre == "Placemark" and self.placemark is not None:
                self.placemark["nombre"] = texto
            elif padre in _CONTENEDORES and self.carpetas:
                self.carpetas[-1][0] = texto
        elif (tag == "extrude" and texto == "1") or (
                tag == "altitudeMode" and texto not in (None, "clampToGround", "clampToSeaFloor")):
            self.lectura.altitud = True

    def _coordenadas(self, datos: str) -> None:
        texto = self.resto + datos
        partes = texto.split()
        if texto and not texto[-1].isspace() and partes:
            self.resto = partes.pop()
            if len(self.resto) > MAX_TOKEN:
                raise _coordenada_invalida()
        else:
            self.resto = ""
        anillo = self.anillo
        assert anillo is not None
        for tupla in partes:
            self.vertices += 1
            if self.vertices > MAX_VERTICES:
                raise KmzError("KML_DEMASIADOS_VERTICES",
                               "El contorno es demasiado complejo para procesarse "
                               f"(más de {MAX_VERTICES:,} vértices).".replace(",", " "))
            anillo.append(self._posicion(tupla))

    def _posicion(self, tupla: str) -> Posicion:
        if len(tupla) > MAX_TOKEN:
            raise _coordenada_invalida()
        partes = tupla.split(",")
        if len(partes) not in (2, 3) or not all(_NUMERO.fullmatch(p) for p in partes):
            raise _coordenada_invalida()
        lon, lat = float(partes[0]), float(partes[1])
        if len(partes) == 3 and float(partes[2]) != 0:
            self.lectura.altitud = True
        # KML order is longitude, latitude. Out of range is refused, not swapped.
        if not (math.isfinite(lon) and math.isfinite(lat)
                and -180 <= lon <= 180 and -90 <= lat <= 90):
            raise KmzError("KML_COORDENADAS_FUERA_DE_RANGO",
                           "El KML tiene coordenadas fuera de rango (¿latitud y longitud "
                           "invertidas?).")
        return (lon, lat)

    def _error_poligono(self, codigo: str, mensaje: str) -> None:
        if self.poligono is not None and self.poligono["error"] is None:
            self.poligono["error"] = KmzError(codigo, mensaje)

    def _fin_anillo(self) -> None:
        anillo, self.anillo = self.anillo, None
        poligono = self.poligono
        if poligono is None or anillo is None:
            return
        if self.borde == "outerBoundaryIs":
            if poligono["exterior"] is not None:
                self._error_poligono("KML_POLIGONO_INCOMPLETO",
                                     "Un polígono tiene más de un borde exterior.")
            else:
                poligono["exterior"] = anillo
        else:
            poligono["huecos"].append(anillo)

    def _fin_poligono(self) -> None:
        poligono, self.poligono = self.poligono, None
        placemark = self.placemark
        if poligono is None or placemark is None:
            return
        if poligono["exterior"] is None:
            self._marcar(placemark, KmzError("KML_POLIGONO_INCOMPLETO",
                                             "Un polígono no tiene borde exterior."))
            placemark["poligonos"].append([[], *poligono["huecos"]])
            return
        if poligono["error"] is not None:
            self._marcar(placemark, poligono["error"])
        placemark["poligonos"].append([poligono["exterior"], *poligono["huecos"]])

    @staticmethod
    def _marcar(placemark: dict[str, Any], error: KmzError) -> None:
        if placemark["error"] is None:
            placemark["error"] = error

    def _fin_placemark(self) -> None:
        placemark, self.placemark = self.placemark, None
        if placemark is None or not placemark["poligonos"]:
            return
        if len(self.lectura.candidatos) >= MAX_CANDIDATOS:
            raise KmzError("KML_DEMASIADOS_CONTORNOS",
                           f"El archivo tiene más de {MAX_CANDIDATOS} contornos.")
        poligonos: list[Poligono] = placemark["poligonos"]
        error = placemark["error"] or validar_poligonos(poligonos)
        carpeta = [n for (n,) in self.carpetas if n]
        self.lectura.candidatos.append(_Candidato(
            len(self.lectura.candidatos), placemark["nombre"], carpeta, poligonos, error))


def _coordenada_invalida() -> KmzError:
    return KmzError("KML_COORDENADAS_INVALIDAS",
                    "El KML tiene coordenadas con un formato inválido.")


# ------------------------------------------------------------------- geometry

def validar_poligonos(poligonos: Sequence[Poligono]) -> KmzError | None:
    """Why these polygons are not one valid terrain boundary, or None.

    Rules, all checked without modifying the input:
    - every ring is closed, has at least three distinct positions and area;
    - no ring touches or crosses itself (a repeated consecutive position is
      allowed; a spike that doubles back is not);
    - rings of one polygon never touch or cross; every hole lies inside its
      shell and outside the other holes;
    - parts may share edges or points but never overlap.
    Arithmetic is plain floating point on longitude/latitude, adequate for
    parcel-scale shapes; it is not a full topology library.
    """
    for poligono in poligonos:
        for i, anillo in enumerate(poligono):
            error = _validar_anillo(anillo, exterior=i == 0)
            if error:
                return error
    # Crossings before area: a symmetric bow-tie has zero signed area, and
    # "it crosses itself" is the explanation a person can act on.
    error, toques = _validar_cruces(poligonos)
    if error:
        return error
    for poligono in poligonos:
        for i, anillo in enumerate(poligono):
            if abs(_area_plana(anillo)) <= _AREA_MINIMA_GRADOS2:
                que = "El borde exterior" if i == 0 else "Un hueco"
                return KmzError("GEOMETRIA_SIN_AREA",
                                f"{que} del contorno no encierra ninguna área.")
    for poligono in poligonos:
        exterior, huecos = poligono[0], poligono[1:]
        for i, hueco in enumerate(huecos):
            if not _en_anillo(hueco[0], exterior):
                return KmzError("GEOMETRIA_HUECO_INVALIDO",
                                "Un hueco del contorno queda fuera de su borde exterior.")
            if any(_en_anillo(hueco[0], otro) for j, otro in enumerate(huecos) if j != i):
                return KmzError("GEOMETRIA_HUECO_INVALIDO",
                                "Un hueco del contorno está dentro de otro hueco.")
    return _validar_partes(poligonos, toques)


def _validar_anillo(anillo: Anillo, *, exterior: bool) -> KmzError | None:
    que = "El borde exterior" if exterior else "Un hueco"
    if len(anillo) >= 2 and anillo[0] != anillo[-1]:
        return KmzError("GEOMETRIA_ANILLO_ABIERTO",
                        f"{que} del contorno no termina en su punto inicial.")
    if len(anillo) < 4 or len(set(anillo)) < 3:
        return KmzError("GEOMETRIA_VERTICES_INSUFICIENTES",
                        f"{que} del contorno tiene menos de tres vértices distintos.")
    return None


def _sin_repetidos(anillo: Anillo) -> Anillo:
    """Consecutive repeats removed, for validation only. Still closed."""
    puntos = [anillo[0]]
    for p in anillo[1:]:
        if p != puntos[-1]:
            puntos.append(p)
    return puntos


@dataclass
class _Segmento:
    __slots__ = ("a", "b", "parte", "anillo", "i", "n")
    a: Posicion
    b: Posicion
    parte: int
    anillo: int        # global ring id
    i: int             # index within its ring
    n: int             # segments in its ring


def _validar_cruces(poligonos: Sequence[Poligono],
                    ) -> tuple[KmzError | None, list[tuple[_Segmento, _Segmento]]]:
    """Every edge contact, found through a sparse grid with a bounded budget.

    Cells start at the median segment length, so detailed edges (a river or
    road side) and long straight sides both register in few cells; the grid
    coarsens only when long edges would need too many registrations. A shape
    that still needs more work than the budget is reported as too complex,
    never accepted unchecked or left running.

    Also returns the touching edge pairs of different parts, which decide
    whether parts that share a boundary overlap.
    """
    toques: list[tuple[_Segmento, _Segmento]] = []
    segmentos: list[_Segmento] = []
    anillo_id = 0
    for parte, poligono in enumerate(poligonos):
        for anillo in poligono:
            puntos = _sin_repetidos(anillo)
            n = len(puntos) - 1
            segmentos.extend(_Segmento(puntos[k], puntos[k + 1], parte, anillo_id, k, n)
                             for k in range(n))
            anillo_id += 1

    total = len(segmentos)
    celdas = _rejilla(segmentos)
    if celdas is None:
        return _demasiado_complejo(), toques

    pares = 0
    limite = _PARES_POR_SEGMENTO * total + _PARES_BASE
    for lista in celdas.values():
        for u in range(len(lista)):
            s = segmentos[lista[u]]
            for v in range(u + 1, len(lista)):
                t = segmentos[lista[v]]
                pares += 1
                if pares > limite:
                    return _demasiado_complejo(), toques
                if s.parte != t.parte:
                    # Parts may share edges or points; crossing means overlap.
                    contacto = _contacto(s.a, s.b, t.a, t.b)
                    if contacto == 2:
                        return _superpuestas(), toques
                    if contacto == 1:
                        toques.append((s, t))
                    continue
                error = _clasificar(s, t)
                if error:
                    return error, toques
    return None, toques


def _rejilla(segmentos: Sequence[_Segmento]) -> dict[int, list[int]] | None:
    """Cells -> segment indices, or None when no cell size fits the budget."""
    total = len(segmentos)
    limite = _REGISTROS_POR_SEGMENTO * total + _REGISTROS_BASE
    x0 = min(min(s.a[0], s.b[0]) for s in segmentos)
    y0 = min(min(s.a[1], s.b[1]) for s in segmentos)
    medidas = sorted(max(abs(s.b[0] - s.a[0]), abs(s.b[1] - s.a[1])) for s in segmentos)
    base = medidas[total // 2] or medidas[-1]
    for factor in (1, 4, 16, 64, 256, 1024):
        lado = base * factor
        estimado = sum((abs(s.b[0] - s.a[0]) + abs(s.b[1] - s.a[1])) / lado + 3
                       for s in segmentos)
        if estimado <= limite:
            break
    else:
        return None

    celdas: dict[int, list[int]] = {}
    registros = 0
    holgura = lado * 1e-9      # touching segments must share a cell at boundaries
    for idx, s in enumerate(segmentos):
        (ax, ay), (bx, by) = s.a, s.b
        c0 = math.floor((min(ax, bx) - holgura - x0) / lado)
        c1 = math.floor((max(ax, bx) + holgura - x0) / lado)
        for c in range(c0, c1 + 1):
            if ax == bx:
                ya, yb = ay, by
            else:
                xa = max(min(ax, bx), x0 + c * lado)
                xb = min(max(ax, bx), x0 + (c + 1) * lado)
                pendiente = (by - ay) / (bx - ax)
                ya, yb = ay + (xa - ax) * pendiente, ay + (xb - ax) * pendiente
            f0 = math.floor((min(ya, yb) - holgura - y0) / lado)
            f1 = math.floor((max(ya, yb) + holgura - y0) / lado)
            for f in range(f0, f1 + 1):
                # One int per cell; indices start at -1 (the holgura), hence +1.
                celdas.setdefault(((c + 1) << 32) | (f + 1), []).append(idx)
            registros += f1 - f0 + 1
            if registros > limite:
                return None
    return celdas


def _demasiado_complejo() -> KmzError:
    return KmzError("GEOMETRIA_DEMASIADO_COMPLEJA",
                    "El contorno es demasiado complejo para validarse con seguridad.")


def _clasificar(s: _Segmento, t: _Segmento) -> KmzError | None:
    contacto = _contacto(s.a, s.b, t.a, t.b)
    if not contacto:
        return None
    if s.parte != t.parte:
        if contacto == 2:
            return _superpuestas()
        return None                      # parts may touch or share an edge
    if s.anillo != t.anillo:
        return KmzError("GEOMETRIA_HUECO_INVALIDO",
                        "Un hueco del contorno toca o cruza otro borde.")
    distancia = abs(s.i - t.i)
    if distancia in (1, s.n - 1):
        # Neighbours share one vertex; they must not double back over each other.
        primero, segundo = (s, t) if (s.i + 1) % s.n == t.i else (t, s)
        a, v, b = primero.a, primero.b, segundo.b
        if _orientacion(a, v, b) == 0 and (_sobre(a, v, b) or _sobre(v, b, a)):
            return _autointerseccion()
        return None
    return _autointerseccion()


def _autointerseccion() -> KmzError:
    return KmzError("GEOMETRIA_AUTOINTERSECCION",
                    "El contorno se cruza o se toca a sí mismo.")


def _superpuestas() -> KmzError:
    return KmzError("GEOMETRIA_PARTES_SUPERPUESTAS",
                    "Las partes del contorno se enciman entre sí.")


def _orientacion(a: Posicion, b: Posicion, c: Posicion) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _sobre(a: Posicion, b: Posicion, c: Posicion) -> bool:
    """c, already known collinear with ab, lies within the segment ab."""
    return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))


def _contacto(p1: Posicion, p2: Posicion, q1: Posicion, q2: Posicion) -> int:
    """0 no contact, 1 touching (endpoint or collinear overlap), 2 proper crossing."""
    if (max(p1[0], p2[0]) < min(q1[0], q2[0]) or max(q1[0], q2[0]) < min(p1[0], p2[0])
            or max(p1[1], p2[1]) < min(q1[1], q2[1])
            or max(q1[1], q2[1]) < min(p1[1], p2[1])):
        return 0
    d1, d2 = _orientacion(q1, q2, p1), _orientacion(q1, q2, p2)
    d3, d4 = _orientacion(p1, p2, q1), _orientacion(p1, p2, q2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return 2
    if ((d1 == 0 and _sobre(q1, q2, p1)) or (d2 == 0 and _sobre(q1, q2, p2))
            or (d3 == 0 and _sobre(p1, p2, q1)) or (d4 == 0 and _sobre(p1, p2, q2))):
        return 1
    return 0


def _en_anillo(p: Posicion, anillo: Anillo) -> bool:
    """Even-odd point-in-ring. Points exactly on the ring are not meaningful here."""
    x, y = p
    dentro = False
    for (x1, y1), (x2, y2) in zip(anillo, anillo[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
    return dentro


def _en_poligono(p: Posicion, poligono: Poligono) -> bool:
    return _en_anillo(p, poligono[0]) and not any(_en_anillo(p, h) for h in poligono[1:])


def _validar_partes(poligonos: Sequence[Poligono],
                    toques: Sequence[tuple[_Segmento, _Segmento]]) -> KmzError | None:
    """Parts with no crossing edges may still overlap. They do exactly when:

    - one part's interior point is strictly inside another (copies, nesting); or
    - a boundary piece of one part, between its contacts with another, lies
      strictly inside that other part (overlaps that only share collinear
      edges, which no crossing reveals).
    Between consecutive contacts a piece cannot cross the other boundary, so
    testing its midpoint decides the whole piece.
    """
    if len(poligonos) < 2:
        return None
    cajas = [_caja(p[0]) for p in poligonos]
    for i, poligono in enumerate(poligonos):
        punto = punto_interior(poligono)
        for j, otro in enumerate(poligonos):
            w, s, e, n = cajas[j]
            if i != j and w <= punto[0] <= e and s <= punto[1] <= n \
                    and _estrictamente_dentro(punto, otro):
                return _superpuestas()

    contactos: dict[int, tuple[_Segmento, list[_Segmento]]] = {}
    for s_, t_ in toques:
        for uno, otro_ in ((s_, t_), (t_, s_)):
            contactos.setdefault(id(uno), (uno, []))[1].append(otro_)
    for segmento, tocados in contactos.values():
        cortes = {0.0, 1.0}
        for t in tocados:
            for p in (t.a, t.b):
                if _orientacion(segmento.a, segmento.b, p) == 0 and \
                        _sobre(segmento.a, segmento.b, p):
                    cortes.add(min(1.0, max(0.0, _parametro(segmento, p))))
        orden = sorted(cortes)
        partes = {t.parte for t in tocados}
        for u, v in zip(orden, orden[1:]):
            if v <= u:
                continue
            m = _en_parametro(segmento, (u + v) / 2)
            if any(_distancia(m, t.a, t.b) <= _TOLERANCIA_GRADOS for t in tocados):
                continue                 # this piece is the shared boundary itself
            if any(_estrictamente_dentro(m, poligonos[p]) for p in partes):
                return _superpuestas()
    return None


def _parametro(s: _Segmento, p: Posicion) -> float:
    dx, dy = s.b[0] - s.a[0], s.b[1] - s.a[1]
    return (p[0] - s.a[0]) / dx if abs(dx) >= abs(dy) else (p[1] - s.a[1]) / dy


def _en_parametro(s: _Segmento, t: float) -> Posicion:
    return (s.a[0] + (s.b[0] - s.a[0]) * t, s.a[1] + (s.b[1] - s.a[1]) * t)


def _distancia(p: Posicion, a: Posicion, b: Posicion) -> float:
    """Planar distance in degrees from p to the segment ab."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    t = 0.0 if largo2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy)
                                             / largo2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _estrictamente_dentro(p: Posicion, poligono: Poligono) -> bool:
    """Inside the filled area and not within tolerance of any of its rings."""
    if not _en_poligono(p, poligono):
        return False
    return not any(_distancia(p, a, b) <= _TOLERANCIA_GRADOS
                   for anillo in poligono for a, b in zip(anillo, anillo[1:]))


def punto_interior(poligono: Poligono) -> Posicion:
    """A point strictly inside the filled area of a VALID polygon, outside holes.

    Scanlines across the shell's latitude range: along each, the even-odd
    crossings of every ring bound the filled intervals; the midpoint of the
    widest interval found is inside the polygon by construction.
    """
    _, s, _, n = _caja(poligono[0])
    alturas = {y for anillo in poligono for _, y in anillo}
    mejor: tuple[float, Posicion] | None = None
    intentos = 0
    for k in range(1, 200):
        # 0.5 first, then a low-discrepancy sequence across the height.
        fraccion = 0.5 if k == 1 else (0.5 + k * 0.6180339887498949) % 1.0
        y = s + (n - s) * fraccion
        if not s < y < n or y in alturas:
            continue
        intentos += 1
        if intentos > 9 and mejor is not None:
            break
        cortes = sorted(
            x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            for anillo in poligono
            for (x1, y1), (x2, y2) in zip(anillo, anillo[1:])
            if (y1 > y) != (y2 > y))
        for a, b in zip(cortes[::2], cortes[1::2]):
            if b > a and (mejor is None or b - a > mejor[0]):
                mejor = (b - a, ((a + b) / 2, y))
    if mejor is None:
        raise ValueError("no interior point: the polygon was not validated")
    return mejor[1]


def _caja(anillo: Anillo) -> tuple[float, float, float, float]:
    xs = [p[0] for p in anillo]
    ys = [p[1] for p in anillo]
    return min(xs), min(ys), max(xs), max(ys)


def _area_plana(anillo: Anillo) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(anillo, anillo[1:])) / 2


def area_aproximada_m2(anillo: Anillo) -> float:
    """Spherical ring area in m² (the approximation Leaflet.draw and Turf use)."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(anillo, anillo[1:]):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(total * _RADIO_TIERRA_M ** 2 / 2)


def _area_poligono(poligono: Poligono) -> float:
    return area_aproximada_m2(poligono[0]) - sum(area_aproximada_m2(h) for h in poligono[1:])


# -------------------------------------------------------------- normalization

def normalizar(poligonos: Sequence[Poligono]) -> dict[str, Any]:
    """The geometry payload for one VALIDATED boundary."""
    cajas = [_caja(p[0]) for p in poligonos]
    mayor = max(poligonos, key=_area_poligono)
    lon, lat = punto_interior(mayor)
    return {
        "geojson": {
            "type": "MultiPolygon",
            "coordinates": [[[[x, y] for x, y in anillo] for anillo in p] for p in poligonos],
        },
        "bbox": [min(c[0] for c in cajas), min(c[1] for c in cajas),
                 max(c[2] for c in cajas), max(c[3] for c in cajas)],
        "punto_interior": {"type": "Point", "coordinates": [lon, lat]},
        "area_aproximada_m2": round(sum(_area_poligono(p) for p in poligonos), 1),
        "partes": len(poligonos),
        "huecos": sum(len(p) - 1 for p in poligonos),
        "vertices": sum(len(a) for p in poligonos for a in p),
    }


def _describir(c: _Candidato) -> dict[str, Any]:
    """What a person needs to choose a candidate: no coordinates."""
    valido = c.error is None
    exteriores = [p[0] for p in c.poligonos if p and p[0]]
    cajas = [_caja(a) for a in exteriores]
    return {
        "indice": c.indice,
        "nombre": c.nombre,
        "carpeta": c.carpeta,
        "partes": len(c.poligonos),
        "huecos": sum(max(0, len(p) - 1) for p in c.poligonos),
        "vertices": sum(len(a) for p in c.poligonos for a in p),
        "bbox": ([min(k[0] for k in cajas), min(k[1] for k in cajas),
                  max(k[2] for k in cajas), max(k[3] for k in cajas)] if cajas else None),
        "area_aproximada_m2": (round(sum(_area_poligono(p) for p in c.poligonos), 1)
                               if valido else None),
        "valido": valido,
        "error": c.error.como_dict() if c.error else None,
    }


def _dentro_de_mexico(bbox: list[float]) -> bool:
    """The same extent server/validation.py applies to X/Y, for the whole boundary."""
    oeste, sur, este, norte = bbox
    return (MEXICO_LAT[0] <= sur and norte <= MEXICO_LAT[1]
            and MEXICO_LON[0] <= oeste and este <= MEXICO_LON[1])

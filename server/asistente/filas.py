"""Which rows below the header are terrains, and which are not.

A row is dropped only on evidence, never on its name alone. A summary is
recognized by what the rest of the line does -- it locates and identifies
nothing, and its figures add up to the rows above it -- and a footer note by
being the only thing written on its line. «Total FICTICIO Encino», with its
price, its area and its coordinates, is a terrain whose name merely starts with
a word, and it is imported like any other.

Whatever this reading concludes, the user's own decision wins: rows named in
the plan's ``excluir`` or ``incluir`` are settled before any evidence is
weighed, so a restored or removed row survives preparation, the preview and the
confirmation unchanged.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..csv_numbers import parse_number
from ..normalize import clean_text, fold

# Labels that are a summary and nothing else, and the words a summary label
# starts with. Neither is a verdict: both only make a row worth examining.
TOTALES = frozenset({"total", "totales", "total general", "gran total", "subtotal",
                     "subtotales", "suma", "suma total", "totals", "sumatoria"})
INICIOS_TOTALES = ("total ", "totales ", "total general ", "gran total ", "subtotal ",
                   "subtotales ", "suma ", "suma total ")

# A footer note announces itself. The word alone never removes a row: it has to
# be the only thing on the line as well.
NOTAS = re.compile(
    r"^(nota|notas|aviso|avisos|observacion|observaciones|comentario|comentarios|"
    r"fuente|fuentes|elaborado|actualizado|advertencia|importante|leyenda|"
    r"pie de pagina|pie de nota)\b")

# Fields that say a row is one property rather than a summary of several.
IDENTIFICAN = ("estado", "municipio", "direccion", "id_origen")
# Fields whose column can be added up, so a matching figure is real evidence.
SUMABLES = ("asking_price", "superficie_m2", "superficie_ha", "afectaciones_m2")

TOLERANCIA = 0.005   # a total written with fewer decimals still is the total
MAX_NOMBRE = 60      # how much of a long note is quoted back to the user


@dataclass(frozen=True)
class Clasificacion:
    motivo: str    # ENCABEZADO_REPETIDO | TOTALES | NOTA | EXCLUIDA
    resumen: str


def clasificar(datos: Sequence[tuple[int, tuple[Any, ...]]], cabecera: Sequence[Any],
               mapped: Mapping[int, str], nombre_pos: int, decimal: str,
               excluir: set[int], incluir: set[int]) -> dict[int, Clasificacion]:
    """The rows that are not terrains, by index, each with a reason to show."""
    cabeza = [fold(v) for v in cabecera if clean_text(v) is not None]
    candidatas = {i for i, valores in datos if _parece_totales(valores, nombre_pos)}
    sumas = _sumas(datos, mapped, decimal, candidatas | excluir)

    marcas: dict[int, Clasificacion] = {}
    for indice, valores in datos:
        if indice in excluir:
            marcas[indice] = Clasificacion("EXCLUIDA", "Excluida en la revisión")
            continue
        if indice in incluir:
            continue    # the user already said this row is a terrain
        marca = (_encabezado_repetido(valores, cabeza)
                 or _nota(valores, nombre_pos)
                 or (_totales(valores, mapped, nombre_pos, decimal, sumas)
                     if indice in candidatas else None))
        if marca:
            marcas[indice] = marca
    return marcas


def _encabezado_repetido(valores: Sequence[Any], cabeza: Sequence[str]) -> Clasificacion | None:
    textos = [fold(v) for v in valores if clean_text(v) is not None]
    if textos and list(textos) == list(cabeza):
        return Clasificacion("ENCABEZADO_REPETIDO", "Repite los encabezados")
    return None


def _nota(valores: Sequence[Any], nombre_pos: int) -> Clasificacion | None:
    """A note is the only thing written on its line, and says it is a note."""
    nombre = _nombre(valores, nombre_pos)
    if nombre is None or not NOTAS.match(fold(nombre)):
        return None
    if any(clean_text(v) is not None for p, v in enumerate(valores) if p != nombre_pos):
        return None     # it has other data: it is a terrain whose name starts that way
    return Clasificacion("NOTA", f"Nota al pie («{_recorte(nombre)}»): es lo único escrito "
                                 "en la fila, sin ubicación, superficie ni precio")


def _totales(valores: Sequence[Any], mapped: Mapping[int, str], nombre_pos: int,
             decimal: str, sumas: Mapping[int, float]) -> Clasificacion | None:
    """A totals-looking name is a summary only when the row behaves like one."""
    nombre = _nombre(valores, nombre_pos)
    if nombre is None or _identifica_un_terreno(valores, mapped, decimal):
        return None
    if _coincide_con_la_suma(valores, decimal, sumas):
        return Clasificacion("TOTALES", f"Fila de totales («{_recorte(nombre)}»): sus cifras son "
                                        "la suma de las demás filas")
    if fold(nombre) in TOTALES:
        return Clasificacion("TOTALES", f"Fila de totales («{_recorte(nombre)}»): no tiene "
                                        "ubicación ni ningún otro dato del terreno")
    return None


def _parece_totales(valores: Sequence[Any], nombre_pos: int) -> bool:
    nombre = _nombre(valores, nombre_pos)
    if nombre is None:
        return False
    plegado = fold(nombre)
    return plegado in TOTALES or plegado.startswith(INICIOS_TOTALES)


def _identifica_un_terreno(valores: Sequence[Any], mapped: Mapping[int, str], decimal: str) -> bool:
    """Coordinates, or a state/municipality/address/id: one property, not a total."""
    grados = [_numero(valores[p], decimal) for p, campo in mapped.items()
              if campo in ("lat", "lon") and p < len(valores)]
    if len(grados) == 2 and all(g is not None for g in grados):
        return True
    return any(clean_text(valores[p]) is not None for p, campo in mapped.items()
               if campo in IDENTIFICAN and p < len(valores))


def _sumas(datos: Sequence[tuple[int, tuple[Any, ...]]], mapped: Mapping[int, str],
           decimal: str, aparte: set[int]) -> dict[int, float]:
    """Column totals of the ordinary rows, to compare a candidate against."""
    posiciones = [p for p, campo in mapped.items() if campo in SUMABLES]
    sumas: dict[int, float] = {}
    for posicion in posiciones:
        valores = [_numero(v[posicion], decimal) for i, v in datos
                   if i not in aparte and posicion < len(v)]
        numeros = [n for n in valores if n is not None]
        if len(numeros) >= 2:
            sumas[posicion] = math.fsum(numeros)
    return sumas


def _coincide_con_la_suma(valores: Sequence[Any], decimal: str, sumas: Mapping[int, float]) -> bool:
    for posicion, suma in sumas.items():
        numero = _numero(valores[posicion], decimal) if posicion < len(valores) else None
        if numero is not None and abs(numero - suma) <= TOLERANCIA * max(abs(suma), 1.0):
            return True
    return False


def _nombre(valores: Sequence[Any], nombre_pos: int) -> str | None:
    return clean_text(valores[nombre_pos]) if nombre_pos < len(valores) else None


def _numero(bruto: Any, decimal: str) -> float | None:
    """A cell as a number, under the plan's convention. Evidence only."""
    if isinstance(bruto, bool) or bruto is None:
        return None
    if isinstance(bruto, (int, float)):
        return float(bruto) if math.isfinite(bruto) else None
    valor, nota = parse_number("asking_price", bruto, decimal)
    return valor if nota is None else None


def _recorte(texto: str) -> str:
    return texto if len(texto) <= MAX_NOMBRE else texto[:MAX_NOMBRE - 1] + "…"

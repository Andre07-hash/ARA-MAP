"""Rules for a work base's custom columns: definitions and the values stored
under them.

Pure functions over plain dicts. The repository stores; this module decides.

A definition belongs to one base and has a stable id, spelled
``custom:<uuid>`` everywhere outside the table. Its type never changes. A value
is stored as sent or not at all: nothing is coerced, converted or derived.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping
from datetime import date
from typing import Any

from . import db
from .web_util import texto_seguro

TIPOS = ("texto", "numero", "opcion", "fecha")
PREFIJO = "custom:"

MAX_NOMBRE = 100          # a column label, single-spaced
MAX_COLUMNAS = 50         # live (unretired) columns in one base
MAX_OPCIONES = 100        # choices of one "opcion" column
MAX_OPCION = 100          # characters of one choice
MAX_TEXTO = 2000          # characters of one "texto" value

# The fourteen core columns' labels. A custom column may not take one of them.
NOMBRES_BASICOS = ("Tipo de terreno", "Nombre de terreno", "Estado", "Municipio", "Superficie",
                   "HA", "Afectaciones %", "Asking price", "Asking $/m2", "Comentarios", "X", "Y",
                   "Archivos", "KMZ")
_RESERVADOS = frozenset(db.plegar(n) for n in NOMBRES_BASICOS)
_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")  # used with fullmatch: no trailing newline
NO_ADMITIDO = "Contiene caracteres no admitidos."


def clave(column_id: str) -> str:
    return PREFIJO + column_id


def id_de_clave(valor: Any) -> str | None:
    """The column id inside a ``custom:<uuid>`` key in canonical form, or None."""
    if not isinstance(valor, str) or not valor.startswith(PREFIJO):
        return None
    crudo = valor[len(PREFIJO):]
    try:
        canonico = str(uuid.UUID(crudo))
    except ValueError:
        return None
    return canonico if canonico == crudo else None


def plegado(nombre: str) -> str:
    """The key two column names are compared by: case and accents folded."""
    return db.plegar(nombre) or ""


def limpiar_nombre(valor: Any) -> str:
    nombre = " ".join(valor.split()) if isinstance(valor, str) else ""
    if not nombre or len(nombre) > MAX_NOMBRE:
        raise ValueError(f"Escribe un nombre (hasta {MAX_NOMBRE} caracteres).")
    if not texto_seguro(nombre):
        raise ValueError(NO_ADMITIDO)
    if plegado(nombre) in _RESERVADOS:
        raise ValueError("Ese nombre es de una columna básica.")
    return nombre


def limpiar_opciones(valor: Any) -> list[str]:
    """A choice list: single-spaced, non-empty, distinct strings."""
    if not isinstance(valor, list) or not valor:
        raise ValueError("Envía la lista de opciones (al menos una).")
    if len(valor) > MAX_OPCIONES:
        raise ValueError(f"Admite hasta {MAX_OPCIONES} opciones.")
    opciones: list[str] = []
    for item in valor:
        texto = " ".join(item.split()) if isinstance(item, str) else ""
        if not texto or len(texto) > MAX_OPCION:
            raise ValueError(f"Cada opción es un texto de 1 a {MAX_OPCION} caracteres.")
        if not texto_seguro(texto):
            raise ValueError(NO_ADMITIDO)
        if texto in opciones:
            raise ValueError("Hay opciones repetidas.")
        opciones.append(texto)
    return opciones


def limpiar_valor(columna: Mapping[str, Any], valor: Any) -> Any:
    """One value for one definition. None clears it. Raises ValueError."""
    if valor is None:
        return None
    tipo = columna["tipo"]
    if tipo == "numero":
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError("Debe ser un número.")
        try:
            numero = float(valor)  # an integer no double holds raises OverflowError
        except OverflowError:
            raise ValueError("Debe ser un número finito.") from None
        if not math.isfinite(numero):
            raise ValueError("Debe ser un número finito.")
        return numero
    if not isinstance(valor, str):
        raise ValueError("Debe ser texto.")
    if tipo == "texto":
        texto = valor.strip()
        if len(texto) > MAX_TEXTO:
            raise ValueError(f"Admite hasta {MAX_TEXTO} caracteres.")
        if not texto_seguro(texto, lineas=True):
            raise ValueError(NO_ADMITIDO)
        return texto or None
    if tipo == "fecha":
        try:
            if not _FECHA.fullmatch(valor):
                raise ValueError
            date(int(valor[:4]), int(valor[5:7]), int(valor[8:]))
        except ValueError:
            raise ValueError("Usa una fecha real con la forma AAAA-MM-DD.") from None
        return valor
    if valor not in columna["opciones"]:  # opcion
        raise ValueError("Elige una de las opciones de la columna.")
    return valor


def limpiar_valores(data: Any, vivas: Mapping[str, Mapping[str, Any]],
                    ) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate a client's ``custom`` map against the live columns of the
    terrain's current base. Returns (clean values, errors).

    A key that is not a live column of that base gets one answer whether the
    column is unknown, retired or another base's.
    """
    if not isinstance(data, Mapping):
        return {}, {"custom": "Se esperaba un objeto con los valores personalizados."}
    limpios: dict[str, Any] = {}
    errores: dict[str, str] = {}
    for nombre, valor in data.items():
        columna = vivas.get(nombre) if isinstance(nombre, str) else None
        if columna is None:
            errores[str(nombre)] = "Columna desconocida o retirada."
            continue
        try:
            limpios[nombre] = limpiar_valor(columna, valor)
        except ValueError as exc:
            errores[nombre] = str(exc)
    return limpios, errores

"""Describe the columns of one table: identity, label, type and a few samples.

A column's identity is its position (``sheet:0/column:4``), never its label, so
two columns both headed "Precio" -- or two with no heading at all -- stay two
separately selectable columns with visible positions.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..csv_numbers import parse_number
from ..normalize import clean_text
from .campos import monedas as monedas_del_texto
from .campos import normalizar
from .rejilla import Hoja

MAX_MUESTRAS = 5
MAX_LARGO_MUESTRA = 60


@dataclass(frozen=True)
class Columna:
    id: str              # "sheet:0/column:4": stable, positional
    posicion: int        # 0-based
    letra: str           # "columna E" (Excel) or "columna 5" (CSV)
    etiqueta: str        # the header text exactly as written ("" if blank)
    visible: str         # unique display name: "Precio (2)", "(sin encabezado)"
    clave: str           # normalized label, for signatures and matching
    ocurrencia: int      # 1st, 2nd... column with this clave
    no_vacias: int
    numericas: int       # typed numbers, or text readable as a number
    enteros: bool
    valores: tuple[float, ...]   # one reading per numeric cell, for summaries
    muestras: tuple[str, ...]
    # Every explicit foreign currency this column declares, whether in its
    # header, in its text, or in the Excel number format of its cells.
    monedas: tuple[str, ...]
    # Every plausible reading of each numeric cell: "20,653" is 20653 with a
    # decimal point and 20.653 with a decimal comma. Range evidence must not
    # depend on a convention that has not been settled yet.
    lecturas: tuple[tuple[float, ...], ...] = ()
    # The subset of `monedas` that only the Excel number format declares: the
    # amounts look like bare numbers, so a message has to say where it read them.
    monedas_formato: tuple[str, ...] = ()

    @property
    def moneda(self) -> str | None:
        """The foreign currency to name when refusing an MXN price."""
        return self.monedas[0] if self.monedas else None

    def en_rango(self, rango: tuple[float, float]) -> float:
        """Share of numeric cells that some reading places inside the range."""
        celdas = self.lecturas or tuple((v,) for v in self.valores)
        if not celdas:
            return 0.0
        dentro = sum(1 for lecturas in celdas if any(rango[0] <= v <= rango[1] for v in lecturas))
        return dentro / len(celdas)


def columna_id(hoja_id: str, posicion: int) -> str:
    return f"{hoja_id}/column:{posicion}"


def texto_de(celda: Any) -> str:
    """A cell as the user would read it: 12.0 -> "12", text as written."""
    if celda is None:
        return ""
    if isinstance(celda, bool):
        return "VERDADERO" if celda else "FALSO"
    if isinstance(celda, float) and celda.is_integer() and abs(celda) < 1e15:
        return str(int(celda))
    return str(celda)


def lecturas_numericas(celda: Any) -> tuple[float, ...]:
    """Every value a cell could mean under either numeric convention."""
    if isinstance(celda, bool) or celda is None:
        return ()
    if isinstance(celda, (int, float)):
        return (float(celda),) if math.isfinite(celda) else ()
    vistas: list[float] = []
    for campo in ("asking_price", "afectaciones_pct"):
        for modo in ("dot", "comma"):
            valor, nota = parse_number(campo, celda, modo)
            if valor is not None and nota is None and valor not in vistas:
                vistas.append(valor)
    return tuple(vistas)


def numero_aproximado(celda: Any) -> float | None:
    """A number for profiling only: typed, or text readable either way.

    Never used to build a terrain -- the plan's explicit convention does that.
    """
    if isinstance(celda, bool) or celda is None:
        return None
    if isinstance(celda, (int, float)):
        return float(celda) if math.isfinite(celda) else None
    for campo in ("asking_price", "afectaciones_pct"):
        for modo in ("dot", "comma"):
            valor, nota = parse_number(campo, celda, modo)
            if valor is not None and nota is None:
                return valor
    return None


def perfilar(hoja: Hoja, encabezado: int, filas: Sequence[int] | None = None) -> tuple[Columna, ...]:
    """Profile every column of the table whose header is row `encabezado`.

    `filas` are the data row indexes (default: all rows after the header).
    """
    cabecera = hoja.filas[encabezado] if hoja.filas else ()
    indices = list(filas if filas is not None else range(encabezado + 1, len(hoja.filas)))
    datos = [hoja.filas[i] for i in indices]
    ancho = max([len(cabecera), *(len(f) for f in datos)], default=0)

    etiquetas = [clean_text(cabecera[i]) if i < len(cabecera) else None for i in range(ancho)]
    claves = [normalizar(e) for e in etiquetas]
    repetidas = Counter(c for c in claves if c)
    vistas: Counter[str] = Counter()

    columnas = []
    for posicion in range(ancho):
        clave = claves[posicion]
        vistas[clave] += 1
        etiqueta = etiquetas[posicion] or ""
        if not etiqueta:
            visible = f"(sin encabezado, {hoja.letra(posicion)})"
        elif repetidas[clave] > 1:
            visible = f"{etiqueta} ({vistas[clave]})"
        else:
            visible = etiqueta
        columnas.append(_perfil_columna(hoja, posicion, etiqueta, visible, clave, vistas[clave],
                                        [f[posicion] if posicion < len(f) else None for f in datos],
                                        hoja.monedas_de(posicion, indices)))
    return tuple(columnas)


def _perfil_columna(hoja: Hoja, posicion: int, etiqueta: str, visible: str, clave: str,
                    ocurrencia: int, celdas: list[Any], formatos: tuple[str, ...]) -> Columna:
    no_vacias = [c for c in celdas if clean_text(c) is not None]
    numeros = [n for n in (numero_aproximado(c) for c in no_vacias) if n is not None]
    lecturas = tuple(lec for lec in (lecturas_numericas(c) for c in no_vacias) if lec)
    muestras: list[str] = []
    for celda in no_vacias:
        texto = texto_de(celda).strip()
        if len(texto) > MAX_LARGO_MUESTRA:
            texto = texto[:MAX_LARGO_MUESTRA - 1] + "…"
        if texto not in muestras:
            muestras.append(texto)
        if len(muestras) >= MAX_MUESTRAS:
            break
    return Columna(
        id=columna_id(hoja.id, posicion), posicion=posicion, letra=hoja.letra(posicion),
        etiqueta=etiqueta, visible=visible, clave=clave, ocurrencia=ocurrencia,
        no_vacias=len(no_vacias), numericas=len(numeros),
        enteros=bool(numeros) and all(n.is_integer() for n in numeros),
        valores=tuple(numeros[:2000]), muestras=tuple(muestras),
        monedas=tuple(dict.fromkeys(
            monedas_del_texto(etiqueta, tuple(c for c in no_vacias if isinstance(c, str))) + formatos)),
        lecturas=lecturas[:2000], monedas_formato=formatos,
    )

"""The ImportPlan: every decision needed to turn one table into terrains.

A plan is explicit and versioned: which table, which header row, which numeric
convention for numbers written as text, what each source column becomes, and
the one currency (USD or MXN) its prices are in.
It is bound to the file's hash and the parser version, and the server
validates it against the actual grid -- the client never sends terrain records,
only choices.

Building from a plan reuses the importer's record builder, so an assistant
import and a legacy import of the same table produce the same records.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ..csv_numbers import DECIMAL_MODES, parse_id, parse_number
from ..errors import WorkbookError
from ..importer import (
    EXPECTED_FIELDS,
    ImportResult,
    ParseNote,
    RejectedRow,
    TerrainRecord,
    _build_record,
)
from .campos import (
    CAMPOS,
    CLAVES_MONEDA,
    DESTINOS,
    EXTRA,
    IGNORAR,
    PRECIOS,
    SOPORTADAS,
    moneda_de_valor,
    nombre_moneda,
    problema_moneda,
)
from .filas import clasificar
from .perfil import Columna, columna_id, perfilar, texto_de
from .rejilla import PARSER_VERSION, Hoja, Rejilla

# 2: prices carry a currency. A version-1 plan assumed pesos and is refused.
PLAN_VERSION = 2


class PlanError(WorkbookError):
    """A plan that cannot be applied to this file. Message is for the user."""


@dataclass(frozen=True)
class ImportPlan:
    sha256: str
    hoja_id: str
    encabezado: int                        # row index within the sheet's nonblank rows
    decimal: str                           # "dot" | "comma", for numbers written as text
    asignaciones: Mapping[str, str]        # column id -> destino, for every column
    excluir: tuple[int, ...] = ()          # data rows the user chose to leave out
    incluir: tuple[int, ...] = ()          # data rows the user chose to keep anyway
    origenes: Mapping[str, str] = field(default_factory=dict)  # column id -> where the choice came from
    moneda: str | None = None              # "USD" | "MXN" when any column is a price
    moneda_origen: str = ""                # archivo | usuario | formato
    parser: int = PARSER_VERSION
    version: int = PLAN_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version, "parser": self.parser, "sha256": self.sha256,
            "hoja_id": self.hoja_id, "encabezado": self.encabezado, "decimal": self.decimal,
            "asignaciones": dict(self.asignaciones), "excluir": list(self.excluir),
            "incluir": list(self.incluir), "origenes": dict(self.origenes),
            "moneda": self.moneda, "moneda_origen": self.moneda_origen,
        }


@dataclass(frozen=True)
class Excluida:
    fila: int      # source row / physical line
    motivo: str    # ENCABEZADO_REPETIDO | TOTALES | NOTA | EXCLUIDA
    resumen: str
    indice: int = -1   # the row's index in the sheet: what «incluir» names


@dataclass(frozen=True)
class Construido:
    resultado: ImportResult
    columnas: tuple[Columna, ...]
    excluidas: tuple[Excluida, ...]
    preambulo: tuple[int, ...]      # source rows above the header (titles, notes)
    originales: Mapping[int, dict[str, str]]  # record orden -> {column id: text as written}
    indices: Mapping[int, int]      # record orden -> the row's index in the sheet

    @property
    def filas_datos(self) -> int:
        """Every nonblank row below the header: accepted + rejected + excluded."""
        return self.resultado.filas_con_datos + len(self.excluidas)


def validar(plan: ImportPlan, rejilla: Rejilla) -> Hoja:
    """Check a plan against the file. Returns the sheet it applies to."""
    if plan.version != PLAN_VERSION or plan.parser != rejilla.version:
        raise PlanError("La interpretación se hizo con otra versión del importador; vuelve a analizar el archivo.")
    if plan.sha256 != rejilla.sha256:
        raise PlanError("La interpretación corresponde a otro archivo.")
    try:
        hoja = rejilla.hoja(plan.hoja_id)
    except KeyError:
        raise PlanError("La hoja elegida no existe en el archivo.") from None
    if not 0 <= plan.encabezado < len(hoja.filas):
        raise PlanError("La fila de encabezados elegida no existe.")
    if plan.decimal not in DECIMAL_MODES:
        raise PlanError("Formato de números no válido.")

    validas = {columna_id(hoja.id, i) for i in range(hoja.ancho)}
    desconocidas = set(plan.asignaciones) - validas
    if desconocidas:
        raise PlanError("La interpretación menciona columnas que no existen en la hoja.")
    usados: dict[str, str] = {}
    for col, destino in plan.asignaciones.items():
        if destino not in DESTINOS:
            raise PlanError(f"Destino desconocido: {destino}.")
        if destino in CAMPOS:
            if destino in usados:
                raise PlanError(f"Dos columnas no pueden ser «{CAMPOS[destino][0]}» a la vez; elige una.")
            usados[destino] = col
    if "terreno" not in usados:
        raise PlanError("Falta indicar qué columna contiene el nombre del terreno; sin nombre no se puede importar.")
    if any(p in usados for p in PRECIOS) and plan.moneda not in SOPORTADAS:
        raise PlanError("Falta indicar la moneda de los precios (USD o MXN).")
    datos = range(plan.encabezado + 1, len(hoja.filas))
    if any(i not in datos for i in plan.excluir):
        raise PlanError("Sólo se pueden excluir filas de datos.")
    if any(i not in datos for i in plan.incluir):
        raise PlanError("Sólo se pueden incluir filas de datos.")
    if set(plan.excluir) & set(plan.incluir):
        raise PlanError("Una misma fila no puede quedar incluida y excluida a la vez.")
    return hoja


def construir(plan: ImportPlan, rejilla: Rejilla) -> Construido:
    """Build every row under the plan. Raises PlanError/EstructuraError."""
    hoja = validar(plan, rejilla)
    columnas = perfilar(hoja, plan.encabezado)
    for col in columnas:
        destino = plan.asignaciones.get(col.id, EXTRA)
        # Whoever chose it -- detection, a saved format, automatic assistance
        # or the user -- a price column is never relabelled into a currency
        # its own markers contradict, and never converted.
        if destino not in PRECIOS:
            continue
        problema = problema_moneda(col.monedas)
        if problema:
            raise PlanError(f"«{col.visible}» {problema}; no se convierten monedas. "
                            "Consérvala como dato adicional.")
        if col.monedas and col.monedas[0] != plan.moneda:
            raise PlanError(f"«{col.visible}» está en {nombre_moneda(col.monedas)}, no en "
                            f"{nombre_moneda([str(plan.moneda)])}.")

    cabecera = hoja.filas[plan.encabezado]
    mapped = {c.posicion: plan.asignaciones[c.id] for c in columnas
              if plan.asignaciones.get(c.id, EXTRA) in CAMPOS}
    unknown = {c.posicion: c.visible for c in columnas if plan.asignaciones.get(c.id, EXTRA) == EXTRA}
    nombre_pos = next(p for p, d in mapped.items() if d == "terreno")
    # A «Moneda» column states each row's currency; a priced row whose cell
    # names another currency, or something that is not one, stops the import.
    columnas_moneda = [c for c in columnas if c.clave in CLAVES_MONEDA]
    donde = "línea" if hoja.separador is not None else "fila"

    records: list[TerrainRecord] = []
    rechazadas: list[RejectedRow] = []
    excluidas: list[Excluida] = []
    originales: dict[int, dict[str, str]] = {}
    indices: dict[int, int] = {}

    datos = _datos(plan, hoja, cabecera, len(columnas))
    marcas = clasificar(datos, cabecera, mapped, nombre_pos, plan.decimal,
                        set(plan.excluir), set(plan.incluir))

    for indice, valores in datos:
        linea = hoja.lineas[indice]
        marca = marcas.get(indice)
        if marca is not None:
            excluidas.append(Excluida(linea, marca.motivo, marca.resumen, indice))
            continue
        where = f"{donde} {linea}"

        def numero(campo: str, raw: Any, w: str = where) -> tuple[float | None, ParseNote | None]:
            return _numero(campo, raw, plan.decimal, w)

        def ident(raw: Any, w: str = where) -> tuple[int | None, ParseNote | None]:
            return _ident(raw, plan.decimal, w)

        fila_leida = _build_record(valores, mapped, unknown, len(records) + 1, linea,
                                   number=numero, ident=ident)
        if isinstance(fila_leida, TerrainRecord) and (
                fila_leida.asking_price is not None or fila_leida.asking_m2 is not None):
            _revisar_moneda_fila(columnas_moneda, valores, plan.moneda, where)
            # Only a record that has a price carries its currency.
            fila_leida = replace(fila_leida, moneda=plan.moneda)
        if isinstance(fila_leida, TerrainRecord):
            records.append(fila_leida)
            indices[fila_leida.orden] = indice
            originales[fila_leida.orden] = {
                c.id: texto_de(valores[c.posicion]) for c in columnas
                if plan.asignaciones.get(c.id, EXTRA) != IGNORAR
            }
        elif isinstance(fila_leida, RejectedRow):
            rechazadas.append(fila_leida)
        else:
            rechazadas.append(RejectedRow(linea, "SIN_NOMBRE",
                                          "Falta el nombre del terreno · la fila sólo contiene valores vacíos"))

    resultado = ImportResult(
        hoja=hoja.nombre,
        records=tuple(records),
        columnas_no_reconocidas=tuple(unknown.values()),
        columnas_faltantes=tuple(sorted(EXPECTED_FIELDS - set(mapped.values()))),
        rechazadas=tuple(rechazadas),
    )
    return Construido(resultado, columnas, tuple(excluidas),
                      tuple(hoja.lineas[:plan.encabezado]), originales, indices)


def _revisar_moneda_fila(columnas: list[Columna], valores: tuple[Any, ...], moneda: str | None,
                        where: str) -> None:
    for col in columnas:
        texto = texto_de(valores[col.posicion]).strip()
        if texto and moneda_de_valor(texto) != moneda:
            raise PlanError(f"En la {where}, «{col.visible}» dice «{texto}», pero los precios se importan en "
                            f"{nombre_moneda([str(moneda)])}. Una tabla se importa con una sola moneda; "
                            "corrige o separa esas filas.")


def _datos(plan: ImportPlan, hoja: Hoja, cabecera: tuple[Any, ...],
           ancho: int) -> list[tuple[int, tuple[Any, ...]]]:
    """Every row below the header, padded to the table's width, index kept."""
    filas: list[tuple[int, tuple[Any, ...]]] = []
    for indice in range(plan.encabezado + 1, len(hoja.filas)):
        fila, linea = hoja.filas[indice], hoja.lineas[indice]
        if hoja.separador is not None and len(fila) != len(cabecera):
            raise PlanError(
                f"El CSV tiene {len(fila)} columnas en la línea {linea}; se esperaban {len(cabecera)}. "
                "Revisa las comillas y los separadores."
            )
        filas.append((indice, tuple(fila) + (None,) * (ancho - len(fila))))
    return filas


def _numero(campo: str, raw: Any, decimal: str, where: str) -> tuple[float | None, ParseNote | None]:
    """Typed Excel numbers pass through untouched; text follows the convention."""
    if isinstance(raw, bool):
        return None, ParseNote(campo, texto_de(raw), f"{where}, es un valor verdadero/falso")
    if isinstance(raw, (int, float)):
        if not math.isfinite(raw):
            return None, ParseNote(campo, texto_de(raw), f"{where}, el valor no es finito")
        return float(raw), None
    return parse_number(campo, raw, decimal, where)


def _ident(raw: Any, decimal: str, where: str) -> tuple[int | None, ParseNote | None]:
    if isinstance(raw, bool):
        return None, ParseNote("id_origen", texto_de(raw), f"{where}, el ID debe ser un número entero")
    if isinstance(raw, (int, float)):
        if math.isfinite(raw) and float(raw).is_integer():
            return int(raw), None
        return None, ParseNote("id_origen", texto_de(raw), f"{where}, el ID debe ser un número entero")
    return parse_id(raw, decimal, where)

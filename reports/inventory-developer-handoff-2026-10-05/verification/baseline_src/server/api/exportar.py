"""Export a set of terrains back to a spreadsheet.

The browser sends the ids currently visible after filtering, so what you export
is exactly what you were looking at.

A saved comparison gets one worksheet per layer rather than one flat sheet:
with several sources in a single table the rows look like duplicates and there
is no way to tell which period each belongs to. Grouping is by the saved
*layer* (its `orden`), never by source id or name -- two layers can be two
snapshots of the same source, and collapsing them would undo the history the
comparison exists to show.

Prices are written with their currency twice: a «Moneda» column, which is the
durable record, and a literal currency in the cell format (``"USD "#,##0``),
which is what a reader of the sheet sees. A row whose currency was never
confirmed says so; it is not labelled with either currency.
"""

from __future__ import annotations

import io
import re
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .. import db
from ..repo import mapas as repo_mapas
from ..repo import terrenos as repo_terrenos
from ..router import Request
from ..web_util import ApiError, parse_json

# Mirrors the source workbook's own layout so an export can be re-imported.
COLUMNS = (
    ("ID", "orden", None),
    ("Terreno", "terreno", None),
    ("Estado", "estado", None),
    ("Municipio", "municipio", None),
    ("Dirección", "direccion", None),
    ("Superficie m2", "superficie_m2", "#,##0.00"),
    ("Superficie Ha", "superficie_ha", "0.0000"),
    ("Afectaciones %", "afectaciones_pct", "0.00%"),
    ("Afectaciones m2", "afectaciones_m2", "#,##0.00"),
    ("Asking Price", "asking_price", "#,##0"),
    # Cents matter in a unit price: 122.5 must not come back as 123.
    ("Asking $/m2", "asking_m2", "#,##0.00"),
    ("X", "lat", None),
    ("Y", "lon", None),
    # Last, so the source workbook's own columns keep their positions.
    ("Moneda", "moneda", None),
)

HOJA_SIMPLE = "Registro Análisis"
SIN_CONFIRMAR = "sin confirmar"
PRECIOS = ("asking_price", "asking_m2")

# Excel forbids these in a worksheet name, and caps the name at 31 characters.
PROHIBIDOS = re.compile(r"[:\\/?*\[\]]")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_TITULO = 31


def sheet_title(nombre: str | None, usados: set[str], indice: int) -> str:
    """Turn a user-chosen layer name into a legal, unique worksheet title.

    Layer names are typed by people, so they can contain characters Excel
    rejects, be far too long, or collide once shortened. The stored name is
    never changed to fit -- only this copy of it is.
    """
    limpio = CONTROL.sub("", PROHIBIDOS.sub(" ", nombre or "")).strip().strip("'")
    limpio = re.sub(r"\s+", " ", limpio)
    if not limpio:
        limpio = f"Capa {indice + 1}"
    # A leading "History" is reserved by Excel for its own change log.
    if limpio.casefold() == "history":
        limpio = f"Capa {indice + 1} {limpio}"

    base = limpio[:MAX_TITULO]
    if base.casefold() not in usados:
        usados.add(base.casefold())
        return base

    # Reserve room for the suffix before truncating, so " (2)" is never cut off.
    for intento in range(2, 1000):
        sufijo = f" ({intento})"
        candidato = base[: MAX_TITULO - len(sufijo)].rstrip() + sufijo
        if candidato.casefold() not in usados:
            usados.add(candidato.casefold())
            return candidato
    raise ApiError("No se pudo generar un nombre de hoja único.")


def write_terrain_sheet(book: Workbook, titulo: str, filas: list[dict[str, Any]]) -> Worksheet:
    """Write one terrain table. An empty list still produces its header row."""
    sheet = book.create_sheet(title=titulo)
    sheet.freeze_panes = "A2"

    for index, (etiqueta, _, _) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index, value=etiqueta)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = max(12, len(etiqueta) + 4)

    for row_index, fila in enumerate(filas, start=2):
        moneda = fila.get("moneda")
        con_precio = any(fila.get(p) is not None for p in PRECIOS)
        for col_index, (_, campo, formato) in enumerate(COLUMNS, start=1):
            valor = fila.get(campo)
            if campo == "moneda":
                valor = moneda or (SIN_CONFIRMAR if con_precio else None)
            elif campo in PRECIOS and moneda and formato:
                formato = f'"{moneda} "{formato}'
            cell = sheet.cell(row=row_index, column=col_index)
            if isinstance(valor, str):
                # Written as literal text: a name or address beginning with "="
                # must never be evaluated as a formula.
                cell.value = valor
                cell.data_type = "s"
            else:
                cell.value = valor
            if formato:
                cell.number_format = formato

    sheet.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(len(filas) + 1, 1)}"
    return sheet


def export(request: Request) -> tuple[bytes, str]:
    """Build an .xlsx in memory and return it as (contents, filename)."""
    data = parse_json(request.body)
    base_id = data.get("base_id")
    mapa_id = data.get("mapa_id")
    if base_id is None and mapa_id is None:
        raise ApiError("Faltan campos obligatorios: base_id o mapa_id")

    ids = data.get("ids")

    with db.session() as conn:
        if mapa_id is not None:
            mapa = repo_mapas.get(conn, int(mapa_id))
            if mapa is None:
                raise ApiError("El mapa no existe.", 404)
            filas = _seleccionar(repo_mapas.terrenos(conn, int(mapa_id)), ids)
            book = _libro_de_mapa(mapa, filas)
        else:
            assert base_id is not None  # guarded above
            filas = _seleccionar(repo_terrenos.for_base(conn, int(base_id)), ids)
            book = Workbook()
            book.remove(book.active)
            write_terrain_sheet(book, HOJA_SIMPLE, filas)

    buffer = io.BytesIO()
    book.save(buffer)
    nombre = (data.get("nombre") or "terrenos").replace("/", "-")
    return buffer.getvalue(), f"{nombre}.xlsx"


def _seleccionar(filas: list[dict[str, Any]], ids: Any) -> list[dict[str, Any]]:
    """Keep only the requested rows.

    An omitted `ids` means "everything in this object"; an empty list is an
    explicit empty selection, not an instruction to export everything.
    """
    if ids is not None:
        queridos = {int(i) for i in ids}
        filas = [f for f in filas if f["id"] in queridos]
    if not filas:
        raise ApiError("No hay terrenos que exportar con los filtros actuales.")
    return filas


def _libro_de_mapa(mapa: dict[str, Any], filas: list[dict[str, Any]]) -> Workbook:
    """One sheet per layer for a comparison; a single sheet otherwise."""
    book = Workbook()
    book.remove(book.active)

    if mapa["tipo"] != "comparacion":
        write_terrain_sheet(book, HOJA_SIMPLE, filas)
        return book

    # Groups are created from the map's layers, not from the surviving rows, so
    # a layer hidden or emptied by filters still gets its (header-only) sheet
    # and the sheet order matches the layer order.
    grupos: dict[int, list[dict[str, Any]]] = {c["orden"]: [] for c in mapa["capas"]}
    for fila in filas:
        grupos.setdefault(fila.get("capa", 0), []).append(fila)

    usados: set[str] = set()
    for indice, capa in enumerate(mapa["capas"]):
        titulo = sheet_title(capa.get("nombre"), usados, indice)
        write_terrain_sheet(book, titulo, grupos.get(capa["orden"], []))
    return book

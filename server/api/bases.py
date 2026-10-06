"""Endpoints for bases and the terrains inside them."""

from __future__ import annotations

from typing import Any

from .. import db
from ..importer import TerrainRecord
from ..repo import bases as repo
from ..repo import carpetas as repo_carpetas
from ..repo import excel as repo_excel
from ..repo import mapas as repo_mapas
from ..repo import terrenos as repo_terrenos
from ..router import Request
from ..validation import validate_record
from ..web_util import ApiError, parse_json, require
from .carpetas import destination, folder_errors

# What every handler returns: the JSON body, serialized by the caller.
Respuesta = dict[str, Any]

EDITABLE = (
    "terreno", "estado", "municipio", "direccion", "superficie_m2", "superficie_ha",
    "afectaciones_pct", "afectaciones_m2", "asking_price", "asking_m2", "lat", "lon",
)
NUMERIC = EDITABLE[4:]


def listing(request: Request) -> Respuesta:
    """Every imported base, newest first, with its terrain counts."""
    with db.session() as conn:
        return {"bases": repo.listing(conn)}


def detail(request: Request) -> Respuesta:
    """One base and its counts."""
    with db.session() as conn:
        base = repo.get(conn, request.param("id"))
        if base is None:
            raise ApiError("La base no existe.", 404)
        return {"base": base}


def terrenos(request: Request) -> Respuesta:
    """Every terrain in a base, each with its validation findings."""
    with db.session() as conn:
        base_id = request.param("id")
        if repo.get(conn, base_id) is None:
            raise ApiError("La base no existe.", 404)
        return {"terrenos": repo_terrenos.for_base(conn, base_id)}


def rename(request: Request) -> Respuesta:
    """Rename a base, carrying the new name into the saved maps that show it.

    The refreshed map list comes back with the response so the interface can
    update its labels without reopening anything and losing the current view.
    """
    data = parse_json(request.body)
    (nombre,) = require(data, "nombre")
    with db.session() as conn:
        base_id = request.param("id")
        if repo.get(conn, base_id) is None:
            raise ApiError("La base no existe.", 404)
        capas = repo.rename(conn, base_id, nombre.strip())
        return {
            "base": repo.get(conn, base_id),
            "mapas": repo_mapas.listing(conn),
            "capas_actualizadas": capas,
        }


def move(request: Request) -> Respuesta:
    """Put a base in a base folder, or back in "Sin carpeta".

    A dedicated route rather than part of rename: renaming carries the name
    into saved maps, and a move must touch nothing but the membership.
    """
    carpeta_id = destination(parse_json(request.body), required=True)
    with db.session() as conn, folder_errors():
        base_id = request.param("id")
        if not repo_carpetas.assign(conn, "bases", base_id, carpeta_id):
            raise ApiError("La base no existe.", 404)
        return {"base": repo.get(conn, base_id)}


def remove(request: Request) -> Respuesta:
    """Delete a base and everything stored under it."""
    db.backup()
    with db.session() as conn:
        base_id = request.param("id")
        base = repo.get(conn, base_id)
        if base is None:
            raise ApiError("La base no existe.", 404)
        # A connected base's history lives in its source; generic delete
        # must not bypass the source lifecycle.
        repo_excel.proteger_base(conn, base_id)
        repo.delete(conn, base_id)
        return {"eliminada": base["nombre"], "terrenos": base["conteo"]}


def add_terreno(request: Request) -> Respuesta:
    """Add one terrain by hand, without a spreadsheet."""
    data = parse_json(request.body)
    require(data, "terreno")

    valores: dict[str, Any] = {}
    for campo in EDITABLE:
        valor = data.get(campo)
        if campo in NUMERIC:
            valores[campo] = _as_number(campo, valor)
        else:
            texto = (valor or "").strip() if isinstance(valor, str) else valor
            valores[campo] = texto or None

    # A price typed by hand needs its currency stated; it is never assumed.
    moneda = data.get("moneda")
    con_precio = valores["asking_price"] is not None or valores["asking_m2"] is not None
    if con_precio and moneda not in ("USD", "MXN"):
        raise ApiError("Indica la moneda del precio: USD o MXN.")
    valores["moneda"] = moneda if con_precio else None

    if valores["superficie_m2"] and not valores["superficie_ha"]:
        valores["superficie_ha"] = valores["superficie_m2"] / 10_000
    elif valores["superficie_ha"] and not valores["superficie_m2"]:
        valores["superficie_m2"] = valores["superficie_ha"] * 10_000

    db.backup()
    with db.session() as conn:
        base_id = request.param("id")
        if repo.get(conn, base_id) is None:
            raise ApiError("La base no existe.", 404)
        repo_excel.proteger_base(conn, base_id)

        orden = repo_terrenos.next_orden(conn, base_id)
        record = TerrainRecord(orden=orden, fila=0, **valores)
        repo_terrenos.insert(conn, base_id, [record], {orden: validate_record(record)})
        return {"base": repo.get(conn, base_id)}


def _as_number(campo: str, valor: Any) -> float | None:
    if valor in (None, ""):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise ApiError(f"El campo {campo} debe ser un número.") from None

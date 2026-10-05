"""Endpoints for saved maps, snapshots and comparison overlays."""

from __future__ import annotations

from typing import Any

from .. import db
from ..protocols import DatabaseConnection
from ..repo import bases as repo_bases
from ..repo import carpetas as repo_carpetas
from ..repo import mapas as repo
from ..router import Request
from ..web_util import ApiError, parse_json, require
from .carpetas import destination, folder_errors

Respuesta = dict[str, Any]

# Colours stay reliably distinguishable up to CAPAS_SEGURAS layers; past that
# the interface says so and every mark carries a second visual channel. The
# hard cap is the size of the palette.
CAPAS_SEGURAS = 4
MAX_CAPAS = 8
TIPOS = ("simple", "comparacion")


def listing(request: Request) -> Respuesta:
    """Every saved map, newest first, each with its layers."""
    with db.session() as conn:
        return {"mapas": repo.listing(conn)}


def detail(request: Request) -> Respuesta:
    """One saved map and its layers."""
    with db.session() as conn:
        mapa = repo.get(conn, request.param("id"))
        if mapa is None:
            raise ApiError("El mapa no existe.", 404)
        return {"mapa": mapa}


def terrenos(request: Request) -> Respuesta:
    """The frozen terrains this map holds, tagged with their layer."""
    with db.session() as conn:
        mapa = repo.get(conn, request.param("id"))
        if mapa is None:
            raise ApiError("El mapa no existe.", 404)
        return {"mapa": mapa, "terrenos": repo.terrenos(conn, mapa["id"])}


def create(request: Request) -> Respuesta:
    """Save a new map, freezing the terrains of every base it draws."""
    data = parse_json(request.body)
    nombre, tipo, capas = require(data, "nombre", "tipo", "capas")
    capas = _validate_capas(tipo, capas)
    carpeta_id = destination(data, required=False)

    db.backup()
    with db.session() as conn, folder_errors():
        _ensure_bases_exist(conn, capas)
        # The destination is checked and the map written in one transaction: a
        # folder deleted meanwhile means no map, never a map in the wrong place.
        with db.transaction(conn):
            repo_carpetas.require_folder(conn, "mapas", carpeta_id)
            mapa_id = repo.create(
                conn, nombre.strip(), tipo, capas, data.get("config"),
                sigue_base=bool(data.get("nombre_sigue_base", False)),
                carpeta_id=carpeta_id,
            )
        return {"mapa": repo.get(conn, mapa_id)}


def plan_merge(request: Request) -> Respuesta:
    """What merging these saved maps would produce, before anything is written."""
    data = parse_json(request.body)
    (mapa_ids,) = require(data, "mapa_ids")
    ids = _validate_mapa_ids(mapa_ids)

    with db.session() as conn:
        for mapa_id in ids:
            if repo.get(conn, mapa_id) is None:
                raise ApiError(f"El mapa {mapa_id} no existe.", 404)

        plan = repo.plan_merge(conn, ids)
        total = len(plan["capas"])
        if total > MAX_CAPAS:
            raise ApiError(
                f"La combinación produce {total} capas y el máximo es {MAX_CAPAS}. "
                "Elige menos mapas."
            )
        return {
            **plan,
            "total": total,
            "aviso_color": total > CAPAS_SEGURAS,
            "capas_seguras": CAPAS_SEGURAS,
        }


def merge(request: Request) -> Respuesta:
    """Create a new saved map from the frozen contents of existing saved maps."""
    data = parse_json(request.body)
    nombre, mapa_ids = require(data, "nombre", "mapa_ids")
    ids = _validate_mapa_ids(mapa_ids)
    colores = data.get("colores") or []
    carpeta_id = destination(data, required=False)

    db.backup()
    with db.session() as conn, folder_errors():
        for mapa_id in ids:
            if repo.get(conn, mapa_id) is None:
                raise ApiError(f"El mapa {mapa_id} no existe.", 404)

        plan = repo.plan_merge(conn, ids)
        if not plan["capas"]:
            raise ApiError("Los mapas elegidos no contienen ninguna capa.")
        if len(plan["capas"]) > MAX_CAPAS:
            raise ApiError(
                f"La combinación produce {len(plan['capas'])} capas y el máximo "
                f"es {MAX_CAPAS}."
            )

        with db.transaction(conn):
            repo_carpetas.require_folder(conn, "mapas", carpeta_id)
            mapa_id = repo.merge(conn, nombre.strip(), ids, colores, data.get("config"),
                                 carpeta_id=carpeta_id)
        return {"mapa": repo.get(conn, mapa_id), "duplicadas": plan["duplicadas"]}


def refresh(request: Request) -> Respuesta:
    """Re-take the snapshot from the current contents of each source base."""
    mapa_id = request.param("id")
    db.backup()
    with db.session() as conn:
        if repo.get(conn, mapa_id) is None:
            raise ApiError("El mapa no existe.", 404)
        resultado = repo.refresh_snapshot(conn, mapa_id)
        return {"mapa": repo.get(conn, mapa_id), **resultado}


def update(request: Request) -> Respuesta:
    """Rename a saved map, replace its layers, or store a new view config."""
    data = parse_json(request.body)
    mapa_id = request.param("id")

    with db.session() as conn:
        mapa = repo.get(conn, mapa_id)
        if mapa is None:
            raise ApiError("El mapa no existe.", 404)

        capas = data.get("capas")
        if capas is not None:
            capas = _validate_capas(data.get("tipo", mapa["tipo"]), capas)
            _ensure_bases_exist(conn, capas)

        nombre = data.get("nombre")
        sigue = data.get("nombre_sigue_base")
        repo.update(
            conn, mapa_id,
            nombre=nombre.strip() if isinstance(nombre, str) else None,
            capas=capas,
            config=data.get("config"),
            sigue_base=None if sigue is None else bool(sigue),
        )
        return {"mapa": repo.get(conn, mapa_id)}


def move(request: Request) -> Respuesta:
    """Put a saved map in a map folder, or back in "Sin carpeta".

    Separate from update, which can replace layers and re-take the snapshot:
    a move changes the membership and nothing else, not even actualizado_en.
    """
    carpeta_id = destination(parse_json(request.body), required=True)
    with db.session() as conn, folder_errors():
        mapa_id = request.param("id")
        if not repo_carpetas.assign(conn, "mapas", mapa_id, carpeta_id):
            raise ApiError("El mapa no existe.", 404)
        return {"mapa": repo.get(conn, mapa_id)}


def remove(request: Request) -> Respuesta:
    """Delete a saved map. The bases it was taken from are left alone."""
    with db.session() as conn:
        mapa_id = request.param("id")
        mapa = repo.get(conn, mapa_id)
        if mapa is None:
            raise ApiError("El mapa no existe.", 404)
        repo.delete(conn, mapa_id)
        return {"eliminado": mapa["nombre"]}


def _validate_mapa_ids(mapa_ids: Any) -> list[int]:
    if not isinstance(mapa_ids, list) or len(mapa_ids) < 2:
        raise ApiError("Elige al menos dos mapas guardados para combinar.")
    try:
        ids = [int(m) for m in mapa_ids]
    except (TypeError, ValueError):
        raise ApiError("Identificadores de mapa inválidos.") from None
    if len(set(ids)) != len(ids):
        raise ApiError("No se puede combinar un mapa consigo mismo.")
    return ids


def _validate_capas(tipo: str, capas: Any) -> list[dict[str, Any]]:
    if tipo not in TIPOS:
        raise ApiError(f"Tipo de mapa desconocido: {tipo}")
    if not isinstance(capas, list) or not capas:
        raise ApiError("Un mapa necesita al menos una base.")
    if tipo == "simple" and len(capas) != 1:
        raise ApiError("Un mapa simple muestra exactamente una base.")
    if len(capas) > MAX_CAPAS:
        raise ApiError(f"Un mapa admite hasta {MAX_CAPAS} capas.")

    limpio, vistos = [], set()
    for capa in capas:
        base_id = capa.get("base_id")
        if base_id in vistos:
            raise ApiError("Una base no puede aparecer dos veces en el mismo mapa.")
        vistos.add(base_id)
        limpio.append({
            "base_id": int(base_id),
            "color": capa.get("color") or "#2a78d6",
            "visible": capa.get("visible", True),
        })
    return limpio


def _ensure_bases_exist(conn: DatabaseConnection, capas: list[dict[str, Any]]) -> None:
    for capa in capas:
        if repo_bases.get(conn, capa["base_id"]) is None:
            raise ApiError(f"La base {capa['base_id']} no existe.", 404)

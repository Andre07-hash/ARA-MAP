"""Data access for folders: flat, per-dashboard groupings of bases or maps.

A folder only organizes. Moving an item into or out of one changes that item's
``carpeta_id`` and nothing else -- never its name, snapshot, layers, view
settings or timestamps -- and deleting a folder returns its items to "Sin
carpeta" instead of deleting them.

``carpeta_id`` is a plain foreign key, which proves the folder exists but not
that it is the right kind, so every write that sets a membership checks the
folder's ``tipo`` too, in the same transaction as the write.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..db import now, require_rowid, transaction
from ..errors import AraError
from ..protocols import DatabaseConnection

TIPOS = ("bases", "mapas")
# The item table each folder type organizes. Internal constants only, so safe
# to interpolate into SQL.
ITEM_TABLE = {"bases": "base", "mapas": "mapa"}


class CarpetaNoExisteError(AraError):
    """The folder was never there, or another editor has deleted it."""


class CarpetaTipoIncorrectoError(AraError):
    """A base folder offered for a map, or the other way round."""


class CarpetaDuplicadaError(AraError):
    """Another folder of the same type already has this (folded) name."""


def listing(conn: DatabaseConnection, tipo: str) -> dict[str, Any]:
    """Every folder of one type with its item count, plus the unfiled count.

    Empty folders are included. Alphabetical by folded name, id as tie-break.
    """
    tabla = ITEM_TABLE[tipo]
    carpetas = [
        _shape(row) for row in conn.execute(
            f"SELECT c.id, c.tipo, c.nombre, c.creado_en, c.actualizado_en,"
            f"       COUNT(i.id) AS conteo"
            f" FROM carpeta c LEFT JOIN {tabla} i ON i.carpeta_id = c.id"
            f" WHERE c.tipo = ?"
            f" GROUP BY c.id, c.tipo, c.nombre, c.nombre_clave, c.creado_en, c.actualizado_en"
            f" ORDER BY c.nombre_clave, c.id",
            (tipo,),
        ).fetchall()
    ]
    totales = conn.execute(
        f"SELECT COUNT(*) AS total,"
        f" COALESCE(SUM(CASE WHEN carpeta_id IS NULL THEN 1 ELSE 0 END), 0) AS sin_carpeta"
        f" FROM {tabla}"
    ).fetchone()
    return {
        "carpetas": carpetas,
        "sin_carpeta": int(totales["sin_carpeta"]),
        "total": int(totales["total"]),
    }


def get(conn: DatabaseConnection, carpeta_id: int) -> dict[str, Any] | None:
    """One folder with its item count, or None."""
    row = conn.execute("SELECT tipo FROM carpeta WHERE id = ?", (carpeta_id,)).fetchone()
    if row is None:
        return None
    tabla = ITEM_TABLE[row["tipo"]]
    found = conn.execute(
        f"SELECT c.id, c.tipo, c.nombre, c.creado_en, c.actualizado_en,"
        f" (SELECT COUNT(*) FROM {tabla} i WHERE i.carpeta_id = c.id) AS conteo"
        f" FROM carpeta c WHERE c.id = ?",
        (carpeta_id,),
    ).fetchone()
    return _shape(found)


def create(conn: DatabaseConnection, tipo: str, nombre: str, clave: str) -> int:
    """Create a folder. Raises CarpetaDuplicadaError on a name clash."""
    _refuse_duplicate(conn, tipo, clave)
    marca = now()
    try:
        cursor = conn.execute(
            "INSERT INTO carpeta (tipo, nombre, nombre_clave, creado_en, actualizado_en)"
            " VALUES (?, ?, ?, ?, ?)",
            (tipo, nombre, clave, marca, marca),
        )
    except Exception as exc:
        # Two editors creating the same name at once both pass the check above;
        # the UNIQUE constraint is what actually decides.
        if _is_unique_violation(exc):
            raise CarpetaDuplicadaError(nombre) from exc
        raise
    return require_rowid(cursor)


def rename(conn: DatabaseConnection, carpeta_id: int, nombre: str, clave: str) -> None:
    """Rename a folder. Renaming to its own folded name is allowed."""
    actual = conn.execute("SELECT tipo FROM carpeta WHERE id = ?", (carpeta_id,)).fetchone()
    if actual is None:
        raise CarpetaNoExisteError(str(carpeta_id))
    _refuse_duplicate(conn, actual["tipo"], clave, excepto=carpeta_id)
    try:
        conn.execute(
            "UPDATE carpeta SET nombre = ?, nombre_clave = ?, actualizado_en = ? WHERE id = ?",
            (nombre, clave, now(), carpeta_id),
        )
    except Exception as exc:
        if _is_unique_violation(exc):
            raise CarpetaDuplicadaError(nombre) from exc
        raise


def delete(conn: DatabaseConnection, carpeta_id: int) -> int:
    """Delete a folder, returning its items to "Sin carpeta".

    Never deletes an item. Both steps happen together or not at all; returns
    how many items were moved out, counted by the write itself.
    """
    with transaction(conn):
        actual = conn.execute("SELECT tipo FROM carpeta WHERE id = ?", (carpeta_id,)).fetchone()
        if actual is None:
            raise CarpetaNoExisteError(str(carpeta_id))
        tabla = ITEM_TABLE[actual["tipo"]]
        trasladados = conn.execute(
            f"UPDATE {tabla} SET carpeta_id = NULL WHERE carpeta_id = ?", (carpeta_id,)
        ).rowcount
        conn.execute("DELETE FROM carpeta WHERE id = ?", (carpeta_id,))
    return int(trasladados)


def require_folder(conn: DatabaseConnection, tipo: str, carpeta_id: int | None) -> None:
    """Check that a destination exists and organizes this kind of item.

    None ("Sin carpeta") always qualifies. Call it inside the transaction that
    writes the membership.
    """
    if carpeta_id is None:
        return
    row = conn.execute("SELECT tipo FROM carpeta WHERE id = ?", (carpeta_id,)).fetchone()
    if row is None:
        raise CarpetaNoExisteError(str(carpeta_id))
    if row["tipo"] != tipo:
        raise CarpetaTipoIncorrectoError(str(carpeta_id))


def assign(conn: DatabaseConnection, tipo: str, item_id: int, carpeta_id: int | None) -> bool:
    """Put one base or map in a folder (or none). Returns False if the item
    does not exist.

    Only ``carpeta_id`` changes; in particular a map's ``actualizado_en`` is
    left alone, since its saved data has not been refreshed. Moving an item to
    the folder it is already in succeeds and changes nothing.
    """
    tabla = ITEM_TABLE[tipo]
    with transaction(conn):
        require_folder(conn, tipo, carpeta_id)
        try:
            cambiadas = conn.execute(
                f"UPDATE {tabla} SET carpeta_id = ? WHERE id = ?", (carpeta_id, item_id)
            ).rowcount
        except Exception as exc:
            # The folder was deleted between the check and the write.
            if _is_foreign_key_violation(exc):
                raise CarpetaNoExisteError(str(carpeta_id)) from exc
            raise
    return bool(cambiadas)


def _refuse_duplicate(conn: DatabaseConnection, tipo: str, clave: str,
                      excepto: int | None = None) -> None:
    row = conn.execute(
        "SELECT id, nombre FROM carpeta WHERE tipo = ? AND nombre_clave = ?", (tipo, clave)
    ).fetchone()
    if row is not None and row["id"] != excepto:
        raise CarpetaDuplicadaError(row["nombre"])


def _is_unique_violation(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return "UNIQUE" in str(exc)
    return getattr(exc, "sqlstate", None) == "23505"


def _is_foreign_key_violation(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return "FOREIGN KEY" in str(exc)
    return getattr(exc, "sqlstate", None) == "23503"


def _shape(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["conteo"] = int(item["conteo"])
    return item

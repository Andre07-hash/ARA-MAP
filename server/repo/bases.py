"""Data access for bases: one imported workbook each."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..db import now, require_rowid, transaction
from ..protocols import DatabaseConnection
from ..validation import sql_ubicacion_valida

_SUMMARY = f"""
SELECT b.id, b.nombre, b.archivo_origen, b.hoja, b.importado_en, b.notas, b.carpeta_id,
       COUNT(t.id) AS conteo,
       COALESCE(SUM(CASE WHEN {sql_ubicacion_valida("t.lat", "t.lon")} THEN 1 ELSE 0 END), 0) AS ubicados,
       COALESCE(SUM(CASE WHEN t.id IS NOT NULL AND (t.lat IS NULL OR t.lon IS NULL) THEN 1 ELSE 0 END), 0) AS sin_coordenadas
FROM base b
LEFT JOIN terreno t ON t.base_id = b.id
"""


def create(conn: DatabaseConnection, nombre: str, archivo_origen: str | None,
           hoja: str | None, notas: str | None = None,
           carpeta_id: int | None = None) -> int:
    """Record a new base and return its id.

    ``carpeta_id`` must already have been checked with
    ``carpetas.require_folder`` in the same transaction.
    """
    cursor = conn.execute(
        "INSERT INTO base (nombre, archivo_origen, hoja, importado_en, notas, carpeta_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (nombre, archivo_origen, hoja, now(), notas, carpeta_id),
    )
    return require_rowid(cursor)


def listing(conn: DatabaseConnection) -> list[dict[str, Any]]:
    """Every base, newest first, with its terrain counts."""
    rows = conn.execute(
        _SUMMARY + " GROUP BY b.id ORDER BY b.importado_en DESC, b.id DESC"
    ).fetchall()
    return [_shape(r) for r in rows]


def get(conn: DatabaseConnection, base_id: int) -> dict[str, Any] | None:
    """One base with its counts, or None if it does not exist."""
    row = conn.execute(_SUMMARY + " WHERE b.id = ? GROUP BY b.id", (base_id,)).fetchone()
    return _shape(row) if row else None


def rename(conn: DatabaseConnection, base_id: int, nombre: str) -> int:
    """Rename a source and carry the new name into everything that shows it.

    A rename is a metadata correction, so the frozen terrains are untouched and
    the snapshot's refresh timestamp is left alone. Layers are found by id,
    never by their current text. Returns how many saved maps were affected.

    Everything happens in one transaction: a half-applied rename would leave a
    source called one thing and its saved layers another.
    """
    with transaction(conn):
        conn.execute("UPDATE base SET nombre = ? WHERE id = ?", (nombre, base_id))

        # Only the raw source component; a layer's version qualifier is what
        # keeps two snapshots of one source apart and must survive.
        capas = conn.execute(
            "UPDATE mapa_capa SET base_nombre = ? WHERE base_id = ?", (nombre, base_id)
        ).rowcount

        # A title that was following the source follows it here too. Restricted
        # to maps with exactly one layer, which is the only unambiguous case.
        conn.execute(
            """
            UPDATE mapa SET nombre = ?
            WHERE nombre_sigue_base = 1
              AND tipo = 'simple'
              AND id IN (
                SELECT mapa_id FROM mapa_capa
                GROUP BY mapa_id
                HAVING COUNT(*) = 1 AND MAX(base_id) = ?
              )
            """,
            (nombre, base_id),
        )
    return int(capas)


def delete(conn: DatabaseConnection, base_id: int) -> None:
    """Delete a base and its terrains.

    Saved maps keep their frozen copies. Their layers are disconnected from the
    id first: leaving the id behind would let a later import inherit it and be
    mistaken for the original source.
    """
    conn.execute(
        "UPDATE mapa_capa SET base_id = NULL WHERE base_id = ?", (base_id,)
    )
    conn.execute("DELETE FROM base WHERE id = ?", (base_id,))


def name_taken(conn: DatabaseConnection, nombre: str) -> bool:
    """Whether a base already carries this exact name."""
    row = conn.execute("SELECT 1 FROM base WHERE nombre = ? LIMIT 1", (nombre,)).fetchone()
    return row is not None


def unique_name(conn: DatabaseConnection, nombre: str) -> str:
    """Return nombre, or nombre (2), (3)... so imports never collide silently."""
    if not name_taken(conn, nombre):
        return nombre
    suffix = 2
    while name_taken(conn, f"{nombre} ({suffix})"):
        suffix += 1
    return f"{nombre} ({suffix})"


def _shape(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["sin_ubicacion"] = item["conteo"] - item["ubicados"]
    # Coordinates that exist but are impossible: neither plottable nor missing.
    item["ubicacion_invalida"] = item["sin_ubicacion"] - item["sin_coordenadas"]
    return item

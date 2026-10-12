"""Read-only SQL for the attachment recovery verifier (server.recuperacion).

Nothing here writes. `solo_lectura` additionally makes the connection refuse
writes for the rest of its transaction, on both databases.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..protocols import DatabaseConnection


def solo_lectura(conn: DatabaseConnection) -> None:
    """Make every later write on this connection fail."""
    if isinstance(conn, sqlite3.Connection):
        conn.execute("PRAGMA query_only = ON")
    else:
        conn.execute("SET TRANSACTION READ ONLY")


def finales(conn: DatabaseConnection) -> list[dict[str, Any]]:
    """Every version that names a final object, whatever became of its attachment.

    Retired attachments and superseded versions keep their bytes, so they are
    all here: this is the complete set of final keys the database references.
    """
    return [dict(row) for row in conn.execute(
        """
        SELECT v.clave_final AS clave, v.tamano, v.sha256, v.id AS version_id,
               v.archivo_id, v.inventory_id, a.tipo, v.estado, v.numero,
               CASE WHEN a.version_actual_id = v.id THEN 1 ELSE 0 END AS actual,
               CASE WHEN a.retirado_en IS NULL THEN 0 ELSE 1 END AS retirado,
               (SELECT COUNT(*) FROM geometria g WHERE g.archivo_version_id = v.id)
                 AS geometrias,
               (SELECT COUNT(*) FROM archivo_evento e WHERE e.archivo_version_id = v.id)
                 AS eventos
        FROM archivo_version v JOIN archivo a ON a.id = v.archivo_id
        WHERE v.clave_final IS NOT NULL
        ORDER BY v.archivo_id, v.numero
        """).fetchall()]


def pendientes(conn: DatabaseConnection) -> list[dict[str, Any]]:
    """Uploads that never finalized: they have staging at most, and deadlines."""
    return [dict(row) for row in conn.execute(
        """
        SELECT v.id AS version_id, v.archivo_id, v.inventory_id, a.tipo, v.numero,
               v.clave_temporal, v.tamano_declarado, v.sha256_declarado, v.iniciado_en,
               v.subida_vence_en, v.completar_antes_de
        FROM archivo_version v JOIN archivo a ON a.id = v.archivo_id
        WHERE v.estado = 'subiendo'
        ORDER BY v.archivo_id, v.numero
        """).fetchall()]

"""Data access for terrains and their validation findings."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ..db import require_rowid
from ..protocols import DatabaseConnection, TerrenoLike
from ..validation import UBICACION_VALIDA, Finding, location_state

FIELDS = (
    "id_origen", "orden", "terreno", "estado", "municipio", "direccion",
    "superficie_m2", "superficie_ha", "afectaciones_pct", "afectaciones_m2",
    "asking_price", "asking_m2", "lat", "lon", "clave_dedupe", "extra_json", "moneda",
)

_INSERT = f"""
INSERT INTO terreno (base_id, {", ".join(FIELDS)})
VALUES (:base_id, {", ".join(f":{f}" for f in FIELDS)})
"""


def _as_params(base_id: int, record: TerrenoLike, orden: int) -> dict[str, Any]:
    """Flatten a TerrainRecord into insert parameters. Builds a new dict."""
    params = {"base_id": base_id, "orden": orden, "clave_dedupe": record.clave_dedupe}
    for name in FIELDS:
        if name in ("orden", "clave_dedupe", "extra_json"):
            continue
        params[name] = getattr(record, name)
    params["extra_json"] = json.dumps(record.extra, ensure_ascii=False) if record.extra else None
    return params


def next_orden(conn: DatabaseConnection, base_id: int) -> int:
    """The display position the next terrain added to this base should take."""
    row = conn.execute(
        "SELECT COALESCE(MAX(orden), 0) AS n FROM terreno WHERE base_id = ?", (base_id,)
    ).fetchone()
    return int(row["n"]) + 1


def insert(
    conn: DatabaseConnection,
    base_id: int,
    records: Iterable[TerrenoLike],
    findings_by_orden: Mapping[int, Sequence[Finding]],
) -> list[int]:
    """Insert records into a base, with their findings. Returns the new ids."""
    orden = next_orden(conn, base_id)
    new_ids: list[int] = []

    for record in records:
        cursor = conn.execute(_INSERT, _as_params(base_id, record, orden))
        terreno_id = require_rowid(cursor)
        new_ids.append(terreno_id)

        for finding in findings_by_orden.get(record.orden, ()):
            conn.execute(
                "INSERT INTO incidencia (terreno_id, severidad, codigo, mensaje)"
                " VALUES (?, ?, ?, ?)",
                (terreno_id, finding.severidad, finding.codigo, finding.mensaje),
            )
        orden += 1

    return new_ids


def update_from_record(
    conn: DatabaseConnection,
    terreno_id: int,
    record: TerrenoLike,
    findings: Sequence[Finding],
) -> None:
    """Replace a stored terrain's values with an incoming revision."""
    assignable = [f for f in FIELDS if f != "orden"]
    params = _as_params(0, record, 0)
    conn.execute(
        f"UPDATE terreno SET {', '.join(f'{f} = :{f}' for f in assignable)} WHERE id = :id",
        {**params, "id": terreno_id},
    )
    conn.execute("DELETE FROM incidencia WHERE terreno_id = ?", (terreno_id,))
    for finding in findings:
        conn.execute(
            "INSERT INTO incidencia (terreno_id, severidad, codigo, mensaje) VALUES (?, ?, ?, ?)",
            (terreno_id, finding.severidad, finding.codigo, finding.mensaje),
        )


def for_base(conn: DatabaseConnection, base_id: int) -> list[dict[str, Any]]:
    """Every terrain in a base, each with its findings attached."""
    rows = conn.execute(
        "SELECT * FROM terreno WHERE base_id = ? ORDER BY orden", (base_id,)
    ).fetchall()
    return _attach_findings(conn, rows)


def for_bases(conn: DatabaseConnection, base_ids: Sequence[int]) -> list[dict[str, Any]]:
    """Every terrain across several bases, for overlay maps."""
    if not base_ids:
        return []
    placeholders = ", ".join("?" for _ in base_ids)
    rows = conn.execute(
        f"SELECT * FROM terreno WHERE base_id IN ({placeholders}) ORDER BY base_id, orden",
        tuple(base_ids),
    ).fetchall()
    return _attach_findings(conn, rows)


# Everything an append can legitimately correct. Identity fields (name, state,
# municipality) are excluded: a change there makes it a different terrain.
CAMPOS_COMPARABLES = (
    "direccion", "superficie_m2", "superficie_ha",
    "afectaciones_pct", "afectaciones_m2",
    "asking_price", "asking_m2", "moneda", "lat", "lon",
)


def dedupe_rows(conn: DatabaseConnection, base_id: int) -> list[dict[str, Any]]:
    """Existing terrains with every field an append is allowed to change.

    The classifier compares content, so it needs the content -- returning only
    the identity key and the price is what let coordinate corrections be
    discarded as "duplicates".
    """
    columnas = ", ".join(("id", "clave_dedupe", *CAMPOS_COMPARABLES))
    rows = conn.execute(
        f"SELECT {columnas} FROM terreno WHERE base_id = ?", (base_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def _attach_findings(
    conn: DatabaseConnection, rows: Sequence[sqlite3.Row]
) -> list[dict[str, Any]]:
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    placeholders = ", ".join("?" for _ in ids)
    found = conn.execute(
        f"SELECT terreno_id, severidad, codigo, mensaje FROM incidencia"
        f" WHERE terreno_id IN ({placeholders})",
        tuple(ids),
    ).fetchall()

    grouped: dict[int, list[dict[str, str]]] = {}
    for row in found:
        grouped.setdefault(row["terreno_id"], []).append(
            {"severidad": row["severidad"], "codigo": row["codigo"], "mensaje": row["mensaje"]}
        )

    result = []
    for row in rows:
        item = dict(row)
        item["extra"] = json.loads(item.pop("extra_json") or "{}")
        item["incidencias"] = grouped.get(row["id"], [])
        item["ubicacion"] = location_state(item["lat"], item["lon"])
        item["ubicado"] = item["ubicacion"] == UBICACION_VALIDA
        result.append(item)
    return result

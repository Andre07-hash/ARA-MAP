"""Reusable import formats and the record of each import.

A format stores a header signature -- normalized labels with their occurrence
number, so two "Precio" columns stay distinct -- and what each header became.
It never stores a cell value. Matching is by label, so a file that only
reorders its columns still matches.

Remembering is explicit and non-destructive: the identical format is reused;
a different interpretation of the same headers becomes a new version, and the
previous one is marked as replaced rather than overwritten.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from ..db import now, require_rowid
from ..protocols import DatabaseConnection


def _canonico(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def firma_clave(firma: Sequence[Sequence[Any]]) -> str:
    """Order-independent key: a reordered file has the same key."""
    return hashlib.sha256(_canonico(sorted([list(f) for f in firma])).encode("utf-8")).hexdigest()


def activos(conn: DatabaseConnection) -> list[dict[str, Any]]:
    """Formats available for automatic matching: the current version of each."""
    rows = conn.execute(
        "SELECT * FROM formato_importacion WHERE reemplazado_por IS NULL ORDER BY id"
    ).fetchall()
    return [_forma(r) for r in rows]


def listing(conn: DatabaseConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM formato_importacion ORDER BY reemplazado_por IS NOT NULL, actualizado_en DESC, id DESC"
    ).fetchall()
    return [_forma(r) for r in rows]


def get(conn: DatabaseConnection, formato_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM formato_importacion WHERE id = ?", (formato_id,)).fetchone()
    return _forma(row) if row else None


def recordar(conn: DatabaseConnection, nombre: str, firma: Sequence[Sequence[Any]],
             config: Mapping[str, Any], plan_version: int) -> tuple[int, int, str]:
    """Remember a confirmed format. Returns (id, version, what happened).

    What happened: "reutilizado" (identical, usage counted), "nuevo", or
    "nueva_version" (same headers, different interpretation).
    """
    clave = firma_clave(firma)
    config_texto = _canonico(config)
    marca = now()
    vigentes = conn.execute(
        "SELECT id, version, config_json FROM formato_importacion"
        " WHERE firma_clave = ? AND reemplazado_por IS NULL", (clave,)
    ).fetchall()
    for fila in vigentes:
        if fila["config_json"] == config_texto:
            conn.execute("UPDATE formato_importacion SET usos = usos + 1, actualizado_en = ? WHERE id = ?",
                         (marca, fila["id"]))
            return int(fila["id"]), int(fila["version"]), "reutilizado"

    anterior = conn.execute("SELECT MAX(version) AS v FROM formato_importacion WHERE firma_clave = ?",
                            (clave,)).fetchone()["v"]
    version = int(anterior or 0) + 1
    etiqueta = nombre if version == 1 else f"{nombre} (v{version})"
    cursor = conn.execute(
        "INSERT INTO formato_importacion (nombre, firma, firma_clave, config_json, plan_version,"
        " version, usos, creado_en, actualizado_en) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (etiqueta, _canonico([list(f) for f in firma]), clave, config_texto, plan_version,
         version, marca, marca),
    )
    nuevo = require_rowid(cursor)
    for fila in vigentes:
        conn.execute("UPDATE formato_importacion SET reemplazado_por = ? WHERE id = ?", (nuevo, fila["id"]))
    return nuevo, version, "nueva_version" if vigentes else "nuevo"


def rename(conn: DatabaseConnection, formato_id: int, nombre: str) -> bool:
    cursor = conn.execute("UPDATE formato_importacion SET nombre = ?, actualizado_en = ? WHERE id = ?",
                          (nombre, now(), formato_id))
    return bool(cursor.rowcount)


def delete(conn: DatabaseConnection, formato_id: int) -> bool:
    """Forget a format. Imported data and saved maps are untouched; the import
    records that used it keep their full plan and lose only the link."""
    conn.execute("UPDATE formato_importacion SET reemplazado_por = NULL WHERE reemplazado_por = ?",
                 (formato_id,))
    cursor = conn.execute("DELETE FROM formato_importacion WHERE id = ?", (formato_id,))
    return bool(cursor.rowcount)


def registrar_importacion(conn: DatabaseConnection, *, base_id: int, tipo: str, archivo: str | None,
                          sha256: str | None, hoja: str | None, fila_encabezado: int | None,
                          plan: Mapping[str, Any], formato_id: int | None,
                          formato_version: int | None) -> int:
    cursor = conn.execute(
        "INSERT INTO importacion (base_id, tipo, archivo, sha256, hoja, fila_encabezado, plan_json,"
        " formato_id, formato_version, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (base_id, tipo, archivo, sha256, hoja, fila_encabezado, _canonico(plan),
         formato_id, formato_version, now()),
    )
    return require_rowid(cursor)


def importaciones(conn: DatabaseConnection, base_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM importacion WHERE base_id = ? ORDER BY id", (base_id,)).fetchall()
    return [{**dict(r), "plan": json.loads(r["plan_json"])} for r in rows]


def _forma(row: Any) -> dict[str, Any]:
    item = dict(row)
    config = json.loads(item.pop("config_json"))
    item["firma"] = json.loads(item["firma"])
    item.update(config)
    return item

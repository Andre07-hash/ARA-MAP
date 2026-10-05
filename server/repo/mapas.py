"""Data access for saved maps.

A saved map is a FROZEN record. Creating one copies the terrains it shows into
``mapa_terreno``, so reopening it months later shows exactly what was saved even
if the source base was edited or deleted since. "Actualizar" re-takes the
snapshot on demand.

Layers therefore keep the base name alongside the id, and ``mapa_capa.base_id``
is deliberately not a foreign key: the snapshot has to outlive its source.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from ..db import now, require_rowid
from ..protocols import DatabaseConnection
from ..validation import UBICACION_VALIDA, location_state, sql_ubicacion_valida

Capa = Mapping[str, Any]


def display_label(base_nombre: str, version_etiqueta: str | None) -> str:
    """What a layer is called on screen: its source, plus a version qualifier.

    Stored apart so renaming a source rewrites only the first part and cannot
    erase what distinguishes two snapshots of it.
    """
    return f"{base_nombre} · {version_etiqueta}" if version_etiqueta else base_nombre

# Columns copied from a live terrain into the frozen snapshot.
SNAPSHOT_FIELDS = (
    "orden", "id_origen", "terreno", "estado", "municipio", "direccion",
    "superficie_m2", "superficie_ha", "afectaciones_pct", "afectaciones_m2",
    "asking_price", "asking_m2", "lat", "lon", "clave_dedupe", "extra_json", "moneda",
)


def create(
    conn: DatabaseConnection,
    nombre: str,
    tipo: str,
    capas: Sequence[Capa],
    config: dict[str, Any] | None = None,
    sigue_base: bool = False,
    carpeta_id: int | None = None,
) -> int:
    """Create a saved map and freeze the terrains of every layer into it.

    ``sigue_base`` records that the title was left at the source's name, so a
    later rename of that source carries through to this map's title.
    ``carpeta_id`` is the map folder it is saved into, already checked.
    """
    cursor = conn.execute(
        "INSERT INTO mapa (nombre, tipo, creado_en, actualizado_en, config_json,"
        " nombre_sigue_base, carpeta_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nombre, tipo, now(), now(), json.dumps(config or {}, ensure_ascii=False),
         1 if sigue_base else 0, carpeta_id),
    )
    mapa_id = require_rowid(cursor)
    _write_capas(conn, mapa_id, capas)
    refresh_snapshot(conn, mapa_id)
    return mapa_id


def update(
    conn: DatabaseConnection,
    mapa_id: int,
    *,
    nombre: str | None = None,
    capas: Sequence[Capa] | None = None,
    config: dict[str, Any] | None = None,
    sigue_base: bool | None = None,
) -> None:
    """Change a saved map. Only the arguments passed are touched.

    Replacing the layers re-freezes the snapshot, since the map now shows
    something different.
    """
    if nombre is not None:
        # Naming a map deliberately turns off following the source, unless the
        # caller says otherwise in the same breath.
        conn.execute(
            "UPDATE mapa SET nombre = ?, nombre_sigue_base = ? WHERE id = ?",
            (nombre, 1 if sigue_base else 0, mapa_id),
        )
    elif sigue_base is not None:
        conn.execute(
            "UPDATE mapa SET nombre_sigue_base = ? WHERE id = ?",
            (1 if sigue_base else 0, mapa_id),
        )
    if config is not None:
        conn.execute(
            "UPDATE mapa SET config_json = ? WHERE id = ?",
            (json.dumps(config, ensure_ascii=False), mapa_id),
        )
    if capas is not None:
        _write_capas(conn, mapa_id, capas)
        refresh_snapshot(conn, mapa_id)


def refresh_snapshot(conn: DatabaseConnection, mapa_id: int) -> dict[str, int]:
    """Re-copy each layer's terrains from its source base.

    Layers whose base no longer exists keep the terrains they already hold --
    the point of a snapshot is that deleting a base does not empty it. Returns
    how many layers were refreshed and how many were kept as they were.
    """
    capas = conn.execute(
        "SELECT orden, base_id FROM mapa_capa WHERE mapa_id = ? ORDER BY orden",
        (mapa_id,),
    ).fetchall()

    actualizadas = conservadas = 0
    for capa in capas:
        base_id = capa["base_id"]
        # Fetch the name, not merely whether the row exists: an old saved map
        # whose source was renamed recovers its label on refresh.
        fuente = None if base_id is None else conn.execute(
            "SELECT nombre FROM base WHERE id = ?", (base_id,)
        ).fetchone()

        if fuente is None:
            conservadas += 1
            continue

        conn.execute(
            "UPDATE mapa_capa SET base_nombre = ? WHERE mapa_id = ? AND orden = ?",
            (fuente["nombre"], mapa_id, capa["orden"]),
        )
        conn.execute(
            "DELETE FROM mapa_terreno WHERE mapa_id = ? AND capa_orden = ?",
            (mapa_id, capa["orden"]),
        )
        _copy_base_into_layer(conn, mapa_id, capa["orden"], base_id)
        actualizadas += 1

    conn.execute(
        "UPDATE mapa SET actualizado_en = ? WHERE id = ?", (now(), mapa_id)
    )
    return {"actualizadas": actualizadas, "conservadas": conservadas}


def _copy_base_into_layer(
    conn: DatabaseConnection, mapa_id: int, capa_orden: int, base_id: int
) -> None:
    columnas = ", ".join(SNAPSHOT_FIELDS)
    marcadores = ", ".join(f":{f}" for f in SNAPSHOT_FIELDS)

    for row in conn.execute("SELECT * FROM terreno WHERE base_id = ? ORDER BY orden", (base_id,)):
        incidencias = [
            {"severidad": i["severidad"], "codigo": i["codigo"], "mensaje": i["mensaje"]}
            for i in conn.execute(
                "SELECT severidad, codigo, mensaje FROM incidencia WHERE terreno_id = ?",
                (row["id"],),
            )
        ]
        params = {f: row[f] for f in SNAPSHOT_FIELDS}
        params.update(
            mapa_id=mapa_id,
            capa_orden=capa_orden,
            terreno_id=row["id"],
            incidencias_json=json.dumps(incidencias, ensure_ascii=False),
        )
        conn.execute(
            f"INSERT INTO mapa_terreno (mapa_id, capa_orden, terreno_id, {columnas},"
            f" incidencias_json) VALUES (:mapa_id, :capa_orden, :terreno_id, {marcadores},"
            " :incidencias_json)",
            params,
        )


def _write_capas(conn: DatabaseConnection, mapa_id: int, capas: Sequence[Capa]) -> None:
    conn.execute("DELETE FROM mapa_capa WHERE mapa_id = ?", (mapa_id,))
    conn.execute("DELETE FROM mapa_terreno WHERE mapa_id = ?", (mapa_id,))

    for orden, capa in enumerate(capas):
        base_id = capa.get("base_id")
        nombre = capa.get("base_nombre")
        if nombre is None and base_id is not None:
            row = conn.execute("SELECT nombre FROM base WHERE id = ?", (base_id,)).fetchone()
            nombre = row["nombre"] if row else "Base eliminada"
        conn.execute(
            "INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre,"
            " version_etiqueta, color, visible) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mapa_id, orden, base_id, nombre or "Base eliminada",
             capa.get("version_etiqueta"),
             capa.get("color") or "#2a78d6", 1 if capa.get("visible", True) else 0),
        )


def layer_fingerprint(conn: DatabaseConnection, mapa_id: int, capa_orden: int) -> str:
    """A hash of a layer's frozen contents.

    Merging deduplicates on this rather than on the source id. Two snapshots of
    the same source taken at different times hold different terrains, and
    collapsing them would destroy exactly the history the merge exists to show.
    """
    digest = hashlib.sha256()
    for row in conn.execute(
        f"SELECT {', '.join(_HUELLA)}, moneda"
        " FROM mapa_terreno WHERE mapa_id = ? AND capa_orden = ? ORDER BY orden",
        (mapa_id, capa_orden),
    ):
        # Values by name, never tuple(row): a Postgres row is a mapping, and
        # iterating it yields column NAMES -- every layer would hash the same
        # and a merge would drop all but one as "duplicates".
        valores = tuple(row[c] for c in _HUELLA)
        # A known currency is part of the content (600 USD is not 600 MXN);
        # an unknown one adds nothing, so older layers hash exactly as before.
        if row["moneda"]:
            valores += (row["moneda"],)
        digest.update(repr(valores).encode("utf-8"))
    return digest.hexdigest()


# The frozen columns a layer's fingerprint covers, besides its currency.
_HUELLA = ("terreno", "superficie_m2", "asking_price", "asking_m2", "lat", "lon", "clave_dedupe")


def plan_merge(conn: DatabaseConnection, mapa_ids: Sequence[int]) -> dict[str, Any]:
    """Work out which layers a merge of these saved maps would produce.

    Only layers holding exactly the same frozen terrains are treated as
    duplicates. Different snapshots of one source are kept, and labelled with
    the map they came from so they can be told apart.
    """
    candidatas: list[dict[str, Any]] = []
    duplicadas: list[dict[str, Any]] = []
    vistos: dict[str, dict[str, Any]] = {}

    for mapa_id in mapa_ids:
        mapa = get(conn, mapa_id)
        if mapa is None:
            continue
        for capa in mapa["capas"]:
            huella = layer_fingerprint(conn, mapa_id, capa["orden"])
            entrada = {
                "mapa_id": mapa_id,
                "mapa_nombre": mapa["nombre"],
                "mapa_creado_en": mapa["creado_en"],
                "orden_origen": capa["orden"],
                "base_id": capa["base_id"],
                "base_nombre": capa["nombre"],
                "conteo": capa["conteo"],
                "ubicados": capa["ubicados"],
                "huella": huella,
            }
            if huella in vistos:
                duplicadas.append({**entrada, "igual_a": vistos[huella]["mapa_nombre"]})
            else:
                vistos[huella] = entrada
                candidatas.append(entrada)

    return {"capas": _label_versions(candidatas), "duplicadas": duplicadas}


def _label_versions(capas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Disambiguate layers that share a source but hold different snapshots."""
    por_nombre: dict[str, int] = {}
    for capa in capas:
        por_nombre[capa["base_nombre"]] = por_nombre.get(capa["base_nombre"], 0) + 1

    etiquetadas = []
    for capa in capas:
        repetido = por_nombre[capa["base_nombre"]] > 1
        version = capa["mapa_nombre"] if repetido else None
        etiquetadas.append({
            **capa,
            "version_etiqueta": version,
            "etiqueta": display_label(capa["base_nombre"], version),
            "es_version": repetido,
        })
    return etiquetadas


def merge(
    conn: DatabaseConnection,
    nombre: str,
    mapa_ids: Sequence[int],
    colores: Sequence[str],
    config: dict[str, Any] | None = None,
    carpeta_id: int | None = None,
) -> int:
    """Build a new saved map from the frozen contents of existing saved maps.

    The terrains are copied from the source maps, not re-read from the bases,
    so a merge of two historical snapshots stays historical. The new map goes
    into ``carpeta_id``, whatever folders its sources are in.
    """
    plan = plan_merge(conn, mapa_ids)

    cursor = conn.execute(
        "INSERT INTO mapa (nombre, tipo, creado_en, actualizado_en, config_json, carpeta_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (nombre, "comparacion", now(), now(), json.dumps(config or {}, ensure_ascii=False),
         carpeta_id),
    )
    mapa_id = require_rowid(cursor)

    columnas = ", ".join(SNAPSHOT_FIELDS)
    marcadores = ", ".join(f":{f}" for f in SNAPSHOT_FIELDS)

    for orden, capa in enumerate(plan["capas"]):
        color = colores[orden] if orden < len(colores) else "#2a78d6"
        conn.execute(
            "INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre,"
            " version_etiqueta, color, visible) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (mapa_id, orden, capa["base_id"], capa["base_nombre"],
             capa.get("version_etiqueta"), color),
        )
        for row in conn.execute(
            "SELECT * FROM mapa_terreno WHERE mapa_id = ? AND capa_orden = ? ORDER BY orden",
            (capa["mapa_id"], capa["orden_origen"]),
        ).fetchall():
            params = {f: row[f] for f in SNAPSHOT_FIELDS}
            params.update(
                mapa_id=mapa_id,
                capa_orden=orden,
                terreno_id=row["terreno_id"],
                incidencias_json=row["incidencias_json"],
            )
            conn.execute(
                f"INSERT INTO mapa_terreno (mapa_id, capa_orden, terreno_id, {columnas},"
                f" incidencias_json) VALUES (:mapa_id, :capa_orden, :terreno_id, {marcadores},"
                " :incidencias_json)",
                params,
            )

    return mapa_id


def listing(conn: DatabaseConnection) -> list[dict[str, Any]]:
    """Every saved map, newest first, each with its layers."""
    rows = conn.execute("SELECT * FROM mapa ORDER BY creado_en DESC, id DESC").fetchall()
    return [_shape(conn, row) for row in rows]


def get(conn: DatabaseConnection, mapa_id: int) -> dict[str, Any] | None:
    """One saved map with its layers, or None if it does not exist."""
    row = conn.execute("SELECT * FROM mapa WHERE id = ?", (mapa_id,)).fetchone()
    return _shape(conn, row) if row else None


def delete(conn: DatabaseConnection, mapa_id: int) -> None:
    """Delete a saved map. The bases it was taken from are left alone."""
    conn.execute("DELETE FROM mapa WHERE id = ?", (mapa_id,))


def terrenos(conn: DatabaseConnection, mapa_id: int) -> list[dict[str, Any]]:
    """The frozen terrains of a saved map, tagged with their layer."""
    capas = {}
    for c in conn.execute(
        "SELECT orden, base_id, base_nombre, version_etiqueta, color"
        " FROM mapa_capa WHERE mapa_id = ?", (mapa_id,)
    ):
        capa = dict(c)
        capa["nombre"] = display_label(c["base_nombre"], c["version_etiqueta"])
        capas[c["orden"]] = capa

    filas = []
    for row in conn.execute(
        "SELECT * FROM mapa_terreno WHERE mapa_id = ? ORDER BY capa_orden, orden",
        (mapa_id,),
    ):
        item = dict(row)
        capa = capas.get(item["capa_orden"], {})
        item["extra"] = json.loads(item.pop("extra_json") or "{}")
        item["incidencias"] = json.loads(item.pop("incidencias_json") or "[]")
        item["ubicacion"] = location_state(item["lat"], item["lon"])
        item["ubicado"] = item["ubicacion"] == UBICACION_VALIDA
        item["capa"] = item["capa_orden"]
        item["base_id"] = capa.get("base_id")
        item["base_nombre"] = capa.get("nombre")
        item["color"] = capa.get("color")
        filas.append(item)
    return filas


def _shape(conn: DatabaseConnection, row: sqlite3.Row) -> dict[str, Any]:
    capas = []
    for capa in conn.execute(
        "SELECT orden, base_id, base_nombre, version_etiqueta, color, visible"
        " FROM mapa_capa WHERE mapa_id = ? ORDER BY orden",
        (row["id"],),
    ):
        conteo = conn.execute(
            "SELECT COUNT(*) AS n,"
            f" COALESCE(SUM(CASE WHEN {sql_ubicacion_valida()} THEN 1 ELSE 0 END), 0) AS ubicados"
            " FROM mapa_terreno WHERE mapa_id = ? AND capa_orden = ?",
            (row["id"], capa["orden"]),
        ).fetchone()
        base_existe = capa["base_id"] is not None and conn.execute(
            "SELECT 1 FROM base WHERE id = ? LIMIT 1", (capa["base_id"],)
        ).fetchone() is not None

        capas.append({
            "orden": capa["orden"],
            "base_id": capa["base_id"],
            "nombre": display_label(capa["base_nombre"], capa["version_etiqueta"]),
            "base_nombre": capa["base_nombre"],
            "version_etiqueta": capa["version_etiqueta"],
            "color": capa["color"],
            "visible": bool(capa["visible"]),
            "conteo": conteo["n"],
            "ubicados": conteo["ubicados"],
            "base_existe": base_existe,
        })

    item = dict(row)
    item["config"] = json.loads(item.pop("config_json") or "{}")
    item["nombre_sigue_base"] = bool(item.get("nombre_sigue_base"))
    item["capas"] = capas
    item["conteo"] = sum(c["conteo"] for c in capas)
    item["ubicados"] = sum(c["ubicados"] for c in capas)
    return item

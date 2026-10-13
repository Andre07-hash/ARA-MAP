"""Data access for a work base's custom-column definitions.

Each definition is its own versioned resource: a change is a compare-and-set
on inventory_column.version and leaves one maestra_base_event carrying the
column id, the actor and the time. No terrain, revision or value is touched by
any of it: renaming or retiring a column changes how stored values are shown,
never the values, and never a terrain's version.

Callers are inside db.escritura(), already re-authorized with
auth.reverificar_base(..., exclusivo=True). That holds the base row
exclusively, so a definition change and a cell save in the same base (which
holds the base shared) never interleave.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from typing import Any

from .. import columnas, db
from ..protocols import DatabaseConnection

_SELECT = ("SELECT id, base_id, nombre, tipo, opciones_json, orden, version, retired_at,"
           " created_at, updated_at FROM inventory_column")


class ConflictError(Exception):
    """The caller's expected_version is no longer current."""


class EstadoError(Exception):
    """The definition is not in the state the action needs. ``code`` says which."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IdempotencyConflictError(Exception):
    """An Idempotency-Key was reused for a different request."""


# -- reads ---------------------------------------------------------------------

def listar(conn: DatabaseConnection, base_id: str, con_retiradas: bool = False,
           ) -> list[dict[str, Any]]:
    """The definitions of one base in display order, retired ones last."""
    rows = conn.execute(
        _SELECT + " WHERE base_id = ?" + ("" if con_retiradas else " AND retired_at IS NULL")
        + " ORDER BY retired_at IS NOT NULL, orden, id", (base_id,)).fetchall()
    return [_dto(r) for r in rows]


def vivas(conn: DatabaseConnection, base_id: str | None) -> dict[str, dict[str, Any]]:
    """The live definitions a value may be written under, by ``custom:<id>``."""
    return {} if base_id is None else {c["id"]: c for c in listar(conn, base_id)}


def obtener(conn: DatabaseConnection, base_id: str, column_id: str) -> dict[str, Any] | None:
    """One definition, only if it belongs to that base."""
    row = conn.execute(_SELECT + " WHERE id = ? AND base_id = ?", (column_id, base_id)).fetchone()
    return _dto(row) if row else None


# -- writes --------------------------------------------------------------------

def crear(conn: DatabaseConnection, base_id: str, nombre: str, tipo: str, opciones: list[str],
          actor: Mapping[str, Any], key: str, request_hash: str) -> dict[str, Any]:
    """A new definition at the end of the base's columns, or the one a repeated
    key already created. The key belongs to one actor in one base; only the id
    is stored, and a replay is answered from the definition as it is now."""
    operation = f"columna:{base_id}:{actor['id']}"
    previa = _guardada(conn, operation, key)
    if previa is None:
        _libre(conn, base_id, nombre)
        if len(listar(conn, base_id)) >= columnas.MAX_COLUMNAS:
            raise EstadoError("limite_columnas")
        try:
            with db.transaction(conn):
                return _crear(conn, base_id, nombre, tipo, opciones, actor, operation, key,
                              request_hash)
        except Exception as exc:
            if not isinstance(exc, sqlite3.IntegrityError) and type(exc).__name__ not in {
                    "UniqueViolation", "IntegrityError"}:
                raise
        previa = _guardada(conn, operation, key)
        if previa is None:
            raise RuntimeError("Idempotency collision without a stored result.")
    if previa["request_hash"] != request_hash:
        raise IdempotencyConflictError()
    return _existente(conn, base_id, str(json.loads(previa["result_json"])["id"]))


def _crear(conn: DatabaseConnection, base_id: str, nombre: str, tipo: str, opciones: list[str],
           actor: Mapping[str, Any], operation: str, key: str, request_hash: str) -> dict[str, Any]:
    column_id, ahora = str(uuid.uuid4()), db.now()
    conn.execute(
        "INSERT INTO inventory_operation_result (operation, idempotency_key, request_hash,"
        " result_json, actor_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (operation, key, request_hash, json.dumps({"id": column_id}), actor["id"], ahora))
    ultimo = conn.execute("SELECT COALESCE(MAX(orden), 0) AS n FROM inventory_column"
                          " WHERE base_id = ?", (base_id,)).fetchone()["n"]
    conn.execute(
        "INSERT INTO inventory_column (id, base_id, nombre, tipo, opciones_json, orden, version,"
        " created_at, created_by, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
        (column_id, base_id, nombre, tipo, json.dumps(opciones, ensure_ascii=False), ultimo + 1,
         ahora, actor["id"], ahora, actor["id"]))
    _evento(conn, base_id, column_id, 1, "columna_crear", actor, ahora,
            {"nombre": nombre, "tipo": tipo, "opciones": opciones})
    return _existente(conn, base_id, column_id)


def cambiar(conn: DatabaseConnection, base_id: str, column_id: str, expected_version: int,
            actor: Mapping[str, Any], nombre: str | None = None,
            opciones: list[str] | None = None, posicion: int | None = None) -> dict[str, Any]:
    """Rename, add choices and/or move one live definition: one version, one
    event. A request that changes nothing returns it as it is.

    ``opciones`` is the complete list afterwards and must keep every existing
    choice, in order, before any new one: removing or renaming a choice that
    values may hold is not offered. ``posicion`` is the 0-based place among the
    base's live columns; the others keep their relative order and only the
    moved definition gets a new version.
    """
    actual = _vigente(conn, base_id, column_id, expected_version)
    if actual["retirada"]:
        raise EstadoError("columna_retirada")
    detalles: dict[str, Any] = {}
    asignar, params = [], []
    if nombre is not None and nombre != actual["nombre"]:
        _libre(conn, base_id, nombre, excepto=column_id)
        detalles["nombre"] = {"antes": actual["nombre"], "despues": nombre}
        asignar.append("nombre = ?")
        params.append(nombre)
    if opciones is not None and opciones != actual["opciones"]:
        if actual["tipo"] != "opcion":
            raise EstadoError("sin_opciones")
        if opciones[:len(actual["opciones"])] != actual["opciones"]:
            raise EstadoError("opciones_solo_se_agregan")
        detalles["opciones_agregadas"] = opciones[len(actual["opciones"]):]
        asignar.append("opciones_json = ?")
        params.append(json.dumps(opciones, ensure_ascii=False))
    orden = [c["id"] for c in listar(conn, base_id)]
    if posicion is not None:
        previa = orden.index(actual["id"])
        nueva = max(0, min(posicion, len(orden) - 1))
        if nueva != previa:
            orden.insert(nueva, orden.pop(previa))
            detalles["posicion"] = {"antes": previa, "despues": nueva}
    if not detalles:
        return actual
    ahora = db.now()
    with db.transaction(conn):
        _reclamar(conn, column_id, expected_version, actor, ahora, ", ".join(asignar), tuple(params))
        if "posicion" in detalles:
            _reordenar(conn, base_id, orden)
        _evento(conn, base_id, column_id, expected_version + 1, "columna_cambiar", actor, ahora,
                detalles)
    return _existente(conn, base_id, column_id)


def retirar(conn: DatabaseConnection, base_id: str, column_id: str, expected_version: int,
            actor: Mapping[str, Any], restaurar: bool = False) -> dict[str, Any]:
    """Retire a definition, or restore it. Its values and their history stay
    stored either way; a retired column is simply shown and written by nobody."""
    actual = _vigente(conn, base_id, column_id, expected_version)
    if actual["retirada"] != restaurar:
        raise EstadoError("columna_no_retirada" if restaurar else "columna_retirada")
    if restaurar:
        _libre(conn, base_id, actual["nombre"], excepto=column_id)
        if len(listar(conn, base_id)) >= columnas.MAX_COLUMNAS:
            raise EstadoError("limite_columnas")
    ahora = db.now()
    with db.transaction(conn):
        _reclamar(conn, column_id, expected_version, actor, ahora,
                  "retired_at = ?, retired_by = ?",
                  (None, None) if restaurar else (ahora, actor["id"]))
        _evento(conn, base_id, column_id, expected_version + 1,
                "columna_restaurar" if restaurar else "columna_retirar", actor, ahora)
    return _existente(conn, base_id, column_id)


# -- helpers -------------------------------------------------------------------

def _guardada(conn: DatabaseConnection, operation: str, key: str) -> Any:
    return conn.execute(
        "SELECT request_hash, result_json FROM inventory_operation_result"
        " WHERE operation = ? AND idempotency_key = ?", (operation, key)).fetchone()


def _libre(conn: DatabaseConnection, base_id: str, nombre: str, excepto: str | None = None) -> None:
    """Two live columns of one base never share a name (case and accents aside)."""
    buscado, propia = columnas.plegado(nombre), columnas.clave(excepto or "")
    if any(columnas.plegado(c["nombre"]) == buscado and c["id"] != propia
           for c in listar(conn, base_id)):
        raise EstadoError("nombre_duplicado")


def _vigente(conn: DatabaseConnection, base_id: str, column_id: str,
             expected_version: int) -> dict[str, Any]:
    actual = obtener(conn, base_id, column_id)
    if actual is None:
        raise LookupError(column_id)
    if actual["version"] != expected_version:
        raise ConflictError()
    return actual


def _existente(conn: DatabaseConnection, base_id: str, column_id: str) -> dict[str, Any]:
    columna = obtener(conn, base_id, column_id)
    assert columna is not None
    return columna


def _reclamar(conn: DatabaseConnection, column_id: str, expected_version: int,
              actor: Mapping[str, Any], ahora: str, cambios: str, params: tuple[Any, ...]) -> None:
    """The compare-and-set. Zero rows means someone else got there first."""
    cursor = conn.execute(
        "UPDATE inventory_column SET version = version + 1, updated_at = ?, updated_by = ?"
        + (", " + cambios if cambios else "") + " WHERE id = ? AND version = ?",
        (ahora, actor["id"], *params, column_id, expected_version))
    if cursor.rowcount != 1:
        raise ConflictError()


def _reordenar(conn: DatabaseConnection, base_id: str, vivas_en_orden: list[str]) -> None:
    """Renumber the base's columns: the live ones as given, retired ones after
    them in their previous order. Position is all this changes."""
    retiradas = [c["id"] for c in listar(conn, base_id, con_retiradas=True) if c["retirada"]]
    for n, clave in enumerate([*vivas_en_orden, *retiradas], start=1):
        conn.execute("UPDATE inventory_column SET orden = ? WHERE id = ? AND orden <> ?",
                     (n, columnas.id_de_clave(clave), n))


def _evento(conn: DatabaseConnection, base_id: str, column_id: str, version: int, action: str,
            actor: Mapping[str, Any], ahora: str, details: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO maestra_base_event (id, base_id, column_id, version, action, actor_id,"
        " actor_name, at, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), base_id, column_id, version, action, actor["id"],
         actor["display_name"], ahora,
         json.dumps(details, ensure_ascii=False) if details else None))


def _opciones(crudo: Any) -> list[str]:
    """Stored choices. A row written before these rules is served as it is,
    and anything that is not a list of strings counts as no choices."""
    try:
        valor = json.loads(crudo or "[]")
    except ValueError:
        return []
    return [o for o in valor if isinstance(o, str)] if isinstance(valor, list) else []


def _dto(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": columnas.clave(row["id"]), "base_id": row["base_id"], "nombre": row["nombre"],
            "tipo": row["tipo"], "opciones": _opciones(row["opciones_json"]),
            "orden": row["orden"], "version": row["version"],
            "retirada": row["retired_at"] is not None, "retired_at": row["retired_at"],
            "created_at": row["created_at"], "updated_at": row["updated_at"]}

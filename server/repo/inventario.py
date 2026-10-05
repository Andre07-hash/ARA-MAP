"""Data access for the shared terrain inventory.

Writes are compare-and-set on inventory_terrain.version, in the same
transaction as the new immutable revision, the pointer change and the history
event: either all of them land or none do. In SQLite the first statement of
each write transaction is itself a write, so it waits for the write lock
instead of failing on a stale read snapshot.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from typing import Any

from .. import db, inventario
from ..protocols import DatabaseConnection

REVISION_FIELDS = inventario.EDITABLE

_SELECT = f"""
SELECT t.id, t.version, t.draft_revision_id, t.published_revision_id, t.published_at,
       t.first_published_at, t.archived_at, t.created_at, t.updated_at,
       t.created_by, cu.display_name AS created_by_name,
       t.updated_by, uu.display_name AS updated_by_name,
       d.revision_number, d.extra_json,
       {", ".join(f"d.{f}" for f in REVISION_FIELDS)},
       d.price_confirmed_at, d.price_confirmed_by, pu.display_name AS price_confirmed_by_name,
       d.availability_confirmed_at, d.availability_confirmed_by,
       au.display_name AS availability_confirmed_by_name,
       p.availability AS published_availability
FROM inventory_terrain t
JOIN inventory_revision d ON d.id = t.draft_revision_id
LEFT JOIN inventory_revision p ON p.id = t.published_revision_id
JOIN team_user cu ON cu.id = t.created_by
JOIN team_user uu ON uu.id = t.updated_by
LEFT JOIN team_user pu ON pu.id = d.price_confirmed_by
LEFT JOIN team_user au ON au.id = d.availability_confirmed_by
"""


class ConflictError(Exception):
    """The caller's expected_version is no longer current."""


class IdempotencyConflictError(Exception):
    """An Idempotency-Key was reused for a different request."""


# -- reads ---------------------------------------------------------------------

def get(conn: DatabaseConnection, inventory_id: str) -> dict[str, Any] | None:
    row = conn.execute(_SELECT + " WHERE t.id = ?", (inventory_id,)).fetchone()
    return _dto(row) if row else None


def all_records(conn: DatabaseConnection) -> list[dict[str, Any]]:
    """Every record as InternalTerrain, for filtering in one consistent read.

    ponytail: the whole inventory is filtered in Python. Fine for hundreds to a
    few thousand rows; move the business filters into SQL past that.
    """
    return [_dto(r) for r in conn.execute(_SELECT).fetchall()]


def history(conn: DatabaseConnection, inventory_id: str, before_version: int | None,
            limit: int) -> tuple[list[dict[str, Any]], int, int | None]:
    """Events newest first. Returns (page, total, next cursor)."""
    total = conn.execute("SELECT COUNT(*) AS n FROM inventory_event WHERE inventory_id = ?",
                         (inventory_id,)).fetchone()["n"]
    rows = conn.execute(
        "SELECT id, version, action, actor_id, actor_name, at, before_revision_id,"
        " after_revision_id, details_json FROM inventory_event"
        " WHERE inventory_id = ? AND version < ? ORDER BY version DESC LIMIT ?",
        (inventory_id, before_version if before_version is not None else 2**62, limit + 1),
    ).fetchall()
    eventos = [{
        "id": r["id"], "version": r["version"], "action": r["action"], "at": r["at"],
        "actor": {"id": r["actor_id"], "display_name": r["actor_name"]},
        "before_revision_id": r["before_revision_id"], "after_revision_id": r["after_revision_id"],
        **json.loads(r["details_json"] or "{}"),
    } for r in rows[:limit]]
    return eventos, int(total), (eventos[-1]["version"] if len(rows) > limit else None)


def stored_result(conn: DatabaseConnection, operation: str, key: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT request_hash, result_json FROM inventory_operation_result"
        " WHERE operation = ? AND idempotency_key = ?", (operation, key)).fetchone()
    if row is None:
        return None
    return {"request_hash": row["request_hash"], "result": json.loads(row["result_json"])}


# -- writes --------------------------------------------------------------------

def create(conn: DatabaseConnection, fields: Mapping[str, Any], actor: Mapping[str, Any],
           key: str, request_hash: str) -> dict[str, Any]:
    """Create a draft record, or replay the original result for a repeated key.
 The idempotency row is the transaction's first
    write: a concurrent request with the same key waits for it, then collides.
    """
    previous = stored_result(conn, "create", key)
    if previous is None:
        try:
            with db.transaction(conn):
                return _create(conn, fields, actor, key, request_hash)
        except Exception as exc:
            if not _unique_violation(exc):
                raise
        previous = stored_result(conn, "create", key)
        if previous is None:
            raise RuntimeError("Idempotency collision without a stored result.")
    if previous["request_hash"] != request_hash:
        raise IdempotencyConflictError()
    result: dict[str, Any] = previous["result"]
    return result


def _create(conn: DatabaseConnection, fields: Mapping[str, Any], actor: Mapping[str, Any],
            key: str, request_hash: str) -> dict[str, Any]:
    ahora = db.now()
    conn.execute(
        "INSERT INTO inventory_operation_result (operation, idempotency_key, request_hash,"
        " result_json, actor_id, created_at) VALUES ('create', ?, ?, '{}', ?, ?)",
        (key, request_hash, actor["id"], ahora))
    inventory_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO inventory_terrain (id, version, created_at, created_by, updated_at, updated_by)"
        " VALUES (?, 1, ?, ?, ?, ?)", (inventory_id, ahora, actor["id"], ahora, actor["id"]))
    draft = {**inventario.empty_draft(), **fields}
    revision_id = _insert_revision(conn, inventory_id, 1, draft, {}, actor, ahora)
    conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?",
                 (revision_id, inventory_id))
    cambios = {n: {"before": None, "after": v} for n, v in draft.items()
               if v != inventario.empty_draft()[n]}
    _event(conn, inventory_id, 1, "create", actor, ahora, None, revision_id, {"changes": cambios})
    body = {"terreno": get(conn, inventory_id)}
    conn.execute("UPDATE inventory_operation_result SET result_json = ?"
                 " WHERE operation = 'create' AND idempotency_key = ?",
                 (json.dumps(body, ensure_ascii=False), key))
    return body


def update(conn: DatabaseConnection, inventory_id: str, expected_version: int,
           changes: Mapping[str, Any], confirm: tuple[str, ...],
           actor: Mapping[str, Any]) -> dict[str, Any]:
    """Save a new draft revision. Raises ConflictError if expected_version is stale.

    A change that alters nothing (and confirms nothing) returns the record as
    it is, without a new version.
    """
    current = get(conn, inventory_id)
    if current is None:
        raise LookupError(inventory_id)
    if current["version"] != expected_version:
        raise ConflictError()
    before = current["draft"]
    draft = {**before, **changes}
    cambios = {n: {"before": before[n], "after": draft[n]} for n in REVISION_FIELDS
               if draft[n] != before[n]}
    if not cambios and not confirm:
        return current

    ahora = db.now()
    with db.transaction(conn):
        _claim(conn, inventory_id, expected_version, actor, ahora)
        stamps = {name: {"at": ahora, "id": actor["id"]} for name in confirm}
        for name in inventario.CONFIRMABLE:
            if name not in stamps and current["confirmations"][name]:
                previous = current["confirmations"][name]
                stamps[name] = {"at": previous["at"], "id": previous["by"]["id"]}
        # Raw source extras are not editable: they ride along unchanged.
        extra_json = conn.execute("SELECT extra_json FROM inventory_revision WHERE id = ?",
                                  (current["draft_revision_id"],)).fetchone()["extra_json"]
        revision_id = _insert_revision(conn, inventory_id, current["revision_number"] + 1,
                                       draft, stamps, actor, ahora, extra_json)
        conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?",
                     (revision_id, inventory_id))
        details: dict[str, Any] = {"changes": cambios}
        if confirm:
            details["confirmed"] = list(confirm)
        _event(conn, inventory_id, expected_version + 1, "update", actor, ahora,
               current["draft_revision_id"], revision_id, details)
    result = get(conn, inventory_id)
    assert result is not None
    return result


def _claim(conn: DatabaseConnection, inventory_id: str, expected_version: int,
           actor: Mapping[str, Any], ahora: str) -> None:
    """The compare-and-set. Zero rows means someone else got there first."""
    cursor = conn.execute(
        "UPDATE inventory_terrain SET version = version + 1, updated_at = ?, updated_by = ?"
        " WHERE id = ? AND version = ?", (ahora, actor["id"], inventory_id, expected_version))
    if cursor.rowcount != 1:
        raise ConflictError()


def _insert_revision(conn: DatabaseConnection, inventory_id: str, number: int,
                     draft: Mapping[str, Any], stamps: Mapping[str, Mapping[str, str]],
                     actor: Mapping[str, Any], ahora: str, extra_json: str | None = None) -> str:
    revision_id = str(uuid.uuid4())
    values = {f: draft[f] for f in REVISION_FIELDS}
    values["price_on_request"] = 1 if draft["price_on_request"] else 0
    columns = ["id", "inventory_id", "revision_number", *REVISION_FIELDS, "extra_json",
               "price_confirmed_at", "price_confirmed_by", "availability_confirmed_at",
               "availability_confirmed_by", "created_at", "created_by"]
    params = [revision_id, inventory_id, number, *values.values(), extra_json,
              stamps.get("price", {}).get("at"), stamps.get("price", {}).get("id"),
              stamps.get("availability", {}).get("at"), stamps.get("availability", {}).get("id"),
              ahora, actor["id"]]
    conn.execute(f"INSERT INTO inventory_revision ({', '.join(columns)})"
                 f" VALUES ({', '.join('?' for _ in columns)})", tuple(params))
    return revision_id


def _event(conn: DatabaseConnection, inventory_id: str, version: int, action: str,
           actor: Mapping[str, Any], ahora: str, before: str | None, after: str | None,
           details: Mapping[str, Any]) -> None:
    conn.execute(
        "INSERT INTO inventory_event (id, inventory_id, version, action, actor_id, actor_name, at,"
        " before_revision_id, after_revision_id, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), inventory_id, version, action, actor["id"], actor["display_name"],
         ahora, before, after, json.dumps(details, ensure_ascii=False)))


def _unique_violation(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    return type(exc).__name__ in {"UniqueViolation", "IntegrityError"}


# -- the InternalTerrain DTO ------------------------------------------------------

def publication_state(row: Mapping[str, Any]) -> str:
    if row["archived_at"]:
        return "archived"
    if row["published_revision_id"]:
        return "published"
    return "unpublished" if row["first_published_at"] else "draft"


def _dto(row: Mapping[str, Any]) -> dict[str, Any]:
    draft = {f: row[f] for f in REVISION_FIELDS}
    draft["price_on_request"] = bool(row["price_on_request"])

    def stamp(prefix: str) -> dict[str, Any] | None:
        if not row[f"{prefix}_confirmed_at"]:
            return None
        return {"at": row[f"{prefix}_confirmed_at"],
                "by": {"id": row[f"{prefix}_confirmed_by"],
                       "display_name": row[f"{prefix}_confirmed_by_name"]}}

    confirmations = {"price": stamp("price"), "availability": stamp("availability")}
    state = publication_state(row)
    return {
        "id": row["id"],
        "version": row["version"],
        "draft_revision_id": row["draft_revision_id"],
        "published_revision_id": row["published_revision_id"],
        "publication_state": state,
        "public_visible": state == "published"
        and row["published_availability"] in inventario.PUBLIC_AVAILABILITY,
        "has_pending_changes": bool(row["published_revision_id"])
        and row["published_revision_id"] != row["draft_revision_id"],
        "published_at": row["published_at"],
        "archived_at": row["archived_at"],
        "draft": draft,
        "confirmations": confirmations,
        "source_extra": json.loads(row["extra_json"] or "{}"),
        "attention": inventario.attention(draft, confirmations),
        "revision_number": row["revision_number"],
        "created_at": row["created_at"],
        "created_by": {"id": row["created_by"], "display_name": row["created_by_name"]},
        "updated_at": row["updated_at"],
        "updated_by": {"id": row["updated_by"], "display_name": row["updated_by_name"]},
    }

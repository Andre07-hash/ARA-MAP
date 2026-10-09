"""Data access for the shared terrain inventory.

Writes are compare-and-set on inventory_terrain.version, in the same
transaction as the new immutable revision, the pointer change and the history
event: either all of them land or none do. In SQLite the first statement of
each write transaction is itself a write, so it waits for the write lock
instead of failing on a stale read snapshot.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from .. import db, inventario
from ..protocols import DatabaseConnection

REVISION_FIELDS = inventario.EDITABLE

_SELECT = f"""
SELECT t.id, t.version, t.draft_revision_id, t.published_revision_id, t.published_at,
       t.first_published_at, t.archived_at, t.created_at, t.updated_at, t.base_id,
       t.created_by, cu.display_name AS created_by_name,
       t.updated_by, uu.display_name AS updated_by_name,
       d.revision_number, d.extra_json, d.custom_json,
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
    return _dtos(conn, [row])[0] if row else None


class CursorError(ValueError):
    """A list cursor that is malformed or belongs to another sort order."""


_FROM = " FROM inventory_terrain t JOIN inventory_revision d ON d.id = t.draft_revision_id"
_BUSCADOS = ("terreno", "municipio", "estado", "direccion")
_ESTADOS_DE_PUBLICACION = {
    "archived": "t.archived_at IS NOT NULL",
    "published": "(t.archived_at IS NULL AND t.published_revision_id IS NOT NULL)",
    "unpublished": "(t.archived_at IS NULL AND t.published_revision_id IS NULL"
                   " AND t.first_published_at IS NOT NULL)",
    "draft": "(t.archived_at IS NULL AND t.published_revision_id IS NULL"
             " AND t.first_published_at IS NULL)",
}


def listar(conn: DatabaseConnection, q: Mapping[str, Any], base_id: str | None = None,
           ) -> tuple[list[dict[str, Any]], int, str | None, dict[str, list[str]]]:
    """One page of a terrain list: (records, total, next cursor, facets).

    ``base_id`` confines the whole query to one work base: the caller has
    already been authorized for it. None is the administrators' master table.
    Scope, filters, search, order, count and facets are all SQL over the same
    predicates, so a row outside the scope can reach none of them, and no more
    than one page of records is ever built.

    The cursor is a position in the chosen order, not a snapshot: a record
    edited or created between two pages may be seen twice or not at all.
    """
    candidatos, p_candidatos = _candidatos(q, base_id)
    filtros, p_filtros = _filtros(conn, q)
    donde = " WHERE " + " AND ".join(candidatos + filtros)
    params = p_candidatos + p_filtros
    orden, clave = _orden(conn, q["sort"])
    tras, p_tras = _tras_cursor(q["sort"], q["cursor"], clave)
    pagina_sql = (_SELECT.rstrip().replace("SELECT ", f"SELECT {clave} AS orden_clave, ", 1)
                  + donde + tras + orden)

    total = conn.execute("SELECT COUNT(*) AS n" + _FROM + donde, params).fetchone()["n"]
    rows = conn.execute(pagina_sql + " LIMIT ?", (*params, *p_tras, q["limit"] + 1)).fetchall()

    pagina = rows[:q["limit"]]
    siguiente = None
    if len(rows) > q["limit"]:
        ultimo = pagina[-1]
        siguiente = ultimo["id"] if q["sort"] == "id" else _cursor(q["sort"], ultimo)
    return (_dtos(conn, pagina), int(total), siguiente,
            _facetas(conn, q, " WHERE " + " AND ".join(candidatos), p_candidatos))


def _candidatos(q: Mapping[str, Any], base_id: str | None) -> tuple[list[str], tuple[Any, ...]]:
    """What the caller is looking at before any business filter: the scope,
    the base filter and whether archived records are in view. Facets are
    computed over exactly this, so choosing a filter never removes the options
    needed to change it."""
    partes: list[str] = ["1 = 1"]
    params: list[Any] = []
    if base_id is not None:
        partes.append("t.base_id = ?")
        params.append(base_id)
    elif q["base"]:
        ids = [b for b in q["base"] if b != inventario.SIN_ASIGNAR]
        opciones = []
        if ids:
            opciones.append(f"t.base_id IN ({', '.join('?' for _ in ids)})")
            params.extend(ids)
        if inventario.SIN_ASIGNAR in q["base"]:
            opciones.append("t.base_id IS NULL")
        partes.append("(" + " OR ".join(opciones) + ")")
    # Archived records only when asked for, either way.
    if not (q["include_archived"] or "archived" in q["publication_state"]):
        partes.append("t.archived_at IS NULL")
    return partes, tuple(params)


def _filtros(conn: DatabaseConnection, q: Mapping[str, Any]) -> tuple[list[str], tuple[Any, ...]]:
    """The business filters. Column names are fixed here; every value the
    client sent is a bound parameter."""
    partes: list[str] = []
    params: list[Any] = []
    for campo in ("estado", "municipio", "tipo_terreno", "availability"):
        if q[campo]:
            partes.append(f"d.{campo} IN ({', '.join('?' for _ in q[campo])})")
            params.extend(q[campo])
    for limite, signo in (("area_min_m2", ">="), ("area_max_m2", "<=")):
        if q[limite] is not None:
            partes.append(f"d.superficie_m2 {signo} ?")
            params.append(q[limite])
    if q["moneda"]:
        # One explicit currency; other and unknown currencies are left out.
        partes.append("d.moneda = ?")
        params.append(q["moneda"])
        monto = "d.asking_price" if q["price_basis"] == "total" else "d.asking_m2"
        for limite, signo in (("price_min", ">="), ("price_max", "<=")):
            if q[limite] is not None:
                partes.append(f"{monto} {signo} ?")
                params.append(q[limite])
    if q["publication_state"]:
        partes.append("(" + " OR ".join(_ESTADOS_DE_PUBLICACION[e]
                                        for e in q["publication_state"]) + ")")
    if q["attention"] is not None:
        partes.append(("" if q["attention"] else "NOT ") + inventario.sql_atencion("d"))
    buscado = db.plegar(" ".join(q["q"].split()))
    if buscado:
        junto = " || ' ' || ".join(f"COALESCE(d.{c}, '')" for c in _BUSCADOS)
        partes.append(f"{db.sql_plegar(conn, junto)} LIKE ? ESCAPE '!'")
        for especial in "!%_":
            buscado = buscado.replace(especial, "!" + especial)
        params.append(f"%{buscado}%")
    return partes, tuple(params)


def _orden(conn: DatabaseConnection, sort: str) -> tuple[str, str]:
    """(ORDER BY clause, sort-key expression). Missing values last in either
    direction; the id breaks ties, so the order is total."""
    campo = sort.lstrip("-")
    if campo == "id":
        clave = "t.id"
    elif campo == "updated_at":
        clave = "t.updated_at"
    elif inventario.SORTS[campo]:
        clave = db.sql_plegar(conn, f"d.{campo}")
    else:
        clave = f"d.{campo}"
    sentido = " DESC" if sort.startswith("-") else ""
    if campo == "id":  # never missing, and already unique: the primary key's own order
        return f" ORDER BY t.id{sentido}", clave
    return f" ORDER BY ({clave}) IS NULL, {clave}{sentido}, t.id", clave


def _cursor(sort: str, row: Mapping[str, Any]) -> str:
    crudo = json.dumps([sort, row["orden_clave"], row["id"]], ensure_ascii=False)
    return base64.urlsafe_b64encode(crudo.encode("utf-8")).decode("ascii")


def _tras_cursor(sort: str, cursor: str | None, clave: str) -> tuple[str, tuple[Any, ...]]:
    """The predicate for "after this cursor" in the chosen order. It is ANDed
    onto the scoped query, so no cursor can reach outside the scope."""
    if not cursor:
        return "", ()
    if sort == "id":
        return " AND t.id > ?", (cursor,)
    try:
        de, valor, ultimo = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        if de != sort or not isinstance(ultimo, str) or isinstance(valor, (list, dict, bool)):
            raise ValueError
    except (ValueError, TypeError, UnicodeError):
        raise CursorError() from None
    if valor is None:  # already among the missing values, which come last
        return f" AND ({clave}) IS NULL AND t.id > ?", (ultimo,)
    signo = "<" if sort.startswith("-") else ">"
    return (f" AND (({clave}) IS NULL OR {clave} {signo} ? OR ({clave} = ? AND t.id > ?))",
            (valor, valor, ultimo))


def _facetas(conn: DatabaseConnection, q: Mapping[str, Any], donde: str,
             params: tuple[Any, ...]) -> dict[str, list[str]]:
    """The distinct values in view. Municipalities narrow to the chosen states."""
    def distintos(campo: str, extra: str = "", mas: tuple[Any, ...] = ()) -> list[str]:
        rows = conn.execute(f"SELECT DISTINCT d.{campo} AS valor" + _FROM + donde
                            + f" AND d.{campo} IS NOT NULL" + extra, (*params, *mas)).fetchall()
        return sorted((r["valor"] for r in rows), key=lambda v: (db.plegar(v), v))

    en_estados = ""
    if q["estado"]:
        en_estados = f" AND d.estado IN ({', '.join('?' for _ in q['estado'])})"
    return {"estados": distintos("estado"),
            "municipios": distintos("municipio", en_estados, tuple(q["estado"])),
            "monedas": distintos("moneda"),
            "tipos": distintos("tipo_terreno")}


def history(conn: DatabaseConnection, inventory_id: str, before_version: int | None,
            limit: int, completo: bool = False) -> tuple[list[dict[str, Any]], int, int | None]:
    """Events newest first. Returns (page, total, next cursor).

    ``completo`` is the administrators' audit. Without it an event shows the
    core-field changes, which travel with the terrain, and nothing about work
    bases the reader may not be in: a transfer appears, the bases it went
    between do not.
    """
    total = conn.execute("SELECT COUNT(*) AS n FROM inventory_event WHERE inventory_id = ?",
                         (inventory_id,)).fetchone()["n"]
    rows = conn.execute(
        "SELECT id, version, action, actor_id, actor_name, at, before_revision_id,"
        " after_revision_id, details_json FROM inventory_event"
        " WHERE inventory_id = ? AND version < ? ORDER BY version DESC LIMIT ?",
        (inventory_id, before_version if before_version is not None else 2**62, limit + 1),
    ).fetchall()
    eventos = []
    for r in rows[:limit]:
        detalles = json.loads(r["details_json"] or "{}")
        if not completo:
            detalles = {k: v for k, v in detalles.items() if k in _DETALLES_COMUNES}
        eventos.append({
            "id": r["id"], "version": r["version"], "action": r["action"], "at": r["at"],
            "actor": {"id": r["actor_id"], "display_name": r["actor_name"]},
            "before_revision_id": r["before_revision_id"],
            "after_revision_id": r["after_revision_id"], **detalles})
    return eventos, int(total), (eventos[-1]["version"] if len(rows) > limit else None)


# Event details any reader of the terrain may see. Everything else (the bases
# of a transfer today, custom-value changes later) is for the full audit.
_DETALLES_COMUNES = ("changes", "confirmed")


def _stored_result(conn: DatabaseConnection, operation: str, key: str,
                   actor_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT request_hash, result_json FROM inventory_operation_result"
        " WHERE operation = ? AND idempotency_key = ? AND actor_id = ?",
        (operation, key, actor_id)).fetchone()
    if row is None:
        return None
    return {"request_hash": row["request_hash"], "result": json.loads(row["result_json"])}


# -- writes --------------------------------------------------------------------

def create(conn: DatabaseConnection, fields: Mapping[str, Any], actor: Mapping[str, Any],
           key: str, request_hash: str, base_id: str | None = None) -> dict[str, Any]:
    """crear(), returning the record. For callers that already hold the right
    to see it; a request handler re-authorizes a replay before serializing."""
    inventory_id, _ = crear(conn, fields, actor, key, request_hash, base_id)
    return {"terreno": get(conn, inventory_id)}


def crear(conn: DatabaseConnection, fields: Mapping[str, Any], actor: Mapping[str, Any],
          key: str, request_hash: str, base_id: str | None = None) -> tuple[str, bool]:
    """Create a draft record in a work base (or unassigned), or find the one a
    repeated key already created. Returns (terrain id, whether it is a replay).

    A key belongs to one actor creating in one place: the same key from
    another account, or for another base, is a different key and can never
    return this record. Only the id is stored, never a response: a replay is
    answered from the record as it is now, after the caller is authorized for
    it again. The idempotency row is the transaction's first write, so a
    concurrent request with the same key waits for it, then collides.
    """
    operation = f"create:{base_id or 'global'}:{actor['id']}"
    previous = (_stored_result(conn, operation, key, actor["id"])
                # Keys stored before they were scoped: honoured for their own actor only.
                or (_stored_result(conn, "create", key, actor["id"]) if base_id is None else None))
    if previous is None:
        try:
            with db.transaction(conn):
                return _create(conn, fields, actor, operation, key, request_hash, base_id), False
        except Exception as exc:
            if not _unique_violation(exc):
                raise
        previous = _stored_result(conn, operation, key, actor["id"])
        if previous is None:
            raise RuntimeError("Idempotency collision without a stored result.")
    if previous["request_hash"] != request_hash:
        raise IdempotencyConflictError()
    stored = previous["result"]
    return str(stored["id"] if "id" in stored else stored["terreno"]["id"]), True


def _create(conn: DatabaseConnection, fields: Mapping[str, Any], actor: Mapping[str, Any],
            operation: str, key: str, request_hash: str, base_id: str | None) -> str:
    ahora = db.now()
    inventory_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO inventory_operation_result (operation, idempotency_key, request_hash,"
        " result_json, actor_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (operation, key, request_hash, json.dumps({"id": inventory_id}), actor["id"], ahora))
    conn.execute(
        "INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by, updated_at,"
        " updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
        (inventory_id, base_id, ahora, actor["id"], ahora, actor["id"]))
    draft = {**inventario.empty_draft(), **fields}
    revision_id = _insert_revision(conn, inventory_id, 1, draft, {}, actor, ahora, base_id=base_id)
    conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?",
                 (revision_id, inventory_id))
    cambios = {n: {"before": None, "after": v} for n, v in draft.items()
               if v != inventario.empty_draft()[n]}
    _event(conn, inventory_id, 1, "create", actor, ahora, None, revision_id, {"changes": cambios})
    return inventory_id


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
        revision_id = _siguiente_revision(conn, current, draft, stamps, actor, ahora,
                                          current["base_id"])
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


class EstadoError(Exception):
    """The record is not in the state the action needs. ``code`` says which."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def archivar(conn: DatabaseConnection, inventory_id: str, expected_version: int,
             actor: Mapping[str, Any], restaurar: bool = False) -> dict[str, Any]:
    """Archive a terrain, or restore it. Reversible, and the record itself is
    untouched: same id, same revision, same files and layout. Only archived_at
    and the version change, with one event."""
    current = _vigente(conn, inventory_id, expected_version)
    if bool(current["archived_at"]) != restaurar:
        raise EstadoError("terreno_no_archivado" if restaurar else "terreno_archivado")
    ahora = db.now()
    with db.transaction(conn):
        _claim(conn, inventory_id, expected_version, actor, ahora,
               "archived_at = ?", (None if restaurar else ahora,))
        _event(conn, inventory_id, expected_version + 1, "restore" if restaurar else "archive",
               actor, ahora, current["draft_revision_id"], current["draft_revision_id"], {})
    return _existente(conn, inventory_id)


def transferir(conn: DatabaseConnection, inventory_id: str, expected_version: int,
               destino: str | None, actor: Mapping[str, Any]) -> dict[str, Any]:
    """Move a terrain to another work base, or to none. One transaction: the
    owner, a revision recording the new base, the version and the event.

    Nothing is copied. Files, layout and history stay on the same terrain id.
    Custom values stay stored under their own column ids; they are simply not
    shown while the terrain is outside the base that defines them, and show
    again if it returns. The caller has locked the terrain and checked that
    the destination exists and is active.
    """
    current = _vigente(conn, inventory_id, expected_version)
    if current["base_id"] == destino:
        return current
    ahora = db.now()
    with db.transaction(conn):
        _claim(conn, inventory_id, expected_version, actor, ahora, "base_id = ?", (destino,))
        stamps = {n: {"at": c["at"], "id": c["by"]["id"]}
                  for n, c in current["confirmations"].items() if c}
        revision_id = _siguiente_revision(conn, current, current["draft"], stamps, actor, ahora,
                                          destino)
        conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?",
                     (revision_id, inventory_id))
        _event(conn, inventory_id, expected_version + 1, "transfer", actor, ahora,
               current["draft_revision_id"], revision_id,
               {"base": {"before": current["base_id"], "after": destino}})
    return _existente(conn, inventory_id)


def vista_previa_de_transferencia(conn: DatabaseConnection, inventory_id: str,
                                  destino: str | None) -> dict[str, Any]:
    """What a transfer would change, for the confirmation screen. Reads only.

    ``columnas_que_se_ocultan`` are the source base's custom columns: their
    values stay stored but leave view. ``con_valor`` says whether this terrain
    has one. ``acceso`` is who can open the destination; administrators always
    can and are not listed.
    """
    fila = conn.execute(
        "SELECT t.version, t.base_id, d.custom_json" + _FROM + " WHERE t.id = ?",
        (inventory_id,)).fetchone()
    valores = json.loads(fila["custom_json"] or "{}")
    columnas = [] if fila["base_id"] is None else conn.execute(
        "SELECT id, nombre FROM inventory_column WHERE base_id = ? AND retired_at IS NULL"
        " ORDER BY orden, id", (fila["base_id"],)).fetchall()
    acceso = [] if destino is None else conn.execute(
        "SELECT u.id, u.login, u.display_name, u.active FROM maestra_base_acceso a"
        " JOIN team_user u ON u.id = a.user_id WHERE a.base_id = ?"
        " ORDER BY u.display_name, u.id", (destino,)).fetchall()
    return {
        "terreno": {"id": inventory_id, "version": fila["version"]},
        "origen": fila["base_id"], "destino": destino,
        "sin_cambio": fila["base_id"] == destino,
        "acceso": [{"id": u["id"], "login": u["login"], "display_name": u["display_name"],
                    "active": bool(u["active"])} for u in acceso],
        "columnas_que_se_ocultan": [
            {"id": f"custom:{c['id']}", "nombre": c["nombre"],
             "con_valor": valores.get(f"custom:{c['id']}") is not None} for c in columnas],
    }


def _vigente(conn: DatabaseConnection, inventory_id: str, expected_version: int) -> dict[str, Any]:
    current = get(conn, inventory_id)
    if current is None:
        raise LookupError(inventory_id)
    if current["version"] != expected_version:
        raise ConflictError()
    return current


def _existente(conn: DatabaseConnection, inventory_id: str) -> dict[str, Any]:
    result = get(conn, inventory_id)
    assert result is not None
    return result


def _siguiente_revision(conn: DatabaseConnection, current: Mapping[str, Any],
                        draft: Mapping[str, Any], stamps: Mapping[str, Mapping[str, str]],
                        actor: Mapping[str, Any], ahora: str, base_id: str | None) -> str:
    """The next revision of a record. What no route edits rides along
    unchanged: the raw source extras and every custom value, whichever base
    defined it. ``base_id`` is the base the terrain belongs to as of this
    revision, which is what a revision records."""
    previa = conn.execute("SELECT extra_json, custom_json FROM inventory_revision WHERE id = ?",
                          (current["draft_revision_id"],)).fetchone()
    return _insert_revision(conn, current["id"], current["revision_number"] + 1, draft, stamps,
                            actor, ahora, previa["extra_json"], base_id, previa["custom_json"])


def _claim(conn: DatabaseConnection, inventory_id: str, expected_version: int,
           actor: Mapping[str, Any], ahora: str, cambios: str = "",
           params: tuple[Any, ...] = ()) -> None:
    """The compare-and-set. Zero rows means someone else got there first."""
    cursor = conn.execute(
        "UPDATE inventory_terrain SET version = version + 1, updated_at = ?, updated_by = ?"
        + (", " + cambios if cambios else "") + " WHERE id = ? AND version = ?",
        (ahora, actor["id"], *params, inventory_id, expected_version))
    if cursor.rowcount != 1:
        raise ConflictError()


def _insert_revision(conn: DatabaseConnection, inventory_id: str, number: int,
                     draft: Mapping[str, Any], stamps: Mapping[str, Mapping[str, str]],
                     actor: Mapping[str, Any], ahora: str, extra_json: str | None = None,
                     base_id: str | None = None, custom_json: str = "{}") -> str:
    revision_id = str(uuid.uuid4())
    values = {f: draft[f] for f in REVISION_FIELDS}
    values["price_on_request"] = 1 if draft["price_on_request"] else 0
    columns = ["id", "inventory_id", "revision_number", *REVISION_FIELDS, "extra_json",
               "base_id", "custom_json", "price_confirmed_at", "price_confirmed_by", "availability_confirmed_at",
               "availability_confirmed_by", "created_at", "created_by"]
    params = [revision_id, inventory_id, number, *values.values(), extra_json,
              base_id, custom_json, stamps.get("price", {}).get("at"), stamps.get("price", {}).get("id"),
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


def _dtos(conn: DatabaseConnection, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Records for a page of rows, with one query for the custom columns of
    the bases on that page however many rows there are."""
    bases = sorted({r["base_id"] for r in rows if r["base_id"]})
    visibles: dict[str, set[str]] = {b: set() for b in bases}
    if bases:
        for c in conn.execute(
                "SELECT id, base_id FROM inventory_column WHERE retired_at IS NULL"
                f" AND base_id IN ({', '.join('?' for _ in bases)})", tuple(bases)).fetchall():
            visibles[c["base_id"]].add(f"custom:{c['id']}")
    return [_dto(r, visibles) for r in rows]


def _dto(row: Mapping[str, Any], visibles: Mapping[str, set[str]]) -> dict[str, Any]:
    draft = {f: row[f] for f in REVISION_FIELDS}
    # Custom values of the terrain's CURRENT base only. Values kept from a base
    # it used to belong to, or of a retired column, are stored and not shown.
    propias = visibles.get(row["base_id"] or "", set())
    custom = {k: v for k, v in json.loads(row["custom_json"] or "{}").items() if k in propias}
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
        "base_id": row["base_id"],
        "draft": draft,
        "custom": custom,
        "confirmations": confirmations,
        "source_extra": json.loads(row["extra_json"] or "{}"),
        "attention": inventario.attention(draft, confirmations),
        "revision_number": row["revision_number"],
        "created_at": row["created_at"],
        "created_by": {"id": row["created_by"], "display_name": row["created_by_name"]},
        "updated_at": row["updated_at"],
        "updated_by": {"id": row["updated_by"], "display_name": row["updated_by_name"]},
    }

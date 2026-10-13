"""Work bases and who may open them.

A work base is a container: terrains are assigned to it and operators are
granted access to it. It holds no terrain data itself, so archiving one, or
changing its grants, touches no terrain, revision, column, file or published
content. Every change here is a compare-and-set on the base's version and
leaves one maestra_base_event; grants also leave a team_user_event per person,
which is what keeps a revoked grant on record after its row is deleted.

Callers are administrators inside db.escritura(), already re-authorized with
auth.reverificar_base(..., exclusivo=True), which holds the base row.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Collection, Mapping
from typing import Any

from .. import db
from ..protocols import DatabaseConnection

_SELECT = """
SELECT b.id, b.nombre, b.version, b.archived_at, b.created_at, b.updated_at,
       (SELECT COUNT(*) FROM inventory_terrain t
         WHERE t.base_id = b.id AND t.archived_at IS NULL) AS terrenos
FROM maestra_base b
"""


class ConflictError(Exception):
    """The caller's expected_version is no longer current."""


class EstadoError(Exception):
    """The base is not in the state the action needs. ``code`` says which."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class UsuariosError(Exception):
    """Some requested grantees cannot be granted. Maps each id to the reason."""

    def __init__(self, motivos: dict[str, str]) -> None:
        super().__init__("usuarios")
        self.motivos = motivos


# -- reads ---------------------------------------------------------------------

def listar(conn: DatabaseConnection, user_id: str | None,
           con_archivadas: bool = False) -> list[dict[str, Any]]:
    """The work bases one caller may open, filtered in SQL.

    ``user_id`` None is an administrator: every base. Otherwise only the
    active bases granted to that person; an archived base is closed to
    operators, so ``con_archivadas`` only widens an administrator's list.
    """
    if user_id is None:
        donde = "" if con_archivadas else " WHERE b.archived_at IS NULL"
        params: tuple[Any, ...] = ()
    else:
        donde = (" JOIN maestra_base_acceso a ON a.base_id = b.id AND a.user_id = ?"
                 " WHERE b.archived_at IS NULL")
        params = (user_id,)
    rows = conn.execute(_SELECT + donde + " ORDER BY b.nombre, b.id", params).fetchall()
    return [_dto(r) for r in rows]


def obtener(conn: DatabaseConnection, base_id: str) -> dict[str, Any] | None:
    row = conn.execute(_SELECT + " WHERE b.id = ?", (base_id,)).fetchone()
    return _dto(row) if row else None


def accesos(conn: DatabaseConnection, base_id: str) -> list[dict[str, Any]]:
    """Current grants of one base, with enough to recognise each person."""
    rows = conn.execute(
        "SELECT u.id, u.login, u.display_name, u.active, a.granted_at"
        " FROM maestra_base_acceso a JOIN team_user u ON u.id = a.user_id"
        " WHERE a.base_id = ? ORDER BY u.display_name, u.id", (base_id,)).fetchall()
    return [{"id": r["id"], "login": r["login"], "display_name": r["display_name"],
             "active": bool(r["active"]), "granted_at": r["granted_at"]} for r in rows]


def operadores(conn: DatabaseConnection, buscado: str, limite: int,
               ) -> tuple[list[dict[str, Any]], int]:
    """Operator accounts a grant may name: (one bounded page, how many match).

    Identity and status only. Nothing about passwords, sessions or what each
    one can open.
    """
    donde, params = "rol = 'operador'", []
    plegado = db.plegar(" ".join(buscado.split()))
    if plegado:
        for especial in "!%_":
            plegado = plegado.replace(especial, "!" + especial)
        junto = db.sql_plegar(conn, "login || ' ' || display_name")
        donde += f" AND {junto} LIKE ? ESCAPE '!'"
        params.append(f"%{plegado}%")
    total = conn.execute(f"SELECT COUNT(*) AS n FROM team_user WHERE {donde}",
                         tuple(params)).fetchone()["n"]
    rows = conn.execute(
        f"SELECT id, login, display_name, active FROM team_user WHERE {donde}"
        " ORDER BY display_name, id LIMIT ?", (*params, limite)).fetchall()
    return ([{"id": r["id"], "login": r["login"], "display_name": r["display_name"],
              "active": bool(r["active"])} for r in rows], int(total))


# -- writes --------------------------------------------------------------------

def crear(conn: DatabaseConnection, nombre: str, actor: Mapping[str, Any]) -> dict[str, Any]:
    """A new, empty work base: no terrains, no grants, version 1."""
    base_id, ahora = str(uuid.uuid4()), db.now()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO maestra_base (id, nombre, version, created_at, created_by, updated_at,"
            " updated_by) VALUES (?, ?, 1, ?, ?, ?, ?)",
            (base_id, nombre, ahora, actor["id"], ahora, actor["id"]))
        _evento(conn, base_id, 1, "crear", actor, ahora, {"nombre": nombre})
    return _existente(conn, base_id)


def renombrar(conn: DatabaseConnection, base_id: str, expected_version: int, nombre: str,
              actor: Mapping[str, Any]) -> dict[str, Any]:
    actual = _actual(conn, base_id, expected_version)
    if actual["archived_at"]:
        raise EstadoError("base_archivada")
    if actual["nombre"] == nombre:
        return actual
    ahora = db.now()
    with db.transaction(conn):
        _reclamar(conn, base_id, expected_version, actor, ahora, "nombre = ?", (nombre,))
        _evento(conn, base_id, expected_version + 1, "renombrar", actor, ahora,
                {"antes": actual["nombre"], "despues": nombre})
    return _existente(conn, base_id)


def archivar(conn: DatabaseConnection, base_id: str, expected_version: int,
             actor: Mapping[str, Any]) -> dict[str, Any]:
    """Close the base to operators and to ordinary writes. Reversible, and
    nothing that belongs to it is changed: only the base row."""
    if _actual(conn, base_id, expected_version)["archived_at"]:
        raise EstadoError("base_archivada")
    ahora = db.now()
    with db.transaction(conn):
        _reclamar(conn, base_id, expected_version, actor, ahora,
                  "archived_at = ?, archived_by = ?", (ahora, actor["id"]))
        _evento(conn, base_id, expected_version + 1, "archivar", actor, ahora)
    return _existente(conn, base_id)


def restaurar(conn: DatabaseConnection, base_id: str, expected_version: int,
              actor: Mapping[str, Any]) -> dict[str, Any]:
    if not _actual(conn, base_id, expected_version)["archived_at"]:
        raise EstadoError("base_no_archivada")
    ahora = db.now()
    with db.transaction(conn):
        _reclamar(conn, base_id, expected_version, actor, ahora,
                  "archived_at = NULL, archived_by = NULL", ())
        _evento(conn, base_id, expected_version + 1, "restaurar", actor, ahora)
    return _existente(conn, base_id)


def reemplazar_accesos(conn: DatabaseConnection, base_id: str, expected_version: int,
                       user_ids: Collection[str], actor: Mapping[str, Any]) -> dict[str, Any]:
    """Make the base's grants exactly ``user_ids``. All of it or none of it.

    The whole request is checked before anything changes. Each id must be an
    existing operator; one that is being ADDED must also be active. An
    inactive account that already has a grant may stay in the set or leave it.
    An unchanged set changes nothing and leaves no event.
    """
    _actual(conn, base_id, expected_version)
    pedidos = set(user_ids)
    actuales = {r["user_id"] for r in conn.execute(
        "SELECT user_id FROM maestra_base_acceso WHERE base_id = ?", (base_id,)).fetchall()}
    motivos: dict[str, str] = {}
    for user_id in sorted(pedidos):
        usuario = conn.execute("SELECT rol, active FROM team_user WHERE id = ?",
                               (user_id,)).fetchone()
        if usuario is None:
            motivos[user_id] = "no_existe"
        elif usuario["rol"] != "operador":
            motivos[user_id] = "no_es_operador"
        elif not usuario["active"] and user_id not in actuales:
            motivos[user_id] = "inactivo"
    if motivos:
        raise UsuariosError(motivos)

    # Sorted, so two administrators always take grant rows in the same order.
    otorgados, revocados = sorted(pedidos - actuales), sorted(actuales - pedidos)
    if not otorgados and not revocados:
        return _existente(conn, base_id)
    ahora = db.now()
    with db.transaction(conn):
        _reclamar(conn, base_id, expected_version, actor, ahora, "", ())
        for user_id in revocados:
            conn.execute("DELETE FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?",
                         (base_id, user_id))
        for user_id in otorgados:
            conn.execute(
                "INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                " VALUES (?, ?, ?, ?)", (base_id, user_id, ahora, actor["id"]))
        for accion, afectados in (("acceso_revocado", revocados), ("acceso_otorgado", otorgados)):
            for user_id in afectados:
                conn.execute(
                    "INSERT INTO team_user_event (id, user_id, action, base_id, actor_id,"
                    " actor_name, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), user_id, accion, base_id, actor["id"],
                     actor["display_name"], ahora))
        _evento(conn, base_id, expected_version + 1, "acceso", actor, ahora,
                {"otorgados": otorgados, "revocados": revocados})
    return _existente(conn, base_id)


# -- helpers -------------------------------------------------------------------

def _actual(conn: DatabaseConnection, base_id: str, expected_version: int) -> dict[str, Any]:
    actual = obtener(conn, base_id)
    if actual is None:
        raise LookupError(base_id)
    if actual["version"] != expected_version:
        raise ConflictError()
    return actual


def _existente(conn: DatabaseConnection, base_id: str) -> dict[str, Any]:
    base = obtener(conn, base_id)
    assert base is not None
    return base


def _reclamar(conn: DatabaseConnection, base_id: str, expected_version: int,
              actor: Mapping[str, Any], ahora: str, cambios: str, params: tuple[Any, ...]) -> None:
    """The compare-and-set. Zero rows means someone else got there first."""
    cursor = conn.execute(
        "UPDATE maestra_base SET version = version + 1, updated_at = ?, updated_by = ?"
        + (", " + cambios if cambios else "") + " WHERE id = ? AND version = ?",
        (ahora, actor["id"], *params, base_id, expected_version))
    if cursor.rowcount != 1:
        raise ConflictError()


def _evento(conn: DatabaseConnection, base_id: str, version: int, action: str,
            actor: Mapping[str, Any], ahora: str, details: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO maestra_base_event (id, base_id, version, action, actor_id, actor_name, at,"
        " details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), base_id, version, action, actor["id"], actor["display_name"], ahora,
         json.dumps(details, ensure_ascii=False) if details else None))


def _dto(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "nombre": row["nombre"], "version": row["version"],
            "archivada": row["archived_at"] is not None, "archived_at": row["archived_at"],
            "terrenos": row["terrenos"], "created_at": row["created_at"],
            "updated_at": row["updated_at"]}

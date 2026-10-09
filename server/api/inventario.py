"""Endpoints for the shared terrain inventory (internal) and the public catalog.

Every internal route needs a signed-in team user; the actor always comes from
the session (request.user), never from the request body. The unscoped list
and create are the administrators' master table (maestra.global). The routes
that name one terrain check its work base: an operator reaches a record only
if it is assigned to an active base granted to that person, and writes check
that again inside the transaction that saves.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from typing import Any

from .. import auth, columnas, db, inventario
from ..protocols import DatabaseConnection
from ..repo import columnas as repo_columnas
from ..repo import inventario as repo
from ..router import Request
from ..web_util import ApiError, parse_json

Respuesta = dict[str, Any]

_KEY = re.compile(r"^[\x21-\x7e]{8,200}$")
NO_EXISTE = "El terreno no existe."


def _actor(request: Request) -> dict[str, Any]:
    if request.user is None:  # the dispatcher already enforces this
        raise ApiError("Inicia sesión para continuar.", 401, {"code": "unauthenticated"})
    return request.user


def _invalid(fields: Mapping[str, str], mensaje: str = "Revisa los campos marcados.") -> ApiError:
    return ApiError(mensaje, 422, {"code": "validation_failed", "fields": dict(fields)})


def _not_found() -> ApiError:
    return ApiError(NO_EXISTE, 404, {"code": "not_found"})


def listing(request: Request) -> Respuesta:
    """The administrators' master table: every base and the unassigned records."""
    return _listar(request, inventario.INTERNAL_QUERY, None)


def base_listing(request: Request) -> Respuesta:
    """The terrains of one work base, for whoever may open it."""
    base_id = request.uuid_param("bid")
    return _listar(request, inventario.SCOPED_QUERY, base_id)


def _listar(request: Request, permitidos: tuple[str, ...], base_id: str | None) -> Respuesta:
    _actor(request)
    with db.session() as conn:
        if base_id is not None:
            # Before the query is even parsed: out of scope is 404 whatever was asked.
            auth.require_base(request, base_id, "maestra.ver", conn)
        try:
            q = inventario.parse_query(request.query, permitidos)
            terrenos, total, cursor, facets = repo.listar(conn, q, base_id)
        except inventario.QueryError as exc:
            raise _invalid(exc.errors, "Filtros inválidos.") from None
        except repo.CursorError:
            raise _invalid({"cursor": "Cursor inválido para este orden."},
                           "Filtros inválidos.") from None
    return {"terrenos": terrenos, "total": total, "next_cursor": cursor, "facets": facets}


def detail(request: Request) -> Respuesta:
    inventory_id = request.uuid_param("id")
    with db.session() as conn:
        auth.require_terreno(request, inventory_id, "maestra.ver", conn)
        terreno = repo.get(conn, inventory_id)
    if terreno is None:
        raise _not_found()
    return {"terreno": terreno}


def create(request: Request) -> Respuesta:
    """A new unassigned draft, administrators only."""
    return _crear(request, None)


def base_create(request: Request) -> Respuesta:
    """A new draft in one work base. Every business field is optional: an
    empty body creates a blank record."""
    return _crear(request, request.uuid_param("bid"))


def _crear(request: Request, base_id: str | None) -> Respuesta:
    """Requires an Idempotency-Key: a retry with the same key and body returns
    the record it created instead of creating another. The body is the flat
    field map; who creates and where come from the session and the path."""
    actor = _actor(request)
    with db.escritura() as conn:
        # Authorized where it is saved, before any answer about the body.
        if base_id is None:
            auth.reverificar(conn, request.sesion, "maestra.global")
        else:
            auth.reverificar_base(conn, request.sesion, base_id, "maestra.editar")
        key = (request.headers.get("Idempotency-Key") or "").strip()
        if not _KEY.match(key):
            raise ApiError("Falta el encabezado Idempotency-Key (8 a 200 caracteres).", 422,
                           {"code": "idempotency_key_required"})
        fields, errors = inventario.clean_changes(parse_json(request.body))
        if errors:
            raise _invalid(errors)
        request_hash = _hash({"base": base_id, "campos": fields})
        try:
            # A key stored before keys were scoped carries the hash of the fields alone.
            inventory_id, repetida = repo.crear(conn, fields, actor, key, request_hash, base_id,
                                                hash_heredado=_hash(fields))
        except repo.IdempotencyConflictError:
            raise ApiError("Esa Idempotency-Key ya se usó con otros datos.", 409,
                           {"code": "idempotency_conflict"}) from None
        if repetida:
            # The record may have been moved or archived since: answer from
            # what it is now, and only if this caller may still see it.
            auth.reverificar_terreno(conn, request.sesion, inventory_id, "maestra.ver")
        return {"terreno": repo.get(conn, inventory_id)}


def _hash(cuerpo: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(cuerpo, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def update(request: Request) -> Respuesta:
    """Save a new draft revision: {expected_version, changes?, custom?, confirm?}.

    `custom` is {"custom:<column id>": value} for live columns of the terrain's
    current base; null clears a value and a key left out keeps what is stored.
    Core and custom changes in one request are one version, one revision and
    one event, or none of them. `confirm` (optional, e.g. ["price"]) stamps the
    price/availability confirmation with this user and time.
    """
    actor = _actor(request)
    inventory_id = request.uuid_param("id")
    data = parse_json(request.body)
    errors = {k: "Campo no admitido." for k in data
              if k not in ("expected_version", "changes", "custom", "confirm")}
    expected: Any = data.get("expected_version")
    if type(expected) is not int or expected < 1:
        errors["expected_version"] = "Envía la versión que estabas editando (entero)."
    confirm = data.get("confirm", [])
    if not isinstance(confirm, list) or any(c not in inventario.CONFIRMABLE for c in confirm):
        errors["confirm"] = "Usa una lista con «price» y/o «availability»."
        confirm = []
    fields, field_errors = inventario.clean_changes(data.get("changes", {}))
    errors.update(field_errors)

    with db.escritura() as conn:
        # Authorization is decided here, in the transaction that saves, and
        # before any validation answer: out of scope is 404 whatever was sent.
        alcance = auth.reverificar_terreno(conn, request.sesion, inventory_id, "maestra.editar",
                                           exclusivo=True)
        # The base is held by that check, so its live columns cannot change
        # under this save: a column retired first is refused here.
        custom, custom_errors = columnas.limpiar_valores(
            data.get("custom", {}), repo_columnas.vivas(conn, alcance.base_id))
        errors.update(custom_errors)
        if errors:
            raise _invalid(errors)
        try:
            return {"terreno": repo.update(conn, inventory_id, expected, fields,
                                           tuple(dict.fromkeys(confirm)), actor, custom)}
        except repo.ConflictError:
            raise _conflicto(conn, inventory_id) from None


def _conflicto(conn: DatabaseConnection, inventory_id: str) -> ApiError:
    """The 409 for a stale expected_version, with the record as it is now.
    Only ever built after the caller was authorized for that record."""
    latest = repo.get(conn, inventory_id)
    return ApiError(
        "Otra persona guardó cambios en este terreno. Revisa su versión antes de guardar"
        " la tuya; tus datos no se han perdido.", 409,
        {"code": "conflict", "current_version": latest["version"] if latest else None,
         "terreno": latest})


def _version_esperada(request: Request, *permitidos: str) -> tuple[dict[str, Any], int]:
    data = parse_json(request.body)
    errors = {k: "Campo no admitido." for k in data if k not in ("expected_version", *permitidos)}
    expected: Any = data.get("expected_version")
    if type(expected) is not int or expected < 1:
        errors["expected_version"] = "Envía la versión que estabas viendo (entero)."
    if errors:
        raise _invalid(errors)
    return data, expected


def archive(request: Request) -> Respuesta:
    """{expected_version}: take the terrain out of active work. Reversible."""
    return _archivar(request, restaurar=False)


def restore(request: Request) -> Respuesta:
    """{expected_version}: bring an archived terrain back, same id and content."""
    return _archivar(request, restaurar=True)


def _archivar(request: Request, restaurar: bool) -> Respuesta:
    inventory_id = request.uuid_param("id")
    with db.escritura() as conn:
        alcance = auth.reverificar_terreno(conn, request.sesion, inventory_id, "maestra.archivar",
                                           exclusivo=True)
        _, expected = _version_esperada(request)
        publicado = conn.execute(
            "SELECT published_revision_id FROM inventory_terrain WHERE id = ?",
            (inventory_id,)).fetchone()["published_revision_id"]
        if publicado and alcance.rol != "admin":
            # Archiving or restoring a published terrain changes what the public
            # sees. An operator never does that, even indirectly.
            raise ApiError("Este terreno está publicado; pide a un administrador que lo haga.",
                           403, {"code": "requiere_admin"})
        try:
            return {"terreno": repo.archivar(conn, inventory_id, expected, alcance.actor, restaurar)}
        except repo.ConflictError:
            raise _conflicto(conn, inventory_id) from None
        except repo.EstadoError as exc:
            raise ApiError("El terreno ya está archivado." if exc.code == "terreno_archivado"
                           else "El terreno no está archivado.", 409, {"code": exc.code}) from None


def _destino(valor: Any) -> str | None:
    """A destination base id, or None for "no base" (null in a body,
    "sin_asignar" in a query string). Anything else is a 422."""
    if valor is None or valor == inventario.SIN_ASIGNAR:
        return None
    try:
        return str(uuid.UUID(valor))
    except (ValueError, TypeError, AttributeError):
        raise _invalid({"base_id": "Envía el identificador de la base de destino, o ninguno"
                                   " para dejar el terreno sin base."}) from None


def _destino_activo(conn: DatabaseConnection, destino: str | None) -> None:
    if destino is None:
        return
    # Locked like the source, so archiving the destination waits for this transfer.
    base = conn.execute("SELECT archived_at FROM maestra_base WHERE id = ?" + db.bloqueo(conn),
                        (destino,)).fetchone()
    if base is None:
        raise _invalid({"base_id": "La base de destino no existe."})
    if base["archived_at"]:
        raise ApiError("La base de destino está archivada.", 409, {"code": "base_archivada"})


def transfer_preview(request: Request) -> Respuesta:
    """GET …/transferir?base_id=ID (or base_id=sin_asignar for "no base"): what
    the move would change. Reads only; the transfer checks everything again."""
    inventory_id = request.uuid_param("id")
    if "base_id" not in request.query or set(request.query) - {"base_id"}:
        raise _invalid({"base_id": "Indica la base de destino con base_id (o sin_asignar)."})
    destino = _destino(request.q("base_id"))
    with db.session() as conn:
        auth.require_terreno(request, inventory_id, "bases.gestionar", conn)
        if destino is not None and conn.execute(
                "SELECT 1 AS ok FROM maestra_base WHERE id = ?", (destino,)).fetchone() is None:
            raise _invalid({"base_id": "La base de destino no existe."})
        return repo.vista_previa_de_transferencia(conn, inventory_id, destino)


def transfer(request: Request) -> Respuesta:
    """{expected_version, base_id}: move the terrain to another work base, or
    to none with base_id null. Administrators only."""
    inventory_id = request.uuid_param("id")
    with db.escritura() as conn:
        alcance = auth.reverificar_terreno(conn, request.sesion, inventory_id, "bases.gestionar",
                                           exclusivo=True)
        data, expected = _version_esperada(request, "base_id")
        if "base_id" not in data:
            raise _invalid({"base_id": "Indica la base de destino (null para ninguna)."})
        destino = _destino(data["base_id"])
        # A transfer is not a way around an archive: restore first.
        if alcance.base_archivada:
            raise ApiError("La base de origen está archivada; restáurala antes de mover el terreno.",
                           409, {"code": "base_archivada"})
        if alcance.terreno_archivado:
            raise ApiError("El terreno está archivado; restáuralo antes de moverlo.", 409,
                           {"code": "terreno_archivado"})
        if destino != alcance.base_id:
            _destino_activo(conn, destino)
        try:
            return {"terreno": repo.transferir(conn, inventory_id, expected, destino, alcance.actor)}
        except repo.ConflictError:
            raise _conflicto(conn, inventory_id) from None


def history(request: Request) -> Respuesta:
    _actor(request)
    inventory_id = request.uuid_param("id")
    errors = {k: "Parámetro no admitido." for k in request.query if k not in ("cursor", "limit")}
    try:
        limit = int(request.q("limit") or inventario.DEFAULT_LIMIT)
        if not 1 <= limit <= inventario.MAX_LIMIT:
            raise ValueError
    except ValueError:
        errors["limit"] = f"Usa un número entero de 1 a {inventario.MAX_LIMIT}."
        limit = inventario.DEFAULT_LIMIT
    cursor = request.q("cursor")
    # A version number: ASCII digits, and few enough for either database's integer.
    if cursor is not None and not re.fullmatch(r"[0-9]{1,18}", cursor):
        errors["cursor"] = "Cursor inválido."
    if errors:
        raise _invalid(errors, "Parámetros inválidos.")
    with db.session() as conn:
        alcance = auth.require_terreno(request, inventory_id, "maestra.ver", conn)
        eventos, total, siguiente = repo.history(
            conn, inventory_id, int(cursor) if cursor else None, limit,
            completo=alcance.rol == "admin")
    return {"eventos": eventos, "total": total,
            "next_cursor": str(siguiente) if siguiente is not None else None}


# -- public catalog: Stage 2 placeholders ------------------------------------------
# Publishing does not exist yet, so nothing is eligible: the catalog is empty
# and every detail is the same 404 a missing or unpublished id will get.

def public_listing(request: Request) -> Respuesta:
    return {"terrenos": [], "total": 0, "next_cursor": None,
            "facets": {"estados": [], "municipios": [], "monedas": []}}


def public_detail(request: Request) -> Respuesta:
    raise ApiError("Terreno no encontrado.", 404, {"code": "not_found"})

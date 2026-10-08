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
from collections.abc import Mapping
from typing import Any

from .. import auth, db, inventario
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
    _actor(request)
    try:
        q = inventario.parse_query(request.query, inventario.INTERNAL_QUERY)
    except inventario.QueryError as exc:
        raise _invalid(exc.errors, "Filtros inválidos.") from None
    with db.session() as conn:
        records = repo.all_records(conn)

    # Archived records only when asked for, either way.
    archived = q["include_archived"] or "archived" in q["publication_state"]
    candidates = [r for r in records if archived or not r["archived_at"]]
    matching = [
        r for r in candidates
        if inventario.matches(r["draft"], q)
        and (not q["publication_state"] or r["publication_state"] in q["publication_state"])
        and (not q["availability"] or r["draft"]["availability"] in q["availability"])
        and (q["attention"] is None or bool(r["attention"]) == q["attention"])
    ]
    terrenos, cursor = inventario.page(matching, q)
    return {"terrenos": terrenos, "total": len(matching), "next_cursor": cursor,
            "facets": inventario.facets(candidates, lambda r: r["draft"], q)}


def detail(request: Request) -> Respuesta:
    inventory_id = request.uuid_param("id")
    with db.session() as conn:
        auth.require_terreno(request, inventory_id, "maestra.ver", conn)
        terreno = repo.get(conn, inventory_id)
    if terreno is None:
        raise _not_found()
    return {"terreno": terreno}


def create(request: Request) -> Respuesta:
    """A new draft. Requires an Idempotency-Key: a retry with the same key and
    body returns the original record instead of creating another."""
    actor = _actor(request)
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not _KEY.match(key):
        raise ApiError("Falta el encabezado Idempotency-Key (8 a 200 caracteres).", 422,
                       {"code": "idempotency_key_required"})
    fields, errors = inventario.clean_changes(parse_json(request.body))
    errors.update(inventario.check_merged(fields, {**inventario.empty_draft(), **fields}))
    if errors:
        raise _invalid(errors)
    request_hash = hashlib.sha256(
        json.dumps(fields, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    try:
        with db.escritura() as conn:
            auth.reverificar(conn, request.sesion, "maestra.global")
            return repo.create(conn, fields, actor, key, request_hash)
    except repo.IdempotencyConflictError:
        raise ApiError("Esa Idempotency-Key ya se usó con otros datos.", 409,
                       {"code": "idempotency_conflict"}) from None


def update(request: Request) -> Respuesta:
    """Save a new draft revision: {expected_version, changes, confirm?}.

    `confirm` (optional, e.g. ["price"]) stamps the price/availability
    confirmation with this user and time. Ordinary edits never do.
    """
    actor = _actor(request)
    inventory_id = request.uuid_param("id")
    data = parse_json(request.body)
    errors = {k: "Campo no admitido." for k in data
              if k not in ("expected_version", "changes", "confirm")}
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
        auth.reverificar_terreno(conn, request.sesion, inventory_id, "maestra.editar",
                                 exclusivo=True)
        current = repo.get(conn, inventory_id)
        if current is None:
            raise _not_found()
        errors.update(inventario.check_merged(fields, {**current["draft"], **fields}))
        if errors:
            raise _invalid(errors)
        try:
            return {"terreno": repo.update(conn, inventory_id, expected, fields,
                                           tuple(dict.fromkeys(confirm)), actor)}
        except repo.ConflictError:
            latest = repo.get(conn, inventory_id)
            raise ApiError(
                "Otra persona guardó cambios en este terreno. Revisa su versión antes de guardar"
                " la tuya; tus datos no se han perdido.", 409,
                {"code": "conflict", "current_version": latest["version"] if latest else None,
                 "terreno": latest}) from None


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
    if cursor is not None and not cursor.isdigit():
        errors["cursor"] = "Cursor inválido."
    if errors:
        raise _invalid(errors, "Parámetros inválidos.")
    with db.session() as conn:
        auth.require_terreno(request, inventory_id, "maestra.ver", conn)
        eventos, total, siguiente = repo.history(
            conn, inventory_id, int(cursor) if cursor else None, limit)
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

"""Endpoints for the shared terrain inventory (internal) and the public catalog.

Every internal route needs a signed-in team user; the actor always comes from
the session (request.user), never from the request body.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .. import db, inventario
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
        and all(q[f] is None or bool(r[f]) == q[f]
                for f in ("attention", "public_visible", "has_pending_changes"))
    ]
    terrenos, cursor = inventario.page(matching, q)
    return {"terrenos": terrenos, "total": len(matching), "next_cursor": cursor,
            "facets": inventario.facets(candidates, lambda r: r["draft"], q)}


def detail(request: Request) -> Respuesta:
    _actor(request)
    with db.session() as conn:
        terreno = repo.get(conn, request.uuid_param("id"))
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
        with db.session() as conn:
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

    with db.session() as conn:
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
        if repo.get(conn, inventory_id) is None:
            raise _not_found()
        eventos, total, siguiente = repo.history(
            conn, inventory_id, int(cursor) if cursor else None, limit)
    return {"eventos": eventos, "total": total,
            "next_cursor": str(siguiente) if siguiente is not None else None}


# -- publication lifecycle ------------------------------------------------------

def _expected_version(data: Mapping[str, Any], allowed: tuple[str, ...]) -> tuple[int, dict[str, str]]:
    errors = {str(k): "Campo no admitido." for k in data if k not in allowed}
    expected: Any = data.get("expected_version")
    if type(expected) is not int or expected < 1:
        errors["expected_version"] = "Envía la versión que revisaste (entero)."
        expected = 0
    return expected, errors


def _conflict(conn: Any, inventory_id: str) -> ApiError:
    latest = repo.get(conn, inventory_id)
    return ApiError(
        "Otra persona cambió este terreno. Revisa la versión actual antes de continuar.", 409,
        {"code": "conflict", "current_version": latest["version"] if latest else None,
         "terreno": latest})


def _lifecycle(request: Request, action: str) -> Respuesta:
    actor = _actor(request)
    inventory_id = request.uuid_param("id")
    data = parse_json(request.body)
    allowed = ("expected_version", "revision_id") if action == "publish" else ("expected_version",)
    expected, errors = _expected_version(data, allowed)
    revision_id = data.get("revision_id")
    if action == "publish" and (not isinstance(revision_id, str) or not revision_id):
        errors["revision_id"] = "Envía la revisión que revisaste en la vista previa."
    if errors:
        raise _invalid(errors)
    with db.session() as conn:
        try:
            if action == "publish":
                terreno = repo.publish(conn, inventory_id, expected, str(revision_id), actor)
            else:
                terreno = getattr(repo, action)(conn, inventory_id, expected, actor)
        except LookupError:
            raise _not_found() from None
        except repo.ConflictError:
            raise _conflict(conn, inventory_id) from None
        except repo.RevisionChangedError:
            latest = repo.get(conn, inventory_id)
            raise ApiError(
                "El borrador cambió después de tu vista previa. Revísalo de nuevo antes de"
                " publicar.", 409,
                {"code": "revision_changed", "current_version": latest["version"] if latest else None,
                 "terreno": latest}) from None
        except repo.InvalidStateError as exc:
            raise ApiError(exc.mensaje, 409, {"code": "invalid_state"}) from None
        except repo.PublicationBlockedError as exc:
            raise ApiError("Este borrador todavía no se puede publicar.", 422,
                           {"code": "publication_blocked", "blockers": exc.blockers}) from None
    return {"terreno": terreno}


def publish(request: Request) -> Respuesta:
    """{expected_version, revision_id}: publish exactly the reviewed saved draft."""
    return _lifecycle(request, "publish")


def unpublish(request: Request) -> Respuesta:
    return _lifecycle(request, "unpublish")


def archive(request: Request) -> Respuesta:
    return _lifecycle(request, "archive")


def restore(request: Request) -> Respuesta:
    return _lifecycle(request, "restore")


def preview(request: Request) -> Respuesta:
    """The saved draft exactly as the public would see it once published.

    Uses the same serializer as the catalog; published_at is null because the
    commit time is unknown. Only the current saved draft can be previewed for
    publication: a stale revision_id is a 409, so the team reviews again.
    """
    _actor(request)
    inventory_id = request.uuid_param("id")
    errors = {k: "Parámetro no admitido." for k in request.query if k != "revision_id"}
    if errors:
        raise _invalid(errors, "Parámetros inválidos.")
    requested = request.q("revision_id")
    with db.session() as conn:
        current = repo.get(conn, inventory_id)
        if current is None:
            raise _not_found()
        if requested is not None and requested != current["draft_revision_id"]:
            if repo.revision(conn, inventory_id, requested) is None:
                raise _not_found()
            raise ApiError(
                "Esa revisión ya no es el borrador guardado. Revisa la versión actual.", 409,
                {"code": "revision_changed", "current_version": current["version"],
                 "terreno": current})
        published = (repo.revision(conn, inventory_id, current["published_revision_id"])
                     if current["published_revision_id"] else None)
    draft = current["draft"]
    return {
        "id": current["id"],
        "version": current["version"],
        "revision_id": current["draft_revision_id"],
        "preview": True,
        "terreno": inventario.public_terrain(current["id"], current["draft_revision_id"], draft, None),
        "blockers": inventario.publication_blockers(draft),
        "warnings": inventario.preview_warnings(draft, current["confirmations"], published),
    }


# -- the public catalog (anonymous) ------------------------------------------------
# Only the revision selected by the published pointer, only eligible records and
# only PublicTerrain fields. A missing, draft, unpublished, archived, sold or
# withdrawn id all get the same 404.

def _public_not_found() -> ApiError:
    return ApiError("Terreno no encontrado.", 404, {"code": "not_found"})


def public_listing(request: Request) -> Respuesta:
    try:
        q = inventario.parse_query(request.query, inventario.PUBLIC_QUERY)
    except inventario.QueryError as exc:
        raise _invalid(exc.errors, "Filtros inválidos.") from None
    with db.session() as conn:
        candidates = repo.public_records(conn)
    matching = [t for t in candidates if inventario.matches(t, q)]
    terrenos, cursor = inventario.page(matching, q)
    return {"terrenos": terrenos, "total": len(matching), "next_cursor": cursor,
            "facets": inventario.facets(candidates, lambda t: t, q)}


def public_detail(request: Request) -> Respuesta:
    if request.query:
        raise _invalid({k: "Parámetro no admitido." for k in request.query}, "Parámetros inválidos.")
    try:
        inventory_id = request.uuid_param("id")
    except ApiError:
        raise _public_not_found() from None
    with db.session() as conn:
        terreno = repo.public_get(conn, inventory_id)
    if terreno is None:
        raise _public_not_found()
    return {"terreno": terreno}

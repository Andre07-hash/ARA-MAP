"""Endpoints for a work base's custom-column definitions.

Reading them needs the base in scope (maestra.ver); changing them needs
columnas.gestionar, and every change re-checks the session, the role, the
base and the grant inside the transaction that writes, holding the base row
exclusively. Out of scope is the base's 404 whatever else was sent.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from .. import auth, columnas, db
from ..protocols import DatabaseConnection
from ..repo import columnas as repo
from ..router import Request
from ..web_util import ApiError, parse_json

Respuesta = dict[str, Any]

_KEY = re.compile(r"^[\x21-\x7e]{8,200}$")
_MENSAJES = {
    "columna_retirada": "La columna está retirada; restáurala para cambiarla.",
    "columna_no_retirada": "La columna no está retirada.",
    "nombre_duplicado": "Ya hay una columna con ese nombre en esta base.",
    "limite_columnas": f"Una base admite hasta {columnas.MAX_COLUMNAS} columnas personalizadas.",
    "sin_opciones": "Sólo las columnas de opción tienen opciones.",
    "opciones_solo_se_agregan": "Las opciones existentes no se quitan ni se renombran; agrega"
                                " las nuevas al final.",
}


def _invalid(fields: dict[str, str]) -> ApiError:
    return ApiError("Revisa los campos marcados.", 422,
                    {"code": "validation_failed", "fields": fields})


def _columna(request: Request, conn: DatabaseConnection, base_id: str) -> str:
    """The column named in the path, once the base is known to be in scope."""
    try:
        column_id = str(uuid.UUID(request.params["cid"]))
    except (KeyError, ValueError):
        column_id = ""
    if not column_id or repo.obtener(conn, base_id, column_id) is None:
        raise ApiError("La columna no existe.", 404, {"code": "not_found"})
    return column_id


def _version(data: dict[str, Any], errors: dict[str, str]) -> int:
    expected: Any = data.get("expected_version")
    if type(expected) is not int or expected < 1:
        errors["expected_version"] = "Envía la versión que estabas viendo (entero)."
        return 0
    return expected


def _campo(data: dict[str, Any], nombre: str, limpiar: Any, errors: dict[str, str]) -> Any:
    try:
        return limpiar(data[nombre])
    except ValueError as exc:
        errors[nombre] = str(exc)
        return None


def _estado(exc: repo.EstadoError) -> ApiError:
    return ApiError(_MENSAJES[exc.code], 409, {"code": exc.code})


def listing(request: Request) -> Respuesta:
    """?retiradas=1 adds the retired definitions."""
    base_id = request.uuid_param("bid")
    with db.session() as conn:
        auth.require_base(request, base_id, "maestra.ver", conn)
        return {"columnas": repo.listar(conn, base_id, request.q("retiradas") == "1")}


def create(request: Request) -> Respuesta:
    """{nombre, tipo, opciones?} with an Idempotency-Key: a retry with the same
    key and body returns the definition it created instead of another."""
    base_id = request.uuid_param("bid")
    with db.escritura() as conn:
        alcance = auth.reverificar_base(conn, request.sesion, base_id, "columnas.gestionar",
                                        exclusivo=True)
        key = (request.headers.get("Idempotency-Key") or "").strip()
        if not _KEY.match(key):
            raise ApiError("Falta el encabezado Idempotency-Key (8 a 200 caracteres).", 422,
                           {"code": "idempotency_key_required"})
        data = parse_json(request.body)
        errors = {k: "Campo no admitido." for k in data if k not in ("nombre", "tipo", "opciones")}
        nombre = _campo({"nombre": data.get("nombre")}, "nombre", columnas.limpiar_nombre, errors)
        tipo = data.get("tipo")
        opciones: list[str] = []
        if tipo not in columnas.TIPOS:
            errors["tipo"] = "Usa texto, numero, opcion o fecha."
        elif tipo == "opcion":
            opciones = _campo({"opciones": data.get("opciones")}, "opciones",
                              columnas.limpiar_opciones, errors) or []
        elif "opciones" in data:
            errors["opciones"] = _MENSAJES["sin_opciones"]
        if errors:
            raise _invalid(errors)
        assert isinstance(nombre, str) and isinstance(tipo, str)
        cuerpo = {"nombre": nombre, "tipo": tipo, "opciones": opciones}
        request_hash = hashlib.sha256(
            json.dumps(cuerpo, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        try:
            return {"columna": repo.crear(conn, base_id, nombre, tipo, opciones, alcance.actor,
                                          key, request_hash)}
        except repo.IdempotencyConflictError:
            raise ApiError("Esa Idempotency-Key ya se usó con otros datos.", 409,
                           {"code": "idempotency_conflict"}) from None
        except repo.EstadoError as exc:
            raise _estado(exc) from None


def update(request: Request) -> Respuesta:
    """{expected_version, nombre?, opciones?, posicion?}. The type and the id
    never change; ``opciones`` may only add choices after the existing ones."""
    def cambio(conn: DatabaseConnection, base_id: str, column_id: str,
               actor: dict[str, Any]) -> dict[str, Any]:
        data = parse_json(request.body)
        errors = {k: "Campo no admitido." for k in data
                  if k not in ("expected_version", "nombre", "opciones", "posicion")}
        expected = _version(data, errors)
        nombre = (_campo(data, "nombre", columnas.limpiar_nombre, errors)
                  if "nombre" in data else None)
        opciones = (_campo(data, "opciones", columnas.limpiar_opciones, errors)
                    if "opciones" in data else None)
        posicion: Any = data.get("posicion")
        if "posicion" in data and (type(posicion) is not int
                                   or not 0 <= posicion < columnas.MAX_COLUMNAS):
            errors["posicion"] = "Envía el lugar de la columna (entero desde 0)."
        if errors:
            raise _invalid(errors)
        return repo.cambiar(conn, base_id, column_id, expected, actor, nombre, opciones, posicion)
    return _cambiar(request, cambio)


def retire(request: Request) -> Respuesta:
    """{expected_version}: stop showing and accepting the column. Reversible."""
    return _retirar(request, restaurar=False)


def restore(request: Request) -> Respuesta:
    """{expected_version}: the column and the values kept under it show again."""
    return _retirar(request, restaurar=True)


def _retirar(request: Request, restaurar: bool) -> Respuesta:
    def cambio(conn: DatabaseConnection, base_id: str, column_id: str,
               actor: dict[str, Any]) -> dict[str, Any]:
        data = parse_json(request.body)
        errors = {k: "Campo no admitido." for k in data if k != "expected_version"}
        expected = _version(data, errors)
        if errors:
            raise _invalid(errors)
        return repo.retirar(conn, base_id, column_id, expected, actor, restaurar)
    return _cambiar(request, cambio)


def _cambiar(request: Request, cambio: Any) -> Respuesta:
    """Run one change on the definition named in the path: authorized where it
    is saved, before any answer about the column, the body or the version."""
    base_id = request.uuid_param("bid")
    with db.escritura() as conn:
        alcance = auth.reverificar_base(conn, request.sesion, base_id, "columnas.gestionar",
                                        exclusivo=True)
        column_id = _columna(request, conn, base_id)
        try:
            return {"columna": cambio(conn, base_id, column_id, alcance.actor)}
        except repo.ConflictError:
            raise ApiError(
                "Otra persona cambió esta columna. Revisa su versión antes de repetir el cambio.",
                409, {"code": "conflict",
                      "columna": repo.obtener(conn, base_id, column_id)}) from None
        except repo.EstadoError as exc:
            raise _estado(exc) from None

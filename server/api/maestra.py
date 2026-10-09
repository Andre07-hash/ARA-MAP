"""Endpoints for work bases and their access grants.

Listing is for anyone who can open a base, and returns only the ones that
caller may open. Everything else is administration (bases.gestionar): the
dispatcher refuses it to operators, and each write re-checks the session, the
role and the base inside its own transaction before changing anything.
"""

from __future__ import annotations

import uuid
from typing import Any

from .. import auth, db
from ..protocols import DatabaseConnection
from ..repo import maestra as repo
from ..router import Request
from ..web_util import ApiError, parse_json

Respuesta = dict[str, Any]

MAX_NOMBRE = 100


def _invalid(fields: dict[str, str], **extra: Any) -> ApiError:
    return ApiError("Revisa los campos marcados.", 422,
                    {"code": "validation_failed", "fields": fields, **extra})


def _body(request: Request, *permitidos: str) -> tuple[dict[str, Any], dict[str, str]]:
    data = parse_json(request.body)
    return data, {k: "Campo no admitido." for k in data if k not in permitidos}


def _version(data: dict[str, Any], errors: dict[str, str]) -> int:
    expected: Any = data.get("expected_version")
    if type(expected) is not int or expected < 1:
        errors["expected_version"] = "Envía la versión que estabas viendo (entero)."
        return 0
    return expected


def _nombre(data: dict[str, Any], errors: dict[str, str]) -> str:
    valor = data.get("nombre")
    nombre = " ".join(valor.split()) if isinstance(valor, str) else ""
    if not nombre or len(nombre) > MAX_NOMBRE:
        errors["nombre"] = f"Escribe un nombre (hasta {MAX_NOMBRE} caracteres)."
    return nombre


def _cambiar(request: Request, cambio: Any) -> Respuesta:
    """Run one administrative change on the base named in the path."""
    base_id = request.uuid_param("bid")
    with db.escritura() as conn:
        alcance = auth.reverificar_base(conn, request.sesion, base_id, "bases.gestionar",
                                        exclusivo=True)
        try:
            return _respuesta(conn, cambio(conn, base_id, alcance.actor))
        except repo.ConflictError:
            raise ApiError(
                "Otra persona cambió esta base de trabajo. Revisa su versión antes de repetir"
                " el cambio.", 409,
                {"code": "conflict", "base": repo.obtener(conn, base_id)}) from None
        except repo.EstadoError as exc:
            mensaje = ("La base de trabajo está archivada." if exc.code == "base_archivada"
                       else "La base de trabajo no está archivada.")
            raise ApiError(mensaje, 409, {"code": exc.code}) from None


def _respuesta(conn: DatabaseConnection, base: dict[str, Any]) -> Respuesta:
    return {"base": base, "usuarios": repo.accesos(conn, base["id"])}


def listing(request: Request) -> Respuesta:
    """?archivadas=1 adds archived bases, for administrators only."""
    sesion: auth.Sesion = request.sesion
    admin = sesion.rol == "admin"
    with db.session() as conn:
        bases = repo.listar(conn, None if admin else sesion.user_id,
                            con_archivadas=admin and request.q("archivadas") == "1")
    return {"bases": bases, "total": len(bases)}


MAX_OPERADORES = 200


def operators(request: Request) -> Respuesta:
    """?q=&limit=: the operator accounts a grant may name, for the grant
    editor. Administrators only (bases.gestionar); at most 200 per answer."""
    errors = {k: "Parámetro no admitido." for k in request.query if k not in ("q", "limit")}
    try:
        limite = int(request.q("limit") or 100)
        if not 1 <= limite <= MAX_OPERADORES:
            raise ValueError
    except ValueError:
        errors["limit"] = f"Usa un número entero de 1 a {MAX_OPERADORES}."
        limite = 100
    buscado = request.q("q") or ""
    if len(buscado) > MAX_NOMBRE:
        errors["q"] = f"Admite hasta {MAX_NOMBRE} caracteres."
    if errors:
        raise ApiError("Parámetros inválidos.", 422, {"code": "validation_failed", "fields": errors})
    with db.session() as conn:
        usuarios, total = repo.operadores(conn, buscado, limite)
    return {"usuarios": usuarios, "total": total}


def create(request: Request) -> Respuesta:
    """{nombre}: a new empty work base. No terrain data or file is needed."""
    data, errors = _body(request, "nombre")
    nombre = _nombre(data, errors)
    if errors:
        raise _invalid(errors)
    with db.escritura() as conn:
        alcance = auth.reverificar(conn, request.sesion, "bases.gestionar")
        return _respuesta(conn, repo.crear(conn, nombre, alcance.actor))


def rename(request: Request) -> Respuesta:
    """{expected_version, nombre}"""
    data, errors = _body(request, "expected_version", "nombre")
    expected, nombre = _version(data, errors), _nombre(data, errors)
    if errors:
        raise _invalid(errors)
    return _cambiar(request, lambda conn, bid, actor: repo.renombrar(conn, bid, expected, nombre, actor))


def archive(request: Request) -> Respuesta:
    """{expected_version}"""
    return _archivo(request, repo.archivar)


def restore(request: Request) -> Respuesta:
    """{expected_version}"""
    return _archivo(request, repo.restaurar)


def _archivo(request: Request, operacion: Any) -> Respuesta:
    data, errors = _body(request, "expected_version")
    expected = _version(data, errors)
    if errors:
        raise _invalid(errors)
    return _cambiar(request, lambda conn, bid, actor: operacion(conn, bid, expected, actor))


def access(request: Request) -> Respuesta:
    base_id = request.uuid_param("bid")
    with db.session() as conn:
        auth.require_base(request, base_id, "bases.gestionar", conn)
        base = repo.obtener(conn, base_id)
        assert base is not None
        return _respuesta(conn, base)


def replace_access(request: Request) -> Respuesta:
    """{expected_version, usuarios: [id, ...]}: the complete set of operators
    who may open this base afterwards. An empty list revokes everyone."""
    data, errors = _body(request, "expected_version", "usuarios")
    expected = _version(data, errors)
    usuarios: set[str] = set()
    pedidos = data.get("usuarios")
    if not isinstance(pedidos, list):
        errors["usuarios"] = "Envía la lista completa de identificadores de usuario."
    else:
        try:
            usuarios = {str(uuid.UUID(u)) for u in pedidos}
        except (ValueError, TypeError, AttributeError):
            errors["usuarios"] = "Cada usuario debe ser un identificador válido."
    if errors:
        raise _invalid(errors)

    def cambio(conn: DatabaseConnection, bid: str, actor: dict[str, Any]) -> dict[str, Any]:
        try:
            return repo.reemplazar_accesos(conn, bid, expected, usuarios, actor)
        except repo.UsuariosError as exc:
            raise _invalid({"usuarios": "Hay usuarios que no pueden recibir acceso."},
                           usuarios=exc.motivos) from None
    return _cambiar(request, cambio)

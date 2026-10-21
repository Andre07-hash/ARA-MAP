"""Endpoints for work bases and their access grants.

Listing is for anyone who can open a base, and returns only the ones that
caller may open. Everything else is administration (bases.gestionar): the
dispatcher refuses it to operators, and each write re-checks the session, the
role and the base inside its own transaction before changing anything.
"""

from __future__ import annotations

import uuid
from typing import Any

from .. import auth, carga_maestra, db
from ..protocols import DatabaseConnection
from ..repo import maestra as repo
from ..router import Request
from ..web_util import ApiError, parse_json, texto_seguro
from .importar import _read_upload

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
    elif not texto_seguro(nombre):
        errors["nombre"] = "Contiene caracteres no admitidos."
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


def _respuesta(conn: DatabaseConnection, base: dict[str, Any]) -> Respuesta:
    return {"base": base, "usuarios": repo.accesos(conn, base["id"])}


def listing(request: Request) -> Respuesta:
    sesion: auth.Sesion = request.sesion
    with db.session() as conn:
        bases = repo.listar(conn, None if sesion.rol == "admin" else sesion.user_id)
    return {"bases": bases, "total": len(bases)}


MAX_OPERADORES = 200
MAX_CAMPO_CUENTA = 200


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
    elif not texto_seguro(buscado):
        errors["q"] = "Contiene caracteres no admitidos."
    if errors:
        raise ApiError("Parámetros inválidos.", 422, {"code": "validation_failed", "fields": errors})
    with db.session() as conn:
        usuarios, total = repo.operadores(conn, buscado, limite)
    return {"usuarios": usuarios, "total": total}


def create_account(request: Request) -> Respuesta:
    """{login, display_name, password, rol}: a new account, operator or
    administrator. Administrators only (usuarios.gestionar). The password is
    only hashed: it is never logged, stored as is or sent back."""
    data, errors = _body(request, "login", "display_name", "password", "rol")
    for campo in ("login", "display_name", "password"):
        valor = data.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            errors[campo] = "Campo obligatorio."
        elif len(valor) > MAX_CAMPO_CUENTA or not texto_seguro(valor):
            errors[campo] = "Contiene caracteres no admitidos o es demasiado largo."
    if data.get("rol") not in auth.ROLES:
        errors["rol"] = "Elige operador o administrador."
    if errors:
        raise _invalid(errors)
    with db.escritura() as conn:
        alcance = auth.reverificar(conn, request.sesion, "usuarios.gestionar")
        try:
            # ponytail: hashing (PBKDF2) runs inside the write lock; rare admin action.
            cuenta = auth.create_user(conn, data["login"], data["display_name"], data["password"],
                                      rol=data["rol"], actor=alcance.actor)
        except auth.AccountError as error:
            raise ApiError(str(error), 422, {"code": "validation_failed"}) from None
    return {"cuenta": cuenta}


def create(request: Request) -> Respuesta:
    """{nombre}: a new empty work base. No terrain data or file is needed."""
    data, errors = _body(request, "nombre")
    nombre = _nombre(data, errors)
    if errors:
        raise _invalid(errors)
    with db.escritura() as conn:
        alcance = auth.reverificar(conn, request.sesion, "bases.gestionar")
        return _respuesta(conn, repo.crear(conn, nombre, alcance.actor))


def importar(request: Request) -> Respuesta:
    """The raw bytes of an Excel or CSV file (name in X-Archivo) into a work base.

    With ?simular=1 it only reports what a load would do. Otherwise it creates
    the new rows, all or nothing; duplicates are skipped and reported, and an
    invalid value anywhere is a 422 that writes nothing (server/carga_maestra.py).
    """
    base_id = request.uuid_param("bid")
    simular = request.q("simular") == "1"
    # Parsed before any transaction: the write lock is never held while a file
    # is read (the router already refused anyone without bases.gestionar).
    leido = _read_upload(request).resultado
    filas, errores = carga_maestra.validar(leido.records)
    if errores:
        raise ApiError("El archivo tiene valores no admitidos; no se guardó nada.", 422,
                       {"code": "validation_failed", "errores": errores[:LISTA_MAXIMA],
                        "total_errores": len(errores)})
    if simular:
        with db.session() as conn:
            auth.require_base(request, base_id, "bases.gestionar", conn)
            nuevas, duplicadas = carga_maestra.cargar(conn, base_id, leido.records, filas,
                                                      {}, simular=True)
    else:
        with db.escritura() as conn:
            alcance = auth.reverificar_base(conn, request.sesion, base_id, "bases.gestionar")
            nuevas, duplicadas = carga_maestra.cargar(conn, base_id, leido.records, filas,
                                                      alcance.actor, simular=False)
    avisos = [f"línea {r.fila} ({r.terreno}): «{n.valor}» en {n.campo} no es un número;"
              " el campo queda vacío" for r in leido.records for n in r.notes]
    return {
        "simulacion": simular,
        "leidas": len(leido.records),
        "nuevas": nuevas,
        "duplicadas": duplicadas[:LISTA_MAXIMA],
        "total_duplicadas": len(duplicadas),
        "sin_nombre": [f"línea {r.fila}: {r.resumen}" for r in leido.rechazadas][:LISTA_MAXIMA],
        "total_sin_nombre": len(leido.rechazadas),
        "avisos": avisos[:LISTA_MAXIMA],
        "total_avisos": len(avisos),
        "no_cargadas": carga_maestra.no_cargadas(leido),
    }


LISTA_MAXIMA = 200      # lines of each kind sent back; the totals say the rest


def rename(request: Request) -> Respuesta:
    """{expected_version, nombre}"""
    data, errors = _body(request, "expected_version", "nombre")
    expected, nombre = _version(data, errors), _nombre(data, errors)
    if errors:
        raise _invalid(errors)
    return _cambiar(request, lambda conn, bid, actor: repo.renombrar(conn, bid, expected, nombre, actor))


def delete(request: Request) -> Respuesta:
    """{expected_version}: delete an empty work base for good, with its
    columns and grants. A base with terrains is a 409 base_con_terrenos."""
    data, errors = _body(request, "expected_version")
    expected = _version(data, errors)
    if errors:
        raise _invalid(errors)
    base_id = request.uuid_param("bid")
    with db.escritura() as conn:
        auth.reverificar_base(conn, request.sesion, base_id, "bases.gestionar", exclusivo=True)
        try:
            repo.borrar(conn, base_id, expected)
        except repo.ConflictError:
            raise ApiError(
                "Otra persona cambió esta base de trabajo. Revisa su versión antes de repetir"
                " el cambio.", 409,
                {"code": "conflict", "base": repo.obtener(conn, base_id)}) from None
        except repo.EstadoError as exc:
            raise ApiError("La base todavía tiene terrenos. Bórralos o transfiérelos a otra base"
                           " antes de borrarla.", 409, {"code": exc.code}) from None
    return {"borrado": True}


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

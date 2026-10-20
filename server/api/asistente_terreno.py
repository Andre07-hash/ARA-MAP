"""Endpoints of the terrain assistant (server/asistente/terreno.py).

    GET  /api/asistente-terreno/config          {habilitado, disponible, max_pregunta}
    POST /api/asistente-terreno/:id/consultar   {accion, pregunta} -> one answer
    POST /api/asistente-terreno/buscar          {pregunta} -> criteria and the first page
    POST /api/asistente-terreno/resultados      {filtros, cursor} -> the next page, no model
    POST /api/asistente-terreno/comparar        {terrenos: [{id, version}] x 2-3}

Administrators only (maestra.global, checked by the dispatcher) and, per
request, the terrain itself (auth.require_terreno). Nothing here writes a
terrain: the only row written is the usage ledger's, in its own short session.
The contract of the master-table routes is in issue #69.
"""

from __future__ import annotations

import uuid
from typing import Any

from .. import auth, db, inventario
from ..asistente import busqueda
from ..asistente import terreno as asistente
from ..repo import inventario as repo
from ..router import Request
from ..web_util import ApiError, parse_json, texto_seguro

Respuesta = dict[str, Any]
CAPACIDAD = "maestra.global"
MAX_CUERPO = 4096


def config(request: Request) -> Respuesta:
    return asistente.estado_publico()


def _no_existe() -> ApiError:
    return ApiError(auth.NO_EXISTE_TERRENO, 404, {"code": "not_found"})


def _invalida(campos: dict[str, str]) -> ApiError:
    return ApiError("Revisa la consulta.", 422, {"code": "validation_failed", "fields": campos})


def _falla(falla: asistente.FallaChatError) -> ApiError:
    return ApiError(falla.mensaje, falla.status, {"code": falla.code})


def _leer_terreno(request: Request, terreno_id: str) -> dict[str, Any]:
    """Authorize and read in one short session, closed before returning."""
    with db.session() as conn:
        auth.require_terreno(request, terreno_id, CAPACIDAD, conn)
        terreno = repo.get(conn, terreno_id)
    if terreno is None:
        raise _no_existe()
    return terreno


def _peticion(body: bytes) -> tuple[str, str]:
    if len(body) > MAX_CUERPO:
        raise _invalida({"pregunta": f"Máximo {asistente.MAX_PREGUNTA} caracteres."})
    try:
        data = parse_json(body)
    except ApiError:
        raise _invalida({"cuerpo": "Se esperaba un objeto JSON."}) from None
    extra = sorted(set(data) - {"accion", "pregunta"})
    if extra:
        raise _invalida({k: "Campo no admitido." for k in extra})
    accion, pregunta = data.get("accion"), data.get("pregunta", "")
    if accion not in asistente.ACCIONES:
        raise _invalida({"accion": "Acción no reconocida."})
    if pregunta is None:
        pregunta = ""
    if not isinstance(pregunta, str) or not texto_seguro(pregunta, lineas=True):
        raise _invalida({"pregunta": "Texto no válido."})
    pregunta = pregunta.strip()
    if len(pregunta) > asistente.MAX_PREGUNTA:
        raise _invalida({"pregunta": f"Máximo {asistente.MAX_PREGUNTA} caracteres."})
    if accion == "pregunta" and not pregunta:
        raise _invalida({"pregunta": "Escribe una pregunta."})
    if accion != "pregunta" and pregunta:
        raise _invalida({"pregunta": "Sólo la acción «pregunta» lleva texto."})
    return accion, pregunta


def consultar(request: Request) -> Respuesta:
    try:
        terreno_id = request.uuid_param("id")
    except ApiError:
        raise _no_existe() from None
    # 1. Who and what, before anything about the service or the body.
    terreno = _leer_terreno(request, terreno_id)
    # 2. The service.
    if not asistente.habilitado():
        raise _falla(asistente.falla("chat_deshabilitado"))
    # 3. The request.
    accion, pregunta = _peticion(request.body)
    usados, faltantes, advertencias = asistente.contexto(terreno["draft"])
    if accion == "faltantes":
        texto, origen = asistente.respuesta_de_reglas(faltantes), "reglas"
    else:
        try:
            texto, cortado = asistente.consultar_modelo(accion, usados, faltantes, pregunta)
        except asistente.FallaChatError as falla:
            raise _falla(falla) from None
        if cortado:
            advertencias.append("La respuesta se recortó por su longitud.")
        origen = "modelo"
        # 4. A late answer is delivered only to whoever may still read this
        # terrain, and only if it still describes the current version.
        actual = _leer_terreno(request, terreno_id)
        if actual["version"] != terreno["version"]:
            raise ApiError("El terreno cambió mientras se preparaba la respuesta. Actualiza y"
                           " vuelve a consultar.", 409,
                           {"code": "conflict", "current_version": actual["version"]})
    return {"terreno_id": terreno_id, "version": terreno["version"], "accion": accion,
            "respuesta": texto, "campos_usados": usados, "faltantes": faltantes,
            "advertencias": advertencias, "origen": origen}


# -------------------------------------------- the master table (issue #69)

MAX_CURSOR = 2000


def _activo() -> None:
    if not asistente.habilitado():
        raise _falla(asistente.falla("chat_deshabilitado"))


def _cuerpo(body: bytes, permitidas: set[str]) -> dict[str, Any]:
    if len(body) > MAX_CUERPO:
        raise _invalida({"cuerpo": "La petición es demasiado grande."})
    try:
        data = parse_json(body)
    except ApiError:
        raise _invalida({"cuerpo": "Se esperaba un objeto JSON."}) from None
    extra = sorted(set(data) - permitidas)
    if extra:
        raise _invalida({k: "Campo no admitido." for k in extra})
    return data


def buscar(request: Request) -> Respuesta:
    """Interpret the question with the model, then run the existing list query."""
    auth.require(request, CAPACIDAD)
    _activo()
    pregunta = _cuerpo(request.body, {"pregunta"}).get("pregunta")
    if not isinstance(pregunta, str) or not texto_seguro(pregunta, lineas=True) or not pregunta.strip():
        raise _invalida({"pregunta": "Escribe qué terrenos buscas."})
    pregunta = pregunta.strip()
    if len(pregunta) > asistente.MAX_PREGUNTA:
        raise _invalida({"pregunta": f"Máximo {asistente.MAX_PREGUNTA} caracteres."})
    try:
        texto, cortado = asistente.llamar_modelo(busqueda.SISTEMA_BUSQUEDA,
                                                 f"<peticion>{asistente._json(pregunta)}</peticion>")
        if cortado:
            raise busqueda.RespuestaInvalidaError()
        filtros, aclaracion = busqueda.interpretar(texto)
    except asistente.FallaChatError as error:
        raise _falla(error) from None
    except busqueda.RespuestaInvalidaError:
        raise _falla(asistente.falla("chat_respuesta_invalida")) from None
    if aclaracion is not None:
        return {"estado": "aclaracion", "aclaracion": aclaracion, "origen": "modelo"}
    assert filtros is not None
    # The session and role are read again after the wait, with the query.
    with db.session() as conn:
        auth.require(request, CAPACIDAD, conn)
        try:
            canon = busqueda.validar(conn, filtros)
        except busqueda.AclaracionError as aclara:
            return {"estado": "aclaracion", "aclaracion": str(aclara), "origen": "reglas"}
        return {**busqueda.pagina(conn, canon, None), "origen": "modelo"}


def resultados(request: Request) -> Respuesta:
    """The next page of a search already interpreted: no model call."""
    _activo()
    data = _cuerpo(request.body, {"filtros", "cursor"})
    cursor = data.get("cursor")
    if not isinstance(cursor, str) or not cursor or len(cursor) > MAX_CURSOR:
        raise _invalida({"cursor": "Cursor inválido."})
    try:
        filtros = busqueda.filtros_de(data.get("filtros"))
    except busqueda.RespuestaInvalidaError:
        raise _invalida({"filtros": "Filtros inválidos."}) from None
    with db.session() as conn:
        auth.require(request, CAPACIDAD, conn)
        try:
            canon = busqueda.validar(conn, filtros)
            return {**busqueda.pagina(conn, canon, cursor), "origen": "reglas"}
        except busqueda.AclaracionError:
            # The registered values changed since the search: start again.
            raise _invalida({"filtros": "Los criterios ya no coinciden con el inventario."}) from None
        except (inventario.QueryError, repo.CursorError):
            raise _invalida({"cursor": "Cursor inválido."}) from None


def _seleccion(body: bytes) -> list[tuple[str, int]]:
    terrenos = _cuerpo(body, {"terrenos"}).get("terrenos")
    if not isinstance(terrenos, list) or not 2 <= len(terrenos) <= len(busqueda.ALIAS):
        raise _invalida({"terrenos": "Elige de dos a tres terrenos."})
    seleccion = []
    for t in terrenos:
        if not isinstance(t, dict) or set(t) != {"id", "version"} or type(t["version"]) is not int:
            raise _invalida({"terrenos": "Selección inválida."})
        try:
            seleccion.append((str(uuid.UUID(t["id"])), t["version"]))
        except (ValueError, TypeError, AttributeError):
            raise _invalida({"terrenos": "Selección inválida."}) from None
    if len({i for i, _ in seleccion}) != len(seleccion):
        raise _invalida({"terrenos": "Hay terrenos repetidos."})
    return seleccion


def _leer_seleccion(request: Request, seleccion: list[tuple[str, int]]) -> list[dict[str, Any]]:
    """Every terrain authorized and at the version the person saw, or nothing."""
    terrenos = []
    with db.session() as conn:
        for terreno_id, version in seleccion:
            auth.require_terreno(request, terreno_id, CAPACIDAD, conn)
            terreno = repo.get(conn, terreno_id)
            if terreno is None:
                raise _no_existe()
            if terreno["version"] != version:
                raise ApiError("Un terreno de la selección cambió. Actualiza la búsqueda y vuelve a"
                               " elegir.", 409, {"code": "conflict", "terreno_id": terreno_id,
                                                  "current_version": terreno["version"]})
            terrenos.append(terreno)
    return terrenos


def comparar(request: Request) -> Respuesta:
    auth.require(request, CAPACIDAD)
    _activo()
    seleccion = _seleccion(request.body)
    terrenos = _leer_seleccion(request, seleccion)
    filas, advertencias, datos = busqueda.tabla_comparativa(terrenos)
    try:
        texto, cortado = asistente.llamar_modelo(busqueda.SISTEMA_COMPARACION,
                                                 busqueda.mensaje_comparacion(datos, advertencias))
        resumen: dict[str, Any] = {"estado": "ok", "texto": texto, "origen": "modelo"}
        if cortado:
            advertencias.append("El resumen se recortó por su longitud.")
    except asistente.FallaChatError as error:
        resumen = {"estado": "error", "code": error.code, "mensaje": error.mensaje}
    # Late: the same people, terrains and versions, or no answer at all.
    _leer_seleccion(request, seleccion)
    return {"terrenos": [{"alias": a, "terreno_id": t["id"], "version": t["version"],
                          "nombre": t["draft"].get("terreno") or "Terreno sin nombre",
                          "base_id": t["base_id"]} for a, t in zip(busqueda.ALIAS, terrenos)],
            "filas": filas, "advertencias": advertencias, "resumen": resumen}

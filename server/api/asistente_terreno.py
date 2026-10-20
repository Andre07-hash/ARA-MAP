"""Endpoints of the terrain assistant (server/asistente/terreno.py).

    GET  /api/asistente-terreno/config          {habilitado, disponible, max_pregunta}
    POST /api/asistente-terreno/:id/consultar   {accion, pregunta} -> one answer

Administrators only (maestra.global, checked by the dispatcher) and, per
request, the terrain itself (auth.require_terreno). Nothing here writes a
terrain: the only row written is the usage ledger's, in its own short session.
"""

from __future__ import annotations

from typing import Any

from .. import auth, db
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

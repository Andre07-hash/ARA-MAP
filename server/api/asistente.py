"""Endpoints of the import assistant.

    POST /api/importar/analizar     raw file bytes + X-Archivo [+ ?base_id]
    POST /api/importar/preparar     {borrador, revision, respuestas, correcciones}
    GET  /api/formatos              saved formats (no cell values)
    PATCH/DELETE /api/formatos/:id  rename / forget a format

Confirmation stays on the existing /api/importar/confirmar and
/api/bases/:id/adjuntar, which commit the exact previewed result.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .. import db
from ..asistente import servicio
from ..repo import bases as repo_bases
from ..repo import formatos as repo_formatos
from ..router import Request
from ..web_util import ApiError, parse_json, require
from .importar import MAX_UPLOAD

Respuesta = dict[str, Any]
MAX_NOMBRE_FORMATO = 100


def analizar(request: Request) -> Respuesta:
    if not request.body:
        raise ApiError("No se recibió ningún archivo.")
    if len(request.body) > MAX_UPLOAD:
        raise ApiError("El archivo supera el límite de 25 MB.", 413)
    archivo = unquote(request.headers.get("X-Archivo", "") or "")
    if not archivo:
        raise ApiError("Falta el nombre del archivo.")
    base_id = request.q("base_id")
    if base_id is not None:
        try:
            base_id_int = int(base_id)
        except ValueError:
            raise ApiError("La base indicada no existe.", 404) from None
        with db.session() as conn:
            if repo_bases.get(conn, base_id_int) is None:
                raise ApiError("La base indicada no existe.", 404)
    return servicio.analizar(request.body, archivo, int(base_id) if base_id else None)


def preparar(request: Request) -> Respuesta:
    data = parse_json(request.body)
    token, revision = require(data, "borrador", "revision")
    if not isinstance(token, str) or type(revision) is not int:
        raise ApiError("Petición inválida.")
    respuestas = data.get("respuestas") or []
    correcciones = data.get("correcciones") or {}
    if not isinstance(respuestas, list) or not all(isinstance(r, dict) for r in respuestas):
        raise ApiError("Respuestas inválidas.")
    if not isinstance(correcciones, dict):
        raise ApiError("Correcciones inválidas.")
    return servicio.preparar(token, revision, respuestas, correcciones)


def formatos(request: Request) -> Respuesta:
    with db.session() as conn:
        return {"formatos": [_publico(f) for f in repo_formatos.listing(conn)]}


def renombrar_formato(request: Request) -> Respuesta:
    data = parse_json(request.body)
    (nombre,) = require(data, "nombre")
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre.strip()) > MAX_NOMBRE_FORMATO:
        raise ApiError(f"El nombre debe tener entre 1 y {MAX_NOMBRE_FORMATO} caracteres.")
    with db.session() as conn:
        if not repo_formatos.rename(conn, request.param("id"), " ".join(nombre.split())):
            raise ApiError("El formato no existe.", 404)
        return {"formato": _publico(repo_formatos.get(conn, request.param("id")))}


def eliminar_formato(request: Request) -> Respuesta:
    with db.session() as conn:
        formato = repo_formatos.get(conn, request.param("id"))
        if formato is None or not repo_formatos.delete(conn, formato["id"]):
            raise ApiError("El formato no existe.", 404)
        return {"eliminado": formato["nombre"]}


def _publico(formato: Any) -> dict[str, Any]:
    from ..asistente.campos import ETIQUETA_DESTINO
    return {
        "id": formato["id"], "nombre": formato["nombre"], "version": formato["version"],
        "usos": formato["usos"], "vigente": formato["reemplazado_por"] is None,
        "creado_en": formato["creado_en"], "actualizado_en": formato["actualizado_en"],
        "decimal": formato.get("decimal"), "hoja": formato.get("hoja"),
        "campos": [{"encabezado": c, "ocurrencia": o, "destino": ETIQUETA_DESTINO.get(d, d)}
                   for c, o, d in formato.get("asignaciones", [])],
    }

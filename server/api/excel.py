"""Connected workbook endpoints (signed-in team members only).

    GET  /api/excel/fuentes                      every source + connector availability
    GET  /api/excel/fuentes/:id                  one source (expires stale runs first)
    GET  /api/excel/fuentes/:id/versiones        activated versions, newest first
    GET  /api/excel/fuentes/:id/versiones/:vid   one retained version, reconstructed
    POST /api/excel/vista-previa                 {cuenta_id, drive_id, item_id, hoja?}
    POST /api/excel/fuentes                      connect (Idempotency-Key required)
    POST /api/excel/fuentes/:id/actualizar       refresh {confirmar_vacio?} (Idempotency-Key)
    POST /api/excel/fuentes/:id/configuracion    {generacion, hoja, columna_id, moneda, columna_moneda?}
    POST /api/excel/fuentes/:id/desconectar      {generacion}
    POST /api/excel/fuentes/:id/reconectar       {generacion}

Every refresh/connect returns {fuente, ejecucion}; see repo/excel.fuente_dto.
The provider comes from FABRICA, which tests replace with an in-memory fake.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

from .. import db
from ..excel import lectura, microsoft, servicio
from ..excel.lectura import Configuracion, LecturaError
from ..excel.proveedor import ProveedorError
from ..repo import carpetas as repo_carpetas
from ..repo import excel as repo
from ..router import Request
from ..web_util import ApiError, parse_json

Respuesta = dict[str, Any]
_KEY = re.compile(r"^[\x21-\x7e]{8,200}$")


# The provider for a stored file identity. Tests replace it with an
# in-memory fake; it is never chosen from request input.
FABRICA: servicio.FabricaProveedor = microsoft.fabrica


def _actor(request: Request) -> dict[str, Any]:
    if request.user is None:
        raise ApiError("Inicia sesión para continuar.", 401, {"code": "unauthenticated"})
    return request.user


def _clave(request: Request) -> str:
    clave = (request.headers.get("Idempotency-Key") or "").strip()
    if not _KEY.match(clave):
        raise ApiError("Falta el encabezado Idempotency-Key (8 a 200 caracteres).", 422,
                       {"code": "idempotency_key_required"})
    return clave


def _id(request: Request) -> str:
    try:
        return str(uuid.UUID(request.params["id"]))
    except (KeyError, ValueError):
        raise ApiError("La fuente no existe.", 404, {"code": "not_found"}) from None


def _config(data: Mapping[str, Any]) -> Configuracion:
    errores: dict[str, str] = {}
    hoja, columna_id = data.get("hoja"), data.get("columna_id")
    moneda, columna_moneda = data.get("moneda"), data.get("columna_moneda")
    if not isinstance(hoja, str) or not hoja.strip():
        errores["hoja"] = "Elige la hoja."
    if not isinstance(columna_id, str) or not columna_id.strip():
        errores["columna_id"] = "Elige la columna con el ID único de cada terreno."
    if moneda not in lectura.MONEDAS:
        errores["moneda"] = "Indica la moneda de los precios: USD, MXN, una columna de moneda o desconocida."
    if moneda == "columna" and (not isinstance(columna_moneda, str) or not columna_moneda.strip()):
        errores["columna_moneda"] = "Elige la columna que indica la moneda."
    if errores:
        raise ApiError("Revisa la configuración.", 422, {"code": "validation_failed", "fields": errores})
    return Configuracion(str(hoja), str(columna_id).strip(), str(moneda),
                         str(columna_moneda).strip() if moneda == "columna" else None)


def _proveedor_error(exc: ProveedorError) -> ApiError:
    status = {"reconectar": 409, "sin_permiso": 403, "no_encontrado": 404, "no_disponible": 503,
              "no_configurado": 503, "demasiado_grande": 413, "archivo_cambiando": 409}.get(exc.codigo, 502)
    return ApiError(exc.mensaje, status, {"code": exc.codigo, "reintentable": exc.reintentable})


def _lectura_error(exc: LecturaError) -> ApiError:
    return ApiError(exc.mensaje, 413 if exc.codigo == "demasiado_grande" else 422, {"code": exc.codigo})


# -- reads ------------------------------------------------------------------

def listing(request: Request) -> Respuesta:
    _actor(request)
    with db.session() as conn:
        repo.expirar(conn)
        fuentes = repo.fuentes(conn)
    return {"fuentes": fuentes, "conector": microsoft.disponibilidad()}


def detail(request: Request) -> Respuesta:
    _actor(request)
    fuente_id = _id(request)
    with db.session() as conn:
        repo.expirar(conn, fuente_id)
        dto = repo.fuente_dto(conn, fuente_id)
    if dto is None:
        raise ApiError("La fuente no existe.", 404, {"code": "not_found"})
    return {"fuente": dto}


def versions(request: Request) -> Respuesta:
    _actor(request)
    fuente_id = _id(request)
    with db.session() as conn:
        if repo.fuente(conn, fuente_id) is None:
            raise ApiError("La fuente no existe.", 404, {"code": "not_found"})
        rows = conn.execute(
            "SELECT id, numero, filas, activada_en, modificado_en, modificado_por, configuracion_id,"
            " vacia_confirmada FROM excel_version WHERE fuente_id = ? ORDER BY numero DESC",
            (fuente_id,)).fetchall()
    return {"versiones": [dict(r) for r in rows]}


def version_detail(request: Request) -> Respuesta:
    _actor(request)
    fuente_id = _id(request)
    try:
        version_id = str(uuid.UUID(request.params["vid"]))
    except (KeyError, ValueError):
        raise ApiError("La versión no existe.", 404, {"code": "not_found"}) from None
    with db.session() as conn:
        v = repo.version(conn, version_id)
        if v is None or v["fuente_id"] != fuente_id:
            raise ApiError("La versión no existe.", 404, {"code": "not_found"})
        return {"version": v, "filas": repo.filas_de_version(conn, version_id)}


# -- setup ------------------------------------------------------------------

def preview(request: Request) -> Respuesta:
    """Sheets, headers and ID-column candidates of the chosen workbook.
    Nothing is stored."""
    _actor(request)
    data = parse_json(request.body)
    cuenta_id, drive_id, item_id = (data.get(k) for k in ("cuenta_id", "drive_id", "item_id"))
    if not all(isinstance(v, str) and v for v in (cuenta_id, drive_id, item_id)):
        raise ApiError("Elige un archivo.", 422, {"code": "validation_failed"})
    hoja = data.get("hoja") if isinstance(data.get("hoja"), str) else None
    try:
        proveedor = FABRICA({"cuenta_id": cuenta_id, "drive_id": drive_id, "item_id": item_id})
        meta, contenido = servicio.version_coherente(proveedor, lectura.MAX_BYTES)
        resumen = lectura.examinar(contenido, hoja)
    except ProveedorError as exc:
        raise _proveedor_error(exc) from None
    except LecturaError as exc:
        raise _lectura_error(exc) from None
    with db.session() as conn:
        existente = repo.fuente_por_archivo(conn, str(drive_id), str(item_id))
    return {"archivo": {"nombre": meta.nombre, "web_url": meta.web_url, "modificado_en": meta.modificado_en,
                        "modificado_por": meta.modificado_por},
            "ya_conectada": existente["id"] if existente else None, **resumen}


def create(request: Request) -> Respuesta:
    actor = _actor(request)
    clave = _clave(request)
    data = parse_json(request.body)
    config = _config(data)
    cuenta_id, drive_id, item_id = (data.get(k) for k in ("cuenta_id", "drive_id", "item_id"))
    nombre = data.get("nombre")
    if not all(isinstance(v, str) and v for v in (cuenta_id, drive_id, item_id)):
        raise ApiError("Elige un archivo.", 422, {"code": "validation_failed"})
    if not isinstance(nombre, str) or not nombre.strip():
        raise ApiError("Ponle un nombre a la base.", 422,
                       {"code": "validation_failed", "fields": {"nombre": "Obligatorio."}})
    carpeta_id = data.get("carpeta_id")
    if carpeta_id is not None:
        with db.session() as conn:
            repo_carpetas.require_folder(conn, "bases", int(carpeta_id))
    try:
        return servicio.conectar(fabrica=FABRICA, cuenta_id=str(cuenta_id), drive_id=str(drive_id),
                                 item_id=str(item_id), config=config, nombre=nombre.strip(),
                                 carpeta_id=int(carpeta_id) if carpeta_id is not None else None,
                                 actor=actor, clave=clave)
    except servicio.DatosInvalidosError as exc:
        raise ApiError("El libro tiene filas que no se pueden usar; no se conectó nada.", 422,
                       {"code": "datos_invalidos", "problemas": [p.dto() for p in exc.problemas[:200]]}) from None
    except servicio.YaConectadaError as exc:
        raise ApiError("Ese archivo ya está conectado a otra base.", 409,
                       {"code": "ya_conectada", "fuente_id": exc.fuente_id}) from None
    except repo.IdempotenciaConflictoError:
        raise ApiError("Esa Idempotency-Key ya se usó con otros datos.", 409,
                       {"code": "idempotency_conflict"}) from None
    except ProveedorError as exc:
        raise _proveedor_error(exc) from None
    except LecturaError as exc:
        raise _lectura_error(exc) from None


# -- refresh and lifecycle -----------------------------------------------------

def refresh(request: Request) -> Respuesta:
    actor = _actor(request)
    clave = _clave(request)
    fuente_id = _id(request)
    data = parse_json(request.body)
    confirmar = data.get("confirmar_vacio")
    if confirmar is not None and not isinstance(confirmar, str):
        raise ApiError("Confirmación inválida.", 422, {"code": "validation_failed"})
    try:
        return servicio.actualizar(fabrica=FABRICA, fuente_id=fuente_id, actor=actor, clave=clave,
                                   confirmar_vacio=confirmar)
    except servicio.NoActivaError:
        raise ApiError("La fuente no existe o está desconectada.", 409, {"code": "no_activa"}) from None
    except repo.EnCursoError as exc:
        raise ApiError("Ya se está actualizando desde Excel.", 409,
                       {"code": "en_curso", "ejecucion": exc.ejecucion}) from None
    except repo.IdempotenciaConflictoError:
        raise ApiError("Esa Idempotency-Key ya se usó con otros datos.", 409,
                       {"code": "idempotency_conflict"}) from None


def _generacion(data: Mapping[str, Any]) -> int:
    generacion = data.get("generacion")
    if type(generacion) is not int or generacion < 1:
        raise ApiError("Envía la generación que estabas viendo.", 422, {"code": "validation_failed"})
    return generacion


def configure(request: Request) -> Respuesta:
    actor = _actor(request)
    fuente_id = _id(request)
    data = parse_json(request.body)
    generacion = _generacion(data)
    config = _config(data)
    try:
        return servicio.configurar(fabrica=FABRICA, fuente_id=fuente_id, generacion=generacion,
                                   config=config, actor=actor)
    except servicio.NoActivaError:
        raise ApiError("La fuente no existe.", 404, {"code": "not_found"}) from None
    except repo.ConflictoError:
        raise ApiError("La fuente cambió; vuelve a cargarla.", 409, {"code": "conflict"}) from None
    except ProveedorError as exc:
        raise _proveedor_error(exc) from None
    except LecturaError as exc:
        raise _lectura_error(exc) from None


def _lifecycle(request: Request, estado: str) -> Respuesta:
    _actor(request)
    fuente_id = _id(request)
    generacion = _generacion(parse_json(request.body))
    with db.session() as conn:
        if repo.fuente(conn, fuente_id) is None:
            raise ApiError("La fuente no existe.", 404, {"code": "not_found"})
        try:
            repo.cambiar_estado(conn, fuente_id, generacion, estado)
        except repo.ConflictoError:
            raise ApiError("La fuente cambió; vuelve a cargarla.", 409, {"code": "conflict"}) from None
        return {"fuente": repo.fuente_dto(conn, fuente_id)}


def disconnect(request: Request) -> Respuesta:
    """Stop refreshing; the base, its data and all history stay."""
    return _lifecycle(request, "desconectada")


def reconnect(request: Request) -> Respuesta:
    return _lifecycle(request, "activa")

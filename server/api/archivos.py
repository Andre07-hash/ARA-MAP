"""HTTP handlers for terrain attachments (packet 2B).

A thin transport over the accepted lifecycle in :mod:`server.archivos`: every
handler parses the request, calls exactly one service function with the
validated ``request.sesion`` and returns its result. Authorization, scope,
deadlines, leases, idempotency, privacy and cleanup reporting all stay in the
service; SQL stays in ``server/repo``. The actor and base always come from
the session and the database, never from the request.

Bytes are kept in an injected store (``configurar_almacen``); no store is
configured by default, so nothing can be written until the application wires
one (packet 3A). Binary answers are ``RespuestaBinaria`` values: see
``server/api/binario.py``. Routes are not registered here: the registry is
A-owned and listed in the 2B report's INTEGRATION_REQUESTS.md.
"""

from __future__ import annotations

import threading
import unicodedata
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from .. import archivos
from ..almacen import MAX_BLOQUE, Almacen, AlmacenLocal
from ..router import Request
from ..web_util import ApiError, parse_json
from .binario import RespuestaBinaria

Respuesta = dict[str, Any]
FabricaAlmacen = Callable[[], Almacen]

# Raw upload media types. Multipart or JSON/base64 bodies are refused: the
# body must be exactly the file's bytes.
TIPOS_CONTENIDO = {"application/pdf", "application/vnd.google-earth.kmz",
                   "application/octet-stream"}
METADATOS_MAX_BYTES = 16 * 1024
_SIN_CACHE = "private, no-store"
_AISLADO = "default-src 'none'; sandbox"

_candado = threading.Lock()
_fabrica: FabricaAlmacen | None = None
_almacen: Almacen | None = None


def configurar_almacen(fabrica: FabricaAlmacen | None) -> None:
    """Install (or, with None, remove) the factory that builds the byte store.

    The store is built on first use and reused; replacing the factory closes
    the previous store if it can be closed.
    """
    global _fabrica, _almacen
    with _candado:
        anterior = _almacen
        _fabrica, _almacen = fabrica, None
    cerrar = getattr(anterior, "close", None)
    if callable(cerrar):
        cerrar()


def almacen_local(raiz: str) -> FabricaAlmacen:
    """A factory for the accepted local filesystem store rooted at ``raiz``."""
    return lambda: AlmacenLocal(raiz)


def _almacen_actual() -> Almacen:
    global _almacen
    with _candado:
        if _almacen is None:
            if _fabrica is None:
                raise ApiError("El almacenamiento de archivos no está configurado.", 503,
                               {"code": "almacen_no_configurado"})
            _almacen = _fabrica()
        return _almacen


# -- request parsing -------------------------------------------------------------

def _cuerpo(request: Request) -> dict[str, Any]:
    try:
        return parse_json(request.body)
    except ApiError as exc:
        raise ApiError(exc.mensaje, 400, {"code": "cuerpo_invalido"}) from None


def _campo(datos: dict[str, Any], nombre: str) -> Any:
    """A body field as sent; the service validates its type and value."""
    return datos.get(nombre)


def _clave(request: Request) -> Any:
    # The service validates it (idempotencia_invalida when absent or malformed).
    return request.headers.get("Idempotency-Key")


def _limite(request: Request) -> Any:
    valor = request.q("limite")
    if valor is None:
        return archivos.HISTORY_DEFAULT
    return int(valor) if valor.isdigit() and len(valor) <= 4 else valor  # the service rejects the rest


def _parametro(request: Request, nombre: str) -> str:
    return str(request.params.get(nombre, ""))


def _sin_contenido(resultado: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in resultado.items() if k != "contenido"}


def _ascii(nombre: str) -> str:
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    limpio = "".join(c if 0x20 <= ord(c) < 0x7f and c not in '"\\;' else "_" for c in plano)
    return limpio.strip(" .") or "archivo"


def disposicion(nombre: str, tipo: str) -> str:
    """A safe attachment Content-Disposition: ASCII fallback plus RFC 5987 UTF-8.

    Quotes, backslashes, separators and every control character (CR/LF
    included) are removed from the fallback; the UTF-8 form is percent-encoded.
    """
    sin_control = "".join(c for c in nombre if unicodedata.category(c)[0] != "C")
    fallback = _ascii(sin_control)
    extension = "." + tipo
    if not fallback.lower().endswith(extension):
        fallback += extension
    utf8 = quote(sin_control or fallback, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{utf8}"


# -- lifecycle ---------------------------------------------------------------------

def iniciar(request: Request) -> Respuesta:
    datos = _cuerpo(request)
    return archivos.iniciar(
        request.sesion, _parametro(request, "id"), tipo=_campo(datos, "tipo"),
        nombre_original=_campo(datos, "nombre_original"),
        tamano_declarado=_campo(datos, "tamano_declarado"),
        sha256_declarado=_campo(datos, "sha256_declarado"), idempotency_key=_clave(request))


def listar(request: Request) -> Respuesta:
    return archivos.listar(request.sesion, _parametro(request, "id"),
                           cursor=request.q("cursor"), limite=_limite(request))


def contenido(request: Request) -> Respuesta:
    """PUT the raw file bytes of a pending upload (replaces earlier staging)."""
    tipo = (request.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if tipo not in TIPOS_CONTENIDO:
        raise ApiError("Envía el archivo tal cual, sin multipart ni JSON.", 415,
                       {"code": "tipo_contenido_invalido", "permitidos": sorted(TIPOS_CONTENIDO)})
    if request.headers.get("Transfer-Encoding"):
        raise ApiError("Indica Content-Length; no se acepta envío por partes.", 411,
                       {"code": "longitud_requerida"})
    declarada = request.headers.get("Content-Length")
    if declarada is None or not declarada.isdigit() or int(declarada) != len(request.body):
        raise ApiError("El contenido llegó incompleto.", 400, {"code": "cuerpo_incompleto"})
    vista = memoryview(request.body)
    bloques = (vista[i:i + MAX_BLOQUE] for i in range(0, len(vista), MAX_BLOQUE))
    return archivos.escribir_temporal(request.sesion, _parametro(request, "vid"), bloques,
                                      _almacen_actual())


def completar(request: Request) -> Respuesta:
    return archivos.completar(request.sesion, _parametro(request, "vid"), _almacen_actual())


def cancelar(request: Request) -> Respuesta:
    return archivos.cancelar(request.sesion, _parametro(request, "vid"), _almacen_actual())


def procesar(request: Request) -> Respuesta:
    datos = _cuerpo(request)
    seleccion = datos.get("seleccion")
    if seleccion is not None and (not isinstance(seleccion, list) or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in seleccion)):
        raise ApiError("La selección debe ser una lista de índices.", 400,
                       {"code": "seleccion_invalida"})
    return archivos.reprocesar(request.sesion, _parametro(request, "vid"), _almacen_actual(),
                               seleccion=seleccion, idempotency_key=_clave(request))


def activar(request: Request) -> Respuesta:
    datos = _cuerpo(request)
    return archivos.activar(
        request.sesion, _parametro(request, "aid"), version_id=_campo(datos, "version_id"),
        geometria_id=_campo(datos, "geometria_id"), expected_revision=_campo(datos, "expected_revision"),
        idempotency_key=_clave(request))


def retirar(request: Request) -> Respuesta:
    datos = _cuerpo(request)
    return archivos.retirar(request.sesion, _parametro(request, "aid"),
                            expected_revision=_campo(datos, "expected_revision"),
                            idempotency_key=_clave(request), almacen=_almacen_actual())


# -- reads -------------------------------------------------------------------------

def historial(request: Request) -> Respuesta:
    return archivos.historial(request.sesion, _parametro(request, "aid"),
                              cursor=request.q("cursor"), limite=_limite(request))


def versiones(request: Request) -> Respuesta:
    return archivos.versiones(request.sesion, _parametro(request, "aid"),
                              cursor=request.q("cursor"), limite=_limite(request))


def intentos(request: Request) -> Respuesta:
    return archivos.intentos(request.sesion, _parametro(request, "vid"),
                             cursor=request.q("cursor"), limite=_limite(request))


def intento(request: Request) -> Respuesta:
    return archivos.intento(request.sesion, _parametro(request, "iid"))


def descarga(request: Request) -> RespuestaBinaria:
    """The finalized version's exact bytes, as a download (never inline)."""
    r = archivos.descargar(request.sesion, _parametro(request, "vid"), _almacen_actual())
    return RespuestaBinaria(r["contenido"], r["tipo_contenido"], {
        "Content-Disposition": disposicion(r["nombre_original"], r["tipo"]),
        "Cache-Control": _SIN_CACHE, "Content-Security-Policy": _AISLADO,
        "X-Archivo-Version-Id": r["version_id"], "X-Archivo-Sha256": r["sha256"],
    })


def metadatos_geometrias(request: Request) -> Respuesta:
    """POST {"ids": [...]}: descriptors only. Read-only despite the method."""
    if len(request.body) > METADATOS_MAX_BYTES:
        raise ApiError("La petición es demasiado grande.", 413,
                       {"code": "solicitud_demasiado_grande", "limite": METADATOS_MAX_BYTES})
    return archivos.metadatos_geometrias(request.sesion, _cuerpo(request).get("ids"))


def fragmento_geometria(request: Request) -> RespuestaBinaria:
    """GET ?desde=<offset>: one 512 KiB slice of the stored UTF-8 GeoJSON."""
    valor = request.q("desde", "0") or ""
    desde: Any = int(valor) if valor.isdigit() and len(valor) <= 9 else -1
    r = archivos.fragmento_geometria(request.sesion, _parametro(request, "gid"), desde)
    return RespuestaBinaria(r["contenido"], "application/octet-stream", {
        "Cache-Control": _SIN_CACHE, "Content-Security-Policy": _AISLADO,
        "X-Geometria-Id": r["geometria_id"], "X-Geometria-Desde": str(r["desde"]),
        "X-Geometria-Longitud": str(r["longitud"]), "X-Geometria-Bytes": str(r["bytes"]),
        "X-Geometria-Siguiente": "fin" if r["final"] else str(r["siguiente"]),
        "X-Geometria-Final": "1" if r["final"] else "0", "X-Geometria-Sha256": r["sha256"],
    })


# The exact registry entries requested from A for 3A (method, path, handler,
# capability). The 2B harness registers these temporarily; nothing here
# touches server/app.py.
RUTAS: tuple[tuple[str, str, Callable[[Request], Any], str], ...] = (
    ("POST", "/api/archivos/geometrias/metadatos", metadatos_geometrias, "archivos.ver"),
    ("GET", "/api/archivos/geometrias/:gid/contenido", fragmento_geometria, "archivos.ver"),
    ("GET", "/api/archivos/intentos/:iid", intento, "archivos.ver"),
    ("PUT", "/api/archivos/versiones/:vid/contenido", contenido, "archivos.subir"),
    ("POST", "/api/archivos/versiones/:vid/completar", completar, "archivos.subir"),
    ("POST", "/api/archivos/versiones/:vid/cancelar", cancelar, "archivos.subir"),
    ("POST", "/api/archivos/versiones/:vid/procesar", procesar, "archivos.subir"),
    ("GET", "/api/archivos/versiones/:vid/intentos", intentos, "archivos.ver"),
    ("GET", "/api/archivos/versiones/:vid/descarga", descarga, "archivos.ver"),
    ("POST", "/api/archivos/:aid/activar", activar, "archivos.subir"),
    ("POST", "/api/archivos/:aid/retirar", retirar, "archivos.retirar"),
    ("GET", "/api/archivos/:aid/historial", historial, "archivos.ver"),
    ("GET", "/api/archivos/:aid/versiones", versiones, "archivos.ver"),
    ("POST", "/api/inventario/terrenos/:id/archivos", iniciar, "archivos.subir"),
    ("GET", "/api/inventario/terrenos/:id/archivos", listar, "archivos.ver"),
)
# The one POST that only reads, for the read-only-mode allowlist.
POSTS_DE_LECTURA = frozenset({"/api/archivos/geometrias/metadatos"})

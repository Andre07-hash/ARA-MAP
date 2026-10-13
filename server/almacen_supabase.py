"""Supabase private Storage as an `Almacen` (free private pilot, packet F0-B).

Supabase is only the byte store here: no Supabase Auth, database, public
bucket, signed or public URL. The application authorizes every request before
this module is reached; the server credential bypasses the provider's row
policies, so nothing in this module is an authorization decision.

Provider calls, all through the official `storage3` SDK (imported lazily, so
the local application starts without it):

    upload(path, file, {"upsert": ...})   staging replacement / create-only final
    info(path)                            size of one object
    remove([path])                        exact-key deletion
    list(folder, {"limit", "offset"})     lazy, paginated listing

Reads are the one exception. The SDK's `download` returns the whole body as
one `bytes` with no bound, so `leer` and `copiar` stream the same documented
endpoint the SDK uses (GET /object/<bucket>/<key>) on the SDK client's own
HTTP session and stop at the caller's limit.

How the contract is met:

- Every incoming or outgoing object is first written whole to an anonymous
  temporary file (disposable scratch, never authoritative), so limits, chunk
  validation and input failures are settled before anything is published and
  a reader never sees provider bytes that were not counted against its limit.
- `guardar_temporal` publishes with upsert: the provider replaces the object
  as a whole. `copiar` snapshots the staging object and uploads it with
  upsert=false: the provider refuses an existing key, which is the only
  collision check (no HEAD-then-write).
- A write whose answer was lost (transport failure, 5xx) raises
  ResultadoInciertoError: the object may exist. It is never reported as a
  confirmed failure.

Not established by this module's tests, which use fakes of the provider: real
duplicate-upload behaviour and error bodies, replacement atomicity and
read-after-overwrite freshness, 20/25 MiB transfers through the host, quota
and paused-project answers. Those belong to the hosted gate.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import suppress
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from .almacen import (
    BLOQUE_LECTURA,
    FINAL,
    TEMPORAL,
    Almacen,
    AlmacenError,
    AlmacenNoConfiguradoError,
    Bloque,
    ColisionError,
    FalloAlmacenError,
    Lectura,
    LimiteExcedidoError,
    Metadato,
    ObjetoAusenteError,
    ResultadoInciertoError,
    _bloques_validos,
    _como_bytes,
    _partes_de_prefijo,
    _validar_limite,
    _validar_tamano_bloque,
    partes_de_clave,
)

ENV_URL = "ARA_MAP_ARCHIVOS_SUPABASE_URL"
ENV_KEY = "ARA_MAP_ARCHIVOS_SUPABASE_KEY"
ENV_BUCKET = "ARA_MAP_ARCHIVOS_SUPABASE_BUCKET"

# The SDK release this adapter was written and tested against.
SDK_PROBADO = "storage3==2.32.0"

_RUTA_API = "/storage/v1"
_PAGINA = 100
_SEGMENTO = re.compile(r"[0-9a-z][0-9a-z_-]{0,99}")
_BUCKET = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}")
_LOCALES = {"localhost", "127.0.0.1", "::1"}
_CUERPO_ERROR_MAX = 8 * 1024
# Seconds for each connect/read/write/pool step, not for a whole transfer.
# ponytail: no total deadline per call; add one if a stalled provider is seen
# holding a completion past its 180 s lease.
_ESPERA = 60.0

_registro = logging.getLogger(__name__)

FabricaAlmacen = Callable[[], Almacen]


# --------------------------------------------------------------------- errors

def _entero(valor: object) -> int | None:
    try:
        return int(str(valor))
    except ValueError:
        return None


def _es_respuesta_de_api(exc: BaseException) -> bool:
    """True for the SDK's StorageApiError (the provider answered with an error).

    Recognized by shape, not by class, so that classifying an error never
    needs the SDK imported. Anything else is a transport failure.
    """
    return hasattr(exc, "status") and hasattr(exc, "code")


def _etiqueta(status: object, codigo: object) -> str:
    """A log-safe "status/code" pair: no message, key, URL or credential."""
    limpio = re.sub(r"[^0-9A-Za-z_ -]", "", str(codigo))[:40]
    return f"{_entero(status) or 0}/{limpio}"


def _error_de_api(status: object, codigo: object, mensaje: object) -> AlmacenError:
    """The storage error for one provider answer (status and code as the body gave them)."""
    numero = _entero(status) or 0
    etiqueta = _etiqueta(status, codigo)
    # A missing bucket is also a 404; only a missing OBJECT is an absent object.
    if (numero == 404 and str(codigo) in ("not_found", "NoSuchKey")
            and "bucket" not in str(mensaje).lower()):
        return ObjetoAusenteError()
    if numero == 409 or str(codigo) == "Duplicate":
        return ColisionError()
    return FalloAlmacenError(reintentar=numero in (408, 429) or numero >= 500,
                             proveedor=etiqueta)


def _traducir(exc: BaseException, *, escritura: bool) -> AlmacenError:
    """Map a failure of one provider call. `escritura`: the call sends an object."""
    if isinstance(exc, AlmacenError):
        return exc
    if not _es_respuesta_de_api(exc):
        if escritura:       # sent, answer lost: it may have been stored
            return ResultadoInciertoError(proveedor="transporte")
        return FalloAlmacenError(proveedor="transporte")
    error = _error_de_api(getattr(exc, "status", None), getattr(exc, "code", None),
                          getattr(exc, "message", ""))
    if (escritura and isinstance(error, FalloAlmacenError)
            and (_entero(getattr(exc, "status", None)) or 0) >= 500):
        return ResultadoInciertoError(proveedor=error.proveedor)    # e.g. a gateway timeout
    return error


# ------------------------------------------------------------------- reading

def _escribir_todo(archivo: Any, datos: bytes) -> None:
    vista = memoryview(datos)
    while vista:
        vista = vista[archivo.write(vista):]


class _LecturaTemporal(Lectura):
    """A fully downloaded, already bounded object served from scratch space."""

    def __init__(self, archivo: Any, tamano: int, bloque: int) -> None:
        self._archivo: Any = archivo
        self.tamano = tamano
        self._bloque = bloque

    def __next__(self) -> bytes:
        if self._archivo is None:
            raise StopIteration
        datos: bytes = self._archivo.read(self._bloque)
        if not datos:
            self.close()
            raise StopIteration
        return datos

    def close(self) -> None:
        archivo, self._archivo = self._archivo, None
        if archivo is not None:
            archivo.close()

    @property
    def cerrada(self) -> bool:
        return self._archivo is None

    def __del__(self) -> None:
        self.close()


# --------------------------------------------------------------------- store

class AlmacenSupabase:
    """One private bucket. `cliente` is a storage3 SyncStorageClient (or its shape)."""

    def __init__(self, cliente: Any, bucket: str, url_api: str,
                 cabeceras: Mapping[str, str]) -> None:
        self._cliente = cliente
        self._bucket = cliente.from_(bucket)        # no provider call
        self._url_objetos = f"{url_api.rstrip('/')}/object/{bucket}/"
        self._cabeceras = dict(cabeceras)

    def close(self) -> None:
        sesion = getattr(self._cliente, "session", None)
        cerrar = getattr(sesion, "close", None)
        if callable(cerrar):
            cerrar()

    # -- transfers through scratch space

    def _descargar(self, clave: str, limite: int) -> tuple[Any, int]:
        """The whole object in an anonymous temporary file, or an error.

        Nothing is returned unless the complete body fit in `limite`, whatever
        the provider's metadata claims.
        """
        archivo = tempfile.TemporaryFile(buffering=0)   # noqa: SIM115 - handed to the caller
        try:
            cabeceras = {**self._cabeceras, "Cache-Control": "no-cache",
                         "Accept-Encoding": "identity"}
            with self._cliente.session.stream("GET", self._url_objetos + clave,
                                              headers=cabeceras) as respuesta:
                if respuesta.status_code != 200:
                    raise self._error_de_respuesta(respuesta)
                declarado = _entero(respuesta.headers.get("content-length"))
                if declarado is not None and declarado > limite:
                    raise LimiteExcedidoError(limite)
                total = 0
                for datos in respuesta.iter_bytes(BLOQUE_LECTURA):
                    total += len(datos)
                    if total > limite:
                        raise LimiteExcedidoError(limite)
                    _escribir_todo(archivo, datos)
                if declarado is not None and total != declarado:
                    raise FalloAlmacenError("El archivo llegó incompleto.")
            archivo.seek(0)
            return archivo, total
        except AlmacenError as exc:
            archivo.close()
            _registrar("leer", exc)
            raise
        except BaseException as exc:
            archivo.close()
            if not isinstance(exc, Exception):
                raise
            error = _traducir(exc, escritura=False)
            _registrar("leer", error)
            raise error from exc

    @staticmethod
    def _error_de_respuesta(respuesta: Any) -> AlmacenError:
        """The error for a non-200 streamed answer (same body the SDK parses)."""
        status: object = respuesta.status_code
        codigo: object = "InternalError"
        mensaje: object = ""
        with suppress(Exception):
            cuerpo = b""
            for datos in respuesta.iter_bytes(_CUERPO_ERROR_MAX):
                cuerpo += datos
                if len(cuerpo) >= _CUERPO_ERROR_MAX:
                    break
            leido = json.loads(cuerpo[:_CUERPO_ERROR_MAX])
            status, codigo = leido["statusCode"], leido["error"]
            mensaje = leido.get("message", "")
        return _error_de_api(status, codigo, mensaje)

    def _subir(self, clave: str, archivo: Any, *, reemplazar: bool) -> None:
        archivo.seek(0)
        try:
            self._bucket.upload(clave, archivo, {
                "content-type": "application/octet-stream",
                "cache-control": "0",
                "upsert": "true" if reemplazar else "false",
            })
        except AlmacenError:
            raise
        except Exception as exc:
            error = _traducir(exc, escritura=True)
            if reemplazar and isinstance(error, ColisionError):     # upsert never collides
                error = FalloAlmacenError(reintentar=False, proveedor="409/Duplicate")
            _registrar("subir", error)
            raise error from exc

    # -- operations

    def guardar_temporal(self, clave: str, bloques: Iterable[Bloque], limite: int) -> int:
        partes_de_clave(clave, TEMPORAL)
        _validar_limite(limite)
        bloques = _bloques_validos(bloques)
        with tempfile.TemporaryFile(buffering=0) as archivo:
            total = 0
            for bloque in bloques:
                datos = _como_bytes(bloque)
                total += len(datos)
                if total > limite:
                    raise LimiteExcedidoError(limite)
                _escribir_todo(archivo, datos)
            self._subir(clave, archivo, reemplazar=True)
        return total

    def copiar(self, origen: str, destino: str, limite: int) -> int:
        partes_de_clave(origen, TEMPORAL)
        partes_de_clave(destino, FINAL)
        _validar_limite(limite)
        archivo, total = self._descargar(origen, limite)
        with archivo:
            self._subir(destino, archivo, reemplazar=False)
        return total

    def leer(self, clave: str, limite: int, bloque: int = BLOQUE_LECTURA) -> Lectura:
        partes_de_clave(clave)
        _validar_limite(limite)
        _validar_tamano_bloque(bloque)
        archivo, total = self._descargar(clave, limite)
        return _LecturaTemporal(archivo, total, bloque)

    def tamano_de(self, clave: str) -> int | None:
        partes_de_clave(clave)
        try:
            datos = self._bucket.info(clave)
        except Exception as exc:
            error = _traducir(exc, escritura=False)
            if isinstance(error, ObjetoAusenteError):
                return None
            _registrar("tamano_de", error)
            raise error from exc
        tamano = _tamano_en(datos)
        if tamano is None:
            raise FalloAlmacenError(reintentar=False, proveedor="info/sin-tamano")
        return tamano

    def borrar(self, clave: str) -> bool:
        partes_de_clave(clave)
        try:
            borrados = self._bucket.remove([clave])
        except Exception as exc:
            error = _traducir(exc, escritura=False)
            _registrar("borrar", error)
            raise error from exc
        return bool(borrados)

    def listar(self, prefijo: str) -> Iterator[Metadato]:
        partes = _partes_de_prefijo(prefijo)
        return self._listar(partes)

    def _listar(self, partes: tuple[str, ...]) -> Iterator[Metadato]:
        carpeta = "/".join(partes)
        for entrada in self._paginas(carpeta):
            nombre = entrada.get("name")
            if not isinstance(nombre, str) or not _SEGMENTO.fullmatch(nombre):
                continue                        # nothing this module wrote
            es_objeto = entrada.get("id") is not None
            if partes == (FINAL,):
                if not es_objeto:               # a folder: one version's nonces
                    yield from self._listar((FINAL, nombre))
                continue
            tamano = _tamano_en(entrada)
            if es_objeto and tamano is not None:
                yield Metadato(f"{carpeta}/{nombre}", tamano, _epoca(entrada))

    def _paginas(self, carpeta: str) -> Iterator[dict[str, Any]]:
        # ponytail: offset pagination can skip or repeat an entry when the
        # folder changes mid-listing; fine for cleanup checks and inventory
        # of a quiet store, not a consistent snapshot.
        desde = 0
        while True:
            try:
                pagina = self._bucket.list(carpeta, {"limit": _PAGINA, "offset": desde})
            except Exception as exc:
                error = _traducir(exc, escritura=False)
                _registrar("listar", error)
                raise error from exc
            yield from (e for e in pagina if isinstance(e, dict))
            if len(pagina) < _PAGINA:
                return
            desde += len(pagina)


def _tamano_en(datos: object) -> int | None:
    """The object size from an `info` answer or a `list` entry."""
    if not isinstance(datos, dict):
        return None
    metadatos = datos.get("metadata")
    for origen in (datos, metadatos if isinstance(metadatos, dict) else {}):
        for campo in ("size", "contentLength"):
            valor = origen.get(campo)
            if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0:
                return valor
    return None


def _epoca(entrada: dict[str, Any]) -> float:
    for campo in ("updated_at", "created_at", "last_modified"):
        valor = entrada.get(campo)
        if isinstance(valor, str):
            with suppress(ValueError):
                return datetime.fromisoformat(valor.replace("Z", "+00:00")).timestamp()
    return 0.0


def _registrar(operacion: str, error: AlmacenError) -> None:
    """One sanitized line per provider failure: operation, class and status/code."""
    if isinstance(error, FalloAlmacenError):
        _registro.warning("almacen supabase: %s falló (%s, proveedor=%s, reintentar=%s)",
                          operacion, error.codigo, error.proveedor, error.reintentar)


# ------------------------------------------------------------------- factory

def _url_de_api(url: str) -> str | None:
    """The Storage API base for a project URL, or None when it is not acceptable."""
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        return None
    if partes.username or partes.password or partes.query or partes.fragment:
        return None
    if not partes.hostname or puerto == 0:
        return None
    if partes.scheme != "https" and not (partes.scheme == "http"
                                         and partes.hostname in _LOCALES):
        return None             # the credential never travels in clear text
    ruta = partes.path.rstrip("/")
    if ruta not in ("", _RUTA_API):
        return None
    return f"{partes.scheme}://{partes.netloc}{_RUTA_API}"


def fabrica_desde_entorno(environ: Mapping[str, str]) -> FabricaAlmacen | None:
    """A factory for the configured Supabase store, or None when not configured.

    Pure: reads the three settings and validates their shape. No import of
    the SDK, no connection and no provider call happen here; they happen on
    the factory's first call. Incomplete or malformed settings also give None
    (the application then answers its safe "store not configured" 503) and a
    warning naming the variables, never their values.
    """
    url = (environ.get(ENV_URL) or "").strip()
    clave = (environ.get(ENV_KEY) or "").strip()
    bucket = (environ.get(ENV_BUCKET) or "").strip()
    if not (url or clave or bucket):
        return None
    url_api = _url_de_api(url) if url else None
    malas = [nombre for nombre, ok in (
        (ENV_URL, url_api is not None),
        (ENV_KEY, bool(clave) and clave.isascii() and not any(c.isspace() for c in clave)),
        (ENV_BUCKET, bool(_BUCKET.fullmatch(bucket))),
    ) if not ok]
    if malas or url_api is None:
        _registro.warning("almacen supabase: configuración incompleta o inválida en %s",
                          ", ".join(malas))
        return None
    base = url_api
    return lambda: _construir(base, clave, bucket)


def _construir(url_api: str, clave: str, bucket: str, transporte: Any = None) -> AlmacenSupabase:
    """Build the store. `transporte` is a test seam (an httpx transport)."""
    try:
        storage3 = importlib.import_module("storage3")
        httpx = importlib.import_module("httpx")
    except ImportError as exc:
        raise AlmacenNoConfiguradoError() from exc
    cabeceras = {"apiKey": clave, "Authorization": f"Bearer {clave}"}
    # Our own session instead of the SDK default: redirects are not followed,
    # so the credential headers are never replayed to another origin.
    sesion = httpx.Client(timeout=_ESPERA, follow_redirects=False, transport=transporte,
                          trust_env=False)
    try:
        cliente = storage3.SyncStorageClient(url_api + "/", cabeceras, http_client=sesion)
        return AlmacenSupabase(cliente, bucket, url_api, cabeceras)
    except Exception as exc:
        sesion.close()
        raise AlmacenNoConfiguradoError() from exc


__all__ = ["ENV_BUCKET", "ENV_KEY", "ENV_URL", "SDK_PROBADO", "AlmacenSupabase",
           "fabrica_desde_entorno"]

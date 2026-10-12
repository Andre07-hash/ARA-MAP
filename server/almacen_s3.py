"""Private S3 byte store for the hosted portal (hosted transfer contract M1).

The same `Almacen` contract as server.almacen, over one private bucket:

- guardar_temporal: one whole-object PutObject (an atomic replacement);
- copiar / componer: pin each staging source (HEAD: size, version, ETag), read
  exactly those bytes, then ONE create-only PutObject (If-None-Match: *) with
  the SHA-256 checksum of what was read. A staging write that lands later can
  never reach the composed object;
- leer: one bounded streaming GET; tamano_de: HEAD; borrar: exact-key DELETE;
  listar: ListObjectsV2 pages.

Importing this module never imports the SDK and never touches the network:
local startup keeps working without boto3. The SDK is imported when a store is
built, and credentials are obtained only at the first request that needs them
(after the application has authorized the resource, outside database locks).

Credentials. The hosted entry (Team A) puts the request's Vercel OIDC token
into a context variable with fijar_token_oidc and resets it with
restablecer_token_oidc. When the SDK needs credentials it calls
STS AssumeRoleWithWebIdentity (unsigned) with the CURRENT request's token and
caches the temporary credentials in botocore's refreshable credentials, which
refresh 15 minutes before expiry (mandatory from 10 minutes) under their own
lock. The role is the project/environment identity, never an end user's, so a
warm instance may serve every request with it. On an expired-credentials
answer the client is rebuilt once (one fresh exchange) and a safe operation is
retried once.

Configuration (all three required in the cloud):
    ARA_MAP_ARCHIVOS_S3_BUCKET, ARA_MAP_ARCHIVOS_S3_REGION, ARA_MAP_ARCHIVOS_S3_ROLE_ARN
ARA_MAP_ARCHIVOS_S3_ENDPOINT is for isolated local tests only: a loopback
http endpoint, refused whenever the process runs on Vercel.

Errors never carry credentials, tokens, bucket names, keys or provider
messages: only the server.almacen classes, and logs record condition classes.
"""

from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import logging
import re
import threading
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
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
    _origenes_validos,
    _partes_de_prefijo,
    _validar_limite,
    _validar_tamano_bloque,
    partes_de_clave,
)

VARIABLE_BUCKET = "ARA_MAP_ARCHIVOS_S3_BUCKET"
VARIABLE_REGION = "ARA_MAP_ARCHIVOS_S3_REGION"
VARIABLE_ROL = "ARA_MAP_ARCHIVOS_S3_ROLE_ARN"
VARIABLE_ENDPOINT = "ARA_MAP_ARCHIVOS_S3_ENDPOINT"

DURACION_CREDENCIALES = 3600            # seconds asked of STS
_LOG = logging.getLogger("ara_map.archivos.s3")

FabricaAlmacen = Callable[[], Almacen]


# ------------------------------------------------------------- OIDC handoff

_TOKEN_OIDC: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ara_map_token_oidc", default=None)


def fijar_token_oidc(valor: str | None) -> contextvars.Token[str | None]:
    """Set the current request's OIDC token; returns the mark to reset it with.

    Called by the hosted entry for every request, before dispatch. An empty or
    non-string value counts as no token.
    """
    return _TOKEN_OIDC.set(valor if isinstance(valor, str) and valor.strip() else None)


def restablecer_token_oidc(marca: contextvars.Token[str | None]) -> None:
    """Reset what fijar_token_oidc set (call it in `finally`)."""
    _TOKEN_OIDC.reset(marca)


# ------------------------------------------------------------- configuration

_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_REGION = re.compile(r"^[a-z]{2}(-gov)?-[a-z]+-[0-9]$")
_ROL = re.compile(r"^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]{1,512}$")
_HOSTS_DE_PRUEBA = ("127.0.0.1", "localhost", "::1")


@dataclass(frozen=True)
class Configuracion:
    bucket: str
    region: str
    rol: str | None
    endpoint: str | None        # isolated local tests only


def leer_configuracion(environ: Mapping[str, str]) -> Configuracion | None:
    """The S3 settings in `environ`, None if none is set at all.

    Pure: no SDK, no network. Raises AlmacenNoConfiguradoError (without the
    values) when the settings are incomplete or invalid.
    """
    bucket = (environ.get(VARIABLE_BUCKET) or "").strip()
    region = (environ.get(VARIABLE_REGION) or "").strip()
    rol = (environ.get(VARIABLE_ROL) or "").strip() or None
    endpoint = (environ.get(VARIABLE_ENDPOINT) or "").strip() or None
    if not (bucket or region or rol or endpoint):
        return None
    problemas = []
    if not _BUCKET.fullmatch(bucket) or ".." in bucket:
        problemas.append(VARIABLE_BUCKET)
    if not _REGION.fullmatch(region):
        problemas.append(VARIABLE_REGION)
    if endpoint is not None:
        partes = urlsplit(endpoint)
        if (environ.get("VERCEL") or partes.scheme != "http" or partes.hostname not in _HOSTS_DE_PRUEBA
                or partes.path not in ("", "/") or partes.query or partes.username):
            problemas.append(VARIABLE_ENDPOINT)
    if rol is None and endpoint is None:
        problemas.append(VARIABLE_ROL)
    if rol is not None and not _ROL.fullmatch(rol):
        problemas.append(VARIABLE_ROL)
    if problemas:
        _LOG.error("Configuración de archivos S3 inválida: %s", ", ".join(problemas))
        raise AlmacenNoConfiguradoError()
    return Configuracion(bucket, region, rol, endpoint)


def fabrica_desde_entorno(environ: Mapping[str, str]) -> FabricaAlmacen | None:
    """The store factory for the hosted entry, or None when S3 is not configured.

    Building the factory is pure. Invalid settings give a factory that raises
    AlmacenNoConfiguradoError when (and only when) an authorized operation
    needs the store, so the entry point itself always imports and starts.
    """
    try:
        configuracion = leer_configuracion(environ)
    except AlmacenNoConfiguradoError:
        def no_configurada() -> Almacen:
            raise AlmacenNoConfiguradoError()
        return no_configurada
    if configuracion is None:
        return None
    return lambda: AlmacenS3(configuracion)


# ---------------------------------------------------------------- the store

_AUSENTE = {"NoSuchKey", "NotFound", "404", "NoSuchVersion"}
_COLISION = {"PreconditionFailed", "412"}
_CONFLICTO = {"ConditionalRequestConflict", "409"}
_DENEGADO = {"AccessDenied", "403", "AllAccessDisabled", "InvalidAccessKeyId",
             "SignatureDoesNotMatch", "AccountProblem", "InvalidObjectState", "NoSuchBucket"}
_CADUCADO = {"ExpiredToken", "ExpiredTokenException", "RequestExpired", "InvalidToken",
             "TokenRefreshRequired"}


class _CaducadasError(Exception):
    """Internal: the provider said the temporary credentials expired."""


_TRANSITORIO = {"SlowDown", "Throttling", "ThrottlingException", "RequestLimitExceeded",
                "ServiceUnavailable", "InternalError", "InternalFailure", "RequestTimeout",
                "RequestTimeoutException", "IDPCommunicationError"}


def _codigo(exc: Exception) -> tuple[str, int]:
    """The provider's error code (or its HTTP status as text) and the HTTP status."""
    respuesta = getattr(exc, "response", None) or {}
    error = respuesta.get("Error") or {}
    try:
        estado = int((respuesta.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
    except (TypeError, ValueError):
        estado = 0
    return str(error.get("Code") or estado or ""), estado


class AlmacenS3:
    """The `Almacen` contract on one private bucket. See the module docstring."""

    def __init__(self, configuracion: Configuracion, *,
                 _sts: Callable[[], Any] | None = None) -> None:
        try:
            import boto3  # noqa: F401  (lazy: never imported for local startup)
            import botocore.config
            import botocore.credentials
            import botocore.exceptions
            import botocore.session
        except ImportError:
            _LOG.error("SDK de S3 ausente en este entorno.")
            raise AlmacenNoConfiguradoError() from None
        self._config = configuracion
        self._bc = botocore
        self._crear_sts = _sts
        self._candado = threading.Lock()
        self._generacion = 0
        self._cliente = self._nuevo_cliente()

    # -- SDK plumbing (no network here)

    def _nuevo_cliente(self) -> Any:
        botocore = self._bc
        sesion = botocore.session.get_session()
        if self._config.rol is not None:
            proveedor = _ProveedorOIDC(self._config, self._crear_sts or self._sts_por_defecto,
                                       botocore)
            sesion.get_component("credential_provider").insert_before("env", proveedor)
        ajustes = botocore.config.Config(
            region_name=self._config.region, retries={"mode": "standard", "max_attempts": 3},
            connect_timeout=5, read_timeout=30, s3={"addressing_style": "path"}
            if self._config.endpoint else None)
        return sesion.create_client("s3", endpoint_url=self._config.endpoint, config=ajustes)

    def _sts_por_defecto(self) -> Any:
        botocore = self._bc
        endpoint = self._config.endpoint or f"https://sts.{self._config.region}.amazonaws.com"
        return botocore.session.get_session().create_client(
            "sts", region_name=self._config.region, endpoint_url=endpoint,
            config=botocore.config.Config(signature_version=botocore.UNSIGNED,
                                          retries={"mode": "standard", "max_attempts": 3},
                                          connect_timeout=5, read_timeout=15))

    def _renovar(self, vista: int) -> None:
        """Rebuild the client (a fresh credential exchange) once per generation."""
        with self._candado:
            if self._generacion == vista:
                self._cliente = self._nuevo_cliente()
                self._generacion += 1

    def _llamar(self, operacion: str, segura: bool, escritura: bool, **argumentos: Any) -> Any:
        """One SDK call with the error mapping; one refresh-and-retry when safe."""
        for intento in (1, 2):
            with self._candado:
                cliente, generacion = self._cliente, self._generacion
            metodo: Callable[..., Any] = getattr(cliente, operacion)
            bucket = self._config.bucket
            try:
                return self._traducir(partial(metodo, Bucket=bucket, **argumentos), escritura)
            except _CaducadasError:
                if intento == 1 and segura:
                    self._renovar(generacion)
                    continue
                if intento == 1:
                    self._renovar(generacion)
                # The request was refused, so nothing was written.
                raise FalloAlmacenError(reintentar=True) from None
        raise FalloAlmacenError(reintentar=True)    # pragma: no cover

    def _traducir(self, llamada: Callable[[], Any], escritura: bool) -> Any:
        exc_bc = self._bc.exceptions
        try:
            return llamada()
        except AlmacenError:
            raise                                   # from the credential provider
        except exc_bc.ClientError as exc:
            codigo, estado = _codigo(exc)
            if codigo in _AUSENTE:
                raise ObjetoAusenteError() from None
            if codigo in _COLISION:
                raise ColisionError() from None
            if codigo in _CADUCADO:
                raise _CaducadasError() from None
            if codigo in _DENEGADO:
                _LOG.error("Almacén S3: acceso denegado (%s).", codigo)
                raise FalloAlmacenError(reintentar=False) from None
            _LOG.warning("Almacén S3: error del proveedor (%s).", codigo or "desconocido")
            transitorio = codigo in _TRANSITORIO or estado >= 500 or estado == 0
            if escritura and (codigo in _CONFLICTO or transitorio):
                raise ResultadoInciertoError() from None     # it may have been applied
            raise FalloAlmacenError(reintentar=transitorio) from None
        except (exc_bc.NoCredentialsError, exc_bc.PartialCredentialsError):
            _LOG.error("Almacén S3: sin credenciales.")
            raise AlmacenNoConfiguradoError() from None
        except (exc_bc.ConnectTimeoutError, exc_bc.EndpointConnectionError):
            _LOG.warning("Almacén S3: no se pudo conectar.")
            raise FalloAlmacenError(reintentar=True) from None   # never sent: not uncertain
        except (exc_bc.BotoCoreError, OSError) as exc:
            _LOG.warning("Almacén S3: fallo de transporte (%s).", type(exc).__name__)
            if escritura:
                raise ResultadoInciertoError() from None
            raise FalloAlmacenError(reintentar=True) from None

    # -- operations

    def guardar_temporal(self, clave: str, bloques: Iterable[Bloque], limite: int) -> int:
        partes_de_clave(clave, TEMPORAL)
        _validar_limite(limite)
        bloques = _bloques_validos(bloques)
        datos = bytearray()
        for bloque in bloques:
            trozo = _como_bytes(bloque)
            if len(datos) + len(trozo) > limite:
                raise LimiteExcedidoError(limite)
            datos.extend(trozo)
        # A whole-object replacement of staging: safe to retry once.
        self._llamar("put_object", segura=True, escritura=True, Key=clave, Body=bytes(datos),
                     ContentType="application/octet-stream")
        return len(datos)

    def copiar(self, origen: str, destino: str, limite: int) -> int:
        partes_de_clave(origen, TEMPORAL)
        partes_de_clave(destino, FINAL)
        _validar_limite(limite)
        try:
            return self._componer((origen,), destino, limite)
        except ObjetoAusenteError:
            raise ObjetoAusenteError() from None

    def componer(self, origenes: Sequence[str], destino: str, limite: int) -> int:
        claves = _origenes_validos(origenes)
        partes_de_clave(destino, FINAL)
        _validar_limite(limite)
        return self._componer(claves, destino, limite)

    def _componer(self, claves: Sequence[str], destino: str, limite: int) -> int:
        fijadas: list[tuple[str, int, dict[str, str]]] = []
        ausentes: list[str] = []
        for clave in claves:
            try:
                cabecera = self._llamar("head_object", segura=True, escritura=False, Key=clave)
            except ObjetoAusenteError:
                ausentes.append(clave)
                continue
            pin = {"VersionId": cabecera["VersionId"]} if cabecera.get("VersionId") \
                not in (None, "null") else {"IfMatch": cabecera["ETag"]}
            fijadas.append((clave, int(cabecera["ContentLength"]), pin))
        if ausentes:
            raise ObjetoAusenteError(claves=ausentes)
        total = sum(t for _c, t, _p in fijadas)
        if total > limite:
            raise LimiteExcedidoError(limite)
        datos = bytearray()
        for clave, tamano, pin in fijadas:
            try:
                respuesta = self._llamar("get_object", segura=True, escritura=False, Key=clave, **pin)
            except (ObjetoAusenteError, ColisionError):
                # Replaced or removed since it was pinned: nothing was written.
                raise FalloAlmacenError(reintentar=True) from None
            leido = self._leer_cuerpo(respuesta, tamano)
            if len(leido) != tamano:
                raise FalloAlmacenError(reintentar=True)
            datos.extend(leido)
        suma = base64.b64encode(hashlib.sha256(datos).digest()).decode("ascii")
        # Create-only. Never retried by this adapter after an expired-credential
        # refusal; a lost reply is ResultadoInciertoError, a winner is ColisionError.
        self._llamar("put_object", segura=False, escritura=True, Key=destino, Body=bytes(datos),
                     IfNoneMatch="*", ChecksumSHA256=suma, ContentType="application/octet-stream")
        return total

    def _leer_cuerpo(self, respuesta: Mapping[str, Any], maximo: int) -> bytes:
        cuerpo = respuesta["Body"]
        try:
            partes = []
            total = 0
            while True:
                trozo = self._traducir(lambda: cuerpo.read(BLOQUE_LECTURA), escritura=False)
                if not trozo:
                    break
                total += len(trozo)
                if total > maximo:
                    raise FalloAlmacenError(reintentar=True)
                partes.append(trozo)
            return b"".join(partes)
        finally:
            cuerpo.close()

    def leer(self, clave: str, limite: int, bloque: int = BLOQUE_LECTURA) -> Lectura:
        partes_de_clave(clave)
        _validar_limite(limite)
        _validar_tamano_bloque(bloque)
        respuesta = self._llamar("get_object", segura=True, escritura=False, Key=clave)
        tamano = int(respuesta["ContentLength"])
        if tamano > limite:
            respuesta["Body"].close()
            raise LimiteExcedidoError(limite)
        return _LecturaS3(respuesta["Body"], tamano, limite, bloque, self._traducir)

    def tamano_de(self, clave: str) -> int | None:
        partes_de_clave(clave)
        try:
            cabecera = self._llamar("head_object", segura=True, escritura=False, Key=clave)
        except ObjetoAusenteError:
            return None
        return int(cabecera["ContentLength"])

    def borrar(self, clave: str) -> bool:
        partes_de_clave(clave)
        # S3 does not say whether a DELETE removed anything: ask first. With
        # versioning on, the delete only hides the bytes behind a marker.
        if self.tamano_de(clave) is None:
            return False
        self._llamar("delete_object", segura=True, escritura=True, Key=clave)
        return True

    def listar(self, prefijo: str) -> Iterator[Metadato]:
        partes = _partes_de_prefijo(prefijo)
        return self._listar(prefijo, len(partes))

    def _listar(self, prefijo: str, profundidad: int) -> Iterator[Metadato]:
        segmentos = 2 if prefijo.startswith(TEMPORAL + "/") else 3
        continuacion: str | None = None
        while True:
            extra = {"ContinuationToken": continuacion} if continuacion else {}
            pagina = self._llamar("list_objects_v2", segura=True, escritura=False,
                                  Prefix=prefijo, MaxKeys=1000, **extra)
            for objeto in pagina.get("Contents") or []:
                clave = str(objeto["Key"])
                try:
                    if len(partes_de_clave(clave)) != segmentos:
                        continue
                except AlmacenError:
                    continue                    # anything foreign under the prefix
                yield Metadato(clave, int(objeto["Size"]), objeto["LastModified"].timestamp())
            if not pagina.get("IsTruncated"):
                return
            continuacion = pagina.get("NextContinuationToken")


class _LecturaS3(Lectura):
    def __init__(self, cuerpo: Any, tamano: int, limite: int, bloque: int,
                 traducir: Callable[[Callable[[], Any], bool], Any]) -> None:
        self._cuerpo: Any | None = cuerpo
        self.tamano = tamano
        self._limite = limite
        self._bloque = bloque
        self._leidos = 0
        self._traducir = traducir

    def __next__(self) -> bytes:
        cuerpo = self._cuerpo
        if cuerpo is None:
            raise StopIteration
        try:
            trozo = self._traducir(lambda: cuerpo.read(self._bloque), False)
        except BaseException:
            self.close()
            raise
        if not trozo:
            completo = self._leidos == self.tamano
            self.close()
            if not completo:
                raise FalloAlmacenError(reintentar=True)
            raise StopIteration
        self._leidos += len(trozo)
        if self._leidos > min(self.tamano, self._limite):
            self.close()
            raise FalloAlmacenError(reintentar=True)
        return bytes(trozo)

    def close(self) -> None:
        cuerpo, self._cuerpo = self._cuerpo, None
        if cuerpo is not None:
            with contextlib.suppress(Exception):   # never mask the real error
                cuerpo.close()


# --------------------------------------------------------------- credentials

class _ProveedorOIDC:
    """A botocore credential provider: STS web identity with the request's token.

    It returns botocore DeferredRefreshableCredentials, so the first exchange
    happens on first use (never at construction) and later refreshes are
    serialized by botocore's own lock.
    """

    METHOD = "ara-map-oidc-sts"
    CANONICAL_NAME = "ara-map-oidc-sts"

    def __init__(self, configuracion: Configuracion, crear_sts: Callable[[], Any],
                 botocore: Any) -> None:
        self._config = configuracion
        self._crear_sts = crear_sts
        self._bc = botocore
        self._sts: Any | None = None
        self._candado = threading.Lock()

    def load(self) -> Any:
        return self._bc.credentials.DeferredRefreshableCredentials(
            refresh_using=self._obtener, method=self.METHOD)

    def _obtener(self) -> dict[str, Any]:
        token = _TOKEN_OIDC.get()
        if token is None:
            _LOG.error("Almacén S3: falta el token OIDC de la petición.")
            raise AlmacenNoConfiguradoError()
        with self._candado:
            if self._sts is None:
                self._sts = self._crear_sts()
            sts = self._sts
        exc_bc = self._bc.exceptions
        try:
            respuesta = sts.assume_role_with_web_identity(
                RoleArn=self._config.rol, RoleSessionName="ara-map-" + uuid.uuid4().hex[:16],
                WebIdentityToken=token, DurationSeconds=DURACION_CREDENCIALES)
        except exc_bc.ClientError as exc:
            codigo, estado = _codigo(exc)
            # An expired OIDC token is replaced by the next request's; outages pass.
            if codigo == "ExpiredTokenException" or codigo in _TRANSITORIO or estado >= 500:
                _LOG.warning("Almacén S3: STS no disponible (%s).", codigo or "desconocido")
                raise FalloAlmacenError(reintentar=True) from None
            # AccessDenied, InvalidIdentityToken, IDPRejectedClaim, ...: trust/role setup.
            _LOG.error("Almacén S3: STS denegó la identidad (%s).", codigo or "desconocido")
            raise FalloAlmacenError(reintentar=False) from None
        except (exc_bc.BotoCoreError, OSError) as exc:
            _LOG.warning("Almacén S3: STS inalcanzable (%s).", type(exc).__name__)
            raise FalloAlmacenError(reintentar=True) from None
        credenciales = respuesta["Credentials"]
        return {"access_key": credenciales["AccessKeyId"],
                "secret_key": credenciales["SecretAccessKey"],
                "token": credenciales["SessionToken"],
                "expiry_time": credenciales["Expiration"].isoformat()}

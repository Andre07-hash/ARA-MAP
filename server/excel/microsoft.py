"""Microsoft OneDrive provider: OAuth (authorization code + PKCE) and Graph.

Account types: the authority defaults to "common" (personal Microsoft
accounts and work/school accounts); the app registration's supported account
types must match ARA_MAP_MS_AUTHORITY. Scopes, all delegated:

  offline_access  a refresh token, so employees can refresh later without the
                  owner signing in again
  User.Read       /me: the connected account's id and display name
  Files.Read      the connecting account's own OneDrive: browse/search its
                  files, read metadata and download content

No write scope and no Files.Read.All: the first release reads a workbook
owned by the connecting account, chosen from that account's own drive. The
/shares (pasted link) API needs Files.ReadWrite and is not used. OpenID
scopes are not requested; identity comes from the authenticated Graph /me
response, never from an unvalidated ID token.

Endpoints are fixed (login.microsoftonline.com, graph.microsoft.com). The only
override is ARA_MAP_MS_TEST_HOST, accepted solely for a 127.0.0.1 address so
tests can run a local fake; it cannot point anywhere else.

Downloads: Graph answers /content with a redirect to a pre-authenticated URL.
It is followed manually, only to HTTPS Microsoft download hosts, without the
Graph bearer token, never stored, logged or returned.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import credenciales
from .proveedor import Metadatos, ProveedorError

SCOPES = "offline_access User.Read Files.Read"
AUTORIDADES = ("common", "consumers", "organizations")
TIMEOUT = 30
REDIRECCIONES = 3
PRESUPUESTO_REINTENTO = 10.0  # seconds of Retry-After we will wait in total
MAX_REINTENTOS = 3  # and at most this many retries, even with Retry-After: 0
EXCEL = (".xlsx", ".xlsm")
# Pre-authenticated download hosts, matched on whole DNS labels.
HOSTS_DESCARGA = ("files.1drv.com", "1drv.com", "sharepoint.com", "onedrive.live.com")
HOSTS_WEB = ("onedrive.live.com", "1drv.ms", "sharepoint.com")


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    redirect_uri: str
    autoridad: str
    login: str
    graph: str
    prueba: str | None  # "127.0.0.1:port" when testing against a local fake


def config() -> Config | None:
    client_id = os.environ.get("ARA_MAP_MS_CLIENT_ID", "").strip()
    secret = os.environ.get("ARA_MAP_MS_CLIENT_SECRET", "")
    redirect = os.environ.get("ARA_MAP_MS_REDIRECT_URI", "").strip()
    autoridad = os.environ.get("ARA_MAP_MS_AUTHORITY", "common").strip()
    if not (client_id and secret and redirect):
        return None
    if autoridad not in AUTORIDADES and not _es_guid(autoridad):
        return None
    prueba = os.environ.get("ARA_MAP_MS_TEST_HOST", "").strip() or None
    if prueba is not None:
        host = prueba.rsplit(":", 1)[0]
        if host != "127.0.0.1":
            return None  # never an arbitrary OAuth/Graph host
        base = f"http://{prueba}"
        return Config(client_id, secret, redirect, autoridad, f"{base}/login", f"{base}/graph/v1.0", prueba)
    if not redirect.startswith("https://"):
        return None
    return Config(client_id, secret, redirect, autoridad, "https://login.microsoftonline.com",
                  "https://graph.microsoft.com/v1.0", None)


def disponibilidad() -> dict[str, Any]:
    if config() is None:
        return {"disponible": False, "motivo": "La conexión con Microsoft no está configurada en este servidor."}
    ok, motivo = credenciales.disponible()
    return {"disponible": ok, "motivo": motivo}


def _es_guid(texto: str) -> bool:
    try:
        import uuid
        uuid.UUID(texto)
        return True
    except ValueError:
        return False


# -- OAuth -------------------------------------------------------------------

def pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(64)[:100]
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, reto


def url_autorizacion(cfg: Config, estado: str, reto: str) -> str:
    return f"{cfg.login}/{cfg.autoridad}/oauth2/v2.0/authorize?" + urllib.parse.urlencode({
        "client_id": cfg.client_id, "response_type": "code", "redirect_uri": cfg.redirect_uri,
        "response_mode": "query", "scope": SCOPES, "state": estado, "code_challenge": reto,
        "code_challenge_method": "S256", "prompt": "select_account"})


def canjear_codigo(cfg: Config, codigo: str, verificador: str) -> dict[str, Any]:
    return _token(cfg, {"grant_type": "authorization_code", "code": codigo, "code_verifier": verificador,
                        "redirect_uri": cfg.redirect_uri})


def renovar(cfg: Config, refresh_token: str) -> dict[str, Any]:
    return _token(cfg, {"grant_type": "refresh_token", "refresh_token": refresh_token})


def _token(cfg: Config, campos: Mapping[str, str]) -> dict[str, Any]:
    datos = urllib.parse.urlencode({"client_id": cfg.client_id, "client_secret": cfg.client_secret,
                                    "scope": SCOPES, **campos}).encode()
    status, cuerpo, _ = _pedir("POST", f"{cfg.login}/{cfg.autoridad}/oauth2/v2.0/token", datos,
                               {"Content-Type": "application/x-www-form-urlencoded"})
    respuesta = _json(cuerpo)
    if status == 200 and respuesta.get("access_token"):
        return respuesta
    if status in (400, 401) and respuesta.get("error") in ("invalid_grant", "interaction_required",
                                                           "consent_required", "invalid_client"):
        raise ProveedorError("reconectar", "Microsoft ya no acepta esta conexión; vuelve a conectar la cuenta.")
    raise ProveedorError("no_disponible", "Microsoft no respondió como se esperaba; inténtalo más tarde.",
                         reintentable=True)


# -- Graph ---------------------------------------------------------------------

class Graph:
    """Calls fixed Graph endpoints with one access token."""

    def __init__(self, cfg: Config, token: str) -> None:
        self.cfg = cfg
        self.token = token

    def get(self, ruta: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        url = self.cfg.graph + ruta + ("?" + urllib.parse.urlencode(params) if params else "")
        status, cuerpo, _ = _con_reintentos(lambda: _pedir("GET", url, None, self._auth()))
        _comprobar(status)
        return _json(cuerpo)

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def yo(self) -> dict[str, Any]:
        perfil = self.get("/me", {"$select": "id,displayName,userPrincipalName,mail"})
        unidad = self.get("/me/drive", {"$select": "id,driveType"})
        return {"id": perfil["id"], "nombre": perfil.get("displayName"),
                "correo": perfil.get("mail") or perfil.get("userPrincipalName"),
                "tipo": "personal" if unidad.get("driveType") == "personal" else "organizacion",
                "drive_id": unidad.get("id")}

    def listar(self, carpeta: str | None, buscar: str | None) -> list[dict[str, Any]]:
        campos = {"$select": "id,name,folder,file,size,lastModifiedDateTime,parentReference", "$top": "200"}
        if buscar:
            q = buscar.replace("'", "''")[:100]
            datos = self.get(f"/me/drive/root/search(q='{urllib.parse.quote(q)}')", campos)
        elif carpeta:
            datos = self.get(f"/me/drive/items/{urllib.parse.quote(carpeta, safe='')}/children", campos)
        else:
            datos = self.get("/me/drive/root/children", campos)
        items = []
        for it in datos.get("value", []):
            es_carpeta = "folder" in it
            if not es_carpeta and not str(it.get("name", "")).lower().endswith(EXCEL):
                continue
            items.append({"id": it["id"], "nombre": it.get("name"), "carpeta": es_carpeta,
                          "drive_id": (it.get("parentReference") or {}).get("driveId"),
                          "tamano": it.get("size"), "modificado_en": it.get("lastModifiedDateTime")})
        return items

    def metadatos(self, drive_id: str, item_id: str) -> Metadatos:
        it = self.get(f"/drives/{_seg(drive_id)}/items/{_seg(item_id)}",
                      {"$select": "id,name,eTag,cTag,size,lastModifiedDateTime,lastModifiedBy,webUrl,file"})
        if "file" not in it or not str(it.get("name", "")).lower().endswith(EXCEL):
            raise ProveedorError("no_encontrado", "El elemento ya no es un libro de Excel.")
        autor = ((it.get("lastModifiedBy") or {}).get("user") or {}).get("displayName")
        return Metadatos(str(it.get("name")), it.get("eTag"), it.get("cTag"), it.get("size"),
                         it.get("lastModifiedDateTime"), autor, url_web_segura(it.get("webUrl")))

    def descargar(self, drive_id: str, item_id: str, max_bytes: int) -> bytes:
        url = f"{self.cfg.graph}/drives/{_seg(drive_id)}/items/{_seg(item_id)}/content"
        status, cuerpo, cabeceras = _con_reintentos(lambda: _pedir("GET", url, None, self._auth(), max_bytes))
        for _ in range(REDIRECCIONES):
            if status not in (301, 302, 303, 307, 308):
                break
            destino = cabeceras.get("location", "")
            if not self._host_descarga_valido(destino):
                raise ProveedorError("no_disponible", "Microsoft redirigió la descarga a un destino no admitido.")
            # No Authorization header: the bearer token never leaves Graph.
            status, cuerpo, cabeceras = _con_reintentos(lambda d=destino: _pedir("GET", d, None, {}, max_bytes))
        _comprobar(status)
        if len(cuerpo) > max_bytes:
            raise ProveedorError("demasiado_grande", "El archivo es demasiado grande.")
        return cuerpo

    def _host_descarga_valido(self, url: str) -> bool:
        partes = urllib.parse.urlsplit(url)
        if self.cfg.prueba is not None:
            return partes.scheme == "http" and partes.netloc == self.cfg.prueba and partes.path.startswith("/descarga/")
        return partes.scheme == "https" and _host_en(partes.hostname or "", HOSTS_DESCARGA)


def url_web_segura(url: Any) -> str | None:
    """A link to open the workbook in Microsoft, only if it is plainly one."""
    if not isinstance(url, str):
        return None
    partes = urllib.parse.urlsplit(url)
    if partes.scheme == "https" and _host_en(partes.hostname or "", HOSTS_WEB):
        return url
    return None


def _host_en(host: str, permitidos: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == p or host.endswith("." + p) for p in permitidos)


def _seg(valor: str) -> str:
    return urllib.parse.quote(valor, safe="")


def _comprobar(status: int) -> None:
    if status in (200, 206):
        return
    if status == 401:
        raise ProveedorError("reconectar", "Microsoft rechazó la conexión; vuelve a conectar la cuenta.")
    if status == 403:
        raise ProveedorError("sin_permiso", "La cuenta conectada ya no tiene acceso a ese archivo.")
    if status in (404, 410):
        raise ProveedorError("no_encontrado", "El archivo ya no existe o se movió fuera del alcance de la cuenta.")
    raise ProveedorError("no_disponible", "Microsoft no está disponible en este momento; inténtalo más tarde.",
                         reintentable=True)


class _SinRedirigir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _pedir(metodo: str, url: str, datos: bytes | None, cabeceras: Mapping[str, str],
           max_bytes: int = 2 * 1024 * 1024) -> tuple[int, bytes, dict[str, str]]:
    """One HTTP exchange; redirects are returned, not followed. Errors never
    include the URL (it may be pre-authenticated) or any header."""
    pedido = urllib.request.Request(url, data=datos, method=metodo, headers=dict(cabeceras))
    abridor = urllib.request.build_opener(_SinRedirigir())
    try:
        with abridor.open(pedido, timeout=TIMEOUT) as r:
            return r.status, r.read(max_bytes + 1), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        with e:
            return e.code, e.read(max_bytes + 1), {k.lower(): v for k, v in e.headers.items()}
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProveedorError("no_disponible", "No se pudo comunicar con Microsoft; inténtalo más tarde.",
                             reintentable=True) from None


def _con_reintentos(hacer: Any) -> tuple[int, bytes, dict[str, str]]:
    """429/503 with Retry-After are retried within a small total budget and a
    bounded number of attempts."""
    gastado = 0.0
    for intento in range(MAX_REINTENTOS + 1):
        status, cuerpo, cabeceras = hacer()
        if status not in (429, 503) or intento == MAX_REINTENTOS:
            return status, cuerpo, cabeceras
        try:
            espera = max(0.0, min(float(cabeceras.get("retry-after", "2")), 5.0))
        except ValueError:
            espera = 2.0
        if gastado + espera > PRESUPUESTO_REINTENTO:
            return status, cuerpo, cabeceras
        time.sleep(espera)
        gastado += espera
    raise AssertionError("unreachable")


def _json(cuerpo: bytes) -> dict[str, Any]:
    try:
        datos = json.loads(cuerpo or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


# -- the provider ------------------------------------------------------------------

def graph_de_cuenta(cuenta_id: str) -> Graph:
    cfg = config()
    if cfg is None:
        raise ProveedorError("no_configurado", "La conexión con Microsoft no está configurada en este servidor.")
    ok, motivo = credenciales.disponible()
    if not ok:
        raise ProveedorError("no_configurado", motivo or "Conector deshabilitado.")
    token = credenciales.con_token_fresco(cuenta_id, lambda rt: renovar(cfg, rt))
    return Graph(cfg, token)


class ArchivoMicrosoft:
    """Proveedor for one stored file identity, through its account's grant."""

    def __init__(self, ident: Mapping[str, Any]) -> None:
        self.ident = ident
        self._graph: Graph | None = None

    def graph(self) -> Graph:
        if self._graph is None:
            self._graph = graph_de_cuenta(str(self.ident["cuenta_id"]))
        return self._graph

    def metadatos(self) -> Metadatos:
        return self.graph().metadatos(str(self.ident["drive_id"]), str(self.ident["item_id"]))

    def descargar(self, max_bytes: int) -> bytes:
        return self.graph().descargar(str(self.ident["drive_id"]), str(self.ident["item_id"]), max_bytes)


def fabrica(ident: Mapping[str, Any]) -> ArchivoMicrosoft:
    return ArchivoMicrosoft(ident)

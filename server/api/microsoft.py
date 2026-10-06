"""Connecting a Microsoft account (OAuth authorization code + PKCE).

    GET  /api/microsoft/estado                  connector availability + accounts (no secrets)
    POST /api/microsoft/conectar                start: {url}; sets the browser-flow cookie
    GET  /api/microsoft/callback                Microsoft's redirect (anonymous allowlist)
    GET  /api/microsoft/cuentas/:id/archivos    browse/search the owner's OneDrive (?carpeta=&q=)
    POST /api/microsoft/cuentas/:id/olvidar     remove the usable credential (reconnect later)

The callback is the only anonymous route here, and only because the
SameSite=Strict session cookie is not sent when Microsoft redirects back. It
trusts nothing from its query except the authorization code and state:

* state is unpredictable and single use; only its SHA-256 is stored, with a
  10-minute expiry;
* the pending flow is bound to this browser (a separate Secure, HttpOnly,
  SameSite=Lax cookie scoped to the callback path; only its hash is stored)
  and to the team session and user that started it;
* the flow is claimed atomically (deleted) before the code is exchanged, so
  a replayed or concurrent callback finds nothing;
* the starting session must still be valid when the flow is claimed AND again
  when the account is attached, after the token exchange;
* it always answers 303 to the fixed page /#/bases?excel=<resultado>, with
  no-store and no-referrer, clears the flow cookie and drops the code from the
  visible URL. Codes, state, cookies and tokens are never logged.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from http.cookies import CookieError, SimpleCookie
from typing import Any

from .. import auth, db
from ..excel import credenciales, microsoft
from ..excel.proveedor import ProveedorError
from ..repo import excel as repo
from ..router import Request
from ..web_util import ApiError, Redireccion

COOKIE_FLUJO = "ara_ms_flujo"
RUTA_CALLBACK = "/api/microsoft/callback"
VIGENCIA = 600


def _h(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def _actor(request: Request) -> dict[str, Any]:
    if request.user is None:
        raise ApiError("Inicia sesión para continuar.", 401, {"code": "unauthenticated"})
    return request.user


def _cookie_flujo(valor: str, max_age: int, seguro: bool) -> str:
    return (f"{COOKIE_FLUJO}={valor}; Path={RUTA_CALLBACK}; Max-Age={max_age}; HttpOnly"
            f"{'; Secure' if seguro else ''}; SameSite=Lax")


def estado(request: Request) -> dict[str, Any]:
    _actor(request)
    conector = microsoft.disponibilidad()  # opens its own session; never nest them
    with db.session() as conn:
        return {"conector": conector, "cuentas": repo.cuentas(conn)}


def conectar(request: Request) -> dict[str, Any]:
    actor = _actor(request)
    cfg = microsoft.config()
    disponible = microsoft.disponibilidad()
    if cfg is None or not disponible["disponible"]:
        raise ApiError(disponible["motivo"] or "Conector no disponible.", 503, {"code": "no_configurado"})
    token_sesion = auth.token_from_cookie(request.headers.get("Cookie"))
    if token_sesion is None:
        raise ApiError("Inicia sesión para continuar.", 401, {"code": "unauthenticated"})
    estado_oauth = secrets.token_urlsafe(32)
    flujo = secrets.token_urlsafe(32)
    verificador, reto = microsoft.pkce()
    with db.session() as conn, db.transaction(conn):
        conn.execute("DELETE FROM excel_autorizacion WHERE expira < ?", (time.time(),))
        cifrado, version = credenciales.cifrar(conn, verificador)
        conn.execute(
            "INSERT INTO excel_autorizacion (estado_hash, flujo_hash, verificador_cifrado, clave_version,"
            " user_id, sesion_hash, expira) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_h(estado_oauth), _h(flujo), cifrado, version, actor["id"], _h(token_sesion), time.time() + VIGENCIA))
    request.response_headers["Set-Cookie"] = _cookie_flujo(flujo, VIGENCIA, request.cloud)
    return {"url": microsoft.url_autorizacion(cfg, estado_oauth, reto)}


def _sesion_valida(conn: Any, sesion_hash: str, user_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM team_session s JOIN team_user u ON u.id = s.user_id WHERE s.token_hash = ?"
        " AND s.user_id = ? AND s.revoked_at IS NULL AND s.expires_at > ? AND u.active = 1"
        " AND u.credential_revision = s.credential_revision",
        (sesion_hash, user_id, time.time())).fetchone() is not None


def callback(request: Request) -> Redireccion:
    resultado = _callback(request)
    request.response_headers["Set-Cookie"] = _cookie_flujo("", 0, request.cloud)
    return Redireccion(f"/#/bases?excel={resultado}")


def _callback(request: Request) -> str:
    estado_oauth = request.q("state")
    flujo = _leer_cookie(request.headers.get("Cookie"))
    cfg = microsoft.config()
    if not estado_oauth or not flujo or cfg is None:
        return "error"
    with db.session() as conn, db.transaction(conn):
        fila = conn.execute("SELECT * FROM excel_autorizacion WHERE estado_hash = ? AND flujo_hash = ?",
                            (_h(estado_oauth), _h(flujo))).fetchone()
        if fila is None:
            return "error"
        reclamada = conn.execute("DELETE FROM excel_autorizacion WHERE estado_hash = ? AND flujo_hash = ?",
                                 (_h(estado_oauth), _h(flujo))).rowcount
        if reclamada != 1 or fila["expira"] < time.time():
            return "error"
        if not _sesion_valida(conn, fila["sesion_hash"], fila["user_id"]):
            return "error"
        if request.q("error"):
            return "cancelado"
        codigo = request.q("code")
        if not codigo:
            return "error"
        try:
            verificador = credenciales.descifrar(conn, fila["verificador_cifrado"], fila["clave_version"])
        except ProveedorError:
            return "error"
    try:  # outside any database session
        tokens = microsoft.canjear_codigo(cfg, codigo, verificador)
        identidad = microsoft.Graph(cfg, str(tokens["access_token"])).yo()
    except ProveedorError:
        return "error"
    if not tokens.get("refresh_token"):
        return "error"
    tenant = "consumers" if identidad["tipo"] == "personal" else "organizations"
    with db.session() as conn, db.transaction(conn):
        if not _sesion_valida(conn, fila["sesion_hash"], fila["user_id"]):
            return "error"  # logged out or deactivated during the exchange: attach nothing
        existente = conn.execute(
            "SELECT id FROM excel_cuenta WHERE proveedor = 'microsoft' AND proveedor_tenant = ?"
            " AND proveedor_cuenta_id = ?", (tenant, identidad["id"])).fetchone()
        ahora = db.now()
        if existente:
            cuenta_id = existente["id"]
            conn.execute("UPDATE excel_cuenta SET nombre = ?, correo = ?, tipo = ?, conectada_por = ?,"
                         " conectada_en = ?, actualizada_en = ? WHERE id = ?",
                         (identidad["nombre"], identidad["correo"], identidad["tipo"], fila["user_id"], ahora,
                          ahora, cuenta_id))
        else:
            cuenta_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO excel_cuenta (id, proveedor, proveedor_tenant, proveedor_cuenta_id, tipo, nombre,"
                " correo, conectada_por, conectada_en, actualizada_en) VALUES (?, 'microsoft', ?, ?, ?, ?, ?, ?, ?, ?)",
                (cuenta_id, tenant, identidad["id"], identidad["tipo"], identidad["nombre"], identidad["correo"],
                 fila["user_id"], ahora, ahora))
        credenciales.guardar(conn, cuenta_id, str(tokens["refresh_token"]))
    return "conectado"


def _leer_cookie(header: str | None) -> str | None:
    if not header:
        return None
    try:
        jar: SimpleCookie = SimpleCookie()
        jar.load(header)
    except CookieError:
        return None
    morsel = jar.get(COOKIE_FLUJO)
    valor = morsel.value if morsel else ""
    return valor if 20 <= len(valor) <= 200 else None


def _cuenta_id(request: Request) -> str:
    try:
        return str(uuid.UUID(request.params["id"]))
    except (KeyError, ValueError):
        raise ApiError("La cuenta no existe.", 404, {"code": "not_found"}) from None


def archivos(request: Request) -> dict[str, Any]:
    """The owner's OneDrive, for choosing the workbook: folders and .xlsx/.xlsm
    files of one folder, or a search. Read-only."""
    _actor(request)
    cuenta_id = _cuenta_id(request)
    with db.session() as conn:
        if repo.cuenta(conn, cuenta_id) is None:
            raise ApiError("La cuenta no existe.", 404, {"code": "not_found"})
    carpeta, buscar = request.q("carpeta"), (request.q("q") or "").strip() or None
    try:
        items = microsoft.graph_de_cuenta(cuenta_id).listar(carpeta, buscar)
    except ProveedorError as exc:
        raise ApiError(exc.mensaje, 409 if exc.codigo == "reconectar" else 503,
                       {"code": exc.codigo, "reintentable": exc.reintentable}) from None
    return {"elementos": items}


def olvidar(request: Request) -> dict[str, Any]:
    _actor(request)
    cuenta_id = _cuenta_id(request)
    with db.session() as conn, db.transaction(conn):
        if repo.cuenta(conn, cuenta_id) is None:
            raise ApiError("La cuenta no existe.", 404, {"code": "not_found"})
        credenciales.olvidar(conn, cuenta_id)
        return {"cuentas": repo.cuentas(conn)}

"""Sign-in, sign-out, the current session and nonsecret runtime configuration.

These four routes are on the anonymous allowlist (auth.PUBLIC_API).
"""

from __future__ import annotations

import os
from typing import Any

from .. import auth, db
from ..protocols import DatabaseConnection
from ..repo import maestra as repo_maestra
from ..router import Request
from ..web_util import ApiError, parse_json

Respuesta = dict[str, Any]

MAX_LOGIN_BODY = 4096


def config(request: Request) -> Respuesta:
    """Nonsecret UI configuration. /api/session is the authority on sign-in;
    readOnly is kept for the legacy interface until it moves to /api/session."""
    return {
        "readOnly": os.environ.get("ARA_MAP_READ_ONLY") == "1" or request.user is None,
        "cloud": request.cloud,
        "authRequired": True,
        "maxUploadBytes": (4 if request.cloud else 25) * 1024 * 1024,
    }


def _estado(conn: DatabaseConnection, sesion: auth.Sesion) -> Respuesta:
    """What the signed-in user may do (capacidades) and where (alcance), read
    now. It helps the interface decide what to show; every route checks again."""
    alcance: Any = "todas"
    if sesion.rol != "admin":
        alcance = [{"id": b["id"], "nombre": b["nombre"]}
                   for b in repo_maestra.listar(conn, sesion.user_id)]
    return {"authenticated": True,
            "user": {**sesion.actor, "rol": sesion.rol},
            "capacidades": list(auth.CAPACIDADES[sesion.rol]),
            "alcance": {"bases": alcance}}


def session(request: Request) -> Respuesta:
    if request.sesion is None:
        return {"authenticated": False}
    with db.session() as conn:
        return _estado(conn, request.sesion)


def login(request: Request) -> Respuesta:
    if len(request.body) > MAX_LOGIN_BODY:
        raise ApiError("La petición es demasiado grande.", 413)
    data = parse_json(request.body)
    # The session block must end normally so the recorded failure commits on
    # Postgres too; the error is raised only afterwards.
    with db.session() as conn:
        token, _user, throttled = auth.login(conn, data.get("username"), data.get("password"))
        sesion = auth.sesion_de_token(conn, token) if token else None
        estado = _estado(conn, sesion) if sesion else None
    if throttled:
        raise ApiError("Demasiados intentos. Espera unos minutos e inténtalo de nuevo.", 429,
                       {"code": "rate_limited"})
    if token is None or estado is None:
        raise ApiError("Usuario o contraseña incorrectos.", 401, {"code": "invalid_credentials"})
    request.response_headers["Set-Cookie"] = auth.cookie(token, auth.SESSION_SECONDS,
                                                         secure=request.cloud)
    return estado


def logout(request: Request) -> Respuesta:
    """Revoke the current session if there is one. Always succeeds."""
    token = auth.token_from_cookie(request.headers.get("Cookie"))
    if token:
        with db.session() as conn:
            auth.logout(conn, token)
    request.response_headers["Set-Cookie"] = auth.cookie("", 0, secure=request.cloud)
    return {"authenticated": False}

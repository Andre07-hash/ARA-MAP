"""Sign-in, sign-out, the current session and nonsecret runtime configuration.

These four routes are on the anonymous allowlist (auth.PUBLIC_API).
"""

from __future__ import annotations

import os
from typing import Any

from .. import auth, db
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


def session(request: Request) -> Respuesta:
    if request.user is None:
        return {"authenticated": False}
    return {"authenticated": True, "user": request.user}


def login(request: Request) -> Respuesta:
    if len(request.body) > MAX_LOGIN_BODY:
        raise ApiError("La petición es demasiado grande.", 413)
    data = parse_json(request.body)
    # The session block must end normally so the recorded failure commits on
    # Postgres too; the error is raised only afterwards.
    with db.session() as conn:
        token, user, throttled = auth.login(conn, data.get("username"), data.get("password"))
    if throttled:
        raise ApiError("Demasiados intentos. Espera unos minutos e inténtalo de nuevo.", 429,
                       {"code": "rate_limited"})
    if token is None:
        raise ApiError("Usuario o contraseña incorrectos.", 401, {"code": "invalid_credentials"})
    request.response_headers["Set-Cookie"] = auth.cookie(token, auth.SESSION_SECONDS,
                                                         secure=request.cloud)
    return {"authenticated": True, "user": user}


def logout(request: Request) -> Respuesta:
    """Revoke the current session if there is one. Always succeeds."""
    token = auth.token_from_cookie(request.headers.get("Cookie"))
    if token:
        with db.session() as conn:
            auth.logout(conn, token)
    request.response_headers["Set-Cookie"] = auth.cookie("", 0, secure=request.cloud)
    return {"authenticated": False}

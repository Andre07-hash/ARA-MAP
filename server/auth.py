"""Individual team accounts, revocable server-side sessions and the route policy.

Every signed-in team user has the same powers: there is no role column and no
privileged in-app user. Accounts are created, reset and deactivated by an
explicit-target operations command (scripts/cuentas.py), never by the web app.

The same policy guards the local loopback server and the cloud adapter: an API
route is anonymous only if it is on PUBLIC_API; everything else -- including
unknown /api paths, before any fallback -- needs a valid session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
import uuid
from http.cookies import CookieError, SimpleCookie
from typing import Any

from .protocols import DatabaseConnection

COOKIE = "ara_sesion"
SESSION_SECONDS = 12 * 60 * 60

# PBKDF2-HMAC-SHA256 at OWASP's 2023 figure. scrypt would be preferable but
# macOS's /usr/bin/python3 (LibreSSL) lacks hashlib.scrypt, and the app must run
# there. Iterations are stored in each hash, so raising this later re-hashes
# nothing and breaks no login. Measured: ~0.06 s (3.14) / ~0.14 s (3.9).
PBKDF2_ITERATIONS = 600_000
MIN_PASSWORD = 12

# Login throttle, counted in the database so every cloud worker shares it.
# ponytail: keyed by login only; an attacker can lock a known login for the
# window. Add a per-address key if that becomes a real nuisance.
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60

_LOGIN = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,63}$")

# The anonymous API allowlist (INTEGRATION_DECISIONS §3). Nothing else.
PUBLIC_API = {
    ("GET", "/api/config"),
    ("GET", "/api/session"),
    ("POST", "/api/login"),
    ("POST", "/api/logout"),
    ("GET", "/api/publico/terrenos"),
    # Microsoft's OAuth redirect back. Approved deviation (supervisor brief
    # 3c486f9, section 2A): the SameSite=Strict session cookie is not sent on
    # that cross-site navigation; the handler binds the flow by state, PKCE
    # and its own browser cookie instead, and only ever redirects.
    ("GET", "/api/microsoft/callback"),
}
_PUBLIC_DETAIL = re.compile(r"^/api/publico/terrenos/[^/]+$")


class AccountError(ValueError):
    """An operations-command input problem, shown to the operator as is."""


# -- route policy -------------------------------------------------------------

def is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def is_public(method: str, path: str) -> bool:
    """Whether an already-normalized API path may be called anonymously."""
    return (method, path) in PUBLIC_API or (method == "GET" and bool(_PUBLIC_DETAIL.match(path)))


# -- passwords ----------------------------------------------------------------

def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(("pbkdf2_sha256", str(iterations), _b64(salt), _b64(digest)))


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _unb64(salt), int(iterations))
        return hmac.compare_digest(candidate, _unb64(digest))
    except (ValueError, TypeError):
        return False


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


# Verified against when the login does not exist, so a wrong username costs as
# much time as a wrong password and the response time does not reveal accounts.
# Matches nothing: no password derives an all-zero digest.
_DUMMY_HASH = "$".join(("pbkdf2_sha256", str(PBKDF2_ITERATIONS), _b64(bytes(16)), _b64(bytes(32))))


# -- accounts (operations command only) -----------------------------------------

def normalize_login(value: Any) -> str:
    return str(value or "").strip().casefold()


def create_user(conn: DatabaseConnection, login: str, display_name: str, password: str,
                *, iterations: int = PBKDF2_ITERATIONS) -> dict[str, Any]:
    login = normalize_login(login)
    if not _LOGIN.match(login):
        raise AccountError(
            "El usuario debe tener 3 a 64 caracteres: letras, números, «.», «_», «-» o «@».")
    nombre = " ".join(str(display_name or "").split())
    if not nombre or len(nombre) > 100:
        raise AccountError("El nombre visible es obligatorio (hasta 100 caracteres).")
    _check_password(password)
    if conn.execute("SELECT 1 FROM team_user WHERE login = ?", (login,)).fetchone():
        raise AccountError(f"Ya existe el usuario «{login}».")
    ahora = _now_iso()
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO team_user (id, login, display_name, password_hash, active,"
        " credential_revision, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 1, ?, ?)",
        (user_id, login, nombre, hash_password(password, iterations), ahora, ahora))
    return {"id": user_id, "login": login, "display_name": nombre}


def set_password(conn: DatabaseConnection, login: str, password: str,
                 *, iterations: int = PBKDF2_ITERATIONS) -> None:
    """Reset a password. Every existing session of that user stops working."""
    _check_password(password)
    _change(conn, login, "password_hash = ?, credential_revision = credential_revision + 1",
            (hash_password(password, iterations),))


def set_active(conn: DatabaseConnection, login: str, active: bool) -> None:
    """Deactivate (or reactivate) an account; deactivation ends its sessions."""
    _change(conn, login, "active = ?, credential_revision = credential_revision + 1",
            (1 if active else 0,))


def list_users(conn: DatabaseConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, login, display_name, active, created_at FROM team_user ORDER BY login"
    ).fetchall()
    return [dict(r) for r in rows]


def _change(conn: DatabaseConnection, login: str, assignments: str, params: tuple[Any, ...]) -> None:
    cursor = conn.execute(
        f"UPDATE team_user SET {assignments}, updated_at = ? WHERE login = ?",
        (*params, _now_iso(), normalize_login(login)))
    if cursor.rowcount == 0:
        raise AccountError(f"No existe el usuario «{normalize_login(login)}».")


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AccountError(f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres.")


# -- login and sessions ----------------------------------------------------------

def login(conn: DatabaseConnection, username: Any, password: Any) -> tuple[str | None, dict[str, Any] | None, bool]:
    """Check credentials. Returns (token, user, throttled).

    A failure never says whether the account exists. The token is only ever
    returned to the browser; the database keeps its SHA-256.
    """
    clave = normalize_login(username)[:200]
    ahora = time.time()
    conn.execute("DELETE FROM team_login_failure WHERE failed_at < ?",
                 (ahora - FAILURE_WINDOW_SECONDS,))
    fallos = conn.execute("SELECT COUNT(*) AS n FROM team_login_failure WHERE login = ?",
                          (clave,)).fetchone()["n"]
    if fallos >= MAX_FAILURES:
        return None, None, True

    row = conn.execute(
        "SELECT id, display_name, password_hash, active, credential_revision"
        " FROM team_user WHERE login = ?", (clave,)).fetchone()
    secreto = password if isinstance(password, str) else ""
    valid = verify_password(secreto, row["password_hash"] if row else _DUMMY_HASH)
    if not (row and valid and row["active"] and secreto):
        conn.execute("INSERT INTO team_login_failure (login, failed_at) VALUES (?, ?)",
                     (clave, ahora))
        return None, None, False

    conn.execute("DELETE FROM team_login_failure WHERE login = ?", (clave,))
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO team_session (token_hash, user_id, credential_revision, created_at,"
        " expires_at) VALUES (?, ?, ?, ?, ?)",
        (_token_hash(token), row["id"], row["credential_revision"], _now_iso(),
         ahora + SESSION_SECONDS))
    return token, {"id": row["id"], "display_name": row["display_name"]}, False


def user_for_token(conn: DatabaseConnection, token: str) -> dict[str, Any] | None:
    """The active user behind a session token, or None.

    A session dies with logout, expiry, deactivation or any credential change.
    """
    row = conn.execute(
        "SELECT u.id, u.display_name FROM team_session s JOIN team_user u ON u.id = s.user_id"
        " WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ?"
        " AND u.active = 1 AND u.credential_revision = s.credential_revision",
        (_token_hash(token), time.time())).fetchone()
    return {"id": row["id"], "display_name": row["display_name"]} if row else None


def logout(conn: DatabaseConnection, token: str) -> None:
    conn.execute("UPDATE team_session SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                 (_now_iso(), _token_hash(token)))


def token_from_cookie(header: str | None) -> str | None:
    if not header:
        return None
    try:
        cookies: SimpleCookie = SimpleCookie()
        cookies.load(header)
    except CookieError:
        return None
    morsel = cookies.get(COOKIE)
    value = morsel.value if morsel else ""
    return value if 20 <= len(value) <= 200 else None


def cookie(value: str, max_age: int, secure: bool) -> str:
    """The session cookie. Secure everywhere except the loopback-only local
    server (http://localhost), which rejects any non-loopback Host header."""
    flags = "; Secure" if secure else ""
    return f"{COOKIE}={value}; Path=/; Max-Age={max_age}; HttpOnly{flags}; SameSite=Strict"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    from .db import now
    return now()

"""Team accounts, revocable server-side sessions, roles and the access policy.

Two things decide what a signed-in user may do. The ROLE gives capabilities
(CAPACIDADES): every private route declares one and the dispatcher refuses the
request without it. The SCOPE says where: an administrator's capabilities
apply everywhere, an operator's only inside the work bases granted to that
person (maestra_base_acceso), checked by require_* / reverificar_*.

Accounts and roles are created and changed by an explicit-target operations
command (scripts/cuentas.py), never by the web app.

The same policy guards the local loopback server and the cloud adapter: an API
route is anonymous only if it is on PUBLIC_API; everything else -- including
unknown /api paths, before any fallback -- needs a valid session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from http.cookies import CookieError, SimpleCookie
from typing import Any

from . import db
from .errors import ApiError
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
}
_PUBLIC_DETAIL = re.compile(r"^/api/publico/terrenos/[^/]+$")


ROLES = ("admin", "operador")
_DE_TRABAJO = ("maestra.ver", "maestra.editar", "maestra.archivar", "columnas.gestionar",
               "archivos.ver", "archivos.subir", "archivos.retirar")
# What each role may do. Where is a separate question, answered per request
# from the database (never cached): see _verificar.
CAPACIDADES = {
    "operador": _DE_TRABAJO,
    "admin": (*_DE_TRABAJO, "maestra.global", "bases.gestionar", "derivados.ver",
              "derivados.gestionar", "usuarios.gestionar"),
}
# Reads may look at archived content inside scope; these may also change it.
_LECTURA = ("maestra.ver", "archivos.ver")
_EDICION_ORDINARIA = ("maestra.editar", "archivos.subir", "archivos.retirar")
# Administering a base (its grants, restoring it) is how an archived base is reopened.
_ADMINISTRA_BASE = ("bases.gestionar",)

# The audit identity of scripts/cuentas.py, which has no signed-in account.
ACTOR_CLI = "CLI scripts/cuentas.py"

NO_EXISTE_TERRENO = "El terreno no existe."
NO_EXISTE_BASE = "La base de trabajo no existe."


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
                *, iterations: int = PBKDF2_ITERATIONS, rol: str = "operador") -> dict[str, Any]:
    """A new account. It is an operator unless told otherwise: nothing here,
    and no migration, ever makes an administrator by default."""
    _check_rol(rol)
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
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO team_user (id, login, display_name, password_hash, active,"
            " credential_revision, rol, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 1, ?, ?, ?)",
            (user_id, login, nombre, hash_password(password, iterations), rol, ahora, ahora))
        _account_event(conn, user_id, "cuenta_creada", ahora, {"rol": rol})
    return {"id": user_id, "login": login, "display_name": nombre, "rol": rol}


def set_password(conn: DatabaseConnection, login: str, password: str,
                 *, iterations: int = PBKDF2_ITERATIONS) -> None:
    """Reset a password. Every existing session of that user stops working."""
    _check_password(password)
    _change(conn, login, "password_hash = ?, credential_revision = credential_revision + 1",
            (hash_password(password, iterations),), "contrasena_restablecida")


def set_active(conn: DatabaseConnection, login: str, active: bool) -> None:
    """Deactivate (or reactivate) an account; deactivation ends its sessions."""
    _change(conn, login, "active = ?, credential_revision = credential_revision + 1",
            (1 if active else 0,), "cuenta_reactivada" if active else "cuenta_desactivada")


def set_role(conn: DatabaseConnection, login: str, rol: str) -> bool:
    """Change an account's role; False if it already had it (nothing changes).

    A real change ends every session of that user, so no open session keeps
    acting with the old role.
    """
    _check_rol(rol)
    actual = conn.execute("SELECT rol FROM team_user WHERE login = ?",
                          (normalize_login(login),)).fetchone()
    if actual is not None and actual["rol"] == rol:
        return False
    _change(conn, login, "rol = ?, credential_revision = credential_revision + 1", (rol,),
            "rol_cambiado", {"antes": actual["rol"] if actual else None, "despues": rol})
    return True


def list_users(conn: DatabaseConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, login, display_name, rol, active, created_at FROM team_user ORDER BY login"
    ).fetchall()
    return [dict(r) for r in rows]


def _change(conn: DatabaseConnection, login: str, assignments: str, params: tuple[Any, ...],
            action: str, details: dict[str, Any] | None = None) -> None:
    """One account change and its audit row, together or not at all."""
    ahora = _now_iso()
    with db.transaction(conn):
        row = conn.execute("SELECT id FROM team_user WHERE login = ?",
                           (normalize_login(login),)).fetchone()
        if row is None:
            raise AccountError(f"No existe el usuario «{normalize_login(login)}».")
        conn.execute(f"UPDATE team_user SET {assignments}, updated_at = ? WHERE id = ?",
                     (*params, ahora, row["id"]))
        _account_event(conn, row["id"], action, ahora, details)


def _account_event(conn: DatabaseConnection, user_id: str, action: str, ahora: str,
                   details: dict[str, Any] | None = None) -> None:
    """Append-only account history. These functions are only reachable from
    the operations command, so the actor is the command, not a web user."""
    conn.execute(
        "INSERT INTO team_user_event (id, user_id, action, actor_id, actor_name, at, details_json)"
        " VALUES (?, ?, ?, NULL, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, action, ACTOR_CLI, ahora,
         json.dumps(details, ensure_ascii=False) if details else None))


def _check_rol(rol: str) -> None:
    if rol not in ROLES:
        raise AccountError(f"El rol debe ser uno de: {', '.join(ROLES)}.")


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
        " FROM team_user WHERE login = ?", (clave,)).fetchone()  # the role is read per request
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


class Sesion:
    """A validated session: who is asking, and which session and credential
    generation proved it.

    Built only by sesion_de_token, from the cookie. ``referencia`` names the
    team_session row so the same session can be validated again later, inside
    a write transaction (reverificar_*). It is internal: never put it, or this
    object, in a response, a log, an audit payload or a stored result. It is
    deliberately not a dataclass or a tuple, which the JSON encoder would
    unpack; encoded by accident it shows only its repr.
    """

    __slots__ = ("referencia", "user_id", "display_name", "rol", "credential_revision")

    def __init__(self, referencia: str, user_id: str, display_name: str, rol: str,
                 credential_revision: int) -> None:
        self.referencia = referencia
        self.user_id = user_id
        self.display_name = display_name
        self.rol = rol
        self.credential_revision = credential_revision

    def __repr__(self) -> str:
        return f"<Sesion de {self.user_id}>"

    @property
    def actor(self) -> dict[str, Any]:
        """The audit identity, shaped like request.user."""
        return {"id": self.user_id, "display_name": self.display_name}


class Alcance:
    """What one authorization check established, as read from the database at
    that moment. Not a dataclass, for the same reason as Sesion."""

    __slots__ = ("sesion", "actor", "rol", "capacidad", "terreno_id", "base_id",
                 "terreno_archivado", "base_archivada")

    def __init__(self, sesion: Sesion, rol: str, capacidad: str, terreno_id: str | None,
                 base_id: str | None, terreno_archivado: bool, base_archivada: bool) -> None:
        self.sesion = sesion
        self.actor = sesion.actor
        self.rol = rol
        self.capacidad = capacidad
        self.terreno_id = terreno_id
        self.base_id = base_id
        self.terreno_archivado = terreno_archivado
        self.base_archivada = base_archivada

    def __repr__(self) -> str:
        return f"<Alcance {self.capacidad} terreno={self.terreno_id} base={self.base_id}>"


def sesion_de_token(conn: DatabaseConnection, token: str) -> Sesion | None:
    """The validated session behind a cookie token, or None.

    A session dies with logout, expiry, deactivation or any credential change
    (password reset, role change).
    """
    referencia = _token_hash(token)
    row = conn.execute(
        "SELECT u.id, u.display_name, u.rol, s.credential_revision"
        " FROM team_session s JOIN team_user u ON u.id = s.user_id"
        " WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ?"
        " AND u.active = 1 AND u.credential_revision = s.credential_revision",
        (referencia, time.time())).fetchone()
    if row is None:
        return None
    return Sesion(referencia, row["id"], row["display_name"], row["rol"], row["credential_revision"])


def user_for_token(conn: DatabaseConnection, token: str) -> dict[str, Any] | None:
    """The active user behind a session token, or None."""
    sesion = sesion_de_token(conn, token)
    return sesion.actor if sesion else None


# -- authorization ---------------------------------------------------------------
#
# 401 no valid session; 403 the role lacks the capability; 404 the resource is
# missing OR outside the caller's scope (the two are indistinguishable on
# purpose); 409 the caller is in scope but the terrain or base is archived.

def no_autenticado() -> ApiError:
    return ApiError("Inicia sesión para continuar.", 401, {"code": "unauthenticated"})


def prohibido(capacidad: str | None) -> ApiError:
    return ApiError("Tu cuenta no tiene permiso para esta acción.", 403,
                    {"code": "forbidden", "capacidad": capacidad})


def _no_existe(mensaje: str) -> ApiError:
    return ApiError(mensaje, 404, {"code": "not_found"})


def _sesion(request: Any) -> Sesion:
    sesion = getattr(request, "sesion", None)
    if not isinstance(sesion, Sesion):  # only the dispatcher sets it, from the cookie
        raise no_autenticado()
    return sesion


def require_base(request: Any, base_id: str, capacidad: str,
                 conn: DatabaseConnection | None = None) -> Alcance:
    """Request-start check that the caller may do this in that work base.

    Pass ``conn`` to read with the connection the handler already has open.
    Before a write, check again with reverificar_base inside db.escritura().
    """
    sesion = _sesion(request)
    if conn is not None:
        return _verificar(conn, sesion, capacidad, base_id=base_id)
    with db.session() as propia:
        return _verificar(propia, sesion, capacidad, base_id=base_id)


def require_terreno(request: Any, terreno_id: str, capacidad: str,
                    conn: DatabaseConnection | None = None) -> Alcance:
    """Request-start check that the caller may do this to that terrain. The
    terrain's base is read from the database, never taken from the caller."""
    sesion = _sesion(request)
    if conn is not None:
        return _verificar(conn, sesion, capacidad, terreno_id=terreno_id)
    with db.session() as propia:
        return _verificar(propia, sesion, capacidad, terreno_id=terreno_id)


def reverificar(conn: DatabaseConnection, sesion: Sesion, capacidad: str) -> Alcance:
    """reverificar_terreno for a write that names no terrain or base."""
    return _verificar(conn, sesion, capacidad, bloquear=True)


def reverificar_base(conn: DatabaseConnection, sesion: Sesion, base_id: str, capacidad: str,
                     *, exclusivo: bool = False) -> Alcance:
    """reverificar_terreno for a write addressed to a work base."""
    return _verificar(conn, sesion, capacidad, base_id=base_id, bloquear=True, exclusivo=exclusivo)


def reverificar_terreno(conn: DatabaseConnection, sesion: Sesion, terreno_id: str, capacidad: str,
                        *, exclusivo: bool = False) -> Alcance:
    """The authorization check at the write boundary.

    Call it first inside ``with db.escritura() as conn``, with the Sesion the
    request was authenticated with, before the first write. db.escritura() is
    the only supported way in, on both databases; a connection from anywhere
    else is refused on SQLite and NOT detected on Postgres. It reads again,
    on that connection, everything the decision depends on: the session
    (revoked, expired, credential generation), the account (active, role), the
    terrain (exists, current base, archived), that base (archived) and the
    caller's grant on it. Whatever the request saw when it started no longer
    counts. Raises the same 401/403/404/409 as require_terreno; on any of
    them the caller must write nothing and let the transaction roll back.

    On Postgres each row is read FOR SHARE, in the fixed order user ->
    session -> terrain -> base -> grant, so a scope change that already
    committed is seen, and one that comes later waits for this transaction.
    Take any further locks (attachment, version) after this call.
    ``exclusivo`` locks the terrain row FOR UPDATE instead: pass it when this
    transaction will itself update inventory_terrain, so two such writers
    queue instead of deadlocking on a lock upgrade.
    """
    return _verificar(conn, sesion, capacidad, terreno_id=terreno_id, bloquear=True,
                      exclusivo=exclusivo)


def _verificar(conn: DatabaseConnection, sesion: Sesion, capacidad: str, *,
               terreno_id: str | None = None, base_id: str | None = None,
               bloquear: bool = False, exclusivo: bool = False) -> Alcance:
    """Every authorization decision, in one place. ``bloquear`` is the
    write-boundary form: it takes row locks, and refuses a SQLite connection
    that did not come from db.escritura(). It cannot check that for Postgres
    (see db.en_escritura): there the caller is trusted to have used it."""
    if bloquear and not db.en_escritura(conn):
        raise RuntimeError("reverificar_* debe llamarse dentro de db.escritura().")
    compartido = db.bloqueo(conn) if bloquear else ""
    del_recurso = db.bloqueo(conn, exclusivo) if bloquear else ""

    usuario = conn.execute(
        "SELECT id, rol, active, credential_revision FROM team_user WHERE id = ?" + compartido,
        (sesion.user_id,)).fetchone()
    abierta = conn.execute(
        "SELECT user_id, credential_revision, revoked_at, expires_at FROM team_session"
        " WHERE token_hash = ?" + compartido, (sesion.referencia,)).fetchone()
    if (usuario is None or abierta is None or not usuario["active"]
            or abierta["user_id"] != usuario["id"] or abierta["revoked_at"] is not None
            or abierta["expires_at"] <= time.time()
            or not (abierta["credential_revision"] == usuario["credential_revision"]
                    == sesion.credential_revision)):
        raise no_autenticado()
    rol = usuario["rol"]
    if capacidad not in CAPACIDADES[rol]:
        raise prohibido(capacidad)

    falta = NO_EXISTE_BASE
    terreno_archivado = base_archivada = False
    if terreno_id is not None:
        falta = NO_EXISTE_TERRENO
        terreno = conn.execute(
            "SELECT base_id, archived_at FROM inventory_terrain WHERE id = ?" + del_recurso,
            (terreno_id,)).fetchone()
        # An unassigned terrain belongs to no work base: administrators only.
        if terreno is None or (terreno["base_id"] is None and rol != "admin"):
            raise _no_existe(falta)
        base_id = terreno["base_id"]
        terreno_archivado = terreno["archived_at"] is not None
    if base_id is not None:
        base = conn.execute(
            "SELECT archived_at FROM maestra_base WHERE id = ?"
            + (compartido if terreno_id is not None else del_recurso), (base_id,)).fetchone()
        if base is None:
            raise _no_existe(falta)
        base_archivada = base["archived_at"] is not None
        if rol != "admin":
            acceso = conn.execute(
                "SELECT 1 AS ok FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?"
                + compartido, (base_id, usuario["id"])).fetchone()
            # An archived base is closed to operators, granted or not.
            if acceso is None or base_archivada:
                raise _no_existe(falta)

    # Only now, in scope, may the caller learn that something is archived.
    if capacidad not in _LECTURA and capacidad not in _ADMINISTRA_BASE:
        if base_archivada:
            raise ApiError("La base de trabajo está archivada; restáurala para hacer cambios.",
                           409, {"code": "base_archivada"})
        if terreno_archivado and capacidad in _EDICION_ORDINARIA:
            raise ApiError("El terreno está archivado; restáuralo para hacer cambios.",
                           409, {"code": "terreno_archivado"})
    return Alcance(sesion, rol, capacidad, terreno_id, base_id, terreno_archivado, base_archivada)


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
    return db.now()

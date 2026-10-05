"""Shared editor password and signed, expiring browser sessions."""

import hashlib
import hmac
import os
import secrets
import time
from http.cookies import SimpleCookie

COOKIE = "ara_editor"
SESSION_SECONDS = 12 * 60 * 60


def public_edit() -> bool:
    return os.environ.get("ARA_MAP_PUBLIC_EDIT") == "1"


def password_matches(value: str) -> bool:
    expected = os.environ.get("ARA_MAP_EDIT_PASSWORD", "")
    return bool(expected) and secrets.compare_digest(value.encode(), expected.encode())


def _signature(value: str) -> str:
    return hmac.new(os.environ.get("ARA_MAP_EDIT_PASSWORD", "").encode(),
                    value.encode(), hashlib.sha256).hexdigest()


def session_token() -> str:
    value = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(16)}"
    return f"{value}.{_signature(value)}"


def authenticated(cookie_header: str) -> bool:
    if public_edit():
        return True
    if not os.environ.get("ARA_MAP_EDIT_PASSWORD"):
        return False
    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        token = cookies[COOKIE].value
        value, signature = token.rsplit(".", 1)
        expires = int(value.split(".", 1)[0])
        return expires > time.time() and secrets.compare_digest(signature, _signature(value))
    except (KeyError, ValueError, TypeError):
        return False


def cookie(value: str, max_age: int = SESSION_SECONDS) -> str:
    return f"{COOKIE}={value}; Path=/; Max-Age={max_age}; HttpOnly; Secure; SameSite=Strict"

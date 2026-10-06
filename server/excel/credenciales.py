"""Encrypted connector credentials in Postgres (pgcrypto).

* PGP symmetric encryption (pgp_sym_encrypt / pgp_sym_decrypt, AES-256) from
  the pgcrypto extension, ciphertext stored base64-encoded in TEXT.
* The key is ARA_MAP_TOKEN_KEY (server-only secret, at least 32 characters,
  different for Preview and Production), labelled by ARA_MAP_TOKEN_KEY_VERSION
  (default "1"). It is never generated: without it the connector is disabled.
  A stored credential whose key version differs is treated as "reconnect".
* The database server performs the encryption, so it sees the plaintext and
  the key while executing these statements (always as bound parameters, never
  in SQL text or logs). This protects stored values and backups, not against
  a trusted database operator watching live execution.
* Each account's credential refresh is serialized across workers by a short
  lease on its excel_credencial row; the replacement refresh token is written
  with a compare-and-set on generacion, so a stale writer cannot overwrite it.

Nothing here holds a database session open while Microsoft is called.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from typing import Any

from .. import db, postgres
from ..protocols import DatabaseConnection
from .proveedor import ProveedorError

MIN_CLAVE = 32
LEASE_SEGUNDOS = 30.0
ESPERA_MAXIMA = 20.0


def clave() -> tuple[str, str] | None:
    """(key, key version), or None when not configured."""
    valor = os.environ.get("ARA_MAP_TOKEN_KEY", "")
    if len(valor) < MIN_CLAVE:
        return None
    return valor, os.environ.get("ARA_MAP_TOKEN_KEY_VERSION", "1")


def disponible() -> tuple[bool, str | None]:
    """Whether credentials can be stored here: Postgres, a key, pgcrypto."""
    if not postgres.enabled():
        return False, "La conexión con Excel en la nube sólo está disponible en la versión web."
    if clave() is None:
        return False, "Falta la clave de cifrado del servidor (ARA_MAP_TOKEN_KEY)."
    with db.session() as conn:
        if conn.execute("SELECT to_regprocedure('public.pgp_sym_encrypt(text,text,text)') AS f"
                        ).fetchone()["f"] is None:
            return False, "La base de datos no tiene pgcrypto; el conector está deshabilitado."
    return True, None


def cifrar(conn: DatabaseConnection, texto: str) -> tuple[str, str]:
    k = _clave_obligatoria()
    row = conn.execute("SELECT encode(public.pgp_sym_encrypt(?, ?, 'cipher-algo=aes256'), 'base64') AS c",
                       (texto, k[0])).fetchone()
    return str(row["c"]), k[1]


def descifrar(conn: DatabaseConnection, cifrado: str, version: str) -> str:
    k = _clave_obligatoria()
    if version != k[1]:
        raise ProveedorError("reconectar", "La credencial guardada usa otra clave; vuelve a conectar la cuenta.")
    try:
        row = conn.execute("SELECT public.pgp_sym_decrypt(decode(?, 'base64'), ?) AS t", (cifrado, k[0])).fetchone()
    except Exception:  # noqa: BLE001 - wrong key or corrupt value; never echo it
        raise ProveedorError("reconectar", "No se pudo leer la credencial guardada; vuelve a conectar la cuenta."
                             ) from None
    return str(row["t"])


def _clave_obligatoria() -> tuple[str, str]:
    k = clave()
    if k is None:
        raise ProveedorError("no_configurado", "Falta la clave de cifrado del servidor.")
    return k


def guardar(conn: DatabaseConnection, cuenta_id: str, refresh_token: str) -> None:
    """Store (or replace) an account's credential after an OAuth sign-in."""
    cifrado, version = cifrar(conn, refresh_token)
    ahora = db.now()
    if conn.execute("SELECT 1 FROM excel_credencial WHERE cuenta_id = ?", (cuenta_id,)).fetchone():
        conn.execute("UPDATE excel_credencial SET token_cifrado = ?, clave_version = ?,"
                     " generacion = generacion + 1, ocupada_hasta = 0, ocupada_por = NULL, actualizada_en = ?"
                     " WHERE cuenta_id = ?", (cifrado, version, ahora, cuenta_id))
    else:
        conn.execute("INSERT INTO excel_credencial (cuenta_id, token_cifrado, clave_version, actualizada_en)"
                     " VALUES (?, ?, ?, ?)", (cuenta_id, cifrado, version, ahora))


def olvidar(conn: DatabaseConnection, cuenta_id: str) -> None:
    """Remove the usable credential; the account and its sources stay and
    show 'reconnect required'."""
    conn.execute("DELETE FROM excel_credencial WHERE cuenta_id = ?", (cuenta_id,))


def con_token_fresco(cuenta_id: str, renovar: Callable[[str], dict[str, Any]]) -> str:
    """An access token for this account. `renovar(refresh_token)` calls the
    provider's token endpoint and returns {access_token, refresh_token?}.

    Serialized per account: take the lease (short transaction), read and
    decrypt, release the session, call the provider, then write the rotated
    refresh token only if this worker still holds the lease at the same
    generation (short transaction)."""
    yo = str(uuid.uuid4())
    limite = time.monotonic() + ESPERA_MAXIMA
    while True:
        with db.session() as conn, db.transaction(conn):
            ahora = time.time()
            cursor = conn.execute(
                "UPDATE excel_credencial SET ocupada_hasta = ?, ocupada_por = ?"
                " WHERE cuenta_id = ? AND ocupada_hasta < ?", (ahora + LEASE_SEGUNDOS, yo, cuenta_id, ahora))
            fila = conn.execute("SELECT token_cifrado, clave_version, generacion FROM excel_credencial"
                                " WHERE cuenta_id = ?", (cuenta_id,)).fetchone()
            if fila is None:
                raise ProveedorError("reconectar", "Hay que volver a conectar la cuenta de Microsoft.")
            if cursor.rowcount == 1:
                refresh_token = descifrar(conn, fila["token_cifrado"], fila["clave_version"])
                generacion = fila["generacion"]
                break
        if time.monotonic() > limite:
            raise ProveedorError("no_disponible", "La cuenta de Microsoft está ocupada; inténtalo de nuevo.",
                                 reintentable=True)
        time.sleep(0.2)

    try:
        tokens = renovar(refresh_token)
    except ProveedorError as exc:
        with db.session() as conn, db.transaction(conn):
            if exc.codigo == "reconectar":
                conn.execute("DELETE FROM excel_credencial WHERE cuenta_id = ? AND ocupada_por = ?", (cuenta_id, yo))
            else:
                _soltar(conn, cuenta_id, yo)
        raise
    except BaseException:
        with db.session() as conn, db.transaction(conn):
            _soltar(conn, cuenta_id, yo)
        raise

    with db.session() as conn, db.transaction(conn):
        nuevo = tokens.get("refresh_token")
        if nuevo and nuevo != refresh_token:
            cifrado, version = cifrar(conn, nuevo)
            conn.execute(
                "UPDATE excel_credencial SET token_cifrado = ?, clave_version = ?, generacion = generacion + 1,"
                " ocupada_hasta = 0, ocupada_por = NULL, actualizada_en = ?"
                " WHERE cuenta_id = ? AND ocupada_por = ? AND generacion = ?",
                (cifrado, version, db.now(), cuenta_id, yo, generacion))
        else:
            _soltar(conn, cuenta_id, yo)
    return str(tokens["access_token"])


def _soltar(conn: DatabaseConnection, cuenta_id: str, yo: str) -> None:
    conn.execute("UPDATE excel_credencial SET ocupada_hasta = 0, ocupada_por = NULL"
                 " WHERE cuenta_id = ? AND ocupada_por = ?", (cuenta_id, yo))

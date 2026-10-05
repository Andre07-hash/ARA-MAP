"""Import drafts: the parsed file and the choices made so far, between requests.

Local installations keep drafts in memory, like preview tokens. The shared
deployment keeps them in Postgres, because consecutive requests may reach
different workers. Either way a draft expires, the number held is bounded, and
it is never part of a workspace backup.

Every change is a compare-and-set on the revision: a request built on an older
revision cannot overwrite a newer one.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

TTL_SEGUNDOS = 60 * 60
MAX_LOCALES = 12
MAX_NUBE = 40


class RevisionObsoleta(Exception):  # noqa: N818 - a state, not a failure
    """The draft moved on since the caller last saw it."""


@dataclass(frozen=True)
class Borrador:
    token: str
    rejilla: str           # Rejilla.empaquetar()
    estado: dict[str, Any]
    revision: int
    creado: float


class Borradores:
    def __init__(self) -> None:
        self._items: dict[str, Borrador] = {}
        self._lock = threading.Lock()

    def crear(self, rejilla: str, estado: dict[str, Any]) -> Borrador:
        borrador = Borrador(secrets.token_urlsafe(18), rejilla, estado, 0, time.time())
        from .. import postgres
        if postgres.enabled():
            with postgres.session() as conn:
                conn.execute("DELETE FROM borrador_importacion WHERE creado < ?", (time.time() - TTL_SEGUNDOS,))
                conn.execute(
                    "DELETE FROM borrador_importacion WHERE token IN (SELECT token FROM borrador_importacion"
                    " ORDER BY creado DESC OFFSET ?)", (MAX_NUBE - 1,))
                conn.execute("INSERT INTO borrador_importacion (token, rejilla, estado, revision, creado)"
                             " VALUES (?, ?, ?, 0, ?)",
                             (borrador.token, rejilla, json.dumps(estado), borrador.creado))
            return borrador
        with self._lock:
            self._purgar()
            while len(self._items) >= MAX_LOCALES:
                del self._items[min(self._items, key=lambda t: self._items[t].creado)]
            self._items[borrador.token] = borrador
        return borrador

    def leer(self, token: str) -> Borrador | None:
        from .. import postgres
        if postgres.enabled():
            with postgres.session() as conn:
                fila = conn.execute("SELECT * FROM borrador_importacion WHERE token = ?", (token,)).fetchone()
            if fila is None or fila["creado"] < time.time() - TTL_SEGUNDOS:
                return None
            return Borrador(fila["token"], fila["rejilla"], json.loads(fila["estado"]),
                            int(fila["revision"]), float(fila["creado"]))
        with self._lock:
            self._purgar()
            return self._items.get(token)

    def guardar(self, token: str, revision: int, estado: dict[str, Any]) -> int:
        """Store a new state if the draft is still at `revision`. Returns the new one."""
        from .. import postgres
        if postgres.enabled():
            with postgres.session() as conn:
                fila = conn.execute(
                    "UPDATE borrador_importacion SET estado = ?, revision = revision + 1"
                    " WHERE token = ? AND revision = ? AND creado >= ? RETURNING revision",
                    (json.dumps(estado), token, revision, time.time() - TTL_SEGUNDOS)).fetchone()
            if fila is None:
                raise RevisionObsoleta(token)
            return int(fila["revision"])
        with self._lock:
            actual = self._items.get(token)
            if actual is None or actual.revision != revision:
                raise RevisionObsoleta(token)
            nuevo = Borrador(token, actual.rejilla, estado, revision + 1, actual.creado)
            self._items[token] = nuevo
            return nuevo.revision

    def reclamar(self, token: str, revision: int) -> bool:
        """Freeze the draft at `revision` for confirmation, atomically.

        After this, no preparation can succeed: the revision has moved on and
        the draft is marked as confirming. Raises RevisionObsoleta when the
        draft already moved past `revision` (a newer preview exists) or is
        being confirmed. Returns False when the draft no longer exists or has
        expired. That is NOT permission to proceed: a draft disappears when a
        different revision of it was already imported, so the caller must
        treat False as a stale preview.
        """
        from .. import postgres
        if postgres.enabled():
            with postgres.session() as conn:  # the workspace lock serializes read and write
                fila = conn.execute("SELECT estado, revision FROM borrador_importacion"
                                    " WHERE token = ? AND creado >= ?",
                                    (token, time.time() - TTL_SEGUNDOS)).fetchone()
                if fila is None:
                    return False
                estado = json.loads(fila["estado"])
                if int(fila["revision"]) != revision or estado.get("confirmando"):
                    raise RevisionObsoleta(token)
                estado["confirmando"] = True
                cambiada = conn.execute(
                    "UPDATE borrador_importacion SET estado = ?, revision = revision + 1"
                    " WHERE token = ? AND revision = ? RETURNING revision",
                    (json.dumps(estado), token, revision)).fetchone()
                if cambiada is None:
                    raise RevisionObsoleta(token)
                return True
        with self._lock:
            self._purgar()
            actual = self._items.get(token)
            if actual is None:
                return False
            if actual.revision != revision or actual.estado.get("confirmando"):
                raise RevisionObsoleta(token)
            self._items[token] = Borrador(token, actual.rejilla, {**actual.estado, "confirmando": True},
                                          revision + 1, actual.creado)
            return True

    def borrar(self, token: str) -> None:
        from .. import postgres
        if postgres.enabled():
            with postgres.session() as conn:
                conn.execute("DELETE FROM borrador_importacion WHERE token = ?", (token,))
            return
        with self._lock:
            self._items.pop(token, None)

    def _purgar(self) -> None:
        limite = time.time() - TTL_SEGUNDOS
        for token in [t for t, b in self._items.items() if b.creado < limite]:
            del self._items[token]


borradores = Borradores()

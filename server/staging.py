"""Holds a parsed workbook between the preview and the confirmation.

The user sees exactly what will be written before anything is written, so the
parsed result has to survive between two requests. It lives in memory only: if
the app restarts mid-import, the user re-picks the file.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

TTL_SECONDS = 30 * 60
MAX_PENDING = 8


@dataclass(frozen=True)
class Pending:
    token: str
    archivo: str
    nombre_sugerido: str
    resultado: Any
    incidencias: Mapping[int, Any]
    creado: float = field(default_factory=time.time)
    # What the import assistant needs at confirmation (plan, draft revision,
    # format to remember). JSON-serializable; absent in older payloads.
    meta: Mapping[str, Any] = field(default_factory=dict)


class Staging:
    """Thread-safe store of pending imports, oldest evicted first."""

    def __init__(self) -> None:
        self._items: dict[str, Pending] = {}
        self._lock = threading.Lock()

    def put(
        self,
        archivo: str,
        nombre_sugerido: str,
        resultado: Any,
        incidencias: Mapping[int, Any],
        meta: Mapping[str, Any] | None = None,
    ) -> Pending:
        """Hold a parsed workbook and hand back the token that retrieves it."""
        pending = Pending(
            token=secrets.token_urlsafe(16),
            archivo=archivo,
            nombre_sugerido=nombre_sugerido,
            resultado=resultado,
            incidencias=incidencias,
            meta=dict(meta or {}),
        )
        from . import postgres
        if postgres.enabled():
            with postgres.session() as conn:
                conn.execute("DELETE FROM pending_import WHERE created < ?", (time.time() - TTL_SECONDS,))
                conn.execute("INSERT INTO pending_import(token, payload, created) VALUES (?, ?, ?)",
                             (pending.token, json.dumps(asdict(pending), ensure_ascii=False), pending.creado))
            return pending
        with self._lock:
            self._evict()
            self._items[pending.token] = pending
        return pending

    def take(self, token: str) -> Pending | None:
        """Fetch and remove a pending import; a token is single-use."""
        from . import postgres
        if postgres.enabled():
            with postgres.session() as conn:
                row = conn.execute("DELETE FROM pending_import WHERE token = ? RETURNING payload, created",
                                   (token,)).fetchone()
            if row is None or row["created"] < time.time() - TTL_SECONDS:
                return None
            return _decode_pending(json.loads(row["payload"]))
        with self._lock:
            self._evict()
            return self._items.pop(token, None)

    def _evict(self) -> None:
        cutoff = time.time() - TTL_SECONDS
        for token in [t for t, p in self._items.items() if p.creado < cutoff]:
            del self._items[token]
        while len(self._items) >= MAX_PENDING:
            oldest = min(self._items, key=lambda t: self._items[t].creado)
            del self._items[oldest]


staging = Staging()


def _decode_pending(data: dict[str, Any]) -> Pending:
    from .importer import ImportResult, ParseNote, RejectedRow, TerrainRecord
    from .validation import Finding

    result = data["resultado"]
    records = []
    for record in result["records"]:
        record["notes"] = tuple(ParseNote(**note) for note in record["notes"])
        records.append(TerrainRecord(**record))
    result["records"] = tuple(records)
    result["rechazadas"] = tuple(RejectedRow(**row) for row in result["rechazadas"])
    for key in ("columnas_no_reconocidas", "columnas_faltantes"):
        result[key] = tuple(result[key])
    data["resultado"] = ImportResult(**result)
    data["incidencias"] = {int(key): tuple(Finding(**finding) for finding in values)
                           for key, values in data["incidencias"].items()}
    return Pending(**data)

"""A typed binary HTTP response, for handlers that return bytes, not JSON.

The dispatcher's existing tuple ``(contents, filename)`` means an XLSX export
and keeps that meaning. A handler that returns a RespuestaBinaria asks for
exactly these bytes, content type, status and headers instead. Mounting it in
the production dispatcher is an A-owned 3A change (see the 2B report's
INTEGRATION_REQUESTS.md); until then only the 2B HTTP test harness sends it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RespuestaBinaria:
    cuerpo: bytes | bytearray
    tipo: str
    cabeceras: dict[str, str] = field(default_factory=dict)
    status: int = 200

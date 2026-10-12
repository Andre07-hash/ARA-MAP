"""The hosted entry point: one small always-HTTPS deployment behind a proxy.

    python -m server.hosted

The same router, services and static app as the local server (server/app.py),
under the cloud policy: Postgres is required and SQLite is never a fallback,
the session cookie is Secure, and the only trusted host and origin are the one
public hostname named in the environment. The platform's proxy ends TLS and
forwards plain HTTP to 0.0.0.0:$PORT; nothing here reads a forwarded header,
so a client cannot choose what this server trusts.

The local launcher keeps its loopback-only behavior: this module is never
imported by it.
"""

from __future__ import annotations

import os
import re
import signal
import sys
import threading
from collections.abc import Mapping
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from . import db, postgres
from .api import archivos as api_archivos
from .app import Handler

# Answered before any policy and without touching the database: the
# platform's probe arrives with its own Host, and a probe that woke the
# database every few seconds would spend a free plan's compute on nothing.
SALUD = "/healthz"
# ponytail: one global bound on requests in flight; each may hold a 25 MiB
# body. Per-route budgets if the small host's memory ever needs finer control.
EN_CURSO_MAX = 4
ESPERA_DE_CUPO = 20.0
_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
_PUERTO = re.compile(r"[0-9]{1,5}")
_HSTS = {"Strict-Transport-Security": "max-age=31536000"}


class HostedHandler(Handler):
    """The shared handler under the hosted policy."""

    CLOUD = True
    HOST_PUBLICO = ""          # set once by configurar(); empty trusts nothing
    timeout = 30               # seconds a silent socket may hold a thread
    _cupo = threading.BoundedSemaphore(EN_CURSO_MAX)

    def _dispatch(self, method: str) -> None:
        if method == "GET" and self.path == SALUD:
            return self._send(HTTPStatus.OK, b"ok\n", "text/plain")
        if not self._cupo.acquire(timeout=ESPERA_DE_CUPO):
            return self._busy()  # closes: the body was not read
        try:
            super()._dispatch(method)
        finally:
            self._cupo.release()

    def _host_is_local(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        return bool(self.HOST_PUBLICO) and host == self.HOST_PUBLICO

    def _origin_is_local(self) -> bool:
        """A write must come from this portal's own HTTPS origin, or carry no
        Origin at all (a command-line client; browsers always send one)."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        partes = urlsplit(origin)
        return partes.scheme == "https" and partes.netloc.lower() == self.HOST_PUBLICO

    def _database_ready(self) -> bool:
        return postgres.enabled()  # never a local SQLite file

    def _send(self, status: HTTPStatus | int, payload: bytes | bytearray, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        return super()._send(status, payload, content_type, {**_HSTS, **(extra or {})})

    def log_message(self, fmt: str, *args: Any) -> None:
        # The query string can carry a search someone typed; the path is enough.
        if len(args) < 2:  # not a request line: a timeout or a malformed request
            sys.stderr.write(f"{fmt % args}\n")
        elif not str(args[1]).startswith(("2", "3")):
            sys.stderr.write(f"{self.command} {self.path.split('?', 1)[0]} {args[1]}\n")


def configuracion(environ: Mapping[str, str]) -> tuple[str, int]:
    """The public hostname and the port to bind, or a refusal to start."""
    if not environ.get("ARA_MAP_DATABASE_URL"):
        raise SystemExit("Falta ARA_MAP_DATABASE_URL: el servicio hospedado exige Postgres"
                         " y nunca usa un archivo SQLite.")
    host = (environ.get("ARA_MAP_HOST_PUBLICO") or environ.get("RENDER_EXTERNAL_HOSTNAME")
            or "").strip().lower()
    if not _HOST.fullmatch(host):
        raise SystemExit("Falta ARA_MAP_HOST_PUBLICO (sólo el nombre, sin https:// ni ruta):"
                         " es el único host y origen en que confía el servicio.")
    puerto = environ.get("PORT", "10000")
    if not _PUERTO.fullmatch(puerto) or not 0 < int(puerto) < 65536:
        raise SystemExit("PORT no es un puerto válido.")
    return host, int(puerto)


def comprobar_esquema() -> None:
    """Refuse to serve a database this code was not written for. Never migrates:
    scripts/esquema.py does, as an operator step."""
    with postgres.session() as conn:
        version = postgres.schema_version(conn)
    if version != db.SCHEMA_VERSION:
        raise SystemExit(f"La base está en el esquema {version}; este código espera"
                         f" {db.SCHEMA_VERSION}. Ejecuta scripts/esquema.py antes de desplegar.")


def configurar(environ: Mapping[str, str]) -> int:
    """Apply the environment to the handler and the byte store; returns the port."""
    HostedHandler.HOST_PUBLICO, puerto = configuracion(environ)
    # No store is wired by this module alone: file content routes answer 503
    # almacen_no_configurado while every other route keeps working. There is
    # no local-disk store here: the host's disk does not survive a restart.
    api_archivos.configurar_almacen(None)
    return puerto


def serve() -> None:
    puerto = configurar(os.environ)
    comprobar_esquema()
    httpd = ThreadingHTTPServer(("0.0.0.0", puerto), HostedHandler)
    # The platform stops a deployment with SIGTERM; finish what is in flight.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown).start())
    print(f"ARA Map hospedado en el puerto {puerto} para https://{HostedHandler.HOST_PUBLICO}/",
          flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()

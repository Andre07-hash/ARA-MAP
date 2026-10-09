"""Isolated HTTP harness for the 2B attachment handlers (test-only).

HTTP HARNESS EVIDENCE, NOT APPLICATION-MOUNTED ENDPOINT ACCEPTANCE.

- The routes in ``server.api.archivos.RUTAS`` are added to the REAL router
  (``server.app.router``) with their real capabilities for the duration of one
  test, and the previous route table is restored afterwards. ``server/app.py``
  is not modified.
- JSON routes are served by the unmodified ``server.app.Handler`` over a real
  loopback connection: real cookie sessions, the real deny-by-default check,
  capability check, body reading, error envelope and busy handling.
- Binary routes are served by ``HandlerBinario``, which differs from the real
  handler in one method only: a ``RespuestaBinaria`` result is written with its
  own status, content type and headers instead of being JSON-encoded. That is
  the thin adapter whose production equivalent is requested from A
  (INTEGRATION_REQUESTS.md, R-2). Everything before the handler is unchanged.
- The byte store is the accepted ``AlmacenEnMemoria`` (or ``AlmacenLocal``)
  installed through ``server.api.archivos.configurar_almacen``.
"""

from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from server import app as app_module
from server.api import archivos as api
from server.api.binario import RespuestaBinaria


class HandlerBinario(app_module.Handler):
    """The real dispatcher plus the requested RespuestaBinaria adapter."""

    def _send_json(self, payload: Any, status: Any = 200, extra: Any = None) -> None:
        if isinstance(payload, RespuestaBinaria):
            return self._send(payload.status, bytes(payload.cuerpo), payload.tipo,
                              extra=dict(payload.cabeceras))
        return super()._send_json(payload, status, extra)


class Servidor:
    def __init__(self, handler: type) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def cerrar(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=10)


@contextmanager
def rutas_registradas(solo_lectura_exenta: bool = False):
    """Temporarily register the 2B routes on the real router; always restore."""
    anteriores = list(app_module.router._routes)
    for metodo, ruta, handler, capacidad in api.RUTAS:
        app_module.router.add(metodo, ruta, handler, capacidad)
    exentas = app_module.READ_ONLY_POSTS | (api.POSTS_DE_LECTURA if solo_lectura_exenta else set())
    try:
        with patch.object(app_module, "READ_ONLY_POSTS", exentas):
            yield
    finally:
        app_module.router._routes[:] = anteriores


class Cliente:
    """Raw http.client requests: exact bytes and headers, no redirects or decoding."""

    def __init__(self, json_port: int, binario_port: int, timeout: float = 60) -> None:
        self.json_port = json_port
        self.binario_port = binario_port
        self.timeout = timeout

    def pedir(self, metodo: str, ruta: str, *, cookie: str | None = None, cuerpo: Any = None,
              datos: Any = None, cabeceras: dict[str, str] | None = None,
              binario: bool = False) -> tuple[int, dict[str, str], bytes]:
        h = dict(cabeceras or {})
        if cookie:
            h["Cookie"] = cookie
        if datos is not None:
            cuerpo = json.dumps(datos).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        conn = http.client.HTTPConnection("127.0.0.1", self.binario_port if binario else self.json_port,
                                          timeout=self.timeout)
        try:
            conn.request(metodo, ruta, body=cuerpo, headers=h)
            r = conn.getresponse()
            return r.status, {k: v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def json(self, *args: Any, **kwargs: Any) -> tuple[int, Any]:
        status, _h, cuerpo = self.pedir(*args, **kwargs)
        return status, json.loads(cuerpo) if cuerpo else None

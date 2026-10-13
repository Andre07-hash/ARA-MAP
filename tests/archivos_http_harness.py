"""HTTP client and loopback server for the attachment handler tests (test-only).

Since the Round 3 checkpoint C1 the routes, the RespuestaBinaria branch and the
read-only exemption are mounted in ``server/app.py``. This harness therefore
registers nothing and overrides nothing: it starts the unmodified production
``server.app.Handler`` on one loopback port and sends raw requests to it. The
byte store is still chosen by each test through
``server.api.archivos.configurar_almacen`` (a disposable in-memory or temporary
local store); no test uses the application's configured store.
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from typing import Any


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

"""The local web server.

Binds to the loopback interface only and checks the Host header, so nothing on
the network can reach it even if the machine is on shared Wi-Fi.
"""

from __future__ import annotations

import mimetypes
import os
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlsplit

from . import auth, db
from .api import asistente as api_asistente
from .api import bases as api_bases
from .api import carpetas as api_carpetas
from .api import excel as api_excel
from .api import exportar as api_exportar
from .api import importar as api_importar
from .api import inventario as api_inventario
from .api import mapas as api_mapas
from .api import sesion as api_sesion
from .router import Request, Router
from .web_util import ApiError, encode

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
DEFAULT_PORT = 8420
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
# The same machine, as a URL's hostname rather than a Host header (no brackets).
ALLOWED_ORIGIN_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_BODY = 25 * 1024 * 1024

router = Router()
# Anonymous allowlist (auth.PUBLIC_API): these four plus the public catalog.
router.add("GET", "/api/config", api_sesion.config)
router.add("GET", "/api/session", api_sesion.session)
router.add("POST", "/api/login", api_sesion.login)
router.add("POST", "/api/logout", api_sesion.logout)
router.add("GET", "/api/publico/terrenos", api_inventario.public_listing)
router.add("GET", "/api/publico/terrenos/:id", api_inventario.public_detail)
# Everything below requires a signed-in team user.
router.add("GET", "/api/inventario/terrenos", api_inventario.listing)
router.add("POST", "/api/inventario/terrenos", api_inventario.create)
router.add("GET", "/api/inventario/terrenos/:id", api_inventario.detail)
router.add("PATCH", "/api/inventario/terrenos/:id", api_inventario.update)
router.add("GET", "/api/inventario/terrenos/:id/historial", api_inventario.history)
router.add("GET", "/api/excel/fuentes", api_excel.listing)
router.add("POST", "/api/excel/fuentes", api_excel.create)
router.add("POST", "/api/excel/vista-previa", api_excel.preview)
router.add("GET", "/api/excel/fuentes/:id", api_excel.detail)
router.add("GET", "/api/excel/fuentes/:id/versiones", api_excel.versions)
router.add("GET", "/api/excel/fuentes/:id/versiones/:vid", api_excel.version_detail)
router.add("POST", "/api/excel/fuentes/:id/actualizar", api_excel.refresh)
router.add("POST", "/api/excel/fuentes/:id/configuracion", api_excel.configure)
router.add("POST", "/api/excel/fuentes/:id/desconectar", api_excel.disconnect)
router.add("POST", "/api/excel/fuentes/:id/reconectar", api_excel.reconnect)
router.add("GET", "/api/bases", api_bases.listing)
router.add("GET", "/api/bases/:id", api_bases.detail)
router.add("GET", "/api/bases/:id/terrenos", api_bases.terrenos)
router.add("POST", "/api/bases/:id/terrenos", api_bases.add_terreno)
router.add("PATCH", "/api/bases/:id", api_bases.rename)
router.add("PATCH", "/api/bases/:id/carpeta", api_bases.move)
router.add("DELETE", "/api/bases/:id", api_bases.remove)
router.add("POST", "/api/bases/:id/adjuntar", api_importar.append)
router.add("POST", "/api/importar/vista-previa", api_importar.preview)
router.add("POST", "/api/importar/confirmar", api_importar.confirm)
router.add("POST", "/api/importar/analizar", api_asistente.analizar)
router.add("POST", "/api/importar/preparar", api_asistente.preparar)
router.add("GET", "/api/formatos", api_asistente.formatos)
router.add("PATCH", "/api/formatos/:id", api_asistente.renombrar_formato)
router.add("DELETE", "/api/formatos/:id", api_asistente.eliminar_formato)
router.add("GET", "/api/mapas", api_mapas.listing)
router.add("POST", "/api/mapas", api_mapas.create)
router.add("GET", "/api/mapas/:id", api_mapas.detail)
router.add("GET", "/api/mapas/:id/terrenos", api_mapas.terrenos)
router.add("POST", "/api/mapas/:id/actualizar", api_mapas.refresh)
router.add("POST", "/api/mapas/combinar/vista-previa", api_mapas.plan_merge)
router.add("POST", "/api/mapas/combinar", api_mapas.merge)
router.add("PATCH", "/api/mapas/:id", api_mapas.update)
router.add("PATCH", "/api/mapas/:id/carpeta", api_mapas.move)
router.add("DELETE", "/api/mapas/:id", api_mapas.remove)
router.add("POST", "/api/exportar", api_exportar.export)
router.add("GET", "/api/carpetas", api_carpetas.listing)
router.add("POST", "/api/carpetas", api_carpetas.create)
router.add("PATCH", "/api/carpetas/:id", api_carpetas.rename)
router.add("DELETE", "/api/carpetas/:id", api_carpetas.remove)

# POSTs that only read: allowed in read-only mode.
READ_ONLY_POSTS = {"/api/exportar"}


class Handler(BaseHTTPRequestHandler):
    """Serves the JSON API and the static app, loopback only."""

    server_version = "ARAMap"
    protocol_version = "HTTP/1.1"
    # The cloud adapter (api/index.py) sets this: HTTPS, Secure cookies.
    CLOUD = False

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args: Any) -> None:
        # The console is the user's launcher window; keep it to real problems.
        if not str(args[1] if len(args) > 1 else "").startswith(("2", "3")):
            sys.stderr.write(f"  {fmt % args}\n")

    def _dispatch(self, method: str) -> None:
        if not self._host_is_local():
            return self._send(HTTPStatus.FORBIDDEN, b"Forbidden", "text/plain")
        if method != "GET" and not self._origin_is_local():
            return self._send_json(
                {"error": "Petición rechazada: origen externo."}, HTTPStatus.FORBIDDEN
            )
        # Read-only mode already opens the database read-only; refusing the
        # write here turns what would be a 500 into a clear answer.
        path = self.path.split("?", 1)[0]
        if (os.environ.get("ARA_MAP_READ_ONLY") == "1" and method != "GET"
                and path not in READ_ONLY_POSTS):
            return self._send_json(
                {"error": "ARA Map está en modo de solo consulta."}, HTTPStatus.FORBIDDEN
            )

        # Deny by default, before routing, so an unknown /api path can never
        # reach a fallback anonymously. Normalized exactly as the router does.
        api_path = urlparse(self.path).path.rstrip("/") or "/"
        user = None
        if auth.is_api(api_path):
            public = auth.is_public(method, api_path)
            token = auth.token_from_cookie(self.headers.get("Cookie"))
            if token is None and not public:
                return self._unauthenticated()
            ready = self._database_ready()
            if not ready and api_path != "/api/config":
                self.close_connection = True
                return self._send_json(
                    {"error": "La base compartida no está configurada."}, HTTPStatus.SERVICE_UNAVAILABLE)
            if token is not None and ready:
                with db.session() as conn:
                    user = auth.user_for_token(conn, token)
            if user is None and not public:
                return self._unauthenticated()

        handler, context = router.resolve(method, self.path)
        if handler is None:
            # Only page requests fall back to the app shell. An unknown /api
            # path must fail loudly instead of quietly returning HTML.
            is_api = self.path.split("?", 1)[0].startswith("/api/")
            if method == "GET" and not is_api:
                return self._serve_static()
            status = HTTPStatus.METHOD_NOT_ALLOWED if context else HTTPStatus.NOT_FOUND
            return self._send_json({"error": "Ruta no encontrada."}, status)

        try:
            request = Request(
                method=method, path=context["path"], query=context["query"],
                params=context["params"], body=self._read_body(), headers=self.headers,
                user=user, cloud=self.CLOUD,
            )
            result = handler(request)
        except ApiError as exc:
            if exc.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE:
                self.close_connection = True  # the body was never read
            return self._send_json({"error": exc.mensaje, "detalle": exc.detalle}, exc.status)
        except Exception:  # noqa: BLE001 - logged here, never sent to the caller
            import traceback
            traceback.print_exc()
            self.close_connection = True
            return self._send_json(
                {"error": "Ocurrió un error inesperado. Inténtalo de nuevo; si se repite,"
                          " avisa al equipo.", "detalle": {"code": "internal"}},
                HTTPStatus.INTERNAL_SERVER_ERROR
            )

        if isinstance(result, tuple):  # a file download
            payload, filename = result
            return self._send(
                HTTPStatus.OK, payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                extra={"Content-Disposition": f'attachment; filename="{filename}"',
                       "Cache-Control": "no-store"},
            )
        return self._send_json(result, extra=request.response_headers)

    def _unauthenticated(self) -> None:
        # The body may be unread; do not let it be parsed as the next request.
        self.close_connection = True
        return self._send_json(
            {"error": "Inicia sesión para continuar.", "detalle": {"code": "unauthenticated"}},
            HTTPStatus.UNAUTHORIZED)

    def _database_ready(self) -> bool:
        """Locally the SQLite file is always there; the cloud needs Postgres."""
        return True

    def _host_is_local(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ALLOWED_HOSTS or host == ""

    def _origin_is_local(self) -> bool:
        """Reject writes initiated by a page on another site.

        The Host check above stops another machine reaching this server, but not
        a website the user happens to have open: the browser sends that
        cross-site request with a correct Host. A simple POST needs no preflight,
        so without this an unrelated page could delete a base or re-snapshot a
        saved map. Requests with no Origin at all -- curl, the e2e suite, a
        same-origin navigation -- are left alone.
        """
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return (urlsplit(origin).hostname or "") in ALLOWED_ORIGIN_HOSTS

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError("La petición es demasiado grande.", 413)
        return self.rfile.read(length) if length else b""

    def _serve_static(self) -> None:
        relative = unquote(self.path.split("?", 1)[0]).lstrip("/") or "index.html"
        target = (WEB_ROOT / relative).resolve()

        if not target.is_relative_to(WEB_ROOT):  # path traversal
            return self._send(HTTPStatus.FORBIDDEN, b"Forbidden", "text/plain")
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            target = WEB_ROOT / "index.html"  # single-page app fallback
        if not target.is_file():
            return self._send(HTTPStatus.NOT_FOUND, b"No encontrado", "text/plain")

        content_type, _ = mimetypes.guess_type(target.name)
        return self._send(
            HTTPStatus.OK, target.read_bytes(), content_type or "application/octet-stream",
            extra={"Cache-Control": "no-cache"},
        )

    def _send_json(self, payload: Any, status: HTTPStatus | int = HTTPStatus.OK,
                   extra: dict[str, str] | None = None) -> None:
        # API answers depend on who is asking and on the latest commit: never cache.
        self._send(status, encode(payload), "application/json; charset=utf-8",
                   extra={"Cache-Control": "no-store", **(extra or {})})

    def _send(
        self,
        status: HTTPStatus | int,
        payload: bytes,
        content_type: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)


def find_port(preferred: int = DEFAULT_PORT) -> int:
    """The first free port at or after the preferred one."""
    for port in range(preferred, preferred + 20):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("No se encontró un puerto libre.")


def serve(port: int | None = None, open_browser: bool = True) -> None:
    """Start the server and, unless told otherwise, open a browser at it."""
    db.connect().close()  # create/migrate before the first request
    port = port or find_port()
    url = f"http://localhost:{port}/"
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    print(f"\n  ARA Map  ->  {url}")
    print(f"  Datos:   {db.db_path()}")
    print("  Para cerrar, presiona Ctrl+C o cierra esta ventana.\n")

    if open_browser:
        threading.Timer(0.6, webbrowser.open, args=[url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Cerrando ARA Map.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()

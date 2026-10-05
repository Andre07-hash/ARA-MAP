"""Vercel entry point backed by the shared Postgres workspace."""

import os
from urllib.parse import urlsplit

if os.environ.get("DATABASE_URL"):
    os.environ.setdefault("ARA_MAP_DATABASE_URL", os.environ["DATABASE_URL"])

from server import cloud_auth, postgres
from server.app import Handler
from server.web_util import ApiError, encode, parse_json


class handler(Handler):
    def _host_is_local(self):
        return True

    def _origin_is_local(self):
        origin = self.headers.get("Origin")
        return not origin or urlsplit(origin).netloc == self.headers.get("Host")

    def _dispatch(self, method):
        path = urlsplit(self.path).path
        editor = cloud_auth.authenticated(self.headers.get("Cookie", ""))
        if path == "/api/config" and method == "GET":
            return self._send_json({"readOnly": not editor, "cloud": True,
                                    "authRequired": not cloud_auth.public_edit(),
                                    "maxUploadBytes": 4 * 1024 * 1024})
        if method != "GET" and not self._origin_is_local():
            self.close_connection = True
            return self._send_json({"error": "Petición rechazada: origen externo."}, 403)
        if path in {"/api/login", "/api/logout"} and method == "POST":
            try:
                if path == "/api/logout":
                    value, age = "", 0
                else:
                    payload = parse_json(self._read_body())
                    if not cloud_auth.password_matches(str(payload.get("password", ""))):
                        return self._send_json({"error": "Contraseña incorrecta."}, 401)
                    value, age = cloud_auth.session_token(), cloud_auth.SESSION_SECONDS
                return self._send(200, encode({"ok": True}), "application/json",
                                  {"Set-Cookie": cloud_auth.cookie(value, age)})
            except ApiError as error:
                self.close_connection = True
                return self._send_json({"error": error.mensaje}, error.status)
        # Import configuration is for editors, even to read.
        privado = path.startswith(("/api/formatos", "/api/importar/"))
        if (method != "GET" or privado) and path != "/api/exportar" and not editor:
            self.close_connection = True
            return self._send_json({"error": "Inicia sesión para editar el espacio compartido."}, 401)
        if not postgres.enabled():
            self.close_connection = True
            return self._send_json({"error": "La base compartida no está configurada."}, 503)
        return super()._dispatch(method)

    def _read_body(self):
        if int(self.headers.get("Content-Length") or 0) > 4 * 1024 * 1024:
            raise ApiError("El archivo supera el límite de 4 MB de la versión web.", 413)
        return super()._read_body()

    def _send(self, status, payload, content_type, extra=None):
        return super()._send(status, payload, content_type,
                             {"Cache-Control": "no-store", **(extra or {})})

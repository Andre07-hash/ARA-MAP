"""Vercel entry point backed by the shared Postgres workspace.

Authentication and the public/private route policy are NOT decided here: they
live in server.app.Handler (server/auth.py), shared with the local server. This
adapter only states what differs in the cloud: any Host, same-host Origin for
writes, HTTPS (Secure cookies), a 4 MB body limit and Postgres being required.
"""

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if os.environ.get("DATABASE_URL"):
    os.environ.setdefault("ARA_MAP_DATABASE_URL", os.environ["DATABASE_URL"])

from server import postgres
from server.app import Handler
from server.web_util import ApiError

MAX_BODY = 4 * 1024 * 1024


class handler(Handler):
    CLOUD = True

    def _host_is_local(self):
        return True

    def _origin_is_local(self):
        origin = self.headers.get("Origin")
        return not origin or urlsplit(origin).netloc == self.headers.get("Host")

    def _dispatch(self, method):
        # Vercel forwards the :path* rewrite capture as query metadata. It is
        # transport information, not an inventory filter. Remove only the
        # matching capture; unknown or conflicting application filters still
        # reach normal validation.
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/api/"):
            captured = parsed.path[len("/api/"):].strip("/")
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            filtered = [(key, value) for key, value in pairs
                        if not (key == "path" and value.strip("/") == captured)]
            if len(filtered) != len(pairs):
                self.path = urlunsplit(parsed._replace(query=urlencode(filtered)))
        if method != "GET" and not self._origin_is_local():
            self.close_connection = True
            return self._send_json({"error": "Petición rechazada: origen externo."}, 403)
        return super()._dispatch(method)

    def _database_ready(self):
        # Never fall back to a local SQLite file in the cloud.
        return postgres.enabled()

    def _read_body(self):
        if int(self.headers.get("Content-Length") or 0) > MAX_BODY:
            raise ApiError("El archivo supera el límite de 4 MB de la versión web.", 413)
        return super()._read_body()

    def _send(self, status, payload, content_type, extra=None):
        return super()._send(status, payload, content_type,
                             {"Cache-Control": "no-store", **(extra or {})})

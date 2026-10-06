"""A local stand-in for Microsoft's identity platform, Graph and the
pre-authenticated download host, for tests only (127.0.0.1).

It enforces what the real services enforce that matters here: client
credentials, redirect URI, single-use codes, PKCE S256, bearer tokens,
revocation (invalid_grant), 302 downloads to another path, and Retry-After
throttling. It records whether a bearer token ever reached the download host.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tests.excel_support import Archivo


class FakeMicrosoft:
    def __init__(self, client_id: str = "cliente-ficticio", secret: str = "secreto-ficticio-123") -> None:
        self.client_id, self.secret = client_id, secret
        self.usuarios: dict[str, dict[str, Any]] = {}
        self.codigos: dict[str, dict[str, Any]] = {}
        self.accesos: dict[str, str] = {}
        self.renovaciones: dict[str, str] = {}
        self.archivos: dict[tuple[str, str], Archivo] = {}
        self.carpetas: dict[str, list[dict[str, Any]]] = {}
        self.descargas_con_bearer = 0
        self.descargas = 0
        self.cola_status: list[tuple[int, dict[str, str]]] = []  # forced next Graph answers
        self.redirigir_a: str | None = None
        self.renovaciones_usadas = 0
        self.retraso = 0.0   # seconds each download takes (browser tests watch a run in progress)
        self.usuario_navegador: str | None = None   # who "signs in" at the browser authorize page
        self.lock = threading.Lock()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def do_GET(self) -> None:
                fake._get(self)

            def do_POST(self) -> None:
                fake._post(self)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.host = f"127.0.0.1:{self.httpd.server_port}"
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()

    def cerrar(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    # -- set-up helpers -------------------------------------------------------
    def usuario(self, clave: str, nombre: str, tipo: str = "personal") -> dict[str, Any]:
        u = {"id": f"id-{clave}", "nombre": nombre, "correo": f"{clave}@example.com",
             "drive_type": tipo, "drive_id": f"drive-{clave}", "revocado": False}
        self.usuarios[clave] = u
        return u

    def archivo(self, usuario: str, item_id: str, nombre: str, contenido: bytes) -> Archivo:
        u = self.usuarios[usuario]
        a = Archivo(contenido, nombre)
        self.archivos[(u["drive_id"], item_id)] = a
        self.carpetas.setdefault(u["drive_id"], []).append({"id": item_id, "name": nombre})
        return a

    def autorizar(self, url: str, usuario: str) -> dict[str, str]:
        """What the browser would bring back: Microsoft's redirect query."""
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        assert q["client_id"] == self.client_id and q["code_challenge_method"] == "S256"
        assert q["response_mode"] == "query" and "offline_access" in q["scope"]
        codigo = secrets.token_urlsafe(24)
        self.codigos[codigo] = {"reto": q["code_challenge"], "redirect": q["redirect_uri"], "usuario": usuario}
        return {"code": codigo, "state": q["state"]}

    # -- HTTP -------------------------------------------------------------------
    def _enviar(self, h: BaseHTTPRequestHandler, status: int, cuerpo: Any = None,
                cabeceras: dict[str, str] | None = None) -> None:
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo or {}).encode()
        h.send_response(status)
        for k, v in (cabeceras or {}).items():
            h.send_header(k, v)
        h.send_header("Content-Length", str(len(datos)))
        h.end_headers()
        h.wfile.write(datos)

    def _post(self, h: BaseHTTPRequestHandler) -> None:
        if h.path == "/_control":
            return self._control(h)
        if not h.path.endswith("/oauth2/v2.0/token"):
            return self._enviar(h, 404)
        datos = dict(urllib.parse.parse_qsl(h.rfile.read(int(h.headers["Content-Length"])).decode()))
        if datos.get("client_id") != self.client_id or datos.get("client_secret") != self.secret:
            return self._enviar(h, 401, {"error": "invalid_client"})
        with self.lock:
            if datos.get("grant_type") == "authorization_code":
                c = self.codigos.pop(datos.get("code", ""), None)
                verif = datos.get("code_verifier", "")
                reto = base64.urlsafe_b64encode(hashlib.sha256(verif.encode()).digest()).rstrip(b"=").decode()
                if c is None or c["reto"] != reto or c["redirect"] != datos.get("redirect_uri"):
                    return self._enviar(h, 400, {"error": "invalid_grant"})
                usuario = c["usuario"]
            elif datos.get("grant_type") == "refresh_token":
                usuario = self.renovaciones.get(datos.get("refresh_token", ""))
                self.renovaciones_usadas += 1
                if usuario is None:
                    return self._enviar(h, 400, {"error": "invalid_grant"})
            else:
                return self._enviar(h, 400, {"error": "unsupported_grant_type"})
            if self.usuarios[usuario]["revocado"]:
                return self._enviar(h, 400, {"error": "invalid_grant"})
            acceso, renovacion = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
            self.accesos[acceso] = usuario
            self.renovaciones[renovacion] = usuario
        return self._enviar(h, 200, {"access_token": acceso, "refresh_token": renovacion, "expires_in": 3600})

    def _control(self, h: BaseHTTPRequestHandler) -> None:
        """Browser tests change the fake world here: the workbook's rows, a
        revoked grant, the next Graph answers."""
        from tests.excel_support import fila, libro
        orden = json.loads(h.rfile.read(int(h.headers["Content-Length"])))
        if "filas" in orden:
            a = self.archivos[(self.usuarios[orden["usuario"]]["drive_id"], orden["item"])]
            a.poner(libro([fila(*f) for f in orden["filas"]]))
        if "revocado" in orden:
            self.usuarios[orden["usuario"]]["revocado"] = bool(orden["revocado"])
        if "navegador" in orden:
            self.usuario_navegador = orden["navegador"]
        if "retraso" in orden:
            self.retraso = float(orden["retraso"])
        if "cola_status" in orden:
            self.cola_status[:] = [(int(st), {"Retry-After": "0"}) for st in orden["cola_status"]]
        return self._enviar(h, 200, {"ok": True})

    def _get(self, h: BaseHTTPRequestHandler) -> None:
        partes = urllib.parse.urlsplit(h.path)
        if partes.path.endswith("/oauth2/v2.0/authorize"):
            # The browser's sign-in page: approves at once as usuario_navegador.
            url = f"http://{self.host}{h.path}"
            if self.usuario_navegador is None:
                q = dict(urllib.parse.parse_qsl(partes.query))
                destino = q["redirect_uri"] + "?" + urllib.parse.urlencode(
                    {"error": "access_denied", "state": q.get("state", "")})
            else:
                q = dict(urllib.parse.parse_qsl(partes.query))
                destino = q["redirect_uri"] + "?" + urllib.parse.urlencode(self.autorizar(url, self.usuario_navegador))
            return self._enviar(h, 302, b"", {"Location": destino})
        if partes.path.startswith("/descarga/"):
            if self.retraso:
                time.sleep(self.retraso)
            self.descargas += 1
            if h.headers.get("Authorization"):
                self.descargas_con_bearer += 1
            clave = tuple(urllib.parse.unquote(partes.path[len("/descarga/"):]).split("|", 1))
            a = self.archivos.get(clave)  # type: ignore[arg-type]
            return self._enviar(h, 200 if a else 404, a.contenido if a else b"")
        if not partes.path.startswith("/graph/v1.0"):
            return self._enviar(h, 404)
        if self.cola_status:
            status, cab = self.cola_status.pop(0)
            return self._enviar(h, status, {"error": {"code": "forced"}}, cab)
        bearer = (h.headers.get("Authorization") or "").removeprefix("Bearer ")
        usuario = self.accesos.get(bearer)
        if usuario is None or self.usuarios[usuario]["revocado"]:
            return self._enviar(h, 401, {"error": {"code": "InvalidAuthenticationToken"}})
        u = self.usuarios[usuario]
        ruta = urllib.parse.unquote(partes.path[len("/graph/v1.0"):])
        if ruta == "/me":
            return self._enviar(h, 200, {"id": u["id"], "displayName": u["nombre"], "mail": u["correo"]})
        if ruta == "/me/drive":
            return self._enviar(h, 200, {"id": u["drive_id"], "driveType": u["drive_type"]})
        if ruta == "/me/drive/root/children" or ruta.startswith("/me/drive/root/search"):
            valores = [{"id": f["id"], "name": f["name"], "file": {}, "size": 1,
                        "parentReference": {"driveId": u["drive_id"]}} for f in self.carpetas.get(u["drive_id"], [])]
            valores.append({"id": "carpeta-1", "name": "Documentos", "folder": {"childCount": 0},
                            "parentReference": {"driveId": u["drive_id"]}})
            valores.append({"id": "pdf-1", "name": "nota.pdf", "file": {}, "parentReference": {"driveId": u["drive_id"]}})
            return self._enviar(h, 200, {"value": valores})
        if ruta.startswith("/drives/"):
            _, _, drive, _, resto = ruta.split("/", 4)
            item, _, sufijo = resto.partition("/")
            a = self.archivos.get((drive, item))
            if drive != u["drive_id"] or a is None:
                return self._enviar(h, 404, {"error": {"code": "itemNotFound"}})
            if sufijo == "content":
                destino = self.redirigir_a or f"http://{self.host}/descarga/{urllib.parse.quote(drive + '|' + item)}"
                if a.cambiar_durante_descarga:
                    a.cambiar_durante_descarga -= 1
                    a.revision += 1
                return self._enviar(h, 302, b"", {"Location": destino})
            return self._enviar(h, 200, {
                "id": item, "name": a.nombre, "eTag": f'"e{a.revision}"', "cTag": f'"c{a.revision}"',
                "size": len(a.contenido), "lastModifiedDateTime": "2026-10-06T12:00:00Z", "file": {},
                "lastModifiedBy": {"user": {"displayName": "Empleado Ficticio"}},
                "webUrl": f"https://onedrive.live.com/edit?id={item}"})
        return self._enviar(h, 404, {"error": {"code": "notFound"}})

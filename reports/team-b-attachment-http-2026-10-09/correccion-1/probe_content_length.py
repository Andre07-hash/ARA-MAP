"""Probe the unmodified shared dispatcher's Content-Length parsing (A-owned).

    PYTHONPATH=<tree> python3 probe_content_length.py

Starts the real ``server.app.Handler`` on loopback with a throwaway SQLite
database and sends anonymous POSTs to the public ``/api/login`` route with
Content-Length values that ``int()`` either rejects or accepts unexpectedly.
Nothing is patched; each line printed is one observation (JSON).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

# (name, Content-Length, bytes sent after the headers, half-close?, seconds to wait)
PRUEBAS = [
    ("superscript_two", "²", b"{}", False, 30),
    # 26 MiB > MAX_BODY (25 MiB). A dispatcher 413 would come before reading;
    # login's own size check answering instead means the body was buffered.
    ("negative_one_then_half_close", "-1", b"x" * (26 * 1024 * 1024), True, 60),
    # Without a half-close the server keeps reading: no answer within 5 s.
    ("negative_one_kept_open", "-1", b"{}", False, 5),
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ARA_MAP_DB"] = str(Path(tmp) / "probe.db")
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        from server import app, db

        db.connect().close()  # creates the schema
        app.Handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        try:
            for nombre, longitud, cuerpo, medio_cierre, espera in PRUEBAS:
                with socket.create_connection(("127.0.0.1", port), timeout=espera) as s:
                    cabecera = ("POST /api/login HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                "Content-Type: application/json\r\n"
                                f"Content-Length: {longitud}\r\n\r\n").encode("latin-1")
                    s.sendall(cabecera + cuerpo)
                    if medio_cierre:
                        s.shutdown(socket.SHUT_WR)
                    datos = b""
                    try:
                        while True:
                            parte = s.recv(65536)
                            if not parte:
                                break
                            datos += parte
                            if b"\r\n\r\n" in datos and not medio_cierre:
                                break
                    except socket.timeout:
                        datos += b"(no response within %d s)" % espera
                    linea = datos.split(b"\r\n", 1)[0].decode("latin-1")
                    cuerpo_resp = datos.split(b"\r\n\r\n", 1)[1][:200] if b"\r\n\r\n" in datos else b""
                    print(json.dumps({"probe": nombre, "content_length": longitud,
                                      "bytes_sent_after_headers": len(cuerpo),
                                      "status_line": linea,
                                      "body_start": cuerpo_resp.decode("utf-8", "replace")},
                                     ensure_ascii=True))
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    main()

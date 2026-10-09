"""Reproducer for request R-5 (A-owned dispatcher, server/app.py).

    PYTHONPATH=. python3 reports/team-b-attachment-http-2026-10-09/reproduce_read_only_keepalive.py

In read-only mode the dispatcher refuses a non-GET request with 403 WITHOUT
reading its body and WITHOUT setting close_connection. On a keep-alive
connection the unread body is then parsed as the next request line. The
other early refusals (401, the capability 403, 413) already set
close_connection for exactly this reason. Fictional data; no route needed.
"""

from __future__ import annotations

import os
import re
import socket
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["ARA_MAP_DB"] = str(Path(tempfile.mkdtemp()) / "repro.db")
from server import app, db  # noqa: E402

db.connect().close()                      # create the schema before read-only mode
os.environ["ARA_MAP_READ_ONLY"] = "1"
app.Handler.log_message = lambda *a: None
httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

cuerpo = b"GET /api/config HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"   # smuggled as a "body"
peticion = (b"POST /api/logout HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: text/plain\r\n"
            b"Content-Length: " + str(len(cuerpo)).encode() + b"\r\n\r\n" + cuerpo)
with socket.create_connection(("127.0.0.1", httpd.server_address[1]), timeout=5) as sock:
    sock.sendall(peticion)
    sock.settimeout(2)
    datos = b""
    try:
        while True:
            parte = sock.recv(65536)
            if not parte:
                break
            datos += parte
    except socket.timeout:
        pass
respuestas = datos.count(b"HTTP/1.1 ")
print({"responses_on_one_connection": respuestas,
       "status_lines": [m.decode() for m in re.findall(rb"HTTP/1\.1 \d{3} [A-Za-z ]+", datos)]})
print("DEFECT REPRODUCED: the unread body was served as a second request" if respuestas > 1
      else "not reproduced: the connection closed after the refusal")
httpd.shutdown()

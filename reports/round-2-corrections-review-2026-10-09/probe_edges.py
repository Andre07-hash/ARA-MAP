"""Supervisor-only probes. PYTHONPATH must select an exact review archive.

Usage: python probe_edges.py framing | privacy sqlite | privacy postgres
Only loopback servers, synthetic data and disposable test schemas are used.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


def framing():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["ARA_MAP_DB"] = str(Path(directory) / "fictional.db")
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        from server import app, db
        db.connect().close()
        with patch.object(app.Handler, "log_message", lambda *args: None):
            server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            public = b"GET /api/config HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
            cases = {
                "superscript_header_only": (b"Content-Length: \xb2", b""),
                "negative_header_only": (b"Content-Length: -1", b""),
                "over_limit_header_only": (b"Content-Length: 27262976", b""),
                "conflicting_lengths": (b"Content-Length: 0\r\nContent-Length: "
                                        + str(len(public)).encode(), public),
                "empty_length": (b"Content-Length: ", public),
                "empty_then_chunked_encoding": (b"Content-Length: 0\r\nTransfer-Encoding: "
                                                 b"\r\nTransfer-Encoding: chunked", public),
            }
            try:
                for label, (headers, body) in cases.items():
                    with socket.create_connection(server.server_address, timeout=2) as sock:
                        sock.sendall(b"POST /api/login HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                     + headers + b"\r\n\r\n" + body)
                        response, closed = b"", False
                        try:
                            while True:
                                chunk = sock.recv(65536)
                                if not chunk:
                                    closed = True
                                    break
                                response += chunk
                        except socket.timeout:
                            pass
                    print(json.dumps({"case": label, "statuses": [int(x) for x in re.findall(
                        rb"HTTP/1\.[01] (\d{3})", response)], "closed": closed,
                        "sent_body_bytes": len(body)}), flush=True)
            finally:
                server.shutdown()
                server.server_close()


def privacy(backend):
    from tests.test_archivos import AttachmentLifecycleSQLite, AttachmentLifecyclePostgres, PDF
    cls = AttachmentLifecyclePostgres if backend == "postgres" else AttachmentLifecycleSQLite
    cls.setUpClass()
    case = cls("test_l2_pending_privacy_is_one_rule_on_every_read_surface")
    case.setUp()
    counter = 0

    def collision_uuid():
        nonlocal counter
        counter += 1
        # Unique valid UUIDs, with the public ID containing the hidden byte count.
        return uuid.UUID(f"{len(PDF):08d}-0000-4000-8000-{counter:012x}")

    try:
        with patch("uuid.uuid4", side_effect=collision_uuid):
            try:
                case.test_l2_pending_privacy_is_one_rule_on_every_read_surface()
                print(json.dumps({"backend": backend, "result": "pass"}))
            except AssertionError as exc:
                print(json.dumps({"backend": backend, "result": "assertion_failure",
                                  "message": str(exc)}))
    finally:
        case.doCleanups()
        cls.tearDownClass()


if sys.argv[1] == "framing":
    framing()
else:
    privacy(sys.argv[2])

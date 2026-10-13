"""Request-boundary probe; local ephemeral server, public /config only."""
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import threading
from http.server import ThreadingHTTPServer

with tempfile.TemporaryDirectory() as scratch:
    os.environ['ARA_MAP_DB'] = str(Path(scratch) / 'fictional.db')
    os.environ.pop('ARA_MAP_DATABASE_URL', None)
    from server import app, db
    db.connect().close()
    app.Handler.log_message = lambda *args: None
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        for case in ['read_only', 'foreign_origin', 'bad_host']:
            os.environ['ARA_MAP_READ_ONLY'] = '1' if case == 'read_only' else '0'
            body = b'GET /api/config HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n'
            host = b'example.invalid' if case == 'bad_host' else b'127.0.0.1'
            origin = b'Origin: https://example.invalid\r\n' if case == 'foreign_origin' else b''
            request = (b'POST /api/logout HTTP/1.1\r\nHost: ' + host + b'\r\n' + origin
                       + b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
            with socket.create_connection(httpd.server_address, timeout=3) as sock:
                sock.sendall(request)
                data = b''
                try:
                    while chunk := sock.recv(65536):
                        data += chunk
                except socket.timeout:
                    pass
            print(json.dumps({'case': case, 'statuses': [int(x) for x in re.findall(
                rb'HTTP/1\.1 (\d{3})', data)]}))
    finally:
        httpd.shutdown()
        httpd.server_close()

"""Serve the real Vercel handler on 127.0.0.1:8471 against a disposable Postgres. Dry run only."""
import os, sys
from http.server import ThreadingHTTPServer
ROOT = "/Users/andrejasso/Desktop/ARA Map"
sys.path.insert(0, ROOT); os.chdir(ROOT)
assert "127.0.0.1:54329" in os.environ["ARA_MAP_DATABASE_URL"]
from server import postgres
from api.index import handler
with postgres.session() as c:
    c.raw.execute(postgres.schema_sql(), prepare=False)
    postgres.migrate(c)
    if not c.execute("SELECT COUNT(*) FROM base").fetchone()[0]:
        c.execute("INSERT INTO base (nombre, importado_en) VALUES ('Base preexistente', '2026-09-01')")
print("ready", flush=True)
ThreadingHTTPServer(("127.0.0.1", 8471), handler).serve_forever()

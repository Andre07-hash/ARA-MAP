"""The supervisor's ``unbounded_list`` probe, adapted to the paged ``listar``.

The reviewed probe measured ``len(listar(...))`` on the old list result. The
corrected service returns one bounded page plus a cursor, so this variant
reports page sizes instead. Fictional data only; never point it at production.

Usage: PYTHONPATH=. python3 reports/team-b-attachment-lifecycle-2026-10-08/\
corrections-2026-10-09/probe_paged_listing.py [sqlite|postgres]
Postgres requires ARA_MAP_TEST_DATABASE_URL pointing to a disposable UTF-8 DB.
"""
import json
import sys

from server import archivos
from tests.test_archivos import PDF, AttachmentLifecyclePostgres, AttachmentLifecycleSQLite


def paged_list(t):
    for i in range(105):
        started = t.start(PDF, key=str(i))
        archivos.cancelar(t.sessions["ana"], started["version_id"], bd=t.database,
                          reloj=t.clock)
    pages, cursor = [], None
    while True:
        page = archivos.listar(t.sessions["ana"], t.terrain, cursor=cursor,
                               bd=t.database, reloj=t.clock)
        pages.append(len(page["archivos"]))
        cursor = page["cursor_siguiente"]
        if cursor is None:
            return {"default_page_sizes": pages, "total": sum(pages)}


if __name__ == "__main__":
    backend = sys.argv[1] if len(sys.argv) > 1 else "sqlite"
    cls = AttachmentLifecyclePostgres if backend == "postgres" else AttachmentLifecycleSQLite
    if backend == "postgres":
        cls.setUpClass()
    try:
        fixture = cls()
        fixture.setUp()
        try:
            print(json.dumps({"backend": backend, "probe": "paged_list",
                              "observed": paged_list(fixture)}))
        finally:
            fixture.doCleanups()
    finally:
        if backend == "postgres":
            cls.tearDownClass()

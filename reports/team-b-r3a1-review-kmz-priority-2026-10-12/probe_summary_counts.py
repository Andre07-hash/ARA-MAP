"""Supervisor probe: count old/new summaries on the same synthetic fixture."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root))
    use_postgres = "--postgres" in sys.argv[2:]
    if use_postgres:
        target = os.environ.get("ARA_MAP_TEST_DATABASE_URL", "")
        if urlsplit(target).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise SystemExit("This probe requires a disposable loopback Postgres target.")
    from tests.test_resumenes_lote import ResumenesLotePostgres, ResumenesLoteSQLite

    fixture_class = ResumenesLotePostgres if use_postgres else ResumenesLoteSQLite
    if use_postgres:
        fixture_class.setUpClass()
    fixture = fixture_class()
    output = {"backend": "postgres" if use_postgres else "sqlite", "service_counts": {}}
    try:
        fixture.setUp()
        ids = fixture._terrenos_extra(200)
        for account in ("ana", "olga"):
            rows = {}
            for n in (1, 50, 100, 200):
                rows[n] = {
                    "before": fixture.contar(fixture.anterior, ids[:n], fixture.s[account]),
                    "after": fixture.contar(fixture.nuevo, ids[:n], fixture.s[account]),
                }
            output["service_counts"]["admin" if account == "ana" else "operator"] = rows
        print(json.dumps(output, indent=2))
    finally:
        fixture.doCleanups()
        if use_postgres:
            fixture_class.tearDownClass()


if __name__ == "__main__":
    main()

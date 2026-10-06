#!/usr/bin/env python3
"""Build a FICTIONAL production-shaped schema-7 Postgres workspace through the
frozen PRE-CHANGE code (verification/baseline_src, schema 7): 3 bases with
104 terrains in total and 2 saved maps (one simple, one comparison), matching
the counts read from production on 2026-10-05. No production data is used.

    python3 build_v7_workspace.py --url-env REHEARSAL_DATABASE_URL

Refuses any target that is not a loopback disposable cluster.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
LEGACY = HERE.parents[1] / "inventory-developer-handoff-2026-10-05" / "verification" / "legacy"
sys.path.insert(0, str(LEGACY))
import build_legacy_v7 as B  # noqa: E402  (loads the baseline v7 modules)

SPECS = [  # tag, terrains, estado, municipio, lat, lon, price mode
    ("P1", 40, "Jalisco", "Zapopan", 20.70, -103.40, "usd"),
    ("P2", 36, "Querétaro", "El Marqués", 20.60, -100.30, "mxn"),
    ("P3", 28, "Guanajuato", "León", 21.10, -101.70, "unknown"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url-env", required=True)
    url = os.environ[ap.parse_args().url_env]
    if urlsplit(url).hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("REFUSING: only a loopback disposable Postgres")
    B.verify_baseline()
    mods = B.load_baseline()
    db, validation, TerrainRecord, _fold, bases, _carpetas, _formatos, mapas, terrenos = mods
    os.environ["ARA_MAP_DATABASE_URL"] = url
    from server import postgres  # the BASELINE adapter (schema 7)
    ids: dict = {"bases": {}, "mapas": {}}
    with postgres.session() as conn:
        conn.raw.execute(postgres.schema_sql(), prepare=False)
        postgres.migrate(conn)
        with db.transaction(conn):
            for tag, n, estado, municipio, lat, lon, mode in SPECS:
                base_id = bases.create(conn, f"Base ensayo {tag}", f"ensayo_{tag}.xlsx", "Hoja1")
                rows = B.terrain_rows(tag, n, estado, municipio, lat, lon, mode)
                records = [TerrainRecord(orden=i + 1, fila=i + 2, **r) for i, r in enumerate(rows)]
                terrenos.insert(conn, base_id, records,
                                {r.orden: validation.validate_record(r) for r in records})
                ids["bases"][tag] = base_id
            ids["mapas"]["simple"] = mapas.create(
                conn, "Mapa ensayo P1", "simple", [{"base_id": ids["bases"]["P1"], "color": "#2a78d6"}],
                config={"basemap": "claro"})
            ids["mapas"]["comparacion"] = mapas.create(
                conn, "Comparación ensayo P1 vs P2", "comparacion",
                [{"base_id": ids["bases"]["P1"], "color": "#2a78d6", "version_etiqueta": "sept"},
                 {"base_id": ids["bases"]["P2"], "color": "#d62a2a", "version_etiqueta": "oct"}],
                config={"basemap": "claro"})
        ids["schema_version"] = postgres.schema_version(conn)
    print(json.dumps(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a FICTIONAL schema-v7 ARA Map workspace through the PRE-CHANGE code.

It imports the frozen baseline copy of `server/` in ../baseline_src (copied
2026-10-05 after every file matched BASELINE_MANIFEST.sha256), never the
workspace's changing `server/`. Bases, terrains, findings, folders, saved
maps (simple, comparison, and one whose source base was then deleted),
import formats and import records are written through the baseline repository
functions, with a private sentinel in every confidential place.

Purpose: Stage-1 legacy-route leakage audit and later migration rehearsal.

  build:   python3 build_legacy_v7.py --out /path/in/tmp/legacy_v7.db
  digest:  python3 build_legacy_v7.py --digest /path/to/copy.db   (legacy tables only)

--out must not exist and must not be the workspace's datos/ or api/data/.
Writes <out>.manifest.json beside the database. Timestamps are frozen, so two
builds with the same seed produce identical table digests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent / "baseline_src"
WORKSPACE = HERE.parents[3]
FROZEN_NOW = "2026-09-01T10:00:00-06:00"
SEED = 20261005
LEGACY_TABLES = ("carpeta", "base", "terreno", "incidencia", "mapa", "mapa_capa",
                 "mapa_terreno", "formato_importacion", "importacion")


def sentinel(kind: str, key: str) -> str:
    return f"SNTL-{kind}-{key}-{hashlib.sha256(f'{SEED}|{kind}|{key}'.encode()).hexdigest()[:6]}"


def verify_baseline() -> str:
    """Refuse to model on anything but the recorded baseline. Returns subset hash."""
    manifest = (BASELINE / "BASELINE_SUBSET.sha256").read_text()
    for line in manifest.splitlines():
        digest, rel = line.split("  ", 1)
        actual = hashlib.sha256((BASELINE / rel).read_bytes()).hexdigest()
        if actual != digest:
            raise SystemExit(f"baseline copy altered: {rel}")
    return hashlib.sha256(manifest.encode()).hexdigest()


def load_baseline():  # noqa: ANN201 - returns the baseline modules
    sys.path.insert(0, str(BASELINE))
    sys.path.append(str(WORKSPACE / "vendor" / "python"))  # openpyxl for importer.py
    from server import db, validation
    from server.importer import TerrainRecord
    from server.normalize import fold
    from server.repo import bases, carpetas, formatos, mapas, terrenos
    assert Path(db.__file__).resolve().is_relative_to(BASELINE), db.__file__
    for module in (db, bases, carpetas, formatos, mapas):
        module.now = lambda: FROZEN_NOW
    assert db.SCHEMA_VERSION == 7
    return db, validation, TerrainRecord, fold, bases, carpetas, formatos, mapas, terrenos


def terrain_rows(key: str, n: int, estado: str, municipio: str, lat0: float, lon0: float,
                 price_mode: str) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        k = f"{key}R{i:02d}"
        area = 5000.0 + 1250.0 * i
        row = {
            "terreno": f"Predio Histórico {k}", "estado": estado, "municipio": municipio,
            "direccion": f"Camino Viejo {i}, {municipio}", "id_origen": 100 + i,
            "superficie_m2": area, "superficie_ha": area / 10_000,
            "afectaciones_pct": 0.1 if i % 3 == 0 else None,
            "afectaciones_m2": area * 0.1 if i % 3 == 0 else None,
            "lat": round(lat0 + i * 0.002, 6), "lon": round(lon0 - i * 0.002, 6),
            "extra": {
                f"Contacto {sentinel('LEXTRAK', k)}": sentinel("LCONTACT", k),
                "Notas": f"<b>privado</b> {sentinel('LNOTE', k)}",
                "Fórmula": f"=HYPERLINK(\"{sentinel('LFORMULA', k)}\")",
            },
        }
        if price_mode == "unknown":   # pre-v7 rows: amounts with NULL currency
            row.update(asking_m2=round(900.0 + i, 2), asking_price=round((900.0 + i) * area, 2), moneda=None)
        elif price_mode == "usd":
            row.update(asking_m2=122.50 if i == 1 else round(95.0 + i * 1.25, 2), moneda="USD")
            row["asking_price"] = round(row["asking_m2"] * area, 2)
        else:
            row.update(asking_m2=round(1500.0 + i * 10.55, 2), moneda="MXN")
            row["asking_price"] = round(row["asking_m2"] * area, 2)
        rows.append(row)
    if key == "L1":  # literal HTML / formula / invalid coordinates
        rows[1]["terreno"] = "<script>alert('legacy')</script> Lote L1R02"
        rows[2]["terreno"] = "=1+2 Lote L1R03"
        rows[3].update(lat=None, lon=None)
        rows[4].update(lat=-100.4, lon=20.6)
    return rows


def build(out: Path) -> dict:
    mods = load_baseline()
    conn = mods[0].connect(out)
    ids = populate(conn, mods)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return {"ids": ids, "user_version": version, "deleted_base": {"L4": ids["bases"]["L4"]}}


def check_pg(url: str) -> str:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    if parts.hostname not in ("127.0.0.1", "localhost") or parts.port != 55433:
        raise SystemExit("REFUSING: Postgres target must be the verifier cluster 127.0.0.1:55433")
    return url


def build_pg(url: str) -> dict:
    """Same content, through the baseline Postgres adapter (fresh v7 workspace)."""
    import os
    mods = load_baseline()
    os.environ["ARA_MAP_DATABASE_URL"] = check_pg(url)  # this process only
    from server import postgres
    with postgres.session() as conn:
        conn.raw.execute(postgres.schema_sql(), prepare=False)
        postgres.migrate(conn)
        ids = populate(conn, mods)
        version = postgres.schema_version(conn)
    return {"ids": ids, "user_version": version, "deleted_base": {"L4": ids["bases"]["L4"]}}


def populate(conn, mods) -> dict:  # noqa: ANN001
    db, validation, TerrainRecord, fold, bases, carpetas, formatos, mapas, terrenos = mods
    ids: dict = {"carpetas": {}, "bases": {}, "mapas": {}, "formatos": {}, "importaciones": {}}
    with db.transaction(conn):
        for tag, tipo in (("F1", "bases"), ("F2", "mapas")):
            nombre = f"Carpeta {tag} {sentinel('FOLDER', tag)}"
            ids["carpetas"][tag] = carpetas.create(conn, tipo, nombre, fold(nombre))

        specs = [  # tag, rows, base folder
            ("L1", terrain_rows("L1", 15, "Querétaro", "El Marqués", 20.60, -100.30, "usd"), "F1"),
            ("L2", terrain_rows("L2", 12, "Jalisco", "Zapopan", 20.70, -103.40, "mxn"), None),
            ("L3", terrain_rows("L3", 6, "Guanajuato", "León", 21.10, -101.70, "unknown"), None),
            ("L4", terrain_rows("L4", 4, "Yucatán", "Mérida", 20.95, -89.60, "mxn"), None),
        ]
        for tag, rows, folder in specs:
            base_id = bases.create(
                conn, f"Base {tag} {sentinel('BASE', tag)}",
                f"fuente_{sentinel('SRCFILE', tag)}.xlsx", f"Hoja {sentinel('SHEET', tag)}",
                notas=f"Notas {sentinel('BASENOTE', tag)}",
                carpeta_id=ids["carpetas"][folder] if folder else None)
            ids["bases"][tag] = base_id
            records = [TerrainRecord(orden=i + 1, fila=i + 2, **r) for i, r in enumerate(rows)]
            terrenos.insert(conn, base_id, records,
                            {r.orden: validation.validate_record(r) for r in records})

        fid, fver, _ = formatos.recordar(
            conn, f"Formato {sentinel('FORMAT', 'FMT1')}",
            [["Terreno", "Estado", f"Col {sentinel('FMTHEADER', 'FMT1')}"]],
            {"columnas": {f"Col {sentinel('FMTHEADER', 'FMT1')}": "extra"}}, 1)
        ids["formatos"]["FMT1"] = fid
        for tag in ("L1", "L2", "L3", "L4"):
            ids["importaciones"][tag] = formatos.registrar_importacion(
                conn, base_id=ids["bases"][tag], tipo="nueva",
                archivo=f"fuente_{sentinel('SRCFILE', tag)}.xlsx",
                sha256=hashlib.sha256(tag.encode()).hexdigest(), hoja=f"Hoja {sentinel('SHEET', tag)}",
                fila_encabezado=1, plan={"nota": sentinel("PLAN", tag)},
                formato_id=fid if tag == "L1" else None, formato_version=fver if tag == "L1" else None)

        ids["mapas"]["S1"] = mapas.create(
            conn, f"Mapa S1 {sentinel('MAP', 'S1')}", "simple",
            [{"base_id": ids["bases"]["L1"], "color": "#2a78d6"}],
            config={"vista": sentinel("MAPCONFIG", "S1")}, carpeta_id=ids["carpetas"]["F2"])
        ids["mapas"]["C1"] = mapas.create(
            conn, f"Comparación C1 {sentinel('MAP', 'C1')}", "comparacion",
            [{"base_id": ids["bases"]["L1"], "color": "#2a78d6", "version_etiqueta": "sept"},
             {"base_id": ids["bases"]["L2"], "color": "#d62a2a",
              "version_etiqueta": f"oct {sentinel('LAYERTAG', 'C1')}"}],
            config={"vista": sentinel("MAPCONFIG", "C1")})
        ids["mapas"]["D1"] = mapas.create(
            conn, f"Mapa D1 {sentinel('MAP', 'D1')}", "simple",
            [{"base_id": ids["bases"]["L4"], "color": "#2ad66b"}], config={})
        # Source deleted afterwards: the frozen D1 snapshot must survive.
        bases.delete(conn, ids["bases"]["L4"])
    return ids


def _tables(path: Path | None = None, pg_url: str | None = None):  # noqa: ANN202
    """Yield (table, columns, rows) for every legacy table, read-only, canonical order."""
    if pg_url:
        import psycopg
        conn = psycopg.connect(check_pg(pg_url))
        q = ("SELECT column_name FROM information_schema.columns WHERE table_name = %s"
             " AND table_schema = current_schema() ORDER BY ordinal_position")
    else:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for table in LEGACY_TABLES:
            cols = ([r[0] for r in conn.execute(q, (table,)).fetchall()] if pg_url
                    else [r[1] for r in conn.execute(f"PRAGMA table_info({table})")])
            cols = sorted(cols)  # engine-neutral: added columns are compared by name
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {', '.join(cols)}").fetchall()
            yield table, cols, [list(r) for r in rows]
        if pg_url:
            v = conn.execute("SELECT value FROM workspace_metadata WHERE key='schema_version'").fetchone()
            yield "_user_version", None, int(v[0]) if v else None
        else:
            yield "_user_version", None, conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def digest(path: Path | None = None, pg_url: str | None = None) -> dict:
    """Row counts and canonical sha256 per legacy table."""
    out: dict = {}
    for table, cols, rows in _tables(path, pg_url):
        if cols is None:
            out[table] = rows
            continue
        payload = json.dumps([cols, rows], ensure_ascii=False, sort_keys=True, default=str).encode()
        out[table] = {"rows": len(rows), "sha256": hashlib.sha256(payload).hexdigest()}
    return out


def all_sentinels(path: Path | None = None, pg_url: str | None = None) -> list[str]:
    import re
    found: set[str] = set()
    for _, cols, rows in _tables(path, pg_url):
        if cols is None:
            continue
        for row in rows:
            for value in row:
                if isinstance(value, str):
                    found.update(re.findall(r"SNTL-[A-Z]+-[A-Za-z0-9]+-[0-9a-f]{6}", value))
    return sorted(found)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", type=Path)
    g.add_argument("--digest", type=Path)
    g.add_argument("--pg-url-env", help="env var holding the verifier cluster URL (127.0.0.1:55433)")
    ap.add_argument("--manifest", type=Path, help="manifest path (required with --pg-url-env)")
    ap.add_argument("--digest-only", action="store_true", help="with --pg-url-env: print digest only")
    args = ap.parse_args()
    if args.digest:
        print(json.dumps(digest(args.digest), indent=1, sort_keys=True))
        return 0
    import os
    pg_url = os.environ[args.pg_url_env] if args.pg_url_env else None
    if pg_url and args.digest_only:
        print(json.dumps(digest(pg_url=pg_url), indent=1, sort_keys=True))
        return 0
    subset_hash = verify_baseline()
    if pg_url:
        if not args.manifest:
            raise SystemExit("--manifest required with --pg-url-env")
        result = build_pg(pg_url)
        out, manifest_path = None, args.manifest
    else:
        out = args.out.resolve()
        forbidden = (WORKSPACE / "datos", WORKSPACE / "api" / "data")
        if out.exists() or any(out.is_relative_to(f.resolve()) for f in forbidden):
            raise SystemExit(f"refusing target {out}: exists or is a workspace data path")
        result = build(out)
        manifest_path = Path(str(out) + ".manifest.json")
    if result["user_version"] != 7:
        raise SystemExit(f"expected schema v7, got {result['user_version']}")
    manifest = {
        "fictional": True,
        "database": str(out) if out else "postgres 127.0.0.1:55433 (verifier cluster)",
        "modelled_on": {"baseline_manifest": "BASELINE_MANIFEST.sha256",
                        "baseline_subset_sha256": subset_hash,
                        "baseline_db_py_sha256": hashlib.sha256(
                            (BASELINE / "server" / "db.py").read_bytes()).hexdigest(),
                        "schema_version": result["user_version"]},
        "frozen_now": FROZEN_NOW,
        "ids": result["ids"],
        "deleted_source_base": result["deleted_base"],
        "digest": digest(out, pg_url),
        "sentinels": all_sentinels(out, pg_url),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"legacy v7 workspace -> {out or 'postgres'}  manifest {manifest_path}")
    print(json.dumps({t: v["rows"] for t, v in manifest["digest"].items() if t != "_user_version"}))
    print(f"sentinels: {len(manifest['sentinels'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

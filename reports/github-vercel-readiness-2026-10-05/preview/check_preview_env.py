#!/usr/bin/env python3
"""Prove that no effective Vercel PREVIEW database variable reaches Production.

Inputs are two dotenv files written by the Vercel CLI on the supervisor's Mac
(both match `.env*`, which Git ignores; delete them afterwards):

    vercel env pull --environment=preview    .env.preview.check
    vercel env pull --environment=production .env.production.check
    python3 check_preview_env.py .env.preview.check .env.production.check [--connect]

Nothing secret is printed: a connection string is reduced to its host,
database name and role, and other values to "set"/"unset". Exit status 0
only when every check passes.

What it checks:
  * the EFFECTIVE database URL the app uses in Preview. api/index.py copies
    DATABASE_URL into ARA_MAP_DATABASE_URL only when the latter is unset, so a
    shared ARA_MAP_DATABASE_URL would silently override a Preview-only
    DATABASE_URL;
  * every Postgres-looking variable (DATABASE_URL*, POSTGRES_*, PG*, *_URL with
    a postgres scheme, NEON_*): no Preview value may share a host/endpoint
    with any Production database value;
  * Preview has no paid-AI key (imports in Preview must not call a paid model);
  * with --connect, a read-only connection to the effective Preview database
    reports its database, schema version and legacy row counts (fictional
    data only: expected 0 before seeding).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

DB_HINTS = ("DATABASE_URL", "POSTGRES", "PGHOST", "PGUSER", "PGDATABASE", "PGPASSWORD", "NEON")
AI_KEYS = ("OPENAI_API_KEY", "ARA_MAP_IA_CLAVE", "ARA_MAP_IA_PROVEEDOR")


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def is_db(name: str, value: str) -> bool:
    return any(h in name.upper() for h in DB_HINTS) or value.startswith(("postgres://", "postgresql://"))


def describe(name: str, value: str) -> dict[str, str | None]:
    """Host, database and role only -- never the password or query string."""
    if value.startswith(("postgres://", "postgresql://")):
        parts = urlsplit(value)
        return {"kind": "url", "host": parts.hostname, "db": parts.path.lstrip("/") or None,
                "role": parts.username}
    if name.upper().endswith(("PGHOST", "POSTGRES_HOST")) or name.upper() == "PGHOST":
        return {"kind": "host", "host": value, "db": None, "role": None}
    if "PASSWORD" in name.upper() or "SECRET" in name.upper() or "KEY" in name.upper():
        return {"kind": "secret", "host": None, "db": None, "role": None}
    return {"kind": "value", "host": None, "db": value if "DATABASE" in name.upper() else None,
            "role": value if "USER" in name.upper() else None}


def endpoint(host: str | None) -> str | None:
    """Neon hosts look like ep-xxxx-yyyy[-pooler].region.aws.neon.tech: the
    endpoint id identifies the branch compute, pooled or not."""
    if not host:
        return None
    first = host.split(".")[0]
    return first.removesuffix("-pooler")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("preview", type=Path)
    ap.add_argument("production", type=Path)
    ap.add_argument("--connect", action="store_true", help="read-only probe of the effective Preview database")
    args = ap.parse_args()
    pre, prod = read_dotenv(args.preview), read_dotenv(args.production)
    failures: list[str] = []

    prod_endpoints = {endpoint(describe(k, v)["host"]) for k, v in prod.items() if is_db(k, v)} - {None}
    prod_secret_values = {v for k, v in prod.items() if is_db(k, v) and v}
    # Passwords embedded in Production URLs, compared in memory only.
    prod_passwords = {urlsplit(v).password for v in prod.values()
                      if v.startswith(("postgres://", "postgresql://")) and urlsplit(v).password}
    prod_passwords |= {v for k, v in prod.items() if "PASSWORD" in k.upper() and v}

    print("Variable                         Preview                                  Production")
    for name in sorted({k for k in (*pre, *prod) if is_db(k, pre.get(k, prod.get(k, "")))}):
        a = describe(name, pre[name]) if name in pre else None
        b = describe(name, prod[name]) if name in prod else None

        def show(d: dict | None) -> str:
            if d is None:
                return "unset"
            if d["kind"] == "secret":
                return "set (secret)"
            return " ".join(str(x) for x in (endpoint(d["host"]), d["db"], d["role"]) if x) or "set"
        print(f"{name:32} {show(a):40} {show(b)}")
        if a and a["host"] and endpoint(a["host"]) in prod_endpoints:
            failures.append(f"{name}: Preview host is a Production endpoint")
        if name in pre and pre[name] and pre[name] in prod_secret_values and a and a["kind"] != "value":
            failures.append(f"{name}: Preview value is identical to a Production value")
        if name in pre and a and a["kind"] == "url" and urlsplit(pre[name]).password in prod_passwords:
            failures.append(f"{name}: Preview reuses a Production password (a Neon branch inherits its"
                            " parent's roles; use a role that exists only on the Preview branch)")

    effective = pre.get("ARA_MAP_DATABASE_URL") or pre.get("DATABASE_URL")
    source = "ARA_MAP_DATABASE_URL" if pre.get("ARA_MAP_DATABASE_URL") else "DATABASE_URL"
    if not effective:
        failures.append("Preview has no database URL at all (the app would answer 503)")
        eff_host = None
    else:
        eff_host = urlsplit(effective).hostname
        print(f"\nEffective Preview database (from {source}): endpoint {endpoint(eff_host)},"
              f" db {urlsplit(effective).path.lstrip('/')}")
        if endpoint(eff_host) in prod_endpoints:
            failures.append("EFFECTIVE Preview database is a Production endpoint")
    if pre.get("ARA_MAP_DATABASE_URL") and pre.get("DATABASE_URL") and \
            pre["ARA_MAP_DATABASE_URL"] != pre["DATABASE_URL"]:
        failures.append("ARA_MAP_DATABASE_URL and DATABASE_URL differ in Preview; "
                        "ARA_MAP_DATABASE_URL wins -- remove it from Preview or make them equal")

    # Splitting Preview off must not strip Production of its database.
    if not (prod.get("ARA_MAP_DATABASE_URL") or prod.get("DATABASE_URL")):
        failures.append("Production has no DATABASE_URL any more: restore its Production target")

    for key in AI_KEYS:
        if pre.get(key):
            failures.append(f"{key} is set in Preview: paid AI calls are not part of Preview testing")
    print("Paid-AI settings in Preview:", ", ".join(f"{k}={'set' if pre.get(k) else 'unset'}" for k in AI_KEYS))

    if args.connect and effective and not failures:
        import psycopg
        with psycopg.connect(effective, connect_timeout=15) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            db = conn.execute("SELECT current_database(), current_user, version()").fetchone()
            print(f"Connected read-only: database {db[0]}, role {db[1]}, {db[2].split(',')[0]}")
            meta = conn.execute("SELECT to_regclass('workspace_metadata') IS NOT NULL").fetchone()[0]
            version_row = conn.execute("SELECT value FROM workspace_metadata WHERE key = 'schema_version'"
                                   ).fetchone() if meta else None
            version = version_row[0] if version_row else None
            print(f"Schema version: {version or 'none (empty database)'}")
            for table in ("base", "terreno", "mapa", "team_user", "inventory_terrain"):
                exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (table,)).fetchone()[0]
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if exists else "-"
                print(f"  {table:18} {n}")

    print()
    for f in failures:
        print("FAIL ", f)
    print("PASS  Preview is isolated from Production" if not failures else f"{len(failures)} problem(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

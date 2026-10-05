"""Create or upgrade the Postgres schema of an explicitly named target.

Ordinary cloud requests never create or alter schema; this command does, and
only against the database whose URL is in the environment variable you name.
It never reads .env.local and refuses to run without --url-env:

    python3 scripts/esquema.py --url-env ARA_MAP_TEST_DATABASE_URL           # create/upgrade
    python3 scripts/esquema.py --url-env ARA_MAP_TEST_DATABASE_URL --check   # report only

Every statement is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT
EXISTS), so it serves both an empty database and an existing workspace, and
running it twice changes nothing. Existing tables are backed up into
workspace_backup first. Exit status of --check: 0 when already current.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Esquema Postgres de ARA Map.")
    parser.add_argument("--url-env", metavar="VARIABLE", required=True,
                        help="variable de entorno con la URL de Postgres de destino")
    parser.add_argument("--check", action="store_true", help="sólo informa la versión")
    args = parser.parse_args(argv)
    url = os.environ.get(args.url_env)
    if not url:
        raise SystemExit(f"{args.url_env} no está definida; no se usa ningún destino por omisión.")
    os.environ["ARA_MAP_DATABASE_URL"] = url

    from server import db, postgres

    with postgres.session() as conn:
        before = postgres.schema_version(conn)
    print(f"Versión del esquema: {before if before is not None else 'sin registrar'};"
          f" este código espera {db.SCHEMA_VERSION}.")
    if args.check:
        return 0 if before == db.SCHEMA_VERSION else 1
    if before is not None:
        postgres.backup()
    with postgres.session() as conn:
        conn.raw.execute(postgres.schema_sql(), prepare=False)
        postgres.migrate(conn)
        after = postgres.schema_version(conn)
    print(f"Esquema en la versión {after}. Los datos existentes se conservaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Upgrade the shared cloud workspace's schema in place, preserving its data.

setup_cloud.py only initializes an empty workspace. A workspace that is already
in use is brought up to date here instead: every statement is idempotent
(CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS), so running it twice is
harmless, and it runs under the same advisory lock as every request, so it
cannot interleave with an edit.

Run it BEFORE deploying code that needs the new schema (currently: folders,
schema version 5); the new code queries columns this adds.

    .venv-dev/bin/python scripts/migrate_cloud.py           # upgrade
    .venv-dev/bin/python scripts/migrate_cloud.py --check   # only report

By default reads DATABASE_URL from .env.local, like setup_cloud.py -- that is
the production workspace. To upgrade anything else (a disposable test
database, a preview branch), name the variable that holds its URL:

    .venv-dev/bin/python scripts/migrate_cloud.py --url-env ARA_MAP_TEST_DATABASE_URL

With --url-env, .env.local is never read, so a missing variable is an error
rather than a silent fall-back to production.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

argumentos = sys.argv[1:]
if "--url-env" in argumentos:
    indice = argumentos.index("--url-env")
    if indice + 1 >= len(argumentos):
        raise SystemExit("--url-env necesita el nombre de una variable de entorno.")
    variable = argumentos[indice + 1]
    destino = os.environ.get(variable)
    if not destino:
        raise SystemExit(f"{variable} no está definida; no se usa .env.local como respaldo.")
    os.environ["ARA_MAP_DATABASE_URL"] = destino
else:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local")
    os.environ["ARA_MAP_DATABASE_URL"] = os.environ["DATABASE_URL"]

from server import db, postgres

with postgres.session() as cloud:
    before = postgres.schema_version(cloud)
print(f"Cloud schema version: {before if before is not None else 'unrecorded (before 5)'}; "
      f"this code expects {db.SCHEMA_VERSION}.")

if "--check" in argumentos:
    raise SystemExit(0 if before == db.SCHEMA_VERSION else 1)

postgres.backup()  # the existing tables, before anything changes
with postgres.session() as cloud:
    postgres.migrate(cloud)
    after = postgres.schema_version(cloud)
print(f"Cloud schema upgraded to version {after}. Existing data preserved.")

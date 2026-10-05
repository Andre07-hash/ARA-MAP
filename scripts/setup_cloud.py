"""Initialize and seed an empty cloud database once, never overwrite live data.

Run with .venv-dev/bin/python scripts/setup_cloud.py. Uses .env.local privately.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local")
os.environ["ARA_MAP_DATABASE_URL"] = os.environ["DATABASE_URL"]

from server import db, postgres

with postgres.session() as cloud:
    cloud.raw.execute(postgres.schema_sql(), prepare=False)
    if cloud.execute("SELECT 1 FROM workspace_metadata WHERE key = 'seeded'").fetchone():
        print("Cloud database already initialized; existing data preserved.")
        raise SystemExit(0)
    if any(cloud.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in postgres.TABLES):
        raise SystemExit("Cloud database is not empty; refusing to overwrite it.")
    # A fresh workspace already has every column; this adds the indexes and
    # records the schema version. Existing workspaces use migrate_cloud.py.
    postgres.migrate(cloud)
    with db.session(db.db_path()) as local:
        for table in postgres.TABLES:
            rows = local.execute(f"SELECT * FROM {table}").fetchall()
            if rows:
                columns = rows[0].keys()
                sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('%s' for _ in columns)})"
                with cloud.raw.cursor() as cursor:
                    cursor.executemany(sql, [tuple(row) for row in rows])
            if table in postgres.ID_TABLES:
                maximum = max((row["id"] for row in rows), default=0)
                old_sequence = local.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)).fetchone()
                maximum = max(maximum, old_sequence[0] if old_sequence else 0)
                cloud.raw.execute("SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, %s)",
                                  (table, max(maximum, 1), maximum > 0))
            print(f"Migrated {table}: {len(rows)} records")
    cloud.execute("INSERT INTO workspace_metadata(key, value) VALUES ('seeded', ?)", (db.now(),))
print("Cloud database initialized. Future deployments preserve shared changes.")

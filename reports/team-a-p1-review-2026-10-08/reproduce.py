"""Run P1 review reproductions against a disposable archive passed as argv[1].

Example: python3 reproduce.py /path/to/disposable/7588665/archive
Uses only fictional fixture data and temporary SQLite databases. Exit 1 means
at least one reviewed bug still reproduces. This is review evidence, not app code.
"""

import json
import os
from pathlib import Path
import sqlite3
import sys


def main():
    root = Path(sys.argv[1]).resolve()
    if not (root / "tests/test_schema_v10.py").is_file():
        raise SystemExit("Expected a disposable P1 archive containing schema-v10 tests")
    for key in list(os.environ):
        if "DATABASE_URL" in key or key.startswith(("PG", "NEON_")):
            del os.environ[key]
    sys.path.insert(0, str(root))
    from server import db
    from tests.test_schema_v10 import AHORA, SchemaV10Sqlite, insertar, nuevo

    failures = []
    SchemaV10Sqlite.setUpClass()
    test = SchemaV10Sqlite()
    try:
        inv = test.confirmar(test.terreno)
        attachment = test.confirmar(lambda conn: test.archivo(conn, inv))
        for number, state in enumerate(("subiendo", "cancelado", "expirado"), 1):
            try:
                test.confirmar(lambda conn, n=number, s=state: test.version(
                    conn, attachment, inv, n, s, motivo_no_aplicada="superada"))
            except sqlite3.IntegrityError:
                print("F1 rejected as required:", state)
            else:
                failures.append("F1:" + state)
                print("F1 unexpectedly committed:", json.dumps({
                    "estado": state, "aplicada": None, "motivo_no_aplicada": "superada"}))

        pending = test.confirmar(lambda conn: test.version(
            conn, attachment, inv, 4, "subiendo"))
        test.confirmar(lambda conn: insertar(
            conn, "archivo_trabajo", archivo_version_id=pending, trabajo_id=nuevo(),
            actor_id=test.ana(conn)["id"], operacion="completar", inicio=AHORA,
            vence_en="2099-01-01T00:00:00Z"))
        backup_path = db.backup(test.path)
        with sqlite3.connect(backup_path) as backup:
            leases = backup.execute("SELECT count(*) FROM archivo_trabajo").fetchone()[0]
            pending_rows = backup.execute(
                "SELECT count(*) FROM archivo_version WHERE id = ? AND estado = 'subiendo'",
                (pending,)).fetchone()[0]
        source_leases = test.cuenta("archivo_trabajo")
        print("F2 backup/source counts:", json.dumps({
            "backup_leases": leases, "backup_pending": pending_rows,
            "source_leases": source_leases}))
        if leases != 0 or pending_rows != 1 or source_leases != 1:
            failures.append("F2:backup")
    finally:
        SchemaV10Sqlite.tearDownClass()
    print("Remaining failures:", failures)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())

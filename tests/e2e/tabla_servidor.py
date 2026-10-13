"""A disposable local ARA Map for the table's browser checks (packet 2A).

    python3 tests/e2e/tabla_servidor.py --puerto 8433                    # journeys: accounts only
    python3 tests/e2e/tabla_servidor.py --puerto 8434 --registros 25000  # measurement data

A temporary SQLite file that is deleted on exit, the real server, and
fictional accounts whose password is the test fixture's
(tests/support.py, TEST_PASSWORD): administrators ada and alan; operators
olga, omar, oscar, olivia, oriol and otto. Nothing here reads the
application's configured database or any real account.

With --carpeta DIR the database and the attachment store live in DIR and are
kept on exit, so a second start with the same DIR is a restart of the same
local installation (accounts are seeded only the first time). With
--postgres-esquema NAME the database is that schema of the disposable Postgres
named by ARA_MAP_TEST_DATABASE_URL (created if absent), and the store is
DIR/archivos; it requires --carpeta. Never point it at a real database.

    python3 tests/e2e/tabla_servidor.py --puerto 8436 --carpeta /tmp/ara-3a
    ARA_MAP_TEST_DATABASE_URL=postgresql://.../desechable \
      python3 tests/e2e/tabla_servidor.py --puerto 8437 --carpeta /tmp/ara-3a-pg --postgres-esquema e2e_3a

With --registros N it also writes N synthetic terrains straight to the tables:
3,000 in "Base Grande" (granted to olga, omar, oscar, olivia and oriol), 1,000
unassigned and the rest spread over ten other bases. otto never has a grant.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ADMINS = ("ada", "alan")
OPERADORES = ("olga", "omar", "oscar", "olivia", "oriol", "otto")
ESTADOS = ["Jalisco", "Nuevo León", "Querétaro", "Yucatán", "Sonora", "Michoacán", "Puebla", "Colima"]
TIPOS = ["Industrial", "Agrícola", "Comercial", "Habitacional", None]


def sembrar(registros: int) -> None:
    from server import auth, db
    from tests.support import TEST_PASSWORD
    with db.escritura() as conn:
        ids = {n: auth.create_user(conn, n, n.capitalize() + " Ficticia", TEST_PASSWORD,
                                   iterations=1000, rol="admin" if n in ADMINS else "operador")["id"]
               for n in ADMINS + OPERADORES}
        if not registros:
            return
        ahora, ada = db.now(), ids["ada"]
        bases = [str(uuid.uuid4()) for _ in range(11)]
        for n, base in enumerate(bases):
            conn.execute("INSERT INTO maestra_base (id, nombre, created_at, created_by, updated_at,"
                         " updated_by) VALUES (?, ?, ?, ?, ?, ?)",
                         (base, "Base Grande" if n == 0 else f"Base {n:02d}", ahora, ada, ahora, ada))
        for login in OPERADORES[:5]:
            conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                         " VALUES (?, ?, ?, ?)", (bases[0], ids[login], ahora, ada))
        grande, sueltos = min(3000, registros), min(1000, max(0, registros - 3000))
        for n in range(registros):
            base = bases[0] if n < grande else None if n >= registros - sueltos else bases[1 + n % 10]
            tid, rid = str(uuid.uuid4()), str(uuid.uuid4())
            conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                         " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                         (tid, base, ahora, ada, ahora, ada))
            conn.execute(
                "INSERT INTO inventory_revision (id, inventory_id, revision_number, terreno, estado,"
                " municipio, tipo_terreno, superficie_m2, asking_price, notas_internas, lat, lon,"
                " base_id, created_at, created_by) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, tid, None if n % 97 == 0 else f"Lote {'Ñandú' if n % 5 == 0 else 'Árbol'} {n}",
                 ESTADOS[n % len(ESTADOS)], f"Municipio {n % 40}", TIPOS[n % len(TIPOS)],
                 None if n % 11 == 0 else 500 + (n * 37) % 90_000,
                 None if n % 7 == 0 else 100_000 + (n * 911) % 9_000_000,
                 f"Comentario ficticio {n}" if n % 3 == 0 else None,
                 20 + (n % 50) / 100, -103 - (n % 50) / 100, base, ahora, ada))
            conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?", (rid, tid))
            conn.execute("INSERT INTO inventory_event (id, inventory_id, version, action, actor_id,"
                         " actor_name, at, after_revision_id, details_json) VALUES (?, ?, 1, 'create',"
                         " ?, 'Ada Ficticia', ?, ?, '{}')", (str(uuid.uuid4()), tid, ada, ahora, rid))


def preparar_postgres(esquema: str) -> None:
    """Point the application at one schema of the disposable test Postgres."""
    import psycopg
    from psycopg.conninfo import make_conninfo
    url = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
    if not url:
        raise SystemExit("--postgres-esquema necesita ARA_MAP_TEST_DATABASE_URL (una base desechable).")
    if not esquema.replace("_", "").isalnum():
        raise SystemExit("Nombre de esquema no válido.")
    with psycopg.connect(url) as conn:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"')
    os.environ["ARA_MAP_DATABASE_URL"] = make_conninfo(url, options=f"-c search_path={esquema}")
    from server import postgres
    with postgres.session() as conn:
        conn.raw.execute(postgres.schema_sql(), prepare=False)
        postgres.migrate(conn)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--puerto", type=int, default=8433)
    parser.add_argument("--registros", type=int, default=0)
    parser.add_argument("--carpeta", help="keep the database and the store here (restartable)")
    parser.add_argument("--postgres-esquema", help="disposable Postgres schema (needs --carpeta)")
    args = parser.parse_args()
    if args.postgres_esquema and not args.carpeta:
        raise SystemExit("--postgres-esquema requiere --carpeta para el almacén de archivos.")
    temporal = None if args.carpeta else tempfile.TemporaryDirectory()
    carpeta = Path(args.carpeta) if args.carpeta else Path(temporal.name)  # type: ignore[union-attr]
    carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        for variable in ("ARA_MAP_DATABASE_URL", "DATABASE_URL", "ARA_MAP_READ_ONLY", "ARA_MAP_ARCHIVOS"):
            os.environ.pop(variable, None)
        os.environ["ARA_MAP_DB"] = str(carpeta / "desechable.db")
        if args.postgres_esquema:
            os.environ["ARA_MAP_ARCHIVOS"] = str(carpeta / "archivos")
            preparar_postgres(args.postgres_esquema)
        from server import app, db
        db.connect().close()
        marca = carpeta / "sembrado"
        if not marca.exists():
            sembrar(args.registros)
            marca.write_text("1")
        print(f"BD {os.environ.get('ARA_MAP_DATABASE_URL') and 'postgres' or os.environ['ARA_MAP_DB']}",
              flush=True)   # for scripts/cuentas.py --sqlite in a journey
        print(f"LISTO http://localhost:{args.puerto}", flush=True)
        app.serve(args.puerto, open_browser=False)
    finally:
        if temporal is not None:
            temporal.cleanup()


if __name__ == "__main__":
    main()

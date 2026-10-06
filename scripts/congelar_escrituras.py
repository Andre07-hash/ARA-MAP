"""Server-enforced write freeze for a release, at the DATABASE.

An environment variable or a maintenance page only stops the deployment that
reads it; Vercel keeps every older deployment reachable at its own URL with
its own configuration. Making the database itself read-only stops writes from
all of them at once (and from a refresh still running somewhere): reads keep
working, and the app answers writes with 503 "en mantenimiento".

    python3 scripts/congelar_escrituras.py --url-env VARIABLE estado
    python3 scripts/congelar_escrituras.py --url-env VARIABLE activar
    python3 scripts/congelar_escrituras.py --url-env VARIABLE desactivar

`activar` sets default_transaction_read_only on the database, then ends every
other open connection to it so none keeps writing under the old setting, and
reports Excel refreshes that were in progress (their previous data stays
active; the next read after the freeze marks them interrupted).

While frozen, the release's own migration/backup steps connect with the
setting overridden for their session only, e.g. a DIRECT (unpooled) URL with
`options=-c default_transaction_read_only=off`. Nothing else does.

Explicit target only: it never reads .env.local and has no default database.
Needs a role that owns the database (Neon: the database owner role).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import Any

PARAMETRO = "default_transaction_read_only"


def _ident(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


def estado(conn: Any) -> dict[str, Any]:
    fila = conn.execute(
        "SELECT current_database(), (SELECT array_to_string(setconfig, ',') FROM pg_db_role_setting"
        " WHERE setdatabase = (SELECT oid FROM pg_database WHERE datname = current_database())"
        " AND setrole = 0)").fetchone()
    config = fila[1] or ""
    en_curso = None
    if conn.execute("SELECT to_regclass('excel_ejecucion')").fetchone()[0] is not None:
        en_curso = conn.execute("SELECT COUNT(*) FROM excel_ejecucion WHERE estado = 'en_curso'").fetchone()[0]
    otras = conn.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()"
                         " AND pid <> pg_backend_pid()").fetchone()[0]
    return {"base_de_datos": fila[0], "congelada": f"{PARAMETRO}=on" in config,
            "actualizaciones_en_curso": en_curso, "otras_conexiones": otras}


def activar(conn: Any) -> dict[str, Any]:
    nombre = conn.execute("SELECT current_database()").fetchone()[0]
    conn.execute(f"ALTER DATABASE {_ident(nombre)} SET {PARAMETRO} = on")
    terminadas = conn.execute(
        "SELECT COUNT(*) FILTER (WHERE pg_terminate_backend(pid)) FROM pg_stat_activity"
        " WHERE datname = current_database() AND pid <> pg_backend_pid()"
        " AND usename IS NOT NULL").fetchone()[0]
    return {**estado(conn), "conexiones_terminadas": terminadas}


def desactivar(conn: Any) -> dict[str, Any]:
    nombre = conn.execute("SELECT current_database()").fetchone()[0]
    conn.execute(f"ALTER DATABASE {_ident(nombre)} RESET {PARAMETRO}")
    return estado(conn)


def conectar(url: str) -> Any:
    import psycopg
    conn = psycopg.connect(url, autocommit=True)
    # This session must be able to lift the freeze it may be under.
    conn.execute(f"SET {PARAMETRO} = off")
    return conn


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Congelar las escrituras de ARA Map en la base de datos.")
    parser.add_argument("--url-env", metavar="VARIABLE", required=True)
    parser.add_argument("accion", choices=("estado", "activar", "desactivar"))
    args = parser.parse_args(argv)
    url = os.environ.get(args.url_env)
    if not url:
        raise SystemExit(f"{args.url_env} no está definida; no hay destino por omisión.")
    with conectar(url) as conn:
        resultado = {"estado": estado, "activar": activar, "desactivar": desactivar}[args.accion](conn)
    for clave, valor in resultado.items():
        print(f"{clave}: {valor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

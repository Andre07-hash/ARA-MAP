"""Load a terrain CSV into one work base of the editable master table.

A trusted operations command, like scripts/cuentas.py, for loads outside the
app; administrators also load files from the table («Importar Excel»), through
the same server/carga_maestra.py, which also loads the «Tipo de terreno» and
«Comentarios» columns (validated like the table's own cells). It refuses to run without an explicitly named target and
never reads .env.local:

    python3 scripts/cargar_maestra.py --sqlite RUTA/ara_map.db \
        --base "Piloto Norte" --admin ana --dry-run terrenos.csv
    python3 scripts/cargar_maestra.py --url-env VARIABLE --base ID_DE_BASE --admin ana terrenos.csv

--base is a work base's id or its exact name; --admin is the login of the
active administrator the rows are recorded under. The CSV is read by the same
reader as the legacy import (UTF-8, same header aliases; X is the latitude and
Y the longitude) and every row passes the same field validation as a row typed
in the table. Each terrain is created by the master table's own repository
function, so it gets its revision, its "create" history event and its
idempotency row exactly like one created in the app.

All or nothing, in one write transaction: a row with an invalid value stops
the whole load before anything is written. A row already in the base (same
name + state + municipality + area, the domain identity) is skipped and
reported, never duplicated and never updated; so is a repeat inside the file.
--dry-run validates and reports the same way and writes nothing.

A Postgres target must already be at the current schema: this command checks
and refuses, it never migrates.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Carga un CSV de terrenos en una base de trabajo.")
    destino = parser.add_mutually_exclusive_group(required=True)
    destino.add_argument("--sqlite", metavar="RUTA", help="archivo SQLite de destino")
    destino.add_argument("--url-env", metavar="VARIABLE",
                         help="variable de entorno con la URL de Postgres de destino")
    parser.add_argument("--base", required=True, help="id o nombre exacto de la base de trabajo")
    parser.add_argument("--admin", required=True, metavar="USUARIO",
                        help="administrador activo a cuyo nombre queda la carga")
    parser.add_argument("--decimales", choices=("dot", "comma"), default="dot",
                        help="convención numérica del CSV (punto o coma decimal)")
    parser.add_argument("--moneda", choices=("MXN", "USD"),
                        help="moneda de los precios del CSV; sin esta opción quedan sin moneda")
    parser.add_argument("--dry-run", action="store_true",
                        help="valida e informa; no escribe nada")
    parser.add_argument("csv", help="archivo CSV UTF-8 con los terrenos")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.url_env:
        url = os.environ.get(args.url_env)
        if not url:
            raise SystemExit(f"{args.url_env} no está definida; no se usa ningún destino por omisión.")
        os.environ["ARA_MAP_DATABASE_URL"] = url
        sqlite_path = None
    else:
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        sqlite_path = Path(args.sqlite).expanduser().resolve()
        if not sqlite_path.exists():
            raise SystemExit(f"No existe {sqlite_path}.")

    from server import auth, carga_maestra, db, postgres
    from server.csv_importer import read_csv_bytes
    from server.errors import WorkbookError
    from server.repo import maestra as repo_maestra

    try:
        leido = read_csv_bytes(Path(args.csv).expanduser().read_bytes(),
                               decimal_mode=args.decimales)
    except (OSError, WorkbookError) as exc:
        raise SystemExit(f"No se pudo leer el CSV: {exc}") from None

    # The same validation as a row saved from the table, for every row, before
    # the database is touched. The declared currency goes on the rows that
    # carry a price, and nowhere else.
    records = [dataclasses.replace(r, moneda=args.moneda)
               if args.moneda and (r.asking_price is not None or r.asking_m2 is not None) else r
               for r in leido.records]
    filas, errores = carga_maestra.validar(records)
    if errores:
        raise SystemExit("\n".join(["El CSV tiene valores no admitidos; no se escribió nada.",
                                    *errores]))

    with db.escritura(sqlite_path) as conn:
        if sqlite_path is None and (postgres.schema_version(conn) or 0) < db.SCHEMA_VERSION:
            raise SystemExit(f"El destino Postgres no está en el esquema {db.SCHEMA_VERSION};"
                             " migra primero. Este comando no migra.")
        login = auth.normalize_login(args.admin)
        cuenta = next((u for u in auth.list_users(conn) if u["login"] == login), None)
        if (cuenta is None or not cuenta["active"]
                or "maestra.global" not in auth.CAPACIDADES[cuenta["rol"]]):
            raise SystemExit(f"«{args.admin}» no es un administrador activo; no se escribió nada.")
        actor = {"id": cuenta["id"], "display_name": cuenta["display_name"]}

        # ponytail: the base row is read, not locked. SQLite's write reservation
        # covers it; on Postgres a delete committed mid-load is not waited for.
        # Lock it in server/repo/maestra.py if loads ever run beside live admins.
        bases = [b for b in repo_maestra.listar(conn, None)
                 if args.base in (b["id"], b["nombre"])]
        if len(bases) != 1:
            raise SystemExit(f"La base de trabajo «{args.base}» "
                             + ("no existe" if not bases else "no es única; usa su id")
                             + "; no se escribió nada.")
        base = bases[0]
        nuevas, omitidas = carga_maestra.cargar(conn, base["id"], records, filas, actor,
                                                simular=args.dry_run)

    print(("SIMULACIÓN: no se escribió nada. " if args.dry_run else "")
          + f"Base «{base['nombre']}» ({base['id']}), a nombre de {actor['display_name']}.")
    print(f"Filas leídas: {len(records)} · "
          + ("se crearían" if args.dry_run else "creadas") + f": {nuevas} · "
          f"omitidas por duplicadas: {len(omitidas)} · sin nombre (no cargadas): "
          f"{len(leido.rechazadas)}")
    for linea in omitidas:
        print(f"  DUPLICADA {linea}")
    for rechazada in leido.rechazadas:
        print(f"  SIN NOMBRE línea {rechazada.fila}: {rechazada.resumen}")
    for record in records:
        for nota in record.notes:
            print(f"  AVISO línea {record.fila} ({record.terreno}): «{nota.valor}» en"
                  f" {nota.campo} no es un número; el campo queda vacío")
    if carga_maestra.no_cargadas(leido):
        print("  AVISO columnas no cargadas (la tabla maestra no las tiene): "
              + ", ".join(carga_maestra.no_cargadas(leido)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

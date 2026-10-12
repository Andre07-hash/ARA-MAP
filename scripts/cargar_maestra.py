"""Load a terrain CSV into one work base of the editable master table.

A trusted operations command, like scripts/cuentas.py: the web app has no bulk
load into the master table (the legacy import only fills the old `base` /
`terreno` workspace). It refuses to run without an explicitly named target and
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
import hashlib
import json
import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

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

    from server import auth, db, inventario, postgres
    from server.csv_importer import read_csv_bytes
    from server.errors import WorkbookError
    from server.matching import Disposition, classify
    from server.repo import inventario as repo
    from server.repo import maestra as repo_maestra

    try:
        leido = read_csv_bytes(Path(args.csv).expanduser().read_bytes(),
                               decimal_mode=args.decimales)
    except (OSError, WorkbookError) as exc:
        raise SystemExit(f"No se pudo leer el CSV: {exc}") from None

    # The same validation as a row saved from the table, for every row, before
    # the database is touched. TerrainRecord and the draft share field names.
    # The declared currency goes on the rows that carry a price, and nowhere else.
    records = [dataclasses.replace(r, moneda=args.moneda)
               if args.moneda and (r.asking_price is not None or r.asking_m2 is not None) else r
               for r in leido.records]
    filas: list[dict[str, Any]] = []
    errores: list[str] = []
    for record in records:
        crudos = {n: getattr(record, n) for n in inventario.EDITABLE if hasattr(record, n)}
        campos, malos = inventario.clean_changes({n: v for n, v in crudos.items() if v is not None})
        errores.extend(f"línea {record.fila} ({record.terreno}): {campo}: {mensaje}"
                       for campo, mensaje in malos.items())
        filas.append(campos)
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
        # covers it; on Postgres an archive committed mid-load is not waited for.
        # Lock it in server/repo/maestra.py if loads ever run beside live admins.
        bases = [b for b in repo_maestra.listar(conn, None, con_archivadas=True)
                 if args.base in (b["id"], b["nombre"])]
        if len(bases) != 1:
            raise SystemExit(f"La base de trabajo «{args.base}» "
                             + ("no existe" if not bases else "no es única; usa su id")
                             + "; no se escribió nada.")
        base = bases[0]
        if base["archivada"]:
            raise SystemExit(f"La base de trabajo «{base['nombre']}» está archivada;"
                             " no se escribió nada.")

        decisiones = classify(records, _existentes(conn, base["id"]))
        nuevas = 0
        omitidas: list[str] = []
        for decision in decisiones:
            record = records[decision.incoming_index]
            if decision.disposition is not Disposition.NUEVA:
                donde = (f"terreno {decision.existing_id}" if decision.existing_id
                         else "otra línea de este archivo")
                omitidas.append(f"línea {record.fila} ({record.terreno}): ya existe en {donde}"
                                + (f" · {decision.reason}" if decision.reason else ""))
                continue
            nuevas += 1
            if not args.dry_run:
                campos = filas[decision.incoming_index]
                pedido = hashlib.sha256(json.dumps(
                    {"base": base["id"], "campos": campos}, sort_keys=True,
                    ensure_ascii=False).encode("utf-8")).hexdigest()
                repo.crear(conn, campos, actor, f"carga-{uuid.uuid4()}", pedido, base["id"])

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
    if leido.columnas_no_reconocidas:
        print("  AVISO columnas no cargadas (la tabla maestra no las tiene): "
              + ", ".join(leido.columnas_no_reconocidas))
    return 0


def _existentes(conn: Any, base_id: str) -> list[dict[str, Any]]:
    """Every terrain of the base, archived ones included, shaped for classify()."""
    from server import inventario
    from server.matching import dedupe_key
    from server.repo import inventario as repo

    consulta = inventario.parse_query(
        {"limit": [str(inventario.MAX_LIST_LIMIT)], "include_archived": ["true"]},
        inventario.SCOPED_QUERY)
    existentes: list[dict[str, Any]] = []
    while True:
        pagina, _, cursor, _ = repo.listar(conn, consulta, base_id)
        existentes.extend(
            {**t["draft"], "id": t["id"], "clave_dedupe": dedupe_key(
                t["draft"]["terreno"] or "", t["draft"]["estado"], t["draft"]["municipio"])}
            for t in pagina)
        if cursor is None:
            return existentes
        consulta = {**consulta, "cursor": cursor}


if __name__ == "__main__":
    raise SystemExit(main())

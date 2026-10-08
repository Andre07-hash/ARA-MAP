"""Team accounts and roles: a trusted operations command, not a web feature.

An account is an operator unless created with --rol admin or changed with the
rol command; nothing promotes anyone automatically. An operator can do nothing
until an administrator grants a work base in the app. The command refuses to
run without an explicitly named target and never reads .env.local:

    python3 scripts/cuentas.py --sqlite RUTA/ara_map.db crear USUARIO "Nombre visible"
    python3 scripts/cuentas.py --sqlite RUTA crear USUARIO "Nombre visible" --rol admin
    python3 scripts/cuentas.py --url-env VARIABLE rol USUARIO admin
    python3 scripts/cuentas.py --url-env VARIABLE restablecer USUARIO
    python3 scripts/cuentas.py --url-env VARIABLE desactivar USUARIO
    python3 scripts/cuentas.py --url-env VARIABLE reactivar USUARIO
    python3 scripts/cuentas.py --sqlite RUTA listar

--url-env names an environment variable holding a Postgres URL (the URL itself
never goes on the command line). Passwords are read with a hidden prompt, or,
for automation, as one line from standard input with --password-stdin; never
from arguments. Resetting a password, deactivating or changing a role ends
that user's sessions. Every change is recorded in team_user_event under the
command's own identity (auth.ACTOR_CLI), in the same transaction.

A Postgres target must already be at the current schema: this command checks
and refuses, it never migrates (scripts/esquema.py does, as a release step).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cuentas del equipo de ARA Map.")
    destino = parser.add_mutually_exclusive_group(required=True)
    destino.add_argument("--sqlite", metavar="RUTA", help="archivo SQLite de destino")
    destino.add_argument("--url-env", metavar="VARIABLE",
                         help="variable de entorno con la URL de Postgres de destino")
    parser.add_argument("--password-stdin", action="store_true",
                        help="lee la contraseña como una línea de la entrada estándar")
    sub = parser.add_subparsers(dest="accion", required=True)
    crear = sub.add_parser("crear")
    crear.add_argument("usuario")
    crear.add_argument("nombre")
    crear.add_argument("--rol", choices=("operador", "admin"), default="operador")
    rol = sub.add_parser("rol")
    rol.add_argument("usuario")
    rol.add_argument("rol", choices=("operador", "admin"))
    for accion in ("restablecer", "desactivar", "reactivar"):
        sub.add_parser(accion).add_argument("usuario")
    sub.add_parser("listar")
    return parser


def _password(ask: Callable[[str], str]) -> str:
    primera = ask("Contraseña nueva: ")
    if ask("Repite la contraseña: ") != primera:
        raise SystemExit("Las contraseñas no coinciden; no se cambió nada.")
    return primera


def main(argv: Sequence[str] | None = None, ask: Callable[[str], str] = getpass.getpass) -> int:
    args = _parser().parse_args(argv)
    if args.password_stdin:
        linea = sys.stdin.readline().rstrip("\r\n")
        ask = lambda _prompt: linea  # noqa: E731 - same answer for both prompts
    if args.url_env:
        url = os.environ.get(args.url_env)
        if not url:
            raise SystemExit(f"{args.url_env} no está definida; no se usa ningún destino por omisión.")
        os.environ["ARA_MAP_DATABASE_URL"] = url
        sqlite_path = None
    else:
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        sqlite_path = Path(args.sqlite).expanduser().resolve()
        if args.accion != "crear" and not sqlite_path.exists():
            raise SystemExit(f"No existe {sqlite_path}.")

    from server import auth, db, postgres

    # One write transaction, entered the same way as every other change to
    # what authorization reads: an account change waits its turn behind a
    # write that already checked, and is recorded with its audit row or not at all.
    with db.escritura(sqlite_path) as conn:
        if sqlite_path is None and (postgres.schema_version(conn) or 0) < db.SCHEMA_VERSION:
            raise SystemExit(f"El destino Postgres no está en el esquema {db.SCHEMA_VERSION};"
                             " migra primero. Este comando no migra.")
        try:
            if args.accion == "crear":
                usuario = auth.create_user(conn, args.usuario, args.nombre, _password(ask),
                                           rol=args.rol)
                print(f"Cuenta creada: {usuario['login']} ({usuario['display_name']}),"
                      f" rol {usuario['rol']}.")
            elif args.accion == "rol":
                if auth.set_role(conn, args.usuario, args.rol):
                    print(f"Rol cambiado a {args.rol}; sus sesiones abiertas se cerraron.")
                else:
                    print(f"La cuenta ya tenía el rol {args.rol}; no se cambió nada.")
            elif args.accion == "restablecer":
                auth.set_password(conn, args.usuario, _password(ask))
                print("Contraseña cambiada; sus sesiones abiertas se cerraron.")
            elif args.accion in ("desactivar", "reactivar"):
                auth.set_active(conn, args.usuario, args.accion == "reactivar")
                print(f"Cuenta {'reactivada' if args.accion == 'reactivar' else 'desactivada'}.")
            else:
                for u in auth.list_users(conn):
                    estado = "activa" if u["active"] else "desactivada"
                    print(f"{u['login']}\t{u['display_name']}\t{u['rol']}\t{estado}\t{u['created_at']}")
        except auth.AccountError as exc:
            raise SystemExit(str(exc)) from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

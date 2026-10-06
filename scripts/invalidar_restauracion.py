"""Run against a RESTORED database before it serves any request.

A private disaster-recovery backup (pg_dump, Neon restore) carries everything,
including live sessions, pending Microsoft sign-ins and encrypted connector
credentials. This command, against an explicitly named target only:

* ends every team session and clears login throttling;
* deletes pending Microsoft authorizations;
* marks refreshes that were running at backup time as interrupted (their
  previous data stays active);
* with --olvidar-credenciales, also deletes connector credentials, so each
  Microsoft account shows "reconnect required" and is reconnected through the
  UI. Use it whenever the restored environment does not have the SAME token
  key/version as the one that wrote them, or the credentials should not be
  trusted (for example, a restore into another environment).

    python3 scripts/invalidar_restauracion.py --url-env RESTORED_DATABASE_URL [--olvidar-credenciales]

It never reads .env.local and refuses to run without --url-env.
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
    parser = argparse.ArgumentParser(description="Invalidación tras restaurar ARA Map.")
    parser.add_argument("--url-env", metavar="VARIABLE", required=True)
    parser.add_argument("--olvidar-credenciales", action="store_true")
    args = parser.parse_args(argv)
    url = os.environ.get(args.url_env)
    if not url:
        raise SystemExit(f"{args.url_env} no está definida; no se usa ningún destino por omisión.")
    os.environ["ARA_MAP_DATABASE_URL"] = url

    from server import db, postgres

    with postgres.session() as conn:
        conteos = {
            "sesiones": conn.execute("DELETE FROM team_session").rowcount,
            "intentos_de_acceso": conn.execute("DELETE FROM team_login_failure").rowcount,
            "autorizaciones_microsoft": conn.execute("DELETE FROM excel_autorizacion").rowcount,
            "actualizaciones_interrumpidas": conn.execute(
                "UPDATE excel_ejecucion SET estado = 'interrumpida', terminada_en = ?,"
                " error_codigo = 'restauracion', error_mensaje = 'Interrumpida por una restauración.'"
                " WHERE estado = 'en_curso'", (db.now(),)).rowcount,
        }
        if args.olvidar_credenciales:
            conteos["credenciales_olvidadas"] = conn.execute("DELETE FROM excel_credencial").rowcount
    for nombre, n in conteos.items():
        print(f"{nombre}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

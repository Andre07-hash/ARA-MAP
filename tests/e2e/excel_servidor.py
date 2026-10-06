"""Disposable server for tests/e2e/excel-conectado.mjs. Local only.

The real cloud adapter (api/index.py) on 127.0.0.1, a fresh schema in a
DISPOSABLE Postgres, and the local fake Microsoft (tests/fake_microsoft.py)
standing in for sign-in, Graph and OneDrive. Fictional users and workbook.

    ARA_MAP_TEST_DATABASE_URL=postgresql://…@127.0.0.1:…/… ARA_E2E_PW=… \\
        python3 tests/e2e/excel_servidor.py 8461 /ruta/estado.json

Writes {"url", "fake"} to the given JSON path once ready; drops its schema on
exit (Ctrl-C / SIGTERM). Refuses a database that is not on 127.0.0.1.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    puerto, salida = int(sys.argv[1]), Path(sys.argv[2])
    url = os.environ.get("ARA_MAP_TEST_DATABASE_URL", "")
    clave = os.environ.get("ARA_E2E_PW", "")
    if "@127.0.0.1:" not in url or not clave:
        raise SystemExit("Hace falta ARA_MAP_TEST_DATABASE_URL en 127.0.0.1 y ARA_E2E_PW.")
    import psycopg
    from psycopg.conninfo import make_conninfo

    from tests.excel_support import BASICO, libro
    from tests.fake_microsoft import FakeMicrosoft

    esquema = "test_ara_e2e_" + uuid.uuid4().hex
    with psycopg.connect(url) as conn:
        conn.execute(f'CREATE SCHEMA "{esquema}"')
    fake = FakeMicrosoft()
    os.environ.update({
        "ARA_MAP_DATABASE_URL": make_conninfo(url, options=f"-c search_path={esquema}"),
        "ARA_MAP_MS_CLIENT_ID": fake.client_id, "ARA_MAP_MS_CLIENT_SECRET": fake.secret,
        "ARA_MAP_MS_REDIRECT_URI": f"http://127.0.0.1:{puerto}/api/microsoft/callback",
        "ARA_MAP_MS_TEST_HOST": fake.host,
        "ARA_MAP_TOKEN_KEY": "clave-e2e-ficticia-de-32-caracteres-o-mas-xx",
        "ARA_MAP_TOKEN_KEY_VERSION": "e2e-1"})
    os.environ.pop("DATABASE_URL", None)

    from server import auth, postgres
    with postgres.session() as conn:
        conn.raw.execute(postgres.schema_sql(), prepare=False)
        postgres.migrate(conn)
        for n in ("ana", "beto"):
            auth.create_user(conn, n, n.capitalize(), clave, iterations=1000)
    fake.usuario("dueno", "Dueño Ficticio")
    fake.archivo("dueno", "item-libro", "Terrenos Ficticios.xlsx", libro(BASICO))
    fake.usuario_navegador = "dueno"

    import importlib.util
    spec = importlib.util.spec_from_file_location("adaptador_e2e", ROOT / "api" / "index.py")
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    httpd = ThreadingHTTPServer(("127.0.0.1", puerto), modulo.handler)

    def terminar(*_: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminar)
    salida.write_text(json.dumps({"url": f"http://127.0.0.1:{puerto}", "fake": f"http://{fake.host}"}))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        fake.cerrar()
        with psycopg.connect(url) as conn:
            conn.execute(f'DROP SCHEMA "{esquema}" CASCADE')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

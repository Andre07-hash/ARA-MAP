"""Packet 3A measurement: what the `archivos`/`ubicacion` siblings cost per page.

    python3 reports/team-a-application-integration-2026-10-09/medir_resumenes.py            # SQLite, temporary file
    ARA_MAP_TEST_DATABASE_URL=postgresql://.../desechable python3 .../medir_resumenes.py    # disposable Postgres

Synthetic data only (tests/e2e/tabla_servidor.py): 25,000 terrains, 3,000 of
them in "Base Grande" granted to five operators. A share of the first page is
given a PDF attachment row and a KMZ attachment row written straight to the
tables (no versions, no bytes): this measures the list, not uploads. It compares, for one operator
session and several page sizes, the 2A list (repository page alone) with the
3A list (the handler, which adds the attachment service's summaries and the
active descriptors). On SQLite it also counts statements. Prints JSON.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests" / "e2e"))

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
REGISTROS, CON_ARCHIVOS, VUELTAS = 25_000, 60, 7


def preparar() -> tuple[str, object]:
    """A disposable database with the synthetic set; returns (base id, cleanup)."""
    if URL:
        import psycopg
        from psycopg.conninfo import make_conninfo
        esquema = "medir_3a_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{esquema}"')
        os.environ["ARA_MAP_DATABASE_URL"] = make_conninfo(URL, options=f"-c search_path={esquema}")
        from server import postgres
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

        def limpiar() -> None:
            with psycopg.connect(URL) as conn:
                conn.execute(f'DROP SCHEMA "{esquema}" CASCADE')
    else:
        carpeta = tempfile.TemporaryDirectory()
        os.environ["ARA_MAP_DB"] = str(Path(carpeta.name) / "medir.db")
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        limpiar = carpeta.cleanup
    from server import db
    db.connect().close()
    import tabla_servidor
    tabla_servidor.sembrar(REGISTROS)
    with db.escritura() as conn:
        base = conn.execute("SELECT id FROM maestra_base WHERE nombre = 'Base Grande'").fetchone()["id"]
        ada = conn.execute("SELECT id FROM team_user WHERE login = 'ada'").fetchone()["id"]
        filas = conn.execute("SELECT id FROM inventory_terrain WHERE base_id = ? ORDER BY id LIMIT ?",
                             (base, CON_ARCHIVOS)).fetchall()
        ahora = db.now()
        for fila in filas:
            for tipo, columna in (("pdf", "core:archivos"), ("kmz", "core:kmz")):
                conn.execute("INSERT INTO archivo (id, inventory_id, columna_id, tipo, revision,"
                             " creado_en, creado_por, actualizado_en, actualizado_por)"
                             " VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
                             (str(uuid.uuid4()), fila["id"], columna, tipo, ahora, ada, ahora, ada))
    return base, limpiar


def main() -> None:
    base, limpiar = preparar()
    try:
        from server import auth, db, inventario
        from server.api import inventario as api
        from server.repo import inventario as repo
        from server.router import Request
        from server.web_util import encode
        from tests.support import TEST_PASSWORD
        with db.session() as conn:
            token, _, _ = auth.login(conn, "olga", TEST_PASSWORD)
        with db.session() as conn:
            sesion = auth.sesion_de_token(conn, token)
        salida: dict = {"backend": "postgres" if URL else "sqlite", "registros": REGISTROS,
                        "en_la_base": 3000, "con_archivos_en_la_primera_pagina": CON_ARCHIVOS, "paginas": []}
        for limite in (50, 100, 200):
            consulta = {"limit": [str(limite)]}

            def pedir() -> Request:
                return Request(method="GET", path="", query=consulta, params={"bid": base}, body=b"",
                               headers={}, user=sesion.actor, sesion=sesion)

            def solo_2a() -> bytes:
                with db.session() as conn:
                    auth.require_base(pedir(), base, "maestra.ver", conn)
                    q = inventario.parse_query(consulta, inventario.SCOPED_QUERY)
                    t, total, cursor, facets = repo.listar(conn, q, base)
                return encode({"terrenos": t, "total": total, "next_cursor": cursor, "facets": facets})

            def con_3a() -> bytes:
                return encode(api.base_listing(pedir()))

            fila: dict = {"limit": limite}
            for nombre, fn in (("lista_2a", solo_2a), ("lista_3a", con_3a)):
                fn()
                tiempos = []
                for _ in range(VUELTAS):
                    t0 = time.perf_counter()
                    cuerpo = fn()
                    tiempos.append((time.perf_counter() - t0) * 1000)
                fila[nombre] = {"ms_mediana": round(statistics.median(tiempos), 1),
                                "ms_max": round(max(tiempos), 1), "bytes": len(cuerpo)}
                if not URL:
                    cuenta = [0]
                    original = db.connect

                    def contando(*a: object, **k: object):
                        conn = original(*a, **k)
                        conn.set_trace_callback(lambda _s: cuenta.__setitem__(0, cuenta[0] + 1))
                        return conn
                    db.connect = contando
                    try:
                        fn()
                    finally:
                        db.connect = original
                    fila[nombre]["sentencias_sql"] = cuenta[0]
            salida["paginas"].append(fila)
        print(json.dumps(salida, indent=2))
    finally:
        limpiar()


if __name__ == "__main__":
    main()

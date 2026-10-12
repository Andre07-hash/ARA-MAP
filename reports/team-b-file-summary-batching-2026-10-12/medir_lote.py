"""R3-A1: statements and time of the file summaries, for the tree it runs in.

    python3 reports/team-b-file-summary-batching-2026-10-12/medir_lote.py              # SQLite, temporary file
    ARA_MAP_TEST_DATABASE_URL=postgresql://.../desechable python3 .../medir_lote.py    # disposable Postgres

Run it unchanged in an archive of the base and in an archive of the change:
the data, the session and the method are the same, so the two outputs compare
before and after. Dataset: Team A's 3A measurement (its `preparar`: 25,000
synthetic terrains, 3,000 in "Base Grande", 60 of them with a PDF and a KMZ row).
One operator session; pages of 1, 50, 100 and 200 terrains of that base.

Two levels, each counted by wrapping the connection's execute (both backends):
- servicio: archivos.resumenes_de_archivos alone, on one open connection;
- handler:  GET /api/maestra/bases/:bid/terrenos (api.base_listing) as a whole.
Times are medians of 9 rounds after one warm-up, on this machine only: they
compare before and after, they are not a target. Prints JSON.
"""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
A = RAIZ / "reports" / "team-a-application-integration-2026-10-09" / "medir_resumenes.py"
VUELTAS = 9


def cargar_preparar():
    spec = importlib.util.spec_from_file_location("medir_resumenes_a", A)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


class Contador:
    def __init__(self, conn) -> None:
        self._conn, self.n = conn, 0

    def execute(self, *a, **k):
        self.n += 1
        return self._conn.execute(*a, **k)

    def __getattr__(self, nombre):
        return getattr(self._conn, nombre)


def main() -> None:
    a = cargar_preparar()
    base, limpiar = a.preparar()
    try:
        from server import archivos, auth, db, postgres
        from server.api import inventario as api
        from server.repo import inventario as repo
        from server.router import Request
        from server.web_util import encode
        from tests.support import TEST_PASSWORD
        with db.session() as conn:
            token, _, _ = auth.login(conn, "olga", TEST_PASSWORD)
        with db.session() as conn:
            sesion = auth.sesion_de_token(conn, token)
            q = __import__("server.inventario", fromlist=["x"])
            ids = [t["id"] for t in repo.listar(conn, q.parse_query({"limit": ["200"]}, q.SCOPED_QUERY), base)[0]]

        # Count every statement of the handler, whatever connection it opens.
        cuenta = [0]
        sqlite_conectar = db.connect

        def contando(*args, **kwargs):
            conn = sqlite_conectar(*args, **kwargs)
            conn.set_trace_callback(lambda _s: cuenta.__setitem__(0, cuenta[0] + 1))
            return conn
        pg_execute = postgres.Connection.execute

        def pg_contando(self, *args, **kwargs):
            cuenta[0] += 1
            return pg_execute(self, *args, **kwargs)

        def medir(fn):
            fn()
            tiempos = []
            for _ in range(VUELTAS):
                t0 = time.perf_counter()
                fn()
                tiempos.append((time.perf_counter() - t0) * 1000)
            return round(statistics.median(tiempos), 2)

        try:   # present only in trees that carry R3-A1's tests
            from tests.test_resumenes_lote import resumenes_anteriores as referencia
        except ImportError:
            referencia = None
        ahora = db.now()
        salida = {"backend": "postgres" if a.URL else "sqlite", "arbol": str(RAIZ.name),
                  "paginas": []}
        for n in (1, 50, 100, 200):
            pagina = ids[:n]
            fila: dict = {"terrenos": n}

            def servicio() -> dict:
                with db.session() as conn:
                    return archivos.resumenes_de_archivos(conn, pagina, sesion)
            with db.session() as conn:
                c = Contador(conn)
                r = archivos.resumenes_de_archivos(c, pagina, sesion)
            fila["servicio"] = {"sentencias": c.n, "ms_mediana": medir(servicio),
                                "con_archivos": sum(1 for v in r["resultados"].values()
                                                    if v["pdf_total"] or v["kmz"])}
            if referencia is not None:
                # Same data, same connection: the old per-terrain algorithm's answer.
                with db.session() as conn:
                    viejo = referencia(conn, pagina, sesion, ahora)
                    nuevo = archivos.resumenes_de_archivos(conn, pagina, sesion, reloj=lambda: ahora)
                fila["servicio"]["igual_a_la_referencia"] = (
                    viejo == nuevo and list(viejo["resultados"]) == list(nuevo["resultados"]))

            consulta = {"limit": [str(n)]}

            def handler() -> bytes:
                return encode(api.base_listing(Request(method="GET", path="", query=consulta,
                                                       params={"bid": base}, body=b"", headers={},
                                                       user=sesion.actor, sesion=sesion)))
            cuenta[0] = 0
            db.connect, postgres.Connection.execute = contando, pg_contando
            try:
                cuerpo = handler()
            finally:
                db.connect, postgres.Connection.execute = sqlite_conectar, pg_execute
            fila["handler"] = {"sentencias": cuenta[0], "ms_mediana": medir(handler), "bytes": len(cuerpo)}
            salida["paginas"].append(fila)
        print(json.dumps(salida, indent=2))
    finally:
        limpiar()


if __name__ == "__main__":
    main()

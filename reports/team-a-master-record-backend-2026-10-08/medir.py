"""Backend measurement for the terrain lists: 25,000 synthetic records, one
3,000-record work base, five editing sessions.

    python3 reports/team-a-master-record-backend-2026-10-08/medir.py            # SQLite, temp file
    ARA_MAP_TEST_DATABASE_URL=postgresql://… python3 …/medir.py --postgres     # disposable schema

Everything is fictional and disposable: a temporary SQLite file, or a schema
it creates and drops in the database named by ARA_MAP_TEST_DATABASE_URL. It
never reads the application's configured database. Requests go through the
real HTTP dispatcher with real sessions; query counts and plans are taken
from the repository call the handler makes.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

POSTGRES = "--postgres" in sys.argv
TOTAL, BASE_GRANDE, OTRAS_BASES, SIN_ASIGNAR = 25_000, 3_000, 10, 1_000
ESTADOS = ["Jalisco", "Nuevo León", "Querétaro", "Yucatán", "Sonora", "Michoacán", "Puebla", "Colima"]
TIPOS = ["Industrial", "Agrícola", "Comercial", "Habitacional", None]
CLAVE = "contraseña-ficticia-larga"


def preparar_base_de_datos():
    if POSTGRES:
        import psycopg
        from psycopg.conninfo import make_conninfo
        url = os.environ["ARA_MAP_TEST_DATABASE_URL"]
        schema = "medicion_ara_" + uuid.uuid4().hex
        with psycopg.connect(url) as conn:
            conn.execute(f'CREATE SCHEMA "{schema}"')
        os.environ["ARA_MAP_DATABASE_URL"] = make_conninfo(url, options=f"-c search_path={schema}")
        from server import postgres
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

        def limpiar():
            with psycopg.connect(url) as conn:
                conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        return limpiar
    os.environ.pop("ARA_MAP_DATABASE_URL", None)
    directorio = tempfile.TemporaryDirectory()
    os.environ["ARA_MAP_DB"] = str(Path(directorio.name) / "medicion.db")
    return directorio.cleanup


def sembrar():
    from server import auth, db
    with db.escritura() as conn:
        ids = {n: auth.create_user(conn, n, n.capitalize() + " Ficticia", CLAVE, iterations=1000,
                                   rol="admin" if n == "ada" else "operador")["id"]
               for n in ("ada", "olga", "omar", "oscar", "olivia", "oriol")}
        ahora, ada = db.now(), ids["ada"]
        bases = [str(uuid.uuid4()) for _ in range(OTRAS_BASES + 1)]
        for n, base in enumerate(bases):
            conn.execute("INSERT INTO maestra_base (id, nombre, created_at, created_by, updated_at,"
                         " updated_by) VALUES (?, ?, ?, ?, ?, ?)",
                         (base, "Base Grande" if n == 0 else f"Base {n:02d}", ahora, ada, ahora, ada))
        for login in ("olga", "omar", "oscar", "olivia", "oriol"):
            conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                         " VALUES (?, ?, ?, ?)", (bases[0], ids[login], ahora, ada))
        for n in range(TOTAL):
            if n < BASE_GRANDE:
                base = bases[0]
            elif n < TOTAL - SIN_ASIGNAR:
                base = bases[1 + n % OTRAS_BASES]
            else:
                base = None
            tid, rid = str(uuid.uuid4()), str(uuid.uuid4())
            estado = ESTADOS[n % len(ESTADOS)]
            conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                         " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                         (tid, base, ahora, ada, ahora, ada))
            conn.execute(
                "INSERT INTO inventory_revision (id, inventory_id, revision_number, terreno, estado,"
                " municipio, tipo_terreno, superficie_m2, asking_price, moneda, lat, lon, base_id,"
                " created_at, created_by) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, tid, None if n % 97 == 0 else f"Lote {'Ñandú' if n % 5 == 0 else 'Árbol'} {n}",
                 estado, f"Municipio {n % 40}", TIPOS[n % len(TIPOS)],
                 None if n % 11 == 0 else 500 + (n * 37) % 90_000,
                 None if n % 7 == 0 else 100_000 + (n * 911) % 9_000_000,
                 (None, "USD", "MXN")[n % 3], 20 + (n % 50) / 100, -103 - (n % 50) / 100, base,
                 ahora, ada))
            conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?", (rid, tid))
            conn.execute("INSERT INTO inventory_event (id, inventory_id, version, action, actor_id,"
                         " actor_name, at, after_revision_id, details_json) VALUES (?, ?, 1, 'create',"
                         " ?, 'Ada Ficticia', ?, ?, '{}')", (str(uuid.uuid4()), tid, ada, ahora, rid))
    return ids, bases


class Cliente:
    def __init__(self):
        from server import app
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.raiz = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def entrar(self, login):
        peticion = urllib.request.Request(
            self.raiz + "/api/login", method="POST", headers={"Content-Type": "application/json"},
            data=json.dumps({"username": login, "password": CLAVE}).encode())
        with urllib.request.urlopen(peticion, timeout=60) as r:
            return r.headers["Set-Cookie"].split(";")[0]

    def pedir(self, method, path, cookie, body=None):
        peticion = urllib.request.Request(
            self.raiz + path, method=method, headers={"Cookie": cookie, "Content-Type": "application/json"},
            data=json.dumps(body).encode() if body is not None else None)
        inicio = time.perf_counter()
        try:
            with urllib.request.urlopen(peticion, timeout=120) as r:
                crudo, status = r.read(), r.status
        except urllib.error.HTTPError as error:
            with error:
                crudo, status = error.read(), error.code
        return status, crudo, (time.perf_counter() - inicio) * 1000


def consultas_y_planes(query, base_id):
    """How many statements one list costs, and the plans of its count and page."""
    import sqlite3
    from urllib.parse import parse_qs

    from server import db, inventario
    from server.repo import inventario as repo
    q = inventario.parse_query(parse_qs(query), inventario.SCOPED_QUERY if base_id else inventario.INTERNAL_QUERY)
    with db.session() as conn:
        vistas = []
        if isinstance(conn, sqlite3.Connection):
            conn.set_trace_callback(vistas.append)
            repo.listar(conn, q, base_id)
            conn.set_trace_callback(None)
            planes = [[" ".join(str(c) for c in fila) for fila in conn.execute("EXPLAIN QUERY PLAN " + s)]
                      for s in vistas[:2]]
        else:
            ejecutar = conn.execute

            class Contador:
                raw = conn.raw

                def execute(self, sentencia, params=None):
                    vistas.append((sentencia, params))
                    return ejecutar(sentencia, params)
            repo.listar(Contador(), q, base_id)
            planes = [[fila[0] for fila in ejecutar("EXPLAIN " + s, p)] for s, p in vistas[:2]]
    return len(vistas), planes


def main():
    limpiar = preparar_base_de_datos()
    try:
        inicio = time.perf_counter()
        ids, bases = sembrar()
        siembra = time.perf_counter() - inicio
        if POSTGRES:
            # A bulk load leaves the planner with no statistics until autovacuum
            # analyzes the tables, which a database in service has had. Without
            # this the first minutes after a load pick nested loops over 25,000
            # rows (measured: seconds instead of tens of milliseconds).
            from server import postgres
            with postgres.session() as conn:
                conn.raw.execute("ANALYZE")
        cliente = Cliente()
        ada, olga = cliente.entrar("ada"), cliente.entrar("olga")
        grande = f"/api/maestra/bases/{bases[0]}/terrenos"
        operaciones = [
            ("Master table, default page (100)", "/api/inventario/terrenos", "", ada, None),
            ("Master table, 200 rows", "/api/inventario/terrenos", "limit=200", ada, None),
            ("Master table, state + type filter", "/api/inventario/terrenos",
             "estado=Jalisco&tipo_terreno=Industrial", ada, None),
            ("Master table, price range in USD", "/api/inventario/terrenos",
             "moneda=USD&price_min=500000&price_max=2000000", ada, None),
            ("Master table, search 'nandu 12'", "/api/inventario/terrenos", "q=nandu%2012", ada, None),
            ("Master table, one base + unassigned", "/api/inventario/terrenos",
             f"base={bases[3]}&base=sin_asignar", ada, None),
            ("Master table, sorted by name", "/api/inventario/terrenos", "sort=terreno", ada, None),
            ("Master table, sorted by area, descending", "/api/inventario/terrenos", "sort=-superficie_m2", ada, None),
            ("Master table, attention=false (no record matches: the whole scan)", "/api/inventario/terrenos",
             "attention=false", ada, None),
            ("Master table, attention=true", "/api/inventario/terrenos", "attention=true", ada, None),
            ("Master table, attention=true, 200 rows sorted by name", "/api/inventario/terrenos",
             "attention=true&limit=200&sort=terreno", ada, None),
            ("Master table, attention=true + state filter", "/api/inventario/terrenos",
             "attention=true&estado=Jalisco", ada, None),
            ("3,000-record base, operator, attention=true", grande, "attention=true", olga, bases[0]),
            ("3,000-record base, operator, attention=false", grande, "attention=false", olga, bases[0]),
            ("3,000-record base, operator, default page", grande, "", olga, bases[0]),
            ("3,000-record base, operator, 200 rows sorted by name", grande, "limit=200&sort=terreno", olga, bases[0]),
            ("3,000-record base, operator, search", grande, "q=arbol%201", olga, bases[0]),
            ("3,000-record base, operator, state filter", grande, "estado=Sonora", olga, bases[0]),
        ]
        filas, planes = [], {}
        for nombre, ruta, query, cookie, base in operaciones:
            tiempos = []
            for _ in range(5):
                status, crudo, ms = cliente.pedir("GET", ruta + (f"?{query}" if query else ""), cookie)
                assert status == 200, (nombre, status, crudo[:200])
                tiempos.append(ms)
            cuerpo = json.loads(crudo)
            n, plan = consultas_y_planes(query, base)
            planes[nombre] = plan
            filas.append({"operacion": nombre, "total": cuerpo["total"], "filas": len(cuerpo["terrenos"]),
                          "bytes": len(crudo), "consultas_sql": n,
                          "ms_mediana": round(statistics.median(tiempos), 1), "ms_max": round(max(tiempos), 1)})
        # A deep page: follow the cursor ten pages into the master table, sorted by name.
        cursor, tiempos = None, []
        for _ in range(10):
            status, crudo, ms = cliente.pedir(
                "GET", "/api/inventario/terrenos?sort=terreno&limit=200" + (f"&cursor={cursor}" if cursor else ""), ada)
            cursor = json.loads(crudo)["next_cursor"]
            tiempos.append(ms)
        filas.append({"operacion": "Master table, pages 1-10 of 200 by cursor, sorted by name", "total": TOTAL,
                      "filas": 200, "bytes": len(crudo), "consultas_sql": filas[1]["consultas_sql"],
                      "ms_mediana": round(statistics.median(tiempos), 1), "ms_max": round(max(tiempos), 1)})

        # Five editing sessions in the 3,000-record base.
        sesiones = [cliente.entrar(n) for n in ("olga", "omar", "oscar", "olivia", "oriol")]
        pagina = json.loads(cliente.pedir("GET", grande + "?limit=101", olga)[1])["terrenos"]
        disputado, propios = pagina[0]["id"], [t["id"] for t in pagina[1:101]]
        resultados, tiempos, barrera = [], [], threading.Barrier(5)

        def editar_distintos(numero):
            barrera.wait()
            for tid in propios[numero::5]:
                status, _, ms = cliente.pedir("PATCH", f"/api/inventario/terrenos/{tid}", sesiones[numero],
                                              {"expected_version": 1, "changes": {"municipio": f"Sesión {numero}"}})
                resultados.append(status)
                tiempos.append(ms)
        hilos = [threading.Thread(target=editar_distintos, args=(n,)) for n in range(5)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        distintos = {"ediciones": len(resultados), "aceptadas": resultados.count(200),
                     "otras": sorted(set(resultados) - {200}),
                     "ms_mediana": round(statistics.median(tiempos), 1), "ms_max": round(max(tiempos), 1)}
        mismos, barrera = [], threading.Barrier(5)

        def editar_el_mismo(numero):
            barrera.wait()
            mismos.append(cliente.pedir("PATCH", f"/api/inventario/terrenos/{disputado}", sesiones[numero],
                                        {"expected_version": 1, "changes": {"municipio": f"Sesión {numero}"}})[0])
        hilos = [threading.Thread(target=editar_el_mismo, args=(n,)) for n in range(5)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        from server import db
        with db.session() as conn:
            estado = dict(conn.execute(
                "SELECT t.version, (SELECT COUNT(*) FROM inventory_revision r WHERE r.inventory_id = t.id)"
                " AS revisiones, (SELECT COUNT(*) FROM inventory_event e WHERE e.inventory_id = t.id)"
                " AS eventos FROM inventory_terrain t WHERE t.id = ?", (disputado,)).fetchone())
        resultado = {
            "motor": "PostgreSQL (disposable schema)" if POSTGRES else "SQLite (temporary file)",
            "python": sys.version.split()[0], "registros": TOTAL, "base_grande": BASE_GRANDE,
            "segundos_de_siembra": round(siembra, 1), "listas": filas,
            "cinco_sesiones_registros_distintos": distintos,
            "cinco_sesiones_mismo_registro": {"respuestas": sorted(mismos), **estado},
            "planes": planes,
        }
        print(json.dumps(resultado, ensure_ascii=False, indent=1))
    finally:
        limpiar()


if __name__ == "__main__":
    main()

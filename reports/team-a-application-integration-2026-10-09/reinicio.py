"""Packet 3A: stored files survive a restart of the local server.

    python3 reports/team-a-application-integration-2026-10-09/reinicio.py             # SQLite + sibling folder
    ARA_MAP_TEST_DATABASE_URL=postgresql://.../desechable python3 .../reinicio.py     # disposable Postgres + named folder

Starts the real local server (server.app.serve) as a separate process against
one disposable database and one disk folder, uploads a fictional PDF and KMZ
through the mounted routes as an operator, STOPS the process, starts a new one
against the SAME database and folder, and checks from a new session of another
authorized account that the bytes, hash, history and active boundary are
there; an account with no grant is refused. Prints JSON. Nothing is kept.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
PUERTO = 8441

SERVIDOR = ("import sys; sys.path.insert(0, %r); from server import app; "
            "app.serve(%d, open_browser=False)" % (str(RAIZ), PUERTO))


def pedir(metodo: str, ruta: str, cookie: str | None = None, datos: object = None,
          cuerpo: bytes | None = None, cabeceras: dict | None = None) -> tuple[int, dict, bytes]:
    h = dict(cabeceras or {})
    if cookie:
        h["Cookie"] = cookie
    if datos is not None:
        cuerpo = json.dumps(datos).encode()
        h["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection("127.0.0.1", PUERTO, timeout=60)
    try:
        conn.request(metodo, ruta, body=cuerpo, headers=h)
        r = conn.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        conn.close()


def entrar(login: str, clave: str) -> str:
    s, h, _ = pedir("POST", "/api/login", datos={"username": login, "password": clave})
    assert s == 200, s
    return h["Set-Cookie"].split(";", 1)[0]


def arrancar(entorno: dict) -> subprocess.Popen:
    proceso = subprocess.Popen([sys.executable, "-c", SERVIDOR], env=entorno, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    for _ in range(100):
        try:
            if pedir("GET", "/api/config")[0] == 200:
                return proceso
        except OSError:
            time.sleep(0.1)
    proceso.kill()
    raise SystemExit("El servidor no arrancó: " + (proceso.stdout.read() if proceso.stdout else ""))


def main() -> None:
    carpeta = tempfile.TemporaryDirectory()
    entorno = {k: v for k, v in os.environ.items()
               if k not in ("ARA_MAP_DATABASE_URL", "DATABASE_URL", "ARA_MAP_READ_ONLY", "ARA_MAP_ARCHIVOS")}
    limpiar = carpeta.cleanup
    if URL:
        import psycopg
        from psycopg.conninfo import make_conninfo
        esquema = "reinicio_3a_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{esquema}"')
        entorno["ARA_MAP_DATABASE_URL"] = make_conninfo(URL, options=f"-c search_path={esquema}")
        entorno["ARA_MAP_ARCHIVOS"] = str(Path(carpeta.name) / "archivos-nombrados")

        def limpiar() -> None:  # noqa: F811
            with psycopg.connect(URL) as conn:
                conn.execute(f'DROP SCHEMA "{esquema}" CASCADE')
            carpeta.cleanup()
    else:
        entorno["ARA_MAP_DB"] = str(Path(carpeta.name) / "reinicio.db")
    os.environ.update({k: v for k, v in entorno.items() if k.startswith("ARA_MAP_")})
    for k in ("ARA_MAP_DATABASE_URL", "ARA_MAP_ARCHIVOS", "ARA_MAP_DB"):
        if k not in entorno:
            os.environ.pop(k, None)
    try:
        from server import auth, db, postgres
        from tests.support import TEST_PASSWORD
        from tests.test_archivos_http import PDF, kmz
        if URL:
            with postgres.session() as conn:
                conn.raw.execute(postgres.schema_sql(), prepare=False)
                postgres.migrate(conn)
        db.connect().close()
        with db.escritura() as conn:
            for login, rol in (("ada", "admin"), ("olga", "operador"), ("omar", "operador"),
                               ("otto", "operador")):
                auth.create_user(conn, login, login.capitalize() + " Ficticia", TEST_PASSWORD,
                                 iterations=1000, rol=rol)
        archivos = {"pdf": PDF, "kmz": kmz("poligono_simple")}
        salida: dict = {"backend": "postgres" if URL else "sqlite", "pasos": []}

        # -- first process: create, upload ------------------------------------------------
        proceso = arrancar(entorno)
        try:
            ada = entrar("ada", TEST_PASSWORD)
            s, _, c = pedir("POST", "/api/maestra/bases", ada, {"nombre": "Base Reinicio Ficticia"})
            base = json.loads(c)["base"]
            s, _, c = pedir("GET", "/api/maestra/operadores?limit=200", ada)
            ids = [u["id"] for u in json.loads(c)["usuarios"] if u["login"] in ("olga", "omar")]
            s, _, c = pedir("PUT", f"/api/maestra/bases/{base['id']}/acceso", ada,
                            {"expected_version": base["version"], "usuarios": ids})
            assert s == 200, c
            olga = entrar("olga", TEST_PASSWORD)
            s, _, c = pedir("POST", f"/api/maestra/bases/{base['id']}/terrenos", olga, {},
                            cabeceras={"Idempotency-Key": str(uuid.uuid4())})
            terreno = json.loads(c)["terreno"]
            versiones = {}
            for tipo, contenido in archivos.items():
                s, _, c = pedir("POST", f"/api/inventario/terrenos/{terreno['id']}/archivos", olga,
                                {"tipo": tipo, "nombre_original": f"ficticio.{tipo}",
                                 "tamano_declarado": len(contenido),
                                 "sha256_declarado": hashlib.sha256(contenido).hexdigest()},
                                cabeceras={"Idempotency-Key": str(uuid.uuid4())})
                assert s == 200, c
                inicio = json.loads(c)
                s, _, c = pedir("PUT", f"/api/archivos/versiones/{inicio['version_id']}/contenido", olga,
                                cuerpo=contenido, cabeceras={"Content-Type": "application/octet-stream"})
                assert s == 200, c
                s, _, c = pedir("POST", f"/api/archivos/versiones/{inicio['version_id']}/completar", olga)
                assert s == 200, c
                versiones[tipo] = {"vid": inicio["version_id"], "aid": inicio["archivo_id"]}
            s, _, c = pedir("GET", f"/api/inventario/terrenos/{terreno['id']}", olga)
            antes = json.loads(c)["terreno"]
            salida["pasos"].append({"proceso": 1, "pid": proceso.pid, "subidos": sorted(versiones),
                                    "modo": antes["ubicacion"]["modo"]})
        finally:
            proceso.terminate()
            proceso.wait(timeout=20)
        try:
            pedir("GET", "/api/config")
            raise SystemExit("El primer servidor sigue respondiendo.")
        except OSError:
            salida["pasos"].append({"proceso": 1, "detenido": True})

        # -- second process: same database, same folder -------------------------------------
        proceso = arrancar(entorno)
        try:
            omar = entrar("omar", TEST_PASSWORD)      # another authorized account, a new session
            otto = entrar("otto", TEST_PASSWORD)      # no grant
            comprobado = {}
            for tipo, contenido in archivos.items():
                s, h, c = pedir("GET", f"/api/archivos/versiones/{versiones[tipo]['vid']}/descarga", omar)
                s2, _, hist = pedir("GET", f"/api/archivos/{versiones[tipo]['aid']}/historial", omar)
                s3, _, c3 = pedir("GET", f"/api/archivos/versiones/{versiones[tipo]['vid']}/descarga", otto)
                comprobado[tipo] = {
                    "descarga": s, "bytes_iguales": c == contenido,
                    "sha256_igual": hashlib.sha256(c).hexdigest() == hashlib.sha256(contenido).hexdigest(),
                    "historial": s2, "eventos": len(json.loads(hist)["eventos"]) if s2 == 200 else None,
                    "sin_acceso": s3, "sin_acceso_recibe_bytes": contenido[:16] in c3}
            s, _, c = pedir("GET", f"/api/inventario/terrenos/{terreno['id']}", omar)
            despues = json.loads(c)["terreno"]
            gid = despues["ubicacion"]["geometria"]["id"]
            s, h, cuerpo = pedir("GET", f"/api/archivos/geometrias/{gid}/contenido?desde=0", omar)
            salida["pasos"].append({
                "proceso": 2, "pid": proceso.pid, "archivos": comprobado,
                "misma_geometria": gid == antes["ubicacion"]["geometria"]["id"],
                "mismo_resumen": despues["archivos"] == antes["archivos"],
                "contorno": {"estado": s, "sha256_coincide":
                             hashlib.sha256(cuerpo).hexdigest() == h.get("X-Geometria-Sha256")},
                "version_del_terreno_sin_cambio": despues["version"] == terreno["version"],
                "sin_acceso_terreno": pedir("GET", f"/api/inventario/terrenos/{terreno['id']}", otto)[0]})
        finally:
            proceso.terminate()
            proceso.wait(timeout=20)
        print(json.dumps(salida, indent=2))
    finally:
        limpiar()


if __name__ == "__main__":
    main()

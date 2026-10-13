"""Local rehearsal of the private pilot's operator path, on disposable Postgres.

Not a test of the hosted providers: it runs the real hosted entry point
(python -m server.hosted) on this machine against a throwaway Postgres
database, with fictional accounts and 100 synthetic terrains, and exercises
exactly the commands the operator checklist names:

  schema -> accounts -> hosted start -> admin creates a base and grants it ->
  CSV dry run, load and re-run -> operator pages, filters and edits ->
  a second operator is refused -> true process restart -> logical backup ->
  restore into a second fresh database -> operational tables cleared ->
  restored service refuses the old session and serves the same rows.

    python reports/team-a-free-pilot-2026-10-12/ensayo_local.py \
        --admin-url postgresql://USUARIO@127.0.0.1:5432/postgres

--admin-url is a local server where two databases named ara_ensayo_piloto and
ara_ensayo_restaurada may be dropped and created. It refuses any host that is
not loopback. Passwords are generated per run and never printed.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

RAIZ = Path(__file__).resolve().parents[2]
HOST = "piloto.example.test"
ORIGEN = {"Origin": f"https://{HOST}"}
PUERTO = 9481
BASES = ("ara_ensayo_piloto", "ara_ensayo_restaurada")
TABLAS = ("team_user", "maestra_base", "maestra_base_acceso", "inventory_terrain",
          "inventory_revision", "inventory_event", "inventory_operation_result",
          "team_user_event", "maestra_base_event", "archivo", "archivo_version",
          "archivo_intento", "geometria", "archivo_evento")
OPERATIVAS = ("team_session", "team_login_failure", "archivo_trabajo")
LUGARES = (("Jalisco", "Zapopan", 20.72, -103.39), ("Nuevo León", "Apodaca", 25.78, -100.19),
           ("Querétaro", "El Marqués", 20.61, -100.28), ("Yucatán", "Mérida", 20.97, -89.62))


SUSTITUTO = """
import os, sys
from server import hosted
from server.api import archivos
puerto = hosted.configurar(os.environ)
archivos.configurar_almacen(archivos.almacen_local(sys.argv[1]))
hosted.comprobar_esquema()
hosted.servir(puerto)
"""


def paso(texto: str) -> None:
    print(f"OK  {texto}", flush=True)


def exigir(condicion: object, texto: str) -> None:
    if not condicion:
        raise SystemExit(f"FALLA  {texto}")
    paso(texto)


def correr(*args: str, entorno: dict[str, str] | None = None, entrada: str | None = None) -> str:
    hecho = subprocess.run(args, cwd=RAIZ, env={**os.environ, **(entorno or {})}, input=entrada,
                           capture_output=True, text=True, check=False)
    if hecho.returncode:
        raise SystemExit(f"FALLA  {' '.join(args[:3])}…\n{hecho.stdout}{hecho.stderr}")
    return hecho.stdout


def sql(url: str, sentencia: str) -> str:
    return correr("psql", url, "-AtX", "-v", "ON_ERROR_STOP=1", "-c", sentencia).strip()


def csv_sintetico(n: int = 100) -> str:
    lineas = ["Terreno,Estado,Municipio,Superficie m2,Asking Price,X,Y"]
    for i in range(1, n + 1):
        estado, municipio, lat, lon = LUGARES[i % len(LUGARES)]
        xy = f"{lat + i / 10000:.5f},{lon - i / 10000:.5f}" if i % 7 else ","  # X is the latitude
        lineas.append(f"Predio Ficticio {i:03d},{estado},{municipio},{1000 + 10 * i},{500000 + 1000 * i},{xy}")
    return "\n".join(lineas) + "\n"


class Servicio:
    """The hosted entry point as its own process, like the platform runs it."""

    def __init__(self, url: str, almacen_sustituto: Path | None = None,
                 entorno: dict[str, str] | None = None) -> None:
        self.entorno = {"ARA_MAP_DATABASE_URL": url, "ARA_MAP_HOST_PUBLICO": HOST, "PORT": str(PUERTO),
                        **(entorno or {})}
        self.proceso: subprocess.Popen[bytes] | None = None
        # Rehearsal scaffolding only: the accepted local store standing in for
        # the external byte store, in a folder outside the "host". The hosted
        # entry point itself never wires a disk store.
        self.orden = [sys.executable, "-m", "server.hosted"]
        if almacen_sustituto is not None:
            self.orden = [sys.executable, "-c", SUSTITUTO, str(almacen_sustituto)]

    def arrancar(self) -> None:
        self.proceso = subprocess.Popen(self.orden, cwd=RAIZ,
                                        env={**os.environ, **self.entorno},
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if self.pedir("GET", "/healthz", host="10.0.0.9")[0] == 200:
                    return
            except OSError:
                time.sleep(0.1)
        raise SystemExit("FALLA  el servicio hospedado no arrancó")

    def parar(self) -> None:
        if self.proceso:
            self.proceso.terminate()  # SIGTERM, as the platform stops a deployment
            self.proceso.wait(timeout=20)
            self.proceso = None

    def pedir(self, metodo: str, ruta: str, cuerpo: object = None, cookie: str | None = None,
              host: str = HOST, extra: dict[str, str] | None = None) -> tuple[int, dict, dict[str, str]]:
        conexion = http.client.HTTPConnection("127.0.0.1", PUERTO, timeout=120)
        cabeceras = {"Host": host, **(ORIGEN if metodo != "GET" else {}), **(extra or {})}
        if cookie:
            cabeceras["Cookie"] = cookie
        datos = cuerpo if isinstance(cuerpo, bytes) or cuerpo is None else json.dumps(cuerpo).encode()
        conexion.request(metodo, ruta, body=datos, headers=cabeceras)
        respuesta = conexion.getresponse()
        crudo = respuesta.read()
        conexion.close()
        if respuesta.getheader("Content-Type", "").split(";")[0] != "application/json":
            return respuesta.status, {"bytes": crudo}, dict(respuesta.getheaders())
        try:
            return respuesta.status, json.loads(crudo), dict(respuesta.getheaders())
        except ValueError:
            return respuesta.status, {}, dict(respuesta.getheaders())

    def entrar(self, usuario: str, clave: str) -> str:
        estado, _, cabeceras = self.pedir("POST", "/api/login", {"username": usuario, "password": clave})
        if estado != 200:
            raise SystemExit(f"FALLA  {usuario} no pudo entrar ({estado})")
        galleta = cabeceras["Set-Cookie"]
        if "Secure" not in galleta or "HttpOnly" not in galleta:
            raise SystemExit("FALLA  la cookie de sesión no es Secure y HttpOnly")
        return galleta.split(";")[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--admin-url", required=True)
    admin = parser.parse_args().admin_url
    partes = urlsplit(admin)
    if partes.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Sólo se ensaya contra un Postgres local desechable.")
    piloto, restaurada = (urlunsplit(partes._replace(path="/" + nombre)) for nombre in BASES)
    for nombre in BASES:
        sql(admin, f"DROP DATABASE IF EXISTS {nombre}")
        sql(admin, f"CREATE DATABASE {nombre} ENCODING 'UTF8' TEMPLATE template0")
    carpeta = Path(os.environ.get("TMPDIR", "/tmp")) / f"ara-ensayo-{secrets.token_hex(4)}"
    carpeta.mkdir(mode=0o700)
    claves = {u: secrets.token_urlsafe(18) for u in ("ada", "olga", "otto")}

    # -- operator setup: the commands of the checklist -------------------------
    destino = {"ENSAYO_DB": piloto}
    correr(sys.executable, "scripts/esquema.py", "--url-env", "ENSAYO_DB", entorno=destino)
    correr(sys.executable, "scripts/esquema.py", "--url-env", "ENSAYO_DB", "--check", entorno=destino)
    paso("esquema creado y comprobado con scripts/esquema.py")
    for usuario, rol in (("ada", "admin"), ("olga", "operador"), ("otto", "operador")):
        correr(sys.executable, "scripts/cuentas.py", "--url-env", "ENSAYO_DB", "--password-stdin",
               "crear", usuario, f"{usuario.capitalize()} Ficticia", "--rol", rol,
               entorno=destino, entrada=claves[usuario] + "\n")
    paso("cuentas ficticias creadas con scripts/cuentas.py (1 administradora, 2 operadoras)")

    servicio = Servicio(piloto)
    servicio.arrancar()
    try:
        exigir(servicio.pedir("GET", "/api/config", host="otro.example.test")[0] == 403,
               "otro Host es rechazado; /healthz responde a la sonda")
        exigir(servicio.pedir("POST", "/api/login", {}, extra={"Origin": "https://otro.example.test"})[0] == 403,
               "un origen ajeno no puede escribir")
        ada = servicio.entrar("ada", claves["ada"])
        olga = servicio.entrar("olga", claves["olga"])
        otto = servicio.entrar("otto", claves["otto"])
        estado, cuerpo, _ = servicio.pedir("POST", "/api/maestra/bases", {"nombre": "Piloto Ficticio"}, ada)
        exigir(estado == 200, "la administradora crea la base de trabajo en el portal")
        base = cuerpo["base"]
        operadoras = servicio.pedir("GET", "/api/maestra/operadores", cookie=ada)[1]["usuarios"]
        olga_id = next(u["id"] for u in operadoras if u["login"] == "olga")
        estado, _, _ = servicio.pedir("PUT", f"/api/maestra/bases/{base['id']}/acceso",
                                      {"expected_version": base["version"], "usuarios": [olga_id]}, ada)
        exigir(estado == 200, "la administradora da acceso a una operadora")

        archivo = carpeta / "terrenos.csv"
        archivo.write_text(csv_sintetico(), encoding="utf-8")
        carga = (sys.executable, "scripts/cargar_maestra.py", "--url-env", "ENSAYO_DB",
                 "--base", "Piloto Ficticio", "--admin", "ada")
        simulacro = correr(*carga, "--dry-run", str(archivo), entorno=destino)
        exigir("se crearían: 100" in simulacro
               and sql(piloto, "SELECT count(*) FROM inventory_terrain") == "0",
               "simulación: informa 100 filas y no escribe ninguna")
        real = correr(*carga, str(archivo), entorno=destino)
        exigir("creadas: 100" in real
               and sql(piloto, f"SELECT count(*) FROM inventory_terrain WHERE base_id = '{base['id']}'") == "100",
               "carga real: 100 terrenos en la tabla maestra, en la base indicada")
        repetida = correr(*carga, str(archivo), entorno=destino)
        exigir("creadas: 0" in repetida and "omitidas por duplicadas: 100" in repetida
               and sql(piloto, "SELECT count(*) FROM inventory_terrain") == "100",
               "repetir la carga no duplica: 100 omitidas")
        exigir(sql(piloto, "SELECT count(*) FROM inventory_event WHERE action = 'create'") == "100",
               "cada terreno cargado tiene su evento de historial")

        ruta = f"/api/maestra/bases/{base['id']}/terrenos"
        vistos, cursor = [], ""
        while True:
            estado, pagina, _ = servicio.pedir("GET", f"{ruta}?limit=40{cursor}", cookie=olga)
            vistos += pagina["terrenos"]
            if not pagina.get("next_cursor"):
                break
            cursor = "&cursor=" + pagina["next_cursor"]
        exigir(len(vistos) == 100, "la operadora con acceso pagina los 100 terrenos")
        sin_xy = sum(1 for t in vistos if t["draft"]["lat"] is None)
        exigir(sin_xy == 14, "14 terrenos quedan sin X/Y, como venían")
        filtrados = servicio.pedir("GET", f"{ruta}?estado=Jalisco&limit=100", cookie=olga)[1]["terrenos"]
        exigir(len(filtrados) == 25 and all(t["draft"]["estado"] == "Jalisco" for t in filtrados),
               "la operadora filtra por estado")
        uno = vistos[0]
        estado, editado, _ = servicio.pedir(
            "PATCH", f"/api/inventario/terrenos/{uno['id']}",
            {"expected_version": uno["version"], "changes": {"notas_internas": "Revisado en el ensayo"}}, olga)
        exigir(estado == 200, "la operadora edita un terreno")
        exigir(servicio.pedir("GET", ruta, cookie=otto)[0] == 404
               and servicio.pedir("GET", f"/api/inventario/terrenos/{uno['id']}", cookie=otto)[0] == 404,
               "la operadora sin acceso no ve la base ni el terreno (404)")
        exigir(servicio.pedir("GET", f"/api/inventario/terrenos/{uno['id']}/archivos", cookie=olga)[0] == 200,
               "sin almacén configurado, la lista de archivos sigue respondiendo")

        # -- a true restart with the same external database ---------------------
        servicio.parar()
        servicio.arrancar()
        estado, detalle, _ = servicio.pedir("GET", f"/api/inventario/terrenos/{uno['id']}", cookie=olga)
        exigir(estado == 200 and detalle["terreno"]["draft"]["notas_internas"] == "Revisado en el ensayo",
               "tras reiniciar el proceso: misma sesión, mismo dato editado")

        # -- logical backup and restore into a fresh target ---------------------
        respaldo = carpeta / "piloto.dump"
        correr("pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(respaldo), piloto)
        antes = {t: sql(piloto, f"SELECT count(*) FROM {t}") for t in TABLAS}
    finally:
        servicio.parar()

    correr("pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", restaurada, str(respaldo))
    exigir(int(sql(restaurada, "SELECT count(*) FROM team_session")) >= 3,
           "el respaldo lógico completo SÍ trae sesiones: hay que limpiarlas")
    sql(restaurada, "BEGIN; " + " ".join(f"DELETE FROM {t};" for t in OPERATIVAS) + " COMMIT;")
    exigir(all(sql(restaurada, f"SELECT count(*) FROM {t}") == "0" for t in OPERATIVAS),
           "sesiones, bloqueos de acceso y turnos de proceso vaciados en el destino restaurado")
    despues = {t: sql(restaurada, f"SELECT count(*) FROM {t}") for t in TABLAS}
    exigir(antes == despues, "todas las tablas de contenido coinciden fila por fila en número: "
           + ", ".join(f"{t}={n}" for t, n in antes.items()))
    exigir(sql(piloto, "SELECT md5(string_agg(id || ':' || version, ',' ORDER BY id)) FROM inventory_terrain")
           == sql(restaurada, "SELECT md5(string_agg(id || ':' || version, ',' ORDER BY id)) FROM inventory_terrain"),
           "mismos terrenos y versiones en el destino restaurado")

    servicio = Servicio(restaurada)
    servicio.arrancar()
    try:
        exigir(servicio.pedir("GET", f"/api/inventario/terrenos/{uno['id']}", cookie=olga)[0] == 401,
               "el servicio restaurado rechaza la sesión anterior")
        nueva = servicio.entrar("olga", claves["olga"])
        estado, detalle, _ = servicio.pedir("GET", f"/api/inventario/terrenos/{uno['id']}", cookie=nueva)
        historial = servicio.pedir("GET", f"/api/inventario/terrenos/{uno['id']}/historial", cookie=nueva)[1]
        exigir(estado == 200 and detalle["terreno"]["draft"]["notas_internas"] == "Revisado en el ensayo"
               and len(historial["eventos"]) >= 2,
               "tras restaurar: la operadora entra de nuevo y ve el dato y su historial")
    finally:
        servicio.parar()
        for f in carpeta.iterdir():
            f.unlink()
        carpeta.rmdir()
        for nombre in BASES:
            sql(admin, f"DROP DATABASE IF EXISTS {nombre}")
    print("ENSAYO COMPLETO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

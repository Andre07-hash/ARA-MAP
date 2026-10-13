"""Smoke test of a deployed pilot, with fictional accounts and synthetic files only.

For the operator, after the checklist's sections 1-4 are done on the free
providers. It signs in over HTTPS and runs the employee workflow against the
real service, database and byte store:

    python reports/team-a-free-pilot-2026-10-12/humo_hospedado.py https://<servicio>.onrender.com

Accounts must already exist (scripts/cuentas.py): one administrator, one
operator who will be granted the test base, one operator who will not. Their
logins and passwords are read from the environment, never from arguments:

    HUMO_ADMIN / HUMO_ADMIN_CLAVE
    HUMO_OPERADOR / HUMO_OPERADOR_CLAVE
    HUMO_AJENO / HUMO_AJENO_CLAVE

It creates one work base named "Humo <random>" with two fictional terrains
and uploads about 45 MiB of synthetic files (one 25 MiB PDF, one 20 MiB KMZ,
two small KMZ). That counts against the store's quota: use a disposable
target, or retire the files afterwards. Nothing is deleted by this script.

`--local PUERTO` talks plain HTTP to 127.0.0.1:PUERTO with the public Host
header instead (how this script itself was checked before any deployment).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ensayo_archivos import MIB, Portal, kmz  # noqa: E402
from ensayo_local import exigir, paso  # noqa: E402


class Remoto:
    """The same request interface as ensayo_local.Servicio, against a deployed URL."""

    def __init__(self, url: str, puerto_local: int | None) -> None:
        partes = urlsplit(url)
        if partes.scheme != "https" or not partes.hostname or partes.path not in ("", "/"):
            raise SystemExit("Indica la dirección del servicio como https://nombre, sin ruta.")
        self.host, self.puerto_local = partes.netloc, puerto_local

    def pedir(self, metodo: str, ruta: str, cuerpo: object = None, cookie: str | None = None,
              host: str | None = None, extra: dict[str, str] | None = None) -> tuple[int, dict, dict[str, str]]:
        if self.puerto_local:
            conexion: http.client.HTTPConnection = http.client.HTTPConnection("127.0.0.1", self.puerto_local, timeout=300)
        else:
            conexion = http.client.HTTPSConnection(self.host, timeout=300)
        cabeceras = {"Host": host or self.host}
        if metodo != "GET":
            cabeceras["Origin"] = f"https://{self.host}"
        cabeceras.update(extra or {})
        if cookie:
            cabeceras["Cookie"] = cookie
        datos = cuerpo if isinstance(cuerpo, bytes) or cuerpo is None else json.dumps(cuerpo).encode()
        conexion.request(metodo, ruta, body=datos, headers=cabeceras)
        respuesta = conexion.getresponse()
        crudo = respuesta.read()
        conexion.close()
        if respuesta.getheader("Content-Type", "").split(";")[0] != "application/json":
            return respuesta.status, {"bytes": crudo}, dict(respuesta.getheaders())
        return respuesta.status, json.loads(crudo), dict(respuesta.getheaders())

    def entrar(self, variable: str) -> tuple[str, str]:
        usuario, clave = os.environ.get(variable), os.environ.get(variable + "_CLAVE")
        if not usuario or not clave:
            raise SystemExit(f"Faltan {variable} y {variable}_CLAVE en el entorno.")
        estado, _, cabeceras = self.pedir("POST", "/api/login", {"username": usuario, "password": clave})
        if estado != 200:
            raise SystemExit(f"FALLA  {variable} no pudo entrar ({estado})")
        galleta = cabeceras["Set-Cookie"]
        exigir(all(m in galleta for m in ("Secure", "HttpOnly", "SameSite=Strict")),
               f"{variable} entra; la cookie es Secure, HttpOnly y SameSite=Strict")
        return usuario, galleta.split(";")[0]


def cronometrar(texto: str, inicio: float) -> None:
    paso(f"{texto} ({time.monotonic() - inicio:.1f} s)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("url")
    parser.add_argument("--local", type=int, metavar="PUERTO")
    args = parser.parse_args()
    remoto = Remoto(args.url, args.local)

    inicio = time.monotonic()
    exigir(remoto.pedir("GET", "/healthz")[0] == 200, "el servicio responde")
    cronometrar("tiempo hasta la primera respuesta (incluye despertar si estaba dormido)", inicio)
    config = remoto.pedir("GET", "/api/config")[1]
    exigir(config.get("cloud") is True and config.get("authRequired") is True,
           "es la entrada hospedada y exige iniciar sesión")
    exigir(remoto.pedir("GET", "/api/config", host="otro.example.test")[0] in (403, 404, 421),
           "otro Host no es atendido por la aplicación")
    exigir(remoto.pedir("POST", "/api/login", {}, extra={"Origin": "https://otro.example.test"})[0] == 403,
           "un origen ajeno no puede escribir")

    (admin, c_admin), (operador, c_operador), (_, c_ajeno) = (
        remoto.entrar(v) for v in ("HUMO_ADMIN", "HUMO_OPERADOR", "HUMO_AJENO"))
    p = Portal(remoto, {"ada": c_admin, "olga": c_operador, "otto": c_ajeno})  # roles, not real names
    nombre = f"Humo {secrets.token_hex(3)}"
    estado, creada = p.j("POST", "/api/maestra/bases", "ada", {"nombre": nombre})
    exigir(estado == 200, f"la administradora crea la base «{nombre}»")
    base = creada["base"]
    operadoras = p.j("GET", "/api/maestra/operadores", "ada")[1]["usuarios"]
    operador_id = next(u["id"] for u in operadoras if u["login"] == operador.strip().lower())
    exigir(p.j("PUT", f"/api/maestra/bases/{base['id']}/acceso", "ada",
               {"expected_version": base["version"], "usuarios": [operador_id]})[0] == 200,
           "y da acceso a la operadora")
    lista = f"/api/maestra/bases/{base['id']}/terrenos"
    terrenos = []
    for n in ("Uno", "Dos"):
        estado, hecho = p.j("POST", lista, "olga", {"terreno": f"Predio Ficticio {n}", "estado": "Jalisco",
                                                    "municipio": "Zapopan"}, clave=True)
        exigir(estado == 200, f"la operadora crea el terreno ficticio {n}, sin X/Y")
        terrenos.append(hecho["terreno"])
    uno, dos = terrenos
    exigir(p.j("GET", lista, "otto")[0] == 404, "la operadora sin acceso no ve la base")

    # -- existing row -> edit -> attach KMZ -> select -> activate ------------------
    exigir(p.j("PATCH", f"/api/inventario/terrenos/{uno['id']}", "olga",
               {"expected_version": uno["version"], "changes": {"direccion": "Camino Ficticio 12"}})[0] == 200,
           "la operadora edita el terreno")
    inicio_kmz, completo = p.subir(uno["id"], kmz("ambiguo_tres_lotes"), "kmz")
    vid, aid = inicio_kmz["version_id"], inicio_kmz["archivo_id"]
    exigir(completo["intento"]["resultado"] == "requiere_seleccion" and not completo["aplicada"],
           "KMZ con tres contornos: se guarda en el almacén real y pide elegir")
    estado, elegido = p.j("POST", f"/api/archivos/versiones/{vid}/procesar", "olga", {"seleccion": [1]}, clave=True)
    gid = elegido.get("geometria_id")
    estado2, activo = p.j("POST", f"/api/archivos/{aid}/activar", "olga",
                          {"version_id": vid, "geometria_id": gid,
                           "expected_revision": completo["archivo"]["revision"]}, clave=True)
    exigir((estado, estado2) == (200, 200) and activo["archivo"]["geometria_activa_id"] == gid,
           "la operadora elige un contorno y lo activa")
    fila = next(t for t in p.j("GET", lista, "olga")[1]["terrenos"] if t["id"] == uno["id"])
    exigir(fila["draft"]["lat"] is None and fila["ubicacion"]["modo"] == "geometria",
           "la fila sin X/Y queda ubicada por su contorno")
    _, malo = p.subir(uno["id"], kmz("solo_lineas"), "kmz")
    exigir(not malo["aplicada"] and p.contorno(gid, "olga")[1]["geometrias"][gid]["activa"],
           "un KMZ de reemplazo inválido no se aplica: el contorno anterior sigue activo")

    # -- full sizes through the real host and store -------------------------------
    pdf = b"%PDF-1.7\n" + os.urandom(25 * MIB - 9)
    inicio = time.monotonic()
    inicio_pdf, _ = p.subir(dos["id"], pdf, "pdf")
    cronometrar("PDF de 25 MiB: subido y verificado", inicio)
    inicio = time.monotonic()
    estado, bajado, cabeceras = p.bajar(inicio_pdf["version_id"], "olga")
    exigir(estado == 200 and hashlib.sha256(bajado["bytes"]).hexdigest() == hashlib.sha256(pdf).hexdigest()
           and cabeceras["Cache-Control"] == "private, no-store",
           "PDF de 25 MiB: baja idéntico, con cabeceras privadas")
    cronometrar("descarga de 25 MiB", inicio)
    grande = kmz("poligono_simple", relleno=20 * MIB - 2048)
    inicio = time.monotonic()
    _, completo_grande = p.subir(dos["id"], grande, "kmz")
    exigir(completo_grande["aplicada"], f"KMZ de {len(grande) / MIB:.2f} MiB: sube, se procesa y se aplica")
    cronometrar("KMZ de 20 MiB completo (debe caber en el turno de 180 s)", inicio)

    # -- permissions ---------------------------------------------------------------
    exigir(p.bajar(inicio_pdf["version_id"], "ada")[0] == 200
           and p.contorno(gid, "ada")[1]["geometrias"][gid]["activa"],
           "una segunda sesión autorizada lee el mismo PDF y el mismo contorno")
    exigir(p.bajar(inicio_pdf["version_id"], "otto")[0] == 404 and p.bajar(str(uuid.uuid4()), "otto")[0] == 404
           and p.contorno(gid, "otto")[1]["no_disponibles"] == [gid],
           "la cuenta sin acceso recibe 404, igual que para un archivo inexistente")

    print(f"\nHUMO COMPLETO en {remoto.host}. Base de prueba: «{nombre}». Para la comprobación de "
          f"persistencia tras redesplegar, vuelve a descargar la versión {inicio_pdf['version_id']} "
          f"(SHA-256 {hashlib.sha256(pdf).hexdigest()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

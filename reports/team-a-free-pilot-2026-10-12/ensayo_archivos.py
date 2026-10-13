"""Local rehearsal of the employee file workflow on the hosted entry point.

    existing terrain row -> edit fields -> attach KMZ -> select/activate boundary

plus PDF upload/download at full size, permissions, a true restart and a
database-plus-file recovery, with the real `server.hosted` process on
disposable Postgres and fictional accounts.

The byte store is a stand-in: the accepted local store in a folder outside
the "host", injected by rehearsal scaffolding (see ensayo_local.Servicio).
Nothing here exercises a real provider; collision behaviour, quotas and
full-size reliability through the real host remain hosted gates.

    python reports/team-a-free-pilot-2026-10-12/ensayo_archivos.py \
        --admin-url postgresql://USUARIO@127.0.0.1:5432/postgres
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import secrets
import shutil
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ensayo_local import BASES, OPERATIVAS, RAIZ, Servicio, correr, exigir, paso, sql  # noqa: E402

MIB = 1024 * 1024
KML = RAIZ / "tests" / "fixtures" / "kmz"
TIPO = {"pdf": "application/pdf", "kmz": "application/vnd.google-earth.kmz"}


def kmz(nombre: str, relleno: int = 0) -> bytes:
    """A fixture KML as a KMZ; `relleno` adds an incompressible unused member."""
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", (KML / f"{nombre}.kml").read_bytes())
        if relleno:
            zf.writestr(zipfile.ZipInfo("files/relleno.bin"), os.urandom(relleno), zipfile.ZIP_STORED)
    return salida.getvalue()


class Portal:
    def __init__(self, servicio: Servicio, cookies: dict[str, str]) -> None:
        self.s, self.cookies = servicio, cookies

    def j(self, metodo: str, ruta: str, quien: str, datos: object = None, clave: bool = False):
        extra = {"Idempotency-Key": str(uuid.uuid4())} if clave else None
        estado, cuerpo, _ = self.s.pedir(metodo, ruta, datos, self.cookies[quien], extra=extra)
        return estado, cuerpo

    def iniciar(self, terreno: str, contenido: bytes, tipo: str, quien: str):
        return self.j("POST", f"/api/inventario/terrenos/{terreno}/archivos", quien,
                      {"tipo": tipo, "nombre_original": f"ficticio.{tipo}", "tamano_declarado": len(contenido),
                       "sha256_declarado": hashlib.sha256(contenido).hexdigest()}, clave=True)

    def contenido(self, vid: str, contenido: bytes, tipo: str, quien: str) -> int:
        return self.s.pedir("PUT", f"/api/archivos/versiones/{vid}/contenido", contenido,
                            self.cookies[quien], extra={"Content-Type": TIPO[tipo]})[0]

    def subir(self, terreno: str, contenido: bytes, tipo: str, quien: str = "olga"):
        estado, inicio = self.iniciar(terreno, contenido, tipo, quien)
        if estado != 200:
            raise SystemExit(f"FALLA  iniciar {tipo}: {estado} {inicio}")
        if self.contenido(inicio["version_id"], contenido, tipo, quien) != 200:
            raise SystemExit(f"FALLA  enviar el contenido {tipo}")
        estado, completo = self.j("POST", f"/api/archivos/versiones/{inicio['version_id']}/completar", quien)
        if estado != 200:
            raise SystemExit(f"FALLA  completar {tipo}: {estado} {completo}")
        return inicio, completo

    def bajar(self, vid: str, quien: str):
        return self.s.pedir("GET", f"/api/archivos/versiones/{vid}/descarga", cookie=self.cookies[quien])

    def contorno(self, gid: str, quien: str) -> tuple[int, dict]:
        return self.j("POST", "/api/archivos/geometrias/metadatos", quien, {"ids": [gid]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
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
    almacen, almacen_restaurado = carpeta / "almacen", carpeta / "almacen-restaurado"
    almacen.mkdir(mode=0o700, parents=True)
    claves = {u: secrets.token_urlsafe(18) for u in ("ada", "olga", "otto")}
    destino = {"ENSAYO_DB": piloto}
    correr(sys.executable, "scripts/esquema.py", "--url-env", "ENSAYO_DB", entorno=destino)
    for usuario, rol in (("ada", "admin"), ("olga", "operador"), ("otto", "operador")):
        correr(sys.executable, "scripts/cuentas.py", "--url-env", "ENSAYO_DB", "--password-stdin",
               "crear", usuario, f"{usuario.capitalize()} Ficticia", "--rol", rol,
               entorno=destino, entrada=claves[usuario] + "\n")

    servicio = Servicio(piloto, almacen_sustituto=almacen)
    servicio.arrancar()
    try:
        p = Portal(servicio, {u: servicio.entrar(u, claves[u]) for u in claves})
        base = p.j("POST", "/api/maestra/bases", "ada", {"nombre": "Piloto Ficticio"})[1]["base"]
        operadoras = p.j("GET", "/api/maestra/operadores", "ada")[1]["usuarios"]
        olga_id = next(u["id"] for u in operadoras if u["login"] == "olga")
        acceso = f"/api/maestra/bases/{base['id']}/acceso"
        p.j("PUT", acceso, "ada", {"expected_version": base["version"], "usuarios": [olga_id]})
        csv = carpeta / "terrenos.csv"
        csv.write_text("Terreno,Estado,Municipio,Superficie m2\n"
                       "Predio Ficticio Uno,Jalisco,Zapopan,1200\nPredio Ficticio Dos,Jalisco,Zapopan,3400\n",
                       encoding="utf-8")
        correr(sys.executable, "scripts/cargar_maestra.py", "--url-env", "ENSAYO_DB", "--base",
               "Piloto Ficticio", "--admin", "ada", str(csv), entorno=destino)
        lista = f"/api/maestra/bases/{base['id']}/terrenos"
        uno, dos = sorted(p.j("GET", lista, "olga")[1]["terrenos"], key=lambda t: t["draft"]["superficie_m2"])
        exigir(uno["draft"]["lat"] is None and uno["ubicacion"]["modo"] != "geometria",
               "preparación: dos terrenos cargados, sin X/Y y sin contorno")

        # -- the employee workflow ---------------------------------------------
        estado, editado = p.j("PATCH", f"/api/inventario/terrenos/{uno['id']}", "olga",
                              {"expected_version": uno["version"], "changes": {"direccion": "Camino Ficticio 12"}})
        exigir(estado == 200, "la operadora edita campos del terreno existente")
        inicio, completo = p.subir(uno["id"], kmz("ambiguo_tres_lotes"), "kmz")
        vid, aid = inicio["version_id"], inicio["archivo_id"]
        exigir(completo["intento"]["resultado"] == "requiere_seleccion" and not completo["aplicada"],
               "KMZ con tres contornos: se guarda y pide elegir; nada se activa solo")
        estado, elegido = p.j("POST", f"/api/archivos/versiones/{vid}/procesar", "olga", {"seleccion": [1]}, clave=True)
        exigir(estado == 200 and elegido.get("geometria_id"), "la operadora elige un contorno")
        estado, activo = p.j("POST", f"/api/archivos/{aid}/activar", "olga",
                             {"version_id": vid, "geometria_id": elegido["geometria_id"],
                              "expected_revision": completo["archivo"]["revision"]}, clave=True)
        gid = elegido["geometria_id"]
        exigir(estado == 200 and activo["archivo"]["geometria_activa_id"] == gid, "y lo activa explícitamente")
        fila = next(t for t in p.j("GET", lista, "olga")[1]["terrenos"] if t["id"] == uno["id"])
        exigir(fila["draft"]["lat"] is None and fila["ubicacion"]["modo"] == "geometria"
               and fila["draft"]["direccion"] == "Camino Ficticio 12",
               "la fila sin X/Y ahora se ubica por su contorno y conserva lo editado")
        estado, trozo, cabeceras = servicio.pedir("GET", f"/api/archivos/geometrias/{gid}/contenido?desde=0",
                                                  cookie=p.cookies["olga"])
        geometria = trozo["bytes"]
        exigir(estado == 200 and cabeceras["X-Geometria-Final"] == "1"
               and hashlib.sha256(geometria).hexdigest() == cabeceras["X-Geometria-Sha256"],
               "el contorno se entrega completo y coincide con su SHA-256")

        _, malo = p.subir(uno["id"], kmz("solo_lineas"), "kmz")
        meta = p.contorno(gid, "olga")[1]
        exigir(not malo["aplicada"] and meta["geometrias"][gid]["activa"],
               "un KMZ de reemplazo sin contorno válido no se aplica: el contorno anterior sigue activo")

        # -- full sizes through the hosted entry point ---------------------------
        pdf = b"%PDF-1.7\n" + os.urandom(25 * MIB - 9)
        ipdf, cpdf = p.subir(dos["id"], pdf, "pdf")
        estado, bajado, cabeceras = p.bajar(ipdf["version_id"], "olga")
        exigir(estado == 200 and len(bajado["bytes"]) == 25 * MIB
               and hashlib.sha256(bajado["bytes"]).hexdigest() == hashlib.sha256(pdf).hexdigest(),
               "PDF de 25 MiB exactos: sube y baja idéntico byte a byte")
        exigir(cabeceras["Cache-Control"] == "private, no-store" and cabeceras["X-Content-Type-Options"] == "nosniff"
               and cabeceras["Content-Disposition"].startswith("attachment")
               and "sandbox" in cabeceras["Content-Security-Policy"],
               "la descarga lleva las cabeceras privadas (no-store, nosniff, attachment, sandbox)")
        grande = kmz("poligono_simple", relleno=20 * MIB - 2048)
        estado, ikmz = p.iniciar(dos["id"], grande, "kmz", "olga")
        estado_put = p.contenido(ikmz["version_id"], grande, "kmz", "olga") if estado == 200 else 0
        estado_fin, ckmz = p.j("POST", f"/api/archivos/versiones/{ikmz['version_id']}/completar", "olga")
        exigir((estado, estado_put, estado_fin) == (200, 200, 200) and len(grande) > 19 * MIB,
               f"KMZ de {len(grande) / MIB:.2f} MiB: sube y se procesa (resultado: "
               f"{ckmz.get('intento', {}).get('resultado')}, aplicado: {ckmz.get('aplicada')})")
        demasiado = b"%PDF-1.7\n" + bytes(25 * MIB - 8)
        exigir(p.iniciar(dos["id"], demasiado, "pdf", "olga")[0] == 400,
               "un PDF de 25 MiB + 1 byte se rechaza al iniciar")

        # -- permissions -----------------------------------------------------------
        segunda = servicio.entrar("ada", claves["ada"])
        exigir(servicio.pedir("GET", f"/api/archivos/versiones/{ipdf['version_id']}/descarga", cookie=segunda)[0] == 200
               and servicio.pedir("POST", "/api/archivos/geometrias/metadatos", {"ids": [gid]}, segunda)[1]
               ["geometrias"][gid]["activa"], "una segunda sesión autorizada lee el mismo PDF y el mismo contorno")
        ajena = p.contorno(gid, "otto")[1]
        exigir(p.bajar(ipdf["version_id"], "otto")[0] == 404 and ajena["no_disponibles"] == [gid]
               and p.j("GET", f"/api/inventario/terrenos/{uno['id']}/archivos", "otto")[0] == 404
               and p.bajar(str(uuid.uuid4()), "otto")[0] == 404,
               "la cuenta sin acceso recibe lo mismo que para un archivo inexistente (404)")
        mini = b"%PDF-1.7\nficticio"
        _, pendiente = p.iniciar(dos["id"], mini, "pdf", "olga")
        p.contenido(pendiente["version_id"], mini, "pdf", "olga")
        version = p.j("GET", acceso, "ada")[1]["base"]["version"]
        p.j("PUT", acceso, "ada", {"expected_version": version, "usuarios": []})
        exigir(p.j("POST", f"/api/archivos/versiones/{pendiente['version_id']}/completar", "olga")[0] in (403, 404)
               and p.bajar(ipdf["version_id"], "olga")[0] == 404
               and sql(piloto, f"SELECT estado FROM archivo_version WHERE id = '{pendiente['version_id']}'") == "subiendo",
               "acceso revocado antes de completar: la subida no se vuelve archivo y la descarga se niega")
        version = p.j("GET", acceso, "ada")[1]["base"]["version"]
        p.j("PUT", acceso, "ada", {"expected_version": version, "usuarios": [olga_id]})
        actual = p.j("GET", f"/api/inventario/terrenos/{dos['id']}", "ada")[1]["terreno"]
        p.j("POST", f"/api/inventario/terrenos/{dos['id']}/archivar", "ada", {"expected_version": actual["version"]})
        estado, negado = p.j("POST", f"/api/archivos/versiones/{pendiente['version_id']}/completar", "olga")
        exigir(estado == 409 and negado["detalle"]["code"] == "terreno_archivado"
               and p.bajar(ipdf["version_id"], "olga")[0] == 200,
               "terreno archivado antes de completar: no se completa; lo ya guardado se sigue leyendo")
        actual = p.j("GET", f"/api/inventario/terrenos/{dos['id']}", "ada")[1]["terreno"]
        p.j("POST", f"/api/inventario/terrenos/{dos['id']}/restaurar", "ada", {"expected_version": actual["version"]})

        # -- a true restart with the same external database and store -------------
        servicio.parar()
        servicio.arrancar()
        estado, otra_vez, _ = p.bajar(ipdf["version_id"], "olga")
        exigir(estado == 200 and otra_vez["bytes"] == pdf and p.contorno(gid, "olga")[1]["geometrias"][gid]["activa"],
               "tras reiniciar el proceso: mismo PDF, mismo contorno activo, misma sesión")

        # -- storage unavailable: nothing else breaks --------------------------------
        servicio.parar()
        sin_almacen = Servicio(piloto)
        sin_almacen.arrancar()
        try:
            estado, error, _ = sin_almacen.pedir("GET", f"/api/archivos/versiones/{ipdf['version_id']}/descarga",
                                                 cookie=p.cookies["olga"])
            exigir(estado == 503 and error["detalle"]["code"] == "almacen_no_configurado"
                   and sin_almacen.pedir("GET", lista, cookie=p.cookies["olga"])[0] == 200
                   and sin_almacen.pedir("POST", "/api/archivos/geometrias/metadatos", {"ids": [gid]},
                                         p.cookies["olga"])[1]["geometrias"][gid]["activa"]
                   and sin_almacen.pedir("GET", f"/api/archivos/geometrias/{gid}/contenido?desde=0",
                                         cookie=p.cookies["olga"])[1]["bytes"] == geometria,
                   "sin almacén: la descarga responde 503; tabla, contorno y su geometría siguen funcionando")
            antes = sql(piloto, "SELECT count(*) FROM archivo_version")
            estado = sin_almacen.pedir("POST", f"/api/inventario/terrenos/{dos['id']}/archivos",
                                       {"tipo": "pdf", "nombre_original": "x.pdf", "tamano_declarado": len(mini),
                                        "sha256_declarado": hashlib.sha256(mini).hexdigest()}, p.cookies["olga"],
                                       extra={"Idempotency-Key": str(uuid.uuid4())})[0]
            creo = sql(piloto, "SELECT count(*) FROM archivo_version") != antes
            ajeno = sin_almacen.pedir("GET", f"/api/archivos/versiones/{ipdf['version_id']}/descarga",
                                      cookie=p.cookies["otto"])[0]
            # Both are requirements on Team B's lifecycle slice, not yet in this tree.
            print(f"{'OK ' if not creo else 'PENDIENTE DE B'}  iniciar sin almacén responde {estado} y "
                  f"{'no crea' if not creo else 'SÍ crea'} una subida pendiente")
            print(f"{'OK ' if ajeno == 404 else 'PENDIENTE DE B'}  sin almacén, la cuenta sin acceso recibe {ajeno} "
                  "(debe ser 404: la negativa va antes que el almacén)")
        finally:
            sin_almacen.parar()

        # -- the real adapter and SDK, wired by the hosted entry point itself ------------
        # Settings shaped like the provider's, pointing at a closed local port: the
        # service starts, builds the SDK client on first use, and the unreachable
        # provider is a retryable storage error. Not a test of the provider.
        con_adaptador = Servicio(piloto, entorno={
            "ARA_MAP_ARCHIVOS_SUPABASE_URL": "http://127.0.0.1:9", "ARA_MAP_ARCHIVOS_SUPABASE_KEY": "clave-ficticia",
            "ARA_MAP_ARCHIVOS_SUPABASE_BUCKET": "piloto-ficticio"})
        con_adaptador.arrancar()
        try:
            estado, error, _ = con_adaptador.pedir("GET", f"/api/archivos/versiones/{ipdf['version_id']}/descarga",
                                                   cookie=p.cookies["olga"])
            exigir(estado == 503 and error["detalle"]["code"] == "almacen_no_disponible"
                   and error["detalle"].get("reintentar") is True
                   and con_adaptador.pedir("GET", lista, cookie=p.cookies["olga"])[0] == 200,
                   "con el adaptador de B conectado por server.hosted y el proveedor inalcanzable: "
                   "503 reintentable en archivos; la tabla sigue funcionando")
        finally:
            con_adaptador.parar()

        # -- database-plus-file recovery ------------------------------------------------
        respaldo = carpeta / "piloto.dump"
        correr("pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(respaldo), piloto)
        # Stand-in for Team B's exporter: every final object the dump refers to,
        # checked against its recorded size and SHA-256, copied out of the store.
        referidos = [fila.split("|") for fila in sql(
            piloto, "SELECT clave_final, tamano, sha256 FROM archivo_version WHERE estado = 'disponible'").splitlines()]
        for clave, tamano, sha in referidos:
            origen, copia = almacen / clave, almacen_restaurado / clave
            datos = origen.read_bytes()
            if len(datos) != int(tamano) or hashlib.sha256(datos).hexdigest() != sha:
                raise SystemExit(f"FALLA  un archivo referido no coincide con su registro ({len(referidos)} revisados)")
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origen, copia)
        paso(f"respaldo: volcado de la base y {len(referidos)} archivos finales referidos, cada uno con tamaño y SHA-256 verificados")
    finally:
        servicio.parar()

    try:
        correr("pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", restaurada, str(respaldo))
        sql(restaurada, "BEGIN; " + " ".join(f"DELETE FROM {t};" for t in OPERATIVAS) + " COMMIT;")
        restaurado = Servicio(restaurada, almacen_sustituto=almacen_restaurado)
        restaurado.arrancar()
        try:
            exigir(restaurado.pedir("GET", lista, cookie=p.cookies["olga"])[0] == 401,
                   "destino restaurado: la sesión anterior ya no sirve")
            nueva = restaurado.entrar("olga", claves["olga"])
            estado, bajado, _ = restaurado.pedir("GET", f"/api/archivos/versiones/{ipdf['version_id']}/descarga", cookie=nueva)
            exigir(estado == 200 and bajado["bytes"] == pdf, "destino restaurado: el PDF de 25 MiB baja idéntico")
            meta = restaurado.pedir("POST", "/api/archivos/geometrias/metadatos", {"ids": [gid]}, nueva)[1]
            fila = next(t for t in restaurado.pedir("GET", lista, cookie=nueva)[1]["terrenos"] if t["id"] == uno["id"])
            historial = restaurado.pedir("GET", f"/api/archivos/{aid}/historial", cookie=nueva)[1]
            exigir(meta["geometrias"][gid]["activa"] and fila["ubicacion"]["modo"] == "geometria"
                   and len(historial["eventos"]) >= 3,
                   "destino restaurado: contorno activo, fila ubicada por contorno e historial del archivo completos")
            estado, _ = Portal(restaurado, {"olga": nueva}).j(
                "POST", f"/api/archivos/versiones/{pendiente['version_id']}/cancelar", "olga")
            exigir(estado == 200, "destino restaurado: la subida que quedó pendiente (sin sus bytes) se puede cancelar")
        finally:
            restaurado.parar()
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
        for nombre in BASES:
            sql(admin, f"DROP DATABASE IF EXISTS {nombre}")
    print("ENSAYO DE ARCHIVOS COMPLETO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

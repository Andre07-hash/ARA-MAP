"""A disposable local ARA Map for the 3B file widgets' browser harness.

    python3 tests/e2e/archivos_servidor.py --puerto 8461

The real server (server.app.Handler) on loopback, a temporary SQLite file and a
temporary LOCAL DISK byte store (AlmacenLocal), both deleted on exit, and
fictional accounts whose password is the test fixture's (tests/support.py,
TEST_PASSWORD): administrator ana, operators olga and omar (granted the base)
and otto (no grant at all). Nothing here reads the configured database, a
real account or a real file.

Two modes, printed on start-up and returned by /api/__arnes/modo:

- "montado": the attachment routes are already registered by server/app.py
  (A's C1 checkpoint). Nothing is patched: requests reach the mounted
  application, with its dispatcher, binary transport and store wiring.
- "arnes": before C1 the routes are not mounted. They are registered on the
  real router exactly as tests/archivos_http_harness.py does, with the
  one-method RespuestaBinaria adapter and the local store. HTTP HARNESS
  EVIDENCE, NOT APPLICATION-MOUNTED ENDPOINT ACCEPTANCE.

Test-only additions in both modes (private, capability-checked through the
real dispatcher, under /api/__arnes/): the terrain's caller-aware file summary
and active geometry descriptor, which C1/3A will expose on the terrain DTO.
The harness pages under tests/e2e/archivos/ are served at /__arnes/.

Generated fictional KMZ/PDF fixtures are written to a temporary folder whose
path is printed as a JSON line {"fixtures": {...}}, with the seeded ids.
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import sys
import tempfile
import uuid
import zipfile
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

PAGINAS = Path(__file__).resolve().parent / "archivos"
KML = RAIZ / "tests" / "fixtures" / "kmz"


def kmz_de(kml: bytes) -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("doc.kml", date_time=(2026, 10, 9, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, kml)
    return salida.getvalue()


def kml_limite(partes: int = 20_000) -> bytes:
    """The accepted parser's 100,000-vertex limit (same generator as the 2B tests)."""
    from tests.test_archivos_http import kml_limite as generar
    return generar(partes=partes)


def pdf_ficticio(texto: str, relleno: int = 0) -> bytes:
    cuerpo = f"%PDF-1.4\n% {texto}\n1 0 obj << /Type /Catalog >> endobj\n".encode()
    return cuerpo + b"%" + b"x" * relleno + b"\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def escribir_fixtures(carpeta: Path) -> dict[str, str]:
    archivos = {
        "pdf": ("Avalúo ficticio.pdf", pdf_ficticio("ficticio uno")),
        "pdf2": ("Escritura ficticia.pdf", pdf_ficticio("ficticio dos", 4000)),
        "kmz_simple": ("Contorno ficticio.kmz", kmz_de((KML / "poligono_simple.kml").read_bytes())),
        "kmz_varios": ("Tres lotes ficticios.kmz", kmz_de((KML / "ambiguo_tres_lotes.kml").read_bytes())),
        "kmz_reemplazo": ("Forma U ficticia.kmz", kmz_de((KML / "forma_u.kml").read_bytes())),
        "kmz_invalido": ("Sin contorno.kmz", kmz_de((KML / "documento_vacio.kml").read_bytes())),
        "kmz_limite": ("Límite ficticio.kmz", kmz_de(kml_limite())),
        "no_pdf": ("notas.txt", b"no es un pdf"),
    }
    rutas = {}
    for clave, (nombre, datos) in archivos.items():
        destino = carpeta / clave
        destino.mkdir()
        (destino / nombre).write_bytes(datos)
        rutas[clave] = str(destino / nombre)
    return rutas


def sembrar() -> dict[str, object]:
    from server import auth, db
    from server.repo import maestra
    from tests.support import TEST_PASSWORD
    with db.escritura() as conn:
        usuarios = {login: auth.create_user(conn, login, f"{login.capitalize()} Ficticia", TEST_PASSWORD,
                                            iterations=1000, rol=rol)
                    for login, rol in (("ana", "admin"), ("olga", "operador"), ("omar", "operador"),
                                       ("otto", "operador"))}
        base = maestra.crear(conn, "Base Ficticia de Archivos", usuarios["ana"])["id"]
        ahora = db.now()
        for login in ("olga", "omar"):
            conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                         " VALUES (?, ?, ?, ?)", (base, usuarios[login]["id"], ahora, usuarios["ana"]["id"]))
        terrenos = {}
        for clave, nombre, lat, lon in (("uno", "Lote Ficticio Uno", 20.6015, -100.398),
                                        ("dos", "Lote Ficticio Dos", 20.65, -100.35),
                                        ("tres", "Lote Ficticio Tres", None, None)):
            tid, rid = str(uuid.uuid4()), str(uuid.uuid4())
            conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                         " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                         (tid, base, ahora, usuarios["ana"]["id"], ahora, usuarios["ana"]["id"]))
            conn.execute("INSERT INTO inventory_revision (id, inventory_id, revision_number, terreno, estado,"
                         " municipio, lat, lon, base_id, created_at, created_by)"
                         " VALUES (?, ?, 1, ?, 'Querétaro', 'Municipio Ficticio', ?, ?, ?, ?, ?)",
                         (rid, tid, nombre, lat, lon, base, ahora, usuarios["ana"]["id"]))
            conn.execute("UPDATE inventory_terrain SET draft_revision_id = ? WHERE id = ?", (rid, tid))
            terrenos[clave] = {"id": tid, "nombre": nombre, "lat": lat, "lon": lon}
    return {"base": base, "terrenos": terrenos, "usuarios": {k: v["id"] for k, v in usuarios.items()}}


def construir(almacen: Path):
    """Return (Handler class, mode) for the current tree."""
    from server import app, archivos, auth, db
    from server.api import archivos as api
    from server.api.binario import RespuestaBinaria
    from server.web_util import ApiError

    rutas = {(r.method, r.path) for r in app.router.routes}
    montado = ("POST", "/api/archivos/geometrias/metadatos") in rutas
    modo = "montado" if montado else "arnes"

    if not montado:
        for metodo, ruta, handler, capacidad in api.RUTAS:
            app.router.add(metodo, ruta, handler, capacidad)
        app.READ_ONLY_POSTS = set(app.READ_ONLY_POSTS) | set(api.POSTS_DE_LECTURA)
    if api._fabrica is None:
        api.configurar_almacen(api.almacen_local(almacen))

    def estado_archivos(request):
        """Test-only: the 1B summary and active descriptor C1/3A put on the terrain DTO."""
        terreno = request.params["id"]
        with db.session() as conn:
            resumen = archivos.resumenes_de_archivos(conn, [terreno], request.sesion)
        if terreno in resumen.get("no_disponibles", []):
            raise ApiError("El terreno no existe.", 404, {"code": "not_found"})
        fila = resumen["resultados"][terreno]
        descriptor = None
        gid = (fila.get("kmz") or {}).get("geometria_activa_id")
        if gid:
            meta = archivos.metadatos_geometrias(request.sesion, [gid])["geometrias"].get(gid)
            if meta and meta.get("utilizable"):
                descriptor = {k: meta[k] for k in ("id", "archivo_version_id", "utilizable", "bbox",
                                                   "punto_interior")}
        return {"modo": modo, "resumen": fila, "geometria": descriptor}

    app.router.add("GET", "/api/__arnes/terrenos/:id/archivos-estado", estado_archivos, "archivos.ver")
    app.router.add("GET", "/api/__arnes/modo", lambda request: {"modo": modo}, "archivos.ver")

    class HandlerArnes(app.Handler):
        def _send_json(self, payload, status=HTTPStatus.OK, extra=None):
            if not montado and isinstance(payload, RespuestaBinaria):
                return self._send(payload.status, bytes(payload.cuerpo), payload.tipo,
                                  extra=dict(payload.cabeceras))
            return super()._send_json(payload, status, extra)

        def _serve_static(self):
            ruta = unquote(self.path.split("?", 1)[0])
            if not ruta.startswith("/__arnes/"):
                return super()._serve_static()
            destino = (PAGINAS / ruta[len("/__arnes/"):]).resolve()
            if not destino.is_relative_to(PAGINAS) or not destino.is_file():
                return self._send(HTTPStatus.NOT_FOUND, b"No encontrado", "text/plain")
            tipo, _ = mimetypes.guess_type(destino.name)
            return self._send(HTTPStatus.OK, destino.read_bytes(), tipo or "application/octet-stream",
                              extra={"Cache-Control": "no-store"})

        def log_message(self, *args):
            pass

    del auth
    return HandlerArnes, modo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--puerto", type=int, default=8461)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as carpeta:
        raiz = Path(carpeta)
        os.environ["ARA_MAP_DB"] = str(raiz / "desechable.db")
        for variable in ("ARA_MAP_DATABASE_URL", "DATABASE_URL", "ARA_MAP_READ_ONLY"):
            os.environ.pop(variable, None)
        (raiz / "almacen").mkdir(mode=0o700)
        (raiz / "fixtures").mkdir()
        from http.server import ThreadingHTTPServer

        from server import db
        db.connect().close()
        semilla = sembrar()
        Handler, modo = construir(raiz / "almacen")
        fixtures = escribir_fixtures(raiz / "fixtures")
        print(json.dumps({"modo": modo, "almacen": "local-disk", **semilla, "fixtures": fixtures}), flush=True)
        httpd = ThreadingHTTPServer(("127.0.0.1", args.puerto), Handler)
        print(f"LISTO http://localhost:{args.puerto} modo={modo}", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()


if __name__ == "__main__":
    main()

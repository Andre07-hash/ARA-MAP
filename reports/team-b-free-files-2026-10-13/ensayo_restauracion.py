"""Restore drill with real pg_dump/pg_restore, a disposable Postgres and local stores.

    ENSAYO_ORIGEN_URL=postgresql://.../origen ENSAYO_DESTINO_URL=postgresql://.../destino \
        python3 reports/team-b-free-files-2026-10-13/ensayo_restauracion.py

Both URLs must name EMPTY, disposable databases (the script refuses one that
already has tables). URLs are read from the environment and never printed.
Synthetic data only: three KMZ versions with geometry and history, a PDF, an
upload started and never sent (no staging) and one unreferenced object.
Stores are local folders standing in for the bucket; this is not evidence
about Supabase.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from server import postgres, recuperacion  # noqa: E402
from server.almacen import AlmacenLocal  # noqa: E402
from tests import test_archivos  # noqa: E402
from tests.test_recuperacion import _Datos, poner  # noqa: E402

TABLAS = ("archivo", "archivo_version", "archivo_evento", "archivo_intento", "geometria")


def cli(*argumentos: str) -> tuple[int, dict]:
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(io.StringIO()):
        codigo = recuperacion.main([*argumentos, "--json"])
    return codigo, json.loads(salida.getvalue())


def conteos(url: str) -> dict:
    os.environ["ARA_MAP_DATABASE_URL"] = url
    with postgres.session() as conn:
        return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in TABLAS}


def vacia(url: str) -> None:
    os.environ["ARA_MAP_DATABASE_URL"] = url
    with postgres.session() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM pg_tables WHERE schemaname = 'public'"
                         ).fetchone()["n"]
    if n:
        raise SystemExit("La base no está vacía; el ensayo sólo usa bases desechables nuevas.")


def comprobar(nombre: str, ok: bool, detalle: object = "") -> None:
    print(("OK    " if ok else "FALLA ") + nombre + (f" — {detalle}" if detalle != "" else ""))
    if not ok:
        raise SystemExit(1)


def main() -> None:
    origen, destino = os.environ["ENSAYO_ORIGEN_URL"], os.environ["ENSAYO_DESTINO_URL"]
    vacia(origen)
    vacia(destino)
    trabajo = Path(tempfile.mkdtemp(prefix="ensayo-restauracion-"))
    vivo, respaldo, nuevo = trabajo / "bucket-vivo", trabajo / "respaldo", trabajo / "bucket-nuevo"
    vivo.mkdir()
    nuevo.mkdir()

    # 1. Source: schema and synthetic attachments through the real lifecycle.
    os.environ["ARA_MAP_DATABASE_URL"] = origen
    with postgres.session() as conn:
        conn.raw.execute(postgres.schema_sql(), prepare=False)
        postgres.migrate(conn)
    datos = _Datos(lambda d: setattr(d, "database", None))
    datos.setUp()
    datos.store = AlmacenLocal(vivo)
    for n, nombre in enumerate(("poligono_simple", "multiparte", "poligono_con_hueco")):
        datos.complete(datos.upload(test_archivos.kmz(nombre), "kmz", key=f"kmz-{n}"))
    datos.complete(datos.upload(test_archivos.PDF))
    pendiente = datos.start(test_archivos.PDF, key="pendiente")
    poner(datos.store, "final/huerfano/0", b"objeto sin referencia")
    antes = conteos(origen)
    print("origen:", antes)

    # 2. Logical backup and restore into the other disposable database.
    volcado = trabajo / "piloto.dump"
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges",
                    "--file", str(volcado), origen], check=True)
    subprocess.run(["pg_restore", "--no-owner", "--no-privileges", "--dbname", destino,
                    str(volcado)], check=True)
    comprobar("filas restauradas iguales al origen", conteos(destino) == antes)

    # 3. Export: references come from the RESTORED backup, bytes from the live bucket.
    codigo, export = cli("--url-env", "ENSAYO_DESTINO_URL", "--almacen-local", str(vivo),
                         "--exportar", str(respaldo))
    comprobar("exportación verificada (salida 0)", codigo == 0, export["conteos"])
    comprobar("huérfano reportado, no borrado",
              [m["clave"] for m in export["no_referenciados"]] == ["final/huerfano/0"]
              and (vivo / "final/huerfano/0").is_file())
    comprobar("bytes leídos = referenciados",
              export["bytes"]["leidos_del_almacen"] == export["bytes"]["referenciados"],
              export["bytes"])
    codigo, otra = cli("--url-env", "ENSAYO_DESTINO_URL", "--almacen-local", str(vivo),
                       "--exportar", str(respaldo))
    comprobar("segunda exportación incremental (0 bytes leídos)",
              codigo == 0 and otra["bytes"]["leidos_del_almacen"] == 0
              and otra["exportacion"]["copias_locales_reutilizadas"] == 4)

    # 4. Load the export into an empty target bucket and verify it.
    manifiesto = str(respaldo / recuperacion.NOMBRE_MANIFIESTO)
    codigo, carga = cli("--manifiesto", manifiesto, "--almacen-local", str(nuevo),
                        "--restauracion", "--cargar-exportacion", str(respaldo))
    comprobar("carga en bucket nuevo (salida 0)",
              codigo == 0 and carga["carga"]["cargados"] == 4, carga["carga"])
    codigo, rest = cli("--url-env", "ENSAYO_DESTINO_URL", "--almacen-local", str(nuevo),
                       "--restauracion")
    comprobar("base restaurada contra bucket restaurado (salida 0)",
              codigo == 0 and rest["conteos"]["ok"] == 4, rest["conteos"])
    comprobar("subida pendiente listada sin temporal, no es error",
              [(p["version_id"], p["staging_presente"]) for p in rest["pendientes"]]
              == [(pendiente["version_id"], False)])
    comprobar("sin huérfanos ni temporales en el destino",
              rest["no_referenciados"] == [] and rest["staging"] == [])

    # 5. One missing and one corrupt object in the target are each reported.
    finales = recuperacion.cargar_manifiesto(Path(manifiesto))["finales"]
    (nuevo / finales[0]["clave"]).unlink()
    (nuevo / finales[1]["clave"]).write_bytes(b"x" * finales[1]["tamano"])
    codigo, roto = cli("--url-env", "ENSAYO_DESTINO_URL", "--almacen-local", str(nuevo),
                       "--restauracion")
    comprobar("faltante y corrupto detectados (salida 1)",
              codigo == 1 and roto["conteos"]["ausente"] == 1
              and roto["conteos"]["sha_distinto"] == 1, roto["conteos"])
    print(f"Ensayo correcto. Carpeta de trabajo: {trabajo.name} (temporal, borrable)")


if __name__ == "__main__":
    main()

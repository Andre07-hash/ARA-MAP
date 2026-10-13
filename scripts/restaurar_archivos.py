"""Upload an exported attachment backup into a fresh byte store.

The one step scripts/verificar_archivos.py does not do: it verifies and
exports, it never writes to a store. This command takes an export directory
(`manifiesto.json` plus each object at the path of its key, as that tool
writes it) and puts every final object the manifest names into the store of a
restore target, at the same key:

    python3 scripts/restaurar_archivos.py CARPETA_EXPORTADA --almacen-local DESTINO
    python3 scripts/restaurar_archivos.py CARPETA_EXPORTADA --almacen-entorno

--almacen-entorno is the store named by ARA_MAP_ARCHIVOS_SUPABASE_URL, _KEY
and _BUCKET in this shell: set them to the RESTORE target's values, never the
live pilot's. Nothing in the export directory or in any database is modified.

Each local file is checked against the manifest's size and SHA-256 before it
is sent, and nothing is sent if any file is missing or different. Objects are
created through the store's own contract (stage, then create-only copy), so
an existing object is never overwritten: a key already present with the
manifest's size is reported as already there and left alone; with another
size it is an error. Afterwards, verify the result with
scripts/verificar_archivos.py --manifiesto ... --restauracion.

Exit codes: 0 every object is in the store; 1 a file or object is wrong or a
transfer failed; 2 usage or configuration error.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid
from collections.abc import Iterator, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BLOQUE = 1024 * 1024


def _bloques(ruta: Path) -> Iterator[bytes]:
    with ruta.open("rb") as archivo:
        while True:
            datos = archivo.read(BLOQUE)
            if not datos:
                return
            yield datos


def _coincide(ruta: Path, entrada: dict[str, Any]) -> bool:
    if not ruta.is_file() or ruta.is_symlink() or ruta.stat().st_size != entrada["tamano"]:
        return False
    resumen = hashlib.sha256()
    for datos in _bloques(ruta):
        resumen.update(datos)
    return resumen.hexdigest() == entrada["sha256"]


def restaurar(carpeta: Path, almacen: Any) -> dict[str, list[str]]:
    """Put every final object of the export into `almacen`. Returns keys by outcome."""
    from server import recuperacion
    from server.almacen import AlmacenError, ColisionError

    manifiesto = recuperacion.cargar_manifiesto(carpeta / recuperacion.NOMBRE_MANIFIESTO)
    finales = manifiesto["finales"]
    malos = [e["clave"] for e in finales if not _coincide(carpeta / e["clave"], e)]
    resultado: dict[str, list[str]] = {"subidos": [], "ya_estaban": [], "fallidos": malos}
    if malos:
        return resultado  # an incomplete backup is not half-restored
    for entrada in finales:
        clave, limite = entrada["clave"], recuperacion.LIMITES[entrada["tipo"]]
        temporal = f"temporal/{uuid.uuid4().hex}"
        try:
            almacen.guardar_temporal(temporal, _bloques(carpeta / clave), limite)
            almacen.copiar(temporal, clave, limite)
            resultado["subidos"].append(clave)
        except ColisionError:
            igual = almacen.tamano_de(clave) == entrada["tamano"]
            resultado["ya_estaban" if igual else "fallidos"].append(clave)
        except AlmacenError:
            resultado["fallidos"].append(clave)
        finally:
            with suppress(AlmacenError):  # staging only; the verifier reports what remains
                almacen.borrar(temporal)
    return resultado


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sube un respaldo exportado a un almacén nuevo.")
    parser.add_argument("carpeta", help="carpeta exportada por scripts/verificar_archivos.py")
    destino = parser.add_mutually_exclusive_group(required=True)
    destino.add_argument("--almacen-local", metavar="CARPETA")
    destino.add_argument("--almacen-entorno", action="store_true")
    args = parser.parse_args(argv)

    from server import almacen_supabase, recuperacion
    from server.almacen import AlmacenError, AlmacenLocal

    carpeta = Path(args.carpeta).expanduser()
    try:
        if args.almacen_local:
            raiz = Path(args.almacen_local).expanduser()
            raiz.mkdir(mode=0o700, exist_ok=True)
            almacen: Any = AlmacenLocal(raiz)
        else:
            fabrica = almacen_supabase.fabrica_desde_entorno(os.environ)
            if fabrica is None:
                print("Error: el almacén remoto no está configurado en las variables de entorno.",
                      file=sys.stderr)
                return 2
            almacen = fabrica()
        resultado = restaurar(carpeta, almacen)
    except (recuperacion.ManifiestoInvalidoError, AlmacenError, OSError) as exc:
        print(f"Error: no se pudo restaurar ({type(exc).__name__}).", file=sys.stderr)
        return 2
    print(f"Subidos: {len(resultado['subidos'])} · ya estaban: {len(resultado['ya_estaban'])}"
          f" · con problemas: {len(resultado['fallidos'])}")
    for clave in resultado["fallidos"]:
        print(f"  PROBLEMA {clave}")
    return 1 if resultado["fallidos"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

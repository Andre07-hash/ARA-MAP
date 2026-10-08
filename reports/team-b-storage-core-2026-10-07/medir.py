"""Measure that the local backend streams: time and Python peak allocations.

Run from the repository root:  python3 reports/team-b-storage-core-2026-10-07/medir.py [MiB]
Uses a disposable temporary root, synthetic bytes, and removes everything after.
"""

from __future__ import annotations

import hashlib
import platform
import resource
import shutil
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.almacen import BLOQUE_LECTURA, AlmacenLocal  # noqa: E402

MB = 1024 * 1024


def main() -> None:
    mib = int(sys.argv[1]) if len(sys.argv) > 1 else 256
    tamano = mib * MB
    bloque = bytes(range(256)) * (MB // 256)

    def flujo():
        for _ in range(mib):
            yield bloque

    raiz = tempfile.mkdtemp(prefix="ara-medir-")
    print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")
    print(f"object size {mib} MiB, write chunks 1 MiB, read chunks {BLOQUE_LECTURA // 1024} KiB")
    rss_inicio = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    try:
        with AlmacenLocal(raiz) as almacen:
            for nombre, accion in (
                ("guardar_temporal", lambda: almacen.guardar_temporal("temporal/m1", flujo(), tamano)),
                ("copiar", lambda: almacen.copiar("temporal/m1", "final/m1/n1", tamano)),
                ("leer + sha256", lambda: leer(almacen, tamano)),
            ):
                tracemalloc.start()
                t0 = time.perf_counter()
                resultado = accion()
                dt = time.perf_counter() - t0
                _, pico = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                print(f"{nombre:18} {dt:6.2f} s  {tamano / MB / dt:7.1f} MiB/s  "
                      f"peak Python allocations {pico / MB:5.2f} MiB  -> {resultado}")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
    rss_fin = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"max RSS grew by {(rss_fin - rss_inicio) / 1024:.1f} MiB (ru_maxrss, KiB on Linux)")


def leer(almacen: AlmacenLocal, tamano: int) -> str:
    h = hashlib.sha256()
    with almacen.leer("final/m1/n1", tamano) as lectura:
        for parte in lectura:
            h.update(parte)
    return h.hexdigest()[:16] + "…"


if __name__ == "__main__":
    main()

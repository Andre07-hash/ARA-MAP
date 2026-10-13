"""Real-provider gate for the Supabase store. Run ONLY with the owner's authorization.

    pip install storage3==2.32.0 httpx==0.28.1
    export ARA_MAP_ARCHIVOS_SUPABASE_URL=...   # a DISPOSABLE test bucket, not the pilot's
    export ARA_MAP_ARCHIVOS_SUPABASE_KEY=...   # the server credential the host will use
    export ARA_MAP_ARCHIVOS_SUPABASE_BUCKET=...
    python3 reports/team-b-free-files-2026-10-13/prueba_proveedor.py [--grandes]

It never prints a URL, key or credential. Every object it writes is under
keys with one random run id (temporal/prueba-<id>..., final/prueba-<id>/...)
and it deletes exactly those keys at the end, even after a failure. It writes
at most about 2 x 45 MiB with --grandes (counts against the free quota and
egress); without it, a few KiB. Results are what this provider, credential
and bucket did now; record them with the date.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.almacen import (  # noqa: E402
    ColisionError,
    FalloAlmacenError,
    LimiteExcedidoError,
    ObjetoAusenteError,
)
from server.almacen_supabase import ENV_BUCKET, ENV_KEY, ENV_URL, fabrica_desde_entorno  # noqa: E402

MIB = 1024 * 1024
resultados: list[tuple[str, bool, str]] = []


def anotar(nombre: str, ok: bool, detalle: str = "") -> None:
    resultados.append((nombre, ok, detalle))
    print(("OK    " if ok else "FALLA ") + nombre + (f" — {detalle}" if detalle else ""), flush=True)


def bloques(datos: bytes) -> list[bytes]:
    return [datos[i:i + MIB] for i in range(0, len(datos), MIB)] or [b""]


def leer_todo(almacen, clave: str, limite: int) -> bytes:
    with almacen.leer(clave, limite) as lectura:
        return b"".join(lectura)


def main() -> int:
    args = argparse.ArgumentParser()
    args.add_argument("--grandes", action="store_true", help="también 20 MiB y 25 MiB")
    opciones = args.parse_args()
    fabrica = fabrica_desde_entorno(os.environ)
    if fabrica is None:
        print("Faltan o son inválidas las variables del almacén.", file=sys.stderr)
        return 2
    almacen = fabrica()
    run = secrets.token_hex(6)
    temporal, final = f"temporal/prueba-{run}", f"final/prueba-{run}"
    propias = [temporal, f"{temporal}-b", f"{final}/a", f"{final}/carrera", f"{final}/grande"]
    try:
        # 1. Staging replacement and immediate read (no stale cache).
        almacen.guardar_temporal(temporal, [b"version-uno"], 100)
        almacen.guardar_temporal(temporal, [b"version-dos-mas-larga"], 100)
        anotar("reemplazo y lectura inmediata",
               leer_todo(almacen, temporal, 100) == b"version-dos-mas-larga")
        anotar("metadatos: tamano_de tras reemplazo", almacen.tamano_de(temporal) == 21,
               str(almacen.tamano_de(temporal)))
        # 2. Create-only final, collision and its error mapping.
        almacen.copiar(temporal, f"{final}/a", 100)
        try:
            almacen.copiar(temporal, f"{final}/a", 100)
            anotar("crear sin sobrescribir: segunda copia rechazada", False, "no hubo error")
        except ColisionError:
            anotar("crear sin sobrescribir: segunda copia rechazada", True, "ColisionError")
        except FalloAlmacenError as exc:
            anotar("crear sin sobrescribir: segunda copia rechazada", False,
                   f"mapeo distinto: {exc.proveedor}")
        anotar("final conserva sus bytes", leer_todo(almacen, f"{final}/a", 100)
               == b"version-dos-mas-larga")
        # 3. Concurrent creation: exactly one winner.
        almacen.guardar_temporal(f"{temporal}-b", [b"otro-contenido"], 100)
        salidas: list[str] = []

        def copiar(origen: str) -> None:
            try:
                almacen.copiar(origen, f"{final}/carrera", 100)
                salidas.append("gana")
            except ColisionError:
                salidas.append("colision")
            except Exception as exc:  # noqa: BLE001 - recorded as evidence
                salidas.append(type(exc).__name__)

        hilos = [threading.Thread(target=copiar, args=(o,)) for o in (temporal, f"{temporal}-b")]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        anotar("carrera de creación: un ganador", sorted(salidas) == ["colision", "gana"],
               ",".join(sorted(salidas)))
        # 4. Bounded reads and absence.
        try:
            leer_todo(almacen, f"{final}/a", 5)
            anotar("lectura acotada rechaza objeto mayor", False)
        except LimiteExcedidoError:
            anotar("lectura acotada rechaza objeto mayor", True)
        try:
            leer_todo(almacen, f"{final}/no-existe", 100)
            anotar("objeto ausente", False)
        except ObjetoAusenteError:
            anotar("objeto ausente", True)
        anotar("tamano_de de ausente es None", almacen.tamano_de(f"{final}/no-existe") is None)
        anotar("listar encuentra el final propio",
               any(m.clave == f"{final}/a" for m in almacen.listar(f"{final}/")))
        # 5. Privacy: no anonymous access with the bucket's public or plain path.
        import httpx
        base = os.environ[ENV_URL].rstrip("/").removesuffix("/storage/v1") + "/storage/v1/object"
        cubo = os.environ[ENV_BUCKET]
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as anon:
            estados = [anon.get(f"{base}/public/{cubo}/{final}/a").status_code,
                       anon.get(f"{base}/{cubo}/{final}/a").status_code]
        anotar("sin lectura anónima", 200 not in estados, str(estados))
        # 6. Provider error with a rejected credential: storage failure, not retryable.
        entorno = dict(os.environ)
        entorno[ENV_KEY] = "credencial-invalida-de-prueba"
        malo = fabrica_desde_entorno(entorno)
        assert malo is not None
        try:
            malo().tamano_de(f"{final}/a")
            anotar("credencial rechazada es fallo no reintentable", False, "sin error")
        except FalloAlmacenError as exc:
            anotar("credencial rechazada es fallo no reintentable", exc.reintentar is False,
                   f"{exc.proveedor}, reintentar={exc.reintentar}")
        # 7. Full-size transfers (the host gate repeats this through the app).
        if opciones.grandes:
            for nombre, tamano in (("kmz 20 MiB", 20 * MIB), ("pdf 25 MiB", 25 * MIB)):
                datos = os.urandom(tamano)
                inicio = time.monotonic()
                almacen.guardar_temporal(temporal, bloques(datos), tamano)
                almacen.borrar(f"{final}/grande")
                almacen.copiar(temporal, f"{final}/grande", tamano)
                leido = leer_todo(almacen, f"{final}/grande", tamano)
                anotar(f"transferencia completa {nombre}",
                       hashlib.sha256(leido).digest() == hashlib.sha256(datos).digest(),
                       f"{time.monotonic() - inicio:.1f} s ida y vuelta")
    except Exception as exc:  # noqa: BLE001 - an unexpected provider answer is the finding
        anotar("ejecución completa", False, f"{type(exc).__name__}: {getattr(exc, 'proveedor', '')}")
    finally:
        for clave in propias:
            try:
                almacen.borrar(clave)
            except Exception:  # noqa: BLE001
                print(f"No se pudo borrar una clave de prueba: {clave}", file=sys.stderr)
    fallas = [n for n, ok, _ in resultados if not ok]
    print(f"{len(resultados) - len(fallas)}/{len(resultados)} comprobaciones correctas")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())

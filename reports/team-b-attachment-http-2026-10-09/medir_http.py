"""Near-limit 2B HTTP measurements with fictional bytes (local store, SQLite).

    PYTHONPATH=. python3 reports/team-b-attachment-http-2026-10-09/medir_http.py

HTTP HARNESS EVIDENCE: the routes are registered temporarily on the real router
and served by the real dispatcher over loopback (tests/archivos_http_harness.py).
Server and client run in ONE process, so each tracemalloc peak includes the
client's copy of the request/response as well as the server's work. Peaks are
Python allocations only (tracemalloc), not process RSS.
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import sqlite3
import tempfile
import time
import tracemalloc
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from server import archivos, db
from server.almacen import AlmacenLocal
from server.api import archivos as api
from tests.test_archivos_http import HTTPSQLite, kml_limite, kmz_de_kml

ROOT = Path(__file__).resolve().parents[2]
KML = (ROOT / "tests" / "fixtures" / "kmz" / "poligono_simple.kml").read_bytes()


@contextmanager
def contar_sql():
    """Count SQL statements on every connection the request opens."""
    sentencias: list[str] = []
    real = db.connect

    def conectar(*args, **kwargs):
        conn = real(*args, **kwargs)
        conn.set_trace_callback(sentencias.append)
        return conn

    with patch.object(db, "connect", conectar):
        yield sentencias


def fase(nombre, llamada):
    tracemalloc.reset_peak()
    base, _ = tracemalloc.get_traced_memory()
    with contar_sql() as sentencias:
        t0 = time.perf_counter()
        resultado = llamada()
        dt = time.perf_counter() - t0
    _, pico = tracemalloc.get_traced_memory()
    return resultado, {"fase": nombre, "segundos": round(dt, 3),
                       "pico_python_mib": round((pico - base) / 1024 / 1024, 2),
                       "sentencias_sql": len([s for s in sentencias if not s.startswith("PRAGMA")])}


def ciclo(t: HTTPSQLite, nombre: str, tipo: str, datos: bytes) -> list[dict]:
    filas = []
    (s, inicio), m = fase(f"{nombre}: iniciar", lambda: t.iniciar(datos, tipo, nombre=f"{nombre}.{tipo}"))
    filas.append(m | {"status": s})
    (s, r), m = fase(f"{nombre}: PUT contenido", lambda: t.subir(inicio["version_id"], datos))
    filas.append(m | {"status": s, "bytes_peticion": len(datos)})
    (s, r), m = fase(f"{nombre}: completar", lambda: t.completar(inicio["version_id"]))
    filas.append(m | {"status": s, "estado": r["version"]["estado"],
                      "resultado_intento": (r.get("intento") or {}).get("resultado")})
    (s, h, cuerpo), m = fase(f"{nombre}: descarga",
                             lambda: t.bajar(f"/api/archivos/versiones/{inicio['version_id']}/descarga"))
    filas.append(m | {"status": s, "bytes_respuesta": len(cuerpo),
                      "hash_identico": hashlib.sha256(cuerpo).digest() == hashlib.sha256(datos).digest()})
    return filas, r


def main() -> None:
    caso = HTTPSQLite("test_store_not_configured_is_controlled")
    caso.setUp()
    raiz = tempfile.TemporaryDirectory()
    api.configurar_almacen(lambda: AlmacenLocal(raiz.name))
    caso.c.timeout = 1800
    limite = kmz_de_kml(kml_limite())
    # Wall time of the parser-limit completion WITHOUT tracemalloc (its overhead
    # on the parser's validation loops is large); the traced cycle follows.
    s, inicio = caso.iniciar(limite, "kmz", nombre="sin-trazado.kmz")
    caso.subir(inicio["version_id"], limite)
    t0 = time.perf_counter()
    s, r = caso.completar(inicio["version_id"])
    sin_trazado = {"fase": "kmz-100000-vertices: completar SIN tracemalloc", "status": s,
                   "segundos": round(time.perf_counter() - t0, 3),
                   "resultado_intento": (r.get("intento") or {}).get("resultado")}
    tracemalloc.start()
    filas = [sin_trazado]
    try:
        pdf = b"%PDF-1.4\n" + bytes(archivos.PDF_MAX - len(b"%PDF-1.4\n"))
        f, _ = ciclo(caso, "pdf-25MiB-exacto", "pdf", pdf)
        filas += f
        relleno = io.BytesIO()
        with zipfile.ZipFile(relleno, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("doc.kml", KML)
            zf.writestr("relleno-ficticio.bin", bytes(archivos.KMZ_MAX - 4096))
        f, _ = ciclo(caso, "kmz-casi-20MiB", "kmz", relleno.getvalue())
        filas += f
        f, r = ciclo(caso, "kmz-100000-vertices", "kmz", limite)
        filas += f
        gid = r["archivo"]["geometria_activa_id"]
        (s, meta), m = fase("geometria: metadatos (1 id)", lambda: caso.j(
            "POST", "/api/archivos/geometrias/metadatos", datos={"ids": [gid]}))
        d = meta["geometrias"][gid]
        filas.append(m | {"status": s, "bytes_geojson": d["bytes"], "fragmentos": d["fragmentos"],
                          "vertices": d["vertices"], "partes": d["partes"]})
        ids = [gid] + [str(uuid.uuid4()) for _ in range(49)]
        (s, meta50), m = fase("geometria: metadatos (50 ids)", lambda: caso.j(
            "POST", "/api/archivos/geometrias/metadatos", datos={"ids": ids}))
        filas.append(m | {"status": s, "bytes_respuesta": len(json.dumps(meta50).encode())})
        desde, partes = 0, []
        while True:
            (s, h, cuerpo), m = fase(f"geometria: fragmento desde={desde}", lambda d=desde: caso.bajar(
                f"/api/archivos/geometrias/{gid}/contenido?desde={d}"))
            filas.append(m | {"status": s, "bytes_respuesta": len(cuerpo), "final": h["X-Geometria-Final"]})
            partes.append(cuerpo)
            if h["X-Geometria-Final"] == "1":
                break
            desde = int(h["X-Geometria-Siguiente"])
        datos = b"".join(partes)
        filas.append({"fase": "geometria: reensamblado", "bytes": len(datos),
                      "sha256_coincide": hashlib.sha256(datos).hexdigest() == d["sha256"]})
    finally:
        tracemalloc.stop()
        api.configurar_almacen(None)
        caso.doCleanups()
        raiz.cleanup()
    print(json.dumps({"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                      "platform": platform.platform(), "mediciones": filas},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

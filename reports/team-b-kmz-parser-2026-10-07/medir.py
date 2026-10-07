"""Measure server/kmz.py on synthetic FICTIONAL files near its limits.

    python3 reports/team-b-kmz-parser-2026-10-07/medir.py

Each case runs in a fresh child process so peak RSS is per case. Reports wall
time of procesar_kmz (median of 3, after one untimed call), RSS growth during
that first call, tracemalloc peak of Python allocations, process peak RSS,
and the size of the JSON-serialized result. Report evidence
only; not part of the test suite.
"""

from __future__ import annotations

import io
import json
import math
import platform
import resource
import statistics
import subprocess
import sys
import time
import tracemalloc
import zipfile
from collections.abc import Callable
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from server import kmz  # noqa: E402

LON, LAT = -100.4, 20.6


def documento(cuerpo: str) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
            f"<Document><name>Medición ficticia</name>{cuerpo}</Document></kml>").encode()


def placemark(nombre: str, anillos: list[list[tuple[float, float]]]) -> str:
    def texto(anillo: list[tuple[float, float]]) -> str:
        return " ".join(f"{x:.7f},{y:.7f}" for x, y in anillo)
    huecos = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{texto(h)}</coordinates>"
                     "</LinearRing></innerBoundaryIs>" for h in anillos[1:])
    return (f"<Placemark><name>{nombre}</name><Polygon><outerBoundaryIs><LinearRing>"
            f"<coordinates>{texto(anillos[0])}</coordinates></LinearRing></outerBoundaryIs>"
            f"{huecos}</Polygon></Placemark>")


def circulo(posiciones: int, radio: float = 0.01, cx: float = LON,
            cy: float = LAT) -> list[tuple[float, float]]:
    n = posiciones - 1
    pts = [(cx + radio * math.cos(2 * math.pi * k / n), cy + radio * math.sin(2 * math.pi * k / n))
           for k in range(n)]
    return [*pts, pts[0]]


def dientes(posiciones: int) -> list[tuple[float, float]]:
    """A comb of long thin teeth: the worst case for the longitude sweep."""
    t = (posiciones - 3) // 4
    pts = [(LON, LAT)]
    for k in range(t):
        y = LAT + k * 0.00002
        pts += [(LON + 0.05, y), (LON + 0.05, y + 0.00001), (LON + 0.00001, y + 0.00001),
                (LON + 0.00001, y + 0.00002)]
    pts += [(LON, LAT + t * 0.00002), (LON, LAT)]
    return pts


def empaquetar(kml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml)
    return buf.getvalue()


def _lotes() -> bytes:
    m = kmz.MAX_VERTICES
    return empaquetar(documento("".join(
        placemark(f"Lote {k}", [circulo(m // kmz.MAX_CANDIDATOS, 0.0004,
                                        LON + (k % 25) * 0.001, LAT + (k // 25) * 0.001)])
        for k in range(kmz.MAX_CANDIDATOS))))


def _borde_compartido() -> bytes:
    """Two parts sharing one detailed wiggling edge, selected together."""
    n = kmz.MAX_VERTICES // 2 - 4
    alto = n * 1e-6
    borde = [(LON + 0.0005 * math.sin(k / 50), LAT + k * 1e-6) for k in range(n)]
    oeste = [(LON - 0.01, LAT), *borde, (LON - 0.01, LAT + alto)]
    este = [(LON + 0.01, LAT), *borde, (LON + 0.01, LAT + alto)]
    return empaquetar(documento(placemark("Oeste", [[*oeste, oeste[0]]])
                                + placemark("Este", [[*este, este[0]]])))


def _huecos(n: int, por_fila: int = 50, paso: float = 0.003) -> bytes:
    """The supervisor's F2 fixture: one shell, n disjoint 0.001° square holes."""
    lado = 0.2 if por_fila == 50 else 0.3
    exterior = [(LON, LAT), (LON + lado, LAT), (LON + lado, LAT + lado), (LON, LAT + lado),
                (LON, LAT)]
    huecos = []
    for i in range(n):
        x, y = LON + 0.001 + (i % por_fila) * paso, LAT + 0.001 + (i // por_fila) * paso
        huecos.append([(x, y), (x + .001, y), (x + .001, y + .001), (x, y + .001), (x, y)])
    return empaquetar(documento(placemark("H", [exterior, *huecos])))


def _fila_de_huecos(n: int) -> bytes:
    """Adversarial: n holes in ONE row; every horizontal ray crosses the rest."""
    ancho = n * 0.0002 + 0.001
    exterior = [(LON, LAT), (LON + ancho, LAT), (LON + ancho, LAT + 0.002), (LON, LAT + 0.002),
                (LON, LAT)]
    huecos = [[(x, LAT + .0005), (x + .0001, LAT + .0005), (x + .0001, LAT + .0015),
               (x, LAT + .0015), (x, LAT + .0005)]
              for x in (LON + 0.0005 + i * 0.0002 for i in range(n))]
    return empaquetar(documento(placemark("F", [exterior, *huecos])))


def _rectangulo_f1() -> bytes:
    """The supervisor's F1 reproducer: vertices at every old sampling height."""
    rect = [(-100.4, 20.6), (-100.39, 20.6), (-100.39, 20.61), (-100.4, 20.61)]
    alturas = sorted({20.6 + 0.01 * (0.5 if k == 1 else (0.5 + k * 0.6180339887498949) % 1.0)
                      for k in range(1, 200)})
    anillo = rect + [(-100.4, y) for y in reversed(alturas)] + rect[:1]
    coords = " ".join(f"{x},{y}" for x, y in anillo)        # exact, not rounded
    return empaquetar(documento(
        "<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>" + coords
        + "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"))


def _multiparte(n: int) -> bytes:
    """Second review: n disjoint squares in ONE placemark's MultiGeometry."""
    poligonos = []
    for i in range(n):
        x, y = LON + (i % 40) * .003, LAT + (i // 40) * .003
        anillo = [(x, y), (x + .001, y), (x + .001, y + .001), (x, y + .001), (x, y)]
        poligonos.append("<Polygon><outerBoundaryIs><LinearRing><coordinates>"
                         + " ".join(f"{a},{b}" for a, b in anillo)
                         + "</coordinates></LinearRing></outerBoundaryIs></Polygon>")
    return empaquetar(documento("<Placemark><MultiGeometry>" + "".join(poligonos)
                                + "</MultiGeometry></Placemark>"))


def _elementos_al_limite() -> bytes:
    base = documento(placemark("S", [circulo(5)]))
    relleno = b"<Folder/>" * (kmz.MAX_ELEMENTOS - 20)
    return empaquetar(base.replace(b"</Document>", relleno + b"</Document>"))


def _justo_bajo_el_limite() -> bytes:
    base = documento(placemark("S", [circulo(5)]))
    relleno = kmz.MAX_KML_BYTES - len(base)
    return empaquetar(base.replace(b"</Document>", b" " * relleno + b"</Document>"))


# Built lazily: each child process constructs only its own case.
CASOS: dict[str, Callable[[], tuple[bytes, object]]] = {
    "circulo_100k_vertices": lambda: (
        empaquetar(documento(placemark("C", [circulo(kmz.MAX_VERTICES)]))), None),
    "con_hueco_100k_vertices": lambda: (empaquetar(documento(placemark(
        "H", [circulo(kmz.MAX_VERTICES // 2, 0.02), circulo(kmz.MAX_VERTICES // 2, 0.01)]))),
        None),
    "peine_100k_vertices": lambda: (
        empaquetar(documento(placemark("P", [dientes(kmz.MAX_VERTICES)]))), None),
    "500_lotes_sin_seleccion": lambda: (_lotes(), None),
    "500_lotes_todos_seleccionados": lambda: (_lotes(), list(range(kmz.MAX_CANDIDATOS))),
    "2_partes_borde_compartido_100k": lambda: (_borde_compartido(), [0, 1]),
    "F1_rectangulo_203_vertices": lambda: (_rectangulo_f1(), None),
    "F2_huecos_100": lambda: (_huecos(100), None),
    "F2_huecos_500": lambda: (_huecos(500), None),
    "F2_huecos_1500": lambda: (_huecos(1500), None),
    "huecos_19999_100k_vertices": lambda: (_huecos(19_999, 150, 0.0019), None),
    "fila_de_2000_huecos": lambda: (_fila_de_huecos(2000), None),
    "fila_de_19999_huecos_adversaria": lambda: (_fila_de_huecos(19_999), None),
    "multiparte_100_partes": lambda: (_multiparte(100), None),
    "multiparte_400_partes": lambda: (_multiparte(400), None),
    "multiparte_800_partes": lambda: (_multiparte(800), None),
    "multiparte_4000_partes": lambda: (_multiparte(4000), None),
    "multiparte_20000_partes_100k_vertices": lambda: (_multiparte(20_000), None),
    "500k_elementos_al_limite": lambda: (_elementos_al_limite(), None),
    "vertices_300k_corte_en_100k": lambda: (
        empaquetar(documento(placemark("X", [circulo(3 * kmz.MAX_VERTICES)]))), None),
    "kml_16MiB_justo_bajo_limite": lambda: (_justo_bajo_el_limite(), None),
}


class _Registro(kmz.Presupuesto):
    """Remembers the work units each processing call charged."""
    usos: list[kmz.Presupuesto] = []

    def __init__(self, limite: int | None = None) -> None:
        super().__init__(limite)
        _Registro.usos.append(self)


def medir(nombre: str) -> dict[str, object]:
    kmz.Presupuesto = _Registro                 # type: ignore[misc]
    datos, seleccion = CASOS[nombre]()
    rss_antes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    resultado = kmz.procesar_kmz(datos, seleccion)      # first call: RSS growth
    rss_despues = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tiempos = []
    for _ in range(3):
        t0 = time.perf_counter()
        resultado = kmz.procesar_kmz(datos, seleccion)
        tiempos.append(time.perf_counter() - t0)
    tracemalloc.start()
    kmz.procesar_kmz(datos, seleccion)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "caso": nombre,
        "kmz_bytes": len(datos),
        "estado": resultado["estado"],
        "codigo": (resultado["error"] or {}).get("codigo"),
        "segundos_mediana": round(statistics.median(tiempos), 3),
        "segundos_max": round(max(tiempos), 3),
        "tracemalloc_pico_mib": round(pico / 2 ** 20, 1),
        # Peak RSS of the whole child, and the growth during the first call
        # after the fixture was built (ru_maxrss is KiB on Linux).
        "rss_pico_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "rss_pico_tras_fixture_mib": round((rss_despues - rss_antes) / 1024, 1),
        "resultado_json_bytes": len(json.dumps(resultado, ensure_ascii=False)),
        "trabajo_unidades": _Registro.usos[0].usado,
        "trabajo_limite": kmz.MAX_TRABAJO,
    }


def main() -> None:
    if len(sys.argv) > 1:
        print(json.dumps(medir(sys.argv[1])))
        return
    print(f"python {platform.python_version()} · {platform.machine()} · {platform.system()} "
          f"{platform.release()} · cpus {__import__('os').cpu_count()}")
    print(f"MAX_VERTICES={kmz.MAX_VERTICES} MAX_KML_BYTES={kmz.MAX_KML_BYTES} "
          f"MAX_CANDIDATOS={kmz.MAX_CANDIDATOS} MAX_ELEMENTOS={kmz.MAX_ELEMENTOS} "
          f"MAX_TRABAJO={kmz.MAX_TRABAJO}")
    for nombre in CASOS:
        salida = subprocess.run([sys.executable, __file__, nombre], capture_output=True,
                                text=True, check=True)
        print(salida.stdout.strip())


if __name__ == "__main__":
    main()

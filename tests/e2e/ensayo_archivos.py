"""Repeated and concurrent PDF/KMZ trials against the real local server (issue #51).

    python3 tests/e2e/ensayo_archivos.py --salida /tmp/ensayo.json
    python3 tests/e2e/ensayo_archivos.py --fases grandes --limite-memoria-mb 512

Starts tests/e2e/tabla_servidor.py (the real server.app.Handler, a disposable
SQLite file and the local disk store in a temporary folder deleted at the end)
with fictional accounts, and drives the attachment API over real loopback
HTTP with one cookie session per account. Nothing is simulated on the server
side and nothing here can reach a hosted database or bucket: the provider
variables are removed before the server starts and only 127.0.0.1 is used.

Phases (all by default, or a comma list in --fases):

- ciclos:    N sequential cycles on one session (PDF, KMZ, replays, double
             completion, cancellation, deletion with a stale link, reads).
- sesiones:  the same cycle in 2 and then 5 isolated sessions at once.
- grandes:   a PDF of exactly 25 MiB and a valid KMZ of exactly 20 MiB at the
             same time while other sessions read, then one byte over each.
- reinicio:  uploads stopped before content, after content and after
             completion; the server is killed (SIGKILL) and started again on
             the same folder; then a kill in the middle of a large PUT.

Every saved file is checked byte for byte (size and SHA-256) against what was
sent, every terrain's listing is compared with the expected set (no duplicate,
no missing, no extra), and the store folder must hold no staging object and
exactly one final object per saved version. Durations, errors and the peak
resident memory of the server process (VmHWM) are written to --salida.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import os
import random
import re
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]
CLAVE = re.search(r'TEST_PASSWORD\s*=\s*"([^"]+)"', (RAIZ / "tests" / "support.py").read_text())[1]
MiB = 1024 * 1024
PDF_MAX = 25 * MiB
KMZ_MAX = 20 * MiB
OPERADORES = ("olga", "omar", "oscar", "olivia", "oriol")      # granted "Base Grande" by the seed
VARIABLES_NUBE = ("ARA_MAP_DATABASE_URL", "DATABASE_URL", "ARA_MAP_READ_ONLY", "ARA_MAP_ARCHIVOS",
                  "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ARA_MAP_SUPABASE_URL",
                  "ARA_MAP_SUPABASE_CLAVE", "ARA_MAP_SUPABASE_BUCKET")


# ------------------------------------------------------------------ fixtures

def pdf_ficticio(semilla: str, tamano: int | None = None) -> bytes:
    cabeza = f"%PDF-1.4\n% ensayo ficticio {semilla}\n1 0 obj << /Type /Catalog >> endobj\n".encode()
    cola = b"\ntrailer << /Root 1 0 R >>\n%%EOF\n"
    if tamano is None:
        tamano = len(cabeza) + len(cola) + random.randint(2_000, 60_000)
    relleno = tamano - len(cabeza) - len(cola) - 1
    return cabeza + b"%" + random.randbytes(relleno) + cola


def kml_poligono(semilla: int) -> bytes:
    x = -100.40 + (semilla % 97) * 0.001
    y = 20.60 + (semilla % 89) * 0.001
    d = 0.0005 + (semilla % 7) * 0.0001
    coords = " ".join(f"{a:.6f},{b:.6f}" for a, b in
                      ((x, y), (x + d, y), (x + d, y + d), (x, y + d), (x, y)))
    return ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2">'
            f"<Document><Placemark><name>Lote ficticio {semilla}</name><Polygon><outerBoundaryIs>"
            f"<LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs>"
            "</Polygon></Placemark></Document></kml>").encode()


def kmz_ficticio(semilla: int, tamano: int | None = None) -> bytes:
    """One valid polygon; with `tamano`, a stored padding member makes it exactly that long."""
    def armar(relleno: int) -> bytes:
        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w") as z:
            info = zipfile.ZipInfo("doc.kml", date_time=(2026, 10, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, kml_poligono(semilla))
            if relleno:
                extra = zipfile.ZipInfo("files/relleno.bin", date_time=(2026, 10, 15, 0, 0, 0))
                extra.compress_type = zipfile.ZIP_STORED
                z.writestr(extra, random.Random(semilla).randbytes(relleno))
        return salida.getvalue()
    if tamano is None:
        return armar(0)
    base = len(armar(1))
    datos = armar(1 + tamano - base)
    assert len(datos) == tamano, (len(datos), tamano)
    return datos


def sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


# ------------------------------------------------------------------ server

class Servidor:
    def __init__(self, puerto: int, carpeta: Path, limite_mb: int, postgres: str | None) -> None:
        self.puerto, self.carpeta, self.limite_mb, self.postgres = puerto, carpeta, limite_mb, postgres
        self.proc: subprocess.Popen[str] | None = None
        self.picos: list[int] = []
        self.picos_virtuales: list[int] = []
        self.muestras: list[tuple[float, int]] = []

    def iniciar(self) -> None:
        entorno = {k: v for k, v in os.environ.items() if k not in VARIABLES_NUBE}
        cmd = [sys.executable, str(RAIZ / "tests" / "e2e" / "tabla_servidor.py"),
               "--puerto", str(self.puerto), "--carpeta", str(self.carpeta), "--registros", "60"]
        if self.postgres:
            cmd += ["--postgres-esquema", self.postgres]
        if self.limite_mb:
            cmd = ["prlimit", f"--as={self.limite_mb * MiB}", "--"] + cmd
        self.err = open(self.carpeta.parent / "servidor.err", "a")   # noqa: SIM115 - closed in detener()
        self.proc = subprocess.Popen(cmd, cwd=RAIZ, env=entorno, stdout=subprocess.PIPE,
                                     stderr=self.err, text=True)
        assert self.proc.stdout is not None
        for linea in self.proc.stdout:
            if linea.startswith("LISTO"):
                break
        else:
            raise SystemExit("el servidor local no arrancó; ver servidor.err")
        threading.Thread(target=self.proc.stdout.read, daemon=True).start()
        # LISTO is printed just before the socket is bound.
        for _ in range(200):
            try:
                socket.create_connection(("127.0.0.1", self.puerto), timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        self._vigilar = True
        threading.Thread(target=self._muestrear, daemon=True).start()

    def _status(self, campo: str) -> int:
        try:
            texto = Path(f"/proc/{self.proc.pid}/status").read_text()   # type: ignore[union-attr]
        except OSError:
            return 0
        m = re.search(rf"^{campo}:\s+(\d+) kB", texto, re.M)
        return int(m[1]) * 1024 if m else 0

    def _muestrear(self) -> None:
        inicio = time.monotonic()
        while self._vigilar and self.proc and self.proc.poll() is None:
            self.muestras.append((round(time.monotonic() - inicio, 2), self._status("VmRSS")))
            time.sleep(0.05)

    def detener(self, senal: int = signal.SIGTERM) -> None:
        if not self.proc:
            return
        self.picos.append(self._status("VmHWM"))
        self.picos_virtuales.append(self._status("VmPeak"))
        self._vigilar = False
        self.proc.send_signal(senal)
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc = None
        self.err.close()


# ------------------------------------------------------------------ client

class FalloError(AssertionError):
    pass


class Sesion:
    def __init__(self, puerto: int, login: str, registro: Registro) -> None:
        self.puerto, self.login, self.registro = puerto, login, registro
        self.cookie = ""
        s, h, cuerpo = self.pedir("POST", "/api/login", datos={"username": login, "password": CLAVE},
                                  operacion="login")
        if s != 200:
            raise FalloError(f"login {login}: {s} {cuerpo[:200]!r}")
        self.cookie = h["Set-Cookie"].split(";", 1)[0]

    def pedir(self, metodo: str, ruta: str, *, datos: Any = None, cuerpo: bytes | None = None,
              cabeceras: dict[str, str] | None = None, operacion: str = "",
              timeout: float = 120) -> tuple[int, dict[str, str], bytes]:
        h = dict(cabeceras or {})
        if self.cookie:
            h["Cookie"] = self.cookie
        if datos is not None:
            cuerpo = json.dumps(datos).encode()
            h["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=timeout)
        t = time.monotonic()
        try:
            conn.request(metodo, ruta, body=cuerpo, headers=h)
            r = conn.getresponse()
            resultado = r.status, {k: v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()
            self.registro.tiempo(operacion or metodo, time.monotonic() - t)
        return resultado

    def json(self, metodo: str, ruta: str, **kw: Any) -> tuple[int, Any]:
        s, _h, cuerpo = self.pedir(metodo, ruta, **kw)
        try:
            return s, json.loads(cuerpo) if cuerpo else None
        except ValueError:
            raise FalloError(f"{metodo} {ruta}: respuesta no JSON {s} {cuerpo[:200]!r}") from None


class Registro:
    """Timings, failures and the expected saved set, shared by every thread."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tiempos: dict[str, list[float]] = defaultdict(list)
        self.fallos: list[str] = []
        self.esperado: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)   # terrain -> version -> file
        self.borrados: list[tuple[str, str]] = []
        self.conteo: dict[str, int] = defaultdict(int)

    def tiempo(self, operacion: str, segundos: float) -> None:
        with self.lock:
            self.tiempos[operacion].append(segundos)

    def fallo(self, texto: str) -> None:
        with self.lock:
            self.fallos.append(texto)
        print("FALLO", texto, flush=True)

    def contar(self, que: str) -> None:
        with self.lock:
            self.conteo[que] += 1

    def guardado(self, terreno: str, aid: str, vid: str, tipo: str, datos: bytes, quien: str) -> None:
        with self.lock:
            self.esperado[terreno][vid] = {"archivo": aid, "tipo": tipo, "sha": sha(datos),
                                           "bytes": len(datos), "quien": quien}

    def quitar(self, terreno: str, aid: str, vid: str) -> None:
        with self.lock:
            self.esperado[terreno].pop(vid, None)
            self.borrados.append((terreno, vid))

    def resumen(self) -> dict[str, Any]:
        out = {}
        for op, xs in sorted(self.tiempos.items()):
            xs = sorted(xs)
            out[op] = {"n": len(xs), "p50_ms": round(statistics.median(xs) * 1000, 1),
                       "p95_ms": round(xs[max(0, -(-len(xs) * 95 // 100) - 1)] * 1000, 1),
                       "max_ms": round(xs[-1] * 1000, 1)}
        return out


def esperar(cond: bool, texto: str) -> None:
    if not cond:
        raise FalloError(texto)


# ------------------------------------------------------------------ operations

def iniciar(s: Sesion, terreno: str, tipo: str, nombre: str, datos: bytes, clave: str,
            tamano: int | None = None) -> tuple[int, Any]:
    return s.json("POST", f"/api/inventario/terrenos/{terreno}/archivos", operacion="iniciar",
                  datos={"tipo": tipo, "nombre_original": nombre,
                         "tamano_declarado": len(datos) if tamano is None else tamano,
                         "sha256_declarado": sha(datos)}, cabeceras={"Idempotency-Key": clave})


def contenido(s: Sesion, vid: str, tipo: str, datos: bytes) -> tuple[int, Any]:
    tipo_mime = "application/pdf" if tipo == "pdf" else "application/vnd.google-earth.kmz"
    return s.json("PUT", f"/api/archivos/versiones/{vid}/contenido", cuerpo=datos,
                  cabeceras={"Content-Type": tipo_mime}, operacion=f"contenido_{tipo}")


def completar(s: Sesion, vid: str) -> tuple[int, Any]:
    return s.json("POST", f"/api/archivos/versiones/{vid}/completar", operacion="completar")


def descargar(s: Sesion, vid: str, datos: bytes, tipo: str) -> None:
    st, h, cuerpo = s.pedir("GET", f"/api/archivos/versiones/{vid}/descarga", operacion=f"descarga_{tipo}")
    esperar(st == 200, f"descarga {vid}: {st}")
    esperar(len(cuerpo) == len(datos) and cuerpo == datos, f"descarga {vid}: bytes distintos")
    esperar(h.get("X-Archivo-Sha256") == sha(datos) == sha(cuerpo), f"descarga {vid}: SHA-256 distinto")


def subida_completa(s: Sesion, reg: Registro, terreno: str, tipo: str, datos: bytes, nombre: str,
                    *, doble: bool = False, repetir_inicio: bool = False,
                    compartido: bool = False) -> dict[str, Any]:
    clave = str(uuid.uuid4())
    st, ini = iniciar(s, terreno, tipo, nombre, datos, clave)
    esperar(st == 200, f"iniciar {tipo} {s.login}: {st} {ini}")
    if repetir_inicio:      # the start's answer was "lost": the same key replays it
        st2, ini2 = iniciar(s, terreno, tipo, nombre, datos, clave)
        esperar(st2 == 200 and ini2["version_id"] == ini["version_id"], f"replay de inicio: {st2} {ini2}")
        reg.contar("replay_inicio")
    vid = ini["version_id"]
    st, r = contenido(s, vid, tipo, datos)
    esperar(st == 200 and r["bytes_recibidos"] == len(datos), f"contenido {vid}: {st} {r}")
    if doble:               # a double click: two completions at once
        resultados: list[tuple[int, Any]] = []
        hilos = [threading.Thread(target=lambda: resultados.append(completar(s, vid))) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        frescos = [r for st_, r in resultados if st_ == 200 and r.get("replay") is False]
        otros = [(st_, r) for st_, r in resultados if not (st_ == 200 and r.get("replay") is False)]
        esperar(len(frescos) == 1, f"doble completar {vid}: {resultados}")
        for st_, r_ in otros:
            esperar((st_ == 200 and r_.get("replay") is True)
                    or (st_ == 409 and r_["detalle"]["code"] == "procesamiento_en_curso"),
                    f"doble completar, segunda respuesta {st_} {r_}")
        reg.contar("doble_completar")
        st, r = completar(s, vid)
        esperar(st == 200 and r["replay"] is True, f"replay de completar {vid}: {st} {r}")
    else:
        st, r = completar(s, vid)
        esperar(st == 200, f"completar {vid}: {st} {r}")
    esperar(r["version"]["estado"] == "disponible", f"completar {vid}: {r['version']}")
    if tipo == "kmz":
        esperar(r["intento"]["resultado"] == "listo", f"KMZ {vid}: {r.get('intento')}")
        if r.get("aplicada") is not True:
            # Another session's KMZ for the same terrain won the revision: the
            # contract keeps this version saved but not active ("superada").
            esperar(r.get("motivo_no_aplicada") == "superada" and compartido,
                    f"KMZ {vid} no activado: {r.get('aplicada')} {r.get('motivo_no_aplicada')}")
            reg.contar("kmz_superada")
    reg.guardado(terreno, ini["archivo_id"], vid, tipo, datos, s.login)
    descargar(s, vid, datos, tipo)
    return {"vid": vid, "aid": ini["archivo_id"], "revision": r["archivo"]["revision"]}


def cancelada(s: Sesion, reg: Registro, terreno: str) -> None:
    datos = pdf_ficticio("cancelada")
    st, ini = iniciar(s, terreno, "pdf", "Cancelada ficticia.pdf", datos, str(uuid.uuid4()))
    esperar(st == 200, f"iniciar cancelada: {st} {ini}")
    contenido(s, ini["version_id"], "pdf", datos)
    st, r = s.json("POST", f"/api/archivos/versiones/{ini['version_id']}/cancelar", operacion="cancelar")
    esperar(st == 200 and r["estado"] == "cancelado", f"cancelar: {st} {r}")
    st, r = completar(s, ini["version_id"])         # a late completion after cancelling
    esperar(st == 409 and r["detalle"]["code"] == "subida_no_pendiente", f"completar cancelada: {st} {r}")
    st, _h, _b = s.pedir("GET", f"/api/archivos/versiones/{ini['version_id']}/descarga", operacion="descarga_404")
    esperar(st == 404, f"descarga de cancelada: {st}")
    reg.contar("cancelada")


def borrar_con_enlace_viejo(s: Sesion, reg: Registro, terreno: str, hecho: dict[str, Any],
                            base: str) -> None:
    st, r = s.json("POST", f"/api/archivos/{hecho['aid']}/borrar", operacion="borrar",
                   datos={"expected_revision": hecho["revision"]})
    esperar(st == 200 and r["borrado"] is True, f"borrar {hecho['aid']}: {st} {r}")
    reg.quitar(terreno, hecho["aid"], hecho["vid"])
    st, _h, cuerpo = s.pedir("GET", f"/api/archivos/versiones/{hecho['vid']}/descarga", operacion="descarga_404")
    esperar(st == 404 and json.loads(cuerpo)["detalle"]["code"] == "not_found", f"enlace viejo: {st}")
    st, t = s.json("GET", f"/api/inventario/terrenos/{terreno}", operacion="detalle_terreno")
    esperar(st == 200, f"el terreno desapareció al borrar su PDF: {st}")
    reg.contar("borrado_enlace_viejo")


def lecturas(s: Sesion, base: str) -> None:
    st, r = s.json("GET", f"/api/maestra/bases/{base}/terrenos?limit=50", operacion="tabla")
    esperar(st == 200 and len(r["terrenos"]) > 0, f"tabla: {st}")


def ciclo(s: Sesion, reg: Registro, terrenos: list[str], base: str, n: int, salto: int,
          compartido: bool = False) -> None:
    terreno = terrenos[(salto + n) % len(terrenos)]
    pdf = pdf_ficticio(f"{s.login}-{n}")
    hecho = subida_completa(s, reg, terreno, "pdf", pdf, f"Avalúo ficticio ñ #{n} (copia).pdf",
                            doble=n % 4 == 1, repetir_inicio=n % 3 == 0)
    semilla = hash((s.login, n)) % 10_000
    subida_completa(s, reg, terreno, "kmz", kmz_ficticio(semilla), f"Contorno ficticio {n}.kmz",
                    doble=n % 4 == 3, compartido=compartido)
    lecturas(s, base)
    if n % 5 == 2:
        cancelada(s, reg, terreno)
    if n % 3 == 2:
        borrar_con_enlace_viejo(s, reg, terreno, hecho, base)


# ------------------------------------------------------------------ final checks

def listar_todo(s: Sesion, terreno: str) -> list[dict[str, Any]]:
    items, cursor = [], None
    while True:
        ruta = f"/api/inventario/terrenos/{terreno}/archivos?limite=20"
        if cursor:
            ruta += "&cursor=" + cursor
        st, r = s.json("GET", ruta, operacion="listar")
        esperar(st == 200, f"listar {terreno}: {st} {r}")
        items += r["archivos"]
        cursor = r["cursor_siguiente"]
        if not cursor:
            return items


def comprobar_final(admin: Sesion, reg: Registro, carpeta: Path) -> dict[str, Any]:
    """Listing equals the expected set exactly; bytes equal; no staging left."""
    for terreno, esperados in reg.esperado.items():
        items = listar_todo(admin, terreno)
        ids = [i["id"] for i in items]
        esperar(len(ids) == len(set(ids)), f"{terreno}: archivos duplicados en el listado")
        pdf_listados = {i["id"] for i in items if i["tipo"] == "pdf"
                        and (i.get("ultima_version") or {}).get("estado") == "disponible"}
        pdf_esperados = {e["archivo"] for e in esperados.values() if e["tipo"] == "pdf"}
        esperar(pdf_listados == pdf_esperados,
                f"{terreno}: PDF guardados {sorted(pdf_listados)} != esperados {sorted(pdf_esperados)}")
        kmz_listados = {i["id"] for i in items if i["tipo"] == "kmz"}
        kmz_esperados = {e["archivo"] for e in esperados.values() if e["tipo"] == "kmz"}
        esperar(len(kmz_listados) <= 1 and kmz_listados == kmz_esperados,
                f"{terreno}: KMZ {sorted(kmz_listados)} != {sorted(kmz_esperados)}")
        for vid, e in esperados.items():
            st, _h, cuerpo = admin.pedir("GET", f"/api/archivos/versiones/{vid}/descarga",
                                         operacion="verificacion_final")
            esperar(st == 200 and len(cuerpo) == e["bytes"] and sha(cuerpo) == e["sha"],
                    f"{terreno}/{vid}: bytes finales distintos ({st})")
    for _terreno, vid in reg.borrados:
        st, _h, _b = admin.pedir("GET", f"/api/archivos/versiones/{vid}/descarga", operacion="verificacion_final")
        esperar(st == 404, f"un PDF borrado reapareció: {vid} {st}")
    almacen = carpeta / "archivos"

    def objetos(nombre: str, parciales: bool = False) -> int:
        # Hidden ".parcial-" files are writes a killed process never renamed:
        # the store documents that it never lists, reads or removes them.
        raiz = almacen / nombre
        return sum(1 for p in raiz.rglob("*") if p.is_file()
                   and p.name.startswith(".parcial-") == parciales) if raiz.exists() else 0
    return {"terrenos": len(reg.esperado),
            "versiones_esperadas": sum(len(v) for v in reg.esperado.values()),
            "objetos_temporales": objetos("temporal"), "objetos_finales": objetos("final"),
            "parciales_huerfanos": objetos("temporal", True) + objetos("final", True)}


# ------------------------------------------------------------------ phases

def base_y_terrenos(s: Sesion) -> tuple[str, list[str]]:
    st, r = s.json("GET", "/api/maestra/bases")
    base = next(b["id"] for b in r["bases"] if b["nombre"] == "Base Grande")
    st, r = s.json("GET", f"/api/maestra/bases/{base}/terrenos?limit=100")
    return base, [t["id"] for t in r["terrenos"]]


def en_paralelo(trabajos: list[Any]) -> float:
    errores: list[BaseException] = []

    def correr(fn: Any) -> None:
        try:
            fn()
        except BaseException as exc:     # noqa: BLE001 - reported below
            errores.append(exc)
    t = time.monotonic()
    hilos = [threading.Thread(target=correr, args=(fn,)) for fn in trabajos]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    if errores:
        raise errores[0]
    return time.monotonic() - t


def fase_ciclos(puerto: int, reg: Registro, ciclos: int) -> dict[str, Any]:
    s = Sesion(puerto, "olga", reg)
    base, terrenos = base_y_terrenos(s)
    duraciones = []
    for n in range(ciclos):
        t = time.monotonic()
        try:
            ciclo(s, reg, terrenos, base, n, 0)
        except FalloError as exc:
            reg.fallo(f"ciclo {n}: {exc}")
        duraciones.append(round(time.monotonic() - t, 3))
    return {"ciclos": ciclos, "duracion_ciclo_s": duraciones}


def fase_sesiones(puerto: int, reg: Registro, cantidad: int, ciclos: int) -> dict[str, Any]:
    sesiones = [Sesion(puerto, login, reg) for login in OPERADORES[:cantidad]]
    base, terrenos = base_y_terrenos(sesiones[0])

    def trabajo(i: int, s: Sesion) -> Any:
        def correr() -> None:
            for n in range(ciclos):
                try:
                    # Two sessions share every other terrain on purpose.
                    ciclo(s, reg, terrenos, base, n, 20 + (i // 2) * 7, compartido=True)
                except FalloError as exc:
                    reg.fallo(f"sesiones={cantidad} {s.login} ciclo {n}: {exc}")
        return correr
    dur = en_paralelo([trabajo(i, s) for i, s in enumerate(sesiones)])
    return {"sesiones": cantidad, "ciclos_por_sesion": ciclos, "duracion_s": round(dur, 2)}


def fase_grandes(puerto: int, reg: Registro) -> dict[str, Any]:
    ada = Sesion(puerto, "ada", reg)
    lectores = [Sesion(puerto, login, reg) for login in OPERADORES[:3]]
    base, terrenos = base_y_terrenos(ada)
    pdf, kmz = pdf_ficticio("grande", PDF_MAX), kmz_ficticio(4242, KMZ_MAX)
    esperar(len(pdf) == PDF_MAX and len(kmz) == KMZ_MAX, "tamaños de fixture")
    resultado: dict[str, Any] = {}
    alto = threading.Event()

    def leer(s: Sesion) -> Any:
        def correr() -> None:
            while not alto.is_set():
                try:
                    lecturas(s, base)
                except FalloError as exc:
                    reg.fallo(f"lectura durante grandes: {exc}")
        return correr

    def grande(tipo: str, datos: bytes, terreno: str) -> Any:
        def correr() -> None:
            t = time.monotonic()
            try:
                subida_completa(ada if tipo == "pdf" else Sesion(puerto, "alan", reg), reg, terreno, tipo,
                                datos, f"Grande ficticio al límite.{tipo}")
            except FalloError as exc:
                reg.fallo(f"grande {tipo}: {exc}")
            resultado[f"{tipo}_s"] = round(time.monotonic() - t, 2)
        return correr
    hilos = [threading.Thread(target=leer(s)) for s in lectores]
    for h in hilos:
        h.start()
    try:
        resultado["simultaneo_s"] = round(en_paralelo([grande("pdf", pdf, terrenos[1]),
                                                       grande("kmz", kmz, terrenos[2])]), 2)
    finally:
        alto.set()
        for h in hilos:
            h.join()
    # One byte over: declared, and actual body.
    rechazos = {}
    for tipo, maximo in (("pdf", PDF_MAX), ("kmz", KMZ_MAX)):
        st, r = iniciar(ada, terrenos[3], tipo, f"Uno de más.{tipo}", b"x", str(uuid.uuid4()), tamano=maximo + 1)
        rechazos[f"{tipo}_declarado"] = (st, r["detalle"]["code"])
        esperar((st, r["detalle"]["code"]) == (400, "tamano_invalido"), f"{tipo} declarado +1: {st} {r}")
        st, ini = iniciar(ada, terrenos[3], tipo, f"Uno de más.{tipo}", b"x", str(uuid.uuid4()), tamano=1)
        cuerpo = (pdf if tipo == "pdf" else kmz) + b"\0"
        try:
            st, _h, b = ada.pedir("PUT", f"/api/archivos/versiones/{ini['version_id']}/contenido", cuerpo=cuerpo,
                                  cabeceras={"Content-Type": "application/pdf"}, operacion="contenido_mas_uno")
            rechazos[f"{tipo}_cuerpo"] = (st, json.loads(b)["detalle"]["code"] if b else None)
        except (ConnectionError, http.client.HTTPException) as exc:
            # The dispatcher may close before the client finished sending: still a refusal.
            rechazos[f"{tipo}_cuerpo"] = ("conexion_cerrada", type(exc).__name__)
        esperar(rechazos[f"{tipo}_cuerpo"][0] in (413, "conexion_cerrada"), f"{tipo} cuerpo +1: {rechazos}")
        st, r = completar(ada, ini["version_id"])     # nothing staged: never a saved file
        esperar(st == 409 and r["detalle"]["code"] == "contenido_temporal_ausente",
                f"{tipo} +1 completar: {st} {r}")
        st, r = ada.json("POST", f"/api/archivos/versiones/{ini['version_id']}/cancelar")
        esperar(st == 200, f"cancelar +1: {st} {r}")
    resultado["rechazos_mas_uno"] = {k: list(v) for k, v in rechazos.items()}
    return resultado


def fase_reinicio(servidor: Servidor, reg: Registro) -> dict[str, Any]:
    puerto = servidor.puerto
    s = Sesion(puerto, "omar", reg)
    base, terrenos = base_y_terrenos(s)
    t = terrenos[40]
    a, b, c = (pdf_ficticio(f"reinicio-{k}") for k in "abc")
    st, ia = iniciar(s, t, "pdf", "Antes del contenido.pdf", a, str(uuid.uuid4()))
    st, ib = iniciar(s, t, "pdf", "Antes de completar.pdf", b, str(uuid.uuid4()))
    contenido(s, ib["version_id"], "pdf", b)
    hecho_c = subida_completa(s, reg, t, "pdf", c, "Completo antes del reinicio.pdf")
    servidor.detener(signal.SIGKILL)
    servidor.iniciar()
    s = Sesion(puerto, "omar", reg)            # sessions are stored in the database
    st, r = s.json("GET", f"/api/maestra/bases/{base}/terrenos?limit=100")
    fila = next(x for x in r["terrenos"] if x["id"] == t)
    resumen = fila.get("archivos") or {}
    # Two own uploads are still pending (one without content). The server's
    # pdf_total counts live attachments, pending ones included; each recent
    # entry carries its state, and only the completed one may read as saved.
    estados = sorted((x.get("ultima_version") or {}).get("estado") for x in resumen.get("pdf_recientes", []))
    esperar(estados == ["disponible", "subiendo", "subiendo"], f"resumen tras reinicio: {estados}")
    resumen_pdf = {"pdf_total": resumen.get("pdf_total"), "estados_recientes": estados}
    descargar(s, hecho_c["vid"], c, "pdf")
    contenido(s, ia["version_id"], "pdf", a)
    for ini, datos in ((ia, a), (ib, b)):
        st, r = completar(s, ini["version_id"])
        esperar(st == 200 and r["version"]["estado"] == "disponible", f"tras reinicio: {st} {r}")
        reg.guardado(t, ini["archivo_id"], ini["version_id"], "pdf", datos, "omar")
        descargar(s, ini["version_id"], datos, "pdf")
    # A kill in the middle of a large PUT: the version stays pending and the same
    # file can be sent again after the restart.
    grande = pdf_ficticio("corte", 20 * MiB)
    st, ig = iniciar(s, t, "pdf", "Cortado a la mitad.pdf", grande, str(uuid.uuid4()))
    conn = http.client.HTTPConnection("127.0.0.1", puerto, timeout=30)
    conn.putrequest("PUT", f"/api/archivos/versiones/{ig['version_id']}/contenido")
    conn.putheader("Cookie", s.cookie)
    conn.putheader("Content-Type", "application/pdf")
    conn.putheader("Content-Length", str(len(grande)))
    conn.endheaders()
    conn.send(grande[: len(grande) // 2])
    servidor.detener(signal.SIGKILL)
    conn.close()
    servidor.iniciar()
    s = Sesion(puerto, "omar", reg)
    st, r = completar(s, ig["version_id"])
    corte_antes = (st, r["detalle"]["code"] if st != 200 else r["version"]["estado"])
    esperar(st == 409 and r["detalle"]["code"] == "contenido_temporal_ausente",
            f"tras corte a la mitad, completar: {st} {r}")
    st, r = contenido(s, ig["version_id"], "pdf", grande)
    esperar(st == 200, f"reenvío tras corte: {st} {r}")
    st, r = completar(s, ig["version_id"])
    esperar(st == 200 and r["version"]["estado"] == "disponible", f"completar tras reenvío: {st} {r}")
    reg.guardado(t, ig["archivo_id"], ig["version_id"], "pdf", grande, "omar")
    descargar(s, ig["version_id"], grande, "pdf")
    return {"resumen_pdf_tras_reinicio": resumen_pdf, "corte_a_la_mitad_completar": list(corte_antes)}


# ------------------------------------------------------------------ main

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--puerto", type=int, default=8495)
    p.add_argument("--ciclos", type=int, default=20)
    p.add_argument("--ciclos-sesion", type=int, default=4)
    p.add_argument("--fases", default="ciclos,sesiones,grandes,reinicio")
    p.add_argument("--limite-memoria-mb", type=int, default=0,
                   help="address-space cap (prlimit --as) for the server process; 0 = none")
    p.add_argument("--postgres-esquema", help="disposable schema of ARA_MAP_TEST_DATABASE_URL")
    p.add_argument("--semilla", type=int, default=51)
    p.add_argument("--salida")
    args = p.parse_args()
    random.seed(args.semilla)
    fases = args.fases.split(",")
    tmp = Path(tempfile.mkdtemp(prefix="ara-ensayo-"))
    servidor = Servidor(args.puerto, tmp / "instalacion", args.limite_memoria_mb, args.postgres_esquema)
    reg = Registro()
    informe: dict[str, Any] = {"fases": {}, "limite_memoria_mb": args.limite_memoria_mb,
                               "bd": "postgres" if args.postgres_esquema else "sqlite"}
    t0 = time.monotonic()
    try:
        servidor.iniciar()
        for fase in fases:
            t = time.monotonic()
            try:
                if fase == "ciclos":
                    informe["fases"][fase] = fase_ciclos(args.puerto, reg, args.ciclos)
                elif fase == "sesiones":
                    informe["fases"][fase] = [fase_sesiones(args.puerto, reg, n, args.ciclos_sesion)
                                              for n in (2, 5)]
                elif fase == "grandes":
                    informe["fases"][fase] = fase_grandes(args.puerto, reg)
                elif fase == "reinicio":
                    informe["fases"][fase] = fase_reinicio(servidor, reg)
            except FalloError as exc:
                reg.fallo(f"fase {fase}: {exc}")
            except (ConnectionError, OSError, http.client.HTTPException) as exc:
                reg.fallo(f"fase {fase}: {type(exc).__name__}: {exc}")
            print(f"fase {fase}: {time.monotonic() - t:.1f} s, fallos acumulados {len(reg.fallos)}", flush=True)
        try:
            informe["final"] = comprobar_final(Sesion(args.puerto, "ada", reg), reg, servidor.carpeta)
            f = informe["final"]
            if f["objetos_temporales"]:
                reg.fallo(f"quedaron {f['objetos_temporales']} objetos temporales")
            if f["objetos_finales"] != f["versiones_esperadas"]:
                reg.fallo(f"objetos finales {f['objetos_finales']} != versiones {f['versiones_esperadas']}")
        except FalloError as exc:
            reg.fallo(f"comprobación final: {exc}")
    finally:
        servidor.detener()
        informe["duracion_total_s"] = round(time.monotonic() - t0, 1)
        informe["rss_pico_servidor_mib"] = [round(x / MiB, 1) for x in servidor.picos]
        informe["memoria_virtual_pico_servidor_mib"] = [round(x / MiB, 1) for x in servidor.picos_virtuales]
        informe["tiempos"] = reg.resumen()
        informe["conteos"] = dict(reg.conteo)
        informe["fallos"] = reg.fallos
        err = tmp / "servidor.err"
        informe["servidor_stderr_tracebacks"] = err.read_text().count("Traceback") if err.exists() else 0
        if args.salida and err.exists():
            shutil.copy(err, args.salida + ".servidor.err")
        shutil.rmtree(tmp, ignore_errors=True)
        texto = json.dumps(informe, ensure_ascii=False, indent=2)
        if args.salida:
            Path(args.salida).write_text(texto)
        print(texto)
    return 1 if reg.fallos else 0


if __name__ == "__main__":
    sys.exit(main())

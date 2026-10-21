"""A small, real trial of the assistant against Anthropic's API, on fictional data.

Run it from a checkout of the candidate SHA, in the owner's Terminal where
ARA_MAP_CHAT_CLAVE already holds the key (it is read from the environment
only; never pass it as an argument):

    export ARA_MAP_CHAT_CLAVE
    python3 scripts/ensayo_claude.py

What it does, all in a temporary folder that is deleted at the end:

  * a throwaway SQLite database and the real local server on 127.0.0.1;
    every hosted-database variable is removed from this process first, so it
    can never touch Render, Neon or Supabase;
  * a fictional administrator and fictional terrains;
  * a free check of the model with the Models API (exists for this key, and
    accepts thinking: disabled) before anything is billed;
  * then, through the real HTTP routes and the real Anthropic adapter: a
    search with a strict bound, the next page (which must not call the model),
    a search that needs a clarification, a comparison of three terrains and
    one question about one terrain.

Spending: ARA_MAP_CHAT_LIMITE_MENSUAL_USD is set to 1 for this temporary
database, so the app's own reservation refuses any call that could take the
trial past US$1; the script also stops if the ledger passes US$0.90. Nothing
is retried automatically.

It prints, per step, whether it worked, the HTTP status and code, the
criteria the server built, and at the end the usage ledger (tokens, cost),
the model and the SHA. It never prints the key, the prompts or the model's
answers.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODELO = os.environ.get("ARA_MAP_CHAT_MODELO") or "claude-haiku-5-5"
TOPE_USD = 1.0
ALTO_USD = 0.90
VERSION_API = "2023-06-01"


def salir(mensaje: str, codigo: int) -> None:
    print(mensaje)
    sys.exit(codigo)


def sha() -> str:
    """The checkout's commit, flagged when it has local changes (then it is not that SHA)."""
    try:
        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                  check=True).stdout.strip()
        cambios = git("status", "--porcelain", "--untracked-files=no")
        return git("rev-parse", "HEAD") + (" (con cambios locales: no es ese SHA)" if cambios else "")
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


def revisar_modelo(clave: str) -> None:
    """The Models API: free. Stops before any billed call if the model is not
    available to this key or does not take thinking: disabled."""
    peticion = urllib.request.Request(
        f"https://api.anthropic.com/v1/models/{MODELO}",
        headers={"x-api-key": clave, "anthropic-version": VERSION_API})
    try:
        with urllib.request.urlopen(peticion, timeout=20) as respuesta:  # noqa: S310 - fixed https URL
            datos = json.loads(respuesta.read())
    except urllib.error.HTTPError as error:
        salir(f"Modelo: la API respondió HTTP {error.code} para {MODELO}. No se gastó nada. "
              "401: clave inválida; 403/404: la cuenta no tiene ese modelo.", 2)
    except (urllib.error.URLError, OSError) as error:
        motivo = type(getattr(error, "reason", error)).__name__
        salir(f"Modelo: no se pudo conectar con la API ({motivo}). No se gastó nada.", 2)
    disabled = (((datos.get("capabilities") or {}).get("thinking") or {}).get("types") or {}).get("disabled")
    soporta = disabled.get("supported") if isinstance(disabled, dict) else None
    print(f"Modelo: {datos.get('id')} disponible para esta clave; thinking disabled admitido: {soporta}")
    if soporta is False:
        salir("El modelo no admite thinking: disabled. No se gastó nada; hay que elegir otro modelo.", 2)


class Registro(logging.Handler):
    """Keeps the adapter's warnings (an HTTP status or an error class, never content)."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.mensajes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensajes.append(record.getMessage())


def main() -> None:
    clave = os.environ.get("ARA_MAP_CHAT_CLAVE", "").strip()
    if not clave:
        salir("Falta ARA_MAP_CHAT_CLAVE en esta Terminal. Ejecuta antes: export ARA_MAP_CHAT_CLAVE", 2)
    carpeta = tempfile.TemporaryDirectory(prefix="ara-ensayo-claude-")
    for variable in ("ARA_MAP_DATABASE_URL", "DATABASE_URL", "ARA_MAP_READ_ONLY", "ARA_MAP_ARCHIVOS",
                     "ARA_MAP_TEST_DATABASE_URL"):
        os.environ.pop(variable, None)
    os.environ.update({
        "ARA_MAP_DB": str(Path(carpeta.name) / "ensayo.db"),
        "ARA_MAP_CHAT_HABILITADO": "1", "ARA_MAP_CHAT_MODELO": MODELO,
        "ARA_MAP_CHAT_COSTO_ENTRADA_USD_MTOK": "0.10", "ARA_MAP_CHAT_COSTO_SALIDA_USD_MTOK": "0.50",
        "ARA_MAP_CHAT_LIMITE_MENSUAL_USD": str(TOPE_USD), "ARA_MAP_CHAT_MAX_POR_HORA": "20",
    })
    print(f"SHA: {sha()}")
    print(f"Base de datos desechable en una carpeta temporal; tope del ensayo: US${TOPE_USD:.2f}")
    revisar_modelo(clave)

    from server import app, auth, db
    from server.asistente import terreno
    registro = Registro()
    logging.getLogger("ara.asistente_terreno").addHandler(registro)
    db.connect().close()
    contrasena = secrets.token_urlsafe(24)
    with db.escritura() as conn:
        auth.create_user(conn, "ensayo_admin", "Administración Ficticia", contrasena, rol="admin")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    raiz = f"http://127.0.0.1:{httpd.server_address[1]}"
    cookie = ""

    def llamar(metodo: str, ruta: str, cuerpo: Any = None, cabeceras: dict[str, str] | None = None
               ) -> tuple[int, Any]:
        nonlocal cookie
        peticion = urllib.request.Request(
            raiz + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
            headers={"Content-Type": "application/json", "Cookie": cookie, **(cabeceras or {})})
        try:
            with urllib.request.urlopen(peticion, timeout=60) as respuesta:  # noqa: S310 - loopback
                if respuesta.headers.get("Set-Cookie"):
                    cookie = respuesta.headers["Set-Cookie"].split(";")[0]
                return respuesta.status, json.loads(respuesta.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read() or b"{}")

    llamar("POST", "/api/login", {"username": "ensayo_admin", "password": contrasena})
    base = llamar("POST", "/api/maestra/bases", {"nombre": "Base Ficticia del Ensayo"})[1]["base"]["id"]

    def crear(n: int, en_base: bool = False, **campos: Any) -> str:
        ruta = f"/api/maestra/bases/{base}/terrenos" if en_base else "/api/inventario/terrenos"
        datos = {"terreno": f"Lote Ensayo {n:02d} Ficticio", "estado": "Jalisco", "municipio": "Zapopan",
                 "tipo_terreno": "Industrial", **campos}
        return llamar("POST", ruta, datos, {"Idempotency-Key": f"ensayo-{secrets.token_hex(8)}"})[1]["terreno"]["id"]

    # 14 match «industrial, Jalisco, more than 10,000 m²»: 8 without a base and 6 in one.
    coinciden = [crear(n, en_base=n >= 8, superficie_m2=10500 + n * 500,
                       asking_price=1_000_000 + n * 50_000 if n < 3 else None,
                       moneda="MXN" if n < 3 else None, availability="available" if n == 0 else "unknown")
                 for n in range(14)]
    crear(20, superficie_m2=10000)                       # exactly the bound: not «more than»
    crear(21, superficie_m2=9000)
    crear(22, estado="Colima", superficie_m2=30000)
    crear(23, tipo_terreno="Agrícola", superficie_m2=30000)

    def gastado() -> tuple[int, float]:
        with db.session() as conn:
            fila = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(costo_usd), 0) AS c FROM uso_ia").fetchone()
        return int(fila["n"]), float(fila["c"])

    resultados: list[dict[str, Any]] = []

    def paso(nombre: str, status: int, cuerpo: Any, correcto: bool, extra: str = "") -> None:
        codigo = (cuerpo.get("detalle") or {}).get("code") if isinstance(cuerpo, dict) else None
        resultados.append({"paso": nombre, "ok": correcto, "status": status, "codigo": codigo})
        print(f"{'OK   ' if correcto else 'FALLO'} {nombre}: HTTP {status}"
              + (f", código {codigo}" if codigo else "") + (f". {extra}" if extra else ""))
        if gastado()[1] > ALTO_USD:
            salir(f"Se detiene: el registro de uso pasó US${ALTO_USD:.2f}.", 1)

    # 1. Search with a strict bound.
    status, b = llamar("POST", "/api/asistente-terreno/buscar",
                       {"pregunta": "Busca terrenos industriales en Jalisco de más de 10,000 m²"})
    criterios = [c["texto"] for c in b.get("criterios", [])] if isinstance(b, dict) else []
    ok = (status == 200 and b.get("estado") == "resultados" and b.get("total") == len(coinciden)
          and b.get("filtros", {}).get("superficie_m2_mayor_que") == 10000)
    paso("Búsqueda con límite estricto", status, b, ok,
         f"estado={b.get('estado')}, total={b.get('total')} (esperado {len(coinciden)}), criterios={criterios}")

    # 2. Next page: the model must not be called again.
    if status == 200 and b.get("next_cursor"):
        antes = gastado()[0]
        s2, p2 = llamar("POST", "/api/asistente-terreno/resultados",
                        {"filtros": b["filtros"], "cursor": b["next_cursor"]})
        vistos = {t["terreno_id"] for t in b["terrenos"]} | {t["terreno_id"] for t in p2.get("terrenos", [])}
        paso("Página siguiente sin llamar al modelo", s2, p2,
             s2 == 200 and gastado()[0] == antes and vistos == set(coinciden),
             f"llamadas nuevas al modelo: {gastado()[0] - antes}; coincidencias vistas: {len(vistos)}")
    else:
        paso("Página siguiente sin llamar al modelo", status, b, False, "no hubo primera página con cursor")

    # 3. A condition the system cannot run: a clarification, never a list.
    s3, c3 = llamar("POST", "/api/asistente-terreno/buscar",
                    {"pregunta": "Terrenos industriales en Jalisco cerca de la playa"})
    paso("Condición no admitida pide aclaración", s3, c3,
         s3 == 200 and c3.get("estado") == "aclaracion" and "terrenos" not in c3,
         f"estado={c3.get('estado')}, origen={c3.get('origen')}")

    # 4. Compare three.
    s4, c4 = llamar("POST", "/api/asistente-terreno/comparar",
                    {"terrenos": [{"id": i, "version": 1} for i in coinciden[:3]]})
    resumen = c4.get("resumen", {}) if isinstance(c4, dict) else {}
    paso("Comparar tres terrenos", s4, c4, s4 == 200 and resumen.get("estado") == "ok",
         f"resumen={resumen.get('estado')}" + (f" ({resumen.get('code')})" if resumen.get("code") else "")
         + f", filas={len(c4.get('filas', []))}")

    # 5. One question about one terrain.
    s5, c5 = llamar("POST", f"/api/asistente-terreno/{coinciden[0]}/consultar",
                    {"accion": "pregunta", "pregunta": "¿Qué superficie y precio tiene registrados?"})
    paso("Pregunta sobre un terreno", s5, c5, s5 == 200 and c5.get("origen") == "modelo",
         f"origen={c5.get('origen')}")

    httpd.shutdown()
    httpd.server_close()
    with db.session() as conn:
        filas = [dict(r) for r in conn.execute(
            "SELECT estado, modelo, tokens_entrada, tokens_salida, costo_usd FROM uso_ia ORDER BY id").fetchall()]
    n, costo = gastado()
    print("\nUso registrado por la app (Anthropic factura lo que informa; esto es la contabilidad de ARA):")
    for f in filas:
        print(f"  {f['estado']:<22} {f['modelo']}  entrada={f['tokens_entrada']}  salida={f['tokens_salida']}"
              f"  US${float(f['costo_usd']):.6f}")
    print(f"  Total: {n} llamadas, US${costo:.6f} (tope del ensayo US${TOPE_USD:.2f})")
    if registro.mensajes:
        print("Avisos del adaptador (sin contenido): " + "; ".join(sorted(set(registro.mensajes))))
    aprobados = sum(1 for r in resultados if r["ok"])
    # Only the script's own test injects a provider; then nothing here was Claude.
    quien = "PROVEEDOR SIMULADO (prueba del script), no Claude" if terreno._proveedor_prueba else "Claude real"
    print(f"\nResultado: {aprobados}/{len(resultados)} pasos correctos con {quien}, modelo {MODELO}, SHA {sha()}.")
    carpeta.cleanup()
    sys.exit(0 if aprobados == len(resultados) else 1)


if __name__ == "__main__":
    main()

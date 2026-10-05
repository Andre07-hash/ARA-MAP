"""Remove exactly the smoke-test records listed in smoke_ledger.json, then verify.

Usage: cleanup.py ENV_FILE [BASE_URL]. Never prints the password.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = (sys.argv[2] if len(sys.argv) > 2 else "https://ara-map-ivory.vercel.app").rstrip("/") + "/api"
ETIQUETA = "SMOKE 2026-09-25"
AQUI = Path(__file__).parent
cookie = None
fallas = []


def leer_env(ruta, clave):
    for linea in Path(ruta).read_text().splitlines():
        k, _, v = linea.partition("=")
        if k.strip().removeprefix("export ").strip() == clave:
            return v.strip().strip('"').strip("'")
    return None


def llamar(metodo, ruta, cuerpo=None, sesion=True):
    h = {"Content-Type": "application/json"}
    if sesion and cookie:
        h["Cookie"] = cookie
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=h),
                                    timeout=60) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def check(nombre, condicion):
    print(("  PASS  " if condicion else "  FAIL  ") + nombre)
    if not condicion:
        fallas.append(nombre)


def estado_publico():
    salida = {}
    for ruta, clave in (("/bases", "bases"), ("/mapas", "mapas"),
                        ("/carpetas?tipo=bases", "carpetas"), ("/carpetas?tipo=mapas", "carpetas")):
        s, cuerpo, _ = llamar("GET", ruta, sesion=False)
        assert s == 200, (ruta, s)
        for item in cuerpo[clave]:
            salida[f"{ruta.split('?')[0]}#{item['id']}"] = item
    return salida


ledger = json.loads((AQUI / "smoke_ledger.json").read_text())
linea_base = json.loads((AQUI / "smoke_baseline.json").read_text())
print("Ledger:", ledger)

s, _, h = llamar("POST", "/login", {"password": leer_env(sys.argv[1], "ARA_MAP_EDIT_PASSWORD")}, sesion=False)
cookie = (h.get("Set-Cookie") or "").split(";", 1)[0]
assert s == 200 and cookie.startswith("ara_editor="), "login failed"

# Maps first (they reference bases), then bases, folders, remembered formats.
for mapa_id in reversed(ledger["mapas"]):
    s, _, _ = llamar("DELETE", f"/mapas/{mapa_id}")
    check(f"deleted smoke map {mapa_id}", s == 200 and llamar("GET", f"/mapas/{mapa_id}", sesion=False)[0] == 404)
for base_id in ledger["bases"]:
    s, _, _ = llamar("DELETE", f"/bases/{base_id}")
    check(f"deleted smoke base {base_id}", s == 200 and llamar("GET", f"/bases/{base_id}", sesion=False)[0] == 404)
for carpeta_id in ledger["carpetas"]:
    s, r, _ = llamar("DELETE", f"/carpetas/{carpeta_id}")
    check(f"deleted smoke folder {carpeta_id} (held nothing else)", s == 200 and r["trasladados"] == 0)
for formato_id in ledger["formatos"]:
    s, _, _ = llamar("DELETE", f"/formatos/{formato_id}")
    _, lista, _ = llamar("GET", "/formatos")
    check(f"deleted smoke format {formato_id}",
          s == 200 and all(f["id"] != formato_id for f in lista["formatos"]))

despues = estado_publico()
check("no record labeled SMOKE remains",
      not any(ETIQUETA in json.dumps(v, ensure_ascii=False) for v in despues.values()))
check(f"all {len(linea_base)} pre-existing records still present and unchanged", despues == linea_base)
for clave, antes in linea_base.items():
    if clave.startswith("/mapas#"):
        s, det, _ = llamar("GET", f"/mapas/{antes['id']}/terrenos", sesion=False)
        check(f"pre-existing map «{antes['nombre']}» opens ({len(det['terrenos']) if s == 200 else s} terrains)",
              s == 200)
    if clave.startswith("/bases#"):
        s, det, _ = llamar("GET", f"/bases/{antes['id']}/terrenos", sesion=False)
        check(f"pre-existing base «{antes['nombre']}» opens", s == 200)

llamar("POST", "/logout", {})
print("\nCLEANUP OK" if not fallas else f"\nCLEANUP PROBLEMS: {fallas}")
sys.exit(1 if fallas else 0)

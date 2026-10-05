"""Production smoke test for the import assistant release. Fictional, labeled data only.

Every created id goes into smoke_ledger.json so cleanup removes exactly those.
Stops at the first failed check.
"""

import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from openpyxl import load_workbook

BASE = (sys.argv[2] if len(sys.argv) > 2 else "https://ara-map-ivory.vercel.app").rstrip("/") + "/api"
ETIQUETA = "SMOKE 2026-09-25"
LEDGER = Path(__file__).with_name("smoke_ledger.json")
ledger = {"bases": [], "mapas": [], "carpetas": [], "formatos": []}
cookie = None
resultados = []


def guardar():
    LEDGER.write_text(json.dumps(ledger, indent=2))


def llamar(metodo, ruta, cuerpo=None, crudo=None, cabeceras=None, sesion=True):
    datos = crudo if crudo is not None else (json.dumps(cuerpo).encode() if cuerpo is not None else None)
    h = {"Content-Type": "application/octet-stream" if crudo is not None else "application/json", **(cabeceras or {})}
    if sesion and cookie:
        h["Cookie"] = cookie
    peticion = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(peticion, timeout=60) as r:
            cuerpo_r = r.read()
            tipo = r.headers.get("Content-Type", "")
            return r.status, (json.loads(cuerpo_r) if "json" in tipo else cuerpo_r), dict(r.headers)
    except urllib.error.HTTPError as e:
        cuerpo_r = e.read()
        try:
            return e.code, json.loads(cuerpo_r), dict(e.headers)
        except ValueError:
            return e.code, cuerpo_r, dict(e.headers)


def check(nombre, condicion, detalle=""):
    resultados.append((nombre, bool(condicion)))
    print(("  PASS  " if condicion else "  FAIL  ") + nombre + (f" — {detalle}" if detalle and not condicion else ""))
    if not condicion:
        guardar()
        print("\nSTOPPED at first failure. Ledger:", ledger)
        sys.exit(1)


def analizar(nombre, csv_texto, base_id=None):
    q = f"?base_id={base_id}" if base_id else ""
    return llamar("POST", f"/importar/analizar{q}", crudo=csv_texto.encode("utf-8"),
                  cabeceras={"X-Archivo": quote(nombre)})


def filas(prefijo, cabecera, n=4, precio="Asking Price"):
    lineas = [cabecera]
    datos = [("Jalisco", "Tala", 25000, 20.653, -103.701), ("Nuevo León", "Apodaca", 12000, 25.781, -100.188),
             ("Querétaro", "El Marqués", 60000, 20.627, -100.271), ("Estado de México", "Tecámac", 40000, 19.713, -98.968)]
    for i in range(n):
        e, m, s, la, lo = datos[i]
        lineas.append(f"{ETIQUETA} {prefijo} {i + 1},{e},{m},{s},{s * (500 + i)},{la},{lo}")
    return "\n".join(lineas) + "\n"


# ---------------------------------------------------------------- baseline
def estado_publico():
    """Every pre-existing record as viewers see it, keyed by id."""
    salida = {}
    for ruta, clave in (("/bases", "bases"), ("/mapas", "mapas"),
                        ("/carpetas?tipo=bases", "carpetas"), ("/carpetas?tipo=mapas", "carpetas")):
        s, cuerpo, _ = llamar("GET", ruta, sesion=False)
        assert s == 200, (ruta, s)
        for item in cuerpo[clave]:
            salida[f"{ruta.split('?')[0]}#{item['id']}"] = item
    return salida


LINEA_BASE = Path(__file__).with_name("smoke_baseline.json")
linea_base = estado_publico()
LINEA_BASE.write_text(json.dumps(linea_base, indent=2, ensure_ascii=False))
print(f"Baseline: {len(linea_base)} pre-existing records (bases, maps, folders)")

# ------------------------------------------------------------ viewer access
s, cfg, _ = llamar("GET", "/config", sesion=False)
check("viewer: config reports read-only, cloud, auth required",
      s == 200 and cfg["readOnly"] and cfg["cloud"] and cfg["authRequired"])
check("viewer: anonymous analyze refused", analizar("x.csv", "Terreno\nA\n")[0] == 401)
check("viewer: anonymous format listing refused", llamar("GET", "/formatos", sesion=False)[0] == 401)
check("viewer: anonymous folder creation refused",
      llamar("POST", "/carpetas", {"tipo": "bases", "nombre": "x"}, sesion=False)[0] == 401)
check("viewer: can still read bases", llamar("GET", "/bases", sesion=False)[0] == 200)

# ----------------------------------------------------------------- login
def leer_env(ruta, clave):
    for linea in Path(ruta).read_text().splitlines():
        k, _, v = linea.partition("=")
        if k.strip().removeprefix("export ").strip() == clave:
            return v.strip().strip('"').strip("'")
    return None


password = leer_env(sys.argv[1], "ARA_MAP_EDIT_PASSWORD")  # never printed
s, _, h = llamar("POST", "/login", {"password": password}, sesion=False)
cookie = (h.get("Set-Cookie") or "").split(";", 1)[0]
check("editor: login", s == 200 and cookie.startswith("ara_editor="))
s, cfg, _ = llamar("GET", "/config")
check("editor: config reports editable", s == 200 and not cfg["readOnly"])

# ------------------------------------------------ familiar CSV import (A)
s, r, _ = analizar("smoke-familiar.csv",
                   filas("Norte", "Terreno,Estado,Municipio,Superficie m2,Asking Price,X,Y"))
check("familiar: straight to preview, no AI needed",
      s == 200 and r["estado"] == "vista_previa" and r["interpretacion"]["automatico"]["estado"] == "no_necesario",
      json.dumps(r)[:300])
check("familiar: 4 terrains, all on the map", (r["vista_previa"]["conteo"], r["vista_previa"]["ubicados"]) == (4, 4))
s, c, _ = llamar("POST", "/importar/confirmar", {"token": r["vista_previa"]["token"],
                                                  "nombre": f"{ETIQUETA} Familiar", "recordar_formato": False})
check("familiar: imported", s == 200 and c["base"]["conteo"] == 4, str(c)[:200])
base_a = c["base"]["id"]
ledger["bases"].append(base_a)
guardar()

# ------------------------------- ambiguous header: question + correction (B)
s, r, _ = analizar("smoke-ambiguo.csv", filas("Sur", "Terreno,Estado,Municipio,Superficie m2,Valor,Latitud,Longitud"))
check("ambiguous: exactly one question", s == 200 and r["estado"] == "preguntas" and len(r["preguntas"]) == 1,
      json.dumps(r)[:300])
p = r["preguntas"][0]
opcion = next(o["indice"] for o in p["opciones"] if o["etiqueta"] == "Precio total (MXN)")
s, r, _ = llamar("POST", "/importar/preparar", {"borrador": r["borrador"], "revision": r["revision"],
                                                 "respuestas": [{"pregunta": p["id"], "opcion": opcion}]})
check("ambiguous: answered → preview with prices", s == 200 and r["estado"] == "vista_previa"
      and r["vista_previa"]["con_precio"] == 4, str(r)[:300])
municipio = next(col["id"] for col in r["interpretacion"]["columnas"] if col["visible"] == "Municipio")
revision_antes = r["revision"]
s, r, _ = llamar("POST", "/importar/preparar", {"borrador": r["borrador"], "revision": r["revision"],
                                                 "correcciones": {"columnas": {municipio: "extra"}}})
check("ambiguous: correction applied as a new revision",
      s == 200 and r["revision"] > revision_antes and r["vista_previa"]["filas"][0]["municipio"] is None)
s, r, _ = llamar("POST", "/importar/preparar", {"borrador": r["borrador"], "revision": r["revision"],
                                                 "correcciones": {"columnas": {municipio: "municipio"}}})
check("ambiguous: correction reverted", s == 200 and r["vista_previa"]["filas"][0]["municipio"] == "Tala")
s, c, _ = llamar("POST", "/importar/confirmar", {"token": r["vista_previa"]["token"],
                                                  "nombre": f"{ETIQUETA} Ambiguo", "recordar_formato": True})
check("ambiguous: imported and format remembered",
      s == 200 and c["base"]["conteo"] == 4 and c.get("formato", {}).get("accion") == "nuevo", str(c)[:200])
base_b = c["base"]["id"]
ledger["bases"].append(base_b)
ledger["formatos"].append(c["formato"]["id"])
guardar()

# --------------------------------------------------- AI disabled in production
s, r, _ = analizar("smoke-desconocido.csv",
                   "Desarrollo,Edo.,Mpio.,Sup. aprox (m2),Precio pedido MXN,Lat. dec,Lon. dec\n"
                   f"{ETIQUETA} Gama,Jalisco,Tala,25000,12500000,20.653,-103.701\n")
check("AI disabled: unfamiliar file falls back to focused questions",
      s == 200 and r["interpretacion"]["automatico"]["estado"] == "no_configurado"
      and r["estado"] == "preguntas" and r["preguntas"][0]["id"] == "campo:terreno", str(r)[:300])

# ------------------------------------------------------------------ folders
s, f, _ = llamar("POST", "/carpetas", {"tipo": "bases", "nombre": f"{ETIQUETA} Carpeta"})
check("folders: created", s == 200)
ledger["carpetas"].append(f["carpeta"]["id"])
guardar()
s, m, _ = llamar("PATCH", f"/bases/{base_a}/carpeta", {"carpeta_id": f["carpeta"]["id"]})
check("folders: base moved in", s == 200 and m["base"]["carpeta_id"] == f["carpeta"]["id"])
s, lst, _ = llamar("GET", "/carpetas?tipo=bases")
check("folders: listing counts it",
      s == 200 and next(c for c in lst["carpetas"] if c["id"] == f["carpeta"]["id"])["conteo"] == 1)

# ------------------------------------------------------ save & reopen maps
mapas = []
for base_id, nombre in ((base_a, "Mapa Norte"), (base_b, "Mapa Sur")):
    s, mp, _ = llamar("POST", "/mapas", {"nombre": f"{ETIQUETA} {nombre}", "tipo": "simple",
                                         "capas": [{"base_id": base_id, "color": "#2a78d6"}]})
    check(f"maps: saved {nombre}", s == 200 and mp["mapa"]["conteo"] == 4, str(mp)[:200])
    ledger["mapas"].append(mp["mapa"]["id"])
    guardar()
    mapas.append(mp["mapa"]["id"])
    s, det, _ = llamar("GET", f"/mapas/{mp['mapa']['id']}/terrenos")
    check(f"maps: reopened {nombre}", s == 200 and len(det["terrenos"]) == 4)

# --------------------- merge two DISTINCT saved maps with EQUAL terrain counts
s, plan, _ = llamar("POST", "/mapas/combinar/vista-previa", {"mapa_ids": mapas})
check("merge fix: plan keeps both equal-count layers", s == 200 and plan["total"] == 2 and not plan["duplicadas"],
      str(plan)[:300])
s, mg, _ = llamar("POST", "/mapas/combinar", {"nombre": f"{ETIQUETA} Comparación", "mapa_ids": mapas,
                                                "colores": ["#2a78d6", "#eb6834"]})
check("merge fix: comparison created with 2 layers", s == 200 and len(mg["mapa"]["capas"]) == 2, str(mg)[:300])
ledger["mapas"].append(mg["mapa"]["id"])
guardar()
s, det, _ = llamar("GET", f"/mapas/{mg['mapa']['id']}/terrenos")
por_capa = {}
for t in det["terrenos"]:
    por_capa.setdefault(t["capa"], []).append(t["terreno"])
check("merge fix: both layers keep their own data",
      sorted(len(v) for v in por_capa.values()) == [4, 4]
      and all(n.startswith(f"{ETIQUETA} Norte") for n in por_capa[0])
      and all(n.startswith(f"{ETIQUETA} Sur") for n in por_capa[1]))

# ----------------------------------------------------------- Excel export
s, xlsx, h = llamar("POST", "/exportar", {"mapa_id": mg["mapa"]["id"], "nombre": "smoke"})
libro = load_workbook(io.BytesIO(xlsx)) if s == 200 else None
check("export: comparison has one sheet per source",
      s == 200 and len(libro.sheetnames) == 2 and all(libro[n].max_row == 5 for n in libro.sheetnames),
      f"status {s}")
s, _, _ = llamar("POST", "/exportar", {"mapa_id": mg["mapa"]["id"], "nombre": "smoke"}, sesion=False)
check("export: viewers can export too", s == 200)

# ---------------------------------------------------------------- append
s, r, _ = analizar("smoke-agregar.csv", filas("Norte", "Terreno,Estado,Municipio,Superficie m2,Asking Price,X,Y")
                   + f"{ETIQUETA} Norte 5,Sonora,Hermosillo,5000,2500000,29.07,-110.96\n", base_id=base_a)
check("append: preview classifies 1 new, 4 duplicates",
      s == 200 and r["estado"] == "vista_previa"
      and (r["vista_previa"]["clasificacion"]["nuevas"], r["vista_previa"]["clasificacion"]["duplicadas"]) == (1, 4),
      str(r)[:300])
s, ap, _ = llamar("POST", f"/bases/{base_a}/adjuntar", {"token": r["vista_previa"]["token"], "recordar_formato": False})
check("append: 1 added, base now 5", s == 200 and ap["agregados"] == 1 and ap["base"]["conteo"] == 5, str(ap)[:200])
s, det, _ = llamar("GET", f"/mapas/{mapas[0]}")
check("append: saved map stays a snapshot (still 4)", s == 200 and det["mapa"]["conteo"] == 4)

print(f"\nAll {len(resultados)} checks passed. Ledger: {ledger}")

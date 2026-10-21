"""Disposable probe of the application baseline. Not application code.

Answers, against a temporary SQLite file and fictional values only: what the
existing inventory already does for a master record (blank creation, partial
entry, conflicts, history) and where it contradicts the master plan.

    python3 reports/team-a-master-table-prep-2026-10-07/experiment/baseline_probe.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.pop("ARA_MAP_DATABASE_URL", None)
os.environ["ARA_MAP_DB"] = str(Path(tempfile.mkdtemp()) / "probe.db")

from server import auth, db, inventario  # noqa: E402
from server.repo import inventario as repo  # noqa: E402


def intento(campos, base=None):
    limpio, errores = inventario.clean_changes(campos)
    errores.update(inventario.check_merged(limpio, {**(base or inventario.empty_draft()), **limpio}))
    return limpio, errores


with db.session() as conn:
    ana = auth.create_user(conn, "ana.ficticia", "Ana Ficticia", "clave-ficticia-123", iterations=1)
    actor = {"id": ana["id"], "display_name": ana["display_name"]}

    print("1. Blank record")
    limpio, errores = intento({})
    print("   validation errors:", errores)
    t = repo.create(conn, limpio, actor, "probe-key-0001", "h0")["terreno"]
    print("   created id is a uuid:", len(t["id"]) == 36, "| version:", t["version"])
    print("   name:", t["draft"]["terreno"], "| moneda:", t["draft"]["moneda"])
    print("   attention codes on a blank record:", [a["code"] for a in t["attention"]])

    print("2. Price typed without a currency")
    print("   errors:", intento({"asking_price": 1500000})[1])
    print("   with moneda=MXN:", intento({"asking_price": 1500000, "moneda": "MXN"})[1])

    print("3. Partial and odd values")
    print("   only X (lat) given:", intento({"lat": 20.6})[1])
    print("   negative area:", intento({"superficie_m2": -5})[1])
    print("   text in a number cell:", intento({"superficie_m2": "SD"})[1])
    print("   unknown core field tipo_terreno:", intento({"tipo_terreno": "Industrial"})[1])
    print("   unknown core field comentarios:", intento({"comentarios": "x"})[1])

    print("4. Compare-and-set and history")
    t2 = repo.update(conn, t["id"], 1, {"municipio": "Ficticia"}, (), actor)
    print("   version after one cell edit:", t2["version"])
    try:
        repo.update(conn, t["id"], 1, {"estado": "Ficticio"}, (), actor)
    except repo.ConflictError:
        print("   stale expected_version -> ConflictError")
    eventos, total, _ = repo.history(conn, t["id"], None, 10)
    print("   events:", [(e["version"], e["action"], list(e["changes"])) for e in eventos])

    print("5. Roles")
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(team_user)").fetchall()]
    print("   team_user columns:", cols)
    print("   session user payload keys:", sorted(actor))

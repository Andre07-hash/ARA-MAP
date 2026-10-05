"""Reproduce this incident without a database, uploads or source edits.

Run from any directory using a Python environment with openpyxl installed.
The output describes pre-fix behavior; it is not the post-fix acceptance suite.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.asistente.detectar import interpretar
from server.asistente.plan import construir
from server.asistente.rejilla import leer
from server.importer import read_workbook

PACKET = Path(__file__).resolve().parent
saved = json.loads((PACKET / "evidence/observed-format-4-reconstruction.json").read_text())
xlsx = ROOT / "Base Terrenos 09.26 copy.xlsx"
csv = Path("/Users/andrejasso/Desktop/Base Terrenos 09.26 copy.csv")

def counts(result):
    return {
        "terrains": len(result.records), "located": result.ubicados,
        "total_prices": sum(r.asking_price is not None for r in result.records),
        "unit_prices": sum(r.asking_m2 is not None for r in result.records),
    }

print(json.dumps({"case": "legacy_xlsx", **counts(read_workbook(xlsx))}))
for label, file, formats in [
    ("assistant_xlsx_clean", xlsx, []),
    ("assistant_xlsx_saved_format_4", xlsx, [saved]),
    ("assistant_csv_clean", csv, []),
]:
    grid = leer(file.read_bytes(), file.name)
    interpretation = interpretar(grid, {}, formats)
    plan = interpretation.plan()
    if plan is None:
        print(json.dumps({"case": label, "questions": [q.texto for q in interpretation.preguntas]}, ensure_ascii=False))
        continue
    result = construir(plan, grid).resultado
    print(json.dumps({"case": label, **counts(result)}, ensure_ascii=False))

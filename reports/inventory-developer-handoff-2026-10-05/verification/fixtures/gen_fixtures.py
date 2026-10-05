#!/usr/bin/env python3
"""Deterministic FICTIONAL fixtures for ARA Map inventory verification.

Stdlib only. Same seed -> byte-identical output and the same fixture hash.

Outputs (default: ./out next to this file):
  master_120.json   120 master terrains (100 intended-published available,
                    10 drafts, 10 intended-unpublished) in contract-v1 draft shape
  matching_251.json 251 publishable records sharing one municipality, to cross
                    the 250-row page boundary
  users.json        three fictional team identities (+ one never-provisioned
                    identity used for signup / enumeration probes)
  sentinels.txt     every private sentinel string, one per line
  manifest.json     stable keys, expected values/outcomes, counts, fixture hash

Every confidential value carries a unique sentinel "SNTL-<KIND>-<KEY>-<hex6>".
Public fields carry positive markers "PUBMARK-<KEY>" instead, so a scan that
finds no sentinels can be shown to have looked at real public data.

Private draft field NAMES are not frozen by contract v1. Records use the
logical names `contacts`, `internal_notes`, `extra`, `price_confirmed_at`,
`availability_confirmed_at`; ../field_map.json maps them to the backend's real
names at request time (see stage1/aralib.py).

Usage: python3 gen_fixtures.py [--seed 20261005] [--out DIR] [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

DEFAULT_SEED = 20261005
SENTINEL_RE = r"(?i)sntl-[a-z]+-[a-z0-9]+-[0-9a-f]{6}"

# (estado, municipio, lat, lon) -- approximate, all inside server/validation.py
# MEXICO_LAT/MEXICO_LON bounds.
PLACES = [
    ("Querétaro", "Querétaro", 20.5888, -100.3899),
    ("Querétaro", "El Marqués", 20.6200, -100.2700),
    ("Querétaro", "Corregidora", 20.5400, -100.4400),
    ("Nuevo León", "Monterrey", 25.6866, -100.3161),
    ("Nuevo León", "Apodaca", 25.7800, -100.1900),
    ("Nuevo León", "Santa Catarina", 25.6700, -100.4600),
    ("Jalisco", "Guadalajara", 20.6597, -103.3496),
    ("Jalisco", "Zapopan", 20.7200, -103.3900),
    ("Jalisco", "Tlajomulco de Zúñiga", 20.4700, -103.4400),
    ("Guanajuato", "León", 21.1250, -101.6860),
    ("Guanajuato", "Silao de la Victoria", 20.9400, -101.4300),
    ("Guanajuato", "Celaya", 20.5200, -100.8100),
    ("San Luis Potosí", "San Luis Potosí", 22.1565, -100.9855),
    ("San Luis Potosí", "Soledad de Graciano Sánchez", 22.1800, -100.9400),
    ("Yucatán", "Mérida", 20.9674, -89.5926),
    ("Estado de México", "Cuautitlán Izcalli", 19.6469, -99.2464),
    ("Estado de México", "Tepotzotlán", 19.7100, -99.2200),
    ("Coahuila", "Ramos Arizpe", 25.5400, -100.9500),
    ("Coahuila", "Saltillo", 25.4200, -101.0000),
    ("Puebla", "San José Chiapa", 19.2300, -97.7600),
    ("Baja California", "Tijuana", 32.5149, -117.0382),
    ("Quintana Roo", "Benito Juárez", 21.1600, -86.8500),
]

NAME_STEMS = [
    "Parque Industrial El Ñandú", "Rancho San José de Gracia", "Lote Ávila Camacho",
    "Terreno Peña Blanca", "Bodega Ex-Hacienda Álamos", "Fracción Güémez",
    "Predio Los Cañones", "Nave Logística Ébano", "Polígono Santa Mónica",
    "Ejido La Purísima", "Macrolote Río Bravo", "Reserva Cerro Azul",
]

# Literal strings that must survive storage and rendering unchanged.
HTML_LITERALS = {
    "M020": ("terreno", "<b>Terreno Negritas</b> & \"comillas\""),
    "M021": ("direccion", "<script>alert(\"xss-M021\")</script> Calle 5"),
    "M022": ("public_description", "<img src=x onerror=alert(1)> PUBMARK-M022"),
}
FORMULA_LITERALS = {
    "M023": ("terreno", "=HYPERLINK(\"http://example.invalid\",\"Lote\")"),
    "M024": ("direccion", "+52 (442) 000 0000 Carretera 57"),
    "M025": ("public_description", "@SUM(A1:A2) PUBMARK-M025"),
    "M026": ("terreno", "-Lote Menos Uno"),
}


def h6(seed: int, *parts: str) -> str:
    return hashlib.sha256("|".join([str(seed), *parts]).encode()).hexdigest()[:6]


def sentinel(seed: int, kind: str, key: str) -> str:
    return f"SNTL-{kind}-{key}-{h6(seed, kind, key)}"


def private_fields(seed: int, key: str, rng: random.Random) -> dict:
    """Confidential values: contacts, notes, raw source extras (keys AND values)."""
    extra_key = sentinel(seed, "EXTRAK", key)
    extra = {
        f"Columna {extra_key}": sentinel(seed, "EXTRAV", key),
        "Comisión interna": f"{rng.randint(1, 5)}% {sentinel(seed, 'COMMISSION', key)}",
        "Archivo origen": f"inventario_{sentinel(seed, 'SRCFILE', key)}.xlsx",
        "Fórmula privada": f"=CONCAT(\"{sentinel(seed, 'FORMULA', key)}\")",
    }
    return {
        "contacts": f"Lic. Ñúñez Pérez {sentinel(seed, 'CONTACT', key)} tel. 55 0000 {rng.randint(1000, 9999)}",
        "internal_notes": f"<i>Nota interna</i> {sentinel(seed, 'NOTE', key)}",
        "extra": extra,
    }


def priced(rng: random.Random, area: float, i: int) -> dict:
    """Commercial terms by index bucket. Never converts or guesses currency."""
    bucket = i % 10
    if bucket in (0, 1, 2, 3):
        moneda, m2 = "MXN", round(rng.uniform(800, 9000), 2)
    elif bucket in (4, 5, 6, 7):
        moneda, m2 = "USD", round(rng.uniform(40, 450), 2)
    elif bucket == 8:
        return {"asking_price": None, "asking_m2": None, "moneda": None, "price_on_request": True}
    else:  # total only
        return {"asking_price": round(rng.uniform(2e6, 9e7), 2), "asking_m2": None,
                "moneda": "MXN", "price_on_request": False}
    total = round(m2 * area, 2) if bucket != 7 else None  # bucket 7: per-m2 only
    return {"asking_price": total, "asking_m2": m2, "moneda": moneda, "price_on_request": False}


def base_record(seed: int, rng: random.Random, key: str, i: int, place: tuple) -> dict:
    estado, municipio, lat0, lon0 = place
    area = round(rng.choice([rng.uniform(2_000, 60_000), rng.uniform(60_000, 900_000)]), 2)
    afect_pct = None if i % 4 == 0 else round(rng.uniform(0, 0.35), 4)
    draft = {
        "terreno": f"{NAME_STEMS[i % len(NAME_STEMS)]} {key}",
        "estado": estado,
        "municipio": municipio,
        "direccion": None if i % 6 == 0 else f"Km {rng.randint(1, 80)} Carretera Federal, {municipio}",
        "superficie_m2": area,
        "superficie_ha": area / 10_000,
        "afectaciones_pct": afect_pct,
        "afectaciones_m2": None if afect_pct is None else round(area * afect_pct, 2),
        "lat": round(lat0 + rng.uniform(-0.08, 0.08), 6),
        "lon": round(lon0 + rng.uniform(-0.08, 0.08), 6),
        "availability": "available",
        "public_description": f"Terreno de prueba ficticio PUBMARK-{key}",
        "price_confirmed_at": None,
        "availability_confirmed_at": None,
    }
    draft.update(priced(rng, area, i))
    draft.update(private_fields(seed, key, rng))
    return draft


def expectations(d: dict) -> tuple[list[str], list[str]]:
    """Contract-v1 publication gate (INTEGRATION_DECISIONS §5), as blockers/warnings.

    Codes are verifier-logical, not backend error codes: name, coordinates,
    area, availability, price, price_conflict, currency.
    """
    blockers: list[str] = []
    if not (d.get("terreno") or "").strip():
        blockers.append("name")
    lat, lon = d.get("lat"), d.get("lon")
    valid = (lat is not None and lon is not None and not (lat < 0 and lon > 0)
             and 14.0 <= lat <= 33.0 and -118.5 <= lon <= -86.0)
    if not valid:
        blockers.append("coordinates")
    if not (d.get("superficie_m2") or 0) > 0:
        blockers.append("area")
    if d.get("availability") in (None, "unknown"):
        blockers.append("availability")
    has_amount = d.get("asking_price") is not None or d.get("asking_m2") is not None
    if d.get("price_on_request"):
        if has_amount:
            blockers.append("price_conflict")
    elif not has_amount:
        blockers.append("price")
    elif d.get("moneda") not in ("USD", "MXN"):
        blockers.append("currency")
    warnings = []
    if d.get("asking_price") and d.get("asking_m2") and d.get("superficie_m2"):
        expected = d["asking_m2"] * d["superficie_m2"]
        if abs(d["asking_price"] - expected) / expected > 0.02:
            warnings.append("price_inconsistency")
    if not d.get("price_confirmed_at") or not d.get("availability_confirmed_at"):
        warnings.append("never_confirmed")
    return blockers, warnings


def build_master(seed: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(1, 121):
        key = f"M{i:03d}"
        out.append({"key": key, "draft": base_record(seed, rng, key, i, PLACES[i % len(PLACES)])})
    by = {r["key"]: r["draft"] for r in out}

    # Repeated name, distinct locations.
    for k, p in (("M005", PLACES[0]), ("M006", PLACES[6]), ("M007", PLACES[14])):
        by[k].update(terreno="Predio La Esperanza", estado=p[0], municipio=p[1],
                     lat=round(p[2] + 0.01, 6), lon=round(p[3] + 0.01, 6))
    # Nearby parcels (~45 m apart) with distinct names, plus a likely duplicate.
    by["M010"].update(terreno="Fracción A Los Olivos", estado="Querétaro", municipio="El Marqués",
                      lat=20.6301, lon=-100.2801, superficie_m2=12000.0, superficie_ha=1.2)
    by["M011"].update(terreno="Fracción B Los Olivos", estado="Querétaro", municipio="El Marqués",
                      lat=20.6305, lon=-100.2801, superficie_m2=12500.0, superficie_ha=1.25)
    by["M012"].update(terreno="Fracción A Los Olivos", estado="Querétaro", municipio="El Marqués",
                      lat=20.6302, lon=-100.2802, superficie_m2=12000.0, superficie_ha=1.2)
    for k, (field, value) in {**HTML_LITERALS, **FORMULA_LITERALS}.items():
        by[k][field] = value
    # Exact cents / canonical currency cases.
    by["M030"].update(superficie_m2=10000.0, superficie_ha=1.0, asking_m2=122.50,
                      asking_price=1225000.00, moneda="USD", price_on_request=False)
    by["M031"].update(superficie_m2=2500.0, superficie_ha=0.25, asking_m2=3456.78,
                      asking_price=8641950.00, moneda="MXN", price_on_request=False)
    by["M032"].update(superficie_m2=40000.0, superficie_ha=4.0, asking_m2=85.25,
                      asking_price=None, moneda="USD", price_on_request=False)
    by["M033"].update(asking_price=987654321.99, asking_m2=None, moneda="MXN", price_on_request=False)
    by["M034"].update(asking_price=None, asking_m2=None, moneda=None, price_on_request=True)
    # Inconsistent total vs unit (publishable, warning expected).
    by["M040"].update(superficie_m2=5000.0, superficie_ha=0.5, asking_m2=1500.00,
                      asking_price=10000000.00, moneda="MXN", price_on_request=False)
    # Area extremes.
    by["M041"].update(superficie_m2=1.0, superficie_ha=0.0001)
    by["M042"].update(superficie_m2=25000000.0, superficie_ha=2500.0)
    # Confirmation dates: fresh / stale / never (warnings only; no SLA invented).
    by["M050"].update(price_confirmed_at="2026-10-01", availability_confirmed_at="2026-10-01")
    by["M051"].update(price_confirmed_at="2024-01-15", availability_confirmed_at="2024-01-15")

    # Drafts: incomplete or not publishable as written.
    by["M101"].update(lat=None, lon=None)
    by["M102"].update(lat=-100.39, lon=20.58)            # X/Y swapped
    by["M103"].update(lat=40.7128, lon=-74.0060)         # outside Mexico
    by["M104"].update(asking_price=None, asking_m2=None, moneda=None, price_on_request=False)
    by["M105"].update(availability="unknown")
    by["M106"].update(price_on_request=True, asking_price=5000000.00, moneda="MXN")
    by["M107"].update(asking_price=3000000.00, asking_m2=None, moneda=None, price_on_request=False)
    by["M108"].update(superficie_m2=None, superficie_ha=None, afectaciones_m2=None)
    by["M109"].update(superficie_m2=0.0, superficie_ha=0.0, afectaciones_m2=None)
    keep = private_fields(seed, "M110", random.Random(seed + 110))
    m110 = {k: None for k in by["M110"]}
    m110.update(terreno="=CMD(\"calc\") Borrador mínimo M110", availability="unknown",
                      price_on_request=False, **keep)
    next(r for r in out if r["key"] == "M110")["draft"] = m110

    for r in out:
        d = r["draft"]
        # Area overrides above must not create accidental total/unit warnings;
        # M040 is the one deliberate inconsistency.
        if (r["key"] != "M040" and d.get("asking_price") is not None
                and d.get("asking_m2") is not None and d.get("superficie_m2")):
            d["asking_price"] = round(d["asking_m2"] * d["superficie_m2"], 2)
        if d.get("afectaciones_pct") is not None and d.get("superficie_m2"):
            d["afectaciones_m2"] = round(d["superficie_m2"] * d["afectaciones_pct"], 2)
        n =int(r["key"][1:])
        r["intended_lifecycle"] = ("published" if n <= 100 else "draft" if n <= 110 else "unpublished")
        r["dup_group"] = "olivos-A" if r["key"] in ("M010", "M012") else None
    return out


def build_matching(seed: int) -> list[dict]:
    rng = random.Random(seed + 251)
    out = []
    for i in range(1, 252):
        key = f"P{i:03d}"
        d = base_record(seed, rng, key, i, ("Aguascalientes", "Villa Verificación Paginación",
                                            21.8800, -102.2900))
        d["terreno"] = f"Lote Paginación {key}"
        d["lat"] = round(21.80 + (i % 16) * 0.01 + rng.uniform(0, 0.004), 6)
        d["lon"] = round(-102.40 + (i // 16) * 0.01 + rng.uniform(0, 0.004), 6)
        d["availability"] = "negotiation" if i % 10 == 0 else "available"
        out.append({"key": key, "draft": d, "intended_lifecycle": "published", "dup_group": None})
    return out


def build_users(seed: int) -> list[dict]:
    users = []
    for tag, name in (("A", "Ana Verificadora"), ("B", "Beto Verificador"),
                      ("C", "Cata Verificadora"), ("X", "Nunca Provisionado")):
        users.append({
            "tag": tag,
            "username": sentinel(seed, "USER", tag).lower(),
            "display_name": f"{name} {sentinel(seed, 'ACTOR', tag)}",
            "password": f"{sentinel(seed, 'PASS', tag)}-Fict!{h6(seed, 'pw', tag)}",
            "provision": tag != "X",
        })
    return users


def collect_sentinels(obj: object, found: set[str]) -> None:
    import re
    if isinstance(obj, dict):
        for k, v in obj.items():
            collect_sentinels(k, found)
            collect_sentinels(v, found)
    elif isinstance(obj, list):
        for v in obj:
            collect_sentinels(v, found)
    elif isinstance(obj, str):
        found.update(re.findall(SENTINEL_RE, obj))


def canonical(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def generate(seed: int) -> dict:
    master, matching, users = build_master(seed), build_matching(seed), build_users(seed)
    for r in master + matching:
        r["expected_blockers"], r["expected_warnings"] = expectations(r["draft"])
        r["publishable"] = not r["expected_blockers"]
        found: set[str] = set()
        collect_sentinels(r["draft"], found)
        r["sentinels"] = sorted(found)
    sentinels: set[str] = set()
    collect_sentinels([master, matching, users], sentinels)
    fixture_hash = hashlib.sha256(
        canonical({"seed": seed, "master": master, "matching": matching, "users": users})
    ).hexdigest()

    def count(rows, pred):
        return sum(1 for r in rows if pred(r))

    manifest = {
        "fixture_version": 1,
        "generator": "verification/fixtures/gen_fixtures.py",
        "seed": seed,
        "fixture_hash_sha256": fixture_hash,
        "fictional": True,
        "sentinel_regex": SENTINEL_RE,
        "sentinel_count": len(sentinels),
        "logical_private_fields": ["contacts", "internal_notes", "extra",
                                   "price_confirmed_at", "availability_confirmed_at"],
        "counts": {
            "master_total": len(master),
            "master_intended_published": count(master, lambda r: r["intended_lifecycle"] == "published"),
            "master_drafts": count(master, lambda r: r["intended_lifecycle"] == "draft"),
            "master_intended_unpublished": count(master, lambda r: r["intended_lifecycle"] == "unpublished"),
            "master_publishable": count(master, lambda r: r["publishable"]),
            "master_by_currency": {str(m): count(master, lambda r, m=m: r["draft"]["moneda"] == m)
                                   for m in ("USD", "MXN", None)},
            "master_price_on_request": count(master, lambda r: r["draft"]["price_on_request"]),
            "matching_total": len(matching),
            "matching_by_currency": {str(m): count(matching, lambda r, m=m: r["draft"]["moneda"] == m)
                                     for m in ("USD", "MXN", None)},
            "matching_negotiation": count(matching, lambda r: r["draft"]["availability"] == "negotiation"),
        },
        "canonical_cases": {
            "usd_cents_per_m2": {"key": "M030", "asking_m2": 122.50, "moneda": "USD"},
            "mxn_cents_per_m2": {"key": "M031", "asking_m2": 3456.78, "moneda": "MXN"},
            "usd_per_m2_only": {"key": "M032", "asking_m2": 85.25, "asking_price": None},
            "price_on_request": {"key": "M034"},
            "price_inconsistency_warning": {"key": "M040"},
            "area_min": {"key": "M041"}, "area_max": {"key": "M042"},
            "repeated_name_distinct_location": ["M005", "M006", "M007"],
            "nearby_distinct_parcels": ["M010", "M011"],
            "likely_duplicate_pair": ["M010", "M012"],
            "html_literals": sorted(HTML_LITERALS), "formula_literals": sorted(FORMULA_LITERALS),
            "confirmation_fresh_stale": ["M050", "M051"],
            "pagination_query": {"municipio": "Villa Verificación Paginación",
                                 "estado": "Aguascalientes", "q": "Lote Paginación"},
        },
        "records": {r["key"]: {k: r[k] for k in ("intended_lifecycle", "publishable",
                                                  "expected_blockers", "expected_warnings",
                                                  "dup_group", "sentinels")}
                    for r in master + matching},
    }
    return {"master_120.json": master, "matching_251.json": matching, "users.json": users,
            "sentinels.txt": "\n".join(sorted(sentinels)) + "\n", "manifest.json": manifest}


def self_check(files: dict, seed: int) -> None:
    master, matching = files["master_120.json"], files["matching_251.json"]
    m = files["manifest.json"]
    assert len(master) == 120 and len(matching) == 251
    c = m["counts"]
    assert (c["master_intended_published"], c["master_drafts"], c["master_intended_unpublished"]) == (100, 10, 10)
    # Every intended-published / unpublished record must pass the gate; every draft must not.
    for r in master:
        want = r["intended_lifecycle"] != "draft"
        assert r["publishable"] == want, (r["key"], r["expected_blockers"])
    assert all(r["publishable"] for r in matching)
    # Each record has its own unique private sentinels.
    seen: set[str] = set()
    for r in master + matching:
        assert len(r["sentinels"]) >= 6, r["key"]
        assert not seen & set(r["sentinels"]), r["key"]
        seen |= set(r["sentinels"])
    # Public fields never carry a sentinel.
    import re
    public = ("terreno", "estado", "municipio", "direccion", "public_description")
    for r in master + matching:
        for f in public:
            assert not re.search(SENTINEL_RE, str(r["draft"].get(f) or "")), (r["key"], f)
    assert len({r["key"] for r in master + matching}) == 371
    assert generate(seed)["manifest.json"]["fixture_hash_sha256"] == m["fixture_hash_sha256"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out")
    ap.add_argument("--check", action="store_true", help="only run the self-check")
    args = ap.parse_args()
    files = generate(args.seed)
    self_check(files, args.seed)
    if args.check:
        print("self-check OK", files["manifest.json"]["fixture_hash_sha256"])
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = args.out / name
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_text(json.dumps(content, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(f"fixtures -> {args.out}")
    print(f"fixture_hash_sha256 {files['manifest.json']['fixture_hash_sha256']}")
    print(json.dumps(files["manifest.json"]["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

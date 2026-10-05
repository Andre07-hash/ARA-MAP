"""Inventory rules shared by every route: editable fields, their validation,
the publication gate, attention reasons and list filtering.

Pure functions over plain dicts. The repository stores; this module decides.
Preview, Publish and the public catalog share one publication gate
(publication_blockers), one eligibility predicate (publicly_visible) and one
explicit serializer (public_terrain), so they cannot drift apart.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .importer import TerrainRecord
from .normalize import fold
from .validation import UBICACION_VALIDA, location_state, validate_record

AVAILABILITY = ("unknown", "available", "negotiation", "sold", "withdrawn")
PUBLIC_AVAILABILITY = ("available", "negotiation")
MONEDAS = ("USD", "MXN")
PUBLICATION_STATES = ("draft", "published", "unpublished", "archived")

# Text fields and their length limits. Short ones are single-spaced.
SHORT_TEXT = {"terreno": 200, "estado": 100, "municipio": 100}
LONG_TEXT = {"direccion": 500, "public_description": 5000, "contacto": 2000,
             "notas_internas": 10000}
NUMBERS = ("superficie_m2", "superficie_ha", "afectaciones_pct", "afectaciones_m2",
           "asking_price", "asking_m2", "lat", "lon")
NON_NEGATIVE = tuple(n for n in NUMBERS if n not in ("lat", "lon"))

# Everything a team user may write. Ids, version, pointers, actors, timestamps
# and confirmation stamps are server-controlled and rejected if sent.
EDITABLE = (*SHORT_TEXT, *LONG_TEXT, *NUMBERS, "moneda", "price_on_request", "availability")
CONFIRMABLE = ("price", "availability")

DEFAULT_LIMIT = 100
MAX_LIMIT = 250

# Validation findings that a publication blocker already reports.
_COVERED_BY_BLOCKERS = {"SIN_COORDENADAS", "COORD_INVERTIDA", "COORD_FUERA_MEXICO"}


def empty_draft() -> dict[str, Any]:
    draft: dict[str, Any] = dict.fromkeys(EDITABLE)
    draft["price_on_request"] = False
    draft["availability"] = "unknown"
    return draft


def clean_changes(data: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate a client-supplied field map. Returns (clean values, errors)."""
    if not isinstance(data, Mapping):
        return {}, {"changes": "Se esperaba un objeto con los campos a guardar."}
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, value in data.items():
        if name not in EDITABLE:
            errors[str(name)] = "Campo desconocido o no editable."
            continue
        try:
            clean[name] = _clean_value(name, value)
        except ValueError as exc:
            errors[name] = str(exc)
    return clean, errors


def _clean_value(name: str, value: Any) -> Any:
    if name in SHORT_TEXT or name in LONG_TEXT:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Debe ser texto.")
        text = " ".join(value.split()) if name in SHORT_TEXT else value.strip()
        limit = SHORT_TEXT.get(name) or LONG_TEXT[name]
        if len(text) > limit:
            raise ValueError(f"Admite hasta {limit} caracteres.")
        return text or None
    if name in NUMBERS:
        return _number(name, value)
    if name == "moneda":
        if value not in (None, *MONEDAS):
            raise ValueError("Usa USD o MXN (o vacío si se desconoce).")
        return value
    if name == "price_on_request":
        if not isinstance(value, bool):
            raise ValueError("Debe ser verdadero o falso.")
        return value
    if value not in AVAILABILITY:  # availability
        raise ValueError("Disponibilidad inválida.")
    return value


def _number(name: str, value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Debe ser un número.")
    try:
        number = float(value)
    except ValueError:
        raise ValueError("Debe ser un número.") from None
    if not math.isfinite(number):
        raise ValueError("Debe ser un número finito.")
    if name in NON_NEGATIVE and number < 0:
        raise ValueError("No puede ser negativo.")
    if name == "lat" and not -90 <= number <= 90:
        raise ValueError("La latitud va de -90 a 90.")
    if name == "lon" and not -180 <= number <= 180:
        raise ValueError("La longitud va de -180 a 180.")
    return number


def check_merged(changes: Mapping[str, Any], merged: Mapping[str, Any]) -> dict[str, str]:
    """Rules that span fields, applied only to what this change touches, so an
    edit elsewhere never fails on an adopted record's old gaps."""
    # A half or out-of-Mexico coordinate pair saves (INTEGRATION_DECISIONS §9);
    # it only blocks publication. Impossible values fail in _number().
    errors: dict[str, str] = {}
    priced = any(changes.get(n) is not None for n in ("asking_price", "asking_m2"))
    if priced and merged["moneda"] is None:
        # A price typed by hand states its currency; it is never assumed.
        errors["moneda"] = "Indica la moneda del precio: USD o MXN."
    return errors


# -- publication gate and attention -------------------------------------------

def publication_blockers(draft: Mapping[str, Any]) -> list[dict[str, str]]:
    """Supervisor contract v1 publication gate. Drafts may fail it; Publish may not."""
    blockers: list[dict[str, str]] = []

    def add(code: str, field: str, message: str) -> None:
        blockers.append({"code": code, "field": field, "message": message})

    if not (draft.get("terreno") or "").strip():
        add("name_required", "terreno", "Falta el nombre del terreno.")
    if location_state(draft.get("lat"), draft.get("lon")) != UBICACION_VALIDA:
        add("location_invalid", "lat", "Faltan coordenadas válidas dentro de México.")
    if not any((draft.get(n) or 0) > 0 for n in ("superficie_m2", "superficie_ha")):
        add("area_required", "superficie_m2", "Falta una superficie positiva.")
    if draft.get("availability") not in AVAILABILITY[1:]:
        add("availability_unknown", "availability", "Indica la disponibilidad.")
    amounts = [draft.get(n) for n in ("asking_price", "asking_m2")]
    if draft.get("price_on_request"):
        if any(a is not None for a in amounts):
            add("price_conflict", "price_on_request",
                "«Precio a consultar» no puede llevar montos; borra los montos o desmárcalo.")
    elif not any((a or 0) > 0 for a in amounts):
        add("price_required", "asking_price",
            "Falta un precio positivo, o marca «Precio a consultar».")
    elif draft.get("moneda") not in MONEDAS:
        add("currency_required", "moneda", "Indica la moneda del precio: USD o MXN.")
    return blockers


def warnings(draft: Mapping[str, Any]) -> list[dict[str, str]]:
    """The existing validation findings (inconsistent prices, area, ...), never
    corrections: source amounts are kept as entered."""
    valores: dict[str, Any] = {n: draft.get(n) for n in (
        "estado", "municipio", "direccion", *NUMBERS, "moneda")}
    record = TerrainRecord(orden=0, fila=0, terreno=draft.get("terreno") or "", **valores)
    return [{"code": f.codigo, "severity": f.severidad, "message": f.mensaje}
            for f in validate_record(record) if f.codigo not in _COVERED_BY_BLOCKERS]


def attention(draft: Mapping[str, Any], confirmations: Mapping[str, Any]) -> list[dict[str, str]]:
    """Why a record needs a look. No staleness cutoff: only never-confirmed."""
    reasons = [{"kind": "blocker", **b} for b in publication_blockers(draft)]
    if not confirmations.get("price") and not draft.get("price_on_request"):
        reasons.append({"kind": "unconfirmed", "code": "price_unconfirmed", "field": "asking_price",
                        "message": "El precio nunca se ha confirmado."})
    if not confirmations.get("availability"):
        reasons.append({"kind": "unconfirmed", "code": "availability_unconfirmed",
                        "field": "availability",
                        "message": "La disponibilidad nunca se ha confirmado."})
    reasons.extend({"kind": "warning", "field": "", **w} for w in warnings(draft))
    return reasons


# -- the public projection ------------------------------------------------------

# PublicTerrain, field by field (INTEGRATION_DECISIONS §5). Explicit selection:
# a revision is never copied whole and then trimmed, so a private field added
# later cannot leak by default. contacto, notas_internas, extra_json,
# confirmations and every actor are absent on purpose.
PUBLIC_REVISION_FIELDS = (
    "terreno", "estado", "municipio", "direccion", "superficie_m2", "superficie_ha",
    "afectaciones_pct", "afectaciones_m2", "lat", "lon", "asking_price", "asking_m2",
    "moneda", "price_on_request", "availability", "public_description")
PUBLIC_FIELDS = ("id", "revision_id", *PUBLIC_REVISION_FIELDS, "published_at")


def publicly_visible(availability: Any) -> bool:
    """Whether a published revision belongs in the active public catalog.
    Sold and withdrawn stay published internally but leave the catalog."""
    return availability in PUBLIC_AVAILABILITY


def public_terrain(inventory_id: str, revision_id: str, revision: Mapping[str, Any],
                   published_at: str | None) -> dict[str, Any]:
    """The one PublicTerrain serializer, for preview, public list and detail.
    Preview passes published_at=None: the commit time is not known yet."""
    terrain: dict[str, Any] = {"id": inventory_id, "revision_id": revision_id}
    for name in PUBLIC_REVISION_FIELDS:
        terrain[name] = revision[name]
    terrain["price_on_request"] = bool(terrain["price_on_request"])
    terrain["published_at"] = published_at
    return terrain


def public_changes(draft: Mapping[str, Any],
                   published: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Public fields where the saved draft differs from the published revision:
    what Publish would change in the catalog. Private notes are not a public
    change, so editing only them leaves nothing pending."""
    if published is None:
        return {}
    return {n: {"published": published[n], "draft": draft[n]}
            for n in PUBLIC_REVISION_FIELDS if _public_value(draft[n]) != _public_value(published[n])}


def _public_value(value: Any) -> Any:
    return bool(value) if isinstance(value, bool) else value


def preview_warnings(draft: Mapping[str, Any], confirmations: Mapping[str, Any],
                     published: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """What the team should see before publishing: unconfirmed facts, the
    existing validation findings (inconsistent prices...) and whether this
    publication takes the terrain out of the public catalog."""
    reasons = [r for r in attention(draft, confirmations) if r["kind"] != "blocker"]
    if draft.get("availability") in ("sold", "withdrawn"):
        visible_now = published is not None and publicly_visible(published.get("availability"))
        reasons.append({
            "kind": "warning", "code": "leaves_catalog", "field": "availability",
            "message": ("Al publicar, este terreno saldrá del catálogo público."
                        if visible_now else
                        "Publicado así, este terreno no aparecerá en el catálogo público.")})
    return reasons


# -- list queries -------------------------------------------------------------

class QueryError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("Filtros inválidos.")
        self.errors = errors


PUBLIC_QUERY = ("q", "estado", "municipio", "area_min_m2", "area_max_m2", "moneda",
                "price_min", "price_max", "price_basis", "cursor", "limit")
INTERNAL_QUERY = (*PUBLIC_QUERY, "publication_state", "availability", "attention",
                  "public_visible", "has_pending_changes", "include_archived")
_BOOLEAN = ("attention", "public_visible", "has_pending_changes", "include_archived")
_MULTI = ("estado", "municipio", "publication_state", "availability")


def parse_query(raw: Mapping[str, Sequence[str]], allowed: Sequence[str]) -> dict[str, Any]:
    """Validate list query parameters. Unknown selectors are rejected, never ignored."""
    errors = {k: "Filtro no admitido." for k in raw if k not in allowed}
    single = {k: v[-1] for k, v in raw.items() if k not in _MULTI and v}
    q: dict[str, Any] = {k: [x for x in raw.get(k, []) if x] for k in _MULTI}
    q["q"] = single.get("q", "").strip()
    for name in ("area_min_m2", "area_max_m2", "price_min", "price_max"):
        q[name] = None
        if single.get(name, "").strip():
            try:
                q[name] = _number("filtro", single[name])
            except ValueError as exc:
                errors[name] = str(exc)
    q["moneda"] = single.get("moneda") or None
    if q["moneda"] not in (None, *MONEDAS):
        errors["moneda"] = "Usa USD o MXN."
    q["price_basis"] = single.get("price_basis") or "total"
    if q["price_basis"] not in ("total", "per_m2"):
        errors["price_basis"] = "Usa total o per_m2."
    if (q["price_min"] is not None or q["price_max"] is not None) and not q["moneda"]:
        errors["moneda"] = "Un filtro de precio necesita una sola moneda: USD o MXN."
    q["cursor"] = single.get("cursor") or None
    try:
        q["limit"] = int(single.get("limit") or DEFAULT_LIMIT)
        if not 1 <= q["limit"] <= MAX_LIMIT:
            raise ValueError
    except ValueError:
        errors["limit"] = f"Usa un número entero de 1 a {MAX_LIMIT}."
    for name, choices in (("publication_state", PUBLICATION_STATES), ("availability", AVAILABILITY)):
        if any(v not in choices for v in q[name]):
            errors[name] = f"Valores admitidos: {', '.join(choices)}."
    for name in _BOOLEAN:
        value = single.get(name)
        if value not in (None, "true", "false", "1", "0"):
            errors[name] = "Usa true o false."
        q[name] = None if value is None else value in ("true", "1")
    if errors:
        raise QueryError(errors)
    return q


Fields = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def matches(fields: Mapping[str, Any], q: Mapping[str, Any]) -> bool:
    """Business-field filters, identical for the internal list and the public
    catalog (which passes published-revision fields, never draft ones)."""
    if q["estado"] and fields.get("estado") not in q["estado"]:
        return False
    if q["municipio"] and fields.get("municipio") not in q["municipio"]:
        return False
    if not _in_range(fields.get("superficie_m2"), q["area_min_m2"], q["area_max_m2"]):
        return False
    if q["moneda"] and (q["price_min"] is not None or q["price_max"] is not None):
        # One explicit currency; other and unknown currencies are left out.
        amount = fields.get("asking_price" if q["price_basis"] == "total" else "asking_m2")
        if fields.get("moneda") != q["moneda"] or amount is None:
            return False
        if not _in_range(amount, q["price_min"], q["price_max"]):
            return False
    elif q["moneda"] and fields.get("moneda") != q["moneda"]:
        return False
    if q["q"]:
        haystack = fold(" ".join(str(fields.get(n) or "") for n in
                                 ("terreno", "municipio", "estado", "direccion")))
        if fold(q["q"]) not in haystack:
            return False
    return True


def _in_range(value: float | None, low: float | None, high: float | None) -> bool:
    if low is not None and (value is None or value < low):
        return False
    return not (high is not None and (value is None or value > high))


def facets(items: Iterable[Mapping[str, Any]], fields: Fields, q: Mapping[str, Any]) -> dict[str, list[str]]:
    """Options over the whole candidate set, not one page. Municipalities
    narrow to the selected states."""
    rows = [fields(i) for i in items]

    def distinct(values: Iterable[Any]) -> list[str]:
        return sorted({v for v in values if v}, key=fold)

    return {
        "estados": distinct(r.get("estado") for r in rows),
        "municipios": distinct(r.get("municipio") for r in rows
                               if not q["estado"] or r.get("estado") in q["estado"]),
        "monedas": distinct(r.get("moneda") for r in rows),
    }


def page(items: Sequence[Mapping[str, Any]], q: Mapping[str, Any]) -> tuple[list[Any], str | None]:
    """Stable id order. The cursor is the last id already returned."""
    ordered = sorted(items, key=lambda i: i["id"])
    if q["cursor"]:
        ordered = [i for i in ordered if i["id"] > q["cursor"]]
    chunk = ordered[:q["limit"]]
    return list(chunk), (chunk[-1]["id"] if len(ordered) > q["limit"] else None)

"""Inventory rules shared by every route: editable fields, their validation,
the publication gate, attention reasons and list query parameters.

Pure functions over plain dicts. The repository stores; this module decides.
The list queries themselves run in SQL (server/repo/inventario.py).
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from .importer import TerrainRecord
from .validation import (
    AFECTACION_ALTA,
    AREA_TOLERANCE_M2,
    AVISO,
    PRICE_TOLERANCE,
    UBICACION_VALIDA,
    location_state,
    sql_ubicacion_valida,
    validate_record,
)
from .web_util import texto_seguro

AVAILABILITY = ("unknown", "available", "negotiation", "sold", "withdrawn")
PUBLIC_AVAILABILITY = ("available", "negotiation")
MONEDAS = ("USD", "MXN")
PUBLICATION_STATES = ("draft", "published", "unpublished", "archived")

# Text fields and their length limits. Short ones are single-spaced.
SHORT_TEXT = {"terreno": 200, "estado": 100, "municipio": 100, "tipo_terreno": 100}
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
MAX_LIMIT = 250          # history pages
MAX_LIST_LIMIT = 200     # terrain lists

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
        if not texto_seguro(text, lineas=name in LONG_TEXT):
            raise ValueError("Contiene caracteres no admitidos.")
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


# No rule spans fields when saving. Every business value is optional and
# independent: a half coordinate pair saves, and so does an amount whose
# currency is not known (moneda stays NULL, never assumed). Those gaps only
# block publication, below.

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
    found = [{"code": f.codigo, "severity": f.severidad, "message": f.mensaje}
             for f in validate_record(record) if f.codigo not in _COVERED_BY_BLOCKERS]
    if any(_fuera_de_rango(draft.get(n)) for n in _CRUZADOS):
        found.append({"code": "VALOR_FUERA_DE_RANGO", "severity": AVISO,
                      "message": "Un valor es demasiado grande o pequeño para comprobar su"
                                 " consistencia automáticamente; revísalo."})
    return found


# The numbers the findings multiply and divide. This is a technical guard for
# those consistency checks, not a business limit: the value is stored as
# entered and nothing about saving or publishing changes. Beyond this
# deliberately conservative range a product can overflow or underflow, which
# Postgres reports as an error, so the checks are not computed: the record is
# flagged instead, and sql_atencion() does no arithmetic on it. It says
# nothing about what a database can hold or what a property may cost.
_CRUZADOS = ("superficie_m2", "superficie_ha", "asking_price", "asking_m2")
RANGO_COMPROBABLE = (1e-100, 1e100)


def _fuera_de_rango(value: Any) -> bool:
    return bool(value) and not RANGO_COMPROBABLE[0] <= abs(value) <= RANGO_COMPROBABLE[1]


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


def sql_atencion(d: str = "d") -> str:
    """Whether attention() is non-empty, as a SQL predicate over the draft
    revision aliased ``d``. Never NULL, so NOT (...) is its exact complement.

    Built from the same constants and the same floating-point operations in
    the same order as the Python rules, so a list filtered by it and the
    reasons shown on each record cannot disagree. A test compares the two on
    both databases, tolerance boundaries included.
    """
    m2, ha, precio, unitario = (f"{d}.{n}" for n in _CRUZADOS)
    a_consultar = f"{d}.price_on_request = 1"
    sin_monto = f"(COALESCE({precio}, 0) <= 0 AND COALESCE({unitario}, 0) <= 0)"
    disponibles = ", ".join(f"'{a}'" for a in AVAILABILITY[1:])
    monedas = ", ".join(f"'{m}'" for m in MONEDAS)
    implicito = f"{unitario} * {m2}"
    fuera = " OR ".join(f"({c} <> 0 AND ({c} < {RANGO_COMPROBABLE[0]!r} OR {c} > {RANGO_COMPROBABLE[1]!r}))"
                        for c in (m2, ha, precio, unitario))
    hallazgos = (
        f"COALESCE({d}.estado, '') = ''",
        f"COALESCE({d}.municipio, '') = ''",
        f"({m2} IS NOT NULL AND {ha} IS NOT NULL"
        f" AND ABS({ha} * 10000 - {m2}) > {AREA_TOLERANCE_M2!r})",
        # A zero amount first: it is its own finding and would divide by zero below.
        f"CASE WHEN {precio} = 0 OR {unitario} = 0 THEN 1 = 1"
        f" WHEN {precio} IS NULL OR {unitario} IS NULL OR {m2} IS NULL THEN 1 = 0"
        f" ELSE ABS({implicito} - {precio}) / (CASE WHEN ABS({implicito}) >= ABS({precio})"
        f" THEN ABS({implicito}) ELSE ABS({precio}) END) > {PRICE_TOLERANCE!r} END",
        f"COALESCE({d}.afectaciones_pct, 0) > {AFECTACION_ALTA!r}",
    )
    return "(" + " OR ".join((
        # publication_blockers()
        f"TRIM(COALESCE({d}.terreno, '')) = ''",
        f"NOT {sql_ubicacion_valida(f'{d}.lat', f'{d}.lon')}",
        f"(COALESCE({m2}, 0) <= 0 AND COALESCE({ha}, 0) <= 0)",
        f"COALESCE({d}.availability, '') NOT IN ({disponibles})",
        f"({a_consultar} AND ({precio} IS NOT NULL OR {unitario} IS NOT NULL))",
        f"(NOT {a_consultar} AND ({sin_monto} OR COALESCE({d}.moneda, '') NOT IN ({monedas})))",
        # never confirmed
        f"(NOT {a_consultar} AND COALESCE({d}.price_confirmed_at, '') = '')",
        f"COALESCE({d}.availability_confirmed_at, '') = ''",
        # warnings(); CASE, because it alone fixes the order of evaluation
        f"CASE WHEN {fuera} THEN 1 = 1 ELSE ({' OR '.join(hallazgos)}) END",
    )) + ")"


# -- list queries -------------------------------------------------------------

class QueryError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("Filtros inválidos.")
        self.errors = errors


PUBLIC_QUERY = ("q", "estado", "municipio", "area_min_m2", "area_max_m2", "moneda",
                "price_min", "price_max", "price_basis", "cursor", "limit")
# One work base's list. "sort" names a key of SORTS, "-" in front for descending.
SCOPED_QUERY = (*PUBLIC_QUERY, "publication_state", "availability", "attention",
                "include_archived", "tipo_terreno", "sort")
# The administrators' master table adds the base filter: base ids and/or
# SIN_ASIGNAR for records that belong to no base.
INTERNAL_QUERY = (*SCOPED_QUERY, "base")
_MULTI = ("estado", "municipio", "publication_state", "availability", "tipo_terreno", "base")
SIN_ASIGNAR = "sin_asignar"
# Sort keys a client may name, and whether the column is text (sorted folded).
SORTS = {"id": False, "terreno": True, "estado": True, "municipio": True, "tipo_terreno": True,
         "superficie_m2": False, "asking_price": False, "updated_at": False}


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
        if not 1 <= q["limit"] <= MAX_LIST_LIMIT:
            raise ValueError
    except ValueError:
        errors["limit"] = f"Usa un número entero de 1 a {MAX_LIST_LIMIT}."
    q["sort"] = single.get("sort") or "id"
    if q["sort"].lstrip("-") not in SORTS or q["sort"].startswith("--"):
        errors["sort"] = f"Valores admitidos: {', '.join(SORTS)} (con «-» delante para descendente)."
    bases = []
    for valor in q["base"]:
        try:
            bases.append(valor if valor == SIN_ASIGNAR else str(uuid.UUID(valor)))
        except ValueError:
            errors["base"] = f"Usa identificadores de base o «{SIN_ASIGNAR}»."
    q["base"] = bases
    for name, choices in (("publication_state", PUBLICATION_STATES), ("availability", AVAILABILITY)):
        if any(v not in choices for v in q[name]):
            errors[name] = f"Valores admitidos: {', '.join(choices)}."
    for name in ("attention", "include_archived"):
        value = single.get(name)
        if value not in (None, "true", "false", "1", "0"):
            errors[name] = "Usa true o false."
        q[name] = None if value is None else value in ("true", "1")
    # Text that reaches a bound parameter: a NUL from %00 is refused by Postgres.
    for name in ("q", "estado", "municipio", "tipo_terreno"):
        valores = [q[name]] if name == "q" else q[name]
        if not all(texto_seguro(v) for v in valores):
            errors[name] = "Contiene caracteres no admitidos."
    if errors:
        raise QueryError(errors)
    return q

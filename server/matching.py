"""Identity for terrains across workbooks.

The ``ID`` column in the source workbooks is a row number within one file, so
it cannot join a terrain in September's base to the same terrain in October's.
Identity is derived from the fields that actually describe the site, with area
as the tiebreaker -- which is what correctly keeps the two distinct "Tecamac 93"
rows (45 Ha and 93 Ha) apart instead of collapsing them into one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .normalize import fold
from .protocols import TerrenoLike

# Two areas within this relative tolerance are treated as the same measurement,
# absorbing rounding differences between revisions of a workbook.
AREA_TOLERANCE = 0.005


def dedupe_key(terreno: str, estado: str | None, municipio: str | None) -> str:
    """Build the normalized identity key stored on every terrain row."""
    return "|".join(fold(part or "") for part in (terreno, estado, municipio))


def same_area(left: float | None, right: float | None) -> bool:
    """Compare two areas within tolerance, treating a missing pair as equal."""
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    largest = max(abs(left), abs(right))
    if largest == 0:
        return True
    return abs(left - right) / largest <= AREA_TOLERANCE


class Disposition(Enum):
    """What an incoming row turns out to be, relative to an existing base."""

    NUEVA = "nueva"
    DUPLICADA = "duplicada"
    CONFLICTO = "conflicto"


# How each comparable field is described when it differs.
ETIQUETAS_CAMPO = {
    "direccion": "Dirección",
    "superficie_m2": "Superficie m²",
    "superficie_ha": "Superficie ha",
    "afectaciones_pct": "Afectaciones %",
    "afectaciones_m2": "Afectaciones m²",
    "asking_price": "Asking Price",
    "asking_m2": "Asking $/m²",
    # 600 USD and 600 MXN are different prices, not a duplicate.
    "moneda": "Moneda",
    "lat": "Latitud (X)",
    "lon": "Longitud (Y)",
}


@dataclass(frozen=True)
class Difference:
    """One field whose stored value differs from the incoming one."""

    campo: str
    etiqueta: str
    anterior: Any
    nuevo: Any


@dataclass(frozen=True)
class Classification:
    """One incoming row, paired with the existing terrain it resolved against."""

    disposition: Disposition
    incoming_index: int
    existing_id: int | None = None
    reason: str | None = None
    diferencias: tuple[Difference, ...] = ()


def classify(
    incoming: Sequence[TerrenoLike],
    existing: Sequence[Mapping[str, Any]],
) -> tuple[Classification, ...]:
    """Classify each incoming record against the terrains already in a base.

    ``incoming`` is a sequence of parsed records; ``existing`` is a sequence of
    rows already stored, each needing ``id``, ``clave_dedupe``, ``superficie_m2``
    and ``asking_price``. Nothing is mutated and nothing is written -- the result
    is a plan the caller shows the user before any row is inserted.
    """
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in existing:
        by_key.setdefault(row["clave_dedupe"], []).append(row)

    results: list[Classification] = []
    # Rows added earlier in this same import are visible to later rows, so a file
    # containing the same terrain twice reports the second one as a duplicate.
    seen_in_batch: dict[str, list[Mapping[str, Any]]] = {}

    for index, record in enumerate(incoming):
        key = record.clave_dedupe
        candidates = by_key.get(key, []) + seen_in_batch.get(key, [])

        if not candidates:
            results.append(Classification(Disposition.NUEVA, index))
            seen_in_batch.setdefault(key, []).append(
                {"id": None, "clave_dedupe": key, "superficie_m2": record.superficie_m2,
                 "asking_price": record.asking_price}
            )
            continue

        twin = _closest_twin(candidates, record.superficie_m2)

        if twin is None:
            # Same name and place, different size: a genuinely different parcel.
            results.append(Classification(Disposition.NUEVA, index))
            seen_in_batch.setdefault(key, []).append(
                {"id": None, "clave_dedupe": key, "superficie_m2": record.superficie_m2,
                 "asking_price": record.asking_price}
            )
            continue

        cambios = differences(twin, record)
        if not cambios:
            results.append(Classification(Disposition.DUPLICADA, index, twin["id"]))
        else:
            etiquetas = ", ".join(d.etiqueta for d in cambios)
            results.append(
                Classification(
                    Disposition.CONFLICTO,
                    index,
                    twin["id"],
                    reason=f"Cambia: {etiquetas}",
                    diferencias=cambios,
                )
            )

    return tuple(results)


def _closest_twin(
    candidates: Sequence[Mapping[str, Any]], area: float | None
) -> Mapping[str, Any] | None:
    """Among candidates within tolerance, the one closest in area.

    Taking the first match instead would pair rows crosswise whenever two
    stored terrains sit within tolerance of each other, and then report the
    mismatch as a change the user never made.
    """
    viables = [c for c in candidates if same_area(c["superficie_m2"], area)]
    if not viables:
        return None
    if area is None:
        return viables[0]
    return min(
        viables,
        key=lambda c: abs((c["superficie_m2"] or 0) - area),
    )


def _same_value(left: Any, right: Any) -> bool:
    """Compare one field, tolerating float rounding and blank-vs-missing."""
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        largest = max(abs(left), abs(right))
        return True if largest == 0 else abs(left - right) / largest <= AREA_TOLERANCE
    return str(left).strip() == str(right).strip()


def differences(existing: Mapping[str, Any], record: TerrenoLike) -> tuple[Difference, ...]:
    """Every comparable field where the incoming row disagrees with the stored one.

    This is what separates "already here" from "here, but out of date". Only
    fields the existing row actually carries are compared, so a caller that
    supplies a partial row cannot produce phantom differences.
    """
    found = []
    for campo, etiqueta in ETIQUETAS_CAMPO.items():
        if campo not in existing:
            continue
        anterior = existing[campo]
        nuevo = getattr(record, campo, None)
        if not _same_value(anterior, nuevo):
            found.append(Difference(campo, etiqueta, anterior, nuevo))
    return tuple(found)

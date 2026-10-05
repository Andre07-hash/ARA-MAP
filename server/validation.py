"""Quality rules applied to every imported terrain.

Findings never block an import and never change a value. The workbook is stored
exactly as written and the problems are surfaced next to it, because the person
who maintains the file is the only one who can say which number is the correct
one.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .protocols import TerrenoLike

ERROR = "error"
AVISO = "aviso"

# Continental Mexico plus its islands, generously bounded. Guadalupe Island sits
# near -118.3, so the western edge is -118.5.
MEXICO_LAT = (14.0, 33.0)
MEXICO_LON = (-118.5, -86.0)

# A price is cross-checked against area x unit-price. Real rows reconcile within
# a fraction of a percent; 2% leaves room for rounding without hiding a typo.
PRICE_TOLERANCE = 0.02
AREA_TOLERANCE_M2 = 1.0
AFECTACION_ALTA = 0.5


# A coordinate pair is one of three things, and they must not be conflated:
# usable, absent, or present but impossible. Only the first can be plotted.
UBICACION_VALIDA = "valida"
UBICACION_SIN_DATO = "sin_dato"
UBICACION_INVALIDA = "invalida"


def location_state(lat: float | None, lon: float | None) -> str:
    """Classify a coordinate pair without altering it.

    An impossible pair is never silently swapped or dropped: it keeps its
    original values and is held back from the map for deliberate review.
    """
    if lat is None or lon is None:
        return UBICACION_SIN_DATO
    if lat < 0 and lon > 0:
        return UBICACION_INVALIDA          # X and Y written the other way round
    inside_lat = MEXICO_LAT[0] <= lat <= MEXICO_LAT[1]
    inside_lon = MEXICO_LON[0] <= lon <= MEXICO_LON[1]
    return UBICACION_VALIDA if (inside_lat and inside_lon) else UBICACION_INVALIDA


def sql_ubicacion_valida(lat: str = "lat", lon: str = "lon") -> str:
    """The same rule as location_state, as a SQL predicate.

    Generated from the constants above rather than written out again, so the
    counts shown in the interface cannot drift from the validation rules. A
    test asserts the two agree.
    """
    return (
        f"({lat} IS NOT NULL AND {lon} IS NOT NULL"
        f" AND NOT ({lat} < 0 AND {lon} > 0)"
        f" AND {lat} BETWEEN {MEXICO_LAT[0]} AND {MEXICO_LAT[1]}"
        f" AND {lon} BETWEEN {MEXICO_LON[0]} AND {MEXICO_LON[1]})"
    )


# How a field is named to the user in a finding, matching the file's headers.
ETIQUETAS_CAMPO = {
    "id_origen": "ID",
    "superficie_m2": "Superficie m2",
    "superficie_ha": "Superficie Ha",
    "afectaciones_pct": "Afectaciones %",
    "afectaciones_m2": "Afectaciones m2",
    "asking_price": "Asking Price",
    "asking_m2": "Asking $/m2",
    "lat": "X (latitud)",
    "lon": "Y (longitud)",
}


@dataclass(frozen=True)
class Finding:
    """One problem found in one terrain."""

    codigo: str
    severidad: str
    mensaje: str


def _relative_gap(left: float, right: float) -> float:
    largest = max(abs(left), abs(right))
    return 0.0 if largest == 0 else abs(left - right) / largest


def validate_record(record: TerrenoLike) -> tuple[Finding, ...]:
    """Check one terrain in isolation."""
    findings: list[Finding] = []

    for note in record.notes:
        motivo = getattr(note, "motivo", None)
        findings.append(
            Finding(
                "VALOR_NO_NUMERICO",
                AVISO,
                f"«{note.valor}» no se pudo leer en {ETIQUETAS_CAMPO.get(note.campo, note.campo)} "
                f"({motivo}); el campo quedó vacío."
                if motivo else
                f"«{note.valor}» no es un número; el campo {note.campo} quedó vacío.",
            )
        )

    for campo, etiqueta in (("estado", "Estado"), ("municipio", "Municipio")):
        if not getattr(record, campo):
            findings.append(Finding("CAMPO_FALTANTE", AVISO, f"Falta {etiqueta}."))

    findings.extend(_check_coordinates(record))
    findings.extend(_check_surface(record))
    findings.extend(_check_price(record))
    findings.extend(_check_afectaciones(record))

    return tuple(findings)


def _check_coordinates(record: TerrenoLike) -> list[Finding]:
    estado = location_state(record.lat, record.lon)
    if estado == UBICACION_SIN_DATO:
        return [
            Finding(
                "SIN_COORDENADAS",
                AVISO,
                "Sin coordenadas: no se puede dibujar en el mapa.",
            )
        ]
    if estado == UBICACION_VALIDA:
        return []

    # Impossible, but which way impossible tells the user what to correct.
    if record.lat is not None and record.lon is not None and record.lat < 0 < record.lon:
        return [
            Finding(
                "COORD_INVERTIDA",
                ERROR,
                f"X y Y parecen invertidas (lat {record.lat:.4f}, lon {record.lon:.4f}). "
                "No se dibuja en el mapa hasta corregirlo.",
            )
        ]
    return [
        Finding(
            "COORD_FUERA_MEXICO",
            ERROR,
            f"Las coordenadas caen fuera de México (lat {record.lat:.4f}, "
            f"lon {record.lon:.4f}). No se dibuja en el mapa.",
        )
    ]


def _check_surface(record: TerrenoLike) -> list[Finding]:
    if record.superficie_m2 is None or record.superficie_ha is None:
        return []
    implied = record.superficie_ha * 10_000
    if abs(implied - record.superficie_m2) > AREA_TOLERANCE_M2:
        return [
            Finding(
                "SUPERFICIE_INCONSISTENTE",
                ERROR,
                f"Superficie Ha ({record.superficie_ha:,.4f}) equivale a {implied:,.0f} m², "
                f"pero la columna m² dice {record.superficie_m2:,.0f}.",
            )
        ]
    return []


def _dinero(valor: float, moneda: str | None) -> str:
    """An amount with its currency code; a bare "$" only when it is unknown."""
    cifra = f"{valor:,.0f}" if float(valor).is_integer() or abs(valor) >= 1000 else f"{valor:,.2f}"
    return f"{cifra} {moneda}" if moneda else f"${cifra}"


def _check_price(record: TerrenoLike) -> list[Finding]:
    # A price of exactly zero reconciles with zero per m2, so the consistency
    # check below would pass it silently. It is a placeholder, not a price.
    if record.asking_price == 0 or record.asking_m2 == 0:
        return [
            Finding(
                "PRECIO_CERO",
                AVISO,
                "El precio está en cero; probablemente falta capturarlo.",
            )
        ]

    precio = record.asking_price
    unitario = record.asking_m2
    superficie = record.superficie_m2
    if precio is None or unitario is None or superficie is None:
        return []

    implied = unitario * superficie
    if _relative_gap(implied, precio) > PRICE_TOLERANCE:
        factor = precio / implied if implied else 0
        hint = " Parece un error de un dígito (10×)." if 9 < factor < 11 else ""
        moneda = getattr(record, "moneda", None)
        return [
            Finding(
                "PRECIO_INCONSISTENTE",
                ERROR,
                f"Asking Price es {_dinero(precio, moneda)} pero "
                f"{_dinero(unitario, moneda)}/m² × {superficie:,.0f} m² "
                f"da {_dinero(implied, moneda)}.{hint}",
            )
        ]
    return []


def _check_afectaciones(record: TerrenoLike) -> list[Finding]:
    pct = record.afectaciones_pct
    if pct is None:
        return []
    if pct > 1:
        # The column is formatted as a percentage, so 0.85 means 85%. A value
        # above 1 was almost certainly typed as a whole number.
        return [
            Finding(
                "AFECTACION_FORMATO",
                AVISO,
                f"Afectaciones dice {pct:g}; se esperaba una fracción (0.85 = 85%).",
            )
        ]
    if pct > AFECTACION_ALTA:
        return [
            Finding(
                "AFECTACION_ALTA",
                AVISO,
                f"{pct:.1%} del terreno está afectado.",
            )
        ]
    return []


def validate_all(records: Iterable[TerrenoLike]) -> dict[int, tuple[Finding, ...]]:
    """Validate a whole import, including checks that span rows.

    Keyed by ``record.orden``.
    """
    results = {r.orden: list(validate_record(r)) for r in records}

    by_key: dict[str, list[TerrenoLike]] = defaultdict(list)
    for record in records:
        by_key[record.clave_dedupe].append(record)

    for twins in by_key.values():
        if len(twins) < 2:
            continue
        for record in twins:
            others = [t for t in twins if t is not record]
            filas = ", ".join(str(t.fila) for t in others)
            results[record.orden].append(
                Finding(
                    "DUPLICADO_EN_BASE",
                    AVISO,
                    f"Mismo nombre, estado y municipio que la fila {filas}.",
                )
            )

    return {orden: tuple(found) for orden, found in results.items()}


def summarize(findings_by_orden: Mapping[int, Sequence[Finding]]) -> dict[str, int]:
    """Count findings by code, for the import preview."""
    counts: dict[str, int] = defaultdict(int)
    for findings in findings_by_orden.values():
        for finding in findings:
            counts[finding.codigo] += 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

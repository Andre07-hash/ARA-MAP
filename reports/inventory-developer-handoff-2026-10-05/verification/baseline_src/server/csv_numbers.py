"""Read CSV cell text as numbers under an explicit, user-chosen convention.

A CSV cell is always text, and the same text means different things depending
on who exported it: ``1,234`` is one thousand two hundred thirty-four with a
decimal point, and one point two three four with a decimal comma. Guessing per
cell would silently change values, so the user picks the convention for the
whole file and every cell is checked against it. Text whose separators do not
fit the convention is reported, never coerced.

This is deliberately separate from ``normalize.to_number``, which strips every
comma and percent sign: that is right for typed Excel cells and wrong here.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .importer import ParseNote
from .normalize import NULL_SENTINELS, fold

DOT = "dot"
COMMA = "comma"
DECIMAL_MODES = {DOT: "punto decimal", COMMA: "coma decimal"}

MONEY_FIELDS = frozenset({"asking_price", "asking_m2"})
PERCENT_FIELD = "afectaciones_pct"

# Mantissa: plain digits, or digits grouped in threes by the thousands mark,
# then an optional fraction after the decimal mark. An optional exponent may
# follow; its sign and digits carry no separators in either convention.
_EXPONENT = r"(?:[eE][+-]?\d+)?"
_PATTERNS = {
    DOT: re.compile(r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)" + _EXPONENT),
    COMMA: re.compile(r"(?:(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?|,\d+)" + _EXPONENT),
}
# A supported currency written next to an amount: "US$ 600", "600 USD",
# "MXN 1,200". Which currency the amount is in is decided before any amount is
# read -- by the column's explicit markers or the user's answer -- and checked
# against every marker in the column; here the marker is only taken off so the
# digits can be read. Other currencies are left in place and fail as text.
_MONEDA_INICIAL = re.compile(r"^(?:us\s*\$|u\s*\$\s*s|usd|mx\s*\$|mxn)\s*", re.I)
_MONEDA_FINAL = re.compile(r"\s*(?:usd|mxn|dlls?|dls)$", re.I)
_GROUP_MARK = {DOT: ",", COMMA: "."}
_DECIMAL_MARK = {DOT: ".", COMMA: ","}


def _sin_moneda(texto: str) -> str:
    return _MONEDA_FINAL.sub("", _MONEDA_INICIAL.sub("", texto)).strip()


class _InvalidNumberError(ValueError):
    """Internal: the reason a cell could not be read, in the user's words."""


def parse_number(field_name: str, raw: Any, mode: str, where: str = "") -> tuple[float | None, ParseNote | None]:
    """Read one CSV cell as a float under ``mode`` ("dot" or "comma").

    Returns ``(value, None)``, ``(None, None)`` for an empty cell, or
    ``(None, note)`` with the original text kept for the finding. ``where``
    (for example "línea 7") is added to the note's reason.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None, None
    if fold(text) in NULL_SENTINELS or (field_name in MONEY_FIELDS and fold(_sin_moneda(text)) in NULL_SENTINELS):
        # Same as Excel: "SD" means no data, and the row says so. "US$ -" is
        # the same no-data dash with a currency in front: missing, never zero.
        return None, ParseNote(field_name, text)

    try:
        return _parse(field_name, text, mode), None
    except _InvalidNumberError as reason:
        prefix = f"{where}, " if where else ""
        return None, ParseNote(field_name, text, f"{prefix}{DECIMAL_MODES[mode]}: {reason}")


def parse_id(raw: Any, mode: str, where: str = "") -> tuple[int | None, ParseNote | None]:
    """Read the source ID: a whole number or nothing, never truncated."""
    value, note = parse_number("id_origen", raw, mode, where)
    if note is not None or value is None:
        return None, note
    if not value.is_integer():
        prefix = f"{where}, " if where else ""
        return None, ParseNote("id_origen", str(raw).strip(),
                               f"{prefix}el ID debe ser un número entero")
    return int(value), None


def _parse(field_name: str, text: str, mode: str) -> float:
    if text[0] in "=@":
        raise _InvalidNumberError("parece una fórmula; el CSV se lee como texto y no se evalúa")

    body = text.replace("−", "-")  # the Unicode minus Excel sometimes writes
    if field_name in MONEY_FIELDS:
        body = _sin_moneda(body) or body
    sign = ""
    if body[0] in "+-":
        sign, body = body[0], body[1:].lstrip()

    if body.startswith("$"):
        if field_name not in MONEY_FIELDS:
            raise _InvalidNumberError("el signo $ solo se admite en los campos de precio")
        body = body[1:].lstrip()
        if not sign and body[:1] in ("+", "-"):
            sign, body = body[0], body[1:]

    scale = 1.0
    if body.endswith("%"):
        if field_name != PERCENT_FIELD:
            raise _InvalidNumberError("el signo % solo se admite en Afectaciones %")
        # "10%" is ten percent, stored as the fraction 0.10 the validator expects.
        body, scale = body[:-1].rstrip(), 100.0

    if not _PATTERNS[mode].fullmatch(body):
        raise _InvalidNumberError("los separadores o caracteres no corresponden a este formato")

    canonical = body.replace(_GROUP_MARK[mode], "").replace(_DECIMAL_MARK[mode], ".")
    value = float(sign + canonical) / scale
    if not math.isfinite(value):
        raise _InvalidNumberError("el valor es demasiado grande")
    return value

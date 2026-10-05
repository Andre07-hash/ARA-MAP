"""Text and value normalization shared by the importer, matcher and validator.

Everything here is a pure function over a single cell value. Coercion never
raises and never guesses: a value that cannot be read as a number comes back as
``None`` together with the original text, so the caller can report what was
rejected instead of silently dropping it.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Values that mean "no data" in the source workbooks. "SD" is the one actually
# present in Base Terrenos 09.26 (three rows of Asking $/m2); the rest are
# variants seen in hand-maintained spreadsheets.
NULL_SENTINELS = frozenset(
    {"", "-", "--", "---", "n/a", "na", "nd", "n.d.", "sd", "s/d", "sin dato", "none", "null"}
)

_WHITESPACE = re.compile(r"\s+")

# Characters stripped before a numeric parse: thousands separators, currency,
# percent signs and the non-breaking spaces Excel likes to leave behind.
_NUMERIC_NOISE = str.maketrans({",": "", "$": "", "%": "", " ": "", " ": "", "−": "-"})


def fold(text: Any) -> str:
    """Fold text to a comparable key: no accents, no case, single spaces.

    Uses NFKD so compatibility characters collapse too, which is what turns a
    header of ``Superficie m²`` into ``superficie m2``.
    """
    decomposed = unicodedata.normalize("NFKD", str(text))
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return _WHITESPACE.sub(" ", without_marks.strip().lower())


def clean_text(value: Any) -> str | None:
    """Trim a cell to display text, or ``None`` when it carries no information."""
    if value is None:
        return None
    text = _WHITESPACE.sub(" ", str(value).strip())
    if not text or fold(text) in NULL_SENTINELS:
        return None
    return text


def to_number(value: Any) -> tuple[float | None, str | None]:
    """Coerce a cell to a float.

    Returns ``(number, rejected)``. Exactly one side is ever populated:
    ``(3.5, None)`` on success, ``(None, "SD")`` when text was present but not
    numeric, and ``(None, None)`` when the cell was simply empty.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        # Excel booleans in a numeric column are a data error, not a 0/1.
        return None, str(value)
    if isinstance(value, (int, float)):
        return float(value), None

    text = str(value).strip()
    if not text:
        return None, None
    if fold(text) in NULL_SENTINELS:
        return None, text

    try:
        return float(text.translate(_NUMERIC_NOISE)), None
    except ValueError:
        return None, text

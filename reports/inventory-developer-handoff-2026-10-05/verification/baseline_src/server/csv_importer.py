"""Read a terrain CSV into the same records an Excel import produces.

A CSV is one table with no worksheets: the first nonblank record is the header
and every later nonblank record is one terrain. Headers go through the same
alias table as a workbook, rows through the same record builder, so everything
downstream -- validation, matching, staging, storage -- sees no difference.

What differs is how much can go wrong silently in a text file, so this reader
is strict where a workbook reader need not be:

- UTF-8 only (with or without BOM), decoded strictly. Anything else is an error
  asking for "CSV UTF-8", never a best guess that mangles accents.
- Comma, semicolon or tab separators, chosen by which one yields a recognizable
  header and a consistent width. Two different valid readings are refused.
- Every data record must be exactly as wide as the header. An unquoted
  separator inside a value would otherwise shift every later column.
- Numbers follow the convention the user picked (see ``csv_numbers``).

``fila`` on records and rejected rows is the first physical line of the record
in the file, so a quoted multiline address does not throw the count off.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from . import csv_numbers
from .errors import WorkbookError
from .importer import (
    EXPECTED_FIELDS,
    ImportResult,
    RejectedRow,
    TerrainRecord,
    _build_record,
    map_headers,
)
from .normalize import clean_text, fold

CSV_SHEET = "CSV"  # ImportResult.hoja for a CSV: it has no worksheets.
DELIMITERS = (",", ";", "\t")

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_SEP_DIRECTIVE = re.compile(r"sep=([,;\t])")
_EXCEL_SIGNATURES = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")  # .xlsx zip, legacy .xls

ENCODING_ERROR = "No se pudo leer la codificación del CSV. Vuelve a exportarlo como CSV UTF-8."


class CsvError(WorkbookError):
    """A CSV file that cannot be imported; the message is for the user."""


@dataclass(frozen=True)
class _Row:
    linea: int  # first physical line of the record
    values: tuple[str, ...]


@dataclass(frozen=True)
class _Reading:
    """One delimiter's interpretation of the whole file."""

    delimiter: str
    rows: tuple[_Row, ...]  # nonblank records, header first
    error: str | None = None

    @property
    def header(self) -> tuple[str, ...]:
        return self.rows[0].values if self.rows else ()

    @property
    def recognizes_terreno(self) -> bool:
        mapped, _ = map_headers(self.header)
        return "terreno" in mapped.values()

    @property
    def width_mismatch(self) -> _Row | None:
        width = len(self.header)
        return next((row for row in self.rows[1:] if len(row.values) != width), None)

    @property
    def valid(self) -> bool:
        return self.error is None and self.recognizes_terreno and self.width_mismatch is None


def read_csv_bytes(content: bytes, *, decimal_mode: str = csv_numbers.DOT) -> ImportResult:
    """Read a terrain CSV into immutable records. Does not touch the DB."""
    if decimal_mode not in csv_numbers.DECIMAL_MODES:
        raise CsvError("Formato de números no válido: elige punto decimal o coma decimal.")

    text = decode(content)
    if not text.strip():
        raise CsvError("El CSV está vacío.")

    reading = _choose_reading(text)
    header, data = reading.header, reading.rows[1:]
    _check_header(header, data)
    if not data:
        raise CsvError("El CSV solo contiene la fila de encabezados; no hay terrenos que importar.")

    mapped, unknown = map_headers(header)
    records: list[TerrainRecord] = []
    rechazadas: list[RejectedRow] = []
    for row in data:
        where = f"línea {row.linea}"
        resultado = _build_record(
            row.values, mapped, unknown, len(records) + 1, row.linea,
            number=partial(csv_numbers.parse_number, mode=decimal_mode, where=where),
            ident=partial(csv_numbers.parse_id, mode=decimal_mode, where=where),
        )
        if isinstance(resultado, TerrainRecord):
            records.append(resultado)
        elif isinstance(resultado, RejectedRow):
            rechazadas.append(resultado)
        else:
            # The record has text, but only "SD"/"N/A"-style placeholders. It
            # still has to be accounted for rather than vanish.
            rechazadas.append(RejectedRow(
                fila=row.linea, motivo="SIN_NOMBRE",
                resumen="Falta el nombre del terreno · la línea solo contiene valores vacíos",
            ))

    return ImportResult(
        hoja=CSV_SHEET,
        records=tuple(records),
        columnas_no_reconocidas=tuple(unknown.values()),
        columnas_faltantes=tuple(sorted(EXPECTED_FIELDS - set(mapped.values()))),
        rechazadas=tuple(rechazadas),
    )


def decode(content: bytes) -> str:
    """Strict UTF-8, BOM optional. Never drops or replaces bytes."""
    if content.startswith(_EXCEL_SIGNATURES):
        raise CsvError(
            "El archivo tiene extensión .csv pero es un libro de Excel. "
            "Selecciónalo con su extensión .xlsx, o expórtalo como CSV UTF-8."
        )
    # UTF-16 decodes "successfully" as UTF-8 surprisingly often when it is
    # mostly ASCII; its BOM or its NUL bytes give it away.
    if content.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in content:
        raise CsvError(ENCODING_ERROR)
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvError(ENCODING_ERROR) from None


def _directive(text: str) -> tuple[str | None, int | None]:
    """Excel's optional first line ``sep=,`` / ``sep=;`` / ``sep=<tab>``."""
    for number, line in enumerate(_LINE_BREAK.split(text), start=1):
        if not line.strip():
            continue
        match = _SEP_DIRECTIVE.fullmatch(line.strip())
        return (match.group(1), number) if match else (None, None)
    return None, None


def _read(text: str, delimiter: str, skip_line: int | None) -> _Reading:
    """Parse the whole file with one delimiter, keeping each record's first line."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    rows: list[_Row] = []
    while True:
        start = reader.line_num + 1
        try:
            values = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            return _Reading(delimiter, tuple(rows), _explain(exc, start))
        if start == skip_line or not any(v.strip() for v in values):
            continue
        rows.append(_Row(start, tuple(values)))
    return _Reading(delimiter, tuple(rows))


def _explain(exc: csv.Error, linea: int) -> str:
    message = str(exc)
    if "field larger than field limit" in message or "unexpected end of data" in message:
        detail = "hay una comilla sin cerrar"
    elif "expected after" in message:
        detail = "hay texto pegado a una comilla de cierre"
    else:
        detail = "el formato no es CSV válido"
    return (f"No se pudo leer el CSV en la línea {linea}: {detail}. "
            "Revisa las comillas y los separadores.")


def _choose_reading(text: str) -> _Reading:
    """Pick comma or semicolon from the whole file, or refuse to guess."""
    forced, directive_line = _directive(text)
    candidates = (forced,) if forced else DELIMITERS
    readings = [_read(text, d, directive_line) for d in candidates]

    valid = [r for r in readings if r.valid]
    if len(valid) == 1:
        return valid[0]
    if len(valid) > 1:
        # A one-column file reads the same either way; that is not ambiguity.
        if all(r.rows == valid[0].rows for r in valid[1:]):
            return valid[0]
        raise CsvError(
            "No se pudo determinar el separador de columnas: el archivo se puede leer "
            "de varias formas con resultados distintos. "
            "Vuelve a exportarlo como CSV UTF-8 o agrega «sep=,», «sep=;» o «sep=<tabulación>» "
            "como primera línea."
        )

    if not any(r.rows for r in readings):
        failed = next((r for r in readings if r.error), None)
        raise CsvError(failed.error if failed else "El CSV está vacío.")

    headed = [r for r in readings if r.recognizes_terreno]
    if not headed:
        widest = max(readings, key=lambda r: len(r.header))
        encontradas = ", ".join(v.strip() for v in widest.header if v.strip())
        raise CsvError(
            "El CSV no contiene la columna obligatoria «Terreno»."
            + (f" Columnas encontradas: {encontradas}." if encontradas else "")
        )

    # The header was recognized, so this delimiter is right; the body is not.
    reading = max(headed, key=lambda r: len(r.header))
    if reading.error:
        raise CsvError(reading.error)
    bad = reading.width_mismatch
    assert bad is not None
    raise CsvError(
        f"El CSV tiene {len(bad.values)} columnas en la línea {bad.linea}; "
        f"se esperaban {len(reading.header)}. Revisa las comillas y los separadores."
    )


def _check_header(header: Sequence[str], data: Sequence[_Row]) -> None:
    """Refuse headers that would lose or overwrite data."""
    seen: dict[str, str] = {}
    for label in header:
        text = clean_text(label)
        if text is None:
            continue
        key = fold(text)
        if key in seen:
            raise CsvError(
                f"El CSV repite el encabezado «{text}». Cada columna debe tener un nombre distinto."
            )
        seen[key] = text

    unnamed = [i for i, label in enumerate(header) if clean_text(label) is None]
    for row in data:
        for index in unnamed:
            if clean_text(row.values[index]) is not None:
                raise CsvError(
                    f"La columna {index + 1} no tiene encabezado, pero la línea {row.linea} "
                    f"tiene datos en ella («{row.values[index].strip()}»). "
                    "Agrega un nombre a esa columna o elimínala."
                )

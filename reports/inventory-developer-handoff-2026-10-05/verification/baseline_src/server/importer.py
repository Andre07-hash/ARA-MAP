"""Read an ARA terrain workbook into normalized records.

The source is a hand-maintained Excel file: one sheet, "Registro Analisis", a
header row, then one row per terrain. Headers are matched by a folded alias
table rather than by position, so a reordered or renamed-but-recognizable column
still lands in the right field, and an unrecognized column is carried along in
``extra`` instead of being dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .errors import WorkbookError
from .matching import dedupe_key
from .normalize import clean_text, fold, to_number
from .validation import UBICACION_INVALIDA, UBICACION_SIN_DATO, UBICACION_VALIDA, location_state

SHEET_NAME = "Registro Análisis"

# Folded header -> field name. The X/Y pair is the one mapping that must never
# be "corrected" to the usual GIS convention: in these workbooks X holds the
# LATITUDE (~19.8) and Y holds the LONGITUDE (~-99.1). Reading them as
# x=longitude puts every terrain in the Indian Ocean.
COLUMN_ALIASES: Mapping[str, str] = {
    "id": "id_origen",
    "terreno": "terreno",
    "nombre": "terreno",
    "predio": "terreno",
    "estado": "estado",
    "municipio": "municipio",
    "direccion": "direccion",
    "domicilio": "direccion",
    "superficie m2": "superficie_m2",
    "superficie": "superficie_m2",
    "area m2": "superficie_m2",
    "superficie ha": "superficie_ha",
    "superficie hectareas": "superficie_ha",
    "hectareas": "superficie_ha",
    "afectaciones %": "afectaciones_pct",
    "afectaciones porcentaje": "afectaciones_pct",
    "afectacion %": "afectaciones_pct",
    "afectaciones m2": "afectaciones_m2",
    "afectacion m2": "afectaciones_m2",
    "asking price": "asking_price",
    "precio": "asking_price",
    "precio de venta": "asking_price",
    "asking $/m2": "asking_m2",
    "precio $/m2": "asking_m2",
    "$/m2": "asking_m2",
    "x": "lat",
    "latitud": "lat",
    "latitude": "lat",
    "lat": "lat",
    "y": "lon",
    "longitud": "lon",
    "longitude": "lon",
    "lon": "lon",
}

TEXT_FIELDS = ("terreno", "estado", "municipio", "direccion")
NUMERIC_FIELDS = (
    "superficie_m2",
    "superficie_ha",
    "afectaciones_pct",
    "afectaciones_m2",
    "asking_price",
    "asking_m2",
    "lat",
    "lon",
)
REQUIRED_FIELDS = ("terreno",)
# Not required, but worth flagging in the preview when a file lacks them.
EXPECTED_FIELDS = frozenset({"estado", "municipio", "superficie_m2", "asking_price", "lat", "lon"})


@dataclass(frozen=True)
class ParseNote:
    """A cell whose text could not be read as a number, kept for reporting.

    ``motivo`` says why, when the reader knows more than "not a number" (a CSV
    cell with misplaced separators, say). It defaults to None so pending imports
    serialized before the field existed still decode.
    """

    campo: str
    valor: str
    motivo: str | None = None


@dataclass(frozen=True)
class TerrainRecord:
    """One terrain, normalized. Immutable: revisions produce a new record."""

    orden: int
    fila: int
    terreno: str
    id_origen: int | None = None
    estado: str | None = None
    municipio: str | None = None
    direccion: str | None = None
    superficie_m2: float | None = None
    superficie_ha: float | None = None
    afectaciones_pct: float | None = None
    afectaciones_m2: float | None = None
    asking_price: float | None = None
    asking_m2: float | None = None
    lat: float | None = None
    lon: float | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[ParseNote, ...] = ()
    # "USD" | "MXN" for the prices, or None when unknown: an amount is never
    # assumed to be in either. Set by the import plan, which settles it.
    moneda: str | None = None

    @property
    def clave_dedupe(self) -> str:
        return dedupe_key(self.terreno, self.estado, self.municipio)

    @property
    def ubicacion(self) -> str:
        """Whether this terrain's coordinates are usable, absent or impossible."""
        return location_state(self.lat, self.lon)

    @property
    def ubicado(self) -> bool:
        """True when the terrain can honestly be drawn on the map."""
        return self.ubicacion == UBICACION_VALIDA


@dataclass(frozen=True)
class RejectedRow:
    """A row that carried data but could not be stored, and why.

    Kept so that no non-blank row can disappear behind a clean import message:
    every one is either accepted or listed here with its spreadsheet row number.
    """

    fila: int
    motivo: str
    resumen: str


@dataclass(frozen=True)
class ImportResult:
    """Everything read from one workbook, plus what could not be mapped."""

    hoja: str
    records: tuple[TerrainRecord, ...]
    columnas_no_reconocidas: tuple[str, ...]
    columnas_faltantes: tuple[str, ...]
    rechazadas: tuple[RejectedRow, ...] = ()

    @property
    def filas_con_datos(self) -> int:
        """Every non-blank row in the sheet: accepted plus rejected."""
        return len(self.records) + len(self.rechazadas)

    @property
    def ubicados(self) -> int:
        return sum(1 for r in self.records if r.ubicado)

    @property
    def sin_ubicacion(self) -> int:
        """Rows that cannot be plotted, whether coordinates are absent or bad."""
        return len(self.records) - self.ubicados

    @property
    def sin_coordenadas(self) -> int:
        return sum(1 for r in self.records if r.ubicacion == UBICACION_SIN_DATO)

    @property
    def ubicacion_invalida(self) -> int:
        return sum(1 for r in self.records if r.ubicacion == UBICACION_INVALIDA)


def resolve_sheet(workbook: Any) -> str:
    """Pick the terrain sheet: the expected name, else the first sheet."""
    wanted = fold(SHEET_NAME)
    for name in workbook.sheetnames:
        if fold(name) == wanted:
            return str(name)
    if not workbook.sheetnames:
        raise WorkbookError("El archivo no contiene ninguna hoja.")
    return str(workbook.sheetnames[0])


def map_headers(header_row: Sequence[Any]) -> tuple[dict[int, str], dict[int, str]]:
    """Map column index -> field name, and the columns we did not recognize."""
    mapped: dict[int, str] = {}
    unknown: dict[int, str] = {}
    for index, raw in enumerate(header_row):
        label = clean_text(raw)
        if label is None:
            continue  # trailing empty column N in the current workbooks
        field_name = COLUMN_ALIASES.get(fold(label))
        if field_name is None:
            unknown[index] = label
        elif field_name not in mapped.values():
            mapped[index] = field_name
        else:
            unknown[index] = label  # a second column claiming a taken field
    return mapped, unknown


# A converter turns one raw cell into a value, plus a note when the cell held
# text that could not be read. Excel and CSV need different ones: a workbook
# cell is usually already typed, a CSV cell is always text.
NumberConverter = Callable[[str, Any], "tuple[float | None, ParseNote | None]"]
IdConverter = Callable[[Any], "tuple[int | None, ParseNote | None]"]


def excel_number(field_name: str, raw: Any) -> tuple[float | None, ParseNote | None]:
    number, rejected = to_number(raw)
    return number, (ParseNote(field_name, rejected) if rejected is not None else None)


def excel_id(raw: Any) -> tuple[int | None, ParseNote | None]:
    number, _ = to_number(raw)
    return (int(number) if number is not None else None), None


def _build_record(
    values: Sequence[Any],
    mapped: Mapping[int, str],
    unknown: Mapping[int, str],
    orden: int,
    fila: int,
    number: NumberConverter = excel_number,
    ident: IdConverter = excel_id,
) -> TerrainRecord | RejectedRow | None:
    """Turn one spreadsheet row into a record.

    Returns None only for a genuinely blank row. A row that holds data but
    cannot be stored comes back as a RejectedRow so the caller can report it.
    """
    if not any(clean_text(v) is not None for v in values):
        return None

    fields: dict[str, Any] = {}
    notes: list[ParseNote] = []

    for index, field_name in mapped.items():
        raw = values[index] if index < len(values) else None
        note: ParseNote | None = None
        if field_name in TEXT_FIELDS:
            fields[field_name] = clean_text(raw)
        elif field_name in NUMERIC_FIELDS:
            fields[field_name], note = number(field_name, raw)
        elif field_name == "id_origen":
            fields[field_name], note = ident(raw)
        if note is not None:
            notes.append(note)

    if not fields.get("terreno"):
        # A terrain with no name cannot be identified, matched or shown. The row
        # is not stored, but it is reported with whatever it did carry so the
        # user can find it in the spreadsheet and fix it.
        pistas = [
            f"{etiqueta}: {valor}"
            for etiqueta, valor in (
                ("Estado", fields.get("estado")),
                ("Municipio", fields.get("municipio")),
                ("Superficie m²", fields.get("superficie_m2")),
                ("Asking Price", fields.get("asking_price")),
            )
            if valor not in (None, "")
        ]
        return RejectedRow(
            fila=fila,
            motivo="SIN_NOMBRE",
            resumen="Falta el nombre del terreno"
                    + (f" · {' · '.join(pistas)}" if pistas else ""),
        )

    extra = {
        label: clean_text(values[index]) if index < len(values) else None
        for index, label in unknown.items()
        if index < len(values) and clean_text(values[index]) is not None
    }

    return TerrainRecord(orden=orden, fila=fila, extra=extra, notes=tuple(notes), **fields)


def read_workbook(path: str | Path) -> ImportResult:
    """Read a terrain workbook into immutable records. Does not touch the DB."""
    path = Path(path)
    if not path.exists():
        raise WorkbookError(f"No se encontró el archivo: {path}")

    try:
        workbook = load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:  # openpyxl raises a variety of types
        raise WorkbookError(f"No se pudo abrir el archivo de Excel: {exc}") from exc

    try:
        sheet_name = resolve_sheet(workbook)
        sheet = workbook[sheet_name]
        rows = sheet.iter_rows(values_only=True)

        try:
            header_row = next(rows)
        except StopIteration:
            raise WorkbookError(f"La hoja «{sheet_name}» está vacía.") from None

        mapped, unknown = map_headers(header_row)
        missing = tuple(f for f in REQUIRED_FIELDS if f not in mapped.values())
        if missing:
            raise WorkbookError(
                "La hoja no tiene la columna obligatoria «Terreno». "
                f"Columnas encontradas: {', '.join(str(h) for h in header_row if h)}"
            )

        records: list[TerrainRecord] = []
        rechazadas: list[RejectedRow] = []
        for offset, values in enumerate(rows, start=2):
            resultado = _build_record(values, mapped, unknown, len(records) + 1, offset)
            if isinstance(resultado, TerrainRecord):
                records.append(resultado)
            elif isinstance(resultado, RejectedRow):
                rechazadas.append(resultado)
    finally:
        workbook.close()

    return ImportResult(
        hoja=sheet_name,
        records=tuple(records),
        columnas_no_reconocidas=tuple(unknown.values()),
        columnas_faltantes=tuple(sorted(EXPECTED_FIELDS - set(mapped.values()))),
        rechazadas=tuple(rechazadas),
    )

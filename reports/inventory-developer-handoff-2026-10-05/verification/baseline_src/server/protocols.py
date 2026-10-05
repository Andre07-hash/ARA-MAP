"""Structural types shared across modules.

Validation and matching both consume "something shaped like a terrain". Stating
that shape as a Protocol keeps them from importing the importer, and lets a
manually entered terrain satisfy the same contract as an imported row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol


class DatabaseConnection(Protocol):
    """Query operations shared by the local and cloud database adapters."""

    def execute(self, statement: str, params: Any = ...) -> Any: ...


class ParseNoteLike(Protocol):
    """A cell whose text could not be read as a number."""

    @property
    def campo(self) -> str: ...
    @property
    def valor(self) -> str: ...


class TerrenoLike(Protocol):
    """The fields the validation, matching and storage layers read.

    Declared as read-only properties because the records passed in are frozen:
    a plain attribute annotation would demand a settable attribute and no
    immutable record could satisfy it.
    """

    @property
    def orden(self) -> int: ...
    @property
    def fila(self) -> int: ...
    @property
    def terreno(self) -> str: ...
    @property
    def estado(self) -> str | None: ...
    @property
    def municipio(self) -> str | None: ...
    @property
    def direccion(self) -> str | None: ...
    @property
    def id_origen(self) -> int | None: ...
    @property
    def superficie_m2(self) -> float | None: ...
    @property
    def superficie_ha(self) -> float | None: ...
    @property
    def afectaciones_pct(self) -> float | None: ...
    @property
    def afectaciones_m2(self) -> float | None: ...
    @property
    def asking_price(self) -> float | None: ...
    @property
    def asking_m2(self) -> float | None: ...
    @property
    def lat(self) -> float | None: ...
    @property
    def lon(self) -> float | None: ...
    @property
    def moneda(self) -> str | None: ...
    @property
    def extra(self) -> Mapping[str, Any]: ...
    @property
    def notes(self) -> Sequence[ParseNoteLike]: ...

    @property
    def clave_dedupe(self) -> str:
        """The normalized identity key used to match terrains across files."""

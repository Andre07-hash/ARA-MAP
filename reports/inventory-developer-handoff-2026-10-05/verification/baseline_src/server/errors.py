"""The application's exception hierarchy.

One base class means a caller can catch everything this application raises
without also catching unrelated failures from the standard library.
"""

from __future__ import annotations

from typing import Any


class AraError(Exception):
    """Base for every error ARA Map raises deliberately."""


class WorkbookError(AraError):
    """A spreadsheet could not be read.

    Carries a message written for the person who picked the file, since it is
    shown to them directly.
    """


class ApiError(AraError):
    """An error that should reach the browser as a clean JSON message."""

    def __init__(self, mensaje: str, status: int = 400, detalle: Any = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.detalle = detalle

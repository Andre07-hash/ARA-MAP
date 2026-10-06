"""The boundary between a refresh and wherever the workbook lives.

A provider is bound to one stored file identity (drive + item) and to the
connected account's grant. It returns metadata and complete bytes, or raises
ProveedorError with a stable code the UI can act on. Microsoft's
implementation is in microsoft.py; tests use an in-memory fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Metadatos:
    nombre: str
    etag: str | None
    ctag: str | None
    tamano: int | None
    modificado_en: str | None
    modificado_por: str | None
    web_url: str | None

    def revision(self) -> tuple[str | None, str | None, int | None, str | None]:
        return (self.etag, self.ctag, self.tamano, self.modificado_en)


class ProveedorError(Exception):
    """Codes: reconectar (grant revoked/expired), sin_permiso, no_encontrado,
    no_disponible (429/5xx/timeout, retryable), demasiado_grande,
    archivo_cambiando (changed during download), no_configurado."""

    def __init__(self, codigo: str, mensaje: str, *, reintentable: bool = False) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.reintentable = reintentable


class Proveedor(Protocol):
    def metadatos(self) -> Metadatos: ...

    def descargar(self, max_bytes: int) -> bytes: ...


def version_coherente(proveedor: Proveedor, max_bytes: int, intentos: int = 3) -> tuple[Metadatos, bytes]:
    """Metadata and bytes of ONE provider revision. If the file changes while
    it is being downloaded, try again; never return a mixed version."""
    for _ in range(intentos):
        antes = proveedor.metadatos()
        contenido = proveedor.descargar(max_bytes)
        despues = proveedor.metadatos()
        if antes.revision() == despues.revision():
            return despues, contenido
    raise ProveedorError("archivo_cambiando",
                         "El archivo cambió mientras se leía. Espera a que termine de guardarse"
                         " y vuelve a intentarlo.", reintentable=True)

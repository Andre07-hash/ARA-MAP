"""Fixtures for connected-workbook tests: generated workbooks (fictional
rows only) and an in-memory provider standing in for OneDrive."""

from __future__ import annotations

import io
import threading
from typing import Any

from openpyxl import Workbook

from server.excel.proveedor import Metadatos, ProveedorError

ENCABEZADO = ["ID", "Terreno", "Estado", "Municipio", "Superficie m2", "Asking Price", "Asking $/m2", "X", "Y"]


def fila(clave: Any, nombre: str, precio: float = 1_000_000, m2: float = 10_000, **extra: Any) -> list[Any]:
    return [clave, nombre, extra.get("estado", "Jalisco"), extra.get("municipio", "Zapopan"), m2,
            precio, extra.get("unitario", round(precio / m2, 2)), extra.get("x", 20.7), extra.get("y", -103.4)]


def libro(filas: list[list[Any]], encabezado: list[str] | None = None, hoja: str = "Registro Análisis",
          otras_hojas: tuple[str, ...] = ()) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(encabezado or ENCABEZADO)
    for f in filas:
        ws.append(f)
    for nombre in otras_hojas:
        wb.create_sheet(nombre).append(["Otra"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


BASICO = [fila("A-001", "Lote Alfa", 1_000_000), fila("A-002", "Lote Beta", 2_000_000),
          fila("007", "Lote Gamma", 3_000_000)]


class Archivo:
    """One fake cloud file. revision bumps on every content change."""

    def __init__(self, contenido: bytes, nombre: str = "Terrenos.xlsx") -> None:
        self.contenido = contenido
        self.nombre = nombre
        self.revision = 1
        self.falla: ProveedorError | None = None
        self.cambiar_durante_descarga = 0   # times the file changes mid-download
        self.esperar: threading.Event | None = None  # block descargar until set
        self.descargando = threading.Event()
        self.descargas = 0

    def poner(self, contenido: bytes) -> None:
        self.contenido = contenido
        self.revision += 1


class Proveedor:
    def __init__(self, archivo: Archivo) -> None:
        self.archivo = archivo

    def metadatos(self) -> Metadatos:
        if self.archivo.falla:
            raise self.archivo.falla
        a = self.archivo
        return Metadatos(a.nombre, f'"etag-{a.revision}"', f'"ctag-{a.revision}"', len(a.contenido),
                         "2026-10-06T12:00:00Z", "Empleado Ficticio", "https://onedrive.live.com/edit?id=FICTICIO")

    def descargar(self, max_bytes: int) -> bytes:
        a = self.archivo
        a.descargas += 1
        a.descargando.set()
        if a.esperar is not None:
            a.esperar.wait(10)
        if a.falla:
            raise a.falla
        contenido = a.contenido
        if a.cambiar_durante_descarga:
            a.cambiar_durante_descarga -= 1
            a.revision += 1
        if len(contenido) > max_bytes:
            raise ProveedorError("demasiado_grande", "El archivo es demasiado grande.")
        return contenido


class Drive:
    """file identity -> Archivo; used as the API's FABRICA."""

    def __init__(self) -> None:
        self.archivos: dict[tuple[str, str], Archivo] = {}

    def agregar(self, item_id: str, contenido: bytes, drive_id: str = "drive-ficticio") -> Archivo:
        archivo = Archivo(contenido)
        self.archivos[(drive_id, item_id)] = archivo
        return archivo

    def __call__(self, ident: Any) -> Proveedor:
        archivo = self.archivos.get((ident["drive_id"], ident["item_id"]))
        if archivo is None:
            raise ProveedorError("no_encontrado", "No se encontró el archivo.")
        return Proveedor(archivo)


def crear_cuenta(conn: Any, user_id: str, cuenta_id: str = "cuenta-ficticia") -> str:
    from server import db
    conn.execute(
        "INSERT INTO excel_cuenta (id, proveedor, proveedor_tenant, proveedor_cuenta_id, tipo, nombre,"
        " correo, conectada_por, conectada_en, actualizada_en)"
        " VALUES (?, 'microsoft', 'consumers', ?, 'personal', 'Dueño Ficticio', 'dueno@example.com', ?, ?, ?)",
        (cuenta_id, f"ms-{cuenta_id}", user_id, db.now(), db.now()))
    return cuenta_id

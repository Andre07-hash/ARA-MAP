"""Folder endpoints, plus the validation every folder-aware endpoint shares.

Folders organize the two dashboards separately: ``tipo`` "bases" folders hold
bases, "mapas" folders hold saved maps. Deleting a folder never deletes what
is in it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .. import db
from ..normalize import fold
from ..repo import carpetas as repo
from ..router import Request
from ..web_util import ApiError, parse_json, require

Respuesta = dict[str, Any]

MAX_NOMBRE = 100
_ESPACIOS = re.compile(r"\s+")
# The navigation's own entries. A folder with one of these names would be
# indistinguishable from them.
RESERVADOS = {
    "bases": {fold("Todas las bases"), fold("Sin carpeta")},
    "mapas": {fold("Todos los mapas"), fold("Sin carpeta")},
}
NO_EXISTE = "La carpeta ya no existe; puede que otra persona la haya eliminado."


def parse_tipo(value: Any) -> str:
    if value not in repo.TIPOS:
        raise ApiError("Tipo de carpeta inválido: usa «bases» o «mapas».")
    return str(value)


def parse_nombre(value: Any, tipo: str) -> tuple[str, str]:
    """The display name (trimmed, single-spaced) and its uniqueness key."""
    if not isinstance(value, str):
        raise ApiError("El nombre de la carpeta debe ser texto.")
    nombre = _ESPACIOS.sub(" ", value).strip()
    if not nombre:
        raise ApiError("El nombre de la carpeta no puede estar vacío.")
    if len(nombre) > MAX_NOMBRE:
        raise ApiError(f"El nombre de la carpeta admite hasta {MAX_NOMBRE} caracteres.")
    clave = fold(nombre)
    if clave in RESERVADOS[tipo]:
        raise ApiError(f"«{nombre}» es un nombre reservado de la navegación; elige otro.")
    return nombre, clave


def parse_carpeta_id(value: Any) -> int | None:
    """A destination: a positive integer id, or None for "Sin carpeta".

    JSON booleans are ints in Python, and "3" or 3.0 are not ids, so the type
    is checked exactly.
    """
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ApiError("carpeta_id debe ser un número entero positivo o null.")
    return value


def destination(data: dict[str, Any], *, required: bool) -> int | None:
    """Read ``carpeta_id`` from a request body.

    For a move it must be present (``{}`` is a mistake; ``null`` explicitly
    unfiles). For creation it is optional and absent means "Sin carpeta", so
    older clients keep working.
    """
    if required and "carpeta_id" not in data:
        raise ApiError("Falta carpeta_id (usa null para «Sin carpeta»).")
    return parse_carpeta_id(data.get("carpeta_id"))


@contextmanager
def folder_errors() -> Iterator[None]:
    """Translate the repository's folder errors into HTTP answers."""
    try:
        yield
    except repo.CarpetaNoExisteError:
        raise ApiError(NO_EXISTE, 404) from None
    except repo.CarpetaTipoIncorrectoError:
        raise ApiError("Esa carpeta es de otro tipo: las bases y los mapas tienen "
                       "carpetas separadas.") from None
    except repo.CarpetaDuplicadaError as exc:
        raise ApiError(f"Ya existe una carpeta llamada «{exc}».", 409) from None


def listing(request: Request) -> Respuesta:
    tipo = parse_tipo(request.q("tipo"))
    with db.session() as conn:
        return repo.listing(conn, tipo)


def create(request: Request) -> Respuesta:
    data = parse_json(request.body)
    tipo = parse_tipo(data.get("tipo"))
    nombre, clave = parse_nombre(data.get("nombre"), tipo)
    with db.session() as conn, folder_errors():
        carpeta_id = repo.create(conn, tipo, nombre, clave)
        return {"carpeta": repo.get(conn, carpeta_id)}


def rename(request: Request) -> Respuesta:
    data = parse_json(request.body)
    require(data, "nombre")
    carpeta_id = request.param("id")
    with db.session() as conn, folder_errors():
        actual = repo.get(conn, carpeta_id)
        if actual is None:
            raise repo.CarpetaNoExisteError(str(carpeta_id))
        nombre, clave = parse_nombre(data["nombre"], actual["tipo"])
        repo.rename(conn, carpeta_id, nombre, clave)
        return {"carpeta": repo.get(conn, carpeta_id)}


def remove(request: Request) -> Respuesta:
    """Delete a folder; its items move to "Sin carpeta", none is deleted."""
    carpeta_id = request.param("id")
    with db.session() as conn, folder_errors():
        actual = repo.get(conn, carpeta_id)
        if actual is None:
            raise repo.CarpetaNoExisteError(str(carpeta_id))
        trasladados = repo.delete(conn, carpeta_id)
        return {"eliminada": actual["nombre"], "tipo": actual["tipo"], "trasladados": trasladados}

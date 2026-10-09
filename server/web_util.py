"""Small helpers shared by the HTTP handlers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from .errors import ApiError

# Re-exported so handlers can import their error type from one place.
__all__ = ["ApiError", "encode", "parse_json", "require", "texto_seguro"]


def encode(payload: Any) -> bytes:
    """Serialize a response body, unpacking dataclasses on the way."""
    return json.dumps(payload, ensure_ascii=False, default=_fallback).encode("utf-8")


def _fallback(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


def texto_seguro(texto: str, lineas: bool = False) -> bool:
    """Whether client text can be stored, hashed and sent back on either
    database: it encodes as UTF-8 (JSON can carry a lone surrogate, which does
    not) and holds no control character. ``lineas`` allows tab, line feed and
    carriage return, for free text. Any other Unicode, beyond the BMP too, is
    fine."""
    try:
        texto.encode("utf-8")
    except UnicodeError:
        return False
    permitidos = "\t\n\r" if lineas else ""
    return not any((c < " " or "\x7f" <= c <= "\x9f") and c not in permitidos for c in texto)


def parse_json(body: bytes) -> dict[str, Any]:
    """Read a JSON object body, or fail with a message the browser can show."""
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(f"Cuerpo de la petición inválido: {exc}") from exc
    if not isinstance(data, dict):
        raise ApiError("Se esperaba un objeto JSON.")
    return data


def require(data: Mapping[str, Any], *names: str) -> tuple[Any, ...]:
    """Pull required keys out of a payload, failing with a clear message."""
    missing = [n for n in names if data.get(n) in (None, "")]
    if missing:
        raise ApiError(f"Faltan campos obligatorios: {', '.join(missing)}")
    return tuple(data[n] for n in names)

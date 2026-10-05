"""What a column can become, the names that say so, and the evidence rules.

Header names are matched in a fixed order of trust: the legacy ARA aliases, then
a curated synonym table, each after folding accents, case, punctuation and
spacing. A name is never trusted blindly where it can mislead: "X"/"Y" and
"Norte"/"Este" are checked against the values, "Valor" or "Importe" could be a
total or a price per m², and a price's currency is never guessed: a bare "$"
is used by both dollars and pesos, so only an explicit marker (US$, USD, MXN,
pesos...) or the user's answer settles it. USD and MXN are supported; any
other currency stays additional data.

``respaldo`` is the one gate every non-user assignment passes -- deterministic
or automatic alike: does the column's header and content actually support the
field? Only an explicit answer from the user skips it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..importer import COLUMN_ALIASES
from ..normalize import fold
from ..validation import MEXICO_LAT, MEXICO_LON

EXTRA = "extra"       # keep the value as additional data (the default)
IGNORAR = "ignorar"   # do not import the column at all

# target -> (label shown to the user, kind of value)
CAMPOS: dict[str, tuple[str, str]] = {
    "terreno": ("Nombre del terreno", "texto"),
    "id_origen": ("ID de origen", "entero"),
    "estado": ("Estado", "texto"),
    "municipio": ("Municipio", "texto"),
    "direccion": ("Dirección", "texto"),
    "superficie_m2": ("Superficie (m²)", "numero"),
    "superficie_ha": ("Superficie (ha)", "numero"),
    "afectaciones_pct": ("Afectaciones (%)", "numero"),
    "afectaciones_m2": ("Afectaciones (m²)", "numero"),
    "asking_price": ("Precio total", "numero"),
    "asking_m2": ("Precio por m²", "numero"),
    "lat": ("Latitud", "numero"),
    "lon": ("Longitud", "numero"),
}
DESTINOS = (*CAMPOS, EXTRA, IGNORAR)
ETIQUETA_DESTINO = {
    **{k: v[0] for k, v in CAMPOS.items()},
    EXTRA: "Conservar como dato adicional",
    IGNORAR: "No importar",
}
NUMERICOS = frozenset(k for k, (_, tipo) in CAMPOS.items() if tipo != "texto")
TEXTO = frozenset(k for k, (_, tipo) in CAMPOS.items() if tipo == "texto")
PRECIOS = ("asking_price", "asking_m2")

# Price currencies ARA stores. Amounts are kept as written: never converted.
SOPORTADAS = ("USD", "MXN")
NOMBRE_MONEDA = {"USD": "Dólares estadounidenses (USD)", "MXN": "Pesos mexicanos (MXN)"}
# Headers of a column that states each row's currency ("Moneda": USD).
CLAVES_MONEDA = frozenset({"moneda", "currency", "divisa", "moneda del precio", "moneda precio"})

_PUNTUACION = re.compile(r"[()\[\]{}:;,.*_\-]+")
_ESPACIOS = re.compile(r"\s+")


def normalizar(etiqueta: Any) -> str:
    """Fold a header for matching: no accents/case, punctuation as spaces.

    Keeps $, % and / because they carry meaning ("$/m2", "%").
    """
    if etiqueta is None:
        return ""
    return _ESPACIOS.sub(" ", _PUNTUACION.sub(" ", fold(etiqueta))).strip()


_SINONIMOS: dict[str, tuple[str, ...]] = {
    "terreno": ("nombre del terreno", "nombre del predio", "nombre comercial",
                "nombre de la propiedad", "propiedad", "inmueble", "nombre terreno"),
    "estado": ("entidad", "entidad federativa", "estado republica"),
    "municipio": ("alcaldia", "municipio / alcaldia", "municipio alcaldia", "delegacion"),
    "direccion": ("calle", "direccion completa", "ubicacion direccion"),
    "superficie_m2": ("superficie total m2", "metros cuadrados", "m2", "area del predio m2",
                      "superficie terreno m2", "superficie m 2", "area total m2"),
    "superficie_ha": ("ha", "superficie en hectareas", "area ha", "area del predio ha",
                      "superficie total ha", "hectareas ha"),
    "afectaciones_pct": ("% afectacion", "% afectaciones", "porcentaje de afectacion"),
    "afectaciones_m2": ("superficie afectada m2", "area afectada m2"),
    "asking_price": ("precio total", "valor de venta", "valor de venta mxn", "precio mxn",
                     "precio total mxn", "precio de venta mxn", "precio de lista"),
    "asking_m2": ("precio m2", "precio por m2", "precio/m2", "valor m2", "precio unitario m2",
                  "precio por metro cuadrado", "$ m2", "precio $ m2"),
    "lat": ("latitude",),
    "lon": ("lng", "long"),
    "id_origen": ("clave", "folio"),
}

# X/Y and Norte/Este are never mapped by name alone; see detectar.coordenadas.
EJES_X = frozenset({"x"})
EJES_Y = frozenset({"y"})
NORTE = frozenset({"norte", "northing", "n", "coord n", "coordenada norte"})
ESTE = frozenset({"este", "easting", "e", "coord e", "coordenada este"})
AMBIGUOS_PRECIO = frozenset({"valor", "importe", "monto", "costo", "precio unitario", "valor total"})

_NOMBRES: dict[str, str] = {}
for _alias, _campo in COLUMN_ALIASES.items():
    _NOMBRES[normalizar(_alias)] = _campo
for _campo, _lista in _SINONIMOS.items():
    for _alias in _lista:
        _NOMBRES.setdefault(normalizar(_alias), _campo)
for _eje in ("x", "y"):
    _NOMBRES.pop(_eje, None)  # X/Y: decided with their values, never by name alone


def por_nombre(etiqueta: Any) -> tuple[str | None, str]:
    """(field, how it matched) for a recognized header, else (None, "").

    A currency written into the header ("Asking Price (USD)") is evidence about
    the amounts, not part of the field's name, so it is set aside for matching.
    """
    if etiqueta is None:
        return None, ""
    exacto = fold(etiqueta)
    if exacto in COLUMN_ALIASES and exacto not in ("x", "y"):
        return COLUMN_ALIASES[exacto], "nombre"
    campo = _NOMBRES.get(normalizar(etiqueta)) or _NOMBRES.get(normalizar(_MONEDA.sub(" ", exacto)))
    return (campo, "alias") if campo else (None, "")


# Explicit currency markers, matched on folded text. A bare "$" is NOT one: it
# is written for dollars and pesos alike, so it never decides a currency. The
# boundaries are lookarounds rather than \b so that markers ending in a symbol
# ("US$") still match at the end of a header.
_MONEDAS: tuple[tuple[str, str], ...] = (
    ("USD", r"usd|us\s*\$|u\s*\$\s*s|u\.s\.d\.?|dolares|dolar|dlls|dll|dls"),
    ("MXN", r"mxn|mxp|mx\s*\$|pesos"),
    ("EUR", r"eur|euros?|€"),
    ("CAD", r"cad|c\s*\$"),
    ("GBP", r"gbp|£"),
    ("JPY", r"jpy|¥|yenes|yen"),
    ("CHF", r"chf"),
    ("CNY", r"cny|rmb|yuanes|yuan"),
    ("BRL", r"brl|r\s*\$|reales"),
    ("COP", r"cop"),
    ("ARS", r"ars"),
    ("CLP", r"clp"),
)
_MONEDA = re.compile("|".join(f"(?P<{codigo}>(?<![a-z0-9])(?:{patron})(?![a-z]))"
                              for codigo, patron in _MONEDAS))
# The literal text of an Excel number format: a quoted run, the symbol of a
# ``[$SYM-LOCALE]`` section, or one escaped character. Everything else in a
# format is the numeric pattern and says nothing about currency.
_LITERAL_FORMATO = re.compile(r'"([^"]*)"|\[\$([^\]-]*)[^\]]*\]|\\(.)')
_DINERO = re.compile(r"(precio|valor|importe|monto|venta|costo|asking|\$|mxn|pesos|usd|dolar)")
_POR_M2 = re.compile(r"(m2|/\s*m\b|por m|unitario|metro cuadrado|\$ m)")
_AREA = re.compile(r"(superficie|area|metros|m2|hectar|\bha\b|extension|tamano)")
_HA = re.compile(r"(hectar|\bha\b)")


# Contact details and free-text notes: never a candidate field, never sampled
# for automatic assistance.
_SENSIBLE = re.compile(
    r"(contacto|telefono|tel\b|celular|whats|correo|e ?mail|mail|propietario|dueno|owner|"
    r"contact|nota|observa|coment|rfc|curp|vendedor|broker|asesor)")


def sensible(etiqueta: Any) -> bool:
    return bool(_SENSIBLE.search(normalizar(etiqueta)))


def monedas(etiqueta: Any, valores: tuple[str, ...]) -> tuple[str, ...]:
    """Every explicit currency ("USD", "MXN", "EUR"...) the text declares.

    `valores` should be every text cell of the column, not a sample: one
    "MXN 1,200,000" anywhere in a dollar column is a conflict, and a column
    mixing two currencies has to show both.
    """
    vistas: list[str] = []
    for texto in (etiqueta or "", *valores):
        for encontrada in _MONEDA.finditer(fold(texto)):
            if encontrada.lastgroup not in vistas:
                vistas.append(str(encontrada.lastgroup))
    return tuple(vistas)


def moneda_formato(formato: Any) -> str | None:
    """The currency an Excel number format explicitly declares, or None.

    Only the format's literal text counts: quoted runs (``"USD "#,##0.00``),
    the symbol of a currency/locale section (``[$€-2]``) and escaped
    characters (``\\$``). The numeric pattern itself is never matched, so
    ``#,##0.00`` and a date format declare nothing. A bare "$" -- including
    ``[$$-409]``, a dollar sign with a regional setting -- declares nothing
    either: the currency is then asked, never inferred. Formatting is
    evidence about the amount, never permission to convert it.
    """
    if not isinstance(formato, str) or not formato:
        return None
    literales = [texto for encontrado in _LITERAL_FORMATO.finditer(formato)
                 for texto in encontrado.groups() if texto]
    if not literales:
        return None
    encontrada = _MONEDA.search(fold(" ".join(literales)))
    return str(encontrada.lastgroup) if encontrada else None


def nombre_moneda(codigos: Sequence[str]) -> str:
    """How to name a column's currencies in a message meant for the user."""
    if not codigos:
        return ""
    if len(codigos) == 1:
        return {"USD": "dólares (USD)", "MXN": "pesos (MXN)"}.get(codigos[0], codigos[0])
    return ", ".join(codigos[:-1]) + f" y {codigos[-1]}"


def moneda_de_valor(texto: Any) -> str | None:
    """The currency a single cell names ("USD", "pesos"), or None."""
    encontradas = monedas("", (str(texto),)) if texto is not None else ()
    return encontradas[0] if len(encontradas) == 1 else None


def problema_moneda(codigos: Sequence[str]) -> str | None:
    """Why these explicit currencies cannot be one price column's, or None."""
    no_soportadas = [c for c in codigos if c not in SOPORTADAS]
    if no_soportadas:
        return f"está en {nombre_moneda(no_soportadas)} y ARA sólo maneja precios en USD o MXN"
    if len(codigos) > 1:
        return f"mezcla {nombre_moneda(codigos)} en la misma columna"
    return None


def respaldo(campo: str, columna: Any) -> str | None:
    """Why the column CANNOT be this field, or None when the evidence agrees.

    `columna` is a perfil.Columna. Text fields need text; numbers need numbers;
    prices, areas and coordinates additionally need their header or values to
    say so -- a number alone never decides between a price, an area and a
    coordinate.
    """
    if campo in (EXTRA, IGNORAR):
        return None
    if columna.no_vacias == 0:
        return "la columna está vacía"
    etiqueta = normalizar(columna.etiqueta)
    numericos = columna.numericas / columna.no_vacias

    if campo in TEXTO:
        return "casi todos sus valores son números" if numericos > 0.8 and campo == "terreno" else None
    if numericos < 0.8:
        return "sus valores no son números"
    if campo in ("asking_price", "asking_m2"):
        problema = problema_moneda(columna.monedas)
        if problema:
            return problema
        if not _DINERO.search(etiqueta):
            return "el encabezado no indica que sea un precio"
        por_m2 = bool(_POR_M2.search(etiqueta))
        if campo == "asking_m2" and not por_m2:
            return "el encabezado no indica que sea un precio por m²"
        if campo == "asking_price" and por_m2:
            return "el encabezado indica un precio por m², no un total"
    if campo in ("superficie_m2", "superficie_ha"):
        if not _AREA.search(etiqueta):
            return "el encabezado no indica que sea una superficie"
        if campo == "superficie_ha" and not _HA.search(etiqueta):
            return "el encabezado no indica hectáreas"
        if campo == "superficie_m2" and _HA.search(etiqueta):
            return "el encabezado indica hectáreas, no m²"
    if campo in ("afectaciones_pct", "afectaciones_m2") and "afect" not in etiqueta:
        return "el encabezado no menciona afectaciones"
    if campo == "lat" and not _en_rango(columna, MEXICO_LAT):
        return "sus valores no caen en el rango de latitud de México"
    if campo == "lon" and not _en_rango(columna, MEXICO_LON):
        return "sus valores no caen en el rango de longitud de México"
    if campo == "id_origen" and not columna.enteros:
        return "sus valores no son números enteros"
    return None


def _en_rango(columna: Any, rango: tuple[float, float]) -> bool:
    """Most numeric values inside the range (a few bad rows are the validator's job)."""
    return bool(columna.numericas > 0 and columna.en_rango(rango) >= 0.8)

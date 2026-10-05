"""Interpret a table: which one, which header, what each column is, and what
still has to be asked.

Order of trust, highest last so it wins:

    default      every column is kept as additional data
    saved format a confirmed format whose headers all appear in this file
    name/alias   exact legacy names, then curated synonyms
    values       X/Y and Norte/Este, only when their values agree
    automatic    an AI proposal, only for columns nothing above settled, and
                 only where the column's own header/values support it
    user         explicit answers and corrections -- always final

Genuine ambiguity -- two candidate columns for one field, a "Valor" that could
be a total or a price per m², coordinates whose values contradict their
names, a number like 1,234, prices whose currency the file does not state --
becomes a plain question with real sample values. No confidence score settles
it.

The prices of one table share one currency, USD or MXN. An explicit marker in
the file (US$, USD, MXN, a «Moneda» column, an Excel format such as
``"USD "#,##0``) decides it and beats a saved format; otherwise a saved
format's confirmed currency, otherwise the user is asked. Magnitudes and
geography never decide it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..csv_numbers import parse_number
from ..normalize import clean_text, fold
from ..validation import MEXICO_LAT, MEXICO_LON
from . import campos as C  # noqa: N812 - short alias for a vocabulary module
from .perfil import Columna, numero_aproximado, perfilar, texto_de
from .plan import ImportPlan
from .rejilla import Hoja, Rejilla

BUSQUEDA_ENCABEZADO = 50      # rows scanned to choose a header automatically
BUSQUEDA_AMPLIA = 2_000       # rows scanned when nothing in that window looks like one
MAX_PREGUNTAS_COLUMNA = 3
CLAVE = ("asking_price", "superficie_m2", "superficie_ha", "lat", "lon", "asking_m2")
HOJA_HISTORICA = fold("Registro Análisis")
_OPCIONES_PRECIO = C.PRECIOS


@dataclass(frozen=True)
class Opcion:
    etiqueta: str
    decision: Mapping[str, Any]   # merged into the draft's decisions when chosen
    detalle: str = ""


@dataclass(frozen=True)
class Pregunta:
    id: str
    texto: str
    detalle: str
    opciones: tuple[Opcion, ...]
    sugerida: int | None = None


@dataclass(frozen=True)
class Origen:
    fuente: str    # usuario | formato | nombre | alias | valores | ia | predeterminado | pendiente
    motivo: str


@dataclass(frozen=True)
class Interpretacion:
    sha256: str
    hoja: Hoja
    hojas: tuple[str, ...]           # plausible tables, best first
    encabezado: int
    encabezados: tuple[int, ...]     # header candidates offered in corrections
    columnas: tuple[Columna, ...]
    asignaciones: Mapping[str, str]
    origenes: Mapping[str, Origen]
    decimal: str | None
    preguntas: tuple[Pregunta, ...]
    avisos: tuple[str, ...]
    necesita_ia: bool
    formato: Mapping[str, Any] | None
    ia_descartadas: int = 0
    moneda: str | None = None        # the prices' currency, once settled
    moneda_origen: str = ""          # archivo | usuario | formato
    # Columns kept out of price fields only because of their currency: never
    # remembered as a deliberate choice in a saved format.
    excluidas_moneda: tuple[str, ...] = ()

    def plan(self, excluir: Sequence[int] = (), incluir: Sequence[int] = ()) -> ImportPlan | None:
        if self.preguntas:
            return None
        return ImportPlan(
            sha256=self.sha256, hoja_id=self.hoja.id, encabezado=self.encabezado,
            decimal=self.decimal or "dot", asignaciones=dict(self.asignaciones),
            excluir=tuple(excluir), incluir=tuple(incluir),
            origenes={k: v.fuente for k, v in self.origenes.items()},
            moneda=self.moneda, moneda_origen=self.moneda_origen,
        )


def fusionar(decisiones: Mapping[str, Any], parche: Mapping[str, Any]) -> dict[str, Any]:
    """Combine decisions: column choices and absent fields accumulate."""
    nuevo = dict(decisiones)
    for clave, valor in parche.items():
        if clave == "columnas":
            nuevo["columnas"] = {**decisiones.get("columnas", {}), **valor}
        elif clave == "sin_campo":
            nuevo["sin_campo"] = sorted(set(decisiones.get("sin_campo", [])) | set(valor))
        elif clave in ("excluir", "incluir"):
            nuevo[clave] = sorted(set(valor))
        else:
            nuevo[clave] = valor
    # A row cannot be kept and dropped at once: naming it on one list takes it
    # off the other, so the newest decision about that row is the one that holds.
    for clave, otra in (("excluir", "incluir"), ("incluir", "excluir")):
        if clave in parche and otra not in parche:
            nuevo[otra] = sorted(set(nuevo.get(otra, [])) - set(parche[clave]))
    return nuevo


def interpretar(rejilla: Rejilla, decisiones: Mapping[str, Any], formatos: Sequence[Mapping[str, Any]] = (),
                propuesta_ia: Mapping[str, Any] | None = None) -> Interpretacion:
    preguntas: list[Pregunta] = []
    hoja, hojas = _elegir_hoja(rejilla, decisiones, formatos, preguntas)
    encabezados = _candidatos_encabezado(hoja, formatos)
    encabezado = decisiones.get("encabezado")
    if not isinstance(encabezado, int) or not 0 <= encabezado < len(hoja.filas):
        encabezado = encabezados[0] if encabezados else 0
    columnas = perfilar(hoja, encabezado)
    por_id = {c.id: c for c in columnas}

    asign: dict[str, str] = {c.id: C.EXTRA for c in columnas}
    orig: dict[str, Origen] = {
        c.id: Origen("predeterminado", "Encabezado no reconocido: se conserva como dato adicional.")
        for c in columnas}
    avisos: list[str] = []

    grupos_repetidos: list[tuple[list[Columna], list[str]]] = []
    dudosas: list[Columna] = []
    formato = _aplicar_formato(columnas, formatos, asign, orig, avisos, grupos_repetidos, dudosas)
    retenidas = {c.id for cols, _ in grupos_repetidos for c in cols}
    pendientes = _por_nombre(columnas, asign, orig, retenidas)
    _coordenadas(columnas, asign, orig, avisos)
    excluidas_moneda = _monedas_no_admitidas(columnas, asign, orig, avisos)
    necesita_ia = formato is None and _faltan_claves(columnas, asign, orig)

    sugeridas: dict[str, str] = {}
    descartadas = _aplicar_ia(propuesta_ia, por_id, asign, orig, pendientes, sugeridas)
    usuario = decisiones.get("columnas", {})
    for col_id, destino in usuario.items():
        if col_id in asign and destino in C.DESTINOS:
            asign[col_id] = destino
            orig[col_id] = Origen("usuario", "Elegido en la revisión.")
            pendientes.pop(col_id, None)

    sin_campo = set(decisiones.get("sin_campo", []))
    _preguntas_formato_repetidas(grupos_repetidos, orig, preguntas)
    _preguntas_formato_precio(dudosas, orig, formato, preguntas)
    _preguntas_duplicados(columnas, asign, orig, preguntas)
    _preguntas_precio(pendientes, asign, sugeridas, preguntas)
    _pregunta_coordenadas(por_id, asign, orig, decisiones, preguntas)
    _pregunta_nombre(columnas, asign, sin_campo, preguntas)
    _preguntas_desconocidas(columnas, asign, orig, sin_campo, sugeridas, preguntas)
    decimal = _pregunta_decimal(hoja, encabezado, columnas, asign, decisiones, formato, preguntas, avisos)
    moneda, moneda_origen = _moneda(columnas, asign, orig, decisiones, formato, preguntas, avisos)

    _avisos_generales(hoja, columnas, asign, orig, avisos)
    return Interpretacion(
        sha256=rejilla.sha256, hoja=hoja, hojas=hojas, encabezado=encabezado,
        encabezados=tuple(encabezados), columnas=columnas, asignaciones=asign, origenes=orig,
        decimal=decimal, preguntas=tuple(preguntas), avisos=tuple(avisos),
        necesita_ia=necesita_ia, formato=formato, ia_descartadas=descartadas,
        moneda=moneda, moneda_origen=moneda_origen,
        excluidas_moneda=tuple(c for c in excluidas_moneda if asign[c] == C.EXTRA),
    )


# ------------------------------------------------------------ table/header

def _puntaje(fila: tuple[Any, ...]) -> int:
    reconocidas = textos = numeros = 0
    for celda in fila:
        if clean_text(celda) is None:
            continue
        if numero_aproximado(celda) is not None:
            numeros += 1
            continue
        textos += 1
        clave = C.normalizar(celda)
        if C.por_nombre(celda)[0] or clave in C.EJES_X | C.EJES_Y | C.NORTE | C.ESTE:
            reconocidas += 1
    return reconocidas * 10 + (textos if textos >= 2 and numeros == 0 else 0)


def _firma(fila: tuple[Any, ...]) -> set[tuple[str, int]]:
    vistas: dict[str, int] = {}
    firma = set()
    for celda in fila:
        clave = C.normalizar(clean_text(celda))
        if clave:
            vistas[clave] = vistas.get(clave, 0) + 1
            firma.add((clave, vistas[clave]))
    return firma


def _requeridas(formato: Mapping[str, Any]) -> set[tuple[str, int]]:
    return {(c, o) for c, o, d in formato["asignaciones"] if d in C.CAMPOS}


def _candidatos_encabezado(hoja: Hoja, formatos: Sequence[Mapping[str, Any]]) -> list[int]:
    """Header rows, best first. The search is bounded; the choice is not.

    The first rows are where a header normally is, so that is where the search
    stops. When none of them looks like one -- a long preamble of notes, a
    title page -- settling for row 1 would hide the real table, so the search
    widens instead of guessing.
    """
    puntajes = _puntuar_filas(hoja, formatos, min(len(hoja.filas), BUSQUEDA_ENCABEZADO))
    if not any(puntaje > 0 for puntaje, _ in puntajes) and len(hoja.filas) > BUSQUEDA_ENCABEZADO:
        puntajes = _puntuar_filas(hoja, formatos, min(len(hoja.filas), BUSQUEDA_AMPLIA))
    ordenados = [-i for _, i in sorted(puntajes, reverse=True)]
    return ordenados or [0]


def _puntuar_filas(hoja: Hoja, formatos: Sequence[Mapping[str, Any]],
                   limite: int) -> list[tuple[int, int]]:
    puntajes = []
    for i in range(limite):
        puntaje = _puntaje(hoja.filas[i])
        firma = _firma(hoja.filas[i])
        if any(_requeridas(f) and _requeridas(f) <= firma for f in formatos):
            puntaje += 1000
        puntajes.append((puntaje, -i))
    return puntajes


def _elegir_hoja(rejilla: Rejilla, decisiones: Mapping[str, Any], formatos: Sequence[Mapping[str, Any]],
                 preguntas: list[Pregunta]) -> tuple[Hoja, tuple[str, ...]]:
    puntuadas = []
    for hoja in rejilla.hojas:
        mejor = _candidatos_encabezado(hoja, formatos)[0]
        puntaje = _puntaje(hoja.filas[mejor]) + (
            1000 if any(_requeridas(f) and _requeridas(f) <= _firma(hoja.filas[mejor]) for f in formatos) else 0)
        filas = len(hoja.filas) - mejor - 1
        if puntaje > 0 and filas >= 1:
            puntuadas.append((puntaje, filas, hoja))
    puntuadas.sort(key=lambda t: (t[0], t[1]), reverse=True)
    if not puntuadas:
        puntuadas = [(0, len(h.filas), h) for h in rejilla.hojas]
    ids = tuple(h.id for _, _, h in puntuadas)

    elegida = decisiones.get("hoja")
    if elegida in {h.id for h in rejilla.hojas}:
        return rejilla.hoja(elegida), ids
    historica = [h for _, _, h in puntuadas if fold(h.nombre) == HOJA_HISTORICA]
    if historica:
        return historica[0], ids
    fuertes = [t for t in puntuadas if t[0] >= 20]
    # A saved format that matches exactly one table settles it; otherwise two
    # strong candidates are the user's choice.
    un_formato = bool(fuertes) and fuertes[0][0] >= 1000 and (len(fuertes) < 2 or fuertes[1][0] < 1000)
    if len(fuertes) >= 2 and not un_formato:
        es_csv = all(h.separador is not None for _, _, h in fuertes)
        preguntas.append(Pregunta(
            id="hoja",
            texto="¿Cómo se separan las columnas del archivo?" if es_csv
            else f"Encontramos {len(fuertes)} tablas de terrenos. ¿Cuál quieres importar?",
            detalle="Se importa una tabla por vez.",
            opciones=tuple(Opcion(_nombre_hoja(h), {"hoja": h.id}, _vista_hoja(h)) for _, _, h in fuertes),
            sugerida=0,
        ))
    return puntuadas[0][2], ids


SEPARADORES = {",": "comas", ";": "punto y coma", "\t": "tabulaciones"}


def _nombre_hoja(hoja: Hoja) -> str:
    if hoja.separador in SEPARADORES:
        return f"Separadas por {SEPARADORES[hoja.separador]}"
    return f"Hoja «{hoja.nombre}» ({len(hoja.filas)} filas)"


def _vista_hoja(hoja: Hoja) -> str:
    fila = hoja.filas[_candidatos_encabezado(hoja, ())[0]]
    return " | ".join(texto_de(c) for c in fila[:6] if clean_text(c) is not None)


# -------------------------------------------------------------- assignments

def _aplicar_formato(columnas: Sequence[Columna], formatos: Sequence[Mapping[str, Any]],
                     asign: dict[str, str], orig: dict[str, Origen], avisos: list[str],
                     grupos_repetidos: list[tuple[list[Columna], list[str]]],
                     dudosas: list[Columna]) -> Mapping[str, Any] | None:
    """Apply the confirmed format whose headers all appear here.

    Several compatible formats that disagree about this file are not settled
    by recency or name: none is applied and the columns are interpreted afresh.

    Uniquely named columns are matched by name, whatever their order. Columns
    that share a name are different: "the second «Precio»" only says where a
    column is, not that it still means what it meant last time -- the two may
    have been swapped. When the format gave such columns different meanings,
    they are withheld and returned in `grupos_repetidos` to be reconfirmed.

    A format saved before prices carried a currency (it has no ``moneda``)
    may have kept a price column as additional data only because it was in
    dollars, which that version refused. That choice is not reapplied
    silently: the column is returned in `dudosas` and asked about again.
    """
    firma = {(c.clave, c.ocurrencia) for c in columnas if c.clave}
    compatibles = [f for f in formatos if _requeridas(f) and _requeridas(f) <= firma]
    if not compatibles:
        return None
    lecturas = [{(c, o): d for c, o, d in f["asignaciones"]} for f in compatibles]
    if any(lec != lecturas[0] for lec in lecturas[1:]):
        avisos.append("Varios formatos guardados coinciden con este archivo y no están de acuerdo; "
                      "se interpretó sin aplicar ninguno.")
        return None
    formato = compatibles[0]
    por_clave: dict[str, list[Columna]] = {}
    for col in columnas:
        if col.clave:
            por_clave.setdefault(col.clave, []).append(col)
    for col in columnas:
        destino = lecturas[0].get((col.clave, col.ocurrencia))
        if destino is None:
            continue
        if destino == C.EXTRA and "moneda" not in formato and C.por_nombre(col.etiqueta)[0] in C.PRECIOS:
            dudosas.append(col)
            continue
        hermanas = por_clave.get(col.clave, [col])
        destinos = [lecturas[0].get((h.clave, h.ocurrencia), C.EXTRA) for h in hermanas]
        if len(hermanas) > 1 and any(d in C.CAMPOS for d in destinos) and len(set(destinos)) > 1:
            if col is hermanas[0]:
                grupos_repetidos.append((hermanas, destinos))
            orig[col.id] = Origen("pendiente", f"Hay varias columnas «{col.etiqueta}»; confirma cuál es cuál.")
            continue
        asign[col.id] = destino
        orig[col.id] = Origen("formato", f"Formato guardado «{formato['nombre']}».")
    return formato


def _por_nombre(columnas: Sequence[Columna], asign: dict[str, str],
                orig: dict[str, Origen], retenidas: set[str]) -> dict[str, Columna]:
    """Recognized names; returns the price-like columns that must be asked about."""
    pendientes: dict[str, Columna] = {}
    for col in columnas:
        if orig[col.id].fuente == "formato" or col.id in retenidas:
            continue
        campo, como = C.por_nombre(col.etiqueta)
        if campo:
            asign[col.id] = campo
            orig[col.id] = Origen(como, f"«{col.etiqueta}» es un nombre conocido de {C.CAMPOS[campo][0]}.")
        elif col.clave in C.AMBIGUOS_PRECIO and col.numericas:
            pendientes[col.id] = col
            orig[col.id] = Origen("pendiente", "Puede ser un precio total o un precio por m².")
    return pendientes


def _coordenadas(columnas: Sequence[Columna], asign: dict[str, str], orig: dict[str, Origen],
                 avisos: list[str]) -> None:
    """X/Y and Norte/Este: never by name alone -- the values have to agree."""
    def buscar(nombres: frozenset[str]) -> Columna | None:
        return next((c for c in columnas if c.clave in nombres and orig[c.id].fuente
                     in ("predeterminado", "pendiente")), None)

    for a, b, convencion in ((C.EJES_X, C.EJES_Y, "ara"), (C.NORTE, C.ESTE, "norte")):
        col_a, col_b = buscar(a), buscar(b)
        if not col_a or not col_b:
            continue
        a_lat = col_a.en_rango(MEXICO_LAT) >= 0.8
        b_lon = col_b.en_rango(MEXICO_LON) >= 0.8
        a_lon = col_a.en_rango(MEXICO_LON) >= 0.8
        b_lat = col_b.en_rango(MEXICO_LAT) >= 0.8
        sin_valores = not col_a.numericas and not col_b.numericas
        if convencion == "ara" and (sin_valores or (a_lat and b_lon) or (a_lon and b_lat)):
            # ARA's convention stays the visible default; contradicting values
            # are raised as a question later, never silently swapped.
            asign[col_a.id], asign[col_b.id] = "lat", "lon"
            motivo = "Convención de ARA: X = latitud, Y = longitud."
            orig[col_a.id] = orig[col_b.id] = Origen("nombre", motivo)
        elif convencion == "norte" and a_lat and b_lon:
            asign[col_a.id], asign[col_b.id] = "lat", "lon"
            motivo = "Sus valores son latitudes y longitudes de México."
            orig[col_a.id] = orig[col_b.id] = Origen("valores", motivo)
        elif col_a.numericas or col_b.numericas:
            motivo = "No parecen latitud/longitud; esta versión no convierte coordenadas."
            orig[col_a.id] = orig[col_b.id] = Origen("valores", motivo)
            avisos.append(f"«{col_a.visible}» y «{col_b.visible}» no parecen latitud y longitud "
                          "(¿coordenadas proyectadas/UTM?). Se conservan como datos adicionales; "
                          "esta versión no convierte coordenadas.")


def _monedas_no_admitidas(columnas: Sequence[Columna], asign: dict[str, str], orig: dict[str, Origen],
                          avisos: list[str]) -> list[str]:
    """Prices in an unsupported currency, or mixing two, stay additional data.

    Saved formats included. Returns the ids of the columns set aside, so that
    a saved format does not remember the exclusion as a deliberate choice.
    """
    apartadas = []
    for col in columnas:
        problema = C.problema_moneda(col.monedas)
        posible_precio = asign[col.id] in _OPCIONES_PRECIO or (
            orig[col.id].fuente in ("predeterminado", "pendiente")
            and col.no_vacias and col.numericas / col.no_vacias >= 0.5)
        # A text column (an address, a note) that merely mentions a currency is not a price.
        if problema and posible_precio and orig[col.id].fuente in (
                "predeterminado", "pendiente", "nombre", "alias", "formato"):
            # Values formatted in Excel look like bare numbers, so say so.
            segun = " según el formato de celda de Excel" if col.monedas_formato else ""
            asign[col.id] = C.EXTRA
            orig[col.id] = Origen("valores", f"{problema[0].upper()}{problema[1:]}{segun}.")
            avisos.append(f"«{col.visible}» {problema}{segun}. No se convierten monedas, así que se "
                          "conserva como dato adicional con su importe original.")
            apartadas.append(col.id)
    return apartadas


def _moneda(columnas: Sequence[Columna], asign: dict[str, str], orig: dict[str, Origen],
            decisiones: Mapping[str, Any], formato: Mapping[str, Any] | None,
            preguntas: list[Pregunta], avisos: list[str]) -> tuple[str | None, str]:
    """The one currency of this table's prices, and where it came from.

    Explicit markers in the file win -- over a saved format and over an
    earlier answer -- so a template remembered as USD cannot relabel a file
    that says MXN. Two explicit currencies are a conflict: the prices are kept
    as additional data rather than guessing which one applies.
    """
    precios = [c for c in columnas if asign[c.id] in C.PRECIOS]
    if not precios:
        return None, ""
    declaradas = [m for c in precios for m in c.monedas]
    declaradas += [m for c in columnas if c.clave in C.CLAVES_MONEDA for m in c.monedas]
    explicitas = tuple(dict.fromkeys(declaradas))
    if len(explicitas) > 1:
        for col in precios:
            asign[col.id] = C.EXTRA
            orig[col.id] = Origen("valores", f"Los precios del archivo mezclan {C.nombre_moneda(explicitas)}.")
        avisos.append(f"Los precios del archivo mezclan {C.nombre_moneda(explicitas)}; una tabla se importa "
                      "con una sola moneda. Se conservan como datos adicionales con su importe original. "
                      "Separa las monedas en archivos distintos para importarlos como precio.")
        return None, ""
    elegida = decisiones.get("moneda")
    if explicitas:
        if elegida in C.SOPORTADAS and elegida != explicitas[0]:
            avisos.append(f"El archivo indica {C.nombre_moneda(explicitas)}; se respeta lo que dice el archivo.")
        return explicitas[0], "archivo"
    if elegida in C.SOPORTADAS:
        return str(elegida), "usuario"
    if formato and formato.get("moneda") in C.SOPORTADAS:
        return str(formato["moneda"]), "formato"
    ejemplos = " · ".join(f"«{c.visible}»: {', '.join(c.muestras[:3]) or 'vacía'}" for c in precios)
    preguntas.append(Pregunta(
        id="moneda",
        texto="¿En qué moneda están los precios?",
        detalle=f"Valores de ejemplo — {ejemplos}. El archivo no lo indica: el signo «$» se usa igual para "
                "dólares y para pesos, y ARA no adivina la moneda por el tamaño de los importes ni por la "
                "ubicación. Los importes se guardan tal cual; no se convierten.",
        opciones=(
            Opcion(C.NOMBRE_MONEDA["USD"], {"moneda": "USD"}),
            Opcion(C.NOMBRE_MONEDA["MXN"], {"moneda": "MXN"}),
            Opcion("No importar los precios: conservarlos como datos adicionales",
                   {"columnas": {c.id: C.EXTRA for c in precios}}),
        ),
        sugerida=None))
    return None, ""


def _faltan_claves(columnas: Sequence[Columna], asign: Mapping[str, str], orig: Mapping[str, Origen]) -> bool:
    asignados = set(asign.values())
    if "terreno" not in asignados:
        return True
    desconocidas = [c for c in columnas if orig[c.id].fuente == "predeterminado" and c.no_vacias
                    and c.numericas / c.no_vacias >= 0.8 and not C.sensible(c.etiqueta)]
    return bool(desconocidas) and not set(CLAVE) <= asignados


def _aplicar_ia(propuesta: Mapping[str, Any] | None, por_id: Mapping[str, Columna], asign: dict[str, str],
                orig: dict[str, Origen], pendientes: Mapping[str, Columna], sugeridas: dict[str, str]) -> int:
    """Apply what the automatic proposal can back up with this file's evidence.

    Never over a name, a saved format or the user; never to settle a price
    ambiguity; a suggestion the column's own header/values do not support is
    reduced to a suggested answer to a question, not applied.
    """
    if not propuesta:
        return 0
    descartadas = 0
    ocupados = {d for c, d in asign.items() if d in C.CAMPOS}
    for item in propuesta.get("asignaciones", []):
        col, campo = por_id.get(item.get("columna")), item.get("campo")
        if col is None or campo not in C.CAMPOS:
            continue
        if col.id in pendientes:
            sugeridas[col.id] = campo
            continue
        if orig[col.id].fuente != "predeterminado" or campo in ocupados:
            descartadas += 1
            continue
        if C.respaldo(campo, col) is None:
            asign[col.id] = campo
            orig[col.id] = Origen("ia", str(item.get("motivo") or "Sugerencia automática.")[:200])
            ocupados.add(campo)
        else:
            sugeridas[col.id] = campo
            descartadas += 1
    return descartadas


# ---------------------------------------------------------------- questions

def _muestra(col: Columna) -> str:
    valores = " · ".join(col.muestras[:4]) or "vacía"
    return f"{col.letra}: {valores}"


def _preguntas_formato_repetidas(grupos: Sequence[tuple[list[Columna], list[str]]],
                                 orig: Mapping[str, Origen], preguntas: list[Pregunta]) -> None:
    """Reconfirm same-named columns a saved format gave different meanings.

    Only these columns are asked about; everything else still comes from the
    format. Nothing is preselected: which «Precio» is which is exactly what
    cannot be known from the name, and magnitudes do not settle it either.
    """
    for columnas, destinos in grupos:
        if all(orig[c.id].fuente == "usuario" for c in columnas):
            continue
        etiqueta = columnas[0].etiqueta
        def lectura(orden: Sequence[str], columnas: Sequence[Columna] = columnas) -> str:
            return "; ".join(f"«{c.visible}» ({c.letra}) = {C.ETIQUETA_DESTINO[d]}" for c, d in zip(columnas, orden))
        detalle = " · ".join(f"«{c.visible}»: {', '.join(c.muestras[:3]) or 'vacía'}" for c in columnas)
        todas_extra = {"columnas": {c.id: C.EXTRA for c in columnas}}
        if len(columnas) == 2:
            invertido = [destinos[1], destinos[0]]
            opciones = (
                Opcion(f"Como la vez anterior: {lectura(destinos)}",
                       {"columnas": {c.id: d for c, d in zip(columnas, destinos)}}),
                Opcion(f"Al revés: {lectura(invertido)}",
                       {"columnas": {c.id: d for c, d in zip(columnas, invertido)}}),
                Opcion("Conservar ambas como datos adicionales", todas_extra),
            )
            preguntas.append(Pregunta(
                id=f"formato-repetidas:{columnas[0].clave}",
                texto=f"El archivo tiene {len(columnas)} columnas «{etiqueta}». ¿Cuál es cuál?",
                detalle=f"El formato guardado distingue estas columnas sólo por su orden, y el orden "
                        f"pudo cambiar. Valores de ejemplo — {detalle}.",
                opciones=opciones, sugerida=None))
            continue
        campos = sorted({d for d in destinos if d in C.CAMPOS})
        for col in columnas:
            if orig[col.id].fuente == "usuario":
                continue
            por_columna = tuple(Opcion(C.CAMPOS[d][0], {"columnas": {col.id: d}}) for d in campos) + (
                Opcion(C.ETIQUETA_DESTINO[C.EXTRA], {"columnas": {col.id: C.EXTRA}}),)
            preguntas.append(Pregunta(
                id=f"columna:{col.id}",
                texto=f"¿Qué contiene la columna «{col.visible}» ({col.letra})?",
                detalle=f"Hay {len(columnas)} columnas «{etiqueta}»; el formato guardado no puede saber "
                        f"cuál es cuál. Valores de ejemplo — {_muestra(col)}.",
                opciones=por_columna, sugerida=None))


def _preguntas_formato_precio(dudosas: Sequence[Columna], orig: Mapping[str, Origen],
                              formato: Mapping[str, Any] | None, preguntas: list[Pregunta]) -> None:
    """Ask again about price columns an older saved format kept as extra data."""
    for col in dudosas:
        campo = C.por_nombre(col.etiqueta)[0]
        if formato is None or campo is None or orig[col.id].fuente == "usuario":
            continue
        nombre = C.CAMPOS[campo][0].lower()
        preguntas.append(Pregunta(
            id=f"columna:{col.id}",
            texto=f"¿Importar «{col.visible}» como {nombre}?",
            detalle=f"El formato guardado «{formato['nombre']}» la conservaba como dato adicional. Las "
                    "versiones anteriores de ARA hacían eso con los precios en dólares, porque sólo "
                    f"aceptaban pesos. Valores de ejemplo — {_muestra(col)}.",
            opciones=(
                Opcion(f"Sí, es el {nombre}", {"columnas": {col.id: campo}}),
                Opcion("No, conservarla como dato adicional", {"columnas": {col.id: C.EXTRA}}),
            ),
            sugerida=0))


def _preguntas_duplicados(columnas: Sequence[Columna], asign: dict[str, str], orig: dict[str, Origen],
                          preguntas: list[Pregunta]) -> None:
    por_campo: dict[str, list[Columna]] = {}
    for col in columnas:
        if asign[col.id] in C.CAMPOS:
            por_campo.setdefault(asign[col.id], []).append(col)
    for campo, cols in por_campo.items():
        if len(cols) < 2:
            continue
        del_usuario = [c for c in cols if orig[c.id].fuente == "usuario"]
        if del_usuario:
            for c in cols:
                if c is not del_usuario[-1]:
                    asign[c.id] = C.EXTRA
                    orig[c.id] = Origen("predeterminado", "Otra columna ocupa ese dato según tu respuesta.")
            continue
        etiqueta = C.CAMPOS[campo][0]
        opciones = [Opcion(f"«{c.visible}»", {"columnas": {o.id: (campo if o is c else C.EXTRA) for o in cols}},
                           _muestra(c)) for c in cols]
        opciones.append(Opcion("Ninguna de estas", {"columnas": {o.id: C.EXTRA for o in cols}}))
        preguntas.append(Pregunta(
            id=f"duplicado:{campo}", texto=f"¿Cuál columna contiene el dato «{etiqueta}»?",
            detalle="Varias columnas parecen tener ese dato; la otra se conserva como dato adicional.",
            opciones=tuple(opciones), sugerida=0))


def _preguntas_precio(pendientes: Mapping[str, Columna], asign: Mapping[str, str],
                      sugeridas: Mapping[str, str], preguntas: list[Pregunta]) -> None:
    ocupados = {d for d in asign.values() if d in C.CAMPOS}
    for col in pendientes.values():
        if asign[col.id] != C.EXTRA:
            continue
        destinos = [d for d in _OPCIONES_PRECIO if d not in ocupados]
        if not destinos:
            continue
        opciones = [Opcion(C.CAMPOS[d][0], {"columnas": {col.id: d}}) for d in destinos]
        opciones.append(Opcion(C.ETIQUETA_DESTINO[C.EXTRA], {"columnas": {col.id: C.EXTRA}}))
        sugerida = next((i for i, d in enumerate(destinos) if d == sugeridas.get(col.id)), None)
        preguntas.append(Pregunta(
            id=f"columna:{col.id}", texto=f"¿Qué representa la columna «{col.visible}»?",
            detalle=f"Valores de ejemplo — {_muestra(col)}. Un precio total y un precio por m² "
                    "no se pueden distinguir sólo por los números.",
            opciones=tuple(opciones), sugerida=sugerida))


def _pregunta_coordenadas(por_id: Mapping[str, Columna], asign: Mapping[str, str], orig: Mapping[str, Origen],
                          decisiones: Mapping[str, Any], preguntas: list[Pregunta]) -> None:
    lat = next((por_id[c] for c, d in asign.items() if d == "lat"), None)
    lon = next((por_id[c] for c, d in asign.items() if d == "lon"), None)
    if not lat or not lon or decisiones.get("coordenadas") == "confirmadas":
        return
    if orig[lat.id].fuente == "usuario" and orig[lon.id].fuente == "usuario":
        return
    if not (lat.en_rango(MEXICO_LON) >= 0.8 and lon.en_rango(MEXICO_LAT) >= 0.8):
        return
    confirmar = {"coordenadas": "confirmadas"}
    preguntas.append(Pregunta(
        id="coordenadas",
        texto=f"¿«{lat.visible}» es la latitud y «{lon.visible}» la longitud?",
        detalle=f"Los valores parecen al revés: «{lat.visible}» tiene {', '.join(lat.muestras[:2])} "
                f"(parecen longitudes) y «{lon.visible}» tiene {', '.join(lon.muestras[:2])} "
                "(parecen latitudes). En los archivos de ARA, X es la latitud y Y la longitud.",
        opciones=(
            Opcion(f"No: «{lat.visible}» es la longitud y «{lon.visible}» la latitud",
                   {"columnas": {lat.id: "lon", lon.id: "lat"}, **confirmar}),
            Opcion(f"Sí: «{lat.visible}» es la latitud (convención ARA)",
                   {"columnas": {lat.id: "lat", lon.id: "lon"}, **confirmar}),
            Opcion("No importarlas como coordenadas",
                   {"columnas": {lat.id: C.EXTRA, lon.id: C.EXTRA}, **confirmar}),
        ),
        sugerida=0))


def _pregunta_nombre(columnas: Sequence[Columna], asign: Mapping[str, str], sin_campo: set[str],
                     preguntas: list[Pregunta]) -> None:
    if "terreno" in asign.values() or "terreno" in sin_campo:
        return
    textos = [c for c in columnas if c.no_vacias and c.numericas / c.no_vacias < 0.5
              and not C.sensible(c.etiqueta)]
    opciones = [Opcion(f"«{c.visible}»", {"columnas": {c.id: "terreno"}}, _muestra(c)) for c in textos[:8]]
    opciones.append(Opcion("Ninguna: el archivo no tiene nombres", {"sin_campo": ["terreno"]}))
    preguntas.append(Pregunta(
        id="campo:terreno", texto="¿Cuál columna contiene el nombre del terreno?",
        detalle="Es el único dato obligatorio: sin nombre, un terreno no se puede guardar.",
        opciones=tuple(opciones), sugerida=0 if textos else None))


def _preguntas_desconocidas(columnas: Sequence[Columna], asign: Mapping[str, str], orig: Mapping[str, Origen],
                            sin_campo: set[str], sugeridas: Mapping[str, str], preguntas: list[Pregunta]) -> None:
    faltan = [d for d in CLAVE if d not in asign.values() and d not in sin_campo]
    if not faltan:
        return
    candidatas = [c for c in columnas if orig[c.id].fuente == "predeterminado" and asign[c.id] == C.EXTRA
                  and c.no_vacias and c.numericas / c.no_vacias >= 0.8 and not C.problema_moneda(c.monedas)
                  and not C.sensible(c.etiqueta)]
    for col in candidatas[:MAX_PREGUNTAS_COLUMNA]:
        respaldadas = [d for d in faltan if C.respaldo(d, col) is None]
        orden = respaldadas + [d for d in faltan if d not in respaldadas]
        opciones = [Opcion(C.CAMPOS[d][0], {"columnas": {col.id: d}}) for d in orden]
        opciones.append(Opcion(C.ETIQUETA_DESTINO[C.EXTRA], {"columnas": {col.id: C.EXTRA}}))
        preferida = sugeridas.get(col.id) or (respaldadas[0] if len(respaldadas) == 1 else None)
        sugerida = next((i for i, d in enumerate(orden) if d == preferida), None)
        preguntas.append(Pregunta(
            id=f"columna:{col.id}", texto=f"¿Qué contiene la columna «{col.visible}»?",
            detalle=f"Valores de ejemplo — {_muestra(col)}. Si no es ninguno de estos datos, "
                    "se conserva como dato adicional.",
            opciones=tuple(opciones), sugerida=sugerida))


def _pregunta_decimal(hoja: Hoja, encabezado: int, columnas: Sequence[Columna], asign: Mapping[str, str],
                      decisiones: Mapping[str, Any], formato: Mapping[str, Any] | None,
                      preguntas: list[Pregunta], avisos: list[str]) -> str | None:
    """The numeric convention for numbers written as text, or a question."""
    if decisiones.get("decimal") in ("dot", "comma"):
        return str(decisiones["decimal"])
    solo = {"dot": 0, "comma": 0}
    ejemplo: tuple[str, str, float, float] | None = None
    for col in columnas:
        campo = asign[col.id]
        if campo not in C.NUMERICOS:
            continue
        for fila in hoja.filas[encabezado + 1:]:
            celda = fila[col.posicion] if col.posicion < len(fila) else None
            if not isinstance(celda, str) or clean_text(celda) is None:
                continue
            punto, nota_p = parse_number(campo, celda, "dot")
            coma, nota_c = parse_number(campo, celda, "comma")
            mal_p, mal_c = nota_p is not None, nota_c is not None
            if campo in ("lat", "lon"):
                mal_p = mal_p or _fuera_de_grados(punto)
                mal_c = mal_c or _fuera_de_grados(coma)
            if not mal_p and mal_c:
                solo["dot"] += 1
            elif not mal_c and mal_p:
                solo["comma"] += 1
            elif not mal_p and not mal_c and punto != coma and ejemplo is None:
                ejemplo = (col.visible, celda.strip(), punto or 0.0, coma or 0.0)
    if solo["dot"] and not solo["comma"]:
        return "dot"
    if solo["comma"] and not solo["dot"]:
        return "comma"
    guardado = formato.get("decimal") if formato else None
    if not solo["dot"] and not solo["comma"]:
        if ejemplo is None:
            return guardado or "dot"
        if guardado:
            return str(guardado)
    if ejemplo is None and solo["dot"] and solo["comma"]:
        avisos.append("El archivo mezcla números con punto decimal y con coma decimal.")
    columna, texto, punto, coma = ejemplo or ("", "", 0.0, 0.0)
    preguntas.append(Pregunta(
        id="decimal",
        texto=(f"En «{columna}», ¿«{texto}» significa {_num(punto)} o {_num(coma)}?" if ejemplo
               else "¿Cómo están escritos los números del archivo?"),
        detalle="La misma regla se aplica a todos los números escritos como texto.",
        opciones=(
            Opcion("Punto decimal (1,234.56)", {"decimal": "dot"},
                   f"«{texto}» = {_num(punto)}" if ejemplo else ""),
            Opcion("Coma decimal (1.234,56)", {"decimal": "comma"},
                   f"«{texto}» = {_num(coma)}" if ejemplo else ""),
        ),
        sugerida=None))
    return None


def _fuera_de_grados(valor: float | None) -> bool:
    """No coordinate is outside ±180 degrees."""
    return valor is not None and not -180 <= valor <= 180


def _num(valor: float) -> str:
    """Plain digits, no grouping: 1250 and 1.25 cannot be misread."""
    return f"{valor:.6f}".rstrip("0").rstrip(".")


def _avisos_generales(hoja: Hoja, columnas: Sequence[Columna], asign: Mapping[str, str],
                      orig: Mapping[str, Origen], avisos: list[str]) -> None:
    if hoja.formulas_sin_valor:
        celdas = ", ".join(hoja.formulas_sin_valor[:3])
        avisos.append(f"{len(hoja.formulas_sin_valor)} celda(s) con fórmula no tienen un resultado guardado "
                      f"(p. ej. {celdas}) y se leen vacías. Ábrelo y guárdalo en Excel para calcularlas.")
    extra = [c.visible for c in columnas if asign[c.id] == C.EXTRA and c.no_vacias
             and orig[c.id].fuente == "predeterminado"]
    if extra:
        avisos.append("Se conservan como datos adicionales: " + ", ".join(f"«{e}»" for e in extra[:8])
                      + (f" y {len(extra) - 8} más" if len(extra) > 8 else "") + ".")

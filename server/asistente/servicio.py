"""Orchestration behind the assistant's endpoints.

    analizar   parse, interpret, maybe ask the model once, respond
    preparar   apply answers/corrections to the draft, respond again

A response is either the questions still open, or -- when nothing is -- the
ordinary preview with a single-use token, built from a validated plan. Every
change to the draft makes a new revision and a new preview; the previous
preview token is discarded, so a superseded preview cannot be confirmed.

External calls happen outside every database session: model latency never
holds the shared workspace's lock.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import db
from ..repo import formatos as repo_formatos
from ..staging import staging
from ..validation import summarize, validate_all
from ..web_util import ApiError
from . import campos as C  # noqa: N812 - short alias for a vocabulary module
from . import ia
from .borradores import RevisionObsoleta, borradores
from .detectar import Interpretacion, fusionar, interpretar
from .perfil import texto_de
from .plan import PLAN_VERSION, Construido, PlanError, construir
from .rejilla import EstructuraError, Hoja, Rejilla, leer

MAX_INTENTOS_IA = 2          # per draft: the first analysis, plus one materially different table
MAX_FILAS_VISTA = 100
MAX_PUNTOS = 2000


def _formatos() -> list[dict[str, Any]]:
    with db.session() as conn:
        return repo_formatos.activos(conn)


def _clave_analisis(interp: Interpretacion) -> str:
    return f"{interp.hoja.id}|{interp.encabezado}"


def _interpretar(rejilla: Rejilla, estado: Mapping[str, Any], formatos: Sequence[Mapping[str, Any]]) -> Interpretacion:
    base = interpretar(rejilla, estado.get("decisiones", {}), formatos)
    cache = estado.get("ia", {}).get(_clave_analisis(base), {})
    if cache.get("propuesta"):
        return interpretar(rejilla, estado.get("decisiones", {}), formatos, cache["propuesta"])
    return base


def _quizas_ia(rejilla: Rejilla, interp: Interpretacion, estado: dict[str, Any],
               formatos: Sequence[Mapping[str, Any]],
               reclamar: Callable[[dict[str, Any]], None] | None = None) -> Interpretacion:
    """At most one attempt per table choice, a bounded number per draft.

    `reclamar` records the attempt on the stored draft before calling out, so
    a concurrent request on the same draft sees it and does not call again.
    """
    clave = _clave_analisis(interp)
    registro = estado.setdefault("ia", {})
    if not interp.necesita_ia or clave in registro:
        return interp
    if not ia.disponible():
        registro[clave] = {"estado": "no_configurado"}
        return interp
    if estado.get("ia_intentos", 0) >= MAX_INTENTOS_IA:
        registro[clave] = {"estado": "limite_borrador"}
        return interp
    estado["ia_intentos"] = estado.get("ia_intentos", 0) + 1
    registro[clave] = {"estado": "en_curso"}
    if reclamar is not None:
        reclamar(estado)
    pendientes = {c.id for c in interp.columnas
                  if interp.origenes[c.id].fuente in ("predeterminado", "pendiente") and c.no_vacias}
    resultado = ia.sugerir(interp.columnas, interp.asignaciones, pendientes)
    registro[clave] = {"estado": resultado.estado, "propuesta": resultado.propuesta,
                       "proveedor": resultado.proveedor, "latencia_ms": resultado.latencia_ms}
    if resultado.propuesta:
        return interpretar(rejilla, estado.get("decisiones", {}), formatos, resultado.propuesta)
    return interp


def analizar(contenido: bytes, archivo: str, base_id: int | None) -> dict[str, Any]:
    try:
        rejilla = leer(contenido, archivo)
    except EstructuraError as exc:
        raise ApiError(str(exc)) from exc
    formatos = _formatos()
    estado: dict[str, Any] = {"archivo": archivo, "base_id": base_id, "decisiones": {}, "ia": {}}
    interp = _quizas_ia(rejilla, interpretar(rejilla, {}, formatos), estado, formatos)
    borrador = borradores.crear(rejilla.empaquetar(), estado)
    return _responder(borrador.token, borrador.revision, rejilla, interp, estado)


def preparar(token: str, revision: int, respuestas: Sequence[Mapping[str, Any]],
             correcciones: Mapping[str, Any]) -> dict[str, Any]:
    borrador = borradores.leer(token)
    if borrador is None:
        raise ApiError("El análisis del archivo expiró. Vuelve a seleccionarlo.", 410)
    if borrador.estado.get("confirmando"):
        raise ApiError("Esta importación ya se está guardando; no se puede cambiar.", 409)
    if revision != borrador.revision:
        raise ApiError("Hay una versión más reciente de esta importación.", 409,
                       {"revision": borrador.revision})
    rejilla = Rejilla.desempaquetar(borrador.rejilla)
    formatos = _formatos()
    estado = dict(borrador.estado)
    actual = _interpretar(rejilla, estado, formatos)

    decisiones = dict(estado.get("decisiones", {}))
    preguntas = {p.id: p for p in actual.preguntas}
    for respuesta in respuestas:
        pregunta = preguntas.get(str(respuesta.get("pregunta")))
        opcion = respuesta.get("opcion")
        if pregunta is None or type(opcion) is not int or not 0 <= opcion < len(pregunta.opciones):
            raise ApiError("La pregunta ya no está vigente; revisa la versión más reciente.", 409)
        decisiones = fusionar(decisiones, pregunta.opciones[opcion].decision)
    if correcciones:
        decisiones = fusionar(decisiones, _validar_correcciones(correcciones, rejilla, actual.hoja))
    estado["decisiones"] = decisiones

    actual_revision = revision

    def reclamar(estado_reclamado: dict[str, Any]) -> None:
        nonlocal actual_revision
        try:
            actual_revision = borradores.guardar(token, actual_revision, estado_reclamado)
        except RevisionObsoleta:
            raise ApiError("Hay una versión más reciente de esta importación.", 409) from None

    interp = _quizas_ia(rejilla, _interpretar(rejilla, estado, formatos), estado, formatos, reclamar)
    return _responder(token, actual_revision, rejilla, interp, estado, anterior=estado.get("vista_previa"))


def _validar_correcciones(parche: Mapping[str, Any], rejilla: Rejilla, hoja: Hoja) -> dict[str, Any]:
    """Only known keys with well-formed values; the plan validates the rest."""
    limpio: dict[str, Any] = {}
    # A header row can be named by the row number printed in the file; it is
    # translated here, because blank rows make it differ from the row's index.
    destino = rejilla.hoja(parche["hoja"]) if parche.get("hoja") in {h.id for h in rejilla.hojas} else hoja
    for clave, valor in parche.items():
        if clave == "encabezado_linea" and type(valor) is int and valor >= 1:
            limpio["encabezado"] = _indice_de_linea(destino, valor)
        elif clave == "hoja" and valor in {h.id for h in rejilla.hojas}:
            limpio["hoja"] = valor
        elif clave == "encabezado" and type(valor) is int and valor >= 0:
            limpio["encabezado"] = valor
        elif clave == "decimal" and valor in ("dot", "comma"):
            limpio["decimal"] = valor
        elif clave == "moneda" and valor in C.SOPORTADAS:
            limpio["moneda"] = valor
        elif clave == "columnas" and isinstance(valor, dict) and all(
                isinstance(k, str) and v in C.DESTINOS for k, v in valor.items()):
            limpio["columnas"] = dict(valor)
        elif clave in ("excluir", "incluir") and isinstance(valor, list) and all(
                type(i) is int and i >= 0 for i in valor):
            limpio[clave] = sorted(set(valor))
        else:
            raise ApiError(f"Corrección no válida: {clave}.")
    return limpio


def _indice_de_linea(hoja: Hoja, linea: int) -> int:
    """Turn the row number printed in the file into the row's index."""
    for indice, numero in enumerate(hoja.lineas):
        if numero == linea:
            return indice
    donde = "línea" if hoja.separador is not None else "fila"
    cercanas = [n for n in hoja.lineas if abs(n - linea) <= 10][:8] or list(hoja.lineas[:8])
    raise ApiError(f"La {donde} {linea} no tiene datos o no existe en el archivo. "
                   f"Con datos cerca: {', '.join(str(n) for n in cercanas)}.")


# ----------------------------------------------------------------- response

def _responder(token: str, revision: int, rejilla: Rejilla, interp: Interpretacion,
               estado: dict[str, Any], anterior: str | None = None) -> dict[str, Any]:
    if anterior:
        staging.take(anterior)   # a superseded preview must not be confirmable
    estado["vista_previa"] = None
    decisiones = estado.get("decisiones", {})
    plan = interp.plan(decisiones.get("excluir", ()), decisiones.get("incluir", ()))
    cuerpo: dict[str, Any] = {"borrador": token, "interpretacion": _interpretacion(interp, estado, rejilla)}
    construido = None
    if plan is not None:
        try:
            construido = construir(plan, rejilla)
        except (PlanError, EstructuraError) as exc:
            cuerpo["error"] = str(exc)

    if construido is not None and not construido.resultado.records:
        cuerpo["error"] = "La tabla no contiene ningún terreno con nombre."
        construido = None

    if construido is None:
        cuerpo["estado"] = "preguntas" if interp.preguntas else "revisar"
        cuerpo["preguntas"] = [_pregunta(p) for p in interp.preguntas]
    else:
        assert plan is not None  # construido exists only when a plan did
        # The compare-and-set below yields exactly revision + 1, so the preview
        # can record the draft revision it belongs to before it is saved.
        vista, preview_token = _vista_previa(rejilla, interp, construido, plan.to_dict(), estado,
                                             token, revision + 1)
        estado["vista_previa"] = preview_token
        cuerpo.update(estado="vista_previa", vista_previa=vista)

    try:
        cuerpo["revision"] = borradores.guardar(token, revision, estado)
    except RevisionObsoleta:
        if estado.get("vista_previa"):
            staging.take(estado["vista_previa"])
        raise ApiError("Hay una versión más reciente de esta importación.", 409) from None
    return cuerpo


def _pregunta(p: Any) -> dict[str, Any]:
    return {"id": p.id, "texto": p.texto, "detalle": p.detalle, "sugerida": p.sugerida,
            "opciones": [{"indice": i, "etiqueta": o.etiqueta, "detalle": o.detalle}
                         for i, o in enumerate(p.opciones)]}


def _interpretacion(interp: Interpretacion, estado: Mapping[str, Any], rejilla: Rejilla) -> dict[str, Any]:
    hoja = interp.hoja
    orden = {h_id: i for i, h_id in enumerate(interp.hojas)}
    hojas = sorted(rejilla.hojas, key=lambda h: orden.get(h.id, len(orden)))
    ia_estado = estado.get("ia", {}).get(_clave_analisis(interp), {})
    return {
        "hoja": {"id": hoja.id, "nombre": hoja.nombre, "separador": hoja.separador,
                 "filas": len(hoja.filas),
                 "primera_linea": hoja.lineas[0] if hoja.lineas else 1,
                 "ultima_linea": hoja.lineas[-1] if hoja.lineas else 1},
        "hojas": [{"id": h.id, "nombre": h.nombre, "separador": h.separador, "filas": len(h.filas)}
                  for h in hojas],
        "encabezado": {"indice": interp.encabezado, "linea": hoja.lineas[interp.encabezado] if hoja.lineas else 1},
        "encabezados": [{"indice": i, "linea": hoja.lineas[i],
                         "vista": " | ".join(texto_de(c) for c in hoja.filas[i][:6] if texto_de(c))}
                        for i in sorted(interp.encabezados[:50])],
        "decimal": interp.decimal,
        # The prices' currency once settled, and what settled it: the file's
        # own markers, the user's answer, or a saved format.
        "moneda": interp.moneda, "moneda_origen": interp.moneda_origen,
        "hay_precios": any(d in C.PRECIOS for d in interp.asignaciones.values()),
        "columnas": [{
            "id": c.id, "letra": c.letra, "etiqueta": c.etiqueta, "visible": c.visible,
            "muestras": list(c.muestras[:3]), "destino": interp.asignaciones[c.id],
            "origen": interp.origenes[c.id].fuente, "motivo": interp.origenes[c.id].motivo,
            "moneda": c.moneda, "monedas": list(c.monedas),
            "monedas_formato": list(c.monedas_formato),
        } for c in interp.columnas],
        "destinos": [{"valor": d, "etiqueta": C.ETIQUETA_DESTINO[d]} for d in C.DESTINOS],
        "avisos": list(interp.avisos),
        "formato": ({"id": interp.formato["id"], "nombre": interp.formato["nombre"],
                     "version": interp.formato["version"]} if interp.formato else None),
        "automatico": {"estado": ia_estado.get("estado", "no_necesario"),
                       "proveedor": ia_estado.get("proveedor"),
                       "aplicadas": sum(1 for o in interp.origenes.values() if o.fuente == "ia"),
                       "descartadas": interp.ia_descartadas},
        "excluir": list(estado.get("decisiones", {}).get("excluir", [])),
        "incluir": list(estado.get("decisiones", {}).get("incluir", [])),
        # Whether this installation may send minimal column data out, so the
        # dialog can disclose it. Configuration, not a choice for the manager.
        "asistencia_configurada": ia.disponible(),
    }


def _formato_para_recordar(rejilla: Rejilla, interp: Interpretacion) -> dict[str, Any]:
    """What a confirmed import remembers about this layout.

    A column kept out of the prices only because of its currency is not
    remembered as a choice: a later file is judged on its own currency. The
    currency is remembered, but a later file's explicit markers still win.
    """
    firma = [[c.clave, c.ocurrencia] for c in interp.columnas if c.clave]
    asignaciones = [[c.clave, c.ocurrencia, interp.asignaciones[c.id]] for c in interp.columnas
                    if c.clave and c.id not in interp.excluidas_moneda]
    return {
        "nombre": f"Formato de «{Path(rejilla.archivo).stem}»",
        "firma": firma,
        "config": {"asignaciones": asignaciones, "decimal": interp.decimal,
                   "hoja": interp.hoja.nombre, "formato": rejilla.formato,
                   "moneda": interp.moneda},
        "plan_version": PLAN_VERSION,
    }


def _vista_previa(rejilla: Rejilla, interp: Interpretacion, construido: Construido, plan: dict[str, Any],
                  estado: Mapping[str, Any], token: str, revision: int) -> tuple[dict[str, Any], str]:
    resultado = construido.resultado
    incidencias = validate_all(resultado.records)
    meta = {
        "borrador": token, "revision": revision, "plan": plan, "sha256": rejilla.sha256, "archivo": rejilla.archivo,
        "hoja": interp.hoja.nombre, "fila_encabezado": interp.hoja.lineas[interp.encabezado],
        "formato_usado": ({"id": interp.formato["id"], "version": interp.formato["version"]}
                          if interp.formato else None),
        "recordar": _formato_para_recordar(rejilla, interp),
    }
    pending = staging.put(rejilla.archivo, Path(rejilla.archivo).stem, resultado, incidencias, meta=meta)

    from ..api.importar import _clasificar, _muestra
    etiquetas = {c.id: c.visible for c in construido.columnas}
    filas = []
    for record in resultado.records[:MAX_FILAS_VISTA]:
        filas.append({
            "fila": record.fila, "orden": record.orden, "terreno": record.terreno,
            "indice": construido.indices.get(record.orden, -1),
            "estado": record.estado, "municipio": record.municipio,
            "superficie_m2": record.superficie_m2, "superficie_ha": record.superficie_ha,
            "asking_price": record.asking_price, "asking_m2": record.asking_m2, "moneda": record.moneda,
            "lat": record.lat, "lon": record.lon, "ubicado": record.ubicado,
            "originales": [{"columna": etiquetas[k], "valor": v}
                           for k, v in construido.originales.get(record.orden, {}).items() if v],
        })
    vista = {
        "token": pending.token, "archivo": rejilla.archivo, "nombre_sugerido": pending.nombre_sugerido,
        "formato": rejilla.formato, "hoja": resultado.hoja,
        "conteo": len(resultado.records), "ubicados": resultado.ubicados,
        "sin_ubicacion": resultado.sin_ubicacion, "sin_coordenadas": resultado.sin_coordenadas,
        "ubicacion_invalida": resultado.ubicacion_invalida,
        "con_precio": sum(1 for r in resultado.records if r.asking_price is not None),
        "con_precio_m2": sum(1 for r in resultado.records if r.asking_m2 is not None),
        "filas_con_datos": construido.filas_datos,
        "rechazadas": [{"fila": r.fila, "motivo": r.motivo, "resumen": r.resumen} for r in resultado.rechazadas],
        "excluidas": [{"fila": e.fila, "motivo": e.motivo, "resumen": e.resumen, "indice": e.indice}
                      for e in construido.excluidas],
        "preambulo": list(construido.preambulo),
        "resumen": summarize(incidencias),
        "hallazgos": _muestra(resultado, incidencias),
        "columnas_no_reconocidas": list(resultado.columnas_no_reconocidas),
        "columnas_faltantes": list(resultado.columnas_faltantes),
        "columnas_duplicadas": [],
        "filas": filas,
        "puntos": [[r.lat, r.lon, r.terreno] for r in resultado.records if r.ubicado][:MAX_PUNTOS],
        "decimal": plan["decimal"],
        "moneda": plan["moneda"],
        "moneda_origen": plan["moneda_origen"],
        # Columns in an unsupported currency, or mixing two: kept as additional
        # data with their original amount, never relabelled or converted.
        "monedas_no_admitidas": [
            {"columna": c.visible, "letra": c.letra, "monedas": list(c.monedas),
             "por_formato": bool(c.monedas_formato), "motivo": C.problema_moneda(c.monedas)}
            for c in construido.columnas if C.problema_moneda(c.monedas)],
    }
    base_id = estado.get("base_id")
    if base_id:
        vista["clasificacion"] = _clasificar(int(base_id), resultado)
    return vista, pending.token

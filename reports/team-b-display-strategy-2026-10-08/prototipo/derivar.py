"""Derive prototipo/MapCanvas.js from the ACCEPTED B-2 renderer.

    python3 -I derivar.py <b2-archive-dir>

Reads web/components/map/MapCanvas.js from `git archive 5d8e2dc`, applies the
prototype edits below (each must match exactly once) and writes
prototipo/MapCanvas.js plus prototipo/MapCanvas.diff. The accepted file is
never modified; this keeps the prototype a replayable patch.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

EDICIONES: list[tuple[str, str]] = [
    # Imports: the accepted modules from the /b2/ mount, plus the prototype.
    ('from "../../lib/colors.js";', 'from "/b2/web/lib/colors.js";'),
    ('from "../../lib/format.js";', 'from "/b2/web/lib/format.js";'),
    ('} from "../../lib/geo.js";', '} from "/b2/web/lib/geo.js";'),
    ('} from "../../lib/geometria.js";', '} from "/b2/web/lib/geometria.js";'),
    ('import { BASEMAPS, MEXICO_BOUNDS } from "./basemaps.js";',
     'import { BASEMAPS, MEXICO_BOUNDS } from "/b2/web/components/map/basemaps.js";\n'
     'import { crearClases } from "./capa.js";\n'
     'import { prepararAhora } from "./preparar.js";\n'
     'import { crearCache, crearPlanificador } from "./planificador.js";\n'
     '\n'
     '/* PROTOTYPE switch for the benchmark: "e1" closes rings without closePath;\n'
     ' * "e2" draws cached prepared bodies with culling; "e3" = e2 + cooperative,\n'
     ' * cancellable preparation with an explicit pending status. */\n'
     'let ESTRATEGIA = "e3";\n'
     'export function configurarPrototipo({ estrategia }) { ESTRATEGIA = estrategia; }'),
    # Pending look: dotted, distinct from the dashed "not available" symbol.
    ('const SIN_CONTORNO = { fillOpacity: 0.18, weight: 2, dashArray: "3 3" };',
     'const SIN_CONTORNO = { fillOpacity: 0.18, weight: 2, dashArray: "3 3" };\n'
     '/* PROTOTYPE: an outline that is loading or being prepared. Dotted, so it\n'
     ' * reads as "in progress", never as a loaded outline or a missing one. */\n'
     'const PENDIENTE = { fillOpacity: 0.18, weight: 2, dashArray: "1 4" };\n'
     '/* PROTOTYPE: employee-visible wording per boundary state (tooltip line). */\n'
     'const AVISOS = {\n'
     '  cargando: "Cargando contorno…",\n'
     '  preparando: "Preparando contorno…",\n'
     '  no_disponible: "Contorno no disponible",\n'
     '  invalido: "Contorno no válido",\n'
     '};'),
    ('export function createMapCanvas(container, { onSelect, onScaleChange, onDoubleSelect } = {}) {',
     'export function createMapCanvas(container, {\n'
     '  onSelect, onScaleChange, onDoubleSelect, onContornoEstado,\n'
     '} = {}) {\n'
     '  const { PoligonoSinClosePath, CapaContorno } = crearClases(L);\n'
     '  const cache = crearCache();\n'
     '  const planificador = crearPlanificador();\n'
     '  let generacion = 0;'),
    # render(): generation, cancellation of jobs nobody needs, session reset.
    ('  function render(terrenos, { colorFor, dashFor = null, geometrias = null } = {}) {\n'
     '    contornoLayer.clearLayers();',
     '  function render(terrenos, { colorFor, dashFor = null, geometrias = null,\n'
     '                             cargando = null } = {}) {\n'
     '    generacion += 1;\n'
     '    contornoLayer.clearLayers();'),
    ('    for (const terreno of contornos) {\n'
     '      if (byId.has(terreno.id)) continue;           // one logical mark per terrain\n'
     '      byId.set(terreno.id, crearContorno(\n'
     '        terreno, geometrias, zoom, offsets.get(terreno.id) ?? 0, colorFor, dashFor));\n'
     '    }',
     '    // PROTOTYPE: preparation nobody needs any more is cancelled; an empty\n'
     '    // render is the session/scope reset, which also drops every cached body.\n'
     '    planificador.conservarSolo(new Set(contornos.map((t) => t.geometria.id)));\n'
     '    if (!filas.length) cache.vaciar();\n'
     '    for (const terreno of contornos) {\n'
     '      if (byId.has(terreno.id)) continue;           // one logical mark per terrain\n'
     '      byId.set(terreno.id, crearContorno(\n'
     '        terreno, geometrias, zoom, offsets.get(terreno.id) ?? 0, colorFor, dashFor,\n'
     '        cargando));\n'
     '    }'),
    # crearContorno: strategy-specific body handling.
    ('  function crearContorno(terreno, geometrias, zoom, extra, colorFor, dashFor) {\n'
     '    const descriptor = terreno.geometria;\n'
     '    const cuerpo = cuerpoLeaflet(descriptor, geometrias);\n'
     '    const disponible = cuerpo.estado === "cargado";\n'
     '    const fill = colorFor(terreno);\n'
     '    const dash = dashFor?.(terreno) ?? null;\n'
     '    const symbolic = SYMBOL_RADIUS + extra;\n'
     '    const html = tooltipHtml(terreno, { sinContorno: !disponible });\n',
     '  function crearContorno(terreno, geometrias, zoom, extra, colorFor, dashFor, cargando) {\n'
     '    const descriptor = terreno.geometria;\n'
     '    // PROTOTYPE: what the body is, per strategy. e3 never prepares a\n'
     '    // large body inside render(); it starts (or joins) a cooperative job.\n'
     '    let cuerpo;\n'
     '    let estadoContorno;\n'
     '    if (ESTRATEGIA === "e1") {\n'
     '      cuerpo = cuerpoLeaflet(descriptor, geometrias);\n'
     '    } else {\n'
     '      cuerpo = cache.obtener(descriptor);\n'
     '      if (!cuerpo && ESTRATEGIA === "e2") {\n'
     '        cuerpo = prepararAhora(descriptor, geometrias);\n'
     '        if (cuerpo.estado === "cargado") cache.guardar(descriptor, cuerpo);\n'
     '      }\n'
     '      if (!cuerpo && !geometrias?.has?.(descriptor.id)) {\n'
     '        cuerpo = { estado: "no_disponible" };\n'
     '      }\n'
     '    }\n'
     '    if (cuerpo) {\n'
     '      estadoContorno = cuerpo.estado === "cargado" ? "listo" : cuerpo.estado;\n'
     '    } else {\n'
     '      estadoContorno = "preparando";\n'
     '    }\n'
     '    if (estadoContorno === "no_disponible" && cargando?.has?.(descriptor.id)) {\n'
     '      estadoContorno = "cargando";\n'
     '    }\n'
     '    const disponible = estadoContorno === "listo";\n'
     '    const fill = colorFor(terreno);\n'
     '    const dash = dashFor?.(terreno) ?? null;\n'
     '    const symbolic = SYMBOL_RADIUS + extra;\n'
     '    const html = tooltipHtml(terreno, { aviso: AVISOS[estadoContorno] ?? null });\n'),
    ('      ...simboloStyle({ fill, dash, disponible }),\n'
     '    });\n'
     '    simbolo.bindTooltip(html, {',
     '      ...simboloStyle({ fill, dash, disponible, estadoContorno }),\n'
     '    });\n'
     '    simbolo.bindTooltip(html, {'),
    ('    let contorno = null;\n'
     '    if (disponible) {\n'
     '      contorno = L.polygon(cuerpo.partes, {\n'
     '        fillColor: fill,\n'
     '        bubblingMouseEvents: false,\n'
     '        ...contornoStyle({ fill, dash }),\n'
     '      });\n'
     '      contorno.bindTooltip(html, { sticky: true, opacity: 1, className: "mark-tooltip" });\n'
     '      wireActivation(contorno, terreno.id);\n'
     '    }\n',
     '    const crearCapa = (c) => {\n'
     '      const opciones = { fillColor: fill, bubblingMouseEvents: false,\n'
     '                         ...contornoStyle({ fill, dash }) };\n'
     '      const capa = ESTRATEGIA === "e1"\n'
     '        ? new PoligonoSinClosePath(c.partes, opciones)\n'
     '        : new CapaContorno(c, opciones);\n'
     '      capa.bindTooltip(tooltipHtml(terreno), { sticky: true, opacity: 1,\n'
     '                                              className: "mark-tooltip" });\n'
     '      wireActivation(capa, terreno.id);\n'
     '      return capa;\n'
     '    };\n'
     '    const contorno = disponible ? crearCapa(cuerpo) : null;\n'),
    ('      posiciones: disponible ? cuerpo.posiciones : 0,\n'
     '      aEscala: false,\n'
     '    };\n'
     '    mostrarContorno(entry, zoom);\n'
     '    return entry;\n'
     '  }',
     '      posiciones: disponible ? cuerpo.posiciones : 0,\n'
     '      aEscala: false,\n'
     '      estadoContorno,\n'
     '    };\n'
     '    mostrarContorno(entry, zoom);\n'
     '    if (estadoContorno === "preparando") {\n'
     '      const miGeneracion = generacion;\n'
     '      planificador.pedir(descriptor, geometrias, (r) => {\n'
     '        if (r.estado === "cargado") cache.guardar(descriptor, r);\n'
     '        // A newer render, filter or reset owns the map now: drop the result.\n'
     '        if (miGeneracion !== generacion || byId.get(terreno.id) !== entry) return;\n'
     '        entry.estadoContorno = r.estado === "cargado" ? "listo" : r.estado;\n'
     '        entry.disponible = r.estado === "cargado";\n'
     '        if (entry.disponible) {\n'
     '          entry.contorno = crearCapa(r);\n'
     '          entry.cajaEscala = r.cajaMayor;\n'
     '          entry.posiciones = r.posiciones;\n'
     '        }\n'
     '        entry.simbolo.setTooltipContent(tooltipHtml(terreno, {\n'
     '          aviso: AVISOS[entry.estadoContorno] ?? null }));\n'
     '        entry.aEscala = false;\n'
     '        mostrarContorno(entry, map.getZoom());\n'
     '        aplicarEstiloContorno(entry, terreno.id === selectedId);\n'
     '        reportScale();\n'
     '        emitirEstado(entry, terreno.id);\n'
     '      });\n'
     '    }\n'
     '    emitirEstado(entry, terreno.id);\n'
     '    return entry;\n'
     '  }'),
    ('    const zoom = map.getZoom();\n'
     '    if (!entry.disponible) {\n'
     '      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo };\n'
     '    }',
     '    const zoom = map.getZoom();\n'
     '    // PROTOTYPE: never report an outline that is still loading or being prepared.\n'
     '    if (entry.estadoContorno === "preparando" || entry.estadoContorno === "cargando") {\n'
     '      return { estado: "contorno_pendiente", contorno: true, zoom, requerido, maximo };\n'
     '    }\n'
     '    if (!entry.disponible) {\n'
     '      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo };\n'
     '    }'),
    ('    return { x: p.x, y: p.y, tipo: entry.tipo, contorno: Boolean(entry.aEscala && entry.contorno) };',
     '    return { x: p.x, y: p.y, tipo: entry.tipo, contorno: Boolean(entry.aEscala && entry.contorno),\n'
     '             estadoContorno: entry.estadoContorno ?? null };'),
    ('    invalidate: () => map.invalidateSize(),',
     '    invalidate: () => map.invalidateSize(),\n'
     '    // PROTOTYPE (additive): teardown cancels preparation and drops cached bodies.\n'
     '    destruir() {\n'
     '      planificador.detener();\n'
     '      cache.vaciar();\n'
     '      byId = new Map();\n'
     '      map.remove();\n'
     '    },\n'
     '    _diagnostico: { planificador, cache },'),
    # Symbol look per state.
    ('function simboloStyle({ fill, dash, disponible, selected = false }) {\n'
     '  if (selected) {\n'
     '    return { color: "#111111", weight: 3, dashArray: disponible ? null : SIN_CONTORNO.dashArray,\n'
     '             fillOpacity: disponible ? 1 : 0.32 };\n'
     '  }\n'
     '  if (!disponible) {',
     'function simboloStyle({ fill, dash, disponible, estadoContorno = null, selected = false }) {\n'
     '  const pendiente = estadoContorno === "preparando" || estadoContorno === "cargando";\n'
     '  if (selected) {\n'
     '    const marca = disponible ? null : (pendiente ? PENDIENTE : SIN_CONTORNO).dashArray;\n'
     '    return { color: "#111111", weight: 3, dashArray: marca,\n'
     '             fillOpacity: disponible ? 1 : 0.32 };\n'
     '  }\n'
     '  if (pendiente) {\n'
     '    return { color: fill, weight: PENDIENTE.weight, dashArray: PENDIENTE.dashArray,\n'
     '             fillOpacity: PENDIENTE.fillOpacity };\n'
     '  }\n'
     '  if (!disponible) {'),
    ('function tooltipHtml(terreno, { sinContorno = false } = {}) {',
     'function tooltipHtml(terreno, { aviso = null } = {}) {'),
    ('    (sinContorno ? `<span class="mark-tooltip-aviso">Contorno no disponible</span>` : "")',
     '    (aviso ? `<span class="mark-tooltip-aviso">${escapeHtml(aviso)}</span>` : "")'),
    # ---- E4: off-main-thread raster for heavy views (applied after the above).
    ('import { crearCache, crearPlanificador } from "./planificador.js";\n',
     'import { crearCache, crearPlanificador } from "./planificador.js";\n'
     'import { crearClienteRaster } from "./raster.js";\n'),
    ('"e3" = e2 + cooperative,\n'
     ' * cancellable preparation with an explicit pending status. */',
     '"e3" = e2 + cooperative,\n'
     ' * cancellable preparation with an explicit pending status; "e4" = e3 +\n'
     ' * worker rasterization when the visible geometry is heavy. */'),
    ('  preparando: "Preparando contorno…",\n',
     '  preparando: "Preparando contorno…",\n'
     '  dibujando: "Dibujando contorno…",\n'),
    ('  const { PoligonoSinClosePath, CapaContorno } = crearClases(L);\n',
     '  const { PoligonoSinClosePath, CapaContorno, CapaContornoRaster } = crearClases(L);\n'
     '  const raster = ESTRATEGIA === "e4" ? crearClienteRaster() : null;\n'),
    ('    if (!filas.length) cache.vaciar();\n',
     '    if (!filas.length) { cache.vaciar(); raster?.olvidarTodo(); }\n'),
    ('    const crearCapa = (c) => {\n'
     '      const opciones = { fillColor: fill, bubblingMouseEvents: false,\n'
     '                         ...contornoStyle({ fill, dash }) };\n'
     '      const capa = ESTRATEGIA === "e1"\n'
     '        ? new PoligonoSinClosePath(c.partes, opciones)\n'
     '        : new CapaContorno(c, opciones);\n',
     '    let entrada = null;                          // set below; used by E4 callbacks\n'
     '    const crearCapa = (c) => {\n'
     '      const opciones = { fillColor: fill, bubblingMouseEvents: false,\n'
     '                         ...contornoStyle({ fill, dash }) };\n'
     '      let capa;\n'
     '      if (ESTRATEGIA === "e1") capa = new PoligonoSinClosePath(c.partes, opciones);\n'
     '      else if (ESTRATEGIA === "e4") {\n'
     '        const completo = (sel) => {\n'
     '          const o = L.Util.extend({}, L.Path.prototype.options, { fill: true }, opciones,\n'
     '                                  contornoStyle({ fill, dash, selected: sel }));\n'
     '          if (typeof o.dashArray === "string") o.dashArray = o.dashArray.split(/[, ]+/).map(Number);\n'
     '          return o;\n'
     '        };\n'
     '        capa = new CapaContornoRaster(c, opciones, {\n'
     '          id: descriptor.id, cliente: raster, estilos: [completo(false), completo(true)],\n'
     '          alCambiarEstado: (estado) => alDibujo(entrada, terreno, estado),\n'
     '        });\n'
     '      } else capa = new CapaContorno(c, opciones);\n'),
    ('      estadoContorno,\n'
     '    };\n'
     '    mostrarContorno(entry, zoom);\n',
     '      estadoContorno,\n'
     '    };\n'
     '    entrada = entry;\n'
     '    mostrarContorno(entry, zoom);\n'),
    ('  /** Show the outline or the symbol for this zoom; returns whether it changed. */',
     '  /** E4: the worker raster for an outline started ("dibujando") or arrived ("listo").\n'
     '   * The state is recorded at once, so posicionDe/zoomToScale never report an\n'
     '   * unpainted outline; the layer and style changes are deferred (Leaflet calls\n'
     '   * this from inside its redraw loop) and coalesced to the last state. */\n'
     '  function alDibujo(entry, terreno, estado) {\n'
     '    if (!entry || byId.get(terreno.id) !== entry || !entry.disponible) return;\n'
     '    const nuevo = estado === "dibujando" && entry.aEscala ? "dibujando" : "listo";\n'
     '    if (nuevo === entry.estadoContorno) return;\n'
     '    entry.estadoContorno = nuevo;\n'
     '    if (entry.visualPendiente) return;\n'
     '    entry.visualPendiente = true;\n'
     '    queueMicrotask(() => {\n'
     '      entry.visualPendiente = false;\n'
     '      if (byId.get(terreno.id) !== entry) return;\n'
     '      const actual = entry.estadoContorno;          // idempotent: apply the latest state\n'
     '      // Pending: the interior-point symbol stays, in the pending look, over the\n'
     '      // undrawn outline; never an outline that is not painted yet.\n'
     '      if (actual === "dibujando") entry.simbolo.addTo(markerLayer);\n'
     '      else if (entry.aEscala) markerLayer.removeLayer(entry.simbolo);\n'
     '      entry.simbolo.setTooltipContent(tooltipHtml(terreno, { aviso: AVISOS[actual] ?? null }));\n'
     '      aplicarEstiloContorno(entry, terreno.id === selectedId);\n'
     '      reportScale();\n'
     '      emitirEstado(entry, terreno.id);\n'
     '    });\n'
     '  }\n'
     '\n'
     '  /** One callback per state actually reached (no repeats). */\n'
     '  function emitirEstado(entry, id) {\n'
     '    if (entry.estadoEmitido === entry.estadoContorno) return;\n'
     '    entry.estadoEmitido = entry.estadoContorno;\n'
     '    onContornoEstado?.(id, entry.estadoContorno);\n'
     '  }\n'
     '\n'
     '  /** Show the outline or the symbol for this zoom; returns whether it changed. */'),
    ('      markerLayer.removeLayer(entry.simbolo);\n'
     '      entry.contorno.addTo(contornoLayer);\n',
     '      if (entry.estadoContorno !== "dibujando") markerLayer.removeLayer(entry.simbolo);\n'
     '      entry.contorno.addTo(contornoLayer);\n'),
    ('      if (entry.contorno) contornoLayer.removeLayer(entry.contorno);\n'
     '      entry.simbolo.addTo(markerLayer);\n',
     '      if (entry.contorno) contornoLayer.removeLayer(entry.contorno);\n'
     '      if (entry.estadoContorno === "dibujando") entry.estadoContorno = "listo";\n'
     '      entry.simbolo.addTo(markerLayer);\n'),
    ('        if (entry.aEscala) {\n'
     '          contornosAEscala += 1;',
     '        if (entry.aEscala && entry.estadoContorno !== "dibujando") {\n'
     '          contornosAEscala += 1;'),
    ('    if (entry.estadoContorno === "preparando" || entry.estadoContorno === "cargando") {\n'
     '      return { estado: "contorno_pendiente", contorno: true, zoom, requerido, maximo };',
     '    if (entry.estadoContorno === "preparando" || entry.estadoContorno === "cargando"\n'
     '        || entry.estadoContorno === "dibujando") {\n'
     '      return { estado: "contorno_pendiente", contorno: true, zoom, requerido, maximo,\n'
     '               motivo: entry.estadoContorno };'),
    ('contorno: Boolean(entry.aEscala && entry.contorno),\n'
     '             estadoContorno: entry.estadoContorno ?? null };',
     'contorno: Boolean(entry.aEscala && entry.contorno\n'
     '                                       && entry.estadoContorno !== "dibujando"),\n'
     '             estadoContorno: entry.estadoContorno ?? null };'),
    ('      planificador.detener();\n'
     '      cache.vaciar();\n',
     '      planificador.detener();\n'
     '      cache.vaciar();\n'
     '      raster?.cerrar();\n'),
    ('    _diagnostico: { planificador, cache },',
     '    _diagnostico: { planificador, cache, raster,\n'
     '                    // Test hook: the symbol tooltip text (state wording) of a terrain.\n'
     '                    aviso: (id) => byId.get(id)?.simbolo?.getTooltip()?.getContent() ?? null },'),
    ('  const pendiente = estadoContorno === "preparando" || estadoContorno === "cargando";',
     '  const pendiente = estadoContorno === "preparando" || estadoContorno === "cargando"\n'
     '    || estadoContorno === "dibujando";'),
    ('function contornoStyle({ fill, dash, selected = false }) {\n'
     '  if (selected) return { color: "#111111", weight: 3, dashArray: null, fillOpacity: 0.32 };\n'
     '  return { color: fill, weight: HUELLA.weight, dashArray: dash, fillOpacity: HUELLA.fillOpacity };',
     'function contornoStyle({ fill, dash, selected = false }) {\n'
     '  // PROTOTYPE: `seleccionado` tells the E4 layer which pre-rasterized style to show.\n'
     '  if (selected) {\n'
     '    return { color: "#111111", weight: 3, dashArray: null, fillOpacity: 0.32, seleccionado: true };\n'
     '  }\n'
     '  return { color: fill, weight: HUELLA.weight, dashArray: dash, fillOpacity: HUELLA.fillOpacity,\n'
     '           seleccionado: false };'),
    # ---- F3 correction (supervisory review): bounded worker copies, applied last.
    ('  dibujando: "Dibujando contorno…",\n',
     '  dibujando: "Dibujando contorno…",\n'
     '  // F3: the worker budget is held by other outlines on the map; explicit, never pending.\n'
     '  sin_memoria: "Contorno no disponible: demasiados contornos a la vez",\n'),
    ('const DOBLE_ACTIVACION_MS = 280;\n',
     'const DOBLE_ACTIVACION_MS = 280;\n'
     '/* PROTOTYPE (F3): E4 states where the outline layer is attached but not painted. */\n'
     'const NO_PINTADO = new Set(["dibujando", "sin_memoria"]);\n'),
    ('  const cache = crearCache();\n',
     '  // F3: an evicted body leaves the worker too, unless a layer still pins it.\n'
     '  const cache = crearCache(undefined, { alExpulsar: (id) => raster?.expulsado(id) });\n'
     '  let reinicioTrabajador = null;                 // F3: resolves when the worker confirms\n'),
    ('    if (!filas.length) { cache.vaciar(); raster?.olvidarTodo(); }\n',
     '    if (!filas.length) { cache.vaciar(); if (raster) reinicioTrabajador = raster.olvidarTodo(); }\n'),
    ('          id: descriptor.id, cliente: raster, estilos: [completo(false), completo(true)],\n',
     '          id: descriptor.id, cliente: raster, estilos: [completo(false), completo(true)],\n'
     '          enCache: () => cache.contiene(descriptor.id),\n'),
    ('    const nuevo = estado === "dibujando" && entry.aEscala ? "dibujando" : "listo";\n',
     '    const nuevo = NO_PINTADO.has(estado) && entry.aEscala ? estado : "listo";\n'),
    ('      if (actual === "dibujando") entry.simbolo.addTo(markerLayer);\n',
     '      if (NO_PINTADO.has(actual)) entry.simbolo.addTo(markerLayer);\n'),
    ('      if (entry.estadoContorno !== "dibujando") markerLayer.removeLayer(entry.simbolo);\n',
     '      if (!NO_PINTADO.has(entry.estadoContorno)) markerLayer.removeLayer(entry.simbolo);\n'),
    ('      if (entry.estadoContorno === "dibujando") entry.estadoContorno = "listo";\n',
     '      if (NO_PINTADO.has(entry.estadoContorno)) entry.estadoContorno = "listo";\n'),
    ('        if (entry.aEscala && entry.estadoContorno !== "dibujando") {\n',
     '        if (entry.aEscala && !NO_PINTADO.has(entry.estadoContorno)) {\n'),
    ('                                       && entry.estadoContorno !== "dibujando"),\n',
     '                                       && !NO_PINTADO.has(entry.estadoContorno)),\n'),
    ('    if (entry.estadoContorno === "preparando" || entry.estadoContorno === "cargando"\n'
     '        || entry.estadoContorno === "dibujando") {\n',
     '    if (entry.estadoContorno === "sin_memoria") {\n'
     '      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo,\n'
     '               motivo: "sin_memoria" };\n'
     '    }\n'
     '    if (entry.estadoContorno === "preparando" || entry.estadoContorno === "cargando"\n'
     '        || entry.estadoContorno === "dibujando") {\n'),
    ('    _diagnostico: { planificador, cache, raster,\n',
     '    _diagnostico: { planificador, cache, raster,\n'
     '                    get reinicioTrabajador() { return reinicioTrabajador; },\n'),
    ('function simboloStyle({ fill, dash, disponible, estadoContorno = null, selected = false }) {\n',
     'function simboloStyle({ fill, dash, disponible: cargado, estadoContorno = null, selected = false }) {\n'
     '  // F3: an outline refused by the worker budget looks "not available", never pending.\n'
     '  const disponible = cargado && estadoContorno !== "sin_memoria";\n'),
    # ---- Review follow-up: "e1p" closes each ring with closePath() on its own
    # Path2D (exact closePath stroke semantics), merged with addPath.
    ('  const { PoligonoSinClosePath, CapaContorno, CapaContornoRaster } = crearClases(L);\n',
     '  const { PoligonoSinClosePath, PoligonoPath2D, CapaContorno, CapaContornoRaster } = crearClases(L);\n'),
    ('    if (ESTRATEGIA === "e1") {\n',
     '    if (ESTRATEGIA === "e1" || ESTRATEGIA === "e1p") {\n'),
    ('      if (ESTRATEGIA === "e1") capa = new PoligonoSinClosePath(c.partes, opciones);\n',
     '      if (ESTRATEGIA === "e1") capa = new PoligonoSinClosePath(c.partes, opciones);\n'
     '      else if (ESTRATEGIA === "e1p") capa = new PoligonoPath2D(c.partes, opciones);\n'),
    # F3: a test may lower the worker budget (behaviour check of "sin_memoria").
    ('export function configurarPrototipo({ estrategia }) { ESTRATEGIA = estrategia; }',
     'let PRESUPUESTO_TRABAJADOR;                      // F3: undefined = raster.js default\n'
     'export function configurarPrototipo({ estrategia, presupuestoTrabajador }) {\n'
     '  ESTRATEGIA = estrategia;\n'
     '  PRESUPUESTO_TRABAJADOR = presupuestoTrabajador;\n'
     '}'),
    ('  const raster = ESTRATEGIA === "e4" ? crearClienteRaster() : null;\n',
     '  const raster = ESTRATEGIA === "e4"\n'
     '    ? crearClienteRaster({ presupuesto: PRESUPUESTO_TRABAJADOR }) : null;\n'),
]


def main(b2: Path) -> None:
    original = (b2 / "web" / "components" / "map" / "MapCanvas.js").read_text(encoding="utf-8")
    texto = original
    for antes, despues in EDICIONES:
        veces = texto.count(antes)
        if veces != 1:
            raise SystemExit(f"edit must match once, matched {veces}: {antes[:70]!r}")
        texto = texto.replace(antes, despues)
    cabecera = ("/* PROTOTYPE derived from the ACCEPTED B-2 renderer (5d8e2dc) by\n"
                " * prototipo/derivar.py. Display-strategy investigation only; not\n"
                " * application code. See MapCanvas.diff for the exact changes. */\n")
    (AQUI / "MapCanvas.js").write_text(cabecera + texto, encoding="utf-8")
    diff = difflib.unified_diff(original.splitlines(keepends=True), texto.splitlines(keepends=True),
                                "a/web/components/map/MapCanvas.js",
                                "b/web/components/map/MapCanvas.js")
    (AQUI / "MapCanvas.diff").write_text("".join(diff), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).resolve())

/* PROTOTYPE derived from PR #16's derived prototype MapCanvas.js (9da0ab1)
 * by prototipo/derivar.py, adding strategy "e5" (memory budget). Not
 * application code. See MapCanvas.diff for the exact changes. */
/* PROTOTYPE derived from the ACCEPTED B-2 renderer (5d8e2dc) by
 * prototipo/derivar.py. Display-strategy investigation only; not
 * application code. See MapCanvas.diff for the exact changes. */
/* The Leaflet map: basemaps, markers, selection and fitting.
 *
 * Kept deliberately imperative and self-contained -- Leaflet owns its own DOM,
 * so the rest of the app talks to it through this small surface instead of
 * re-rendering it.
 *
 * Two kinds of mark share that surface. XY rows are the established circles
 * (symbol, then true-scale footprint). Rows with an ACTIVE boundary
 * (t.geometria, shared contract v1 §4) are drawn from their geometry body:
 * a symbol on the interior point while small, the real outline -- every
 * part, holes included -- once it is big enough to hit. A boundary is never
 * drawn as a circle scaled from declared area.
 */

import { MARK_RING } from "/b2/web/lib/colors.js";
import { fmtArea, fmtUnitPrice } from "/b2/web/lib/format.js";
import {
  coincidentRingOffsets, markRadius, SYMBOL_RADIUS, trueScaleZoom,
} from "/b2/web/lib/geo.js";
import {
  contornoAEscala, cuerpoLeaflet, limitesDeFilas, limitesLeaflet, MODO, modoDeFila,
  puntoDeSimbolo, puntoLeaflet, zoomDeContorno,
} from "/b2/web/lib/geometria.js";
import { BASEMAPS, MEXICO_BOUNDS } from "/b2/web/components/map/basemaps.js";
import { crearClases } from "/proto/prototipo/capa.js";
import { prepararAhora } from "/proto/prototipo/preparar.js";
import { crearCache, crearPlanificador } from "/proto/prototipo/planificador.js";
import { crearClienteRaster } from "/proto/prototipo/raster.js";
// E5 (memory-budget investigation): shared budget, registry, capped planner, worker client, controller.
import { crearPresupuesto } from "./presupuesto.js";
import { crearRegistro } from "./registro.js";
import { crearPlanificador as crearPlanificadorE5 } from "./planificador.js";
import { crearCliente } from "./cliente.js";
import { crearClasesE5, crearControlador, bytesDeCapa } from "./e5.js";

/* PROTOTYPE switch for the benchmark: "e1" closes rings without closePath;
 * "e2" draws cached prepared bodies with culling; "e3" = e2 + cooperative,
 * cancellable preparation with an explicit pending status; "e4" = e3 +
 * worker rasterization when the visible geometry is heavy. */
let ESTRATEGIA = "e3";
let PRESUPUESTO_TRABAJADOR;                      // F3: undefined = raster.js default
/* E5: ONE budget shared by every map created on the page (two maps compete),
 * plus test-only failure simulation and the unanswered-request deadline. */
let PRESUPUESTO_E5 = null;
let SIMULAR_E5 = null;
let PLAZO_E5_MS = 8000;
let mapasE5 = 0;
export function configurarE5({ presupuesto = null, bytes = 64 * 1024 * 1024, simular = null, plazoMs = 8000 } = {}) {
  PRESUPUESTO_E5 = presupuesto ?? crearPresupuesto(bytes);
  SIMULAR_E5 = simular;
  PLAZO_E5_MS = plazoMs;
  return PRESUPUESTO_E5;
}
export function configurarPrototipo({ estrategia, presupuestoTrabajador }) {
  ESTRATEGIA = estrategia;
  PRESUPUESTO_TRABAJADOR = presupuestoTrabajador;
}

/* A mark has two jobs and two looks.
 *
 * As a SYMBOL it is a filled dot with a white ring: small, legible, and read
 * against its neighbours. As a FOOTPRINT it covers real ground, so it becomes
 * a translucent wash with its own colour as the outline -- you have to be able
 * to see the land underneath the shape that claims to describe it. */
const SIMBOLO = { fillOpacity: 0.82, weight: 2, ring: MARK_RING };
const HUELLA  = { fillOpacity: 0.20, weight: 2 };

/* A boundary whose body has not loaded (or failed validation) keeps its place
 * with a hollow, dashed symbol, so it never passes for a loaded outline. */
const SIN_CONTORNO = { fillOpacity: 0.18, weight: 2, dashArray: "3 3" };
/* PROTOTYPE: an outline that is loading or being prepared. Dotted, so it
 * reads as "in progress", never as a loaded outline or a missing one. */
const PENDIENTE = { fillOpacity: 0.18, weight: 2, dashArray: "1 4" };
/* PROTOTYPE: employee-visible wording per boundary state (tooltip line). */
const AVISOS = {
  cargando: "Cargando contorno…",
  preparando: "Preparando contorno…",
  dibujando: "Dibujando contorno…",
  // F3: the worker budget is held by other outlines on the map; explicit, never pending.
  sin_memoria: "Contorno no disponible: demasiados contornos a la vez",
  no_disponible: "Contorno no disponible",
  invalido: "Contorno no válido",
};

/* How long a second activation on the same terrain still counts as a double.
 * An interaction choice, not a geometry constant: kept here so both the mouse
 * and touch paths use one value. */
const DOBLE_ACTIVACION_MS = 280;
/* PROTOTYPE (F3): E4 states where the outline layer is attached but not painted. */
const NO_PINTADO = new Set(["dibujando", "sin_memoria", "demasiado_grande", "sin_trabajador"]);
/* E5: states where the outline is not available (explicit, never pending). */
const NO_DISPONIBLE_E5 = new Set(["sin_memoria", "demasiado_grande", "sin_trabajador"]);
const AVISOS_E5 = {
  cargando: "Cargando contorno…",
  preparando: "Cargando contorno…",
  dibujando: "Cargando contorno…",
  sin_memoria: "Contorno no disponible: no hay memoria para dibujarlo ahora",
  demasiado_grande: "Contorno no disponible: la ventana es demasiado grande para dibujarlo",
  sin_trabajador: "Contorno no disponible: falló el dibujo; se reintentará al actualizar el mapa",
};
/* A second tap further than this from the first is a new gesture, not a double. */
const DOBLE_ACTIVACION_PX = 28;

export const ZOOM_MAXIMO = 20;

export function createMapCanvas(container, {
  onSelect, onScaleChange, onDoubleSelect, onContornoEstado,
} = {}) {
  const { PoligonoSinClosePath, PoligonoPath2D, CapaContorno, CapaContornoRaster } = crearClases(L);
  const raster = ESTRATEGIA === "e4"
    ? crearClienteRaster({ presupuesto: PRESUPUESTO_TRABAJADOR }) : null;
  // F3: an evicted body leaves the worker too, unless a layer still pins it.
  const E5 = ESTRATEGIA === "e5";
  if (E5) Object.assign(AVISOS, AVISOS_E5);
  const duenoE5 = E5 ? `mapa-${++mapasE5}` : null;
  const presupuestoE5 = E5 ? (PRESUPUESTO_E5 ?? configurarE5()) : null;
  const registro = E5 ? crearRegistro(presupuestoE5, duenoE5) : null;
  const { CapaContornoE5, CapaBitmap } = crearClasesE5(L, CapaContorno);
  // E5: the registry is the cache; the planner reserves before allocating.
  const cache = E5
    ? { obtener: (d) => registro.obtener(d), guardar() {}, vaciar: () => registro.vaciar(),
        contiene: () => false, get bytes() { return registro.bytesReservados(); },
        get tamano() { return registro.tamano; } }
    : crearCache(undefined, { alExpulsar: (id) => raster?.expulsado(id) });
  let reinicioTrabajador = null;                 // F3: resolves when the worker confirms
  const planificador = E5
    ? crearPlanificadorE5({ registro, presupuesto: presupuestoE5,
                            alPreparar: (d, r, reserva) => registro.guardar(d, r, reserva) })
    : crearPlanificador();
  let generacion = 0;
  const map = L.map(container, {
    zoomControl: false,
    attributionControl: true,
    preferCanvas: true, // one canvas beats hundreds of SVG nodes when panning
    maxZoom: ZOOM_MAXIMO,
    minZoom: 3,
  });

  map.fitBounds(MEXICO_BOUNDS);
  L.control.zoom({ position: "topright" }).addTo(map);
  const controlador = E5 ? crearControlador({
    L, map, CapaBitmap, presupuesto: presupuestoE5, dueno: duenoE5,
    crearCliente: (o) => crearCliente({ presupuesto: presupuestoE5, dueno: duenoE5, simular: SIMULAR_E5,
                                       plazoMs: PLAZO_E5_MS, ...o }),
    alEstado: (capa, estado) => capa._avisarE5?.(estado),
  }) : null;
  // A body that leaves the registry leaves the worker too: copies follow cache membership.
  registro?.alQuitar((id) => controlador.expulsado(id));
  map.attributionControl.setPrefix("");

  // Outlines share the map's single canvas renderer with every circle and
  // symbol: a second canvas would sit on top and swallow their mouse events.
  // They are kept at the back of that canvas (see mostrarContorno).
  const contornoLayer = L.layerGroup().addTo(map);
  const markerLayer = L.layerGroup().addTo(map);
  let tileLayers = [];
  let basemapKey = null;
  let byId = new Map();
  let selectedId = null;

  // Marks grow with the map once their real footprint is bigger than the
  // symbol, so every zoom change re-measures them.
  map.on("zoomend", () => resizeMarks());

  /* One recogniser serves mouse and touch. Leaflet emits click for both, so
   * deciding here avoids a synthetic double-click firing the action twice. */
  let gesto = { id: null, tiempo: 0, punto: null, timer: null, consumido: false };

  function cancelarPendiente() {
    if (gesto.timer) {
      clearTimeout(gesto.timer);
      gesto.timer = null;
    }
  }

  function olvidarGesto() {
    cancelarPendiente();
    gesto = { id: null, tiempo: 0, punto: null, timer: null, consumido: false };
  }

  // Panning or pinching abandons any pending activation.
  map.on("dragstart zoomstart movestart", olvidarGesto);

  function activar(id, event) {
    const ahora = Date.now();
    const punto = event?.containerPoint ?? null;
    const cerca = gesto.punto && punto
      ? gesto.punto.distanceTo(punto) <= DOBLE_ACTIVACION_PX
      : true;

    const esDoble = gesto.id === id
      && !gesto.consumido
      && ahora - gesto.tiempo <= DOBLE_ACTIVACION_MS
      && cerca;

    if (esDoble) {
      cancelarPendiente();
      gesto.consumido = true;   // a third click starts a fresh gesture
      onDoubleSelect?.(id);
      return;
    }

    cancelarPendiente();
    gesto = { id, tiempo: ahora, punto, timer: null, consumido: false };

    // Selection feedback is immediate; the layout-changing detail panel waits
    // out the double window so the second click still lands on this marker.
    selectedId = id;
    applySelection();
    gesto.timer = setTimeout(() => {
      gesto.timer = null;
      onSelect?.(id);
    }, DOBLE_ACTIVACION_MS);
  }

  function setBasemap(key) {
    if (key === basemapKey) return;
    const spec = BASEMAPS[key] ?? BASEMAPS.claro;

    for (const layer of tileLayers) map.removeLayer(layer);

    // Esri serves the base imagery and its place-name labels as separate
    // layers, so a basemap is a short stack rather than a single URL.
    tileLayers = spec.capas.map((url, index) => {
      const layer = L.tileLayer(url, {
        attribution: index === 0 ? spec.attribution : "",
        // maxZoom is the map's limit so tiles keep being displayed (upscaled)
        // past the service's own levels; maxNativeZoom stops us requesting
        // tile levels that do not exist. Overzoom shows no extra detail.
        maxZoom: ZOOM_MAXIMO,
        maxNativeZoom: spec.maxZoom,
        // No crossOrigin: the tile services do not reliably send CORS headers,
        // and requesting it makes tiles fail to load. Nothing reads tile pixels.
      }).addTo(map);
      layer.setZIndex(index);
      return layer;
    });

    basemapKey = key;
    container.dataset.basemap = key;
  }

  /**
   * Draw a set of terrains. `colorFor` maps a terrain to its fill colour.
   *
   * `geometrias` (optional) is a Map from geometry ID to loaded geometry
   * body. Rows carrying an active usable `t.geometria` descriptor are drawn
   * from it; entries for terrains not in `terrenos`, or for any geometry that
   * is not a row's active descriptor, are ignored. Without the option every
   * row takes the established XY path.
   *
   * Returns how many terrains were placed (XY marks plus boundaries), as
   * before. render([]) clears every layer, the selection and any pending
   * click -- the reset path for a session or scope change.
   */
  function render(terrenos, { colorFor, dashFor = null, geometrias = null,
                             cargando = null } = {}) {
    generacion += 1;
    // E5: the old entries' layers stop pinning their prepared bodies; a failed worker is retried.
    if (E5) {
      for (const e of byId.values()) {
        if (!e.contorno?._ctl) continue;
        e.contorno.liberarMemoriaE5();               // R1: the layer's own array goes with it
        registro.soltar(e.contorno._id);
      }
      controlador.reintentar();
    }
    contornoLayer.clearLayers();
    markerLayer.clearLayers();
    byId = new Map();

    const filas = Array.isArray(terrenos) ? terrenos : [];
    const plotted = [];
    const contornos = [];
    for (const terreno of filas) {
      const modo = modoDeFila(terreno);
      if (modo === MODO.PUNTO) plotted.push(terreno);
      else if (modo === MODO.GEOMETRIA) contornos.push(terreno);
    }

    // Boundary symbols and XY marks stacked on one point read as concentric
    // rings, using the established grouping.
    const offsets = coincidentRingOffsets(
      [...plotted, ...contornos].map(puntoDeSimbolo).filter(Boolean));

    // Each mark has one symbol size for every terrain and a true footprint. The
    // drawn radius is whichever is larger, so zooming in hands over from symbol
    // to measurement.
    const zoom = map.getZoom();
    const sized = plotted.map((terreno) => {
      const extra = offsets.get(terreno.id) ?? 0;
      const { radius, aEscala } = markRadius(
        terreno.superficie_m2, terreno.lat, zoom, { extra });
      return { terreno, radius, symbolic: SYMBOL_RADIUS + extra, aEscala };
    });

    // Draw largest-first, so a wide footprint never paints over the smaller
    // marks standing on top of it.
    sized.sort((a, b) => b.radius - a.radius);

    for (const { terreno, radius, symbolic, aEscala } of sized) {
      // Layers past the validated colour range carry a dashed ring, so their
      // identity does not rest on hue alone.
      const dash = dashFor?.(terreno) ?? null;

      const fill = colorFor(terreno);
      const marker = L.circleMarker([terreno.lat, terreno.lon], {
        radius,
        opacity: 1,
        fillColor: fill,
        dashArray: dash,
        bubblingMouseEvents: false,
        ...markStyle({ fill, dash, aEscala }),
      });

      marker.bindTooltip(tooltipHtml(terreno), {
        direction: "top",
        offset: [0, -radius - 2],
        opacity: 1,
        className: "mark-tooltip",
      });
      wireActivation(marker, terreno.id);

      marker.addTo(markerLayer);
      byId.set(terreno.id, {
        tipo: "punto",
        marker, radius, dash, symbolic, fill, aEscala,
        m2: terreno.superficie_m2, lat: terreno.lat, lon: terreno.lon,
      });
    }

    // PROTOTYPE: preparation nobody needs any more is cancelled; an empty
    // render is the session/scope reset, which also drops every cached body.
    planificador.conservarSolo(new Set(contornos.map((t) => t.geometria.id)));
    if (!filas.length) {
      cache.vaciar();
      if (raster) reinicioTrabajador = raster.olvidarTodo();
      if (controlador) reinicioTrabajador = controlador.vaciar();
    }
    for (const terreno of contornos) {
      if (byId.has(terreno.id)) continue;           // one logical mark per terrain
      byId.set(terreno.id, crearContorno(
        terreno, geometrias, zoom, offsets.get(terreno.id) ?? 0, colorFor, dashFor,
        cargando));
    }

    // A selection or a pending click on a terrain that is no longer drawn
    // must not survive a filter change or reset.
    if (selectedId !== null && !byId.has(selectedId)) selectedId = null;
    if (gesto.id !== null && !byId.has(gesto.id)) olvidarGesto();

    applySelection();
    reportScale();
    return plotted.length + contornos.length;
  }

  /** One boundary terrain: its symbol, and its outline when the body loaded. */
  function crearContorno(terreno, geometrias, zoom, extra, colorFor, dashFor, cargando) {
    const descriptor = terreno.geometria;
    // PROTOTYPE: what the body is, per strategy. e3 never prepares a
    // large body inside render(); it starts (or joins) a cooperative job.
    let cuerpo;
    let estadoContorno;
    if (ESTRATEGIA === "e1" || ESTRATEGIA === "e1p") {
      cuerpo = cuerpoLeaflet(descriptor, geometrias);
    } else {
      cuerpo = cache.obtener(descriptor);
      if (!cuerpo && ESTRATEGIA === "e2") {
        cuerpo = prepararAhora(descriptor, geometrias);
        if (cuerpo.estado === "cargado") cache.guardar(descriptor, cuerpo);
      }
      if (!cuerpo && !geometrias?.has?.(descriptor.id)) {
        cuerpo = { estado: "no_disponible" };
      }
    }
    if (cuerpo) {
      estadoContorno = cuerpo.estado === "cargado" ? "listo" : cuerpo.estado;
    } else {
      estadoContorno = "preparando";
    }
    if (estadoContorno === "no_disponible" && cargando?.has?.(descriptor.id)) {
      estadoContorno = "cargando";
    }
    let reservaCapa = null;
    if (E5 && estadoContorno === "listo") {
      reservaCapa = presupuestoE5.reservar("capa", bytesDeCapa(cuerpo), duenoE5);
      if (!reservaCapa) estadoContorno = "sin_memoria";
    }
    const disponible = estadoContorno === "listo";
    const fill = colorFor(terreno);
    const dash = dashFor?.(terreno) ?? null;
    const symbolic = SYMBOL_RADIUS + extra;
    const html = tooltipHtml(terreno, { aviso: AVISOS[estadoContorno] ?? null });

    const simbolo = L.circleMarker(puntoLeaflet(descriptor.punto_interior), {
      radius: symbolic,
      opacity: 1,
      fillColor: fill,
      bubblingMouseEvents: false,
      ...simboloStyle({ fill, dash, disponible, estadoContorno }),
    });
    simbolo.bindTooltip(html, {
      direction: "top", offset: [0, -symbolic - 2], opacity: 1, className: "mark-tooltip",
    });
    wireActivation(simbolo, terreno.id);

    let entrada = null;                          // set below; used by E4 callbacks
    const crearCapa = (c) => {
      const opciones = { fillColor: fill, bubblingMouseEvents: false,
                         ...contornoStyle({ fill, dash }) };
      let capa;
      if (ESTRATEGIA === "e1") capa = new PoligonoSinClosePath(c.partes, opciones);
      else if (ESTRATEGIA === "e1p") capa = new PoligonoPath2D(c.partes, opciones);
      else if (ESTRATEGIA === "e4") {
        const completo = (sel) => {
          const o = L.Util.extend({}, L.Path.prototype.options, { fill: true }, opciones,
                                  contornoStyle({ fill, dash, selected: sel }));
          if (typeof o.dashArray === "string") o.dashArray = o.dashArray.split(/[, ]+/).map(Number);
          return o;
        };
        capa = new CapaContornoRaster(c, opciones, {
          id: descriptor.id, cliente: raster, estilos: [completo(false), completo(true)],
          enCache: () => cache.contiene(descriptor.id),
          alCambiarEstado: (estado) => alDibujo(entrada, terreno, estado),
        });
      } else if (E5) {
        // R1: the layer's own array is admitted before the layer is built.
        capa = CapaContornoE5.crear(c, opciones, { id: descriptor.id, controlador, presupuesto: presupuestoE5,
                                                  dueno: duenoE5, reserva: reservaCapa });
        reservaCapa = null;                         // owned by the layer now, or released
        if (!capa) return null;                     // no room: the caller reports "sin_memoria"
        registro.fijar(descriptor.id);              // pinned for this entry's lifetime
        capa._avisarE5 = (estado) => alDibujo(entrada, terreno, estado);
      } else capa = new CapaContorno(c, opciones);
      capa.bindTooltip(tooltipHtml(terreno), { sticky: true, opacity: 1,
                                              className: "mark-tooltip" });
      wireActivation(capa, terreno.id);
      return capa;
    };
    const contorno = disponible ? crearCapa(cuerpo) : null;

    const entry = {
      tipo: "contorno",
      simbolo, contorno, disponible, fill, dash, symbolic,
      bbox: descriptor.bbox,
      // The handover follows the largest part: a multipart of small, scattered
      // parts keeps its symbol until those parts can actually be hit.
      cajaEscala: disponible ? cuerpo.cajaMayor : descriptor.bbox,
      punto: puntoLeaflet(descriptor.punto_interior),
      posiciones: disponible ? cuerpo.posiciones : 0,
      aEscala: false,
      estadoContorno,
    };
    entrada = entry;
    mostrarContorno(entry, zoom);
    if (estadoContorno === "preparando") {
      const miGeneracion = generacion;
      planificador.pedir(descriptor, geometrias, (r) => {
        if (r.estado === "cargado") cache.guardar(descriptor, r);
        // A newer render, filter or reset owns the map now: drop the result.
        if (miGeneracion !== generacion || byId.get(terreno.id) !== entry) return;
        entry.estadoContorno = r.estado === "cargado" ? "listo" : r.estado;
        entry.disponible = r.estado === "cargado";
        if (entry.disponible) {
          entry.contorno = crearCapa(r);
          if (entry.contorno) {
            entry.cajaEscala = r.cajaMayor;
            entry.posiciones = r.posiciones;
          } else {                                  // E5 (R1): no room for the layer's array
            entry.disponible = false;
            entry.estadoContorno = "sin_memoria";
          }
        }
        entry.simbolo.setTooltipContent(tooltipHtml(terreno, {
          aviso: AVISOS[entry.estadoContorno] ?? null }));
        entry.aEscala = false;
        mostrarContorno(entry, map.getZoom());
        aplicarEstiloContorno(entry, terreno.id === selectedId);
        reportScale();
        emitirEstado(entry, terreno.id);
      });
    }
    emitirEstado(entry, terreno.id);
    return entry;
  }

  /** E4: the worker raster for an outline started ("dibujando") or arrived ("listo").
   * The state is recorded at once, so posicionDe/zoomToScale never report an
   * unpainted outline; the layer and style changes are deferred (Leaflet calls
   * this from inside its redraw loop) and coalesced to the last state. */
  function alDibujo(entry, terreno, estado) {
    if (!entry || byId.get(terreno.id) !== entry || !entry.disponible) return;
    const nuevo = NO_PINTADO.has(estado) && entry.aEscala ? estado : "listo";
    if (nuevo === entry.estadoContorno) return;
    entry.estadoContorno = nuevo;
    if (entry.visualPendiente) return;
    entry.visualPendiente = true;
    queueMicrotask(() => {
      entry.visualPendiente = false;
      if (byId.get(terreno.id) !== entry) return;
      const actual = entry.estadoContorno;          // idempotent: apply the latest state
      // Pending: the interior-point symbol stays, in the pending look, over the
      // undrawn outline; never an outline that is not painted yet.
      if (NO_PINTADO.has(actual)) entry.simbolo.addTo(markerLayer);
      else if (entry.aEscala) markerLayer.removeLayer(entry.simbolo);
      entry.simbolo.setTooltipContent(tooltipHtml(terreno, { aviso: AVISOS[actual] ?? null }));
      aplicarEstiloContorno(entry, terreno.id === selectedId);
      reportScale();
      emitirEstado(entry, terreno.id);
    });
  }

  /** One callback per state actually reached (no repeats). */
  function emitirEstado(entry, id) {
    if (entry.estadoEmitido === entry.estadoContorno) return;
    entry.estadoEmitido = entry.estadoContorno;
    onContornoEstado?.(id, entry.estadoContorno);
  }

  /** Show the outline or the symbol for this zoom; returns whether it changed. */
  function mostrarContorno(entry, zoom) {
    const aEscala = Boolean(entry.contorno) && contornoAEscala(entry.cajaEscala, zoom);
    const yaVisible = entry.contorno && contornoLayer.hasLayer(entry.contorno);
    if (aEscala === entry.aEscala && (yaVisible || markerLayer.hasLayer(entry.simbolo))) {
      return false;
    }
    entry.aEscala = aEscala;
    if (aEscala) {
      if (!NO_PINTADO.has(entry.estadoContorno)) markerLayer.removeLayer(entry.simbolo);
      entry.contorno.addTo(contornoLayer);
      entry.contorno.bringToBack();          // below every circle and symbol
    } else {
      if (entry.contorno) contornoLayer.removeLayer(entry.contorno);
      if (NO_PINTADO.has(entry.estadoContorno)) entry.estadoContorno = "listo";
      entry.simbolo.addTo(markerLayer);
    }
    return true;
  }

  function wireActivation(layer, id) {
    layer.on("click", (event) => {
      L.DomEvent.stop(event);
      activar(id, event);
    });
    // Swallow the mark's own double-click so Leaflet does not also apply
    // its ordinary zoom-in. Background double-click keeps working.
    layer.on("dblclick", (event) => L.DomEvent.stop(event));
  }

  /** Re-measure every mark against the new zoom. */
  function resizeMarks() {
    const zoom = map.getZoom();
    for (const [id, entry] of byId) {
      if (entry.tipo === "contorno") {
        if (mostrarContorno(entry, zoom)) aplicarEstiloContorno(entry, id === selectedId);
        continue;
      }
      const { radius, aEscala } = markRadius(
        entry.m2, entry.lat, zoom, { extra: entry.symbolic - SYMBOL_RADIUS });
      if (radius !== entry.radius) {
        entry.radius = radius;
        entry.marker.setRadius(radius);
      }
      // Crossing the handover changes what the mark means, so it changes look.
      if (aEscala !== entry.aEscala) {
        entry.aEscala = aEscala;
        entry.marker.setStyle(markStyle({ ...entry, selected: id === selectedId }));
      }
    }
    reportScale();
  }

  /** Tell the caller how many marks currently show real ground area. */
  function reportScale() {
    if (!onScaleChange) return;
    const zoom = map.getZoom();
    let aEscala = 0;
    let contornos = 0;
    let contornosAEscala = 0;
    for (const entry of byId.values()) {
      if (entry.tipo === "contorno") {
        // A drawn outline is real ground, like a circle at true scale.
        contornos += 1;
        if (entry.aEscala && !NO_PINTADO.has(entry.estadoContorno)) {
          contornosAEscala += 1;
          aEscala += 1;
        }
        continue;
      }
      const extra = entry.symbolic - SYMBOL_RADIUS;
      if (markRadius(entry.m2, entry.lat, zoom, { extra }).aEscala) aEscala += 1;
    }
    // contornos / contornosAEscala are additive: XY-only maps report 0.
    onScaleChange({ aEscala, total: byId.size, zoom, contornos, contornosAEscala });
  }

  /** How a mark looks, given what it currently represents. */
  function markStyle({ fill, dash, aEscala, selected = false }) {
    if (selected) {
      return {
        color: "#111111",
        weight: 3,
        dashArray: null,
        fillOpacity: aEscala ? 0.32 : 1,
      };
    }
    return aEscala
      ? { color: fill, weight: HUELLA.weight, dashArray: dash, fillOpacity: HUELLA.fillOpacity }
      : { color: SIMBOLO.ring, weight: dash ? 2.5 : SIMBOLO.weight, dashArray: dash,
          fillOpacity: SIMBOLO.fillOpacity };
  }

  function applySelection() {
    for (const [id, entry] of byId) {
      const selected = id === selectedId;
      if (entry.tipo === "contorno") {
        aplicarEstiloContorno(entry, selected);
        continue;
      }
      entry.marker.setStyle(markStyle({ ...entry, selected }));
      if (selected) entry.marker.bringToFront();
    }
  }

  function aplicarEstiloContorno(entry, selected) {
    entry.simbolo.setStyle(simboloStyle({ ...entry, selected }));
    if (entry.contorno) entry.contorno.setStyle(contornoStyle({ ...entry, selected }));
    // A selected symbol comes forward; a selected outline stays behind the
    // symbols so it never hides a mark standing on it.
    if (selected && markerLayer.hasLayer(entry.simbolo)) entry.simbolo.bringToFront();
  }

  function select(id, { pan = false } = {}) {
    selectedId = id;
    applySelection();
    const entry = byId.get(id);
    if (entry && pan) {
      if (entry.tipo === "contorno") {
        // The whole boundary, every part, framed -- not just its centre.
        map.fitBounds(limitesLeaflet(entry.bbox), {
          padding: [40, 40], maxZoom: ZOOM_MAXIMO, animate: !prefersReducedMotion(),
        });
        return;
      }
      map.setView(entry.marker.getLatLng(), Math.max(map.getZoom(), 13), {
        animate: !prefersReducedMotion(),
      });
    }
  }

  function fitTo(terrenos) {
    const filas = Array.isArray(terrenos) ? terrenos : [];
    const conContorno = filas.some((t) => modoDeFila(t) === MODO.GEOMETRIA);
    if (!conContorno) {
      // XY only: exactly the established framing.
      const points = filas.filter((t) => modoDeFila(t) === MODO.PUNTO).map((t) => [t.lat, t.lon]);
      if (!points.length) {
        map.fitBounds(MEXICO_BOUNDS);
        return;
      }
      if (points.length === 1) {
        map.setView(points[0], 13);
        return;
      }
      map.fitBounds(L.latLngBounds(points).pad(0.12));
      return;
    }
    // Boundaries contribute their whole extent, every part included.
    map.fitBounds(L.latLngBounds(limitesDeFilas(filas)).pad(0.12), { maxZoom: ZOOM_MAXIMO });
  }

  function setView(center, zoom) {
    map.setView(center, zoom, { animate: false });
  }

  /**
   * Zoom until the terrain's circle represents its real area, and centre it.
   *
   * Returns why it could or could not, so the caller can say something true
   * rather than silently doing nothing.
   */
  function zoomToScale(id) {
    const entry = byId.get(id);
    if (!entry) return { estado: "sin_marca" };
    if (entry.tipo === "contorno") return zoomAlContorno(entry);
    if (!Number.isFinite(entry.m2) || entry.m2 <= 0) return { estado: "sin_area" };
    if (!Number.isFinite(entry.lat) || !Number.isFinite(entry.lon)) {
      return { estado: "sin_ubicacion" };
    }

    // The mark's own symbol radius, which in a comparison includes its
    // concentric offset: a hardcoded radius would under-zoom those layers.
    const objetivo = trueScaleZoom(entry.m2, entry.lat, entry.symbolic);
    if (!Number.isFinite(objetivo)) return { estado: "sin_area" };

    const maximo = map.getMaxZoom();
    const deseado = Math.max(map.getZoom(), objetivo);
    const zoom = Math.min(Math.max(deseado, map.getMinZoom()), maximo);

    map.stop();
    map.setView([entry.lat, entry.lon], zoom, { animate: !prefersReducedMotion() });

    const alcanzado = markRadius(
      entry.m2, entry.lat, zoom, { extra: entry.symbolic - SYMBOL_RADIUS },
    ).aEscala;
    return {
      estado: alcanzado ? "a_escala" : "limite_de_zoom",
      zoom,
      requerido: objetivo,
      maximo,
    };
  }

  /**
   * Boundary version of zoomToScale: frame the whole boundary. Additive
   * result fields: `contorno: true` always; `requerido`, the zoom at which
   * the outline first shows. Additive state: "contorno_no_disponible" when
   * the body is not loaded (framed by the descriptor's bbox, no outline).
   */
  function zoomAlContorno(entry) {
    const maximo = map.getMaxZoom();
    const requerido = zoomDeContorno(entry.cajaEscala, maximo);
    map.stop();
    map.fitBounds(limitesLeaflet(entry.bbox), {
      padding: [40, 40], maxZoom: maximo, animate: false,
    });
    if (requerido !== null && map.getZoom() < requerido) {
      map.setView(entry.punto, requerido, { animate: false });
    }
    const zoom = map.getZoom();
    // PROTOTYPE: never report an outline that is still loading or being prepared.
    if (NO_DISPONIBLE_E5.has(entry.estadoContorno)) {
      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo,
               motivo: entry.estadoContorno };
    }
    if (entry.estadoContorno === "preparando" || entry.estadoContorno === "cargando"
        || entry.estadoContorno === "dibujando") {
      return { estado: "contorno_pendiente", contorno: true, zoom, requerido, maximo,
               motivo: entry.estadoContorno };
    }
    if (!entry.disponible) {
      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo };
    }
    return {
      estado: contornoAEscala(entry.cajaEscala, zoom) ? "a_escala" : "limite_de_zoom",
      contorno: true, zoom, requerido, maximo,
    };
  }

  /**
   * Where a placed terrain can be clicked, in container pixels: the XY
   * centre, the boundary symbol, or a point inside the drawn outline. For
   * test hooks; null when the terrain is not drawn.
   */
  function posicionDe(id) {
    const entry = byId.get(id);
    if (!entry) return null;
    const latlng = entry.tipo === "contorno" ? entry.punto : entry.marker.getLatLng();
    const p = map.latLngToContainerPoint(latlng);
    return { x: p.x, y: p.y, tipo: entry.tipo, contorno: Boolean(entry.aEscala && entry.contorno
                                       && !NO_PINTADO.has(entry.estadoContorno)),
             estadoContorno: entry.estadoContorno ?? null };
  }

  /** The current viewport, for storing in a saved map's view state. */
  function viewport() {
    const center = map.getCenter();
    return { center: [center.lat, center.lng], zoom: map.getZoom() };
  }

  return {
    map,
    setBasemap,
    render,
    select,
    fitTo,
    setView,
    viewport,
    zoomToScale,
    posicionDe,
    invalidate: () => map.invalidateSize(),
    // PROTOTYPE (additive): teardown cancels preparation and drops cached bodies.
    destruir() {
      planificador.detener();
      cache.vaciar();
      for (const e of byId.values()) e.contorno?.liberarMemoriaE5?.();
      controlador?.cerrar();
      registro?.cerrar();
      raster?.cerrar();
      byId = new Map();
      map.remove();
    },
    _diagnostico: { planificador, cache, raster, presupuesto: presupuestoE5, registro, controlador,
                    // R1 audit: the layers' own arrays, reserved vs actually held.
                    capasE5() {
                      let reservado = 0; let real = 0; let n = 0;
                      for (const e of byId.values()) {
                        const c = e.contorno;
                        if (!c?._reservaCapa) continue;
                        n += 1; reservado += c._reservaCapa.bytes; real += c.bytesCapaE5();
                      }
                      return { reservado, real, n };
                    },
                    get reinicioTrabajador() { return reinicioTrabajador; },
                    // Test hook: the symbol tooltip text (state wording) of a terrain.
                    aviso: (id) => byId.get(id)?.simbolo?.getTooltip()?.getContent() ?? null },
    get basemap() { return basemapKey; },
  };
}

/** A boundary symbol: solid when its outline is loaded, hollow and dashed when not. */
function simboloStyle({ fill, dash, disponible: cargado, estadoContorno = null, selected = false }) {
  // F3: an outline refused by the worker budget looks "not available", never pending.
  const disponible = cargado && !NO_DISPONIBLE_E5.has(estadoContorno);
  const pendiente = estadoContorno === "preparando" || estadoContorno === "cargando"
    || estadoContorno === "dibujando";
  if (selected) {
    const marca = disponible ? null : (pendiente ? PENDIENTE : SIN_CONTORNO).dashArray;
    return { color: "#111111", weight: 3, dashArray: marca,
             fillOpacity: disponible ? 1 : 0.32 };
  }
  if (pendiente) {
    return { color: fill, weight: PENDIENTE.weight, dashArray: PENDIENTE.dashArray,
             fillOpacity: PENDIENTE.fillOpacity };
  }
  if (!disponible) {
    return { color: fill, weight: SIN_CONTORNO.weight, dashArray: SIN_CONTORNO.dashArray,
             fillOpacity: SIN_CONTORNO.fillOpacity };
  }
  return { color: SIMBOLO.ring, weight: dash ? 2.5 : SIMBOLO.weight, dashArray: dash,
           fillOpacity: SIMBOLO.fillOpacity };
}

/** A drawn outline: the footprint look, the selection look when selected. */
function contornoStyle({ fill, dash, selected = false }) {
  // PROTOTYPE: `seleccionado` tells the E4 layer which pre-rasterized style to show.
  if (selected) {
    return { color: "#111111", weight: 3, dashArray: null, fillOpacity: 0.32, seleccionado: true };
  }
  return { color: fill, weight: HUELLA.weight, dashArray: dash, fillOpacity: HUELLA.fillOpacity,
           seleccionado: false };
}

function tooltipHtml(terreno, { aviso = null } = {}) {
  const name = escapeHtml(terreno.terreno);
  const place = escapeHtml(
    [terreno.municipio, terreno.estado].filter(Boolean).join(", ")
  );
  const figures = [fmtArea(terreno.superficie_m2), fmtUnitPrice(terreno.asking_m2, terreno.moneda)]
    .filter((v) => v !== "—")
    .join(" · ");

  return (
    `<strong>${name}</strong>` +
    (place ? `<span>${place}</span>` : "") +
    (figures ? `<span class="figure">${escapeHtml(figures)}</span>` : "") +
    (aviso ? `<span class="mark-tooltip-aviso">${escapeHtml(aviso)}</span>` : "")
  );
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

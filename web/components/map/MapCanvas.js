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

import { MARK_RING } from "../../lib/colors.js";
import { fmtArea, fmtUnitPrice } from "../../lib/format.js";
import {
  coincidentRingOffsets, markRadius, SYMBOL_RADIUS, trueScaleZoom,
} from "../../lib/geo.js";
import {
  contornoAEscala, cuerpoLeaflet, limitesDeFilas, limitesLeaflet, MODO, modoDeFila,
  puntoDeSimbolo, puntoLeaflet, zoomDeContorno,
} from "../../lib/geometria.js";
import { BASEMAPS, MEXICO_BOUNDS } from "./basemaps.js";

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

/* How long a second activation on the same terrain still counts as a double.
 * An interaction choice, not a geometry constant: kept here so both the mouse
 * and touch paths use one value. */
const DOBLE_ACTIVACION_MS = 280;
/* A second tap further than this from the first is a new gesture, not a double. */
const DOBLE_ACTIVACION_PX = 28;

export const ZOOM_MAXIMO = 20;

export function createMapCanvas(container, { onSelect, onScaleChange, onDoubleSelect } = {}) {
  const map = L.map(container, {
    zoomControl: false,
    attributionControl: true,
    preferCanvas: true, // one canvas beats hundreds of SVG nodes when panning
    maxZoom: ZOOM_MAXIMO,
    minZoom: 3,
  });

  map.fitBounds(MEXICO_BOUNDS);
  L.control.zoom({ position: "topright" }).addTo(map);
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
  function render(terrenos, { colorFor, dashFor = null, geometrias = null } = {}) {
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

    for (const terreno of contornos) {
      if (byId.has(terreno.id)) continue;           // one logical mark per terrain
      byId.set(terreno.id, crearContorno(
        terreno, geometrias, zoom, offsets.get(terreno.id) ?? 0, colorFor, dashFor));
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
  function crearContorno(terreno, geometrias, zoom, extra, colorFor, dashFor) {
    const descriptor = terreno.geometria;
    const cuerpo = cuerpoLeaflet(descriptor, geometrias);
    const disponible = cuerpo.estado === "cargado";
    const fill = colorFor(terreno);
    const dash = dashFor?.(terreno) ?? null;
    const symbolic = SYMBOL_RADIUS + extra;
    const html = tooltipHtml(terreno, { sinContorno: !disponible });

    const simbolo = L.circleMarker(puntoLeaflet(descriptor.punto_interior), {
      radius: symbolic,
      opacity: 1,
      fillColor: fill,
      bubblingMouseEvents: false,
      ...simboloStyle({ fill, dash, disponible }),
    });
    simbolo.bindTooltip(html, {
      direction: "top", offset: [0, -symbolic - 2], opacity: 1, className: "mark-tooltip",
    });
    wireActivation(simbolo, terreno.id);

    let contorno = null;
    if (disponible) {
      contorno = L.polygon(cuerpo.partes, {
        fillColor: fill,
        bubblingMouseEvents: false,
        ...contornoStyle({ fill, dash }),
      });
      contorno.bindTooltip(html, { sticky: true, opacity: 1, className: "mark-tooltip" });
      wireActivation(contorno, terreno.id);
    }

    const entry = {
      tipo: "contorno",
      simbolo, contorno, disponible, fill, dash, symbolic,
      bbox: descriptor.bbox,
      punto: puntoLeaflet(descriptor.punto_interior),
      posiciones: disponible ? cuerpo.posiciones : 0,
      aEscala: false,
    };
    mostrarContorno(entry, zoom);
    return entry;
  }

  /** Show the outline or the symbol for this zoom; returns whether it changed. */
  function mostrarContorno(entry, zoom) {
    const aEscala = Boolean(entry.contorno) && contornoAEscala(entry.bbox, zoom);
    const yaVisible = entry.contorno && contornoLayer.hasLayer(entry.contorno);
    if (aEscala === entry.aEscala && (yaVisible || markerLayer.hasLayer(entry.simbolo))) {
      return false;
    }
    entry.aEscala = aEscala;
    if (aEscala) {
      markerLayer.removeLayer(entry.simbolo);
      entry.contorno.addTo(contornoLayer);
      entry.contorno.bringToBack();          // below every circle and symbol
    } else {
      if (entry.contorno) contornoLayer.removeLayer(entry.contorno);
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
        if (entry.aEscala) {
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
    const requerido = zoomDeContorno(entry.bbox, maximo);
    map.stop();
    map.fitBounds(limitesLeaflet(entry.bbox), {
      padding: [40, 40], maxZoom: maximo, animate: false,
    });
    if (requerido !== null && map.getZoom() < requerido) {
      map.setView(entry.punto, requerido, { animate: false });
    }
    const zoom = map.getZoom();
    if (!entry.disponible) {
      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo };
    }
    return {
      estado: contornoAEscala(entry.bbox, zoom) ? "a_escala" : "limite_de_zoom",
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
    return { x: p.x, y: p.y, tipo: entry.tipo, contorno: Boolean(entry.aEscala && entry.contorno) };
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
    get basemap() { return basemapKey; },
  };
}

/** A boundary symbol: solid when its outline is loaded, hollow and dashed when not. */
function simboloStyle({ fill, dash, disponible, selected = false }) {
  if (selected) {
    return { color: "#111111", weight: 3, dashArray: disponible ? null : SIN_CONTORNO.dashArray,
             fillOpacity: disponible ? 1 : 0.32 };
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
  if (selected) return { color: "#111111", weight: 3, dashArray: null, fillOpacity: 0.32 };
  return { color: fill, weight: HUELLA.weight, dashArray: dash, fillOpacity: HUELLA.fillOpacity };
}

function tooltipHtml(terreno, { sinContorno = false } = {}) {
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
    (sinContorno ? `<span class="mark-tooltip-aviso">Contorno no disponible</span>` : "")
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

/* The Leaflet map: basemaps, markers, selection and fitting.
 *
 * Kept deliberately imperative and self-contained -- Leaflet owns its own DOM,
 * so the rest of the app talks to it through this small surface instead of
 * re-rendering it.
 */

import { MARK_RING } from "../../lib/colors.js";
import { fmtArea, fmtUnitPrice } from "../../lib/format.js";
import {
  coincidentRingOffsets, markRadius, SYMBOL_RADIUS, trueScaleZoom,
} from "../../lib/geo.js";
import { BASEMAPS, MEXICO_BOUNDS } from "./basemaps.js";

/* A mark has two jobs and two looks.
 *
 * As a SYMBOL it is a filled dot with a white ring: small, legible, and read
 * against its neighbours. As a FOOTPRINT it covers real ground, so it becomes
 * a translucent wash with its own colour as the outline -- you have to be able
 * to see the land underneath the shape that claims to describe it. */
const SIMBOLO = { fillOpacity: 0.82, weight: 2, ring: MARK_RING };
const HUELLA  = { fillOpacity: 0.20, weight: 2 };

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

  /** Draw a set of terrains. `colorFor` maps a terrain to its fill colour. */
  function render(terrenos, { colorFor, dashFor = null } = {}) {
    markerLayer.clearLayers();
    byId = new Map();

    const plotted = terrenos.filter((t) => t.ubicado);
    const offsets = coincidentRingOffsets(plotted);

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
      marker.on("click", (event) => {
        L.DomEvent.stop(event);
        activar(terreno.id, event);
      });
      // Swallow the marker's own double-click so Leaflet does not also apply
      // its ordinary zoom-in. Background double-click keeps working.
      marker.on("dblclick", (event) => L.DomEvent.stop(event));

      marker.addTo(markerLayer);
      byId.set(terreno.id, {
        marker, radius, dash, symbolic, fill, aEscala,
        m2: terreno.superficie_m2, lat: terreno.lat, lon: terreno.lon,
      });
    }

    applySelection();
    reportScale();
    return plotted.length;
  }

  /** Re-measure every mark against the new zoom. */
  function resizeMarks() {
    const zoom = map.getZoom();
    for (const [id, entry] of byId) {
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
    for (const entry of byId.values()) {
      const extra = entry.symbolic - SYMBOL_RADIUS;
      if (markRadius(entry.m2, entry.lat, zoom, { extra }).aEscala) aEscala += 1;
    }
    onScaleChange({ aEscala, total: byId.size, zoom });
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
      entry.marker.setStyle(markStyle({ ...entry, selected }));
      if (selected) entry.marker.bringToFront();
    }
  }

  function select(id, { pan = false } = {}) {
    selectedId = id;
    applySelection();
    const entry = byId.get(id);
    if (entry && pan) {
      map.setView(entry.marker.getLatLng(), Math.max(map.getZoom(), 13), {
        animate: !prefersReducedMotion(),
      });
    }
  }

  function fitTo(terrenos) {
    const points = terrenos.filter((t) => t.ubicado).map((t) => [t.lat, t.lon]);
    if (!points.length) {
      map.fitBounds(MEXICO_BOUNDS);
      return;
    }
    if (points.length === 1) {
      map.setView(points[0], 13);
      return;
    }
    map.fitBounds(L.latLngBounds(points).pad(0.12));
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
    invalidate: () => map.invalidateSize(),
    get basemap() { return basemapKey; },
  };
}

function tooltipHtml(terreno) {
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
    (figures ? `<span class="figure">${escapeHtml(figures)}</span>` : "")
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

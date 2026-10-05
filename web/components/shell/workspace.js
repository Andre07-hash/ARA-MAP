/* The persistent map workspace shared by the catalog, the inventory and the
 * legacy bases/maps: rails, toolbar, map drawing, selection and scale zoom. */

import { layerColor, layerDash, priceColor } from "../../lib/colors.js";
import { el } from "../../lib/dom.js";
import { FILTROS_VACIOS } from "../../lib/inventario.js";
import { navigate } from "../../lib/router.js";
import { getState, resetFilters, setDataset, setFilter, setState } from "../../lib/store.js";
import { pedirCarga } from "../inventory/datasets.js";
import { createMapCanvas } from "../map/MapCanvas.js";
import { escalaTexto } from "../map/Legend.js";
import { createFilterRail } from "../terrain/FilterRail.js";
import { openFiltersDrawer } from "../terrain/FiltersDrawer.js";
import { toast, toastError } from "../ui/toast.js";
import { shell } from "./context.js";

/* The toolbar is rebuilt on every change (a reload, a page arriving); a
 * focused control with an id is focused again, so keyboard users keep place. */
export function replaceKeepingFocus(host, children) {
  const active = document.activeElement;
  const id = active && host.contains(active) ? active.id : "";
  host.replaceChildren(...children);
  if (id) document.getElementById(id)?.focus();
}

/* ------------------------------------------------------------- map screen */

/* The map workspace is built once and kept. Rebuilding it on every state
 * change is what destroyed the focused search box after each character, and it
 * also threw away Leaflet's markers between a click and its double-click. */

export function ensureWorkspace() {
  if (shell.workspace) return shell.workspace;

  shell.mapHost = el("div", { class: "map-host", id: "map-host" });

  const toolbar = el("div", { class: "toolbar" });
  const overlays = el("div", { class: "stage-overlays" });
  const mensaje = el("div", { class: "stage-mensaje-slot" });
  const unplacedSlot = el("div", { class: "unplaced-slot" });
  const tableSlot = el("div", { class: "table-slot" });
  const stage = el("div", { class: "stage" }, shell.mapHost, tableSlot, overlays, mensaje, unplacedSlot);

  const railSlot = el("div", { class: "rail-slot" });
  const detailSlot = el("div", { class: "detail-slot" });
  const root = el("div", { class: "workspace" },
    railSlot,
    el("div", { class: "stage-slot" }, toolbar, stage),
  );

  shell.workspace = {
    root, rails: {}, railSlot, toolbar, overlays, mensaje, unplacedSlot, tableSlot, detailSlot,
  };
  return shell.workspace;
}

/* One persistent rail per context: a legacy base ("local"), the catalog and
 * the inventory each keep their own typed values and checked boxes. */
export function usarRail(modo) {
  const ws = ensureWorkspace();
  if (!ws.rails[modo]) {
    ws.rails[modo] = modo === "local"
      ? createFilterRail({ onChange: (patch) => setFilter(patch), onReset: () => resetFilters() })
      : createFilterRail({
        modo,
        onChange: (patch) => {
          setDataset(modo, { filtros: { ...getState()[modo].filtros, ...patch } });
          pedirCarga(modo);
        },
        onReset: () => {
          setDataset(modo, { filtros: FILTROS_VACIOS });
          pedirCarga(modo, { inmediato: true });
        },
      });
  }
  const rail = ws.rails[modo];
  // While the phone drawer holds the rail, it stays there.
  if (!rail.element.closest("dialog") && rail.element.parentNode !== ws.railSlot) {
    ws.railSlot.replaceChildren(rail.element);
  }
  return rail;
}

function abrirFiltros(modo) {
  const ws = ensureWorkspace();
  openFiltersDrawer({
    rail: usarRail(modo),
    slot: ws.railSlot,
    onClosed: () => {
      document.getElementById("filtros-btn")?.focus();
      shell.canvas?.invalidate();
    },
  });
}

/* Shown only below 960px, where the rail itself is hidden. */
export const FiltrosBoton = (modo, activos) => el("button", {
  type: "button", id: "filtros-btn", class: "btn btn-quiet filtros-btn", "aria-haspopup": "dialog",
  onclick: () => abrirFiltros(modo),
}, activos ? `Filtros (${activos})` : "Filtros");

export function ordenarTabla(campo) {
  shell.tableSort = campo === shell.tableSort.campo
    ? { campo, direccion: shell.tableSort.direccion === "asc" ? "desc" : "asc" }
    : { campo, direccion: "asc" };
  setState({});
}

/* --------------------------------------------------------------- map draw */

/* `vista` is { basemap, capas, modoColor, seleccionado }; `encuadrar` frames
 * the data once, when a dataset first arrives. */
export function drawMap(vista, filtrados, breaks, { encuadrar = false } = {}) {
  // The container must be in the document before Leaflet measures it.
  requestAnimationFrame(() => {
    const primeraVez = !shell.canvas;
    if (primeraVez) {
      shell.canvas = createMapCanvas(shell.mapHost, {
        onSelect: (id) => selectTerreno(id),
        onDoubleSelect: (id) => zoomTerrenoAEscala(id),
        // Written straight into the legend: routing it through the store would
        // re-render the map, which would report the scale again, and so on.
        onScaleChange: (escala) => {
          shell.escalaActual = escala;
          const nota = document.querySelector(".legend-escala");
          if (nota) nota.textContent = escalaTexto(escala);
        },
      });

      // Opt-in hook so browser tests can turn a terrain's coordinates into
      // screen pixels and send a real double click at it. It exists only when
      // asked for with ?test=1, never in normal use.
      if (new URLSearchParams(location.search).has("test")) {
        window.__araTest = {
          puntoDe(id) {
            const t = shell.itemsActuales.find((x) => x.id === id);
            if (!t?.ubicado) return null;
            const punto = shell.canvas.map.latLngToContainerPoint([t.lat, t.lon]);
            const caja = shell.mapHost.getBoundingClientRect();
            return { x: caja.left + punto.x, y: caja.top + punto.y };
          },
          zoom: () => shell.canvas.map.getZoom(),
          irA: (lat, lon, z) => shell.canvas.setView([lat, lon], z),
        };
      }
    }
    shell.canvas.setBasemap(vista.basemap);
    // Leaflet has to know its real size before it can frame anything, so the
    // first fit happens after the container has been measured -- otherwise it
    // frames a zero-sized viewport and lands zoomed far out.
    shell.canvas.invalidate();
    if (primeraVez || encuadrar) shell.canvas.fitTo(filtrados);

    const porBase = vista.modoColor === "base" && vista.capas.length > 0;
    const colores = new Map(vista.capas.map((c) => [c.orden ?? 0, c.color]));
    const indices = new Map(vista.capas.map((c, i) => [c.orden ?? 0, i]));

    shell.canvas.render(filtrados, {
      colorFor: (t) => (porBase
        ? colores.get(t.capa ?? 0) ?? layerColor(0, vista.basemap)
        : priceColor(t.asking_m2, breaks)),
      dashFor: (t) => (porBase ? layerDash(indices.get(t.capa ?? 0) ?? 0) : null),
    });
    shell.canvas.select(vista.seleccionado);
  });
}

export function selectTerreno(id, { pan = false } = {}) {
  const { ruta } = getState();
  if (ruta.nombre === "catalogo" || ruta.nombre === "inventario") {
    navigate({ nombre: ruta.nombre, id }, { replace: true });
  } else {
    setState({ seleccionado: id });
  }
  shell.canvas?.select(id, { pan });
}

export function toggleCapa(orden) {
  setState((state) => ({
    capas: state.capas.map((capa) =>
      (capa.orden ?? 0) === orden ? { ...capa, visible: !capa.visible } : capa),
  }));
}

export function changeBasemap(basemap) {
  setState((state) => ({
    basemap,
    // Layer colours are stepped for the surface they sit on, so switching to
    // satellite re-steps them rather than keeping the light-surface values.
    capas: state.capas.map((capa, index) => ({ ...capa, color: layerColor(index, basemap) })),
    terrenos: state.terrenos.map((t) => ({
      ...t,
      color: layerColor(
        state.capas.findIndex((c) => (c.orden ?? 0) === (t.capa ?? 0)),
        basemap,
      ),
    })),
  }));
}

/**
 * Zoom until the terrain's circle covers its real area, and centre it.
 *
 * The detail panel is opened first and the map re-measured before framing,
 * because the panel takes a third of the width: framing before it lands would
 * leave the terrain sitting behind it.
 */
export async function zoomTerrenoAEscala(id) {
  selectTerreno(id);
  await new Promise((listo) =>
    requestAnimationFrame(() => requestAnimationFrame(listo)));
  shell.canvas?.invalidate();

  const resultado = shell.canvas?.zoomToScale(id);
  if (!resultado) return;

  const terreno = shell.itemsActuales.find((t) => t.id === id);
  const nombre = terreno?.terreno ?? "El terreno";

  if (resultado.estado === "a_escala") {
    toast(`${nombre}: el círculo ya cubre su superficie real.`);
  } else if (resultado.estado === "limite_de_zoom") {
    toastError(
      "Este terreno necesita más acercamiento del disponible para verse a escala."
    );
  } else if (resultado.estado === "sin_area") {
    toastError(`${nombre} no tiene superficie registrada, así que no se puede dibujar a escala.`);
  } else if (resultado.estado === "sin_ubicacion") {
    toastError(`${nombre} no tiene coordenadas válidas para centrarlo.`);
  }
}

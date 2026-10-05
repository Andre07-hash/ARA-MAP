/* A legacy base or saved map open on the shared workspace (client-side
 * filtering, layers, comparison). */

import { priceBreaks } from "../../lib/colors.js";
import { clear, el } from "../../lib/dom.js";
import { activeCount, applyFilters, sinFiltrosDePrecio } from "../../lib/filters.js";
import { monedasDe } from "../../lib/format.js";
import { getState, setState } from "../../lib/store.js";
import { importWorkbook } from "../bases/ImportDialog.js";
import { segment } from "../inventory/DatosView.js";
import { BasemapSwitcher } from "../map/BasemapSwitcher.js";
import { Legend } from "../map/Legend.js";
import { openSaveMapDialog } from "../maps/OverlayBuilder.js";
import { api } from "../../lib/api.js";
import { TerrainDetail } from "../terrain/TerrainDetail.js";
import { TerrainTable } from "../terrain/TerrainTable.js";
import { UnplacedList } from "../terrain/UnplacedList.js";
import { shell } from "./context.js";
import {
  actualizarMapa, afterBaseChange, exportar, guardarVista, vistaActual,
} from "./legacyActions.js";
import {
  changeBasemap, drawMap, ensureWorkspace, FiltrosBoton, ordenarTabla, replaceKeepingFocus,
  selectTerreno, toggleCapa, usarRail, zoomTerrenoAEscala,
} from "./workspace.js";

export function renderMapa(host, state) {
  if (!state.terrenos.length && !state.baseActiva && !state.mapaActivo) {
    clear(host).append(el("div", { class: "screen" },
      el("div", { class: "empty-state" },
        el("h2", {}, "Nada que mostrar todavía"),
        el("p", { class: "secondary" },
          shell.readOnly ? "Todavía no hay terrenos publicados." : "Importa una base de terrenos para verla en el mapa."),
        !shell.readOnly && el("button", {
          type: "button", class: "btn btn-principal",
          onclick: () => importWorkbook({
            onDone: afterBaseChange, carpetas: getState().carpetas.bases,
          }),
        }, "Importar archivo"),
      )));
    return;
  }

  const visibles = visibleTerrenos(state);
  // Prices in more than one currency (or with an unrecorded one) share no
  // scale: no common colour bands, price filters or price sorting. Location
  // and everything else still compare normally.
  const monedas = monedasDe(visibles);
  const preciosComparables = monedas.length <= 1;
  const filtrados = applyFilters(visibles,
    preciosComparables ? state.filtros : sinFiltrosDePrecio(state.filtros));
  const ubicados = filtrados.filter((t) => t.ubicado);
  const sinUbicacion = filtrados.filter((t) => !t.ubicado);
  const breaks = preciosComparables ? priceBreaks(visibles.map((t) => t.asking_m2)) : null;
  const seleccionado = filtrados.find((t) => t.id === state.seleccionado) ?? null;

  shell.itemsActuales = state.terrenos;
  const ws = ensureWorkspace();
  if (ws.root.parentNode !== host) clear(host).append(ws.root);
  ws.mensaje.replaceChildren();

  usarRail("local").update({
    terrenos: visibles,
    filtros: state.filtros,
    visibles: filtrados.length,
    monedas,
  });

  replaceKeepingFocus(ws.toolbar, MapToolbar(state, filtrados));

  ws.tableSlot.replaceChildren(
    ...(state.panel === "tabla"
      ? [el("div", { class: "table-panel" },
          TerrainTable({
            terrenos: filtrados,
            orden: shell.tableSort.campo,
            direccion: shell.tableSort.direccion,
            seleccionado: state.seleccionado,
            comparando: state.capas.length > 1,
            preciosComparables,
            onSort: ordenarTabla,
            onSelect: (id) => selectTerreno(id, { pan: true }),
          })
        )]
      : [])
  );

  // The table covers the map entirely, so the map's own furniture is not drawn
  // behind it -- it would otherwise float over the rows.
  ws.overlays.replaceChildren(
    ...(state.panel === "mapa"
      ? [
          Legend({
            modo: state.modoColor,
            capas: state.capas,
            breaks,
            monedas,
            conteo: ubicados.length,
            sinUbicacion: sinUbicacion.length,
            invalidas: sinUbicacion.filter((t) => t.ubicacion === "invalida").length,
            escala: shell.escalaActual,
            onToggleCapa: toggleCapa,
          }),
          BasemapSwitcher({ activo: state.basemap, onChange: changeBasemap }),
        ]
      : [])
  );

  ws.unplacedSlot.replaceChildren(
    ...(state.panel === "mapa"
      ? [UnplacedList({
          terrenos: sinUbicacion,
          seleccionado: state.seleccionado,
          abierto: shell.unplacedOpen,
          onSelect: (id) => selectTerreno(id),
          onToggle: () => { shell.unplacedOpen = !shell.unplacedOpen; setState({}); },
        })]
      : [])
  );

  if (seleccionado) {
    ws.detailSlot.replaceChildren(TerrainDetail({
      terreno: seleccionado,
      baseNombre: baseNameFor(state, seleccionado),
      onZoomAEscala: () => zoomTerrenoAEscala(seleccionado.id),
      onClose: () => setState({ seleccionado: null }),
    }));
    if (ws.detailSlot.parentNode !== ws.root) ws.root.append(ws.detailSlot);
  } else {
    ws.detailSlot.remove();
  }

  drawMap(state, filtrados, breaks);
}

/** The toolbar's children. The toolbar element itself persists. */
function MapToolbar(state, filtrados) {
  const titulo = state.mapaActivo?.nombre ?? state.baseActiva?.nombre ?? "Mapa";

  return [
    el("div", { class: "toolbar-title" },
      el("span", { class: "eyebrow" },
        state.mapaActivo ? (state.mapaActivo.tipo === "comparacion" ? "Comparación" : "Mapa guardado") : "Base"),
      el("h1", { class: "truncate", title: titulo }, titulo),
    ),
    el("div", { class: "toolbar-actions" },
      FiltrosBoton("local", activeCount(state.filtros)),
      state.capas.length > 1 && el("div", { class: "segmented", role: "group", "aria-label": "Colorear por" },
        segment("Por base", state.modoColor === "base", () => setState({ modoColor: "base" })),
        segment("Por precio", state.modoColor === "precio", () => setState({ modoColor: "precio" })),
      ),
      el("div", { class: "segmented", role: "group", "aria-label": "Vista" },
        segment("Mapa", state.panel === "mapa", () => setState({ panel: "mapa" })),
        segment("Tabla", state.panel === "tabla", () => setState({ panel: "tabla" })),
      ),
      el("button", {
        type: "button", class: "btn btn-quiet",
        onclick: () => shell.canvas?.fitTo(filtrados),
      }, "Encuadrar"),
      el("button", {
        type: "button", class: "btn btn-quiet",
        onclick: () => exportar(state, filtrados),
      }, "Exportar"),
      !shell.readOnly && state.mapaActivo && el("button", {
        type: "button", class: "btn btn-quiet",
        title: "Vuelve a copiar los terrenos desde las bases de origen",
        onclick: () => actualizarMapa(state.mapaActivo),
      }, "Actualizar"),
      !shell.readOnly && state.mapaActivo && el("button", {
        type: "button", class: "btn btn-quiet",
        title: "Guarda los filtros, el mapa base y la vista actual en este mapa",
        onclick: () => guardarVista(state),
      }, "Guardar vista"),
      !shell.readOnly && state.baseActiva && !state.mapaActivo && el("button", {
        type: "button", class: "btn btn-principal",
        onclick: () => openSaveMapDialog({
          base: state.baseActiva,
          carpetas: getState().carpetas.mapas,
          basemap: state.basemap,
          modoColor: state.modoColor,
          vista: vistaActual(state),
          onCreated: async () => {
            const { mapas } = await api.mapas();
            setState({ mapas });
          },
        }),
      }, "Guardar como mapa"),
    ),
  ].filter(Boolean);
}

function visibleTerrenos(state) {
  if (!state.capas.length) return state.terrenos;
  const ocultas = new Set(
    state.capas.filter((c) => !c.visible).map((c) => c.orden ?? 0)
  );
  return ocultas.size
    ? state.terrenos.filter((t) => !ocultas.has(t.capa ?? 0))
    : state.terrenos;
}

function baseNameFor(state, terreno) {
  return terreno.base_nombre
    ?? state.capas.find((c) => (c.orden ?? 0) === (terreno.capa ?? 0))?.nombre
    ?? state.baseActiva?.nombre;
}

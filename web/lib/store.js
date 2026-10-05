/* The application's shared state.
 *
 * Updates replace state rather than mutating it, so a listener always sees a
 * complete, consistent snapshot.
 */

import { EMPTY_FILTERS } from "./filters.js";
import { FILTROS_VACIOS } from "./inventario.js";

/* A server-queried terrain list: the public catalog or the team inventory. */
export const DATASET_VACIO = Object.freeze({
  registros: [],            // complete assembled result of `consulta`, never one page
  facets: {},
  filtros: FILTROS_VACIOS,
  consulta: null,           // the query string `registros` answers
  cargando: false,
  cargado: false,
  progreso: null,           // { recibidos, total } while pages are assembling
  error: null,
});

const INITIAL = Object.freeze({
  ruta: { nombre: "catalogo", id: null },
  sesion: null,             // { id, display_name } while signed in
  sesionLista: false,       // the first /api/session answer has arrived
  catalogo: DATASET_VACIO,
  inventario: DATASET_VACIO,
  detalle: null,            // { tipo, id, terreno, cargando, error } for the open terrain

  // The legacy workspace (signed in only).
  bases: [],               // always the complete lists, never a folder's subset
  mapas: [],
  carpetas: { bases: [], mapas: [] },
  carpetasError: { bases: null, mapas: null },
  // Each dashboard remembers its own folder: "all", "unfiled" or a folder id.
  carpetaVista: { bases: "all", mapas: "all" },
  mapaActivo: null,         // the saved map being shown, if any
  baseActiva: null,
  terrenos: [],
  capas: [],                // [{ base_id, nombre, color, visible }]
  seleccionado: null,       // terrain id shown in the detail panel
  filtros: { ...EMPTY_FILTERS },

  basemap: "claro",
  modoColor: "precio",      // precio | base
  panel: "mapa",            // mapa | tabla
  cargando: false,
});

/* Everything a signed-in session may have loaded. Logout resets all of it. */
const PRIVATE_KEYS = [
  "sesion", "inventario", "detalle", "bases", "mapas", "carpetas", "carpetasError",
  "carpetaVista", "mapaActivo", "baseActiva", "terrenos", "capas", "seleccionado", "filtros",
];

let state = { ...INITIAL };
const listeners = new Set();

export const getState = () => state;

export function setState(patch) {
  const next = typeof patch === "function" ? patch(state) : patch;
  state = { ...state, ...next };
  for (const listener of listeners) listener(state);
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetFilters() {
  return setState({ filtros: { ...EMPTY_FILTERS } });
}

export function setFilter(patch) {
  return setState((current) => ({ filtros: { ...current.filtros, ...patch } }));
}

/** Patch one dataset (catalogo | inventario). */
export function setDataset(tipo, patch) {
  return setState((current) => ({ [tipo]: { ...current[tipo], ...patch } }));
}

/** Forget every private value. The public catalog and map preferences stay. */
export function clearPrivateState() {
  return setState(Object.fromEntries(PRIVATE_KEYS.map((k) => [k, INITIAL[k]])));
}

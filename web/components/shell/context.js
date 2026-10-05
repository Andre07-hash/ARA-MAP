/* State the shell's modules share. One mutable object, so a module that
 * reassigns (the map canvas once created, the table sort) is seen by all. */

export const SORT_COMPARACION = { campo: "cambio", direccion: "asc" };

export const shell = {
  canvas: null,          // the Leaflet wrapper, created on first map render
  mapHost: null,         // its persistent container element
  workspace: null,       // the persistent map workspace (see workspace.js)
  unplacedOpen: false,
  escalaActual: null,    // { aEscala, total, zoom }
  tableSort: { campo: "orden", direccion: "asc" },
  readOnly: true,        // legacy workspace actions: signed in only
  cloud: false,
  itemsActuales: [],     // what the map currently shows, for selection lookups
  encuadrado: { catalogo: false, inventario: false },
};

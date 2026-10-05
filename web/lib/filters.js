/* Filtering and derived options for the screening tools.
 *
 * Pure functions over a terrain list: the same filter drives the markers, the
 * unplaced list and the table, so the three can never disagree.
 */

import { foldText } from "./format.js";

export const EMPTY_FILTERS = Object.freeze({
  busqueda: "",
  estados: [],
  municipios: [],
  superficieMin: null,
  superficieMax: null,
  precioMin: null,
  precioMax: null,
  unitarioMin: null,
  unitarioMax: null,
  soloUbicados: false,
  soloConIncidencias: false,
});

const inRange = (value, min, max) => {
  if (min != null && (value == null || value < min)) return false;
  if (max != null && (value == null || value > max)) return false;
  return true;
};

export function matches(terreno, filters) {
  const f = { ...EMPTY_FILTERS, ...filters };

  if (f.soloUbicados && !terreno.ubicado) return false;
  if (f.soloConIncidencias && !(terreno.incidencias?.length > 0)) return false;
  if (f.estados.length && !f.estados.includes(terreno.estado)) return false;
  if (f.municipios.length && !f.municipios.includes(terreno.municipio)) return false;

  if (!inRange(terreno.superficie_m2, f.superficieMin, f.superficieMax)) return false;
  if (!inRange(terreno.asking_price, f.precioMin, f.precioMax)) return false;
  if (!inRange(terreno.asking_m2, f.unitarioMin, f.unitarioMax)) return false;

  if (f.busqueda) {
    const needle = foldText(f.busqueda);
    const haystack = foldText(
      [terreno.terreno, terreno.municipio, terreno.estado, terreno.direccion]
        .filter(Boolean).join(" ")
    );
    if (!haystack.includes(needle)) return false;
  }
  return true;
}

export function applyFilters(terrenos, filters) {
  return terrenos.filter((t) => matches(t, filters));
}

/** The same filters without the price ranges: for prices in mixed currencies. */
export function sinFiltrosDePrecio(filters) {
  return { ...filters, precioMin: null, precioMax: null, unitarioMin: null, unitarioMax: null };
}

/** How many filters the user has actually set, for the "limpiar (3)" affordance. */
export function activeCount(filters) {
  const f = { ...EMPTY_FILTERS, ...filters };
  let count = 0;
  if (f.busqueda) count += 1;
  if (f.estados.length) count += 1;
  if (f.municipios.length) count += 1;
  if (f.superficieMin != null || f.superficieMax != null) count += 1;
  if (f.precioMin != null || f.precioMax != null) count += 1;
  if (f.unitarioMin != null || f.unitarioMax != null) count += 1;
  if (f.soloUbicados) count += 1;
  if (f.soloConIncidencias) count += 1;
  return count;
}

/**
 * The option lists the rail offers. Municipality options narrow to the
 * selected states, so the list stays usable instead of listing all of Mexico.
 */
export function deriveOptions(terrenos, filters = EMPTY_FILTERS) {
  const estados = tally(terrenos, "estado");
  const scoped = filters.estados?.length
    ? terrenos.filter((t) => filters.estados.includes(t.estado))
    : terrenos;
  const municipios = tally(scoped, "municipio");

  return {
    estados,
    municipios,
    rangos: {
      superficie: extent(terrenos, "superficie_m2"),
      precio: extent(terrenos, "asking_price"),
      unitario: extent(terrenos, "asking_m2"),
    },
  };
}

function tally(terrenos, campo) {
  const counts = new Map();
  for (const terreno of terrenos) {
    const value = terreno[campo];
    if (!value) continue;
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([valor, conteo]) => ({ valor, conteo }))
    .sort((a, b) => b.conteo - a.conteo || a.valor.localeCompare(b.valor, "es"));
}

function extent(terrenos, campo) {
  const values = terrenos
    .map((t) => t[campo])
    .filter((v) => typeof v === "number" && Number.isFinite(v));
  return values.length ? { min: Math.min(...values), max: Math.max(...values) } : null;
}

export const SORTS = {
  orden:      { etiqueta: "Orden original", get: (t) => t.orden },
  terreno:    { etiqueta: "Nombre",         get: (t) => foldText(t.terreno), texto: true },
  estado:     { etiqueta: "Estado",         get: (t) => foldText(t.estado ?? ""), texto: true },
  superficie: { etiqueta: "Superficie",     get: (t) => t.superficie_m2 },
  precio:     { etiqueta: "Asking Price",   get: (t) => t.asking_price },
  unitario:   { etiqueta: "Asking $/m²",    get: (t) => t.asking_m2 },
};

/**
 * Sort a copy. Missing numbers always sink, in either direction.
 * `sorts` lets a caller add columns that only exist in some views.
 */
export function sortTerrenos(terrenos, campo = "orden", direccion = "asc", sorts = SORTS) {
  const spec = sorts[campo] ?? sorts.orden ?? SORTS.orden;
  const sign = direccion === "desc" ? -1 : 1;

  return [...terrenos].sort((a, b) => {
    const left = spec.get(a);
    const right = spec.get(b);
    const leftEmpty = left == null || left === "";
    const rightEmpty = right == null || right === "";
    if (leftEmpty && rightEmpty) return 0;
    if (leftEmpty) return 1;
    if (rightEmpty) return -1;
    if (spec.texto) return sign * String(left).localeCompare(String(right), "es");
    return sign * (left - right);
  });
}

/* The rules of the tables' map (Tabla / Mapa), with no DOM: which rows the
 * map's own filters keep, how they are coloured, and what the read-only
 * record sheet lists.
 *
 * The map's filters narrow the set the table already gathered for its view
 * and query; they never change that query. Prices are coloured by price per
 * m², with thresholds taken from the whole set (not the filtered rows), so a
 * filter never changes what a colour means. Nothing is converted or derived:
 * the sheet shows values as stored, X is latitude and Y is longitude, and a
 * terrain located by its active boundary keeps its own X/Y, empty or not.
 */

import { priceBreaks, priceColor } from "./colors.js";
import { applyFilters, EMPTY_FILTERS } from "./filters.js";
import { ubicacionDe } from "./geometria.js";
import { itemDeInventario } from "./inventario.js";
import { COLUMNAS_BASICAS, textoDe, valorDe } from "./tabla.js";

/* The map's own filters: the shared ones plus the terrain type, a value the
 * rows already carry (`tipo_terreno`, as stored; nothing is classified). */
export const FILTROS_MAPA = Object.freeze({ ...EMPTY_FILTERS, tipos: Object.freeze([]) });

/**
 * A table row as a map row: located by its active boundary or by valid X/Y
 * (geometria.js ubicacionDe), the same adaptation as the inventory's map.
 * `ubicacion` stays the X/Y diagnostic and `registro` the row itself.
 */
export function filaDeMapa(registro) {
  const fila = itemDeInventario(registro);
  return { ...fila, ubicado: ubicacionDe(fila).ubicado };
}

/**
 * Apply the map's own filters to the view's set.
 *
 * `filas` are map rows (filaDeMapa). Options, ranges and colour thresholds
 * come from all of them; `visibles` are the ones the filters keep.
 */
export function filtrarMapa(filas, filtros = FILTROS_MAPA) {
  const visibles = applyFilters(filas, filtros);
  const breaks = priceBreaks(filas.map((t) => t.asking_m2));
  return { visibles, breaks };
}

/** A map row's colour: its price per m² on the view's ramp, grey without one. */
export const colorDeFila = (fila, breaks) => priceColor(fila.asking_m2, breaks);

/** How many of `filas` the map can draw, and how many it cannot. */
export function conteoDeUbicacion(filas) {
  const ubicados = filas.filter((t) => t.ubicado).length;
  return { ubicados, sinUbicacion: filas.length - ubicados };
}

/* The sheet's core fields: the table's columns without the name (the
 * sheet's title), the X/Y (their own section) and the file mounts. */
const OMITIDAS = new Set(["core:terreno", "core:lat", "core:lon"]);
export const CAMPOS_DE_FICHA = Object.freeze(
  COLUMNAS_BASICAS.filter((c) => c.tipo !== "archivo" && !OMITIDAS.has(c.id)));

const vacio = (texto) => (texto === "" ? "—" : texto);

/** [etiqueta, texto, column id] of the core fields, as the table shows them. */
export function camposDeFicha(registro) {
  return CAMPOS_DE_FICHA.map((c) => [c.etiqueta, vacio(textoDe(valorDe(registro, c), c)), c.id]);
}

/**
 * [etiqueta, texto, column id] of the live custom columns of the terrain's OWN base.
 * `definiciones` must be that base's; retired columns are not shown.
 */
export function personalizadasDeFicha(registro, definiciones = []) {
  return definiciones.filter((d) => !d.retirada).map((d) =>
    [d.nombre, vacio(textoDe(valorDe(registro, { id: d.id, custom: true }), d)), d.id]);
}

/**
 * Where the terrain is on this map, in words, and its stored X/Y. A boundary
 * locates it even without X/Y; its X/Y are never filled from the boundary.
 */
export function ubicacionDeFicha(registro) {
  const fila = itemDeInventario(registro);
  const { modo, xy } = ubicacionDe(fila);
  const d = registro.draft ?? {};
  let texto;
  if (modo === "geometria") texto = "En el mapa por su contorno KMZ / KML activo.";
  else if (modo === "punto") texto = "En el mapa por sus coordenadas X/Y; no tiene contorno activo.";
  else if (xy === "invalida") texto = "Fuera del mapa: sus X/Y no son coordenadas válidas en México y no tiene contorno activo.";
  else texto = "Fuera del mapa: no tiene contorno activo ni coordenadas X/Y.";
  return {
    modo, texto,
    x: vacio(textoDe(d.lat ?? null)),
    y: vacio(textoDe(d.lon ?? null)),
  };
}

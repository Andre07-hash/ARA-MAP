/* Folder navigation, as pure functions over the full item lists.
 *
 * The gallery always receives the complete bases/mapas arrays and derives the
 * visible subset here. The arrays themselves are never replaced by a filtered
 * one: comparisons pick sources from every folder.
 *
 * A selection is "all", "unfiled", or a numeric folder id. On an item,
 * carpeta_id null means unfiled; that null never doubles as "all".
 */

export const TODAS = "all";
export const SIN_CARPETA = "unfiled";

export const TEXTOS = {
  bases: { todas: "Todas las bases", singular: "base", plural: "bases" },
  mapas: { todas: "Todos los mapas", singular: "mapa", plural: "mapas" },
};

export const isFolderId = (seleccion) => typeof seleccion === "number";

/** Items in the selected view, in their original order. */
export function filterByFolder(items, seleccion) {
  if (seleccion === TODAS) return items;
  if (seleccion === SIN_CARPETA) return items.filter((item) => item.carpeta_id == null);
  return items.filter((item) => item.carpeta_id === seleccion);
}

/** Counts for every navigation entry, from the items actually held. */
export function folderCounts(items, carpetas) {
  const porCarpeta = new Map(carpetas.map((c) => [c.id, 0]));
  let sinCarpeta = 0;
  for (const item of items) {
    if (item.carpeta_id == null) sinCarpeta += 1;
    else if (porCarpeta.has(item.carpeta_id)) {
      porCarpeta.set(item.carpeta_id, porCarpeta.get(item.carpeta_id) + 1);
    }
  }
  return { todas: items.length, sinCarpeta, porCarpeta };
}

/** A selection that still exists: a deleted folder falls back to unfiled. */
export function resolveSelection(seleccion, carpetas) {
  if (!isFolderId(seleccion)) return seleccion === SIN_CARPETA ? SIN_CARPETA : TODAS;
  return carpetas.some((c) => c.id === seleccion) ? seleccion : SIN_CARPETA;
}

/** The label a view is known by. */
export function selectionLabel(tipo, seleccion, carpetas) {
  if (seleccion === TODAS) return TEXTOS[tipo].todas;
  if (seleccion === SIN_CARPETA) return "Sin carpeta";
  return carpetas.find((c) => c.id === seleccion)?.nombre ?? "Sin carpeta";
}

/** Where an item lives, for the label shown on it. */
export function folderNameOf(item, carpetas) {
  if (item.carpeta_id == null) return "Sin carpeta";
  return carpetas.find((c) => c.id === item.carpeta_id)?.nombre ?? "Sin carpeta";
}

/** The destination a creation dialog starts on: the open folder, if any. */
export const defaultDestination = (seleccion) => (isFolderId(seleccion) ? seleccion : null);

/** Replace one item's membership in a full list, by id. */
export const withFolder = (items, id, carpetaId) =>
  items.map((item) => (item.id === id ? { ...item, carpeta_id: carpetaId } : item));

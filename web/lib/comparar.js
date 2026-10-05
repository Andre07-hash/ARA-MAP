/* Comparing the layers of a saved comparison map.
 *
 * The first layer is the baseline; every other layer is described relative to
 * it. That keeps the answer unambiguous with three or more layers, and matches
 * how the maps are actually read: an older month against a newer one.
 *
 * Matching reuses the rule the importer uses -- normalized name, state and
 * municipality, with area as the tiebreaker -- so a terrain that is genuinely
 * two parcels does not collapse into one row.
 */

import { foldText } from "./format.js";

const AREA_TOLERANCE = 0.005;
const VALUE_TOLERANCE = 0.005;

export const ESTADOS = {
  base:        { etiqueta: "Base",       descripcion: "Está en la capa de referencia" },
  nuevo:       { etiqueta: "Nuevo",      descripcion: "No está en la capa de referencia" },
  eliminado:   { etiqueta: "Eliminado",  descripcion: "Está sólo en la capa de referencia" },
  sin_cambio:  { etiqueta: "Sin cambio", descripcion: "Mismos valores que la referencia" },
  cambiado:    { etiqueta: "Cambiado",   descripcion: "Cambió respecto a la referencia" },
};

/* Coordinates need an absolute tolerance, not a relative one: a longitude near
 * zero would make any relative comparison meaningless. 1e-5 degrees is about a
 * metre, well below the precision the source records carry. */
const GRADO_EPSILON = 1e-5;

const cercaEnGrados = (left, right) => {
  if (left == null && right == null) return true;
  if (left == null || right == null) return false;
  return Math.abs(left - right) <= GRADO_EPSILON;
};

const mismoTexto = (left, right) => {
  const a = (left ?? "").toString().trim();
  const b = (right ?? "").toString().trim();
  return a === b;
};

/* Every field worth reporting a difference in, with how to compare it.
 * Location belongs here: a marker that moved has materially changed, even when
 * every financial figure stayed the same. */
const CAMPOS = [
  { campo: "asking_price",     etiqueta: "Asking Price" },
  { campo: "asking_m2",        etiqueta: "Asking $/m²" },
  // The same amount in another currency is a different price.
  { campo: "moneda",           etiqueta: "Moneda", compara: mismoTexto },
  { campo: "superficie_m2",    etiqueta: "Superficie" },
  { campo: "afectaciones_pct", etiqueta: "Afectaciones" },
  { campo: "lat",              etiqueta: "Ubicación", compara: cercaEnGrados, agrupa: "ubicacion" },
  { campo: "lon",              etiqueta: "Ubicación", compara: cercaEnGrados, agrupa: "ubicacion" },
  { campo: "direccion",        etiqueta: "Dirección", compara: mismoTexto },
];

export function dedupeKey(terreno) {
  return [terreno.terreno, terreno.estado, terreno.municipio]
    .map((part) => foldText(part ?? ""))
    .join("|");
}

function closeEnough(left, right, tolerance = VALUE_TOLERANCE) {
  if (left == null && right == null) return true;
  if (left == null || right == null) return false;
  const largest = Math.max(Math.abs(left), Math.abs(right));
  return largest === 0 ? true : Math.abs(left - right) / largest <= tolerance;
}

/**
 * Find the baseline counterpart of a terrain: same key, comparable area.
 *
 * A baseline row already claimed by another terrain is skipped. Without that,
 * a genuine pair of same-named parcels (the two "Tecamac 26" rows differ by
 * 0.03% in area) would both match the first one, leaving the second baseline
 * row looking removed when nothing was removed.
 */
function findTwin(terreno, candidates, claimed) {
  if (!candidates?.length) return null;

  const viables = candidates.filter((c) =>
    !claimed.has(c.id)
    && closeEnough(c.superficie_m2, terreno.superficie_m2, AREA_TOLERANCE)
  );
  if (!viables.length) return null;
  if (terreno.superficie_m2 == null) return viables[0];

  // The closest area, not merely the first within tolerance: two reference
  // rows can sit within tolerance of each other, and taking the first would
  // pair them crosswise and invent changes.
  return viables.reduce((mejor, c) =>
    Math.abs((c.superficie_m2 ?? 0) - terreno.superficie_m2)
      < Math.abs((mejor.superficie_m2 ?? 0) - terreno.superficie_m2) ? c : mejor
  );
}

/**
 * Which of the reported fields differ between two terrains.
 *
 * Latitude and longitude are reported once, as "Ubicación": they move together
 * and a reader does not care which of the two numbers changed.
 */
export function changedFields(baseline, current) {
  const etiquetas = [];
  const vistos = new Set();

  for (const { campo, etiqueta, compara, agrupa } of CAMPOS) {
    const iguales = (compara ?? closeEnough)(baseline[campo], current[campo]);
    if (iguales) continue;
    const clave = agrupa ?? campo;
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    etiquetas.push(etiqueta);
  }
  return etiquetas;
}

/**
 * Describe every terrain relative to the first layer.
 *
 * Returns a new array; the input is not modified. Terrains that exist only in
 * the baseline are appended as "eliminado" rows so a removal is visible rather
 * than simply absent.
 */
export function compareLayers(terrenos, capas) {
  if (!capas || capas.length < 2) {
    return terrenos.map((t) => ({ ...t, comparacion: null }));
  }

  const baselineOrden = capas[0].orden ?? 0;
  const baseline = terrenos.filter((t) => (t.capa ?? 0) === baselineOrden);

  const byKey = new Map();
  for (const terreno of baseline) {
    const key = dedupeKey(terreno);
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(terreno);
  }

  // Each layer is compared against the reference independently. Sharing one
  // claimed set across layers would let a match in the second layer stop the
  // third from matching the same reference row, inventing a new terrain.
  const reclamadoPorCapa = new Map();
  const vistoPorCapa = new Map();
  const claim = (orden) => {
    if (!reclamadoPorCapa.has(orden)) reclamadoPorCapa.set(orden, new Set());
    return reclamadoPorCapa.get(orden);
  };

  const salida = terrenos.map((terreno) => {
    const orden = terreno.capa ?? 0;
    if (orden === baselineOrden) {
      return { ...terreno, comparacion: { estado: "base", campos: [] } };
    }

    const reclamado = claim(orden);
    const twin = findTwin(terreno, byKey.get(dedupeKey(terreno)), reclamado);
    if (!twin) {
      return { ...terreno, comparacion: { estado: "nuevo", campos: [] } };
    }

    reclamado.add(twin.id);
    if (!vistoPorCapa.has(twin.id)) vistoPorCapa.set(twin.id, new Set());
    vistoPorCapa.get(twin.id).add(orden);

    const campos = changedFields(twin, terreno);
    return {
      ...terreno,
      comparacion: {
        estado: campos.length ? "cambiado" : "sin_cambio",
        campos,
        referencia: twin.id,
      },
    };
  });

  // A reference terrain missing from a later layer was removed from it. With
  // more than two layers the label says which ones it is missing from, rather
  // than being withheld entirely.
  const otras = capas.slice(1).map((c, i) => ({
    orden: c.orden ?? i + 1,
    nombre: c.nombre ?? `Capa ${i + 2}`,
  }));

  for (const terreno of baseline) {
    const presente = vistoPorCapa.get(terreno.id) ?? new Set();
    const ausente = otras.filter((c) => !presente.has(c.orden));
    if (!ausente.length) continue;

    const index = salida.findIndex((s) => s.id === terreno.id);
    if (index < 0) continue;
    salida[index] = {
      ...salida[index],
      comparacion: {
        estado: "eliminado",
        campos: [],
        ausenteEn: ausente.map((c) => c.nombre),
      },
    };
  }

  return salida;
}

/** Counts per state, for the comparison summary. */
export function summarize(terrenos) {
  const counts = {};
  for (const terreno of terrenos) {
    const estado = terreno.comparacion?.estado;
    if (!estado) continue;
    counts[estado] = (counts[estado] ?? 0) + 1;
  }
  return counts;
}

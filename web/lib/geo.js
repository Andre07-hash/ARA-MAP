/* Ground geometry for the map marks.
 *
 * A terrain is stored as a point plus an area, with no boundary. Drawing it as
 * a circle of the right area centred on that point is the most that can be
 * claimed from the data: the position is real, the size is real, the SHAPE is
 * an approximation.
 */

/* Web Mercator, 256 px tiles: metres per pixel at the equator, zoom 0. */
const EQUATOR_METRES_PER_PIXEL = 156543.03392804097;

/** The radius a circle needs to cover `m2`, in metres. */
export function groundRadius(m2) {
  if (typeof m2 !== "number" || !Number.isFinite(m2) || m2 <= 0) return 0;
  return Math.sqrt(m2 / Math.PI);
}

/** Ground metres covered by one screen pixel, at a latitude and zoom. */
export function metresPerPixel(lat, zoom) {
  return (EQUATOR_METRES_PER_PIXEL * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
}

/** How many pixels the true footprint spans at this latitude and zoom. */
export function trueScaleRadius(m2, lat, zoom) {
  const metres = groundRadius(m2);
  if (!metres) return 0;
  return metres / metresPerPixel(lat, zoom);
}

/**
 * The radius to draw, in pixels.
 *
 * Zoomed out, the true footprint is a fraction of a pixel, so the mark falls
 * back to a legible symbol. Zoomed in, the true footprint overtakes the symbol
 * and the circle becomes a real measurement of the land. Taking the larger of
 * the two makes that handover continuous -- no jump, no mode switch.
 */
export function drawnRadius(m2, lat, zoom, symbolic) {
  const real = trueScaleRadius(m2, lat, zoom);
  return { radius: Math.max(symbolic, real), aEscala: real >= symbolic };
}

/** The zoom at which a terrain starts being drawn at its true size. */
export function trueScaleZoom(m2, lat, symbolic) {
  const metres = groundRadius(m2);
  if (!metres || symbolic <= 0) return null;
  // symbolic = metres / (EQ * cos(lat) / 2^z)  ->  solve for z
  const z = Math.log2((symbolic * EQUATOR_METRES_PER_PIXEL * Math.cos((lat * Math.PI) / 180)) / metres);
  return Math.ceil(z);
}

/* Coincident marks --------------------------------------------------------- */

/* Two terrains recorded at the same point would hide one another, so each one
 * after the first is drawn a little wider and they read as concentric rings.
 *
 * The widening is CAPPED. A single coordinate can carry far more than a handful
 * of terrains -- a development entered as sixty lots on one point, or the same
 * base imported twice -- and an uncapped step turns the sixtieth mark into a
 * ring hundreds of pixels across that covers half the country. Past the cap the
 * rings simply stop growing: the pile is still one readable cluster, and the
 * table is where you enumerate what is in it. */
export const COINCIDENT_STEP = 3.5;
export const MAX_COINCIDENT_RINGS = 6;
const COINCIDENT_PRECISION = 5;

/** Extra radius, in pixels, for each terrain sharing a coordinate with another. */
export function coincidentRingOffsets(terrenos) {
  const groups = new Map();
  for (const terreno of terrenos) {
    const key = `${terreno.lat.toFixed(COINCIDENT_PRECISION)},${terreno.lon.toFixed(COINCIDENT_PRECISION)}`;
    const group = groups.get(key);
    if (group) group.push(terreno);
    else groups.set(key, [terreno]);
  }

  const offsets = new Map();
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    group.forEach((terreno, index) => {
      offsets.set(terreno.id, Math.min(index, MAX_COINCIDENT_RINGS) * COINCIDENT_STEP);
    });
  }
  return offsets;
}

/* A symbol is one fixed size for every terrain.
 *
 * It used to scale with area, so that zoomed out you could rank terrains by
 * how big the dot was. In practice that is what made the overview hard to
 * read: a small terrain near a large one is drawn INSIDE it, and with the
 * white separator ring around each mark a cluster turns into a pile of
 * concentric rings instead of a set of pins.
 *
 * So size now means exactly one thing, and only when it can be trusted: the
 * real footprint, once you are close enough to measure it. Zoomed out, the
 * marks are plain circles that say where a terrain is and -- by colour -- what
 * it costs. Area is in the table, and under the mark as soon as you zoom in. */
export const SYMBOL_RADIUS = 7;

/**
 * The radius and mode for one terrain's mark.
 *
 * `extra` widens the symbol so terrains stacked on one coordinate read as
 * concentric rings instead of hiding each other -- see coincidentRingOffsets.
 */
export function markRadius(m2, lat, zoom, { extra = 0 } = {}) {
  return drawnRadius(m2, lat, zoom, SYMBOL_RADIUS + extra);
}

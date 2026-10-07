/* Terrain location for the map: an active KMZ boundary, else X/Y, else none.
 *
 * Pure functions, no DOM and no network, following shared contract v1 §4.
 *
 * Coordinate orders, stated once because ARA's X/Y are latitude/longitude:
 * - Geometry bodies and descriptors are GeoJSON: positions [longitude, latitude],
 *   bbox [west, south, east, north], punto_interior a GeoJSON Point.
 * - Leaflet takes [latitude, longitude]. Every conversion happens here, in the
 *   functions named ...Leaflet, and nowhere else.
 * - Stored X/Y (t.lat / t.lon) are only ever READ, through the existing
 *   validator estadoUbicacion. Nothing here writes them or derives them from
 *   a boundary.
 */

import { estadoUbicacion } from "./inventario.js";
import { metresPerPixel } from "./geo.js";

export const MODO = Object.freeze({ GEOMETRIA: "geometria", PUNTO: "punto", NINGUNA: "ninguna" });

/* A boundary hands over from symbol to outline once its bounding box is at
 * least this many CSS pixels on its SHORTER side. 24 px is the WCAG 2.2
 * minimum target size (SC 2.5.8); below it an outline is a hard-to-hit
 * smudge, while the symbol (14 px plus its ring) is a dependable target. */
export const UMBRAL_CONTORNO_PX = 24;

/* Bodies larger than this are not drawn as outlines. It equals the accepted
 * parser's MAX_VERTICES, so every parser-accepted body is eligible; the
 * measured browser cost of the largest is recorded in the B-2 report. */
export const MAX_POSICIONES_CUERPO = 100_000;

const finito = (v) => typeof v === "number" && Number.isFinite(v);
const lonValida = (v) => finito(v) && v >= -180 && v <= 180;
const latValida = (v) => finito(v) && v >= -90 && v <= 90;

/** [west, south, east, north] with real, ordered coordinates. */
export function bboxValido(b) {
  return Array.isArray(b) && b.length === 4
    && lonValida(b[0]) && latValida(b[1]) && lonValida(b[2]) && latValida(b[3])
    && b[0] <= b[2] && b[1] <= b[3];
}

/** A GeoJSON Point with real [longitude, latitude]. */
export function puntoValido(p) {
  return p !== null && typeof p === "object" && p.type === "Point"
    && Array.isArray(p.coordinates) && p.coordinates.length === 2
    && lonValida(p.coordinates[0]) && latValida(p.coordinates[1]);
}

function puntoEnCaja([lon, lat], [w, s, e, n]) {
  return lon >= w && lon <= e && lat >= s && lat <= n;
}

/**
 * Whether `g` is an ACTIVE, USABLE geometry descriptor (contract v1 §4).
 * Structural checks only: whether the geometry is eligible to locate the
 * terrain was decided upstream and arrives as `utilizable === true`. Anything
 * malformed counts as no descriptor at all, never as a footprint.
 */
export function descriptorActivo(g) {
  return g !== null && typeof g === "object"
    && typeof g.id === "string" && g.id.length > 0
    && g.utilizable === true
    && bboxValido(g.bbox)
    && puntoValido(g.punto_interior)
    && puntoEnCaja(g.punto_interior.coordinates, g.bbox);
}

/**
 * How a terrain is located: {modo, ubicado, xy}.
 *
 * `xy` is the existing X/Y diagnostic ("valida" | "sin_dato" | "invalida"),
 * from the same validator the rest of the app uses. An active usable boundary
 * locates the terrain even when X/Y is blank; otherwise valid X/Y does, as
 * today; otherwise the terrain is unplaced.
 */
export function ubicacionDe({ lat, lon, geometria } = {}) {
  const xy = estadoUbicacion(lat, lon);
  if (descriptorActivo(geometria)) return { modo: MODO.GEOMETRIA, ubicado: true, xy };
  if (xy === "valida") return { modo: MODO.PUNTO, ubicado: true, xy };
  return { modo: MODO.NINGUNA, ubicado: false, xy };
}

/**
 * The renderer's mode for a row. Rows without a `geometria` key are legacy
 * XY rows and keep their caller-supplied `ubicado`, exactly as before.
 */
export function modoDeFila(t) {
  if (t === null || typeof t !== "object") return MODO.NINGUNA;
  if (t.geometria === undefined) return t.ubicado ? MODO.PUNTO : MODO.NINGUNA;
  return ubicacionDe(t).modo;
}

/* ------------------------------------------------------- Leaflet conversion */

/** GeoJSON Point -> Leaflet [lat, lng]. */
export function puntoLeaflet(punto) {
  const [lon, lat] = punto.coordinates;
  return [lat, lon];
}

/** GeoJSON bbox -> Leaflet [[south, west], [north, east]]. */
export function limitesLeaflet([w, s, e, n]) {
  return [[s, w], [n, e]];
}

/**
 * A loaded body, validated and converted for L.polygon, or why not.
 *
 * Returns {estado: "cargado", partes, posiciones, cajaMayor} where `partes`
 * is the Leaflet multipolygon form [[ring of [lat, lng]], ...] per part
 * (shell first, holes after) and `cajaMayor` is the GeoJSON bbox of the
 * part with the largest shell box -- the size that decides whether the
 * outline can be hit; or {estado: "no_disponible"} when the map holds no
 * body for this descriptor; or {estado: "invalido"} for anything malformed,
 * oversized or belonging to a different version. An invalid body is never
 * drawn as if it were a validated footprint.
 */
export function cuerpoLeaflet(descriptor, geometrias) {
  if (!(geometrias instanceof Map) || !descriptorActivo(descriptor)) {
    return { estado: "no_disponible" };
  }
  const cuerpo = geometrias.get(descriptor.id);
  if (cuerpo === undefined || cuerpo === null) return { estado: "no_disponible" };
  if (typeof cuerpo !== "object" || !bboxValido(cuerpo.bbox)
      || !mismaCaja(cuerpo.bbox, descriptor.bbox)) {
    return { estado: "invalido" };
  }
  const gj = cuerpo.geojson;
  if (gj === null || typeof gj !== "object" || gj.type !== "MultiPolygon"
      || !Array.isArray(gj.coordinates) || gj.coordinates.length === 0) {
    return { estado: "invalido" };
  }
  let posiciones = 0;
  const partes = [];
  let cajaMayor = null;
  let areaMayor = -1;
  for (const poligono of gj.coordinates) {
    if (!Array.isArray(poligono) || poligono.length === 0) return { estado: "invalido" };
    const anillos = [];
    for (const [indice, anillo] of poligono.entries()) {
      if (!Array.isArray(anillo) || anillo.length < 4) return { estado: "invalido" };
      posiciones += anillo.length;
      if (posiciones > MAX_POSICIONES_CUERPO) return { estado: "invalido" };
      const convertido = new Array(anillo.length);
      let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
      for (let k = 0; k < anillo.length; k += 1) {
        const p = anillo[k];
        if (!Array.isArray(p) || p.length < 2 || !lonValida(p[0]) || !latValida(p[1])) {
          return { estado: "invalido" };
        }
        convertido[k] = [p[1], p[0]];                  // [lon, lat] -> [lat, lng]
        if (indice === 0) {
          if (p[0] < w) w = p[0];
          if (p[0] > e) e = p[0];
          if (p[1] < s) s = p[1];
          if (p[1] > n) n = p[1];
        }
      }
      if (indice === 0 && (e - w) * (n - s) > areaMayor) {
        areaMayor = (e - w) * (n - s);
        cajaMayor = [w, s, e, n];
      }
      const [a, z] = [anillo[0], anillo[anillo.length - 1]];
      if (a[0] !== z[0] || a[1] !== z[1]) return { estado: "invalido" };
      anillos.push(convertido);
    }
    partes.push(anillos);
  }
  return { estado: "cargado", partes, posiciones, cajaMayor };
}

function mismaCaja(a, b) {
  return a.every((v, i) => Math.abs(v - b[i]) <= 1e-9);
}

/* ------------------------------------------------------------- map geometry */

/** On-screen size of a bbox at a zoom, in CSS pixels: {ancho, alto}. */
export function tamanoEnPantalla([w, s, e, n], zoom) {
  const latMedia = (s + n) / 2;
  const mpp = metresPerPixel(latMedia, zoom);
  const ancho = ((e - w) * 111_320 * Math.cos((latMedia * Math.PI) / 180)) / mpp;
  const alto = ((n - s) * 110_574) / mpp;
  return { ancho, alto };
}

/** Whether a boundary is big enough on screen to be drawn and hit as an outline. */
export function contornoAEscala(bbox, zoom, umbral = UMBRAL_CONTORNO_PX) {
  const { ancho, alto } = tamanoEnPantalla(bbox, zoom);
  return Math.min(ancho, alto) >= umbral;
}

/**
 * The zoom at which a boundary first shows as an outline (null if never
 * within maxZoom). Each zoom level doubles the on-screen size.
 */
export function zoomDeContorno(bbox, maxZoom, umbral = UMBRAL_CONTORNO_PX) {
  for (let z = 0; z <= maxZoom; z += 1) {
    if (contornoAEscala(bbox, z, umbral)) return z;
  }
  return null;
}

/**
 * Leaflet bounds [[s, w], [n, e]] covering the given rows -- whole boundary
 * extents (every part) for boundary rows, points for XY rows -- or null.
 */
export function limitesDeFilas(terrenos) {
  let s = Infinity, w = Infinity, n = -Infinity, e = -Infinity;
  const extender = (lat, lon) => {
    if (lat < s) s = lat;
    if (lat > n) n = lat;
    if (lon < w) w = lon;
    if (lon > e) e = lon;
  };
  for (const t of terrenos ?? []) {
    const modo = modoDeFila(t);
    if (modo === MODO.GEOMETRIA) {
      const [bw, bs, be, bn] = t.geometria.bbox;
      extender(bs, bw);
      extender(bn, be);
    } else if (modo === MODO.PUNTO) {
      extender(t.lat, t.lon);
    }
  }
  return Number.isFinite(s) ? [[s, w], [n, e]] : null;
}

/**
 * The point a terrain's symbol stands on, in GeoJSON-free {id, lat, lon} form
 * for the existing coincident-ring grouping: the interior point for boundary
 * rows, X/Y for point rows.
 */
export function puntoDeSimbolo(t) {
  const modo = modoDeFila(t);
  if (modo === MODO.GEOMETRIA) {
    const [lat, lon] = puntoLeaflet(t.geometria.punto_interior);
    return { id: t.id, lat, lon };
  }
  if (modo === MODO.PUNTO) return { id: t.id, lat: t.lat, lon: t.lon };
  return null;
}

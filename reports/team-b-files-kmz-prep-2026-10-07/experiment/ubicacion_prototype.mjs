/* DISPOSABLE prototype of the proposed boundary-first location rule.
 *
 * Not application code. It shows the smallest extension to MapCanvas: decide
 * per terrain whether it is drawn by boundary, by X/Y point, or not at all,
 * WITHOUT changing how an X/Y terrain is drawn today. The production version
 * is proposed as web/lib/geometria.js (pure) plus a small branch in
 * web/components/map/MapCanvas.js.
 *
 * Geometry shape, as proposed in the contract draft:
 *   t.geometria = { id, estado: "activa", utilizable, bbox: [w, s, e, n],
 *                   punto_simbolo: [lat, lon], geojson? }
 * X/Y stay t.lat / t.lon (X = latitude, Y = longitude), untouched.
 */

import { estadoUbicacion } from "../../../web/lib/inventario.js";
import { metresPerPixel, SYMBOL_RADIUS } from "../../../web/lib/geo.js";

/** "geometria" | "punto" | "ninguna". A usable boundary wins over X/Y. */
export function modoUbicacion(t) {
  const g = t?.geometria;
  if (g && g.estado === "activa" && g.utilizable && validBbox(g.bbox)) return "geometria";
  if (estadoUbicacion(t?.lat, t?.lon) === "valida") return "punto";
  return "ninguna";
}

/** Split for the renderer. Point terrains keep the existing code path. */
export function particionar(terrenos) {
  const out = { contornos: [], puntos: [], sinUbicacion: [] };
  for (const t of terrenos) {
    const modo = modoUbicacion(t);
    if (modo === "geometria") out.contornos.push(t);
    else if (modo === "punto") out.puntos.push(t);
    else out.sinUbicacion.push(t);
  }
  return out;
}

/** Leaflet bounds [[s, w], [n, e]] covering boundaries and points, or null. */
export function limites(terrenos) {
  let s = Infinity, w = Infinity, n = -Infinity, e = -Infinity;
  const { contornos, puntos } = particionar(terrenos);
  for (const t of contornos) {
    const [bw, bs, be, bn] = t.geometria.bbox;
    s = Math.min(s, bs); w = Math.min(w, bw); n = Math.max(n, bn); e = Math.max(e, be);
  }
  for (const t of puntos) {
    s = Math.min(s, t.lat); n = Math.max(n, t.lat);
    w = Math.min(w, t.lon); e = Math.max(e, t.lon);
  }
  return Number.isFinite(s) ? [[s, w], [n, e]] : null;
}

/**
 * Whether a boundary is big enough on screen to be read as land, mirroring
 * the existing symbol -> footprint handover for circles (geo.js drawnRadius).
 * Below it, a symbol is drawn at punto_simbolo so the terrain stays visible.
 */
export function contornoAEscala(bbox, zoom) {
  const [w, s, e, n] = bbox;
  const latMedia = (s + n) / 2;
  const mpp = metresPerPixel(latMedia, zoom);
  const ancho = ((e - w) * 111_320 * Math.cos((latMedia * Math.PI) / 180)) / mpp;
  const alto = ((n - s) * 110_574) / mpp;
  return Math.max(ancho, alto) >= SYMBOL_RADIUS * 2;
}

/**
 * Stored X/Y that disagrees with the boundary: shown for review, never fixed.
 * `margenGrados` tolerates a point on the edge (~0.005° ≈ 500 m).
 */
export function conflictoXY(t, margenGrados = 0.005) {
  if (modoUbicacion(t) !== "geometria") return false;
  if (estadoUbicacion(t.lat, t.lon) !== "valida") return false;
  const [w, s, e, n] = t.geometria.bbox;
  return t.lat < s - margenGrados || t.lat > n + margenGrados
    || t.lon < w - margenGrados || t.lon > e + margenGrados;
}

function validBbox(b) {
  return Array.isArray(b) && b.length === 4 && b.every(Number.isFinite)
    && b[0] <= b[2] && b[1] <= b[3];
}

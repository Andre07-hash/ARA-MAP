/* PROTOTYPE (display-strategy investigation; not application code).
 *
 * Memory-budget experiment copy of PR #16's preparar.js @ 9da0ab1. One
 * change: an optional `reservar(bytes)` hook runs AFTER the structural pass
 * (which knows the exact sizes) and BEFORE the typed arrays are allocated.
 * It returns true (reserved), false (refused: result {estado:
 * "sin_memoria"}) or "esperar" (memory is being released; the step returns
 * null and retries later). Everything else is unchanged.
 *
 * Prepare one geometry body for drawing, in resumable slices.
 *
 * Accepts and rejects exactly what B-2's cuerpoLeaflet() accepts and rejects
 * (web/lib/geometria.js @ 5d8e2dc; equivalence is a test). The difference is
 * the output: instead of nested [lat, lng] arrays that Leaflet re-projects
 * on every view, it keeps the EXACT positions, projected once into Leaflet's
 * EPSG:3857 world units (pixel / 256 / 2^zoom), in typed arrays, plus a box
 * per part for viewport culling. Nothing is simplified, rounded or dropped.
 *
 * No imports: the constants below duplicate B-2's and a test asserts they
 * are equal.
 */

export const MAX_POSICIONES_CUERPO = 100_000;
export const TOLERANCIA_GRADOS = 1e-9;

const finito = (v) => typeof v === "number" && Number.isFinite(v);
const lonValida = (v) => finito(v) && v >= -180 && v <= 180;
const latValida = (v) => finito(v) && v >= -90 && v <= 90;

function bboxValido(b) {
  return Array.isArray(b) && b.length === 4
    && lonValida(b[0]) && latValida(b[1]) && lonValida(b[2]) && latValida(b[3])
    && b[0] <= b[2] && b[1] <= b[3];
}

function puntoValido(p) {
  return p !== null && typeof p === "object" && p.type === "Point"
    && Array.isArray(p.coordinates) && p.coordinates.length === 2
    && lonValida(p.coordinates[0]) && latValida(p.coordinates[1]);
}

export function descriptorActivo(g) {
  return g !== null && typeof g === "object"
    && typeof g.id === "string" && g.id.length > 0
    && g.utilizable === true
    && bboxValido(g.bbox)
    && puntoValido(g.punto_interior)
    && g.punto_interior.coordinates[0] >= g.bbox[0]
    && g.punto_interior.coordinates[0] <= g.bbox[2]
    && g.punto_interior.coordinates[1] >= g.bbox[1]
    && g.punto_interior.coordinates[1] <= g.bbox[3];
}

function mismaCaja(a, b) {
  return a.every((v, i) => Math.abs(v - b[i]) <= TOLERANCIA_GRADOS);
}

/* Leaflet 1.9.4 L.Projection.SphericalMercator + L.CRS.EPSG3857
 * transformation, written in the same operation order so the result is the
 * same double Leaflet computes before scaling by 256 * 2^zoom. */
const R = 6378137;
const MAX_LAT = 85.0511287798;
const D = Math.PI / 180;
const ESCALA = 0.5 / (Math.PI * R);

export function mundoX(lon) {
  return ESCALA * (R * lon * D) + 0.5;
}

export function mundoY(lat) {
  const l = Math.max(Math.min(MAX_LAT, lat), -MAX_LAT);
  const sin = Math.sin(l * D);
  return -ESCALA * (R * Math.log((1 + sin) / (1 - sin)) / 2) + 0.5;
}

const INVALIDO = Object.freeze({ estado: "invalido" });
const NO_DISPONIBLE = Object.freeze({ estado: "no_disponible" });
const SIN_MEMORIA = Object.freeze({ estado: "sin_memoria" });
const CADA = 1024;                        // positions between clock checks

/**
 * A resumable preparation. `paso(ms)` works for at most about `ms`
 * milliseconds and returns null while unfinished, else the final result:
 *   {estado: "no_disponible"} | {estado: "invalido"} |
 *   {estado: "cargado", posiciones, cajaMayor, partes, anillos,
 *    x, y (Float64Array world units), inicioAnillo (Int32Array, anillos+1),
 *    inicioParte (Int32Array, partes+1: first ring of each part),
 *    cajasParte (Float64Array, 4 per part: minX, minY, maxX, maxY world units)}
 * `ahora` is injectable for tests.
 */
export function crearPreparacion(descriptor, geometrias, ahora = () => performance.now(),
                                 { reservar = null } = {}) {
  let resultado = null;
  let fase = "inicio";
  let cuerpo; let gj; let total = 0; let nAnillos = 0; let nPartes = 0;
  let x; let y; let inicioAnillo; let inicioParte; let cajasParte;
  let iParte = 0; let iAnillo = 0; let k = 0; let escrito = 0; let anilloGlobal = 0;
  let w; let s; let e; let n;                      // current ring, degrees
  let uw = Infinity; let us = Infinity; let ue = -Infinity; let un = -Infinity;
  let areaMayor = -1; let cajaMayor = null;
  let bw; let bs; let be; let bn;

  function terminar(r) { resultado = r; fase = "fin"; return r; }

  function inicio() {
    if (!(geometrias instanceof Map) || !descriptorActivo(descriptor)) return terminar(NO_DISPONIBLE);
    cuerpo = geometrias.get(descriptor.id);
    if (cuerpo === undefined || cuerpo === null) return terminar(NO_DISPONIBLE);
    if (typeof cuerpo !== "object" || !bboxValido(cuerpo.bbox)
        || !mismaCaja(cuerpo.bbox, descriptor.bbox)) return terminar(INVALIDO);
    gj = cuerpo.geojson;
    if (gj === null || typeof gj !== "object" || gj.type !== "MultiPolygon"
        || !Array.isArray(gj.coordinates) || gj.coordinates.length === 0) return terminar(INVALIDO);
    // Structural pass over parts and rings only (O(rings)): the same checks
    // cuerpoLeaflet makes before reading positions, and the exact total.
    for (const poligono of gj.coordinates) {
      if (!Array.isArray(poligono) || poligono.length === 0) return terminar(INVALIDO);
      for (const anillo of poligono) {
        if (!Array.isArray(anillo) || anillo.length < 4) return terminar(INVALIDO);
        total += anillo.length;
        if (total > MAX_POSICIONES_CUERPO) return terminar(INVALIDO);
        nAnillos += 1;
      }
    }
    nPartes = gj.coordinates.length;
    if (reservar) {
      const r = reservar(total * 16 + (nAnillos + 1) * 4 + (nPartes + 1) * 4 + nPartes * 32);
      if (r === "esperar") {                 // retry from scratch on a later step
        total = 0; nAnillos = 0; nPartes = 0;
        return null;
      }
      if (!r) return terminar(SIN_MEMORIA);
    }
    [bw, bs, be, bn] = cuerpo.bbox;
    x = new Float64Array(total);
    y = new Float64Array(total);
    inicioAnillo = new Int32Array(nAnillos + 1);
    inicioParte = new Int32Array(nPartes + 1);
    cajasParte = new Float64Array(nPartes * 4);
    for (let p = 0; p < nPartes; p += 1) {
      cajasParte[p * 4] = Infinity; cajasParte[p * 4 + 1] = Infinity;
      cajasParte[p * 4 + 2] = -Infinity; cajasParte[p * 4 + 3] = -Infinity;
    }
    w = Infinity; s = Infinity; e = -Infinity; n = -Infinity;
    fase = "posiciones";
    return null;
  }

  /** Read positions until the deadline; null when more remain. */
  function posiciones(limite) {
    const t = TOLERANCIA_GRADOS;
    const partes = gj.coordinates;
    let cuenta = 0;
    while (iParte < nPartes) {
      const poligono = partes[iParte];
      if (iAnillo === 0 && k === 0) inicioParte[iParte] = anilloGlobal;
      const anillo = poligono[iAnillo];
      if (k === 0) inicioAnillo[anilloGlobal] = escrito;
      const largo = anillo.length;
      while (k < largo) {
        const p = anillo[k];
        if (!Array.isArray(p) || p.length < 2 || !lonValida(p[0]) || !latValida(p[1])
            || p[0] < bw - t || p[0] > be + t || p[1] < bs - t || p[1] > bn + t) {
          return terminar(INVALIDO);
        }
        const lon = p[0]; const lat = p[1];
        if (lon < w) w = lon;
        if (lon > e) e = lon;
        if (lat < s) s = lat;
        if (lat > n) n = lat;
        const mx = mundoX(lon); const my = mundoY(lat);
        x[escrito] = mx; y[escrito] = my;
        const c = iParte * 4;
        if (mx < cajasParte[c]) cajasParte[c] = mx;
        if (my < cajasParte[c + 1]) cajasParte[c + 1] = my;
        if (mx > cajasParte[c + 2]) cajasParte[c + 2] = mx;
        if (my > cajasParte[c + 3]) cajasParte[c + 3] = my;
        escrito += 1; k += 1; cuenta += 1;
        if (cuenta >= CADA) {
          cuenta = 0;
          if (ahora() >= limite) return null;          // resume at (iParte, iAnillo, k)
        }
      }
      // End of a ring: the per-ring checks of cuerpoLeaflet.
      if (!(e > w && n > s)) return terminar(INVALIDO);
      if (iAnillo === 0) {
        if (w < uw) uw = w;
        if (s < us) us = s;
        if (e > ue) ue = e;
        if (n > un) un = n;
        if ((e - w) * (n - s) > areaMayor) {
          areaMayor = (e - w) * (n - s);
          cajaMayor = [w, s, e, n];
        }
      }
      const a = anillo[0]; const z = anillo[largo - 1];
      if (a[0] !== z[0] || a[1] !== z[1]) return terminar(INVALIDO);
      w = Infinity; s = Infinity; e = -Infinity; n = -Infinity;
      anilloGlobal += 1; k = 0; iAnillo += 1;
      if (iAnillo >= poligono.length) { iAnillo = 0; iParte += 1; }
    }
    inicioAnillo[nAnillos] = escrito;
    inicioParte[nPartes] = nAnillos;
    if (!mismaCaja([uw, us, ue, un], cuerpo.bbox)) return terminar(INVALIDO);
    return terminar({
      estado: "cargado", posiciones: total, cajaMayor, partes: nPartes, anillos: nAnillos,
      x, y, inicioAnillo, inicioParte, cajasParte,
      cajaMundo: [mundoX(bw), mundoY(bn), mundoX(be), mundoY(bs)],
    });
  }

  return {
    get terminado() { return fase === "fin"; },
    get resultado() { return resultado; },
    /** Work for about `ms`; returns the result when finished, else null. */
    paso(ms) {
      if (fase === "fin") return resultado;
      const limite = ahora() + ms;
      if (fase === "inicio") {
        if (inicio() !== null) return resultado;
        if (fase === "inicio") return null;      // waiting for memory: nothing allocated yet
      }
      return posiciones(limite);
    },
  };
}

/** Prepare to completion, synchronously (E2, tests). */
export function prepararAhora(descriptor, geometrias) {
  const p = crearPreparacion(descriptor, geometrias);
  let r = null;
  while (r === null) r = p.paso(Infinity);
  return r;
}

/** Approximate retained bytes of a prepared body (typed arrays only). */
export function bytesDe(preparado) {
  if (preparado?.estado !== "cargado") return 64;
  return preparado.x.byteLength + preparado.y.byteLength + preparado.inicioAnillo.byteLength
    + preparado.inicioParte.byteLength + preparado.cajasParte.byteLength;
}

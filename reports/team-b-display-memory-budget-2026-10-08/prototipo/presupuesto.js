/* PROTOTYPE (memory-budget investigation; not application code).
 *
 * One byte budget shared by every map instance on the page. Every managed
 * rendering allocation is RESERVED here before it is made and RELEASED when
 * its owner gives it up:
 *   "preparado"  typed arrays of a prepared body (main thread), one per body
 *                however many layers or caches use it;
 *   "copia"      a worker copy of a prepared body, from postMessage until
 *                the worker acknowledges dropping it (queued copies count);
 *   "raster"     a raster canvas/bitmap, from the request (the worker's
 *                scratch canvas becomes the bitmap by transfer, no copy)
 *                until the main thread closes it; the displayed image and
 *                its replacement overlap, and both are reserved.
 * A reservation that does not fit fails; nothing is allocated for it. Before
 * failing, registered relievers may free unpinned items (LRU caches). The
 * ledger keeps the peak and every live reservation, so tests can compare it
 * with the bytes actually held (typed-array byteLength, bitmap width x
 * height x 4, the worker's own counters).
 *
 * Not managed here (reported separately): caller-owned GeoJSON bodies, JS
 * object overhead, Leaflet's own canvas and DOM, browser/GPU memory.
 */

let siguienteId = 0;

export function crearPresupuesto(total) {
  const vivas = new Map();                // id -> reservation
  const porCategoria = { preparado: 0, copia: 0, raster: 0 };
  const picoPorCategoria = { preparado: 0, copia: 0, raster: 0 };
  const aliviadores = new Set();          // (bytesFaltantes) => void: free unpinned items
  const oyentes = new Set();              // () => void: something was released or became evictable
  let usados = 0;
  let pico = 0;
  let rechazos = 0;
  let aviso = false;
  let porConfirmar = 0;                   // bytes already given up, release not yet acknowledged

  function avisarLiberado() {
    if (aviso) return;
    aviso = true;
    queueMicrotask(() => { aviso = false; for (const f of oyentes) f(); });
  }

  const p = {
    total,
    /** Reserve `bytes` for `categoria`; a reservation object, or null (nothing reserved). */
    reservar(categoria, bytes, dueno = "") {
      if (!(categoria in porCategoria)) throw new Error(`unknown category ${categoria}`);
      if (!Number.isFinite(bytes) || bytes < 0) throw new Error(`bad size ${bytes}`);
      // Bytes already given up but not yet acknowledged will be freed: they
      // count against the shortage, so each reliever frees only what is still
      // missing (every reliever used to free the whole shortage).
      const faltan = () => usados - porConfirmar + bytes - total;
      for (const aliviar of aliviadores) {
        if (faltan() <= 0) break;
        aliviar(faltan());
      }
      if (usados + bytes > total) { rechazos += 1; return null; }
      siguienteId += 1;
      const r = { id: siguienteId, categoria, bytes, dueno, viva: true };
      vivas.set(r.id, r);
      usados += bytes;
      porCategoria[categoria] += bytes;
      if (usados > pico) pico = usados;
      if (porCategoria[categoria] > picoPorCategoria[categoria]) picoPorCategoria[categoria] = porCategoria[categoria];
      return r;
    },
    liberar(r) {
      if (!r || !r.viva) return;
      r.viva = false;
      vivas.delete(r.id);
      usados -= r.bytes;
      porCategoria[r.categoria] -= r.bytes;
      avisarLiberado();
    },
    /** A holder announces bytes it has given up whose release is not yet
     *  acknowledged (a worker forget in flight); a refused caller may wait. */
    anunciarPorConfirmar(delta) { porConfirmar += delta; },
    get pendienteDeLiberar() { return porConfirmar; },
    /** Whether `bytes` could ever fit (the whole budget, nothing else held). */
    cabe(bytes) { return bytes <= total; },
    registrarAliviador(f) { aliviadores.add(f); return () => aliviadores.delete(f); },
    /** Listeners run (coalesced, in a microtask) after a release, or after
     *  `avisarDisponible`: held items became evictable (unpinned), so a
     *  caller refused earlier may now fit. */
    alLiberar(f) { oyentes.add(f); return () => oyentes.delete(f); },
    avisarDisponible() { avisarLiberado(); },
    get usados() { return usados; },
    get pico() { return pico; },
    get rechazos() { return rechazos; },
    get libres() { return total - usados; },
    porCategoria: () => ({ ...porCategoria }),
    picoPorCategoria: () => ({ ...picoPorCategoria }),
    vivas: () => [...vivas.values()],
    /** Restart peak tracking (between test scenarios). */
    reiniciarPico() {
      pico = usados;
      for (const k of Object.keys(picoPorCategoria)) picoPorCategoria[k] = porCategoria[k];
      rechazos = 0;
    },
  };
  return p;
}

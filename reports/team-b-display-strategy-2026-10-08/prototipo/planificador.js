/* PROTOTYPE (display-strategy investigation; not application code).
 *
 * Cooperative preparation of geometry bodies, plus the bounded cache of
 * prepared bodies.
 *
 * - One job per geometry ID, shared by every render that needs it.
 * - Work runs in slices of at most SLICE_MS; between slices the main thread
 *   is yielded (scheduler.postTask where available, else MessageChannel), so
 *   input and painting are never blocked by preparation.
 * - Cancellation: a job is cancelled when no current render needs its ID
 *   (filter change, newer render, session reset) or on teardown. A
 *   cancelled job never reports a result.
 * - Cache: prepared bodies by immutable geometry ID, checked against the
 *   descriptor bbox, evicted least-recently-used beyond a byte budget.
 */

import { bytesDe, crearPreparacion } from "./preparar.js";

export const SLICE_MS = 8;
export const PRESUPUESTO_CACHE_BYTES = 32 * 1024 * 1024;   // ~1.4M positions

function claveCaja(b) { return b.join(","); }

export function crearCache(presupuesto = PRESUPUESTO_CACHE_BYTES) {
  const entradas = new Map();          // id -> {caja, preparado, bytes}; insertion order = LRU
  let bytes = 0;
  return {
    obtener(descriptor) {
      const e = entradas.get(descriptor.id);
      if (!e) return null;
      if (e.caja !== claveCaja(descriptor.bbox)) return null;   // not this descriptor's body
      entradas.delete(descriptor.id);
      entradas.set(descriptor.id, e);  // most recently used
      return e.preparado;
    },
    guardar(descriptor, preparado) {
      const anterior = entradas.get(descriptor.id);
      if (anterior) { bytes -= anterior.bytes; entradas.delete(descriptor.id); }
      const b = bytesDe(preparado);
      if (b > presupuesto) return;     // never cache something larger than the budget
      entradas.set(descriptor.id, { caja: claveCaja(descriptor.bbox), preparado, bytes: b });
      bytes += b;
      for (const [id, e] of entradas) {
        if (bytes <= presupuesto) break;
        entradas.delete(id);
        bytes -= e.bytes;
      }
    },
    vaciar() { entradas.clear(); bytes = 0; },
    get bytes() { return bytes; },
    get tamano() { return entradas.size; },
  };
}

const ceder = typeof globalThis.scheduler?.postTask === "function"
  ? (fn) => globalThis.scheduler.postTask(fn, { priority: "user-visible" })
  : (() => {
    const canal = new MessageChannel();
    const cola = [];
    canal.port1.onmessage = () => cola.shift()?.();
    canal.port1.unref?.();             // Node (tests): do not keep the process alive
    return (fn) => { cola.push(fn); canal.port2.postMessage(null); };
  })();

export function crearPlanificador({ ahora = () => performance.now() } = {}) {
  const trabajos = new Map();          // id -> {preparacion, avisos:Set, cancelado}
  let programado = false;
  let detenido = false;
  const metricas = { porciones: 0, porcionMaxMs: 0, completados: 0, cancelados: 0 };

  function programar() {
    if (programado || detenido || trabajos.size === 0) return;
    programado = true;
    ceder(ciclo);
  }

  function ciclo() {
    programado = false;
    if (detenido) return;
    const inicio = ahora();
    // One slice in total per task, shared round-robin by the open jobs.
    for (const [id, t] of trabajos) {
      const restante = SLICE_MS - (ahora() - inicio);
      if (restante <= 0) break;
      const r = t.preparacion.paso(restante);
      if (r !== null) {
        trabajos.delete(id);
        metricas.completados += 1;
        for (const aviso of t.avisos) aviso(r);
      }
    }
    const duracion = ahora() - inicio;
    metricas.porciones += 1;
    if (duracion > metricas.porcionMaxMs) metricas.porcionMaxMs = duracion;
    programar();
  }

  return {
    /** Start (or join) preparing `descriptor`'s body; `aviso(result)` once done. */
    pedir(descriptor, geometrias, aviso) {
      let t = trabajos.get(descriptor.id);
      if (!t) {
        t = { preparacion: crearPreparacion(descriptor, geometrias, ahora), avisos: new Set() };
        trabajos.set(descriptor.id, t);
      }
      t.avisos.add(aviso);
      programar();
      return () => t.avisos.delete(aviso);
    },
    /** Cancel every job whose ID is not in `necesarios`. */
    conservarSolo(necesarios) {
      for (const [id] of trabajos) {
        if (!necesarios.has(id)) { trabajos.delete(id); metricas.cancelados += 1; }
      }
    },
    /** Teardown: cancel everything and refuse new work. */
    detener() {
      metricas.cancelados += trabajos.size;
      trabajos.clear();
      detenido = true;
    },
    get pendientes() { return trabajos.size; },
    metricas,
  };
}

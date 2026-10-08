/* PROTOTYPE (memory-budget investigation; not application code).
 *
 * Cooperative preparation, from PR #16's planificador.js @ 9da0ab1, with
 * memory admission:
 * - At most MAX_TRABAJOS preparations hold memory at once; the others wait
 *   in arrival order and allocate nothing (they keep a reference to the
 *   caller's geometry Map and the descriptor only).
 * - A preparation reserves its exact typed-array bytes (preparar.js hook)
 *   before allocating. Refused with nothing being released: the result is
 *   {estado: "sin_memoria"}. Refused while some release awaits an
 *   acknowledgement: it waits and retries.
 * - The job owns its reservation until it finishes. A loaded result hands it
 *   to `alPreparar` (the map's registry); any other ending (invalid,
 *   cancelled, stopped, no one waiting) releases it.
 * - Work runs in slices of at most SLICE_MS, yielding between slices.
 */

import { crearPreparacion } from "./preparar.js";

export const SLICE_MS = 8;
export const MAX_TRABAJOS = 2;

const ceder = typeof globalThis.scheduler?.postTask === "function"
  ? (fn) => globalThis.scheduler.postTask(fn, { priority: "user-visible" })
  : (() => {
    const canal = new MessageChannel();
    const cola = [];
    canal.port1.onmessage = () => cola.shift()?.();
    canal.port1.unref?.();
    return (fn) => { cola.push(fn); canal.port2.postMessage(null); };
  })();

export function crearPlanificador({ registro, presupuesto, alPreparar, ahora = () => performance.now(),
                                    maxTrabajos = MAX_TRABAJOS, ceder: cederSlice = ceder } = {}) {
  const trabajos = new Map();          // id -> job, arrival order
  let programado = false;
  let detenido = false;
  const metricas = { porciones: 0, porcionMaxMs: 0, completados: 0, cancelados: 0, sinMemoria: 0, esperas: 0 };

  function nuevoTrabajo(descriptor, geometrias) {
    const t = { descriptor, avisos: new Set(), reserva: null, preparacion: null };
    t.preparacion = crearPreparacion(descriptor, geometrias, ahora, {
      reservar: (bytes) => {
        const r = registro.reservar(bytes);
        if (r) { t.reserva = r; return true; }
        if (presupuesto.pendienteDeLiberar > 0) { metricas.esperas += 1; return "esperar"; }
        return false;
      },
    });
    return t;
  }

  function terminarTrabajo(id, t, r) {
    trabajos.delete(id);
    metricas.completados += 1;
    if (r.estado === "sin_memoria") metricas.sinMemoria += 1;
    let resultado = r;
    if (r.estado === "cargado" && t.avisos.size) {
      resultado = alPreparar(t.descriptor, r, t.reserva);   // ownership handed over
    } else presupuesto.liberar(t.reserva);
    t.reserva = null;
    for (const aviso of t.avisos) aviso(resultado);
  }

  function programar() {
    if (programado || detenido || trabajos.size === 0) return;
    programado = true;
    cederSlice(ciclo);
  }

  function ciclo() {
    programado = false;
    if (detenido) return;
    const inicio = ahora();
    let activos = 0;
    for (const [id, t] of trabajos) {
      if (activos >= maxTrabajos) break;          // later jobs wait, allocating nothing
      activos += 1;
      const restante = SLICE_MS - (ahora() - inicio);
      if (restante <= 0) break;
      const r = t.preparacion.paso(restante);
      if (r !== null) terminarTrabajo(id, t, r);
    }
    const duracion = ahora() - inicio;
    metricas.porciones += 1;
    if (duracion > metricas.porcionMaxMs) metricas.porcionMaxMs = duracion;
    programar();
  }

  function cancelar(id, t) {
    trabajos.delete(id);
    presupuesto.liberar(t.reserva);
    t.reserva = null;
    metricas.cancelados += 1;
  }

  return {
    pedir(descriptor, geometrias, aviso) {
      let t = trabajos.get(descriptor.id);
      if (!t) { t = nuevoTrabajo(descriptor, geometrias); trabajos.set(descriptor.id, t); }
      t.avisos.add(aviso);
      programar();
      return () => t.avisos.delete(aviso);
    },
    conservarSolo(necesarios) {
      for (const [id, t] of trabajos) if (!necesarios.has(id)) cancelar(id, t);
    },
    detener() {
      for (const [id, t] of trabajos) cancelar(id, t);
      detenido = true;
    },
    get pendientes() { return trabajos.size; },
    get enMemoria() { let n = 0; for (const t of trabajos.values()) if (t.reserva) n += 1; return n; },
    /** Bytes reserved by preparations in progress (their typed arrays). */
    get bytesReservados() { let b = 0; for (const t of trabajos.values()) b += t.reserva?.bytes ?? 0; return b; },
    metricas,
  };
}

/* PROTOTYPE (memory-budget investigation; not application code).
 *
 * One map's worker: copies of prepared bodies and combined raster requests.
 *
 * Memory (shared budget, category "copia"): a copy is reserved BEFORE it is
 * posted and released only when the worker ACKNOWLEDGES dropping it, so
 * queued copies count. Copies used by the request in flight are pinned.
 * Unpinned copies stay for later rasters and are dropped least recently used
 * first when the budget needs room (this client's reliever); their bytes are
 * announced as awaiting release until the acknowledgement.
 *
 * Raster requests are reserved by the caller ("raster"); this client only
 * delivers or fails them. One request at a time per map is the caller's rule.
 *
 * Failure (all end in estado "fallido" with a reason, never a silent pending):
 *   "constructor"   new Worker threw;
 *   "sinOffscreen"  the worker has no OffscreenCanvas;
 *   "error"         the worker raised an error or a message failed to clone;
 *   "sinRespuesta"  a raster was not answered within `plazoMs`.
 * On failure the worker is terminated and every reservation this client holds
 * is released (ownership ends with the worker; the browser frees its memory
 * on its own schedule).
 */

import { bytesDe } from "./preparar.js";

const URL_TRABAJADOR = new URL("./trabajador.js", import.meta.url);

export function crearCliente({ presupuesto, dueno, simular = null, plazoMs = 8000, alFallar = null,
                               alListo = null, crearTrabajador = null } = {}) {
  const copias = new Map();          // id -> {copia, reserva, fijos}; order = LRU
  const porConfirmar = new Map();    // copia -> reserva (forget posted, ack pending)
  const esperas = new Map();         // pedido -> {aviso, reloj}
  const estadisticas = [];
  const reinicios = [];
  let numeroCopia = 0; let numero = 0;
  let estado = "iniciando";
  let motivo = null;
  let trabajador = null;
  const metricas = { copiasEnviadas: 0, olvidos: 0, sinMemoria: 0, rasters: 0, descartados: 0, cancelados: 0 };

  function fallar(razon) {
    if (estado === "fallido" || estado === "cerrado") return;
    estado = "fallido";
    motivo = razon;
    try { trabajador?.terminate(); } catch { /* already gone */ }
    soltarTodo();
    for (const [, e] of esperas) { clearTimeout(e.reloj); e.aviso({ fallo: razon }); }
    esperas.clear();
    for (const r of estadisticas.splice(0)) r(null);
    for (const [, r] of reinicios.splice(0)) r(false);
    alFallar?.(razon);
  }

  function soltarTodo() {
    for (const c of copias.values()) presupuesto.liberar(c.reserva);
    copias.clear();
    for (const r of porConfirmar.values()) { presupuesto.anunciarPorConfirmar(-r.bytes); presupuesto.liberar(r); }
    porConfirmar.clear();
  }

  function olvidar(id) {
    const c = copias.get(id);
    if (!c) return 0;
    copias.delete(id);
    porConfirmar.set(c.copia, c.reserva);
    presupuesto.anunciarPorConfirmar(c.reserva.bytes);
    metricas.olvidos += 1;
    trabajador.postMessage({ tipo: "olvidar", id, copia: c.copia });
    return c.reserva.bytes;
  }

  const quitarAliviador = presupuesto.registrarAliviador((faltan) => {
    if (estado !== "listo") return;
    let liberado = 0;
    for (const [id, c] of copias) {
      if (liberado >= faltan) break;
      if (c.fijos === 0) liberado += olvidar(id);
    }
  });

  try {
    if (simular === "constructor") throw new Error("simulated constructor failure");
    const url = new URL(URL_TRABAJADOR);
    if (simular) url.searchParams.set("simular", simular);
    trabajador = crearTrabajador ? crearTrabajador(url) : new Worker(url, { type: "module" });
  } catch {
    estado = "fallido";
    motivo = "constructor";
  }

  if (trabajador) {
    trabajador.onerror = (e) => { e.preventDefault?.(); fallar("error"); };
    trabajador.onmessageerror = () => fallar("error");
    trabajador.onmessage = ({ data }) => {
      if (estado === "fallido" || estado === "cerrado") return;
      switch (data.tipo) {
        case "listo":
          if (!data.offscreen) fallar("sinOffscreen");
          else if (estado === "iniciando") { estado = "listo"; alListo?.(); }
          return;
        case "olvidado": {
          const r = porConfirmar.get(data.copia);
          if (r) { porConfirmar.delete(data.copia); presupuesto.anunciarPorConfirmar(-r.bytes); presupuesto.liberar(r); }
          return;
        }
        case "olvidadoTodo":
          for (const [copia, r] of porConfirmar) {
            if (copia <= data.hasta) { porConfirmar.delete(copia); presupuesto.anunciarPorConfirmar(-r.bytes); presupuesto.liberar(r); }
          }
          while (reinicios.length && reinicios[0][0] <= data.hasta) reinicios.shift()[1](true);
          return;
        case "estadisticas": estadisticas.shift()?.(data); return;
        case "raster": {
          const e = esperas.get(data.pedido);
          esperas.delete(data.pedido);
          if (!e) {
            if (data.cancelado) metricas.cancelados += 1;      // dropped in the worker before it started
            else { data.bitmap?.close(); metricas.descartados += 1; }   // a late reply: closed, never shown
            return;
          }
          clearTimeout(e.reloj);
          e.aviso(data);
          return;
        }
        default:
      }
    };
  }

  return {
    get estado() { return estado; },
    get motivo() { return motivo; },
    /** Make sure the worker has `id`'s body: "listo" | "esperar" | "sin_memoria" | "fallido". */
    asegurar(id, p) {
      if (estado === "fallido" || estado === "cerrado") return "fallido";
      const c = copias.get(id);
      if (c) { c.expulsar = false; copias.delete(id); copias.set(id, c); return "listo"; }
      const reserva = presupuesto.reservar("copia", bytesDe(p), dueno);
      if (!reserva) {
        if (presupuesto.pendienteDeLiberar > 0) return "esperar";
        metricas.sinMemoria += 1;
        return "sin_memoria";
      }
      numeroCopia += 1;
      copias.set(id, { copia: numeroCopia, reserva, fijos: 0 });
      metricas.copiasEnviadas += 1;
      trabajador.postMessage({ tipo: "cuerpo", id, copia: numeroCopia, x: p.x, y: p.y, inicioAnillo: p.inicioAnillo,
                               inicioParte: p.inicioParte, cajasParte: p.cajasParte, partes: p.partes });
      return "listo";
    },
    fijar(ids) { for (const id of ids) { const c = copias.get(id); if (c) c.fijos += 1; } },
    soltar(ids) {
      for (const id of ids) {
        const c = copias.get(id);
        if (!c) continue;
        c.fijos = Math.max(0, c.fijos - 1);
        if (c.fijos === 0 && c.expulsar && estado === "listo") olvidar(id);
      }
    },
    /** The main thread dropped `id`'s body: its copy goes too, at once or, if a
     *  request in flight pins it, when unpinned. A copy already being forgotten
     *  (awaiting acknowledgement) is not in `copias`: nothing can go stale. */
    expulsado(id) {
      const c = copias.get(id);
      if (!c || estado !== "listo") return;
      if (c.fijos > 0) c.expulsar = true;
      else olvidar(id);
    },
    ids() { return [...copias.keys()]; },
    /** Ask for a combined raster; `aviso(reply)` gets {bitmap, faltan} or {fallo} or {cancelado}. */
    raster(parametros, aviso) {
      if (estado !== "listo") { aviso({ fallo: motivo ?? "noListo" }); return null; }
      numero += 1;
      metricas.rasters += 1;
      const reloj = setTimeout(() => fallar("sinRespuesta"), plazoMs);
      esperas.set(numero, { aviso, reloj });
      trabajador.postMessage({ tipo: "raster", pedido: numero, ...parametros });
      return numero;
    },
    /** Not wanted any more: cancelled in the worker if not started; a late reply is closed. */
    descartar(n) {
      const e = esperas.get(n);
      if (!e) return;
      clearTimeout(e.reloj);
      esperas.delete(n);
      if (estado === "listo") trabajador.postMessage({ tipo: "cancelar", pedido: n });
    },
    /** Reset: drop every copy; resolves true when the worker acknowledges. */
    olvidarTodo() {
      if (estado !== "listo") return Promise.resolve(false);
      for (const [, c] of copias) { porConfirmar.set(c.copia, c.reserva); presupuesto.anunciarPorConfirmar(c.reserva.bytes); }
      copias.clear();
      const hasta = numeroCopia;
      trabajador.postMessage({ tipo: "olvidarTodo", hasta });
      return new Promise((ok) => reinicios.push([hasta, ok]));
    },
    cerrar() {
      if (estado === "cerrado") return;
      const antes = estado;
      estado = "cerrado";
      quitarAliviador();
      for (const [, e] of esperas) clearTimeout(e.reloj);
      esperas.clear();
      if (antes !== "fallido") { try { trabajador?.terminate(); } catch { /* gone */ } }
      soltarTodo();
      for (const r of estadisticas.splice(0)) r(null);
      for (const [, r] of reinicios.splice(0)) r(false);
    },
    estadisticas() {
      if (estado !== "listo") return Promise.resolve(null);
      return new Promise((ok) => { estadisticas.push(ok); trabajador.postMessage({ tipo: "estadisticas" }); });
    },
    /** Bytes this client holds in the ledger (copies held plus forgets awaiting acknowledgement). */
    bytesReservados() {
      let b = 0;
      for (const c of copias.values()) b += c.reserva.bytes;
      for (const r of porConfirmar.values()) b += r.bytes;
      return b;
    },
    get copias() { return copias.size; },
    get enVuelo() { return esperas.size; },
    metricas,
  };
}

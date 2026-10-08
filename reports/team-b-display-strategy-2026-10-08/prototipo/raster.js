/* PROTOTYPE (display-strategy investigation; not application code).
 *
 * Main-thread client of trabajador-raster.js: one worker per map.
 *
 * Correction F3 (supervisory review of PR #16). The worker's copies of
 * prepared bodies are bounded and coordinated with the main cache:
 * - Byte budget for worker copies (default 32 MiB). A copy counts from the
 *   moment it is posted until the worker ACKNOWLEDGES dropping it, so copies
 *   still queued in the message channel are included.
 * - A body is "pinned" while a layer on the map uses it (asegurar/liberar).
 *   Unpinned bodies are forgotten least-recently-used first when room is
 *   needed, and at once when the main cache evicts them (expulsado), so the
 *   worker holds a subset of (main cache ∪ pinned).
 * - When the budget is held by pinned bodies, asegurar() answers "rechazado"
 *   (the caller must show an explicit state); when room will be free once
 *   pending forgets are acknowledged, it answers "esperando" and posts the
 *   body (and its queued raster requests) after the acknowledgement.
 * - A forgotten ID leaves the sent set, so it is posted again when needed.
 * - Raster requests: descartar() sends "cancelar"; the worker drops the
 *   request if it has not started, else the reply is discarded and its
 *   bitmaps closed. Callers keep at most one request in flight per layer.
 * - Bitmaps handed to a layer are counted until the layer calls
 *   soltarBitmaps().
 * - olvidarTodo() (session reset) resolves when the worker acknowledges;
 *   cerrar() (teardown) terminates the worker: there is nothing to
 *   acknowledge, the browser discards the worker with its queue.
 */

import { bytesDe } from "./preparar.js";

export const PRESUPUESTO_TRABAJADOR_BYTES = 32 * 1024 * 1024;

const crearTrabajadorReal = () =>
  new Worker(new URL("./trabajador-raster.js", import.meta.url), { type: "module" });

export function crearClienteRaster({
  presupuesto = PRESUPUESTO_TRABAJADOR_BYTES, crearTrabajador = crearTrabajadorReal,
} = {}) {
  const trabajador = crearTrabajador();
  const vigentes = new Map();     // id -> {copia, bytes, fijos, enCache}; first = least recently used
  const esperando = new Map();    // id -> {p, bytes, fijos, enCache, pedidos: [[numero, parametros]]}
  const copias = new Map();       // copia -> bytes: posted and not yet acknowledged as dropped
  const esperas = new Map();      // request number -> aviso(reply)
  const enVuelo = new Set();      // request numbers posted and not yet answered
  const estadisticas = [];        // resolvers, in order
  const reinicios = [];           // [hasta, resolver]
  let bytesCopias = 0;            // sum of `copias`: upper bound of worker-side typed-array bytes
  let bytesReservados = 0;        // vigentes + esperando: what the worker will hold
  let numeroCopia = 0;
  let numero = 0;
  let cerrado = false;
  const metricas = {
    pedidos: 0, descartados: 0, cancelados: 0, sinCuerpo: 0, msMax: 0,
    copiasEnviadas: 0, rechazados: 0, esperas: 0,
    bytesCopiasMax: 0, enVueloMax: 0, bitmapsBytes: 0, bitmapsBytesMax: 0,
  };

  const bytesBitmaps = (lista) => lista.reduce((a, b) => a + b.width * b.height * 4, 0);

  function soltarCopia(copia) {
    const b = copias.get(copia);
    if (b === undefined) return;
    copias.delete(copia);
    bytesCopias -= b;
  }

  function olvidar(id) {
    const v = vigentes.get(id);
    if (!v) return;
    vigentes.delete(id);
    bytesReservados -= v.bytes;
    trabajador.postMessage({ tipo: "olvidar", id, copia: v.copia });
  }

  function publicar(numeroPedido, parametros) {
    enVuelo.add(numeroPedido);
    if (enVuelo.size > metricas.enVueloMax) metricas.enVueloMax = enVuelo.size;
    trabajador.postMessage({ tipo: "raster", pedido: numeroPedido, ...parametros });
  }

  function enviar(id, p, bytes, fijos, enCache) {
    numeroCopia += 1;
    copias.set(numeroCopia, bytes);
    bytesCopias += bytes;
    if (bytesCopias > metricas.bytesCopiasMax) metricas.bytesCopiasMax = bytesCopias;
    metricas.copiasEnviadas += 1;
    vigentes.set(id, { copia: numeroCopia, bytes, fijos, enCache });
    trabajador.postMessage({ tipo: "cuerpo", id, copia: numeroCopia, x: p.x, y: p.y,
                             inicioAnillo: p.inicioAnillo, inicioParte: p.inicioParte,
                             cajasParte: p.cajasParte, partes: p.partes });
  }

  /** Post waiting bodies (in order) whose copy now fits under the budget. */
  function atenderEspera() {
    for (const [id, e] of esperando) {
      if (bytesCopias + e.bytes > presupuesto) break;
      esperando.delete(id);                     // already reserved in bytesReservados
      enviar(id, e.p, e.bytes, e.fijos, e.enCache);
      for (const [n, parametros] of e.pedidos) if (esperas.has(n)) publicar(n, parametros);
    }
  }

  trabajador.onmessage = ({ data }) => {
    switch (data.tipo) {
      case "olvidado": soltarCopia(data.copia); atenderEspera(); return;
      case "olvidadoTodo":
        for (const c of [...copias.keys()]) if (c <= data.hasta) soltarCopia(c);
        while (reinicios.length && reinicios[0][0] <= data.hasta) reinicios.shift()[1]();
        atenderEspera();
        return;
      case "estadisticas": estadisticas.shift()?.(data); return;
      case "raster": {
        enVuelo.delete(data.pedido);
        if (data.ms > metricas.msMax) metricas.msMax = data.ms;
        const aviso = esperas.get(data.pedido);
        esperas.delete(data.pedido);
        if (data.cancelado) { metricas.cancelados += 1; return; }
        if (data.sinCuerpo) metricas.sinCuerpo += 1;
        if (!aviso) {
          metricas.descartados += 1;
          for (const b of data.bitmaps) b.close();
          return;
        }
        metricas.bitmapsBytes += bytesBitmaps(data.bitmaps);
        if (metricas.bitmapsBytes > metricas.bitmapsBytesMax) metricas.bitmapsBytesMax = metricas.bitmapsBytes;
        aviso(data);
        return;
      }
      default:
    }
  };

  return {
    /** Pin `id` for a layer and make sure the worker has its body.
     *  "listo" | "esperando" (posted once room is acknowledged) | "rechazado". */
    asegurar(id, p, { enCache = true } = {}) {
      if (cerrado) return "rechazado";
      const v = vigentes.get(id);
      if (v) {
        vigentes.delete(id);
        vigentes.set(id, v);                    // most recently used
        v.fijos += 1;
        v.enCache = v.enCache || enCache;
        return "listo";
      }
      const e = esperando.get(id);
      if (e) { e.fijos += 1; return "esperando"; }
      const bytes = bytesDe(p);
      if (bytesReservados + bytes > presupuesto) {
        for (const [otro, w] of vigentes) {     // least recently used first
          if (bytesReservados + bytes <= presupuesto) break;
          if (w.fijos === 0) olvidar(otro);
        }
      }
      if (bytesReservados + bytes > presupuesto) { metricas.rechazados += 1; return "rechazado"; }
      bytesReservados += bytes;
      if (bytesCopias + bytes <= presupuesto && esperando.size === 0) {
        enviar(id, p, bytes, 1, enCache);
        return "listo";
      }
      metricas.esperas += 1;
      esperando.set(id, { p, bytes, fijos: 1, enCache, pedidos: [] });
      return "esperando";
    },
    /** A layer no longer uses `id`. Unpinned and not in the main cache: forgotten. */
    liberar(id) {
      const e = esperando.get(id);
      if (e) {
        e.fijos -= 1;
        if (e.fijos > 0) return;
        esperando.delete(id);
        bytesReservados -= e.bytes;
        for (const [n] of e.pedidos) esperas.delete(n);
        atenderEspera();
        return;
      }
      const v = vigentes.get(id);
      if (!v) return;
      v.fijos = Math.max(0, v.fijos - 1);
      if (v.fijos === 0 && !v.enCache) olvidar(id);
    },
    /** The main cache evicted `id`: the worker keeps it only while pinned. */
    expulsado(id) {
      const v = vigentes.get(id);
      if (!v) return;
      v.enCache = false;
      if (v.fijos === 0) olvidar(id);
    },
    /** Ask for a raster; `aviso(reply)` unless descartar(numero) is called first. */
    pedir(parametros, aviso) {
      if (cerrado) return null;
      numero += 1;
      metricas.pedidos += 1;
      esperas.set(numero, aviso);
      const e = esperando.get(parametros.id);
      if (e) e.pedidos.push([numero, parametros]);
      else publicar(numero, parametros);
      return numero;
    },
    /** Not wanted any more: cancelled in the worker if not started, else discarded. */
    descartar(n) {
      if (!esperas.delete(n)) return;
      if (enVuelo.has(n) && !cerrado) trabajador.postMessage({ tipo: "cancelar", pedido: n });
    },
    /** A layer stops showing bitmaps it received. */
    soltarBitmaps(lista) {
      metricas.bitmapsBytes -= bytesBitmaps(lista);
      for (const b of lista) b.close();
    },
    /** Session reset. Resolves when the worker has dropped every body. */
    olvidarTodo() {
      for (const n of esperas.keys()) if (enVuelo.has(n) && !cerrado) trabajador.postMessage({ tipo: "cancelar", pedido: n });
      esperas.clear();
      vigentes.clear();
      esperando.clear();
      bytesReservados = 0;
      if (cerrado) return Promise.resolve(false);
      const hasta = numeroCopia;
      trabajador.postMessage({ tipo: "olvidarTodo", hasta });
      return new Promise((ok) => reinicios.push([hasta, () => ok(true)]));
    },
    /** Teardown: terminate the worker (its queue and copies are discarded). */
    cerrar() {
      cerrado = true;
      esperas.clear();
      enVuelo.clear();
      vigentes.clear();
      esperando.clear();
      copias.clear();
      bytesCopias = 0;
      bytesReservados = 0;
      trabajador.terminate();
      for (const r of estadisticas.splice(0)) r(null);
      for (const [, r] of reinicios.splice(0)) r();
    },
    /** What the worker itself holds (diagnostics and tests). */
    estadisticas() {
      if (cerrado) return Promise.resolve(null);
      return new Promise((ok) => { estadisticas.push(ok); trabajador.postMessage({ tipo: "estadisticas" }); });
    },
    get enVuelo() { return enVuelo.size + [...esperando.values()].reduce((a, e) => a + e.pedidos.length, 0); },
    get bytesTrabajador() { return bytesCopias; },
    get bytesReservados() { return bytesReservados; },
    get entradas() { return vigentes.size; },
    get fijados() { let n = 0; for (const v of vigentes.values()) if (v.fijos) n += 1; return n; },
    get cerrado() { return cerrado; },
    presupuesto,
    metricas,
  };
}

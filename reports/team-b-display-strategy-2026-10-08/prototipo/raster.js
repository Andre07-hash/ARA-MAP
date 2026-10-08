/* PROTOTYPE (display-strategy investigation; not application code).
 *
 * Main-thread client of trabajador-raster.js: one worker per map.
 * - Each prepared body is posted once per geometry ID (typed-array copy).
 * - Requests carry an increasing number; a reply for a request the caller
 *   no longer wants is discarded and its bitmaps closed.
 * - olvidarTodo() on session reset; cerrar() on teardown terminates it.
 */

export function crearClienteRaster() {
  const trabajador = new Worker(new URL("./trabajador-raster.js", import.meta.url), { type: "module" });
  const enviados = new Set();
  const esperas = new Map();
  let numero = 0;
  let cerrado = false;
  const metricas = { pedidos: 0, descartados: 0, msMax: 0 };

  trabajador.onmessage = ({ data }) => {
    const aviso = esperas.get(data.pedido);
    esperas.delete(data.pedido);
    if (data.ms > metricas.msMax) metricas.msMax = data.ms;
    if (aviso) aviso(data);
    else { metricas.descartados += 1; for (const b of data.bitmaps) b.close(); }
  };

  return {
    asegurar(id, p) {
      if (cerrado || enviados.has(id)) return;
      enviados.add(id);
      trabajador.postMessage({ tipo: "cuerpo", id, x: p.x, y: p.y, inicioAnillo: p.inicioAnillo,
                               inicioParte: p.inicioParte, cajasParte: p.cajasParte, partes: p.partes });
    },
    /** Ask for a raster; `aviso(reply)` unless descartar(numero) is called first. */
    pedir(parametros, aviso) {
      if (cerrado) return null;
      numero += 1;
      metricas.pedidos += 1;
      esperas.set(numero, aviso);
      trabajador.postMessage({ tipo: "raster", pedido: numero, ...parametros });
      return numero;
    },
    descartar(n) { esperas.delete(n); },
    olvidarTodo() {
      enviados.clear();
      esperas.clear();
      if (!cerrado) trabajador.postMessage({ tipo: "olvidarTodo" });
    },
    cerrar() { cerrado = true; esperas.clear(); trabajador.terminate(); },
    get enVuelo() { return esperas.size; },
    metricas,
  };
}

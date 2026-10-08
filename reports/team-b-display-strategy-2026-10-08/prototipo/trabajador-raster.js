/* PROTOTYPE (display-strategy investigation; not application code).
 *
 * Module worker that rasterizes prepared bodies off the main thread
 * (OffscreenCanvas 2D). The geometry is the same prepared typed arrays the
 * main thread hit-tests; the drawing code is the same exact path (every
 * part intersecting the area, every position, rings closed with lineTo).
 *
 * Messages in:
 *   {tipo: "cuerpo", id, copia, x, y, inicioAnillo, inicioParte, cajasParte, partes}
 *   {tipo: "olvidar", id, copia}            -> {tipo: "olvidado", id, copia}
 *   {tipo: "olvidarTodo", hasta}            -> {tipo: "olvidadoTodo", hasta}
 *   {tipo: "raster", pedido, id, escala, x0, y0, ancho, alto, dpr, estilos}
 *     area = absolute pixels [x0, x0 + ancho) x [y0, y0 + alto) at `escala`
 *                                           -> {tipo: "raster", pedido, id, bitmaps, ms}
 *   {tipo: "cancelar", pedido}              -> {tipo: "raster", pedido, bitmaps: [], cancelado: true}
 *   {tipo: "estadisticas"}                  -> {tipo: "estadisticas", entradas, bytes, pendientes}
 *
 * Correction F3 (supervisory review of PR #16):
 * - Every forget is acknowledged, so the client counts a copy until the
 *   worker has really dropped it (queued copies included).
 * - Raster requests are queued here and run one per task, so a "cancelar"
 *   that arrives before a queued request starts removes it: discarded work
 *   is not run. A request whose body is absent is answered (sinCuerpo), never
 *   left without a reply.
 */

const CLAVES = ["x", "y", "inicioAnillo", "inicioParte", "cajasParte"];

export function bytesCopia(c) {
  let b = 0;
  for (const k of CLAVES) b += c[k].byteLength;
  return b;
}

function dibujar(ctx, c, escala, x0, y0, dpr) {
  const { x, y, inicioAnillo, inicioParte, cajasParte, partes } = c;
  const minX = x0 / escala; const minY = y0 / escala;
  const maxX = (x0 + ctx.canvas.width / dpr) / escala;
  const maxY = (y0 + ctx.canvas.height / dpr) / escala;
  const margen = 4 / escala;
  ctx.beginPath();
  for (let p = 0; p < partes; p += 1) {
    const k = p * 4;
    if (cajasParte[k] > maxX + margen || cajasParte[k + 2] < minX - margen
        || cajasParte[k + 1] > maxY + margen || cajasParte[k + 3] < minY - margen) continue;
    for (let a = inicioParte[p]; a < inicioParte[p + 1]; a += 1) {
      const desde = inicioAnillo[a]; const hasta = inicioAnillo[a + 1];
      ctx.moveTo(x[desde] * escala - x0, y[desde] * escala - y0);
      for (let i = desde + 1; i < hasta; i += 1) ctx.lineTo(x[i] * escala - x0, y[i] * escala - y0);
    }
  }
}

function pintar(ctx, e) {
  // Same sequence as Leaflet's Canvas._fillStroke.
  if (e.fill) {
    ctx.globalAlpha = e.fillOpacity;
    ctx.fillStyle = e.fillColor || e.color;
    ctx.fill(e.fillRule || "evenodd");
  }
  if (e.stroke && e.weight !== 0) {
    ctx.setLineDash(e.dashArray || []);
    ctx.globalAlpha = e.opacity;
    ctx.lineWidth = e.weight;
    ctx.strokeStyle = e.color;
    ctx.lineCap = e.lineCap;
    ctx.lineJoin = e.lineJoin;
    ctx.stroke();
  }
}

function rasterizar(c, data) {
  return data.estilos.map((estilo) => {
    const lienzo = new OffscreenCanvas(Math.ceil(data.ancho * data.dpr), Math.ceil(data.alto * data.dpr));
    const ctx = lienzo.getContext("2d");
    ctx.scale(data.dpr, data.dpr);
    dibujar(ctx, c, data.escala, data.x0, data.y0, data.dpr);
    pintar(ctx, estilo);
    return lienzo.transferToImageBitmap();
  });
}

/** Message handling, separate from the worker global so Node tests can drive it.
 *  `enviar(mensaje, transferibles)` replies; `programar(fn)` runs fn in a later task. */
export function crearManejador({ enviar, programar, raster = rasterizar }) {
  const cuerpos = new Map();             // id -> message (its typed arrays)
  const pendientes = new Map();          // pedido -> raster request, in arrival order
  let programado = false;

  function siguiente() {
    programado = false;
    const primero = pendientes.entries().next();
    if (primero.done) return;
    const [pedido, data] = primero.value;
    pendientes.delete(pedido);
    const c = cuerpos.get(data.id);
    if (!c) enviar({ tipo: "raster", pedido, id: data.id, bitmaps: [], sinCuerpo: true });
    else {
      const t0 = performance.now();
      const bitmaps = raster(c, data);
      enviar({ tipo: "raster", pedido, id: data.id, bitmaps, ms: performance.now() - t0 }, bitmaps);
    }
    if (pendientes.size && !programado) { programado = true; programar(siguiente); }
  }

  const manejar = (data) => {
    switch (data.tipo) {
      case "cuerpo": cuerpos.set(data.id, data); return;
      case "olvidar":
        if (cuerpos.get(data.id)?.copia === data.copia) cuerpos.delete(data.id);
        enviar({ tipo: "olvidado", id: data.id, copia: data.copia });
        return;
      case "olvidarTodo":
        cuerpos.clear();
        enviar({ tipo: "olvidadoTodo", hasta: data.hasta });
        return;
      case "raster":
        pendientes.set(data.pedido, data);
        if (!programado) { programado = true; programar(siguiente); }
        return;
      case "cancelar":
        if (pendientes.delete(data.pedido)) {
          enviar({ tipo: "raster", pedido: data.pedido, bitmaps: [], cancelado: true });
        }
        return;
      case "estadisticas": {
        let bytes = 0;
        for (const c of cuerpos.values()) bytes += bytesCopia(c);
        enviar({ tipo: "estadisticas", entradas: cuerpos.size, bytes, pendientes: pendientes.size });
        return;
      }
      default:
    }
  };
  manejar.cuerpos = cuerpos;
  return manejar;
}

/* Module-scope view of the retained bodies; the supervisor's review probe
 * appends code to this file that reads `cuerpos`. */
let cuerpos = null;
if (typeof WorkerGlobalScope !== "undefined" && globalThis instanceof WorkerGlobalScope) {
  const manejar = crearManejador({
    enviar: (m, t) => self.postMessage(m, t ?? []),
    programar: (fn) => setTimeout(fn, 0),
  });
  cuerpos = manejar.cuerpos;
  self.onmessage = ({ data }) => manejar(data);
}

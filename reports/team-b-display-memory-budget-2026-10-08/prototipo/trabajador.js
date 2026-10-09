/* PROTOTYPE (memory-budget investigation; not application code).
 *
 * Module worker: ONE combined raster per request for every outline of a
 * map's view, in the map's draw order, with each outline's own style. The
 * canvas has the map's real device size; the transform is the one Leaflet's
 * canvas renderer uses (scale by its pixel ratio, then translate by the
 * renderer bounds), and each outline is the same exact path drawn by
 * CapaContorno (positions x escala - pixel origin, rings closed by their
 * stored closing position), filled then stroked in Leaflet's _fillStroke
 * sequence. Composited 1:1 at the bounds, the bitmap reproduces drawing the
 * same outlines directly on that canvas.
 *
 * Messages in:
 *   {tipo: "cuerpo", id, copia, x, y, inicioAnillo, inicioParte, cajasParte, partes}
 *   {tipo: "olvidar", id, copia}        -> {tipo: "olvidado", copia}
 *   {tipo: "olvidarTodo", hasta}        -> {tipo: "olvidadoTodo", hasta}
 *   {tipo: "raster", pedido, ancho, alto, m, bmin: [x, y], origen: [x, y], escala, capas: [{id, estilo}]}
 *                                       -> {tipo: "raster", pedido, bitmap, ms, faltan: [ids]}
 *   {tipo: "cancelar", pedido}          -> {tipo: "raster", pedido, cancelado: true}
 *   {tipo: "estadisticas"}              -> {tipo: "estadisticas", entradas, bytes, lienzos, bytesLienzos, pendientes}
 * On start: {tipo: "listo", offscreen: boolean}.
 * Failure simulation for the prototype's tests (?simular=): "sinOffscreen"
 * reports no OffscreenCanvas; "error" throws on the first raster; "silencio"
 * never answers rasters; "sinInicio" (R2) never sends "listo".
 */

const CLAVES = ["x", "y", "inicioAnillo", "inicioParte", "cajasParte"];
export function bytesCopia(c) { let b = 0; for (const k of CLAVES) b += c[k].byteLength; return b; }

function trazar(ctx, c, escala, ox, oy, minX, minY, maxX, maxY) {
  const { x, y, inicioAnillo, inicioParte, cajasParte, partes } = c;
  ctx.beginPath();
  for (let p = 0; p < partes; p += 1) {
    const k = p * 4;
    if (cajasParte[k] > maxX || cajasParte[k + 2] < minX || cajasParte[k + 1] > maxY || cajasParte[k + 3] < minY) continue;
    for (let a = inicioParte[p]; a < inicioParte[p + 1]; a += 1) {
      const desde = inicioAnillo[a]; const hasta = inicioAnillo[a + 1];
      ctx.moveTo(x[desde] * escala - ox, y[desde] * escala - oy);
      for (let i = desde + 1; i < hasta; i += 1) ctx.lineTo(x[i] * escala - ox, y[i] * escala - oy);
    }
  }
}

function pintar(ctx, e) {
  // Leaflet 1.9.4 Canvas._fillStroke, in order.
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

export function crearManejador({ enviar, programar, crearLienzo, simular = null }) {
  const cuerpos = new Map();
  const pendientes = new Map();
  let programado = false;
  let lienzos = 0; let bytesLienzos = 0;          // scratch canvases alive (during a raster only)
  let fallo = simular === "error";

  function rasterizar(d) {
    const lienzo = crearLienzo(d.ancho, d.alto);
    lienzos += 1; bytesLienzos += d.ancho * d.alto * 4;
    const ctx = lienzo.getContext("2d");
    ctx.scale(d.m, d.m);
    ctx.translate(-d.bmin[0], -d.bmin[1]);
    // Area in world units, plus 4 px for strokes, for skipping far parts only.
    const margen = 4;
    const minX = (d.bmin[0] + d.origen[0] - margen) / d.escala;
    const minY = (d.bmin[1] + d.origen[1] - margen) / d.escala;
    const maxX = (d.bmin[0] + d.origen[0] + d.ancho / d.m + margen) / d.escala;
    const maxY = (d.bmin[1] + d.origen[1] + d.alto / d.m + margen) / d.escala;
    const faltan = [];
    for (const { id, estilo } of d.capas) {
      const c = cuerpos.get(id);
      if (!c) { faltan.push(id); continue; }
      trazar(ctx, c, d.escala, d.origen[0], d.origen[1], minX, minY, maxX, maxY);
      pintar(ctx, estilo);
    }
    const bitmap = lienzo.transferToImageBitmap();   // the canvas's pixels move into the bitmap
    // R1 inventory: after a transfer the specification gives the canvas a new
    // blank bitmap of the SAME size, alive until the canvas is collected. It is
    // never drawn, so shrink it now rather than leave an uncounted second
    // width x height x 4 buffer to the garbage collector.
    lienzo.width = 0;
    lienzo.height = 0;
    lienzos -= 1; bytesLienzos -= d.ancho * d.alto * 4;
    return { bitmap, faltan };
  }

  function siguiente() {
    programado = false;
    const primero = pendientes.entries().next();
    if (primero.done) return;
    const [pedido, d] = primero.value;
    pendientes.delete(pedido);
    if (fallo) throw new Error("simulated worker error");
    const t0 = performance.now();
    const { bitmap, faltan } = rasterizar(d);
    enviar({ tipo: "raster", pedido, bitmap, faltan, ms: performance.now() - t0 }, [bitmap]);
    if (pendientes.size && !programado) { programado = true; programar(siguiente); }
  }

  const manejar = (d) => {
    switch (d.tipo) {
      case "cuerpo": cuerpos.set(d.id, d); return;
      case "olvidar":
        if (cuerpos.get(d.id)?.copia === d.copia) cuerpos.delete(d.id);
        enviar({ tipo: "olvidado", copia: d.copia });
        return;
      case "olvidarTodo": cuerpos.clear(); enviar({ tipo: "olvidadoTodo", hasta: d.hasta }); return;
      case "raster":
        if (simular === "silencio") return;
        pendientes.set(d.pedido, d);
        if (!programado) { programado = true; programar(siguiente); }
        return;
      case "cancelar":
        if (pendientes.delete(d.pedido)) enviar({ tipo: "raster", pedido: d.pedido, cancelado: true });
        return;
      case "estadisticas": {
        let bytes = 0;
        for (const c of cuerpos.values()) bytes += bytesCopia(c);
        enviar({ tipo: "estadisticas", entradas: cuerpos.size, bytes, lienzos, bytesLienzos, pendientes: pendientes.size });
        return;
      }
      default:
    }
  };
  manejar.cuerpos = cuerpos;
  return manejar;
}

if (typeof WorkerGlobalScope !== "undefined" && globalThis instanceof WorkerGlobalScope) {
  const simular = new URL(self.location.href).searchParams.get("simular");
  const offscreen = typeof OffscreenCanvas === "function" && simular !== "sinOffscreen";
  const manejar = crearManejador({
    enviar: (m, t) => self.postMessage(m, t ?? []),
    programar: (fn) => setTimeout(fn, 0),
    crearLienzo: (w, h) => new OffscreenCanvas(w, h),
    simular,
  });
  self.onmessage = ({ data }) => manejar(data);
  if (simular !== "sinInicio") self.postMessage({ tipo: "listo", offscreen });
}

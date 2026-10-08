/* PROTOTYPE (display-strategy investigation; not application code).
 *
 * Module worker that rasterizes prepared bodies off the main thread
 * (OffscreenCanvas 2D). The geometry is the same prepared typed arrays the
 * main thread hit-tests; the drawing code is the same exact path (every
 * part intersecting the area, every position, rings closed with lineTo).
 *
 * Messages in:
 *   {tipo: "cuerpo", id, x, y, inicioAnillo, inicioParte, cajasParte, partes}
 *   {tipo: "raster", pedido, id, escala, x0, y0, ancho, alto, dpr, estilos}
 *     area = absolute pixels [x0, x0 + ancho) x [y0, y0 + alto) at `escala`
 *   {tipo: "olvidar", id} | {tipo: "olvidarTodo"}
 * Messages out:
 *   {tipo: "raster", pedido, id, bitmaps: [ImageBitmap per style], ms}
 * Requests are processed in order; the main thread drops superseded ones.
 */

const cuerpos = new Map();

function dibujar(ctx, c, escala, x0, y0) {
  const { x, y, inicioAnillo, inicioParte, cajasParte, partes } = c;
  const minX = x0 / escala; const minY = y0 / escala;
  const maxX = (x0 + ctx.canvas.width / ctx.dpr) / escala;
  const maxY = (y0 + ctx.canvas.height / ctx.dpr) / escala;
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

self.onmessage = ({ data }) => {
  if (data.tipo === "cuerpo") { cuerpos.set(data.id, data); return; }
  if (data.tipo === "olvidar") { cuerpos.delete(data.id); return; }
  if (data.tipo === "olvidarTodo") { cuerpos.clear(); return; }
  if (data.tipo !== "raster") return;
  const c = cuerpos.get(data.id);
  if (!c) return;
  const t0 = performance.now();
  const bitmaps = data.estilos.map((estilo) => {
    const lienzo = new OffscreenCanvas(Math.ceil(data.ancho * data.dpr), Math.ceil(data.alto * data.dpr));
    const ctx = lienzo.getContext("2d");
    ctx.dpr = data.dpr;
    ctx.scale(data.dpr, data.dpr);
    dibujar(ctx, c, data.escala, data.x0, data.y0);
    pintar(ctx, estilo);
    return lienzo.transferToImageBitmap();
  });
  self.postMessage({ tipo: "raster", pedido: data.pedido, id: data.id, bitmaps,
                     ms: performance.now() - t0 }, bitmaps);
};

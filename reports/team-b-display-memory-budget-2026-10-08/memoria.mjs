/* E5 memory evidence in a real Chromium: the scenario matrix of the packet,
 * every run audited against what is actually held.
 *
 *   B2_DIR=... E1_DIR=... CASOS_DIR=... CHROMIUM=... EVIDENCIA=<dir> \
 *     node reports/team-b-display-memory-budget-2026-10-08/memoria.mjs [escenario,...]
 *
 * Scenarios: matriz (64/128 MiB x DPR 1/2 x 1200x640/1920x1080 x 1/6/12
 * heavy outlines, overlapping, with light outlines and XY marks, one heavy
 * outline selected), cambio (resize during work), dos-mapas (two maps, one
 * budget), visitas (45 visits + 10 revisits), rafaga (rapid view and
 * selection changes), pequeno (too-small budgets), fallos (worker failure
 * modes), reinicio (reset and teardown).
 *
 * Audit (auditar): the ledger is compared with what is held:
 *   preparado = registry reservations + preparations in progress; each
 *               registry entry's typed-array byteLength equals its reservation;
 *   copia     = the worker client's reservations (held + awaiting
 *               acknowledgement); the worker's own byte count matches the
 *               held copies once quiet;
 *   raster    = displayed bitmap + in-flight reservations; the displayed
 *               bitmap's width x height x 4 equals its reservation and its size
 *               equals the canvas's real device size.
 * A per-frame sampler checks, during work, that the bytes held on the main
 * thread (typed arrays + displayed bitmaps) never exceed the ledger's
 * preparado + raster, and records the ledger peak; the ledger itself can
 * never exceed the budget (refused reservations allocate nothing).
 */

import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { entorno, servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const servidor = await servir(entorno());
const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const EVIDENCIA = process.env.EVIDENCIA ?? null;
const ELEGIDOS = (process.argv[2] ?? 'matriz,cambio,dos-mapas,visitas,rafaga,pequeno,fallos,reinicio').split(',');
const salida = { navegador: browser.version(), escenarios: {} };
let fallas = 0;
const ok = (cond, que) => { console.log(`${cond ? 'OK   ' : 'FALLA'} ${que}`); if (!cond) fallas += 1; };

const AYUDAS = () => {
  const MiB = 1024 * 1024;
  window.__pendientes = ['preparando', 'dibujando', 'cargando'];
  /** Until no outline of `filas` is pending in any map (max ms). */
  window.__asentar = async (filas, maxMs = 30000) => {
    const fin = performance.now() + maxMs;
    const pend = () => window.__m5.canvases.some((c) => filas.some((f) => window.__pendientes.includes(c.posicionDe(f.id)?.estadoContorno)));
    await new Promise((ok) => setTimeout(ok, 30));
    while (pend() && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 15));
    await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    return !pend();
  };
  /** States of the outline rows in map i. */
  window.__estados = (filas, i = 0) => {
    const c = window.__m5.canvases[i];
    const cuenta = {};
    for (const f of filas) {
      if (!f.geometria) continue;
      const p = c.posicionDe(f.id);
      const k = p?.contorno ? 'pintado' : (p?.estadoContorno ?? 'ausente');
      cuenta[k] = (cuenta[k] ?? 0) + 1;
    }
    return cuenta;
  };
  /* Per-frame sampler: main-thread bytes held vs the ledger's reservations for them. */
  window.__muestreo = { violaciones: [], muestras: 0, maxReal: 0 };
  const muestrear = () => {
    const m = window.__m5;
    if (m?.presupuesto) {
      let real = 0;
      for (const c of m.canvases) {
        const d = c._diagnostico;
        if (!d?.registro) continue;
        real += d.registro.bytesReales() + d.planificador.bytesReservados + d.controlador.bytesRaster().mostrada;
      }
      const cat = m.presupuesto.porCategoria();
      window.__muestreo.muestras += 1;
      window.__muestreo.maxReal = Math.max(window.__muestreo.maxReal, real);
      if (real > cat.preparado + cat.raster) window.__muestreo.violaciones.push({ real, cat });
      if (m.presupuesto.usados > m.presupuesto.total) window.__muestreo.violaciones.push({ excede: m.presupuesto.usados });
    }
    requestAnimationFrame(muestrear);
  };
  requestAnimationFrame(muestrear);
  /** Ledger vs actual holdings, all maps. */
  window.__auditar = async () => {
    const m = window.__m5; const p = m.presupuesto;
    const r = { total: p.total, usados: p.usados, pico: p.pico, ledger: p.porCategoria(), picoPorCategoria: p.picoPorCategoria(),
                rechazos: p.rechazos, pendienteDeLiberar: p.pendienteDeLiberar, mapas: [], errores: [] };
    let prep = 0; let copia = 0; let raster = 0;
    for (const [i, c] of m.canvases.entries()) {
      const d = c._diagnostico;
      const reg = d.registro.bytesReservados(); const regReal = d.registro.bytesReales(); const plan = d.planificador.bytesReservados;
      const cl = d.controlador.cliente;
      const w = cl && cl.estado === 'listo' ? await cl.estadisticas() : null;
      const br = d.controlador.bytesRaster();
      const lienzo = c.map.getContainer().querySelector('.leaflet-overlay-pane canvas');
      const mostrada = d.controlador.mostrada;
      prep += reg + plan; copia += cl?.bytesReservados() ?? 0; raster += br.reservadaMostrada + br.enVuelo;
      const mapa = { i, registro: { reservados: reg, reales: regReal, entradas: d.registro.tamano, fijados: d.registro.fijados() },
                     preparando: plan, cliente: cl ? { estado: cl.estado, motivo: cl.motivo, reservados: cl.bytesReservados(), copias: cl.copias } : null,
                     trabajador: w ? { bytes: w.bytes, entradas: w.entradas, lienzos: w.lienzos } : null,
                     raster: br, bitmap: mostrada ? [mostrada.bitmap.width, mostrada.bitmap.height] : null,
                     lienzo: lienzo ? [lienzo.width, lienzo.height] : null, metricas: { ...d.controlador.metricas } };
      if (reg !== regReal) r.errores.push(`map ${i}: registry reserved ${reg} != byteLength ${regReal}`);
      if (br.mostrada !== br.reservadaMostrada) r.errores.push(`map ${i}: bitmap ${br.mostrada} != reserved ${br.reservadaMostrada}`);
      if (mostrada && (mostrada.bitmap.width !== mostrada.area.ancho || mostrada.bitmap.height !== mostrada.area.alto)) {
        r.errores.push(`map ${i}: bitmap ${mostrada.bitmap.width}x${mostrada.bitmap.height} != its area ${mostrada.area.ancho}x${mostrada.area.alto}`);
      }
      if (mostrada && d.controlador.bitmapVigente() && (mostrada.bitmap.width !== lienzo.width || mostrada.bitmap.height !== lienzo.height)) {
        r.errores.push(`map ${i}: bitmap ${mostrada.bitmap.width}x${mostrada.bitmap.height} != canvas ${lienzo.width}x${lienzo.height}`);
      }
      const enBitmap = d.controlador.estado().modos.filter(([, modo]) => modo === 'bitmap').length;
      if (enBitmap && !d.controlador.bitmapVigente()) r.errores.push(`map ${i}: ${enBitmap} outlines claim a bitmap that is not current`);
      if (mostrada && !d.controlador.bitmapVigente()) r.errores.push(`map ${i}: an image for another view is still held`);
      if (w && p.pendienteDeLiberar === 0 && w.bytes > (cl?.bytesReservados() ?? 0)) r.errores.push(`map ${i}: worker holds ${w.bytes} > reserved ${cl.bytesReservados()}`);
      r.mapas.push(mapa);
    }
    if (prep !== r.ledger.preparado) r.errores.push(`ledger preparado ${r.ledger.preparado} != owners ${prep}`);
    if (copia !== r.ledger.copia) r.errores.push(`ledger copia ${r.ledger.copia} != clients ${copia}`);
    if (raster !== r.ledger.raster) r.errores.push(`ledger raster ${r.ledger.raster} != maps ${raster}`);
    if (r.pico > r.total) r.errores.push(`peak ${r.pico} > budget ${r.total}`);
    r.muestreo = { ...window.__muestreo, violaciones: window.__muestreo.violaciones.slice(0, 5), nViolaciones: window.__muestreo.violaciones.length };
    if (window.__muestreo.violaciones.length) r.errores.push(`sampler: ${window.__muestreo.violaciones.length} frames held more than reserved`);
    r.MiB = { total: +(r.total / MiB).toFixed(1), pico: +(r.pico / MiB).toFixed(1), usados: +(r.usados / MiB).toFixed(1) };
    return r;
  };
  /* Long tasks overlapping an interval (F1 method). */
  window.__tareas = [];
  const obs = new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__tareas.push([e.startTime, e.duration]); });
  obs.observe({ type: 'longtask', buffered: true });
  window.__tareaMax = async (t0, t1) => {
    await new Promise((ok) => setTimeout(ok, 0));
    await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    for (const e of obs.takeRecords()) window.__tareas.push([e.startTime, e.duration]);
    const s = window.__tareas.filter(([a, d]) => a < t1 && a + d > t0).map(([, d]) => d);
    return { tareaMaxMs: s.length ? Math.max(...s) : 0, tareasLargas: s.length };
  };
};

async function pagina({ mib = 64, dpr = 1, ancho = 1200, alto = 640, mapas = 1, simular = null, plazo = 8000 } = {}) {
  const page = await browser.newPage({ viewport: { width: ancho, height: alto }, deviceScaleFactor: dpr });
  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.addInitScript(AYUDAS);
  const q = new URLSearchParams({ impl: 'e5', mib, mapas, plazo, ...(simular ? { simular } : {}) });
  await page.goto(`${servidor.url}/mem/pagina.html?${q}`);
  await page.waitForFunction(() => document.title === 'listo');
  return { page, errores };
}

/** Render generated outlines in every map, frame them, settle; select one heavy outline. */
const PINTAR = async ({ n, ligeros = 2, xy = 3, seleccionar = true, paso = 0.02 }) => {
  const m = window.__m5;
  const d = m.sinteticos({ n, ligeros, xy, paso });
  const t0 = performance.now();
  await new Promise((ok) => setTimeout(ok, 0));
  for (const c of m.canvases) { c.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias }); c.fitTo(d.filas); }
  const asentado = await window.__asentar(d.filas);
  const tFinal = performance.now() - t0;
  const r = { asentado, contornoFinalMs: +tFinal.toFixed(0), estados: m.canvases.map((c, i) => window.__estados(d.filas, i)),
              ...(await window.__tareaMax(t0, performance.now())) };
  if (seleccionar) {
    const objetivo = d.filas.find((f) => f.id === 't-0') ? 't-0' : null;
    const t1 = performance.now();
    m.canvases[0].select(objetivo);
    const ctl = m.canvases[0]._diagnostico.controlador;
    const fin = performance.now() + 15000;
    // The selection is painted when the image shown carries t-0's selected style (or it is drawn directly).
    const pintada = () => {
      const capa = [...m.canvases[0].map._layers ? Object.values(m.canvases[0].map._layers) : []].find((l) => l._id === 'g-t-0');
      if (!capa) return true;
      if (capa._modo === 'directo') return true;
      return ctl.mostrada?.lista.some((x) => x.id === 'g-t-0' && x.clave.includes('#111111'));
    };
    while (!pintada() && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 10));
    r.seleccionPintadaMs = +(performance.now() - t1).toFixed(0);
    await window.__asentar(d.filas);
    r.estadosTrasSeleccion = window.__estados(d.filas, 0);
  }
  return r;
};

async function escenario(nombre, fn) {
  if (!ELEGIDOS.includes(nombre)) return;
  console.log(`\n== ${nombre}`);
  salida.escenarios[nombre] = await fn();
  if (EVIDENCIA) {
    mkdirSync(EVIDENCIA, { recursive: true });
    const parte = nombre === 'matriz' && (process.env.MATRIZ_MIB || process.env.MATRIZ_DPR)
      ? `-${process.env.MATRIZ_MIB ?? 'todos'}mib-dpr${process.env.MATRIZ_DPR ?? 'todos'}` : '';
    writeFileSync(path.join(EVIDENCIA, `memoria-${nombre}${parte}.json`),
                  JSON.stringify({ navegador: salida.navegador, escenario: nombre, resultado: salida.escenarios[nombre] }, null, 1));
  }
}

// 1. Matrix.
await escenario('matriz', async () => {
  const filas = [];
  // MATRIZ_MIB / MATRIZ_DPR restrict the matrix so it can be run in pieces.
  const mibs = process.env.MATRIZ_MIB ? [Number(process.env.MATRIZ_MIB)] : [64, 128];
  const dprs = process.env.MATRIZ_DPR ? [Number(process.env.MATRIZ_DPR)] : [1, 2];
  for (const mib of mibs) for (const dpr of dprs) for (const [ancho, alto] of [[1200, 640], [1920, 1080]]) for (const n of [1, 6, 12]) {
    const { page, errores } = await pagina({ mib, dpr, ancho, alto });
    const r = await page.evaluate(PINTAR, { n });
    const a = await page.evaluate(() => window.__auditar());
    await page.close();
    const fila = { mib, dpr, vista: `${ancho}x${alto}`, n, ...r, auditoria: a, errores };
    filas.push(fila);
    ok(a.errores.length === 0 && errores.length === 0 && r.asentado && a.pico <= a.total,
       `${mib} MiB DPR ${dpr} ${ancho}x${alto} ${n} heavy: states ${JSON.stringify(r.estados[0])}; peak ${a.MiB.pico} MiB `
       + `(raster peak ${(a.picoPorCategoria.raster / 2 ** 20).toFixed(1)}); contour ${r.contornoFinalMs} ms; selection ${r.seleccionPintadaMs} ms; `
       + `longest task ${r.tareaMaxMs} ms ${a.errores.concat(errores).join('; ')}`);
  }
  return filas;
});

// 2. Resize during work.
await escenario('cambio', async () => {
  const { page, errores } = await pagina({ mib: 64, dpr: 2, ancho: 1200, alto: 640 });
  const r = await page.evaluate(async () => {
    const m = window.__m5;
    const d = m.sinteticos({ n: 12, ligeros: 2, xy: 3 });
    m.canvas.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias });
    m.canvas.fitTo(d.filas);
    await new Promise((ok) => setTimeout(ok, 40));           // preparing / first raster in flight
    window.__filas = d.filas;
    return { antes: window.__estados(d.filas) };
  });
  await page.setViewportSize({ width: 1920, height: 1080 });
  const r2 = await page.evaluate(async () => {
    window.__m5.canvas.invalidate();
    await new Promise((ok) => setTimeout(ok, 30));
    const enMedio = window.__estados(window.__filas);
    const asentado = await window.__asentar(window.__filas);
    return { enMedio, asentado, despues: window.__estados(window.__filas) };
  });
  await page.setViewportSize({ width: 900, height: 500 });
  const r3 = await page.evaluate(async () => {
    window.__m5.canvas.invalidate();
    const asentado = await window.__asentar(window.__filas);
    return { asentado, final: window.__estados(window.__filas) };
  });
  const a = await page.evaluate(() => window.__auditar());
  await page.close();
  ok(a.errores.length === 0 && errores.length === 0 && r2.asentado && r3.asentado,
     `resize 1200x640 -> 1920x1080 -> 900x500 during work (DPR 2, 64 MiB): canvas ${JSON.stringify(a.mapas[0].lienzo)}, `
     + `bitmap ${JSON.stringify(a.mapas[0].bitmap)}, states ${JSON.stringify(r3.final)}, peak ${a.MiB.pico} MiB, `
     + `obsolete replies ${a.mapas[0].metricas.obsoletos} ${a.errores.concat(errores).join('; ')}`);
  return { ...r, ...r2, ...r3, auditoria: a, errores };
});

// 3. Two maps, one budget.
await escenario('dos-mapas', async () => {
  const filas = [];
  for (const mib of [64, 128]) {
    const { page, errores } = await pagina({ mib, dpr: 2, ancho: 1920, alto: 1080, mapas: 2 });
    const r = await page.evaluate(PINTAR, { n: 12 });
    const a = await page.evaluate(() => window.__auditar());
    await page.close();
    filas.push({ mib, ...r, auditoria: a, errores });
    ok(a.errores.length === 0 && errores.length === 0 && a.pico <= a.total,
       `two maps, ${mib} MiB, DPR 2, 1920x1080: map 0 ${JSON.stringify(r.estados[0])}, map 1 ${JSON.stringify(r.estados[1])}; `
       + `peak ${a.MiB.pico} MiB (raster ${(a.picoPorCategoria.raster / 2 ** 20).toFixed(1)}) ${a.errores.concat(errores).join('; ')}`);
  }
  return filas;
});

// 4. 45 visits and 10 revisits.
await escenario('visitas', async () => {
  const { page, errores } = await pagina({ mib: 64, dpr: 1 });
  const r = await page.evaluate(async () => {
    const m = window.__m5; const c = m.canvas;
    const t0 = performance.now();
    const visitar = async (i) => {
      const d = m.sinteticos({ n: 1, posiciones: 60000, ligeros: 0, xy: 0, semilla: 2 });
      // A distinct terrain per visit: shift it and rename its geometry.
      const f = d.filas[0]; const g = d.geometrias.get(f.geometria.id);
      const dx = i * 0.05;
      const mover = (p) => [p[0] + dx, p[1]];
      g.geojson.coordinates = g.geojson.coordinates.map((poly) => poly.map((ring) => ring.map(mover)));
      g.bbox = [g.bbox[0] + dx, g.bbox[1], g.bbox[2] + dx, g.bbox[3]];
      g.punto_interior = { type: 'Point', coordinates: mover(g.punto_interior.coordinates) };
      const id = `visita-${i}`;
      const filas = [{ ...f, id: `t-${i}`, geometria: { ...f.geometria, id, bbox: g.bbox, punto_interior: g.punto_interior } }];
      c.render(filas, { colorFor: m.colorFor, geometrias: new Map([[id, g]]) });
      c.zoomToScale(`t-${i}`);
      await window.__asentar(filas);
      return c.posicionDe(`t-${i}`);
    };
    const res = [];
    for (let i = 0; i < 45; i += 1) res.push(await visitar(i));
    for (let i = 0; i < 10; i += 1) res.push(await visitar(i));
    const t1 = performance.now();
    return { pintados: res.filter((p) => p.contorno).length, total: res.length, ms: +(t1 - t0).toFixed(0),
             ...(await window.__tareaMax(t0, t1)), expulsados: c._diagnostico.registro.metricas.expulsados,
             copias: c._diagnostico.controlador.cliente.metricas };
  });
  const a = await page.evaluate(() => window.__auditar());
  await page.close();
  ok(a.errores.length === 0 && errores.length === 0 && r.pintados === r.total,
     `45 visits + 10 revisits (60,000 positions each, 64 MiB): ${r.pintados}/${r.total} drawn; registry evictions ${r.expulsados}; `
     + `worker copies sent ${r.copias.copiasEnviadas}, forgotten ${r.copias.olvidos}; peak ${a.MiB.pico} MiB; longest task ${r.tareaMaxMs} ms `
     + `${a.errores.concat(errores).join('; ')}`);
  return { ...r, auditoria: a, errores };
});

// 5. Burst of view and selection changes.
await escenario('rafaga', async () => {
  const { page, errores } = await pagina({ mib: 64, dpr: 2, ancho: 1200, alto: 640 });
  await page.evaluate(PINTAR, { n: 12, seleccionar: false });
  // Real wheel and drag input interleaved with programmatic selection changes, no waiting.
  for (let i = 0; i < 20; i += 1) {
    await page.mouse.move(600, 320);
    if (i % 3 === 0) await page.mouse.wheel(0, i % 2 ? 120 : -120);
    else { await page.mouse.down(); await page.mouse.move(600 + (i % 2 ? 40 : -40), 330); await page.mouse.up(); }
    await page.evaluate((i) => window.__m5.canvas.select(i % 2 ? 't-0' : (i % 5 ? 't-3' : null)), i);
  }
  const r = await page.evaluate(async () => {
    const ctl = window.__m5.canvas._diagnostico.controlador;
    const filas = window.__m5.canvas.map ? Object.values(window.__m5.canvas.map._layers).filter((l) => l._id).map((l) => ({ id: l._id })) : [];
    const fin = performance.now() + 20000;
    while ((ctl.enVuelo || !ctl.bitmapVigente()) && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 20));
    await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    const modos = ctl.estado().modos;
    return { capas: filas.length, enVuelo: Boolean(ctl.enVuelo), vigente: ctl.bitmapVigente(), metricas: { ...ctl.metricas },
             modos: modos.reduce((a, [, modo, estado]) => { a[`${modo}/${estado}`] = (a[`${modo}/${estado}`] ?? 0) + 1; return a; }, {}) };
  });
  const a = await page.evaluate(() => window.__auditar());
  await page.close();
  ok(a.errores.length === 0 && errores.length === 0 && !r.enVuelo && (r.vigente || !a.mapas[0].bitmap),
     `burst of 20 real wheel/drag inputs with selection changes (DPR 2): settled, image for the current view; rasters `
     + `${r.metricas.rasters}, obsolete replies discarded ${r.metricas.obsoletos}; modes ${JSON.stringify(r.modos)}; peak ${a.MiB.pico} MiB `
     + `${a.errores.concat(errores).join('; ')}`);
  return { ...r, auditoria: a, errores };
});

// 6. Too-small budgets: the declared fallback before anything is allocated.
await escenario('pequeno', async () => {
  const filas = [];
  for (const [mib, ancho, alto, dpr] of [[4, 1920, 1080, 1], [16, 1920, 1080, 2], [1, 1200, 640, 1]]) {
    const { page, errores } = await pagina({ mib, dpr, ancho, alto });
    const r = await page.evaluate(PINTAR, { n: 6, seleccionar: false });
    const extra = await page.evaluate(() => {
      const c = window.__m5.canvas;
      const filas = window.__m5.sinteticos({ n: 6, ligeros: 2, xy: 3 }).filas;
      return { avisos: filas.filter((f) => f.geometria).map((f) => [f.id, c.posicionDe(f.id)?.estadoContorno,
        (c._diagnostico.aviso(f.id) ?? '').replace(/<[^>]+>/g, ' ').trim()]), zoom: c.zoomToScale('t-0') };
    });
    const a = await page.evaluate(() => window.__auditar());
    await page.close();
    filas.push({ mib, dpr, vista: `${ancho}x${alto}`, ...r, ...extra, auditoria: a, errores });
    ok(a.errores.length === 0 && errores.length === 0 && r.asentado,
       `${mib} MiB, ${ancho}x${alto} DPR ${dpr}: states ${JSON.stringify(r.estados[0])}; raster peak ${a.picoPorCategoria.raster} B; `
       + `worker canvases ${a.mapas[0].trabajador?.lienzos ?? '—'}; zoomToScale ${JSON.stringify(extra.zoom.estado)}/${extra.zoom.motivo ?? ''} `
       + `${a.errores.concat(errores).join('; ')}`);
  }
  return filas;
});

// 7. Worker failures.
await escenario('fallos', async () => {
  const filas = [];
  for (const simular of ['constructor', 'sinOffscreen', 'error', 'silencio']) {
    const { page, errores } = await pagina({ mib: 64, simular, plazo: 1500 });
    const t0 = Date.now();
    const r = await page.evaluate(PINTAR, { n: 6, seleccionar: false });
    const extra = await page.evaluate(() => {
      const c = window.__m5.canvas;
      const filas = window.__m5.sinteticos({ n: 6, ligeros: 2, xy: 3 }).filas;
      return { avisos: filas.filter((f) => f.geometria).map((f) => [f.id, c.posicionDe(f.id)?.estadoContorno,
        (c._diagnostico.aviso(f.id) ?? '').replace(/<[^>]+>/g, ' ').trim()]), cliente: c._diagnostico.controlador.estado() };
    });
    const a = await page.evaluate(() => window.__auditar());
    await page.close();
    const noPendiente = extra.avisos.every(([, e]) => !['preparando', 'dibujando', 'cargando'].includes(e));
    filas.push({ simular, ...r, ...extra, auditoria: a, errores, ms: Date.now() - t0 });
    ok(r.asentado && noPendiente && a.ledger.copia === 0 && a.ledger.raster === 0 && a.errores.length === 0,
       `worker failure "${simular}": client ${extra.cliente.cliente}/${extra.cliente.motivo}; states ${JSON.stringify(r.estados[0])}; `
       + `nothing pending after ${r.contornoFinalMs} ms; worker and raster reservations released `
       + `${a.errores.join('; ')}`);
  }
  return filas;
});

// 8. Reset and teardown, audited per map (the other map keeps its own holdings).
await escenario('reinicio', async () => {
  const { page, errores } = await pagina({ mib: 64, dpr: 1, mapas: 2 });
  await page.evaluate(PINTAR, { n: 6, seleccionar: false });
  const r = await page.evaluate(async () => {
    const m = window.__m5; const p = m.presupuesto;
    const antes = await window.__auditar();
    m.canvases[0].render([]);
    const contadoAntesDeConfirmar = p.porCategoria();
    const confirmado = await m.canvases[0]._diagnostico.reinicioTrabajador;
    await new Promise((ok) => setTimeout(ok, 50));
    const trasReinicio = await window.__auditar();
    // Map 0's remaining holdings, to compare with the ledger once map 1 is gone.
    const d0 = m.canvases[0]._diagnostico;
    const br0 = d0.controlador.bytesRaster();
    const resto0 = d0.registro.bytesReservados() + d0.planificador.bytesReservados
      + (d0.controlador.cliente?.bytesReservados() ?? 0) + br0.reservadaMostrada + br0.enVuelo;
    m.canvases[1].destruir();
    await new Promise((ok) => setTimeout(ok, 50));
    return { antes, contadoAntesDeConfirmar, confirmado, trasReinicio, resto0, trasDestruir: p.porCategoria(), usados: p.usados };
  });
  await page.close();
  const m0 = r.trasReinicio.mapas[0]; const m1a = r.antes.mapas[1]; const m1b = r.trasReinicio.mapas[1];
  const raster0 = m0.raster.reservadaMostrada + m0.raster.enVuelo;
  const intacto1 = m1b.registro.reservados === m1a.registro.reservados && m1b.cliente.reservados === m1a.cliente.reservados
    && m1b.raster.reservadaMostrada === m1a.raster.reservadaMostrada;
  ok(r.confirmado && r.antes.errores.length === 0 && r.trasReinicio.errores.length === 0 && raster0 === 0 && !m0.bitmap
     && m0.cliente.reservados === 0 && m0.registro.entradas === 0 && intacto1
     && r.contadoAntesDeConfirmar.copia === r.antes.ledger.copia && r.usados === r.resto0 && errores.length === 0,
     `reset of map 0: image and prepared bodies released at once, its ${m1a.cliente ? r.antes.mapas[0].cliente.reservados : 0} B of worker `
     + `copies counted until the worker acknowledged (${r.confirmado}); map 1 untouched (${m1b.registro.reservados} B prepared, `
     + `${m1b.cliente.reservados} B copies, ${m1b.raster.reservadaMostrada} B image); teardown of map 1 releases all of it: ledger `
     + `${r.usados} B = map 0's remaining ${r.resto0} B ${r.antes.errores.concat(r.trasReinicio.errores, errores).join('; ')}`);
  return { ...r, errores };
});

await browser.close();
servidor.cerrar();
console.log(fallas ? `${fallas} fallo(s)` : 'Todas las comprobaciones pasaron');
process.exit(fallas ? 1 : 0);

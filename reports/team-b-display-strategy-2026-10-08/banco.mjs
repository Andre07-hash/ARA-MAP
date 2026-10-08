/* Display-strategy benchmark: the accepted B-2 renderer against three
 * prototype strategies, in a real Chromium with real pointer input.
 *
 *   (cd tests/e2e && npm install)          # playwright-core, as for B-2
 *   B2_DIR=<git archive 5d8e2dc> CASOS_DIR=<generar_casos.py out> \
 *   CHROMIUM=/path/to/chrome EVIDENCIA=<dir> \
 *     node reports/team-b-display-strategy-2026-10-08/banco.mjs [impl,...] [case,...]
 *
 * Strategies: b2 (accepted), e1 (no closePath), e2 (prepared + culled),
 * e3 (e2 + cooperative cancellable preparation), e4 (e3 + worker raster). Cases: the four generated
 * limit cases, the B-2 12-row fixture ("fixture") and 500 XY points ("xy").
 *
 * Per run (fresh page): cold load to a painted outline; repeated real drags
 * and wheel zooms; real clicks on a small part and the interior point;
 * rapid render cancellation; teardown; JS heap after GC. Long tasks come
 * from the Long Tasks API, input acknowledgement from the Event Timing API
 * (input to next paint), frame gaps from requestAnimationFrame. Paint
 * evidence waits two frames and rejects blank canvases. Wall-clock figures
 * are for the recorded machine only.
 */

import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');

const B2 = process.env.B2_DIR;
const CASOS = process.env.CASOS_DIR;
if (!B2 || !CASOS) throw new Error('set B2_DIR and CASOS_DIR (see the report)');
const EVIDENCIA = process.env.EVIDENCIA ?? null;
const IMPLS = (process.argv[2] ?? 'b2,e1,e2,e3').split(',');
const TODOS = ['fixture', 'xy', 'circulo-100k', 'multiparte-20000', 'grande-mas-19999',
               'denso-grande-mas-19999'];
const CASOS_ELEGIDOS = (process.argv[3] ?? TODOS.join(',')).split(',');
const REPETICIONES = Number(process.env.REPETICIONES ?? 3);

const servidor = await servir({ b2: B2, casos: CASOS });
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
if (EVIDENCIA) mkdirSync(EVIDENCIA, { recursive: true });

/* Installed before any page script: long tasks, event timing, frame gaps. */
const INSTRUMENTOS = () => {
  const m = { tareas: [], eventos: [], cuadros: [], errores: [] };
  window.__m = m;
  new PerformanceObserver((l) => { for (const e of l.getEntries()) m.tareas.push([e.startTime, e.duration]); })
    .observe({ type: 'longtask', buffered: true });
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) m.eventos.push([e.startTime, e.duration, e.name, e.processingStart - e.startTime]);
  }).observe({ type: 'event', durationThreshold: 16, buffered: true });
  const ciclo = (t) => { m.cuadros.push(t); requestAnimationFrame(ciclo); };
  requestAnimationFrame(ciclo);
  window.addEventListener('error', (e) => m.errores.push(String(e.message)));
  /* Summary of everything observed since t0 (ms, performance clock). */
  window.__desde = (t0) => {
    const tareas = m.tareas.filter(([s]) => s >= t0).map(([, d]) => d);
    const eventos = m.eventos.filter(([s]) => s >= t0);
    const cuadros = m.cuadros.filter((t) => t >= t0);
    let cuadroMax = 0;
    for (let i = 1; i < cuadros.length; i += 1) cuadroMax = Math.max(cuadroMax, cuadros[i] - cuadros[i - 1]);
    return {
      tareaMaxMs: tareas.length ? Math.max(...tareas) : 0,
      tareasLargas: tareas.length,
      eventoMaxMs: eventos.length ? Math.max(...eventos.map((e) => e[1])) : null,
      retrasoEntradaMaxMs: eventos.length ? Math.max(...eventos.map((e) => e[3])) : null,
      eventos: eventos.length,
      cuadroMaxMs: +cuadroMax.toFixed(1),
    };
  };
  window.__dosCuadros = () => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
  /* Until the view has not changed for 4 frames (animations finished; max 3 s). */
  window.__quieto = async () => {
    const mapa = window.__banco.canvas.map;
    const fin = performance.now() + 3000;
    let previo = ''; let iguales = 0;
    while (iguales < 4 && performance.now() < fin) {
      await new Promise((ok) => requestAnimationFrame(ok));
      const c = mapa.getCenter(); const ahora = `${c.lat},${c.lng},${mapa.getZoom()}`;
      iguales = ahora === previo ? iguales + 1 : 0;
      previo = ahora;
    }
  };
  /* Until the terrain's outline is neither preparing nor drawing (max 20 s). */
  window.__sinPendiente = async (id, maxMs = 20000) => {
    const fin = performance.now() + maxMs;
    const pendiente = () => ['preparando', 'dibujando'].includes(window.__banco.canvas.posicionDe(id)?.estadoContorno);
    while (pendiente() && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 5));
    await window.__dosCuadros();
  };
};

/* Paint evidence (B-2's corrected method): two frames, then the canvas. */
async function pintura(page) {
  return page.evaluate(async () => {
    await window.__dosCuadros();
    const lienzo = document.querySelector('.leaflet-overlay-pane canvas');
    const ctx = lienzo.getContext('2d');
    const { data, width, height } = ctx.getImageData(0, 0, lienzo.width, lienzo.height);
    let pintados = 0;
    const mascara = new Uint8Array(Math.ceil((width * height) / 8));
    for (let i = 3, px = 0; i < data.length; i += 4, px += 1) {
      if (data[i]) { pintados += 1; mascara[px >> 3] |= 1 << (px & 7); }
    }
    const resumen = await crypto.subtle.digest('SHA-256', data);
    const hex = [...new Uint8Array(resumen)].map((b) => b.toString(16).padStart(2, '0')).join('');
    let binario = '';
    for (let i = 0; i < mascara.length; i += 1) binario += String.fromCharCode(mascara[i]);
    return { ancho: width, alto: height, pintados, sha256: hex, mascara: btoa(binario) };
  });
}

async function heap(cdp) {
  await cdp.send('HeapProfiler.collectGarbage');
  const { metrics } = await cdp.send('Performance.getMetrics');
  return +(metrics.find((x) => x.name === 'JSHeapUsedSize').value / 2 ** 20).toFixed(1);
}

/* Settle after real input: moveend (if any) and two frames. */
const ESPERAR_ASENTADO = () => new Promise((ok) => {
  const mapa = window.__banco.canvas.map;
  const t0 = performance.now();
  let listo = false;
  const fin = () => {
    if (listo) return;
    listo = true;
    window.__dosCuadros().then(async () => {
      const asentado = performance.now() - t0;
      await window.__sinPendiente('contorno', 5000);
      ok({ asentado, completo: performance.now() - t0 });
    });
  };
  mapa.once('moveend', fin);
  setTimeout(fin, 8000);
});

async function corrida(impl, caso, repeticion) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 } });
  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.addInitScript(INSTRUMENTOS);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  await page.goto(`${servidor.url}/proto/banco.html?impl=${impl}`);
  await page.waitForFunction(() => document.title === 'listo');

  // Data into the page, outside every timed section.
  const info = await page.evaluate(async (c) => {
    const b = window.__banco;
    b.d = c === 'fixture' ? await b.cargarFixture() : c === 'xy' ? b.cargarXY() : await b.cargar(c);
    const otro = c === 'circulo-100k' ? 'multiparte-20000' : 'circulo-100k';
    b.otro = await b.cargar(otro);                  // for the cancellation scenario
    b.fix = await b.cargarFixture();
    return { filas: b.d.filas.length, objetivo: b.d.filas.find((t) => t.geometria)?.id ?? b.d.filas[0].id };
  }, caso);
  const heapAntes = await heap(cdp);
  const r = { impl, caso, repeticion, filas: info.filas };

  // A. Cold: render, frame the terrain at outline scale, wait for the outline.
  r.frio = await page.evaluate(async (id) => {
    const b = window.__banco;
    const opciones = { colorFor: b.colorFor, geometrias: b.d.geometrias };
    const t0 = performance.now();
    b.canvas.render(b.d.filas, opciones);
    const tRender = performance.now() - t0;
    const primero = b.canvas.zoomToScale(id);
    const tSync = performance.now() - t0;
    await window.__dosCuadros();
    const tPrimerCuadro = performance.now() - t0;
    // Pending outlines (preparing, or E4 drawing): wait, then frame again.
    await window.__sinPendiente(id);
    let estadoFinal = primero.estado;
    if (primero.estado === 'contorno_pendiente') {
      estadoFinal = b.canvas.zoomToScale(id).estado;
      await window.__sinPendiente(id);
      if (estadoFinal === 'contorno_pendiente') estadoFinal = b.canvas.zoomToScale(id).estado;
    }
    await window.__dosCuadros();
    const pos = b.canvas.posicionDe(id);
    return {
      renderMs: +tRender.toFixed(1), sincronoMs: +tSync.toFixed(1), primerCuadroMs: +tPrimerCuadro.toFixed(1),
      hastaContornoMs: +(performance.now() - t0).toFixed(1), estadoInicial: primero.estado, estadoFinal,
      zoom: b.canvas.map.getZoom(), contorno: pos?.contorno ?? false, ...window.__desde(t0),
    };
  }, info.objetivo);
  r.pintura = await pintura(page);
  if (r.pintura.pintados === 0) throw new Error(`${impl}/${caso}: blank canvas`);
  if (EVIDENCIA && repeticion === 0) {
    await page.screenshot({ path: path.join(EVIDENCIA, `${caso}-${impl}.png`) });
  }

  // B. Repeated views with real input at that view: drags and wheel zooms.
  const acciones = [];
  for (let i = 0; i < 6; i += 1) {
    const t0 = await page.evaluate(() => performance.now());
    const espera = page.evaluate(ESPERAR_ASENTADO);
    const dx = i % 2 ? 1 : -1;
    await page.mouse.move(600, 320);
    await page.mouse.down();
    for (let k = 1; k <= 6; k += 1) await page.mouse.move(600 + dx * k * 25, 320 + k * 6);
    await page.mouse.up();
    const e = await espera;
    acciones.push(await page.evaluate(([t, c]) => ({ tipo: 'arrastre', ms: performance.now() - t,
      contornoCompletoMs: c, ...window.__desde(t) }), [t0, e.completo]));
  }
  for (let i = 0; i < 4; i += 1) {
    const t0 = await page.evaluate(() => performance.now());
    const espera = page.evaluate(ESPERAR_ASENTADO);
    await page.mouse.move(600, 320);
    await page.mouse.wheel(0, i % 2 ? 120 : -120);
    const e = await espera;
    acciones.push(await page.evaluate(([t, c]) => ({ tipo: 'rueda', ms: performance.now() - t,
      contornoCompletoMs: c, ...window.__desde(t) }), [t0, e.completo]));
  }
  // Direct redraw cost, as B-2 measured it (no animation): pan 200 px, zoom +1/-1.
  const directo = await page.evaluate(async () => {
    const mapa = window.__banco.canvas.map;
    const salida = [];
    for (const [tipo, f] of [['pan', () => mapa.panBy([200, 0], { animate: false })],
                             ['pan', () => mapa.panBy([-200, 0], { animate: false })],
                             ['zoom', () => mapa.setZoom(mapa.getZoom() + 1, { animate: false })],
                             ['zoom', () => mapa.setZoom(mapa.getZoom() - 1, { animate: false })]]) {
      const t0 = performance.now();
      f();
      await window.__dosCuadros();
      const ms = performance.now() - t0;
      await window.__sinPendiente('contorno', 5000);
      salida.push({ tipo: `${tipo}-directo`, ms, contornoCompletoMs: performance.now() - t0,
                    ...window.__desde(t0) });
    }
    return salida;
  });
  r.vistas = [...acciones, ...directo].map((a) => ({ ...a, ms: +a.ms.toFixed(1) }));

  // C. Selection with real clicks: a small part (multipart cases) and the
  // interior point. Each click: input-to-paint and the selected ID.
  r.seleccion = [];
  await page.evaluate(async (id) => {
    const b = window.__banco;
    b.canvas.zoomToScale(id);                       // XY rows animate; boundaries do not
    await window.__quieto();
    await window.__sinPendiente(id);
  }, info.objetivo);
  const objetivos = await page.evaluate((id) => {
    const b = window.__banco;
    const mapa = b.canvas.map;
    const lista = [];
    const pos = b.canvas.posicionDe(id);
    if (pos) lista.push({ que: 'punto-interior', x: pos.x, y: pos.y });
    const fila = b.d.filas.find((t) => t.id === id);
    const cuerpo = fila?.geometria && b.d.geometrias?.get(fila.geometria.id);
    if (cuerpo && cuerpo.geojson.coordinates.length > 1) {
      // The last small part: its centre, brought on screen at this zoom.
      const anillo = cuerpo.geojson.coordinates.at(-1)[0];
      const lon = anillo.slice(0, -1).reduce((a, p) => a + p[0], 0) / (anillo.length - 1);
      const lat = anillo.slice(0, -1).reduce((a, p) => a + p[1], 0) / (anillo.length - 1);
      mapa.setView([lat, lon], mapa.getZoom(), { animate: false });
      const p = mapa.latLngToContainerPoint([lat, lon]);
      lista.push({ que: 'parte-pequena', x: p.x, y: p.y });
    }
    return lista;
  }, info.objetivo);
  await page.evaluate(() => window.__quieto());
  await page.evaluate(() => window.__sinPendiente('contorno'));
  // Paint at this detail view too (small parts are several pixels here).
  r.pinturaDetalle = await pintura(page);
  if (r.pinturaDetalle.pintados === 0) throw new Error(`${impl}/${caso}: blank detail canvas`);
  for (const o of objetivos.reverse()) {
    await page.evaluate(() => { window.__banco.selecciones.length = 0; window.__banco.canvas.select(null); });
    await page.evaluate(() => window.__dosCuadros());
    const t0 = await page.evaluate(() => performance.now());
    await page.mouse.click(o.x, o.y);
    // onSelect fires after the renderer's deliberate 280 ms double-click window.
    await page.waitForFunction(() => window.__banco.selecciones.length > 0, null, { timeout: 8000 }).catch(() => {});
    r.seleccion.push(await page.evaluate(([q, t]) => {
      const s = window.__banco.selecciones[0];
      return { que: q, seleccionado: s?.id ?? null,
               msHastaOnSelect: s ? +(s.t - t).toFixed(1) : null, ...window.__desde(t) };
    }, [o.que, t0]));
  }
  r.heapDespuesMiB = await heap(cdp);
  r.heapAntesMiB = heapAntes;

  // D. Rapid cancellation: four renders one frame apart, ending in a reset.
  r.cancelacion = await page.evaluate(async () => {
    const b = window.__banco;
    const t0 = performance.now();
    const op = (d) => ({ colorFor: b.colorFor, geometrias: d.geometrias });
    b.canvas.render(b.d.filas, op(b.d)); await window.__dosCuadros();
    b.canvas.render(b.otro.filas, op(b.otro)); await window.__dosCuadros();
    b.canvas.render(b.fix.filas, op(b.fix)); await window.__dosCuadros();
    const tReset = performance.now();
    b.canvas.render([]);
    await new Promise((ok) => setTimeout(ok, 1200));
    const tarde = b.estados.filter((e) => e.t > tReset);
    return {
      ms: +(tReset - t0).toFixed(1), ...window.__desde(t0),
      pendientes: (b.canvas._diagnostico?.planificador.pendientes ?? 0)
        + (b.canvas._diagnostico?.raster?.enVuelo ?? 0),
      cacheBytes: b.canvas._diagnostico?.cache.bytes ?? null,
      estadosTrasReinicio: tarde.length, dibujadoTrasReinicio: b.canvas.posicionDe('contorno') !== null,
    };
  });

  // E. Teardown while a large body may still be preparing.
  r.desmontaje = await page.evaluate(async () => {
    const b = window.__banco;
    b.canvas.render(b.otro.filas, { colorFor: b.colorFor, geometrias: b.otro.geometrias });
    const diag = b.canvas._diagnostico;
    const pendientesAntes = diag?.planificador.pendientes ?? 0;
    if (b.canvas.destruir) b.canvas.destruir(); else b.canvas.map.remove();
    await new Promise((ok) => setTimeout(ok, 800));
    return { pendientesAntes, pendientesDespues: diag?.planificador.pendientes ?? 0,
             errores: window.__m.errores.length };
  });
  r.errores = errores;
  await page.close();
  return r;
}

/* Memory under many visits: VISITAS (default 45) distinct 60k-position
 * bodies, one at a time: 45 x ~0.96 MB exceeds the 32 MiB cache budget. */
const VISITAS = Number(process.env.VISITAS ?? 45);
async function visitas(impl) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 } });
  await page.addInitScript(INSTRUMENTOS);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  await page.goto(`${servidor.url}/proto/banco.html?impl=${impl}`);
  await page.waitForFunction(() => document.title === 'listo');
  const antes = await heap(cdp);
  const r = await page.evaluate(async (visitas) => {
    const b = window.__banco;
    const t0 = performance.now();
    let cacheMax = 0;
    for (let i = 0; i < visitas; i += 1) {
      const n = 60_000;
      const lon0 = -100.5 + i * 0.05; const lat0 = 20.6; const rad = 0.01;
      const anillo = Array.from({ length: n - 1 }, (_, k) => [lon0 + rad * Math.cos((2 * Math.PI * k) / (n - 1)),
                                                             lat0 + rad * Math.sin((2 * Math.PI * k) / (n - 1))]);
      anillo.push([...anillo[0]]);
      const xs = anillo.map((p) => p[0]); const ys = anillo.map((p) => p[1]);
      const bbox = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
      const punto = { type: 'Point', coordinates: [lon0, lat0] };
      const id = `visita-${i}`;
      const geometrias = new Map([[id, { geojson: { type: 'MultiPolygon', coordinates: [[anillo]] }, bbox, punto_interior: punto }]]);
      const filas = [{ id: 't', terreno: 'Visita', lat: null, lon: null,
                       geometria: { id, archivo_version_id: `v${i}`, utilizable: true, bbox, punto_interior: punto } }];
      b.canvas.render(filas, { colorFor: b.colorFor, geometrias });
      while (b.canvas.posicionDe('t')?.estadoContorno === 'preparando') await new Promise((ok) => setTimeout(ok, 10));
      b.canvas.zoomToScale('t');
      await window.__sinPendiente('t');
      cacheMax = Math.max(cacheMax, b.canvas._diagnostico?.cache.bytes ?? 0);
    }
    return { visitas, ms: +(performance.now() - t0).toFixed(0), cacheBytes: b.canvas._diagnostico?.cache.bytes ?? null,
             cacheBytesMax: cacheMax, cacheEntradas: b.canvas._diagnostico?.cache.tamano ?? null,
             tareasLargas: window.__desde(t0).tareasLargas, tareaMaxMs: window.__desde(t0).tareaMaxMs };
  }, VISITAS);
  const despues = await heap(cdp);
  const reinicio = await page.evaluate(() => { window.__banco.canvas.render([]); return window.__banco.canvas._diagnostico?.cache.bytes ?? null; });
  const trasReinicio = await heap(cdp);
  await page.close();
  return { impl, ...r, heapAntesMiB: antes, heapDespuesMiB: despues, cacheTrasReinicio: reinicio, heapTrasReinicioMiB: trasReinicio };
}

const mediana = (v) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[Math.floor((s.length - 1) / 2)] : null; };
const peor = (v) => (v.length ? Math.max(...v) : null);

const salida = {
  navegador: browser.version(),
  maquina: { cpu: os.cpus()[0]?.model, nucleos: os.cpus().length, memoriaGiB: +(os.totalmem() / 2 ** 30).toFixed(1),
             sistema: `${os.type()} ${os.release()}`, node: process.version },
  repeticiones: REPETICIONES, corridas: [], visitas: [],
};
console.log(`Chromium ${salida.navegador} · ${salida.maquina.cpu} ×${salida.maquina.nucleos}`);
for (const caso of CASOS_ELEGIDOS) {
  for (const impl of IMPLS) {
    for (let i = 0; i < REPETICIONES; i += 1) {
      const r = await corrida(impl, caso, i);
      salida.corridas.push(r);
      const v = r.vistas;
      console.log(JSON.stringify({ caso, impl, i, frio: r.frio.hastaContornoMs, frioTarea: r.frio.tareaMaxMs,
        vistaPeor: peor(v.map((x) => x.ms)), vistaTarea: peor(v.map((x) => x.tareaMaxMs)),
        sel: r.seleccion.map((s) => `${s.que}:${s.seleccionado}`).join(' '),
        cancelTarea: r.cancelacion.tareaMaxMs, pintados: r.pintura.pintados }));
    }
  }
}
for (const impl of IMPLS) {
  if (!process.env.SIN_VISITAS) {
    const v = await visitas(impl);
    salida.visitas.push(v);
    console.log(JSON.stringify(v));
  }
}

/* Paint comparisons at the same outline view: each strategy against b2. */
salida.comparacionPintura = [];
for (const caso of CASOS_ELEGIDOS) {
  const base = salida.corridas.find((r) => r.caso === caso && r.impl === 'b2' && r.repeticion === 0);
  if (!base) continue;
  const mb = Buffer.from(base.pintura.mascara, 'base64');
  for (const r of salida.corridas.filter((x) => x.caso === caso && x.repeticion === 0 && x.impl !== 'b2')) {
    const mr = Buffer.from(r.pintura.mascara, 'base64');
    let inter = 0; let union = 0;
    for (let i = 0; i < mb.length; i += 1) {
      const a = mb[i]; const b = mr[i];
      for (let k = 0; k < 8; k += 1) { const x = (a >> k) & 1; const y = (b >> k) & 1; inter += x & y; union += x | y; }
    }
    salida.comparacionPintura.push({ caso, impl: r.impl, mismaVista: base.frio.zoom === r.frio.zoom,
      identicoAB2: base.pintura.sha256 === r.pintura.sha256, iou: +(inter / union).toFixed(4),
      pintadosB2: base.pintura.pintados, pintados: r.pintura.pintados });
  }
}

/* Summary table rows: median / worst over repetitions and actions. */
salida.resumen = [];
for (const caso of CASOS_ELEGIDOS) {
  for (const impl of IMPLS) {
    const rs = salida.corridas.filter((r) => r.caso === caso && r.impl === impl);
    if (!rs.length) continue;
    const vistas = rs.flatMap((r) => r.vistas);
    const sel = rs.flatMap((r) => r.seleccion);
    salida.resumen.push({
      caso, impl, n: rs.length,
      frioMs: [mediana(rs.map((r) => r.frio.hastaContornoMs)), peor(rs.map((r) => r.frio.hastaContornoMs))],
      frioPrimerCuadroMs: [mediana(rs.map((r) => r.frio.primerCuadroMs)), peor(rs.map((r) => r.frio.primerCuadroMs))],
      frioTareaMaxMs: peor(rs.map((r) => r.frio.tareaMaxMs)),
      vistaMs: [mediana(vistas.map((a) => a.ms)), peor(vistas.map((a) => a.ms)), vistas.length],
      vistaTareaMaxMs: peor(vistas.map((a) => a.tareaMaxMs)),
      contornoCompletoMs: [mediana(vistas.map((a) => a.contornoCompletoMs ?? a.ms)),
                           peor(vistas.map((a) => a.contornoCompletoMs ?? a.ms))],
      vistaTareasLargas: vistas.reduce((a, x) => a + x.tareasLargas, 0),
      entradaAPinturaMaxMs: peor([...vistas, ...sel].map((a) => a.eventoMaxMs ?? 0)),
      seleccionCorrecta: sel.every((s) => s.seleccionado === rs[0].seleccion.find((x) => x.que === s.que)?.seleccionado)
        && sel.every((s) => s.seleccionado !== null),
      seleccionTareaMaxMs: peor(sel.map((s) => s.tareaMaxMs)),
      seleccionMs: peor(sel.map((s) => s.msHastaOnSelect ?? Infinity)),
      cancelacionTareaMaxMs: peor(rs.map((r) => r.cancelacion.tareaMaxMs)),
      cancelacionLimpia: rs.every((r) => r.cancelacion.pendientes === 0 && !r.cancelacion.dibujadoTrasReinicio
                                       && r.cancelacion.estadosTrasReinicio === 0),
      desmontajeLimpio: rs.every((r) => r.desmontaje.pendientesDespues === 0 && r.errores.length === 0),
      heapMiB: peor(rs.map((r) => r.heapDespuesMiB)),
    });
  }
}
for (const caso of CASOS_ELEGIDOS) {
  const base = salida.corridas.find((r) => r.caso === caso && r.impl === 'b2' && r.repeticion === 0);
  if (!base) continue;
  for (const r of salida.corridas.filter((x) => x.caso === caso && x.repeticion === 0 && x.impl !== 'b2')) {
    const fila = salida.comparacionPintura.find((c) => c.caso === caso && c.impl === r.impl);
    const mb = Buffer.from(base.pinturaDetalle.mascara, 'base64');
    const mr = Buffer.from(r.pinturaDetalle.mascara, 'base64');
    let inter = 0; let union = 0;
    for (let i = 0; i < mb.length; i += 1) {
      for (let k = 0; k < 8; k += 1) { const x = (mb[i] >> k) & 1; const y = (mr[i] >> k) & 1; inter += x & y; union += x | y; }
    }
    fila.detalleIdentico = base.pinturaDetalle.sha256 === r.pinturaDetalle.sha256;
    fila.detalleIou = +(inter / union).toFixed(4);
  }
}
for (const r of salida.corridas) { delete r.pintura.mascara; delete r.pinturaDetalle.mascara; }
if (EVIDENCIA) writeFileSync(path.join(EVIDENCIA, 'banco.json'), JSON.stringify(salida, null, 1));
console.table(salida.resumen.map((x) => ({ ...x, frioMs: x.frioMs.join(' / '), frioPrimerCuadroMs: x.frioPrimerCuadroMs.join(' / '),
  vistaMs: x.vistaMs.map((v) => (typeof v === 'number' ? +v.toFixed(0) : v)).join(' / '),
  contornoCompletoMs: x.contornoCompletoMs.map((v) => +v.toFixed(0)).join(' / ') })));
console.table(salida.comparacionPintura);
await browser.close();
servidor.cerrar();

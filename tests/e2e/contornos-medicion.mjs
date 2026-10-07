/* B-2 measurements: the real renderer with mixed and parser-limit boundaries.
 *
 *   cd tests/e2e && npm install && node contornos-medicion.mjs [limit.json ...]
 *
 * Each case runs in a fresh page of contornos.html. Mixed sets are generated
 * in the page (fictional circles and points). Optional arguments are JSON
 * files {descriptor, cuerpo} produced by the accepted B-1 parser (see the B-2
 * report for the generator and provenance); they are served locally, never
 * committed.
 *
 * Per case: render() time, time to first paint, frame times while a REAL
 * mouse drag pans the map at outline zoom, click-to-select latency (real
 * mouse; the renderer's deliberate 280 ms double-click window is reported
 * separately), and JS heap after GC. Wall-clock figures are for this machine
 * only; they are evidence, not thresholds.
 *
 *   CHROMIUM=/path/to/chrome   CONTORNOS_EVIDENCIA=dir   as in contornos.mjs
 */

import { chromium } from 'playwright-core';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { opcionesNavegador, servir } from './servidor-estatico.mjs';

const EVIDENCIA = process.env.CONTORNOS_EVIDENCIA ?? null;
const limites = process.argv.slice(2).map((ruta) => ({
  nombre: path.basename(ruta, '.json'),
  json: readFileSync(ruta, 'utf8'),
}));
const extras = Object.fromEntries(limites.map(({ nombre, json }) =>
  [`/__medicion/${nombre}.json`, () => ({ tipo: 'application/json', cuerpo: json })]));
const servidor = await servir(extras);
const browser = await chromium.launch(opcionesNavegador());
if (EVIDENCIA) mkdirSync(EVIDENCIA, { recursive: true });

/* Mixed set: `n` boundaries (circles of `v` positions) and `n` XY points. */
const mixto = (n, v) => ({ tipo: 'mixto', n, v });
const CASOS = [
  { nombre: 'fixture-12-filas', fuente: { tipo: 'fixture' } },
  { nombre: 'mixto-100x64+100xy', fuente: mixto(100, 64) },
  { nombre: 'mixto-500x64+500xy', fuente: mixto(500, 64) },
  { nombre: 'mixto-2000x64+2000xy', fuente: mixto(2000, 64) },
  { nombre: 'mixto-500x1000+500xy', fuente: mixto(500, 1000) },
  ...limites.map(({ nombre }) => ({ nombre: `limite-${nombre}`, fuente: { tipo: 'limite', nombre } })),
];

async function medir({ nombre, fuente }) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 } });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const heap = async () => {
    await cdp.send('HeapProfiler.collectGarbage');
    const { metrics } = await cdp.send('Performance.getMetrics');
    return metrics.find((m) => m.name === 'JSHeapUsedSize').value / 2 ** 20;
  };
  await page.goto(`${servidor.url}/tests/e2e/contornos.html`);
  await page.waitForFunction(() => document.title === 'listo');

  // Prepare rows and bodies in the page, outside the timed section.
  const preparado = await page.evaluate(async (f) => {
    const h = window.__harness;
    h.render([]);
    let filas = [];
    let geometrias = new Map();
    if (f.tipo === 'fixture') {
      filas = h.fixture.filas;
      geometrias = h.geometrias;
    } else if (f.tipo === 'mixto') {
      for (let i = 0; i < f.n; i += 1) {
        const lon0 = -100.6 + (i % 50) * 0.01;
        const lat0 = 20.4 + Math.floor(i / 50) * 0.01;
        const r = 0.003;
        const anillo = Array.from({ length: f.v - 1 }, (_, k) => [
          lon0 + r * Math.cos((2 * Math.PI * k) / (f.v - 1)),
          lat0 + r * Math.sin((2 * Math.PI * k) / (f.v - 1))]);
        anillo.push([...anillo[0]]);
        const bbox = [lon0 - r, lat0 - r, lon0 + r, lat0 + r];
        const punto = { type: 'Point', coordinates: [lon0, lat0] };
        const id = `g-${i}`;
        geometrias.set(id, { geojson: { type: 'MultiPolygon', coordinates: [[anillo]] },
                             bbox, punto_interior: punto, partes: 1, huecos: 0, vertices: f.v });
        filas.push({ id: `c-${i}`, terreno: `Contorno ficticio ${i}`, lat: null, lon: null,
                     geometria: { id, archivo_version_id: `v-${i}`, utilizable: true, bbox,
                                  punto_interior: punto } });
        filas.push({ id: `p-${i}`, terreno: `Punto ficticio ${i}`, lat: lat0 + 0.004,
                     lon: lon0 + 0.004, superficie_m2: 20000, geometria: null });
      }
    } else {
      const datos = await (await fetch(`/__medicion/${f.nombre}.json`)).json();
      geometrias.set(datos.descriptor.id, datos.cuerpo);
      filas = [{ id: 'grande', terreno: 'Contorno ficticio al límite', lat: null, lon: null,
                 geometria: datos.descriptor },
               { id: 'xy', terreno: 'Punto ficticio', lat: datos.descriptor.bbox[1] - 0.002,
                 lon: datos.descriptor.bbox[0] - 0.002, superficie_m2: 5000, geometria: null }];
    }
    h.datosMedicion = { filas, geometrias };
    return { filas: filas.length, posiciones: [...geometrias.values()]
      .reduce((a, c) => a + (c.vertices ?? 0), 0) };
  }, fuente);
  const heapAntes = await heap();

  // Render + fit, then the first paint.
  const tiempos = await page.evaluate(() => new Promise((ok) => {
    const h = window.__harness;
    const { filas, geometrias } = h.datosMedicion;
    const t0 = performance.now();
    const colocados = h.canvas.render(filas, { colorFor: () => '#2a78d6', geometrias });
    h.canvas.fitTo(filas);
    const t1 = performance.now();
    requestAnimationFrame(() => requestAnimationFrame(() =>
      ok({ colocados, renderMs: t1 - t0, primerPintadoMs: performance.now() - t0 })));
  }));

  // Let fitTo's own (animated) move finish before timing anything else.
  await page.evaluate(() => new Promise((ok) => {
    const mapa = window.__harness.canvas.map;
    let hecho = false;
    const fin = () => { if (!hecho) { hecho = true; requestAnimationFrame(() => ok()); } };
    mapa.once('moveend', fin);
    setTimeout(fin, 1500);
  }));

  // Frame to an outline: select the first boundary (fitBounds to it).
  const objetivo = await page.evaluate(() => window.__harness.datosMedicion.filas
    .find((t) => t.geometria)?.id ?? null);
  const enfoque = await page.evaluate((id) => new Promise((ok) => {
    const h = window.__harness;
    const t0 = performance.now();
    h.canvas.map.once('moveend', () => requestAnimationFrame(() => requestAnimationFrame(() =>
      ok({ ms: performance.now() - t0, zoom: h.canvas.map.getZoom(),
           contorno: h.canvas.posicionDe(id)?.contorno ?? null }))));
    h.canvas.select(id, { pan: true });
  }), objetivo);

  // Direct redraw cost at this view: a 200 px pan and a one-level zoom, both
  // without animation, each timed to the second frame after it.
  const redibujo = await page.evaluate(async () => {
    const mapa = window.__harness.canvas.map;
    const dosCuadros = () => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    let t0 = performance.now();
    mapa.panBy([200, 0], { animate: false });
    await dosCuadros();
    const panMs = performance.now() - t0;
    mapa.panBy([-200, 0], { animate: false });
    await dosCuadros();
    t0 = performance.now();
    mapa.setZoom(mapa.getZoom() + 1, { animate: false });
    await dosCuadros();
    const zoomMs = performance.now() - t0;
    mapa.setZoom(mapa.getZoom() - 1, { animate: false });
    await dosCuadros();
    return { panMs, zoomMs };
  });

  // zoomToScale on the same terrain (outline zoom for a boundary), then the
  // same redraw timings there -- where every ring is projected and drawn.
  const escala = await page.evaluate(async (id) => {
    const h = window.__harness;
    const mapa = h.canvas.map;
    const dosCuadros = () => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    let t0 = performance.now();
    const resultado = h.canvas.zoomToScale(id);
    await dosCuadros();
    const ms = performance.now() - t0;
    t0 = performance.now();
    mapa.panBy([200, 0], { animate: false });
    await dosCuadros();
    const panMs = performance.now() - t0;
    t0 = performance.now();
    mapa.setZoom(mapa.getZoom() + 1, { animate: false });
    await dosCuadros();
    const zoomMs = performance.now() - t0;
    mapa.setZoom(mapa.getZoom() - 1, { animate: false });
    await dosCuadros();
    return { estado: resultado.estado, zoom: mapa.getZoom(),
             contorno: h.canvas.posicionDe(id)?.contorno ?? null, ms, panMs, zoomMs };
  }, objetivo);

  // Real mouse drag across the map; record every frame duration meanwhile.
  await page.evaluate(() => {
    const marcas = [];
    window.__frames = marcas;
    const ciclo = (t) => { marcas.push(t); if (window.__frames === marcas) requestAnimationFrame(ciclo); };
    requestAnimationFrame(ciclo);
  });
  await page.mouse.move(700, 300);
  await page.mouse.down();
  for (let k = 1; k <= 30; k += 1) await page.mouse.move(700 - k * 12, 300 + k * 4);
  await page.mouse.up();
  await page.waitForTimeout(300);
  const marco = await page.evaluate(() => {
    const t = window.__frames;
    window.__frames = null;
    const d = t.slice(1).map((v, i) => v - t[i]).sort((a, b) => a - b);
    return { cuadros: d.length, p50: d[Math.floor(d.length * 0.5)] ?? null,
             p95: d[Math.floor(d.length * 0.95)] ?? null, max: d.at(-1) ?? null };
  });

  // Click-to-select with a real mouse click on the terrain's clickable point.
  await page.evaluate((id) => new Promise((ok) => {
    const h = window.__harness;
    h.canvas.map.once('moveend', () => requestAnimationFrame(ok));
    h.canvas.select(null);
    h.canvas.select(id, { pan: true });
    setTimeout(ok, 10000);                 // slow redraws can delay moveend
  }), objetivo);
  const p = await page.evaluate((id) => window.__harness.canvas.posicionDe(id), objetivo);
  await page.evaluate(() => {
    window.__clic = null;
    document.getElementById('mapa').addEventListener('mousedown',
      () => { window.__clic = performance.now(); }, { capture: true, once: true });
    window.__harness.selecciones.length = 0;
    const original = window.__harness.canvas;
    window.__seleccionEn = null;
    const intervalo = setInterval(() => {
      if (window.__harness.selecciones.length && window.__seleccionEn === null) {
        window.__seleccionEn = performance.now();
        clearInterval(intervalo);
      }
    }, 1);
    return Boolean(original);
  });
  await page.mouse.click(p.x, p.y);
  // Poll: a body that redraws slowly also selects slowly (up to 6 s).
  await page.waitForFunction(() => window.__seleccionEn !== null, null, { timeout: 6000 })
    .catch(() => {});
  const clic = await page.evaluate(() => ({
    seleccionado: window.__harness.selecciones[0] ?? null,
    msHastaSeleccion: window.__seleccionEn !== null && window.__clic !== null
      ? window.__seleccionEn - window.__clic : null,
  }));

  const heapDespues = await heap();
  if (EVIDENCIA) await page.screenshot({ path: path.join(EVIDENCIA, `medicion-${nombre}.png`) });
  await page.close();
  return {
    caso: nombre, ...preparado, ...tiempos,
    enfoqueMs: enfoque.ms, zoomEnfoque: enfoque.zoom, contornoVisible: enfoque.contorno,
    redibujo, escala,
    arrastre: marco,
    clic: { ...clic, ventanaDobleClicMs: 280,
            msSinVentana: clic.msHastaSeleccion === null ? null : clic.msHastaSeleccion - 280 },
    heapMiB: { antes: +heapAntes.toFixed(1), despues: +heapDespues.toFixed(1) },
  };
}

const resultados = { navegador: browser.version(), casos: [] };
console.log(`Chromium ${browser.version()}`);
for (const caso of CASOS) {
  const r = await medir(caso);
  resultados.casos.push(r);
  console.log(JSON.stringify(r));
}
if (EVIDENCIA) writeFileSync(path.join(EVIDENCIA, 'medicion.json'), JSON.stringify(resultados, null, 1));
await browser.close();
servidor.cerrar();

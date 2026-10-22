/* F3 correction, browser evidence (supervisory review of PR #16): worker
 * copies of prepared bodies through the REAL module worker, plus measured
 * bitmap memory with several heavy outlines at DPR 1 and 2.
 *
 *   B2_DIR=... CASOS_DIR=... CHROMIUM=... node reports/team-b-display-strategy-2026-10-08/memoria-trabajador.mjs
 *
 * 1. Module level (cache + client + worker, as the supervisor's probe):
 *    a. 45 visits of 60,000-position bodies, each pinned while "on the map",
 *       then released; the main cache's evictions reach the worker.
 *    b. Revisit of the first (evicted) body: sent again and rasterized.
 *    c. The probe's pattern: 45 bodies pinned and never released.
 *    d. Reset (acknowledged) and teardown (terminated).
 *    Worker-held bytes come from the worker itself ("estadisticas"); the
 *    client's count includes copies still queued.
 * 2. Map level (E4 renderer): N heavy outlines visible at once; measured
 *    worker bytes, main cache bytes and bitmap bytes (width x height x 4 of
 *    the bitmaps layers hold), at DPR 1 and 2.
 */

import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const servidor = await servir({ b2: process.env.B2_DIR, casos: process.env.CASOS_DIR });
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const salida = { navegador: browser.version() };

async function pagina(dpr = 1) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 }, deviceScaleFactor: dpr });
  page.on('pageerror', (e) => { throw e; });
  await page.goto(`${servidor.url}/proto/banco.html?impl=e4`);
  await page.waitForFunction(() => document.title === 'listo');
  return page;
}

// 1. Module level.
{
  const page = await pagina();
  salida.modulo = await page.evaluate(async () => {
    const { crearClienteRaster, PRESUPUESTO_TRABAJADOR_BYTES } = await import('/proto/prototipo/raster.js');
    const { crearCache, PRESUPUESTO_CACHE_BYTES } = await import('/proto/prototipo/planificador.js');
    const sintetico = (n) => ({ estado: 'cargado', x: new Float64Array(n), y: new Float64Array(n),
      inicioAnillo: new Int32Array([0, n]), inicioParte: new Int32Array([0, 1]), cajasParte: new Float64Array(4), partes: 1 });
    const AREA = { escala: 1, x0: 0, y0: 0, ancho: 64, alto: 64, dpr: 1,
                   estilos: [{ fill: true, fillOpacity: 0.2, color: '#000', stroke: true, weight: 2, opacity: 1, lineCap: 'round', lineJoin: 'round' }] };
    const tarea = () => new Promise((ok) => setTimeout(ok, 0));
    const montar = () => {
      const cliente = crearClienteRaster();
      const cache = crearCache(PRESUPUESTO_CACHE_BYTES, { alExpulsar: (id) => cliente.expulsado(id) });
      return { cliente, cache };
    };
    const raster = (cliente, id) => new Promise((ok) => cliente.pedir({ id, ...AREA }, ok));
    const r = { presupuestoTrabajador: PRESUPUESTO_TRABAJADOR_BYTES, presupuestoCache: PRESUPUESTO_CACHE_BYTES };

    // a + b. Visits, then a revisit after eviction.
    {
      const { cliente, cache } = montar();
      let peorContado = 0;
      for (let i = 0; i < 45; i += 1) {
        const id = `cuerpo-${i}`;
        const p = sintetico(60_000);
        cache.guardar({ id, bbox: [0, 0, 1, 1] }, p);
        const estado = cliente.asegurar(id, p, { enCache: cache.contiene(id) });
        peorContado = Math.max(peorContado, cliente.bytesTrabajador);
        const respuesta = await raster(cliente, id);
        if (estado === 'rechazado' || respuesta.sinCuerpo || respuesta.bitmaps.length !== 1) throw new Error(`visit ${i}: ${estado}`);
        cliente.soltarBitmaps(respuesta.bitmaps);
        cliente.liberar(id);
        peorContado = Math.max(peorContado, cliente.bytesTrabajador);
      }
      for (let i = 0; i < 10; i += 1) await tarea();
      const w = await cliente.estadisticas();
      r.visitas = { mainBytes: cache.bytes, mainEntradas: cache.tamano, trabajadorBytes: w.bytes, trabajadorEntradas: w.entradas,
                    totalBytes: cache.bytes + w.bytes, clienteContadoMaxBytes: peorContado,
                    copiasEnviadas: cliente.metricas.copiasEnviadas, esperas: cliente.metricas.esperas,
                    bitmapsRetenidos: cliente.metricas.bitmapsBytes };
      const antes = cliente.metricas.copiasEnviadas;
      const p0 = sintetico(60_000);
      cache.guardar({ id: 'cuerpo-0', bbox: [0, 0, 1, 1] }, p0);
      const estado = cliente.asegurar('cuerpo-0', p0, { enCache: cache.contiene('cuerpo-0') });
      const respuesta = await raster(cliente, 'cuerpo-0');
      r.revisita = { estado, reenviado: cliente.metricas.copiasEnviadas === antes + 1,
                     dibujado: respuesta.bitmaps.length === 1 && !respuesta.sinCuerpo };
      cliente.soltarBitmaps(respuesta.bitmaps);
      cliente.liberar('cuerpo-0');
      // d. Reset and teardown.
      const contadoAntes = cliente.bytesTrabajador;
      const confirmado = await cliente.olvidarTodo();
      const w2 = await cliente.estadisticas();
      r.reinicio = { contadoAntesDeConfirmar: contadoAntes, confirmado, trabajadorBytes: w2.bytes,
                     trabajadorEntradas: w2.entradas, contadoDespues: cliente.bytesTrabajador };
      cliente.cerrar();
      r.desmontaje = { cerrado: cliente.cerrado, contado: cliente.bytesTrabajador,
                       estadisticasTrasCerrar: await cliente.estadisticas(),
                       asegurarTrasCerrar: cliente.asegurar('x', sintetico(10)) };
    }
    // c. The probe's pattern: pinned and never released.
    {
      const cliente = crearClienteRaster();
      const cache = crearCache();
      const estados = {};
      for (let i = 0; i < 45; i += 1) {
        const p = sintetico(60_000);
        cache.guardar({ id: `fijo-${i}`, bbox: [0, 0, 1, 1] }, p);
        const e = cliente.asegurar(`fijo-${i}`, p);
        estados[e] = (estados[e] ?? 0) + 1;
      }
      for (let i = 0; i < 10; i += 1) await tarea();
      const w = await cliente.estadisticas();
      r.fijados = { estados, mainBytes: cache.bytes, trabajadorBytes: w.bytes, trabajadorEntradas: w.entradas,
                    totalBytes: cache.bytes + w.bytes };
      cliente.cerrar();
    }
    return r;
  });
  await page.close();
  console.log('MODULO', JSON.stringify(salida.modulo, null, 1));
}

// 2. Map level: several heavy outlines visible at once, DPR 1 and 2.
salida.mapa = [];
for (const dpr of [1, 2]) {
  for (const n of [1, 3, 6]) {
    const page = await pagina(dpr);
    const r = await page.evaluate(async (n) => {
      const b = window.__banco;
      const geometrias = new Map();
      const filas = [];
      for (let i = 0; i < n; i += 1) {
        const m = 30_000;                       // > 20,000 visible positions: heavy
        const lon0 = -100.5 + (i % 3) * 0.03; const lat0 = 20.6 + Math.floor(i / 3) * 0.03; const rad = 0.012;
        const anillo = Array.from({ length: m - 1 }, (_, k) => [lon0 + rad * Math.cos((2 * Math.PI * k) / (m - 1)),
                                                               lat0 + rad * Math.sin((2 * Math.PI * k) / (m - 1))]);
        anillo.push([...anillo[0]]);
        const bbox = [lon0 - rad, lat0 - rad, lon0 + rad, lat0 + rad];
        const punto = { type: 'Point', coordinates: [lon0, lat0] };
        geometrias.set(`g-${i}`, { geojson: { type: 'MultiPolygon', coordinates: [[anillo]] }, bbox, punto_interior: punto });
        filas.push({ id: `t-${i}`, terreno: `Contorno ${i}`, lat: null, lon: null,
                     geometria: { id: `g-${i}`, archivo_version_id: `v${i}`, utilizable: true, bbox, punto_interior: punto } });
      }
      b.canvas.render(filas, { colorFor: b.colorFor, geometrias });
      const pendiente = () => filas.some((f) => ['preparando', 'dibujando'].includes(b.canvas.posicionDe(f.id)?.estadoContorno));
      const fin = performance.now() + 30000;
      while (pendiente() && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 10));
      b.canvas.map.fitBounds([[20.58, -100.52], [20.6 + 0.03 * Math.ceil(n / 3) + 0.02, -100.5 + 0.03 * 3]], { animate: false });
      await new Promise((ok) => setTimeout(ok, 50));
      while (pendiente() && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 10));
      await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
      const d = b.canvas._diagnostico;
      const w = await d.raster.estadisticas();
      const estados = filas.map((f) => b.canvas.posicionDe(f.id)?.estadoContorno);
      const lienzo = document.querySelector('.leaflet-overlay-pane canvas');
      return { n, estados, zoom: b.canvas.map.getZoom(), lienzo: `${lienzo.width}x${lienzo.height}`,
               cacheBytes: d.cache.bytes, trabajadorBytes: w.bytes, bitmapsBytes: d.raster.metricas.bitmapsBytes,
               bitmapsBytesMax: d.raster.metricas.bitmapsBytesMax, enVueloMax: d.raster.metricas.enVueloMax,
               descartados: d.raster.metricas.descartados, cancelados: d.raster.metricas.cancelados };
    }, n);
    r.dpr = dpr;
    r.totalBytes = r.cacheBytes + r.trabajadorBytes + r.bitmapsBytes;
    salida.mapa.push(r);
    console.log('MAPA', JSON.stringify(r));
    await page.close();
  }
}
if (process.env.SALIDA_JSON) writeFileSync(process.env.SALIDA_JSON, JSON.stringify(salida, null, 1));
await browser.close();
servidor.cerrar();

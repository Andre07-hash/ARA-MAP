/* Behaviour checks for a prototype strategy (default e4) in a real Chromium
 * with real pointer input. Same environment variables as banco.mjs.
 *
 *   node reports/team-b-display-strategy-2026-10-08/comprobaciones.mjs [e4|e3]
 */

import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const impl = process.argv[2] ?? 'e4';
const servidor = await servir({ b2: process.env.B2_DIR, casos: process.env.CASOS_DIR });
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const fallos = [];
const ok = (cond, que) => { console.log(`${cond ? 'OK   ' : 'FALLA'} ${que}`); if (!cond) fallos.push(que); };

async function pagina(extra = '') {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 } });
  page.on('pageerror', (e) => fallos.push(`pageerror: ${e}`));
  await page.goto(`${servidor.url}/proto/banco.html?impl=${impl}${extra}`);
  await page.waitForFunction(() => document.title === 'listo');
  await page.evaluate(() => {
    window.__dos = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    window.__esperar = async (id, fuera) => {
      const fin = performance.now() + 20000;
      while (fuera.includes(window.__banco.canvas.posicionDe(id)?.estadoContorno) && performance.now() < fin) {
        await new Promise((r) => setTimeout(r, 5));
      }
      await window.__dos();
    };
  });
  return page;
}

const clic = async (page, x, y) => {
  await page.evaluate(() => { window.__banco.selecciones.length = 0; window.__banco.canvas.select(null); });
  await page.evaluate(() => window.__dos());
  await page.mouse.click(x, y);
  await page.waitForTimeout(450);
  return page.evaluate(() => window.__banco.selecciones[0]?.id ?? null);
};

// 1. Fixture: hole, multipart, XY, missing body.
{
  const page = await pagina();
  const p = await page.evaluate(async () => {
    const b = window.__banco;
    b.d = await b.cargarFixture();
    b.canvas.render(b.d.filas, { colorFor: b.colorFor, geometrias: b.d.geometrias });
    for (const t of b.d.filas) if (t.geometria) await window.__esperar(t.id, ['preparando', 'dibujando']);
    const mapa = b.canvas.map;
    b.canvas.zoomToScale('t-hueco');
    await window.__esperar('t-hueco', ['dibujando']);
    const c = b.d.geometrias.get('geo-hueco').geojson.coordinates[0];
    const hueco = c[1].slice(0, -1);
    const enHueco = mapa.latLngToContainerPoint([hueco.reduce((a, q) => a + q[1], 0) / 4, hueco.reduce((a, q) => a + q[0], 0) / 4]);
    const enRelleno = mapa.latLngToContainerPoint([c[0][0][1] + 0.0004, c[0][0][0] + 0.0004]);
    return { enHueco, enRelleno };
  });
  ok(await clic(page, p.enHueco.x, p.enHueco.y) === null, 'click inside a hole selects nothing');
  ok(await clic(page, p.enRelleno.x, p.enRelleno.y) === 't-hueco', 'click on the filled area selects the terrain');
  const partes = await page.evaluate(async () => {
    const b = window.__banco;
    b.canvas.zoomToScale('t-multiparte');
    await window.__esperar('t-multiparte', ['dibujando']);
    return b.d.geometrias.get('geo-multiparte').geojson.coordinates.map((parte) => {
      const r = parte[0].slice(0, -1);
      return b.canvas.map.latLngToContainerPoint([r.reduce((a, q) => a + q[1], 0) / r.length, r.reduce((a, q) => a + q[0], 0) / r.length]);
    });
  });
  for (const [i, q] of partes.entries()) ok(await clic(page, q.x, q.y) === 't-multiparte', `multipart part ${i + 1} selects the same terrain ID`);
  const sin = await page.evaluate(() => { const b = window.__banco; return { z: b.canvas.zoomToScale('t-sin-cuerpo'),
    p: b.canvas.posicionDe('t-sin-cuerpo'), aviso: b.canvas._diagnostico.aviso('t-sin-cuerpo') }; });
  ok(sin.z.estado === 'contorno_no_disponible' && !sin.p.contorno, 'missing body: contorno_no_disponible, no outline');
  ok(sin.aviso.includes('Contorno no disponible'), 'missing body wording: "Contorno no disponible"');
  await page.close();
}

// 2. Large body: pending states, wording, selection retained, no claim of scale.
{
  const page = await pagina();
  const r = await page.evaluate(async () => {
    const b = window.__banco;
    b.d = await b.cargar('grande-mas-19999');
    b.estados.length = 0;
    // Test-only control of the asynchronous boundary (review: the wording
    // check raced the preparation). Preparation slices are scheduled with
    // scheduler.postTask; they are held while the pending state is inspected
    // and released afterwards. Renderer code and timing are unchanged.
    const real = scheduler.postTask.bind(scheduler);
    const retenidas = [];
    scheduler.postTask = (fn, o) => { retenidas.push([fn, o]); return Promise.resolve(); };
    const leer = () => ({ estado: b.canvas.posicionDe('contorno')?.estadoContorno ?? null,
                          contorno: b.canvas.posicionDe('contorno')?.contorno ?? null,
                          aviso: b.canvas._diagnostico.aviso('contorno') });
    b.canvas.render(b.d.filas, { colorFor: b.colorFor, geometrias: b.d.geometrias });
    const inicial = leer();
    const z = b.canvas.zoomToScale('contorno');
    b.canvas.select('contorno');
    await window.__dos();
    await new Promise((ok) => setTimeout(ok, 50));
    const retenido = { ...leer(), tareasRetenidas: retenidas.length };
    delete scheduler.postTask;                     // back to the browser's own
    for (const [fn, o] of retenidas.splice(0)) real(fn, o);
    // Without any hold: state and wording read together, in separate tasks,
    // until preparation ends; each pair must agree.
    const pares = [];
    for (let i = 0; i < 2000 && leer().estado === 'preparando'; i += 1) {
      pares.push(leer());
      await new Promise((ok) => setTimeout(ok, 1));
    }
    pares.push(leer());
    return { inicial, z, retenido, pares };
  });
  const VERBO = { preparando: 'Preparando contorno…', dibujando: 'Dibujando contorno…' };
  ok(r.inicial.estado === 'preparando' && !r.inicial.contorno,
     `large body starts "preparando", no outline claimed (${JSON.stringify(r.inicial)})`);
  ok(r.z.estado === 'contorno_pendiente', `zoomToScale while preparing returns contorno_pendiente (${r.z.estado})`);
  ok(r.retenido.estado === 'preparando' && r.retenido.aviso?.includes('Preparando contorno…') && !r.retenido.contorno,
     `pending wording while preparation is held: "Preparando contorno…" (${JSON.stringify(r.retenido)})`);
  const desacuerdos = r.pares.filter((x) => (VERBO[x.estado] ? !x.aviso?.includes(VERBO[x.estado])
    : /Preparando|Dibujando|Cargando/.test(x.aviso ?? '')));
  ok(desacuerdos.length === 0,
     `state and wording agree in every sample (${r.pares.length} samples; mismatches ${JSON.stringify(desacuerdos.slice(0, 3))})`);
  const fin = await page.evaluate(async () => {
    const b = window.__banco;
    await window.__esperar('contorno', ['preparando']);
    const z = b.canvas.zoomToScale('contorno');
    await window.__esperar('contorno', ['dibujando']);
    const z2 = b.canvas.zoomToScale('contorno');
    await window.__dos();
    // Selection kept: the selected (black) outline style is painted.
    const lienzo = document.querySelector('.leaflet-overlay-pane canvas');
    const { data } = lienzo.getContext('2d').getImageData(0, 0, lienzo.width, lienzo.height);
    let negros = 0;
    for (let i = 0; i < data.length; i += 4) if (data[i + 3] > 200 && data[i] < 40 && data[i + 1] < 40 && data[i + 2] < 40) negros += 1;
    return { z, z2, p: b.canvas.posicionDe('contorno'), estados: b.estados.map((e) => e.estado), negros };
  });
  ok(fin.p.contorno && fin.p.estadoContorno === 'listo' && fin.z2.estado === 'a_escala', 'after preparation: outline drawn, a_escala');
  ok(fin.estados[0] === 'preparando' && fin.estados.at(-1) === 'listo', `state sequence ${fin.estados.join(' → ')}`);
  ok(fin.negros > 1000, `selection retained across preparation (${fin.negros} selected-outline pixels)`);
  if (impl === 'e4') {
    // A zoom change asks the worker for a new raster: "dibujando" at once,
    // no outline claimed, then the exact outline again.
    const d = await page.evaluate(async () => {
      const b = window.__banco;
      const m = b.canvas.map;
      m.setZoom(m.getZoom() + 1, { animate: false });
      await new Promise((r) => queueMicrotask(r));
      const durante = { p: b.canvas.posicionDe('contorno'), aviso: b.canvas._diagnostico.aviso('contorno') };
      // zoomToScale returns to the outline view: its result must match what is painted there.
      durante.z = b.canvas.zoomToScale('contorno');
      durante.pTrasZoom = b.canvas.posicionDe('contorno');
      await window.__esperar('contorno', ['dibujando']);
      return { durante, despues: b.canvas.posicionDe('contorno') };
    });
    ok(d.durante.p.estadoContorno === 'dibujando' && !d.durante.p.contorno,
       'E4 zoom: "dibujando" at once, no outline claimed');
    ok(d.durante.z.estado === 'a_escala' ? d.durante.pTrasZoom.contorno === true
       : d.durante.z.estado === 'contorno_pendiente' && d.durante.z.motivo === 'dibujando' && !d.durante.pTrasZoom.contorno,
       `E4 zoomToScale agrees with what is painted (${d.durante.z.estado})`);
    ok(d.durante.aviso.includes('Dibujando contorno…'), 'E4 wording: "Dibujando contorno…"');
    ok(d.despues.contorno && d.despues.estadoContorno === 'listo', 'E4: exact outline completes after drawing');
  }
  await page.close();
}

// 3. Invalid body, loading body, stale results after a newer render.
{
  const page = await pagina();
  const r = await page.evaluate(async () => {
    const b = window.__banco;
    const d = await b.cargar('circulo-100k');
    const malo = structuredClone(d.geometrias.get(d.descriptor.id));
    malo.geojson.coordinates[0][0][10][0] += 2;            // F1: outside its own bbox
    b.estados.length = 0;
    b.canvas.render(d.filas, { colorFor: b.colorFor, geometrias: new Map([[d.descriptor.id, malo]]) });
    await window.__esperar('contorno', ['preparando']);
    const invalido = { p: b.canvas.posicionDe('contorno'), z: b.canvas.zoomToScale('contorno'),
                       aviso: b.canvas._diagnostico.aviso('contorno') };
    await window.__dos();
    invalido.punto = b.canvas.posicionDe('contorno');
    b.canvas.render(d.filas, { colorFor: b.colorFor, geometrias: new Map(), cargando: new Set([d.descriptor.id]) });
    const cargando = { p: b.canvas.posicionDe('contorno'), z: b.canvas.zoomToScale('contorno'),
                       aviso: b.canvas._diagnostico.aviso('contorno') };
    // Stale: start preparing A, then render something else before it finishes.
    const a = await b.cargar('denso-grande-mas-19999');
    const fx = await b.cargarFixture();
    b.estados.length = 0;
    b.canvas.render(a.filas, { colorFor: b.colorFor, geometrias: a.geometrias });
    // One macrotask yield: at least one ≤ 8 ms slice of A may run, but not the
    // ~150 ms of work A needs, so A is mid-preparation when the newer render comes.
    await new Promise((ok) => setTimeout(ok, 0));
    const aunPreparando = b.canvas.posicionDe('contorno')?.estadoContorno === 'preparando';
    const t = performance.now();                     // the newer render starts here
    b.canvas.render(fx.filas, { colorFor: b.colorFor, geometrias: fx.geometrias });
    await new Promise((ok) => setTimeout(ok, 1500));
    const tarde = b.estados.filter((e) => e.t > t && e.id === 'contorno');
    return { invalido, cargando, aunPreparando, tarde: tarde.map((e) => e.estado), pend: b.canvas._diagnostico.planificador.pendientes,
             dibujado: b.canvas.posicionDe('contorno') };
  });
  ok(r.invalido.p.estadoContorno === 'invalido' && !r.invalido.p.contorno && r.invalido.z.estado === 'contorno_no_disponible',
     'inconsistent body (F1): "invalido", never drawn, contorno_no_disponible');
  ok(r.invalido.aviso.includes('Contorno no válido'), 'inconsistent body wording: "Contorno no válido"');
  ok(r.cargando.p.estadoContorno === 'cargando' && r.cargando.z.estado === 'contorno_pendiente',
     'caller-loading body: "cargando", contorno_pendiente');
  ok(r.cargando.aviso.includes('Cargando contorno…'), 'caller-loading wording: "Cargando contorno…"');
  ok(r.aunPreparando && r.tarde.length === 0 && r.pend === 0 && r.dibujado === null,
     `a newer render cancels older preparation; no late outline (${JSON.stringify({ tarde: r.tarde, pend: r.pend, dibujado: r.dibujado })})`);
  await page.close();
}

// 4. F3: when the worker budget is held by other outlines on the map, the
// outline is "sin_memoria": explicit, located, not pending, not drawn.
if (impl === 'e4') {
  const page = await pagina('&presupuesto=1100000');    // two 30,000-position bodies (480 KB each)
  const r = await page.evaluate(async () => {
    const b = window.__banco;
    const geometrias = new Map();
    const filas = [];
    for (let i = 0; i < 3; i += 1) {
      const m = 30_000; const lon0 = -100.5 + i * 0.03; const lat0 = 20.6; const rad = 0.012;
      const anillo = Array.from({ length: m - 1 }, (_, k) => [lon0 + rad * Math.cos((2 * Math.PI * k) / (m - 1)),
                                                             lat0 + rad * Math.sin((2 * Math.PI * k) / (m - 1))]);
      anillo.push([...anillo[0]]);
      const bbox = [lon0 - rad, lat0 - rad, lon0 + rad, lat0 + rad];
      const punto = { type: 'Point', coordinates: [lon0, lat0] };
      geometrias.set(`g-${i}`, { geojson: { type: 'MultiPolygon', coordinates: [[anillo]] }, bbox, punto_interior: punto });
      filas.push({ id: `t-${i}`, terreno: `Contorno ${i}`, lat: null, lon: null,
                   geometria: { id: `g-${i}`, archivo_version_id: `v${i}`, utilizable: true, bbox, punto_interior: punto } });
    }
    const leer = (id) => ({ estado: b.canvas.posicionDe(id)?.estadoContorno, contorno: b.canvas.posicionDe(id)?.contorno,
                            aviso: b.canvas._diagnostico.aviso(id) });
    const asentar = async () => {
      const fin = performance.now() + 20000;
      while (filas.some((f) => ['preparando', 'dibujando'].includes(b.canvas.posicionDe(f.id)?.estadoContorno))
             && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 10));
      await window.__dos();
    };
    b.canvas.render(filas, { colorFor: b.colorFor, geometrias });
    await asentar();
    b.canvas.map.fitBounds([[20.585, -100.515], [20.615, -100.425]], { animate: false });
    await asentar();
    const estados = filas.map((f) => leer(f.id));
    const negado = filas.find((f) => b.canvas.posicionDe(f.id)?.estadoContorno === 'sin_memoria');
    const z = negado ? b.canvas.zoomToScale(negado.id) : null;
    await window.__dos();
    const trasZoom = negado ? leer(negado.id) : null;
    // Release the others (filter change): the refused outline can now be drawn.
    if (negado) b.canvas.render([negado], { colorFor: b.colorFor, geometrias });
    if (negado) b.canvas.zoomToScale(negado.id);
    const fin = performance.now() + 20000;
    while (negado && b.canvas.posicionDe(negado.id)?.estadoContorno !== 'listo' && performance.now() < fin) {
      b.canvas.map.panBy([1, 0], { animate: false });     // a redraw asks again
      await new Promise((ok) => setTimeout(ok, 50));
    }
    const despues = negado ? leer(negado.id) : null;
    const w = await b.canvas._diagnostico.raster.estadisticas();
    return { estados, z, trasZoom, despues, trabajadorBytes: w.bytes, presupuesto: b.canvas._diagnostico.raster.presupuesto };
  });
  const n = r.estados.filter((e) => e.estado === 'sin_memoria').length;
  ok(n === 1 && r.estados.filter((e) => e.estado === 'listo' && e.contorno).length === 2,
     `worker budget for two: two outlines drawn, one "sin_memoria" (${JSON.stringify(r.estados.map((e) => e.estado))})`);
  ok(r.z?.estado === 'contorno_no_disponible' && r.z?.motivo === 'sin_memoria' && !r.trasZoom?.contorno,
     `refused outline: zoomToScale contorno_no_disponible (sin_memoria), nothing claimed (${JSON.stringify(r.z)})`);
  ok(r.trasZoom?.aviso?.includes('Contorno no disponible: demasiados contornos a la vez'),
     `refused outline wording (${JSON.stringify(r.trasZoom?.aviso)})`);
  ok(r.despues?.estado === 'listo' && r.despues?.contorno && r.trabajadorBytes <= r.presupuesto,
     `after the others leave, the refused outline is drawn; worker ${r.trabajadorBytes} B <= ${r.presupuesto} B`);
  await page.close();
}

await browser.close();
servidor.cerrar();
console.log(fallos.length ? `${fallos.length} fallo(s)` : 'Todas las comprobaciones pasaron');
process.exit(fallos.length ? 1 : 0);

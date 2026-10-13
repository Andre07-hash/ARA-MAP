/* E1 timing: the accepted B-2 MapCanvas against the branch's, same page,
 * same rows, in fresh pages. Evidence for the recorded machine only; no
 * thresholds are asserted (CI does not run this).
 *
 *   cd tests/e2e && npm install && node contornos-trazo-medicion.mjs [limit.json ...]
 *
 *   CHROMIUM, MAPA_BASE, CONTORNOS_EVIDENCIA   as in contornos-trazo.mjs
 *   REPETICIONES=3   runs per case and renderer
 *   DPRS=1           device pixel ratios (e.g. 1,2)
 *
 * Phases, each started inside a page task (synchronous work run directly by
 * page.evaluate is not reported by the Long Tasks API; PR #16 review F1):
 *   frio      render() plus zoomToScale() to the outline (fitTo for XY), then
 *             two frames;
 *   directo   four non-animated redraws: pan +200 / -200 px, zoom +1 / -1.
 * Per phase: the synchronous call time, the longest main-thread task that
 * OVERLAPS the phase (Long Tasks API, drained with takeRecords before
 * reading), and the time to two frames. Before any case, negative controls
 * run through the same phase code with 150 ms of busy work after the call
 * and 5 ms before the phase marker; each must be reported, or the run stops.
 */

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { opcionesNavegador, RAIZ, servir } from './servidor-estatico.mjs';

const BASE = process.env.MAPA_BASE ?? '5d8e2dcc125a688dbba38a260d5d7eca88a6d223';
const EVIDENCIA = process.env.CONTORNOS_EVIDENCIA ?? null;
const REPETICIONES = Number(process.env.REPETICIONES ?? 3);
const DPRS = (process.env.DPRS ?? '1').split(',').map(Number);
const limites = process.argv.slice(2).map((ruta) => ({ nombre: path.basename(ruta, '.json'), json: readFileSync(ruta, 'utf8') }));

const mapaBase = execFileSync('git', ['show', `${BASE}:web/components/map/MapCanvas.js`], { cwd: RAIZ, encoding: 'utf8' })
  .replaceAll('"../../lib/', '"/web/lib/')
  .replaceAll('"./basemaps.js"', '"/web/components/map/basemaps.js"');
const servidor = await servir({
  '/__base/MapCanvas.js': () => ({ tipo: 'text/javascript', cuerpo: mapaBase }),
  ...Object.fromEntries(limites.map(({ nombre, json }) => [`/__casos/${nombre}.json`, () => ({ tipo: 'application/json', cuerpo: json })])),
});
const browser = await chromium.launch(opcionesNavegador());

const INSTRUMENTOS = () => {
  const tareas = [];
  const obs = new PerformanceObserver((l) => { for (const e of l.getEntries()) tareas.push([e.startTime, e.duration]); });
  obs.observe({ type: 'longtask', buffered: true });
  const dos = () => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
  window.__medir = {
    dos,
    tarea: () => new Promise((ok) => setTimeout(ok, 0)),
    ocupar: (ms) => { const fin = performance.now() + (ms ?? 0); while (performance.now() < fin) { /* busy */ } },
    /* Longest long task overlapping [t0, t1], after the measured task ended. */
    async fase(t0, t1) {
      await new Promise((ok) => setTimeout(ok, 0));
      await dos();
      await new Promise((ok) => setTimeout(ok, 0));
      for (const e of obs.takeRecords()) tareas.push([e.startTime, e.duration]);
      const solapan = tareas.filter(([s, d]) => s < t1 && s + d > t0).map(([, d]) => d);
      return { tareaMaxMs: solapan.length ? Math.max(...solapan) : 0, tareasLargas: solapan.length };
    },
  };
};

async function corrida(mapa, caso, dpr, control = null) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 }, deviceScaleFactor: dpr });
  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.addInitScript(INSTRUMENTOS);
  await page.goto(`${servidor.url}/tests/e2e/contornos-trazo.html?mapa=${mapa}`);
  await page.waitForFunction(() => document.title === 'listo');
  const r = await page.evaluate(async ([caso, control]) => {
    const t = window.__trazo;
    const m = window.__medir;
    const d = caso === 'fixture' ? await t.cargarFixture() : caso === 'xy' ? t.cargarXY() : await t.cargarLimite(caso);
    const objetivo = d.filas.find((f) => f.geometria?.utilizable && d.geometrias?.has(f.geometria.id))?.id ?? null;
    // Cold: render and frame the outline.
    await m.tarea();
    if (control) m.ocupar(control.antes);
    const t0 = performance.now();
    t.canvas.render(d.filas, { colorFor: t.colorFor, geometrias: d.geometrias });
    const estado = objetivo ? t.canvas.zoomToScale(objetivo).estado : (t.canvas.fitTo(d.filas), 'xy');
    if (control) m.ocupar(control.despues);
    const llamadaMs = performance.now() - t0;
    await m.dos();
    const t1 = performance.now();
    const frio = { llamadaMs: +llamadaMs.toFixed(1), dosCuadrosMs: +(t1 - t0).toFixed(1), estado, ...(await m.fase(t0, t1)) };
    // Direct redraws.
    const directo = [];
    const mapa = t.canvas.map;
    for (const [tipo, f] of [['pan', () => mapa.panBy([200, 0], { animate: false })],
                             ['pan', () => mapa.panBy([-200, 0], { animate: false })],
                             ['zoom', () => mapa.setZoom(mapa.getZoom() + 1, { animate: false })],
                             ['zoom', () => mapa.setZoom(mapa.getZoom() - 1, { animate: false })]]) {
      await m.tarea();
      if (control) m.ocupar(control.antes);
      const s0 = performance.now();
      f();
      if (control) m.ocupar(control.despues);
      const llamada = performance.now() - s0;
      await m.dos();
      const s1 = performance.now();
      directo.push({ tipo, llamadaMs: +llamada.toFixed(1), dosCuadrosMs: +(s1 - s0).toFixed(1), ...(await m.fase(s0, s1)) });
    }
    return { frio, directo, zoom: mapa.getZoom() };
  }, [caso, control]);
  await page.close();
  if (errores.length) throw new Error(`${mapa}/${caso}: ${errores.join('; ')}`);
  return r;
}

const salida = {
  navegador: browser.version(), base: BASE,
  actual: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: RAIZ, encoding: 'utf8' }).trim(),
  maquina: { cpu: os.cpus()[0]?.model, nucleos: os.cpus().length, memoriaGiB: +(os.totalmem() / 2 ** 30).toFixed(1),
             sistema: `${os.type()} ${os.release()}`, node: process.version },
  repeticiones: REPETICIONES, dprs: DPRS, controles: [], corridas: [],
};
console.log(`Chromium ${salida.navegador} · ${salida.maquina.cpu} ×${salida.maquina.nucleos}`);

// Negative controls (both renderers, fixture, DPR 1).
for (const mapa of ['base', 'actual']) {
  const r = await corrida(mapa, 'fixture', 1, { antes: 5, despues: 150 });
  for (const [fase, x] of [['frio', r.frio], ...r.directo.map((x) => [`${x.tipo}-directo`, x])]) {
    const fila = { mapa, fase, tareaMaxMs: x.tareaMaxMs, llamadaMs: x.llamadaMs, detectada: x.tareaMaxMs >= 150 };
    salida.controles.push(fila);
  }
}
console.table(salida.controles);
if (!salida.controles.every((c) => c.detectada)) throw new Error('negative control missed: instrumentation unreliable');

const CASOS = ['fixture', 'xy', ...limites.map((l) => l.nombre)];
for (const dpr of DPRS) {
  for (const caso of CASOS) {
    for (let i = 0; i < REPETICIONES; i += 1) {
      for (const mapa of ['base', 'actual']) {          // interleaved, so drift affects both
        const r = await corrida(mapa, caso, dpr);
        salida.corridas.push({ dpr, caso, mapa, repeticion: i, ...r });
        const peor = Math.max(...r.directo.map((x) => x.tareaMaxMs));
        console.log(JSON.stringify({ dpr, caso, mapa, i, frioLlamada: r.frio.llamadaMs, frioTarea: r.frio.tareaMaxMs,
                                     directoLlamadaMax: Math.max(...r.directo.map((x) => x.llamadaMs)), directoTareaMax: peor }));
      }
    }
  }
}

const mediana = (v) => { const s = [...v].sort((a, b) => a - b); return s[Math.floor((s.length - 1) / 2)]; };
salida.resumen = [];
for (const dpr of DPRS) {
  for (const caso of CASOS) {
    for (const mapa of ['base', 'actual']) {
      const rs = salida.corridas.filter((r) => r.dpr === dpr && r.caso === caso && r.mapa === mapa);
      const directos = rs.flatMap((r) => r.directo);
      salida.resumen.push({
        dpr, caso, mapa, n: rs.length,
        'frío: llamada ms (mediana / peor)': `${mediana(rs.map((r) => r.frio.llamadaMs))} / ${Math.max(...rs.map((r) => r.frio.llamadaMs))}`,
        'frío: tarea más larga ms': Math.max(...rs.map((r) => r.frio.tareaMaxMs)),
        'directo: llamada ms (mediana / peor)': `${mediana(directos.map((x) => x.llamadaMs))} / ${Math.max(...directos.map((x) => x.llamadaMs))}`,
        'directo: tarea más larga ms (mediana / peor)': `${mediana(directos.map((x) => x.tareaMaxMs))} / ${Math.max(...directos.map((x) => x.tareaMaxMs))}`,
        'directo: tareas ≥ 50 ms': directos.filter((x) => x.tareaMaxMs >= 50).length + ` de ${directos.length}`,
      });
    }
  }
}
console.table(salida.resumen);
if (EVIDENCIA) {
  mkdirSync(EVIDENCIA, { recursive: true });
  writeFileSync(path.join(EVIDENCIA, 'contornos-trazo-medicion.json'), JSON.stringify(salida, null, 1));
}
await browser.close();
servidor.cerrar();

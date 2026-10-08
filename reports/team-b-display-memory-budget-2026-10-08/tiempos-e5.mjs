/* E5 timing against E4 and E3 (and E1 as the accepted direct reference):
 * time to the final visible contour, separately from input responsiveness.
 * Real Chromium, real mouse and wheel.
 *
 *   B2_DIR=... E1_DIR=... CASOS_DIR=... CHROMIUM=... EVIDENCIA=<dir> \
 *     node reports/team-b-display-memory-budget-2026-10-08/tiempos-e5.mjs [impl,...] [escena,...]
 *
 * Defaults: impls e5,e4,e3; scenes seis, doce, denso-grande-mas-19999;
 * REPETICIONES=3; DPR=1; MIB=64 (E5's budget). 1200 x 640 viewport.
 *
 * Method (PR #16 correction F1): every measured phase starts inside a page
 * task (setTimeout 0), long tasks count when they OVERLAP the phase interval,
 * and observers are drained (takeRecords) before a phase is summarized.
 * Negative controls run first, through the same phase code, or the run stops:
 *   - cold phase with 150 ms of busy work right after render() (same task);
 *   - drag phase with a 150 ms page task fired during the drag;
 *   - a 150 ms task that ENDS before the phase marker is not counted;
 *   - work run directly by page.evaluate (a DevTools-protocol task) is
 *     recorded for reference: Chromium 141 does not report it.
 *
 * Per run (fresh page):
 *   frio      render + fitTo -> every outline of the scene final (no pending
 *             state; E5: no raster in flight and the image is for the current
 *             view). contornoFinalMs and the longest overlapping task.
 *   6 drags and 4 wheel zooms, real input. Each: "entrada" = from the first
 *             mouse event to the last (the interval the user is acting):
 *             longest overlapping task, longest Event Timing duration, longest
 *             frame gap. "final" = from the first event until the contour is
 *             final again (moveend + settled): contornoFinalMs and the longest
 *             overlapping task.
 * Wall-clock figures are for the recorded machine only; no absolute
 * thresholds are asserted, only that every run settled and controls held.
 */

import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { entorno, servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const servidor = await servir(entorno());
const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const EVIDENCIA = process.env.EVIDENCIA ?? null;
const IMPLS = (process.argv[2] ?? 'e5,e4,e3').split(',');
const ESCENAS = (process.argv[3] ?? 'seis,doce,denso-grande-mas-19999').split(',');
const REPETICIONES = Number(process.env.REPETICIONES ?? 3);
const DPR = Number(process.env.DPR ?? 1);
const MIB = Number(process.env.MIB ?? 64);
let fallas = 0;
const ok = (cond, que) => { console.log(`${cond ? 'OK   ' : 'FALLA'} ${que}`); if (!cond) fallas += 1; };

/* Installed before any page script. */
const INSTRUMENTOS = () => {
  const m = { tareas: [], eventos: [], cuadros: [] };
  window.__t = m;
  const tomarTareas = (l) => { for (const e of l) m.tareas.push([e.startTime, e.duration]); };
  const tomarEventos = (l) => { for (const e of l) m.eventos.push([e.startTime, e.duration, e.name]); };
  const obsTareas = new PerformanceObserver((l) => tomarTareas(l.getEntries()));
  obsTareas.observe({ type: 'longtask', buffered: true });
  const obsEventos = new PerformanceObserver((l) => tomarEventos(l.getEntries()));
  obsEventos.observe({ type: 'event', durationThreshold: 16, buffered: true });
  const ciclo = (t) => { m.cuadros.push(t); requestAnimationFrame(ciclo); };
  requestAnimationFrame(ciclo);
  window.__tarea = () => new Promise((r) => setTimeout(r, 0));
  window.__ocupar = (ms) => { const fin = performance.now() + ms; while (performance.now() < fin) { /* busy */ } };
  window.__dos = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  window.__drenar = async () => {
    await new Promise((r) => setTimeout(r, 0));
    await window.__dos();
    await new Promise((r) => setTimeout(r, 0));
    tomarTareas(obsTareas.takeRecords());
    tomarEventos(obsEventos.takeRecords());
  };
  window.__fase = async (t0, t1) => {
    await window.__drenar();
    const solapan = m.tareas.filter(([s, d]) => s < t1 && s + d > t0).map(([, d]) => d);
    const eventos = m.eventos.filter(([s, d]) => s < t1 && s + d > t0).map(([, d]) => d);
    const cuadros = m.cuadros.filter((t) => t >= t0 && t <= t1);
    let cuadroMax = 0;
    for (let i = 1; i < cuadros.length; i += 1) cuadroMax = Math.max(cuadroMax, cuadros[i] - cuadros[i - 1]);
    return { tareaMaxMs: solapan.length ? +Math.max(...solapan).toFixed(0) : 0, tareasLargas: solapan.length,
             eventoMaxMs: eventos.length ? Math.max(...eventos) : 0, cuadroMaxMs: +cuadroMax.toFixed(1) };
  };
  /* Every outline row final: no pending state; E5: nothing in flight, image current. */
  window.__final = async (filas, maxMs = 30000) => {
    const c = window.__m5.canvas;
    const fin = performance.now() + maxMs;
    const ctl = c._diagnostico?.controlador;
    const pendiente = () => filas.some((f) => ['preparando', 'dibujando', 'cargando'].includes(c.posicionDe(f.id)?.estadoContorno))
      || Boolean(ctl && (ctl.enVuelo || (ctl.mostrada && !ctl.bitmapVigente())));
    await new Promise((r) => setTimeout(r, 0));
    while (pendiente() && performance.now() < fin) await new Promise((r) => setTimeout(r, 5));
    await window.__dos();
    return !pendiente();
  };
  /* moveend (or 3 s), then final. */
  window.__trasMover = () => new Promise((r) => {
    const mapa = window.__m5.canvas.map;
    let hecho = false;
    const fin = () => { if (!hecho) { hecho = true; window.__final(window.__filas).then(r); } };
    mapa.once('moveend', fin);
    setTimeout(fin, 3000);
  });
};

async function abrir(impl) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 }, deviceScaleFactor: DPR });
  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.addInitScript(INSTRUMENTOS);
  await page.goto(`${servidor.url}/mem/pagina.html?impl=${impl}&mib=${MIB}`);
  await page.waitForFunction(() => document.title === 'listo');
  return { page, errores };
}

async function corrida(impl, escena, control = null) {
  const { page, errores } = await abrir(impl);
  await page.evaluate(async (escena) => {
    const m = window.__m5;
    window.__d = escena.includes('grande') ? await m.cargar(escena)
      : m.sinteticos({ n: escena === 'doce' ? 12 : 6, ligeros: 2, xy: 3, paso: 0.02 });
    window.__filas = window.__d.filas;
  }, escena);
  const r = { impl, escena };
  r.frio = await page.evaluate(async (control) => {
    const m = window.__m5; const c = m.canvas; const d = window.__d;
    await window.__tarea();
    const t0 = performance.now();
    c.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias });
    c.fitTo(d.filas);
    if (control?.frio) window.__ocupar(control.frio);
    const llamadaMs = performance.now() - t0;
    const final = await window.__final(d.filas);
    const t1 = performance.now();
    return { final, llamadaMs: +llamadaMs.toFixed(1), contornoFinalMs: +(t1 - t0).toFixed(0), ...(await window.__fase(t0, t1)),
             estados: d.filas.filter((f) => f.geometria).map((f) => c.posicionDe(f.id)?.estadoContorno ?? null) };
  }, control);
  r.acciones = [];
  for (let i = 0; i < 10; i += 1) {
    const arrastre = i < 6;
    const t0 = await page.evaluate((control) => {
      if (control?.entrada) setTimeout(() => window.__ocupar(control.entrada), 20);
      return performance.now();
    }, arrastre ? control : null);
    const espera = page.evaluate(() => window.__trasMover());
    await page.mouse.move(600, 320);
    if (arrastre) {
      const dx = i % 2 ? 1 : -1;
      await page.mouse.down();
      for (let k = 1; k <= 6; k += 1) await page.mouse.move(600 + dx * k * 25, 320 + k * 6);
      await page.mouse.up();
    } else {
      await page.mouse.wheel(0, i % 2 ? 120 : -120);
    }
    const tEntrada = await page.evaluate(() => performance.now());
    const final = await espera;
    r.acciones.push(await page.evaluate(async ([t0, tEntrada, tipo, final]) => {
      const t1 = performance.now();
      const entrada = await window.__fase(t0, tEntrada);
      const hastaFinal = await window.__fase(t0, t1);
      return { tipo, final, entradaMs: +(tEntrada - t0).toFixed(0), entrada,
               contornoFinalMs: +(t1 - t0).toFixed(0), tareaMaxHastaFinalMs: hastaFinal.tareaMaxMs };
    }, [t0, tEntrada, arrastre ? 'arrastre' : 'rueda', final]));
  }
  r.errores = errores;
  await page.close();
  return r;
}

const salida = { navegador: browser.version(), dpr: DPR, mib: MIB, repeticiones: REPETICIONES,
                 maquina: { cpu: os.cpus()[0]?.model ?? '?', nucleos: os.cpus().length, sistema: `${os.type()} ${os.release()}` },
                 controles: [], corridas: [] };
console.log(`Chromium ${salida.navegador} · ${salida.maquina.cpu} ×${salida.maquina.nucleos} · DPR ${DPR} · E5 ${MIB} MiB`);

// Negative controls first, through the same phase code.
{
  const r = await corrida('e5', 'seis', { frio: 150, entrada: 150 });
  const filas = [
    { control: 'frío: 150 ms tras render()', tareaMaxMs: r.frio.tareaMaxMs, esperado: '>= 150', bien: r.frio.tareaMaxMs >= 150 },
    ...r.acciones.filter((a) => a.tipo === 'arrastre').map((a, i) => ({
      control: `arrastre ${i}: tarea de 150 ms durante la entrada`, tareaMaxMs: a.entrada.tareaMaxMs, esperado: '>= 150',
      // The task is posted 20 ms after the marker; it must overlap the input interval when that interval is long enough.
      bien: a.entradaMs < 40 || a.entrada.tareaMaxMs >= 150 })),
  ];
  const { page } = await abrir('e5');
  const anterior = await page.evaluate(async () => {
    await window.__tarea();
    window.__ocupar(150);                                  // ends before the marker
    await new Promise((r) => setTimeout(r, 0));
    const t0 = performance.now();
    await window.__dos();
    return window.__fase(t0, performance.now());
  });
  const cdp = await page.evaluate(async () => {
    const t0 = performance.now();
    window.__ocupar(150);                                  // directly in the DevTools-protocol task
    const t1 = performance.now();
    return window.__fase(t0, t1);
  });
  await page.close();
  filas.push({ control: 'tarea de 150 ms que termina antes del marcador', tareaMaxMs: anterior.tareaMaxMs, esperado: '0',
               bien: anterior.tareaMaxMs === 0 });
  filas.push({ control: 'referencia: trabajo directo en page.evaluate (no se usa para medir)', tareaMaxMs: cdp.tareaMaxMs,
               esperado: 'no reportado en Chromium 141', bien: true });
  salida.controles = filas;
  console.table(filas);
  if (!filas.every((f) => f.bien)) {
    console.log('negative control failed: long-task instrumentation is unreliable; stopping');
    process.exit(1);
  }
  ok(filas.filter((f) => f.control.startsWith('arrastre')).some((f) => f.tareaMaxMs >= 150),
     'at least one drag control detected its deliberate 150 ms task');
}

const med = (v) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[Math.floor((s.length - 1) / 2)] : null; };
const max = (v) => (v.length ? Math.max(...v) : null);
const tabla = [];
for (const escena of ESCENAS) {
  for (const impl of IMPLS) {
    const rs = [];
    for (let i = 0; i < REPETICIONES; i += 1) {
      const r = await corrida(impl, escena);
      r.repeticion = i;
      rs.push(r);
      salida.corridas.push(r);
      const todo = r.frio.final && r.acciones.every((a) => a.final) && r.errores.length === 0;
      ok(todo, `${escena} ${impl} #${i}: cold contour ${r.frio.contornoFinalMs} ms (longest task ${r.frio.tareaMaxMs}); `
         + `input longest task ${max(r.acciones.map((a) => a.entrada.tareaMaxMs))} ms, longest event ${max(r.acciones.map((a) => a.entrada.eventoMaxMs))} ms; `
         + `contour after input ≤ ${max(r.acciones.map((a) => a.contornoFinalMs))} ms ${r.errores.join('; ')}`);
    }
    const acc = rs.flatMap((r) => r.acciones);
    tabla.push({ escena, impl,
                 'frío contorno final ms (mediana)': med(rs.map((r) => r.frio.contornoFinalMs)),
                 'frío tarea máx ms (peor)': max(rs.map((r) => r.frio.tareaMaxMs)),
                 'entrada tarea máx ms (mediana)': med(acc.map((a) => a.entrada.tareaMaxMs)),
                 'entrada tarea máx ms (peor)': max(acc.map((a) => a.entrada.tareaMaxMs)),
                 'entrada evento máx ms (peor)': max(acc.map((a) => a.entrada.eventoMaxMs)),
                 'entrada cuadro máx ms (peor)': max(acc.map((a) => a.entrada.cuadroMaxMs)),
                 'tras entrada contorno final ms (mediana)': med(acc.map((a) => a.contornoFinalMs)),
                 'tras entrada contorno final ms (peor)': max(acc.map((a) => a.contornoFinalMs)),
                 'tras entrada tarea máx ms (peor)': max(acc.map((a) => a.tareaMaxHastaFinalMs)),
                 'entradas con tarea >= 50 ms': `${acc.filter((a) => a.entrada.tareaMaxMs >= 50).length}/${acc.length}` });
  }
}
salida.tabla = tabla;
console.table(tabla);
if (EVIDENCIA) {
  mkdirSync(EVIDENCIA, { recursive: true });
  const nombre = `tiempos-e5-dpr${DPR}-${IMPLS.join('_')}-${ESCENAS.join('_')}.json`;
  writeFileSync(path.join(EVIDENCIA, nombre), JSON.stringify(salida, null, 1));
}
await browser.close();
servidor.cerrar();
console.log(fallas ? `${fallas} fallo(s)` : 'Todas las comprobaciones pasaron');
process.exit(fallas ? 1 : 0);

/* E5 paint and interaction against E3 (same exact drawing, on the main
 * thread), E4 (PR #16's per-outline worker bitmaps) and the accepted E1 and
 * B-2 renderers. Real Chromium, real mouse.
 *
 *   B2_DIR=... E1_DIR=... CASOS_DIR=... CHROMIUM=... EVIDENCIA=<dir> \
 *     node reports/team-b-display-memory-budget-2026-10-08/pintura-e5.mjs
 *
 * Scenes (1200 x 640 map, DPR 1 and 2): six overlapping heavy outlines
 * (rings with holes, tiny-part multiparts, single rings) with two light
 * outlines and three XY marks; the same one level deeper (clipped at the
 * canvas edges); the same with a heavy outline selected; twelve overlapping
 * heavy outlines; the parser-limit cases "grande-mas-19999" and
 * "denso-grande-mas-19999" at their outline zoom.
 * Paint, three separate measures (PR #16 pintura.mjs, real canvas
 * dimensions): complete RGBA identity (SHA-256), alpha IoU, tolerance
 * coverage. E5 against E3 is expected to be RGBA-identical: one image of the
 * same paths, in the same order, with the canvas's own transform.
 * Interaction: real clicks on a grid of 40 points of the six-outline scene
 * (holes, overlaps, XY marks over outlines, light outlines); the selected
 * terrain must equal E3's at every point. Also a budget too small for some
 * outlines: an unavailable outline is not hit-testable; what is under it,
 * and its symbol, are.
 */

import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { entorno, servir } from './servidor.mjs';
import { CAPTURAR, cobertura, iou, mascaraDeCaptura, mismasDimensiones } from '../team-b-display-strategy-2026-10-08/pintura.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const servidor = await servir(entorno());
const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const EVIDENCIA = process.env.EVIDENCIA ?? null;
let fallas = 0;
const ok = (cond, que) => { console.log(`${cond ? 'OK   ' : 'FALLA'} ${que}`); if (!cond) fallas += 1; };

const ESCENAS = ['seis', 'seis+1', 'seis-seleccion', 'doce', 'grande-mas-19999', 'denso-grande-mas-19999'];

async function abrir(impl, dpr, extra = '') {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 }, deviceScaleFactor: dpr });
  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.goto(`${servidor.url}/mem/pagina.html?impl=${impl}${extra}`);
  await page.waitForFunction(() => document.title === 'listo');
  await page.evaluate(() => {
    window.__dos = () => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    window.__asentar = async (filas) => {
      const c = window.__m5.canvas;
      const fin = performance.now() + 30000;
      const pend = () => filas.some((f) => ['preparando', 'dibujando', 'cargando'].includes(c.posicionDe(f.id)?.estadoContorno));
      await new Promise((ok) => setTimeout(ok, 30));
      while (pend() && performance.now() < fin) await new Promise((ok) => setTimeout(ok, 15));
      // E5: also wait for the image of this view (and selection) to be shown.
      const ctl = c._diagnostico?.controlador;
      while (ctl && (ctl.enVuelo || (ctl.mostrada && !ctl.bitmapVigente())) && performance.now() < fin) {
        await new Promise((ok) => setTimeout(ok, 15));
      }
      await window.__dos();
    };
  });
  return { page, errores };
}

async function escena(page, nombre) {
  return page.evaluate(async ([nombre, capturar]) => {
    const m = window.__m5; const c = m.canvas;
    const tomar = (0, eval)(`(${capturar})`);
    let d;
    if (nombre.startsWith('grande') || nombre.startsWith('denso')) {
      d = await m.cargar(nombre);
      c.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias });
      await window.__asentar(d.filas);
      c.zoomToScale('contorno');
    } else {
      d = m.sinteticos({ n: nombre === 'doce' ? 12 : 6, ligeros: 2, xy: 3, paso: 0.02 });
      c.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias });
      c.fitTo(d.filas);
      if (nombre === 'seis+1') { await window.__asentar(d.filas); c.map.setZoom(c.map.getZoom() + 1, { animate: false }); }
      if (nombre === 'seis-seleccion') { await window.__asentar(d.filas); c.select('t-0'); }
    }
    await window.__asentar(d.filas);
    // E5 selection: wait until the shown image carries the selected style.
    const ctl = c._diagnostico?.controlador;
    if (ctl && nombre === 'seis-seleccion') {
      const fin = performance.now() + 15000;
      while (!(ctl.mostrada?.lista ?? []).some((x) => x.id === 'g-t-0' && x.clave.includes('#111111')) && performance.now() < fin) {
        await new Promise((ok) => setTimeout(ok, 15));
      }
      await window.__dos();
    }
    const estados = d.filas.filter((f) => f.geometria).map((f) => c.posicionDe(f.id)?.estadoContorno ?? null);
    return { zoom: c.map.getZoom(), estados, modos: ctl?.estado().modos ?? null, ...(await tomar()) };
  }, [nombre, CAPTURAR]);
}

const r4 = (v) => +v.toFixed(4);
const salida = { navegador: browser.version(), pintura: [], clics: [], noDisponibles: null };

// Paint.
for (const dpr of [1, 2]) {
  for (const nombre of ESCENAS) {
    const capt = {};
    for (const impl of ['e5', 'e3', 'e4', 'e1', 'b2']) {
      const { page, errores } = await abrir(impl, dpr);
      capt[impl] = await escena(page, nombre);
      await page.close();
      if (errores.length) ok(false, `${impl} ${nombre} DPR ${dpr}: page errors ${errores.join('; ')}`);
      if (!capt[impl].pintados) ok(false, `${impl} ${nombre} DPR ${dpr}: blank canvas`);
    }
    const a = mascaraDeCaptura(capt.e5);
    for (const otro of ['e3', 'e4', 'e1', 'b2']) {
      const b = mascaraDeCaptura(capt[otro]);
      mismasDimensiones(a, b);
      const fila = { dpr, escena: nombre, contra: otro, lienzo: `${a.ancho}x${a.alto}`, zoom: [capt.e5.zoom, capt[otro].zoom],
                     'RGBA idéntico': capt.e5.sha256 === capt[otro].sha256, 'IoU alfa': r4(iou(a, b)),
                     'otro cubierto ±1px': r4(cobertura(b, a, 1)), 'e5 cubierto ±1px': r4(cobertura(a, b, 1)),
                     'otro cubierto ±2px': r4(cobertura(b, a, 2)), 'e5 cubierto ±2px': r4(cobertura(a, b, 2)),
                     pintadosE5: capt.e5.pintados, pintados: capt[otro].pintados, sha256E5: capt.e5.sha256, sha256: capt[otro].sha256,
                     modosE5: capt.e5.modos };
      salida.pintura.push(fila);
    }
    const e3 = salida.pintura.at(-4);
    ok(e3['RGBA idéntico'] && capt.e5.zoom === capt.e3.zoom,
       `${nombre} DPR ${dpr}: E5 vs E3 RGBA ${e3['RGBA idéntico'] ? 'identical' : 'DIFFERENT'} (${e3.lienzo}, ${capt.e5.pintados} px; `
       + `E5 modes ${JSON.stringify((capt.e5.modos ?? []).reduce((x, [, mo]) => { x[mo] = (x[mo] ?? 0) + 1; return x; }, {}))})`);
  }
}

// Interaction: the same terrain under 40 real clicks, E5 vs E3.
const clicsDe = async (impl) => {
  const { page } = await abrir(impl, 1);
  const puntos = await page.evaluate(async () => {
    const m = window.__m5; const c = m.canvas;
    const d = m.sinteticos({ n: 6, ligeros: 2, xy: 3, paso: 0.02 });
    c.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias });
    c.fitTo(d.filas);
    await window.__asentar(d.filas);
    const lista = [];
    // A grid over the outlines' area, plus each XY mark and t-0's hole centre.
    const b = L.latLngBounds(d.filas.filter((f) => f.geometria).flatMap((f) => [[f.geometria.bbox[1], f.geometria.bbox[0]], [f.geometria.bbox[3], f.geometria.bbox[2]]]));
    const sw = c.map.latLngToContainerPoint(b.getSouthWest()); const ne = c.map.latLngToContainerPoint(b.getNorthEast());
    for (let i = 0; i < 6; i += 1) for (let j = 0; j < 5; j += 1) {
      lista.push({ que: 'rejilla', x: Math.round(sw.x + (ne.x - sw.x) * (i + 0.5) / 6), y: Math.round(ne.y + (sw.y - ne.y) * (j + 0.5) / 5) });
    }
    for (const f of d.filas.filter((x) => !x.geometria)) { const p = c.map.latLngToContainerPoint([f.lat, f.lon]); lista.push({ que: `xy ${f.id}`, x: Math.round(p.x), y: Math.round(p.y) }); }
    const g0 = d.geometrias.get('g-t-0').geojson.coordinates[0][1];
    const h = c.map.latLngToContainerPoint([g0.reduce((a, q) => a + q[1], 0) / g0.length, g0.reduce((a, q) => a + q[0], 0) / g0.length]);
    lista.push({ que: 'hueco t-0', x: Math.round(h.x + 3), y: Math.round(h.y + 3) });
    for (const f of d.filas.filter((x) => x.id.startsWith('l-'))) {
      const p = c.map.latLngToContainerPoint([f.geometria.punto_interior.coordinates[1], f.geometria.punto_interior.coordinates[0] + 0.003]);
      lista.push({ que: `ligero ${f.id}`, x: Math.round(p.x), y: Math.round(p.y) });
    }
    return lista.slice(0, 40);
  });
  const res = [];
  for (const p of puntos) {
    await page.evaluate(() => { window.__m5.selecciones.length = 0; window.__m5.canvas.select(null); });
    await page.evaluate(() => window.__dos());
    await page.mouse.click(p.x, p.y);
    await page.waitForTimeout(420);
    res.push({ ...p, id: await page.evaluate(() => window.__m5.selecciones[0]?.id ?? null) });
  }
  await page.close();
  return res;
};
const c5 = await clicsDe('e5');
const c3 = await clicsDe('e3');
const iguales = c5.filter((p, i) => p.id === c3[i].id).length;
salida.clics = c5.map((p, i) => ({ ...p, e3: c3[i].id }));
ok(iguales === c5.length, `real clicks: ${iguales}/${c5.length} select the same terrain as E3 `
   + `(${c5.filter((p) => p.id).length} hit something; hole of t-0 → ${c5.find((p) => p.que === 'hueco t-0')?.id ?? 'nothing'})`);

// Unavailable outlines are not hit-testable; their symbol and what lies under them are.
{
  const { page } = await abrir('e5', 1, '&mib=6');
  const r = await page.evaluate(async () => {
    const m = window.__m5; const c = m.canvas;
    const d = m.sinteticos({ n: 6, ligeros: 2, xy: 3, paso: 0.02 });
    c.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias });
    c.fitTo(d.filas);
    await window.__asentar(d.filas);
    const no = d.filas.filter((f) => f.geometria && ['sin_memoria', 'demasiado_grande'].includes(c.posicionDe(f.id)?.estadoContorno));
    const puntos = no.map((f) => {
      const g = d.geometrias.get(f.geometria.id).geojson.coordinates[0][0];
      const p = c.map.latLngToContainerPoint([g[Math.floor(g.length / 8)][1] * 0.6 + f.geometria.punto_interior.coordinates[1] * 0.4,
                                              g[Math.floor(g.length / 8)][0] * 0.6 + f.geometria.punto_interior.coordinates[0] * 0.4]);
      const s = c.posicionDe(f.id);
      return { id: f.id, borde: { x: Math.round(p.x), y: Math.round(p.y) }, simbolo: { x: Math.round(s.x), y: Math.round(s.y) },
               estado: s.estadoContorno, aviso: (c._diagnostico.aviso(f.id) ?? '').replace(/<[^>]+>/g, ' ').trim() };
    });
    return { puntos, estados: d.filas.filter((f) => f.geometria).map((f) => [f.id, c.posicionDe(f.id)?.estadoContorno]) };
  });
  const res = [];
  for (const p of r.puntos) {
    for (const [donde, q] of [['dentro', p.borde], ['simbolo', p.simbolo]]) {
      await page.evaluate(() => { window.__m5.selecciones.length = 0; window.__m5.canvas.select(null); });
      await page.mouse.click(q.x, q.y);
      await page.waitForTimeout(420);
      res.push({ id: p.id, donde, seleccionado: await page.evaluate(() => window.__m5.selecciones[0]?.id ?? null), estado: p.estado, aviso: p.aviso });
    }
  }
  await page.close();
  salida.noDisponibles = { estados: r.estados, clics: res };
  const simbolos = res.filter((x) => x.donde === 'simbolo');
  const dentro = res.filter((x) => x.donde === 'dentro');
  ok(r.puntos.length > 0 && simbolos.every((x) => x.seleccionado === x.id) && dentro.every((x) => x.seleccionado !== x.id),
     `6 MiB budget: ${r.puntos.length} outlines unavailable (${[...new Set(r.puntos.map((p) => p.estado))].join(', ')}); `
     + `inside them nothing of theirs is hit (${dentro.map((x) => x.seleccionado ?? '—').join(', ')}); their symbol selects them; `
     + `wording "${r.puntos[0]?.aviso.split('  ').at(-1)}"`);
}

console.table(salida.pintura.map(({ sha256E5: _a, sha256: _b, modosE5: _m, ...x }) => x));
if (EVIDENCIA) { mkdirSync(EVIDENCIA, { recursive: true }); writeFileSync(path.join(EVIDENCIA, 'pintura-e5.json'), JSON.stringify(salida, null, 1)); }
await browser.close();
servidor.cerrar();
console.log(fallas ? `${fallas} fallo(s)` : 'Todas las comprobaciones pasaron');
process.exit(fallas ? 1 : 0);

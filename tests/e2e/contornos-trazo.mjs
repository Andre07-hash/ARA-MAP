/* E1 regression: boundary rings drawn by the branch's MapCanvas paint the
 * SAME complete RGBA canvas as the accepted B-2 MapCanvas, and the faster
 * path is used only where its assumptions hold.
 *
 *   cd tests/e2e && npm install && node contornos-trazo.mjs [limit.json ...]
 *
 * Optional arguments: parser-limit cases {descriptor, cuerpo} from the
 * accepted B-1 parser (generator and provenance in
 * reports/team-b-boundary-path-drawing-2026-10-08/); served locally, never
 * committed.
 *
 *   CHROMIUM=/path/to/chrome     that binary instead of the "chrome" channel
 *   MAPA_BASE=<commit>            the accepted renderer (default 5d8e2dc, B-2)
 *   CONTORNOS_EVIDENCIA=dir       JSON summary (every capture's dimensions,
 *                                 painted count and full SHA-256)
 *   DPRS=1,2                      device pixel ratios (default 1 and 2)
 *
 * 1. Paint identity. Each case is drawn by both renderers in fresh pages,
 *    through the same deterministic steps; at every view and style the
 *    overlay canvas is read after two frames: real width and height, count of
 *    painted (alpha > 0) pixels, SHA-256 of all RGBA bytes. Blank captures
 *    fail. Views: the outline zoom; a smaller part two levels deeper (limit
 *    cases); the first position of the first ring three levels deeper (its
 *    closing seam); a corner of the bounds one level deeper (the outline
 *    clipped at the canvas edges). Styles: normal, dashed ("3 2", as
 *    layerDash gives), selected. Cases: the 12-row fixture (holes, several
 *    parts), 500 XY points, and any limit case given.
 * 2. Mechanism and fallbacks (fixture, DPR 1): the branch makes no
 *    context closePath() call for outlines; with Leaflet's version changed,
 *    without Path2D, or with positions that are not whole pixels, it falls
 *    back to Leaflet's own drawing and paints the same bytes as the accepted
 *    renderer under the same condition; on an SVG renderer it draws
 *    Leaflet's SVG path.
 */

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { opcionesNavegador, RAIZ, servir } from './servidor-estatico.mjs';

const BASE = process.env.MAPA_BASE ?? '5d8e2dcc125a688dbba38a260d5d7eca88a6d223';
const EVIDENCIA = process.env.CONTORNOS_EVIDENCIA ?? null;
const DPRS = (process.env.DPRS ?? '1,2').split(',').map(Number);
const limites = process.argv.slice(2).map((ruta) => ({ nombre: path.basename(ruta, '.json'), json: readFileSync(ruta, 'utf8') }));

const mapaBase = execFileSync('git', ['show', `${BASE}:web/components/map/MapCanvas.js`], { cwd: RAIZ, encoding: 'utf8' })
  .replaceAll('"../../lib/', '"/web/lib/')
  .replaceAll('"./basemaps.js"', '"/web/components/map/basemaps.js"');
const servidor = await servir({
  '/__base/MapCanvas.js': () => ({ tipo: 'text/javascript', cuerpo: mapaBase }),
  ...Object.fromEntries(limites.map(({ nombre, json }) => [`/__casos/${nombre}.json`, () => ({ tipo: 'application/json', cuerpo: json })])),
});
const browser = await chromium.launch(opcionesNavegador());
const resumen = { navegador: browser.version(), base: BASE, actual: gitHead(), dprs: DPRS, capturas: [], mecanismo: {} };
let fallos = 0;
const ok = (cond, que) => { console.log(`${cond ? 'OK   ' : 'FALLA'} ${que}`); if (!cond) fallos += 1; };

function gitHead() {
  try { return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: RAIZ, encoding: 'utf8' }).trim(); } catch { return null; }
}

async function pagina(mapa, dpr, espias = false) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 }, deviceScaleFactor: dpr });
  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.goto(`${servidor.url}/tests/e2e/contornos-trazo.html?mapa=${mapa}${espias ? '&espias=1' : ''}`);
  await page.waitForFunction(() => document.title === 'listo');
  await page.evaluate(() => {
    window.__dos = () => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    window.__capturar = async (vista, estilo) => {
      await window.__dos();
      const lienzo = document.querySelector('.leaflet-overlay-pane canvas');
      const { data, width, height } = lienzo.getContext('2d').getImageData(0, 0, lienzo.width, lienzo.height);
      let pintados = 0;
      for (let i = 3; i < data.length; i += 4) if (data[i]) pintados += 1;
      const h = await crypto.subtle.digest('SHA-256', data);
      const m = window.__trazo.canvas.map;
      const c = m.getCenter();
      return { vista, estilo, ancho: width, alto: height, dpr: devicePixelRatio, pintados,
               sha256: [...new Uint8Array(h)].map((x) => x.toString(16).padStart(2, '0')).join(''),
               zoom: m.getZoom(), centro: [+c.lat.toFixed(9), +c.lng.toFixed(9)] };
    };
  });
  return { page, errores };
}

/* Every capture of one case, by one renderer. Same steps for both. */
async function capturas(mapa, caso, dpr) {
  const { page, errores } = await pagina(mapa, dpr);
  const lista = await page.evaluate(async (caso) => {
    const t = window.__trazo;
    const d = caso === 'fixture' ? await t.cargarFixture() : caso === 'xy' ? t.cargarXY() : await t.cargarLimite(caso);
    const m = t.canvas.map;
    const salida = [];
    const pintar = (dash) => t.canvas.render(d.filas, { colorFor: t.colorFor, geometrias: d.geometrias,
                                                         dashFor: dash ? () => '3 2' : null });
    const estilos = async (vista, id) => {
      pintar(false);
      salida.push(await window.__capturar(vista, 'normal'));
      if (id) {
        t.canvas.select(id);
        salida.push(await window.__capturar(vista, 'seleccionado'));
        t.canvas.select(null);
      }
      pintar(true);
      salida.push(await window.__capturar(vista, 'discontinuo'));
      pintar(false);
    };
    pintar(false);
    t.canvas.fitTo(d.filas);
    await estilos('general', null);
    if (caso === 'xy') {
      m.setView([20.45, -100.5], m.getZoom() + 3, { animate: false });
      await estilos('xy+3', d.filas[0].id);
      return salida;
    }
    const conCuerpo = d.filas.filter((f) => f.geometria?.utilizable === true && d.geometrias.has(f.geometria.id));
    for (const fila of conCuerpo) {
      const cuerpo = d.geometrias.get(fila.geometria.id);
      const partes = cuerpo.geojson.coordinates;
      const r = t.canvas.zoomToScale(fila.id);
      const z = m.getZoom();
      await estilos(`${fila.id}:escala(${r.estado})`, fila.id);
      if (partes.length > 1) {
        const anillo = partes.at(-1)[0].slice(0, -1);
        m.setView([anillo.reduce((a, q) => a + q[1], 0) / anillo.length, anillo.reduce((a, q) => a + q[0], 0) / anillo.length],
                  z + 2, { animate: false });
        await estilos(`${fila.id}:parte+2`, fila.id);
      }
      const p0 = partes[0][0][0];
      m.setView([p0[1], p0[0]], z + 3, { animate: false });
      await estilos(`${fila.id}:costura+3`, fila.id);
      m.setView([fila.geometria.bbox[3], fila.geometria.bbox[0]], z + 1, { animate: false });
      await estilos(`${fila.id}:esquina+1`, fila.id);
    }
    return salida;
  }, caso);
  await page.close();
  if (errores.length) throw new Error(`${mapa}/${caso}: ${errores.join('; ')}`);
  for (const c of lista) {
    if (!c.pintados) throw new Error(`${mapa}/${caso}/${c.vista}/${c.estilo}: blank canvas`);
    if (c.dpr !== dpr) throw new Error(`${mapa}/${caso}: DPR ${c.dpr}, asked ${dpr}`);
  }
  return lista;
}

// 1. Paint identity.
const CASOS = ['fixture', 'xy', ...limites.map((l) => l.nombre)];
for (const dpr of DPRS) {
  for (const caso of CASOS) {
    const base = await capturas('base', caso, dpr);
    const actual = await capturas('actual', caso, dpr);
    ok(base.length === actual.length, `${caso} DPR ${dpr}: same ${base.length} views and styles`);
    let iguales = 0;
    for (let i = 0; i < base.length; i += 1) {
      const a = base[i]; const b = actual[i];
      const misma = a.vista === b.vista && a.estilo === b.estilo && a.zoom === b.zoom
        && a.centro.join() === b.centro.join() && a.ancho === b.ancho && a.alto === b.alto;
      const igual = misma && a.sha256 === b.sha256 && a.pintados === b.pintados;
      if (igual) iguales += 1;
      else ok(false, `${caso} DPR ${dpr} ${a.vista} ${a.estilo}: ${JSON.stringify({ base: a, actual: b })}`);
      resumen.capturas.push({ caso, dpr, vista: a.vista, estilo: a.estilo, zoom: a.zoom, lienzo: `${a.ancho}x${a.alto}`,
                              pintados: a.pintados, pintadosActual: b.pintados, sha256Base: a.sha256, sha256Actual: b.sha256,
                              identico: igual });
    }
    ok(iguales === base.length, `${caso} DPR ${dpr}: ${iguales}/${base.length} captures RGBA-identical `
       + `(canvas ${base[0].ancho}x${base[0].alto})`);
  }
}

// 2. Mechanism and fallbacks (fixture, DPR 1, real outline view).
async function cierresYPintura(mapa, preparar = null) {
  const { page, errores } = await pagina(mapa, 1, true);
  const r = await page.evaluate(async (preparar) => {
    const t = window.__trazo;
    if (preparar === 'version') L.version = '1.9.5';
    if (preparar === 'sinPath2D') window.Path2D = undefined;
    // Positions not rounded to whole pixels (Leaflet rounds them itself).
    if (preparar === 'fracciones') L.Point.prototype._round = function noRedondear() { return this; };
    const d = await t.cargarFixture();
    t.canvas.render(d.filas, { colorFor: t.colorFor, geometrias: d.geometrias });
    t.canvas.zoomToScale('t-multiparte');
    await window.__dos();
    window.__cierres.contexto = 0; window.__cierres.path2d = 0;
    t.canvas.map.panBy([10, 0], { animate: false });      // one redraw, counted
    const cierres = { ...window.__cierres };
    return { cierres, captura: await window.__capturar('t-multiparte', preparar ?? 'normal') };
  }, preparar);
  await page.close();
  return { ...r, errores };
}
{
  const base = await cierresYPintura('base');
  const actual = await cierresYPintura('actual');
  ok(base.cierres.contexto > 0 && base.cierres.path2d === 0, `base: Leaflet closes rings on the context (${JSON.stringify(base.cierres)})`);
  ok(actual.cierres.contexto === 0 && actual.cierres.path2d === 0,
     `branch: no closePath() call; rings closed by "Z" in one Path2D's path data (${JSON.stringify(actual.cierres)})`);
  ok(actual.captura.sha256 === base.captura.sha256, 'branch paints the same bytes at that view');
  const NOMBRES = { version: 'Leaflet version not 1.9.4', sinPath2D: 'no Path2D', fracciones: 'positions not whole pixels' };
  for (const caso of Object.keys(NOMBRES)) {
    const r = await cierresYPintura('actual', caso);
    const b = caso === 'fracciones' ? await cierresYPintura('base', caso) : base;
    ok(r.errores.length === 0 && r.cierres.contexto > 0 && r.captura.sha256 === b.captura.sha256,
       `fallback (${NOMBRES[caso]}): Leaflet's own drawing, same bytes as the accepted renderer `
       + `(${JSON.stringify({ cierres: r.cierres, errores: r.errores })})`);
    resumen.mecanismo[caso] = { cierres: r.cierres, sha256: r.captura.sha256, sha256Base: b.captura.sha256 };
  }
  resumen.mecanismo.base = { cierres: base.cierres, sha256: base.captura.sha256 };
  resumen.mecanismo.actual = { cierres: actual.cierres, sha256: actual.captura.sha256 };
  // SVG renderer: the outline class falls back to Leaflet's SVG path.
  const { page, errores } = await pagina('actual', 1);
  const svg = await page.evaluate(async () => {
    const t = window.__trazo;
    const d = await t.cargarFixture();
    t.canvas.render(d.filas, { colorFor: t.colorFor, geometrias: d.geometrias });
    t.canvas.zoomToScale('t-hueco');
    await window.__dos();
    let Clase = null;
    t.canvas.map.eachLayer((l) => { if (l instanceof L.Polygon) Clase = l.constructor; });
    const div = document.createElement('div');
    div.style.cssText = 'width:400px;height:300px';
    document.body.append(div);
    const otro = L.map(div, { renderer: L.svg() }).setView(t.canvas.map.getCenter(), t.canvas.map.getZoom());
    const capa = new Clase(d.geometrias.get('geo-hueco').geojson.coordinates.map((p) => p.map((r) => r.map(([lon, lat]) => [lat, lon]))))
      .addTo(otro);
    const dAttr = capa._path?.getAttribute('d') ?? '';
    return { clase: Clase !== L.Polygon && Clase.prototype instanceof L.Polygon, anillos: (dAttr.match(/z/gi) ?? []).length };
  });
  await page.close();
  ok(errores.length === 0 && svg.clase && svg.anillos === 2,
     `SVG renderer: the outline class draws Leaflet's SVG path (${JSON.stringify({ ...svg, errores })})`);
  resumen.mecanismo.svg = svg;
}

if (EVIDENCIA) {
  mkdirSync(EVIDENCIA, { recursive: true });
  writeFileSync(path.join(EVIDENCIA, 'contornos-trazo.json'), JSON.stringify(resumen, null, 1));
}
await browser.close();
servidor.cerrar();
console.log(`Chromium ${resumen.navegador} · base ${BASE.slice(0, 7)} · actual ${resumen.actual?.slice(0, 7)} · `
            + `${resumen.capturas.length} comparisons`);
console.log(fallos ? `${fallos} fallo(s)` : 'Todas las comprobaciones pasaron');
process.exit(fallos ? 1 : 0);

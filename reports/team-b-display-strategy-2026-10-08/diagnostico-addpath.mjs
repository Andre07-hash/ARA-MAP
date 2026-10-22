/* Why "e1p" (each ring closed on its own Path2D, merged with addPath) is not
 * the accepted drawing: Leaflet's real parts of "one large part + 19,999
 * small" at its outline zoom (10), where Leaflet has left 19,999 two-position
 * rings, drawn on a separate canvas with the accepted closePath() path, with
 * per-ring Path2D + addPath, and with one Path2D of SVG path data (M…L…Z),
 * for the first N rings. Painted pixels (alpha > 0) are counted.
 *
 *   B2_DIR=... CASOS_DIR=... CHROMIUM=... node reports/team-b-display-strategy-2026-10-08/diagnostico-addpath.mjs
 */

import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const servidor = await servir({ b2: process.env.B2_DIR, casos: process.env.CASOS_DIR });
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1200, height: 640 } });
await page.goto(`${servidor.url}/proto/banco.html?impl=b2`);
await page.waitForFunction(() => document.title === 'listo');
const r = await page.evaluate(async () => {
  const b = window.__banco;
  const d = await b.cargar('grande-mas-19999');
  b.canvas.render(d.filas, { colorFor: b.colorFor, geometrias: d.geometrias });
  b.canvas.zoomToScale('contorno');
  await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
  let partes = null;
  b.canvas.map.eachLayer((l) => { if (l instanceof L.Polygon) partes = l._parts.map((p) => p.map((q) => [q.x, q.y])); });
  const longitudes = {};
  for (const p of partes) longitudes[p.length] = (longitudes[p.length] ?? 0) + 1;
  const c = document.createElement('canvas'); c.width = 1440; c.height = 768;
  const ctx = c.getContext('2d');
  const pintar = (anillos, modo) => {
    ctx.clearRect(0, 0, c.width, c.height);
    let p = null;
    if (modo === 'closePath') {
      ctx.beginPath();
      for (const a of anillos) { a.forEach((q, j) => ctx[j ? 'lineTo' : 'moveTo'](q[0], q[1])); ctx.closePath(); }
    } else if (modo === 'addPath') {
      p = new Path2D();
      for (const a of anillos) { const s = new Path2D(); a.forEach((q, j) => s[j ? 'lineTo' : 'moveTo'](q[0], q[1])); s.closePath(); p.addPath(s); }
    } else {
      let t = '';
      for (const a of anillos) { a.forEach((q, j) => { t += `${j ? 'L' : 'M'}${q[0]} ${q[1]}`; }); t += 'Z'; }
      p = new Path2D(t);
    }
    ctx.globalAlpha = 0.2; ctx.fillStyle = '#2a78d6';
    if (p) ctx.fill(p, 'evenodd'); else ctx.fill('evenodd');
    ctx.globalAlpha = 1; ctx.lineWidth = 2; ctx.strokeStyle = '#2a78d6'; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    if (p) ctx.stroke(p); else ctx.stroke();
    const datos = ctx.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 3; i < datos.length; i += 4) if (datos[i]) n += 1;
    return n;
  };
  const filas = [];
  for (const n of [100, 500, 1000, 2000, 5000, 10000, partes.length]) {
    const sub = partes.slice(0, n);
    filas.push({ anillos: n, closePath: pintar(sub, 'closePath'), 'Path2D + addPath': pintar(sub, 'addPath'),
                 'Path2D de datos SVG': pintar(sub, 'svg') });
  }
  return { zoom: b.canvas.map.getZoom(), longitudes, filas };
});
console.log(`Chromium ${browser.version()} · zoom ${r.zoom} · ring lengths (positions: count) ${JSON.stringify(r.longitudes)}`);
console.table(r.filas);
await browser.close();
servidor.cerrar();

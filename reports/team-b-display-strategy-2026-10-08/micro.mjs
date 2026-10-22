/* Isolating the two browser costs found by profiling, outside Leaflet.
 *
 *   CHROMIUM=/path/to/chrome node reports/team-b-display-strategy-2026-10-08/micro.mjs
 *
 * 1. Path building: N square subpaths in ONE path, each closed with
 *    closePath() versus lineTo(first point), on the context and on Path2D.
 *    Time to build only (paint is deferred by the browser).
 * 2. Raster: 20,000 such rings filled and/or stroked with Leaflet's style
 *    (weight 2, round caps and joins) versus miter joins, forced with a 1x1
 *    getImageData. Best of 3. Machine-specific evidence, not thresholds.
 */

import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const page = await browser.newPage();
console.log(`Chromium ${browser.version()}`);

const construir = await page.evaluate(() => {
  const c = document.createElement('canvas'); c.width = 1200; c.height = 640; document.body.append(c);
  const ctx = c.getContext('2d');
  const filas = [];
  for (const n of [1000, 2000, 5000, 10000, 20000]) {
    const medir = (modo) => {
      const veces = [];
      for (let rep = 0; rep < 3; rep += 1) {
        const t0 = performance.now();
        const p = modo.startsWith('Path2D') ? new Path2D() : null;
        const destino = p ?? ctx;
        if (!p) ctx.beginPath();
        for (let i = 0; i < n; i += 1) {
          const x = (i % 160) * 7; const y = Math.floor(i / 160) * 5;
          destino.moveTo(x, y); destino.lineTo(x + 4, y); destino.lineTo(x + 4, y + 4); destino.lineTo(x, y + 4);
          if (modo.endsWith('closePath')) destino.closePath(); else destino.lineTo(x, y);
        }
        veces.push(performance.now() - t0);
      }
      return +Math.min(...veces).toFixed(1);
    };
    filas.push({ subtrayectos: n, 'ctx closePath ms': medir('ctx closePath'), 'ctx lineTo ms': medir('ctx lineTo'),
                 'Path2D closePath ms': medir('Path2D closePath'), 'Path2D lineTo ms': medir('Path2D lineTo') });
  }
  return filas;
});
console.log('\n1. Building one path of N closed square subpaths (best of 3)');
console.table(construir);

const raster = await page.evaluate(() => {
  const c = document.createElement('canvas'); c.width = 1200; c.height = 640; document.body.append(c);
  const ctx = c.getContext('2d');
  const forzar = () => ctx.getImageData(0, 0, 1, 1);
  const filas = [];
  for (const lado of [0.6, 3, 8]) {
    for (const estilo of ['relleno', 'trazo redondo', 'trazo inglete', 'ambos redondo (Leaflet)', 'ambos inglete']) {
      const veces = [];
      for (let rep = 0; rep < 3; rep += 1) {
        ctx.clearRect(0, 0, 1200, 640); forzar();
        const t0 = performance.now();
        ctx.beginPath();
        for (let i = 0; i < 20000; i += 1) {
          const x = 10 + (i % 160) * 7.3; const y = 10 + Math.floor(i / 160) * 5;
          ctx.moveTo(x, y); ctx.lineTo(x + lado, y); ctx.lineTo(x + lado, y + lado); ctx.lineTo(x, y + lado); ctx.lineTo(x, y);
        }
        const redondo = estilo.includes('redondo');
        ctx.lineWidth = 2; ctx.lineJoin = redondo ? 'round' : 'miter'; ctx.lineCap = redondo ? 'round' : 'butt';
        ctx.fillStyle = '#2a78d6'; ctx.strokeStyle = '#2a78d6';
        if (estilo === 'relleno' || estilo.startsWith('ambos')) { ctx.globalAlpha = 0.2; ctx.fill('evenodd'); }
        if (estilo !== 'relleno') { ctx.globalAlpha = 1; ctx.stroke(); }
        forzar();
        veces.push(performance.now() - t0);
      }
      filas.push({ 'lado px': lado, estilo, 'ms (20,000 anillos)': +Math.min(...veces).toFixed(1) });
    }
  }
  return filas;
});
console.log('\n2. Rasterizing 20,000 visible rings (build + paint, best of 3)');
console.table(raster);
await browser.close();

/* Ring closing: cost and stroke identity of five ways to close rings,
 * outside Leaflet (follow-up to the supervisory review of PR #16).
 *
 *   CHROMIUM=/path/to/chrome node reports/team-b-display-strategy-2026-10-08/micro-cierre.mjs
 *
 * Identity sets: (a) 4,000 small irregular quads on a grid (many crossing
 * the canvas edges), plus six 400-position rings each with a 50-position
 * hole, all at non-integer positions; (b) Leaflet-like whole-pixel rings:
 * one 60-position ring and 19,999 two-position rings 1 px tall, as Leaflet
 * leaves small parts after its 1 px smoothing at an overview zoom. Paint is Leaflet 1.9.4's _fillStroke sequence with
 * the outline styles the renderer uses: normal (weight 2, fill 0.20), dashed
 * ("3 2", from layerDash) and selected (#111111, weight 3, fill 0.32), round
 * caps and joins, at DPR 1 and 2. Each way is compared, byte for byte, with
 * the accepted one: one path, closePath() after each ring.
 * Build time: 20,000 rings, best of 3. Machine-specific.
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
const r = await page.evaluate(async () => {
  const c = document.createElement('canvas'); c.width = 2880; c.height = 1536; document.body.append(c);
  const ctx = c.getContext('2d');
  const MODOS = {
    closePath: (anillos) => {
      ctx.beginPath();
      for (const a of anillos) { ctx.moveTo(...a[0]); for (let j = 1; j < a.length; j += 1) ctx.lineTo(...a[j]); ctx.closePath(); }
      return null;
    },
    'lineTo(primero)': (anillos) => {
      ctx.beginPath();
      for (const a of anillos) { ctx.moveTo(...a[0]); for (let j = 1; j < a.length; j += 1) ctx.lineTo(...a[j]); ctx.lineTo(...a[0]); }
      return null;
    },
    'Path2D por anillo + addPath': (anillos) => {
      const p = new Path2D();
      for (const a of anillos) {
        const q = new Path2D(); q.moveTo(...a[0]); for (let j = 1; j < a.length; j += 1) q.lineTo(...a[j]); q.closePath(); p.addPath(q);
      }
      return p;
    },
    'Path2D de datos SVG (M…L…Z)': (anillos) => {
      let t = '';
      for (const a of anillos) { t += `M${a[0][0]} ${a[0][1]}`; for (let j = 1; j < a.length; j += 1) t += `L${a[j][0]} ${a[j][1]}`; t += 'Z'; }
      return new Path2D(t);
    },
    'Path2D único, closePath': (anillos) => {
      const p = new Path2D();
      for (const a of anillos) { p.moveTo(...a[0]); for (let j = 1; j < a.length; j += 1) p.lineTo(...a[j]); p.closePath(); }
      return p;
    },
  };
  // 1. Build time, 20,000 square rings.
  const cuadrados = [];
  for (let i = 0; i < 20000; i += 1) {
    const x = (i % 160) * 9 + 0.3; const y = Math.floor(i / 160) * 6 + 0.7;
    cuadrados.push([[x, y], [x + 4, y], [x + 4, y + 4], [x + 1, y + 5]]);
  }
  const tiempos = {};
  for (const [nombre, f] of Object.entries(MODOS)) {
    const v = [];
    for (let k = 0; k < 3; k += 1) { const t0 = performance.now(); f(cuadrados); v.push(performance.now() - t0); }
    tiempos[nombre] = +Math.min(...v).toFixed(1);
  }
  // 2. Identity of paint against closePath.
  const anillos = [];
  for (let i = 0; i < 4000; i += 1) {
    const x = (i % 100) * 14.3 - 20.7; const y = Math.floor(i / 100) * 19.7 - 15.1;
    anillos.push([[x, y], [x + 7.3, y + 0.4], [x + 6.1, y + 8.9], [x + 0.2, y + 5.5]]);
  }
  for (let k = 0; k < 6; k += 1) {
    const cx = 200 + k * 230.5; const cy = 380.25; const R = 150 + k;
    anillos.push(Array.from({ length: 400 }, (_, j) => [cx + R * Math.cos((j / 400) * 2 * Math.PI), cy + R * Math.sin((j / 400) * 2 * Math.PI)]));
    anillos.push(Array.from({ length: 50 }, (_, j) => [cx + 40 * Math.cos((-j / 50) * 2 * Math.PI), cy + 40 * Math.sin((-j / 50) * 2 * Math.PI)]));
  }
  const enteros = [Array.from({ length: 60 }, (_, j) => [Math.round(700 + 300 * Math.cos(j / 60 * 2 * Math.PI)),
                                                        Math.round(380 + 300 * Math.sin(j / 60 * 2 * Math.PI))])];
  for (let i = 0; i < 19999; i += 1) { const x = 100 + (i % 400) * 3; const y = 40 + Math.floor(i / 400) * 14; enteros.push([[x, y + 1], [x, y]]); }
  const CONJUNTOS = { 'a: fracciones': anillos, 'b: enteros, 2 posiciones': enteros };
  const ESTILOS = {
    normal: { fillOpacity: 0.2, fillColor: '#2a78d6', color: '#2a78d6', weight: 2, dash: [] },
    discontinuo: { fillOpacity: 0.2, fillColor: '#2a78d6', color: '#2a78d6', weight: 2, dash: [3, 2] },
    seleccionado: { fillOpacity: 0.32, fillColor: '#2a78d6', color: '#111111', weight: 3, dash: [] },
  };
  const pintar = (e, dpr, f, conjunto) => {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, c.width, c.height); ctx.scale(dpr, dpr);
    const p = f(conjunto);
    ctx.globalAlpha = e.fillOpacity; ctx.fillStyle = e.fillColor;
    if (p) ctx.fill(p, 'evenodd'); else ctx.fill('evenodd');
    ctx.setLineDash(e.dash); ctx.globalAlpha = 1; ctx.lineWidth = e.weight; ctx.strokeStyle = e.color;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    if (p) ctx.stroke(p); else ctx.stroke();
    return ctx.getImageData(0, 0, c.width, c.height).data;
  };
  const identidad = [];
  for (const [nombreConjunto, conjunto] of Object.entries(CONJUNTOS)) for (const [estilo, e] of Object.entries(ESTILOS)) {
    for (const dpr of [1, 2]) {
      const base = pintar(e, dpr, MODOS.closePath, conjunto);
      let pintados = 0;
      for (let i = 3; i < base.length; i += 4) if (base[i]) pintados += 1;
      const fila = { conjunto: nombreConjunto, estilo, dpr, 'píxeles pintados (closePath)': pintados };
      for (const nombre of Object.keys(MODOS).filter((n) => n !== 'closePath' && n !== 'Path2D único, closePath')) {
        const d = pintar(e, dpr, MODOS[nombre], conjunto);
        let distintos = 0;
        for (let i = 0; i < d.length; i += 1) if (d[i] !== base[i]) distintos += 1;
        fila[`${nombre}: bytes distintos`] = distintos;
      }
      identidad.push(fila);
    }
  }
  return { tiempos, identidad };
});
console.log(`Chromium ${browser.version()}`);
console.log('Build time, 20,000 rings (ms, best of 3):');
console.table(r.tiempos);
console.log('RGBA bytes that differ from closePath() drawing:');
console.table(r.identidad);
await browser.close();

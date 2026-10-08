/* Paint comparison against the accepted renderer at the outline zoom and
 * 2 and 4 levels deeper, centred on the body's last (small) part, so that
 * small parts go from sub-pixel to several pixels. Same capture method as
 * banco.mjs (two frames, non-blank). Same environment variables.
 *
 * Exact identity and IoU of painted (alpha > 0) pixels, plus coverage with
 * a tolerance: the share of each side's painted pixels within 1 or 2 px of
 * a painted pixel of the other. Whole-pixel vertex rounding, Leaflet's 1 px
 * screen simplification and antialiasing move edges by about a pixel; a
 * missing or extra part shows as coverage well below 1.
 *
 *   node reports/team-b-display-strategy-2026-10-08/comparar-pintura.mjs [impl,...] [case,...]
 */

import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const IMPLS = (process.argv[2] ?? 'e1,e4').split(',');
const CASOS = (process.argv[3] ?? 'circulo-100k,multiparte-20000,grande-mas-19999,denso-grande-mas-19999').split(',');
const servidor = await servir({ b2: process.env.B2_DIR, casos: process.env.CASOS_DIR });
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });

async function capturas(impl, caso) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 } });
  await page.goto(`${servidor.url}/proto/banco.html?impl=${impl}`);
  await page.waitForFunction(() => document.title === 'listo');
  const salida = await page.evaluate(async (c) => {
    const b = window.__banco;
    const dos = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const esperar = async () => {
      const fin = performance.now() + 20000;
      while (['preparando', 'dibujando'].includes(b.canvas.posicionDe('contorno')?.estadoContorno)
             && performance.now() < fin) await new Promise((r) => setTimeout(r, 5));
      await dos();
    };
    const d = await b.cargar(c);
    b.canvas.render(d.filas, { colorFor: b.colorFor, geometrias: d.geometrias });
    await esperar();
    b.canvas.zoomToScale('contorno');
    await esperar();
    const z0 = b.canvas.map.getZoom();
    const anillo = d.geometrias.get(d.descriptor.id).geojson.coordinates.at(-1)[0].slice(0, -1);
    const centro = [anillo.reduce((a, q) => a + q[1], 0) / anillo.length, anillo.reduce((a, q) => a + q[0], 0) / anillo.length];
    const res = [];
    for (const extra of [0, 2, 4]) {
      b.canvas.map.setView(centro, z0 + extra, { animate: false });
      await esperar();
      const lienzo = document.querySelector('.leaflet-overlay-pane canvas');
      const { data } = lienzo.getContext('2d').getImageData(0, 0, lienzo.width, lienzo.height);
      const mascara = new Uint8Array(data.length / 4);
      let pintados = 0;
      for (let i = 3, k = 0; i < data.length; i += 4, k += 1) if (data[i]) { mascara[k] = 1; pintados += 1; }
      const h = await crypto.subtle.digest('SHA-256', data);
      res.push({ zoom: z0 + extra, pintados, sha: [...new Uint8Array(h)].slice(0, 8).map((x) => x.toString(16).padStart(2, '0')).join(''),
                 mascara: Array.from(mascara) });
    }
    return res;
  }, caso);
  await page.close();
  for (const s of salida) if (!s.pintados) throw new Error(`${impl}/${caso}: blank canvas at z${s.zoom}`);
  return salida;
}

const ANCHO = 1200;
const ALTO = 640;
/** Share of `a`'s painted pixels with a painted pixel of `b` within `r` px (square). */
function cobertura(a, b, r) {
  let total = 0; let cubiertos = 0;
  for (let y = 0; y < ALTO; y += 1) {
    for (let x = 0; x < ANCHO; x += 1) {
      if (!a[y * ANCHO + x]) continue;
      total += 1;
      let hay = false;
      for (let dy = -r; dy <= r && !hay; dy += 1) {
        const yy = y + dy;
        if (yy < 0 || yy >= ALTO) continue;
        for (let dx = -r; dx <= r; dx += 1) {
          const xx = x + dx;
          if (xx >= 0 && xx < ANCHO && b[yy * ANCHO + xx]) { hay = true; break; }
        }
      }
      if (hay) cubiertos += 1;
    }
  }
  return total ? +(cubiertos / total).toFixed(4) : 1;
}

const filas = [];
for (const caso of CASOS) {
  const base = await capturas('b2', caso);
  for (const impl of IMPLS) {
    const otra = await capturas(impl, caso);
    for (let i = 0; i < base.length; i += 1) {
      let inter = 0; let union = 0;
      const a = base[i].mascara; const b = otra[i].mascara;
      for (let k = 0; k < a.length; k += 1) { inter += a[k] & b[k]; union += a[k] | b[k]; }
      filas.push({ caso, impl, zoom: base[i].zoom, 'pintados b2': base[i].pintados, pintados: otra[i].pintados,
                   'idéntico a b2': base[i].sha === otra[i].sha, IoU: +(inter / union).toFixed(4),
                   'b2 cubierto ±1px': cobertura(a, b, 1), 'cubierto por b2 ±1px': cobertura(b, a, 1),
                   'b2 cubierto ±2px': cobertura(a, b, 2), 'cubierto por b2 ±2px': cobertura(b, a, 2) });
    }
  }
}
console.log(`Chromium ${browser.version()}`);
console.table(filas);
await browser.close();
servidor.cerrar();

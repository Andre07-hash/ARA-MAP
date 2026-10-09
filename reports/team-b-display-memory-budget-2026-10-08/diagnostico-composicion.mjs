/* Diagnose the small E5/E3 RGBA difference around translucent point symbols.
 * This is a research probe, not application code. It compares the normal
 * final canvas and a forced full redraw with circle markers suppressed.
 *
 * B2_DIR=... E1_DIR=... CASOS_DIR=... EVIDENCIA=<dir> node diagnostico-composicion.mjs
 */

import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { entorno, servir } from './servidor.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const servidor = await servir(entorno());
const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const EVIDENCIA = process.env.EVIDENCIA ?? null;

async function captura(impl, escena, dpr, sinSimbolos) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 }, deviceScaleFactor: dpr });
  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.goto(`${servidor.url}/mem/pagina.html?impl=${impl}`);
  await page.waitForFunction(() => document.title === 'listo');
  const resultado = await page.evaluate(async ({ escena, sinSimbolos }) => {
    const m = window.__m5; const c = m.canvas;
    const d = m.sinteticos({ n: escena === 'doce' ? 12 : 6, ligeros: 2, xy: 3, paso: 0.02 });
    c.render(d.filas, { colorFor: m.colorFor, geometrias: d.geometrias });
    c.fitTo(d.filas);
    const fin = performance.now() + 30000;
    const pendiente = () => d.filas.some((f) => ['preparando', 'dibujando', 'cargando'].includes(c.posicionDe(f.id)?.estadoContorno));
    while (pendiente() && performance.now() < fin) await new Promise((r) => setTimeout(r, 15));
    const ctl = c._diagnostico?.controlador;
    while (ctl && (ctl.enVuelo || (ctl.mostrada && !ctl.bitmapVigente())) && performance.now() < fin) {
      await new Promise((r) => setTimeout(r, 15));
    }
    const renderer = Object.values(c.map._layers).find((x) => x?._drawFirst);
    if (sinSimbolos) {
      for (let n = renderer?._drawFirst; n; n = n.next) {
        if (n.layer.options?.radius != null) n.layer._updatePath = () => {};
      }
      renderer._redrawBounds = null;
      renderer._redraw();
    }
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const canvas = document.querySelector('.leaflet-overlay-pane canvas');
    const rgba = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    let binario = '';
    for (let i = 0; i < rgba.length; i += 8192) binario += String.fromCharCode(...rgba.subarray(i, i + 8192));
    return { ancho: canvas.width, alto: canvas.height, rgba: btoa(binario) };
  }, { escena, sinSimbolos });
  await page.close();
  return { ...resultado, errores };
}

function diferencia(a, b) {
  if (a.ancho !== b.ancho || a.alto !== b.alto) throw new Error('canvas dimensions differ');
  const aa = Buffer.from(a.rgba, 'base64'); const bb = Buffer.from(b.rgba, 'base64');
  const primeros = []; let pixeles = 0;
  for (let i = 0; i < aa.length; i += 4) {
    if (aa.subarray(i, i + 4).equals(bb.subarray(i, i + 4))) continue;
    pixeles += 1;
    if (primeros.length < 12) {
      const p = i / 4;
      primeros.push({ x: p % a.ancho, y: Math.floor(p / a.ancho), e5: [...aa.subarray(i, i + 4)], e3: [...bb.subarray(i, i + 4)] });
    }
  }
  return { pixeles, primeros };
}

const salida = { navegador: browser.version(), resultados: [] };
let fallas = 0;
for (const dpr of [1, 2]) for (const escena of ['seis', 'doce']) {
  const e5 = await captura('e5', escena, dpr, false); const e3 = await captura('e3', escena, dpr, false);
  const e5Sin = await captura('e5', escena, dpr, true); const e3Sin = await captura('e3', escena, dpr, true);
  const normal = diferencia(e5, e3); const sinSimbolos = diferencia(e5Sin, e3Sin);
  const errores = [...e5.errores, ...e3.errores, ...e5Sin.errores, ...e3Sin.errores];
  const fila = { escena, dpr, lienzo: `${e5.ancho}x${e5.alto}`, normal, sinSimbolos, errores };
  salida.resultados.push(fila);
  const bien = sinSimbolos.pixeles === 0 && errores.length === 0;
  if (!bien) fallas += 1;
  console.log(`${bien ? 'OK' : 'FALLA'} ${escena} DPR ${dpr}: normal ${normal.pixeles} RGBA pixels; without symbols ${sinSimbolos.pixeles}`);
}
if (EVIDENCIA) {
  mkdirSync(EVIDENCIA, { recursive: true });
  writeFileSync(path.join(EVIDENCIA, 'diagnostico-composicion.json'), JSON.stringify(salida, null, 1));
}
await browser.close();
servidor.cerrar();
process.exit(fallas ? 1 : 0);

/* Paint comparison against the accepted renderer at the outline zoom and
 * 2 and 4 levels deeper, centred on the body's last (small) part, so that
 * small parts go from sub-pixel to several pixels. Same capture method as
 * banco.mjs (two frames, non-blank). Same environment variables, plus DPRS
 * (device pixel ratios, default "1,2").
 *
 * Correction F2 (supervisory review of PR #16): every capture carries its
 * real canvas width and height (Leaflet's padded canvas: 1440 x 768 at DPR 1
 * for a 1200 x 640 map, 2880 x 1536 at DPR 2); comparisons of different
 * sizes are refused and every neighbourhood uses the real stride
 * (pintura.mjs). Three measures are reported separately:
 *   - RGBA identity (complete SHA-256 of both buffers),
 *   - alpha-mask overlap (IoU of painted pixels),
 *   - tolerance coverage (share of one side's painted pixels within 1 or
 *     2 px of the other's).
 * None of them alone proves every polygon and hole is semantically correct.
 * Negative controls on every accepted-renderer capture: paint removed from
 * the region the old helper never read, and the capture moved by 1 and 3 px
 * in x and y, must change the measures as expected, or the run stops.
 *
 *   node reports/team-b-display-strategy-2026-10-08/comparar-pintura.mjs [impl,...] [case,...]
 */

import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { servir } from './servidor.mjs';
import {
  CAPTURAR, borrarDesde, cobertura, desplazar, enBorde, iou, mascaraDeCaptura, mismasDimensiones, pintados,
} from './pintura.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const IMPLS = (process.argv[2] ?? 'e1,e4').split(',');
const CASOS = (process.argv[3] ?? 'circulo-100k,multiparte-20000,grande-mas-19999,denso-grande-mas-19999').split(',');
const DPRS = (process.env.DPRS ?? '1,2').split(',').map(Number);
const SALIDA = process.env.SALIDA_JSON ?? null;
const servidor = await servir({ b2: process.env.B2_DIR, casos: process.env.CASOS_DIR });
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });

async function capturas(impl, caso, dpr) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 }, deviceScaleFactor: dpr });
  await page.goto(`${servidor.url}/proto/banco.html?impl=${impl}`);
  await page.waitForFunction(() => document.title === 'listo');
  const salida = await page.evaluate(async ([c, capturar]) => {
    const b = window.__banco;
    const tomar = (0, eval)(`(${capturar})`);
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
    // Ring-closing seam: the first position of the first ring, 3 levels deeper.
    const costura = d.geometrias.get(d.descriptor.id).geojson.coordinates[0][0][0];
    const vistas = [[0, centro, 'parte'], [2, centro, 'parte'], [4, centro, 'parte'],
                    [3, [costura[1], costura[0]], 'costura']];
    const res = [];
    for (const [extra, c, vista] of vistas) {
      b.canvas.map.setView(c, z0 + extra, { animate: false });
      await esperar();
      const estado = b.canvas.posicionDe('contorno')?.estadoContorno ?? null;
      res.push({ zoom: z0 + extra, vista, estado, ...(await tomar()) });
    }
    return res;
  }, [caso, CAPTURAR]);
  await page.close();
  for (const s of salida) {
    if (!s.pintados) throw new Error(`${impl}/${caso}/dpr ${dpr}: blank canvas at z${s.zoom}`);
    if (s.dpr !== dpr) throw new Error(`${impl}/${caso}: page DPR ${s.dpr}, asked ${dpr}`);
  }
  return salida;
}

const r4 = (v) => +v.toFixed(4);
const filas = [];
const controles = [];
let controlRegionConPintura = 0;
for (const dpr of DPRS) {
  for (const caso of CASOS) {
    const base = await capturas('b2', caso, dpr);
    // Negative controls on the accepted renderer's own captures.
    for (const c of base) {
      const a = mascaraDeCaptura(c);
      const enRegion = pintados(a) - pintados(borrarDesde(a, 1200 * 640));
      const fila = { dpr, caso, vista: c.vista, zoom: c.zoom, lienzo: `${c.ancho}x${c.alto}`, pintadosRegionOmitida: enRegion };
      if (enRegion) {
        controlRegionConPintura += 1;
        fila.coberturaSinRegion = r4(cobertura(a, borrarDesde(a, 1200 * 640), 2));
        if (fila.coberturaSinRegion >= 1) throw new Error(`control: removed region not detected ${JSON.stringify(fila)}`);
      }
      for (const [eje, dx, dy] of [['x', 1, 0], ['y', 0, 1]]) {
        const borde = enBorde(a, 4);
        const uno = cobertura(a, desplazar(a, dx, dy), 1);
        const tres2 = cobertura(a, desplazar(a, 3 * dx, 3 * dy), 2);
        const tres3 = cobertura(a, desplazar(a, 3 * dx, 3 * dy), 3);
        fila[`${eje}+1 a ±1`] = r4(uno);
        fila[`${eje}+3 a ±2`] = r4(tres2);
        fila[`${eje}+3 a ±3`] = r4(tres3);
        if (!borde && (uno !== 1 || tres3 !== 1 || tres2 >= 1)) {
          throw new Error(`control: moved-edge distances wrong ${JSON.stringify(fila)}`);
        }
      }
      controles.push(fila);
    }
    for (const impl of IMPLS) {
      const otra = await capturas(impl, caso, dpr);
      for (let i = 0; i < base.length; i += 1) {
        const a = mascaraDeCaptura(base[i]);
        const b = mascaraDeCaptura(otra[i]);
        mismasDimensiones(a, b);
        filas.push({
          dpr, caso, impl, vista: base[i].vista, zoom: base[i].zoom, lienzo: `${a.ancho}x${a.alto}`, estado: otra[i].estado,
          'pintados b2': base[i].pintados, pintados: otra[i].pintados,
          'RGBA idéntico': base[i].sha256 === otra[i].sha256,
          'IoU alfa': r4(iou(a, b)),
          'b2 cubierto ±1px': r4(cobertura(a, b, 1)), 'cubierto por b2 ±1px': r4(cobertura(b, a, 1)),
          'b2 cubierto ±2px': r4(cobertura(a, b, 2)), 'cubierto por b2 ±2px': r4(cobertura(b, a, 2)),
          'sha256 b2': base[i].sha256, sha256: otra[i].sha256,
        });
      }
    }
  }
}
if (!controlRegionConPintura) throw new Error('control: no capture had paint in the formerly omitted region');
console.log(`Chromium ${browser.version()}`);
console.log('Negative controls on the accepted renderer\'s captures (must change):');
console.table(controles);
console.table(filas.map(({ 'sha256 b2': _a, sha256: _b, ...resto }) => resto));
for (const f of filas) console.log(`${f.dpr} ${f.caso} ${f.impl} ${f.vista} z${f.zoom} b2 ${f['sha256 b2']} ${f.impl} ${f.sha256}`);
if (SALIDA) writeFileSync(SALIDA, JSON.stringify({ navegador: browser.version(), controles, filas }, null, 1));
await browser.close();
servidor.cerrar();

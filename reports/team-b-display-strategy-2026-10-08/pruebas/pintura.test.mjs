/* F2 correction checks: the paint comparison helpers use real canvas
 * dimensions (supervisory review of PR #16).
 *
 *   node --test reports/team-b-display-strategy-2026-10-08/pruebas/pintura.test.mjs
 */

import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';

const aqui = path.dirname(new URL(import.meta.url).pathname);
const p = await import(pathToFileURL(path.join(aqui, '..', 'pintura.mjs')));

const LIENZOS = [[1440, 768], [2880, 1536]];          // Leaflet's padded canvas at DPR 1 and 2

function linea(ancho, alto, { x = null, y = null }) {
  const m = p.crearMascara(ancho, alto);
  for (let k = 0; k < (x !== null ? alto : ancho); k += 1) {
    if (x !== null) m.bits[k * ancho + x] = 1; else m.bits[y * ancho + k] = 1;
  }
  return m;
}

test('masks of different sizes are refused', () => {
  const a = p.crearMascara(1440, 768);
  const b = p.crearMascara(1200, 640);
  assert.throws(() => p.iou(a, b), /sizes differ/);
  assert.throws(() => p.cobertura(a, b, 1), /sizes differ/);
  assert.throws(() => p.mascaraDeRGBA(new Uint8Array(1200 * 640 * 4), 1440, 768), /length/);
});

for (const [ancho, alto] of LIENZOS) {
  test(`${ancho}x${alto}: paint removed from the region the old helper never read is detected`, () => {
    // The old helper read only the first 1200 x 640 = 768,000 entries, with a
    // 1200 stride. Paint only beyond that index:
    const a = p.crearMascara(ancho, alto);
    for (let i = 1200 * 640; i < a.bits.length; i += 997) a.bits[i] = 1;
    const sinRegion = p.borrarDesde(a, 1200 * 640);
    assert.ok(p.pintados(a) > 0);
    assert.equal(p.cobertura(a, sinRegion, 2), 0);
    assert.ok(p.iou(a, sinRegion) < 1);
    assert.equal(p.cobertura(a, a, 0), 1);
  });

  test(`${ancho}x${alto}: moved-edge control (coverage is 1 exactly when the shift is within r)`, () => {
    for (const eje of ['x', 'y']) {
      const a = eje === 'x' ? linea(ancho, alto, { x: 300 }) : linea(ancho, alto, { y: 300 });
      for (let d = 0; d <= 4; d += 1) {
        const b = eje === 'x' ? p.desplazar(a, d, 0) : p.desplazar(a, 0, d);
        for (let r = 0; r <= 3; r += 1) {
          assert.equal(p.cobertura(a, b, r), d <= r ? 1 : 0, `${eje} shift ${d}, r ${r}`);
        }
      }
    }
  });

  test(`${ancho}x${alto}: neighbourhoods use the real stride (no wrap between rows)`, () => {
    // A pixel at the end of a row and one at the start of the next are
    // adjacent in memory but ancho - 1 pixels apart on the canvas.
    const a = p.crearMascara(ancho, alto);
    const b = p.crearMascara(ancho, alto);
    a.bits[10 * ancho + (ancho - 1)] = 1;
    b.bits[11 * ancho] = 1;
    assert.equal(p.cobertura(a, b, 2), 0);
    b.bits[11 * ancho + (ancho - 2)] = 1;                // one row down, one column left
    assert.equal(p.cobertura(a, b, 1), 1);
  });
}

test('RGBA to mask keeps alpha > 0 only, in row order', () => {
  const rgba = new Uint8Array(3 * 2 * 4);
  rgba[(1 * 3 + 2) * 4 + 3] = 1;                         // x 2, y 1
  const m = p.mascaraDeRGBA(rgba, 3, 2);
  assert.deepEqual([...m.bits], [0, 0, 0, 0, 0, 1]);
});

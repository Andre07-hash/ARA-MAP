/* DISPOSABLE prototype tests. Run from the repository root:
 *   node --test reports/team-b-files-kmz-prep-2026-10-07/experiment/ubicacion_prototype.test.mjs
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  conflictoXY, contornoAEscala, limites, modoUbicacion, particionar,
} from "./ubicacion_prototype.mjs";

const bbox = [-100.4, 20.6, -100.396, 20.603];
const geo = (extra = {}) => ({ id: "geo-1", estado: "activa", utilizable: true, bbox, ...extra });

test("boundary locates a terrain with blank X/Y", () => {
  assert.equal(modoUbicacion({ lat: null, lon: null, geometria: geo() }), "geometria");
});

test("X/Y behaviour is unchanged when there is no boundary", () => {
  assert.equal(modoUbicacion({ lat: 20.6, lon: -100.4 }), "punto");
  assert.equal(modoUbicacion({ lat: -100.4, lon: 20.6 }), "ninguna");   // swapped: invalid
  assert.equal(modoUbicacion({ lat: null, lon: null }), "ninguna");
});

test("processing, failed or unusable boundaries fall back to X/Y", () => {
  for (const g of [geo({ estado: "procesando" }), geo({ utilizable: false }), geo({ bbox: null })]) {
    assert.equal(modoUbicacion({ lat: 20.6, lon: -100.4, geometria: g }), "punto");
  }
});

test("partition keeps every terrain exactly once", () => {
  const ts = [
    { id: 1, geometria: geo() },
    { id: 2, lat: 20.7, lon: -100.5 },
    { id: 3 },
  ];
  const p = particionar(ts);
  assert.deepEqual([p.contornos, p.puntos, p.sinUbicacion].map((x) => x.map((t) => t.id)),
    [[1], [2], [3]]);
});

test("bounds cover both boundaries and points", () => {
  const b = limites([{ geometria: geo() }, { lat: 21, lon: -101 }]);
  assert.deepEqual(b, [[20.6, -101], [21, -100.396]]);
  assert.equal(limites([{}]), null);
});

test("a 400 m boundary is a symbol at country zoom and land at street zoom", () => {
  assert.equal(contornoAEscala(bbox, 6), false);
  assert.equal(contornoAEscala(bbox, 16), true);
});

test("X/Y far from the boundary is a visible conflict, never corrected", () => {
  const t = { lat: 25.0, lon: -100.4, geometria: geo() };
  assert.equal(conflictoXY(t), true);
  assert.equal(t.lat, 25.0);
  assert.equal(conflictoXY({ lat: 20.601, lon: -100.398, geometria: geo() }), false);
});

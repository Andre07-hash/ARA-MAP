/* Tests for the ground geometry. Run with: node --test tests/js/geo.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

const { groundRadius, metresPerPixel, trueScaleRadius, drawnRadius, trueScaleZoom } =
  await import("../../web/lib/geo.js");

test("a hectare is a circle of about 56.4 m radius", () => {
  // area = pi r^2  ->  r = sqrt(10000/pi) = 56.4189...
  assert.ok(Math.abs(groundRadius(10_000) - 56.4189) < 0.001);
});

test("the radius of the largest real terrain", () => {
  // El Dorado: 1,086,305.679 m2 -> 588 m across the radius.
  assert.ok(Math.abs(groundRadius(1_086_305.679) - 588.03) < 0.5);
});

test("area four times larger doubles the radius", () => {
  assert.ok(Math.abs(groundRadius(40_000) - 2 * groundRadius(10_000)) < 1e-9);
});

test("missing or nonsense areas have no radius", () => {
  for (const value of [null, undefined, 0, -5, NaN, "grande"]) {
    assert.equal(groundRadius(value), 0);
  }
});

test("metres per pixel halves with each zoom step", () => {
  const a = metresPerPixel(19.4, 10);
  const b = metresPerPixel(19.4, 11);
  assert.ok(Math.abs(a / b - 2) < 1e-9);
});

test("metres per pixel shrinks away from the equator", () => {
  assert.ok(metresPerPixel(60, 12) < metresPerPixel(0, 12));
});

test("a known scale: zoom 16 near Mexico City", () => {
  // 156543.034 * cos(19.43) / 2^16 = 2.2536 m/px
  assert.ok(Math.abs(metresPerPixel(19.43, 16) - 2.2536) < 0.001);
});

test("zoomed out, the symbol wins and the mark is not to scale", () => {
  const { radius, aEscala } = drawnRadius(64_429, 19.8, 5, 8);
  assert.equal(radius, 8);
  assert.equal(aEscala, false);
});

test("zoomed in, the true footprint wins and the mark is to scale", () => {
  const { radius, aEscala } = drawnRadius(64_429, 19.8, 17, 8);
  assert.ok(radius > 8);
  assert.equal(aEscala, true);
});

test("the handover is continuous: radius never shrinks as you zoom in", () => {
  let previo = 0;
  for (let z = 4; z <= 19; z += 1) {
    const { radius } = drawnRadius(282_211, 20.8, z, 10);
    assert.ok(radius >= previo - 1e-9, `radius fell at zoom ${z}`);
    previo = radius;
  }
});

test("a bigger terrain reaches true scale sooner", () => {
  const grande = trueScaleZoom(1_086_305, 20.7, 10);
  const chico = trueScaleZoom(28_198, 19.1, 10);
  assert.ok(grande < chico);
});

test("at true scale the drawn radius really is the ground radius", () => {
  const m2 = 250_000;          // 25 ha
  const lat = 25.7, zoom = 17;
  const { radius } = drawnRadius(m2, lat, zoom, 6);
  const metros = radius * metresPerPixel(lat, zoom);
  // Back out the area the drawn circle covers; it must match the record.
  assert.ok(Math.abs(Math.PI * metros ** 2 - m2) / m2 < 0.001);
});

test("a terrain with no area keeps its symbol at every zoom", () => {
  for (const z of [5, 12, 19]) {
    const { radius, aEscala } = drawnRadius(null, 20, z, 5);
    assert.equal(radius, 5);
    assert.equal(aEscala, false);
  }
});

test("trueScaleRadius grows by four when zooming in two steps", () => {
  const a = trueScaleRadius(100_000, 20, 12);
  const b = trueScaleRadius(100_000, 20, 14);
  assert.ok(Math.abs(b / a - 4) < 1e-9);
});

/* Coincident marks -------------------------------------------------------- */

const { coincidentRingOffsets, MAX_COINCIDENT_RINGS, COINCIDENT_STEP } =
  await import("../../web/lib/geo.js");

const at = (id, lat, lon) => ({ id, lat, lon });

test("a terrain on its own gets no ring offset", () => {
  const offsets = coincidentRingOffsets([at(1, 19.4, -99.1)]);
  assert.equal(offsets.get(1), undefined);
});

test("terrains at the same point are nudged into concentric rings", () => {
  const offsets = coincidentRingOffsets([
    at(1, 19.4, -99.1), at(2, 19.4, -99.1), at(3, 19.4, -99.1),
  ]);
  assert.equal(offsets.get(1), 0);
  assert.equal(offsets.get(2), COINCIDENT_STEP);
  assert.equal(offsets.get(3), 2 * COINCIDENT_STEP);
});

test("terrains at different points are not nudged", () => {
  const offsets = coincidentRingOffsets([at(1, 19.4, -99.1), at(2, 20.7, -103.3)]);
  assert.equal(offsets.size, 0);
});

test("a big pile at one coordinate stops growing instead of swallowing the map", () => {
  // A development recorded as 60 lots on one point must not draw a 200 px ring
  // over its neighbours. Past the cap the rings stop widening.
  const pile = Array.from({ length: 60 }, (_, i) => at(i, 25.7, -100.3));
  const offsets = coincidentRingOffsets(pile);
  const biggest = Math.max(...[...offsets.values()]);
  assert.equal(biggest, MAX_COINCIDENT_RINGS * COINCIDENT_STEP);
  assert.ok(biggest <= 30, `ring offset ${biggest} px is too wide to read`);
});

/* Symbol marks ------------------------------------------------------------- */

const { markRadius, SYMBOL_RADIUS } = await import("../../web/lib/geo.js");

const CHICO = 20_000;        // 2 ha
const GRANDE = 1_086_306;    // El Dorado, the largest real terrain
const LAT = 19.4;

test("zoomed out, every terrain is the same clean circle", () => {
  // Symbol size must NOT encode area: a small terrain drawn inside a large
  // one's symbol reads as a ring around a pin, and a screen full of nested
  // rings is what makes the overview hard to look at.
  for (const zoom of [3, 4, 5, 6, 7]) {
    const chico = markRadius(CHICO, LAT, zoom);
    const grande = markRadius(GRANDE, LAT, zoom);
    assert.equal(chico.radius, grande.radius, `zoom ${zoom} drew different sizes`);
    assert.equal(chico.radius, SYMBOL_RADIUS);
    assert.equal(chico.aEscala, false);
  }
});

test("zoomed in, size becomes the real footprint again", () => {
  const grande = markRadius(GRANDE, LAT, 14);
  assert.equal(grande.aEscala, true);
  assert.ok(grande.radius > SYMBOL_RADIUS);
  assert.ok(grande.radius > markRadius(CHICO, LAT, 14).radius);
});

test("comparison layers are still separated at the same spot", () => {
  // The concentric nudge is what shows a terrain present in two months, so it
  // must survive: only the area-based sizing goes away.
  const capa0 = markRadius(CHICO, LAT, 5, { extra: 0 });
  const capa1 = markRadius(CHICO, LAT, 5, { extra: COINCIDENT_STEP });
  assert.ok(capa1.radius > capa0.radius);
});

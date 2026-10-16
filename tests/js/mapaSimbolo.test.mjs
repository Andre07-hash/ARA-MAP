/* How a boundary symbol looks (web/components/map/MapCanvas.js).
 * Run with: node --test tests/js/mapaSimbolo.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

import { simboloStyle } from "../../web/components/map/MapCanvas.js";

test("a boundary symbol is a filled dot whether or not its outline is loaded", () => {
  const estilo = simboloStyle({ dash: null });
  assert.equal(estilo.dashArray, null);
  assert.ok(estilo.fillOpacity >= 0.8, "filled");
  const elegido = simboloStyle({ dash: null, selected: true });
  assert.equal(elegido.dashArray, null);
  assert.equal(elegido.fillOpacity, 1);
});

test("a layer's dash past the colour range still marks the symbol", () => {
  assert.equal(simboloStyle({ dash: "3 2" }).dashArray, "3 2");
});

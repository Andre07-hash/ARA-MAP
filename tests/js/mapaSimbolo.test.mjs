/* How a boundary symbol looks (web/components/map/MapCanvas.js).
 * Run with: node --test tests/js/mapaSimbolo.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

import { simboloStyle } from "../../web/components/map/MapCanvas.js";

test("a boundary symbol is a filled dot whether or not its outline is loaded", () => {
  for (const disponible of [true, false]) {
    const estilo = simboloStyle({ fill: "#1f6feb", dash: null, disponible });
    assert.equal(estilo.dashArray, null);
    assert.ok(estilo.fillOpacity >= 0.8, `filled (disponible=${disponible})`);
    const elegido = simboloStyle({ fill: "#1f6feb", dash: null, disponible, selected: true });
    assert.equal(elegido.dashArray, null);
    assert.equal(elegido.fillOpacity, 1);
  }
});

test("a layer's dash past the colour range still marks the symbol", () => {
  assert.equal(simboloStyle({ dash: "3 2" }).dashArray, "3 2");
});

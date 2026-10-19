/* How a boundary symbol looks (web/components/map/MapCanvas.js).
 * Run with: node --test tests/js/mapaSimbolo.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

import { avisoDeContorno, simboloStyle } from "../../web/components/map/MapCanvas.js";

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

test("a boundary not drawn says to click for it where a click loads it, and why otherwise", () => {
  assert.equal(avisoDeContorno("no_disponible", true), "Haz clic para ver el contorno");
  assert.equal(avisoDeContorno("no_disponible", false), "Contorno no disponible");
  assert.equal(avisoDeContorno("invalido", true), "No se pudo mostrar el contorno");
  assert.equal(avisoDeContorno("cargado", true), "");
});

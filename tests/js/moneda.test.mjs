// Every price is in pesos and is shown as MXN.
import assert from "node:assert/strict";
import test from "node:test";

import { changedFields } from "../../web/lib/comparar.js";
import { fmtPrice, fmtPriceShort, fmtUnitPrice } from "../../web/lib/format.js";

const limpio = (texto) => texto.replace(/\s/g, " ");

test("prices show as pesos, cents kept", () => {
  assert.equal(limpio(fmtPrice(388689722)), "MXN 388,689,722");
  assert.equal(limpio(fmtUnitPrice(600)), "MXN 600/m²");
  assert.equal(limpio(fmtUnitPrice(122.5)), "MXN 122.50/m²");
  assert.equal(limpio(fmtPriceShort(388689722)), "MXN 388.69 M");
});

test("a price with no recorded currency is still pesos; a missing price stays empty", () => {
  assert.equal(limpio(fmtPrice(1200, null)), "MXN 1,200");
  assert.equal(limpio(fmtPrice(1200, "USD")), "MXN 1,200");
  assert.equal(fmtPrice(null), "—");
});

test("a recorded currency alone is not a change", () => {
  const base = { asking_price: 600, moneda: null, superficie_m2: 10 };
  assert.deepEqual(changedFields(base, { ...base, moneda: "MXN" }), []);
  assert.deepEqual(changedFields(base, { ...base, asking_price: 700 }), ["Asking Price"]);
});

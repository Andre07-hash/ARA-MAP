// Prices are shown in their own currency and never ranked across currencies.
import assert from "node:assert/strict";
import test from "node:test";

import { changedFields } from "../../web/lib/comparar.js";
import { sinFiltrosDePrecio } from "../../web/lib/filters.js";
import {
  fmtPrice, fmtPriceShort, fmtUnitPrice, monedasDe, nombraMonedas,
} from "../../web/lib/format.js";

const limpio = (texto) => texto.replace(/\s/g, " ");

test("the real workbook's prices show as dollars, cents kept", () => {
  assert.equal(limpio(fmtPrice(388689722, "USD")), "USD 388,689,722");
  assert.equal(limpio(fmtUnitPrice(600, "USD")), "USD 600/m²");
  assert.equal(limpio(fmtUnitPrice(122.5, "USD")), "USD 122.50/m²");
  assert.equal(limpio(fmtPriceShort(388689722, "USD")), "USD 388.69 M");
});

test("pesos show as pesos", () => {
  assert.equal(limpio(fmtPrice(1200000, "MXN")), "MXN 1,200,000");
});

test("a price with no recorded currency says so instead of borrowing one", () => {
  assert.equal(fmtPrice(1200, null), "$1,200 · sin moneda");
  assert.equal(fmtUnitPrice(122.5, undefined), "$122.5/m² · sin moneda");
  assert.equal(fmtPrice(null, "USD"), "—");
});

test("currencies in view: unknown counts as its own, unpriced rows do not count", () => {
  assert.deepEqual(monedasDe([{ asking_price: 1, moneda: "USD" }, { asking_m2: 2, moneda: "USD" }]), ["USD"]);
  assert.deepEqual(monedasDe([{ asking_price: 1, moneda: "USD" }, { asking_price: 1, moneda: "MXN" }]),
    ["USD", "MXN"]);
  assert.deepEqual(monedasDe([{ asking_price: 1, moneda: "USD" }, { asking_price: 1 }]), ["USD", null]);
  assert.deepEqual(monedasDe([{ moneda: "MXN" }, { asking_price: null }]), []);
  assert.equal(nombraMonedas(["USD", "MXN"]), "USD y MXN");
});

test("price filters are dropped, not applied, across currencies", () => {
  const filtros = { busqueda: "x", precioMin: 1, precioMax: 2, unitarioMin: 3, unitarioMax: 4 };
  assert.deepEqual(sinFiltrosDePrecio(filtros),
    { busqueda: "x", precioMin: null, precioMax: null, unitarioMin: null, unitarioMax: null });
});

test("the same amount in another currency is a change", () => {
  const base = { asking_price: 600, moneda: "MXN", superficie_m2: 10 };
  assert.ok(changedFields(base, { ...base, moneda: "USD" }).includes("Moneda"));
  assert.deepEqual(changedFields(base, { ...base }), []);
});

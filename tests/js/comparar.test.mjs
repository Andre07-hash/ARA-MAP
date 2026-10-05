/* Tests for the comparison logic. Run with: node --test tests/js
 * Uses only Node's built-in test runner, so nothing needs installing. */

import test from "node:test";
import assert from "node:assert/strict";

const { compareLayers, changedFields, dedupeKey, summarize } =
  await import("../../web/lib/comparar.js");

const CAPAS = [{ orden: 0 }, { orden: 1 }];

function terreno(id, capa, overrides = {}) {
  return {
    id, capa,
    terreno: "El Mirador", estado: "Jalisco", municipio: "Zapopan",
    superficie_m2: 10000, asking_price: 5_000_000, asking_m2: 500,
    afectaciones_pct: null,
    ...overrides,
  };
}

const estadoDe = (salida, id) => salida.find((t) => t.id === id).comparacion.estado;

test("the first layer is the reference", () => {
  const out = compareLayers([terreno(1, 0), terreno(2, 1)], CAPAS);
  assert.equal(estadoDe(out, 1), "base");
});

test("a terrain only in the later layer is new", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { terreno: "Otro", municipio: "Tala" })], CAPAS);
  assert.equal(estadoDe(out, 2), "nuevo");
});

test("a terrain only in the reference layer is removed", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { terreno: "Otro", municipio: "Tala" })], CAPAS);
  assert.equal(estadoDe(out, 1), "eliminado");
});

test("identical values report no change", () => {
  const out = compareLayers([terreno(1, 0), terreno(2, 1)], CAPAS);
  assert.equal(estadoDe(out, 2), "sin_cambio");
});

test("a different price is reported with the field named", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { asking_price: 6_000_000 })], CAPAS);
  const comparacion = out.find((t) => t.id === 2).comparacion;
  assert.equal(comparacion.estado, "cambiado");
  assert.deepEqual(comparacion.campos, ["Asking Price"]);
});

test("several changed fields are all listed", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { asking_price: 6_000_000, asking_m2: 600 })], CAPAS);
  assert.deepEqual(out.find((t) => t.id === 2).comparacion.campos,
                   ["Asking Price", "Asking $/m²"]);
});

test("rounding under half a percent is not a change", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { asking_price: 5_010_000 })], CAPAS);
  assert.equal(estadoDe(out, 2), "sin_cambio");
});

test("matching ignores accents and case", () => {
  assert.equal(
    dedupeKey({ terreno: "Tecámac 26", estado: "Estado de México", municipio: "Tecámac" }),
    dedupeKey({ terreno: "TECAMAC 26", estado: "estado de mexico", municipio: "tecamac" }),
  );
});

test("two same-named parcels match one to one, not both to the first", () => {
  // The real pair: 260,000 and 260,076 m2, 0.03% apart.
  const pareja = (id, capa, m2) => terreno(id, capa, { terreno: "Tecámac 26", superficie_m2: m2 });
  const out = compareLayers(
    [pareja(1, 0, 260000), pareja(2, 0, 260076),
     pareja(3, 1, 260000), pareja(4, 1, 260076)], CAPAS);

  assert.equal(estadoDe(out, 3), "sin_cambio");
  assert.equal(estadoDe(out, 4), "sin_cambio");
  // Neither reference row should look removed.
  assert.equal(estadoDe(out, 1), "base");
  assert.equal(estadoDe(out, 2), "base");
});

test("genuinely different areas stay separate parcels", () => {
  // The real Tecamac 93 pair: 45 ha against 93 ha.
  const a = terreno(1, 0, { terreno: "Tecámac 93", superficie_m2: 450000 });
  const b = terreno(2, 1, { terreno: "Tecámac 93", superficie_m2: 930000 });
  const out = compareLayers([a, b], CAPAS);
  assert.equal(estadoDe(out, 2), "nuevo");
  assert.equal(estadoDe(out, 1), "eliminado");
});

test("a single layer produces no comparison at all", () => {
  const out = compareLayers([terreno(1, 0)], [{ orden: 0 }]);
  assert.equal(out[0].comparacion, null);
});

test("with three layers a removal names the layers it is missing from", () => {
  // Removal used to be withheld entirely beyond two layers, which hid real
  // disappearances. It is now reported per layer.
  const capas = [{ orden: 0, nombre: "Jul" }, { orden: 1, nombre: "Ago" },
                 { orden: 2, nombre: "Sep" }];
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { terreno: "Otro", municipio: "Tala" }),
     terreno(3, 2)], capas);

  const referencia = out.find((t) => t.id === 1).comparacion;
  assert.equal(referencia.estado, "eliminado");
  assert.deepEqual(referencia.ausenteEn, ["Ago"]);   // present in Sep, gone in Ago
});

test("the input array is not modified", () => {
  const entrada = [terreno(1, 0), terreno(2, 1)];
  const copia = JSON.parse(JSON.stringify(entrada));
  compareLayers(entrada, CAPAS);
  assert.deepEqual(entrada, copia);
});

test("changedFields reports location and address, not only money", () => {
  const izquierda = terreno(1, 0, { lat: 20, lon: -103, direccion: "Calle 1" });
  const derecha = terreno(2, 1, { lat: 21, lon: -104, direccion: "Calle 2" });
  assert.deepEqual(changedFields(izquierda, derecha), ["Ubicación", "Dirección"]);
});

test("changedFields ignores fields that are not part of the comparison", () => {
  const izquierda = terreno(1, 0);
  const derecha = terreno(2, 1, { orden: 99, id_origen: 42, extra: { x: 1 } });
  assert.deepEqual(changedFields(izquierda, derecha), []);
});

test("summarize counts each state", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { asking_price: 9_000_000 })], CAPAS);
  assert.deepEqual(summarize(out), { base: 1, cambiado: 1 });
});

/* ---- regressions from the supervisor review of 21 Sep 2026 ---- */

test("#3 three identical layers report no invented new terrain", () => {
  const capas = [{ orden: 0 }, { orden: 1 }, { orden: 2 }];
  const out = compareLayers([terreno(1, 0), terreno(2, 1), terreno(3, 2)], capas);
  assert.deepEqual(out.map((t) => t.comparacion.estado),
                   ["base", "sin_cambio", "sin_cambio"]);
});

test("#3 each layer matches the reference independently", () => {
  const capas = [{ orden: 0 }, { orden: 1 }, { orden: 2 }, { orden: 3 }];
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1), terreno(3, 2), terreno(4, 3)], capas);
  assert.ok(!out.some((t) => t.comparacion.estado === "nuevo"));
});

test("#7 a terrain that only moved is reported as changed", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { lat: 21, lon: -104 })], CAPAS);
  const c = out.find((t) => t.id === 2).comparacion;
  assert.equal(c.estado, "cambiado");
  assert.deepEqual(c.campos, ["Ubicación"]);
});

test("#7 latitude and longitude are reported once, together", () => {
  const out = compareLayers(
    [terreno(1, 0), terreno(2, 1, { lat: 21 })], CAPAS);
  assert.deepEqual(out.find((t) => t.id === 2).comparacion.campos, ["Ubicación"]);
});

test("#7 a changed address is reported", () => {
  const out = compareLayers(
    [terreno(1, 0, { direccion: "Calle 1" }),
     terreno(2, 1, { direccion: "Calle 2" })], CAPAS);
  assert.deepEqual(out.find((t) => t.id === 2).comparacion.campos, ["Dirección"]);
});

test("#7 movement under a metre is not a change", () => {
  const out = compareLayers(
    [terreno(1, 0, { lat: 20.000000 }), terreno(2, 1, { lat: 20.000005 })], CAPAS);
  assert.equal(out.find((t) => t.id === 2).comparacion.estado, "sin_cambio");
});

test("removals name the layers a terrain is missing from", () => {
  const capas = [{ orden: 0, nombre: "Jul" }, { orden: 1, nombre: "Ago" },
                 { orden: 2, nombre: "Sep" }];
  const out = compareLayers([terreno(1, 0), terreno(2, 1)], capas);
  const base = out.find((t) => t.id === 1).comparacion;
  assert.equal(base.estado, "eliminado");
  assert.deepEqual(base.ausenteEn, ["Sep"]);
});

test("a terrain present in every layer is not reported as removed", () => {
  const capas = [{ orden: 0, nombre: "Jul" }, { orden: 1, nombre: "Ago" }];
  const out = compareLayers([terreno(1, 0), terreno(2, 1)], capas);
  assert.equal(out.find((t) => t.id === 1).comparacion.estado, "base");
});

test("the closest area is paired, not merely the first within tolerance", () => {
  // Two reference rows within tolerance of each other must not pair crosswise.
  const p = (id, capa, m2) => terreno(id, capa, { terreno: "Tecámac 26", superficie_m2: m2 });
  const out = compareLayers(
    [p(1, 0, 260000), p(2, 0, 260076), p(3, 1, 260000), p(4, 1, 260076)],
    CAPAS);
  assert.equal(out.find((t) => t.id === 3).comparacion.referencia, 1);
  assert.equal(out.find((t) => t.id === 4).comparacion.referencia, 2);
});

/* Tests for the import assistant's client logic. Run with: node --test tests/js/asistente.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

const {
  aRespuestas, conservarRespuestas, createCorrectionQueue, estadoAutomatico, etiquetaFila,
  mergeCorrecciones, respuestasIniciales, todasRespondidas, vistaConsumida,
} = await import("../../web/lib/asistente.js");

const preguntas = [
  { id: "columna:a", sugerida: 0, opciones: [{}, {}] },
  { id: "decimal", sugerida: null, opciones: [{}, {}] },
];

test("suggested answers are preselected, open ones are not", () => {
  assert.deepEqual(respuestasIniciales(preguntas), { "columna:a": 0 });
  assert.equal(todasRespondidas(preguntas, respuestasIniciales(preguntas)), false);
  assert.equal(todasRespondidas(preguntas, { "columna:a": 0, decimal: 1 }), true);
});

test("answers survive a new response while their question is still open", () => {
  const kept = conservarRespuestas({ "columna:a": 1, viejo: 0 }, preguntas);
  assert.deepEqual(kept, { "columna:a": 1 });
  assert.deepEqual(aRespuestas({ decimal: 1 }), [{ pregunta: "decimal", opcion: 1 }]);
});

test("corrections merge like decisions: columns accumulate, the rest is replaced", () => {
  const merged = mergeCorrecciones(
    { columnas: { a: "extra" }, decimal: "dot" },
    { columnas: { b: "lat" }, decimal: "comma" });
  assert.deepEqual(merged, { columnas: { a: "extra", b: "lat" }, decimal: "comma" });
});

test("the queue sends one request at a time and the newest edit wins", async () => {
  const enviados = [];
  let liberar;
  const cola = createCorrectionQueue(async (parche) => {
    enviados.push(parche);
    if (enviados.length === 1) await new Promise((r) => { liberar = r; });
  });
  cola.push({ decimal: "dot" });
  cola.push({ columnas: { a: "lat" } });
  cola.push({ columnas: { a: "lon" }, decimal: "comma" });
  assert.equal(cola.ocupado, true);
  assert.equal(enviados.length, 1);        // the rest waits for the first
  liberar();
  await cola.idle();
  assert.deepEqual(enviados, [
    { decimal: "dot" },
    { columnas: { a: "lon" }, decimal: "comma" },   // coalesced; latest value wins
  ]);
  assert.equal(cola.ocupado, false);
});

test("labels", () => {
  assert.equal(etiquetaFila("csv"), "Línea");
  assert.equal(etiquetaFila("xlsx"), "Fila");
  assert.match(estadoAutomatico({ estado: "no_configurado" }), /no está configurada/);
  assert.match(estadoAutomatico({ estado: "ok", aplicadas: 3, descartadas: 1 }), /3 columna/);
  assert.match(estadoAutomatico({ estado: "ok", aplicadas: 1, descartadas: 0, proveedor: "simulado" }), /simulado/);
  assert.match(estadoAutomatico({ estado: "tiempo" }), /detección y preguntas/);
});

test("a failed confirmation says whether the preview was used up", () => {
  assert.equal(vistaConsumida({ status: 404, detalle: { vista_previa_consumida: true } }), true);
  assert.equal(vistaConsumida({ status: 409 }), true);
  assert.equal(vistaConsumida({ status: 410 }), true);
  assert.equal(vistaConsumida({ status: 500 }), true);
  // A folder refused before the token was taken: try again with another one.
  assert.equal(vistaConsumida({ status: 404, detalle: null }), false);
  assert.equal(vistaConsumida({ status: 400 }), false);
  assert.equal(vistaConsumida(null), false);
});

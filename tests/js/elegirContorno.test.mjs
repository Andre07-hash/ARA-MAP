/* Choosing a contour from the table cell (web/components/archivos/elegirContorno.js).
 * Run with: node --test tests/js/elegirContorno.test.mjs
 * Fictional names and figures only; the client is a fake. */

import test from "node:test";
import assert from "node:assert/strict";

import {
  candidatosDe, elegirYActivar, etiquetaCandidato, intentoPorElegir,
} from "../../web/components/archivos/elegirContorno.js";

test("a candidate is named first, then its area in ha and m², then its folder", () => {
  const texto = etiquetaCandidato({ indice: 1, nombre: "Lote Norte", carpeta: ["Rancho Ficticio"],
    partes: 1, area_aproximada_m2: 12345, valido: true });
  assert.match(texto, /^Lote Norte · /, "its own name first");
  assert.match(texto, /ha \(12,345 m²\) · Rancho Ficticio$/);
  assert.equal(etiquetaCandidato({ indice: 2, nombre: null, partes: 3, area_aproximada_m2: null }),
    "Contorno 3 · 3 partes", "unnamed and invalid: its number and parts");
});

test("the candidates of an attempt, or none", () => {
  assert.deepEqual(candidatosDe({ resultado_detalle: { candidatos: [{ indice: 0 }] } }), [{ indice: 0 }]);
  assert.deepEqual(candidatosDe(null), []);
});

function clienteFalso({ procesado, activado = { archivo: { revision: 3 } } } = {}) {
  const llamadas = [];
  return {
    llamadas,
    procesar: async (...a) => { llamadas.push(["procesar", ...a]); return procesado; },
    activar: async (...a) => { llamadas.push(["activar", ...a]); return activado; },
    intentos: async (...a) => { llamadas.push(["intentos", ...a]); return { intentos: [{ id: "i-2", resultado: "requiere_seleccion" }] }; },
    intento: async (...a) => { llamadas.push(["intento", ...a]); return { id: "i-2" }; },
  };
}

test("Listo processes the selection and activates its boundary at the attachment's revision", async () => {
  const cliente = clienteFalso({ procesado: { geometria_id: "g-1", intento: { resultado: "listo" }, archivo: { revision: 2 } } });
  await elegirYActivar(cliente, { versionId: "v-1", archivoId: "a-1", revision: 1, seleccion: [0, 2], claves: new Map() });
  assert.deepEqual(cliente.llamadas.map((l) => l[0]), ["procesar", "activar"]);
  assert.deepEqual(cliente.llamadas[0].slice(1, 3), ["v-1", [0, 2]]);
  // The revision the list was shown at, not the fresher one the processing reply carries:
  // a file changed meanwhile must be a conflict, not a silent replacement.
  assert.deepEqual(cliente.llamadas[1].slice(1, 3), ["a-1", { versionId: "v-1", geometriaId: "g-1", revision: 1 }]);
});

test("after a failed activation, a retry activates again without processing the selection again", async () => {
  const claves = new Map();
  const cliente = clienteFalso({ procesado: { geometria_id: "g-1", intento: { resultado: "listo" } } });
  let falla = true;
  cliente.activar = async (...a) => {
    cliente.llamadas.push(["activar", ...a]);
    if (falla) { falla = false; throw new Error("red"); }
    return { archivo: { revision: 5 } };
  };
  const datos = { versionId: "v-1", archivoId: "a-1", revision: 4, seleccion: [1], claves };
  await assert.rejects(elegirYActivar(cliente, datos));
  await elegirYActivar(cliente, datos);
  assert.deepEqual(cliente.llamadas.map((l) => l[0]), ["procesar", "activar", "activar"]);
  const [primera, segunda] = cliente.llamadas.filter((l) => l[0] === "activar");
  assert.equal(primera[3], segunda[3], "the activation retry reuses its key");
  assert.deepEqual(segunda[2], { versionId: "v-1", geometriaId: "g-1", revision: 4 });
  assert.equal(claves.size, 0, "nothing kept once it succeeded");
});

test("a selection that yields no usable contour activates nothing and says why", async () => {
  const cliente = clienteFalso({ procesado: { geometria_id: null, intento: { resultado: "rechazado",
    resultado_detalle: { error: { mensaje: "El contorno se cruza a sí mismo." } } } } });
  await assert.rejects(
    elegirYActivar(cliente, { versionId: "v-1", archivoId: "a-1", revision: 1, seleccion: [1], claves: new Map() }),
    /se cruza a sí mismo/);
  assert.deepEqual(cliente.llamadas.map((l) => l[0]), ["procesar"]);
});

test("a retried step reuses its idempotency key until it succeeds", async () => {
  const claves = new Map();
  let falla = true;
  const cliente = clienteFalso({ procesado: { geometria_id: "g-1", intento: { resultado: "listo" } } });
  const procesar = cliente.procesar;
  cliente.procesar = async (...a) => { if (falla) { falla = false; cliente.llamadas.push(["procesar", ...a]); throw new Error("red"); } return procesar(...a); };
  const datos = { versionId: "v-1", archivoId: "a-1", revision: 1, seleccion: [0], claves };
  await assert.rejects(elegirYActivar(cliente, datos));
  await elegirYActivar(cliente, datos);
  const [primera, segunda] = cliente.llamadas.filter((l) => l[0] === "procesar");
  assert.equal(primera[3], segunda[3], "same key for the same selection");
  assert.equal(claves.size, 0, "keys are dropped once each step succeeds");
});

test("an earlier upload's candidates come from its latest attempt, only when it asks for a choice", async () => {
  const cliente = clienteFalso();
  assert.deepEqual(await intentoPorElegir(cliente, "v-1"), { id: "i-2" });
  cliente.intentos = async () => ({ intentos: [{ id: "i-3", resultado: "rechazado" }] });
  assert.equal(await intentoPorElegir(cliente, "v-1"), null);
});

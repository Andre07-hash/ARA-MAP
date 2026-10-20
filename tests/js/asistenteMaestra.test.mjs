/* The master-table assistant's client (issue #69) against a stubbed fetch
 * with fictional contract answers. No DOM: the panel is checked in the
 * browser (tests/e2e/tabla-asistente-maestra.mjs).
 * Run with: node --test tests/js/asistenteMaestra.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

const { abortPrivate } = await import("../../web/lib/api.js");
const {
  MAX_SELECCION, crearBusqueda, validarBusqueda, validarComparacion,
} = await import("../../web/lib/asistenteMaestra.js");

const id = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const json = (status, cuerpo) => new Response(JSON.stringify(cuerpo), {
  status, headers: { "Content-Type": "application/json" },
});
const terreno = (n) => ({ terreno_id: id(n), version: 1, nombre: `Lote ${n}`, base_id: null,
  campos_usados: [{ campo: "estado", etiqueta: "Estado", valor: "Estado Ficticio" }] });
const pagina = (desde, hasta, cursor, total = 23, origen = "modelo") => ({
  estado: "resultados", origen, criterios: [{ campo: "estado", texto: "Estado: Estado Ficticio" }],
  filtros: { estado: ["Estado Ficticio"] }, total, next_cursor: cursor,
  terrenos: Array.from({ length: hasta - desde }, (_, i) => terreno(desde + i)),
});
const comparacion = (ids) => ({
  terrenos: ids.map((i, n) => ({ alias: "ABC"[n], terreno_id: id(i), version: 1, nombre: `Lote ${i}`, base_id: null })),
  filas: [{ campo: "estado", etiqueta: "Estado", valores: ids.map(() => "Estado Ficticio") }],
  advertencias: [], resumen: { estado: "ok", texto: "Resumen ficticio.", origen: "modelo" },
});

let llamadas = [];
let responder = () => json(200, pagina(0, 10, "c1"));
globalThis.fetch = (ruta, opciones) => {
  llamadas.push({ ruta, cuerpo: opciones?.body ? JSON.parse(opciones.body) : null });
  return new Promise((resolve, reject) => {
    opciones?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    Promise.resolve(responder(ruta, opciones)).then(resolve, reject);
  });
};
test.beforeEach(() => { llamadas = []; responder = () => json(200, pagina(0, 10, "c1")); });

const listo = (b) => new Promise((resolve) => {
  const mirar = () => (b.estado.fase === "inactivo" ? resolve(b.estado) : setTimeout(mirar, 1));
  mirar();
});
function retenida() {
  let soltar;
  const espera = new Promise((r) => { soltar = r; });
  return { espera, soltar: (respuesta) => soltar(respuesta) };
}

test("a search, its pages and the real total", async () => {
  const b = crearBusqueda();
  assert.equal(b.buscar("  industriales en Jalisco  "), true);
  let s = await listo(b);
  assert.deepEqual(llamadas.map((l) => [l.ruta, l.cuerpo]), [
    ["/api/asistente-terreno/buscar", { pregunta: "industriales en Jalisco" }]]);
  assert.equal(s.busqueda.total, 23);
  assert.equal(s.busqueda.terrenos.length, 10);
  responder = () => json(200, pagina(10, 20, "c2", 23, "reglas"));
  b.mas();
  s = await listo(b);
  responder = () => json(200, pagina(20, 23, null, 23, "reglas"));
  b.mas();
  s = await listo(b);
  assert.equal(s.busqueda.terrenos.length, 23);
  assert.equal(s.busqueda.next_cursor, null);
  assert.equal(b.mas(), false);
  // Pages send the filters back as received, with the cursor; never the question.
  assert.deepEqual(llamadas.slice(1).map((l) => l.cuerpo), [
    { filtros: { estado: ["Estado Ficticio"] }, cursor: "c1" },
    { filtros: { estado: ["Estado Ficticio"] }, cursor: "c2" }]);
});

test("a clarification is shown as one, with no list", async () => {
  responder = () => json(200, { estado: "aclaracion", aclaracion: "¿Total o por m²?", origen: "modelo" });
  const b = crearBusqueda();
  b.buscar("barato");
  const s = await listo(b);
  assert.deepEqual(s.busqueda, { estado: "aclaracion", aclaracion: "¿Total o por m²?", origen: "modelo", pregunta: "barato" });
  assert.equal(b.mas(), false);
  assert.equal(b.alternar(id(1)), false);
});

test("answers that do not match the contract are refused", () => {
  assert.equal(validarBusqueda(null), null);
  assert.equal(validarBusqueda({ ...pagina(0, 1, null), origen: "simulado" }), null);
  assert.equal(validarBusqueda({ ...pagina(0, 1, null), total: "1" }), null);
  assert.equal(validarBusqueda({ ...pagina(0, 1, null), filtros: [] }), null);
  assert.equal(validarBusqueda({ ...pagina(0, 1, null), terrenos: [{ terreno_id: 5 }] }), null);
  assert.equal(validarBusqueda({ estado: "aclaracion", aclaracion: " ", origen: "reglas" }), null);
  const sel = [terreno(1), terreno(2)];
  assert.equal(validarComparacion(comparacion([2, 1]), sel), null);                // another order
  assert.equal(validarComparacion({ ...comparacion([1, 2]), filas: [] }, sel), null);
  assert.equal(validarComparacion({ ...comparacion([1, 2]),
    filas: [{ etiqueta: "Estado", valores: ["x"] }] }, sel), null);                // a missing value
  const sinResumen = validarComparacion({ ...comparacion([1, 2]),
    resumen: { estado: "ok", texto: "x", origen: "reglas" } }, sel);
  assert.deepEqual(sinResumen.resumen, { estado: "error", codigo: null });      // never shown as Claude
});

test("two or three are selected, never more, and compared by id and version", async () => {
  const b = crearBusqueda();
  b.buscar("algo");
  await listo(b);
  assert.equal(b.comparar(), false);
  for (const n of [0, 1, 2]) assert.equal(b.alternar(id(n)), true);
  assert.equal(b.alternar(id(3)), false);
  assert.equal(b.estado.seleccion.length, MAX_SELECCION);
  assert.equal(b.alternar(id(99)), false);                  // not a result
  b.alternar(id(2));
  responder = () => json(200, comparacion([0, 1]));
  b.comparar();
  const s = await listo(b);
  assert.deepEqual(llamadas.at(-1).cuerpo, { terrenos: [{ id: id(0), version: 1 }, { id: id(1), version: 1 }] });
  assert.equal(s.comparacion.resumen.texto, "Resumen ficticio.");
  b.alternar(id(1));
  assert.equal(b.estado.comparacion, null);                 // a changed selection drops it
});

test("one request at a time; a late answer after a new action or giving up is dropped", async () => {
  const r = retenida();
  responder = () => r.espera;
  const b = crearBusqueda();
  b.buscar("primera");
  assert.equal(b.buscar("segunda"), false);
  b.dejarDeEsperar();
  r.soltar(json(200, pagina(0, 10, null)));
  await new Promise((done) => setTimeout(done, 5));
  assert.equal(b.estado.busqueda, null);
  assert.equal(llamadas.length, 1);
});

test("errors keep their code; the session's end and destroy drop everything", async () => {
  responder = () => json(409, { error: "x", detalle: { code: "conflict" } });
  const b = crearBusqueda();
  b.buscar("algo");
  let s = await listo(b);
  assert.equal(s.error.status, 409);
  assert.equal(s.error.de, "buscando");
  const r = retenida();
  responder = () => r.espera;
  const cambios = [];
  const c = crearBusqueda({ onCambio: (e) => cambios.push(e.fase) });
  c.buscar("algo");
  abortPrivate();
  r.soltar(json(200, pagina(0, 1, null)));
  await new Promise((done) => setTimeout(done, 5));
  assert.equal(c.estado.busqueda, null);
  c.destroy();
  assert.equal(c.estado.fase, "inactivo");
  assert.equal(c.buscar("otra"), false);
  s = b.estado;
  assert.equal(s.busqueda, null);
});

test("a refused new comparison never leaves the previous one as current", async () => {
  for (const [status, code] of [[409, "conflict"], [404, "not_found"]]) {
    responder = () => json(200, pagina(0, 10, null));
    const b = crearBusqueda();
    b.buscar("algo");
    await listo(b);
    b.alternar(id(0));
    b.alternar(id(1));
    responder = () => json(200, comparacion([0, 1]));
    b.comparar();
    assert.ok((await listo(b)).comparacion, "first comparison");
    const r = retenida();
    responder = () => r.espera;
    b.comparar();
    assert.equal(b.estado.comparacion, null, "dropped as soon as the new one starts");
    r.soltar(json(status, { error: "x", detalle: { code } }));
    const s = await listo(b);
    assert.equal(s.comparacion, null);
    assert.equal(s.error.status, status);
    assert.equal(s.error.de, "comparando");
  }
});

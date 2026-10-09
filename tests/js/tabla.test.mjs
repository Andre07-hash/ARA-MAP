/* The employee table's rules (web/lib/tabla.js). Run with: node --test tests/js/tabla.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

import {
  COLUMNAS_BASICAS, columnasDe, consultaDeLista, crearCola, cuerpoDeCelda, esEditable, esFechaReal,
  leerCelda, resolverIncierto, rutaDeLista, valorDe,
} from "../../web/lib/tabla.js";
import { defaultRoute, parseRoute, routeAllowed, routeHash } from "../../web/lib/router.js";

const BASE = "0b0e7d0c-5a43-4c0e-9d2f-1f1f1f1f1f1f";
const col = (id) => COLUMNAS_BASICAS.find((c) => c.id === id);
const CUSTOM = [
  { id: "custom:a", nombre: "Nota", tipo: "texto", opciones: [], retirada: false },
  { id: "custom:b", nombre: "Etapa", tipo: "opcion", opciones: ["En curso", "Cerrado"], retirada: false },
  { id: "custom:c", nombre: "Vieja", tipo: "numero", opciones: [], retirada: true },
];

test("the fourteen core columns, in order; X is latitude and Y is longitude", () => {
  assert.deepEqual(COLUMNAS_BASICAS.map((c) => c.etiqueta), ["Tipo de terreno", "Nombre de terreno", "Estado",
    "Municipio", "Superficie", "HA", "Afectaciones %", "Asking price", "Asking $/m2", "Comentarios", "X", "Y",
    "Archivos", "KMZ"]);
  assert.equal(col("core:lat").etiqueta, "X");
  assert.equal(col("core:lon").etiqueta, "Y");
  assert.deepEqual(COLUMNAS_BASICAS.filter((c) => !esEditable(c)).map((c) => c.id), ["core:archivos", "core:kmz"]);
});

test("the global table shows Base and no custom column; a base shows its live ones", () => {
  for (const vista of ["maestra", "sin_asignar"]) {
    const ids = columnasDe(vista, CUSTOM).map((c) => c.id);
    assert.equal(ids.length, 15);
    assert.equal(ids.at(-1), "base");
  }
  assert.deepEqual(columnasDe(BASE, CUSTOM).slice(14).map((c) => c.id), ["custom:a", "custom:b"]);
});

test("a cell reads what was typed and converts nothing", () => {
  assert.deepEqual(leerCelda(col("core:superficie_m2"), "12,500"), { valor: 12500 });
  assert.deepEqual(leerCelda(col("core:lon"), " -103.4 "), { valor: -103.4 });
  assert.deepEqual(leerCelda(col("core:asking_price"), ""), { valor: null });      // empty clears; never zero
  assert.ok(leerCelda(col("core:asking_price"), "12,5").error);
  assert.ok(leerCelda(col("core:asking_price"), "caro").error);
  assert.deepEqual(leerCelda(col("core:terreno"), "  Lote   Ñandú "), { valor: "Lote Ñandú" });
  assert.deepEqual(leerCelda(col("core:notas_internas"), " uno\n dos "), { valor: "uno\n dos" });
  assert.ok(leerCelda(col("core:estado"), "x".repeat(101)).error);
  const [nota, etapa] = columnasDe(BASE, CUSTOM).slice(14);
  assert.deepEqual(leerCelda(nota, "  a  b "), { valor: "a  b" });                    // custom text is trimmed only
  assert.deepEqual(leerCelda(etapa, "Cerrado"), { valor: "Cerrado" });
  assert.deepEqual(leerCelda(etapa, ""), { valor: null });
  assert.ok(leerCelda(etapa, "cerrado").error);
  const fecha = { id: "custom:f", tipo: "fecha", custom: true };
  assert.deepEqual(leerCelda(fecha, "2024-02-29"), { valor: "2024-02-29" });
  for (const mala of ["2023-02-29", "2024-13-01", "29/02/2024", "2024-2-9", "0000-01-01"]) {
    assert.ok(leerCelda(fecha, mala).error, mala);
  }
  assert.ok(esFechaReal("0099-12-31"));
});

test("a cell's body names one field and the version it was edited at", () => {
  assert.deepEqual(cuerpoDeCelda(col("core:estado"), "Jalisco", 4),
    { expected_version: 4, changes: { estado: "Jalisco" } });
  assert.deepEqual(cuerpoDeCelda({ id: "custom:a", custom: true }, null, 2),
    { expected_version: 2, custom: { "custom:a": null } });
});

test("a list query is one bounded page; filters and order are the server's", () => {
  assert.equal(consultaDeLista(BASE, {}), "limit=100");
  assert.equal(consultaDeLista("sin_asignar", { q: " lote ", sort: "-terreno", estado: "Jalisco", limit: 200,
    incluirArchivados: true }, "CUR"),
  "q=lote&estado=Jalisco&include_archived=true&base=sin_asignar&sort=-terreno&limit=200&cursor=CUR");
  assert.equal(consultaDeLista(BASE, { limit: 5000 }), "limit=100");               // never more than the maximum
  assert.equal(rutaDeLista("maestra"), "/inventario/terrenos");
  assert.equal(rutaDeLista(BASE), `/maestra/bases/${BASE}/terrenos`);
});

test("saves of one row run in order; other rows do not wait; a failure does not block the row", async () => {
  const cola = crearCola();
  const orden = [];
  let soltar;
  const lento = new Promise((r) => { soltar = r; });
  const a1 = cola.enFila("a", async () => { await lento; orden.push("a1"); throw new Error("falló"); });
  const a2 = cola.enFila("a", async () => { orden.push("a2"); return 2; });
  const b1 = cola.enFila("b", async () => { orden.push("b1"); });
  await b1;
  assert.deepEqual(orden, ["b1"]);
  soltar();
  await assert.rejects(a1, /falló/);
  assert.equal(await a2, 2);
  assert.deepEqual(orden, ["b1", "a1", "a2"]);
  await Promise.resolve();
  assert.equal(cola.pendientes(), 0);
});

test("an unanswered save is resolved from the row, never replayed blindly", () => {
  const estado = col("core:estado");
  const fila = (version, valor) => ({ version, draft: { estado: valor }, custom: {} });
  assert.equal(resolverIncierto(estado, "Colima", 3, fila(3, "Jalisco")), "sin_guardar");
  assert.equal(resolverIncierto(estado, "Colima", 3, fila(4, "Colima")), "guardado");
  assert.equal(resolverIncierto(estado, "Colima", 3, fila(4, "Sonora")), "conflicto");
  assert.equal(resolverIncierto(estado, "Colima", 3, fila(6, "Colima")), "conflicto");
  assert.equal(resolverIncierto(estado, null, 3, fila(4, undefined)), "guardado");
  assert.equal(valorDe({ custom: { "custom:a": 7 } }, { id: "custom:a", custom: true }), 7);
});

test("routes: the table has an address; operators have the table and the catalog only", () => {
  assert.deepEqual(parseRoute("#/tabla"), { nombre: "tabla", id: null });
  assert.deepEqual(parseRoute(`#/tabla/${BASE}`), { nombre: "tabla", id: BASE });
  assert.equal(routeHash({ nombre: "tabla", id: "maestra" }), "#/tabla/maestra");
  assert.equal(parseRoute("#/tabla/a/b"), null);
  assert.equal(defaultRoute(true, "operador").nombre, "tabla");
  assert.equal(defaultRoute(true, "admin").nombre, "inventario");
  assert.equal(defaultRoute(false).nombre, "catalogo");
  for (const nombre of ["inventario", "nuevo", "editar", "bases", "mapas", "mapa"]) {
    assert.equal(routeAllowed({ nombre }, "operador"), false, nombre);
    assert.equal(routeAllowed({ nombre }, "admin"), true, nombre);
  }
  assert.ok(routeAllowed({ nombre: "tabla" }, "operador") && routeAllowed({ nombre: "catalogo" }, "operador"));
});

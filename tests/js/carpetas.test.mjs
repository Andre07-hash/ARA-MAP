/* Tests for folder navigation logic. Run with: node --test tests/js/carpetas.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

const {
  SIN_CARPETA, TODAS, defaultDestination, filterByFolder, folderCounts, folderNameOf,
  resolveSelection, selectionLabel, withFolder,
} = await import("../../web/lib/carpetas.js");

const carpetas = [{ id: 3, nombre: "Cliente Norte" }, { id: 9, nombre: "Vacía" }];
const items = [
  { id: 1, nombre: "Agosto", carpeta_id: 3 },
  { id: 2, nombre: "Septiembre", carpeta_id: null },
  { id: 4, nombre: "Octubre", carpeta_id: 3 },
  { id: 5, nombre: "Huérfana", carpeta_id: 77 },   // its folder was deleted elsewhere
];

test("all, unfiled and a named folder filter without reordering", () => {
  assert.deepEqual(filterByFolder(items, TODAS).map((i) => i.id), [1, 2, 4, 5]);
  assert.deepEqual(filterByFolder(items, SIN_CARPETA).map((i) => i.id), [2]);
  assert.deepEqual(filterByFolder(items, 3).map((i) => i.id), [1, 4]);
  assert.deepEqual(filterByFolder(items, 9), []);
});

test("filtering never replaces the full list", () => {
  const copia = [...items];
  filterByFolder(items, 3);
  assert.deepEqual(items, copia);
});

test("counts include empty folders and count items once", () => {
  const counts = folderCounts(items, carpetas);
  assert.equal(counts.todas, 4);
  assert.equal(counts.sinCarpeta, 1);
  assert.equal(counts.porCarpeta.get(3), 2);
  assert.equal(counts.porCarpeta.get(9), 0);
});

test("a selection that no longer exists falls back to unfiled, not all", () => {
  assert.equal(resolveSelection(3, carpetas), 3);
  assert.equal(resolveSelection(77, carpetas), SIN_CARPETA);
  assert.equal(resolveSelection(SIN_CARPETA, carpetas), SIN_CARPETA);
  assert.equal(resolveSelection(TODAS, []), TODAS);
  assert.equal(resolveSelection(undefined, carpetas), TODAS);
});

test("labels for views and items", () => {
  assert.equal(selectionLabel("bases", TODAS, carpetas), "Todas las bases");
  assert.equal(selectionLabel("mapas", TODAS, carpetas), "Todos los mapas");
  assert.equal(selectionLabel("mapas", SIN_CARPETA, carpetas), "Sin carpeta");
  assert.equal(selectionLabel("bases", 3, carpetas), "Cliente Norte");
  assert.equal(folderNameOf(items[0], carpetas), "Cliente Norte");
  assert.equal(folderNameOf(items[1], carpetas), "Sin carpeta");
});

test("creation defaults to the open folder, never to all/unfiled", () => {
  assert.equal(defaultDestination(3), 3);
  assert.equal(defaultDestination(TODAS), null);
  assert.equal(defaultDestination(SIN_CARPETA), null);
});

test("a move patches one item by id and leaves the rest alone", () => {
  const movidos = withFolder(items, 2, 9);
  assert.equal(movidos.find((i) => i.id === 2).carpeta_id, 9);
  assert.equal(items.find((i) => i.id === 2).carpeta_id, null);  // original untouched
  assert.deepEqual(movidos.filter((i) => i.id !== 2), items.filter((i) => i.id !== 2));
});

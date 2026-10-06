/* Stage 2 publication helpers and requests.
 * Run with: node --test tests/js/publicacion.test.mjs */

import assert from "node:assert/strict";
import test from "node:test";

import { api } from "../../web/lib/api.js";
import {
  accionesDePublicacion, avisoDisponibilidadPendiente, cambiosPendientes, estadoPublicacion,
  normalizarEvento, valorPendiente,
} from "../../web/lib/inventario.js";

const base = {
  id: "t1", version: 4, draft_revision_id: "r4", published_revision_id: "r2",
  publication_state: "published", public_visible: true, has_pending_changes: true,
  archived_at: null, draft: { terreno: "Lote", availability: "available", asking_m2: 130.25 },
  pending_changes: {
    direccion: { published: "Calle 1", draft: "Calle 2" },
    asking_m2: { published: 122.5, draft: 130.25 },
  },
};

test("pending changes come from the server and put price and availability first", () => {
  const cambios = cambiosPendientes(base);
  assert.deepEqual(cambios.map((c) => [c.clave, c.destacado]), [["asking_m2", true], ["direccion", false]]);
  assert.equal(cambios[0].etiqueta, "Asking $/m²");
  assert.equal(valorPendiente("asking_m2", 122.5), "122.5");
  assert.equal(valorPendiente("availability", "sold"), "Vendido");
  assert.deepEqual(cambiosPendientes({ ...base, pending_changes: {} }), []);
});

test("a published sold revision is labelled out of the catalog by the PUBLISHED availability", () => {
  const vendido = { ...base, public_visible: false, has_pending_changes: false, pending_changes: {},
    draft: { ...base.draft, availability: "sold" } };
  assert.equal(estadoPublicacion(vendido).etiqueta, "Fuera del catálogo · Vendido");
  // Saved back to available but not yet published: still out, still says why.
  const vuelta = { ...vendido, has_pending_changes: true,
    pending_changes: { availability: { published: "sold", draft: "available" } },
    draft: { ...base.draft, availability: "available" } };
  assert.equal(estadoPublicacion(vuelta).etiqueta, "Fuera del catálogo · Vendido");
  // A saved sold draft over a live revision: still live, with the warning.
  const pendiente = { ...base, pending_changes: { availability: { published: "available", draft: "sold" } },
    draft: { ...base.draft, availability: "sold" } };
  assert.equal(estadoPublicacion(pendiente).etiqueta, "Publicado · Cambios pendientes");
  assert.match(avisoDisponibilidadPendiente(pendiente), /«Vendido»/);
});

test("lifecycle actions offered match the state; restore only when archived", () => {
  assert.deepEqual(accionesDePublicacion(base), { vistaPrevia: true, retirar: true, archivar: true, restaurar: false });
  assert.deepEqual(accionesDePublicacion({ publication_state: "draft" }),
    { vistaPrevia: true, retirar: false, archivar: true, restaurar: false });
  assert.deepEqual(accionesDePublicacion({ publication_state: "archived", archived_at: "x" }),
    { vistaPrevia: false, retirar: false, archivar: false, restaurar: true });
});

test("history names every lifecycle action", () => {
  const nombres = ["publish", "unpublish", "archive", "restore"].map((action) =>
    normalizarEvento({ action, actor: { display_name: "Ana" }, changes: {} }).accion);
  assert.deepEqual(nombres, ["Publicó", "Retiró del catálogo", "Archivó", "Restauró"]);
});

test("publish sends exactly the reviewed version and revision; the others only the version", async () => {
  const calls = [];
  globalThis.fetch = (url, options = {}) => {
    calls.push({ url, options });
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ terreno: base }) });
  };
  await api.vistaPublica("t1", "r4");
  await api.publicar("t1", 4, "r4");
  await api.despublicar("t1", 5);
  await api.archivar("t1", 6);
  await api.restaurar("t1", 7);
  assert.deepEqual(calls.map((c) => [c.options.method ?? "GET", c.url]), [
    ["GET", "/api/inventario/terrenos/t1/vista-publica?revision_id=r4"],
    ["POST", "/api/inventario/terrenos/t1/publicar"],
    ["POST", "/api/inventario/terrenos/t1/despublicar"],
    ["POST", "/api/inventario/terrenos/t1/archivar"],
    ["POST", "/api/inventario/terrenos/t1/restaurar"],
  ]);
  assert.deepEqual(calls.slice(1).map((c) => JSON.parse(c.options.body)), [
    { expected_version: 4, revision_id: "r4" }, { expected_version: 5 },
    { expected_version: 6 }, { expected_version: 7 },
  ]);
});

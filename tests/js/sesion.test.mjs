/* Routing, the private request scope and session clearing.
 * Run with: node --test tests/js/sesion.test.mjs */

import assert from "node:assert/strict";
import test from "node:test";

import { abortPrivate, api, onSessionExpired } from "../../web/lib/api.js";
import { defaultRoute, isPrivateRoute, parseRoute, routeHash } from "../../web/lib/router.js";
import { clearPrivateState, DATASET_VACIO, getState, setState } from "../../web/lib/store.js";
import { fixture } from "./fixtures/inventario/index.mjs";

/* ----------------------------------------------------------------- routes */

test("every route round-trips through its hash", () => {
  for (const ruta of [
    { nombre: "catalogo", id: null }, { nombre: "catalogo", id: "a b/ñ" },
    { nombre: "inventario", id: null }, { nombre: "inventario", id: "3f1c" },
    { nombre: "editar", id: "3f1c" }, { nombre: "nuevo", id: null },
    { nombre: "bases", id: null }, { nombre: "mapas", id: null }, { nombre: "mapa", id: null },
  ]) {
    assert.deepEqual(parseRoute(routeHash(ruta)), ruta, routeHash(ruta));
  }
});

test("only the catalog is public; anonymous lands on it, signed-in on the inventory", () => {
  assert.equal(isPrivateRoute({ nombre: "catalogo" }), false);
  for (const nombre of ["inventario", "editar", "nuevo", "bases", "mapas", "mapa"]) {
    assert.equal(isPrivateRoute({ nombre }), true, nombre);
  }
  assert.equal(defaultRoute(false).nombre, "catalogo");
  assert.equal(defaultRoute(true).nombre, "inventario");
});

test("unknown or malformed hashes are not routes", () => {
  for (const hash of ["", "#", "#/", "#/admin", "#/bases/3", "#/inventario/x/borrar", "#/catalogo/%E0%A4%A"]) {
    assert.equal(parseRoute(hash), null, hash);
  }
});

/* ------------------------------------------------------------ the network */

function stubFetch(responder) {
  const calls = [];
  globalThis.fetch = (url, options = {}) => {
    calls.push({ url, options });
    return responder(url, options);
  };
  return calls;
}

const json = (status, body) => Promise.resolve({
  ok: status < 400, status, json: async () => body,
});

/* Resolves with what a promise did within a few ticks: "settled" or "pending". */
const settles = (promise) => Promise.race([
  promise.then(() => "settled", () => "settled"),
  new Promise((r) => setTimeout(() => r("pending"), 30)),
]);

test("ending the session cancels private requests; their callers never see a response", async () => {
  const calls = stubFetch((url, { signal }) => new Promise((resolve, reject) => {
    signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
  }));
  const privada = api.inventarioTerrenos(new URLSearchParams(), null);
  const legado = api.bases();
  abortPrivate();
  assert.equal(await settles(privada), "pending");
  assert.equal(await settles(legado), "pending");
  assert.equal(calls.length, 2);
});

test("a private response that lands after logout is dropped, not delivered", async () => {
  let entregar;
  stubFetch(() => new Promise((resolve) => { entregar = resolve; }));
  const pendiente = api.inventarioTerreno("3f1c");
  abortPrivate();
  entregar({ ok: true, status: 200, json: async () => fixture("internal-terrain-draft") });
  assert.equal(await settles(pendiente), "pending");
});

test("public requests are outside the private scope", async () => {
  const calls = stubFetch(() => json(200, fixture("public-list-empty")));
  const publica = api.publicoTerrenos(new URLSearchParams("estado=Jalisco"), null);
  abortPrivate();
  assert.deepEqual(await publica, fixture("public-list-empty"));
  assert.equal(calls[0].options.signal, undefined);
  assert.match(calls[0].url, /^\/api\/publico\/terrenos\?estado=Jalisco&limit=250$/);
});

test("a private 401 reports the expired session; a failed login does not", async () => {
  const avisos = [];
  onSessionExpired((error) => avisos.push(error.status));
  stubFetch(() => json(401, fixture("error-401")));
  await assert.rejects(api.inventarioTerreno("x"), (e) => e.status === 401 && e.detalle.code === "unauthenticated");
  await assert.rejects(api.login("ana", "mal"), (e) => e.status === 401);
  assert.deepEqual(avisos, [401]);
  onSessionExpired(null);
});

test("an unreachable server is a readable network error the editor can tell apart", async () => {
  stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
  await assert.rejects(api.publicoTerreno("x"), (e) => e.red === true && /No se pudo conectar/.test(e.message));
});

test("create carries its Idempotency-Key; save carries the expected version", async () => {
  const calls = stubFetch(() => json(200, fixture("internal-terrain-draft")));
  await api.crearTerreno({ terreno: "A" }, "clave-123456");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["Idempotency-Key"], "clave-123456");
  assert.deepEqual(JSON.parse(calls[0].options.body), { terreno: "A" });

  await api.guardarBorrador("3f1c", 3, { asking_m2: 122.5 });
  assert.equal(calls[1].options.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[1].options.body), { expected_version: 3, changes: { asking_m2: 122.5 } });

  await api.guardarBorrador("3f1c", 4, {}, ["price"]);
  assert.deepEqual(JSON.parse(calls[2].options.body), { expected_version: 4, changes: {}, confirm: ["price"] });

  await api.login("ana", "secreto");
  assert.deepEqual(JSON.parse(calls[3].options.body), { username: "ana", password: "secreto" });
});

/* ------------------------------------------------------------------ state */

test("clearing private state forgets every team dataset but keeps the public catalog", () => {
  const catalogo = { ...DATASET_VACIO, registros: [{ id: "p" }], cargado: true };
  setState({
    sesion: { id: "u", display_name: "Ana" },
    inventario: { ...DATASET_VACIO, registros: [fixture("internal-terrain-draft").terreno] },
    detalle: { tipo: "inventario", id: "x", terreno: {} },
    bases: [{ id: 1 }], mapas: [{ id: 2 }], terrenos: [{ id: 3 }], baseActiva: { id: 1 },
    catalogo,
  });
  clearPrivateState();
  const s = getState();
  assert.equal(s.sesion, null);
  assert.equal(s.inventario.registros.length, 0);
  assert.equal(s.detalle, null);
  assert.deepEqual([s.bases, s.mapas, s.terrenos, s.baseActiva], [[], [], [], null]);
  assert.equal(s.catalogo, catalogo);
});

/* The private transport bridge (Round 3, INTERFACES §2), against a real local
 * HTTP server so bodies, aborts and stalled reads are the platform's own.
 * Run with: node --test tests/js/peticionPrivada.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";

const { peticionPrivada, abortPrivate, onSessionExpired, api } = await import("../../web/lib/api.js");

/* /api/lento sends headers and half a body, then waits until `soltar()`. */
let soltar = () => {};
const vistos = [];
const servidor = http.createServer((req, res) => {
  vistos.push({ url: req.url, method: req.method, headers: req.headers });
  if (req.url === "/api/caducada") {
    res.writeHead(401, { "Content-Type": "application/json" });
    return res.end('{"error":"Inicia sesión para continuar."}');
  }
  if (req.url === "/api/negada") {
    res.writeHead(404, { "Content-Type": "application/json" });
    return res.end('{"error":"No encontrado.","detalle":{"code":"no_encontrado"}}');
  }
  if (req.url === "/api/lento") {
    res.writeHead(200, { "Content-Type": "application/octet-stream", "Content-Length": "8" });
    res.write("priv");
    soltar = () => res.end("ados");
    return;
  }
  const trozos = [];
  req.on("data", (t) => trozos.push(t));
  req.on("end", () => {
    res.writeHead(200, { "Content-Type": "application/octet-stream" });
    res.end(Buffer.concat(trozos).length ? Buffer.concat(trozos) : "privados");
  });
});
await new Promise((listo) => servidor.listen(0, "127.0.0.1", listo));
const origen = `http://127.0.0.1:${servidor.address().port}`;
const real = globalThis.fetch;
const opciones = [];
globalThis.fetch = (ruta, o) => { opciones.push(o); return real(origen + ruta, o); };
test.after(() => { servidor.closeAllConnections(); servidor.close(); });

const esAbort = (error) => error?.name === "AbortError";

test("a successful response is returned undecoded, same-origin and uncached", async () => {
  const { response, signal } = await peticionPrivada("/api/archivos/x", {
    method: "PUT", headers: { "Content-Type": "application/pdf" }, body: new Uint8Array([1, 2, 3]),
  });
  assert.equal(response.bodyUsed, false);
  assert.deepEqual([...new Uint8Array(await response.arrayBuffer())], [1, 2, 3]);
  assert.equal(signal.aborted, false);
  const o = opciones.at(-1);
  assert.deepEqual([o.credentials, o.cache, o.method], ["same-origin", "no-store", "PUT"]);
  assert.equal(vistos.at(-1).headers["content-type"], "application/pdf");
});

test("only same-origin /api/ paths are accepted, before anything is sent", async () => {
  const antes = vistos.length;
  for (const ruta of ["https://example.invalid/api/x", "//example.invalid/api/x", "/apix", "api/x",
    "/api/\\\\example.invalid", "/otra", "/api/a b", "/api/a\nb", null, undefined, 7]) {
    await assert.rejects(peticionPrivada(ruta), TypeError, String(ruta));
  }
  assert.equal(vistos.length, antes);
});

test("a non-2xx answer other than 401 is the caller's to decode", async () => {
  const { response } = await peticionPrivada("/api/negada");
  assert.equal(response.status, 404);
  assert.equal((await response.json()).detalle.code, "no_encontrado");
});

test("a 401 runs the expiry teardown first and never resolves", async () => {
  const orden = [];
  onSessionExpired((error) => { orden.push(`expira ${error.status}`); abortPrivate(); });
  await assert.rejects(peticionPrivada("/api/caducada").then(() => orden.push("resuelta")), esAbort);
  assert.deepEqual(orden, ["expira 401"]);
  // Without a teardown that ends the scope it still cannot succeed.
  onSessionExpired(() => {});
  await assert.rejects(peticionPrivada("/api/caducada"), (e) => e.status === 401);
  onSessionExpired(null);
});

test("the caller's own signal cancels with an AbortError, before and during the request", async () => {
  const ya = new AbortController();
  ya.abort();
  const antes = vistos.length;
  await assert.rejects(peticionPrivada("/api/x", { signal: ya.signal }), esAbort);
  assert.equal(vistos.length, antes);
  const luego = new AbortController();
  const pendiente = peticionPrivada("/api/lento", { signal: luego.signal });
  const { response, signal } = await pendiente;          // headers are in, the body is not
  const lectura = response.arrayBuffer();
  luego.abort();
  await assert.rejects(lectura, esAbort);
  assert.equal(signal.aborted, true);
  soltar();
});

test("ending the session cancels a body read in flight; the bytes never arrive", async () => {
  let liberado = false;
  const leer = async () => {
    const { response, signal } = await peticionPrivada("/api/lento");
    try {
      const bytes = await response.arrayBuffer();
      return { bytes, vigente: !signal.aborted };
    } finally { liberado = true; }                       // what a caller's cleanup relies on
  };
  const lectura = leer();
  await new Promise((r) => setTimeout(r, 50));           // the first half has arrived
  abortPrivate();                                        // logout, expiry, another account
  soltar();                                              // the rest is sent anyway
  await assert.rejects(lectura, esAbort);
  assert.equal(liberado, true);
});

test("a signal stays bound to the session that made the request, across a new login", async () => {
  const { response, signal } = await peticionPrivada("/api/lento");
  abortPrivate();                                        // same account logs out and in again
  assert.equal(signal.aborted, true);                    // the old generation stays ended
  await assert.rejects(response.arrayBuffer(), esAbort);
  soltar();
  const nueva = await peticionPrivada("/api/archivos/y"); // the new session works normally
  assert.equal(nueva.signal.aborted, false);
  assert.equal(await nueva.response.text(), "privados");
});

test("legacy API calls keep their convention: a cancelled private call never settles", async () => {
  const pendiente = api.maestraBases();
  let asentada = false;
  pendiente.then(() => { asentada = true; }, () => { asentada = true; });
  abortPrivate();
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(asentada, false);
});

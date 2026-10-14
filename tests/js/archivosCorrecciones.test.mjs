/* Regressions for the Round 3 review corrections R3-B1..R3-B5 (packet
 * reports/round-3-review-2026-10-12/ on the supervisor branch).
 * Run with: node --test tests/js/archivosCorrecciones.test.mjs
 *
 * Each test holds one boundary with a deferred and acts on it: no timers, no
 * real network, fictional files only. A "scope" is the identity a fake bridge
 * serves at the moment a request is sent; a request sent after teardown is
 * recorded under whatever scope is current then, which is the defect R3-B1
 * describes.
 */

import base from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";

/* A defect here can leave a promise pending forever: fail the test, not the run. */
const test = (nombre, fn) => base(nombre, { timeout: 10_000 }, fn);

const A = await import("../../web/lib/archivos.js");
const { crearSubida, crearTurno, FASE, esTerminal } = await import("../../web/components/archivos/subida.js");
const { crearCargadorGeometrias } = await import("../../web/lib/cargadorGeometrias.js");

const { ErrorArchivos } = A;
const TERRENO = "11111111-1111-4111-8111-111111111111";
const VERSION = "22222222-2222-4222-8222-222222222222";
const ARCHIVO = "33333333-3333-4333-8333-333333333333";
const sha = (b) => createHash("sha256").update(b).digest("hex");
const PDF = Buffer.from("%PDF-1.4\n% ficticio\n%%EOF\n");
const pdf = (nombre = "ficticio.pdf") => new File([PDF], nombre);
const tick = () => new Promise((r) => setTimeout(r, 0));
function diferido() {
  let resolve, reject;
  const promise = new Promise((s, j) => { resolve = s; reject = j; });
  return { promise, resolve, reject };
}
const abortError = () => new DOMException("x", "AbortError");
/* Wait for a deferred unless the signal ends first, like fetch does. */
const esperar = (d, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) return reject(abortError());
  signal?.addEventListener("abort", () => reject(abortError()), { once: true });
  d.promise.then(resolve, reject);
});
const inicio = { version_id: VERSION, archivo_id: ARCHIVO, tamano_declarado: PDF.length };
const terminal = (estado, extra = {}) => ({ version: { id: VERSION, estado, ...extra }, archivo: { id: ARCHIVO, revision: 2 } });
const error = (codigo, status, extra = {}) => new ErrorArchivos(codigo, `Fallo ficticio ${codigo}`, { status, ...extra });

/* A scripted client: every call is recorded with the scope current when it is
 * SENT, and whether it carried a signal. `guion[metodo]` answers it. */
function clienteGuionado(guion) {
  const llamadas = [];
  const ambito = { actual: "inicial" };
  const cliente = {};
  for (const metodo of ["iniciar", "subir", "completar", "cancelar"]) {
    cliente[metodo] = async (...args) => {
      const opciones = args.at(-1) && typeof args.at(-1) === "object" && "signal" in args.at(-1) ? args.at(-1) : {};
      llamadas.push({ metodo, ambito: ambito.actual, conSenal: Boolean(opciones.signal) });
      if (opciones.signal?.aborted) throw abortError();
      return guion[metodo](opciones.signal, llamadas.filter((l) => l.metodo === metodo).length);
    };
  }
  return { cliente, llamadas, ambito };
}

function subida(cliente, extra = {}) {
  const vistas = [];
  const servidor = [];
  const accesos = [];
  const s = crearSubida({ cliente, terrenoId: TERRENO, tipo: "pdf", archivo: pdf(),
    alCambiar: (e) => vistas.push(e.fase), alServidor: () => servidor.push(1),
    alPerderAcceso: (e) => accesos.push(e), ...extra });
  return { s, vistas, servidor, accesos };
}

/* ================================================================ R3-B1 */

test("R3-B1: destroyed while cancellation waits for the PUT: no cancel call, no callback", async () => {
  const entra = diferido(), suelta = diferido();
  const { cliente, llamadas, ambito } = clienteGuionado({
    iniciar: async () => inicio,
    subir: async (signal) => { entra.resolve(); await suelta.promise; if (signal?.aborted) throw abortError(); return {}; },
    cancelar: async () => ({ estado: "cancelado" }),
  });
  const { s, vistas, servidor } = subida(cliente);
  const corre = s.ejecutar();
  await entra.promise;
  const cancela = s.cancelar();
  const n = vistas.length;
  const nServidor = servidor.length;
  s.abortar();
  ambito.actual = "otra-cuenta";
  suelta.resolve();
  await Promise.all([corre, cancela]);
  assert.deepEqual(llamadas.filter((l) => l.ambito === "otra-cuenta"), []);
  assert.equal(llamadas.filter((l) => l.metodo === "cancelar").length, 0);
  // Only "cancelando" may have been shown before teardown; nothing after it.
  assert.equal(vistas.length, n);
  assert.equal(servidor.length, nServidor);
});

for (const reentrada of ["misma-cuenta", "otra-cuenta"]) {
  test(`R3-B1: destroyed during the ambiguous-start replay of a cancellation (${reentrada})`, async () => {
    const replay = diferido();
    let replayEntro = null;
    const { cliente, llamadas, ambito } = clienteGuionado({
      iniciar: async (signal, n) => {
        if (n === 1) throw error("red", 0, { incierto: true });         // the start reply was lost
        replayEntro?.resolve();
        await esperar(replay, signal);
        return inicio;
      },
      subir: async () => ({}), cancelar: async () => ({ estado: "cancelado" }),
    });
    const { s, vistas, servidor } = subida(cliente);
    await s.ejecutar();
    assert.equal(s.estado().fase, FASE.INCIERTO);
    replayEntro = diferido();
    const cancela = s.cancelar();
    await replayEntro.promise;
    assert.equal(llamadas.at(-1).conSenal, true, "the replay carries the upload's lifetime");
    const n = vistas.length;
    s.abortar();
    ambito.actual = reentrada;
    replay.resolve();
    await cancela;
    assert.deepEqual(llamadas.filter((l) => l.ambito === reentrada), []);
    assert.equal(llamadas.filter((l) => l.metodo === "cancelar").length, 0);
    assert.equal(vistas.length, n);
    assert.equal(servidor.length, 0);
  });
}

test("R3-B1: destroyed while the cancel request is in flight: it is aborted and nothing is reported", async () => {
  const respuesta = diferido();
  const { cliente, llamadas, ambito } = clienteGuionado({
    iniciar: async () => inicio,
    subir: async () => ({}),
    completar: async () => { throw error("almacen_no_disponible", 503); },
    cancelar: (signal) => esperar(respuesta, signal),
  });
  const { s, vistas, servidor } = subida(cliente);
  await s.ejecutar();
  const cancela = s.cancelar();
  while (!llamadas.some((l) => l.metodo === "cancelar")) await tick();
  const cancel = llamadas.find((l) => l.metodo === "cancelar");
  assert.equal(cancel.conSenal, true);
  const n = vistas.length;
  const nServidor = servidor.length;          // the start's own notification came before teardown
  s.abortar();
  ambito.actual = "otra-cuenta";
  respuesta.resolve({ estado: "cancelado" });
  await cancela;
  assert.equal(vistas.length, n);
  assert.equal(servidor.length, nServidor);
  assert.deepEqual(llamadas.filter((l) => l.ambito === "otra-cuenta"), []);
});

test("R3-B1: a live cancellation still reaches the server once, with the upload's signal", async () => {
  const entra = diferido();
  const { cliente, llamadas } = clienteGuionado({
    iniciar: async () => inicio,
    subir: async (signal) => { entra.resolve(); await esperar(diferido(), signal); },
    cancelar: async () => ({ estado: "cancelado", limpieza_pendiente: true }),
  });
  const { s, servidor } = subida(cliente);
  const corre = s.ejecutar();
  await entra.promise;
  await s.cancelar();
  await corre;
  const cancel = llamadas.filter((l) => l.metodo === "cancelar");
  assert.equal(cancel.length, 1);
  assert.equal(cancel[0].conSenal, true);
  assert.equal(s.estado().fase, FASE.CANCELADO);
  assert.equal(s.estado().limpiezaPendiente, true);
  assert.ok(servidor.length >= 1, "the cancellation is reported to the host");
});

test("R3-B1: an aborted start replay is teardown, not proof that the start never happened", async () => {
  const { cliente, llamadas } = clienteGuionado({
    iniciar: async (signal, n) => {
      if (n === 1) throw error("red", 0, { incierto: true });
      throw abortError();                                           // the private session ended
    },
    subir: async () => ({}), cancelar: async () => ({ estado: "cancelado" }),
  });
  const { s } = subida(cliente);
  await s.ejecutar();
  await s.cancelar();
  assert.notEqual(s.estado().fase, FASE.CANCELADO);
  assert.equal(llamadas.filter((l) => l.metodo === "cancelar").length, 0);
});

test("R3-B1: through the real client, a destroyed upload sends nothing under a later identity", async () => {
  let identidad = "olga";
  const enviados = [];
  const suelta = diferido();
  const entra = diferido();
  const peticionPrivada = async (ruta, { method = "GET", signal } = {}) => {
    if (signal?.aborted) throw abortError();
    enviados.push({ ruta, method, identidad });
    if (method === "PUT") { entra.resolve(); await suelta.promise; if (signal?.aborted) throw abortError(); }
    if (ruta.endsWith("/archivos")) return { response: Response.json(inicio), signal: new AbortController().signal };
    return { response: Response.json({ estado: "cancelado" }), signal: new AbortController().signal };
  };
  const cliente = A.crearClienteArchivos({ peticionPrivada });
  const { s } = subida(cliente);
  const corre = s.ejecutar();
  await entra.promise;
  const cancela = s.cancelar();
  s.abortar();
  identidad = "otto";
  suelta.resolve();
  await Promise.all([corre, cancela]);
  assert.deepEqual(enviados.filter((e) => e.identidad === "otto"), []);
});

/* ================================================================ R3-B2 */

for (const [donde, guion] of [
  ["start", { iniciar: async () => { throw error("not_found", 404); } }],
  ["PUT", { iniciar: async () => inicio, subir: async () => { throw error("not_found", 404); } }],
  ["completion", { iniciar: async () => inicio, subir: async () => ({}), completar: async () => { throw error("not_found", 404); } }],
]) {
  test(`R3-B2: a 404 from the ${donde} reaches alPerderAcceso and ends the upload`, async () => {
    const { cliente } = clienteGuionado({ cancelar: async () => ({}), ...guion });
    const { s, accesos } = subida(cliente);
    await s.ejecutar();
    assert.equal(accesos.length, 1);
    assert.equal(accesos[0].status, 404);
    assert.ok(esTerminal(s.estado().fase));
    assert.equal(s.estado().reintentable, false);
    assert.equal(s.estado().cancelable, false);
  });
}

test("R3-B2: a 404 on retry and on explicit cancellation reaches alPerderAcceso", async () => {
  let completa = 0;
  const { cliente } = clienteGuionado({
    iniciar: async () => inicio, subir: async () => ({}),
    completar: async () => { completa += 1; throw completa === 1 ? error("red", 0, { incierto: true }) : error("not_found", 404); },
    cancelar: async () => ({}),
  });
  const reintento = subida(cliente);
  await reintento.s.ejecutar();
  assert.equal(reintento.accesos.length, 0);
  await reintento.s.reintentar();
  assert.equal(reintento.accesos.length, 1);

  const c = clienteGuionado({
    iniciar: async () => inicio, subir: async () => ({}),
    completar: async () => { throw error("almacen_no_disponible", 503); },
    cancelar: async () => { throw error("not_found", 404); },
  });
  const cancelacion = subida(c.cliente);
  await cancelacion.s.ejecutar();
  await cancelacion.s.cancelar();
  assert.equal(cancelacion.accesos.length, 1);
  assert.ok(esTerminal(cancelacion.s.estado().fase));
});

test("R3-B2: losing write permission (403) reaches alPerderAcceso; 401 and network do not", async () => {
  for (const [e, espera] of [[error("forbidden", 403), 1],
    [error("unauthenticated", 401), 0], [error("red", 0, { incierto: true }), 0],
    [error("contenido_temporal_ausente", 409), 0]]) {
    const { cliente } = clienteGuionado({ iniciar: async () => inicio, subir: async () => ({}),
      completar: async () => { throw e; }, cancelar: async () => ({}) });
    const { s, accesos } = subida(cliente);
    await s.ejecutar();
    assert.equal(accesos.length, espera, e.codigo);
  }
});

test("R3-B2: alPerderAcceso is not called after teardown", async () => {
  const suelta = diferido();
  const { cliente } = clienteGuionado({ iniciar: async () => inicio, subir: async () => ({}),
    completar: async () => { await suelta.promise; throw error("not_found", 404); } });
  const { s, accesos } = subida(cliente);
  const corre = s.ejecutar();
  await tick();
  s.abortar();
  suelta.resolve();
  await corre;
  assert.equal(accesos.length, 0);
});

/* ================================================================ R3-B3 */

for (const codigo of ["contenido_temporal_ausente", "almacen_no_disponible"]) {
  test(`R3-B3: ${codigo} is a recoverable, still-pending state: counted, cancellable and retryable`, async () => {
    let completa = 0;
    const { cliente, llamadas } = clienteGuionado({
      iniciar: async () => inicio, subir: async () => ({}),
      completar: async () => { completa += 1; if (completa === 1) throw error(codigo, codigo === "almacen_no_disponible" ? 503 : 409); return terminal("disponible"); },
      cancelar: async () => ({ estado: "cancelado" }),
    });
    const { s } = subida(cliente);
    await s.ejecutar();
    const e = s.estado();
    assert.equal(esTerminal(e.fase), false, `fase ${e.fase}`);
    assert.equal(e.reintentable, true);
    assert.equal(e.cancelable, true);
    // Cancelling it reaches the server.
    const otra = subida(clienteGuionado({ iniciar: async () => inicio, subir: async () => ({}),
      completar: async () => { throw error(codigo, 409); }, cancelar: async () => ({ estado: "cancelado" }) }).cliente);
    await otra.s.ejecutar();
    await otra.s.cancelar();
    assert.equal(otra.s.estado().fase, FASE.CANCELADO);
    // Retrying the same operation resolves it (same version, no new start).
    await s.reintentar();
    assert.equal(s.estado().fase, FASE.LISTO);
    assert.equal(llamadas.filter((l) => l.metodo === "iniciar").length, 1);
  });
}

test("R3-B3: a completion reply without an outcome stays at completion replay, without looping", async () => {
  let completa = 0;
  const { cliente, llamadas } = clienteGuionado({
    iniciar: async () => inicio, subir: async () => ({}),
    completar: async () => { completa += 1; return completa === 1 ? {} : terminal("disponible"); },
  });
  const { s } = subida(cliente);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.INCIERTO);
  assert.equal(s.estado().reintentable, true);
  assert.equal(esTerminal(s.estado().fase), false);
  assert.equal(completa, 1, "no automatic retry");
  await s.reintentar();
  assert.equal(completa, 2, "the retry replays completion");
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.equal(llamadas.filter((l) => l.metodo === "iniciar").length, 1, "never a new version");
  assert.equal(llamadas.filter((l) => l.metodo === "subir").length, 1, "content is not re-sent");
});

test("R3-B3: an oversized completion reply is unreadable: completion replay, never terminal", async () => {
  let completa = 0;
  const { cliente } = clienteGuionado({ iniciar: async () => inicio, subir: async () => ({}),
    completar: async () => { completa += 1; if (completa === 1) throw error("respuesta_excesiva", 0); return terminal("disponible"); } });
  const { s } = subida(cliente);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.INCIERTO);
  await s.reintentar();
  assert.equal(completa, 2);
  assert.equal(s.estado().fase, FASE.LISTO);
});

test("R3-B3: an unknown version state and a KMZ outcome without its attempt are unresolved, not terminal", async () => {
  for (const [tipo, respuesta] of [["pdf", terminal("raro")], ["kmz", terminal("disponible")]]) {
    const { cliente } = clienteGuionado({ iniciar: async () => inicio, subir: async () => ({}), completar: async () => respuesta });
    const s = crearSubida({ cliente, terrenoId: TERRENO, tipo, archivo: new File([PDF], `x.${tipo}`) });
    await s.ejecutar();
    assert.equal(s.estado().fase, FASE.INCIERTO, tipo);
    assert.equal(s.estado().reintentable, true);
  }
});

test("R3-B3: confirmed terminal outcomes stay terminal and offer no cancellation", async () => {
  for (const [respuesta, fase] of [
    [terminal("fallido", { error: { codigo: "sha256_no_coincide", mensaje: "No coincide." } }), FASE.FALLIDO],
    [terminal("cancelado"), FASE.CANCELADO], [terminal("expirado"), FASE.EXPIRADO]]) {
    const { cliente, llamadas } = clienteGuionado({ iniciar: async () => inicio, subir: async () => ({}),
      completar: async () => respuesta, cancelar: async () => ({}) });
    const { s } = subida(cliente);
    await s.ejecutar();
    assert.equal(s.estado().fase, fase);
    assert.ok(esTerminal(fase));
    assert.equal(s.estado().cancelable, false);
    await s.cancelar();
    assert.equal(llamadas.filter((l) => l.metodo === "cancelar").length, 0);
  }
  const vencida = clienteGuionado({ iniciar: async () => inicio, subir: async () => { throw error("subida_expirada", 410); } });
  const v = subida(vencida.cliente);
  await v.s.ejecutar();
  assert.equal(v.s.estado().fase, FASE.EXPIRADO);
});

test("R3-B3: a retry hint holds the retry until its deadline, then the same step runs", async () => {
  let reloj = 1000;
  let completa = 0;
  const { cliente } = clienteGuionado({ iniciar: async () => inicio, subir: async () => ({}),
    completar: async () => { completa += 1; if (completa === 1) throw error("procesamiento_en_curso", 409, { reintentarDespuesDe: 3 }); return terminal("disponible"); } });
  const { s } = subida(cliente, { ahora: () => reloj });
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.EN_CURSO);
  assert.equal(esTerminal(s.estado().fase), false);
  await s.reintentar();
  assert.equal(completa, 1);
  reloj += 3000;
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);
});

test("R3-B3: a failure after the version exists but before its outcome is known keeps it cancellable", async () => {
  const { cliente, llamadas } = clienteGuionado({ iniciar: async () => inicio,
    subir: async () => { throw error("cuerpo_incompleto", 400); }, cancelar: async () => ({ estado: "cancelado" }) });
  const { s } = subida(cliente);
  await s.ejecutar();
  assert.equal(esTerminal(s.estado().fase), false);
  assert.equal(s.estado().cancelable, true);
  await s.cancelar();
  assert.equal(llamadas.filter((l) => l.metodo === "cancelar").length, 1);
  assert.equal(s.estado().fase, FASE.CANCELADO);
});

/* ================================================================ R3-B4 */

function archivoLento(nombre, contador, retener) {
  return { name: nombre, size: 1, async arrayBuffer() {
    contador.activos += 1;
    contador.max = Math.max(contador.max, contador.activos);
    try { if (retener) await retener; return new Uint8Array([1]).buffer; } finally { contador.activos -= 1; }
  } };
}
const pararEnInicio = { iniciar: async () => { throw error("parada", 400); } };

test("R3-B4: a destroyed upload keeps the pipeline permit until its file read settles", async () => {
  const turno = crearTurno();
  const contador = { activos: 0, max: 0 };
  const suelta = diferido();
  const a = crearSubida({ cliente: pararEnInicio, terrenoId: TERRENO, tipo: "pdf", turno,
    archivo: archivoLento("lento.pdf", contador, suelta.promise) });
  const corre = a.ejecutar();
  await tick();
  a.abortar();
  const b = crearSubida({ cliente: pararEnInicio, terrenoId: TERRENO, tipo: "pdf", turno,
    archivo: archivoLento("rapido.pdf", contador) });
  await b.ejecutar();
  assert.match(b.estado().mensaje, /Otra subida está en curso/);
  assert.equal(contador.max, 1);
  suelta.resolve();
  await corre;
  assert.equal(turno.ocupado(), false, "released once the read settled");
  await b.reintentar();
  assert.equal(contador.max, 1);
  assert.equal(turno.ocupado(), false);
});

test("R3-B4: a destroyed upload keeps the permit until its digest settles", async () => {
  const turno = crearTurno();
  const entra = diferido(), suelta = diferido();
  const nativo = crypto.subtle.digest.bind(crypto.subtle);
  let digestos = 0, max = 0;
  crypto.subtle.digest = async (...args) => {
    digestos += 1; max = Math.max(max, digestos);
    try { entra.resolve(); await suelta.promise; return await nativo(...args); } finally { digestos -= 1; }
  };
  try {
    const a = crearSubida({ cliente: pararEnInicio, terrenoId: TERRENO, tipo: "pdf", turno, archivo: pdf() });
    const corre = a.ejecutar();
    await entra.promise;
    a.abortar();
    const b = crearSubida({ cliente: pararEnInicio, terrenoId: TERRENO, tipo: "pdf", turno, archivo: pdf() });
    await b.ejecutar();
    assert.match(b.estado().mensaje, /Otra subida está en curso/);
    assert.equal(max, 1);
    suelta.resolve();
    await corre;
    assert.equal(turno.ocupado(), false);
  } finally {
    crypto.subtle.digest = nativo;
  }
});

test("R3-B4: repeated destroy and recreate in one factory never overlaps reads", async () => {
  const turno = crearTurno();
  const contador = { activos: 0, max: 0 };
  const pendientes = [];
  const corridas = [];
  for (let i = 0; i < 6; i += 1) {
    const d = diferido();
    pendientes.push(d);
    const s = crearSubida({ cliente: pararEnInicio, terrenoId: TERRENO, tipo: "pdf", turno,
      archivo: archivoLento(`f${i}.pdf`, contador, d.promise) });
    corridas.push(s.ejecutar());
    await tick();
    s.abortar();
  }
  assert.equal(contador.max, 1);
  for (const d of pendientes) d.resolve();
  await Promise.all(corridas);
  assert.equal(turno.ocupado(), false);
  assert.equal(contador.activos, 0);
});

test("R3-B4: a stale permit cannot release somebody else's", () => {
  const turno = crearTurno();
  const viejo = turno.intentar();
  assert.ok(viejo);
  assert.equal(turno.intentar(), null);
  turno.liberar(viejo);
  const nuevo = turno.intentar();
  assert.ok(nuevo);
  turno.liberar(viejo);                     // stale: ignored
  assert.equal(turno.ocupado(), true);
  assert.equal(turno.intentar(), null);
  turno.liberar(nuevo);
  assert.equal(turno.ocupado(), false);
});

/* ================================================================ R3-B5 */

const GEOJSON = Buffer.from(JSON.stringify({ type: "MultiPolygon", coordinates: [[[[-100, 20], [-99, 20], [-99, 21], [-100, 20]]]] }));
const GID = "44444444-4444-4444-8444-444444444444";
const descriptor = { id: GID, archivo_version_id: VERSION, utilizable: true, bbox: [-100, 20, -99, 21],
  punto_interior: { type: "Point", coordinates: [-99.5, 20.2] } };
const meta = { ...descriptor, terreno_id: TERRENO, activa: true, partes: 1, huecos: 0, vertices: 4,
  area_aproximada_m2: 1, bytes: GEOJSON.length, sha256: sha(GEOJSON), fragmento_bytes: 524288, fragmentos: 1 };

/* A bridge whose captured private scope is `ambito()` at the moment of each call. */
function puenteGeometrias(ambito) {
  const peticiones = [];
  async function peticionPrivada(ruta, { signal } = {}) {
    const alcance = ambito();
    if (signal?.aborted || alcance.aborted) throw abortError();
    peticiones.push(ruta);
    return { signal: alcance, response: ruta.endsWith("metadatos")
      ? Response.json({ geometrias: { [GID]: meta }, no_disponibles: [] })
      : new Response(GEOJSON, { headers: { "Content-Type": "application/octet-stream", "X-Geometria-Id": GID,
        "X-Geometria-Desde": "0", "X-Geometria-Longitud": String(GEOJSON.length), "X-Geometria-Bytes": String(GEOJSON.length),
        "X-Geometria-Sha256": meta.sha256, "X-Geometria-Final": "1", "X-Geometria-Siguiente": "fin" } }) };
  }
  return { peticionPrivada, peticiones };
}
const abortada = (p) => assert.rejects(p, (e) => e?.name === "AbortError");

test("R3-B5: the private scope ending during the final digest installs nothing", async () => {
  const scope = new AbortController();
  const { peticionPrivada } = puenteGeometrias(() => scope.signal);
  const entra = diferido(), suelta = diferido();
  const nativo = crypto.subtle.digest.bind(crypto.subtle);
  crypto.subtle.digest = async (...args) => { entra.resolve(); await suelta.promise; return nativo(...args); };
  try {
    const cargador = crearCargadorGeometrias({ peticionPrivada });
    const carga = cargador.cargar({ terrenoId: TERRENO, geometria: descriptor });
    await entra.promise;
    scope.abort();
    suelta.resolve();
    await abortada(carga);
    assert.deepEqual(cargador.estado(), { enCurso: 0, enEspera: 0, listos: 0, destruido: false });
  } finally {
    crypto.subtle.digest = nativo;
  }
});

test("R3-B5: the private scope ending right after parsing (before install) installs nothing", async () => {
  const scope = new AbortController();
  const { peticionPrivada } = puenteGeometrias(() => scope.signal);
  const parse = JSON.parse;
  JSON.parse = (texto, ...resto) => {
    const v = parse(texto, ...resto);
    if (v?.type === "MultiPolygon") scope.abort();
    return v;
  };
  try {
    const cargador = crearCargadorGeometrias({ peticionPrivada });
    await abortada(cargador.cargar({ terrenoId: TERRENO, geometria: descriptor }));
    assert.equal(cargador.estado().listos, 0);
  } finally {
    JSON.parse = parse;
  }
});

test("R3-B5: a ready body is dropped when its scope ends and never reused across scopes", async () => {
  let scope = new AbortController();
  const { peticionPrivada, peticiones } = puenteGeometrias(() => scope.signal);
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  const uno = await cargador.cargar({ terrenoId: TERRENO, geometria: descriptor });
  assert.equal(uno.id, GID);
  // Live-scope control: the same descriptor is answered without network.
  const n = peticiones.length;
  assert.equal(await cargador.cargar({ terrenoId: TERRENO, geometria: descriptor }), uno);
  assert.equal(peticiones.length, n);
  // The scope ends: the body is released at once.
  scope.abort();
  assert.equal(cargador.estado().listos, 0);
  // A later request for the same descriptor in a NEW scope loads again.
  scope = new AbortController();
  const dos = await cargador.cargar({ terrenoId: TERRENO, geometria: descriptor });
  assert.notEqual(dos, uno);
  assert.equal(peticiones.length, n + 2);
  cargador.destroy();
});

test("R3-B5: obsolete selections and the waiting slot still behave with scope tracking", async () => {
  const scope = new AbortController();
  const puerta = [];
  const { peticionPrivada: base } = puenteGeometrias(() => scope.signal);
  const peticionPrivada = async (ruta, o) => {
    const d = diferido(); puerta.push(d); await esperar(d, o.signal); return base(ruta, o);
  };
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  const otro = { ...descriptor, id: "55555555-5555-4555-8555-555555555555" };
  const x = cargador.cargar({ terrenoId: TERRENO, geometria: otro });
  await tick();
  const y = cargador.cargar({ terrenoId: TERRENO, geometria: descriptor });
  await abortada(x);
  assert.deepEqual(cargador.estado(), { enCurso: 1, enEspera: 0, listos: 0, destruido: false });
  while (cargador.estado().enCurso) { puerta.shift()?.resolve(); await tick(); }
  assert.equal((await y).id, GID);
  assert.equal(cargador.estado().listos, 1);
  cargador.reset();
  assert.equal(cargador.estado().listos, 0);
});

test("R3-B5 audit: the PUT reply read after the private scope ended is a cancellation", async () => {
  const scope = new AbortController();
  const lee = diferido();
  const cuerpo = new ReadableStream({ async pull(c) { await lee.promise; c.enqueue(new TextEncoder().encode('{"estado":"subiendo"}')); c.close(); } });
  const cliente = A.crearClienteArchivos({ peticionPrivada: async () => ({
    response: new Response(cuerpo, { headers: { "Content-Type": "application/json" } }), signal: scope.signal }) });
  const p = cliente.subir(VERSION, "pdf", pdf());
  await tick();
  scope.abort();
  lee.resolve();
  await abortada(p);
});

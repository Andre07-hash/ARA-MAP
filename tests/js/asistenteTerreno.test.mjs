/* The terrain assistant's client (issue #65) against a stubbed fetch with
 * fictional contract answers. No DOM: the panel itself is checked in the
 * browser (tests/e2e/tabla-asistente.mjs).
 * Run with: node --test tests/js/asistenteTerreno.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

const { abortPrivate } = await import("../../web/lib/api.js");
const {
  ACCIONES, MAX_ENTRADAS, consultar, crearAsistente, errorDeConsulta, leerConfig, normalizarConfig,
  validarRespuesta,
} = await import("../../web/lib/asistenteTerreno.js");

const ID = "00000000-0000-4000-8000-000000000001";
const OTRO = "00000000-0000-4000-8000-000000000002";
const json = (status, cuerpo) => new Response(JSON.stringify(cuerpo), {
  status, headers: { "Content-Type": "application/json" },
});
const respuesta = (cambios = {}) => ({
  terreno_id: ID, version: 3, accion: "resumen", respuesta: "Texto ficticio.",
  campos_usados: [{ campo: "estado", etiqueta: "Estado", valor: "Estado ficticio" }],
  faltantes: [{ campo: "asking_price", etiqueta: "Precio total" }], advertencias: [], origen: "modelo",
  ...cambios,
});

/* Each call records what was sent; the answer comes from `responder`. */
let llamadas = [];
let responder = () => json(200, respuesta());
globalThis.fetch = (ruta, opciones) => {
  llamadas.push({ ruta, ...opciones, cuerpo: opciones?.body ? JSON.parse(opciones.body) : null });
  return new Promise((resolve, reject) => {
    opciones?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    Promise.resolve(responder(ruta, opciones)).then(resolve, reject);
  });
};
test.beforeEach(() => { llamadas = []; responder = () => json(200, respuesta()); });

/** A fetch that waits until the test releases it. */
function retenida() {
  let soltar;
  const espera = new Promise((r) => { soltar = r; });
  responder = () => espera;
  return (r) => soltar(r);
}
const tick = () => new Promise((r) => setTimeout(r, 0));
const esperarA = async (cond) => { for (let i = 0; i < 50 && !cond(); i += 1) await tick(); };

/* ------------------------------------------------------------ config */

test("the configuration is off unless the server says otherwise", () => {
  assert.deepEqual({ ...normalizarConfig(null) }, { habilitado: false, disponible: false, max_pregunta: 500 });
  assert.deepEqual({ ...normalizarConfig({ habilitado: "true", disponible: true }) },
    { habilitado: false, disponible: false, max_pregunta: 500 });
  assert.deepEqual({ ...normalizarConfig({ habilitado: false, disponible: true }) },
    { habilitado: false, disponible: false, max_pregunta: 500 });
  assert.deepEqual({ ...normalizarConfig({ habilitado: true, disponible: true, max_pregunta: 200 }) },
    { habilitado: true, disponible: true, max_pregunta: 200 });
  assert.equal(normalizarConfig({ habilitado: true, disponible: false, max_pregunta: 9000 }).max_pregunta, 500);
});

test("the configuration is read privately and a refusal reads as off", async () => {
  responder = () => json(200, { habilitado: true, disponible: true, max_pregunta: 500 });
  assert.equal((await leerConfig()).habilitado, true);
  assert.equal(llamadas[0].ruta, "/api/asistente-terreno/config");
  assert.equal(llamadas[0].credentials, "same-origin");
  for (const status of [403, 404, 500]) {
    responder = () => json(status, { error: "x", detalle: { code: "y" } });
    assert.equal((await leerConfig()).habilitado, false, `status ${status}`);
  }
  responder = () => new Response("no json", { status: 200 });
  assert.equal((await leerConfig()).habilitado, false);
});

/* ------------------------------------------------------------- query */

test("only the action and, for a question, its text are sent", async () => {
  for (const { accion } of ACCIONES) {
    responder = () => json(200, respuesta({ accion }));
    await consultar(ID, { accion, pregunta: "no debe viajar" });
  }
  responder = () => json(200, respuesta({ accion: "pregunta" }));
  await consultar(ID, { accion: "pregunta", pregunta: "¿Qué superficie tiene?" });
  assert.deepEqual(llamadas.map((l) => [l.ruta, l.method, l.cuerpo]), [
    [`/api/asistente-terreno/${ID}/consultar`, "POST", { accion: "resumen", pregunta: "" }],
    [`/api/asistente-terreno/${ID}/consultar`, "POST", { accion: "faltantes", pregunta: "" }],
    [`/api/asistente-terreno/${ID}/consultar`, "POST", { accion: "descripcion", pregunta: "" }],
    [`/api/asistente-terreno/${ID}/consultar`, "POST", { accion: "pregunta", pregunta: "¿Qué superficie tiene?" }],
  ]);
  assert.equal(llamadas[0].headers["Content-Type"], "application/json");
});

test("an answer is checked against the contract and kept as plain text", () => {
  const ok = validarRespuesta(respuesta({ respuesta: "<img src=x onerror=alert(1)> **negritas** [l](http://x)" }),
    { terrenoId: ID, accion: "resumen" });
  assert.equal(ok.respuesta, "<img src=x onerror=alert(1)> **negritas** [l](http://x)");
  assert.ok(Object.isFrozen(ok) && Object.isFrozen(ok.campos_usados));
  const malos = [
    respuesta({ terreno_id: OTRO }), respuesta({ accion: "descripcion" }), respuesta({ respuesta: "  " }),
    respuesta({ respuesta: 5 }), respuesta({ origen: "simulado" }), respuesta({ version: "3" }), null, "texto",
  ];
  for (const m of malos) assert.equal(validarRespuesta(m, { terrenoId: ID, accion: "resumen" }), null, JSON.stringify(m));
  const limpia = validarRespuesta(respuesta({
    campos_usados: [{ campo: "estado", etiqueta: "Estado", valor: "E" }, { campo: "x" }, "y", null,
      { campo: "superficie_m2", etiqueta: "Superficie (m²)", valor: 1200 }],
    faltantes: [{ campo: "moneda" }, { campo: "moneda", etiqueta: "Moneda" }],
    advertencias: ["Aviso ficticio", 3, ""],
  }), { terrenoId: ID, accion: "resumen" });
  assert.deepEqual(limpia.campos_usados.map((c) => c.valor), ["E", "1200"]);
  assert.deepEqual(limpia.faltantes.map((c) => c.etiqueta), ["Moneda"]);
  assert.deepEqual([...limpia.advertencias], ["Aviso ficticio"]);
});

test("an answer for another terrain or action is rejected as invalid", async () => {
  responder = () => json(200, respuesta({ terreno_id: OTRO }));
  await assert.rejects(consultar(ID, { accion: "resumen" }), (e) => e.codigo === "chat_respuesta_invalida" && e.reintentable);
});

test("errors are the contract's codes in readable Spanish, never the server's raw text", async () => {
  const casos = [
    [403, "forbidden", false], [404, "no_encontrado", false], [422, "invalido", true],
    [429, "chat_limite", true], [503, "chat_deshabilitado", false], [503, "chat_no_configurado", false],
    [503, "chat_presupuesto", false], [503, "chat_no_disponible", true], [504, "chat_tiempo", true],
    [502, "chat_respuesta_invalida", true], [500, undefined, true],
  ];
  for (const [status, code, reintentable] of casos) {
    responder = () => json(status, { error: "proveedor: sk-ficticio Traceback", detalle: { code } });
    await assert.rejects(consultar(ID, { accion: "resumen" }), (e) => {
      assert.equal(e.status, status);
      assert.equal(e.reintentable, reintentable, `${status} ${code}`);
      assert.doesNotMatch(e.message, /sk-ficticio|Traceback/);
      assert.ok(e.message.length > 10);
      return true;
    });
  }
  assert.match(errorDeConsulta(503, "chat_presupuesto").message, /presupuesto/);
  assert.match(errorDeConsulta(504).message, /tardó/);
});

test("a network failure is a retryable error", async () => {
  responder = () => Promise.reject(new TypeError("fetch failed"));
  await assert.rejects(consultar(ID, { accion: "resumen" }), (e) => e.reintentable && /conectar/.test(e.message));
});

/* -------------------------------------------------------- controller */

test("one request at a time: a double click sends one query", async () => {
  const soltar = retenida();
  const cambios = [];
  const a = crearAsistente({ terrenoId: ID, version: 3, onCambio: (s) => cambios.push(s.fase) });
  assert.equal(a.pedir("resumen"), true);
  assert.equal(a.pedir("resumen"), false);
  assert.equal(a.pedir("pregunta", "¿otra?"), false);
  assert.equal(a.ocupado, true);
  soltar(json(200, respuesta()));
  await esperarA(() => a.estado.entradas.length);
  assert.equal(llamadas.length, 1);
  assert.deepEqual(cambios, ["esperando", "inactivo"]);
  assert.equal(a.estado.entradas[0].respuesta, "Texto ficticio.");
  assert.equal(a.pedir("faltantes"), true);
  a.destroy();
});

test("an empty, too long or unknown request is not sent", () => {
  const a = crearAsistente({ terrenoId: ID, version: 3 });
  assert.equal(a.pedir("pregunta", "   "), false);
  assert.equal(a.pedir("pregunta", "x".repeat(501)), false);
  assert.equal(a.pedir("borrar"), false);
  assert.equal(a.pedir("pregunta", "😀".repeat(500)), true);    // 500 characters, 1000 UTF-16 units
  assert.equal(llamadas.length, 0 + 1);
  a.destroy();
});

test("an answer that arrives after giving up, closing or logging out is dropped", async () => {
  for (const salir of [(a) => a.dejarDeEsperar(), (a) => a.destroy(), () => abortPrivate()]) {
    const soltar = retenida();
    const cambios = [];
    const a = crearAsistente({ terrenoId: ID, version: 3, onCambio: (s) => cambios.push(s) });
    a.pedir("resumen");
    salir(a);
    soltar(json(200, respuesta()));
    await tick(); await tick();
    assert.equal(a.estado.entradas.length, 0);
    assert.ok(cambios.every((s) => s.entradas.length === 0 && !s.error));
    assert.ok(llamadas.at(-1).signal.aborted, "the request is cancelled");
    a.destroy();
  }
});

test("destroy forgets the answers and accepts nothing more", async () => {
  const a = crearAsistente({ terrenoId: ID, version: 3 });
  a.pedir("resumen");
  await esperarA(() => a.estado.entradas.length);
  a.destroy();
  assert.equal(a.estado.entradas.length, 0);
  assert.equal(a.pedir("resumen"), false);
});

test("an answer for another version is not shown as current", async () => {
  responder = () => json(200, respuesta({ version: 4 }));
  const a = crearAsistente({ terrenoId: ID, version: 3 });
  a.pedir("resumen");
  await esperarA(() => a.estado.fase === "error");
  assert.equal(a.estado.entradas.length, 0);
  assert.match(a.estado.error.mensaje, /cambió/);
  assert.equal(a.estado.error.reintentable, false);
  assert.equal(a.reintentar(), false);
});

test("a manual retry repeats the failed request once", async () => {
  responder = () => json(504, { error: "x", detalle: { code: "chat_tiempo" } });
  const a = crearAsistente({ terrenoId: ID, version: 3 });
  a.pedir("pregunta", "  ¿Tiene precio?  ");
  await esperarA(() => a.estado.fase === "error");
  assert.equal(a.estado.error.reintentable, true);
  responder = () => json(200, respuesta({ accion: "pregunta" }));
  assert.equal(a.reintentar(), true);
  assert.equal(a.reintentar(), false);
  await esperarA(() => a.estado.entradas.length);
  assert.deepEqual(llamadas.map((l) => l.cuerpo), [{ accion: "pregunta", pregunta: "¿Tiene precio?" },
    { accion: "pregunta", pregunta: "¿Tiene precio?" }]);
  assert.equal(a.estado.entradas[0].pregunta, "¿Tiene precio?");
  a.destroy();
});

test("the browser stops waiting after its own limit and says so", async () => {
  retenida();
  const a = crearAsistente({ terrenoId: ID, version: 3, esperaMaxima: 20 });
  a.pedir("descripcion");
  await esperarA(() => a.estado.fase === "error");
  await new Promise((r) => setTimeout(r, 40));
  assert.equal(a.estado.fase, "error");
  assert.match(a.estado.error.mensaje, /tardó/);
  assert.ok(llamadas[0].signal.aborted);
  a.destroy();
});

test("only the last answers are kept in memory", async () => {
  const a = crearAsistente({ terrenoId: ID, version: 3 });
  for (let i = 0; i < MAX_ENTRADAS + 3; i += 1) {
    responder = () => json(200, respuesta({ respuesta: `R${i}` }));
    a.pedir("resumen");
    await esperarA(() => !a.ocupado);
  }
  assert.equal(a.estado.entradas.length, MAX_ENTRADAS);
  assert.equal(a.estado.entradas.at(-1).respuesta, `R${MAX_ENTRADAS + 2}`);
  assert.equal(a.estado.entradas[0].respuesta, "R3");
  a.destroy();
});

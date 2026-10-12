/* R3-B2 / R3-B1 browser regressions: an upload that loses its scope or its
 * write permission mid-flight, in Chromium against the real mounted server
 * (tests/e2e/archivos_servidor.py), with real grants, transfers and archives
 * made through the real administrator API. Nothing in the application is
 * mocked; a Playwright route only HOLDS one request at a chosen boundary and
 * then lets it continue unchanged.
 *
 *   cd tests/e2e && node archivos-alcance.mjs
 *
 * The harness host is deliberately passive (it records onError/onCambio and
 * refreshes the summary, but never closes the detail), so what is asserted
 * here is the widget's own teardown, not a host covering for it.
 * ARCHIVOS_EVIDENCIA=/dir writes alcance.json there.
 */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, "..", "..");
const PUERTO = Number(process.env.ARCHIVOS_PUERTO ?? 8464);
const CLAVE = readFileSync(join(RAIZ, "tests", "support.py"), "utf8").match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];

const resultados = [];
let fallos = 0;
const alTerminar = [];        // cleanups of the running journey, so a failure does not cascade
async function revisar(nombre, fn) {
  const inicio = Date.now();
  try {
    const detalle = await fn();
    resultados.push({ nombre, ok: true, ms: Date.now() - inicio, ...(detalle ? { detalle } : {}) });
    console.log(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    resultados.push({ nombre, ok: false, error: String(error?.stack ?? error) });
    console.log(`FALLO ${nombre}\n     ${String(error?.message ?? error).split("\n")[0]}`);
  } finally {
    for (const f of alTerminar.splice(0).reverse()) await f().catch((e) => console.log(`     limpieza: ${e.message}`));
  }
}
const igual = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const cierto = (v, m) => { if (!v) throw new Error(m); };

const servidor = spawn("python3", [join(AQUI, "archivos_servidor.py"), "--puerto", String(PUERTO)],
  { cwd: RAIZ, stdio: ["ignore", "pipe", "inherit"] });
const semilla = await new Promise((resolve, reject) => {
  let texto = "";
  servidor.stdout.on("data", (d) => {
    texto += d;
    const lineas = texto.split("\n");
    const json = lineas.find((l) => l.startsWith("{"));
    if (json && lineas.some((l) => l.startsWith("LISTO"))) resolve(JSON.parse(json));
  });
  servidor.on("exit", (c) => reject(new Error(`el servidor salió (${c})`)));
});
process.on("exit", () => servidor.kill());
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const T = semilla.terrenos;
const U = semilla.usuarios;
const F = semilla.fixtures;
console.log(`servidor en modo ${semilla.modo}, almacén ${semilla.almacen}`);

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium",
  env: { ...process.env, LANG: "C.UTF-8", LC_ALL: "C.UTF-8" } });

/* ------------------------------------------- the administrator, by API */

const admin = await navegador.newContext();
async function api(method, ruta, data) {
  const r = await admin.request.fetch(URLBASE + ruta, { method, data, headers: { "Idempotency-Key": randomUUID() } });
  const cuerpo = await r.json().catch(() => null);
  if (r.status() !== 200) throw new Error(`${method} ${ruta} → ${r.status()} ${JSON.stringify(cuerpo)}`);
  return cuerpo;
}
await api("POST", "/api/login", { username: "ana", password: CLAVE });
async function versionBase(bid) {
  return (await api("GET", "/api/maestra/bases?archivadas=1")).bases.find((b) => b.id === bid).version;
}
const conceder = async (usuarios) => api("PUT", `/api/maestra/bases/${semilla.base}/acceso`,
  { expected_version: await versionBase(semilla.base), usuarios });
const revocarOlga = () => conceder([U.omar]);
const restaurarOlga = () => conceder([U.olga, U.omar]);
const otraBase = (await api("POST", "/api/maestra/bases", { nombre: "Base ficticia sin olga" })).base.id;

/* ------------------------------------------------------ olga's harness */

const contexto = await navegador.newContext({ viewport: { width: 1300, height: 1400 } });
const page = await contexto.newPage();
const consola = [];
page.on("pageerror", (e) => consola.push(String(e)));
await page.goto(`${URLBASE}/__arnes/arnes.html#${encodeURIComponent(JSON.stringify(Object.values(T)))}`);
await page.waitForFunction(() => document.title === "listo");
await page.fill("#entrar [name=usuario]", "olga");
await page.fill("#entrar [name=clave]", CLAVE);
await page.click("#entrar button[type=submit]");
await page.waitForFunction(() => window.__arnes.widgets && window.__arnes.modo);

const detalle = (tipo) => page.locator(`[data-detalle="${tipo}"]`);
async function seleccionar(id) {
  if (await page.evaluate((i) => window.__arnes.seleccionado === i, id)) {
    // Re-mount: the detail of a terrain that lost its scope is the host's to replace.
    const otro = Object.values(T).find((t) => t.id !== id).id;
    await page.click(`.fila[data-id="${otro}"] button`);
  }
  await page.click(`.fila[data-id="${id}"] button`);
  await page.waitForFunction((i) => window.__arnes.seleccionado === i, id);
  await detalle("pdf").locator(".archivos-lista li").first().waitFor();
}
async function subirPdf(nombre) {
  await detalle("pdf").locator(".archivos-zona input[type=file]")
    .setInputFiles({ name: nombre, mimeType: "application/pdf", buffer: readFileSync(F.pdf) });
}
/* Hold the next request matching `patron` until `soltar()`; it then continues unchanged. */
async function retener(patron, metodo) {
  let soltar, entro;
  const barrera = new Promise((r) => { soltar = r; });
  const entrada = new Promise((r) => { entro = r; });
  let usada = false;
  const manejador = async (route) => {
    if (usada || route.request().method() !== metodo) return route.fallback();
    usada = true;
    entro();
    await barrera;
    await route.continue().catch(() => {});        // the page may have aborted it meanwhile
  };
  await page.route(patron, manejador);
  alTerminar.push(async () => { soltar(); await page.unroute(patron, manejador); });
  return { entrada, soltar: () => soltar() };
}
/* Requests the widget sends after a point (the host's summary refresh is not the widget's). */
function vigilar() {
  const urls = [];
  const f = (r) => { const u = r.url(); if (u.includes("/api/") && !u.includes("/api/__arnes/")) urls.push(`${r.method()} ${new URL(u).pathname}`); };
  page.on("request", f);
  return { parar: () => { page.off("request", f); return urls; } };
}
async function esperarRefrescosDelInicio() {
  // The start triggers onCambio and a list reload: let both finish first, so
  // that only the held step can observe the scope change.
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(300);
}
async function vistaDelDetalle(nombre) {
  return page.evaluate((n) => {
    const d = document.querySelector('[data-detalle="pdf"]');
    return {
      subidas: d.querySelectorAll(".archivos-subida").length,
      filas: d.querySelectorAll(".archivos-lista .archivos-item").length,
      nombreVisible: document.querySelector("#detalles").innerText.includes(n),
      zonaOculta: d.querySelector(".archivos-zona").hidden,
      escritura: [...d.querySelectorAll("[data-escritura]")].filter((b) => !b.hidden).length,
      mensaje: d.querySelector(".archivos-mensaje").textContent,
      errores: window.__arnes.errores.map((e) => e.codigo),
      cambios: window.__arnes.cambios.slice(),
    };
  }, nombre);
}
async function comprobarAlcancePerdido(nombre, terreno, erroresAntes, cambiosAntes) {
  await page.waitForFunction((n) => window.__arnes.errores.length > n, erroresAntes, { timeout: 15000 });
  const vigia = vigilar();
  await page.waitForTimeout(1000);
  const tardias = vigia.parar();
  const v = await vistaDelDetalle(nombre);
  igual(v.errores.slice(erroresAntes), ["no_encontrado"], "onError del host");
  cierto(v.cambios.slice(cambiosAntes).includes(terreno), "onCambio del host (revalidación)");
  igual(v.subidas, 0, "subidas privadas en el DOM");
  igual(v.filas, 0, "archivos privados en el DOM");
  igual(v.nombreVisible, false, "nombre privado visible");
  igual(v.zonaOculta, true, "zona de subida visible");
  igual(v.escritura, 0, "controles de escritura visibles");
  igual(tardias, [], "peticiones del widget después de perder el alcance");
  return { mensaje: v.mensaje };
}
const contadores = () => page.evaluate(() => [window.__arnes.errores.length, window.__arnes.cambios.length]);

/* ------------------------------------------------------------ journeys */

await revisar("revocar el acceso mientras se completa: 404 limpia el detalle y llega al host", async () => {
  await seleccionar(T.uno.id);
  const completar = await retener("**/api/archivos/versiones/*/completar", "POST");
  const [e0, c0] = await contadores();
  await subirPdf("Privado alcance uno.pdf");
  await completar.entrada;
  await esperarRefrescosDelInicio();
  alTerminar.push(restaurarOlga);
  await revocarOlga();
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/completar"));
  completar.soltar();
  igual((await respuesta).status(), 404, "completar");
  const r = await comprobarAlcancePerdido("Privado alcance uno.pdf", T.uno.id, e0, c0);
  return r;
});

await revisar("revocar el acceso durante el PUT: 404 del contenido limpia y llega al host", async () => {
  await seleccionar(T.uno.id);
  const put = await retener("**/api/archivos/versiones/*/contenido", "PUT");
  const [e0, c0] = await contadores();
  await subirPdf("Privado alcance dos.pdf");
  await put.entrada;
  await esperarRefrescosDelInicio();
  alTerminar.push(restaurarOlga);
  await revocarOlga();
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/contenido"));
  put.soltar();
  igual((await respuesta).status(), 404, "PUT");
  const r = await comprobarAlcancePerdido("Privado alcance dos.pdf", T.uno.id, e0, c0);
  return r;
});

await revisar("transferir el terreno a otra base mientras se completa: 404 limpia y llega al host", async () => {
  await seleccionar(T.dos.id);
  const completar = await retener("**/api/archivos/versiones/*/completar", "POST");
  const [e0, c0] = await contadores();
  await subirPdf("Privado transferido.pdf");
  await completar.entrada;
  await esperarRefrescosDelInicio();
  alTerminar.push(async () => {
    const actual = (await api("GET", `/api/inventario/terrenos/${T.dos.id}`)).terreno;
    if (actual.base_id !== semilla.base) {
      await api("POST", `/api/inventario/terrenos/${T.dos.id}/transferir`, { expected_version: actual.version, base_id: semilla.base });
    }
  });
  const { terreno } = await api("GET", `/api/inventario/terrenos/${T.dos.id}`);
  await api("POST", `/api/inventario/terrenos/${T.dos.id}/transferir`, { expected_version: terreno.version, base_id: otraBase });
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/completar"));
  completar.soltar();
  igual((await respuesta).status(), 404, "completar");
  const r = await comprobarAlcancePerdido("Privado transferido.pdf", T.dos.id, e0, c0);
  return r;
});

await revisar("cancelar después de perder el acceso: el 404 de la cancelación también limpia", async () => {
  await seleccionar(T.uno.id);
  const put = await retener("**/api/archivos/versiones/*/contenido", "PUT");
  const [e0, c0] = await contadores();
  await subirPdf("Privado cancelado.pdf");
  await put.entrada;
  await esperarRefrescosDelInicio();
  alTerminar.push(restaurarOlga);
  await revocarOlga();
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/cancelar"));
  await detalle("pdf").locator(".archivos-subida").last().getByRole("button", { name: "Cancelar subida" }).click();
  igual((await respuesta).status(), 404, "cancelar");
  const r = await comprobarAlcancePerdido("Privado cancelado.pdf", T.uno.id, e0, c0);
  put.soltar();
  return r;
});

await revisar("archivar el terreno mientras se completa: permiso perdido, el host revalida y la lista se conserva", async () => {
  await seleccionar(T.uno.id);
  const completar = await retener("**/api/archivos/versiones/*/completar", "POST");
  const [e0, c0] = await contadores();
  await subirPdf("Privado archivado.pdf");
  await completar.entrada;
  await esperarRefrescosDelInicio();
  alTerminar.push(async () => {
    const t = (await api("GET", `/api/inventario/terrenos/${T.uno.id}`)).terreno;
    if (t.archived_at) await api("POST", `/api/inventario/terrenos/${T.uno.id}/restaurar`, { expected_version: t.version });
  });
  const { terreno } = await api("GET", `/api/inventario/terrenos/${T.uno.id}`);
  await api("POST", `/api/inventario/terrenos/${T.uno.id}/archivar`, { expected_version: terreno.version });
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/completar"));
  completar.soltar();
  igual((await respuesta).status(), 409, "completar");
  await page.waitForFunction((n) => window.__arnes.errores.length > n, e0, { timeout: 15000 });
  const v = await vistaDelDetalle("Privado archivado.pdf");
  igual(v.errores.slice(e0), ["terreno_archivado"], "onError del host");
  cierto(v.cambios.slice(c0).includes(T.uno.id), "onCambio del host (revalidación)");
  const fase = await detalle("pdf").locator(".archivos-subida").last().getAttribute("data-fase");
  igual(fase, "fallido", "la subida termina aquí");
  cierto(v.filas >= 1, "la lista legible se conserva");
  return { fase };
});

await revisar("cerrar el detalle mientras la cancelación espera: no sale ninguna petición después", async () => {
  await seleccionar(T.uno.id);
  const put = await retener("**/api/archivos/versiones/*/contenido", "PUT");
  await subirPdf("Privado cerrado.pdf");
  await put.entrada;
  await esperarRefrescosDelInicio();
  const vigia = vigilar();
  // Click "Cancelar subida" and close the detail in the same task.
  await page.evaluate((otro) => {
    [...document.querySelectorAll('[data-detalle="pdf"] .archivos-subida button')].find((b) => b.textContent === "Cancelar subida").click();
    document.querySelector(`.fila[data-id="${otro}"] button`).click();
  }, T.tres.id);
  put.soltar();
  await page.waitForTimeout(1500);
  const tardias = vigia.parar().filter((u) => /cancelar|completar|contenido|\/archivos$/.test(u) && !u.startsWith("GET"));
  igual(tardias, [], "escrituras tras cerrar");
  // The version stays pending on the server; its owner can still cancel it later.
  const lista = await page.evaluate(async (t) => (await (await fetch(`/api/inventario/terrenos/${t}/archivos`)).json()).archivos, T.uno.id);
  cierto(lista.some((a) => a.ultima_version?.nombre_original === "Privado cerrado.pdf" && a.ultima_version.estado === "subiendo"), "versión pendiente");
});

await revisar("control: con el acceso intacto una subida termina y una cancelación viva llega al servidor", async () => {
  await seleccionar(T.uno.id);
  await subirPdf("Ficticio control.pdf");
  await page.waitForFunction(() => [...document.querySelectorAll('[data-detalle="pdf"] .archivos-subida')].at(-1)?.dataset.fase === "listo", null, { timeout: 30000 });
  const put = await retener("**/api/archivos/versiones/*/contenido", "PUT");
  await subirPdf("Ficticio cancelado.pdf");
  await put.entrada;
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/cancelar"));
  await detalle("pdf").locator(".archivos-subida").last().getByRole("button", { name: "Cancelar subida" }).click();
  igual((await respuesta).status(), 200, "cancelar");
  await page.waitForFunction(() => [...document.querySelectorAll('[data-detalle="pdf"] .archivos-subida')].at(-1)?.dataset.fase === "cancelado", null, { timeout: 15000 });
  put.soltar();
});

await revisar("sin errores de página", async () => igual(consola, [], "errores"));

await navegador.close();
servidor.kill();
const resumen = { modo: semilla.modo, almacen: semilla.almacen, total: resultados.length, fallos, resultados };
if (process.env.ARCHIVOS_EVIDENCIA) writeFileSync(join(process.env.ARCHIVOS_EVIDENCIA, "alcance.json"), JSON.stringify(resumen, null, 2));
console.log(`\n${resultados.length - fallos}/${resultados.length} recorridos de alcance correctos (modo ${semilla.modo})`);
process.exit(fallos ? 1 : 0);

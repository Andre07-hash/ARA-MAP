/* 3B browser journeys: B's real widgets and loader against the real local
 * server (tests/e2e/archivos_servidor.py), real cookie sessions, local disk
 * storage and Chromium. Nothing is mocked.
 *
 *   cd tests/e2e && node archivos-recorridos.mjs
 *
 * CHROMIUM=/path/to/chrome picks the browser binary; ARCHIVOS_EVIDENCIA=/dir
 * writes a JSON summary there. The server prints its mode: "montado" (A's C1
 * routes) or "arnes" (temporary registration before C1, harness evidence).
 */

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, "..", "..");
const PUERTO = Number(process.env.ARCHIVOS_PUERTO ?? 8461);
const CLAVE = readFileSync(join(RAIZ, "tests", "support.py"), "utf8").match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const sha = (b) => createHash("sha256").update(b).digest("hex");

const resultados = [];
let fallos = 0;
let paginaActual = null;   // for failure diagnostics
async function revisar(nombre, fn) {
  const inicio = Date.now();
  try {
    const detalle = await fn();
    resultados.push({ nombre, ok: true, ms: Date.now() - inicio, ...(detalle ? { detalle } : {}) });
    console.log(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    const vista = await paginaActual?.evaluate(() => ({
      subidas: [...document.querySelectorAll(".archivos-subida")].map((li) => `${li.dataset.fase}: ${li.textContent}`),
      mensajes: [...document.querySelectorAll(".archivos-mensaje")].map((p) => p.textContent).filter(Boolean),
      errores: window.__arnes?.errores?.slice(-5),
      kmz: (document.querySelector('[data-detalle="kmz"]')?.innerText ?? "").slice(0, 1200),
      expandidos: [...document.querySelectorAll("[aria-expanded]")].map((b) => `${b.textContent}=${b.getAttribute("aria-expanded")}`),
    })).catch(() => null);
    resultados.push({ nombre, ok: false, error: String(error?.stack ?? error), vista });
    if (vista) console.log(`     vista: ${JSON.stringify(vista).slice(0, 1500)}`);
    console.log(`FALLO ${nombre}\n     ${String(error?.message ?? error).split("\n")[0]}`);
  }
}
const igual = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const cierto = (v, m) => { if (!v) throw new Error(m); };

/* ------------------------------------------------------------ server */

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
const F = semilla.fixtures;
const pagina = `${URLBASE}/__arnes/arnes.html#${encodeURIComponent(JSON.stringify(Object.values(T)))}`;
console.log(`servidor en modo ${semilla.modo}, almacén ${semilla.almacen}`);

// A UTF-8 locale: in a C-locale container Chromium names any non-ASCII download "download".
const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium",
  env: { ...process.env, LANG: "C.UTF-8", LC_ALL: "C.UTF-8" } });

async function sesion(usuario) {
  const contexto = await navegador.newContext({ acceptDownloads: true, viewport: { width: 1300, height: 1400 } });
  const page = await contexto.newPage();
  const consola = [];
  page.on("pageerror", (e) => consola.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") consola.push(m.text()); });
  await page.goto(pagina);
  await page.waitForFunction(() => document.title === "listo");
  await page.fill("#entrar [name=usuario]", usuario);
  await page.fill("#entrar [name=clave]", CLAVE);
  await page.click("#entrar button[type=submit]");
  await page.waitForFunction(() => window.__arnes.widgets && window.__arnes.modo);
  return { contexto, page, consola };
}
const celda = (page, id, tipo) => page.locator(`.fila[data-id="${id}"] [data-celda="${tipo}"] .archivos-celda`);
const detalle = (page, tipo) => page.locator(`[data-detalle="${tipo}"]`);
async function textoCelda(page, id, tipo, esperado) {
  await page.waitForFunction(([i, t, e]) => document.querySelector(`.fila[data-id="${i}"] [data-celda="${t}"] .archivos-celda`)?.textContent === e,
    [id, tipo, esperado], { timeout: 30000 });
}
async function seleccionar(page, id) {
  await page.click(`.fila[data-id="${id}"] button`);
  await page.waitForFunction((i) => window.__arnes.seleccionado === i, id);
}
/* The file's bytes and its (possibly non-ASCII) name, handed to the real file
 * input. Paths with non-ASCII characters are not passed through, because
 * Playwright does not reliably deliver them in a C-locale container. */
async function subir(page, tipo, ruta) {
  const nombre = ruta.split("/").at(-1);
  const mimeType = nombre.endsWith(".pdf") ? "application/pdf" : nombre.endsWith(".kmz") ? "application/vnd.google-earth.kmz" : "text/plain";
  await detalle(page, tipo).locator(".archivos-zona input[type=file]").setInputFiles({ name: nombre, mimeType, buffer: readFileSync(ruta) });
}
async function faseFinal(page, tipo, fases, timeout = 60000) {
  await page.waitForFunction(([t, f]) => {
    const li = [...document.querySelectorAll(`[data-detalle="${t}"] .archivos-subida`)].at(-1);
    return li && f.includes(li.dataset.fase);
  }, [tipo, fases], { timeout });
  return detalle(page, tipo).locator(".archivos-subida").last().getAttribute("data-fase");
}
async function estado(page, id) {
  return page.evaluate(async (i) => (await (await fetch(`/api/__arnes/terrenos/${i}/archivos-estado`)).json()), id);
}

/* ---------------------------------------------------------- journeys */

const olga = await sesion("olga");
paginaActual = olga.page;

await revisar("los widgets montan con el resumen real: sin archivos no es 'cargando'", async () => {
  await textoCelda(olga.page, T.uno.id, "pdf", "Sin PDF");
  await textoCelda(olga.page, T.uno.id, "kmz", "Sin KMZ");
  return { modo: await olga.page.evaluate(() => window.__arnes.modo), puente: await olga.page.evaluate(() => window.__arnes.puente) };
});

await revisar("un PDF sube (huella → inicio → PUT → completar) y la celda se actualiza por onCambio", async () => {
  await seleccionar(olga.page, T.uno.id);
  await subir(olga.page, "pdf", F.pdf);
  igual(await faseFinal(olga.page, "pdf", ["listo", "fallido", "incierto"]), "listo", "fase");
  await textoCelda(olga.page, T.uno.id, "pdf", "1 PDF");
  const cambios = await olga.page.evaluate(() => window.__arnes.cambios.length);
  cierto(cambios >= 1, "onCambio no se llamó");
  await detalle(olga.page, "pdf").locator(".archivos-item", { hasText: "Avalúo ficticio.pdf" }).waitFor();
});

await revisar("la descarga autenticada entrega exactamente los bytes guardados", async () => {
  const item = detalle(olga.page, "pdf").locator(".archivos-item", { hasText: "Avalúo ficticio.pdf" });
  const [descarga] = await Promise.all([olga.page.waitForEvent("download"), item.getByRole("button", { name: /^Descargar/ }).click()]);
  const ruta = await descarga.path();
  igual(sha(readFileSync(ruta)), sha(readFileSync(F.pdf)), "sha256");
  igual(descarga.suggestedFilename(), "Avalúo ficticio.pdf", "nombre");
});

await revisar("un archivo que no es PDF se rechaza antes de leerlo", async () => {
  await subir(olga.page, "pdf", F.no_pdf);
  igual(await faseFinal(olga.page, "pdf", ["fallido"]), "fallido", "fase");
  const texto = await detalle(olga.page, "pdf").locator(".archivos-subida").last().textContent();
  cierto(/Elige un archivo PDF/.test(texto), texto);
});

await revisar("un KMZ de un contorno se activa y el mapa carga solo ese contorno verificado", async () => {
  await subir(olga.page, "kmz", F.kmz_simple);
  igual(await faseFinal(olga.page, "kmz", ["listo", "fallido", "rechazado", "incierto"]), "listo", "fase");
  await textoCelda(olga.page, T.uno.id, "kmz", "Contorno activo");
  await olga.page.waitForFunction(() => window.__arnes.cargas.at(-1)?.resultado === "cargado", null, { timeout: 30000 });
  const r = await olga.page.evaluate(() => ({ render: window.__arnes.ultimoRender, carga: window.__arnes.cargas.at(-1),
    cargador: window.__arnes.estadoCargador(), aviso: document.querySelector("#aviso-mapa").textContent }));
  igual(r.render.cuerpos, 1, "un solo cuerpo entregado al renderer");
  igual(r.cargador, { enCurso: 0, enEspera: 0, listos: 1, destruido: false }, "residencia");
  cierto(/Página actual: 3 terrenos/.test(r.aviso) && /los demás se cargan al seleccionarlos/.test(r.aviso), r.aviso);
  return { bytes: r.carga.bytes, ms_carga: Math.round(r.carga.cargado - r.carga.inicio) };
});

await revisar("un KMZ con varios contornos exige elegir y activar explícitamente", async () => {
  await seleccionar(olga.page, T.dos.id);
  await subir(olga.page, "kmz", F.kmz_varios);
  igual(await faseFinal(olga.page, "kmz", ["requiere_seleccion", "listo", "rechazado", "fallido"]), "requiere_seleccion", "fase");
  await textoCelda(olga.page, T.dos.id, "kmz", "KMZ sin contorno activo");
  const d = detalle(olga.page, "kmz");
  await d.locator(".archivos-item").first().getByRole("button", { name: "Versiones" }).click();
  await d.getByRole("button", { name: /Contornos de la versión 1/ }).click();
  await d.getByRole("button", { name: "Elegir contornos…" }).click();
  const casillas = d.locator(".archivos-candidatos input[type=checkbox]:not([disabled])");
  await casillas.first().waitFor();
  const n = await casillas.count();
  cierto(n >= 2, `candidatos válidos: ${n}`);
  await casillas.first().check();
  await d.getByRole("button", { name: "Procesar selección" }).click();
  await d.locator(".archivos-mensaje", { hasText: "Selección válida. Todavía no está activa" }).waitFor({ timeout: 30000 });
  await d.locator(".archivos-intento", { hasText: "Contorno válido" }).waitFor();
  igual(await celda(olga.page, T.dos.id, "kmz").textContent(), "KMZ sin contorno activo", "no se activa sola");
  await d.locator(".archivos-intento", { hasText: "Contorno válido" }).getByRole("button", { name: "Activar este contorno" }).click();
  await textoCelda(olga.page, T.dos.id, "kmz", "Contorno activo");
  await olga.page.waitForFunction(() => window.__arnes.cargas.at(-1)?.resultado === "cargado", null, { timeout: 30000 });
  return { candidatos_validos: n };
});

let geometriaOriginal;
await revisar("un reemplazo fallido conserva el contorno activo anterior", async () => {
  await seleccionar(olga.page, T.uno.id);
  geometriaOriginal = (await estado(olga.page, T.uno.id)).geometria.id;
  await subir(olga.page, "kmz", F.kmz_invalido);
  igual(await faseFinal(olga.page, "kmz", ["rechazado", "listo", "fallido"]), "rechazado", "fase");
  igual((await estado(olga.page, T.uno.id)).geometria.id, geometriaOriginal, "geometría activa");
  await textoCelda(olga.page, T.uno.id, "kmz", "Contorno activo");
});

await revisar("un reemplazo válido se activa y una versión retenida se puede volver a activar", async () => {
  await subir(olga.page, "kmz", F.kmz_reemplazo);
  igual(await faseFinal(olga.page, "kmz", ["listo", "no_aplicada", "rechazado", "fallido"]), "listo", "fase");
  await olga.page.waitForFunction((g) => window.__arnes.descriptores[window.__arnes.seleccionado]?.id && window.__arnes.descriptores[window.__arnes.seleccionado].id !== g, geometriaOriginal);
  const d = detalle(olga.page, "kmz");
  await d.locator(".archivos-item").first().getByRole("button", { name: "Versiones" }).click();
  await d.getByRole("button", { name: /Contornos de la versión 1/ }).click();
  await d.getByRole("button", { name: "Activar este contorno" }).first().click();
  await olga.page.waitForFunction((g) => window.__arnes.descriptores[window.__arnes.seleccionado]?.id === g, geometriaOriginal, { timeout: 30000 });
  await olga.page.waitForFunction(() => window.__arnes.cargas.at(-1)?.resultado === "cargado", null, { timeout: 30000 });
});

/* A second, independent session. */
const omar = await sesion("omar");

await revisar("una segunda sesión autorizada lee los archivos guardados y el contorno real", async () => {
  await textoCelda(omar.page, T.uno.id, "pdf", "1 PDF");
  await textoCelda(omar.page, T.uno.id, "kmz", "Contorno activo");
  await omar.page.waitForFunction(() => window.__arnes.cargas.at(-1)?.resultado === "cargado", null, { timeout: 30000 });
  const item = detalle(omar.page, "pdf").locator(".archivos-item", { hasText: "Avalúo ficticio.pdf" });
  const [descarga] = await Promise.all([omar.page.waitForEvent("download"), item.getByRole("button", { name: /^Descargar/ }).click()]);
  igual(sha(readFileSync(await descarga.path())), sha(readFileSync(F.pdf)), "sha256");
  const r = await omar.page.evaluate(() => window.__arnes.cargas.at(-1));
  igual(r.geometria, geometriaOriginal, "la misma geometría activa");
});

await revisar("la subida pendiente de otra cuenta se ve genérica, sin nombre ni tamaño", async () => {
  // olga registers an upload and stops before the PUT (its file stays local).
  const vid = await olga.page.evaluate(async ([t, s]) => {
    const r = await fetch(`/api/inventario/terrenos/${t}/archivos`, { method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ tipo: "pdf", nombre_original: "Privado ficticio.pdf", tamano_declarado: 1234, sha256_declarado: s }) });
    return (await r.json()).version_id;
  }, [T.dos.id, "a".repeat(64)]);
  await seleccionar(omar.page, T.dos.id);
  const texto = await detalle(omar.page, "pdf").textContent();
  cierto(!texto.includes("Privado ficticio"), "el nombre ajeno aparece");
  await detalle(omar.page, "pdf").getByText("Otra cuenta está subiendo una versión").first().waitFor();
  const e = await estado(omar.page, T.dos.id);
  cierto(!JSON.stringify(e).includes("Privado ficticio") && !JSON.stringify(e).includes(vid), "el resumen filtra datos privados");
  return { version_privada: "oculta" };
});

const otto = await sesion("otto");
await revisar("una cuenta sin permiso no ve nada: 404 indistinguible en lista, descarga y contorno", async () => {
  const r = await otto.page.evaluate(async ([t, g]) => {
    const pedir = async (ruta, o) => { const x = await fetch(ruta, o); return [x.status, await x.text()]; };
    return {
      estado: await pedir(`/api/__arnes/terrenos/${t}/archivos-estado`),
      lista: await pedir(`/api/inventario/terrenos/${t}/archivos`),
      metadatos: await pedir("/api/archivos/geometrias/metadatos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: [g] }) }),
      fragmento: await pedir(`/api/archivos/geometrias/${g}/contenido?desde=0`),
      inexistente: await pedir(`/api/archivos/geometrias/${crypto.randomUUID()}/contenido?desde=0`),
    };
  }, [T.uno.id, geometriaOriginal]);
  igual(r.lista[0], 404, "lista");
  igual(r.fragmento, r.inexistente, "fragmento ajeno = inexistente");
  igual(JSON.parse(r.metadatos[1]).no_disponibles, [geometriaOriginal], "metadatos");
  const cargas = await otto.page.evaluate(() => window.__arnes.cargas);
  cierto(cargas.every((c) => c.resultado !== "cargado"), "otto no debe cargar ningún contorno");
  const texto = await otto.page.locator("#detalles").textContent();
  cierto(!texto.includes("Avalúo ficticio"), "otto ve un nombre de archivo");
  return { estado_harness: r.estado[0] };
});

await revisar("solo lectura deshabilita controles pero no descargas", async () => {
  await seleccionar(olga.page, T.uno.id);
  const d = detalle(olga.page, "pdf");
  await d.getByRole("button", { name: /^Retirar/ }).first().waitFor();
  try {
    await olga.page.evaluate(() => window.__arnes.ponerSoloLectura(true));
    cierto(await d.locator(".archivos-zona").isHidden(), "zona de subida visible");
    igual(await d.getByRole("button", { name: /^Retirar/ }).count(), 0, "retirar presente");
    await d.getByRole("button", { name: /^Descargar/ }).first().waitFor();
    cierto(await d.getByRole("button", { name: /^Descargar/ }).first().isEnabled(), "descarga deshabilitada");
  } finally {
    await olga.page.evaluate(() => window.__arnes.ponerSoloLectura(false));
  }
  await d.getByRole("button", { name: /^Retirar/ }).first().waitFor();
});

await revisar("cancelar una subida en curso usa el endpoint y lo informa", async () => {
  const cdp = await olga.contexto.newCDPSession(olga.page);
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: 16 * 1024 });
  await subir(olga.page, "kmz", F.kmz_limite);
  await olga.page.waitForFunction(() => [...document.querySelectorAll('[data-detalle="kmz"] .archivos-subida')].at(-1)?.dataset.fase === "subiendo", null, { timeout: 30000 });
  await detalle(olga.page, "kmz").locator(".archivos-subida").last().getByRole("button", { name: "Cancelar subida" }).click();
  igual(await faseFinal(olga.page, "kmz", ["cancelado", "incierto", "fallido"]), "cancelado", "fase");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  const versiones = await olga.page.evaluate(async (t) => {
    const lista = await (await fetch(`/api/inventario/terrenos/${t}/archivos`)).json();
    const kmz = lista.archivos.find((a) => a.tipo === "kmz");
    return (await (await fetch(`/api/archivos/${kmz.id}/versiones?limite=1`)).json()).versiones;
  }, T.uno.id);
  igual(versiones[0].estado, "cancelado", "estado en el servidor");
});

await revisar("retirar exige confirmación y es definitivo", async () => {
  const d = detalle(olga.page, "pdf");
  await d.getByRole("button", { name: /^Retirar/ }).first().click();
  await olga.page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
  await textoCelda(olga.page, T.uno.id, "pdf", "1 PDF");
  await d.getByRole("button", { name: /^Retirar/ }).first().click();
  await olga.page.getByRole("dialog").getByRole("button", { name: "Retirar" }).click();
  await textoCelda(olga.page, T.uno.id, "pdf", "Sin PDF");
  await d.locator(".archivos-chip-retirado").first().waitFor();
  // Retained content stays downloadable under current authorization.
  await d.locator(".archivos-item").first().getByRole("button", { name: "Versiones" }).click();
  const [descarga] = await Promise.all([olga.page.waitForEvent("download"),
    d.getByRole("button", { name: /Descargar versión 1/ }).click()]);
  igual(sha(readFileSync(await descarga.path())), sha(readFileSync(F.pdf)), "sha256 retenido");
});

await revisar("al expirar la sesión durante trabajo activo todo se desmonta y nada se instala después", async () => {
  const cdp = await olga.contexto.newCDPSession(olga.page);
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: 16 * 1024 });
  await seleccionar(olga.page, T.tres.id);
  await subir(olga.page, "kmz", F.kmz_limite);
  await olga.page.waitForFunction(() => [...document.querySelectorAll('[data-detalle="kmz"] .archivos-subida')].at(-1)?.dataset.fase === "subiendo", null, { timeout: 30000 });
  // The session ends at the server (logout from another tab of the same account).
  const otra = await olga.contexto.newPage();
  await otra.goto(`${URLBASE}/__arnes/arnes.html`);
  await otra.evaluate(() => fetch("/api/logout", { method: "POST" }));
  await otra.close();
  // The next private request through the bridge answers 401: the bridge runs the
  // expiry teardown (not the logout button), cancelling the throttled PUT too.
  const subidaAntes = await detalle(olga.page, "kmz").locator(".archivos-subida").last().getAttribute("data-fase");
  igual(subidaAntes, "subiendo", "subida en curso al expirar");
  await olga.page.evaluate(() => window.__arnes.refrescarTerreno());
  await olga.page.waitForFunction(() => window.__arnes.expiraciones === 1 && !window.__arnes.widgets, null, { timeout: 10000 });
  const peticiones = [];
  olga.page.on("request", (r) => { if (r.url().includes("/api/")) peticiones.push(r.url()); });
  await olga.page.evaluate(() => {
    window.__mutaciones = 0;
    new MutationObserver((m) => { window.__mutaciones += m.length; }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await olga.page.waitForTimeout(3000);
  const r = await olga.page.evaluate(() => ({ mutaciones: window.__mutaciones, widgets: Boolean(window.__arnes.widgets),
    archivos: document.querySelectorAll(".archivos-detalle, .archivos-celda, dialog").length, cargador: window.__arnes.estadoCargador() }));
  igual(r.widgets, false, "widgets vivos");
  igual(r.archivos, 0, "contenido privado en el DOM");
  igual(r.mutaciones, 0, "instalaciones tardías");
  igual(peticiones.filter((u) => /completar|contenido|metadatos/.test(u)), [], "peticiones tras el cierre");
});

for (const s of [olga, omar, otto]) {
  await revisar(`sin errores de página (${s === olga ? "olga" : s === omar ? "omar" : "otto"})`, async () => igual(s.consola.filter((t) => !/401|404|Failed to load resource/.test(t)), [], "errores"));
}

await navegador.close();
servidor.kill();
const resumen = { modo: semilla.modo, almacen: semilla.almacen, total: resultados.length, fallos, resultados };
if (process.env.ARCHIVOS_EVIDENCIA) writeFileSync(join(process.env.ARCHIVOS_EVIDENCIA, "recorridos.json"), JSON.stringify(resumen, null, 2));
console.log(`\n${resultados.length - fallos}/${resultados.length} recorridos correctos (modo ${semilla.modo})`);
process.exit(fallos ? 1 : 0);

/* 3B near-limit measurement: one accepted 100,000-vertex boundary, uploaded
 * through B's widget, loaded by B's loader (metadata + 512 KiB chunks, hash,
 * strict parse) and drawn by the UNCHANGED renderer, in Chromium against the
 * real local server (tests/e2e/archivos_servidor.py).
 *
 *   cd tests/e2e && node archivos-medicion.mjs
 *
 * Reports timings and JS-heap samples (CDP Runtime.getHeapUsage every 20 ms).
 * The heap is the page's JS heap only, not process RSS and not a total-browser
 * budget. ARCHIVOS_EVIDENCIA=/dir writes medicion.json there.
 */

import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, "..", "..");
const PUERTO = Number(process.env.ARCHIVOS_PUERTO ?? 8463);
const CLAVE = readFileSync(join(RAIZ, "tests", "support.py"), "utf8").match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const MiB = 1024 * 1024;

const servidor = spawn("python3", [join(AQUI, "archivos_servidor.py"), "--puerto", String(PUERTO)],
  { cwd: RAIZ, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => servidor.kill());
const semilla = await new Promise((resolve, reject) => {
  let texto = "";
  servidor.stdout.on("data", (d) => {
    texto += d;
    const json = texto.split("\n").find((l) => l.startsWith("{"));
    if (json && texto.includes("LISTO")) resolve(JSON.parse(json));
  });
  servidor.on("exit", (c) => reject(new Error(`el servidor salió (${c})`)));
});
const T = Object.values(semilla.terrenos);
const kmzLimite = readFileSync(semilla.fixtures.kmz_limite);

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium",
  env: { ...process.env, LANG: "C.UTF-8", LC_ALL: "C.UTF-8" } });
const contexto = await navegador.newContext({ viewport: { width: 1300, height: 1200 } });
const page = await contexto.newPage();
const errores = [];
page.on("pageerror", (e) => errores.push(String(e)));
const cdp = await contexto.newCDPSession(page);
await cdp.send("HeapProfiler.enable");

await page.goto(`http://127.0.0.1:${PUERTO}/__arnes/arnes.html#${encodeURIComponent(JSON.stringify(T))}`);
await page.waitForFunction(() => document.title === "listo");
await page.fill("#entrar [name=usuario]", "olga");
await page.fill("#entrar [name=clave]", CLAVE);
await page.click("#entrar button[type=submit]");
await page.waitForFunction(() => window.__arnes.widgets && window.__arnes.seleccionado);

const gc = async () => { await cdp.send("HeapProfiler.collectGarbage"); await cdp.send("HeapProfiler.collectGarbage"); };
const heap = async () => (await cdp.send("Runtime.getHeapUsage")).usedSize;
function muestreo() {
  const muestras = [];
  let vivo = true;
  (async () => { while (vivo) { try { muestras.push(await heap()); } catch { break; } await new Promise((r) => setTimeout(r, 20)); } })();
  return { parar: () => { vivo = false; return muestras; } };
}

/* 1. Upload through the widget: hash, start, PUT, completion with the parser. */
await gc();
const base0 = await heap();
const m1 = muestreo();
const t0 = Date.now();
await page.locator('[data-detalle="kmz"] .archivos-zona input[type=file]')
  .setInputFiles({ name: "Límite ficticio.kmz", mimeType: "application/vnd.google-earth.kmz", buffer: kmzLimite });
let tCompletando = null;
for (;;) {
  const fase = await page.evaluate(() => [...document.querySelectorAll('[data-detalle="kmz"] .archivos-subida')].at(-1)?.dataset.fase);
  if (fase === "completando" && tCompletando === null) tCompletando = Date.now();
  if (["listo", "fallido", "rechazado", "incierto", "no_aplicada", "requiere_seleccion"].includes(fase)) {
    if (fase !== "listo") throw new Error(`la subida terminó en ${fase}`);
    break;
  }
  if (Date.now() - t0 > 180_000) throw new Error("la subida no terminó");
  await new Promise((r) => setTimeout(r, 50));
}
const subida = { total_ms: Date.now() - t0, completar_ms: tCompletando ? Date.now() - tCompletando : null,
  bytes_kmz: kmzLimite.length, pico_heap_mib: Math.max(...m1.parar()) / MiB, base_heap_mib: base0 / MiB };

/* 2. The selected boundary: metadata + chunks + hash + parse, then the renderer. */
await page.waitForFunction(() => window.__arnes.cargas.at(-1)?.resultado === "cargado", null, { timeout: 120_000 });
const primera = await page.evaluate(() => window.__arnes.cargas.at(-1));

// A clean, measured reload of the same boundary (the first one overlapped the upload).
await page.evaluate(() => { window.__arnes.cargador.reset(); window.__arnes.canvas.render([]); });
await gc();
const antes = await heap();
const m2 = muestreo();
const peticiones = [];
const escuchar = (r) => { if (r.url().includes("/api/archivos/geometrias/")) peticiones.push(r); };
page.on("request", escuchar);
await page.evaluate(() => window.__arnes.recargarContorno());
await page.waitForFunction(() => window.__arnes.cargas.at(-1)?.resultado === "cargado", null, { timeout: 120_000 });
const pico = Math.max(...m2.parar());
page.off("request", escuchar);
const carga = await page.evaluate(() => window.__arnes.cargas.at(-1));
const cuerpo = await page.evaluate(() => {
  const h = window.__arnes;
  const d = h.descriptores[h.seleccionado];
  return { descriptor: d.id, render: h.ultimoRender, escala: h.canvas.zoomToScale(h.seleccionado) };
});
await gc();
const conCuerpo = await heap();

// Exact bytes: the loader's verified hash against the stored geometry's.
const verificado = await page.evaluate(async () => {
  const h = window.__arnes;
  const id = h.descriptores[h.seleccionado].id;
  const r = await fetch("/api/archivos/geometrias/metadatos", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids: [id] }) });
  return (await r.json()).geometrias[id];
});

/* 3. Release: reset the loader and drop the renderer's body. */
await page.evaluate(() => { window.__arnes.cargador.reset(); window.__arnes.canvas.render([]); });
await gc();
const despues = await heap();

const resultado = {
  modo: semilla.modo, almacen: semilla.almacen, navegador: navegador.version(),
  subida,
  geometria: {
    bytes: carga.bytes, vertices: carga.vertices, sha256_cargado: carga.sha256, sha256_servidor: verificado.sha256, fragmentos: verificado.fragmentos,
    peticiones: peticiones.length, cargar_y_verificar_ms: Math.round(carga.cargado - carga.inicio),
    dibujar_ms: Math.round(carga.dibujado - carga.cargado), primera_carga_ms: Math.round(primera.cargado - primera.inicio),
    render: cuerpo.render, zoom_a_escala: cuerpo.escala,
  },
  heap_mib: { antes: antes / MiB, pico_durante_carga: pico / MiB, con_cuerpo_listo: conCuerpo / MiB, tras_reset: despues / MiB },
  errores,
};
console.log(JSON.stringify(resultado, null, 2));
if (process.env.ARCHIVOS_EVIDENCIA) writeFileSync(join(process.env.ARCHIVOS_EVIDENCIA, "medicion.json"), JSON.stringify(resultado, null, 2));
const ok = resultado.geometria.vertices === 100_000 && carga.sha256 === verificado.sha256 && resultado.geometria.render.cuerpos === 1 && errores.length === 0
  && resultado.geometria.peticiones === 1 + verificado.fragmentos;
console.log(ok ? "medición completa" : "MEDICIÓN CON PROBLEMAS");
await navegador.close();
process.exit(ok ? 0 : 1);

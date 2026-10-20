// Writes the mockup pages and renders a PNG of each one.
//   node generar.mjs            (HTML only)
//   node generar.mjs --png      (HTML + PNG, needs Playwright and Chromium)
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CSS_BASE } from "./comun.mjs";
import { generarA } from "./direccionA.mjs";

const AQUI = dirname(fileURLToPath(import.meta.url));
const MOCK = join(AQUI, "..", "mockups"), PNG = join(AQUI, "..", "capturas");
mkdirSync(MOCK, { recursive: true }); mkdirSync(PNG, { recursive: true });
const solo = process.argv.find((a) => a.startsWith("--solo="))?.slice(7);

const conjuntos = [generarA];
for (const m of ["./direccionB.mjs", "./direccionC.mjs"]) {
  try { const mod = await import(m); conjuntos.push(Object.values(mod).find((f) => typeof f === "function" && f.name.startsWith("generar"))); } catch (e) { if (e.code !== "ERR_MODULE_NOT_FOUND") throw e; }
}
const escritos = [];
for (const gen of conjuntos) {
  const { css = "", ...paginas } = gen();
  for (const [archivo, [titulo, cuerpo]] of Object.entries(paginas)) {
    if (solo && !archivo.startsWith(solo)) continue;
    const html = cuerpo.startsWith("<!doctype") ? cuerpo : `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${titulo}</title><style>${CSS_BASE}${css}</style></head><body>${cuerpo}</body></html>`;
    writeFileSync(join(MOCK, archivo), html);
    escritos.push(archivo);
  }
}
console.log("HTML:", escritos.join(", "));
if (process.argv.includes("--png")) {
  const { chromium } = await import("playwright");
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium" });
  const page = await nav.newPage({ viewport: { width: 1800, height: 900 }, deviceScaleFactor: 1 });
  for (const a of escritos) {
    await page.goto("file://" + join(MOCK, a));
    await page.waitForTimeout(150);
    const nodo = (await page.$(".hoja")) ?? (await page.$("body"));
    await nodo.screenshot({ path: join(PNG, a.replace(".html", ".png")) });
  }
  await nav.close();
  console.log("PNG listos");
}

// Click-through of every control in WebKit (Safari's engine), as an administrator.
// Safari does not focus a clicked button, which once closed the ⋯ and account
// menus before their items' clicks landed. Needs Playwright's WebKit
// (`node node_modules/playwright-core/cli.js install webkit`) and the table's
// test server: python3 tests/e2e/tabla_servidor.py --puerto 8471 --registros 300
//   PUERTO=8471 node tests/e2e/safari-clics.mjs
import { webkit } from "playwright-core";
import { readFileSync } from "node:fs";

const BASE = `http://localhost:${process.env.PUERTO ?? 8471}`;
const CLAVE = readFileSync(new URL("../support.py", import.meta.url), "utf8").match(/TEST_PASSWORD = "(.*)"/)[1];
const fallos = [];
const browser = await webkit.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, acceptDownloads: true });
page.setDefaultTimeout(4000);
const errores = [];
page.on("pageerror", (e) => errores.push(e.message + " @ " + (e.stack ?? "").split("\n").slice(0, 3).join(" < ")));

async function paso(nombre, fn) {
  try { await fn(); console.log("ok   ", nombre); }
  catch (e) { fallos.push(nombre); console.log("FALLO", nombre, "—", e.message.split("\n")[0]); }
  await page.keyboard.press("Escape").catch(() => {});
  await page.evaluate(() => { document.querySelectorAll("dialog[open]").forEach((d) => d.close()); document.querySelectorAll("details[open]").forEach((d) => { d.open = false; }); });
}
const visible = (sel) => page.locator(sel).first().waitFor({ state: "visible" });
const menu = async (texto) => {
  await page.click(".tabla-acciones .menu-mas > summary");
  await page.locator(".tabla-acciones .menu-item").filter({ has: page.locator(".menu-item-texto", { hasText: new RegExp(`^${texto}`) }) }).first().click();
};
const vista = async (texto) => {
  await page.selectOption("#tabla-vista", { label: texto });
  await page.waitForTimeout(1200);
};

await page.goto(BASE + "/?test=1#/tabla/maestra");
if (!(await page.locator("#login-usuario").isVisible().catch(() => false))) {
  await page.locator("button", { hasText: "Iniciar sesión" }).first().click();
}
await page.fill("#login-usuario", "ada");
await page.fill("#login-clave", CLAVE);
await page.locator("dialog[open] button[type=submit], form button[type=submit]").first().click();
await visible(".tabla-grid tbody tr");

await paso("Safari no enfoca botones (control del arnés)", async () => {
  await page.click(".tabla-acciones .menu-mas > summary");
  const foco = await page.evaluate(() => document.activeElement?.tagName);
  console.log("      foco tras clic en summary:", foco);
});
await paso("Cuenta → Ver catálogo público", async () => {
  await page.click(".cuenta > summary");
  await page.locator(".cuenta .menu-item", { hasText: "Ver catálogo público" }).click();
  await page.waitForURL(/catalogo/);
  await page.goBack(); await visible(".tabla-grid tbody tr");
});
await paso("⋯ → Exportar a Excel", async () => {
  const descarga = page.waitForEvent("download");
  await menu("Exportar a Excel");
  await descarga;
});
await paso("⋯ → Importar Excel…", async () => { await menu("Importar Excel"); await visible("dialog[open] .importar, dialog[open]"); });
await paso("⋯ → Mostrar columnas (casilla y Listo)", async () => {
  await menu("Mostrar columnas");
  await page.locator("dialog[open] label.check", { hasText: "Asking price" }).click();
  if (await page.locator('.tabla-grid th[data-col="core:asking_price"]').isVisible()) throw new Error("no se escondió");
  await page.locator("dialog[open] button", { hasText: "Listo" }).click();
  await page.locator("dialog[open]").waitFor({ state: "detached" }).catch(() => {});
  await page.evaluate(() => localStorage.clear());
});
await paso("⋯ → Settings", async () => { await menu("Settings"); await visible("dialog[open]"); });
await paso("⋯ → Actualizar", async () => { await menu("Actualizar"); await page.waitForTimeout(500); });
await paso("Filtros → casilla → Ver terrenos → chip ×", async () => {
  await page.click("button[aria-controls=tabla-filtros]");
  await visible("#tabla-filtros[open]");
  await page.locator("#tabla-filtros .tabla-casillas label.check").first().click();
  await page.locator("#tabla-filtros button", { hasText: /Ver .* terrenos/ }).click();
  await visible(".tabla-filtro-chip");
  await page.locator(".tabla-filtro-chip .tabla-chip-quitar").first().click();
  await page.waitForTimeout(800);
  if (await page.locator(".tabla-filtro-chip").count()) throw new Error("el chip no se quitó");
});
await paso("Filtros → Limpiar", async () => {
  await page.click("button[aria-controls=tabla-filtros]");
  await page.locator("#tabla-filtros .tabla-casillas label.check").first().click();
  await page.locator("#tabla-filtros button", { hasText: "Limpiar" }).click();
});
await paso("Paginación Siguiente / Anterior", async () => {
  await page.locator("button", { hasText: "Siguiente" }).click(); await page.waitForTimeout(800);
  await page.locator("button", { hasText: "Anterior" }).click(); await page.waitForTimeout(800);
});
await paso("Fila → casilla → barra de selección → Quitar selección", async () => {
  await page.locator("tbody input.tabla-marca").first().click();
  await visible(".tabla-lote:not([hidden])");
  await page.locator(".tabla-lote button", { hasText: "Quitar selección" }).click();
  await page.locator(".tabla-lote").waitFor({ state: "hidden" });
});
await paso("Fila → ··· abre la ficha y se cierra", async () => {
  await page.locator("tbody .tabla-abrir").first().click();
  await visible("dialog[open]");
  const botones = await page.locator("dialog[open] button:visible").allTextContents();
  console.log("      botones de la ficha:", botones.map((b) => b.trim()).filter(Boolean).join(" | "));
});
await paso("Celda → editar → Escape", async () => {
  await page.locator('tbody td[data-col="core:estado"]').first().dblclick();
  await visible("tbody td input, tbody td textarea");
});
await paso("Cambiar de vista a una base", async () => { await vista("Base Grande"); await visible(".tabla-grid tbody tr"); });
await paso("⋯ → Columnas (en una base)", async () => { await menu("Columnas"); await visible("dialog[open] .columnas-lista, dialog[open]"); });
await paso("Agregar terreno", async () => {
  await page.locator("button", { hasText: "Agregar terreno" }).click();
  await page.waitForTimeout(1200);
});
await paso("Tabla → Mapa", async () => { await page.locator(".tabla-modo button", { hasText: "Mapa" }).click(); await visible(".previa-mapa"); await page.waitForTimeout(1500); });
for (const fondo of ["Satélite", "Calles", "Claro"]) {
  await paso(`Mapa → ${fondo}`, async () => {
    await page.locator(".previa-fondos button, .previa-fondos label", { hasText: fondo }).first().click();
  });
}
await paso("Mapa → Encuadrar todo", async () => { await page.locator(".previa-encuadre").click(); await page.waitForTimeout(800); });
await paso("Mapa → clic en un terreno abre el mini panel → Ver a escala → ×", async () => {
  const ids = await page.evaluate(() => window.__araTabla?.mapa().filas ?? []);
  let p = null;
  for (const id of ids) {
    const q = await page.evaluate((i) => window.__araTabla.posicion(i), id);
    if (q && q.x > 80 && q.y > 260 && q.x < 700 && q.y < 760) { p = q; break; }
  }
  if (!p) throw new Error("ningún terreno visible para picar");
  await page.mouse.click(p.x, p.y);
  await visible(".mapa-tabla-ficha:not([hidden])");
  await page.locator(".mapa-tabla-ficha button", { hasText: "Ver a escala" }).click().catch(() => {});
  await page.locator('.mapa-tabla-ficha [data-ficha="cerrar"]').click();
  await page.locator(".mapa-tabla-ficha").waitFor({ state: "hidden" });
});
await paso("Mapa → Filtros → Más filtros del mapa", async () => {
  await page.click("button[aria-controls=tabla-filtros]");
  await page.locator("#tabla-filtros button, #tabla-filtros a", { hasText: "Más filtros del mapa" }).click();
  await visible("dialog[open]");
});
await paso("Mapa → Tabla", async () => { await page.locator(".tabla-modo button", { hasText: "Tabla" }).click(); await visible(".tabla-grid"); });
await paso("Cuenta → Cerrar sesión", async () => {
  await page.click(".cuenta > summary");
  await page.locator(".cuenta .menu-item", { hasText: "Cerrar sesión" }).click();
  await page.locator("button", { hasText: "Iniciar sesión" }).first().waitFor({ state: "visible" });
});

console.log(errores.length ? `Errores de JS: ${errores.join(" | ")}` : "Sin errores de JS.");
console.log(fallos.length ? `${fallos.length} con fallas: ${fallos.join("; ")}` : "Todo responde.");
await browser.close();
process.exitCode = fallos.length || errores.length ? 1 : 0;

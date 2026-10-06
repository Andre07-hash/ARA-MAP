/* Connected Excel in a real browser: connect, first import, refresh by another
 * employee, no change, double click, empty candidate, invalid rows, run in
 * progress seen from another browser and across a reload, revoked grant and
 * reconnection. LOCAL ONLY, against tests/e2e/excel_servidor.py (a disposable
 * Postgres schema and the local fake Microsoft; fictional data):
 *
 *   ARA_E2E_ESTADO=/ruta/estado.json ARA_E2E_PW=… ARA_CHROMIUM=/ruta/chrome \
 *     node tests/e2e/excel-conectado.mjs [capturas]
 *
 * Optional ARA_URL_LOCAL: a local SQLite server (python3 -m server.app) with
 * user "ana" and the same password, to check that the connector says it is
 * unavailable there.
 */

import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright-core';

const ESTADO = JSON.parse(readFileSync(process.env.ARA_E2E_ESTADO, 'utf8'));
const URL_BASE = ESTADO.url;
const FAKE = ESTADO.fake;
const CLAVE = process.env.ARA_E2E_PW;
const SHOTS = process.argv[2] ?? null;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(URL_BASE) || !/^http:\/\/127\.0\.0\.1:\d+$/.test(FAKE)) {
  throw new Error('Solo contra el servidor local desechable.');
}
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch(process.env.ARA_CHROMIUM
  ? { executablePath: process.env.ARA_CHROMIUM } : { channel: 'chrome' });
const resultados = [];
let fallos = 0;
async function caso(nombre, fn) {
  try { await fn(); resultados.push(`ok   ${nombre}`); }
  catch (error) { fallos += 1; resultados.push(`FAIL ${nombre}\n     ${error.message.split('\n').slice(0, 6).join('\n     ')}`); }
  finally { await control({ retraso: 0 }); }   // a failed case must not slow the next ones
}

async function contexto({ ancho = 1440, alto = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width: ancho, height: alto }, locale: 'es-MX' });
  const page = await context.newPage();
  const api = [];
  const errores = [];
  page.on('request', (r) => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/')) api.push(`${r.method()} ${u.pathname}`); });
  page.on('pageerror', (e) => errores.push(e.message));
  await page.route(/arcgisonline|openstreetmap|tile/, (r) => r.fulfill({ status: 204, body: '' }));
  return { context, page, api, errores };
}

const foto = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, `${nombre}.png`), fullPage: true }); };
const control = (orden) => fetch(`${FAKE}/_control`, { method: 'POST', body: JSON.stringify(orden) });
const filas = (...f) => control({ usuario: 'dueno', item: 'item-libro', filas: f });
const BASICO = [['A-001', 'Lote Alfa', 1000000], ['A-002', 'Lote Beta', 2000000], ['007', 'Lote Gamma', 3000000]];

async function entrar(page, usuario, base = URL_BASE) {
  await page.goto(`${base}/#/bases`);
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVE);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
  await page.goto(`${base}/#/bases`);
  await page.getByRole('heading', { name: 'Bases de terrenos' }).waitFor();
}

const tarjeta = (page) => page.locator('li.card-excel');
const estado = (page) => tarjeta(page).locator('.excel-estado');
const toastCon = (page, texto) => page.locator('.toast', { hasText: texto });

async function sinDesborde(page, nombre) {
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    await page.setViewportSize({ width: w, height: h });
    await foto(page, `${nombre}-${w}`);
    const ancho = await page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(ancho <= w, `${w}: la página mide ${ancho}px`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

let ana;

await caso('connect the owner account, pick the workbook, review and import', async () => {
  ana = await contexto();
  const { page, api, errores } = ana;
  await entrar(page, 'ana');
  await page.getByRole('button', { name: 'Conectar Excel' }).click();
  const dialogo = page.locator('dialog[open]');
  await dialogo.getByRole('button', { name: 'Conectar cuenta de Microsoft' }).click();
  // Microsoft (the fake) signs in and sends the browser back to the callback.
  await toastCon(page, 'Cuenta de Microsoft conectada').waitFor();
  assert.equal(new URL(page.url()).hash, '#/bases', 'the notice is dropped from the address bar');
  assert.ok(!page.url().includes('code='), 'no authorization code in the visible URL');
  await page.locator('dialog[open]').getByRole('button', { name: /dueno@example.com/ }).click();
  const d = page.locator('dialog[open]');
  await d.getByRole('button', { name: /Terrenos Ficticios.xlsx/ }).waitFor();
  assert.equal(await d.getByRole('button', { name: /nota.pdf/ }).count(), 0, 'only Excel files are offered');
  await d.getByRole('button', { name: /Documentos/ }).waitFor();
  await d.getByRole('button', { name: /Terrenos Ficticios.xlsx/ }).click();
  await d.getByLabel('Columna con el ID único de cada terreno').waitFor();
  assert.equal(await d.getByLabel('Columna con el ID único de cada terreno').inputValue(), 'ID');
  assert.equal(await d.getByLabel('Nombre de la base').inputValue(), 'Terrenos Ficticios');
  assert.equal(await d.getByLabel('Moneda de los precios').inputValue(), 'USD');
  await d.getByText('lee la última versión GUARDADA').waitFor();
  await foto(page, 'excel-revision');
  await d.getByRole('button', { name: 'Conectar e importar' }).click();
  await toastCon(page, '«Terrenos Ficticios» conectada: 3 terrenos').waitFor();
  await page.waitForFunction(() => location.hash === '#/mapa');
  await page.getByText('Terrenos Ficticios').first().waitFor();
  assert.equal(api.filter((l) => l === 'POST /api/excel/fuentes').length, 1);
  assert.deepEqual(errores, []);
});

await caso('the connected card states its source and offers only safe actions', async () => {
  const { page } = ana;
  await page.goto(`${URL_BASE}/#/bases`);
  await estado(page).getByText('Conectada a Excel').waitFor();
  await estado(page).getByText('Versión 1 · 3 filas activas').waitFor();
  const t = tarjeta(page);
  assert.equal(await t.getByRole('button', { name: 'Eliminar' }).count(), 0);
  assert.equal(await t.getByRole('button', { name: 'Agregar terrenos' }).count(), 0);
  assert.match(await t.getByRole('link', { name: 'Abrir en Excel' }).getAttribute('href'), /^https:\/\/onedrive\.live\.com\//);
  assert.equal(await t.getByRole('link', { name: 'Abrir en Excel' }).getAttribute('rel'), 'noopener noreferrer');
  await page.getByText('Los mapas guardados no cambian').waitFor();
  assert.ok(!(await page.content()).toLowerCase().includes('refresh_token'));
  await sinDesborde(page, 'excel-tarjeta');
});

await caso('another employee refreshes a saved edit: real counts, map reloads, no duplicate base', async () => {
  await filas(['A-001', 'Lote Alfa', 1500000], BASICO[1], BASICO[2], ['Z-9', 'Lote Nuevo', 500000]);
  const beto = await contexto();
  await entrar(beto.page, 'beto');
  await tarjeta(beto.page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  await toastCon(beto.page, 'Actualizada desde Excel: 1 agregado, 1 actualizado, 0 eliminados.').waitFor();
  await estado(beto.page).getByText('Versión 2 · 4 filas activas').waitFor();
  assert.equal(await beto.page.locator('li.card').count(), 1, 'still one base');
  // No change: last checked advances, no new version.
  await tarjeta(beto.page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  await toastCon(beto.page, 'no tiene cambios').waitFor();
  await estado(beto.page).getByText('Versión 2 · 4 filas activas').waitFor();
  // The open map of the refreshed base shows the new data.
  await beto.page.locator('li.card .card-main').click();
  await toastCon(beto.page, '4 terrenos').waitFor();
  assert.deepEqual(beto.errores, []);
  await beto.context.close();
});

await caso('a double click sends one refresh', async () => {
  const { page, api } = ana;
  await page.goto(`${URL_BASE}/#/bases`);
  await control({ retraso: 1.5 });
  const antes = api.filter((l) => l.endsWith('/actualizar')).length;
  const boton = tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' });
  await boton.dblclick();
  await tarjeta(page).getByText('Actualizando desde Excel…').waitFor();
  await toastCon(page, 'no tiene cambios').waitFor();
  await control({ retraso: 0 });
  assert.equal(api.filter((l) => l.endsWith('/actualizar')).length - antes, 1);
});

await caso('a run in progress is visible to others and survives a reload; old data stays', async () => {
  const { page } = ana;
  await filas(...BASICO);
  await control({ retraso: 6 });
  const beto = await contexto();
  await entrar(beto.page, 'beto');
  await page.goto(`${URL_BASE}/#/bases`);
  void tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  await page.waitForTimeout(800);
  await beto.page.reload();
  // Watched from now: the outcome toast lasts a few seconds.
  const avisoBeto = toastCon(beto.page, '0 agregados, 1 actualizado, 1 eliminado').waitFor({ timeout: 30000 });
  await estado(beto.page).getByText('Actualizando desde Excel…').waitFor();
  await estado(beto.page).getByText(/Iniciada por Ana/).waitFor();
  await estado(beto.page).getByText('Versión 2 · 4 filas activas').waitFor();
  await tarjeta(beto.page).getByRole('button', { name: 'Comprobar' }).waitFor();
  // Ana reloads mid-request: her page recovers the run from the server too.
  await page.reload();
  await estado(page).getByText('Actualizando desde Excel…').waitFor();
  await foto(page, 'excel-en-curso');
  // Both settle without anyone pressing anything (bounded polling).
  await estado(beto.page).getByText('Versión 3 · 3 filas activas').waitFor({ timeout: 20000 });
  await avisoBeto;
  await estado(page).getByText('Versión 3 · 3 filas activas').waitFor({ timeout: 20000 });
  await control({ retraso: 0 });
  await beto.context.close();
});

await caso('an empty workbook needs a confirmation bound to that candidate', async () => {
  const { page } = ana;
  await filas();
  await page.goto(`${URL_BASE}/#/bases`);
  await tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  let d = page.locator('dialog[open]');
  await d.getByText('El libro está vacío').waitFor();
  await d.getByText(/los 3 terrenos de la versión 3/).waitFor();
  await d.getByRole('button', { name: 'Cancelar' }).click();
  await estado(page).getByText('El libro está vacío: falta confirmar').waitFor();
  await estado(page).getByText('Versión 3 · 3 filas activas').waitFor();
  await tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  d = page.locator('dialog[open]');
  await d.getByRole('button', { name: 'Vaciar la base' }).click();
  await estado(page).getByText('Versión 4 · 0 filas activas').waitFor();
});

await caso('invalid rows apply nothing and list row problems', async () => {
  const { page } = ana;
  await filas(['A-001', 'Lote Alfa'], ['A-001', 'Lote Repetido']);
  await tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  const d = page.locator('dialog[open]');
  await d.getByText('No se aplicó la actualización').waitFor();
  await d.getByText(/Fila \d+:/).first().waitFor();
  await foto(page, 'excel-problemas');
  await d.getByRole('button', { name: 'Cerrar' }).click();
  await estado(page).getByText('La última actualización falló').waitFor();
  await estado(page).getByText('Versión 4 · 0 filas activas').waitFor();
});

await caso('a revoked grant keeps the data and is fixed by reconnecting the owner account', async () => {
  const { page, errores } = ana;
  await filas(...BASICO);
  await control({ usuario: 'dueno', revocado: true });
  await tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  await estado(page).getByText('Hay que volver a conectar la cuenta de Microsoft').waitFor();
  await estado(page).getByText(/dueno@example.com/).waitFor();
  assert.equal(await tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' }).count(), 0);
  await control({ usuario: 'dueno', revocado: false });
  await tarjeta(page).getByRole('button', { name: 'Volver a conectar la cuenta' }).click();
  await toastCon(page, 'Cuenta de Microsoft conectada').waitFor();
  await page.keyboard.press('Escape');   // the setup dialog opens; this source needs none
  await tarjeta(page).getByRole('button', { name: 'Actualizar desde Excel' }).click();
  await toastCon(page, 'Actualizada desde Excel: 3 agregados').waitFor();
  await estado(page).getByText('Versión 5 · 3 filas activas').waitFor();
  assert.deepEqual(errores, []);
});

await caso('signing in at Microsoft can be cancelled safely', async () => {
  const { page } = ana;
  await control({ navegador: null });
  await page.getByRole('button', { name: 'Conectar Excel' }).click();
  await page.locator('dialog[open]').getByRole('button', { name: 'Conectar otra cuenta de Microsoft' }).click();
  await toastCon(page, 'Se canceló la conexión con Microsoft').waitFor();
  await control({ navegador: 'dueno' });
  await ana.context.close();
});

await caso('anonymous visitors get nothing from the connector', async () => {
  const r = await fetch(`${URL_BASE}/api/excel/fuentes`);
  assert.equal(r.status, 401);
  const cb = await fetch(`${URL_BASE}/api/microsoft/callback?code=x&state=y`, { redirect: 'manual' });
  assert.equal(cb.status, 303);
  assert.equal(cb.headers.get('location'), '/#/bases?excel=error');
});

if (process.env.ARA_URL_LOCAL) {
  await caso('the local (SQLite) app says the connector is web-only', async () => {
    const { page, context } = await contexto();
    await entrar(page, 'ana', process.env.ARA_URL_LOCAL);
    await page.getByRole('button', { name: 'Conectar Excel' }).click();
    const d = page.locator('dialog[open]');
    await d.getByText('La conexión con Excel no está disponible aquí').waitFor();
    await d.getByText(/sólo está disponible en la versión web|no está configurada/).waitFor();
    assert.equal(await d.getByRole('button', { name: /Conectar cuenta de Microsoft/ }).count(), 0);
    await foto(page, 'excel-local-no-disponible');
    await context.close();
  });
}

await browser.close();
console.log(resultados.join('\n'));
console.log(`\n${resultados.length - fallos}/${resultados.length} correctos`);
process.exit(fallos ? 1 : 0);

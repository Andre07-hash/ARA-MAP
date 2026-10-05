/* INTEGRATED interface checks: the real local server, real sessions, real
 * persistence. Run it only against a disposable instance:
 *
 *   ARA_MAP_DB=/tmp/x/ara.db python3 -c "from server.app import serve; serve(8432, open_browser=False)"
 *   printf '%s\n' "$PW" | python3 scripts/cuentas.py --sqlite /tmp/x/ara.db --password-stdin crear ana "Ana Prueba"
 *   (same for beto, carla)
 *   ARA_URL=http://localhost:8432 ARA_PW_ANA=… ARA_PW_BETO=… ARA_PW_CARLA=… node tests/e2e/inventario-integrado.mjs [capturas]
 *
 * It creates fictional records (including 251 synthetic drafts) and never
 * deletes anything: point it at a throwaway database only.
 */

import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8432').replace(/\/$/, '');
const SHOTS = process.argv[2] ?? null;
const CLAVES = { ana: process.env.ARA_PW_ANA, beto: process.env.ARA_PW_BETO, carla: process.env.ARA_PW_CARLA };
const SENTINELA = `SENTINELA-INTEGRADO-${Date.now()}`;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
for (const [u, c] of Object.entries(CLAVES)) assert.ok(c, `falta ARA_PW_${u.toUpperCase()}`);
if (/vercel|ara-map\.|https:/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');

const browser = await chromium.launch({ channel: 'chrome' });
const resultados = [];
let fallos = 0;
async function caso(nombre, fn) {
  try { await fn(); resultados.push(`ok   ${nombre}`); }
  catch (error) { fallos += 1; resultados.push(`FAIL ${nombre}\n     ${error.message.split('\n').join('\n     ')}`); }
}

async function contexto({ ancho = 1440, alto = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width: ancho, height: alto }, locale: 'es-MX' });
  const page = await context.newPage();
  const api = [];
  const errores = [];
  page.on('request', (r) => { if (r.url().includes('/api/')) api.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  page.on('response', (r) => { if (r.url().includes('/api/')) api.push(`  -> ${r.status()}`); });
  page.on('pageerror', (e) => errores.push(e.message));
  await page.route(/arcgisonline/, (r) => r.fulfill({ status: 204, body: '' }));
  return { context, page, api, errores };
}

const foto = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); };
const html = (page) => page.evaluate(() => document.documentElement.outerHTML);

async function entrar(page, usuario) {
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVES[usuario]);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
}

/* Shared across cases. */
let idTerreno = null;

await caso('anonymous startup calls only config, session and the public catalog; empty state shows', async () => {
  const { context, page, api, errores } = await contexto();
  await page.goto(`${URL_BASE}/`);
  await page.getByText('Todavía no hay terrenos publicados').waitFor();
  const llamadas = api.filter((l) => !l.startsWith('  ->'));
  assert.deepEqual([...new Set(llamadas)].sort(),
    ['GET /api/config', 'GET /api/publico/terrenos', 'GET /api/session']);
  assert.ok(!api.includes('  -> 401'), 'no anonymous 401s, i.e. no private calls');
  for (const [w, h] of [[1440, 900], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width: w, height: h });
    await foto(page, `integrado-catalogo-vacio-${w}`);
    const ancho = await page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(ancho <= w, `${w}: page is ${ancho}px wide`);
  }
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('a private deep link offers sign-in; wrong password is generic; then the empty inventory', async () => {
  const { context, page, errores } = await contexto();
  await page.goto(`${URL_BASE}/#/inventario`);
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  await page.getByLabel('Usuario').fill('ana');
  await page.getByLabel('Contraseña').fill('no-es-la-clave');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.getByText('Usuario o contraseña incorrectos.').waitFor();
  await page.getByLabel('Contraseña').fill(CLAVES.ana);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(/#\/inventario$/);
  await page.locator('.session-user', { hasText: 'Ana Prueba' }).waitFor();
  await page.locator('.toolbar-estado', { hasText: /terreno/ }).waitFor();
  await foto(page, 'integrado-inventario-inicial-1440');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('Ana creates a draft directly: server 422 on currency, then saved with an id', async () => {
  const { context, page, api, errores } = await contexto();
  await page.goto(`${URL_BASE}/`);
  await entrar(page, 'ana');
  await page.getByRole('link', { name: 'Nuevo terreno' }).first().click();
  await page.getByLabel('Nombre').fill('Lote Integración <b>Norte</b>');
  await page.getByLabel('Estado').fill('Jalisco');
  await page.getByLabel('Municipio').fill('Zapopan');
  await page.getByLabel('Latitud (X)').fill('20.7236');
  await page.getByLabel('Longitud (Y)').fill('-103.3848');
  await page.getByLabel('Superficie (m²)').fill('12,500');
  await page.getByLabel('Asking $/m²').fill('122.50');
  await page.getByLabel('Contacto').fill(`Contacto ${SENTINELA}`);
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.locator('#ed-moneda-error', { hasText: /moneda/i }).waitFor();   // server rule, no record created
  await foto(page, 'integrado-editor-422-1440');
  await page.getByLabel('Moneda').selectOption('USD');
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.waitForURL(/#\/inventario\/[0-9a-f-]{36}$/);
  idTerreno = page.url().split('/').pop();
  await page.getByText(/Borrador creado · ID .* · versión 1/).waitFor();
  const detalle = page.locator('.detail');
  await detalle.getByText('Borrador · No publicado').waitFor();
  await detalle.getByText('USD 122.50/m²').waitFor();
  assert.ok((await detalle.innerHTML()).includes('&lt;b&gt;Norte&lt;/b&gt;'), 'HTML-like text stays literal');
  const posts = api.filter((l) => l === 'POST /api/inventario/terrenos').length;
  assert.equal(posts, 2, 'one rejected, one created');
  await foto(page, 'integrado-detalle-1440');
  await page.setViewportSize({ width: 390, height: 844 });
  await foto(page, 'integrado-detalle-390');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('three users, equal powers: Beto edits Ana\'s draft; Carla\'s stale save is a recoverable 409', async () => {
  assert.ok(idTerreno, 'needs the previous case');
  const beto = await contexto();
  const carla = await contexto({ ancho: 768, alto: 1024 });
  await beto.page.goto(`${URL_BASE}/`);
  await entrar(beto.page, 'beto');
  await carla.page.goto(`${URL_BASE}/`);
  await entrar(carla.page, 'carla');

  // Carla opens the editor at version 1 and starts typing.
  await carla.page.goto(`${URL_BASE}/#/inventario/${idTerreno}/editar`);
  await carla.page.getByLabel('Notas internas').fill(`Nota de Carla ${SENTINELA}`);
  await carla.page.getByLabel('Asking $/m²').fill('130');

  // Beto, no re-upload, edits the same record and saves version 2.
  await beto.page.goto(`${URL_BASE}/#/inventario/${idTerreno}/editar`);
  await beto.page.getByLabel('Asking $/m²').fill('125.75');
  await beto.page.getByLabel('Dirección').fill('Camino a Tesistán km 3');
  await beto.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await beto.page.getByText(/Borrador guardado · versión 2/).waitFor();

  // Carla saves from version 1: nothing is overwritten, her input stays.
  await carla.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await carla.page.getByText('Otra persona guardó este terreno mientras lo editabas').waitFor();
  await carla.page.getByText('guardada por Beto Prueba', { exact: false }).waitFor();
  assert.equal(await carla.page.getByLabel('Asking $/m²').inputValue(), '130');
  await foto(carla.page, 'integrado-conflicto-768');
  await carla.page.setViewportSize({ width: 1440, height: 900 });
  await foto(carla.page, 'integrado-conflicto-1440');
  await carla.page.getByRole('button', { name: 'Revisar cambios' }).click();
  assert.equal(await carla.page.getByLabel('Dirección').inputValue(), 'Camino a Tesistán km 3');   // Beto's, kept
  await carla.page.locator('.is-conflicto').first().waitFor();                                         // the price both changed
  await carla.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await carla.page.getByText(/Borrador guardado · versión 3/).waitFor();

  const { terreno } = await (await carla.page.request.get(`${URL_BASE}/api/inventario/terrenos/${idTerreno}`)).json();
  assert.equal(terreno.version, 3);
  assert.equal(terreno.draft.asking_m2, 130);
  assert.equal(terreno.draft.direccion, 'Camino a Tesistán km 3');
  assert.equal(terreno.updated_by.display_name, 'Carla Prueba');

  // History: who did what, from the session, in order.
  await carla.page.locator('.detail').getByRole('button', { name: 'Historial' }).click();
  const dialogo = carla.page.getByRole('dialog', { name: 'Historial' });
  for (const quien of ['Ana Prueba', 'Beto Prueba', 'Carla Prueba']) await dialogo.getByText(quien, { exact: false }).first().waitFor();
  await dialogo.getByText('Creó el borrador').waitFor();
  await foto(carla.page, 'integrado-historial-1440');
  assert.deepEqual([...beto.errores, ...carla.errores], []);
  await beto.context.close();
  await carla.context.close();
});

await caso('confirming the price is a deliberate stamp with actor and date', async () => {
  const { context, page, errores } = await contexto();
  await page.goto(`${URL_BASE}/`);
  await entrar(page, 'ana');
  await page.goto(`${URL_BASE}/#/inventario/${idTerreno}/editar`);
  await page.getByLabel('Confirmo hoy el precio').check();
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.getByText(/Borrador guardado · versión 4/).waitFor();
  await page.locator('.detail').getByText(/· Ana Prueba/).first().waitFor();
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('251 more drafts: every page assembles before the count, table and map agree', async () => {
  const { context, page, api, errores } = await contexto();
  await page.goto(`${URL_BASE}/`);
  await entrar(page, 'carla');
  const n = 251;
  for (let i = 0; i < n; i += 1) {
    const r = await page.request.post(`${URL_BASE}/api/inventario/terrenos`, {
      headers: { 'Idempotency-Key': `integrado-${SENTINELA}-${i}`, Origin: URL_BASE },
      data: { terreno: `Sintético ${i}`, estado: i % 2 ? 'Jalisco' : 'Guanajuato', municipio: i % 2 ? 'Zapopan' : 'León',
        lat: 20 + (i % 50) * 0.01, lon: -103 + (i % 40) * 0.01, superficie_m2: 1000 + i, asking_m2: 100 + i, moneda: 'MXN' },
    });
    assert.equal(r.status(), 200, await r.text());
  }
  api.length = 0;
  await page.goto(`${URL_BASE}/#/inventario`);
  await page.reload();
  const total = n + 1;
  await page.locator('.toolbar-estado', { hasText: `${total} terrenos` }).waitFor({ timeout: 60000 });
  const paginas = api.filter((l) => l === 'GET /api/inventario/terrenos').length;
  assert.equal(paginas, 2, `${paginas} pages for ${total} at limit 250`);
  await page.locator('.legend-count', { hasText: `${total} terrenos` }).waitFor();
  await foto(page, 'integrado-inventario-252-1440');
  await page.getByRole('button', { name: 'Tabla' }).click();
  assert.equal(await page.locator('.table tbody tr').count(), total);
  await foto(page, 'integrado-inventario-tabla-1440');
  // Server filter with a repeated-geography query, through the rail.
  await page.getByLabel('Guanajuato').check();
  await page.locator('.toolbar-estado', { hasText: '126 terrenos' }).waitFor();
  assert.equal(await page.locator('.table tbody tr').count(), 126);
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('phone: filters drawer and editor are usable at 390 and 768', async () => {
  const { context, page, errores } = await contexto({ ancho: 390, alto: 844 });
  await page.goto(`${URL_BASE}/`);
  await entrar(page, 'beto');
  await page.locator('.toolbar-estado', { hasText: /terrenos/ }).waitFor();
  await foto(page, 'integrado-inventario-390');
  await page.locator('.filtros-btn').click();
  const drawer = page.getByRole('dialog', { name: 'Filtros' });
  await drawer.getByLabel('Buscar').fill('Integración');
  await page.locator('.toolbar-estado', { hasText: '1 terreno' }).waitFor();
  await foto(page, 'integrado-filtros-390');
  await drawer.getByRole('button', { name: 'Ver resultados' }).click();
  await page.waitForFunction(() => document.activeElement?.id === 'filtros-btn');
  await page.goto(`${URL_BASE}/#/inventario/${idTerreno}/editar`);
  await page.getByLabel('Nombre').waitFor();
  await foto(page, 'integrado-editor-390');
  assert.ok(await page.getByRole('button', { name: 'Guardar borrador' }).isVisible());
  await page.setViewportSize({ width: 768, height: 1024 });
  await foto(page, 'integrado-editor-768');
  await page.setViewportSize({ width: 1440, height: 900 });
  await foto(page, 'integrado-editor-1440');
  for (const w of [390, 768]) {
    await page.setViewportSize({ width: w, height: 900 });
    const ancho = await page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(ancho <= w, `${w}: page is ${ancho}px wide`);
  }
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('signed in, legacy bases and saved maps stay reachable and editable', async () => {
  const { context, page, errores } = await contexto();
  await page.goto(`${URL_BASE}/`);
  await entrar(page, 'ana');
  const libro = readFileSync(new URL('../fixtures/base_terrenos_09_26.xlsx', import.meta.url));
  const previa = await (await page.request.post(`${URL_BASE}/api/importar/vista-previa`, {
    headers: { 'Content-Type': 'application/octet-stream', 'X-Archivo': 'base.xlsx', Origin: URL_BASE }, data: libro,
  })).json();
  const r = await page.request.post(`${URL_BASE}/api/importar/confirmar`, {
    headers: { Origin: URL_BASE }, data: { token: previa.token, nombre: 'Base legado integración' },
  });
  assert.equal(r.status(), 200, await r.text());
  await page.getByRole('link', { name: 'Bases' }).click();
  await page.waitForURL(/#\/bases$/);
  await page.getByText('Base legado integración').waitFor();
  assert.equal(await page.getByRole('button', { name: 'Importar archivo' }).count(), 1);   // not read-only
  await page.getByText('Base legado integración').click();
  await page.waitForURL(/#\/mapa$/);
  await page.locator('.toolbar-title h1', { hasText: 'Base legado integración' }).waitFor();
  await page.getByRole('link', { name: 'Mapa', exact: true }).waitFor();             // nav offers the open base
  await foto(page, 'integrado-base-legado-1440');
  await page.getByRole('link', { name: 'Mapas guardados' }).click();
  await page.getByRole('heading', { name: /Mapas/ }).first().waitFor();
  await page.getByRole('link', { name: 'Inventario' }).click();
  await page.locator('.toolbar-estado', { hasText: /terrenos/ }).waitFor();
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('a reload keeps the session; logout revokes it, clears private DOM, and Back shows nothing', async () => {
  const { context, page, errores } = await contexto();
  await page.goto(`${URL_BASE}/`);
  await entrar(page, 'ana');
  await page.goto(`${URL_BASE}/#/inventario/${idTerreno}`);
  await page.reload();
  await page.locator('.detail', { hasText: SENTINELA }).waitFor();
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await page.waitForURL(/#\/catalogo$/);
  await page.getByText('Todavía no hay terrenos publicados').waitFor();
  let contenido = await html(page);
  assert.ok(!contenido.includes(SENTINELA) && !contenido.includes('Integración'), 'private content after logout');
  const r = await page.request.get(`${URL_BASE}/api/inventario/terrenos/${idTerreno}`);
  assert.equal(r.status(), 401, 'the server session is revoked');
  await page.goBack();
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  contenido = await html(page);
  assert.ok(!contenido.includes(SENTINELA) && !contenido.includes('Integración'), 'Back resurrected private content');
  await foto(page, 'integrado-logout-back-1440');
  assert.deepEqual(errores, []);
  await context.close();
});

await browser.close();
console.log(resultados.join('\n'));
console.log(`\n${resultados.length - fallos} ok, ${fallos} failed (INTEGRATED against ${URL_BASE})`);
process.exit(fallos ? 1 : 0);

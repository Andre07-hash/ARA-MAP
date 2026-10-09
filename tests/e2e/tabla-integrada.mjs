/* INTEGRATED checks of the employee table (packet 2A): the real local server,
 * real sessions, real persistence, a real Chrome. Nothing is mocked; the two
 * "lost response" cases let the request reach the server and drop its answer.
 *
 *   python3 tests/e2e/tabla_servidor.py --puerto 8433        # terminal 1 (disposable)
 *   cd tests/e2e && npm ci
 *   ARA_URL=http://localhost:8433 node tabla-integrada.mjs [carpeta-de-capturas]
 *
 * It needs a FRESH server each run: it creates the bases, grants, columns and
 * terrains it uses, all fictional, and deletes nothing.
 */

import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8433').replace(/\/$/, '');
const SHOTS = process.argv[2] ?? null;
if (!/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');
// The fixture password of the test accounts, read from the project's own test support.
const CLAVE = /TEST_PASSWORD = "([^"]+)"/.exec(
  readFileSync(new URL('../support.py', import.meta.url), 'utf8'))[1];
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const resultados = [];
let fallos = 0;
async function caso(nombre, fn) {
  try { await fn(); resultados.push(`ok   ${nombre}`); }
  catch (error) { fallos += 1; resultados.push(`FAIL ${nombre}\n     ${String(error.stack ?? error).split('\n').slice(0, 6).join('\n     ')}`); }
}

async function abrir(usuario, { ruta = '' } = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-MX' });
  context.setDefaultTimeout(Number(process.env.E2E_TIMEOUT ?? 10000));
  const page = await context.newPage();
  const api = [];
  const errores = [];
  page.on('response', (r) => { if (r.url().includes('/api/')) api.push(`${r.request().method()} ${new URL(r.url()).pathname} ${r.status()}`); });
  page.on('pageerror', (e) => errores.push(e.message));
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  await page.goto(`${URL_BASE}/${ruta}`);
  if (usuario) await entrar(page, usuario);
  return { context, page, api, errores };
}

async function entrar(page, usuario) {
  const dialogo = page.getByRole('dialog', { name: 'Iniciar sesión' });
  if (!(await dialogo.isVisible().catch(() => false))) await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVE);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
}

const foto = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); };
const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const textoDe = async (page, id, col) => (await celda(page, id, col).innerText()).trim();
const pedir = (page, ruta, opciones) => page.evaluate(async ([r, o]) => {
  const respuesta = await fetch(r, o && { ...o, headers: { 'Content-Type': 'application/json', ...(o.headers ?? {}) } });
  return { status: respuesta.status, body: await respuesta.json() };
}, [ruta, opciones]);
const terreno = async (page, id) => (await pedir(page, `/api/inventario/terrenos/${id}`)).body.terreno;
const listo = (page) => page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
const guardado = (page, id, col) => page.locator(
  `tr[data-id="${id}"] td[data-col="${col}"]:not(.is-pendiente):not(.is-editando)`).waitFor();

/** Wait until what the page shows settles on the expected value. */
async function hasta(leer, esperado, mensaje) {
  let visto;
  for (let i = 0; i < 60; i += 1) {
    visto = await leer();
    if (JSON.stringify(visto) === JSON.stringify(esperado)) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  assert.deepEqual(visto, esperado, mensaje ?? 'the page did not settle on the expected value');
}
const propias = (page) => async () => (await page.locator('thead th[data-col]').allInnerTexts()).slice(14);

/** Edit one cell with the keyboard only: focus, Enter, type, Enter. */
async function escribir(page, id, col, valor, { tipo = 'texto' } = {}) {
  await celda(page, id, col).focus();
  await page.keyboard.press('Enter');
  const editor = celda(page, id, col).locator('.tabla-editor');
  await editor.waitFor();
  if (tipo === 'opcion') await editor.selectOption(valor);
  else await editor.fill(valor);
  await page.keyboard.press('Enter');
  await guardado(page, id, col);
}

async function irATabla(page, vista) {
  await page.goto(`${URL_BASE}/#/tabla${vista ? `/${vista}` : ''}`);
  await page.locator('.tabla-pantalla').waitFor();
  await listo(page);
}

async function agregar(page) {
  const antes = await page.locator('tr.tabla-fila').evaluateAll((filas) => filas.map((f) => f.dataset.id));
  await page.getByRole('button', { name: 'Agregar terreno' }).click();
  await page.waitForFunction((n) => document.querySelectorAll('tr.tabla-fila').length > n
    || document.querySelector('tr.is-nueva'), antes.length);
  const ids = await page.locator('tr.is-nueva').evaluateAll((filas) => filas.map((f) => f.dataset.id));
  return ids.find((id) => !antes.includes(id));
}

/* Shared across cases. */
const B = {};        // base ids by name
const COL = {};      // custom column ids by name
let lote = null;     // the terrain most cases work on
const NOMBRE = 'Lote Ñandú Compartido';

/* ---------------------------------------------------------------- cases */

await caso('administrator: role-aware navigation, master table columns, bases, grants and custom columns', async () => {
  const { context, page, errores } = await abrir('ada');
  const nav = await page.locator('nav .nav-item').allInnerTexts();
  assert.deepEqual(nav, ['Tabla maestra', 'Inventario', 'Bases', 'Mapas guardados', 'Catálogo público']);
  await irATabla(page);
  assert.match(page.url(), /#\/tabla\/maestra$/);
  const cabeceras = await page.locator('thead th[data-col]').allInnerTexts();
  assert.deepEqual(cabeceras, ['Tipo de terreno', 'Nombre de terreno', 'Estado', 'Municipio', 'Superficie', 'HA',
    'Afectaciones %', 'Asking price', 'Asking $/m2', 'Comentarios', 'X', 'Y', 'Archivos', 'KMZ', 'Base']);

  await page.getByRole('button', { name: 'Bases y accesos' }).click();
  const bases = page.getByRole('dialog', { name: 'Bases de trabajo y accesos' });
  for (const nombre of ['Base Norte', 'Base Sur']) {
    await bases.getByLabel('Nombre', { exact: true }).fill(nombre);
    await bases.getByRole('button', { name: 'Crear base' }).click();
    await bases.getByLabel(`Nombre de la base ${nombre}`).waitFor();
  }
  for (const [nombre, quienes] of [['Base Norte', ['Olga', 'Omar']], ['Base Sur', ['Omar']]]) {
    await bases.locator('li', { has: page.getByLabel(`Nombre de la base ${nombre}`) })
      .getByRole('button', { name: 'Accesos…' }).click();
    const accesos = page.getByRole('dialog', { name: `Accesos · ${nombre}` });
    for (const q of quienes) await accesos.getByLabel(new RegExp(`^${q} Ficticia`)).check();
    if (nombre === 'Base Norte') {
      // The lookup lists operators only, with identity and status and nothing else.
      const visibles = await accesos.locator('.accesos-lista label').allInnerTexts();
      assert.equal(visibles.length, 6);
      assert.ok(!visibles.some((v) => /Ada|Alan/.test(v)), 'administrators are not grantable');
      await foto(page, '01-accesos-de-una-base');
    }
    await accesos.getByRole('button', { name: 'Guardar accesos' }).click();
    await accesos.waitFor({ state: 'detached' });
  }
  await foto(page, '02-bases-de-trabajo');
  await bases.getByRole('button', { name: 'Cerrar' }).click();
  for (const b of (await pedir(page, '/api/maestra/bases')).body.bases) B[b.nombre] = b.id;

  await page.locator('#tabla-vista').selectOption(B['Base Norte']);
  await page.waitForURL(new RegExp(`#/tabla/${B['Base Norte']}$`));
  await listo(page);
  await page.getByRole('button', { name: 'Columnas' }).click();
  const columnas = page.getByRole('dialog', { name: 'Columnas de la base' });
  for (const [nombre, tipo, opciones] of [['Nota', 'texto'], ['Avance', 'numero'],
    ['Etapa', 'opcion', 'En curso\nCerrado'], ['Visita', 'fecha']]) {
    await columnas.getByLabel('Nombre', { exact: true }).fill(nombre);
    await columnas.locator('#columna-tipo').selectOption(tipo);
    if (opciones) await columnas.getByLabel('Opciones (una por línea)').fill(opciones);
    await columnas.getByRole('button', { name: 'Crear columna' }).click();
    await columnas.getByLabel(`Nombre de la columna ${nombre}`).waitFor();
  }
  // A core column's name and a duplicate are refused with a message, and nothing is created.
  await columnas.getByLabel('Nombre', { exact: true }).fill('Municipio');
  await columnas.locator('#columna-tipo').selectOption('texto');
  await columnas.getByRole('button', { name: 'Crear columna' }).click();
  await columnas.getByText('Ese nombre es de una columna básica.').waitFor();
  await columnas.getByLabel('Nombre', { exact: true }).fill('nota');
  await columnas.getByRole('button', { name: 'Crear columna' }).click();
  await columnas.getByText('Ya hay una columna con ese nombre en esta base.').waitFor();
  await foto(page, '03-columnas-de-la-base');
  await columnas.getByRole('button', { name: 'Cerrar' }).click();
  for (const c of (await pedir(page, `/api/maestra/bases/${B['Base Norte']}/columnas`)).body.columnas) COL[c.nombre] = c.id;
  assert.deepEqual(Object.keys(COL), ['Nota', 'Avance', 'Etapa', 'Visita']);
  await hasta(propias(page), ['Nota · texto', 'Avance · numero', 'Etapa · opcion', 'Visita · fecha']);
  assert.ok(!(await page.locator('thead th[data-col]').allInnerTexts()).includes('Base'), 'a selected base has no Base column');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('operator: only her bases; blank create; every core and custom type edited by keyboard; reload and a second session', async () => {
  const { context, page, api, errores } = await abrir('olga');
  await page.waitForURL(new RegExp(`#/tabla/${B['Base Norte']}$`));   // the operator's entry point
  await listo(page);
  assert.deepEqual(await page.locator('nav .nav-item').allInnerTexts(), ['Tabla', 'Catálogo público']);
  assert.deepEqual(await page.locator('#tabla-vista option').allInnerTexts(), ['Base Norte']);
  assert.equal(await page.getByRole('button', { name: 'Bases y accesos' }).count(), 0);
  assert.ok(!api.some((l) => / (401|403|500)$/.test(l)), `no refused or failed call: ${api.filter((l) => / (401|403|500)$/.test(l))}`);
  assert.ok(!api.some((l) => /\/api\/(bases|mapas|carpetas|inventario\/terrenos) /.test(l)), 'no legacy or master-table call');

  lote = await agregar(page);
  const creado = await terreno(page, lote);
  assert.equal(creado.version, 1);
  assert.equal(creado.base_id, B['Base Norte']);
  assert.ok(Object.entries(creado.draft).every(([k, v]) => v === null || k === 'price_on_request' || k === 'availability'),
    'a blank terrain has no business value');
  await foto(page, '04-terreno-en-blanco');

  const basicos = [['core:tipo_terreno', 'Industrial'], ['core:terreno', NOMBRE], ['core:estado', 'Jalisco'],
    ['core:municipio', 'Zapopan'], ['core:superficie_m2', '12,500'], ['core:superficie_ha', '1.3'],
    ['core:afectaciones_pct', '0.125'], ['core:asking_price', '1470000'], ['core:asking_m2', '99.5'],
    ['core:lat', '20.7'], ['core:lon', '-103.4']];
  for (const [col, valor] of basicos) await escribir(page, lote, col, valor);
  // Comentarios: Shift+Enter is a line break, Enter saves.
  await celda(page, lote, 'core:notas_internas').focus();
  await page.keyboard.press('Enter');
  await page.keyboard.type('Primera línea');
  await page.keyboard.press('Shift+Enter');
  await page.keyboard.type('segunda línea');
  await page.keyboard.press('Enter');
  await guardado(page, lote, 'core:notas_internas');
  await escribir(page, lote, COL.Nota, 'Junto al río');
  await escribir(page, lote, COL.Avance, '42.5');
  await escribir(page, lote, COL.Etapa, 'Cerrado', { tipo: 'opcion' });
  await escribir(page, lote, COL.Visita, '2026-03-15');
  await page.locator('.tabla-estado', { hasText: /Guardado/ }).waitFor();

  const t = await terreno(page, lote);
  assert.deepEqual({ ...t.draft, direccion: undefined, public_description: undefined, contacto: undefined,
    afectaciones_m2: undefined, price_on_request: undefined, availability: undefined }, {
    tipo_terreno: 'Industrial', terreno: NOMBRE, estado: 'Jalisco', municipio: 'Zapopan',
    superficie_m2: 12500, superficie_ha: 1.3, afectaciones_pct: 0.125, asking_price: 1470000, asking_m2: 99.5,
    notas_internas: 'Primera línea\nsegunda línea', lat: 20.7, lon: -103.4, moneda: null,
    direccion: undefined, public_description: undefined, contacto: undefined, afectaciones_m2: undefined,
    price_on_request: undefined, availability: undefined,
  });   // X is latitude, Y longitude; no currency assumed; 1.3 ha and 99.5 $/m2 stay as typed, not derived
  assert.deepEqual(t.custom, { [COL.Nota]: 'Junto al río', [COL.Avance]: 42.5, [COL.Etapa]: 'Cerrado', [COL.Visita]: '2026-03-15' });
  assert.equal(t.version, 17);   // one version per saved cell: 16 cells after the create
  // The file columns are honest placeholders: no count, no control.
  for (const col of ['core:archivos', 'core:kmz']) {
    assert.equal(await textoDe(page, lote, col), 'No disponible');
    assert.equal(await celda(page, lote, col).locator('button, input, a').count(), 0);
  }
  await foto(page, '05-todas-las-celdas-editadas');

  await page.reload();
  await listo(page);
  assert.equal(await textoDe(page, lote, 'core:terreno'), NOMBRE);
  assert.equal(await textoDe(page, lote, COL.Visita), '2026-03-15');
  assert.equal(await textoDe(page, lote, 'core:superficie_m2'), '12500');

  const otra = await abrir('omar');
  await irATabla(otra.page, B['Base Norte']);
  assert.equal(await textoDe(otra.page, lote, 'core:asking_price'), '1470000');
  assert.equal(await textoDe(otra.page, lote, COL.Etapa), 'Cerrado');
  assert.deepEqual(await otra.page.locator('#tabla-vista option').allInnerTexts(), ['Base Norte', 'Base Sur']);
  await otra.context.close();
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('keyboard only: Tab and arrows move, typing replaces, Escape cancels, Enter and Tab save, focus returns; a bad value is kept', async () => {
  const { context, page, errores } = await abrir('olga');
  await listo(page);
  const enfocada = () => page.evaluate(() => {
    const a = document.activeElement;
    const td = a?.closest?.('td[data-col]');
    return td ? `${td.dataset.col}${a === td ? '' : ':editor'}` : a?.tagName;
  });
  await celda(page, lote, 'core:estado').focus();
  await page.keyboard.press('Tab');
  assert.equal(await enfocada(), 'core:municipio');
  await page.keyboard.press('Shift+Tab');
  assert.equal(await enfocada(), 'core:estado');
  await page.keyboard.press('ArrowRight');
  assert.equal(await enfocada(), 'core:municipio');

  // Typing starts an edit that replaces the value; Escape puts everything back.
  await page.keyboard.type('Tala');
  assert.equal(await enfocada(), 'core:municipio:editor');
  await page.keyboard.press('Escape');
  assert.equal(await enfocada(), 'core:municipio');
  assert.equal(await textoDe(page, lote, 'core:municipio'), 'Zapopan');
  assert.equal((await terreno(page, lote)).draft.municipio, 'Zapopan');

  // Enter saves and the focus stays on the cell; Tab saves and moves on.
  await page.keyboard.press('Enter');
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type('Tala');
  await page.keyboard.press('Enter');
  await guardado(page, lote, 'core:municipio');
  assert.equal(await enfocada(), 'core:municipio');
  await page.keyboard.press('F2');
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type('Tequila');
  await page.keyboard.press('Tab');
  await guardado(page, lote, 'core:municipio');
  assert.equal(await enfocada(), 'core:superficie_m2');
  assert.equal((await terreno(page, lote)).draft.municipio, 'Tequila');

  // A value the column cannot take is not sent and not lost.
  const antes = (await terreno(page, lote)).version;
  await page.keyboard.type('doce mil');
  await page.keyboard.press('Enter');
  await page.locator('.tabla-bandeja', { hasText: 'Escribe un número.' }).waitFor();
  assert.equal(await celda(page, lote, 'core:superficie_m2').getAttribute('aria-invalid'), 'true');
  assert.match(await page.locator('.tabla-bandeja').innerText(), /Tu valor: «doce mil»/);
  assert.equal((await terreno(page, lote)).version, antes);
  await foto(page, '06-valor-invalido-conservado');
  await page.getByRole('button', { name: 'Corregir' }).click();
  assert.equal(await page.locator('.tabla-editor').inputValue(), 'doce mil');
  await page.locator('.tabla-editor').fill('12000');
  await page.keyboard.press('Enter');
  await guardado(page, lote, 'core:superficie_m2');
  await page.locator('.tabla-bandeja').waitFor({ state: 'hidden' });
  assert.equal((await terreno(page, lote)).draft.superficie_m2, 12000);
  // A server-side refusal (latitude out of range) is shown on the cell the same way.
  await escribir(page, lote, 'core:lat', '95').catch(() => {});
  await page.locator('.tabla-bandeja', { hasText: 'La latitud va de -90 a 90.' }).waitFor();
  await page.getByRole('button', { name: 'Descartar el mío' }).click();
  assert.equal(await textoDe(page, lote, 'core:lat'), '20.7');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('two users, one cell: the stale save is a conflict that keeps both values; reapply and discard are explicit', async () => {
  const a = await abrir('olga');
  const b = await abrir('omar');
  await listo(a.page);
  await irATabla(b.page, B['Base Norte']);
  await escribir(b.page, lote, 'core:estado', 'Sonora');
  const version = (await terreno(b.page, lote)).version;

  await celda(a.page, lote, 'core:estado').focus();
  await a.page.keyboard.press('Enter');
  await a.page.locator('.tabla-editor').fill('Colima');
  await a.page.keyboard.press('Enter');
  const bandeja = a.page.locator('.tabla-bandeja');
  await bandeja.getByText(/Otra persona guardó cambios/).waitFor();
  assert.match(await bandeja.innerText(), /Valor actual: «Sonora»/);
  assert.match(await bandeja.innerText(), /Tu valor: «Colima»/);
  assert.match(await textoDe(a.page, lote, 'core:estado'), /^Sonora/);       // the authorized current row
  assert.equal((await terreno(a.page, lote)).draft.estado, 'Sonora');       // nothing was overwritten
  assert.equal((await terreno(a.page, lote)).version, version);
  await foto(a.page, '07-conflicto-de-dos-usuarios');
  await bandeja.getByRole('button', { name: 'Guardar el mío' }).click();
  await guardado(a.page, lote, 'core:estado');
  await bandeja.waitFor({ state: 'hidden' });
  assert.deepEqual([(await terreno(a.page, lote)).draft.estado, (await terreno(a.page, lote)).version], ['Colima', version + 1]);

  // The other direction, on a custom cell, discarded instead.
  await escribir(a.page, lote, COL.Nota, 'Nota de Olga');
  await celda(b.page, lote, COL.Nota).focus();
  await b.page.keyboard.press('Enter');
  await b.page.locator('.tabla-editor').fill('Nota de Omar');
  await b.page.keyboard.press('Enter');
  await b.page.locator('.tabla-bandeja').getByText(/Otra persona guardó cambios/).waitFor();
  await b.page.getByRole('button', { name: 'Descartar el mío' }).click();
  assert.equal(await textoDe(b.page, lote, COL.Nota), 'Nota de Olga');
  assert.equal((await terreno(b.page, lote)).custom[COL.Nota], 'Nota de Olga');
  assert.deepEqual([...a.errores, ...b.errores], []);
  await a.context.close();
  await b.context.close();
});

await caso('a lost response is checked, not replayed; a lost blank create is retried with its own key and not duplicated', async () => {
  const { context, page, errores } = await abrir('olga');
  await listo(page);
  let parches = 0;
  await page.route(`**/api/inventario/terrenos/${lote}`, async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue();
    parches += 1;
    await route.fetch();          // the server saves it …
    return route.abort();         // … and the answer never arrives
  });
  const antes = (await terreno(page, lote)).version;
  await celda(page, lote, 'core:tipo_terreno').focus();
  await page.keyboard.press('Enter');
  await page.locator('.tabla-editor').fill('Agrícola');
  await page.keyboard.press('Enter');
  const bandeja = page.locator('.tabla-bandeja');
  await bandeja.getByText('No se confirmó si se guardó.').waitFor();
  await foto(page, '08-respuesta-perdida');
  await bandeja.getByRole('button', { name: 'Comprobar' }).click();
  await page.locator('.tabla-estado', { hasText: 'Sí se había guardado.' }).waitFor();
  await bandeja.waitFor({ state: 'hidden' });
  assert.equal(parches, 1, 'the mutation was sent once');
  assert.deepEqual([(await terreno(page, lote)).draft.tipo_terreno, (await terreno(page, lote)).version], ['Agrícola', antes + 1]);
  await page.unroute(`**/api/inventario/terrenos/${lote}`);

  const ruta = `**/api/maestra/bases/${B['Base Norte']}/terrenos`;
  const claves = [];
  let perder = true;
  await page.route(ruta, async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    claves.push(route.request().headers()['idempotency-key']);
    if (!perder) return route.continue();
    perder = false;
    await route.fetch();
    return route.abort();
  });
  const total = async () => (await pedir(page, `/api/maestra/bases/${B['Base Norte']}/terrenos?limit=1`)).body.total;
  const habia = await total();
  await page.getByRole('button', { name: 'Agregar terreno' }).click();
  await bandeja.getByText(/No se confirmó si el terreno en blanco se creó/).waitFor();
  assert.equal(await total(), habia + 1);                    // it was created
  await bandeja.getByRole('button', { name: 'Reintentar' }).click();
  await page.locator('tr.is-nueva').waitFor();
  assert.equal(claves.length, 2);
  assert.equal(claves[0], claves[1], 'the retry carries the original Idempotency-Key');
  assert.equal(await total(), habia + 1, 'and creates nothing more');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('archive and restore a terrain; an archived row is read-only', async () => {
  const { context, page, errores } = await abrir('olga');
  await listo(page);
  const fila = page.locator(`tr[data-id="${lote}"]`);
  await fila.getByRole('button', { name: /^Abrir terreno/ }).click();
  const detalle = page.getByRole('dialog', { name: NOMBRE });
  await detalle.getByText('No disponible').first().waitFor();      // the detail mount of the file slots
  assert.equal(await detalle.getByRole('button', { name: /Transferir/ }).count(), 0, 'operators do not transfer');
  await foto(page, '09-detalle-del-terreno');
  await detalle.getByRole('button', { name: 'Archivar terreno' }).click();
  await page.getByRole('dialog', { name: '¿Archivar este terreno?' }).getByRole('button', { name: 'Archivar' }).click();
  await fila.waitFor({ state: 'detached' });
  assert.ok((await terreno(page, lote)).archived_at);

  await page.getByLabel('Incluir archivados').check();
  await listo(page);
  await fila.locator('.tabla-chip', { hasText: 'Archivado' }).waitFor();
  await celda(page, lote, 'core:estado').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.tabla-editor').count(), 0, 'an archived terrain does not open an editor');
  await foto(page, '10-terreno-archivado');
  await fila.getByRole('button', { name: /^Abrir terreno/ }).click();
  await page.getByRole('dialog', { name: NOMBRE }).getByRole('button', { name: 'Restaurar terreno' }).click();
  await page.locator(`tr[data-id="${lote}"]:not(.is-archivada)`).waitFor();
  assert.equal((await terreno(page, lote)).archived_at, null);
  await escribir(page, lote, 'core:estado', 'Jalisco');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('transfer: real preview, explicit confirmation, the row leaves; the source operator loses it without a leak', async () => {
  const olga = await abrir('olga');
  await listo(olga.page);
  const { context, page, errores } = await abrir('ada');
  await irATabla(page, B['Base Norte']);
  await page.locator(`tr[data-id="${lote}"]`).getByRole('button', { name: /^Abrir terreno/ }).click();
  await page.getByRole('dialog', { name: NOMBRE }).getByRole('button', { name: 'Transferir a otra base…' }).click();
  const dialogo = page.getByRole('dialog', { name: 'Transferir terreno' });
  const mover = dialogo.getByRole('button', { name: 'Transferir', exact: true });
  await dialogo.getByLabel('Base de destino').selectOption(B['Base Norte']);
  await dialogo.getByText('El terreno ya está ahí').waitFor();
  assert.ok(await mover.isDisabled());
  await dialogo.getByLabel('Base de destino').selectOption(B['Base Sur']);
  await dialogo.getByRole('heading', { name: 'Quién podrá abrirlo' }).waitFor();
  const resumen = await dialogo.locator('.transferir-resumen').innerText();
  assert.match(resumen, /Omar Ficticia \(omar\)/);
  assert.ok(!/Olga/.test(resumen), 'only the destination grants are listed');
  assert.match(resumen, /Nota · este terreno tiene un valor, que se conserva sin mostrarse/);
  assert.match(resumen, /Avance[\s\S]*Etapa[\s\S]*Visita/);
  assert.ok(await mover.isDisabled(), 'nothing moves before the explicit confirmation');
  await foto(page, '11-vista-previa-de-transferencia');
  await dialogo.getByLabel(/Revisé quién podrá abrirlo/).check();
  await mover.click();
  await page.locator(`tr[data-id="${lote}"]`).waitFor({ state: 'detached' });
  const movido = await terreno(page, lote);
  assert.equal(movido.base_id, B['Base Sur']);
  assert.deepEqual(movido.custom, {});

  // Olga still has the row on screen. Her next save is refused as out of scope.
  await celda(olga.page, lote, 'core:estado').focus();
  await olga.page.keyboard.press('Enter');
  await olga.page.locator('.tabla-editor').fill('Nayarit');
  await olga.page.keyboard.press('Enter');
  await olga.page.locator(`tr[data-id="${lote}"]`).waitFor({ state: 'detached' });
  await olga.page.getByText(/Un terreno ya no está en esta vista/).waitFor();
  assert.ok(!(await olga.page.locator('body').innerText()).includes(NOMBRE), 'nothing of the lost row remains');
  assert.equal(movido.draft.estado, 'Jalisco');
  await foto(olga.page, '12-terreno-fuera-de-alcance');

  // In the master table the row stays and shows its new base; then back to Base Norte.
  await page.locator('#tabla-vista').selectOption('maestra');
  await listo(page);
  assert.equal(await textoDe(page, lote, 'base'), 'Base Sur');
  await page.locator(`tr[data-id="${lote}"]`).getByRole('button', { name: /^Abrir terreno/ }).click();
  await page.getByRole('dialog', { name: NOMBRE }).getByRole('button', { name: 'Transferir a otra base…' }).click();
  await dialogo.getByLabel('Base de destino').selectOption(B['Base Norte']);
  await dialogo.getByRole('heading', { name: 'Quién podrá abrirlo' }).waitFor();
  await dialogo.getByLabel(/Revisé quién podrá abrirlo/).check();
  await mover.click();
  await page.locator(`tr[data-id="${lote}"] td[data-col="base"]`, { hasText: 'Base Norte' }).waitFor();
  assert.equal((await terreno(page, lote)).custom[COL.Nota], 'Nota de Olga', 'its values are back with it');
  assert.deepEqual([...errores, ...olga.errores], []);
  await olga.context.close();
  await context.close();
});

await caso('custom columns: rename, reorder, retire and restore keep ids, values and history', async () => {
  const { context, page, errores } = await abrir('ada');
  await irATabla(page, B['Base Norte']);
  await page.getByRole('button', { name: 'Columnas' }).click();
  const columnas = page.getByRole('dialog', { name: 'Columnas de la base' });
  const item = (nombre) => columnas.locator('li', { has: page.getByLabel(`Nombre de la columna ${nombre}`) });
  await columnas.getByLabel('Nombre de la columna Nota').fill('Observación');
  await item('Nota').getByRole('button', { name: 'Guardar' }).click();
  await columnas.getByLabel('Nombre de la columna Observación').waitFor();
  await columnas.getByLabel('Agregar opción a Etapa').fill('En pausa');
  await item('Etapa').getByRole('button', { name: 'Guardar' }).click();
  await columnas.getByText('Opción: En curso, Cerrado, En pausa').waitFor();
  await item('Visita').getByRole('button', { name: 'Subir' }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('.columnas-item input[aria-label^="Nombre de la columna"]')]
    .map((i) => i.value).join() === 'Observación,Avance,Visita,Etapa');
  await item('Avance').getByRole('button', { name: 'Retirar' }).click();
  await page.getByRole('dialog', { name: /¿Retirar la columna «Avance»\?/ }).getByRole('button', { name: 'Retirar' }).click();
  await item('Avance').getByRole('button', { name: 'Restaurar' }).waitFor();
  await foto(page, '13-columna-retirada');
  await columnas.getByRole('button', { name: 'Cerrar' }).click();
  await hasta(propias(page), ['Observación · texto', 'Visita · fecha', 'Etapa · opcion']);
  assert.equal(await textoDe(page, lote, COL.Nota), 'Nota de Olga');           // same id under the new label
  const oculto = await terreno(page, lote);
  assert.ok(!(COL.Avance in oculto.custom), 'a retired column shows no value');

  await page.locator(`tr[data-id="${lote}"]`).getByRole('button', { name: /^Abrir terreno/ }).click();
  await page.getByRole('dialog', { name: NOMBRE }).getByRole('button', { name: 'Historial' }).click();
  const historial = page.getByRole('dialog', { name: 'Historial' });
  await historial.locator('.historial-evento').first().waitFor();
  await foto(page, '14-historial');
  await historial.getByRole('button', { name: 'Cerrar' }).click();
  await page.getByRole('dialog', { name: NOMBRE }).getByRole('button', { name: 'Cerrar' }).click();

  await page.getByRole('button', { name: 'Columnas' }).click();
  await item('Avance').getByRole('button', { name: 'Restaurar' }).click();
  await item('Avance').getByRole('button', { name: 'Retirar' }).waitFor();
  await columnas.getByRole('button', { name: 'Cerrar' }).click();
  // Restored where it was: retiring does not renumber the columns.
  await hasta(propias(page), ['Observación · texto', 'Avance · numero', 'Visita · fecha', 'Etapa · opcion']);
  assert.equal(await textoDe(page, lote, COL.Avance), '42.5');                  // the value was kept
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('grants: a concurrent change is shown, not overwritten; losing the grant clears the screen without a leak', async () => {
  const olga = await abrir('olga');
  await listo(olga.page);
  // She has unsaved input on screen when her access goes away.
  await celda(olga.page, lote, 'core:asking_price').focus();
  await olga.page.keyboard.type('carísimo-SECRETO-NO-GUARDADO');
  await olga.page.keyboard.press('Enter');
  await olga.page.locator('.tabla-bandeja', { hasText: 'Escribe un número.' }).waitFor();

  const ada = await abrir('ada');
  const alan = await abrir('alan');
  await irATabla(ada.page);
  await ada.page.getByRole('button', { name: 'Bases y accesos' }).click();
  const bases = ada.page.getByRole('dialog', { name: 'Bases de trabajo y accesos' });
  await bases.locator('li', { has: ada.page.getByLabel('Nombre de la base Base Norte') })
    .getByRole('button', { name: 'Accesos…' }).click();
  const accesos = ada.page.getByRole('dialog', { name: 'Accesos · Base Norte' });
  await accesos.getByLabel(/^Otto Ficticia/).check();          // Ada intends: olga, omar, otto

  // Meanwhile Alan removes Olga (through the same API the dialog uses).
  const actual = (await pedir(alan.page, `/api/maestra/bases/${B['Base Norte']}/acceso`)).body;
  const sinOlga = actual.usuarios.filter((u) => u.login !== 'olga').map((u) => u.id);
  const cambio = await pedir(alan.page, `/api/maestra/bases/${B['Base Norte']}/acceso`,
    { method: 'PUT', body: JSON.stringify({ expected_version: actual.base.version, usuarios: sinOlga }) });
  assert.equal(cambio.status, 200);

  await accesos.getByRole('button', { name: 'Guardar accesos' }).click();
  await accesos.getByText(/Otra persona cambió esta base mientras editabas/).waitFor();
  await hasta(async () => [await accesos.getByLabel(/^Olga Ficticia/).isChecked(),
    await accesos.getByLabel(/^Omar Ficticia/).isChecked(), await accesos.getByLabel(/^Otto Ficticia/).isChecked()],
  [false, true, false], "Alan's change is what is shown; Ada's unsaved choice was not applied");
  const tras = (await pedir(alan.page, `/api/maestra/bases/${B['Base Norte']}/acceso`)).body;
  assert.deepEqual(tras.usuarios.map((u) => u.login), ['omar']);
  await foto(ada.page, '15-conflicto-de-accesos');
  await accesos.getByRole('button', { name: 'Cancelar' }).click();

  // Olga looks again: the base is gone for her, and so is everything it showed.
  await olga.page.getByRole('button', { name: 'Actualizar' }).click();
  await olga.page.getByRole('dialog', { name: '¿Descartar cambios sin guardar?' }).getByRole('button', { name: 'Descartar' }).click();
  await olga.page.getByRole('heading', { name: 'Todavía no tienes una base de trabajo' }).waitFor();
  const visible = await olga.page.locator('body').innerText();
  const html = await olga.page.content();
  for (const secreto of [NOMBRE, 'SECRETO-NO-GUARDADO', 'Nota de Olga', 'Observación', 'Base Norte', 'Tequila']) {
    assert.ok(!visible.includes(secreto) && !html.includes(secreto), `"${secreto}" is gone from the page`);
  }
  assert.equal(await olga.page.locator('tr.tabla-fila').count(), 0);
  await foto(olga.page, '16-acceso-perdido');

  // Granted again through the dialog; "Volver a comprobar" brings the base back.
  await bases.locator('li', { has: ada.page.getByLabel('Nombre de la base Base Norte') })
    .getByRole('button', { name: 'Accesos…' }).click();
  await accesos.getByLabel(/^Olga Ficticia/).check();
  await accesos.getByRole('button', { name: 'Guardar accesos' }).click();
  await accesos.waitFor({ state: 'detached' });
  await olga.page.getByRole('button', { name: 'Volver a comprobar' }).click();
  await olga.page.locator(`tr[data-id="${lote}"]`).waitFor();
  assert.deepEqual([...olga.errores, ...ada.errores, ...alan.errores], []);
  for (const s of [olga, ada, alan]) await s.context.close();
});

await caso('no grant: a useful empty state; administrators\' screens are not reachable by address', async () => {
  const { context, page, api, errores } = await abrir('otto');
  await page.waitForURL(/#\/tabla$/);
  await page.getByRole('heading', { name: 'Todavía no tienes una base de trabajo' }).waitFor();
  await page.getByText(/Un administrador tiene que darte acceso/).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Agregar terreno' }).isVisible(), false);
  await foto(page, '17-operador-sin-base');
  for (const ruta of ['#/bases', '#/mapas', '#/inventario', '#/inventario/nuevo', '#/tabla/maestra',
    `#/tabla/${B['Base Norte']}`]) {
    await page.goto(`${URL_BASE}/${ruta}`);
    await page.getByRole('heading', { name: 'Todavía no tienes una base de trabajo' }).waitFor();
    assert.match(page.url(), /#\/tabla$/, ruta);
  }
  assert.equal(await page.locator('tr.tabla-fila').count(), 0);
  assert.ok(!api.some((l) => / (403|500)$/.test(l)), `nothing was even asked for: ${api.filter((l) => / (403|500)$/.test(l))}`);
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('session loss: logout clears the table; the next account on the same page sees nothing of the previous one', async () => {
  const { context, page, errores } = await abrir('olga');
  await listo(page);
  await page.locator(`tr[data-id="${lote}"]`).waitFor();
  // A slow list is in flight when she signs out: its answer must not be painted afterwards.
  await page.route('**/api/maestra/bases/*/terrenos?*', async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue().catch(() => {});
  });
  await page.locator('#tabla-buscar').fill('Lote');
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await page.getByRole('button', { name: 'Iniciar sesión' }).waitFor();
  await page.waitForTimeout(2000);
  assert.equal(await page.locator('.tabla-pantalla').count(), 0);
  assert.ok(!(await page.content()).includes(NOMBRE), 'no private row after logout');
  await page.unroute('**/api/maestra/bases/*/terrenos?*');
  await entrar(page, 'otto');
  await page.getByRole('heading', { name: 'Todavía no tienes una base de trabajo' }).waitFor();
  assert.ok(!(await page.content()).includes(NOMBRE));
  assert.deepEqual(await page.locator('#tabla-vista option').allInnerTexts(), []);

  // A session revoked on the server (signed out elsewhere) while a cell is being saved.
  const otra = await abrir('omar');
  await irATabla(otra.page, B['Base Norte']);
  await pedir(otra.page, '/api/logout', { method: 'POST' });
  await celda(otra.page, lote, 'core:municipio').focus();
  await otra.page.keyboard.press('Enter');
  await otra.page.locator('.tabla-editor').fill('Sin sesión');
  await otra.page.keyboard.press('Enter');
  await otra.page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  await otra.page.getByText(/Tu sesión terminó/).first().waitFor();
  // Correction 1: nothing private waits behind the sign-in dialog, saved or not.
  assert.equal(await otra.page.locator('.tabla-pantalla, tr[data-id]').count(), 0);
  assert.ok(!(await otra.page.content()).includes('Sin sesión') && !(await otra.page.content()).includes(NOMBRE));
  await foto(otra.page, '18-sesion-terminada');
  await otra.page.getByRole('dialog', { name: 'Iniciar sesión' }).getByRole('button', { name: 'Cancelar' }).click();
  assert.equal(await otra.page.locator('.tabla-pantalla').count(), 0);
  assert.deepEqual([...errores, ...otra.errores], []);
  await otra.context.close();
  await context.close();
});

await caso('an archived base is read-only for administrators and closed to operators', async () => {
  const { context, page, errores } = await abrir('ada');
  await irATabla(page, B['Base Sur']);
  const enSur = await agregar(page);
  await escribir(page, enSur, 'core:terreno', 'Lote del Sur');
  await page.getByRole('button', { name: 'Bases y accesos' }).click();
  const bases = page.getByRole('dialog', { name: 'Bases de trabajo y accesos' });
  await bases.locator('li', { has: page.getByLabel('Nombre de la base Base Sur') }).getByRole('button', { name: 'Archivar' }).click();
  await page.getByRole('dialog', { name: /¿Archivar la base «Base Sur»\?/ }).getByRole('button', { name: 'Archivar' }).click();
  await bases.getByText(/archivada \(sólo lectura\)/).waitFor();
  await bases.getByRole('button', { name: 'Cerrar' }).click();
  await page.getByText(/Esta base de trabajo está archivada/).waitFor();
  await listo(page);
  assert.equal(await page.getByRole('button', { name: 'Agregar terreno' }).isVisible(), false);
  await celda(page, enSur, 'core:terreno').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.tabla-editor').count(), 0);
  assert.equal(await celda(page, enSur, 'core:terreno').getAttribute('aria-readonly'), 'true');
  await foto(page, '19-base-archivada');
  const omar = await abrir('omar');
  await omar.page.waitForURL(/#\/tabla\//);
  await listo(omar.page);
  assert.deepEqual(await omar.page.locator('#tabla-vista option').allInnerTexts(), ['Base Norte']);
  await omar.context.close();
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('public and legacy administrator journeys still work', async () => {
  const anon = await abrir(null);
  await anon.page.getByText('Todavía no hay terrenos publicados').waitFor();
  assert.deepEqual([...new Set(anon.api.map((l) => l.replace(/ \d+$/, '')))].sort(),
    ['GET /api/config', 'GET /api/publico/terrenos', 'GET /api/session']);
  assert.ok(!(await anon.page.content()).includes(NOMBRE));
  await anon.context.close();

  const { context, page, api, errores } = await abrir('ada');
  await page.waitForURL(/#\/inventario$/);                 // the administrators' entry point is unchanged
  await page.locator('.toolbar-estado', { hasText: /terreno/ }).waitFor();
  assert.ok(api.some((l) => l === 'GET /api/inventario/terrenos 200'), 'the legacy inventory list loads');
  assert.ok(!api.some((l) => / (4\d\d|500)$/.test(l) ), `no failing call: ${api.filter((l) => / (4\d\d|500)$/.test(l))}`);
  await page.getByRole('link', { name: 'Bases', exact: true }).click();
  await page.waitForURL(/#\/bases$/);
  await page.locator('.screen').first().waitFor();
  await page.getByRole('link', { name: 'Mapas guardados' }).click();
  await page.waitForURL(/#\/mapas$/);
  await page.getByRole('link', { name: 'Catálogo público' }).click();
  await page.getByText('Todavía no hay terrenos publicados').waitFor();
  await foto(page, '20-administrador-catalogo');
  assert.ok(!api.some((l) => / (4\d\d|500)$/.test(l)));
  assert.deepEqual(errores, []);
  await context.close();
});

await browser.close();
console.log(resultados.join('\n'));
console.log(fallos ? `\n${fallos} con fallas.` : `\nTodo en orden: ${resultados.length} recorridos.`);
process.exit(fallos ? 1 : 0);

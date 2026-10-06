/* Stage 2 INTEGRATED interface checks: preview, publish, the real public
 * catalog, pending changes, a stale publish, sold, withdraw/archive/restore,
 * the Historial focus fix, the status column and phone toasts.
 *
 * Real local server, real sessions, a disposable database only:
 *
 *   ARA_MAP_DB=/tmp/x/ara.db python3 -c "from server.app import serve; serve(8432, open_browser=False)"
 *   printf '%s\n' "$PW" | python3 scripts/cuentas.py --sqlite /tmp/x/ara.db --password-stdin crear ana "Ana Prueba"
 *   (same for beto)
 *   ARA_URL=http://localhost:8432 ARA_PW_ANA=… ARA_PW_BETO=… node tests/e2e/publicacion-integrado.mjs [capturas]
 *
 * It creates and publishes fictional records and never deletes anything.
 */

import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8432').replace(/\/$/, '');
const SHOTS = process.argv[2] ?? null;
const CLAVES = { ana: process.env.ARA_PW_ANA, beto: process.env.ARA_PW_BETO };
const SELLO = Date.now().toString(36);
const SENTINELA = `SENTINELA-PUB-${SELLO}`;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
for (const [u, c] of Object.entries(CLAVES)) assert.ok(c, `falta ARA_PW_${u.toUpperCase()}`);
if (/vercel|ara-map\.|https:/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');

const browser = await chromium.launch(process.env.ARA_CHROMIUM ? { executablePath: process.env.ARA_CHROMIUM } : { channel: 'chrome' });
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

/* JSON through the signed-in page itself (same origin, its own cookie). */
const llamar = (page, method, path, body, headers = {}) => page.evaluate(async ({ method, path, body, headers }) => {
  const r = await fetch(`/api${path}`, {
    method, headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: r.status, body: await r.json() };
}, { method, path, body, headers });

const crear = async (page, campos) => {
  const r = await llamar(page, 'POST', '/inventario/terrenos', campos, { 'Idempotency-Key': `e2e-${SELLO}-${Math.random()}` });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  return r.body.terreno;
};

const publico = (id) => fetch(`${URL_BASE}/api/publico/terrenos/${id}`).then(async (r) => ({ status: r.status, body: await r.json() }));

const COMPLETO = {
  terreno: `Lote Público ${SELLO}`, estado: 'Jalisco', municipio: 'Zapopan', direccion: 'Camino real 1',
  superficie_m2: 12000, superficie_ha: 1.2, lat: 20.7236, lon: -103.3848,
  asking_price: 1470000, asking_m2: 122.5, moneda: 'USD', availability: 'available',
  public_description: 'Terreno plano con acceso pavimentado.',
  contacto: `Contacto ${SENTINELA}`, notas_internas: `Nota ${SENTINELA}`,
};

let ana = null;           // Ana's signed-in desktop page, kept across cases
let lote = null;          // the main published record

async function abrirDetalle(page, id) {
  await page.goto(`${URL_BASE}/#/inventario/${id}`);
  await page.locator('aside.detail .estado-row').waitFor();
}

async function publicarDesdeDetalle(page) {
  await page.locator('#vista-previa-btn').click();
  const dialogo = page.getByRole('dialog', { name: 'Vista previa · Aún no publicada' });
  await dialogo.waitFor();
  await dialogo.getByRole('button', { name: 'Publicar' }).click();
  await dialogo.waitFor({ state: 'detached' });
}

await caso('preview shows only public facts of the saved draft; Publicar puts it in the real catalog', async () => {
  ana = await contexto();
  await ana.page.goto(`${URL_BASE}/`);
  await entrar(ana.page, 'ana');
  lote = await crear(ana.page, COMPLETO);
  await abrirDetalle(ana.page, lote.id);
  await ana.page.locator('.detail').getByText('Borrador · No publicado').waitFor();

  await ana.page.locator('#vista-previa-btn').click();
  const dialogo = ana.page.getByRole('dialog', { name: 'Vista previa · Aún no publicada' });
  await dialogo.waitFor();
  await dialogo.getByText(`Revisión ${lote.draft_revision_id.slice(0, 8)} · versión 1`).waitFor();
  await dialogo.getByText('USD 122.50/m²').waitFor();
  await dialogo.getByText('Terreno plano con acceso pavimentado.').waitFor();
  const texto = await dialogo.innerText();
  assert.ok(!texto.includes(SENTINELA), 'no private contact/notes in the preview');
  await foto(ana.page, 'pub-vista-previa-1440');
  await dialogo.getByRole('button', { name: 'Publicar' }).click();
  await dialogo.waitFor({ state: 'detached' });
  await ana.page.getByText(`Publicado · revisión ${lote.draft_revision_id.slice(0, 8)}.`).waitFor();
  await ana.page.locator('aside.detail .estado-chip', { hasText: /^Publicado$/ }).waitFor();

  const r = await publico(lote.id);
  assert.equal(r.status, 200);
  assert.equal(r.body.terreno.revision_id, lote.draft_revision_id);
  assert.ok(!JSON.stringify(r.body).includes(SENTINELA));
  assert.deepEqual(ana.errores, []);
});

await caso('anonymous catalog shows real published records: map/table/count, detail, "Precio a consultar", "En negociación"', async () => {
  await crear(ana.page, { ...COMPLETO, terreno: `Lote Consulta ${SELLO}`, asking_price: null, asking_m2: null,
    moneda: null, price_on_request: true, availability: 'negotiation', lat: 20.8, lon: -103.2 })
    .then(async (t) => {
      const r = await llamar(ana.page, 'POST', `/inventario/terrenos/${t.id}/publicar`,
        { expected_version: t.version, revision_id: t.draft_revision_id });
      assert.equal(r.status, 200);
    });
  const total = (await fetch(`${URL_BASE}/api/publico/terrenos?limit=250`).then((x) => x.json())).total;
  const visitante = await contexto();
  await visitante.page.goto(`${URL_BASE}/#/catalogo`);
  await visitante.page.locator('.toolbar-estado', { hasText: `${total} terreno` }).waitFor();
  await visitante.page.getByRole('button', { name: 'Tabla' }).click();
  assert.equal(await visitante.page.locator('.table tbody tr').count(), total);
  assert.equal(await visitante.page.locator('th', { hasText: 'Publicación' }).count(), 0, 'no status column publicly');
  await visitante.page.locator('.table tbody tr', { hasText: `Lote Consulta ${SELLO}` }).click();
  const detalle = visitante.page.locator('.detail');
  await detalle.getByText('Precio a consultar').waitFor();
  await detalle.getByText('En negociación').waitFor();
  await foto(visitante.page, 'pub-catalogo-consulta-1440');
  for (const [w, h] of [[1440, 900], [1024, 768], [768, 1024], [390, 844], [375, 812], [959, 900], [961, 900]]) {
    await visitante.page.setViewportSize({ width: w, height: h });
    const ancho = await visitante.page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(ancho <= w, `${w}: page is ${ancho}px wide`);
    if ([390, 768].includes(w)) await foto(visitante.page, `pub-catalogo-${w}`);
  }
  assert.ok(!(await html(visitante.page)).includes(SENTINELA));
  const privadas = visitante.api.filter((l) => !/\/api\/(config|session|publico\/)/.test(l));
  assert.deepEqual(privadas, [], 'anonymous makes only public calls');
  assert.deepEqual(visitante.errores, []);
  await visitante.context.close();

  // Signed in, "Catálogo público" is the same real public response.
  await ana.page.goto(`${URL_BASE}/#/catalogo`);
  await ana.page.locator('.toolbar-estado', { hasText: `${total} terreno` }).waitFor();
});

await caso('a saved price change stays private and is flagged until it is published', async () => {
  await ana.page.goto(`${URL_BASE}/#/inventario/${lote.id}/editar`);
  await ana.page.getByLabel('Asking $/m²').fill('130.25');
  await ana.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await ana.page.waitForURL(new RegExp(`#/inventario/${lote.id}$`));
  const detalle = ana.page.locator('aside.detail');
  await detalle.locator('.estado-chip', { hasText: 'Publicado · Cambios pendientes' }).waitFor();
  await detalle.getByText('Precio o disponibilidad guardados sin publicar').waitFor();
  await detalle.locator('.diff-destacado', { hasText: 'Asking $/m²' }).waitFor();
  await foto(ana.page, 'pub-cambios-pendientes-1440');
  assert.equal((await publico(lote.id)).body.terreno.asking_m2, 122.5, 'public still shows the published revision');
});

await caso('a stale publish returns to review; nothing is published unseen', async () => {
  const beto = await contexto();
  await beto.page.goto(`${URL_BASE}/`);
  await entrar(beto.page, 'beto');
  await abrirDetalle(ana.page, lote.id);
  await ana.page.locator('#vista-previa-btn').click();
  const dialogo = ana.page.getByRole('dialog', { name: 'Vista previa · Aún no publicada' });
  await dialogo.getByText('USD 130.25/m²').waitFor();

  // Beto saves while Ana is reviewing.
  const actual = (await llamar(beto.page, 'GET', `/inventario/terrenos/${lote.id}`)).body.terreno;
  const guardado = await llamar(beto.page, 'PATCH', `/inventario/terrenos/${lote.id}`,
    { expected_version: actual.version, changes: { asking_m2: 140.75 } });
  assert.equal(guardado.status, 200);

  await dialogo.getByRole('button', { name: 'Publicar' }).click();
  const nuevo = ana.page.getByRole('dialog', { name: 'Vista previa · Aún no publicada' });
  await nuevo.getByText('Otra persona cambió este terreno mientras lo revisabas').waitFor();
  await nuevo.getByText('USD 140.75/m²').waitFor();
  await foto(ana.page, 'pub-publicacion-obsoleta-1440');
  assert.equal((await publico(lote.id)).body.terreno.asking_m2, 122.5, 'the stale publish changed nothing');
  await nuevo.getByRole('button', { name: 'Publicar' }).click();
  await nuevo.waitFor({ state: 'detached' });
  await ana.page.locator('aside.detail .estado-chip', { hasText: /^Publicado$/ }).waitFor();
  assert.equal((await publico(lote.id)).body.terreno.asking_m2, 140.75);
  assert.deepEqual(beto.errores, []);
  await beto.context.close();
});

await caso('sold: saved = warned and still public; published = out of the catalog, labelled "Fuera del catálogo · Vendido"', async () => {
  const vendido = await crear(ana.page, { ...COMPLETO, terreno: `Lote Vendido ${SELLO}`, lat: 20.6, lon: -103.5 });
  await abrirDetalle(ana.page, vendido.id);
  await publicarDesdeDetalle(ana.page);
  await ana.page.goto(`${URL_BASE}/#/inventario/${vendido.id}/editar`);
  await ana.page.getByLabel('Disponibilidad', { exact: true }).selectOption('sold');
  await ana.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await ana.page.waitForURL(new RegExp(`#/inventario/${vendido.id}$`));
  await ana.page.locator('aside.detail').getByText(/marca este terreno como «Vendido»/).waitFor();
  assert.equal((await publico(vendido.id)).status, 200, 'a saved sold draft alone changes nothing publicly');

  await ana.page.locator('#vista-previa-btn').click();
  const dialogo = ana.page.getByRole('dialog', { name: 'Vista previa · Aún no publicada' });
  await dialogo.getByText('Al publicar, este terreno saldrá del catálogo público.').waitFor();
  await dialogo.getByRole('button', { name: 'Publicar' }).click();
  await dialogo.waitFor({ state: 'detached' });
  await ana.page.locator('aside.detail .estado-chip', { hasText: 'Fuera del catálogo · Vendido' }).waitFor();
  assert.equal((await publico(vendido.id)).status, 404);

  const visitante = await contexto();
  await visitante.page.goto(`${URL_BASE}/#/catalogo/${vendido.id}`);
  await visitante.page.getByText('Este terreno no está en el catálogo público.').waitFor();
  assert.ok(!(await html(visitante.page)).includes(`Lote Vendido ${SELLO}`));
  await visitante.context.close();
});

await caso('Retirar del catálogo, Archivar and Restaurar: named confirmations, immediate withdrawal, no republish', async () => {
  const otro = await crear(ana.page, { ...COMPLETO, terreno: `Lote Ciclo ${SELLO}`, lat: 21.0, lon: -103.0 });
  await abrirDetalle(ana.page, otro.id);
  await publicarDesdeDetalle(ana.page);
  assert.equal((await publico(otro.id)).status, 200);

  await ana.page.getByRole('button', { name: 'Retirar del catálogo' }).click();
  let confirmar = ana.page.getByRole('dialog', { name: 'Retirar del catálogo' });
  await confirmar.getByText(`«Lote Ciclo ${SELLO}» dejará de verse en el catálogo público`).waitFor();
  await confirmar.getByRole('button', { name: 'Retirar del catálogo' }).click();
  await ana.page.locator('aside.detail .estado-chip', { hasText: /^No publicado$/ }).waitFor();
  assert.equal((await publico(otro.id)).status, 404);

  await publicarDesdeDetalle(ana.page);
  await ana.page.getByRole('button', { name: 'Archivar' }).click();
  confirmar = ana.page.getByRole('dialog', { name: 'Archivar terreno' });
  await confirmar.getByText(/dejará de verse en el catálogo público/).waitFor();
  await confirmar.getByRole('button', { name: 'Archivar' }).click();
  await ana.page.locator('aside.detail .estado-chip', { hasText: 'Archivado' }).waitFor();
  assert.equal((await publico(otro.id)).status, 404);
  await foto(ana.page, 'pub-archivado-1440');
  // Hidden from the default inventory list.
  const lista = (await llamar(ana.page, 'GET', '/inventario/terrenos?limit=250')).body;
  assert.ok(!lista.terrenos.some((t) => t.id === otro.id));

  await ana.page.getByRole('button', { name: 'Restaurar' }).click();
  confirmar = ana.page.getByRole('dialog', { name: 'Restaurar terreno' });
  await confirmar.getByText(/No aparece en el catálogo hasta que alguien lo publique de nuevo/).waitFor();
  await confirmar.getByRole('button', { name: 'Restaurar' }).click();
  await ana.page.locator('aside.detail .estado-chip', { hasText: /^No publicado$/ }).waitFor();
  assert.equal((await publico(otro.id)).status, 404, 'restore never republishes');

  const eventos = (await llamar(ana.page, 'GET', `/inventario/terrenos/${otro.id}/historial`)).body.eventos;
  assert.deepEqual(eventos.map((e) => e.action),
    ['restore', 'archive', 'publish', 'unpublish', 'publish', 'create']);
  await ana.page.locator('#historial-btn').click();
  const historial = ana.page.getByRole('dialog', { name: 'Historial' });
  await historial.getByText('Restauró').waitFor();
  await historial.getByText('Archivó').waitFor();
  await historial.getByText('Retiró del catálogo').first().waitFor();
  await historial.getByRole('button', { name: 'Cerrar' }).click();
});

await caso('D-1: closing Historial with Escape returns focus to the Historial button', async () => {
  await abrirDetalle(ana.page, lote.id);
  await ana.page.locator('#historial-btn').focus();
  await ana.page.keyboard.press('Enter');
  await ana.page.getByRole('dialog', { name: 'Historial' }).waitFor();
  await ana.page.getByText('Publicó').first().waitFor();
  await ana.page.keyboard.press('Escape');
  await ana.page.getByRole('dialog', { name: 'Historial' }).waitFor({ state: 'detached' });
  const foco = await ana.page.evaluate(() => document.activeElement?.id || document.activeElement?.tagName);
  assert.equal(foco, 'historial-btn');
  // Also after closing with the Cerrar button.
  await ana.page.keyboard.press('Enter');
  await ana.page.getByRole('dialog', { name: 'Historial' }).getByRole('button', { name: 'Cerrar' }).click();
  assert.equal(await ana.page.evaluate(() => document.activeElement?.id), 'historial-btn');
});

await caso('inventory table has a publication status column', async () => {
  await ana.page.goto(`${URL_BASE}/#/inventario`);
  await ana.page.getByRole('button', { name: 'Tabla' }).click();
  await ana.page.locator('th', { hasText: 'Publicación' }).waitFor();
  await ana.page.locator('.table tbody tr', { hasText: `Lote Vendido ${SELLO}` })
    .locator('.estado-chip', { hasText: 'Fuera del catálogo · Vendido' }).waitFor();
  await ana.page.locator('.table tbody tr', { hasText: `Lote Público ${SELLO}` })
    .locator('.estado-chip', { hasText: /^Publicado$/ }).waitFor();
  await foto(ana.page, 'pub-tabla-estado-1440');
  await ana.page.getByRole('button', { name: 'Mapa' }).click();
});

await caso('phone: toasts stay clear of the editor action bar; preview is reachable at 390 and 375', async () => {
  for (const [w, h] of [[390, 844], [375, 812]]) {
    const tel = await contexto({ ancho: w, alto: h });
    await tel.page.goto(`${URL_BASE}/`);
    await entrar(tel.page, 'ana');
    await tel.page.goto(`${URL_BASE}/#/inventario/${lote.id}/editar`);
    const barra = tel.page.locator('.editor-acciones');
    await barra.waitFor();
    await tel.page.evaluate(() => import('/components/ui/toast.js').then((m) => m.toast('Aviso de prueba para el teléfono')));
    const aviso = tel.page.locator('.toast', { hasText: 'Aviso de prueba' });
    await aviso.waitFor();
    await tel.page.waitForTimeout(400);
    const a = await aviso.boundingBox();
    const b = await barra.boundingBox();
    assert.ok(a.y + a.height <= b.y, `${w}: toast bottom ${a.y + a.height} overlaps bar top ${b.y}`);
    for (const nombre of ['Guardar borrador', 'Vista previa']) {
      const caja = await barra.getByRole('button', { name: nombre }).boundingBox();
      assert.ok(caja && caja.x >= 0 && caja.x + caja.width <= w, `${w}: ${nombre} inside the viewport`);
    }
    const ancho = await tel.page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(ancho <= w, `${w}: page is ${ancho}px wide`);
    await foto(tel.page, `pub-editor-toast-${w}`);
    await barra.getByRole('button', { name: 'Vista previa' }).click();
    const dialogo = tel.page.getByRole('dialog', { name: 'Vista previa · Aún no publicada' });
    await dialogo.waitFor();
    await foto(tel.page, `pub-vista-previa-${w}`);
    await dialogo.getByRole('button', { name: 'Cerrar' }).click();
    assert.deepEqual(tel.errores, []);
    await tel.context.close();
  }
});

await caso('the editor asks to save first: no preview of unsaved input', async () => {
  await ana.page.goto(`${URL_BASE}/#/inventario/${lote.id}/editar`);
  await ana.page.getByLabel('Dirección').fill('Cambio sin guardar');
  await ana.page.getByRole('button', { name: 'Vista previa' }).click();
  await ana.page.getByText('Guarda el borrador antes de la vista previa').waitFor();
  assert.equal(await ana.page.getByRole('dialog', { name: 'Vista previa · Aún no publicada' }).count(), 0);
  await ana.page.locator('.editor-acciones').getByRole('button', { name: 'Cerrar', exact: true }).click();
  const descartar = ana.page.getByRole('dialog', { name: '¿Descartar cambios?' });
  await descartar.getByRole('button', { name: 'Descartar cambios' }).click();
});

await caso('logout after publishing leaves no private data, and the catalog still shows published records', async () => {
  await ana.page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await ana.page.waitForURL(/#\/catalogo$/);
  await ana.page.locator('.toolbar-estado', { hasText: /terreno/ }).waitFor();
  const contenido = await html(ana.page);
  assert.ok(!contenido.includes(SENTINELA));
  assert.ok(!contenido.includes(`Lote Vendido ${SELLO}`));
  assert.deepEqual(ana.errores, []);
  await ana.context.close();
});

await browser.close();
console.log(resultados.join('\n'));
console.log(`\n${resultados.length - fallos} ok, ${fallos} failed (INTEGRATED against ${URL_BASE})`);
process.exit(fallos ? 1 : 0);

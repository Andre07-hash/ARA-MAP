/* Interface checks for the inventory/catalog UI against CONTRACT FIXTURES.
 *
 * FIXTURE-ONLY: web/ is served statically and every /api/* call is answered
 * in-process from tests/js/fixtures/inventario. Nothing here exercises the
 * real backend, its persistence or its security boundary; it proves only that
 * the interface behaves correctly given contract-v1 responses. Integrated
 * evidence against the real server is recorded separately.
 *
 *   node tests/e2e/inventario-fixtures.mjs [carpeta-de-capturas]
 */

import assert from 'node:assert/strict';
import { createReadStream, existsSync, mkdirSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

import { fixture, paginate, publicTerrains } from '../js/fixtures/inventario/index.mjs';

const WEB = fileURLToPath(new URL('../../web/', import.meta.url));
const SHOTS = process.argv[2] ?? null;
const SENTINELA = 'SENTINELA-PRIVADO-7731';
const ANA = fixture('session-user').user;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

/* ---------------------------------------------------------- static server */

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png',
  '.csv': 'text/csv', '.svg': 'image/svg+xml' };
const server = createServer((req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^\/+/, '');
  const file = join(WEB, path || 'index.html');
  if (!file.startsWith(WEB) || !existsSync(file) || statSync(file).isDirectory()) {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream' });
  createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${server.address().port}`;

/* -------------------------------------------------------- the fake server */

function crearApi() {
  const s = {
    sesion: null,
    publicos: [],
    registros: new Map([
      fixture('internal-terrain-draft').terreno,
      fixture('internal-terrain-unplaced').terreno,
      fixture('internal-terrain-published-pending').terreno,
    ].map((t) => [t.id, structuredClone(t)])),
    claves: new Map(),
    clavesEnviadas: [],
    pedidas: [],
    perderRespuestaDeCreacion: 0,
    retrasoLista: 0,
    n: 100,
  };

  async function responder(route) {
    const req = route.request();
    const url = new URL(req.url());
    const ruta = url.pathname;
    const metodo = req.method();
    s.pedidas.push(`${metodo} ${ruta}${url.search}`);
    const json = (status, body) => route.fulfill({
      status, contentType: 'application/json', headers: { 'Cache-Control': 'no-store' },
      body: JSON.stringify(body),
    });
    const cuerpo = () => JSON.parse(req.postData() || '{}');
    const pagina = (items) => paginate(items, {
      limit: Number(url.searchParams.get('limit') ?? 100), cursor: url.searchParams.get('cursor'),
    });

    if (ruta === '/api/config') return json(200, { readOnly: !s.sesion, cloud: false, authRequired: true });
    if (ruta === '/api/session') {
      return json(200, s.sesion ? { authenticated: true, user: s.sesion } : { authenticated: false });
    }
    if (ruta === '/api/login') {
      const { username, password } = cuerpo();
      if (username === 'ana' && password === 'correcta') {
        s.sesion = ANA;
        return json(200, { authenticated: true, user: ANA });
      }
      return json(401, { error: 'Usuario o contraseña incorrectos.', detalle: { code: 'invalid_credentials' } });
    }
    if (ruta === '/api/logout') { s.sesion = null; return json(200, { authenticated: false }); }
    if (ruta === '/api/publico/terrenos') return json(200, pagina(s.publicos));
    if (ruta.startsWith('/api/publico/terrenos/')) {
      const t = s.publicos.find((x) => x.id === decodeURIComponent(ruta.split('/').pop()));
      return t ? json(200, { terreno: t }) : json(404, fixture('error-404-public'));
    }

    if (!s.sesion) return json(401, fixture('error-401'));

    if (ruta === '/api/bases' ) return json(200, { bases: [] });
    if (ruta === '/api/mapas') return json(200, { mapas: [] });
    if (ruta === '/api/carpetas') return json(200, { carpetas: [] });

    if (ruta === '/api/inventario/terrenos' && metodo === 'GET') {
      if (s.retrasoLista) await new Promise((r) => setTimeout(r, s.retrasoLista));
      const items = [...s.registros.values()];
      return json(200, {
        ...pagina(items),
        facets: { estados: [...new Set(items.map((t) => t.draft.estado).filter(Boolean))].sort(),
          municipios: [...new Set(items.map((t) => t.draft.municipio).filter(Boolean))].sort(), monedas: ['MXN', 'USD'] },
      });
    }
    if (ruta === '/api/inventario/terrenos' && metodo === 'POST') {
      const clave = req.headers()['idempotency-key'];
      s.clavesEnviadas.push(clave);
      if (!clave) return json(422, { error: 'Falta Idempotency-Key', detalle: { code: 'idempotency_key_required' } });
      const datos = cuerpo();
      const previa = s.claves.get(clave);
      if (previa) {
        return previa.firma === JSON.stringify(datos)
          ? json(200, { terreno: s.registros.get(previa.id) })
          : json(409, fixture('error-409-idempotency'));
      }
      if (datos.asking_price != null && !datos.moneda) {
        return json(422, { error: 'Revisa los campos marcados.', detalle: { code: 'validation_failed',
          fields: { moneda: 'Indica la moneda del precio: USD o MXN.' } } });
      }
      const id = `3f1c2b9e-7a4d-4f6e-8b21-0c9d5e6f0${s.n++}`;
      const nuevo = { ...structuredClone(fixture('internal-terrain-unplaced').terreno), id, version: 1,
        draft: { ...fixture('internal-terrain-unplaced').terreno.draft, terreno: null, estado: null,
          municipio: null, superficie_m2: null, ...datos } };
      s.registros.set(id, nuevo);
      s.claves.set(clave, { id, firma: JSON.stringify(datos) });
      if (s.perderRespuestaDeCreacion > 0) { s.perderRespuestaDeCreacion -= 1; return route.abort('failed'); }
      return json(200, { terreno: nuevo });
    }

    const m = ruta.match(/^\/api\/inventario\/terrenos\/([^/]+)(\/historial)?$/);
    if (m) {
      const t = s.registros.get(decodeURIComponent(m[1]));
      if (!t) return json(404, { error: 'El terreno no existe.', detalle: { code: 'not_found' } });
      if (m[2]) return json(200, url.searchParams.get('cursor') ? fixture('historial-page2') : fixture('historial'));
      if (metodo === 'GET') return json(200, { terreno: t });
      if (metodo === 'PATCH') {
        const { expected_version, changes } = cuerpo();
        if (expected_version !== t.version) {
          return json(409, { error: fixture('error-409-conflict').error,
            detalle: { code: 'conflict', current_version: t.version, terreno: t } });
        }
        const siguiente = { ...t, version: t.version + 1, draft: { ...t.draft, ...changes },
          draft_revision_id: `9a0e7b1c-0000-4000-8000-0000000001${t.version + 1}`, updated_by: ANA };
        s.registros.set(t.id, siguiente);
        return json(200, { terreno: siguiente });
      }
    }
    return json(404, { error: 'Ruta desconocida', detalle: { code: 'not_found' } });
  }
  return { s, responder };
}

/* ---------------------------------------------------------------- helpers */

const browser = await chromium.launch({ channel: 'chrome' });
const resultados = [];
let fallos = 0;

async function caso(nombre, fn) {
  try {
    await fn();
    resultados.push(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    resultados.push(`FAIL ${nombre}\n     ${error.message.split('\n').join('\n     ')}`);
  }
}

async function abrir({ ancho = 1440, alto = 900, api = crearApi(), hash = '' } = {}) {
  const context = await browser.newContext({ viewport: { width: ancho, height: alto }, locale: 'es-MX' });
  const page = await context.newPage();
  const errores = [];
  page.on('pageerror', (e) => errores.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errores.push(m.text()); });
  await page.route('**/api/**', api.responder);
  // Tiles are irrelevant here and must not leave the machine.
  await page.route(/arcgisonline|openstreetmap|carto/, (r) => r.fulfill({ status: 204, body: '' }));
  await page.goto(`${BASE}/${hash}`);
  return { context, page, api, errores };
}

const foto = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); };
const texto = (page) => page.evaluate(() => document.body.innerText);
const html = (page) => page.evaluate(() => document.documentElement.outerHTML);

async function entrar(page) {
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.getByLabel('Usuario').fill('ana');
  await page.getByLabel('Contraseña').fill('correcta');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(/#\/inventario/);
  await page.locator('.toolbar-estado', { hasText: '3 terrenos' }).waitFor();
}

/* ------------------------------------------------------------------ cases */

await caso('anonymous startup asks only for config, session and the public catalog', async () => {
  const { context, page, api, errores } = await abrir();
  await page.getByText('Todavía no hay terrenos publicados').waitFor();
  const privadas = api.s.pedidas.filter((p) => !/^GET \/api\/(config|session|publico\/terrenos)/.test(p));
  assert.deepEqual(privadas, []);
  assert.match(page.url(), /#\/catalogo$/);
  for (const [w, h] of [[1440, 900], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width: w, height: h });
    await foto(page, `catalogo-vacio-${w}`);
  }
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('251 published terrains: count, table and map agree after every page arrives', async () => {
  const api = crearApi();
  api.s.publicos = publicTerrains(251);
  const { context, page, errores } = await abrir({ api });
  await page.locator('.toolbar-estado', { hasText: '251 terrenos' }).waitFor();
  const paginas = api.s.pedidas.filter((p) => p.startsWith('GET /api/publico/terrenos?'));
  assert.equal(paginas.length, 2, paginas.join('\n'));
  await page.getByRole('button', { name: 'Tabla' }).click();
  assert.equal(await page.locator('.table tbody tr').count(), 251);
  const ids = await page.evaluate(() => document.querySelectorAll('.table tbody tr').length);
  assert.equal(ids, 251);
  await page.getByRole('button', { name: 'Mapa' }).click();
  await page.locator('.legend-count', { hasText: '251 terrenos' }).waitFor();
  await foto(page, 'catalogo-251-1440');
  await page.locator('.table-slot').waitFor({ state: 'attached' });
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('phone: the Filtros drawer holds every control, keeps state and returns focus', async () => {
  const api = crearApi();
  api.s.publicos = publicTerrains(251);
  const { context, page, errores } = await abrir({ api, ancho: 390, alto: 844 });
  await page.locator('.toolbar-estado', { hasText: '251 terrenos' }).waitFor();
  assert.equal(await page.locator('.rail-slot').isVisible(), false);
  const boton = page.locator('.filtros-btn');
  await boton.click();
  const drawer = page.getByRole('dialog', { name: 'Filtros' });
  await drawer.waitFor();
  await foto(page, 'catalogo-filtros-390');
  await drawer.getByLabel('Buscar').fill('sintético 25');
  await drawer.getByText('Ver todos', { exact: false }).count();   // present when > limit
  const consulta = page.waitForRequest((r) => /estado=Jalisco/.test(r.url()) && /q=sint/.test(r.url()));
  await drawer.getByLabel('Jalisco').check();
  await consulta;   // debounced: one combined query, not one per keystroke
  await page.keyboard.press('Escape');
  await drawer.waitFor({ state: 'detached' });
  await page.waitForFunction(() => document.activeElement?.id === 'filtros-btn', null, { timeout: 2000 });
  await page.locator('.filtros-btn', { hasText: 'Filtros (2)' }).waitFor();
  const ultima = api.s.pedidas.filter((p) => p.startsWith('GET /api/publico/terrenos?') && !p.includes('cursor=')).at(-1);
  assert.match(ultima, /q=sint%C3%A9tico\+25/);
  assert.match(ultima, /estado=Jalisco/);
  await page.locator('.filtros-btn').click();
  assert.equal(await page.getByLabel('Buscar').inputValue(), 'sintético 25');
  assert.equal(await page.getByLabel('Jalisco').isChecked(), true);
  await page.getByRole('button', { name: 'Ver resultados' }).click();
  const anchoDoc = await page.evaluate(() => document.documentElement.scrollWidth);
  assert.ok(anchoDoc <= 390, `page is ${anchoDoc}px wide`);
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('a public price-on-request terrain says so, and negotiation is labelled', async () => {
  const api = crearApi();
  api.s.publicos = [fixture('public-terrain').terreno];
  const { context, page, errores } = await abrir({ api, hash: `#/catalogo/${fixture('public-terrain').terreno.id}` });
  await page.getByText('Precio a consultar').waitFor();
  await page.locator('.detail .estado-chip', { hasText: 'En negociación' }).waitFor();
  await foto(page, 'catalogo-detalle-1440');
  await page.setViewportSize({ width: 390, height: 844 });
  await foto(page, 'catalogo-detalle-390');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('a private deep link offers sign-in, then returns there', async () => {
  const id = fixture('internal-terrain-draft').terreno.id;
  const { context, page, api, errores } = await abrir({ hash: `#/inventario/${id}` });
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  assert.match(page.url(), /#\/catalogo$/);
  assert.ok(!api.s.pedidas.some((p) => p.includes('/inventario/')), 'no private request before sign-in');
  await page.getByLabel('Usuario').fill('ana');
  await page.getByLabel('Contraseña').fill('mala');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.getByText('Usuario o contraseña incorrectos.').waitFor();
  await page.getByLabel('Contraseña').fill('correcta');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(new RegExp(`#/inventario/${id}$`));
  await page.locator('.detail h2', { hasText: 'Lote Las Ánimas' }).waitFor();
  await page.locator('.session-user', { hasText: 'Ana Prueba' }).waitFor();
  await foto(page, 'inventario-detalle-1440');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('edit: 409 keeps my input, shows their change, and saves only after review', async () => {
  const id = fixture('internal-terrain-draft').terreno.id;
  const { context, page, api, errores } = await abrir();
  await entrar(page);
  await page.goto(`${BASE}/#/inventario/${id}/editar`);
  await page.getByLabel('Asking Price (total)').waitFor();
  await page.getByLabel('Asking Price (total)').fill('1,550,000');
  await page.getByLabel('Nombre').fill('Lote Las Ánimas Norte');
  // Meanwhile Beto saves version 4 (price and notes).
  api.s.registros.set(id, structuredClone(fixture('internal-terrain-draft-v4').terreno));
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.getByText('Otra persona guardó este terreno mientras lo editabas').waitFor();
  assert.equal(await page.getByLabel('Asking Price (total)').inputValue(), '1,550,000');
  assert.equal(await page.getByLabel('Nombre').inputValue(), 'Lote Las Ánimas Norte');
  assert.equal(await page.getByRole('button', { name: 'Guardar borrador' }).isDisabled(), true);
  await foto(page, 'editor-conflicto-1440');
  await page.getByRole('button', { name: 'Revisar cambios' }).click();
  // Their note arrives; my clashing price stays mine, marked.
  assert.match(await page.getByLabel('Notas internas').inputValue(), /Nota corregida/);
  assert.equal(await page.getByLabel('Asking Price (total)').inputValue(), '1,550,000');
  await page.locator('.is-conflicto').first().waitFor();
  const antes = api.s.pedidas.filter((p) => p.startsWith('PATCH')).length;
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.waitForURL(new RegExp(`#/inventario/${id}$`));
  const patches = api.s.pedidas.filter((p) => p.startsWith('PATCH'));
  assert.equal(patches.length, antes + 1);
  const guardado = api.s.registros.get(id);
  assert.equal(guardado.version, 5);
  assert.equal(guardado.draft.asking_price, 1550000);
  assert.equal(guardado.draft.terreno, 'Lote Las Ánimas Norte');
  assert.match(guardado.draft.notas_internas, /Nota corregida/);   // theirs kept
  await page.getByText('Borrador guardado · versión 5').waitFor();
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('new draft: client and server field errors, and a lost response retried with the same key', async () => {
  const { context, page, api, errores } = await abrir();
  await entrar(page);
  await page.getByRole('link', { name: 'Nuevo terreno' }).first().click();
  await page.getByLabel('Nombre').fill('Predio de prueba');
  await page.getByLabel('Latitud (X)').fill('20,67');
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.getByText('Usa punto decimal', { exact: false }).first().waitFor();
  assert.ok(!api.s.pedidas.some((p) => p.startsWith('POST /api/inventario')), 'no request with an unreadable number');
  await page.getByLabel('Latitud (X)').fill('20.67');
  await page.getByText('Falta la longitud (Y)', { exact: false }).waitFor();   // a warning, not a block (§9.1)
  await page.getByLabel('Longitud (Y)').fill('-103.34');
  await page.getByLabel('Asking Price (total)').fill('900000');
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.locator('#ed-moneda-error', { hasText: 'Indica la moneda' }).waitFor();
  assert.equal(await page.getByLabel('Moneda').getAttribute('aria-invalid'), 'true');
  await foto(page, 'editor-error-422-1440');
  await page.getByLabel('Moneda').selectOption('MXN');
  api.s.perderRespuestaDeCreacion = 1;
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.getByText('No se pudo confirmar si el borrador se creó', { exact: false }).waitFor();
  assert.equal(await page.getByLabel('Nombre').inputValue(), 'Predio de prueba');
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await page.waitForURL(/#\/inventario\/3f1c/);
  const [rechazada, perdida, reintento] = api.s.clavesEnviadas;
  assert.equal(api.s.clavesEnviadas.length, 3);
  assert.notEqual(rechazada, perdida, 'a changed body gets a new key');
  assert.equal(perdida, reintento, 'the uncertain retry reuses its key');
  assert.equal(api.s.registros.size, 4, 'the retry created nothing new');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('phone editor: actions reachable, no horizontal overflow', async () => {
  const id = fixture('internal-terrain-draft').terreno.id;
  const { context, page, errores } = await abrir({ ancho: 390, alto: 844 });
  await entrar(page);
  await page.goto(`${BASE}/#/inventario/${id}/editar`);
  await page.getByLabel('Nombre').waitFor();
  await foto(page, 'editor-390');
  assert.ok(await page.getByRole('button', { name: 'Guardar borrador' }).isVisible());
  const anchoDoc = await page.evaluate(() => document.documentElement.scrollWidth);
  assert.ok(anchoDoc <= 390, `page is ${anchoDoc}px wide`);
  await page.setViewportSize({ width: 768, height: 1024 });
  await foto(page, 'editor-768');
  await page.setViewportSize({ width: 1440, height: 900 });
  await foto(page, 'editor-1440');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('leaving a dirty editor asks first; cancelling keeps the input', async () => {
  const id = fixture('internal-terrain-draft').terreno.id;
  const { context, page, errores } = await abrir();
  await entrar(page);
  await page.goto(`${BASE}/#/inventario/${id}/editar`);
  await page.getByLabel('Nombre').fill('Cambio sin guardar');
  await page.getByRole('link', { name: 'Bases' }).click();
  await page.getByRole('dialog', { name: '¿Descartar cambios?' }).waitFor();
  await page.getByRole('button', { name: 'Cancelar' }).click();
  await page.waitForURL(new RegExp(`#/inventario/${id}/editar$`));
  assert.equal(await page.getByLabel('Nombre').inputValue(), 'Cambio sin guardar');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('history panel lists actor, time, changes and confirmations, with paging', async () => {
  const id = fixture('internal-terrain-draft').terreno.id;
  const { context, page, errores } = await abrir();
  await entrar(page);
  await page.goto(`${BASE}/#/inventario/${id}`);
  await page.locator('.detail').getByRole('button', { name: 'Historial' }).click();
  const dialogo = page.getByRole('dialog', { name: 'Historial' });
  await dialogo.getByText('Beto Prueba', { exact: false }).waitFor();
  await dialogo.getByText('Confirmó: precio.').waitFor();
  await dialogo.getByRole('button', { name: 'Cargar más' }).click();
  await dialogo.getByText('Creó el borrador').waitFor();
  await foto(page, 'historial-1440');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('logout cancels pending private loads, clears private DOM, and Back shows nothing private', async () => {
  const id = fixture('internal-terrain-draft').terreno.id;
  const { context, page, api, errores } = await abrir();
  await entrar(page);
  await page.goto(`${BASE}/#/inventario/${id}`);
  await page.locator('.detail', { hasText: SENTINELA }).waitFor();
  api.s.retrasoLista = 1500;
  await page.locator('.filtros-btn').evaluate(() => {});      // no-op; keep desktop rail
  await page.getByLabel('Buscar').fill('Rancho');             // starts a slow private query
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await page.waitForURL(/#\/catalogo$/);
  await page.waitForTimeout(1800);                            // the slow response lands now
  for (const contenido of [await texto(page), await html(page)]) {
    assert.ok(!contenido.includes(SENTINELA), 'sentinel after logout');
    assert.ok(!contenido.includes('Lote Las Ánimas'), 'private name after logout');
  }
  await page.goBack();
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  const despues = await html(page);
  assert.ok(!despues.includes(SENTINELA) && !despues.includes('Lote Las Ánimas'), 'Back resurrected private content');
  await foto(page, 'logout-back-1440');
  assert.deepEqual(errores, []);
  await context.close();
});

await browser.close();
server.close();
console.log(resultados.join('\n'));
console.log(`\n${resultados.length - fallos} ok, ${fallos} failed (fixture-only; not integrated)`);
process.exit(fallos ? 1 : 0);

/* Independent Stage 1 browser pass (verifier-owned). Run via run_browser.py only:
 * it refuses anything but http://127.0.0.1:8433 and expects a freshly seeded disposable server.
 * Writes OUT/browser_results.json and OUT/shots/*.png. Exit 1 on any FAIL.
 */
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const PW = '/Users/andrejasso/Desktop/ARA Map/tests/e2e/node_modules/playwright-core/index.mjs';
const { chromium } = await import(PW);

const SEED = JSON.parse(readFileSync(process.env.SEED, 'utf8'));
const OUT = process.env.OUT;
const SHOTS = join(OUT, 'shots');
mkdirSync(SHOTS, { recursive: true });
const URL_BASE = SEED.url;
if (URL_BASE !== 'http://127.0.0.1:8433') throw new Error(`REFUSING target ${URL_BASE}`);
console.log(`[target] ${URL_BASE}`);
const USERS = Object.fromEntries(JSON.parse(readFileSync(SEED.users_file, 'utf8')).map((u) => [u.tag, u]));
const LEGACY = JSON.parse(readFileSync(SEED.legacy_manifest, 'utf8'));
const SENT = /sntl-[a-z]+-[a-z0-9]+-[0-9a-f]{6}/i;
const SIZES = [[1440, 900], [1024, 768], [768, 1024], [390, 844], [375, 812], [959, 900], [961, 900]];
const UI_SENT = `SNTL-UICONTACT-UI${Date.now() % 100000}-c0ffee`;

const browser = await chromium.launch();
const results = [];
const perf = {};
const rec = (kase, check, status, detail = null) => {
  results.push({ case: kase, check, status, detail });
  console.log(`  [${status}] ${kase} :: ${check}${status !== 'PASS' && detail ? ` -- ${JSON.stringify(detail).slice(0, 300)}` : ''}`);
};
const ok = (kase, check, cond, detail) => rec(kase, check, cond ? 'PASS' : 'FAIL', cond ? null : detail);

async function caso(kase, fn) {
  console.log(`== ${kase}`);
  try { await fn(); } catch (e) { rec(kase, 'case crashed', 'FAIL', String(e.message).split('\n').slice(0, 4).join(' | ')); }
}

async function ctx({ w = 1440, h = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width: w, height: h }, locale: 'es-MX' });
  const page = await context.newPage();
  const api = [];
  const errors = [];
  const dialogs = [];
  page.on('request', (r) => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/')) api.push({ m: r.method(), p: u.pathname, q: u.search }); });
  page.on('response', (r) => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/')) api.push({ status: r.status(), p: u.pathname }); });
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('dialog', async (d) => { dialogs.push(d.message()); await d.dismiss(); });   // any alert() = executed XSS
  await page.route(/arcgisonline|openstreetmap|tile/, (r) => r.fulfill({ status: 204, body: '' }));
  await page.addInitScript(() => {   // count CircleMarkers in Leaflet layer groups (map uses preferCanvas)
    let real;
    Object.defineProperty(window, 'L', { configurable: true, get: () => real, set: (v) => {
      real = v;
      const lg = v.layerGroup;
      v.layerGroup = function (...a) { const g = lg.apply(this, a); (window.__lgs ||= []).push(g); return g; };
    } });
  });
  return { context, page, api, errors, dialogs };
}

const shot = (page, name) => page.screenshot({ path: join(SHOTS, `${name}.png`) });
async function snapshot(page) {
  return page.evaluate(async () => ({
    html: document.documentElement.outerHTML,
    values: [...document.querySelectorAll('input,textarea,select')].map((e) => e.value).join('\n'),
    ls: JSON.stringify({ ...localStorage }),
    ss: JSON.stringify({ ...sessionStorage }),
    url: location.href,
    title: document.title,
    caches: 'caches' in window ? (await caches.keys()).join(',') : '',
  }));
}
async function sentinelHits(page) {
  const s = await snapshot(page);
  return Object.entries(s).filter(([, v]) => SENT.test(v)).map(([k, v]) => `${k}:${v.match(SENT)[0]}`);
}
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth);
const status = (page) => page.locator('.toolbar-estado').first().innerText();

async function signIn(page, tag, { open = true } = {}) {
  if (open) await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.getByLabel('Usuario').fill(USERS[tag].username);
  await page.getByLabel('Contraseña').fill(USERS[tag].password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
}
async function apiJson(page, path) {
  const r = await page.request.get(`${URL_BASE}${path}`);
  return { status: r.status(), body: r.status() === 200 ? await r.json() : null };
}
async function waitCount(page, n, timeout = 60000) {
  await page.locator('.toolbar-estado', { hasText: new RegExp(`^${n} terrenos?$`) }).waitFor({ timeout });
}

/* ------------------------------------------------------------------ B1 anonymous startup + widths */
await caso('B1-anon-startup', async () => {
  const { context, page, api, errors } = await ctx();
  const all = [];
  page.on('request', (r) => all.push(new URL(r.url()).pathname));
  await page.goto(`${URL_BASE}/`);
  await page.getByText('Todavía no hay terrenos publicados').waitFor();
  await page.waitForTimeout(1500);
  const calls = [...new Set(api.filter((a) => a.m).map((a) => `${a.m} ${a.p}`))].sort();
  ok('VIEW-01', 'anonymous startup calls exactly config, session, publico/terrenos', JSON.stringify(calls) ===
    JSON.stringify(['GET /api/config', 'GET /api/publico/terrenos', 'GET /api/session']), calls);
  ok('VIEW-01', 'no anonymous 401s (no private calls attempted)', !api.some((a) => a.status === 401), api);
  ok('ID-02', 'anonymous DOM/storage/URL carry no sentinel', (await sentinelHits(page)).length === 0, await sentinelHits(page));
  ok('VIEW-01', 'anonymous nav offers only Catálogo + Iniciar sesión',
    (await page.getByRole('link', { name: 'Bases' }).count()) === 0 && (await page.getByRole('link', { name: 'Inventario' }).count()) === 0);
  for (const [w, h] of SIZES) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(250);
    await shot(page, `anon-catalogo-${w}x${h}`);
    const sw = await overflow(page);
    ok('VIEW-01', `anonymous catalog ${w}x${h}: no horizontal overflow`, sw <= w, sw);
  }
  rec('PUB/VIEW', 'public catalog with records (Stage 2)', 'N/A', 'no publish route in Stage 1; empty-state only');
  ok('B1', 'no page/console errors', errors.length === 0, errors);
  await context.close();
});

/* ------------------------------------------------------------------ B2 deep link + sign-in return */
const idM001 = SEED.ids.M001;
await caso('B2-deeplink', async () => {
  const { context, page, api, errors } = await ctx();
  await page.goto(`${URL_BASE}/#/inventario/${idM001}`);
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  ok('ID-02', 'private deep link shows sign-in, no private data in page', (await sentinelHits(page)).length === 0, await sentinelHits(page));
  ok('ID-02', 'no private API call before sign-in', !api.some((a) => a.p && a.p.startsWith('/api/inventario')), api.filter((a) => a.m));
  await page.getByLabel('Usuario').fill(USERS.A.username);
  await page.getByLabel('Contraseña').fill('incorrecta-123456');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.getByText('Usuario o contraseña incorrectos.').waitFor();
  ok('ID-02', 'wrong password shows generic message', true);
  await page.getByLabel('Contraseña').fill(USERS.A.password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(new RegExp(`#/inventario/${idM001}$`));
  await page.locator('.detail').getByText(/SNTL-CONTACT-M001/).waitFor();
  ok('ID-02', 'after sign-in returns to the deep-linked record (team sees private contact)', true);
  const cookies = await context.cookies();
  const c = cookies.find((k) => k.name === 'ara_sesion');
  ok('ID-02', 'session cookie HttpOnly + SameSite=Strict in browser', c && c.httpOnly && c.sameSite === 'Strict', c && { httpOnly: c.httpOnly, sameSite: c.sameSite });
  ok('ID-02', 'session token not readable by page script', !(await page.evaluate(() => document.cookie)).includes('ara_sesion'));
  await shot(page, 'deeplink-return-1440');
  ok('B2', 'no page/console errors', errors.filter((e) => !/401/.test(e)).length === 0, errors);
  await context.close();
});

/* ------------------------------------------------------------------ B3 three identities in the UI */
let uiId = null;
await caso('B3-three-identities', async () => {
  const A = await ctx(); const B = await ctx({ w: 1024, h: 768 }); const C = await ctx({ w: 768, h: 1024 });
  for (const [x, t] of [[A, 'A'], [B, 'B'], [C, 'C']]) { await x.page.goto(`${URL_BASE}/`); await signIn(x.page, t); }
  // A creates through the editor: 422 currency rule first, then saved.
  await A.page.getByRole('link', { name: 'Nuevo terreno' }).first().click();
  await A.page.getByLabel('Nombre').fill('Lote UI <i>Verificación</i> =1+1');
  await A.page.getByLabel('Estado').fill('Querétaro');
  await A.page.getByLabel('Municipio').fill('El Marqués');
  await A.page.getByLabel('Latitud (X)').fill('20.6301');
  await A.page.getByLabel('Longitud (Y)').fill('-100.2801');
  await A.page.getByLabel('Superficie (m²)').fill('10,000');
  await A.page.getByLabel('Asking $/m²').fill('122.50');
  await A.page.getByLabel('Contacto').fill(`Contacto ${UI_SENT}`);
  await A.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await A.page.locator('#ed-moneda-error').waitFor();
  ok('INV-01', 'UI: price without currency gets field error, input kept', (await A.page.getByLabel('Asking $/m²').inputValue()) === '122.50');
  await A.page.getByLabel('Moneda').selectOption('USD');
  const t0 = Date.now();
  await A.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await A.page.waitForURL(/#\/inventario\/[0-9a-f-]{36}$/);
  perf.ui_create_ms = Date.now() - t0;
  uiId = A.page.url().split('/').pop();
  await A.page.locator('.detail').getByText('USD 122.50/m²').waitFor();
  const d = (await apiJson(A.page, `/api/inventario/terrenos/${uiId}`)).body.terreno;
  ok('INV-01', 'UI create persisted exact values (USD 122.5, 10000 m², literal name)',
    d.draft.asking_m2 === 122.5 && d.draft.moneda === 'USD' && d.draft.superficie_m2 === 10000
    && d.draft.terreno === 'Lote UI <i>Verificación</i> =1+1' && d.created_by.id && d.version === 1, d.draft);
  ok('INV-01', 'HTML-like name rendered literally (no <i> element from data)',
    (await A.page.locator('.detail i', { hasText: 'Verificación' }).count()) === 0);
  await shot(A.page, 'ui-create-detail-1440');

  // C starts editing at version 1; B edits A's record and saves; C's stale save -> 409 review.
  await C.page.goto(`${URL_BASE}/#/inventario/${uiId}/editar`);
  await C.page.getByLabel('Notas internas').fill('Nota de C SNTL-NOTE-UIC-0c0c0c');
  await C.page.getByLabel('Asking $/m²').fill('130.25');
  await B.page.goto(`${URL_BASE}/#/inventario/${uiId}/editar`);
  await B.page.getByLabel('Dirección').fill('Camino de B km 4');
  await B.page.getByLabel('Asking $/m²').fill('125.75');
  await B.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await B.page.getByText(/Borrador guardado · versión 2/).waitFor();
  ok('ID-01', 'UI: B edits and saves A\'s record', true);
  await C.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await C.page.getByText('Otra persona guardó este terreno mientras lo editabas').waitFor();
  ok('CON-01', 'UI: stale save shows conflict review', true);
  ok('CON-01', 'UI: C\'s typed values retained after 409', (await C.page.getByLabel('Asking $/m²').inputValue()) === '130.25'
    && (await C.page.getByLabel('Notas internas').inputValue()).includes('SNTL-NOTE-UIC'));
  const mid = (await apiJson(C.page, `/api/inventario/terrenos/${uiId}`)).body.terreno;
  ok('CON-01', 'UI: nothing of C written by the rejected save', mid.version === 2 && mid.draft.asking_m2 === 125.75
    && !(mid.draft.notas_internas || '').includes('UIC'), mid.draft);
  await shot(C.page, 'ui-conflict-768');
  await C.page.getByRole('button', { name: 'Revisar cambios' }).click();
  ok('CON-01', 'UI: review rebases on B\'s untouched field', (await C.page.getByLabel('Dirección').inputValue()) === 'Camino de B km 4');
  await C.page.getByRole('button', { name: 'Guardar borrador' }).click();
  await C.page.getByText(/Borrador guardado · versión 3/).waitFor();
  const fin = (await apiJson(C.page, `/api/inventario/terrenos/${uiId}`)).body.terreno;
  ok('CON-01', 'UI: deliberate resave = v3 with B\'s address + C\'s price/note, actor C',
    fin.version === 3 && fin.draft.direccion === 'Camino de B km 4' && fin.draft.asking_m2 === 130.25
    && fin.updated_by.display_name === USERS.C.display_name, { v: fin.version, d: fin.draft.direccion, p: fin.draft.asking_m2 });

  // History panel lists all three actors with before/after.
  await C.page.locator('.detail').getByRole('button', { name: 'Historial' }).click();
  const h = C.page.getByRole('dialog', { name: 'Historial' });
  for (const t of 'ABC') await h.getByText(USERS[t].display_name, { exact: false }).first().waitFor();
  const htext = await h.innerText();
  ok('INV-02', 'UI history: three actors, create + before→after values', htext.includes('125.75') && htext.includes('130.25'), htext.slice(0, 400));
  await shot(C.page, 'ui-history-1440');
  await C.page.keyboard.press('Escape');
  ok('INV-02', 'history dialog closes with Escape', (await C.page.getByRole('dialog', { name: 'Historial' }).count()) === 0
    || !(await C.page.getByRole('dialog', { name: 'Historial' }).isVisible()));
  const errs = [...A.errors, ...B.errors, ...C.errors].filter((e) => !/409|422|Failed to load resource/.test(e));
  ok('B3', 'no unexpected page/console errors', errs.length === 0, errs);
  ok('B3', 'no alert() executed (XSS trap)', [...A.dialogs, ...B.dialogs, ...C.dialogs].length === 0);
  for (const x of [A, B, C]) await x.context.close();
});

/* ------------------------------------------------------------------ B4 assembly 251 + full list */
await caso('B4-assembly', async () => {
  const { context, page, api, errors, dialogs } = await ctx();
  await page.goto(`${URL_BASE}/`);
  await signIn(page, 'A');
  const total = (await apiJson(page, '/api/inventario/terrenos?limit=1')).body.total;
  api.length = 0;
  let t0 = Date.now();
  await page.goto(`${URL_BASE}/#/inventario`);
  await page.reload();
  await waitCount(page, total);
  perf.full_list_assembled_ms = Date.now() - t0;
  const lists = api.filter((a) => a.m === 'GET' && a.p === '/api/inventario/terrenos');
  const startIdx = lists.map((a) => /cursor=/.test(a.q)).lastIndexOf(false);
  const pages = lists.length - startIdx;
  rec('VIEW-03', 'list requests during load (incl. superseded)', 'INFO', lists.map((a) => a.q));
  ok('VIEW-03', `full inventory (${total}) assembled before count; ${pages} page requests`, pages === Math.ceil(total / 250), pages);
  await page.getByRole('button', { name: 'Tabla' }).click();
  ok('VIEW-03', 'full table rows == API total', (await page.locator('.table tbody tr').count()) === total);
  api.length = 0;
  t0 = Date.now();
  const buscar = page.getByLabel('Buscar').first();
  await buscar.fill('Lote Paginación');
  await waitCount(page, 251);
  perf.filter_251_ms = Date.now() - t0;
  const q = api.filter((a) => a.m === 'GET' && a.p === '/api/inventario/terrenos');
  const last = q.slice(-2);
  ok('VIEW-03', '251 matching: assembled from 2 pages (250 + 1)', last.length === 2 && last.every((a) => /limit=250/.test(a.q)), q.map((a) => a.q));
  const rows = await page.locator('.table tbody tr').allInnerTexts();
  const names = rows.map((t) => (t.match(/Lote Paginación P\d{3}/) || [''])[0]);
  const uniq = new Set(names);
  ok('VIEW-03', 'table holds exactly P001..P251 once each', rows.length === 251 && uniq.size === 251 && !uniq.has(''),
    { rows: rows.length, unique: uniq.size });
  await shot(page, 'assembly-251-table-1440');
  await page.getByRole('button', { name: 'Mapa' }).click();
  await page.waitForTimeout(800);
  const legend = await page.locator('.legend-count').first().innerText();
  const marks = await page.evaluate(() => Math.max(0, ...(window.__lgs || []).map((g) =>
    g.getLayers().filter((l) => l instanceof window.L.CircleMarker).length)));
  ok('VIEW-03', 'map/legend/count agree for the 251 query', legend === '251 terrenos' && marks === 251, { legend, marks });
  await shot(page, 'assembly-251-map-1440');
  await buscar.fill('');
  await waitCount(page, total);
  ok('VIEW-01', 'clearing search restores full count', true);
  ok('B4', 'no page/console errors / alerts', errors.length === 0 && dialogs.length === 0, { errors, dialogs });
  await context.close();
});

/* ------------------------------------------------------------------ B5 logout + Back + late response */
await caso('B5-logout-leak', async () => {
  const { context, page, errors } = await ctx();
  await page.goto(`${URL_BASE}/`);
  await signIn(page, 'A');
  await page.goto(`${URL_BASE}/#/inventario/${SEED.ids.M002}`);
  await page.locator('.detail').getByText(/SNTL-CONTACT-M002/).waitFor();
  // Slow every private detail/list response by 3 s, start a private navigation, then log out mid-flight.
  let late = 0;
  // Fetch while the session is still valid, then hold the DATA response 3 s and deliver it after logout.
  let lateBodies = 0;
  await page.route(/\/api\/inventario\//, async (route) => {
    const resp = await route.fetch().catch(() => null);
    const body = resp ? await resp.text() : '';
    if (resp && resp.status() === 200 && /SNTL-/.test(body)) lateBodies += 1;
    await new Promise((r) => setTimeout(r, 3000));
    late += 1;
    await (resp ? route.fulfill({ response: resp }) : route.abort()).catch(() => {});
  });
  await page.evaluate((id) => { location.hash = `#/inventario/${id}`; }, SEED.ids.M003);
  await page.waitForTimeout(300);
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await page.waitForURL(/#\/catalogo$/);
  await page.waitForTimeout(4500);
  let hits = await sentinelHits(page);
  ok('ID-02', `after logout with ${late} late response(s), ${lateBodies} carrying private data: no sentinel in DOM/inputs/storage/URL`,
    hits.length === 0 && lateBodies > 0, { hits, lateBodies });
  ok('ID-02', 'after logout no team display name in DOM', !(await snapshot(page)).html.includes(USERS.A.display_name));
  const r = await page.request.get(`${URL_BASE}/api/inventario/terrenos/${SEED.ids.M002}`);
  ok('ID-02', 'browser cookie no longer authorizes private API (server revoked)', r.status() === 401, r.status());
  await page.unroute(/\/api\/inventario\//);
  for (let i = 0; i < 3; i += 1) {
    await page.goBack().catch(() => {});
    await page.waitForTimeout(700);
    if (!page.url().startsWith(URL_BASE)) { rec('ID-02', `Back #${i + 1} left the app (${page.url()})`, 'INFO'); break; }
    hits = await sentinelHits(page);
    ok('ID-02', `Back #${i + 1} (${new URL(page.url()).hash}): no private content resurrected`, hits.length === 0, hits);
  }
  await page.goto(`${URL_BASE}/#/inventario/${SEED.ids.M002}`);
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  await page.waitForTimeout(1000);
  ok('ID-02', 'revisiting the private URL after logout: sign-in only, no private content',
    (await sentinelHits(page)).length === 0, await sentinelHits(page));
  await shot(page, 'logout-back-1440');
  ok('B5', 'no page errors', errors.filter((e) => e.startsWith('pageerror')).length === 0, errors);
  await context.close();
});

/* ------------------------------------------------------------------ B6 phone drawer + editor, all widths */
await caso('B6-phone-widths', async () => {
  const { context, page, errors } = await ctx({ w: 390, h: 844 });
  await page.goto(`${URL_BASE}/`);
  await signIn(page, 'B');
  await page.locator('.toolbar-estado', { hasText: /terrenos/ }).waitFor();
  for (const [w, h] of [[390, 844], [375, 812]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`${URL_BASE}/#/inventario`);
    await page.locator('.toolbar-estado', { hasText: /terrenos/ }).waitFor();
    const btn = page.locator('#filtros-btn');
    ok('VIEW-02', `${w}: Filtros button visible`, await btn.isVisible());
    await btn.click();
    const drawer = page.getByRole('dialog', { name: 'Filtros' });
    await drawer.waitFor();
    await drawer.getByLabel('Buscar').fill('Lote Paginación P00');
    await waitCount(page, 9);
    await shot(page, `phone-drawer-${w}x${h}`);
    await drawer.getByRole('button', { name: 'Ver resultados' }).click();
    await page.waitForFunction(() => document.activeElement?.id === 'filtros-btn');
    ok('VIEW-02', `${w}: drawer filters on server (9 results) and returns focus to trigger`, true);
    await btn.click();
    ok('VIEW-02', `${w}: filter state kept when drawer reopens`, (await drawer.getByLabel('Buscar').inputValue()) === 'Lote Paginación P00');
    await drawer.getByLabel('Buscar').fill('');
    await page.keyboard.press('Escape');
    await waitCount(page, (await apiJson(page, '/api/inventario/terrenos?limit=1')).body.total);
    ok('VIEW-02', `${w}: Escape closes drawer; cleared search restores full list`, !(await drawer.isVisible()));
    await page.getByRole('button', { name: 'Tabla' }).click();
    await page.locator('.table tbody tr').first().click();
    await page.locator('.detail').first().waitFor();
    ok('VIEW-02', `${w}: phone user can select a result and see its detail`, await page.locator('.detail').first().isVisible());
    await page.goto(`${URL_BASE}/#/inventario/${SEED.ids.M004}/editar`);
    await page.getByLabel('Dirección').fill(`Calle teléfono ${w}`);
    const save = page.getByRole('button', { name: 'Guardar borrador' });
    await save.scrollIntoViewIfNeeded();
    const box = await save.boundingBox();
    ok('VIEW-02', `${w}: Guardar borrador reachable inside viewport`, box && box.x >= 0 && box.x + box.width <= w, box);
    ok('VIEW-02', `${w}: editor no horizontal overflow`, (await overflow(page)) <= w, await overflow(page));
    await shot(page, `phone-editor-${w}x${h}`);
    await save.click();
    await page.getByText(/Borrador guardado · versión/).waitFor();
    ok('VIEW-02', `${w}: save works from phone editor`, true);
  }
  for (const [w, h] of SIZES) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`${URL_BASE}/#/inventario`);
    await page.locator('.toolbar-estado', { hasText: /terrenos/ }).waitFor();
    await page.waitForTimeout(300);
    await shot(page, `inventory-${w}x${h}`);
    ok('VIEW-01', `inventory ${w}x${h}: no horizontal overflow`, (await overflow(page)) <= w, await overflow(page));
    await page.goto(`${URL_BASE}/#/inventario/${SEED.ids.M005}/editar`);
    await page.getByLabel('Nombre').waitFor();
    await shot(page, `editor-${w}x${h}`);
    ok('VIEW-02', `editor ${w}x${h}: no horizontal overflow; save visible`, (await overflow(page)) <= w
      && await page.getByRole('button', { name: 'Guardar borrador' }).isVisible(), await overflow(page));
    await page.getByRole('link', { name: 'Inventario' }).first().click().catch(() => {});
  }
  for (const [w, wantDrawer] of [[959, true], [961, false]]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto(`${URL_BASE}/#/inventario`);
    await page.locator('.toolbar-estado', { hasText: /terrenos/ }).waitFor();
    const drawerBtn = await page.locator('#filtros-btn').isVisible();
    const rail = await page.getByLabel('Buscar').first().isVisible();
    ok('VIEW-01', `${w}px: ${wantDrawer ? 'Filtros drawer button, rail hidden' : 'rail visible, no drawer button'}`,
      wantDrawer ? (drawerBtn && !rail) : (!drawerBtn && rail), { drawerBtn, rail });
  }
  ok('B6', 'no page errors', errors.filter((e) => e.startsWith('pageerror')).length === 0, errors);
  await context.close();
});

/* ------------------------------------------------------------------ B7 keyboard-only journey */
async function tabTo(page, pred, label, max = 120) {
  for (let i = 0; i < max; i += 1) {
    await page.keyboard.press('Tab');
    const f = await page.evaluate(() => {
      const e = document.activeElement;
      const t = (x) => (x || '').replace(/\s+/g, ' ').trim();
      return { tag: e?.tagName, id: e?.id, name: t(e?.getAttribute('aria-label') || e?.textContent).slice(0, 60),
        label: t(e?.labels?.[0]?.textContent) };
    });
    if (pred(f)) return f;
  }
  throw new Error(`keyboard could not reach ${label}`);
}
await caso('B7-keyboard', async () => {
  const { context, page, errors } = await ctx();
  await page.goto(`${URL_BASE}/`);
  await page.getByText('Todavía no hay terrenos publicados').waitFor();
  await tabTo(page, (f) => f.name === 'Iniciar sesión', 'Iniciar sesión');
  await page.keyboard.press('Enter');
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  const first = await page.evaluate(() => document.activeElement?.labels?.[0]?.textContent?.trim());
  if (first !== 'Usuario') await tabTo(page, (f) => f.label === 'Usuario', 'Usuario');
  await page.keyboard.type(USERS.C.username);
  await page.keyboard.press('Tab');
  await page.keyboard.type(USERS.C.password);
  await page.keyboard.press('Enter');
  await page.locator('.session-user').waitFor();
  ok('VIEW-02', 'keyboard: sign in (Tab/Enter only)', true);
  await page.goto(`${URL_BASE}/#/inventario/${SEED.ids.M006}`);   // address-bar navigation
  await page.locator('.detail').first().waitFor();
  await tabTo(page, (f) => f.name === 'Editar', 'Editar');
  await page.keyboard.press('Enter');
  await page.getByLabel('Dirección').waitFor();
  await tabTo(page, (f) => f.label === 'Dirección', 'Dirección');
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type('Dirección por teclado 1');
  await tabTo(page, (f) => f.name === 'Guardar borrador', 'Guardar borrador');
  await page.keyboard.press('Enter');
  await page.getByText(/Borrador guardado · versión/).waitFor();
  const d = (await apiJson(page, `/api/inventario/terrenos/${SEED.ids.M006}`)).body.terreno;
  ok('VIEW-02', 'keyboard: edit + save persisted', d.draft.direccion === 'Dirección por teclado 1', d.draft.direccion);
  await tabTo(page, (f) => f.name === 'Historial', 'Historial');
  await page.keyboard.press('Enter');
  await page.getByRole('dialog', { name: 'Historial' }).waitFor();
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  const back = await page.evaluate(() => { const e = document.activeElement;
    return { tag: e?.tagName, id: e?.id, cls: e?.className, text: (e?.textContent || '').trim().slice(0, 40) }; });
  ok('VIEW-02', 'keyboard: Escape closes Historial', !(await page.getByRole('dialog', { name: 'Historial' }).isVisible().catch(() => false)));
  rec('VIEW-02', 'keyboard: focus returns to the Historial trigger after Escape',
    back.tag === 'BUTTON' && back.text === 'Historial' ? 'PASS' : 'WARN', back);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${URL_BASE}/#/inventario`);
  await page.locator('.toolbar-estado', { hasText: /terrenos/ }).waitFor();
  await tabTo(page, (f) => f.id === 'filtros-btn', 'Filtros');
  await page.keyboard.press('Enter');
  await page.getByRole('dialog', { name: 'Filtros' }).waitFor();
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.activeElement?.id === 'filtros-btn');
  ok('VIEW-02', 'keyboard: open/close Filtros drawer, focus returns', true);
  await tabTo(page, (f) => f.name === 'Cerrar sesión', 'Cerrar sesión');
  await page.keyboard.press('Enter');
  await page.waitForURL(/#\/catalogo$/);
  ok('VIEW-02', 'keyboard: sign out', true);
  ok('B7', 'no page errors', errors.filter((e) => e.startsWith('pageerror')).length === 0, errors);
  await context.close();
});

/* ------------------------------------------------------------------ B8 legacy reachable when signed in */
await caso('B8-legacy', async () => {
  const { context, page, errors } = await ctx();
  const baseL1 = 'Base L1 ' + LEGACY.sentinels.find((s) => s.startsWith('SNTL-BASE-L1-'));
  const mapS1 = 'Mapa S1 ' + LEGACY.sentinels.find((s) => s.startsWith('SNTL-MAP-S1-'));
  await page.goto(`${URL_BASE}/#/bases`);
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  ok('ID-02', 'anonymous #/bases: sign-in only, no legacy names', (await sentinelHits(page)).length === 0, await sentinelHits(page));
  await signIn(page, 'A', { open: false });
  await page.getByRole('link', { name: 'Bases' }).click();
  await page.getByText(baseL1).first().waitFor();
  ok('REG-01', 'signed in: legacy base gallery lists the v7 bases', true);
  await page.getByText(baseL1).first().click();
  await page.waitForURL(/#\/mapa$/);
  await page.locator('.toolbar-estado, .legend-count').first().waitFor();
  await shot(page, 'legacy-base-1440');
  ok('REG-01', 'signed in: legacy base opens on the map', true);
  await page.getByRole('link', { name: 'Mapas guardados' }).click();
  await page.getByText(mapS1).first().waitFor();
  await page.getByText(mapS1).first().click();
  await page.waitForURL(/#\/mapa$/);
  await shot(page, 'legacy-map-1440');
  ok('REG-01', 'signed in: saved map (frozen v7 snapshot) reopens', true);
  ok('B8', 'no page errors', errors.filter((e) => e.startsWith('pageerror')).length === 0, errors);
  await context.close();
});

const browserVersion = browser.version();
await browser.close();
const counts = results.reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {});
writeFileSync(join(OUT, 'browser_results.json'), JSON.stringify({
  target: URL_BASE, browser: `chromium ${browserVersion}`, playwright: '1.63.0', node: process.version,
  seed_total: SEED.total, perf, counts, results }, null, 1));
console.log(JSON.stringify(counts), JSON.stringify(perf));
process.exit(counts.FAIL ? 1 : 0);

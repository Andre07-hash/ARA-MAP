/* INTEGRATED checks for correction 1 of packet 2A: what happens to private
 * table and dialog state when the identity behind the window changes
 * (R2-A2), and to an open editor when another cell's save comes back (R2-A4).
 * The real local server, real sessions, a real Chrome; fictional accounts.
 *
 *   python3 tests/e2e/tabla_servidor.py --puerto 8435 --registros 4200 > /tmp/srv.log &
 *   ARA_URL=http://localhost:8435 ARA_BD=$(sed -n 's/^BD //p' /tmp/srv.log) \
 *     node tests/e2e/tabla-identidad.mjs [carpeta-de-capturas]
 *
 * ARA_BD is the disposable SQLite file, for the one case that changes a role
 * with scripts/cuentas.py. A fresh server each run.
 */

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8435').replace(/\/$/, '');
const BD = process.env.ARA_BD;
const SHOTS = process.argv[2] ?? null;
if (!/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');
if (!BD || !/desechable\.db$/.test(BD)) throw new Error('ARA_BD debe ser la base desechable de tabla_servidor.py.');
const RAIZ = fileURLToPath(new URL('../../', import.meta.url));
const CLAVE = /TEST_PASSWORD = "([^"]+)"/.exec(readFileSync(join(RAIZ, 'tests/support.py'), 'utf8'))[1];
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const resultados = [];
let fallos = 0;
const SOLO = process.env.E2E_SOLO ?? '';
async function caso(nombre, fn) {
  if (!nombre.includes(SOLO)) return;
  try { await fn(); resultados.push(`ok   ${nombre}`); }
  catch (error) { fallos += 1; resultados.push(`FAIL ${nombre}\n     ${String(error.stack ?? error).split('\n').slice(0, 7).join('\n     ')}`); }
}

/* A browser profile: one cookie jar. `entrarPorApi` signs in through that jar
 * without touching the page, as another tab of the same browser would. */
async function perfil() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-MX' });
  context.setDefaultTimeout(Number(process.env.E2E_TIMEOUT ?? 10000));
  const page = await context.newPage();
  const parches = [];
  const errores = [];
  page.on('request', (r) => { if (r.method() !== 'GET' && /\/api\/(inventario|maestra)\//.test(r.url())) parches.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  page.on('pageerror', (e) => errores.push(e.message));
  const entrarPorApi = async (usuario) => assert.equal(
    (await context.request.post(`${URL_BASE}/api/login`, { data: { username: usuario, password: CLAVE } })).status(), 200);
  const salirPorApi = () => context.request.post(`${URL_BASE}/api/logout`);
  const api = async (metodo, ruta, data, headers) => {
    const r = await context.request.fetch(`${URL_BASE}${ruta}`, { method: metodo, data, headers });
    return { status: r.status(), body: await r.json().catch(() => null) };
  };
  return { context, page, parches, errores, entrarPorApi, salirPorApi, api };
}

const foto = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); };
const filas = (page) => page.locator('tr.tabla-fila');
const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const cargada = (page) => page.waitForFunction(() => document.querySelector('tr.tabla-fila')
  && !document.querySelector('.tabla-lienzo[aria-busy]'));
const revalidar = (page) => page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
/** Poll until the app itself says who is signed in (a sync check each time). */
async function hastaSesion(page, nombre) {
  for (let i = 0; i < 100; i += 1) {
    if ((await sesionDe(page)) === nombre) return;
    await page.waitForTimeout(50);
  }
  assert.equal(await sesionDe(page), nombre);
}
const sesionDe = (page) => page.evaluate(async () => (await import('/lib/store.js')).getState().sesion?.display_name ?? null);

/** Everything a person or a script could read off the page: text, field values, dialogs, rows. */
async function loQueQueda(page, marcas) {
  return page.evaluate((ms) => {
    const campos = [...document.querySelectorAll('input, textarea, select')].map((c) => c.value).join('\n');
    const todo = `${document.documentElement.outerHTML}\n${document.body.innerText}\n${campos}`;
    return {
      marcas: ms.filter((m) => todo.includes(m)),
      donde: ms.filter((m) => todo.includes(m)).map((m) => todo.slice(Math.max(0, todo.indexOf(m) - 160), todo.indexOf(m) + 60)),
      filas: document.querySelectorAll('tr[data-id]').length,
      dialogosPrivados: [...document.querySelectorAll('dialog')].filter((d) => !d.querySelector('#login-usuario')).length,
      editores: document.querySelectorAll('.tabla-editor').length,
      tabla: document.querySelectorAll('.tabla-pantalla').length,
    };
  }, marcas);
}
const LIMPIO = { marcas: [], filas: 0, dialogosPrivados: 0, editores: 0 };
const sinTabla = (q) => ({ marcas: q.marcas, filas: q.filas, dialogosPrivados: q.dialogosPrivados, editores: q.editores });

async function entrarEnDialogo(page, usuario) {
  const dialogo = page.getByRole('dialog', { name: 'Iniciar sesión' });
  await dialogo.waitFor();
  await dialogo.getByLabel('Usuario').fill(usuario);
  await dialogo.getByLabel('Contraseña').fill(CLAVE);
  await dialogo.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user', { hasText: new RegExp(usuario, 'i') }).waitFor();
}

/** Hold the next PATCH of a terrain. `antes: true` holds it before it reaches
 * the server; otherwise the server answers and only the answer is held. */
async function retener(page, { antes = false } = {}) {
  let soltar; let llego;
  const espera = new Promise((r) => { soltar = r; });
  const enviada = new Promise((r) => { llego = r; });
  let usada = false;
  await page.route('**/api/inventario/terrenos/*', async (route) => {
    if (route.request().method() !== 'PATCH' || usada) return route.continue();
    usada = true;
    if (antes) { llego(); await espera; return route.continue().catch(() => {}); }
    const respuesta = await route.fetch();
    llego();
    await espera;
    return route.fulfill({ response: respuesta }).catch(() => {});
  });
  return { enviada, soltar: async () => { soltar(); } };
}

/* ------------------------------------------------------------- fixture */

const admin = await perfil();
await admin.entrarPorApi('ada');
const BASE = (await admin.api('GET', '/api/maestra/bases')).body.bases.find((b) => b.nombre === 'Base Grande');
const OTRA = (await admin.api('GET', '/api/maestra/bases')).body.bases.find((b) => b.nombre === 'Base 01');
const COLUMNA = (await admin.api('POST', `/api/maestra/bases/${BASE.id}/columnas`,
  { nombre: 'Nota privada', tipo: 'texto' }, { 'Idempotency-Key': 'clave-identidad-0001' })).body.columna;
const terrenos = (await admin.api('GET', `/api/maestra/bases/${BASE.id}/terrenos?limit=50`)).body.terrenos;
const version = async (id) => (await admin.api('GET', `/api/inventario/terrenos/${id}`)).body.terreno;
const escribirPorApi = async (id, cuerpo) => {
  const r = await admin.api('PATCH', `/api/inventario/terrenos/${id}`, { expected_version: (await version(id)).version, ...cuerpo });
  assert.equal(r.status, 200, JSON.stringify(r.body));
};
const acceso = async (base, logins) => {
  const actual = (await admin.api('GET', `/api/maestra/bases/${base}/acceso`)).body;
  const todos = (await admin.api('GET', '/api/maestra/operadores')).body.usuarios;
  const r = await admin.api('PUT', `/api/maestra/bases/${base}/acceso`,
    { expected_version: actual.base.version, usuarios: todos.filter((u) => logins.includes(u.login)).map((u) => u.id) });
  assert.equal(r.status, 200, JSON.stringify(r.body));
};
const CINCO = ['olga', 'omar', 'oscar', 'olivia', 'oriol'];
let n = 0;
const fila = () => terrenos[n++].id;      // a row no earlier case touched
const GUARDADA = 'MARCA-GUARDADA-PRIVADA';
const SIN_GUARDAR = 'MARCA-SIN-GUARDAR';

async function olgaEnTabla() {
  const p = await perfil();
  await p.entrarPorApi('olga');
  await p.page.goto(`${URL_BASE}/#/tabla`);
  await cargada(p.page);
  return p;
}

/* ---------------------------------------------------------- R2-A2 cases */

await caso('expiry with unsaved cells clears everything; a queued save never runs; the same user signs in again', async () => {
  const id = fila();
  await escribirPorApi(id, { changes: { notas_internas: GUARDADA } });
  const p = await olgaEnTabla();
  const { page } = p;
  // One cell saving (its request held before the server), one queued behind it in the
  // same row, one invalid value waiting in the tray, one editor open with unsaved text.
  const paso = await retener(page, { antes: true });
  await celda(page, id, 'core:estado').dblclick();
  await page.locator('.tabla-editor').fill(`${SIN_GUARDAR}-1`);
  await page.keyboard.press('Enter');
  await paso.enviada;
  await celda(page, id, 'core:municipio').dblclick();
  await page.locator('.tabla-editor').fill(`${SIN_GUARDAR}-2`);
  await page.keyboard.press('Enter');                       // queued behind the held one
  await celda(page, id, 'core:asking_price').dblclick();
  await page.locator('.tabla-editor').fill(`${SIN_GUARDAR}-3`);
  await page.keyboard.press('Enter');                       // not a number: waits in the tray
  await celda(page, id, COLUMNA.id).dblclick();
  await page.locator('.tabla-editor').fill(`${SIN_GUARDAR}-4`);   // an open editor
  await foto(page, 'c1-01-antes-de-expirar');
  const antes = await version(id);

  await p.salirPorApi();                                    // the session ends at the server
  p.parches.length = 0;
  await paso.soltar();                                      // the held save now reaches it: 401
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  assert.equal(await sesionDe(page), null);
  const queda = await loQueQueda(page, [GUARDADA, SIN_GUARDAR, 'Nota privada', 'Base Grande']);
  assert.deepEqual(sinTabla(queda), LIMPIO);
  assert.equal(queda.tabla, 0);
  await page.getByText('Lo que estaba sin guardar se descartó.').first().waitFor();   // said, not quoted
  await foto(page, 'c1-02-sesion-expirada-sin-datos');

  // The same person signs in again. Nothing of the old queue is sent under the new session.
  await entrarEnDialogo(page, 'olga');
  await cargada(page);
  await page.waitForTimeout(800);
  // The held request had already left the page (it was refused with 401); the one
  // queued behind it, the invalid one and the open editor never leave at all.
  assert.deepEqual(p.parches.filter((l) => l.startsWith('PATCH')), [], 'nothing of the old queue was sent');
  const despues = await version(id);
  assert.deepEqual([despues.version, despues.draft.estado, despues.draft.municipio], [antes.version, antes.draft.estado, antes.draft.municipio]);
  assert.equal(await page.locator('.tabla-bandeja').isVisible(), false);
  assert.ok(!(await loQueQueda(page, [SIN_GUARDAR])).marcas.length, 'the new session starts without the old unsaved text');
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

await caso('a different account signs in over an expired session: it sees and sends nothing of the previous one', async () => {
  const id = fila();
  await escribirPorApi(id, { changes: { notas_internas: GUARDADA }, custom: { [COLUMNA.id]: GUARDADA } });
  const p = await olgaEnTabla();
  const { page } = p;
  await celda(page, id, 'core:notas_internas').dblclick();
  await page.locator('.tabla-editor').fill(SIN_GUARDAR);
  await p.salirPorApi();
  p.parches.length = 0;
  await page.keyboard.press('Enter');                       // the save meets a 401
  await page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  assert.deepEqual(sinTabla(await loQueQueda(page, [GUARDADA, SIN_GUARDAR, 'Nota privada'])), LIMPIO);

  await entrarEnDialogo(page, 'otto');                       // zero grants
  await page.getByRole('heading', { name: 'Todavía no tienes una base de trabajo' }).waitFor();
  await page.waitForTimeout(800);
  assert.deepEqual(sinTabla(await loQueQueda(page, [GUARDADA, SIN_GUARDAR, 'Nota privada', 'Base Grande', 'Olga'])), LIMPIO);
  assert.equal(p.parches.filter((l) => l.startsWith('PATCH')).length, 1, 'nothing was sent as Otto');
  assert.equal((await version(id)).draft.notas_internas, GUARDADA, 'and the old unsaved text was not saved by anyone');
  assert.equal((await p.api('GET', `/api/inventario/terrenos/${id}`)).status, 404);   // the backend already said no
  await foto(page, 'c1-03-otra-cuenta-tras-expirar');
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

for (const [nombre, abrir] of [
  ['a terrain detail', async (page, id) => {
    await page.locator(`tr[data-id="${id}"] .tabla-abrir`).click();
    await page.locator('dialog[open] .detalle-datos', { hasText: GUARDADA }).waitFor();
  }],
  ['a terrain history', async (page, id) => {
    await page.locator(`tr[data-id="${id}"] .tabla-abrir`).click();
    await page.getByRole('button', { name: 'Historial' }).click();
    await page.locator('dialog[open] .historial-evento', { hasText: GUARDADA }).first().waitFor();
  }],
  ['the columns of the base', async (page) => {
    await page.getByRole('button', { name: 'Columnas' }).click();
    await page.getByLabel('Nombre de la columna Nota privada').waitFor();
  }],
  ['an unsaved editor and a clean table', async (page, id) => {
    await celda(page, id, COLUMNA.id).dblclick();
    await page.locator('.tabla-editor').fill(SIN_GUARDAR);
  }],
]) {
  await caso(`revalidation finds another account while ${nombre} is open: all of it is removed`, async () => {
    const id = fila();
    await escribirPorApi(id, { changes: { notas_internas: GUARDADA }, custom: { [COLUMNA.id]: GUARDADA } });
    const p = await olgaEnTabla();
    const { page } = p;
    // A list request is still in flight when the identity changes; its answer comes later.
    await abrir(page, id);
    await page.route('**/api/maestra/bases/*/terrenos?*', async (route) => {
      await new Promise((r) => setTimeout(r, 1200));
      await route.continue().catch(() => {});
    });
    p.parches.length = 0;
    await p.entrarPorApi('otto');                             // another tab of this browser signs in
    await revalidar(page);
    await hastaSesion(page, 'Otto Ficticia');
    await page.getByRole('heading', { name: 'Todavía no tienes una base de trabajo' }).waitFor();
    await page.waitForTimeout(1600);                          // past the delayed answer
    assert.deepEqual(sinTabla(await loQueQueda(page, [GUARDADA, SIN_GUARDAR, 'Nota privada', 'Base Grande', 'Olga'])), LIMPIO);
    assert.deepEqual(p.parches, [], 'nothing queued by the old identity was sent as the new one');
    assert.deepEqual(p.errores, []);
    if (nombre === 'a terrain detail') await foto(page, 'c1-04-otra-cuenta-con-detalle-abierto');
    await p.context.close();
  });
}

await caso('administrator dialogs (bases, grants, transfer preview) do not outlive the administrator', async () => {
  const id = fila();
  for (const abrir of [
    async (page) => {
      await page.getByRole('button', { name: 'Bases y accesos' }).click();
      const bases = page.getByRole('dialog', { name: 'Bases de trabajo y accesos' });
      await bases.locator('li', { has: page.getByLabel('Nombre de la base Base Grande') }).getByRole('button', { name: 'Accesos…' }).click();
      await page.getByRole('dialog', { name: 'Accesos · Base Grande' }).getByLabel(/^Olivia Ficticia/).waitFor();
    },
    async (page) => {
      await page.locator(`tr[data-id="${id}"] .tabla-abrir`).click();
      await page.getByRole('button', { name: 'Transferir a otra base…' }).click();
      await page.getByLabel('Base de destino').selectOption(OTRA.id);
      await page.getByRole('heading', { name: 'Quién podrá abrirlo' }).waitFor();
    },
  ]) {
    const p = await perfil();
    await p.entrarPorApi('ada');
    await p.page.goto(`${URL_BASE}/#/tabla/${BASE.id}`);
    await cargada(p.page);
    await abrir(p.page);
    await p.entrarPorApi('olga');                              // an operator now owns this cookie jar
    await revalidar(p.page);
    await hastaSesion(p.page, 'Olga Ficticia');
    await p.page.waitForFunction(() => document.querySelectorAll('#tabla-vista option').length === 1);
    await cargada(p.page);
    const queda = await loQueQueda(p.page, ['Olivia Ficticia', 'Oriol Ficticia', 'Base 01', 'Bases y accesos', 'Tabla maestra']);
    assert.deepEqual([queda.marcas, queda.dialogosPrivados], [[], 0], JSON.stringify({ ...queda, donde: queda.donde.map((d) => d.slice(100, 220)) }));
    assert.deepEqual(await p.page.locator('nav .nav-item').allInnerTexts(), ['Tabla', 'Catálogo público']);
    assert.deepEqual(await p.page.locator('#tabla-vista option').allInnerTexts(), ['Base Grande']);
    assert.deepEqual(p.errores, []);
    await p.context.close();
  }
});

await caso('a role change ends the session; signing in again shows the new role and nothing of the old screen', async () => {
  const p = await perfil();
  await p.entrarPorApi('alan');
  await p.page.goto(`${URL_BASE}/#/tabla/maestra`);
  await cargada(p.page);
  await p.page.getByRole('button', { name: 'Bases y accesos' }).click();
  await p.page.getByLabel('Nombre de la base Base 01').waitFor();
  execFileSync('/usr/bin/python3', [join(RAIZ, 'scripts/cuentas.py'), '--sqlite', BD, 'rol', 'alan', 'operador'], { stdio: 'pipe' });
  await revalidar(p.page);
  await p.page.getByRole('dialog', { name: 'Iniciar sesión' }).waitFor();
  const queda = await loQueQueda(p.page, ['Base 01', 'Base Grande', 'Lote ']);
  assert.deepEqual(sinTabla(queda), LIMPIO);
  await entrarEnDialogo(p.page, 'alan');
  await p.page.getByRole('heading', { name: 'Todavía no tienes una base de trabajo' }).waitFor();
  assert.deepEqual(await p.page.locator('nav .nav-item').allInnerTexts(), ['Tabla', 'Catálogo público']);
  assert.equal(await p.page.getByRole('button', { name: 'Bases y accesos' }).count(), 0);
  assert.equal((await p.api('GET', '/api/inventario/terrenos?limit=1')).status, 403);
  await foto(p.page, 'c1-05-cambio-de-rol');
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

await caso('the same user signs in again under changed grants: the old base and its queued edit are gone', async () => {
  const id = fila();
  const p = await olgaEnTabla();
  const { page } = p;
  const paso = await retener(page, { antes: true });
  await celda(page, id, 'core:estado').dblclick();
  await page.locator('.tabla-editor').fill(`${SIN_GUARDAR}-1`);
  await page.keyboard.press('Enter');
  await paso.enviada;
  await celda(page, id, 'core:municipio').dblclick();
  await page.locator('.tabla-editor').fill(`${SIN_GUARDAR}-2`);
  await page.keyboard.press('Enter');
  const antes = await version(id);
  await p.salirPorApi();
  await acceso(BASE.id, CINCO.filter((u) => u !== 'olga'));   // she loses the base while signed out
  await acceso(OTRA.id, ['olga']);                            // and gains another
  try {
  p.parches.length = 0;
  await paso.soltar();
  await entrarEnDialogo(page, 'olga');
  await page.waitForFunction(() => document.querySelector('#tabla-vista')?.selectedOptions[0]?.textContent === 'Base 01');
  await cargada(page);
  await page.waitForTimeout(800);
  assert.deepEqual(await page.locator('#tabla-vista option').allInnerTexts(), ['Base 01']);
  assert.equal(await page.locator(`tr[data-id="${id}"]`).count(), 0);
  assert.deepEqual(p.parches.filter((l) => l.startsWith('PATCH')), [], 'the edit queued before the expiry never left');
  const despues = await version(id);
  assert.deepEqual([despues.version, despues.draft.municipio], [antes.version, antes.draft.municipio]);
  assert.ok(!(await loQueQueda(page, [SIN_GUARDAR, 'Base Grande', 'Nota privada'])).marcas.length);
  } finally {
    await acceso(BASE.id, CINCO);
    await acceso(OTRA.id, []);
  }
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

await caso('a terrain transferred away while its detail is open: the save is refused and the dialog goes with the row', async () => {
  const id = fila();
  const SOLO_ESTA = 'MARCA-DEL-TERRENO-TRASLADADO';      // other rows of her page carry the shared marker
  await escribirPorApi(id, { changes: { notas_internas: SOLO_ESTA } });
  const p = await olgaEnTabla();
  const { page } = p;
  const paso = await retener(page, { antes: true });
  await celda(page, id, 'core:estado').dblclick();
  await page.locator('.tabla-editor').fill('Nayarit');
  await page.keyboard.press('Enter');
  await paso.enviada;
  await page.locator(`tr[data-id="${id}"] .tabla-abrir`).click();
  await page.locator('dialog[open] .detalle-datos', { hasText: SOLO_ESTA }).waitFor();
  const t = await version(id);
  assert.equal((await admin.api('POST', `/api/inventario/terrenos/${id}/transferir`, { expected_version: t.version, base_id: OTRA.id })).status, 200);
  await paso.soltar();                                       // her save now reaches the server: 404
  await page.locator(`tr[data-id="${id}"]`).waitFor({ state: 'detached' });
  const queda = await loQueQueda(page, [SOLO_ESTA]);
  assert.deepEqual([queda.marcas, queda.dialogosPrivados], [[], 0]);
  assert.ok(queda.filas > 0, 'the rest of her base is still there');
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

await caso('logout with a save in flight and a dialog open leaves nothing, and the late answer paints nothing', async () => {
  const id = fila();
  await escribirPorApi(id, { changes: { notas_internas: GUARDADA } });
  const p = await olgaEnTabla();
  const { page } = p;
  const paso = await retener(page);                          // the server answers; the answer is held
  await celda(page, id, 'core:estado').dblclick();
  await page.locator('.tabla-editor').fill('Durango');
  await page.keyboard.press('Enter');
  await paso.enviada;
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await page.getByRole('dialog', { name: '¿Descartar cambios?' }).getByRole('button', { name: 'Descartar cambios' }).click();
  await page.getByRole('button', { name: 'Iniciar sesión' }).waitFor();
  await paso.soltar();
  await page.waitForTimeout(600);
  assert.deepEqual(sinTabla(await loQueQueda(page, [GUARDADA, 'Durango', 'Base Grande'])), LIMPIO);
  assert.equal(await page.locator('.toast-error').count(), 0, 'no error about a request nobody is waiting for');
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

/* ---------------------------------------------------------- R2-A4 cases */

const editorActual = (page) => page.evaluate(() => {
  const a = document.activeElement;
  const td = a?.closest?.('td[data-col]');
  return {
    editores: document.querySelectorAll('.tabla-editor').length,
    enfocado: a?.classList?.contains('tabla-editor') ? td?.dataset.col : a?.tagName,
    valor: a?.value ?? null,
    seleccion: a?.classList?.contains('tabla-editor') && a.selectionStart != null ? [a.selectionStart, a.selectionEnd] : null,
  };
});

for (const [tipo, segunda, etiqueta] of [['core', 'core:notas_internas', 'a core cell'], ['custom', COLUMNA.id, 'a custom cell']]) {
  await caso(`a successful save returns while ${etiqueta} is being edited: text, selection and focus stay; Enter then saves it`, async () => {
    const id = fila();
    const p = await olgaEnTabla();
    const { page } = p;
    const paso = await retener(page);
    await celda(page, id, 'core:terreno').dblclick();
    await page.locator('.tabla-editor').fill('Primer guardado');
    await page.keyboard.press('Enter');
    await paso.enviada;                                      // saved at the server; the answer is held
    await celda(page, id, segunda).dblclick();
    await page.locator('.tabla-editor').fill('Segundo sin guardar');
    await page.locator('.tabla-editor').evaluate((c) => c.setSelectionRange(3, 9));
    await paso.soltar();
    await page.locator(`tr[data-id="${id}"] td[data-col="core:terreno"]:not(.is-pendiente)`, { hasText: 'Primer guardado' }).waitFor();
    assert.deepEqual(await editorActual(page), { editores: 1, enfocado: segunda, valor: 'Segundo sin guardar', seleccion: [3, 9] });
    if (tipo === 'core') await foto(page, 'c1-06-editor-conservado');
    await page.keyboard.type('X');                           // typing goes on where the caret was
    assert.equal((await editorActual(page)).valor, 'SegXin guardar');   // the selection (3–9) was replaced
    await page.keyboard.press('Enter');
    await page.locator(`tr[data-id="${id}"] td[data-col="${segunda}"]:not(.is-pendiente):not(.is-editando)`).waitFor();
    const t = await version(id);
    assert.equal(t.draft.terreno, 'Primer guardado');
    assert.equal(tipo === 'core' ? t.draft.notas_internas : t.custom[COLUMNA.id], 'SegXin guardar');
    assert.equal(t.version, 3, 'two saves, each at the version the previous one returned');
    assert.equal(await page.evaluate(() => document.activeElement?.closest?.('td')?.dataset.col), segunda);
    assert.deepEqual(p.errores, []);
    await p.context.close();
  });
}

await caso('same, then Escape: the open editor is cancelled, nothing of it is saved, focus returns to its cell', async () => {
  const id = fila();
  const p = await olgaEnTabla();
  const { page } = p;
  const paso = await retener(page);
  await celda(page, id, 'core:terreno').dblclick();
  await page.locator('.tabla-editor').fill('Primer guardado');
  await page.keyboard.press('Enter');
  await paso.enviada;
  await celda(page, id, COLUMNA.id).dblclick();
  await page.locator('.tabla-editor').fill('No debe guardarse');
  await paso.soltar();
  await page.locator(`tr[data-id="${id}"] td[data-col="core:terreno"]:not(.is-pendiente)`, { hasText: 'Primer guardado' }).waitFor();
  assert.equal((await editorActual(page)).valor, 'No debe guardarse');
  p.parches.length = 0;
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  assert.equal(await page.locator('.tabla-editor').count(), 0);
  assert.equal(await page.evaluate(() => document.activeElement?.closest?.('td')?.dataset.col), COLUMNA.id);
  assert.deepEqual(p.parches, []);
  assert.deepEqual((await version(id)).custom, {});
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

await caso('a conflict returns while another cell is being edited: the editor stays, the conflict is listed, Enter saves at the current version', async () => {
  const id = fila();
  const p = await olgaEnTabla();
  const { page } = p;
  const paso = await retener(page, { antes: true });
  await celda(page, id, 'core:terreno').dblclick();
  await page.locator('.tabla-editor').fill('Nombre de Olga');
  await page.keyboard.press('Enter');
  await paso.enviada;
  await escribirPorApi(id, { changes: { terreno: 'Nombre de Ada' } });   // someone else gets there first
  await celda(page, id, COLUMNA.id).dblclick();
  await page.locator('.tabla-editor').fill('Nota durante el conflicto');
  await paso.soltar();                                                    // her stale save: 409
  await page.locator('.tabla-bandeja').getByText(/Otra persona guardó cambios/).waitFor();
  assert.deepEqual(await editorActual(page), { editores: 1, enfocado: COLUMNA.id, valor: 'Nota durante el conflicto',
    seleccion: [25, 25] });
  assert.match(await page.locator('.tabla-bandeja').innerText(), /Valor actual: «Nombre de Ada»[\s\S]*Tu valor: «Nombre de Olga»/);
  await foto(page, 'c1-07-conflicto-con-editor-abierto');
  await page.keyboard.press('Enter');
  await page.locator(`tr[data-id="${id}"] td[data-col="${COLUMNA.id}"]:not(.is-pendiente):not(.is-editando)`, { hasText: 'Nota durante' }).waitFor();
  const t = await version(id);
  assert.deepEqual([t.draft.terreno, t.custom[COLUMNA.id], t.version], ['Nombre de Ada', 'Nota durante el conflicto', 3]);
  assert.match(await page.locator('.tabla-bandeja').innerText(), /Tu valor: «Nombre de Olga»/, 'the conflict still waits for her');
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

await caso('the refreshed row changed the very cell being edited: Enter does not overwrite it unseen', async () => {
  const id = fila();
  const p = await olgaEnTabla();
  const { page } = p;
  const paso = await retener(page, { antes: true });
  await celda(page, id, 'core:terreno').dblclick();
  await page.locator('.tabla-editor').fill('Nombre de Olga');
  await page.keyboard.press('Enter');
  await paso.enviada;
  await escribirPorApi(id, { changes: { terreno: 'Nombre de Ada', notas_internas: 'Comentario de Ada' } });
  await celda(page, id, 'core:notas_internas').dblclick();                // she starts from the old, empty comment
  await page.locator('.tabla-editor').fill('Comentario de Olga');
  await paso.soltar();
  await page.locator('.tabla-bandeja').getByText(/Otra persona guardó cambios/).waitFor();
  p.parches.length = 0;
  await page.keyboard.press('Enter');
  await page.locator('.tabla-bandeja').getByText(/Valor actual: «Comentario de Ada»/).waitFor();
  assert.match(await page.locator('.tabla-bandeja').innerText(), /Tu valor: «Comentario de Olga»/);
  assert.deepEqual(p.parches, [], 'nothing was sent');
  assert.equal((await version(id)).draft.notas_internas, 'Comentario de Ada');
  // Choosing hers is explicit, and then it is saved.
  await page.locator('.tabla-pendiente', { hasText: 'Comentarios' }).getByRole('button', { name: 'Guardar el mío' }).click();
  await page.locator(`tr[data-id="${id}"] td[data-col="core:notas_internas"]:not(.is-pendiente):not(.is-conflicto)`,
    { hasText: 'Comentario de Olga' }).waitFor();
  assert.equal((await version(id)).draft.notas_internas, 'Comentario de Olga');
  assert.deepEqual(p.errores, []);
  await p.context.close();
});

await admin.context.close();
await browser.close();
console.log(resultados.join('\n'));
console.log(fallos ? `\n${fallos} con fallas.` : `\nTodo en orden: ${resultados.length} recorridos.`);
process.exit(fallos ? 1 : 0);

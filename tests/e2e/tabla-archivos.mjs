/* HOST checks of files, location and the page map preview (packet 3A): the
 * real local server with the attachment routes mounted and its disk store,
 * real sessions, a real Chrome.
 *
 * Team B's widgets (web/components/archivos/) and geometry loader
 * (web/lib/cargadorGeometrias.js) are NOT part of this file's subject. Two
 * situations are exercised:
 *   1. those modules absent  -> the table still works and says so;
 *   2. STAND-INS served in their place by the test (DOBLE_* below) -> the
 *      host's side of the seam: real summaries handed over, coalesced
 *      refresh, selected-boundary loading from the real server, teardown.
 * The stand-ins are test doubles, not Team B's code: they prove the host,
 * not the widgets. Uploads here are made by the test through the real API.
 *
 *   python3 tests/e2e/tabla_servidor.py --puerto 8435        # terminal 1 (fresh, disposable)
 *   ARA_URL=http://localhost:8435 node tabla-archivos.mjs [carpeta-de-capturas]
 */

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8435').replace(/\/$/, '');
const SHOTS = process.argv[2] ?? null;
if (!/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');
const RAIZ = new URL('../..', import.meta.url).pathname;
const CLAVE = /TEST_PASSWORD = "([^"]+)"/.exec(readFileSync(join(RAIZ, 'tests/support.py'), 'utf8'))[1];
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

// Fictional files, built by the project's own fixtures (base64 over stdout).
const [KMZ_B64, PDF_B64] = execFileSync('python3', ['-c',
  'import base64\nfrom tests.test_archivos_http import kmz, PDF\n' +
  'print(base64.b64encode(kmz("poligono_simple")).decode())\nprint(base64.b64encode(PDF).decode())'],
  { cwd: RAIZ, encoding: 'utf8' }).trim().split('\n');

const DOBLE_WIDGETS = `
export function crearWidgetsArchivos({ peticionPrivada }) {
  const d = window.__doble ??= { fabricas: 0, fabricasDestruidas: 0, montados: 0, destruidos: 0, cargas: 0, resets: 0 };
  d.fabricas += 1;
  d.conPuente = typeof peticionPrivada === 'function';
  const fabrica = (detalle) => ({ container, terrenoId, tipo, soloLectura, resumen, onCambio }) => {
    d.montados += 1;
    const pinta = (r, lectura) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'doble-archivo'; b.dataset.tipo = tipo; b.dataset.detalle = String(detalle);
      b.textContent = (r === undefined ? 'sin resumen'
        : tipo === 'pdf' ? 'pdf:' + r.pdf_total
        : 'kmz:' + (r.kmz?.geometria_activa_id ? 'activo' : r.kmz ? 'sin-activar' : 'no')) + (lectura ? ' (lectura)' : '');
      b.onclick = () => { onCambio({ terrenoId }); onCambio({ terrenoId }); onCambio({ terrenoId }); };
      container.replaceChildren(b);
    };
    pinta(resumen, soloLectura);
    return { update({ soloLectura: l, resumen: r }) { pinta(r, l); }, destroy() { d.destruidos += 1; container.replaceChildren(); } };
  };
  return { mount: fabrica(false), mountDetalle: fabrica(true), destroy() { d.fabricasDestruidas += 1; } };
}`;

const DOBLE_CARGADOR = `
export function crearCargadorGeometrias({ peticionPrivada }) {
  const d = window.__doble ??= { fabricas: 0, fabricasDestruidas: 0, montados: 0, destruidos: 0, cargas: 0, resets: 0 };
  return {
    async cargar({ geometria }, { signal } = {}) {
      d.pedidas = (d.pedidas ?? 0) + 1;
      if (window.__dobleFalla) throw Object.assign(new Error('fallo simulado'), { codigo: 'simulado' });
      if (window.__dobleEspera) await new Promise((r) => setTimeout(r, window.__dobleEspera));
      const m = await peticionPrivada('/api/archivos/geometrias/metadatos', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [geometria.id] }), signal });
      const meta = (await m.response.json()).geometrias[geometria.id];
      if (!meta) throw Object.assign(new Error('no disponible'), { codigo: '404' });
      const partes = [];
      for (let desde = 0; ;) {
        const { response } = await peticionPrivada('/api/archivos/geometrias/' + geometria.id + '/contenido?desde=' + desde, { signal });
        partes.push(new Uint8Array(await response.arrayBuffer()));
        if (response.headers.get('X-Geometria-Final') === '1') break;
        desde = Number(response.headers.get('X-Geometria-Siguiente'));
      }
      const texto = new TextDecoder().decode(await new Blob(partes).arrayBuffer());
      d.cargas += 1;
      return { geojson: JSON.parse(texto), bbox: meta.bbox, punto_interior: meta.punto_interior };
    },
    reset() { d.resets += 1; },
    destroy() { d.cargadorDestruido = true; },
  };
}`;

const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const resultados = [];
let fallos = 0;
async function caso(nombre, fn) {
  try { await fn(); resultados.push(`ok   ${nombre}`); }
  catch (error) { fallos += 1; resultados.push(`FAIL ${nombre}\n     ${String(error.stack ?? error).split('\n').slice(0, 7).join('\n     ')}`); }
}

async function abrir(usuario, { dobles = true } = {}) {
  const context = await browser.newContext({ viewport: { width: 1500, height: 900 }, locale: 'es-MX' });
  context.setDefaultTimeout(Number(process.env.E2E_TIMEOUT ?? 10000));
  const page = await context.newPage();
  const api = [];
  const errores = [];
  page.on('response', (r) => { if (r.url().includes('/api/')) api.push(`${r.request().method()} ${new URL(r.url()).pathname} ${r.status()}`); });
  page.on('pageerror', (e) => errores.push(e.message));
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  if (dobles) {
    const js = (body) => (r) => r.fulfill({ status: 200, contentType: 'text/javascript', body });
    await page.route('**/components/archivos/index.js', js(DOBLE_WIDGETS));
    await page.route('**/lib/cargadorGeometrias.js', js(DOBLE_CARGADOR));
  }
  await page.goto(`${URL_BASE}/?test=1`);
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

/** A JSON call from inside the page, with the page's own session. */
const llamar = (page, metodo, ruta, cuerpo, clave) => page.evaluate(async ([m, r, c, k]) => {
  const res = await fetch(r, { method: m, headers: { ...(c ? { 'Content-Type': 'application/json' } : {}), ...(k ? { 'Idempotency-Key': k } : {}) },
    body: c ? JSON.stringify(c) : undefined });
  return { status: res.status, datos: await res.json().catch(() => null) };
}, [metodo, ruta, cuerpo ?? null, clave ?? null]);

/** Upload one file through the real attachment routes, as the page's account. */
const subir = (page, terreno, tipo, b64) => page.evaluate(async ([t, tp, datos]) => {
  const bytes = Uint8Array.from(atob(datos), (c) => c.charCodeAt(0));
  const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map((b) => b.toString(16).padStart(2, '0')).join('');
  const json = async (r) => ({ status: r.status, datos: await r.json().catch(() => null) });
  const inicio = await json(await fetch(`/api/inventario/terrenos/${t}/archivos`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ tipo: tp, nombre_original: `ficticio.${tp}`, tamano_declarado: bytes.length, sha256_declarado: sha }) }));
  if (inicio.status !== 200) return inicio;
  const vid = inicio.datos.version_id;
  const put = await fetch(`/api/archivos/versiones/${vid}/contenido`, {
    method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: bytes });
  if (put.status !== 200) return json(put);
  return json(await fetch(`/api/archivos/versiones/${vid}/completar`, { method: 'POST' }));
}, [terreno, tipo, b64]);

const foto = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); };
const fila = (page, id) => page.locator(`tr[data-id="${id}"]`);
const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const estadoMapa = (page) => page.locator('.previa-estado');
const hasta = async (fn, ms = 8000) => {
  const fin = Date.now() + ms;
  for (;;) { const v = await fn(); if (v) return v; if (Date.now() > fin) throw new Error('no ocurrió a tiempo'); await new Promise((r) => setTimeout(r, 60)); }
};

/* ------------------------------------------------------------------ data */

let base, conXY, soloKmz, enBlanco;
{
  const { context, page } = await abrir('ada', { dobles: false });
  const b = await llamar(page, 'POST', '/api/maestra/bases', { nombre: 'Base Archivos Ficticia' });
  assert.equal(b.status, 200, JSON.stringify(b.datos));
  base = b.datos.base;
  const ops = (await llamar(page, 'GET', '/api/maestra/operadores?limit=200')).datos.usuarios;
  const ids = ['olga', 'omar'].map((n) => ops.find((o) => o.login === n).id);
  const acceso = await llamar(page, 'PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: ids });
  assert.equal(acceso.status, 200, JSON.stringify(acceso.datos));
  const crear = async (campos) => (await llamar(page, 'POST', `/api/maestra/bases/${base.id}/terrenos`, campos, crypto.randomUUID())).datos.terreno.id;
  conXY = await crear({ terreno: 'Lote Con XY Ficticio', lat: 20.67, lon: -103.35, superficie_m2: 5000 });
  soloKmz = await crear({ terreno: 'Lote Solo Contorno Ficticio' });
  enBlanco = await crear({});
  const k = await subir(page, soloKmz, 'kmz', KMZ_B64);
  assert.equal(k.status, 200, JSON.stringify(k.datos));
  assert.ok(k.datos.archivo.geometria_activa_id, 'el KMZ ficticio queda activo');
  await context.close();
}

/* --------------------------------------------------------------- journeys */

await caso('without Team B\'s modules the table works, says the files are unavailable, and the page map is honest', async () => {
  const { context, page, errores } = await abrir('olga', { dobles: false });
  await fila(page, soloKmz).waitFor();
  assert.equal((await celda(page, soloKmz, 'core:kmz').innerText()).trim(), 'No disponible');
  assert.equal((await celda(page, soloKmz, 'core:archivos').innerText()).trim(), 'No disponible');
  await page.getByRole('button', { name: 'Mapa de esta página' }).click();
  await page.locator('.previa-mapa .leaflet-container, .previa-mapa.leaflet-container').waitFor();
  const cuenta = await page.locator('.previa-cuenta').innerText();
  assert.match(cuenta, /2 de 3 filas de esta página con ubicación \(1 con contorno, 1 sin ubicar\)/);
  assert.match(await page.locator('.previa-nota').innerText(), /Sólo se dibujan las filas de la página actual/);
  await celda(page, soloKmz, 'core:terreno').click();
  await hasta(async () => /módulo de contornos no está disponible/.test(await estadoMapa(page).innerText()));
  assert.equal(await page.getByRole('button', { name: 'Reintentar' }).isVisible(), true);
  await celda(page, enBlanco, 'core:terreno').click();
  await hasta(async () => /no tiene ubicación: sigue en la tabla/.test(await estadoMapa(page).innerText()));
  await celda(page, conXY, 'core:terreno').click();
  await hasta(async () => /coordenadas X\/Y/.test(await estadoMapa(page).innerText()));
  assert.equal(await fila(page, conXY).getAttribute('aria-selected'), 'true');
  await foto(page, '01-sin-modulos-mapa-de-pagina');
  // Editing still works with the panel open.
  await celda(page, enBlanco, 'core:terreno').dblclick();
  await page.keyboard.type('Lote Nombrado Ficticio');
  await page.keyboard.press('Enter');
  await hasta(async () => (await celda(page, enBlanco, 'core:terreno').innerText()).trim() === 'Lote Nombrado Ficticio');
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await page.locator('.tabla-pantalla').waitFor({ state: 'detached' });
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('stand-in widgets receive the real summary in cells and in the detail; no placeholder, no fake zero', async () => {
  const { context, page, errores } = await abrir('olga');
  await fila(page, soloKmz).waitFor();
  await hasta(async () => (await celda(page, soloKmz, 'core:kmz').innerText()).trim() === 'kmz:activo');
  assert.equal((await celda(page, soloKmz, 'core:archivos').innerText()).trim(), 'pdf:0');
  assert.equal((await celda(page, conXY, 'core:kmz').innerText()).trim(), 'kmz:no');
  assert.equal(await page.evaluate(() => window.__doble.conPuente), true);
  await fila(page, soloKmz).getByRole('button', { name: /Abrir terreno/ }).click();
  const detalle = page.getByRole('dialog', { name: 'Lote Solo Contorno Ficticio' });
  await detalle.locator('.doble-archivo[data-detalle="true"][data-tipo="kmz"]').waitFor();
  assert.equal((await detalle.locator('.doble-archivo[data-tipo="kmz"]').innerText()).trim(), 'kmz:activo');
  await foto(page, '02-dobles-resumen-en-celda-y-detalle');
  const antes = await page.evaluate(() => window.__doble.destruidos);
  await detalle.getByRole('button', { name: 'Cerrar' }).first().click();
  await hasta(async () => (await page.evaluate(() => window.__doble.destruidos)) === antes + 2);   // both detail mounts
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('a file change refreshes that terrain once and never disturbs an open editor', async () => {
  const { context, page, api, errores } = await abrir('olga');
  await fila(page, conXY).waitFor();
  await hasta(async () => (await celda(page, conXY, 'core:archivos').innerText()).trim() === 'pdf:0');
  const version = (await llamar(page, 'GET', `/api/inventario/terrenos/${conXY}`)).datos.terreno.version;
  // An editor is open with unsaved text and a selection.
  await celda(page, conXY, 'core:municipio').dblclick();
  await page.keyboard.type('Zapopan Ficticio');
  await page.keyboard.press('Shift+ArrowLeft');
  await page.keyboard.press('Shift+ArrowLeft');
  // A PDF arrives (uploaded through the real API), and the widget reports it three times at once.
  const pdf = await subir(page, conXY, 'pdf', PDF_B64);
  assert.equal(pdf.status, 200, JSON.stringify(pdf.datos));
  const antes = api.filter((l) => l === `GET /api/inventario/terrenos/${conXY} 200`).length;
  await page.evaluate((id) => document.querySelector(`tr[data-id="${id}"] td[data-col="core:archivos"] .doble-archivo`)
    .dispatchEvent(new MouseEvent('click', { bubbles: false })), conXY);
  await hasta(async () => (await celda(page, conXY, 'core:archivos').innerText()).trim() === 'pdf:1');
  await new Promise((r) => setTimeout(r, 400));
  const pedidos = api.filter((l) => l === `GET /api/inventario/terrenos/${conXY} 200`).length - antes;
  assert.ok(pedidos >= 1 && pedidos <= 2, `tres avisos, ${pedidos} peticiones`);
  const editor = await page.evaluate(() => {
    const e = document.activeElement;
    return { clase: e.className, valor: e.value, inicio: e.selectionStart, fin: e.selectionEnd };
  });
  assert.match(editor.clase, /tabla-editor/);
  assert.deepEqual([editor.valor, editor.fin - editor.inicio], ['Zapopan Ficticio', 2]);
  // The upload did not move the terrain's version; the cell then saves against it.
  await page.keyboard.press('Enter');
  await hasta(async () => (await celda(page, conXY, 'core:municipio').innerText()).trim() === 'Zapopan Ficticio');
  const despues = (await llamar(page, 'GET', `/api/inventario/terrenos/${conXY}`)).datos.terreno;
  assert.equal(despues.version, version + 1);
  assert.equal(despues.archivos.pdf_total, 1);
  assert.equal((await celda(page, conXY, 'core:archivos').innerText()).trim(), 'pdf:1');
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('the page map loads only the selected boundary, through the loader, and keeps one body', async () => {
  const { context, page, api, errores } = await abrir('olga');
  await fila(page, soloKmz).waitFor();
  await page.getByRole('button', { name: 'Mapa de esta página' }).click();
  await page.locator('.previa-mapa.leaflet-container').waitFor();
  assert.equal(api.filter((l) => l.includes('/api/archivos/geometrias/')).length, 0, 'nothing is prefetched');
  await celda(page, soloKmz, 'core:terreno').click();
  await hasta(async () => /Contorno cargado/.test(await estadoMapa(page).innerText()));
  assert.equal(await page.evaluate(() => window.__doble.cargas), 1);
  // Drawn as a real outline at parcel scale, one body held, nothing loading.
  await hasta(async () => (await page.evaluate((id) => window.__araTabla.posicion(id), soloKmz))?.contorno === true);
  const previa = await page.evaluate(() => window.__araTabla.previa());
  assert.deepEqual([previa.cuerpos, previa.cargando, previa.filas], [1, false, 3]);
  assert.ok(previa.zoom >= 15, `encuadrado al terreno (zoom ${previa.zoom})`);
  await new Promise((r) => setTimeout(r, 700));      // the framing animation
  assert.ok(api.some((l) => /GET \/api\/archivos\/geometrias\/[0-9a-f-]+\/contenido 200/.test(l)));
  await foto(page, '03-contorno-seleccionado-cargado');
  // X/Y of the boundary-only terrain stay blank in the table.
  assert.equal((await celda(page, soloKmz, 'core:lat').innerText()).trim(), '');
  // Another selection drops the body; coming back loads it again (no hidden cache in the host).
  await celda(page, conXY, 'core:terreno').click();
  await hasta(async () => /coordenadas X\/Y/.test(await estadoMapa(page).innerText()));
  assert.equal((await page.evaluate(() => window.__araTabla.previa())).cuerpos, 0);
  assert.equal((await page.evaluate((id) => window.__araTabla.posicion(id), soloKmz)).contorno, false);
  await celda(page, soloKmz, 'core:terreno').click();
  await hasta(async () => (await page.evaluate(() => window.__doble.cargas)) === 2);
  // A failure is said, the terrain stays at its interior point, and retry works.
  await celda(page, conXY, 'core:terreno').click();
  await page.evaluate(() => { window.__dobleFalla = true; });
  await celda(page, soloKmz, 'core:terreno').click();
  await hasta(async () => /No se pudo cargar el contorno/.test(await estadoMapa(page).innerText()));
  await foto(page, '04-contorno-no-disponible-con-reintento');
  await page.evaluate(() => { window.__dobleFalla = false; });
  await page.getByRole('button', { name: 'Reintentar' }).click();
  await hasta(async () => /Contorno cargado/.test(await estadoMapa(page).innerText()));
  // A slow load that the next selection supersedes never lands.
  await celda(page, conXY, 'core:terreno').click();
  await page.evaluate(() => { window.__dobleEspera = 600; });
  await celda(page, soloKmz, 'core:terreno').click();
  await celda(page, conXY, 'core:terreno').click();
  await new Promise((r) => setTimeout(r, 1000));
  assert.match(await estadoMapa(page).innerText(), /coordenadas X\/Y/);
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('logout during a boundary load tears everything down; the next account gets nothing of it', async () => {
  const { context, page, errores } = await abrir('olga');
  await fila(page, soloKmz).waitFor();
  await page.getByRole('button', { name: 'Mapa de esta página' }).click();
  await page.locator('.previa-mapa.leaflet-container').waitFor();
  await page.evaluate(() => { window.__dobleEspera = 1500; });
  await celda(page, soloKmz, 'core:terreno').click();
  await hasta(async () => /Cargando el contorno/.test(await estadoMapa(page).innerText()));
  const antes = await page.evaluate(() => ({ ...window.__doble }));
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await page.locator('.tabla-pantalla').waitFor({ state: 'detached' });
  const d = await page.evaluate(() => ({ ...window.__doble }));
  assert.equal(d.fabricasDestruidas, antes.fabricasDestruidas + 1);
  assert.equal(d.cargadorDestruido, true);
  assert.equal(d.destruidos, d.montados, 'every mount was destroyed');
  assert.equal(await page.locator('.previa, .previa-mapa, .doble-archivo').count(), 0);   // the public map is another one
  // otto has no grant: after signing in on the same page nothing of olga's is there, late answers included.
  await entrar(page, 'otto');
  await new Promise((r) => setTimeout(r, 1800));
  assert.equal(await page.locator('tr[data-id]').count(), 0);
  assert.equal(await page.getByText('Lote Solo Contorno Ficticio').count(), 0);
  assert.equal(await page.evaluate(() => window.__doble.cargas), antes.cargas, 'the interrupted load never completed');
  const negado = await llamar(page, 'GET', `/api/inventario/terrenos/${soloKmz}`);
  assert.equal(negado.status, 404);
  assert.deepEqual(errores, []);
  await context.close();
});

await caso('a second authorized session sees the same stored boundary; losing the grant removes it', async () => {
  const a = await abrir('omar');
  await fila(a.page, soloKmz).waitFor();
  await hasta(async () => (await celda(a.page, soloKmz, 'core:kmz').innerText()).trim() === 'kmz:activo');
  await a.page.getByRole('button', { name: 'Mapa de esta página' }).click();
  await celda(a.page, soloKmz, 'core:terreno').click();
  await hasta(async () => /Contorno cargado/.test(await estadoMapa(a.page).innerText()));
  // The administrator takes omar's grant away.
  const adm = await abrir('ada');
  const actual = (await llamar(adm.page, 'GET', `/api/maestra/bases/${base.id}/acceso`)).datos;
  const resto = actual.usuarios.filter((u) => u.login !== 'omar').map((u) => u.id);
  const r = await llamar(adm.page, 'PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: actual.base.version, usuarios: resto });
  assert.equal(r.status, 200, JSON.stringify(r.datos));
  await adm.context.close();
  // omar's widget reports a change; the refresh is denied and the row, the files and the outline go.
  await a.page.evaluate((id) => document.querySelector(`tr[data-id="${id}"] td[data-col="core:kmz"] .doble-archivo`).click(), soloKmz);
  await hasta(async () => (await a.page.locator('tr[data-id]').count()) === 0);
  await hasta(async () => (await a.page.getByText('Lote Solo Contorno Ficticio').count()) === 0);
  assert.doesNotMatch(await estadoMapa(a.page).innerText().catch(() => ''), /Contorno cargado/);
  await foto(a.page, '05-sin-acceso-nada-queda');
  assert.deepEqual(a.errores, []);
  await a.context.close();
});

console.log(resultados.join('\n'));
console.log(`\n${resultados.length - fallos}/${resultados.length} recorridos`);
await browser.close();
process.exit(fallos ? 1 : 0);

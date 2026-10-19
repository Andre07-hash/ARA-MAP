/* The table keeps its scroll position when a file upload finishes, with the
 * REAL widgets, the real local server (tests/e2e/tabla_servidor.py on a folder
 * it creates and deletes), real sessions and Chromium. Fictional accounts and
 * files only.
 *
 *   cd tests/e2e && node tabla-posicion.mjs
 *
 * A page of 45 rows in a 1100 x 650 window scrolls both ways; the file
 * columns are at the far right. Every check measures the scrolling container
 * (the grid's .tabla-lienzo) and the page, in pixels:
 *   - a PDF chosen in a cell far from the start, with the window regaining
 *     focus when the picker closes (the shell's revalidation), keeps the
 *     position and lands on the right terrain;
 *   - a KML whose bytes are held while the person scrolls elsewhere ends at
 *     the person's NEW position, not where the upload began;
 *   - finishing an upload with no revalidation (the in-place summary update
 *     refrescarArchivos -> aplicarArchivos) reloads nothing and moves nothing;
 *   - the operator's KMZ chosen in the record detail keeps the table where it
 *     was when the detail closes, the focus goes back to that row, and the
 *     keyboard still moves from its cell.
 * Optional: POSICION_CAPTURAS=dir, CHROMIUM=/path, POSICION_PUERTO.
 */

import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.POSICION_PUERTO ?? 8489);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.POSICION_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const FILAS = 45;
const TOLERANCIA = 2;              // px: sub-pixel rounding only

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-posicion-'));
const F = JSON.parse(execFileSync(PY, ['-c',
  'import json, sys\nfrom pathlib import Path\nsys.path.insert(0, "tests/e2e")\n' +
  'from archivos_servidor import escribir_fixtures\n' +
  'd = Path(sys.argv[1]); d.mkdir()\nprint(json.dumps(escribir_fixtures(d)))', join(CARPETA, 'fixtures')],
  { cwd: RAIZ, encoding: 'utf8' }));
mkdirSync(join(CARPETA, 'fixtures', 'kml_simple'));
F.kml_simple = join(CARPETA, 'fixtures', 'kml_simple', 'Contorno ficticio.kml');
writeFileSync(F.kml_simple, readFileSync(join(RAIZ, 'tests', 'fixtures', 'kmz', 'poligono_simple.kml')));

/* ------------------------------------------------------------ server */

const servidor = spawn(PY, [join(AQUI, 'tabla_servidor.py'), '--puerto', String(PUERTO), '--carpeta', join(CARPETA, 'instalacion')],
  { cwd: RAIZ, stdio: ['ignore', 'pipe', 'ignore'] });
await new Promise((resolve, reject) => {
  let texto = '';
  servidor.stdout.on('data', (d) => { texto += d; if (/LISTO/.test(texto)) resolve(); });
  servidor.on('exit', (c) => reject(new Error(`el servidor salió (${c}): ${texto}`)));
});

/* ------------------------------------------------------------ harness */

let fallos = 0;
async function revisar(nombre, fn) {
  try {
    await fn();
    console.log(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    console.log(`FALLO ${nombre}\n     ${String(error?.stack ?? error).split('\n').slice(0, 6).join('\n     ')}`);
    for (const s of sesiones) {
      if (SHOTS && !s.page.isClosed()) await s.page.screenshot({ path: join(SHOTS, `fallo-${fallos}-${s.usuario}.png`) }).catch(() => {});
      if (!s.page.isClosed()) await s.page.keyboard.press('Escape').catch(() => {});
    }
  }
}
const igual = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const cierto = (v, m) => { if (!v) throw new Error(m); };
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
async function hasta(fn, mensaje = 'no ocurrió a tiempo', ms = 60000) {
  const fin = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > fin) throw new Error(typeof mensaje === 'function' ? await mensaje() : mensaje);
    await esperar(60);
  }
}

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium' });
const sesiones = [];
async function abrir(usuario) {
  const contexto = await navegador.newContext({ viewport: { width: 1100, height: 650 }, locale: 'es-MX' });
  contexto.setDefaultTimeout(30000);
  const page = await contexto.newPage();
  const s = { usuario, page, errores: [], lecturas: [] };
  page.on('pageerror', (e) => s.errores.push(String(e)));
  page.on('request', (r) => { if (r.url().includes('/api/')) s.lecturas.push(`${r.method()} ${new URL(r.url()).pathname}${new URL(r.url()).search}`); });
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  await page.goto(`${URLBASE}/?test=1`);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click().catch(() => {});
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVE);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
  s.desde = Date.now();
  sesiones.push(s);
  return s;
}
const llamar = (page, metodo, ruta, cuerpo) => page.evaluate(async ([m, r, c]) => {
  const res = await fetch(r, { method: m, headers: c ? { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() } : {},
    body: c ? JSON.stringify(c) : undefined });
  return { status: res.status, datos: await res.json().catch(() => null) };
}, [metodo, ruta, cuerpo ?? null]);
const terreno = async (page, id) => (await llamar(page, 'GET', `/api/inventario/terrenos/${id}`)).datos?.terreno;

const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const resumen = async (page, id, col) => (await celda(page, id, col).locator('.archivos-celda').innerText().catch(() => '')).trim();
const elegirEn = (page, id, col) => celda(page, id, col).locator('.archivos-celda-elegir');
const COL = { pdf: 'core:archivos', kmz: 'core:kmz' };
const tipoDe = (ruta) => (ruta.endsWith('.pdf') ? 'application/pdf'
  : /\.kml$/i.test(ruta) ? 'application/vnd.google-earth.kml+xml' : 'application/vnd.google-earth.kmz');

/** Where the grid and the page are scrolled, in pixels, and how far they can go. */
const posicion = (page) => page.evaluate(() => {
  const l = document.querySelector('.tabla-lienzo');
  return { top: Math.round(l.scrollTop), left: Math.round(l.scrollLeft),
    maxTop: l.scrollHeight - l.clientHeight, maxLeft: l.scrollWidth - l.clientWidth,
    pageX: Math.round(window.scrollX), pageY: Math.round(window.scrollY) };
});
const enfocada = (page) => page.evaluate(() => {
  const td = document.activeElement?.closest?.('td[data-col]');
  return td ? `${td.closest('tr').dataset.id}|${td.dataset.col}` : document.activeElement?.tagName ?? null;
});
function mismaPosicion(antes, despues, m) {
  for (const k of ['top', 'left', 'pageX', 'pageY']) {
    cierto(Math.abs(antes[k] - despues[k]) <= TOLERANCIA,
      `${m}: ${k} saltó de ${antes[k]} a ${despues[k]} (antes ${JSON.stringify(antes)}, después ${JSON.stringify(despues)})`);
  }
}
/** Scroll the grid so this terrain's file cell is in view, far from the start. */
async function irACelda(page, id, col) {
  await celda(page, id, col).evaluate((td) => td.scrollIntoView({ block: 'center', inline: 'center' }));
  await esperar(150);
  const p = await posicion(page);
  cierto(p.top > 100 && p.left > 100, `la celda no queda lejos del inicio: ${JSON.stringify(p)}`);
  return p;
}

async function irA(page, vista) {
  await page.goto(`${URLBASE}/?test=1#/tabla/${vista}`);
  await page.locator('.tabla-pantalla').waitFor();
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await hasta(async () => (await page.locator('tr.tabla-fila').count()) === FILAS, 'la página no tiene todas las filas');
}

/* app.js revalidates on focus at most every 10 s, per page: wait that out,
 * focus, and wait for the session check that proves the revalidation ran. */
async function enfocar(s) {
  const falta = 10_500 - (Date.now() - (s.ultimoFoco ?? s.desde));
  if (falta > 0) await esperar(falta);
  const antes = s.lecturas.filter((l) => l === 'GET /api/session').length;
  await s.page.evaluate(() => window.dispatchEvent(new Event('focus')));
  s.ultimoFoco = Date.now();
  await hasta(async () => s.lecturas.filter((l) => l === 'GET /api/session').length > antes, 'no hubo revalidación');
}
const listas = (s) => s.lecturas.filter((l) => /^GET \/api\/(maestra\/bases\/[^/]+|inventario)\/terrenos\?/.test(l)).length;

/** Hold every request matching `patron` until released. */
async function retener(page, patron) {
  const vistos = [];
  let soltar;
  const suelta = new Promise((r) => { soltar = r; });
  await page.route(patron, async (ruta) => { vistos.push(ruta.request().url()); await suelta; await ruta.continue(); });
  return { vistos, soltar: async () => { soltar(); await page.unroute(patron); } };
}

/* --------------------------------------------------------------- data */

const ada = await abrir('ada');
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Posición Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
igual((await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] })).status, 200, 'acceso');
const ids = [];
for (let n = 1; n <= FILAS; n += 1) {
  ids.push((await admin('POST', `/api/maestra/bases/${base.id}/terrenos`,
    { terreno: `Lote Posición ${String(n).padStart(2, '0')} Ficticio` })).datos.terreno.id);
}
// The page lists the newest first; pick rows well below the top.
await ada.page.reload();
await ada.page.locator('.tabla-pantalla').waitFor();
ada.desde = Date.now();

/* ----------------------------------------------------------- journeys */

let filasDePagina = [];
await revisar('preparación: 45 filas que se desplazan en las dos direcciones', async () => {
  await irA(ada.page, base.id);
  filasDePagina = await ada.page.locator('tr.tabla-fila').evaluateAll((trs) => trs.map((t) => t.dataset.id));
  const p = await posicion(ada.page);
  cierto(p.maxTop > 600 && p.maxLeft > 200, `sin desplazamiento suficiente: ${JSON.stringify(p)}`);
});

await revisar('administrador: un PDF elegido lejos del inicio, con foco al volver del selector, no mueve la tabla', async () => {
  const id = filasDePagina[30];
  await irA(ada.page, base.id);
  const antes = await irACelda(ada.page, id, COL.pdf);
  const listasAntes = listas(ada);
  const [selector] = await Promise.all([ada.page.waitForEvent('filechooser'), elegirEn(ada.page, id, COL.pdf).click()]);
  await enfocar(ada);                                          // the picker closing gives the window focus first
  await selector.setFiles({ name: 'Avalúo ficticio.pdf', buffer: readFileSync(F.pdf), mimeType: 'application/pdf' });
  await hasta(async () => (await resumen(ada.page, id, COL.pdf)) === '1 PDF', 'la celda no llegó a 1 PDF', 90000);
  await ada.page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await esperar(500);
  mismaPosicion(antes, await posicion(ada.page), 'al terminar el PDF');
  // Never another row or column. (The cell's button is disabled while its
  // upload runs, so the browser may leave the focus on the page body; that
  // is the file widget's own rule and moves nothing.)
  const f = await ada.page.evaluate((fila) => {
    const tr = document.activeElement?.closest?.('tr');
    return tr ? (tr.dataset.id === fila ? 'fila' : `otra fila ${tr.dataset.id}`) : document.activeElement?.tagName;
  }, id);
  cierto(f === 'fila' || f === 'BODY', `el foco saltó: ${f}`);
  igual((await terreno(ada.page, id)).archivos.pdf_total, 1, 'el PDF quedó en su terreno');
  igual((await terreno(ada.page, filasDePagina[29])).archivos.pdf_total, 0, 'la fila vecina no cambió');
  cierto(listas(ada) >= listasAntes, 'lecturas');
});

await revisar('administrador: moverse mientras un KML se sube deja la tabla donde está AHORA', async () => {
  const id = filasDePagina[35];
  await irA(ada.page, base.id);
  await irACelda(ada.page, id, COL.kmz);
  const put = await retener(ada.page, '**/api/archivos/versiones/*/contenido');
  const [selector] = await Promise.all([ada.page.waitForEvent('filechooser'), elegirEn(ada.page, id, COL.kmz).click()]);
  await selector.setFiles({ name: 'Contorno ficticio.kml', buffer: readFileSync(F.kml_simple), mimeType: tipoDe(F.kml_simple) });
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  // The person moves elsewhere while the bytes are on their way.
  await ada.page.locator('.tabla-lienzo').evaluate((l) => l.scrollTo({ top: Math.round(l.scrollHeight * 0.25), left: 40 }));
  await esperar(200);
  const nueva = await posicion(ada.page);
  await enfocar(ada);                                          // a revalidation lands during the upload too
  await put.soltar();
  await hasta(async () => (await resumen(ada.page, id, COL.kmz)) === 'Contorno activo', 'la celda no llegó a Contorno activo', 90000);
  await ada.page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await esperar(500);
  mismaPosicion(nueva, await posicion(ada.page), 'al terminar el KML');
  igual((await terreno(ada.page, id)).ubicacion.modo, 'geometria', 'el contorno quedó en su terreno');
});

await revisar('administrador: sin revalidación, terminar la subida (refrescarArchivos) tampoco mueve la tabla', async () => {
  const id = filasDePagina[40];
  await irA(ada.page, base.id);
  const antes = await irACelda(ada.page, id, COL.pdf);
  const listasAntes = listas(ada);
  const [selector] = await Promise.all([ada.page.waitForEvent('filechooser'), elegirEn(ada.page, id, COL.pdf).click()]);
  await selector.setFiles({ name: 'Escritura ficticia.pdf', buffer: readFileSync(F.pdf2), mimeType: 'application/pdf' });
  await hasta(async () => (await resumen(ada.page, id, COL.pdf)) === '1 PDF', 'la celda no llegó a 1 PDF', 90000);
  await esperar(500);
  mismaPosicion(antes, await posicion(ada.page), 'al terminar sin revalidación');
  igual(listas(ada), listasAntes, 'terminar una subida no recarga la página de la tabla');
});

const olga = await abrir('olga');

await revisar('operador: un KMZ subido en el detalle deja la tabla donde estaba al cerrarlo, y el teclado sigue', async () => {
  const id = filasDePagina[25];
  await irA(olga.page, base.id);
  // Work in a cell of the row first, far to the right, as a person would.
  await celda(olga.page, id, 'core:lon').evaluate((td) => td.scrollIntoView({ block: 'center', inline: 'center' }));
  await celda(olga.page, id, 'core:lon').focus();
  await esperar(150);
  const antes = await posicion(olga.page);
  cierto(antes.top > 100 && antes.left > 100, `la celda no queda lejos del inicio: ${JSON.stringify(antes)}`);
  await olga.page.locator(`tr[data-id="${id}"]`).getByRole('button', { name: /Abrir terreno/ }).click();
  const d = olga.page.getByRole('dialog', { name: /Lote Posición/ });
  const k = d.locator('.archivos-detalle[data-tipo="kmz"]');
  const [selector] = await Promise.all([olga.page.waitForEvent('filechooser'), k.locator('.archivos-elegir').click()]);
  await enfocar(olga);
  await selector.setFiles({ name: 'Forma U ficticia.kmz', buffer: readFileSync(F.kmz_reemplazo), mimeType: tipoDe(F.kmz_reemplazo) });
  await hasta(async () => /KMZ guardado; su contorno es el activo/.test(await k.locator('.archivos-subidas li').first().innerText().catch(() => '')),
    'la subida del detalle no terminó', 90000);
  await d.getByRole('button', { name: 'Cerrar' }).last().click();
  await hasta(async () => (await resumen(olga.page, id, COL.kmz)) === 'Contorno activo', 'la celda no llegó a Contorno activo', 90000);
  await esperar(500);
  mismaPosicion(antes, await posicion(olga.page), 'al cerrar el detalle');
  // The dialog gives the focus back to what opened it: that row's own button.
  cierto(await olga.page.evaluate((fila) => document.activeElement?.closest?.('tr')?.dataset.id === fila, id),
    'el foco vuelve a la fila del detalle');
  // Intentional keyboard navigation still moves from a cell, and scrolls only as needed.
  await celda(olga.page, id, 'core:lon').focus();
  mismaPosicion(antes, await posicion(olga.page), 'al volver a la celda');
  await olga.page.keyboard.press('ArrowDown');
  const abajo = filasDePagina[filasDePagina.indexOf(id) + 1];
  igual(await enfocada(olga.page), `${abajo}|core:lon`, 'la flecha baja a la fila siguiente');
  igual((await terreno(olga.page, id)).ubicacion.modo, 'geometria', 'el contorno quedó en su terreno');
});

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

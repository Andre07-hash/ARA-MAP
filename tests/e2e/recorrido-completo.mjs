/* Packet 3A final check: the COMPLETE local workflow in the real application,
 * with Team B's REAL widgets (web/components/archivos/) and geometry loader
 * (web/lib/cargadorGeometrias.js). Nothing is stubbed: the real mounted server
 * (server.app.Handler through tests/e2e/tabla_servidor.py), its local disk
 * store, real cookie sessions and Chromium. Uploads, choices, activation,
 * downloads and retirement are made by clicking the widgets.
 *
 *   cd tests/e2e && node recorrido-completo.mjs                       # SQLite, every journey
 *   ARA_MAP_TEST_DATABASE_URL=postgresql://…/desechable RECORRIDO_BD=postgres \
 *     PYTHON=../../.venv-dev/bin/python node recorrido-completo.mjs   # focused Postgres smoke
 *
 * The script starts the server itself on a folder it creates, STOPS it and
 * starts a new process on the same database and folder for the restart check,
 * and deletes everything at the end (the Postgres schema too). It refuses any
 * URL that is not loopback. Optional: RECORRIDO_CAPTURAS=dir (screenshots),
 * RECORRIDO_EVIDENCIA=dir (JSON summary), CHROMIUM=/path, RECORRIDO_PUERTO.
 */

import { execFileSync, spawn } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import { mkdirSync, mkdtempSync, openSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const BD = process.env.RECORRIDO_BD ?? 'sqlite';
if (!['sqlite', 'postgres'].includes(BD)) throw new Error('RECORRIDO_BD es sqlite o postgres');
if (BD === 'postgres' && !process.env.ARA_MAP_TEST_DATABASE_URL) throw new Error('Falta ARA_MAP_TEST_DATABASE_URL (desechable).');
const FOCALIZADO = BD === 'postgres';           // the packet asks for one focused smoke there
const PUERTO = Number(process.env.RECORRIDO_PUERTO ?? (BD === 'postgres' ? 8472 : 8471));
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.RECORRIDO_CAPTURAS ?? null;
const EVID = process.env.RECORRIDO_EVIDENCIA ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const sha = (b) => createHash('sha256').update(b).digest('hex');

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-recorrido-3a-'));
const ESQUEMA = BD === 'postgres' ? `recorrido_3a_${randomBytes(6).toString('hex')}` : null;
const F = JSON.parse(execFileSync(PY, ['-c',
  'import json, sys\nfrom pathlib import Path\nsys.path.insert(0, "tests/e2e")\n' +
  'from archivos_servidor import escribir_fixtures\n' +
  'd = Path(sys.argv[1]); d.mkdir()\nprint(json.dumps(escribir_fixtures(d)))', join(CARPETA, 'fixtures')],
  { cwd: RAIZ, encoding: 'utf8' }));

/* ------------------------------------------------------------ server */

let servidor = null;
let arranques = 0;
async function arrancar() {
  const args = [join(AQUI, 'tabla_servidor.py'), '--puerto', String(PUERTO), '--carpeta', join(CARPETA, 'instalacion')];
  if (ESQUEMA) args.push('--postgres-esquema', ESQUEMA);
  // The server's request log goes to RECORRIDO_LOG_SERVIDOR when given, else nowhere.
  const log = process.env.RECORRIDO_LOG_SERVIDOR ? openSync(process.env.RECORRIDO_LOG_SERVIDOR, 'a') : 'ignore';
  const proceso = spawn(PY, args, { cwd: RAIZ, stdio: ['ignore', 'pipe', log] });
  arranques += 1;
  let texto = '';
  await new Promise((resolve, reject) => {
    proceso.stdout.on('data', (d) => { texto += d; if (/LISTO/.test(texto)) resolve(); });
    proceso.on('exit', (c) => reject(new Error(`el servidor salió (${c}): ${texto}`)));
  });
  for (let i = 0; i < 100; i += 1) {
    try { if ((await fetch(`${URLBASE}/api/config`)).ok) break; } catch { /* not yet */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  servidor = { proceso, salida: () => texto };
  return texto;
}
async function detener() {
  const p = servidor.proceso;
  servidor = null;
  await new Promise((r) => { p.once('exit', r); p.kill('SIGTERM'); });
}
function limpiar() {
  servidor?.proceso.kill('SIGKILL');
  if (ESQUEMA) {
    execFileSync(PY, ['-c', 'import os, sys, psycopg\nwith psycopg.connect(os.environ["ARA_MAP_TEST_DATABASE_URL"]) as c:\n' +
      '    c.execute(f\'DROP SCHEMA IF EXISTS "{sys.argv[1]}" CASCADE\')', ESQUEMA], { cwd: RAIZ });
  }
  rmSync(CARPETA, { recursive: true, force: true });
}

/* ------------------------------------------------------------ harness */

const resultados = [];
let fallos = 0;
let enCurso = 'preparación';
async function revisar(nombre, fn) {
  const inicio = Date.now();
  enCurso = nombre;
  try {
    const detalle = await fn();
    resultados.push({ nombre, ok: true, ms: Date.now() - inicio, ...(detalle ? { detalle } : {}) });
    console.log(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    for (const [n, x] of sesiones.entries()) {
      if (x.page.isClosed()) continue;
      const mapa = await estadoMapa(x.page);
      if (mapa) console.log(`     mapa (${x.usuario}): ${mapa}`);
      if (SHOTS) await x.page.screenshot({ path: join(SHOTS, `fallo-${fallos}-${n}-${x.usuario}.png`) }).catch(() => {});
    }
    // Leave no dialog open behind a failure: it would block every later journey.
    for (const x of sesiones) if (!x.page.isClosed()) await x.page.keyboard.press('Escape').catch(() => {});
    resultados.push({ nombre, ok: false, error: String(error?.stack ?? error).split('\n').slice(0, 6).join('\n') });
    console.log(`FALLO ${nombre}\n     ${String(error?.stack ?? error).split('\n').slice(0, 6).join('\n     ')}`);
  }
}
const igual = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const cierto = (v, m) => { if (!v) throw new Error(m); };
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
async function hasta(fn, mensaje = 'no ocurrió a tiempo', ms = 30000) {
  const fin = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > fin) throw new Error(mensaje);
    await esperar(60);
  }
}

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium',
  env: { ...process.env, LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8' } });   // UTF-8 download names

const sesiones = [];
async function abrir(usuario) {
  const contexto = await navegador.newContext({ acceptDownloads: true, viewport: { width: 1500, height: 950 }, locale: 'es-MX' });
  contexto.setDefaultTimeout(30000);
  const page = await contexto.newPage();
  const s = { usuario, contexto, page, errores: [], api: [] };
  page.on('pageerror', (e) => s.errores.push(`${e} [${enCurso}] ${String(e.stack ?? '').split('\n').slice(1, 4).join(' | ')}`));
  page.on('response', (r) => { if (r.url().includes('/api/')) s.api.push(`${r.request().method()} ${new URL(r.url()).pathname} ${r.status()}`); });
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  await page.goto(`${URLBASE}/?test=1`);
  if (usuario) await entrar(page, usuario);
  sesiones.push(s);
  return s;
}
async function entrar(page, usuario) {
  const dialogo = page.getByRole('dialog', { name: 'Iniciar sesión' });
  if (!(await dialogo.isVisible().catch(() => false))) await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVE);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
}
const llamar = (page, metodo, ruta, cuerpo, clave) => page.evaluate(async ([m, r, c, k]) => {
  const res = await fetch(r, { method: m, headers: { ...(c ? { 'Content-Type': 'application/json' } : {}), ...(k ? { 'Idempotency-Key': k } : {}) },
    body: c ? JSON.stringify(c) : undefined });
  return { status: res.status, datos: await res.json().catch(() => null) };
}, [metodo, ruta, cuerpo ?? null, clave ?? null]);
const terreno = async (page, id) => (await llamar(page, 'GET', `/api/inventario/terrenos/${id}`)).datos?.terreno;

const fila = (page, id) => page.locator(`tr[data-id="${id}"]`);
const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const textoCelda = async (page, id, col) => (await celda(page, id, col).innerText().catch(() => '')).trim();
const listo = (page) => page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
const estadoMapa = async (page) => (await page.locator('.previa-estado').innerText().catch(() => '')).trim();
const foto = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); };

async function irATabla(page) {
  await page.goto(`${URLBASE}/?test=1#/tabla`);
  await page.locator('.tabla-pantalla').waitFor();
  await listo(page);
}
async function escribir(page, id, col, valor) {
  await celda(page, id, col).focus();
  await page.keyboard.press('Enter');
  const editor = celda(page, id, col).locator('.tabla-editor');
  await editor.waitFor();
  await editor.fill(valor);
  await page.keyboard.press('Enter');
  await page.locator(`tr[data-id="${id}"] td[data-col="${col}"]:not(.is-pendiente):not(.is-editando)`).waitFor();
}
async function abrirDetalle(page, id, nombre) {
  await fila(page, id).getByRole('button', { name: /Abrir terreno/ }).click();
  const d = page.getByRole('dialog', { name: nombre });
  await d.locator('.archivos-detalle[data-tipo="pdf"]').waitFor();
  return d;
}
async function cerrarDetalle(page, d) {
  await d.getByRole('button', { name: 'Cerrar' }).last().click();
  await d.waitFor({ state: 'detached' }).catch(() => d.waitFor({ state: 'hidden' }));
}
async function subirEnDetalle(d, tipo, ruta) {
  const nombre = ruta.split('/').at(-1);
  const mimeType = nombre.endsWith('.pdf') ? 'application/pdf' : 'application/vnd.google-earth.kmz';
  await d.locator(`.archivos-detalle[data-tipo="${tipo}"] .archivos-zona input[type=file]`).setInputFiles({ name: nombre, mimeType, buffer: readFileSync(ruta) });
}
async function faseFinal(d, tipo, fases, ms = 90000) {
  const ultima = d.locator(`.archivos-detalle[data-tipo="${tipo}"] .archivos-subida`).last();
  await hasta(async () => fases.includes(await ultima.getAttribute('data-fase').catch(() => null)), `fase ${fases}`, ms);
  return ultima.getAttribute('data-fase');
}
async function abrirMapa(page) {
  const b = page.getByRole('button', { name: 'Mapa de esta página' });
  if ((await b.getAttribute('aria-pressed')) !== 'true') await b.click();
  await page.locator('.previa-mapa.leaflet-container').waitFor();
}
async function seleccionarEnTabla(page, id) {
  await celda(page, id, 'core:terreno').click();
}

/* --------------------------------------------------------------- data */

const salida0 = await arrancar();
const almacen = /Archivos: (.*)/.exec(salida0)?.[1] ?? null;
console.log(`servidor ${BD}${ESQUEMA ? ` (esquema ${ESQUEMA})` : ''}, almacén ${almacen}`);

let base, ajena, ids;
{
  const { page, contexto } = await abrir('ada');
  base = (await llamar(page, 'POST', '/api/maestra/bases', { nombre: 'Base Recorrido Ficticia' })).datos.base;
  ajena = (await llamar(page, 'POST', '/api/maestra/bases', { nombre: 'Base Ajena Ficticia' })).datos.base;
  const ops = (await llamar(page, 'GET', '/api/maestra/operadores?limit=200')).datos.usuarios;
  ids = Object.fromEntries(ops.map((o) => [o.login, o.id]));
  const r = await llamar(page, 'PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ids.olga, ids.omar] });
  igual(r.status, 200, 'acceso');
  await contexto.close();
}

const NOMBRE = 'Lote Recorrido Ficticio';
const VECINO = 'Lote Vecino Ficticio';
let lote = null;          // created blank in the UI by olga
let vecino = null;        // X/Y + boundary, for concurrent selection and retirement
let version0 = null;
let geometriaActiva = null;
const medidas = {};

const olga = await abrir('olga');
await irATabla(olga.page);

await revisar('el operador crea un terreno en blanco: los campos de negocio quedan vacíos, no en cero', async () => {
  const antes = await olga.page.locator('tr.tabla-fila').evaluateAll((f) => f.map((x) => x.dataset.id));
  await olga.page.getByRole('button', { name: 'Agregar terreno' }).click();
  await olga.page.locator('tr.is-nueva').first().waitFor();
  lote = (await olga.page.locator('tr.is-nueva').evaluateAll((f) => f.map((x) => x.dataset.id))).find((i) => !antes.includes(i));
  cierto(lote, 'sin fila nueva');
  for (const col of ['core:terreno', 'core:lat', 'core:lon', 'core:superficie_m2', 'core:asking_price']) {
    igual(await textoCelda(olga.page, lote, col), '', `celda ${col} en blanco`);
  }
  // Real widgets in the file cells: an honest "none yet", not a placeholder.
  await hasta(async () => (await textoCelda(olga.page, lote, 'core:archivos')) === 'Sin PDF', 'celda PDF');
  igual(await textoCelda(olga.page, lote, 'core:kmz'), 'Sin KMZ', 'celda KMZ');
  const t = await terreno(olga.page, lote);
  igual([t.draft.lat, t.draft.lon, t.draft.asking_price, t.ubicacion.modo], [null, null, null, 'ninguna'], 'en blanco');
});

await revisar('el operador edita el terreno en la tabla', async () => {
  await escribir(olga.page, lote, 'core:terreno', NOMBRE);
  await escribir(olga.page, lote, 'core:municipio', 'Municipio Ficticio');
  const t = await terreno(olga.page, lote);
  igual([t.draft.terreno, t.draft.municipio], [NOMBRE, 'Municipio Ficticio'], 'guardado');
  version0 = t.version;
});

await revisar('sube un PDF desde el detalle y lo descarga byte por byte idéntico', async () => {
  const d = await abrirDetalle(olga.page, lote, NOMBRE);
  await subirEnDetalle(d, 'pdf', F.pdf);
  igual(await faseFinal(d, 'pdf', ['listo', 'fallido', 'incierto']), 'listo', 'fase');
  await hasta(async () => (await textoCelda(olga.page, lote, 'core:archivos')) === '1 PDF', 'la celda no llegó a 1 PDF');
  const item = d.locator('.archivos-detalle[data-tipo="pdf"] .archivos-item', { hasText: 'Avalúo ficticio.pdf' });
  await item.waitFor();
  const [descarga] = await Promise.all([olga.page.waitForEvent('download'), item.getByRole('button', { name: /^Descargar/ }).click()]);
  igual(sha(readFileSync(await descarga.path())), sha(readFileSync(F.pdf)), 'sha256');
  igual(descarga.suggestedFilename(), 'Avalúo ficticio.pdf', 'nombre');
  await foto(olga.page, '01-detalle-pdf-subido');
  await cerrarDetalle(olga.page, d);
  igual((await terreno(olga.page, lote)).version, version0, 'un archivo no cambia la versión del terreno');
});

await revisar('sube un KMZ con X/Y en blanco, elige entre candidatos, activa y ve el contorno real', async () => {
  const d = await abrirDetalle(olga.page, lote, NOMBRE);
  await subirEnDetalle(d, 'kmz', F.kmz_varios);
  igual(await faseFinal(d, 'kmz', ['requiere_seleccion', 'listo', 'rechazado', 'fallido']), 'requiere_seleccion', 'fase');
  await hasta(async () => (await textoCelda(olga.page, lote, 'core:kmz')) === 'KMZ sin contorno activo', 'celda sin activo');
  const k = d.locator('.archivos-detalle[data-tipo="kmz"]');
  await k.locator('.archivos-item').first().getByRole('button', { name: 'Versiones' }).click();
  await k.getByRole('button', { name: /Contornos de la versión 1/ }).click();
  await k.getByRole('button', { name: 'Elegir contornos…' }).click();
  const casillas = k.locator('.archivos-candidatos input[type=checkbox]:not([disabled])');
  await casillas.first().waitFor();
  const candidatos = await casillas.count();
  cierto(candidatos >= 2, `candidatos ${candidatos}`);
  await casillas.first().check();
  await k.getByRole('button', { name: 'Procesar selección' }).click();
  await k.locator('.archivos-mensaje', { hasText: 'Selección válida. Todavía no está activa' }).waitFor({ timeout: 60000 });
  igual((await terreno(olga.page, lote)).ubicacion.modo, 'ninguna', 'no se activa sola');
  await foto(olga.page, '02-kmz-candidatos-elegidos');
  await k.locator('.archivos-intento', { hasText: 'Contorno válido' }).getByRole('button', { name: 'Activar este contorno' }).click();
  await hasta(async () => (await textoCelda(olga.page, lote, 'core:kmz')) === 'Contorno activo', 'celda activo');
  await cerrarDetalle(olga.page, d);
  const t = await terreno(olga.page, lote);
  igual([t.ubicacion.modo, t.draft.lat, t.draft.lon, t.version], ['geometria', null, null, version0], 'contorno sin X/Y, versión intacta');
  // Same forbidden keys as tests/test_resumenes_terreno.py: no body, key, hash, URL or candidate in a row.
  const prohibidas = ['geojson', 'clave_final', 'clave_temporal', 'clave', 'sha256', 'sha256_geojson', 'candidatos', 'url', 'features', 'geometry'];
  const claves = (v) => (v && typeof v === 'object' ? Object.entries(v).flatMap(([k, x]) => [k, ...claves(x)]) : []);
  igual(claves(t).filter((k) => prohibidas.includes(k)), [], 'sin cuerpo ni claves en la fila');
  geometriaActiva = t.ubicacion.geometria.id;
  // The page map: only this terrain's body is loaded, on selection.
  igual(olga.api.filter((l) => l.includes('/api/archivos/geometrias/')).length, 0, 'nada se pide con el mapa cerrado');
  await abrirMapa(olga.page);
  await seleccionarEnTabla(olga.page, lote);   // already selected since its cells were edited: its load starts with the map
  await hasta(async () => /Contorno cargado/.test(await estadoMapa(olga.page)), 'contorno no cargado');
  await hasta(async () => (await olga.page.evaluate((i) => window.__araTabla.posicion(i), lote))?.contorno === true, 'sin contorno dibujado');
  const p = await olga.page.evaluate(() => window.__araTabla.previa());
  igual([p.cuerpos, p.cargando], [1, false], 'un cuerpo');
  cierto(p.zoom >= 15, `escala de parcela (zoom ${p.zoom})`);
  const cuerpos = olga.api.filter((l) => /\/api\/archivos\/geometrias\/[^/]+\/contenido/.test(l));
  cierto(cuerpos.length && cuerpos.every((l) => l.includes(`/geometrias/${geometriaActiva}/contenido`)), `sólo el cuerpo seleccionado: ${cuerpos}`);
  await esperar(700);
  await foto(olga.page, '03-contorno-real-en-mapa-de-pagina');
  return { candidatos, zoom: p.zoom };
});

await revisar('un reemplazo fallido conserva el último contorno utilizable', async () => {
  const d = await abrirDetalle(olga.page, lote, NOMBRE);
  await subirEnDetalle(d, 'kmz', F.kmz_invalido);
  igual(await faseFinal(d, 'kmz', ['rechazado', 'listo', 'fallido']), 'rechazado', 'fase');
  await cerrarDetalle(olga.page, d);
  const t = await terreno(olga.page, lote);
  igual([t.ubicacion.modo, t.ubicacion.geometria?.id, t.version], ['geometria', geometriaActiva, version0], 'contorno anterior');
  igual(await textoCelda(olga.page, lote, 'core:kmz'), 'Contorno activo', 'celda');
  await seleccionarEnTabla(olga.page, lote);
  await hasta(async () => /Contorno cargado/.test(await estadoMapa(olga.page)), 'el mapa sigue con el contorno');
});

if (!FOCALIZADO) {
  await revisar('selecciones rápidas en la página: sólo el último contorno se instala, un cuerpo retenido', async () => {
    // A second located terrain: X/Y and an auto-activated simple boundary, through the widget.
    const r = await llamar(olga.page, 'POST', `/api/maestra/bases/${base.id}/terrenos`,
      { terreno: VECINO, lat: 20.6015, lon: -100.398, superficie_m2: 1200 }, crypto.randomUUID());
    vecino = r.datos.terreno.id;
    await olga.page.getByRole('button', { name: 'Actualizar' }).click();
    await listo(olga.page);
    await fila(olga.page, vecino).waitFor();
    const d = await abrirDetalle(olga.page, vecino, VECINO);
    await subirEnDetalle(d, 'kmz', F.kmz_simple);
    igual(await faseFinal(d, 'kmz', ['listo', 'fallido', 'rechazado']), 'listo', 'fase');
    await cerrarDetalle(olga.page, d);
    await hasta(async () => (await textoCelda(olga.page, vecino, 'core:kmz')) === 'Contorno activo', 'vecino activo');
    // Count body requests in flight while the selection flips ten times.
    let enVuelo = 0, maximo = 0, respondidas = 0, canceladas = 0;
    const esCuerpo = (q) => /\/api\/archivos\/geometrias\/.*\/contenido/.test(q.url());
    olga.page.on('request', (q) => { if (esCuerpo(q)) { enVuelo += 1; maximo = Math.max(maximo, enVuelo); } });
    olga.page.on('requestfinished', (q) => { if (esCuerpo(q)) { enVuelo -= 1; respondidas += 1; } });
    olga.page.on('requestfailed', (q) => { if (esCuerpo(q)) { enVuelo -= 1; canceladas += 1; } });
    await olga.page.evaluate(([a, b]) => {
      for (let i = 0; i < 10; i += 1) {
        document.querySelector(`tr[data-id="${i % 2 ? b : a}"] td[data-col="core:terreno"]`).click();
      }
    }, [lote, vecino]);
    await hasta(async () => /Contorno cargado/.test(await estadoMapa(olga.page)), 'la última selección no cargó');
    const p = await olga.page.evaluate(() => window.__araTabla.previa());
    igual([p.cuerpos, p.cargando], [1, false], 'residencia final');
    igual(await olga.page.evaluate((i) => window.__araTabla.posicion(i)?.contorno, vecino), true, 'el último seleccionado tiene contorno');
    igual(await olga.page.evaluate((i) => window.__araTabla.posicion(i)?.contorno, lote), false, 'el anterior no retiene contorno');
    igual(await fila(olga.page, vecino).getAttribute('aria-selected'), 'true', 'selección en la tabla');
    cierto(maximo <= 1, `cuerpos en vuelo a la vez: ${maximo}`);
    return { selecciones: 10, maximo_en_vuelo: maximo, fragmentos_respondidos: respondidas, fragmentos_cancelados: canceladas };
  });

  await revisar('un archivo que termina mientras se edita una celda no toca el editor ni la versión', async () => {
    const ruta = `**/api/inventario/terrenos/${lote}`;
    let retenida = null;
    let liberar;
    const liberada = new Promise((r) => { liberar = r; });
    await olga.page.route(ruta, async (r) => {
      if (r.request().method() !== 'GET' || retenida) return r.continue();
      retenida = r;
      await liberada;                // the widget's refresh after completion waits here
      await r.continue();
    });
    try {
      const d = await abrirDetalle(olga.page, lote, NOMBRE);
      await subirEnDetalle(d, 'pdf', F.pdf2);
      igual(await faseFinal(d, 'pdf', ['listo', 'fallido']), 'listo', 'fase');
      await hasta(() => retenida, 'el widget no pidió el resumen');
      await cerrarDetalle(olga.page, d);
      // The person starts editing while that refresh is still out.
      await celda(olga.page, lote, 'core:municipio').dblclick();
      const editor = celda(olga.page, lote, 'core:municipio').locator('.tabla-editor');
      await editor.waitFor();
      await editor.fill('Municipio Editado Ficticio');
      await olga.page.keyboard.press('Shift+ArrowLeft');
      await olga.page.keyboard.press('Shift+ArrowLeft');
      liberar();
      await hasta(async () => (await textoCelda(olga.page, lote, 'core:archivos')) === '2 PDF', 'la celda no llegó a 2 PDF');
      await esperar(300);
      const e = await olga.page.evaluate(() => {
        const x = document.activeElement;
        return { clase: x.className, valor: x.value, sel: x.selectionEnd - x.selectionStart };
      });
      cierto(/tabla-editor/.test(e.clase), `foco perdido: ${e.clase}`);
      igual([e.valor, e.sel], ['Municipio Editado Ficticio', 2], 'editor intacto');
      await olga.page.keyboard.press('Enter');
      await olga.page.locator(`tr[data-id="${lote}"] td[data-col="core:municipio"]:not(.is-pendiente):not(.is-editando)`).waitFor();
      const t = await terreno(olga.page, lote);
      igual([t.draft.municipio, t.version, t.archivos.pdf_total], ['Municipio Editado Ficticio', version0 + 1, 2], 'guardado sin conflicto');
      version0 = t.version;
    } finally {
      liberar();
      await olga.page.unroute(ruta);
    }
  });

  await revisar('retirar el KMZ de un terreno con X/Y lo deja en su punto; el mapa lo dice', async () => {
    const d = await abrirDetalle(olga.page, vecino, VECINO);
    const k = d.locator('.archivos-detalle[data-tipo="kmz"]');
    await k.getByRole('button', { name: /^Retirar/ }).first().click();
    await olga.page.getByRole('dialog', { name: /Retirar/ }).getByRole('button', { name: 'Retirar' }).click();
    await hasta(async () => (await textoCelda(olga.page, vecino, 'core:kmz')) === 'Sin KMZ', 'celda tras retirar');
    await cerrarDetalle(olga.page, d);
    const t = await terreno(olga.page, vecino);
    igual([t.ubicacion.modo, t.ubicacion.geometria, t.draft.lat], ['punto', null, 20.6015], 'ubicación por X/Y');
    await seleccionarEnTabla(olga.page, lote);
    await seleccionarEnTabla(olga.page, vecino);
    await hasta(async () => /coordenadas X\/Y/.test(await estadoMapa(olga.page)), 'el mapa no dice X/Y');
    igual(await olga.page.evaluate((i) => window.__araTabla.posicion(i)?.contorno, vecino), false, 'sin contorno');
  });

  await revisar('un cuerpo cerca del límite (100,000 vértices) se sube, se carga y se dibuja sin recortes', async () => {
    const r = await llamar(olga.page, 'POST', `/api/maestra/bases/${base.id}/terrenos`, { terreno: 'Lote Límite Ficticio' }, crypto.randomUUID());
    const limite = r.datos.terreno.id;
    await olga.page.getByRole('button', { name: 'Actualizar' }).click();
    await listo(olga.page);
    const d = await abrirDetalle(olga.page, limite, 'Lote Límite Ficticio');
    const t0 = Date.now();
    await subirEnDetalle(d, 'kmz', F.kmz_limite);
    igual(await faseFinal(d, 'kmz', ['listo', 'fallido', 'rechazado', 'incierto'], 180000), 'listo', 'fase');
    const subida = Date.now() - t0;
    await cerrarDetalle(olga.page, d);
    await hasta(async () => (await textoCelda(olga.page, limite, 'core:kmz')) === 'Contorno activo', 'activo');
    // Start from a selection with no body (closing the detail may have selected this row).
    await seleccionarEnTabla(olga.page, vecino);
    await hasta(async () => /coordenadas X\/Y/.test(await estadoMapa(olga.page)), 'vecino X/Y');
    const cdp = await olga.contexto.newCDPSession(olga.page);
    await cdp.send('HeapProfiler.collectGarbage');
    const heap = async () => (await cdp.send('Runtime.getHeapUsage')).usedSize;
    const antes = await heap();
    let pico = antes;
    const vigia = setInterval(async () => { try { pico = Math.max(pico, await heap()); } catch { /* closed */ } }, 25);
    let bytes = 0, fragmentos = 0;
    const contar = async (r) => {
      if (!/\/api\/archivos\/geometrias\/.*\/contenido/.test(r.url())) return;
      fragmentos += 1;
      bytes += (await r.body().catch(() => Buffer.alloc(0))).length;
    };
    olga.page.on('response', contar);
    const t1 = Date.now();
    await seleccionarEnTabla(olga.page, limite);
    await hasta(async () => /Contorno cargado/.test(await estadoMapa(olga.page)), 'cuerpo grande no cargado', 60000);
    const carga = Date.now() - t1;
    clearInterval(vigia);
    // Its 20,000 parts spread wider than one parcel: framed whole, each part is
    // a symbol; the renderer's own "to scale" step shows the outline itself.
    const zoomEncuadre = (await olga.page.evaluate(() => window.__araTabla.previa())).zoom;
    await olga.page.getByRole('button', { name: 'Ver a escala' }).click();
    await hasta(async () => (await olga.page.evaluate((i) => window.__araTabla.posicion(i)?.contorno, limite)) === true, 'no se dibuja como contorno');
    const zoom = { encuadre: zoomEncuadre, a_escala: (await olga.page.evaluate(() => window.__araTabla.previa())).zoom };
    olga.page.off('response', contar);
    // Another selection drops it; the heap returns near where it was.
    await seleccionarEnTabla(olga.page, lote);
    await hasta(async () => /Contorno cargado/.test(await estadoMapa(olga.page)), 'vuelta al lote');
    await seleccionarEnTabla(olga.page, vecino);
    await esperar(300);
    await cdp.send('HeapProfiler.collectGarbage');
    const despues = await heap();
    const mib = (x) => Math.round((x / 1048576) * 10) / 10;
    medidas.limite = { subida_ms: subida, seleccion_a_dibujado_ms: carga, zoom, fragmentos, bytes_de_fragmentos: bytes, heap_mib: { antes: mib(antes), pico: mib(pico), despues: mib(despues) } };
    await foto(olga.page, '04-cuerpo-de-100000-vertices');
    return medidas.limite;
  });
}

const omar = await abrir('omar');
await irATabla(omar.page);

await revisar('otra sesión autorizada lee los mismos archivos guardados y el mismo contorno', async () => {
  await fila(omar.page, lote).waitFor();
  await hasta(async () => /PDF/.test(await textoCelda(omar.page, lote, 'core:archivos')), 'celda PDF');
  igual(await textoCelda(omar.page, lote, 'core:kmz'), 'Contorno activo', 'celda KMZ');
  const d = await abrirDetalle(omar.page, lote, NOMBRE);
  const item = d.locator('.archivos-detalle[data-tipo="pdf"] .archivos-item', { hasText: 'Avalúo ficticio.pdf' });
  const [descarga] = await Promise.all([omar.page.waitForEvent('download'), item.getByRole('button', { name: /^Descargar/ }).click()]);
  igual(sha(readFileSync(await descarga.path())), sha(readFileSync(F.pdf)), 'sha256');
  await cerrarDetalle(omar.page, d);
  await abrirMapa(omar.page);
  await seleccionarEnTabla(omar.page, lote);
  await hasta(async () => /Contorno cargado/.test(await estadoMapa(omar.page)), 'contorno');
  cierto(omar.api.some((l) => l.includes(`/api/archivos/geometrias/${geometriaActiva}/contenido`) && l.endsWith(' 200')), 'el mismo contorno');
});

const otto = await abrir('otto');
await revisar('una cuenta sin permiso es rechazada y no recibe contenido', async () => {
  await otto.page.goto(`${URLBASE}/?test=1#/tabla`);
  await esperar(1500);
  igual(await otto.page.locator('tr[data-id]').count(), 0, 'filas');
  igual(await otto.page.getByText(NOMBRE).count(), 0, 'nombre visible');
  const archivo = (await llamar(omar.page, 'GET', `/api/inventario/terrenos/${lote}/archivos`)).datos.archivos.find((a) => a.tipo === 'pdf');
  const r = await otto.page.evaluate(async ([t, g, a]) => {
    const st = async (ruta, o) => (await fetch(ruta, o)).status;
    return {
      terreno: await st(`/api/inventario/terrenos/${t}`),
      archivos: await st(`/api/inventario/terrenos/${t}/archivos`),
      versiones: await st(`/api/archivos/${a}/versiones`),
      fragmento: await st(`/api/archivos/geometrias/${g}/contenido?desde=0`),
    };
  }, [lote, geometriaActiva, archivo.id]);
  igual(r, { terreno: 404, archivos: 404, versiones: 404, fragmento: 404 }, 'denegado');
});

await revisar('reinicio del servidor sobre la misma base y el mismo almacén: bytes, hash e historial siguen', async () => {
  await detener();
  await arrancar();
  const s = await abrir('omar');
  await irATabla(s.page);
  await fila(s.page, lote).waitFor();
  const lista = (await llamar(s.page, 'GET', `/api/inventario/terrenos/${lote}/archivos`)).datos.archivos;
  const pdf = lista.find((a) => a.tipo === 'pdf');
  const versiones = (await llamar(s.page, 'GET', `/api/archivos/${pdf.id}/versiones`)).datos.versiones;
  const d = await abrirDetalle(s.page, lote, NOMBRE);
  const item = d.locator('.archivos-detalle[data-tipo="pdf"] .archivos-item', { hasText: 'Avalúo ficticio.pdf' });
  const [descarga] = await Promise.all([s.page.waitForEvent('download'), item.getByRole('button', { name: /^Descargar/ }).click()]);
  igual(sha(readFileSync(await descarga.path())), sha(readFileSync(F.pdf)), 'sha256 tras reiniciar');
  await cerrarDetalle(s.page, d);
  await abrirMapa(s.page);
  await seleccionarEnTabla(s.page, lote);
  await hasta(async () => /Contorno cargado/.test(await estadoMapa(s.page)), 'contorno tras reiniciar');
  igual((await terreno(s.page, lote)).ubicacion.geometria.id, geometriaActiva, 'misma geometría activa');
  await s.contexto.close();
  return { arranques, archivos: lista.length, versiones_pdf: versiones.length };
});

// The old sessions belong to the stopped process only if sessions were in memory;
// they are in the database, so they still work. Reload them on the new process.
for (const s of [olga, omar]) await irATabla(s.page);

if (!FOCALIZADO) {
  await revisar('se revoca el acceso mientras se leen los fragmentos del contorno: nada se instala y la fila se va', async () => {
    await abrirMapa(omar.page);
    await seleccionarEnTabla(omar.page, vecino);         // X/Y only now: no body held
    let soltar;
    const suelto = new Promise((r) => { soltar = r; });
    let retenidos = 0;
    await omar.page.route('**/api/archivos/geometrias/*/contenido*', async (r) => { retenidos += 1; await suelto; await r.continue(); });
    await seleccionarEnTabla(omar.page, lote);
    await hasta(() => retenidos > 0, 'no se pidió el fragmento');
    const adm = await abrir('ada');
    const actual = (await llamar(adm.page, 'GET', `/api/maestra/bases/${base.id}/acceso`)).datos;
    igual((await llamar(adm.page, 'PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: actual.base.version, usuarios: [ids.olga] })).status, 200, 'revocar');
    await adm.contexto.close();
    soltar();
    await hasta(async () => (await omar.page.locator('tr[data-id]').count()) === 0, 'las filas siguen');
    await esperar(800);
    const p = await omar.page.evaluate(() => window.__araTabla?.previa());
    igual(p?.cuerpos ?? 0, 0, 'cuerpo retenido');
    igual(await omar.page.getByText(NOMBRE).count(), 0, 'nombre visible');
    cierto(!/Contorno cargado/.test(await estadoMapa(omar.page)), 'contorno anunciado');
    await omar.page.unroute('**/api/archivos/geometrias/*/contenido*');
    await foto(omar.page, '05-revocado-durante-lectura');
  });

  await revisar('se transfiere el terreno mientras se descarga: no llega el archivo y el detalle se cierra', async () => {
    const d = await abrirDetalle(olga.page, lote, NOMBRE);
    let soltar;
    const suelto = new Promise((r) => { soltar = r; });
    let retenida = false;
    await olga.page.route('**/api/archivos/versiones/*/descarga', async (r) => {
      if (r.request().method() !== 'GET') return r.continue();
      retenida = true; await suelto; await r.continue();
    });
    let descargas = 0;
    olga.page.on('download', () => { descargas += 1; });
    const item = d.locator('.archivos-detalle[data-tipo="pdf"] .archivos-item', { hasText: 'Avalúo ficticio.pdf' });
    await item.getByRole('button', { name: /^Descargar/ }).click();
    await hasta(() => retenida, 'la descarga no salió');
    const adm = await abrir('ada');
    const t = await terreno(adm.page, lote);
    const mov = await llamar(adm.page, 'POST', `/api/inventario/terrenos/${lote}/transferir`, { expected_version: t.version, base_id: ajena.id });
    igual(mov.status, 200, JSON.stringify(mov.datos));
    await adm.contexto.close();
    soltar();
    await hasta(async () => (await fila(olga.page, lote).count()) === 0, 'la fila sigue');
    await hasta(async () => (await olga.page.locator('dialog[open]').count()) === 0, 'el detalle sigue abierto');
    await esperar(1500);
    igual(descargas, 0, 'descarga entregada');
    igual(await olga.page.getByText('Avalúo ficticio.pdf').count(), 0, 'nombre visible');
    await olga.page.unroute('**/api/archivos/versiones/*/descarga');
  });

  await revisar('la sesión expira durante una subida: todo se desmonta y nada se repuebla después', async () => {
    const d = await abrirDetalle(olga.page, vecino, VECINO);
    const cdp = await olga.contexto.newCDPSession(olga.page);
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: 48 * 1024 });
    await subirEnDetalle(d, 'kmz', F.kmz_limite);
    await hasta(async () => (await d.locator('.archivos-detalle[data-tipo="kmz"] .archivos-subida').last().getAttribute('data-fase')) === 'subiendo', 'no empezó a subir');
    // The session ends at the server (sign-out from another tab of the same account).
    const otra = await olga.contexto.newPage();
    await otra.goto(`${URLBASE}/?test=1`);
    await otra.evaluate(() => fetch('/api/logout', { method: 'POST' }));
    await otra.close();
    const peticiones = [];
    olga.page.on('request', (q) => { if (/completar|contenido|metadatos/.test(q.url())) peticiones.push(q.url()); });
    await hasta(async () => (await olga.page.locator('.tabla-pantalla').count()) === 0, 'la tabla sigue montada', 60000);
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await olga.page.evaluate(() => {
      window.__mutaciones = 0;
      new MutationObserver((m) => { window.__mutaciones += m.filter((x) => x.target.closest?.('.archivos-detalle, .tabla-pantalla, dialog')).length; })
        .observe(document.body, { subtree: true, childList: true, characterData: true });
    });
    await esperar(3000);
    const r = await olga.page.evaluate(() => ({ mutaciones: window.__mutaciones,
      privado: document.querySelectorAll('.archivos-detalle, .archivos-celda, dialog[open] .archivos-detalle, tr[data-id]').length }));
    igual(r.privado, 0, 'contenido privado en el DOM');
    igual(r.mutaciones, 0, 'instalaciones tardías');
    igual(peticiones.filter((u) => /completar/.test(u)), [], 'completar tras expirar');
    await foto(olga.page, '06-expirada-durante-subida');
  });
}

for (const s of sesiones) {
  await revisar(`sin errores de página (${s.usuario})`, async () => igual(s.errores, [], 'errores'));
}

await navegador.close();
await detener().catch(() => {});
limpiar();
const resumen = { bd: BD, focalizado: FOCALIZADO, arranques, total: resultados.length, fallos, medidas, resultados };
if (EVID) { mkdirSync(EVID, { recursive: true }); writeFileSync(join(EVID, `recorrido-${BD}.json`), JSON.stringify(resumen, null, 2)); }
console.log(`\n${resultados.length - fallos}/${resultados.length} recorridos correctos (${BD})`);
process.exit(fallos ? 1 : 0);

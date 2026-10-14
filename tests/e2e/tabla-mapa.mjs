/* Tabla / Mapa for administrators and operators, with the REAL widgets,
 * geometry loader and renderer, the real local server
 * (tests/e2e/tabla_servidor.py on a folder it creates and deletes), real
 * sessions and Chromium. Fictional accounts, terrains and files only, at the
 * pilot's volume (a little over 100 terrains in one base).
 *
 *   cd tests/e2e && node tabla-mapa.mjs
 *
 * Checks: the administrator lands on the master table and "Inventario" is not
 * in the menu; both roles switch Tabla / Mapa and come back with their base,
 * filters, page and selection; the map holds every terrain of the view and
 * its filters (beyond the grid's page) and gathers it once; an operator never
 * receives another base's rows or boundaries; a terrain with an active
 * boundary and no X/Y is on the map and its outline loads when its circle is
 * clicked; different circles load their own outline, one body at most; quick
 * changes of selection, filters and base leave no earlier outline; switching
 * views many times does not pile up maps or bodies; loading, error, empty and
 * no-location states are said; the old inventory address lands somewhere
 * equivalent. Optional: MAPA_CAPTURAS=dir (screenshots), CHROMIUM=/path,
 * MAPA_PUERTO.
 */

import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.MAPA_PUERTO ?? 8482);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.MAPA_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-mapa-'));
const F = JSON.parse(execFileSync(PY, ['-c',
  'import json, sys\nfrom pathlib import Path\nsys.path.insert(0, "tests/e2e")\n' +
  'from archivos_servidor import escribir_fixtures\n' +
  'd = Path(sys.argv[1]); d.mkdir()\nprint(json.dumps(escribir_fixtures(d)))', join(CARPETA, 'fixtures')],
  { cwd: RAIZ, encoding: 'utf8' }));

// A server left on this port by another run would answer instead of this one's.
if (await fetch(`${URLBASE}/api/config`).then(() => true, () => false)) throw new Error(`El puerto ${PUERTO} ya está en uso.`);
const servidor = spawn(PY, [join(AQUI, 'tabla_servidor.py'), '--puerto', String(PUERTO), '--carpeta', join(CARPETA, 'instalacion')],
  { cwd: RAIZ, stdio: ['ignore', 'pipe', 'ignore'] });
await new Promise((resolve, reject) => {
  let texto = '';
  servidor.stdout.on('data', (d) => { texto += d; if (/LISTO/.test(texto)) resolve(); });
  servidor.on('exit', (c) => reject(new Error(`el servidor salió (${c}): ${texto}`)));
});

/* ------------------------------------------------------------ harness */

let fallos = 0;
const medidas = {};
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
    if (Date.now() > fin) throw new Error(mensaje);
    await esperar(60);
  }
}

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium' });
const sesiones = [];
async function abrir(usuario) {
  const contexto = await navegador.newContext({ viewport: { width: 1500, height: 900 }, locale: 'es-MX' });
  contexto.setDefaultTimeout(30000);
  const page = await contexto.newPage();
  const s = { usuario, page, errores: [], api: [] };
  page.on('pageerror', (e) => s.errores.push(String(e)));
  page.on('request', (r) => { if (r.url().includes('/api/')) s.api.push(`${r.method()} ${new URL(r.url()).pathname}${new URL(r.url()).search}`); });
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  await page.goto(`${URLBASE}/?test=1`);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click().catch(() => {});
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVE);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
  sesiones.push(s);
  return s;
}
const llamar = (page, metodo, ruta, cuerpo) => page.evaluate(async ([m, r, c]) => {
  const res = await fetch(r, { method: m, headers: c ? { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() } : {},
    body: c ? JSON.stringify(c) : undefined });
  return { status: res.status, datos: await res.json().catch(() => null) };
}, [metodo, ruta, cuerpo ?? null]);
const terreno = async (page, id) => (await llamar(page, 'GET', `/api/inventario/terrenos/${id}`)).datos?.terreno;

const listo = (page) => page.locator('.tabla-lienzo:not([aria-busy])').waitFor({ state: 'attached' });
const mapa = (page) => page.evaluate(() => window.__araTabla?.mapa());
const previa = (page) => page.evaluate(() => window.__araTabla?.previa());
const posicion = (page, id) => page.evaluate((i) => window.__araTabla?.posicion(i), id);
const reuniones = (s) => s.api.filter((l) => /\/terrenos\?.*limit=200/.test(l)).length;
const cuerposPedidos = (s) => s.api.filter((l) => /\/api\/archivos\/geometrias\/[^/]+\/contenido/.test(l));
const modoBoton = (page, nombre) => page.locator('.tabla-modo').getByRole('button', { name: nombre, exact: true });
const foto = async (page, nombre) => { if (SHOTS) { await esperar(400); await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); } };

async function irA(page, vista, modo = null) {
  await page.goto(`${URLBASE}/?test=1#/tabla/${vista}${modo ? '/mapa' : ''}`);
  await page.locator('.tabla-pantalla').waitFor();
  await listo(page);
}
async function aMapa(page) {
  await modoBoton(page, 'Mapa').click();
  await page.locator('.previa-mapa.leaflet-container').waitFor();
  await hasta(async () => { const m = await mapa(page); return m && !m.reuniendo && m.clave; }, 'el mapa no reunió su conjunto');
}
async function aTabla(page) {
  await modoBoton(page, 'Tabla').click();
  await page.locator('.tabla-lienzo').waitFor();
}
/** A real click on a terrain's symbol on the map. The fictional KMZ fixtures
 * all lie in the same place, so the map is first zoomed in (mouse wheel) on
 * the symbol until no other boundary is within reach of the click. A symbol
 * under the legend and basemap overlay is first panned out from under it
 * (keyboard): the overlay takes the wheel and the click, as on the old map. */
let cercanos = [];
async function alCentro(page, caja, id) {
  let movido = false;
  for (let n = 0; n < 30; n += 1) {
    const p = await posicion(page, id);
    const sobre = await page.locator('.previa-sobre-mapa').boundingBox();
    const dentro = p && sobre && caja.x + p.x <= sobre.x + sobre.width + 30 && caja.y + p.y >= sobre.y - 30;
    if (!dentro) return movido;
    // Leaflet's keyboard panning moves the content without touching any symbol.
    await page.locator('.previa-mapa').focus();
    await page.keyboard.press('ArrowLeft');
    await page.keyboard.press('ArrowDown');
    await esperar(250);
    movido = true;
  }
  return movido;
}
async function clicEnMapa(page, id) {
  const caja = await page.locator('.previa-mapa').boundingBox();
  for (let i = 0; ; i += 1) {
    let p = await hasta(async () => posicion(page, id), `el terreno ${id} no está en el mapa`);
    if (await alCentro(page, caja, id)) p = await hasta(async () => posicion(page, id), `el terreno ${id} no está en el mapa`);
    const otros = (await Promise.all(cercanos.filter((o) => o !== id).map((o) => posicion(page, o)))).filter(Boolean);
    if (i >= 12 || otros.every((o) => Math.hypot(o.x - p.x, o.y - p.y) > 24)) {
      await page.mouse.click(caja.x + p.x, caja.y + p.y);
      return;
    }
    await page.mouse.move(caja.x + p.x, caja.y + p.y);
    await page.mouse.wheel(0, -400);
    await esperar(450);
  }
}
// Basemap changes must preserve the selected boundary and avoid data reloads.
async function comprobarFondos(s, id) {
  const { page } = s;
  const antes = { mapa: await mapa(page), previa: await previa(page), api: s.api.length };
  for (const [nombre, key] of [['Satélite', 'satelite'], ['Calles', 'calles'], ['Claro', 'claro'], ['Satélite', 'satelite']]) {
    await page.getByRole('radio', { name: nombre, exact: true }).click();
    igual(await page.locator('.previa-mapa').getAttribute('data-basemap'), key, 'fondo aplicado');
    igual(await page.getByRole('radio', { name: nombre, exact: true }).getAttribute('aria-checked'), 'true', 'selector');
    igual(await mapa(page), antes.mapa, 'mismos terrenos y selección');
    igual(await previa(page), antes.previa, 'mismo contorno y zoom');
    igual((await posicion(page, id))?.contorno, true, 'contorno visible');
  }
  igual(s.api.length, antes.api, 'cambiar fondo no pide datos ni geometrías');
  await aTabla(page);
  await aMapa(page);
  igual(await page.locator('.previa-mapa').getAttribute('data-basemap'), 'satelite', 'fondo conservado al volver');
  igual((await mapa(page)).seleccion, id, 'selección conservada');
  igual((await previa(page)).cuerpos, 1, 'un contorno');
}

/** The table's query controls are shown in Tabla only (issue #40): from the
 * map, change one there and come back to the map. */
const enMapa = async (page) => (await modoBoton(page, 'Mapa').getAttribute('aria-pressed')) === 'true';
async function enLaTabla(page, fn) {
  const volver = await enMapa(page);
  if (volver) await aTabla(page);
  await fn();
  if (volver) await aMapa(page);
}
async function filtrar(page, selector, valor) {
  await enLaTabla(page, async () => {
    await page.locator(selector).selectOption(valor);
    await listo(page);
  });
}
const buscarEnTabla = (page, texto) => enLaTabla(page, () => page.locator('#tabla-buscar').fill(texto));
async function subirKmzEnCelda(page, id, ruta) {
  const boton = page.locator(`tr[data-id="${id}"] td[data-col="core:kmz"] .archivos-celda-elegir`);
  await boton.waitFor();
  const [selector] = await Promise.all([page.waitForEvent('filechooser'), boton.click()]);
  await selector.setFiles({ name: ruta.split('/').at(-1), buffer: readFileSync(ruta), mimeType: 'application/vnd.google-earth.kmz' });
  await hasta(async () => /Contorno activo/.test(await page.locator(`tr[data-id="${id}"] td[data-col="core:kmz"] .archivos-celda`).innerText().catch(() => '')),
    'el KMZ no quedó activo', 120000);
}

/* --------------------------------------------------------------- data */

const ada = await abrir('ada');
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Mapa Ficticia' })).datos.base;
const ajena = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Ajena Mapa Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
igual((await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] })).status, 200, 'acceso');
igual((await admin('PUT', `/api/maestra/bases/${ajena.id}/acceso`, { expected_version: ajena.version, usuarios: [ops.omar] })).status, 200, 'acceso ajena');
const crear = async (b, campos) => (await admin('POST', `/api/maestra/bases/${b.id}/terrenos`, campos)).datos.terreno.id;

// 100 points spread over a grid (X is latitude, Y longitude), 8 without any location,
// and 3 that get a boundary and no X/Y: 111 in the base, more than one page of 50 or 100.
const puntos = [];
for (let i = 0; i < 100; i += 1) {
  puntos.push(await crear(base, { terreno: `Lote Mapa ${String(i).padStart(3, '0')} Ficticio`,
    estado: i % 2 ? 'Sonora' : 'Jalisco', lat: 18 + (i % 10) * 0.8, lon: -108 + Math.floor(i / 10) * 1.1 }));
}
const sinUbicacion = [];
for (let i = 0; i < 8; i += 1) sinUbicacion.push(await crear(base, { terreno: `Lote Sin Ubicación ${i} Ficticio`, estado: 'Jalisco' }));
const conContorno = await crear(base, { terreno: 'Lote Contorno Sin XY Ficticio', estado: 'Sonora' });
const conContorno2 = await crear(base, { terreno: 'Lote Contorno U Ficticio', estado: 'Sonora' });
const conLimite = await crear(base, { terreno: 'Lote Contorno Grande Ficticio', estado: 'Jalisco' });
const TODOS = [...puntos, ...sinUbicacion, conContorno, conContorno2, conLimite];
cercanos = [conContorno, conContorno2, conLimite];
let activos = TODOS;              // what the base's active list holds (one is archived below)
const deAjena = [];
for (let i = 0; i < 5; i += 1) deAjena.push(await crear(ajena, { terreno: `Lote Ajeno ${i} Ficticio`, estado: 'Sonora', lat: 25, lon: -99 + i * 0.5 }));

/* ----------------------------------------------------------- journeys */

await revisar('administrador: entra a la tabla maestra y «Inventario» ya no está en el menú', async () => {
  await ada.page.goto(`${URLBASE}/?test=1`);
  await ada.page.locator('.tabla-pantalla').waitFor();
  await hasta(async () => /#\/tabla\/maestra$/.test(ada.page.url()), `dirección ${ada.page.url()}`);
  const menu = await ada.page.locator('nav.nav .nav-item').allInnerTexts();
  cierto(!menu.includes('Inventario'), `menú: ${menu}`);
  cierto(menu.includes('Tabla maestra'), `menú: ${menu}`);
  igual(await modoBoton(ada.page, 'Tabla').getAttribute('aria-pressed'), 'true', 'Tabla activo');
  igual(await ada.page.getByRole('button', { name: 'Mapa de esta página' }).count(), 0, 'botón anterior');
});

await revisar('administrador: los contornos se cargan con «Elegir KMZ…» desde las celdas (convivencia con #33)', async () => {
  await irA(ada.page, base.id);
  for (const [id, ruta] of [[conContorno, F.kmz_simple], [conContorno2, F.kmz_reemplazo], [conLimite, F.kmz_limite]]) {
    const nombre = (await terreno(ada.page, id)).draft.terreno;
    await ada.page.locator('#tabla-buscar').fill(nombre);
    await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) === 1, 'búsqueda');
    await subirKmzEnCelda(ada.page, id, ruta);
    const t = await terreno(ada.page, id);
    igual([t.ubicacion.modo, t.draft.lat, t.draft.lon], ['geometria', null, null], `contorno sin X/Y (${nombre})`);
  }
  await ada.page.locator('#tabla-buscar').fill('');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) > 1, 'sin búsqueda');
  await listo(ada.page);
});

await revisar('administrador: el mapa reúne TODOS los terrenos de la base, más allá de la página, una sola vez', async () => {
  await filtrar(ada.page, '#tabla-limite', '50');
  const pagina = await ada.page.locator('tr.tabla-fila').evaluateAll((f) => f.map((x) => x.dataset.id));
  igual(pagina.length, 50, 'página de 50');
  const antes = reuniones(ada);
  const t0 = Date.now();
  await aMapa(ada.page);
  medidas.reunir_111_ms = Date.now() - t0;
  cierto(/#\/tabla\/[^/]+\/mapa$/.test(ada.page.url()), `dirección ${ada.page.url()}`);
  const m = await mapa(ada.page);
  igual([m.filas.length, m.total, m.incompleto], [TODOS.length, TODOS.length, false], 'conjunto');
  igual([...m.filas].sort(), [...TODOS].sort(), 'mismos terrenos');
  cierto(m.filas.some((id) => !pagina.includes(id)), 'debe incluir terrenos fuera de la página');
  igual(reuniones(ada) - antes, 1, 'una reunión (111 < 200 por página)');
  // The counts live in the filters panel (filtered) and the legend (placed / not placed), once.
  cierto(/111 terrenos de 111/.test(await ada.page.locator('.mapa-tabla-rail .rail-result').innerText()), 'filtrados en el panel');
  const leyenda = await ada.page.locator('.previa .legend').innerText();
  cierto(/103 terrenos/.test(leyenda) && /8 terrenos fuera del mapa/.test(leyenda), `leyenda: ${leyenda}`);
  igual(await ada.page.locator('.previa-cuenta, .previa-pie, .tabla-pie:visible').count(), 0, 'sin cuentas repetidas arriba ni abajo');
  igual((await previa(ada.page)).cuerpos, 0, 'ningún cuerpo sin selección');
  for (const id of [conContorno, puntos[99]]) cierto(await posicion(ada.page, id), `${id} dibujado`);
  for (const id of sinUbicacion) igual(await posicion(ada.page, id), null, 'sin ubicación no se dibuja');
  await foto(ada.page, '01-administrador-mapa');
});

await revisar('administrador: el círculo de un terreno sin X/Y carga su contorno activo; otro círculo, el suyo', async () => {
  const antes = cuerposPedidos(ada).length;
  await clicEnMapa(ada.page, conContorno);
  await hasta(async () => (await posicion(ada.page, conContorno))?.contorno === true, 'sin contorno');
  igual((await mapa(ada.page)).seleccion, conContorno, 'selección');
  const g1 = (await terreno(ada.page, conContorno)).ubicacion.geometria.id;
  cierto(cuerposPedidos(ada).slice(antes).every((l) => l.includes(`/geometrias/${g1}/`)), 'sólo su cuerpo');
  await foto(ada.page, '02-administrador-contorno-seleccionado');
  await comprobarFondos(ada, conContorno);
  await ada.page.getByRole('button', { name: 'Encuadrar todo' }).click();
  await esperar(500);
  await clicEnMapa(ada.page, conContorno2);
  await hasta(async () => (await posicion(ada.page, conContorno2))?.contorno === true, 'sin el segundo contorno');
  igual((await posicion(ada.page, conContorno))?.contorno, false, 'el anterior no retiene contorno');
  igual((await previa(ada.page)).cuerpos, 1, 'un cuerpo');
  await ada.page.getByRole('button', { name: 'Encuadrar todo' }).click();
  await esperar(500);
  await clicEnMapa(ada.page, puntos[5]);
  await hasta(async () => (await mapa(ada.page)).seleccion === puntos[5], 'selección de punto');
  igual((await previa(ada.page)).cuerpos, 0, 'un punto no tiene cuerpo');
  cierto(/X\/Y/.test(await ada.page.locator('.previa-estado').innerText()), 'dice que es por X/Y');
});

await revisar('administrador: KMZ grande del fixture, seleccionado desde el mapa (tiempo)', async () => {
  await ada.page.getByRole('button', { name: 'Encuadrar todo' }).click();
  await esperar(500);
  const t0 = Date.now();
  await clicEnMapa(ada.page, conLimite);
  await hasta(async () => (await mapa(ada.page)).seleccion === conLimite && (await previa(ada.page)).cuerpos === 1
    && /Contorno activo cargado/.test(await ada.page.locator('.previa-estado').innerText()), 'sin contorno grande', 120000);
  medidas.contorno_limite_ms = Date.now() - t0;
  // Drawn as an outline once the map is at the terrain's scale.
  await ada.page.getByRole('button', { name: 'Ver a escala' }).click();
  await hasta(async () => (await posicion(ada.page, conLimite))?.contorno === true, 'no se dibuja a escala');
  medidas.contorno_limite_a_escala_ms = Date.now() - t0;
});

await revisar('Tabla ⇄ Mapa conserva base, filtros, página y selección sin volver a reunir', async () => {
  await aTabla(ada.page);
  await ada.page.getByRole('button', { name: 'Siguiente' }).click();
  await listo(ada.page);
  const cuenta = await ada.page.locator('.tabla-cuenta').innerText();
  cierto(/^51–100 de 111$/.test(cuenta), `página 2: ${cuenta}`);
  const antes = reuniones(ada);
  const sel = (await mapa(ada.page)).seleccion;
  for (let i = 0; i < 6; i += 1) {
    await aMapa(ada.page);
    await aTabla(ada.page);
  }
  igual(await ada.page.locator('.tabla-cuenta').innerText(), cuenta, 'misma página');
  igual(await ada.page.locator('#tabla-vista').inputValue(), base.id, 'misma base');
  igual(reuniones(ada) - antes, 0, 'alternar no vuelve a reunir');
  igual((await mapa(ada.page)).seleccion, sel, 'misma selección');
  igual(await ada.page.locator('.leaflet-container').count(), 1, 'un solo mapa');
  igual((await previa(ada.page)).cuerpos <= 1, true, 'a lo más un cuerpo');
  await aMapa(ada.page);
  igual((await mapa(ada.page)).seleccion, sel, 'la selección sigue en el mapa');
  await hasta(async () => (await previa(ada.page)).cuerpos === 1, 'el contorno seleccionado sigue cargado');
});

await revisar('los filtros acotan el mapa; un filtro sin resultados y «sin ubicación» se dicen', async () => {
  await filtrar(ada.page, '#tabla-estado', 'Sonora');
  await hasta(async () => { const m = await mapa(ada.page); return !m.reuniendo && m.clave?.includes('Sonora'); }, 'no se reunió con el filtro');
  const m = await mapa(ada.page);
  const esperados = [...puntos.filter((_, i) => i % 2), conContorno, conContorno2];
  igual([...m.filas].sort(), [...esperados].sort(), 'sólo Sonora');
  igual(m.seleccion === null || esperados.includes(m.seleccion), true, 'selección válida');
  if (!esperados.includes(conLimite)) igual((await posicion(ada.page, conLimite)), null, 'el de Jalisco ya no está');
  cierto((await previa(ada.page)).cuerpos === 0 || esperados.includes(m.seleccion), 'sin cuerpo de fuera del filtro');
  await aTabla(ada.page);
  igual(await ada.page.locator('#tabla-estado').inputValue(), 'Sonora', 'el filtro sigue en la tabla');
  await aMapa(ada.page);
  await buscarEnTabla(ada.page, 'nada coincide con esto');
  await hasta(async () => (await mapa(ada.page)).filas.length === 0 && /Ningún terreno coincide/.test(await ada.page.locator('.tabla-mapa-aviso').innerText()), 'estado vacío');
  // The empty-set notice floats over the map, not in a strip of its own.
  const aviso = await ada.page.locator('.tabla-mapa-aviso').boundingBox();
  const lienzo = await ada.page.locator('.previa-mapa').boundingBox();
  cierto(aviso.y >= lienzo.y && aviso.y + aviso.height <= lienzo.y + lienzo.height, 'aviso sobre el mapa');
  await buscarEnTabla(ada.page, '');
  await filtrar(ada.page, '#tabla-estado', '');
  await hasta(async () => (await mapa(ada.page)).filas.length === TODOS.length, 'vuelve al total');
});

await revisar('cambios rápidos de selección, filtros y base no dejan un contorno anterior', async () => {
  // A slow body: each boundary answer waits, so later choices overtake it.
  await ada.page.route('**/api/archivos/geometrias/*/contenido*', async (r) => { await esperar(700); await r.continue(); });
  await ada.page.getByRole('button', { name: 'Encuadrar todo' }).click();
  await esperar(500);
  await clicEnMapa(ada.page, conContorno);
  await clicEnMapa(ada.page, conContorno2);
  await hasta(async () => (await posicion(ada.page, conContorno2))?.contorno === true, 'sin el último contorno');
  await esperar(1000);
  igual((await posicion(ada.page, conContorno))?.contorno, false, 'el primero no llegó a dibujarse');
  igual((await previa(ada.page)).cuerpos, 1, 'un cuerpo');
  // A filter that excludes the selected one while its body is still on the way.
  await ada.page.getByRole('button', { name: 'Encuadrar todo' }).click();
  await esperar(500);
  await clicEnMapa(ada.page, conContorno);
  await filtrar(ada.page, '#tabla-estado', 'Jalisco');
  await hasta(async () => { const m = await mapa(ada.page); return !m.reuniendo && m.clave?.includes('Jalisco'); }, 'filtro');
  await esperar(1200);
  igual(await posicion(ada.page, conContorno), null, 'el de Sonora no se dibuja');
  igual((await previa(ada.page)).cuerpos, 0, 'ningún cuerpo de otro filtro');
  // Another base while a body is on the way: nothing of the first base remains.
  await filtrar(ada.page, '#tabla-estado', '');
  await hasta(async () => (await mapa(ada.page)).filas.length === TODOS.length, 'total');
  await ada.page.getByRole('button', { name: 'Encuadrar todo' }).click();
  await esperar(500);
  await clicEnMapa(ada.page, conContorno2);
  await ada.page.locator('#tabla-vista').selectOption(ajena.id);
  await hasta(async () => { const m = await mapa(ada.page); return !m.reuniendo && m.clave?.startsWith(ajena.id); }, 'otra base');
  await esperar(1200);
  const m = await mapa(ada.page);
  igual([...m.filas].sort(), [...deAjena].sort(), 'sólo la otra base');
  igual([m.seleccion, (await previa(ada.page)).cuerpos], [null, 0], 'sin selección ni cuerpo');
  igual(await posicion(ada.page, conContorno2), null, 'nada de la base anterior');
  igual(/\/mapa$/.test(ada.page.url()), true, 'sigue en el mapa');
  await ada.page.unroute('**/api/archivos/geometrias/*/contenido*');
});

await revisar('un error al reunir se dice y se puede reintentar; la carga parcial no se presenta como completa', async () => {
  await ada.page.route(/\/terrenos\?.*limit=200/, (r) => r.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"fallo simulado"}' }));
  await ada.page.locator('#tabla-vista').selectOption(base.id);
  await hasta(async () => /No se pudieron reunir/.test(await ada.page.locator('.tabla-mapa-aviso').innerText().catch(() => '')), 'sin aviso de error');
  igual((await mapa(ada.page)).filas.length, 0, 'nada mostrado como completo');
  await ada.page.unroute(/\/terrenos\?.*limit=200/);
  await ada.page.getByRole('button', { name: 'Volver a intentar' }).click();
  await hasta(async () => (await mapa(ada.page)).filas.length === TODOS.length, 'reintento');
  igual(await ada.page.locator('.tabla-mapa-aviso').isVisible(), false, 'sin aviso al completar');
  // A first page that says there is more, then a failure: partial is never shown as the set.
  let n = 0;
  await ada.page.route(/\/terrenos\?.*limit=200/, async (r) => {
    n += 1;
    if (n === 1) {
      const resp = await r.fetch();
      const cuerpo = await resp.json();
      cuerpo.next_cursor = 'cursor-ficticio';
      cuerpo.terrenos = cuerpo.terrenos.slice(0, 40);
      return r.fulfill({ response: resp, json: cuerpo });
    }
    return r.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"fallo simulado"}' });
  });
  await ada.page.getByRole('button', { name: 'Actualizar' }).click();
  await hasta(async () => /No se pudo actualizar el mapa: muestra lo que se reunió antes/.test(await ada.page.locator('.tabla-mapa-aviso').innerText().catch(() => '')), 'aviso de actualización fallida');
  igual((await mapa(ada.page)).filas.length, TODOS.length, 'conserva el conjunto completo anterior, no el parcial');
  await ada.page.unroute(/\/terrenos\?.*limit=200/);
  await ada.page.getByRole('button', { name: 'Volver a intentar' }).click();
  await hasta(async () => !(await ada.page.locator('.tabla-mapa-aviso').isVisible()), 'actualizado');
});

await revisar('una escritura hecha con otro filtro deja el conjunto anterior desactualizado: el mapa no muestra lo archivado', async () => {
  await irA(ada.page, base.id);
  await aMapa(ada.page);
  const victima = puntos[0];
  igual((await mapa(ada.page)).filas.includes(victima), true, 'está en el mapa');
  await aTabla(ada.page);
  await ada.page.locator('#tabla-archivados').check();
  await listo(ada.page);
  await ada.page.locator('#tabla-buscar').fill('Lote Mapa 000 Ficticio');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) === 1, 'búsqueda');
  await ada.page.locator(`tr[data-id="${victima}"]`).getByRole('button', { name: /Abrir terreno/ }).click();
  await ada.page.getByRole('button', { name: 'Archivar terreno' }).click();
  await ada.page.getByRole('dialog', { name: '¿Archivar este terreno?' }).getByRole('button', { name: 'Archivar' }).click();
  await hasta(async () => Boolean((await terreno(ada.page, victima)).archived_at), 'no se archivó');
  await ada.page.locator('#tabla-buscar').fill('');
  await ada.page.locator('#tabla-archivados').uncheck();
  await listo(ada.page);
  await aMapa(ada.page);
  await hasta(async () => { const m = await mapa(ada.page); return !m.reuniendo && !m.filas.includes(victima); }, 'el archivado sigue en el mapa');
  igual((await mapa(ada.page)).filas.length, TODOS.length - 1, 'uno menos');
  activos = TODOS.filter((id) => id !== victima);
});

await revisar('un cambio de filtro en el mapa limpia el mapa al instante y cancela la reunión anterior', async () => {
  // The grid's page answers slowly; the map must not wait for it to drop the old query's rows.
  // The filter is changed in Tabla and the map shown again at once, before the grid's page arrives.
  await aTabla(ada.page);
  await ada.page.route(/\/terrenos\?(?!.*limit=200)/, async (r) => { await esperar(1500); await r.continue(); });
  await ada.page.locator('#tabla-estado').selectOption('Sonora');
  await modoBoton(ada.page, 'Mapa').click();
  await esperar(300);                          // well before the grid's page (1.5 s)
  // Never the old query's 110 rows: either nothing yet or already the 52 of Sonora.
  const sonora = 52;
  cierto([0, sonora].includes((await previa(ada.page)).filas), `filas en el mapa: ${(await previa(ada.page)).filas}`);
  cierto(await ada.page.locator('.tabla-lienzo[aria-busy]').count(), 'la página de la tabla aún no debía llegar');
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo && x.clave?.includes('Sonora'); }, 'nueva consulta');
  await ada.page.unroute(/\/terrenos\?(?!.*limit=200)/);
  await filtrar(ada.page, '#tabla-estado', '');
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo && !x.clave?.includes('Sonora') && x.filas.length === activos.length; }, 'sin filtro');
});

/* The same active query: a write in the grid that takes a terrain out of the
 * filtered result (or a blank create that never matched) must not leave it in
 * the map's set. Membership is decided by the server's query, not here. */
async function escribirCelda(page, id, col, valor) {
  const td = page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
  await td.focus();
  await page.keyboard.press('Enter');
  await td.locator('.tabla-editor').fill(valor);
  await page.keyboard.press('Enter');
  await page.locator(`tr[data-id="${id}"] td[data-col="${col}"]:not(.is-pendiente):not(.is-editando)`).waitFor();
  await hasta(async () => (await terreno(page, id))?.draft?.[col.replace('core:', '')] === valor, 'no se guardó');
}
const primeraFila = (page) => page.locator('tr.tabla-fila').first().getAttribute('data-id');
const reunido = (page, parte) => hasta(async () => { const m = await mapa(page); return m && !m.reuniendo && m.clave?.includes(parte) && m; },
  `no se reunió ${parte}`);

await revisar('misma consulta (estado): editar el estado de un terreno lo saca del mapa filtrado sin pulsar Actualizar', async () => {
  await irA(ada.page, base.id);
  await filtrar(ada.page, '#tabla-estado', 'Sonora');
  await aMapa(ada.page);
  await reunido(ada.page, 'estado=Sonora');
  await aTabla(ada.page);
  const id = await primeraFila(ada.page);
  igual((await mapa(ada.page)).filas.includes(id), true, 'estaba en el conjunto');
  await escribirCelda(ada.page, id, 'core:estado', 'Colima');
  await aMapa(ada.page);
  const m = await reunido(ada.page, 'estado=Sonora');
  cierto(!m.filas.includes(id), 'el terreno que ya no es de Sonora sigue en el mapa filtrado');
  igual(await posicion(ada.page, id), null, 'sigue dibujado');
  // No change since: switching does not gather again.
  const antes = reuniones(ada);
  await aTabla(ada.page);
  await aMapa(ada.page);
  igual(reuniones(ada) - antes, 0, 'alternar sin cambios no vuelve a reunir');
  await filtrar(ada.page, '#tabla-estado', '');
});

await revisar('misma consulta (búsqueda): renombrar un terreno lo saca del mapa de la búsqueda', async () => {
  await aTabla(ada.page);
  await ada.page.locator('#tabla-buscar').fill('Lote Mapa 01');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) === 10, 'búsqueda');
  await listo(ada.page);
  await aMapa(ada.page);
  await reunido(ada.page, 'q=Lote');
  await aTabla(ada.page);
  const id = await primeraFila(ada.page);
  await escribirCelda(ada.page, id, 'core:terreno', 'Predio Renombrado Ficticio');
  await aMapa(ada.page);
  const m = await reunido(ada.page, 'q=Lote');
  igual(m.filas.length, 9, 'nueve siguen coincidiendo');
  cierto(!m.filas.includes(id), 'el renombrado sigue en el mapa de la búsqueda');
  await aTabla(ada.page);
  await ada.page.locator('#tabla-buscar').fill('');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) > 10, 'sin búsqueda');
  await listo(ada.page);
});

await revisar('misma consulta: una fila en blanco creada con un filtro activo no entra al mapa; sin filtros sí, sin reunir de nuevo', async () => {
  await filtrar(ada.page, '#tabla-estado', 'Jalisco');
  await aMapa(ada.page);
  await reunido(ada.page, 'estado=Jalisco');
  const enJalisco = (await mapa(ada.page)).filas.length;
  await aTabla(ada.page);
  const antesIds = await ada.page.locator('tr.tabla-fila').evaluateAll((f) => f.map((x) => x.dataset.id));
  await ada.page.getByRole('button', { name: 'Agregar terreno' }).click();
  await ada.page.locator('tr.is-nueva').first().waitFor();
  const nuevo = (await ada.page.locator('tr.is-nueva').evaluateAll((f) => f.map((x) => x.dataset.id))).find((i) => !antesIds.includes(i));
  cierto(nuevo, 'sin fila nueva');
  activos = [...activos, nuevo];
  await aMapa(ada.page);
  const m = await reunido(ada.page, 'estado=Jalisco');
  cierto(!m.filas.includes(nuevo), 'la fila en blanco (sin estado) figura en el mapa de Jalisco');
  igual(m.filas.length, enJalisco, 'el mismo resultado de Jalisco');
  // Without filters, a blank create belongs to the view: it joins the set without a new gathering.
  await filtrar(ada.page, '#tabla-estado', '');
  const sinFiltro = await hasta(async () => { const x = await mapa(ada.page); return x && !x.reuniendo && x.clave && !x.clave.includes('estado=') && x; }, 'sin filtro');
  igual(sinFiltro.filas.includes(nuevo), true, 'la nueva fila es de la vista sin filtros');
  await aTabla(ada.page);
  const ids2 = await ada.page.locator('tr.tabla-fila').evaluateAll((f) => f.map((x) => x.dataset.id));
  await ada.page.getByRole('button', { name: 'Agregar terreno' }).click();
  await hasta(async () => (await ada.page.locator('tr.is-nueva').evaluateAll((f) => f.map((x) => x.dataset.id))).some((i) => !ids2.includes(i)), 'segunda fila');
  const otro = (await ada.page.locator('tr.is-nueva').evaluateAll((f) => f.map((x) => x.dataset.id))).find((i) => !ids2.includes(i));
  activos = [...activos, otro];
  const antes = reuniones(ada);
  await aMapa(ada.page);
  igual((await mapa(ada.page)).filas.includes(otro), true, 'la fila nueva sin filtros está en el mapa');
  igual(reuniones(ada) - antes, 0, 'sin filtros no hace falta reunir de nuevo');
});

const olga = await abrir('olga');

await revisar('operador: Tabla / Mapa en su base; nunca recibe filas ni contornos de otra base', async () => {
  await hasta(async () => /#\/tabla\//.test(olga.page.url()), 'el operador entra a la tabla');
  await olga.page.locator('.tabla-pantalla').waitFor();
  await listo(olga.page);
  igual(await olga.page.locator('#tabla-vista').inputValue(), base.id, 'su base');
  const opciones = await olga.page.locator('#tabla-vista option').evaluateAll((o) => o.map((x) => x.value));
  igual(opciones, [base.id], 'sólo su base en el selector');
  igual(await olga.page.locator('nav.nav .nav-item').allInnerTexts(), ['Tabla', 'Catálogo público'], 'menú del operador');
  await aMapa(olga.page);
  const m = await mapa(olga.page);
  igual([...m.filas].sort(), [...activos].sort(), 'su base completa');
  cierto(deAjena.every((id) => !m.filas.includes(id)), 'nada de la base ajena');
  // The public catalog the page loads before signing in is not the private list.
  const privadas = olga.api.filter((l) => l.includes('/terrenos?') && !l.includes('/api/publico/'));
  cierto(privadas.length && privadas.every((l) => l.includes(`/maestra/bases/${base.id}/terrenos?`)),
    `sólo la ruta de su base: ${privadas}`);
  await clicEnMapa(olga.page, conContorno);
  await hasta(async () => (await posicion(olga.page, conContorno))?.contorno === true, 'contorno en el operador');
  await comprobarFondos(olga, conContorno);
  await foto(olga.page, '03-operador-mapa');
  // The server refuses what the interface never asks for.
  igual((await llamar(olga.page, 'GET', `/api/maestra/bases/${ajena.id}/terrenos?limit=200`)).status, 404, 'lista ajena');
  igual((await llamar(olga.page, 'GET', '/api/inventario/terrenos?limit=200')).status === 403 ||
    (await llamar(olga.page, 'GET', '/api/inventario/terrenos?limit=200')).status === 404, true, 'lista global');
  const gAjena = (await terreno(ada.page, deAjena[0])).ubicacion?.geometria?.id;
  igual(gAjena ?? null, null, 'la ajena no tiene contorno (control)');
  const meta = await llamar(olga.page, 'POST', '/api/archivos/geometrias/metadatos', { ids: [(await terreno(ada.page, conContorno)).ubicacion.geometria.id] });
  igual(meta.status, 200, 'metadatos de su base');
  await aTabla(olga.page);
  igual(await olga.page.locator('.tabla-cuenta').isVisible(), true, 'vuelve a la tabla');
  await olga.page.goto(`${URLBASE}/?test=1#/tabla/${ajena.id}/mapa`);
  await listo(olga.page);
  await hasta(async () => (await olga.page.locator('#tabla-vista').inputValue()) === base.id, 'una base ajena por dirección cae en la suya');
  await hasta(async () => { const x = await mapa(olga.page); return x && !x.reuniendo && x.clave?.startsWith(base.id); }, 'mapa de su base');
  cierto(deAjena.every((id) => !olga.api.some((l) => l.includes(id))), 'ninguna petición nombra terrenos ajenos');
});

await revisar('direcciones antiguas de Inventario llevan al contexto equivalente', async () => {
  await ada.page.goto(`${URLBASE}/?test=1#/inventario`);
  await hasta(async () => /#\/tabla\/maestra\/mapa$/.test(ada.page.url()), `administrador: ${ada.page.url()}`);
  await ada.page.locator('.previa-mapa').waitFor();
  await ada.page.goto(`${URLBASE}/?test=1#/inventario/${conContorno}`);
  await ada.page.locator('.detail, .panel-detalle, [class*="detalle"]').first().waitFor({ timeout: 15000 }).catch(() => {});
  cierto(/#\/inventario\//.test(ada.page.url()), 'el detalle antiguo de un terreno sigue disponible');
  await olga.page.goto(`${URLBASE}/?test=1#/inventario`);
  await hasta(async () => /#\/tabla(\/|$)/.test(olga.page.url()), `operador: ${olga.page.url()}`);
});

await revisar('alternar muchas veces no acumula mapas, escuchas ni cuerpos', async () => {
  await irA(olga.page, base.id);
  await aMapa(olga.page);
  await clicEnMapa(olga.page, conContorno2);
  await hasta(async () => (await posicion(olga.page, conContorno2))?.contorno === true, 'contorno');
  const heap0 = await olga.page.evaluate(() => performance.memory?.usedJSHeapSize ?? null);
  const antes = reuniones(olga);
  for (let i = 0; i < 20; i += 1) { await aTabla(olga.page); await aMapa(olga.page); }
  igual(await olga.page.locator('.leaflet-container').count(), 1, 'un mapa');
  igual(await olga.page.locator('.leaflet-container canvas').count() <= 2, true, 'sin lienzos acumulados');
  igual((await previa(olga.page)).cuerpos, 1, 'un cuerpo');
  igual(reuniones(olga) - antes, 0, 'sin reuniones nuevas');
  const heap1 = await olga.page.evaluate(() => performance.memory?.usedJSHeapSize ?? null);
  medidas.heap_20_alternancias = heap0 && heap1 ? { antes: heap0, despues: heap1 } : 'no disponible';
});

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

console.log(`medidas: ${JSON.stringify(medidas)}`);
await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

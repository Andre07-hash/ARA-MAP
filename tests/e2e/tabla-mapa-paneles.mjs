/* The tables' map screen (issue #37): filters on the left, the map with its
 * price legend and basemaps in the middle, and a read-only record on the
 * right, for administrators and operators. The real local server
 * (tests/e2e/tabla_servidor.py on a folder it creates and deletes), real
 * sessions, widgets, loader and renderer, and Chromium. Fictional accounts,
 * terrains and files only.
 *
 *   cd tests/e2e && node tabla-mapa-paneles.mjs
 *
 * Checks: the map's filters narrow the map and never the table's query, page
 * or cursors; Limpiar / Actualizar keep or clear only what they should and a
 * new view starts empty; the record shows current values, comments and the
 * custom columns of the terrain's own base (from a base and from the master
 * table, with fast changes); it writes nothing and offers no file actions;
 * a boundary without X/Y is said as such; colours and legend follow price
 * per m² with fixed thresholds, mixed currencies fall back; basemaps;
 * keyboard typing; the narrow layout's drawer; the operator only sees their
 * base; the grid still edits and its file cells still work.
 * The map's layout (issue #40): one slim bar with only the view, Tabla / Mapa
 * and Actualizar; no strips above or below the map; "Encuadrar todo" over the
 * map beside the zoom control; the terrain type as a local map filter; and
 * the table's filters kept and said in a small note.
 * Optional: MAPA_CAPTURAS=dir (screenshots), CHROMIUM=/path, MAPA_PUERTO.
 */

import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

// The table's "⋯" menu and the account menu hold these actions.
const enMenuDe = async (page, menu, nombre) => {
  await page.locator(`${menu} > summary`).click();
  await page.locator(`${menu} .menu-panel`).getByText(nombre, { exact: true }).click();
};
const enMenu = (page, nombre) => enMenuDe(page, '.tabla-acciones .menu-mas', nombre);
const enCuenta = (page, nombre) => enMenuDe(page, '.menu-mas.cuenta', nombre);

// The grid's filters open in a side panel (a modal dialog): open it to use them, close it after.
const verFiltros = async (page) => {
  if (!(await page.locator('#tabla-filtros').evaluate((d) => d.open))) {
    await page.locator('[aria-controls="tabla-filtros"]').click();
  }
};
const cerrarFiltros = async (page) => {
  if (await page.locator('#tabla-filtros').evaluate((d) => d.open)) {
    await page.getByRole('button', { name: 'Cerrar filtros' }).click();
  }
};

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.MAPA_PUERTO ?? 8483);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.MAPA_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-paneles-'));
const F = JSON.parse(execFileSync(PY, ['-c',
  'import json, sys\nfrom pathlib import Path\nsys.path.insert(0, "tests/e2e")\n' +
  'from archivos_servidor import escribir_fixtures\n' +
  'd = Path(sys.argv[1]); d.mkdir()\nprint(json.dumps(escribir_fixtures(d)))', join(CARPETA, 'fixtures')],
  { cwd: RAIZ, encoding: 'utf8' }));

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
  const s = { usuario, page, errores: [], api: [], escrituras: [] };
  page.on('pageerror', (e) => s.errores.push(String(e)));
  page.on('request', (r) => {
    if (!r.url().includes('/api/')) return;
    const linea = `${r.method()} ${new URL(r.url()).pathname}${new URL(r.url()).search}`;
    s.api.push(linea);
    if (r.method() !== 'GET') s.escrituras.push(linea);
  });
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
const modoBoton = (page, nombre) => page.locator('.tabla-modo').getByRole('button', { name: nombre, exact: true });
const foto = async (page, nombre) => { if (SHOTS) { await esperar(400); await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); } };
const ficha = (page) => page.locator('.mapa-tabla-ficha');
const fichaTexto = (page) => ficha(page).textContent();
// The colour legend sits at the foot of the map's own filters.
const leyenda = (page) => page.locator('.mapa-tabla-leyenda .legend');
/* The table's Tipo filter takes several types: the checked ones, in the list's order. */
const marcados = (page, id) => page.locator(`#${id} input:checked`).evaluateAll((n) => n.map((c) => c.value));
const tipoTabla = async (page) => (await marcados(page, 'tabla-tipo')).join(', ') || 'Todos';
async function marcarTipo(page, tipo, marcado = true) {
  await verFiltros(page);
  await page.locator(`#tabla-tipo input[value="${tipo}"]`).setChecked(marcado);
  await listo(page);
  await cerrarFiltros(page);
}
// The map's own filters open from the filters panel («Más filtros del mapa»), as a drawer.
const filtrosMapa = (page) => page.locator('dialog.drawer[open]');
async function abrirFiltrosMapa(page) {
  if (await filtrosMapa(page).count()) return;
  await verFiltros(page);
  await page.locator('.cajon-mapa').click();
  await filtrosMapa(page).waitFor();
}
async function cerrarFiltrosMapa(page) {
  if (await filtrosMapa(page).count()) await filtrosMapa(page).getByRole('button', { name: 'Cerrar filtros' }).click();
}
async function limpiarMapa(page) {
  await abrirFiltrosMapa(page);
  await filtrosMapa(page).locator('.rail-header').getByRole('button', { name: /Limpiar/ }).click();
  await cerrarFiltrosMapa(page);
}

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
/** Select a terrain from its grid row (search for it first), then show the map. */
async function elegirDesdeTabla(page, id, nombre) {
  await page.locator('#tabla-buscar').fill(nombre);
  await hasta(async () => (await page.locator('tr.tabla-fila').count()) === 1, `búsqueda ${nombre}`);
  await page.locator(`tr[data-id="${id}"] td[data-col="core:estado"]`).click();
  await aMapa(page);
  await hasta(async () => (await mapa(page)).seleccion === id && await ficha(page).isVisible(), 'la ficha no se abrió');
}
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
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Paneles Ficticia' })).datos.base;
const otra = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Otra Paneles Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
igual((await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] })).status, 200, 'acceso');
igual((await admin('PUT', `/api/maestra/bases/${otra.id}/acceso`, { expected_version: otra.version, usuarios: [ops.omar] })).status, 200, 'acceso otra');
const columna = async (b, nombre) => (await admin('POST', `/api/maestra/bases/${b.id}/columnas`, { nombre, tipo: 'texto' })).datos.columna;
const colBase = await columna(base, 'Seguimiento Ficticio');
const colOtra = await columna(otra, 'Prioridad Ficticia');
const crear = async (b, campos) => (await admin('POST', `/api/maestra/bases/${b.id}/terrenos`, campos)).datos.terreno.id;
async function escribir(id, cuerpo) {
  const r = await admin('PATCH', `/api/inventario/terrenos/${id}`, { expected_version: (await terreno(ada.page, id)).version, ...cuerpo });
  igual(r.status, 200, `escritura ${JSON.stringify(r.datos)}`);
}

// 120 terrains in one base (more than a page of 100), prices per m² in MXN,
// two states, a few without any location, one that gets a boundary and no X/Y.
const puntos = [];
for (let i = 0; i < 120; i += 1) {
  puntos.push(await crear(base, {
    terreno: `Lote Panel ${String(i).padStart(3, '0')} Ficticio`, estado: i % 2 ? 'Sonora' : 'Jalisco',
    tipo_terreno: i % 3 ? 'Industrial Ficticio' : 'Habitacional Ficticio',
    municipio: i % 2 ? 'Hermosillo' : 'Zapopan', superficie_m2: 1000 + i * 100,
    asking_price: 100000 + i * 1000, asking_m2: 100 + i * 10, moneda: 'MXN',
    lat: 18 + (i % 10) * 0.8, lon: -108 + Math.floor(i / 10) * 0.9,
  }));
}
const sinUbicacion = [];
for (let i = 0; i < 4; i += 1) sinUbicacion.push(await crear(base, { terreno: `Lote Panel Sin Ubicación ${i} Ficticio`, estado: 'Jalisco' }));
const conContorno = await crear(base, { terreno: 'Lote Panel Contorno Ficticio', estado: 'Sonora', asking_m2: 999, moneda: 'MXN' });
const TODOS = [...puntos, ...sinUbicacion, conContorno];
const elegido = puntos[7];
await escribir(elegido, { changes: { notas_internas: 'Comentario ficticio vigente' }, custom: { [colBase.id]: 'Visita ficticia' } });
// The other base: few prices, one with an older USD record.
const deOtra = [];
for (let i = 0; i < 4; i += 1) {
  deOtra.push(await crear(otra, { terreno: `Lote Otra ${i} Ficticio`, estado: 'Yucatán', lat: 20.5, lon: -89 + i * 0.3,
    asking_m2: 50 + i, moneda: i === 3 ? 'USD' : 'MXN' }));
}
await escribir(deOtra[0], { custom: { [colOtra.id]: 'Alta ficticia' } });
// The table read its bases when the session opened: read them again.
await ada.page.reload();
await ada.page.locator('.tabla-pantalla').waitFor();

/* ----------------------------------------------------------- journeys */

await revisar('administrador: la base con contorno KMZ sin X/Y (desde la celda, sin cambios)', async () => {
  await irA(ada.page, base.id);
  await ada.page.locator('#tabla-buscar').fill('Lote Panel Contorno Ficticio');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) === 1, 'búsqueda');
  await subirKmzEnCelda(ada.page, conContorno, F.kmz_simple);
  const t = await terreno(ada.page, conContorno);
  igual([t.ubicacion.modo, t.draft.lat, t.draft.lon], ['geometria', null, null], 'contorno sin X/Y');
  await ada.page.locator('#tabla-buscar').fill('');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) > 1, 'sin búsqueda');
});

let paginaTabla = null;
await revisar('administrador: filtros a la izquierda, mapa con leyenda por precio y todo el conjunto (> una página)', async () => {
  await irA(ada.page, base.id);
  paginaTabla = { cuenta: await ada.page.locator('.tabla-cuenta').innerText(), filas: await ada.page.locator('tr.tabla-fila').count() };
  igual(paginaTabla.filas, 100, 'una página de 100');
  await aMapa(ada.page);
  const m = await mapa(ada.page);
  igual([m.filas.length, m.incompleto], [TODOS.length, false], 'conjunto completo');
  igual((await previa(ada.page)).filas, TODOS.length, 'el mapa dibuja todo sin filtros');
  igual(await ada.page.locator('.mapa-tabla-rail .rail').isVisible(), false, 'sin panel de filtros al lado del mapa');
  cierto(await ada.page.locator('[aria-controls="tabla-filtros"]').isVisible(), 'los filtros se abren desde la barra');
  // A row chosen in the grid (the KMZ cell above may have chosen one) is the map's selection too.
  const seleccion = (await mapa(ada.page)).seleccion;
  igual(await ficha(ada.page).isVisible(), Boolean(seleccion), 'ficha sólo con selección');
  if (seleccion) await ficha(ada.page).getByRole('button', { name: 'Cerrar detalle' }).click();
  igual([await ficha(ada.page).isVisible(), (await mapa(ada.page)).seleccion], [false, null], 'sin ficha sin selección');
  igual(await leyenda(ada.page).locator('.ramp-step:not(.ramp-step-unknown)').count(), 5, 'cinco pasos de precio');
  cierto(/asking \$\/m²/i.test(await leyenda(ada.page).textContent()), 'leyenda por precio por m²');
  cierto(/4 terrenos fuera del mapa: sin contorno activo ni X\/Y válidas/.test(await leyenda(ada.page).textContent()), 'sin ubicación referida al mapa');
  cierto(!/falta de coordenadas|círculos/.test(await leyenda(ada.page).textContent()), 'sin textos heredados');
  await foto(ada.page, '01-administrador-mapa');
});

await revisar('la barra es la misma que en Tabla; sobre el mapa sólo Encuadrar todo y los fondos', async () => {
  const p = ada.page;
  const lugares = async () => {
    const r = [];
    // The bar; the area under it is shorter in Tabla only by the grid's own pager.
    for (const sel of ['#tabla-vista', '.tabla-busqueda', '.tabla-acciones']) r.push(await p.locator(sel).boundingBox());
    const area = await p.locator('.tabla-cuerpo').boundingBox();
    r.push([area.x, area.y, area.width]);
    return JSON.stringify(r);
  };
  // Switching starts each screen at its top, so the bar is measured right after a switch.
  await aTabla(p);
  await aMapa(p);
  const enMapa = await lugares();
  await aTabla(p);
  igual(await lugares(), enMapa, 'cambiar entre Tabla y Mapa no mueve la barra ni el inicio del área');
  await aMapa(p);
  for (const visible of ['#tabla-buscar', '[aria-controls="tabla-filtros"]']) {
    cierto(await p.locator(visible).isVisible(), `${visible} visible también en el mapa`);
  }
  // Inside the closed "⋯" menu nothing is visible, so the hidden attribute is what tells.
  igual(await p.locator('.menu-panel .menu-item', { hasText: /^Columnas$/ }).getAttribute('hidden'), '', 'Columnas oculto en el mapa');
  for (const quitado of ['.mapa-tabla-alcance', '.previa-cuenta', '.previa-titulo', '.previa-pie', '.mapa-tabla-cabecera', '.tabla-heredados']) {
    igual(await p.locator(quitado).count(), 0, `sin ${quitado}`);
  }
  igual(await p.locator('.tabla-pie').isVisible(), false, 'sin el pie que repite «N terrenos»');
  // Over the map: + / − (top left), "Encuadrar todo" (top right) and the basemaps; no info toggle.
  igual(await p.locator('.previa-mapa .leaflet-top.leaflet-left .leaflet-control-zoom').isVisible(), true, '+ / − arriba a la izquierda');
  igual(await p.locator('.previa-info').isVisible(), false, 'sin botón de información');
  igual(await leyenda(p).isVisible(), false, 'la leyenda está en los filtros del mapa, no encima');
  const lienzo = await p.locator('.previa-mapa').boundingBox();
  const encuadre = await p.getByRole('button', { name: 'Encuadrar todo' }).boundingBox();
  const creditos = await p.locator('.previa-mapa .leaflet-control-attribution').boundingBox();
  const separados = (a, b) => a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y;
  cierto(separados(encuadre, creditos), 'sin tapar los créditos');
  cierto(encuadre.y - lienzo.y < 30 && lienzo.x + lienzo.width - (encuadre.x + encuadre.width) < 30, 'arriba a la derecha del mapa');
  cierto(await p.getByRole('radio', { name: 'Satélite', exact: true }).isVisible(), 'fondos abajo');
  // Counts: filtered in the map's own filters, placed / not placed in its legend.
  cierto(/125 terrenos de 125/.test(await p.locator('.mapa-tabla-rail .rail-result').textContent()), 'cuenta de filtrados en el panel');
  cierto(/121 terrenos/.test(await leyenda(p).locator('.legend-count').textContent()), 'ubicados en la leyenda');
  // From a close-up (the wheel still zooms), Encuadrar todo by keyboard goes back to the whole of Mexico.
  for (let i = 0; i < 12 && (await previa(p)).zoom < 10; i += 1) {
    await p.mouse.move(lienzo.x + lienzo.width / 2, lienzo.y + lienzo.height / 2);
    await p.mouse.wheel(0, -400);
    await esperar(300);
  }
  await hasta(async () => (await previa(p)).zoom >= 10, `acercado: ${(await previa(p)).zoom}`);
  await p.getByRole('button', { name: 'Encuadrar todo' }).focus();
  await p.keyboard.press('Enter');
  await hasta(async () => (await previa(p)).zoom <= 5, `todo México: ${(await previa(p)).zoom}`);
  igual((await mapa(p)).seleccion, null, 'sin selección accidental');
});

await revisar('los filtros del mapa acotan el mapa, conservan los colores y no tocan la tabla', async () => {
  const umbrales = await leyenda(ada.page).locator('.ramp-label').allInnerTexts();
  const listas = ada.api.filter((l) => /\/terrenos\?/.test(l)).length;
  // Continuous typing in the search box keeps focus and every character.
  await abrirFiltrosMapa(ada.page);
  await ada.page.locator('#buscar').click();
  await ada.page.keyboard.type('Lote Panel 01', { delay: 25 });
  igual(await ada.page.locator('#buscar').inputValue(), 'Lote Panel 01', 'escritura continua');
  igual(await ada.page.evaluate(() => document.activeElement?.id), 'buscar', 'el foco sigue en la búsqueda');
  await hasta(async () => (await previa(ada.page)).filas === 10, `búsqueda en el mapa: ${(await previa(ada.page)).filas}`);
  await ada.page.locator('#estados-Sonora').check();
  await hasta(async () => (await previa(ada.page)).filas === 5, 'casilla de estado');
  await ada.page.locator('#unitario-min').fill('240');
  await hasta(async () => (await previa(ada.page)).filas === 3, 'precio por m² mínimo');
  igual(await leyenda(ada.page).locator('.ramp-label').allInnerTexts(), umbrales, 'los umbrales no cambian al filtrar');
  igual((await mapa(ada.page)).filas.length, TODOS.length, 'el conjunto de la vista no cambia');
  igual(ada.api.filter((l) => /\/terrenos\?/.test(l)).length, listas, 'filtrar el mapa no pide listas');
  cierto(/Limpiar \(3\)/.test(await filtrosMapa(ada.page).locator('.rail-header').innerText()), 'tres filtros activos');
  await cerrarFiltrosMapa(ada.page);
  await aTabla(ada.page);
  igual(await ada.page.locator('#tabla-buscar').inputValue(), '', 'búsqueda de la tabla intacta');
  igual(await marcados(ada.page, 'tabla-estado'), [], 'estado de la tabla intacto');
  igual(await ada.page.locator('.tabla-cuenta').innerText(), paginaTabla.cuenta, 'misma página');
  igual(await ada.page.locator('tr.tabla-fila').count(), paginaTabla.filas, 'mismas filas');
  await aMapa(ada.page);
  igual(await ada.page.locator('#buscar').inputValue(), 'Lote Panel 01', 'los filtros del mapa se conservan al alternar');
  igual((await previa(ada.page)).filas, 3, 'mismo resultado');
  // Actualizar gathers the set again and keeps the map's filters.
  await enMenu(ada.page, 'Actualizar');
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo; }, 'actualizado');
  igual([await ada.page.locator('#buscar').inputValue(), (await previa(ada.page)).filas], ['Lote Panel 01', 3], 'Actualizar conserva los filtros');
  // Limpiar clears only the map's filters.
  await limpiarMapa(ada.page);
  await hasta(async () => (await previa(ada.page)).filas === TODOS.length, 'Limpiar');
  igual(await ada.page.locator('#tabla-buscar').inputValue(), '', 'Limpiar no toca la tabla');
});

await revisar('Tipo de terreno: filtro local del mapa; Limpiar lo quita y no toca la tabla', async () => {
  const p = ada.page;
  await abrirFiltrosMapa(p);
  cierto(await filtrosMapa(p).getByRole('group', { name: 'Tipo de terreno' }).isVisible(), 'Tipo en los filtros del mapa');
  const listas = ada.api.filter((l) => /\/terrenos\?/.test(l)).length;
  await p.locator('[id="tipos-Habitacional Ficticio"]').check();
  await hasta(async () => (await previa(p)).filas === 40, `tipo en el mapa: ${(await previa(p)).filas}`);
  igual(ada.api.filter((l) => /\/terrenos\?/.test(l)).length, listas, 'filtrar por tipo no pide listas');
  cierto(/Limpiar \(1\)/.test(await filtrosMapa(p).locator('.rail-header').innerText()), 'cuenta como un filtro');
  await cerrarFiltrosMapa(p);
  await aTabla(p);
  igual(await tipoTabla(p), 'Todos', 'el tipo de la tabla no cambia');
  // Actualizar on the map left the grid to be read again: it reloads the same page.
  await hasta(async () => (await p.locator('tr.tabla-fila').count()) === paginaTabla.filas, 'misma página');
  igual(await p.locator('.tabla-cuenta').innerText(), paginaTabla.cuenta, 'misma cuenta');
  await aMapa(p);
  igual(await p.locator('[id="tipos-Habitacional Ficticio"]').isChecked(), true, 'se conserva al alternar');
  await limpiarMapa(p);
  await hasta(async () => (await previa(p)).filas === TODOS.length, 'Limpiar quita el tipo');
  igual(await p.locator('[id="tipos-Habitacional Ficticio"]').isChecked(), false, 'casilla limpia');
});

await revisar('Limpiar no amplía el alcance de la tabla; otra vista empieza sin filtros del mapa', async () => {
  await aTabla(ada.page);
  await verFiltros(ada.page);
  await ada.page.locator('#tabla-estado input[value="Jalisco"]').check();
  await listo(ada.page);
  await cerrarFiltros(ada.page);
  await aMapa(ada.page);
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo && x.clave?.includes('estado=Jalisco'); }, 'reunión con el estado');
  const jalisco = (await mapa(ada.page)).filas.length;
  // The bar is the same on the map: its chips say the table's filter.
  cierto(await ada.page.locator('.tabla-chips').isVisible(), 'las etiquetas siguen en el mapa');
  cierto(/Estado: Jalisco/.test(await ada.page.locator('.tabla-chips').innerText()), 'dice el filtro de la tabla');
  await abrirFiltrosMapa(ada.page);
  await ada.page.locator('#buscar').fill('Lote Panel 00');
  await hasta(async () => (await previa(ada.page)).filas < jalisco, 'búsqueda dentro del alcance');
  await cerrarFiltrosMapa(ada.page);
  await limpiarMapa(ada.page);
  await hasta(async () => (await previa(ada.page)).filas === jalisco, 'Limpiar vuelve al alcance, no a toda la base');
  // The table's type filter: kept, said, and never offered as a map control.
  await aTabla(ada.page);
  await marcarTipo(ada.page, 'Industrial Ficticio');
  await aMapa(ada.page);
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo && /tipo_terreno=Industrial/.test(x.clave); }, 'reunión con el tipo');
  const etiquetas = await ada.page.locator('.tabla-chips').innerText();
  cierto(/Estado: Jalisco/.test(etiquetas) && /Tipo de terreno: Industrial Ficticio/.test(etiquetas), `etiquetas: ${etiquetas}`);
  const tipos = await ada.page.locator('.mapa-tabla-rail [id^="tipos-"]').evaluateAll((n) => n.map((c) => c.value));
  igual(tipos, ['Industrial Ficticio'], 'el Tipo local sólo ofrece los tipos del conjunto');
  await aTabla(ada.page);
  igual([(await marcados(ada.page, 'tabla-estado')).join(', '), await tipoTabla(ada.page)],
    ['Jalisco', 'Industrial Ficticio'], 'la tabla conserva sus filtros');
  // Several types at once: both are sent and both are said.
  await marcarTipo(ada.page, 'Habitacional Ficticio');
  igual(await tipoTabla(ada.page), 'Habitacional Ficticio, Industrial Ficticio', 'dos tipos, en el orden de la lista');
  await aMapa(ada.page);
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo
    && /tipo_terreno=Industrial/.test(x.clave) && /tipo_terreno=Habitacional/.test(x.clave); }, 'reunión con los dos tipos');
  await aTabla(ada.page);
  await marcarTipo(ada.page, 'Industrial Ficticio', false);
  await marcarTipo(ada.page, 'Habitacional Ficticio', false);
  igual(await tipoTabla(ada.page), 'Todos', 'sin tipos');
  // By keyboard: Space checks a type, the table reloads, and focus and the open panel stay.
  await verFiltros(ada.page);
  await ada.page.locator('#tabla-tipo input').first().focus();
  await ada.page.keyboard.press('Space');
  await hasta(async () => (await tipoTabla(ada.page)) !== 'Todos', 'Espacio no marcó un tipo');
  await listo(ada.page);
  igual(await ada.page.evaluate(() => document.getElementById('tabla-filtros').open
    && document.getElementById('tabla-tipo').contains(document.activeElement)), true, 'el foco y el panel siguen tras recargar');
  await ada.page.keyboard.press('Space');
  await hasta(async () => (await tipoTabla(ada.page)) === 'Todos', 'Espacio no desmarcó');
  await ada.page.keyboard.press('Escape');
  igual(await ada.page.locator('#tabla-filtros').evaluate((d) => d.open), false, 'Escape cierra');
  await aMapa(ada.page);
  await abrirFiltrosMapa(ada.page);
  await ada.page.locator('#buscar').fill('Lote Panel 00');
  await cerrarFiltrosMapa(ada.page);
  await ada.page.locator('#tabla-vista').selectOption(otra.id);
  await hasta(async () => { const x = await mapa(ada.page); return x && !x.reuniendo && x.clave?.startsWith(otra.id); }, 'otra vista');
  igual(await ada.page.locator('#buscar').inputValue(), '', 'los filtros del mapa empiezan vacíos');
  igual((await previa(ada.page)).filas, deOtra.length, 'sin filtro arrastrado');
  igual(await ficha(ada.page).isVisible(), false, 'sin ficha de la vista anterior');
});

await revisar('pocos precios: sin graduar; todo precio es MXN y se filtra junto', async () => {
  const texto = await leyenda(ada.page).textContent();
  cierto(/No hay suficientes precios/.test(texto) && !/moneda/i.test(texto), `leyenda: ${texto}`);
  igual(await leyenda(ada.page).locator('.ramp-step').count(), 0, 'sin rampa');
  igual(await ada.page.locator('#unitario-min').isDisabled(), false, 'el filtro de precio sigue disponible');
});

await revisar('la ficha: valores y comentario vigentes, columnas de su base, archivos y sin escrituras', async () => {
  await irA(ada.page, base.id);
  const escrituras = ada.escrituras.length;
  await elegirDesdeTabla(ada.page, elegido, 'Lote Panel 007 Ficticio');
  const texto = await fichaTexto(ada.page);
  for (const esperado of ['Lote Panel 007 Ficticio', 'Base Paneles Ficticia', 'Comentario ficticio vigente', 'Seguimiento Ficticio',
    'Visita ficticia', 'Sin archivos', 'Sin KMZ / KML', 'X (latitud)', 'En el mapa por sus coordenadas X/Y']) {
    cierto(texto.includes(esperado), `falta «${esperado}» en la ficha: ${texto}`);
  }
  igual(await ficha(ada.page).locator('input, select, textarea, [contenteditable="true"]').count(), 0, 'sin controles de edición');
  igual((await ficha(ada.page).getByRole('button').allInnerTexts()).sort(), ['Ver a escala', '×'].sort(), 'sólo cerrar y ver a escala');
  // A change made elsewhere arrives with Actualizar; the record follows.
  await escribir(elegido, { changes: { notas_internas: 'Comentario ficticio nuevo' } });
  await enMenu(ada.page, 'Actualizar');
  await hasta(async () => (await fichaTexto(ada.page)).includes('Comentario ficticio nuevo'), 'valor actual en la ficha');
  // A table search that still includes the selected terrain keeps the selection and its record.
  await aTabla(ada.page);
  await ada.page.locator('#tabla-buscar').fill('Lote Panel 00');
  await aMapa(ada.page);
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo && x.clave?.includes('q=Lote'); }, 'reunión con la búsqueda');
  await hasta(async () => (await mapa(ada.page)).seleccion === elegido && await ficha(ada.page).isVisible(), 'la selección sigue tras la búsqueda');
  await ada.page.getByRole('button', { name: 'Ver a escala' }).click();
  await foto(ada.page, '02-administrador-ficha');
  await ficha(ada.page).getByRole('button', { name: 'Cerrar detalle' }).click();
  igual([await ficha(ada.page).isVisible(), (await mapa(ada.page)).seleccion], [false, null], 'cerrar limpia la selección');
  igual(ada.escrituras.length, escrituras + 1, 'la ficha no escribe (sólo la escritura de la prueba)');
});

await revisar('contorno activo sin X/Y: ficha y cuerpo; cerrar no lo desactiva; un filtro que lo excluye limpia la ficha', async () => {
  // Before it is selected, its symbol says that a click shows the outline.
  await aTabla(ada.page);
  await ada.page.locator('#tabla-buscar').fill('Lote Panel Contorno Ficticio');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) === 1, 'búsqueda del contorno');
  await aMapa(ada.page);
  const caja = await ada.page.locator('.previa-mapa').boundingBox();
  await hasta(async () => {   // the position is read again if the map is still framing
    const p0 = await posicion(ada.page, conContorno);
    if (!p0) return false;
    await ada.page.mouse.move(caja.x + p0.x, caja.y + p0.y);
    return /Haz clic para ver el contorno/.test(
      await ada.page.locator('.leaflet-tooltip.mark-tooltip').innerText({ timeout: 500 }).catch(() => ''));
  }, 'aviso de clic');
  await ada.page.mouse.move(caja.x + 5, caja.y + 5);
  await aTabla(ada.page);
  await elegirDesdeTabla(ada.page, conContorno, 'Lote Panel Contorno Ficticio');
  await hasta(async () => (await previa(ada.page)).cuerpos === 1, 'un cuerpo');
  const texto = await fichaTexto(ada.page);
  cierto(/En el mapa por su contorno KMZ \/ KML activo/.test(texto), `ficha: ${texto}`);
  cierto(/Contorno activo/.test(texto), 'resumen KMZ');
  cierto(!/círculo|Sin coordenadas|Buscar en Google/.test(texto), 'sin textos de X/Y faltantes');
  igual(await ficha(ada.page).locator('.detail-grid dd.mono').allInnerTexts(), ['—', '—'], 'X/Y almacenadas vacías, no del contorno');
  // A map filter that leaves it out clears the record, the selection and the body.
  await abrirFiltrosMapa(ada.page);
  await ada.page.locator('#unitario-max').fill('500');
  await hasta(async () => !(await ficha(ada.page).isVisible()), 'ficha limpia');
  igual([(await mapa(ada.page)).seleccion, (await previa(ada.page)).cuerpos], [null, 0], 'sin selección ni cuerpo');
  await ada.page.locator('#unitario-max').fill('');
  await cerrarFiltrosMapa(ada.page);
  const t = await terreno(ada.page, conContorno);
  igual(t.ubicacion.modo, 'geometria', 'el contorno sigue activo en el servidor');
});

await revisar('desde la maestra: columnas de la base de cada terreno, cambios rápidos sin ficha atrasada', async () => {
  await irA(ada.page, 'maestra');
  await elegirDesdeTabla(ada.page, deOtra[0], 'Lote Otra 0 Ficticio');
  await hasta(async () => (await fichaTexto(ada.page)).includes('Alta ficticia'), 'columna de la otra base');
  cierto(!(await fichaTexto(ada.page)).includes('Seguimiento Ficticio'), 'sin columnas de otra base');
  cierto(ada.api.some((l) => l.includes(`/api/maestra/bases/${otra.id}/columnas`)), 'pidió las columnas de su base');
  await aTabla(ada.page);
  // Delay the other base's columns: choosing another terrain meanwhile must win.
  await ada.page.route(`**/api/maestra/bases/${otra.id}/columnas*`, async (r) => { await esperar(1500); await r.continue().catch(() => {}); });
  await ada.page.locator('#tabla-buscar').fill('Lote Otra 1 Ficticio');
  await hasta(async () => (await ada.page.locator('tr.tabla-fila').count()) === 1, 'búsqueda');
  await ada.page.locator(`tr[data-id="${deOtra[1]}"] td[data-col="core:estado"]`).click();
  await aMapa(ada.page);
  await aTabla(ada.page);
  await elegirDesdeTabla(ada.page, elegido, 'Lote Panel 007 Ficticio');
  await hasta(async () => (await fichaTexto(ada.page)).includes('Visita ficticia'), 'columna de su base');
  await esperar(1800);
  const texto = await fichaTexto(ada.page);
  cierto(texto.includes('Lote Panel 007 Ficticio') && !texto.includes('Prioridad Ficticia'), `ficha atrasada: ${texto}`);
  await ada.page.unroute(`**/api/maestra/bases/${otra.id}/columnas*`);
});

await revisar('fondos Claro/Satélite/Calles con ficha abierta; la tabla sigue editable', async () => {
  for (const nombre of ['Satélite', 'Calles', 'Claro']) {
    await ada.page.getByRole('radio', { name: nombre, exact: true }).click();
    igual(await ada.page.getByRole('radio', { name: nombre, exact: true }).getAttribute('aria-checked'), 'true', nombre);
  }
  cierto(await ficha(ada.page).isVisible(), 'la ficha sigue');
  await aTabla(ada.page);
  const celda = ada.page.locator(`tr[data-id="${elegido}"] td[data-col="core:notas_internas"]`);
  await celda.dblclick();
  await ada.page.keyboard.press('ControlOrMeta+a');
  await ada.page.keyboard.type('Comentario ficticio desde la tabla');
  await ada.page.keyboard.press('Enter');
  await hasta(async () => (await terreno(ada.page, elegido)).draft.notas_internas === 'Comentario ficticio desde la tabla', 'la celda se guardó');
  cierto(await ada.page.locator(`tr[data-id="${elegido}"] td[data-col="core:kmz"] .archivos-celda-elegir`).count() === 1, 'la celda KMZ conserva su control');
  await aMapa(ada.page);
  await hasta(async () => (await fichaTexto(ada.page)).includes('Comentario ficticio desde la tabla'), 'la ficha muestra la edición de la tabla');
});

await revisar('pantalla estrecha: filtros en un cajón, ficha superpuesta, teclado', async () => {
  await aTabla(ada.page);
  await ada.page.locator('#tabla-buscar').fill('');
  await aMapa(ada.page);
  await hasta(async () => { const x = await mapa(ada.page); return !x.reuniendo && x.filas.length > 100; }, 'sin la búsqueda de la tabla');
  await ada.page.setViewportSize({ width: 800, height: 900 });
  await esperar(300);
  igual(await ada.page.locator('.mapa-tabla-rail').isVisible(), false, 'el panel se oculta');
  const boton = ada.page.locator('[aria-controls="tabla-filtros"]');
  cierto(await boton.isVisible(), 'botón Filtros');
  await abrirFiltrosMapa(ada.page);
  const cajon = filtrosMapa(ada.page);
  await cajon.locator('#buscar').click();
  await ada.page.keyboard.type('Lote Panel 11', { delay: 20 });
  await hasta(async () => (await previa(ada.page)).filas === 10, 'filtro desde el cajón');
  await cajon.getByRole('button', { name: 'Ver resultados' }).focus();
  await ada.page.keyboard.press('Enter');
  await hasta(async () => !(await cajon.count()), 'cajón cerrado');
  igual(await ada.page.evaluate(() => document.activeElement?.getAttribute('aria-controls')), 'tabla-filtros', 'el foco vuelve al botón');
  igual(await ada.page.locator('#buscar').inputValue(), 'Lote Panel 11', 'el valor se conserva');
  const ancho = await ada.page.evaluate(() => document.documentElement.scrollWidth);
  cierto(ancho <= 800, `sin desplazamiento horizontal (${ancho})`);
  await foto(ada.page, '03-estrecha');
  // A phone: the bar wraps without clipping, the map takes the rest, and the record opens over it and closes.
  await ada.page.setViewportSize({ width: 390, height: 844 });
  await esperar(300);
  for (const control of [ada.page.locator('#tabla-vista'), modoBoton(ada.page, 'Mapa'), ada.page.locator('.tabla-acciones .menu-mas > summary'), boton]) {
    const c = await control.boundingBox();
    cierto(c && c.x >= 0 && c.x + c.width <= 390, 'control esencial dentro de la pantalla');
  }
  cierto(await ada.page.evaluate(() => document.documentElement.scrollWidth) <= 390, 'sin desplazamiento horizontal en 390px');
  const lienzo = await ada.page.locator('.previa-mapa').boundingBox();
  // A card under the same bar as the grid's, with the page's margins.
  cierto(lienzo.x >= 0 && lienzo.x + lienzo.width <= 390 && lienzo.width >= 340 && lienzo.y + lienzo.height >= 800,
    `el mapa ocupa el resto (${JSON.stringify(lienzo)})`);
  await aTabla(ada.page);
  // One the drawer's search ("Lote Panel 11") keeps on the map.
  await elegirDesdeTabla(ada.page, puntos[110], 'Lote Panel 110 Ficticio');
  const cerrar = ficha(ada.page).getByRole('button', { name: 'Cerrar detalle' });
  const caja = await cerrar.boundingBox();
  cierto(caja && caja.x + caja.width <= 390, 'cerrar la ficha está a la vista');
  await foto(ada.page, '03b-telefono-ficha');
  await cerrar.click();
  igual(await ficha(ada.page).isVisible(), false, 'la ficha se cierra');
  await aTabla(ada.page);
  await ada.page.locator('#tabla-buscar').fill('');
  await aMapa(ada.page);
  await ada.page.setViewportSize({ width: 1500, height: 900 });
});

const olga = await abrir('olga');
await revisar('operador: su base, filtros y ficha con sus columnas; nunca otra base', async () => {
  await hasta(async () => /#\/tabla\//.test(olga.page.url()), 'el operador entra a la tabla');
  await listo(olga.page);
  igual(await olga.page.locator('#tabla-vista').inputValue(), base.id, 'su base');
  await aMapa(olga.page);
  const m = await mapa(olga.page);
  igual(m.filas.length, TODOS.length, 'todo su conjunto, más de una página');
  await abrirFiltrosMapa(olga.page);
  await olga.page.locator('#estados-Sonora').check();
  await hasta(async () => (await previa(olga.page)).filas === 61, `filtro del operador: ${(await previa(olga.page)).filas}`);
  await olga.page.locator('#estados-Sonora').uncheck();
  await cerrarFiltrosMapa(olga.page);
  await aTabla(olga.page);
  await elegirDesdeTabla(olga.page, elegido, 'Lote Panel 007 Ficticio');
  const texto = await fichaTexto(olga.page);
  cierto(texto.includes('Seguimiento Ficticio') && texto.includes('Visita ficticia'), `ficha del operador: ${texto}`);
  igual(olga.api.filter((l) => l.includes(otra.id) || l.includes('/api/inventario/terrenos?')), [], 'sin peticiones de otra base ni de la maestra');
  cierto(deOtra.every((id) => !olga.api.some((l) => l.includes(id))), 'ningún terreno ajeno');
  igual(olga.escrituras.filter((l) => !l.includes('/sesion') && !l.includes('/login')), [], 'sin escrituras');
  await foto(olga.page, '04-operador-ficha');
});

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

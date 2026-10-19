/* KMZ and bare KML in the one boundary column, with the REAL widgets, the
 * real local server (tests/e2e/tabla_servidor.py on a folder it creates and
 * deletes), real sessions and Chromium. Fictional accounts and files only.
 *
 *   cd tests/e2e && node tabla-kml.mjs
 *
 * What it checks: the column says "KMZ / KML" and its button "Elegir KMZ o
 * KML…" in the table and in the detail, with a picker for both extensions;
 * an administrator's single-contour KML (upper-case extension) becomes the
 * active boundary and is drawn on the map; a KML with no usable contour and a
 * .kml that is really a KMZ keep the previous boundary and say so without
 * calling the KML a KMZ; a KMZ can replace a KML in the same history; an
 * authorized operator's KML with several contours waits for the explicit
 * choice and activation in the detail; a KML chosen in the detail survives
 * a table reload from window focus; the detail downloads the original bytes
 * under the original name; and, as regressions of the shared flow, a PDF
 * still opens from its count. Optional: KML_CAPTURAS=dir (screenshots),
 * CHROMIUM=/path, KML_PUERTO.
 */

import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.KML_PUERTO ?? 8487);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.KML_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-kml-'));
const F = JSON.parse(execFileSync(PY, ['-c',
  'import json, sys\nfrom pathlib import Path\nsys.path.insert(0, "tests/e2e")\n' +
  'from archivos_servidor import escribir_fixtures\n' +
  'd = Path(sys.argv[1]); d.mkdir()\nprint(json.dumps(escribir_fixtures(d)))', join(CARPETA, 'fixtures')],
  { cwd: RAIZ, encoding: 'utf8' }));
// Bare KML documents: the fixtures themselves, byte for byte, under fictional names.
const KML = join(RAIZ, 'tests', 'fixtures', 'kmz');
for (const [clave, nombre, fuente] of [['kml_simple', 'Contorno Ñandú ficticio.KML', 'poligono_simple.kml'],
  ['kml_varios', 'Tres lotes ficticios.kml', 'ambiguo_tres_lotes.kml'],
  ['kml_invalido', 'Sin contorno ficticio.kml', 'documento_vacio.kml'],
  ['kml_detalle', 'Forma U ficticia.kml', 'forma_u.kml']]) {
  mkdirSync(join(CARPETA, 'fixtures', clave));
  F[clave] = join(CARPETA, 'fixtures', clave, nombre);
  writeFileSync(F[clave], readFileSync(join(KML, fuente)));
}
mkdirSync(join(CARPETA, 'fixtures', 'kml_falso'));
F.kml_falso = join(CARPETA, 'fixtures', 'kml_falso', 'Paquete ficticio.kml');
writeFileSync(F.kml_falso, readFileSync(F.kmz_simple));          // a KMZ under a .kml name

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
const sha = (b) => createHash('sha256').update(b).digest('hex');

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium' });
const sesiones = [];
async function abrir(usuario) {
  const contexto = await navegador.newContext({ viewport: { width: 1500, height: 900 }, locale: 'es-MX', acceptDownloads: true });
  contexto.setDefaultTimeout(30000);
  const page = await contexto.newPage();
  const s = { usuario, page, contexto, errores: [], lecturas: [] };
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
const geometriaDe = async (page, id) => (await terreno(page, id))?.ubicacion?.geometria?.id ?? null;

const fila = (page, id) => page.locator(`tr[data-id="${id}"]`);
const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const resumen = async (page, id, col) => (await celda(page, id, col).locator('.archivos-celda').innerText().catch(() => '')).trim();
const elegirEn = (page, id, col) => celda(page, id, col).locator('.archivos-celda-elegir');
const COL = { pdf: 'core:archivos', kmz: 'core:kmz' };
const TERMINAL = ['listo', 'requiere_seleccion', 'rechazado', 'fallido', 'interrumpido', 'incierto', 'no_aplicada'];
const tipoDe = (ruta) => (ruta.endsWith('.pdf') ? 'application/pdf'
  : /\.kml$/i.test(ruta) ? 'application/vnd.google-earth.kml+xml' : 'application/vnd.google-earth.kmz');

async function irA(page, vista) {
  await page.goto(`${URLBASE}/?test=1#/tabla/${vista}`);
  await page.locator('.tabla-pantalla').waitFor();
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
}
/** Click the cell's button and give the picker this file. */
async function elegir(page, id, tipo, ruta) {
  const boton = elegirEn(page, id, COL[tipo]);
  await hasta(async () => boton.isEnabled().catch(() => false), 'el botón no está disponible');
  const [selector] = await Promise.all([page.waitForEvent('filechooser'), boton.click()]);
  await selector.setFiles({ name: ruta.split('/').at(-1), buffer: readFileSync(ruta), mimeType: tipoDe(ruta) });
}
const subidaCelda = (page, id) => celda(page, id, COL.kmz).locator('.archivos-celda-subida');
const fase = (page, id) => subidaCelda(page, id).getAttribute('data-fase').catch(() => null);
async function faseFinal(page, id) {
  await hasta(async () => TERMINAL.includes(await fase(page, id)), `fase final de ${id}`, 90000);
  return fase(page, id);
}
const textoSubida = async (page, id) => `${await subidaCelda(page, id).innerText().catch(() => '')} ${await subidaCelda(page, id).getAttribute('title').catch(() => '') ?? ''}`;
const foto = async (page, nombre) => { if (SHOTS) { await esperar(300); await page.screenshot({ path: join(SHOTS, `${nombre}.png`) }); } };

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

/* Map helpers (window.__araTabla is exposed with ?test=1). */
const modoBoton = (page, nombre) => page.locator('.tabla-modo').getByRole('button', { name: nombre, exact: true });
const mapa = (page) => page.evaluate(() => window.__araTabla?.mapa());
const previa = (page) => page.evaluate(() => window.__araTabla?.previa());
const posicion = (page, id) => page.evaluate((i) => window.__araTabla?.posicion(i), id);
async function aMapa(page) {
  await modoBoton(page, 'Mapa').click();
  await page.locator('.previa-mapa.leaflet-container').waitFor();
  await hasta(async () => { const m = await mapa(page); return m && !m.reuniendo && m.clave; }, 'el mapa no reunió su conjunto');
}
async function aTabla(page) {
  await modoBoton(page, 'Tabla').click();
  await page.locator('.tabla-lienzo').waitFor();
}

/* --------------------------------------------------------------- data */

const ada = await abrir('ada');
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base KML Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
igual((await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] })).status, 200, 'acceso');
const crear = async (nombre) => (await admin('POST', `/api/maestra/bases/${base.id}/terrenos`, { terreno: nombre })).datos.terreno.id;
const A = await crear('Lote KML Uno Ficticio');
const B = await crear('Lote KML Dos Ficticio');
const C = await crear('Lote KML Detalle Ficticio');
await ada.page.reload();
await ada.page.locator('.tabla-pantalla').waitFor();
ada.desde = Date.now();

/* ----------------------------------------------------------- journeys */

await revisar('administrador: la columna dice KMZ / KML y su botón admite ambos formatos', async () => {
  await irA(ada.page, base.id);
  await hasta(async () => (await resumen(ada.page, A, COL.kmz)) === 'Sin KMZ / KML', 'resumen vacío');
  igual((await ada.page.locator(`th[data-col="${COL.kmz}"]`).innerText()).trim(), 'KMZ / KML', 'encabezado');
  igual(await elegirEn(ada.page, A, COL.kmz).innerText(), 'Elegir KMZ o KML…', 'botón');
  igual(await celda(ada.page, A, COL.kmz).locator('input[type=file]').getAttribute('accept'), '.kmz,.kml', 'selector');
});

let geometriaA = null;
await revisar('administrador: un KML de un contorno (.KML) queda activo y se ve en el mapa', async () => {
  await elegir(ada.page, A, 'kmz', F.kml_simple);
  igual(await faseFinal(ada.page, A), 'listo', 'fase');
  const texto = await textoSubida(ada.page, A);
  cierto(/KML guardado; su contorno es el activo/.test(texto) && !/KMZ/.test(texto), `mensaje: ${texto}`);
  await hasta(async () => (await resumen(ada.page, A, COL.kmz)) === 'Contorno activo', 'resumen activo');
  igual(await resumen(ada.page, B, COL.kmz), 'Sin KMZ / KML', 'B no cambia');
  const t = await terreno(ada.page, A);
  igual([t.ubicacion.modo, t.draft.lat, t.draft.lon], ['geometria', null, null], 'contorno sin X/Y');
  geometriaA = t.ubicacion.geometria.id;
  await aMapa(ada.page);
  const p = await hasta(async () => posicion(ada.page, A), 'el terreno no está en el mapa');
  const caja = await ada.page.locator('.previa-mapa').boundingBox();
  await ada.page.mouse.click(caja.x + p.x, caja.y + p.y);
  await hasta(async () => (await mapa(ada.page))?.seleccion === A, 'no se seleccionó en el mapa');
  await hasta(async () => (await posicion(ada.page, A))?.contorno === true && (await previa(ada.page))?.cuerpos === 1,
    'el contorno del KML no se dibujó');
  await foto(ada.page, '01-kml-en-mapa');
  await aTabla(ada.page);
});

await revisar('administrador: un KML sin contorno y un .kml que es KMZ conservan el contorno anterior', async () => {
  await irA(ada.page, base.id);
  await elegir(ada.page, A, 'kmz', F.kml_invalido);
  igual(await faseFinal(ada.page, A), 'rechazado', 'fase sin contorno');
  let texto = await textoSubida(ada.page, A);
  cierto(/El KML se guardó, pero no tiene un contorno utilizable/.test(texto) && /contorno activo no cambió/.test(texto), `mensaje: ${texto}`);
  igual(await geometriaDe(ada.page, A), geometriaA, 'mismo contorno tras KML sin contorno');
  await elegir(ada.page, A, 'kmz', F.kml_falso);
  igual(await faseFinal(ada.page, A), 'fallido', 'fase discrepancia');
  texto = await textoSubida(ada.page, A);
  cierto(/se llama \.kml pero su contenido es un KMZ/.test(texto), `mensaje: ${texto}`);
  await esperar(400);
  igual(await resumen(ada.page, A, COL.kmz), 'Contorno activo', 'resumen');
  igual(await geometriaDe(ada.page, A), geometriaA, 'mismo contorno tras discrepancia');
});

await revisar('administrador: un KMZ reemplaza al KML en el mismo historial', async () => {
  await elegir(ada.page, A, 'kmz', F.kmz_reemplazo);
  igual(await faseFinal(ada.page, A), 'listo', 'fase');
  cierto(/KMZ guardado; su contorno es el activo/.test(await textoSubida(ada.page, A)), 'mensaje KMZ');
  const nueva = await hasta(async () => { const g = await geometriaDe(ada.page, A); return g !== geometriaA && g; }, 'el contorno no cambió');
  const versiones = (await llamar(ada.page, 'GET', `/api/inventario/terrenos/${A}/archivos`)).datos.archivos
    .filter((a) => a.tipo === 'kmz');
  igual(versiones.length, 1, 'una sola ranura de contorno');
  const lista = (await llamar(ada.page, 'GET', `/api/archivos/${versiones[0].id}/versiones?limite=20`)).datos.versiones;
  igual(lista.map((v) => [v.numero, v.estado, v.tipo_detectado]).sort((a, b) => a[0] - b[0]), [
    [1, 'disponible', 'application/vnd.google-earth.kml+xml'], [2, 'disponible', 'application/vnd.google-earth.kml+xml'],
    [3, 'fallido', null], [4, 'disponible', 'application/vnd.google-earth.kmz']], 'historial mixto');
  geometriaA = nueva;
});

await revisar('administrador: el detalle descarga el KML original con su nombre y bytes', async () => {
  await fila(ada.page, A).getByRole('button', { name: /Abrir terreno/ }).click();
  const d = ada.page.getByRole('dialog', { name: 'Lote KML Uno Ficticio' });
  const k = d.locator('.archivos-detalle[data-tipo="kmz"]');
  igual((await k.locator('.archivos-titulo').innerText()).trim(), 'KMZ / KML del terreno', 'título');
  igual(await k.locator('.archivos-elegir').innerText(), 'Elegir KMZ o KML…', 'botón del detalle');
  igual(await k.locator('input[type=file]').getAttribute('accept'), '.kmz,.kml', 'selector del detalle');
  cierto(/16 MiB para KML/.test(await k.locator('.archivos-zona').innerText()), 'límite visible');
  await k.locator('.archivos-item').first().getByRole('button', { name: 'Versiones' }).click();
  const v1 = k.locator('.archivos-version', { hasText: 'v1' }).first();
  await v1.waitFor();
  // The name the page gives the save (its anchor's download attribute). This
  // headless Chromium reports any non-ASCII name as "download", so the
  // attribute itself is what is checked.
  await ada.page.evaluate(() => {
    window.__nombres = [];
    const click = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () { if (this.download) window.__nombres.push(this.download); return click.call(this); };
  });
  const [descarga] = await Promise.all([ada.page.waitForEvent('download'), v1.getByRole('button', { name: /Descargar/ }).click()]);
  igual(await ada.page.evaluate(() => window.__nombres), ['Contorno Ñandú ficticio.KML'], 'nombre original');
  const ruta = await descarga.path();
  igual(sha(readFileSync(ruta)), sha(readFileSync(F.kml_simple)), 'mismos bytes');
  await d.getByRole('button', { name: 'Cerrar' }).last().click();
});

const olga = await abrir('olga');

await revisar('operador: un KML con varios contornos se elige y activa en la misma celda', async () => {
  await irA(olga.page, base.id);
  await elegir(olga.page, B, 'kmz', F.kml_varios);
  igual(await faseFinal(olga.page, B), 'requiere_seleccion', 'fase');
  cierto(/Varios contornos: elige cuál es el del terreno/.test(await celda(olga.page, B, COL.kmz).innerText()), 'indicación');
  cierto(/El KML tiene varios contornos/.test(await textoSubida(olga.page, B)), 'mensaje KML');
  // The list is right there in the cell; nothing is active until "Listo".
  const lista = celda(olga.page, B, COL.kmz).locator('.archivos-celda-contornos');
  const casillas = lista.locator('input[type=checkbox]:not([disabled])');
  await casillas.first().waitFor();
  cierto((await casillas.count()) >= 2, 'candidatos en la celda');
  cierto(/m²/.test(await lista.innerText()), 'cada contorno dice su área');
  await hasta(async () => (await resumen(olga.page, B, COL.kmz)) === 'KML sin contorno activo', 'resumen');
  igual((await terreno(olga.page, B)).ubicacion.modo, 'ninguna', 'no se activa solo');
  await foto(olga.page, '02-operador-kml-elegir-en-celda');
  // After a reload the same list is one click away: "Elegir contorno…".
  await olga.page.reload();
  olga.ultimoFoco = Date.now();            // a fresh page starts its own focus throttle (see enfocar)
  await olga.page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await hasta(async () => (await resumen(olga.page, B, COL.kmz)) === 'KML sin contorno activo', 'resumen tras recargar');
  await celda(olga.page, B, COL.kmz).getByRole('button', { name: 'Elegir contorno…' }).click();
  await casillas.first().waitFor();
  await casillas.first().check();
  await lista.getByRole('button', { name: 'Listo' }).click();
  await hasta(async () => (await terreno(olga.page, B)).ubicacion.modo === 'geometria', 'no se activó');
  await hasta(async () => (await resumen(olga.page, B, COL.kmz)) === 'Contorno activo', 'la celda no llegó a activo');
  igual(await lista.count(), 0, 'la lista se cierra');
  igual(await geometriaDe(olga.page, A), geometriaA, 'A no cambia');
});

await revisar('operador: un KML elegido en el detalle sobrevive a la recarga de la tabla por foco', async () => {
  await irA(olga.page, base.id);
  await fila(olga.page, C).getByRole('button', { name: /Abrir terreno/ }).click();
  const d = olga.page.getByRole('dialog', { name: 'Lote KML Detalle Ficticio' });
  const k = d.locator('.archivos-detalle[data-tipo="kmz"]');
  // Hold the PUT so the reload lands while the bytes are in flight.
  let soltar;
  const retenido = new Promise((r) => { soltar = r; });
  let vistos = 0;
  await olga.page.route('**/api/archivos/versiones/*/contenido', async (ruta) => {
    vistos += 1;
    await retenido;
    await ruta.continue();
  });
  const [selector] = await Promise.all([olga.page.waitForEvent('filechooser'), k.locator('.archivos-elegir').click()]);
  await selector.setFiles({ name: 'Forma U ficticia.kml', buffer: readFileSync(F.kml_detalle), mimeType: tipoDe(F.kml_detalle) });
  await hasta(async () => vistos === 1, 'el PUT no salió');
  await enfocar(olga);                     // the session revalidation ran mid-upload
  await esperar(1500);
  soltar();
  await olga.page.unroute('**/api/archivos/versiones/*/contenido');
  const li = k.locator('.archivos-subidas li').first();
  await hasta(async () => /KML guardado; su contorno es el activo/.test(await li.innerText().catch(() => '')),
    async () => `la subida no terminó: ${await li.innerText().catch(() => '(sin subida)')}`, 90000);
  igual(vistos, 1, 'los bytes se enviaron una sola vez');
  await d.getByRole('button', { name: 'Cerrar' }).last().click();
  await hasta(async () => (await resumen(olga.page, C, COL.kmz)) === 'Contorno activo', 'la celda no llegó a activo');
  igual((await terreno(olga.page, C)).ubicacion.modo, 'geometria', 'activado');
});

await revisar('regresión: un PDF sigue abriéndose desde su contador', async () => {
  await irA(olga.page, base.id);
  const boton = elegirEn(olga.page, A, COL.pdf);
  const [selector] = await Promise.all([olga.page.waitForEvent('filechooser'), boton.click()]);
  await selector.setFiles({ name: 'Avalúo ficticio.pdf', buffer: readFileSync(F.pdf), mimeType: 'application/pdf' });
  await hasta(async () => (await resumen(olga.page, A, COL.pdf)) === '1 archivo', 'la celda no dice 1 PDF', 90000);
  const [popup] = await Promise.all([olga.page.waitForEvent('popup'),
    celda(olga.page, A, COL.pdf).locator('.archivos-celda-abrir').click()]);
  await hasta(() => popup.url().startsWith('blob:'), `la pestaña no recibió el PDF (${popup.url()})`);
  const recibido = await popup.evaluate(async () => {
    const b = await (await fetch(location.href)).arrayBuffer();
    return [...new Uint8Array(await crypto.subtle.digest('SHA-256', b))].map((x) => x.toString(16).padStart(2, '0')).join('');
  });
  igual(recibido, sha(readFileSync(F.pdf)), 'mismos bytes del PDF');
  await popup.close();
});

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

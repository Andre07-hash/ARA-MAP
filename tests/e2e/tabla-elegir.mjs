/* "Elegir PDF…" / "Elegir KMZ…" in the table's file cells, with the REAL
 * widgets (web/components/archivos/celda.js), the real local server
 * (tests/e2e/tabla_servidor.py on a folder it creates and deletes), real
 * sessions and Chromium. Fictional accounts and files only.
 *
 *   cd tests/e2e && node tabla-elegir.mjs
 *
 * What it checks: an administrator and an authorized operator pick files
 * straight from the cells, empty and with files; each file lands on the row
 * whose button was used and the summaries follow; a KMZ with several contours
 * keeps its explicit choice and activation (in the detail, which still works);
 * an invalid replacement keeps the active boundary; a cancelled picker sends
 * nothing; the buttons work from the keyboard and never open a cell editor;
 * deleting a terrain from its detail removes its row and leaves the others'
 * buttons. Optional: ELEGIR_CAPTURAS=dir (screenshots), CHROMIUM=/path,
 * ELEGIR_PUERTO.
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
const PUERTO = Number(process.env.ELEGIR_PUERTO ?? 8481);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.ELEGIR_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-elegir-'));
const F = JSON.parse(execFileSync(PY, ['-c',
  'import json, sys\nfrom pathlib import Path\nsys.path.insert(0, "tests/e2e")\n' +
  'from archivos_servidor import escribir_fixtures\n' +
  'd = Path(sys.argv[1]); d.mkdir()\nprint(json.dumps(escribir_fixtures(d)))', join(CARPETA, 'fixtures')],
  { cwd: RAIZ, encoding: 'utf8' }));

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
  const s = { usuario, page, errores: [], escrituras: [] };
  page.on('pageerror', (e) => s.errores.push(String(e)));
  page.on('request', (r) => {
    if (r.method() !== 'GET' && r.url().includes('/api/archivos')) s.escrituras.push(`${r.method()} ${new URL(r.url()).pathname}`);
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

const fila = (page, id) => page.locator(`tr[data-id="${id}"]`);
const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const resumen = async (page, id, col) => (await celda(page, id, col).locator('.archivos-celda').innerText().catch(() => '')).trim();
const elegirEn = (page, id, col) => celda(page, id, col).locator('.archivos-celda-elegir');
const COL = { pdf: 'core:archivos', kmz: 'core:kmz' };

async function irA(page, vista) {
  await page.goto(`${URLBASE}/?test=1#/tabla/${vista}`);
  await page.locator('.tabla-pantalla').waitFor();
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
}
/** Click the cell's button and give the picker this file (a path) or nothing (cancel). */
async function elegir(page, id, tipo, ruta, { teclado = null } = {}) {
  const boton = elegirEn(page, id, COL[tipo]);
  await hasta(async () => boton.isEnabled().catch(() => false), 'el botón no está disponible');
  const [selector] = await Promise.all([
    page.waitForEvent('filechooser'),
    teclado ? boton.focus().then(() => page.keyboard.press(teclado)) : boton.click(),
  ]);
  if (ruta) {
    await selector.setFiles({ name: ruta.split('/').at(-1), buffer: readFileSync(ruta),
      mimeType: ruta.endsWith('.pdf') ? 'application/pdf' : 'application/vnd.google-earth.kmz' });
  } else {
    await selector.setFiles([]);
  }
}
const fase = (page, id, tipo) => celda(page, id, COL[tipo]).locator('.archivos-celda-subida').getAttribute('data-fase').catch(() => null);
async function faseFinal(page, id, tipo, fases) {
  await hasta(async () => fases.includes(await fase(page, id, tipo)), `fase ${fases}`, 90000);
  return fase(page, id, tipo);
}
// Wide enough to show the name column beside the file columns.
const foto = async (page, nombre) => {
  if (!SHOTS) return;
  const antes = page.viewportSize();
  await page.setViewportSize({ width: 2600, height: 700 });
  await esperar(300);
  await page.screenshot({ path: join(SHOTS, `${nombre}.png`) });
  await page.setViewportSize(antes);
};
const botonesVisibles = (page, id) => fila(page, id).locator('.archivos-celda-elegir:visible').count();

/* --------------------------------------------------------------- data */

const ada = await abrir('ada');
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Celdas Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
for (const b of [base]) igual((await admin('PUT', `/api/maestra/bases/${b.id}/acceso`, { expected_version: b.version, usuarios: [ops.olga] })).status, 200, 'acceso');
const crear = async (b, nombre) => (await admin('POST', `/api/maestra/bases/${b.id}/terrenos`, { terreno: nombre })).datos.terreno.id;
const A = await crear(base, 'Lote Celda Uno Ficticio');
const B = await crear(base, 'Lote Celda Dos Ficticio');
const C = await crear(base, 'Lote Celda Borrado Ficticio');

/* ----------------------------------------------------------- journeys */

await revisar('administrador: celdas vacías muestran su resumen y los dos botones', async () => {
  await irA(ada.page, base.id);
  for (const id of [A, B]) {
    await hasta(async () => (await resumen(ada.page, id, COL.pdf)) === 'Sin PDF', 'resumen PDF');
    igual(await resumen(ada.page, id, COL.kmz), 'Sin KMZ / KML', 'resumen KMZ');
    igual(await elegirEn(ada.page, id, COL.pdf).innerText(), 'Elegir PDF…', 'botón PDF');
    igual(await elegirEn(ada.page, id, COL.kmz).innerText(), 'Elegir KMZ o KML…', 'botón KMZ');
    igual(await botonesVisibles(ada.page, id), 2, 'dos botones visibles');
  }
});

await revisar('administrador: un PDF elegido en la fila B queda en B, no en A', async () => {
  await elegir(ada.page, B, 'pdf', F.pdf);
  igual(await faseFinal(ada.page, B, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']), 'listo', 'fase');
  await hasta(async () => (await resumen(ada.page, B, COL.pdf)) === '1 PDF', 'B no llegó a 1 PDF');
  igual(await resumen(ada.page, A, COL.pdf), 'Sin PDF', 'A no cambia');
  igual([(await terreno(ada.page, A)).archivos.pdf_total, (await terreno(ada.page, B)).archivos.pdf_total], [0, 1], 'servidor');
});

await revisar('administrador: otro PDF en una celda que ya tiene archivos', async () => {
  await elegir(ada.page, B, 'pdf', F.pdf2);
  igual(await faseFinal(ada.page, B, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']), 'listo', 'fase');
  await hasta(async () => (await resumen(ada.page, B, COL.pdf)) === '2 PDF', 'B no llegó a 2 PDF');
  igual((await terreno(ada.page, A)).archivos.pdf_total, 0, 'A sigue sin PDF');
});

let geometriaA = null;
await revisar('administrador: KMZ de un contorno en A (regla existente del servidor: un único contorno válido queda activo)', async () => {
  await elegir(ada.page, A, 'kmz', F.kmz_simple);
  igual(await faseFinal(ada.page, A, 'kmz', ['listo', 'requiere_seleccion', 'rechazado', 'fallido', 'interrumpido']), 'listo', 'fase');
  await hasta(async () => (await resumen(ada.page, A, COL.kmz)) === 'Contorno activo', 'A sin contorno activo');
  igual(await resumen(ada.page, B, COL.kmz), 'Sin KMZ / KML', 'B no cambia');
  const t = await terreno(ada.page, A);
  igual(t.ubicacion.modo, 'geometria', 'ubicación');
  geometriaA = t.ubicacion.geometria.id;
  await foto(ada.page, '01-administrador-botones-en-tabla');
});

await revisar('administrador: un reemplazo KMZ inválido conserva el contorno anterior', async () => {
  await elegir(ada.page, A, 'kmz', F.kmz_invalido);
  igual(await faseFinal(ada.page, A, 'kmz', ['listo', 'requiere_seleccion', 'rechazado', 'fallido', 'interrumpido']), 'rechazado', 'fase');
  cierto(/contorno activo no cambió/.test(await celda(ada.page, A, COL.kmz).locator('.archivos-celda-subida').innerText()), 'mensaje');
  await esperar(500);
  igual(await resumen(ada.page, A, COL.kmz), 'Contorno activo', 'resumen');
  igual((await terreno(ada.page, A)).ubicacion.geometria?.id, geometriaA, 'mismo contorno');
});

const olga = await abrir('olga');

await revisar('operador: PDF en una celda vacía (A) y en una con archivos (B), cada uno en su fila', async () => {
  await irA(olga.page, base.id);
  await hasta(async () => (await resumen(olga.page, A, COL.pdf)) === 'Sin PDF', 'resumen');
  igual(await botonesVisibles(olga.page, A), 2, 'botones');
  await elegir(olga.page, A, 'pdf', F.pdf2);
  igual(await faseFinal(olga.page, A, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']), 'listo', 'fase A');
  await hasta(async () => (await resumen(olga.page, A, COL.pdf)) === '1 PDF', 'A no llegó a 1 PDF');
  await elegir(olga.page, B, 'pdf', F.pdf);
  igual(await faseFinal(olga.page, B, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']), 'listo', 'fase B');
  await hasta(async () => (await resumen(olga.page, B, COL.pdf)) === '3 PDF', 'B no llegó a 3 PDF');
  igual([(await terreno(olga.page, A)).archivos.pdf_total, (await terreno(olga.page, B)).archivos.pdf_total], [1, 3], 'servidor');
});

await revisar('operador: KMZ con varios contornos en B no activa nada; se elige y activa en el detalle', async () => {
  await elegir(olga.page, B, 'kmz', F.kmz_varios);
  igual(await faseFinal(olga.page, B, 'kmz', ['listo', 'requiere_seleccion', 'rechazado', 'fallido', 'interrumpido']), 'requiere_seleccion', 'fase');
  cierto(/Varios contornos: elige en el detalle/.test(await celda(olga.page, B, COL.kmz).innerText()), 'indicación');
  await hasta(async () => (await resumen(olga.page, B, COL.kmz)) === 'KMZ sin contorno activo', 'resumen');
  igual((await terreno(olga.page, B)).ubicacion.modo, 'ninguna', 'no se activa solo');
  igual((await terreno(olga.page, A)).ubicacion.geometria?.id, geometriaA, 'A no cambia');
  await foto(olga.page, '02-operador-botones-en-tabla');
  // The detail flow is still there: choose, process, activate explicitly.
  await fila(olga.page, B).getByRole('button', { name: /Abrir terreno/ }).click();
  const d = olga.page.getByRole('dialog', { name: 'Lote Celda Dos Ficticio' });
  const k = d.locator('.archivos-detalle[data-tipo="kmz"]');
  await k.locator('.archivos-item').first().getByRole('button', { name: 'Versiones' }).click();
  await k.getByRole('button', { name: /Contornos de la versión 1/ }).click();
  await k.getByRole('button', { name: 'Elegir contornos…' }).click();
  const casillas = k.locator('.archivos-candidatos input[type=checkbox]:not([disabled])');
  await casillas.first().waitFor();
  cierto((await casillas.count()) >= 2, 'candidatos');
  await casillas.first().check();
  await k.getByRole('button', { name: 'Procesar selección' }).click();
  await k.locator('.archivos-mensaje', { hasText: 'Todavía no está activa' }).waitFor({ timeout: 60000 });
  igual((await terreno(olga.page, B)).ubicacion.modo, 'ninguna', 'procesar no activa');
  await k.locator('.archivos-intento', { hasText: 'Contorno válido' }).getByRole('button', { name: 'Activar este contorno' }).click();
  await d.getByRole('button', { name: 'Cerrar' }).last().click();
  await hasta(async () => (await resumen(olga.page, B, COL.kmz)) === 'Contorno activo', 'la celda no llegó a activo');
  igual((await terreno(olga.page, B)).ubicacion.modo, 'geometria', 'activado');
});

await revisar('cancelar el selector no envía nada ni cambia el resumen', async () => {
  const antes = olga.escrituras.length;
  const estado = async () => celda(olga.page, A, COL.pdf).locator('.archivos-celda-subida').innerText().catch(() => '');
  const estadoAntes = await estado();
  await elegir(olga.page, A, 'pdf', null);
  await elegir(olga.page, A, 'kmz', null);
  await esperar(500);
  igual(olga.escrituras.slice(antes), [], 'escrituras');
  igual([await resumen(olga.page, A, COL.pdf), await resumen(olga.page, A, COL.kmz)], ['1 PDF', 'Contorno activo'], 'resúmenes');
  igual(await estado(), estadoAntes, 'el estado de la última subida no cambia');
});

await revisar('teclado: Enter y Espacio abren el selector; ni teclas ni doble clic abren un editor', async () => {
  const antes = olga.escrituras.length;
  const editor = () => olga.page.locator('.tabla-editor, td.is-editando').count();
  cierto((await elegirEn(olga.page, A, COL.pdf).getAttribute('tabindex')) !== '-1', 'fuera del orden de tabulación');
  await elegir(olga.page, A, 'pdf', null, { teclado: 'Enter' });
  igual(await editor(), 0, 'Enter abrió un editor');
  await elegir(olga.page, A, 'kmz', null, { teclado: ' ' });
  igual(await editor(), 0, 'Espacio abrió un editor');
  await elegirEn(olga.page, A, COL.pdf).focus();
  await olga.page.keyboard.press('F2');
  await olga.page.keyboard.press('x');
  igual(await editor(), 0, 'F2 o una letra abrieron un editor');
  olga.page.on('filechooser', (s) => s.setFiles([]).catch(() => {}));
  await elegirEn(olga.page, A, COL.pdf).dblclick();
  await esperar(300);
  igual(await editor(), 0, 'el doble clic abrió un editor');
  // Tab from the button moves on, like any button.
  await elegirEn(olga.page, A, COL.pdf).focus();
  await olga.page.keyboard.press('Tab');
  cierto(await olga.page.evaluate(() => !document.activeElement?.classList.contains('archivos-celda-elegir')
    || document.activeElement.closest('td')?.dataset.col === 'core:kmz'), 'Tab no avanzó');
  igual(olga.escrituras.slice(antes), [], 'nada enviado');
});

await revisar('borrar un terreno desde su detalle: la fila sale y las demás conservan sus botones', async () => {
  await irA(ada.page, base.id);
  await fila(ada.page, C).getByTitle('Detalle, historial, transferir y borrar').click();
  await ada.page.getByRole('dialog', { name: 'Lote Celda Borrado Ficticio' }).getByRole('button', { name: 'Borrar terreno…' }).click();
  await ada.page.getByRole('dialog', { name: '¿Borrar «Lote Celda Borrado Ficticio»?' })
    .getByRole('button', { name: 'Borrar definitivamente' }).click();
  await hasta(async () => (await fila(ada.page, C).count()) === 0, 'la fila borrada sigue en la tabla');
  igual((await llamar(ada.page, 'GET', `/api/inventario/terrenos/${C}`)).status, 404, 'el terreno sigue en el servidor');
  igual(await botonesVisibles(ada.page, A), 2, 'fila vecina');
});

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

/* PDF uploads that survive the table's own refreshes (issue #39), with the
 * REAL widgets, the real local server (tests/e2e/tabla_servidor.py on a folder
 * it creates and deletes), real sessions and Chromium. Fictional accounts and
 * files only; requests are held with page.route to control the timing.
 *
 *   cd tests/e2e && node tabla-subidas.mjs
 *
 * What it checks: a window focus / visibility revalidation while a PDF is
 * being sent or verified does not abort it; a table reload that was already
 * in flight and answers mid-upload keeps it; creating another row, Actualizar,
 * filters and pages keep it or ask first; closing the record detail (button,
 * Escape, backdrop) asks before interrupting; retry and cancel still work;
 * logout and another account stop everything; the saved PDF downloads with the
 * same bytes; incomplete, expired and rejected uploads are said as such and an
 * earlier saved PDF stays reachable. Optional: SUBIDAS_CAPTURAS=dir,
 * CHROMIUM=/path, SUBIDAS_PUERTO.
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
const PUERTO = Number(process.env.SUBIDAS_PUERTO ?? 8485);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.SUBIDAS_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-subidas-'));
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
    if (Date.now() > fin) throw new Error(typeof mensaje === 'function' ? await mensaje() : mensaje);
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

async function irA(page, vista, { archivados = false } = {}) {
  await page.goto(`${URLBASE}/?test=1#/tabla/${vista}`);
  await page.locator('.tabla-pantalla').waitFor();
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  if (archivados) {
    await page.locator('#tabla-archivados').check();
    await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  }
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

/* ------------------------------------------------------- held requests */

/** Hold every request matching `patron` (and `metodo`) until soltar(). */
async function retener(page, patron, metodo = null) {
  let abrir;
  const puerta = new Promise((r) => { abrir = r; });
  const vistos = [];
  const manejador = async (route) => {
    if (metodo && route.request().method() !== metodo) return route.fallback();
    vistos.push(route.request().url());
    await puerta;
    await route.continue().catch(() => {});   // the page may have aborted it meanwhile
  };
  await page.route(patron, manejador);
  return {
    vistos,
    async soltar() { abrir(); await page.unroute(patron, manejador); },
  };
}
function vigilar(s) {
  s.lecturas = [];
  s.desde = Date.now();
  s.page.on('request', (r) => { if (r.url().includes('/api/')) s.lecturas.push(`${r.method()} ${new URL(r.url()).pathname}${new URL(r.url()).search}`); });
}
/* Chromium reports a reply whose stream the client lets go after reading it
 * as "aborted" too, so aborts prove nothing here. What does: the upload ends
 * "Listo", the server holds the PDF, and its bytes were sent exactly once. */
const marca = (s) => s.lecturas.length;
const contenidos = (s, desde = 0) => {
  const puts = s.lecturas.slice(desde).filter((l) => /^PUT \/api\/archivos\/versiones\/[^/]+\/contenido/.test(l));
  return puts.length === 1 ? [] : puts;
};
const listas = (s) => s.lecturas.filter((l) => /^GET \/api\/(maestra\/bases\/[^/]+|inventario)\/terrenos\?/.test(l)).length;

/* app.js revalidates on focus at most every 10 s, per page: wait that out,
 * focus, and wait for the session check that proves the revalidation ran. */
const ultimoFoco = new Map();
async function enfocar(s, como = 'focus') {
  const falta = 10_500 - (Date.now() - (ultimoFoco.get(s.page) ?? s.desde ?? 0));
  if (falta > 0) await esperar(falta);
  const antes = s.lecturas.filter((l) => l === 'GET /api/session').length;
  await s.page.evaluate((c) => {
    if (c === 'focus') window.dispatchEvent(new Event('focus'));
    else document.dispatchEvent(new Event('visibilitychange'));
  }, como);
  ultimoFoco.set(s.page, Date.now());
  await hasta(async () => s.lecturas.filter((l) => l === 'GET /api/session').length > antes, 'no hubo revalidación');
}
/** Whether the terrain has a saved (finalized) PDF, by the server's own summary. */
const pdfGuardado = async (page, id) => ((await terreno(page, id))?.archivos?.pdf_recientes ?? [])
  .some((f) => f.version_actual_id);
const PUT_CONTENIDO = '**/api/archivos/versiones/*/contenido';
const COMPLETAR = '**/api/archivos/versiones/*/completar';

/* --------------------------------------------------------------- data */

const ada = await abrir('ada');
vigilar(ada);
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Subidas Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
igual((await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] })).status, 200, 'acceso');
const crear = async (nombre) => (await admin('POST', `/api/maestra/bases/${base.id}/terrenos`, { terreno: nombre })).datos.terreno.id;
const T = {};
for (const k of ['foco', 'recarga', 'completar', 'otraFila', 'filtro', 'detalle', 'cancelar', 'operador', 'salida', 'previo', 'vencida', 'selector']) {
  T[k] = await crear(`Lote Subida ${k} Ficticio`);
}
// The table read its bases when the session opened: read them again.
await ada.page.reload();
await ada.page.locator('.tabla-pantalla').waitFor();
ada.desde = Date.now();          // the reloaded page starts its own revalidation clock

/* ----------------------------------------------------------- journeys */

await revisar('foco de la ventana mientras se envía el PDF: la subida no se interrumpe', async () => {
  await irA(ada.page, base.id);
  const desde = marca(ada);
  const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
  await elegir(ada.page, T.foco, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, async () => `el PUT no salió (${await fase(ada.page, T.foco, 'pdf')})`);
  await enfocar(ada, 'focus');
  await esperar(1500);                       // time for a revalidation reload to run
  await put.soltar();
  igual(await faseFinal(ada.page, T.foco, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']).catch(() => null), 'listo', 'fase final');
  igual(contenidos(ada, desde), [], 'los bytes se enviaron una sola vez');
  cierto(await pdfGuardado(ada.page, T.foco), 'el servidor no tiene el PDF guardado');
  await hasta(async () => (await resumen(ada.page, T.foco, COL.pdf)) === '1 PDF', 'la celda no dice 1 PDF');
});

await revisar('regreso del selector de archivos: el foco recarga la tabla antes de que llegue el archivo', async () => {
  await irA(ada.page, base.id);
  const listasAntes = listas(ada);
  const [selector] = await Promise.all([ada.page.waitForEvent('filechooser'), elegirEn(ada.page, T.selector, COL.pdf).click()]);
  await enfocar(ada, 'focus');                                // the picker closing gives the window focus first
  await hasta(async () => listas(ada) > listasAntes, 'la revalidación no recargó la tabla');
  await ada.page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await selector.setFiles({ name: 'Avalúo ficticio.pdf', buffer: readFileSync(F.pdf), mimeType: 'application/pdf' });
  igual(await faseFinal(ada.page, T.selector, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']).catch(() => null), 'listo',
    'el archivo elegido se perdió con la recarga');
  cierto(await pdfGuardado(ada.page, T.selector), 'el servidor no tiene el PDF guardado');
});

await revisar('crear otra fila durante la subida no la interrumpe', async () => {
  await irA(ada.page, base.id);
  const desde = marca(ada);
  const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
  await elegir(ada.page, T.otraFila, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  await ada.page.getByRole('button', { name: 'Agregar terreno' }).click();
  await hasta(async () => (await ada.page.locator('tr.tabla-fila.is-nueva').count()) === 1, 'la fila nueva no apareció');
  await esperar(300);
  await put.soltar();
  igual(await faseFinal(ada.page, T.otraFila, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']).catch(() => null), 'listo', 'fase final');
  igual(contenidos(ada, desde), [], 'los bytes se enviaron una sola vez');
  cierto(await pdfGuardado(ada.page, T.otraFila), 'el servidor no tiene el PDF guardado');
});

const olga = await abrir('olga');
vigilar(olga);
await revisar('operador: volver a la pestaña mientras se verifica el PDF no interrumpe la subida', async () => {
  await irA(olga.page, base.id);
  const desde = marca(olga);
  const fin = await retener(olga.page, COMPLETAR, 'POST');
  await elegir(olga.page, T.operador, 'pdf', F.pdf);
  await hasta(async () => fin.vistos.length === 1, 'la verificación no salió');
  await enfocar(olga, 'visibilitychange');
  await esperar(1500);
  await fin.soltar();
  igual(await faseFinal(olga.page, T.operador, 'pdf', ['listo', 'fallido', 'interrumpido', 'incierto']).catch(() => null), 'listo', 'fase final');
  igual(contenidos(olga, desde), [], 'los bytes se enviaron una sola vez');
  cierto(await pdfGuardado(ada.page, T.operador), 'el servidor no tiene el PDF guardado');
});

/* --------------------------------------------- filters, views, detail */

const aviso = (page) => page.locator('.tabla-subidas');
const dialogo = (page, nombre) => page.getByRole('dialog', { name: nombre });
const sha = (ruta) => execFileSync(PY, ['-c', 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())', ruta],
  { encoding: 'utf8' }).trim();
/** The server's bytes of a version, hashed in the page (same private route the widgets use). */
const shaDescarga = (page, versionId) => page.evaluate(async (v) => {
  const r = await fetch(`/api/archivos/versiones/${v}/descarga`, { credentials: 'same-origin' });
  const h = await crypto.subtle.digest('SHA-256', await r.arrayBuffer());
  return { status: r.status, sha: [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('') };
}, versionId);
const versionGuardada = async (page, id) => ((await terreno(page, id))?.archivos?.pdf_recientes ?? [])
  .find((f) => f.version_actual_id)?.version_actual_id ?? null;
const BD = join(CARPETA, 'instalacion', 'desechable.db');
/** Disposable DB only: let an unfinished upload's deadline pass and drop its lease, as time would. */
function vencer(versionId) {
  execFileSync(PY, ['-c', 'import sqlite3,sys\nc=sqlite3.connect(sys.argv[1])\n'
    + 'c.execute("UPDATE archivo_version SET completar_antes_de=? WHERE id=? AND estado=?",("2000-01-01T00:00:00+00:00",sys.argv[2],"subiendo"))\n'
    + 'c.execute("DELETE FROM archivo_trabajo WHERE archivo_version_id=?",(sys.argv[2],))\nc.commit()', BD, versionId]);
}
const versionDelPut = (url) => url.match(/versiones\/([0-9a-f-]{36})\/contenido/)[1];

await revisar('filtrar y Actualizar durante la subida: sigue, también fuera de la página, y lo dice', async () => {
  await irA(ada.page, base.id);
  const desde = marca(ada);
  const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
  await elegir(ada.page, T.filtro, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  await ada.page.getByRole('button', { name: 'Actualizar' }).click();
  await ada.page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  igual(await fase(ada.page, T.filtro, 'pdf'), 'subiendo', 'Actualizar conserva la celda');
  await ada.page.locator('#tabla-buscar').fill('Lote Subida foco Ficticio');      // its row leaves the page
  await hasta(async () => (await fila(ada.page, T.filtro).count()) === 0, 'la fila no salió');
  await hasta(async () => aviso(ada.page).isVisible(), 'sin aviso de la subida fuera de la página');
  cierto(/Una subida sigue en curso/.test(await aviso(ada.page).innerText()), 'texto del aviso');
  await put.soltar();
  await hasta(async () => pdfGuardado(ada.page, T.filtro), 'el servidor no guardó el PDF de la fila filtrada');
  await hasta(async () => !(await aviso(ada.page).isVisible()), 'el aviso no se quitó');
  igual(contenidos(ada, desde), [], 'los bytes se enviaron una sola vez');
  await ada.page.locator('#tabla-buscar').fill('');
  await hasta(async () => (await resumen(ada.page, T.filtro, COL.pdf)) === '1 PDF', 'al volver, 1 PDF');
});

await revisar('cambiar de vista pregunta antes de interrumpir; quedarse conserva la subida', async () => {
  await irA(ada.page, base.id);
  const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
  await elegir(ada.page, T.cancelar, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  await ada.page.locator('#tabla-vista').selectOption('maestra');
  const d = dialogo(ada.page, '¿Interrumpir la subida de archivos?');
  await d.waitFor();
  cierto(/se interrumpe/.test(await d.innerText()) && /mismo archivo/.test(await d.innerText()), 'el aviso explica qué pasa');
  await d.getByRole('button', { name: 'Seguir en esta vista' }).click();
  igual(await ada.page.locator('#tabla-vista').inputValue(), base.id, 'la vista no cambió');
  // Escape on that question also stays, and nothing is left waiting.
  await ada.page.locator('#tabla-vista').selectOption('maestra');
  await d.waitFor();
  await ada.page.keyboard.press('Escape');
  await hasta(async () => (await ada.page.locator('#tabla-vista').inputValue()) === base.id, 'Escape dejó la vista a medias');
  igual(await d.count(), 0, 'la pregunta sigue abierta');
  igual(await fase(ada.page, T.cancelar, 'pdf'), 'subiendo', 'la subida sigue');
  // Its own Cancelar still works while the PUT is held.
  await celda(ada.page, T.cancelar, COL.pdf).getByRole('button', { name: 'Cancelar' }).click();
  await put.soltar();
  igual(await faseFinal(ada.page, T.cancelar, 'pdf', ['cancelado', 'incierto', 'interrumpido']), 'cancelado', 'cancelada');
  cierto(!(await pdfGuardado(ada.page, T.cancelar)), 'cancelada: nada guardado');
  // Nothing unfinished now: the view changes without asking.
  await ada.page.locator('#tabla-vista').selectOption('maestra');
  await hasta(async () => /#\/tabla\/maestra/.test(ada.page.url()), 'no cambió de vista');
  igual(await dialogo(ada.page, '¿Interrumpir la subida de archivos?').count(), 0, 'sin pregunta');
});

await revisar('cambiar de vista e interrumpir, confirmado: la vista cambia y no se guarda nada a medias', async () => {
  await irA(ada.page, base.id);
  const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
  await elegir(ada.page, T.salida, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  await ada.page.locator('#tabla-vista').selectOption('maestra');
  await dialogo(ada.page, '¿Interrumpir la subida de archivos?').getByRole('button', { name: 'Interrumpir y cambiar de vista' }).click();
  await hasta(async () => /#\/tabla\/maestra/.test(ada.page.url()), 'no cambió de vista');
  await put.soltar();
  await esperar(500);
  cierto(!(await pdfGuardado(ada.page, T.salida)), 'nada guardado de la subida interrumpida');
});

await revisar('detalle: cerrar, Escape y el fondo preguntan durante la subida; el PDF guardado se descarga igual', async () => {
  await irA(ada.page, base.id);
  await fila(ada.page, T.detalle).getByRole('button', { name: /Abrir terreno/ }).click();
  const det = dialogo(ada.page, 'Lote Subida detalle Ficticio');
  await det.waitFor();
  const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
  const boton = det.locator('.archivos-elegir').first();
  const [selector] = await Promise.all([ada.page.waitForEvent('filechooser'), boton.click()]);
  await selector.setFiles({ name: 'Avalúo ficticio.pdf', buffer: readFileSync(F.pdf), mimeType: 'application/pdf' });
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  const pregunta = dialogo(ada.page, '¿Cerrar e interrumpir la subida?');
  for (const [como, accion] of [
    ['Escape', () => ada.page.keyboard.press('Escape')],
    ['fondo', async () => { const b = await det.boundingBox(); await ada.page.mouse.click(Math.max(5, b.x - 20), b.y + 10); }],
    ['botón Cerrar', () => det.getByRole('button', { name: 'Cerrar', exact: true }).click()],
  ]) {
    await accion();
    await pregunta.waitFor().catch(() => { throw new Error(`${como}: no preguntó`); });
    await pregunta.getByRole('button', { name: 'Seguir en el detalle' }).click();
    cierto(await det.isVisible(), `${como}: el detalle se cerró`);
  }
  // Escape on the question is a "no", and the detail still asks next time.
  await ada.page.keyboard.press('Escape');
  await pregunta.waitFor();
  await ada.page.keyboard.press('Escape');
  await hasta(async () => (await pregunta.count()) === 0, 'Escape no cerró la pregunta');
  cierto(await det.isVisible(), 'Escape en la pregunta cerró el detalle');
  await det.getByRole('button', { name: 'Cerrar', exact: true }).click();
  await pregunta.waitFor().catch(() => { throw new Error('tras Escape, «Cerrar» ya no pregunta'); });
  await pregunta.getByRole('button', { name: 'Seguir en el detalle' }).click();
  // Keyboard only, Escape after Escape: never past the question, never two of them.
  for (let i = 0; i < 6; i += 1) { await ada.page.keyboard.press('Escape'); await esperar(150); }
  cierto(await det.isVisible(), 'Escape repetido cerró el detalle');
  cierto((await pregunta.count()) <= 1, 'quedaron preguntas apiladas');
  if (await pregunta.count()) await pregunta.getByRole('button', { name: 'Seguir en el detalle' }).click();
  igual(await det.locator('[data-fase="subiendo"]').count(), 1, 'la subida del detalle sigue');
  await put.soltar();
  await hasta(async () => pdfGuardado(ada.page, T.detalle), 'el servidor no guardó el PDF del detalle');
  await hasta(async () => (await det.locator('.archivos-subida[data-fase="listo"], [data-fase="listo"]').count()) > 0, 'el detalle no dijo Listo');
  await det.getByRole('button', { name: 'Cerrar', exact: true }).click();
  await hasta(async () => !(await det.isVisible()), 'el detalle no se cerró sin subida');
  igual(await pregunta.count(), 0, 'sin pregunta al terminar');
  const v = await versionGuardada(ada.page, T.detalle);
  igual(await shaDescarga(ada.page, v), { status: 200, sha: sha(F.pdf) }, 'mismos bytes al descargar');
});

await revisar('una red caída a mitad del envío: se dice y «Reintentar» termina la misma subida', async () => {
  await irA(ada.page, base.id);
  let fallar = true;
  const patron = PUT_CONTENIDO;
  const manejador = (route) => (route.request().method() === 'PUT' && fallar ? (fallar = false, route.abort('failed')) : route.fallback());
  await ada.page.route(patron, manejador);
  await elegir(ada.page, T.previo, 'pdf', F.pdf);
  igual(await faseFinal(ada.page, T.previo, 'pdf', ['incierto', 'interrumpido', 'fallido', 'listo']), 'incierto', 'se dice sin confirmar');
  await celda(ada.page, T.previo, COL.pdf).getByRole('button', { name: 'Reintentar' }).click();
  igual(await faseFinal(ada.page, T.previo, 'pdf', ['listo', 'fallido']), 'listo', 'reintento');
  await ada.page.unroute(patron, manejador);
  cierto(await pdfGuardado(ada.page, T.previo), 'guardado tras reintentar');
});

await revisar('estados: subida vencida sin PDF previo, y con un PDF guardado que sigue disponible', async () => {
  // Two unfinished uploads, left as a closed tab would leave them, then past their deadline.
  for (const id of [T.vencida, T.previo]) {
    await irA(ada.page, base.id);
    const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
    await elegir(ada.page, id, 'pdf', F.pdf2);
    await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
    const v = versionDelPut(put.vistos[0]);
    await ada.page.goto('about:blank');          // the tab goes away mid-upload
    await put.soltar().catch(() => {});
    vencer(v);
  }
  await irA(ada.page, base.id);
  igual(await resumen(ada.page, T.vencida, COL.pdf), 'Sin PDF guardado', 'sin PDF previo');
  cierto(/subida vencida/i.test(await celda(ada.page, T.vencida, COL.pdf).locator('.archivos-celda').getAttribute('title')), 'dice subida vencida');
  igual(await resumen(ada.page, T.previo, COL.pdf), '1 PDF', 'el PDF guardado sigue contando');
  cierto(/subida vencida/i.test(await celda(ada.page, T.previo, COL.pdf).locator('.archivos-celda').getAttribute('title')), 'con nota de la subida vencida');
  const texto = await ada.page.locator('.tabla-lienzo').innerText();
  cierto(!/PDF vencido/.test(texto), 'nunca «PDF vencido»');
  // The detail: no download for the never-finished one; the saved one stays reachable.
  await fila(ada.page, T.vencida).getByRole('button', { name: /Abrir terreno/ }).click();
  let det = dialogo(ada.page, 'Lote Subida vencida Ficticio');
  await hasta(async () => /Subida vencida/.test(await det.innerText()), 'el detalle no dice subida vencida');
  cierto(/Sin PDF guardado/.test(await det.innerText()), 'chip sin PDF guardado');
  igual(await det.getByRole('button', { name: /^Descargar|^Abrir$/ }).count(), 0, 'nada que descargar');
  await det.getByRole('button', { name: 'Cerrar', exact: true }).click();
  await fila(ada.page, T.previo).getByRole('button', { name: /Abrir terreno/ }).click();
  det = dialogo(ada.page, 'Lote Subida previo Ficticio');
  // Each PDF chosen is its own attachment: the saved one and the expired attempt side by side.
  const guardado = det.locator('.archivos-item').filter({ has: ada.page.locator('.archivos-chip-actual') });
  const vencido = det.locator('.archivos-item').filter({ hasText: 'Sin PDF guardado' });
  await hasta(async () => (await guardado.count()) === 1 && (await vencido.count()) === 1, 'el detalle no muestra los dos adjuntos');
  cierto(/Subida vencida/.test(await vencido.innerText()), 'el intento dice subida vencida');
  igual(await vencido.getByRole('button', { name: /^Descargar|^Abrir/ }).count(), 0, 'el intento no se descarga');
  const [descarga] = await Promise.all([ada.page.waitForEvent('download'),
    guardado.getByRole('button', { name: /^Descargar / }).click()]);
  igual(sha(await descarga.path()), sha(F.pdf), 'el PDF guardado sigue disponible, con los mismos bytes');
  await foto(ada.page, '02-detalle-subida-vencida-con-previo');
  await det.getByRole('button', { name: 'Cerrar', exact: true }).click();
});

await revisar('operador: cerrar sesión durante la subida pregunta; al confirmar, nada más se pide ni se muestra', async () => {
  await irA(olga.page, base.id);
  const put = await retener(olga.page, PUT_CONTENIDO, 'PUT');
  await elegir(olga.page, T.salida, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  await olga.page.getByRole('button', { name: 'Cerrar sesión' }).click();
  const d = dialogo(olga.page, '¿Cerrar sesión e interrumpir la subida?');
  await d.waitFor();
  await d.getByRole('button', { name: 'Seguir en la sesión' }).click();
  cierto(await olga.page.locator('.session-user').isVisible(), 'sigue la sesión');
  await olga.page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await d.getByRole('button', { name: 'Cerrar sesión' }).click();
  await hasta(async () => (await olga.page.locator('.session-user').count()) === 0, 'no cerró sesión');
  const antes = olga.lecturas.length;
  await put.soltar();
  await esperar(1500);
  const despues = olga.lecturas.slice(antes).filter((l) => l.includes('/api/archivos') || l.includes('/api/maestra') || l.includes('/api/inventario'));
  igual(despues, [], 'ninguna petición privada tras cerrar sesión');
  igual(await olga.page.locator('.tabla-pantalla').count(), 0, 'la tabla privada ya no está');
  cierto(!(await pdfGuardado(ada.page, T.salida)), 'nada guardado a medias');
});

await revisar('la sesión termina en otra pestaña durante la subida: la revalidación sigue y no se pide nada más', async () => {
  const s = await abrir('alan');
  vigilar(s);
  await irA(s.page, base.id);
  const put = await retener(s.page, PUT_CONTENIDO, 'PUT');
  await elegir(s.page, T.completar, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  const v = versionDelPut(put.vistos[0]);
  await llamar(s.page, 'POST', '/api/logout');                 // as another tab would
  await enfocar(s, 'focus');                                    // the session check still runs during the upload
  await hasta(async () => (await s.page.locator('.session-user').count()) === 0, 'la sesión terminada no se dijo');
  const antes = s.lecturas.length;
  await put.soltar();
  await esperar(1500);
  igual(s.lecturas.slice(antes).filter((l) => l.includes(v) || /\/api\/(maestra|inventario|archivos)/.test(l)), [],
    'ninguna petición privada tras la sesión terminada');
  igual(await s.page.locator('.tabla-pantalla').count(), 0, 'la tabla privada ya no está');
});

await revisar('otra cuenta en la misma ventana durante la subida: lo anterior se retira y nada sigue bajo la nueva', async () => {
  await irA(ada.page, base.id);
  const put = await retener(ada.page, PUT_CONTENIDO, 'PUT');
  await elegir(ada.page, T.recarga, 'pdf', F.pdf);
  await hasta(async () => put.vistos.length === 1, 'el PUT no salió');
  const v = versionDelPut(put.vistos[0]);
  igual((await llamar(ada.page, 'POST', '/api/login', { username: 'olga', password: CLAVE })).status, 200, 'otra cuenta');
  await enfocar(ada, 'focus');
  await hasta(async () => /Olga/.test(await ada.page.locator('.session-user').innerText().catch(() => '')), 'no cambió de cuenta');
  const antes = ada.lecturas.length;
  await put.soltar();
  await esperar(1500);
  igual(ada.lecturas.slice(antes).filter((l) => l.includes(v) || l.includes(`/terrenos/${T.recarga}/archivos`)), [],
    'nada de la subida anterior bajo la cuenta nueva');
  igual(await celda(ada.page, T.recarga, COL.pdf).locator('.archivos-celda-subida[data-fase]').count(), 0,
    'la cuenta nueva no ve la subida de la anterior');
});

/* ---------------------------------------------------------------- end */

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

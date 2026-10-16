/* Opening saved PDFs from the table's PDF cell (issue #48), with the REAL
 * widgets, the real local server (tests/e2e/tabla_servidor.py on a folder it
 * creates and deletes), real sessions and Chromium. Fictional accounts and
 * files only.
 *
 *   cd tests/e2e && node tabla-abrir-pdf.mjs
 *
 * What it checks: "1 PDF" opens that saved PDF in a new tab with the same
 * bytes, from the right row; several PDFs open a chooser whose every choice
 * opens the right document, also beyond the summary's five recent ones and
 * across list pages; no PDF, unfinished, expired and rejected uploads are not
 * links, and a saved PDF next to a failed one stays openable; the
 * administrator, an authorized operator and a read-only session can open;
 * a deleted document and a lost session are handled without empty tabs;
 * clicks and keys never open a cell editor nor change the row selection;
 * closing the chooser or leaving the view drops late answers; repeated clicks
 * open one tab; a refused tab offers a link. "Elegir PDF…", uploads, the
 * detail's "Abrir" and the KMZ cell keep working.
 * Optional: ABRIR_CAPTURAS=dir (screenshots), CHROMIUM=/path, ABRIR_PUERTO.
 */

import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.ABRIR_PUERTO ?? 8483);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.ABRIR_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-abrir-'));
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
const BD = join(CARPETA, 'instalacion', 'desechable.db');

/* ------------------------------------------------------------ harness */

let fallos = 0;
const retenidas = new Set();       // held routes, released if a check fails midway
async function revisar(nombre, fn) {
  if (process.env.ABRIR_SOLO && !nombre.includes(process.env.ABRIR_SOLO)) return;
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
  } finally {
    for (const r of [...retenidas]) await r.soltar().catch(() => {});
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
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium' });
const sesiones = [];
async function abrirSesion(usuario, { soloLectura = false } = {}) {
  const contexto = await navegador.newContext({ viewport: { width: 1500, height: 900 }, locale: 'es-MX' });
  contexto.setDefaultTimeout(30000);
  const page = await contexto.newPage();
  const s = { usuario, page, contexto, errores: [], descargas: [], escrituras: [] };
  page.on('pageerror', (e) => s.errores.push(String(e)));
  page.on('request', (r) => {
    const ruta = new URL(r.url()).pathname;
    if (/\/descarga$/.test(ruta)) s.descargas.push(ruta);
    if (r.method() !== 'GET' && ruta.startsWith('/api/archivos')) s.escrituras.push(`${r.method()} ${ruta}`);
  });
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  if (soloLectura) {
    // The application's read-only mode, as the server would announce it.
    await page.route('**/api/config', async (r) => {
      const res = await r.fetch();
      r.fulfill({ response: res, json: { ...(await res.json()), readOnly: true } });
    });
  }
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

/** A fictional PDF of its own content, through the same three private routes the widgets use.
 * `hasta` stops early: 'iniciado' leaves the upload unfinished, 'rechazado' completes it with other bytes. */
async function subirPdf(page, terrenoId, nombre, { hasta: etapa = 'listo' } = {}) {
  const texto = `%PDF-1.4\n% ${nombre} ${Math.random()}\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n`;
  return page.evaluate(async ([id, nombre, texto, etapa]) => {
    const bytes = new TextEncoder().encode(texto);
    const hex = async (b) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', b))].map((x) => x.toString(16).padStart(2, '0')).join('');
    const r1 = await fetch(`/api/inventario/terrenos/${id}/archivos`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ tipo: 'pdf', nombre_original: nombre, tamano_declarado: bytes.length, sha256_declarado: await hex(bytes) }) });
    const inicio = await r1.json();
    if (!r1.ok) throw new Error(JSON.stringify(inicio));
    if (etapa === 'iniciado') return { version: inicio.version_id, archivo: inicio.archivo_id };
    const cuerpo = etapa === 'rechazado' ? new TextEncoder().encode(texto.replace('%PDF', '%PDX')) : bytes;
    const r2 = await fetch(`/api/archivos/versiones/${inicio.version_id}/contenido`, { method: 'PUT',
      headers: { 'Content-Type': 'application/pdf' }, body: cuerpo });
    if (!r2.ok) throw new Error(await r2.text());
    const r3 = await fetch(`/api/archivos/versiones/${inicio.version_id}/completar`, { method: 'POST' });
    return { version: inicio.version_id, archivo: inicio.archivo_id, estado: (await r3.json()).version?.estado,
      sha: await hex(bytes) };
  }, [terrenoId, nombre, texto, etapa]);
}
/** Disposable DB only: let an unfinished upload's deadline pass and drop its lease, as time would. */
function vencer(versionId) {
  execFileSync(PY, ['-c', 'import sqlite3,sys\nc=sqlite3.connect(sys.argv[1])\n'
    + 'c.execute("UPDATE archivo_version SET completar_antes_de=? WHERE id=? AND estado=?",("2000-01-01T00:00:00+00:00",sys.argv[2],"subiendo"))\n'
    + 'c.execute("DELETE FROM archivo_trabajo WHERE archivo_version_id=?",(sys.argv[2],))\nc.commit()', BD, versionId]);
}

const fila = (page, id) => page.locator(`tr[data-id="${id}"]`);
const celda = (page, id, col = 'core:archivos') => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const resumen = async (page, id, col) => (await celda(page, id, col).locator('.archivos-celda').innerText().catch(() => '')).trim();
const enlace = (page, id) => celda(page, id).locator('.archivos-celda-abrir');
const aviso = (page, id) => celda(page, id).locator('.archivos-celda-aviso');
const selector = (page) => page.getByRole('dialog', { name: 'PDF guardados de este terreno' });
const editorAbierto = (page) => page.locator('.tabla-editor, td.is-editando').count();
const marcada = (page, id) => fila(page, id).locator('input.tabla-marca').isChecked();

async function irA(page, vista) {
  const destino = `${URLBASE}/?test=1#/tabla/${vista}`;
  const misma = page.url() === destino;
  await page.goto(destino);
  await page.locator('.tabla-pantalla').waitFor();
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  if ((await page.locator('#tabla-vista').inputValue()) !== vista) {
    // A base created after the table listed its bases: load the page again to see it.
    await page.reload();
    await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
    await page.goto(destino);
  } else if (misma) {
    // Same address: nothing reloads by itself; the page's own button does.
    await page.getByRole('button', { name: 'Actualizar' }).click();
  }
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await hasta(async () => (await page.locator('#tabla-vista').inputValue()) === vista, 'la vista no es la pedida');
}

/** Run `accion` (a click or a key), expect one new tab, and return the SHA-256 of what it shows. */
async function pestanaDe(s, accion) {
  const [popup] = await Promise.all([s.page.waitForEvent('popup'), accion()]);
  await hasta(() => popup.url().startsWith('blob:'), `la pestaña no recibió el PDF (${popup.url()})`);
  const datos = await popup.evaluate(async () => {
    const b = await (await fetch(location.href)).arrayBuffer();
    const h = await crypto.subtle.digest('SHA-256', b);
    return { opener: window.opener === null, sha: [...new Uint8Array(h)].map((x) => x.toString(16).padStart(2, '0')).join('') };
  });
  cierto(datos.opener, 'la pestaña puede alcanzar la página que la abrió');
  await popup.close();
  return datos.sha;
}
const pestanasAbiertas = (s) => s.contexto.pages().filter((p) => p !== s.page && !p.isClosed());

/** Hold every request matching `patron` until released. */
async function retener(page, patron) {
  const vistos = [];
  const sueltos = [];
  let libre = false;
  const manejador = async (route) => {
    vistos.push(route.request().url());
    if (libre) return route.continue().catch(() => {});
    await new Promise((r) => sueltos.push(r));
    await route.continue().catch(() => {});
  };
  await page.route(patron, manejador);
  const r = {
    vistos,
    async soltar() {
      if (!retenidas.delete(r)) return;
      libre = true;
      sueltos.splice(0).forEach((f) => f());
      await page.unroute(patron, manejador);
    },
  };
  retenidas.add(r);
  return r;
}
// Wide enough to show the name column beside the file columns.
const foto = async (page, nombre) => {
  if (!SHOTS) return;
  const antes = page.viewportSize();
  await page.setViewportSize({ width: 2400, height: 720 });
  await esperar(300);
  await page.screenshot({ path: join(SHOTS, `${nombre}.png`) });
  await page.setViewportSize(antes);
};

/* --------------------------------------------------------------- data */

const ada = await abrirSesion('ada');
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Abrir PDF Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
igual((await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] })).status, 200, 'acceso');
const crear = async (nombre) => (await admin('POST', `/api/maestra/bases/${base.id}/terrenos`, { terreno: nombre })).datos.terreno.id;
const T = {};
for (const [k, n] of [['vacio', 'Lote Abrir Vacío'], ['uno', 'Lote Abrir Uno'], ['varios', 'Lote Abrir Varios'],
  ['muchos', 'Lote Abrir Muchos'], ['vencida', 'Lote Abrir Vencida'], ['rechazada', 'Lote Abrir Rechazada'],
  ['curso', 'Lote Abrir En Curso'], ['previo', 'Lote Abrir Previo'], ['borrado', 'Lote Abrir Borrado']]) {
  T[k] = await crear(`${n} Ficticio`);
}
const S = {};        // name -> sha of the bytes stored
const V = {};        // name -> {version, archivo}
async function sembrar(id, nombre, opciones) {
  const r = await subirPdf(ada.page, id, nombre, opciones);
  if (r.sha) S[nombre] = r.sha;
  V[nombre] = r;
  return r;
}
await sembrar(T.uno, 'Uno ficticio.pdf');
for (const n of ['Varios A.pdf', 'Varios B.pdf', 'Varios <b>C<b> & "D".pdf']) await sembrar(T.varios, n);
// 22 saved PDFs: more than the summary's five recent ones and more than one list page (20).
for (let i = 1; i <= 22; i += 1) await sembrar(T.muchos, `Muchos ${String(i).padStart(2, '0')}.pdf`);
vencer((await sembrar(T.vencida, 'Vencida.pdf', { hasta: 'iniciado' })).version);
igual((await sembrar(T.rechazada, 'Rechazada.pdf', { hasta: 'rechazado' })).estado, 'fallido', 'rechazo');
await sembrar(T.curso, 'En curso.pdf', { hasta: 'iniciado' });
await sembrar(T.previo, 'Previo guardado.pdf');
vencer((await sembrar(T.previo, 'Previo reemplazo.pdf', { hasta: 'iniciado' })).version);
await sembrar(T.borrado, 'Borrado uno.pdf');

/* ----------------------------------------------------------- journeys */

await revisar('sin PDF, subida sin terminar, vencida y rechazada: texto sin enlace', async () => {
  await irA(ada.page, base.id);
  const casos = [[T.vacio, 'Sin PDF'], [T.vencida, 'Sin PDF guardado'], [T.rechazada, 'Sin PDF guardado'], [T.curso, 'Sin PDF guardado']];
  for (const [id, texto] of casos) {
    await hasta(async () => (await resumen(ada.page, id)) === texto, `resumen de ${texto}`);
    igual(await enlace(ada.page, id).count(), 0, `${texto}: no debe ser un enlace`);
    igual(await celda(ada.page, id).getByRole('button', { name: /pestaña nueva/ }).count(), 0, 'sin botón de abrir');
  }
  igual(await celda(ada.page, T.uno, 'core:kmz').locator('.archivos-celda-abrir').count(), 0, 'KMZ sin enlace');
  igual(ada.descargas, [], 'nada se descargó al cargar la tabla');
});

await revisar('administrador: «1 PDF» abre ese PDF en una pestaña nueva, con los mismos bytes, desde su fila', async () => {
  await irA(ada.page, base.id);
  igual(await resumen(ada.page, T.uno), '1 PDF', 'resumen');
  igual(await enlace(ada.page, T.uno).getAttribute('data-modo'), 'directo', 'modo');
  igual(await enlace(ada.page, T.uno).getAttribute('aria-haspopup'), null, 'sin selector');
  const antes = await marcada(ada.page, T.uno);
  const desde = ada.descargas.length;
  igual(await pestanaDe(ada, () => enlace(ada.page, T.uno).click()), S['Uno ficticio.pdf'], 'contenido');
  igual(ada.descargas.slice(desde), [`/api/archivos/versiones/${V['Uno ficticio.pdf'].version}/descarga`], 'una descarga, de su versión');
  igual(await editorAbierto(ada.page), 0, 'no abre un editor');
  igual(await marcada(ada.page, T.uno), antes, 'no cambia la selección múltiple');
  await hasta(async () => (await aviso(ada.page, T.uno).isHidden()), 'el aviso no se limpió');
  await foto(ada.page, '01-enlace-1-pdf');
});

await revisar('un PDF guardado junto a un reemplazo vencido sigue abriéndose; el vencido no', async () => {
  igual(await resumen(ada.page, T.previo), '1 PDF', 'resumen');
  const titulo = await celda(ada.page, T.previo).locator('.archivos-celda').getAttribute('title');
  cierto(/subida vencida/i.test(titulo), `nota: ${titulo}`);
  igual(await pestanaDe(ada, () => enlace(ada.page, T.previo).click()), S['Previo guardado.pdf'], 'abre el guardado');
});

await revisar('varios PDF: el contador abre una lista; cada elección abre el documento correcto', async () => {
  await irA(ada.page, base.id);
  igual(await resumen(ada.page, T.varios), '3 PDF', 'resumen');
  const desde = ada.descargas.length;
  await enlace(ada.page, T.varios).click();
  await selector(ada.page).waitFor();
  igual(await enlace(ada.page, T.varios).getAttribute('aria-expanded'), 'true', 'aria-expanded');
  const nombres = await selector(ada.page).locator('.archivos-opcion-nombre').allInnerTexts();
  igual([...nombres].sort(), ['Varios <b>C<b> & "D".pdf', 'Varios A.pdf', 'Varios B.pdf'], 'nombres');
  igual(await selector(ada.page).locator('b').count(), 0, 'un nombre nunca se interpreta como HTML');
  igual(ada.descargas.slice(desde), [], 'abrir la lista no descarga nada');
  igual(pestanasAbiertas(ada).length, 0, 'ninguna pestaña todavía');
  await foto(ada.page, '02-selector-varios-pdf');
  for (const n of ['Varios A.pdf', 'Varios B.pdf', 'Varios <b>C<b> & "D".pdf']) {
    if (!(await selector(ada.page).isVisible())) await enlace(ada.page, T.varios).click();
    const opcion = selector(ada.page).locator('.archivos-opcion', { hasText: n });
    igual(await pestanaDe(ada, () => opcion.click()), S[n], `contenido de ${n}`);
    await hasta(async () => (await selector(ada.page).count()) === 0, 'la lista no se cerró tras abrir');
  }
  igual(await editorAbierto(ada.page), 0, 'no abre un editor');
});

await revisar('teclado: Enter abre; flechas, Enter y Escape en la lista; nunca un editor', async () => {
  await irA(ada.page, base.id);
  await enlace(ada.page, T.uno).focus();
  igual(await pestanaDe(ada, () => ada.page.keyboard.press('Enter')), S['Uno ficticio.pdf'], 'Enter en «1 PDF»');
  await enlace(ada.page, T.varios).focus();
  await ada.page.keyboard.press(' ');
  await selector(ada.page).waitFor();
  cierto(await ada.page.evaluate(() => document.activeElement?.classList.contains('archivos-opcion')), 'el foco entra en la lista');
  await ada.page.keyboard.press('ArrowDown');
  const elegido = (await ada.page.evaluate(() => document.activeElement.querySelector('.archivos-opcion-nombre').textContent));
  igual(await pestanaDe(ada, () => ada.page.keyboard.press('Enter')), S[elegido], 'Enter en la lista');
  await enlace(ada.page, T.varios).focus();
  await ada.page.keyboard.press('Enter');
  await selector(ada.page).waitFor();
  await ada.page.keyboard.press('Escape');
  await hasta(async () => (await selector(ada.page).count()) === 0, 'Escape no cerró la lista');
  cierto(await ada.page.evaluate(() => document.activeElement?.classList.contains('archivos-celda-abrir')), 'el foco vuelve al enlace');
  await ada.page.keyboard.press('F2');
  await ada.page.keyboard.press('x');
  await enlace(ada.page, T.uno).dblclick().catch(() => {});
  await esperar(300);
  for (const p of pestanasAbiertas(ada)) await p.close();
  igual(await editorAbierto(ada.page), 0, 'F2, una letra o doble clic abrieron un editor');
  // A click outside closes the list.
  await enlace(ada.page, T.varios).click();
  await selector(ada.page).waitFor();
  await ada.page.locator('.tabla-pantalla h1, .tabla-pantalla .tabla-barra').first().click({ position: { x: 5, y: 5 } }).catch(() => {});
  await hasta(async () => (await selector(ada.page).count()) === 0, 'un clic fuera no cerró la lista');
});

await revisar('más PDF que el resumen reciente: la lista autorizada, con su paginación', async () => {
  await irA(ada.page, base.id);
  igual(await resumen(ada.page, T.muchos), '22 adjuntos PDF', 'resumen truncado');
  await enlace(ada.page, T.muchos).click();
  const sel = selector(ada.page);
  await hasta(async () => (await sel.locator('.archivos-opcion').count()) === 20, 'primera página');
  const mas = sel.getByRole('button', { name: 'Cargar más' });
  await mas.click();
  await hasta(async () => (await sel.locator('.archivos-opcion').count()) === 22, 'segunda página');
  cierto(await mas.isHidden(), 'no hay más páginas');
  const nombres = await sel.locator('.archivos-opcion-nombre').allInnerTexts();
  igual(new Set(nombres).size, 22, 'sin repetidos');
  await foto(ada.page, '03-selector-paginado');
  // The oldest one, only reachable on the second page.
  igual(await pestanaDe(ada, () => sel.locator('.archivos-opcion', { hasText: 'Muchos 01.pdf' }).click()), S['Muchos 01.pdf'], 'contenido');
});

const olga = await abrirSesion('olga');

await revisar('operador autorizado: abre «1 PDF» y elige entre varios', async () => {
  await irA(olga.page, base.id);
  await hasta(async () => (await resumen(olga.page, T.uno)) === '1 PDF', 'resumen');
  igual(await pestanaDe(olga, () => enlace(olga.page, T.uno).click()), S['Uno ficticio.pdf'], '1 PDF');
  await enlace(olga.page, T.varios).click();
  igual(await pestanaDe(olga, () => selector(olga.page).locator('.archivos-opcion', { hasText: 'Varios B.pdf' }).click()),
    S['Varios B.pdf'], 'varios');
});

await revisar('solo consulta: sin «Elegir PDF…», pero la lectura funciona', async () => {
  const lectora = await abrirSesion('olga', { soloLectura: true });
  await irA(lectora.page, base.id);
  await hasta(async () => (await resumen(lectora.page, T.uno)) === '1 PDF', 'resumen');
  igual(await celda(lectora.page, T.uno).locator('.archivos-celda-elegir:visible').count(), 0, 'sin botón de subir');
  igual(await pestanaDe(lectora, () => enlace(lectora.page, T.uno).click()), S['Uno ficticio.pdf'], 'abre');
  await enlace(lectora.page, T.varios).click();
  igual(await pestanaDe(lectora, () => selector(lectora.page).locator('.archivos-opcion', { hasText: 'Varios A.pdf' }).click()),
    S['Varios A.pdf'], 'elige');
  igual(lectora.escrituras, [], 'nada escrito');
  await lectora.contexto.close();
  sesiones.splice(sesiones.indexOf(lectora), 1);
});

await revisar('clics repetidos durante la descarga: una sola pestaña y una sola descarga', async () => {
  await irA(ada.page, base.id);
  const r = await retener(ada.page, '**/descarga');
  const desde = ada.descargas.length;
  const popup = ada.page.waitForEvent('popup');
  await enlace(ada.page, T.uno).click();
  await enlace(ada.page, T.uno).click();
  await enlace(ada.page, T.uno).click();
  await hasta(async () => r.vistos.length === 1, 'la descarga no salió');
  igual(await enlace(ada.page, T.uno).getAttribute('aria-busy'), 'true', 'ocupado');
  await esperar(300);
  igual(pestanasAbiertas(ada).length, 1, 'una sola pestaña reservada');
  await r.soltar();
  const p = await popup;
  await hasta(() => p.url().startsWith('blob:'), 'la pestaña no recibió el PDF');
  igual(ada.descargas.length - desde, 1, 'una sola descarga');
  await p.close();
});

await revisar('una pestaña rechazada por el navegador ofrece un enlace que abre el PDF', async () => {
  await irA(ada.page, base.id);
  await ada.page.evaluate(() => { window.__open = window.open; window.open = () => null; });
  await enlace(ada.page, T.uno).click();
  const respaldo = aviso(ada.page, T.uno).getByRole('link', { name: 'Abrir el PDF' });
  await respaldo.waitFor();
  cierto(/no permitió abrir una pestaña nueva/.test(await aviso(ada.page, T.uno).innerText()), 'mensaje');
  await foto(ada.page, '04-pestana-bloqueada');
  await ada.page.evaluate(() => { window.open = window.__open; });
  igual(await pestanaDe(ada, () => respaldo.click()), S['Uno ficticio.pdf'], 'el enlace abre el PDF');
});

await revisar('cerrar la lista mientras carga y cambiar de vista durante la descarga descartan lo atrasado', async () => {
  await irA(ada.page, base.id);
  const lista = await retener(ada.page, new RegExp(`/api/inventario/terrenos/${T.muchos}/archivos\\?`));
  await enlace(ada.page, T.muchos).click();
  await hasta(async () => lista.vistos.length === 1, 'la lista no se pidió');
  await ada.page.keyboard.press('Escape');
  await hasta(async () => (await selector(ada.page).count()) === 0, 'la lista no se cerró');
  await lista.soltar();
  await esperar(500);
  igual(await selector(ada.page).count(), 0, 'una respuesta atrasada reabrió la lista');
  igual(await aviso(ada.page, T.muchos).isHidden(), true, 'sin mensajes');
  // Leaving the view while the PDF downloads: the reserved tab closes, nothing is shown.
  const descarga = await retener(ada.page, '**/descarga');
  const popup = ada.page.waitForEvent('popup');
  await enlace(ada.page, T.uno).click();
  await hasta(async () => descarga.vistos.length === 1, 'la descarga no salió');
  const p = await popup;
  await ada.page.locator('#tabla-vista').selectOption('maestra');
  await hasta(async () => /#\/tabla\/maestra/.test(ada.page.url()), 'la vista no cambió');
  await hasta(() => p.isClosed(), 'la pestaña reservada quedó abierta y vacía');
  await descarga.soltar();
  await esperar(300);
  igual(pestanasAbiertas(ada).length, 0, 'ninguna pestaña');
});

await revisar('cerrar la lista durante la descarga (Escape, «Cerrar», clic fuera) cancela la apertura y cierra su pestaña', async () => {
  await irA(ada.page, base.id);
  const formas = {
    Escape: () => ada.page.keyboard.press('Escape'),
    Cerrar: () => selector(ada.page).getByRole('button', { name: 'Cerrar la lista de PDF' }).click(),
    fuera: () => ada.page.locator('#tabla-buscar').click(),
  };
  for (const [forma, cerrar] of Object.entries(formas)) {
    const descarga = await retener(ada.page, '**/descarga');
    await enlace(ada.page, T.varios).click();
    await selector(ada.page).waitFor();
    const popup = ada.page.waitForEvent('popup');
    await selector(ada.page).locator('.archivos-opcion', { hasText: 'Varios A.pdf' }).click();
    const p = await popup;
    await hasta(async () => descarga.vistos.length === 1, `${forma}: la descarga no salió`);
    await cerrar();
    await hasta(async () => (await selector(ada.page).count()) === 0, `${forma}: la lista no se cerró`);
    await hasta(() => p.isClosed(), `${forma}: la pestaña reservada quedó abierta`);
    await descarga.soltar();          // the held response arrives after the dismissal
    await esperar(800);
    igual(pestanasAbiertas(ada).length, 0, `${forma}: el PDF se abrió después de cerrar la lista`);
    igual(await aviso(ada.page, T.varios).isHidden(), true, `${forma}: sin aviso pendiente`);
    igual(await enlace(ada.page, T.varios).getAttribute('aria-busy'), null, `${forma}: el enlace sigue ocupado`);
  }
  // A successful opening is untouched: choose and let it arrive.
  await enlace(ada.page, T.varios).click();
  igual(await pestanaDe(ada, () => selector(ada.page).locator('.archivos-opcion', { hasText: 'Varios A.pdf' }).click()),
    S['Varios A.pdf'], 'la apertura normal sigue funcionando');
  await hasta(async () => (await selector(ada.page).count()) === 0, 'la lista no se cerró tras abrir');
});

/* «Borrar» deletes the attachment and every version for good, so a link
 * drawn before the deletion meets the real server's 404 for that version. No
 * route is intercepted: `respuestas` records what the server itself answered. */
async function estadoDeDescarga(page, versionId) {
  const r = await page.waitForResponse((res) => res.url().endsWith(`/api/archivos/versiones/${versionId}/descarga`));
  return r.status();
}

await revisar('documento borrado (enlace viejo): el servidor real responde 404, la pestaña se cierra, la fila sigue y el resumen se actualiza', async () => {
  await irA(ada.page, base.id);
  igual(await resumen(ada.page, T.borrado), '1 PDF', 'resumen');
  const { archivo, version } = V['Borrado uno.pdf'];
  const rev = (await terreno(ada.page, T.borrado)).archivos.pdf_recientes[0].revision;
  igual((await admin('POST', `/api/archivos/${archivo}/borrar`, { expected_revision: rev })).status, 200, 'borrado en el servidor');
  igual((await admin('GET', `/api/archivos/versiones/${version}/descarga`)).status, 404, 'la versión ya no existe en el servidor');
  // The row still shows the summary drawn before the deletion.
  igual(await resumen(ada.page, T.borrado), '1 PDF', 'enlace viejo');
  const popup = ada.page.waitForEvent('popup');
  const respuesta = estadoDeDescarga(ada.page, version);
  await enlace(ada.page, T.borrado).click();
  const p = await popup;
  igual(await respuesta, 404, 'respuesta real del servidor');
  await hasta(() => p.isClosed(), 'quedó una pestaña vacía');
  await hasta(async () => /ya no existe/.test(await aviso(ada.page, T.borrado).innerText()), 'sin aviso');
  await hasta(async () => (await resumen(ada.page, T.borrado)) === 'Sin PDF', 'el resumen no se actualizó');
  igual(await enlace(ada.page, T.borrado).count(), 0, 'ya no es un enlace');
  igual(await fila(ada.page, T.borrado).count(), 1, 'la fila sigue');
  igual(pestanasAbiertas(ada).length, 0, 'ninguna pestaña');
  // In the list: a document deleted after the list was shown.
  await enlace(ada.page, T.varios).click();
  await selector(ada.page).waitFor();
  const b = V['Varios B.pdf'];
  const revB = (await terreno(ada.page, T.varios)).archivos.pdf_recientes.find((f) => f.id === b.archivo).revision;
  igual((await admin('POST', `/api/archivos/${b.archivo}/borrar`, { expected_revision: revB })).status, 200, 'borrado B');
  const otra = ada.page.waitForEvent('popup');
  const respuestaB = estadoDeDescarga(ada.page, b.version);
  await selector(ada.page).locator('.archivos-opcion', { hasText: 'Varios B.pdf' }).click();
  const po = await otra;
  igual(await respuestaB, 404, 'respuesta real del servidor (lista)');
  await hasta(() => po.isClosed(), 'quedó una pestaña vacía (lista)');
  await hasta(async () => (await resumen(ada.page, T.varios)) === '2 PDF', 'el resumen no se actualizó (lista)');
  await hasta(async () => !(await selector(ada.page).locator('.archivos-opcion', { hasText: 'Varios B.pdf' }).count()), 'la lista no se actualizó');
  igual(await selector(ada.page).locator('.archivos-opcion').count(), 2, 'quedan los otros dos');
  await ada.page.keyboard.press('Escape');
  igual(await fila(ada.page, T.varios).count(), 1, 'la fila sigue (lista)');
  igual(pestanasAbiertas(ada).length, 0, 'ninguna pestaña (lista)');
});

await revisar('terreno borrado: el 404 se comprueba con su lista y la fila sale; sin pestaña vacía', async () => {
  const id = await crear('Lote Abrir Terreno Borrado Ficticio');
  await sembrar(id, 'Terreno borrado.pdf');
  await irA(ada.page, base.id);
  await hasta(async () => (await resumen(ada.page, id)) === '1 PDF', 'resumen');
  const t = await terreno(ada.page, id);
  igual((await admin('POST', `/api/inventario/terrenos/${id}/borrar`, { expected_version: t.version })).status, 200, 'borrado');
  const popup = ada.page.waitForEvent('popup');
  await enlace(ada.page, id).click();
  const p = await popup;
  await hasta(() => p.isClosed(), 'quedó una pestaña vacía');
  await hasta(async () => (await fila(ada.page, id).count()) === 0, 'la fila del terreno borrado sigue');
  igual(await fila(ada.page, T.uno).count(), 1, 'las demás filas siguen');
});

await revisar('recargar la página durante la descarga cierra la pestaña reservada', async () => {
  await irA(ada.page, base.id);
  const descarga = await retener(ada.page, '**/descarga');
  const popup = ada.page.waitForEvent('popup');
  await enlace(ada.page, T.uno).click();
  await hasta(async () => descarga.vistos.length === 1, 'la descarga no salió');
  const p = await popup;
  await ada.page.reload();
  await hasta(() => p.isClosed(), 'la pestaña reservada quedó abierta y vacía');
  await descarga.soltar();
  await ada.page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
});

await revisar('sesión perdida durante la descarga: sin pestaña vacía ni PDF', async () => {
  const s = await abrirSesion('alan');
  await irA(s.page, base.id);
  const descarga = await retener(s.page, '**/descarga');
  const popup = s.page.waitForEvent('popup');
  await enlace(s.page, T.uno).click();
  await hasta(async () => descarga.vistos.length === 1, 'la descarga no salió');
  const p = await popup;
  igual((await llamar(s.page, 'POST', '/api/logout', {})).status, 200, 'logout');
  await descarga.soltar();
  await hasta(() => p.isClosed(), 'la pestaña reservada quedó abierta');
  await hasta(async () => (await s.page.locator('.tabla-pantalla').count()) === 0
    || (await s.page.getByLabel('Usuario').count()) > 0, 'la sesión no terminó en la página');
  await s.contexto.close();
  sesiones.splice(sesiones.indexOf(s), 1);
});

await revisar('«Elegir PDF…» sigue igual y convierte «1 PDF» en lista; el detalle abre con el mismo flujo', async () => {
  await irA(ada.page, base.id);
  const boton = celda(ada.page, T.uno).locator('.archivos-celda-elegir');
  const [chooser] = await Promise.all([ada.page.waitForEvent('filechooser'), boton.click()]);
  await chooser.setFiles({ name: 'Segundo ficticio.pdf', buffer: readFileSync(F.pdf2), mimeType: 'application/pdf' });
  await hasta(async () => (await resumen(ada.page, T.uno)) === '2 PDF', 'no llegó a 2 PDF', 60000);
  igual(await enlace(ada.page, T.uno).getAttribute('data-modo'), 'lista', 'ahora es lista');
  await enlace(ada.page, T.uno).click();
  igual(await pestanaDe(ada, () => selector(ada.page).locator('.archivos-opcion', { hasText: 'Segundo ficticio.pdf' }).click()),
    sha(readFileSync(F.pdf2)), 'el PDF recién subido');
  // The detail's "Abrir" uses the same shared flow.
  await fila(ada.page, T.uno).getByRole('button', { name: /Abrir terreno/ }).click();
  const d = ada.page.getByRole('dialog', { name: 'Lote Abrir Uno Ficticio' });
  const item = d.locator('.archivos-detalle[data-tipo="pdf"] .archivos-item', { hasText: 'Uno ficticio.pdf' });
  igual(await pestanaDe(ada, () => item.getByRole('button', { name: /^Abrir Uno ficticio/ }).click()), S['Uno ficticio.pdf'], 'detalle');
  await d.locator('.archivos-mensaje', { hasText: 'Archivo abierto en una pestaña nueva.' }).waitFor();
  await d.getByRole('button', { name: 'Cerrar' }).last().click();
  igual(await resumen(ada.page, T.uno, 'core:kmz'), 'Sin KMZ / KML', 'KMZ intacto');
  igual(await celda(ada.page, T.uno, 'core:kmz').locator('.archivos-celda-elegir').innerText(), 'Elegir KMZ o KML…', 'botón KMZ');
});

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

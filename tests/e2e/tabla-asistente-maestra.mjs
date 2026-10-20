/* «Asistente IA» of the master table (issue #69), connected: the REAL local
 * server (tests/e2e/asistente_servidor.py, which wraps tabla_servidor.py on a
 * folder this script creates and deletes) with the assistant on and its
 * FICTIONAL provider, the real table, detail and map, real sessions and
 * Chromium. Fictional accounts and terrains only. No key, no network to the
 * provider, nothing billed; NOT a test of Claude itself.
 *
 *   cd tests/e2e && npm ci && node tabla-asistente-maestra.mjs
 *
 * On the global master table (with terrains in no base, and matches outside
 * the table's current page): a clarification lists nothing; a search shows
 * its criteria, the real total and pages of ten, with every spelling of a
 * type and «más de» as a strict bound; a result outside the page opens its
 * detail; three results are compared, and a comparison refused for a change
 * (409) or a deletion (404) leaves no old table on screen; closing leaves the
 * table as it was, and a detail still loading opens nothing after closing;
 * the map of the master table still works. Also: an operator never sees it,
 * and the provider never receives a name, id, base or note.
 * Optional: ASISTENTE_CAPTURAS=dir, CHROMIUM=/path, ASISTENTE_PUERTO, PYTHON.
 */

import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.ASISTENTE_PUERTO ?? 8492);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.ASISTENTE_CAPTURAS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const CARPETA = mkdtempSync(join(tmpdir(), 'ara-asistente-maestra-'));
const REGISTRO = join(CARPETA, 'enviado.jsonl');

const servidor = spawn(PY, [join(AQUI, 'asistente_servidor.py'), '--puerto', String(PUERTO),
  '--carpeta', join(CARPETA, 'instalacion'), '--registro', REGISTRO], { cwd: RAIZ, stdio: ['ignore', 'pipe', 'ignore'] });
await new Promise((resolve, reject) => {
  let texto = '';
  servidor.stdout.on('data', (d) => { texto += d; if (/LISTO/.test(texto)) resolve(); });
  servidor.on('exit', (c) => reject(new Error(`el servidor salió (${c}): ${texto}`)));
});

/* ------------------------------------------------------------ harness */

let fallos = 0;
const sesiones = [];
async function revisar(nombre, fn) {
  try {
    await fn();
    console.log(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    console.log(`FALLO ${nombre}\n     ${String(error?.stack ?? error).split('\n').slice(0, 6).join('\n     ')}`);
    for (const s of sesiones) {
      if (SHOTS && !s.page.isClosed()) await s.page.screenshot({ path: join(SHOTS, `fallo-${fallos}-${s.usuario}.png`) }).catch(() => {});
    }
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
    await esperar(50);
  }
}

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium' });
async function abrir(usuario, { viewport = { width: 1200, height: 800 }, apagado = false } = {}) {
  const contexto = await navegador.newContext({ viewport, locale: 'es-MX' });
  contexto.setDefaultTimeout(20000);
  const page = await contexto.newPage();
  const s = { usuario, page, errores: [], lecturas: [] };
  page.on('pageerror', (e) => s.errores.push(String(e)));
  page.on('request', (r) => { if (r.url().includes('/api/')) s.lecturas.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  // «Assistant off» for this page only: the config answer is replaced in the browser.
  if (apagado) {
    await page.route('**/api/asistente-terreno/config', (r) => r.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ habilitado: false, disponible: false, max_pregunta: 500 }) }));
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
const listas = (s) => s.lecturas.filter((l) => /^GET \/api\/(maestra\/bases\/[^/]+|inventario)\/terrenos$/.test(l)).length;
const posicion = (page) => page.evaluate(() => {
  const l = document.querySelector('.tabla-lienzo');
  return { top: Math.round(l.scrollTop), left: Math.round(l.scrollLeft) };
});
const filasDeTabla = (page) => page.locator('tr.tabla-fila').evaluateAll((trs) => trs.map((t) => t.dataset.id));
const dialogo = (page) => page.getByRole('dialog', { name: 'Asistente IA de la tabla maestra' });
const resultados = (d) => d.locator('.asistente-maestra-fila');
const botonAsistente = (page) => page.locator('.tabla-barra').getByRole('button', { name: 'Asistente IA' });
const proximamente = (raiz) => raiz.locator('aside.aviso-proximamente');
const TEXTO_PROXIMAMENTE = /Próximamente\s*ARA MAP sigue creciendo\s*Estamos preparando nuevas funciones de IA\. Mantente atento\./i;   // the label is uppercased by CSS

async function irAMaestra(page) {
  await page.goto(`${URLBASE}/?test=1#/tabla/maestra`);
  await page.locator('.tabla-pantalla').waitFor();
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
}
async function preguntar(d, texto) {
  await d.getByLabel('¿Qué terrenos buscas?').fill(texto);
  await d.getByRole('button', { name: 'Buscar' }).click();
  await hasta(async () => (await d.locator('.asistente-terreno-esperando').count()) === 0
    && ((await resultados(d).count()) > 0 || (await d.locator('.asistente-maestra-aclaracion, .asistente-maestra-total').count()) > 0),
  'la búsqueda no terminó');
}

/* --------------------------------------------------------------- data */

const ada = await abrir('ada');
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Maestra Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] });
const crear = async (datos, enBase = false) => (await admin('POST',
  enBase ? `/api/maestra/bases/${base.id}/terrenos` : '/api/inventario/terrenos',
  { estado: 'Jalisco', tipo_terreno: 'Industrial', notas_internas: 'NOTA-FICTICIA', contacto: 'CONTACTO-FICTICIO',
    direccion: 'DIRECCION-FICTICIA', lat: 20.6, lon: -103.3, ...datos })).datos.terreno;
const coinciden = [];
for (let n = 0; n < 20; n += 1) {
  const extra = n === 0 ? { asking_price: 2500000, moneda: 'MXN', availability: 'available' }
    : n === 1 ? { asking_price: 150000, moneda: 'USD' } : {};
  coinciden.push((await crear({ terreno: `Lote Maestra ${String(n).padStart(2, '0')} Ficticio`,
    superficie_m2: 10250 + n * 250, ...extra }, n >= 14)).id);
}
// Other spellings of the same type are found too (and are not in a base).
for (const tipo of ['industrial', 'Indústrial']) {
  coinciden.push((await crear({ terreno: `Lote Grafía ${tipo} Ficticio`, tipo_terreno: tipo, superficie_m2: 15000 })).id);
}
// «más de 10,000 m²» is strict: exactly 10,000 m² is not a match.
const frontera = (await crear({ terreno: 'Lote Frontera Ficticio', superficie_m2: 10000 })).id;
for (let n = 0; n < 45; n += 1) {                                     // filler: other states and types
  await crear({ terreno: `Lote Relleno ${n} Ficticio`, estado: n % 2 ? 'Colima' : 'Yucatán',
    tipo_terreno: n % 3 ? 'Agrícola' : 'Industrial', superficie_m2: 20000 });
}
await crear({ terreno: 'Lote Pequeño Ficticio', superficie_m2: 5000 });  // Jalisco, industrial, too small
const SIN_BASE = [...coinciden.slice(0, 14), ...coinciden.slice(20)];
await ada.page.reload();          // the table reads the bases created above
await ada.page.locator('.tabla-pantalla').waitFor();

/* ------------------------------------------------------------- checks */

await revisar('operador: ni la tabla maestra ni el asistente global', async () => {
  const olga = await abrir('olga');
  await olga.page.goto(`${URLBASE}/?test=1#/tabla/${base.id}`);
  await olga.page.locator('.tabla-pantalla').waitFor();
  await esperar(400);
  igual(await botonAsistente(olga.page).count(), 0, 'botón del asistente global para el operador');
  cierto(!olga.lecturas.some((l) => /asistente-terreno\/(buscar|resultados|comparar)/.test(l)), 'el operador consultó el asistente');
  await olga.page.context().close();
  sesiones.splice(sesiones.indexOf(olga), 1);
});

let tablaAntes = null;
await revisar('tabla maestra: página de 50, con coincidencias fuera de ella', async () => {
  await irAMaestra(ada.page);
  await ada.page.getByLabel('Filas por página').selectOption('50');
  await hasta(async () => (await filasDeTabla(ada.page)).length === 50, 'la página no tiene 50 filas');
  await ada.page.locator('.tabla-lienzo').evaluate((l) => { l.scrollTop = 300; l.scrollLeft = 40; });
  const ids = await filasDeTabla(ada.page);
  cierto(coinciden.some((id) => !ids.includes(id)), 'todas las coincidencias caben en la página');
  tablaAntes = { ids, posicion: await posicion(ada.page), listas: listas(ada) };
  await botonAsistente(ada.page).waitFor();
});

await revisar('«Próximamente» en la tabla maestra y en el panel, sin abrirlo solo', async () => {
  cierto(TEXTO_PROXIMAMENTE.test(await proximamente(ada.page.locator('.tabla-pantalla')).innerText()), 'aviso de la tabla');
  igual(await dialogo(ada.page).count(), 0, 'el aviso abrió el panel');
  await botonAsistente(ada.page).click();
  await dialogo(ada.page).waitFor();
  cierto(TEXTO_PROXIMAMENTE.test(await proximamente(dialogo(ada.page)).innerText()), 'aviso del panel');
  if (SHOTS) await ada.page.screenshot({ path: join(SHOTS, 'proximamente-escritorio.png') });
  await dialogo(ada.page).getByRole('button', { name: 'Cerrar', exact: true }).last().click();
  await dialogo(ada.page).waitFor({ state: 'detached' });
});

await revisar('asistente apagado: el aviso sigue, sin botón ni consultas de IA (móvil)', async () => {
  const alan = await abrir('alan', { viewport: { width: 390, height: 844 }, apagado: true });
  await irAMaestra(alan.page);
  await proximamente(alan.page.locator('.tabla-pantalla')).waitFor();
  cierto(TEXTO_PROXIMAMENTE.test(await proximamente(alan.page.locator('.tabla-pantalla')).innerText()), 'aviso');
  await esperar(300);
  igual(await botonAsistente(alan.page).count(), 0, 'botón con el asistente apagado');
  igual(alan.lecturas.filter((l) => /asistente-terreno\/(buscar|resultados|comparar)/.test(l)), [], 'consultas de IA');
  const ancho = await alan.page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  cierto(ancho[0] <= ancho[1], `el aviso desborda en móvil: ${ancho}`);
  if (SHOTS) await alan.page.screenshot({ path: join(SHOTS, 'proximamente-movil-apagado.png') });
  await alan.page.context().close();
  sesiones.splice(sesiones.indexOf(alan), 1);
});

await revisar('una condición no admitida pide aclaración y no lista nada', async () => {
  await botonAsistente(ada.page).click();
  const d = dialogo(ada.page);
  await d.waitFor();
  const aviso = await d.locator('.asistente-terreno-aviso').innerText();
  cierto(/ningún terreno/.test(aviso) && /dirección exacta/.test(aviso) && /información sensible/.test(aviso), 'aviso incompleto');
  await preguntar(d, 'Terrenos en Colima cerca del mar');
  cierto(/No puedo filtrar por/.test(await d.locator('.asistente-maestra-aclaracion').innerText()), 'sin aclaración');
  igual(await resultados(d).count(), 0, 'una aclaración no muestra resultados');
});

await revisar('buscar: criterios, total real, diez por página y más resultados', async () => {
  const d = dialogo(ada.page);
  await preguntar(d, 'Busca terrenos industriales en Jalisco de más de 10,000 m²');
  igual(await d.locator('.asistente-maestra-criterios li').allInnerTexts(), [
    'Estado: Jalisco', 'Tipo de terreno: Industrial (con sus variantes de mayúsculas y acentos)',
    'Superficie registrada: más de 10,000 m²'], 'criterios');
  cierto(/22 terrenos coinciden\. Mostrando 10\./.test(await d.locator('.asistente-maestra-total').innerText()), 'total');
  igual(await resultados(d).count(), 10, 'primera página');
  for (const n of [20, 22]) {
    await d.getByRole('button', { name: 'Más resultados' }).click();
    await hasta(async () => (await resultados(d).count()) === n, `no llegaron ${n} resultados`);
  }
  igual(await d.getByRole('button', { name: 'Más resultados' }).count(), 0, 'sobra «Más resultados»');
  const ids = await resultados(d).evaluateAll((li) => li.map((x) => x.dataset.id));
  igual([...ids].sort(), [...coinciden].sort(), 'el conjunto encontrado');
  cierto(!ids.includes(frontera), '«más de 10,000 m²» incluyó uno de 10,000 m²');
  const sinBase = await resultados(d).filter({ hasText: 'Sin base asignada' }).count();
  igual(sinBase, SIN_BASE.length, 'terrenos sin base entre los resultados');
  igual(await resultados(d).filter({ hasText: 'Base Maestra Ficticia' }).count(), coinciden.length - SIN_BASE.length,
    'el nombre local de la base');
  igual(ada.lecturas.filter((l) => l === 'POST /api/asistente-terreno/buscar').length, 2, 'interpretaciones');
});

await revisar('ver detalle de un resultado fuera de la página de la tabla', async () => {
  const d = dialogo(ada.page);
  const fuera = coinciden.find((id) => !tablaAntes.ids.includes(id));
  const fila = d.locator(`.asistente-maestra-fila[data-id="${fuera}"]`);
  const nombre = await fila.locator('.asistente-maestra-nombre').innerText();
  await fila.getByRole('button', { name: 'Ver detalle' }).click();
  const detalle = ada.page.getByRole('dialog', { name: nombre });
  await detalle.waitFor();
  cierto(/Jalisco/.test(await detalle.innerText()), 'el detalle no muestra el terreno');
  await detalle.getByRole('button', { name: 'Cerrar', exact: true }).last().click();
  await detalle.waitFor({ state: 'detached' });
  cierto(await d.isVisible(), 'cerrar el detalle cerró el asistente');
});

await revisar('comparar tres: tabla registrada, advertencias y resumen rotulado', async () => {
  const d = dialogo(ada.page);
  for (const id of coinciden.slice(0, 3)) await d.locator(`.asistente-maestra-fila[data-id="${id}"] input`).check();
  cierto(await d.locator(`.asistente-maestra-fila[data-id="${coinciden[3]}"] input`).isDisabled(), 'se permite un cuarto');
  await d.getByRole('button', { name: 'Comparar seleccionados' }).click();
  await d.locator('.asistente-maestra-tabla').waitFor();
  const filas = await d.locator('.asistente-maestra-tabla tbody tr').evaluateAll((trs) =>
    trs.map((tr) => [...tr.children].map((c) => c.textContent)));
  igual(filas.length, 10, 'filas de la comparación');
  igual(filas.find((f) => f[0] === 'Precio total'), ['Precio total', 'MXN 2,500,000', 'USD 150,000', 'Sin información registrada'], 'precios');
  cierto(/monedas distintas \(MXN, USD\)/.test(await d.locator('.asistente-maestra-comparacion').innerText()), 'sin advertencia de moneda');
  const resumen = await d.locator('.asistente-maestra-resumen').innerText();
  cierto(/proveedor ficticio/.test(resumen) && /Claude/.test(resumen), 'resumen o su rótulo');
  igual(await d.locator('.asistente-maestra-comparacion b').count(), 0, 'HTML del proveedor interpretado');
  const enviado = readFileSync(REGISTRO, 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  const comparacion = JSON.stringify(enviado.at(-1));
  cierto(comparacion.includes('Terreno A') && comparacion.includes('USD 150,000'), 'la comparación no llevaba las fichas');
  for (const e of enviado) {
    const todo = JSON.stringify(e);
    for (const nada of ['Lote Maestra', 'Base Maestra', 'NOTA-FICTICIA', 'CONTACTO-FICTICIO', 'DIRECCION-FICTICIA', '20.6', ...coinciden]) {
      cierto(!todo.includes(nada), `«${nada}» llegó al proveedor`);
    }
  }
  if (SHOTS) await ada.page.screenshot({ path: join(SHOTS, 'comparacion.png') });
});

await revisar('una comparación rechazada (cambio o borrado) no deja la anterior como vigente', async () => {
  const d = dialogo(ada.page);
  const actual = (await admin('GET', `/api/inventario/terrenos/${coinciden[0]}`)).datos.terreno;
  igual((await admin('PATCH', `/api/inventario/terrenos/${coinciden[0]}`,
    { expected_version: actual.version, changes: { asking_price: 2600000 } })).status, 200, 'cambio de precio');
  for (const [paso, patron] of [['cambio', /cambió mientras se comparaba/], ['borrado', /ya no existe/]]) {
    if (paso === 'borrado') {          // the server reports a missing terrain before a stale version
      const t = (await admin('GET', `/api/inventario/terrenos/${coinciden[0]}`)).datos.terreno;
      igual((await admin('POST', `/api/inventario/terrenos/${coinciden[0]}/borrar`, { expected_version: t.version })).status, 200, 'borrado');
    }
    await d.getByRole('button', { name: 'Comparar seleccionados' }).click();
    await hasta(async () => patron.test(await d.locator('.asistente-terreno-estado').innerText()), `sin aviso de ${paso}`);
    igual(await d.locator('.asistente-maestra-tabla, .asistente-maestra-resumen').count(), 0, `comparación vieja tras ${paso}`);
  }
});

await revisar('cerrar: la tabla queda como estaba y el panel olvida todo', async () => {
  const d = dialogo(ada.page);
  await d.getByRole('button', { name: 'Cerrar', exact: true }).last().click();
  await d.waitFor({ state: 'detached' });
  igual(await filasDeTabla(ada.page), tablaAntes.ids, 'filas de la tabla');
  igual(await posicion(ada.page), tablaAntes.posicion, 'desplazamiento');
  igual(listas(ada), tablaAntes.listas, 'la tabla se volvió a pedir');
  await botonAsistente(ada.page).click();
  await dialogo(ada.page).waitFor();
  igual(await resultados(dialogo(ada.page)).count(), 0, 'el panel conservó resultados');
  igual(await dialogo(ada.page).locator('.asistente-maestra-comparacion > *').count(), 0, 'el panel conservó la comparación');
});

await revisar('un detalle que todavía carga no se abre después de cerrar el asistente', async () => {
  const d = dialogo(ada.page);
  await preguntar(d, 'Busca terrenos industriales en Jalisco de más de 10,000 m²');
  // A result outside the table's page: only those are read from the server.
  let fuera;
  for (;;) {
    fuera = (await resultados(d).evaluateAll((li) => li.map((x) => x.dataset.id))).find((id) => !tablaAntes.ids.includes(id));
    if (fuera) break;
    const n = await resultados(d).count();
    await d.getByRole('button', { name: 'Más resultados' }).click();
    await hasta(async () => (await resultados(d).count()) > n, 'no llegó otra página');
  }
  let soltar;
  const retenida = new Promise((r) => { soltar = r; });
  let llego = false;
  await ada.page.route(`**/api/inventario/terrenos/${fuera}`, async (ruta) => {
    llego = true;
    await retenida;
    await ruta.continue().catch(() => {});
  });
  const nombre = await d.locator(`.asistente-maestra-fila[data-id="${fuera}"] .asistente-maestra-nombre`).innerText();
  await d.locator(`.asistente-maestra-fila[data-id="${fuera}"]`).getByRole('button', { name: 'Ver detalle' }).click();
  await hasta(async () => llego, 'el detalle no se pidió');
  await d.getByRole('button', { name: 'Cerrar', exact: true }).last().click();
  await d.waitFor({ state: 'detached' });
  soltar();
  await esperar(800);
  igual(await ada.page.getByRole('dialog', { name: nombre }).count(), 0, 'el detalle se abrió tras cerrar el asistente');
  igual(await ada.page.locator('.toast-error, [role="alert"]:visible').filter({ hasText: /terreno/ }).count(), 0, 'error tardío');
  await ada.page.unroute(`**/api/inventario/terrenos/${fuera}`);
});

await revisar('mapa maestra después del asistente, sin segunda entrada', async () => {
  await ada.page.getByRole('button', { name: 'Mapa', exact: true }).click();
  await hasta(() => ada.page.evaluate(() => {
    const m = window.__araTabla?.mapa();
    return m && m.modo === 'mapa' && !m.reuniendo && m.total > 0;
  }), 'el mapa no reunió su conjunto');
  const mapa = await ada.page.evaluate(() => window.__araTabla.mapa());
  igual(mapa.total, 68, 'terrenos de la tabla maestra en el mapa');      // 69 created, one deleted
  igual(await botonAsistente(ada.page).isVisible(), false, 'el asistente global aparece en el mapa');
  igual(await proximamente(ada.page.locator('.tabla-pantalla')).isVisible(), false, 'el aviso ocupa la cabecera del mapa');
  cierto(await ada.page.evaluate((id) => Boolean(window.__araTabla.posicion(id)), coinciden[3]), 'un terreno con X/Y no se dibuja');
  await ada.page.getByRole('button', { name: 'Tabla', exact: true }).click();
  await botonAsistente(ada.page).waitFor();
});

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

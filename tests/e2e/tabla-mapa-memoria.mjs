/* Packet 3A: a bounded check of what the table, the page map and the real
 * geometry loader retain after repeated use. Same method as 2A's
 * tabla-memoria.mjs (one warm-up batch, then equal batches, heap read after a
 * forced collection), with the page map open and boundary selections added:
 * per round, select two terrains with a boundary (each body is loaded and
 * drawn), one with X/Y only (the body is dropped), next page and back (the
 * page is replaced), another base and back, open and close the detail with
 * Team B's real file widgets. It reports whether the numbers level off and
 * how many bodies are held at rest. Not a leak hunt and not a capacity claim.
 *
 *   python3 tests/e2e/tabla_servidor.py --puerto 8434 --registros 25000     # terminal 1
 *   ARA_URL=http://localhost:8434 node tests/e2e/tabla-mapa-memoria.mjs [salida.json]
 */

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8434').replace(/\/$/, '');
if (!/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');
const RAIZ = new URL('../..', import.meta.url).pathname;
const CLAVE = /TEST_PASSWORD = "([^"]+)"/.exec(readFileSync(new URL('../support.py', import.meta.url), 'utf8'))[1];
const LOTES = Number(process.env.LOTES ?? 3);
const RONDAS = Number(process.env.RONDAS ?? 10);
const KMZ = Buffer.from(execFileSync('python3', ['-c',
  'import base64, sys\nfrom tests.test_archivos_http import kmz\nsys.stdout.write(base64.b64encode(kmz("poligono_simple")).decode())'],
  { cwd: RAIZ, encoding: 'utf8' }), 'base64');

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-MX' });
context.setDefaultTimeout(30000);
const page = await context.newPage();
await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
const pedidas = { cuerpo: 0 };
page.on('request', (q) => { if (/\/api\/archivos\/geometrias\/.*\/contenido/.test(q.url())) pedidas.cuerpo += 1; });
await context.request.post(`${URL_BASE}/api/login`, { data: { username: 'ada', password: CLAVE } });
await page.goto(`${URL_BASE}/?test=1#/tabla`);   // ?test=1: the read-only __araTabla hook
const lista = () => page.waitForFunction(() => document.querySelector('tr.tabla-fila') && !document.querySelector('.tabla-lienzo[aria-busy]'));
await lista();
const bases = await page.locator('#tabla-vista optgroup option').evaluateAll((os) => os.map((o) => [o.value, o.textContent]));
const [A, B] = [bases.find(([, n]) => n === 'Base Grande')[0], bases.find(([, n]) => n === 'Base 01')[0]];
await page.locator('#tabla-vista').selectOption(A);
await lista();

/* Give two terrains on page 1 and one on page 2 an active boundary, through the real routes. */
async function subirKmz(id) {
  const r = await page.evaluate(async ([t, b64, sha]) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const j = async (x) => ({ status: x.status, datos: await x.json().catch(() => null) });
    const ini = await j(await fetch(`/api/inventario/terrenos/${t}/archivos`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ tipo: 'kmz', nombre_original: 'ficticio.kmz', tamano_declarado: bytes.length, sha256_declarado: sha }) }));
    const v = ini.datos.version_id;
    await fetch(`/api/archivos/versiones/${v}/contenido`, { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: bytes });
    return j(await fetch(`/api/archivos/versiones/${v}/completar`, { method: 'POST' }));
  }, [id, KMZ.toString('base64'), createHash('sha256').update(KMZ).digest('hex')]);
  if (r.status !== 200 || !r.datos.archivo.geometria_activa_id) throw new Error(`KMZ no activo: ${JSON.stringify(r)}`);
}
const ids = () => page.locator('tr.tabla-fila').evaluateAll((fs) => fs.map((f) => f.dataset.id));
const pagina1 = await ids();
await subirKmz(pagina1[0]);
await subirKmz(pagina1[1]);
const primera = () => page.locator('tr.tabla-fila').first().getAttribute('data-id');
async function hastaOtra(accion) {
  const antes = await primera();
  await accion();
  await page.waitForFunction((id) => {
    const f = document.querySelector('tr.tabla-fila');
    return f && f.dataset.id !== id && !document.querySelector('.tabla-lienzo[aria-busy]');
  }, antes);
}
await hastaOtra(() => page.getByRole('button', { name: 'Siguiente' }).click());
const pagina2 = await ids();
await subirKmz(pagina2[0]);
await hastaOtra(() => page.getByRole('button', { name: 'Anterior' }).click());
await page.getByRole('button', { name: 'Actualizar' }).click();
await lista();
await page.getByRole('button', { name: 'Mapa de esta página' }).click();
await page.locator('.previa-mapa.leaflet-container').waitFor();

const estado = () => page.locator('.previa-estado').innerText();
async function elegir(id, esperado) {
  await page.locator(`tr[data-id="${id}"] td[data-col="core:terreno"]`).click();
  await page.waitForFunction((re) => new RegExp(re).test(document.querySelector('.previa-estado')?.textContent ?? ''), esperado.source);
}
const maxCuerpos = { valor: 0 };
async function vigilar() { maxCuerpos.valor = Math.max(maxCuerpos.valor, (await page.evaluate(() => window.__araTabla.previa())).cuerpos); }

async function lote() {
  for (let i = 0; i < RONDAS; i += 1) {
    await elegir(pagina1[0], /Contorno cargado/); await vigilar();
    await elegir(pagina1[1], /Contorno cargado/); await vigilar();
    await elegir(pagina1[2], /coordenadas X\/Y|no tiene ubicación/); await vigilar();
    await hastaOtra(() => page.getByRole('button', { name: 'Siguiente' }).click());
    await elegir(pagina2[0], /Contorno cargado/); await vigilar();
    await hastaOtra(() => page.getByRole('button', { name: 'Anterior' }).click());
    await hastaOtra(() => page.locator('#tabla-vista').selectOption(B));
    await hastaOtra(() => page.locator('#tabla-vista').selectOption(A));
    await page.locator('.tabla-abrir').first().click();
    await page.locator('dialog[open] .archivos-detalle[data-tipo="kmz"]').waitFor();
    await page.locator('dialog[open]').getByRole('button', { name: 'Cerrar' }).last().click();
    await page.locator('dialog').waitFor({ state: 'detached' });
  }
}

async function medir() {
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.waitForTimeout(300);
  const cdp = await context.newCDPSession(page);
  await cdp.send('Performance.enable');
  for (let i = 0; i < 3; i += 1) await cdp.send('HeapProfiler.collectGarbage');
  const { metrics } = await cdp.send('Performance.getMetrics');
  await cdp.detach();
  const m = Object.fromEntries(metrics.map((x) => [x.name, x.value]));
  const previa = await page.evaluate(() => window.__araTabla.previa());
  return {
    heap_kb: Math.round(m.JSHeapUsedSize / 1024), nodos_dom: m.Nodes, listeners: m.JSEventListeners,
    filas: await page.locator('tr.tabla-fila').count(), dialogos: await page.locator('dialog').count(),
    cuerpos_retenidos: previa.cuerpos, cargando: previa.cargando, peticiones_de_cuerpo: pedidas.cuerpo,
  };
}

const puntos = [{ tras: 'carga inicial con el mapa abierto', ...(await medir()) }];
const t0 = Date.now();
await lote();
puntos.push({ tras: `calentamiento (${RONDAS} rondas)`, ...(await medir()) });
for (let n = 1; n <= LOTES; n += 1) {
  await lote();
  puntos.push({ tras: `lote ${n} (${RONDAS} rondas)`, ...(await medir()) });
}
const medidos = puntos.slice(1);
const deltas = medidos.slice(1).map((p, i) => ({
  entre: `${medidos[i].tras} -> ${p.tras}`, heap_kb: p.heap_kb - medidos[i].heap_kb,
  nodos_dom: p.nodos_dom - medidos[i].nodos_dom, listeners: p.listeners - medidos[i].listeners,
}));
const informe = { url: URL_BASE, chrome: browser.version(), fecha: new Date().toISOString(),
  que: `${RONDAS} rondas por lote de: 2 contornos seleccionados y cargados, 1 terreno sólo X/Y, página siguiente ` +
    '(1 contorno) y anterior, otra base y volver, abrir y cerrar el detalle con los widgets reales',
  duracion_s: Math.round((Date.now() - t0) / 1000), max_cuerpos_retenidos: maxCuerpos.valor,
  puntos, deltas_por_lote_tras_el_calentamiento: deltas };
await browser.close();
const texto = JSON.stringify(informe, null, 2);
if (process.argv[2]) writeFileSync(process.argv[2], `${texto}\n`);
console.log(texto);
if (maxCuerpos.valor > 1) process.exit(1);

/* A bounded check of what the table retains after repeated use (correction 1
 * of packet 2A). One warm-up batch, then equal batches of 100 transitions:
 * next page, previous page, another base, back, open and close a terrain's
 * detail. Each batch ends in the same view with nothing open; the heap is
 * read after a forced collection. It reports whether the numbers level off.
 * It is not a leak hunt and not a capacity claim.
 *
 *   python3 tests/e2e/tabla_servidor.py --puerto 8434 --registros 25000     # terminal 1
 *   ARA_URL=http://localhost:8434 node tests/e2e/tabla-memoria.mjs [salida.json]
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8434').replace(/\/$/, '');
if (!/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');
const CLAVE = /TEST_PASSWORD = "([^"]+)"/.exec(readFileSync(new URL('../support.py', import.meta.url), 'utf8'))[1];
const LOTES = Number(process.env.LOTES ?? 3);
const RONDAS = 20;                       // x 5 transitions = 100 per batch

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-MX' });
context.setDefaultTimeout(30000);
const page = await context.newPage();
await context.request.post(`${URL_BASE}/api/login`, { data: { username: 'ada', password: CLAVE } });
await page.goto(`${URL_BASE}/#/tabla`);
const lista = () => page.waitForFunction(() => document.querySelector('tr.tabla-fila') && !document.querySelector('.tabla-lienzo[aria-busy]'));
await lista();
const bases = await page.locator('#tabla-vista optgroup option').evaluateAll((os) => os.map((o) => [o.value, o.textContent]));
const [A, B] = [bases.find(([, n]) => n === 'Base Grande')[0], bases.find(([, n]) => n === 'Base 01')[0]];
const primera = () => page.locator('tr.tabla-fila').first().getAttribute('data-id');

async function hastaOtra(accion) {
  const antes = await primera();
  await accion();
  await page.waitForFunction((id) => {
    const f = document.querySelector('tr.tabla-fila');
    return f && f.dataset.id !== id && !document.querySelector('.tabla-lienzo[aria-busy]');
  }, antes);
}

async function lote() {
  for (let i = 0; i < RONDAS; i += 1) {
    await hastaOtra(() => page.getByRole('button', { name: 'Siguiente' }).click());
    await hastaOtra(() => page.getByRole('button', { name: 'Anterior' }).click());
    await hastaOtra(() => page.locator('#tabla-vista').selectOption(B));
    await hastaOtra(() => page.locator('#tabla-vista').selectOption(A));
    await page.locator('.tabla-abrir').first().click();
    await page.locator('dialog[open] .detalle-datos').waitFor();
    await page.locator('dialog[open]').getByRole('button', { name: 'Cerrar' }).click();
    await page.locator('dialog').waitFor({ state: 'detached' });
  }
}

async function medir() {
  // The same resting state every time: Base Grande, first page, nothing open or focused.
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.waitForTimeout(300);
  const cdp = await context.newCDPSession(page);
  await cdp.send('Performance.enable');
  for (let i = 0; i < 3; i += 1) await cdp.send('HeapProfiler.collectGarbage');
  const { metrics } = await cdp.send('Performance.getMetrics');
  await cdp.detach();
  const m = Object.fromEntries(metrics.map((x) => [x.name, x.value]));
  return {
    heap_kb: Math.round(m.JSHeapUsedSize / 1024), nodos_dom: m.Nodes, listeners: m.JSEventListeners,
    filas: await page.locator('tr.tabla-fila').count(), dialogos: await page.locator('dialog').count(),
  };
}

await page.locator('#tabla-vista').selectOption(A);
await lista();
const puntos = [{ tras: 'carga inicial', ...(await medir()) }];
await lote();
puntos.push({ tras: 'calentamiento (100 transiciones)', ...(await medir()) });
for (let n = 1; n <= LOTES; n += 1) {
  await lote();
  puntos.push({ tras: `lote ${n} (100 transiciones)`, ...(await medir()) });
}
const medidos = puntos.slice(1);
const deltas = medidos.slice(1).map((p, i) => ({
  entre: `${medidos[i].tras} -> ${p.tras}`, heap_kb: p.heap_kb - medidos[i].heap_kb,
  nodos_dom: p.nodos_dom - medidos[i].nodos_dom, listeners: p.listeners - medidos[i].listeners,
}));
const informe = { url: URL_BASE, chrome: browser.version(), fecha: new Date().toISOString(),
  que: `${RONDAS} rondas por lote de: página siguiente, anterior, otra base, volver, abrir y cerrar el detalle`,
  puntos, deltas_por_lote_tras_el_calentamiento: deltas };
await browser.close();
const texto = JSON.stringify(informe, null, 2);
if (process.argv[2]) writeFileSync(process.argv[2], `${texto}\n`);
console.log(texto);

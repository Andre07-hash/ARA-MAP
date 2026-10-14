/* Selecting several terrains in the table and acting on them at once, with
 * the real local server (tests/e2e/tabla_servidor.py on a folder it creates
 * and deletes), real sessions and Chromium. Fictional accounts and data only.
 *
 *   cd tests/e2e && node tabla-seleccion.mjs
 *
 * What it checks: rows and "this page" can be ticked; "select all of this
 * view" gathers every terrain of the view; an administrator creates a base
 * with the selection, transfers it and deletes it after the last warning; a
 * cancelled warning deletes nothing; an operator only gets "Borrar…". Optional:
 * CHROMIUM=/path, SELECCION_PUERTO.
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.SELECCION_PUERTO ?? 8483);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const CARPETA = mkdtempSync(join(tmpdir(), 'ara-seleccion-'));

const servidor = spawn(PY, [join(AQUI, 'tabla_servidor.py'), '--puerto', String(PUERTO),
  '--carpeta', join(CARPETA, 'instalacion'), '--registros', '30'], { cwd: RAIZ, stdio: ['ignore', 'pipe', 'ignore'] });
await new Promise((resolve, reject) => {
  let texto = '';
  servidor.stdout.on('data', (d) => { texto += d; if (/LISTO/.test(texto)) resolve(); });
  servidor.on('exit', (c) => reject(new Error(`el servidor salió (${c}): ${texto}`)));
});

let fallos = 0;
async function revisar(nombre, fn) {
  try {
    await fn();
    console.log(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    console.log(`FALLO ${nombre}\n     ${String(error?.stack ?? error).split('\n').slice(0, 6).join('\n     ')}`);
  }
}
const igual = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium' });
const errores = [];
async function abrir(usuario) {
  const page = await (await navegador.newContext({ viewport: { width: 1500, height: 900 }, locale: 'es-MX' })).newPage();
  page.on('pageerror', (e) => errores.push(`${usuario}: ${e}`));
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  await page.goto(`${URLBASE}/?test=1`);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click().catch(() => {});
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVE);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
  return page;
}
const api = (page, ruta) => page.evaluate(async (r) => (await fetch(r)).json(), ruta);
async function irA(page, vista) {
  await page.goto(`${URLBASE}/?test=1#/tabla/${vista}`);
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
}
const filas = (page) => page.locator('.tabla-grid tbody tr');
const lote = (page) => page.locator('.tabla-lote');
const ids = (page, desde, hasta) => filas(page).evaluateAll((trs, [a, b]) => trs.slice(a, b).map((t) => t.dataset.id), [desde, hasta]);
async function marcar(page, lista) {
  for (const id of lista) await page.locator(`tr[data-id="${id}"] input.tabla-marca`).check();
}
const total = async (page) => (await api(page, '/api/inventario/terrenos?limit=1')).total;

const ada = await abrir('ada');
await irA(ada, 'maestra');
const inicial = await total(ada);

await revisar('marcar filas y la página; seleccionar toda la vista', async () => {
  igual(await lote(ada).isHidden(), true, 'sin selección no hay barra');
  await marcar(ada, await ids(ada, 0, 2));
  igual(await lote(ada).locator('strong').innerText(), '2 terrenos seleccionados', 'dos filas');
  await lote(ada).getByRole('button', { name: /^Seleccionar los/ }).click();
  await lote(ada).getByText(`${inicial} terrenos seleccionados`).waitFor();
  igual(await ada.locator('thead input.tabla-marca').isChecked(), true, 'la página entera');
  await lote(ada).getByRole('button', { name: 'Quitar selección' }).click();
  igual(await lote(ada).isHidden(), true, 'quitar selección');
});

await revisar('crear una base con la selección', async () => {
  const elegidos = await ids(ada, 0, 3);
  await marcar(ada, elegidos);
  await lote(ada).getByRole('button', { name: 'Crear base con ellos…' }).click();
  await ada.getByLabel('Nombre de la base').fill('Base Selección Ficticia');
  await ada.getByRole('button', { name: 'Crear y mover' }).click();
  await ada.getByText('3 terrenos movidos a «Base Selección Ficticia».').first().waitFor();
  const base = (await api(ada, '/api/maestra/bases')).bases.find((b) => b.nombre === 'Base Selección Ficticia');
  igual(base?.terrenos, 3, 'la base nueva tiene los tres');
});

await revisar('transferir la selección', async () => {
  const destino = (await api(ada, '/api/maestra/bases')).bases.find((b) => b.nombre === 'Base Selección Ficticia');
  const elegidos = await ids(ada, 5, 7);
  await marcar(ada, elegidos);
  await lote(ada).getByRole('button', { name: 'Transferir…' }).click();
  await ada.getByLabel('Base de destino').selectOption(destino.id);
  await ada.getByRole('button', { name: 'Transferir', exact: true }).click();
  await ada.getByText('2 terrenos transferidos.').first().waitFor();
  for (const id of elegidos) igual((await api(ada, `/api/inventario/terrenos/${id}`)).terreno.base_id, destino.id, id);
});

await revisar('borrar la selección: cancelar no borra; confirmar sí', async () => {
  const elegidos = await ids(ada, 10, 12);
  await marcar(ada, elegidos);
  await lote(ada).getByRole('button', { name: 'Borrar…' }).click();
  await ada.getByText('¿Borrar 2 terrenos?').waitFor();
  await ada.getByRole('button', { name: 'Cancelar' }).click();
  igual(await total(ada), inicial, 'cancelar no borra');
  await lote(ada).getByRole('button', { name: 'Borrar…' }).click();
  await ada.getByRole('button', { name: 'Borrar definitivamente' }).click();
  await ada.getByText('2 terrenos borrados.').first().waitFor();
  igual(await total(ada), inicial - 2, 'borrados');
  // The toast comes when the table starts reloading; the counter follows when the page arrives.
  const contador = `1–${inicial - 2} de ${inicial - 2}`;
  await ada.waitForFunction((t) => document.querySelector('.tabla-cuenta')?.textContent === t, contador, { timeout: 15000 })
    .catch(() => {});
  igual(await ada.locator('.tabla-cuenta').innerText(), contador, 'el contador');
});

await revisar('el operador sólo puede borrar', async () => {
  const olga = await abrir('olga');
  await olga.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await olga.locator('.tabla-grid tbody tr input.tabla-marca').first().check();
  const botones = await lote(olga).locator('button').allInnerTexts();
  igual(botones.filter((b) => !b.startsWith('Seleccionar los')), ['Borrar…', 'Quitar selección'], 'acciones del operador');
});

await revisar('sin errores de página', async () => igual(errores, [], 'errores'));

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : '\ntodo bien');
process.exit(fallos ? 1 : 0);

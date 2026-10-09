/* Local measurement of the employee table in a real Chrome against the real
 * server: 25,000 synthetic terrains, 3,000 of them in one base, five editing
 * sessions. It reports; it asserts only what must hold at any speed (bounded
 * rows, every edit accounted for).
 *
 *   python3 tests/e2e/tabla_servidor.py --puerto 8434 --registros 25000     # terminal 1
 *   ARA_URL=http://localhost:8434 node tests/e2e/tabla-medicion.mjs [salida.json]
 *
 * One developer machine, loopback, fictional data. Not a hosted measurement
 * and not a capacity claim.
 */

import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8434').replace(/\/$/, '');
if (!/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(URL_BASE)) throw new Error('Solo contra un servidor local desechable.');
const CLAVE = /TEST_PASSWORD = "([^"]+)"/.exec(readFileSync(new URL('../support.py', import.meta.url), 'utf8'))[1];
const SALIDA = process.argv[2] ?? null;
const OPERADORES = ['olga', 'omar', 'oscar', 'olivia', 'oriol'];

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const mediana = (xs) => { const o = [...xs].sort((a, b) => a - b); return o[Math.floor(o.length / 2)]; };
const resumen = (xs) => ({ n: xs.length, mediana_ms: Math.round(mediana(xs)), max_ms: Math.round(Math.max(...xs)) });
const informe = { url: URL_BASE, chrome: browser.version(), fecha: new Date().toISOString() };

async function sesion(usuario) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-MX' });
  context.setDefaultTimeout(30000);
  const page = await context.newPage();
  const llamadas = [];
  page.on('response', async (r) => {
    if (!r.url().includes('/api/')) return;
    const cuerpo = await r.body().catch(() => Buffer.alloc(0));
    llamadas.push({ ruta: `${r.request().method()} ${new URL(r.url()).pathname}`, estado: r.status(), bytes: cuerpo.length });
  });
  await page.goto(`${URL_BASE}/`);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.getByLabel('Usuario').fill(usuario);
  await page.getByLabel('Contraseña').fill(CLAVE);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.session-user').waitFor();
  return { context, page, llamadas };
}

const filas = (page) => page.locator('tr.tabla-fila').count();
const cargada = (page, n) => page.waitForFunction((k) => document.querySelectorAll('tr.tabla-fila').length === k
  && !document.querySelector('.tabla-lienzo[aria-busy]'), n);
const primera = (page) => page.locator('tr.tabla-fila').first().getAttribute('data-id');

async function memoria(page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  await cdp.send('HeapProfiler.collectGarbage');
  await cdp.send('HeapProfiler.collectGarbage');
  const { metrics } = await cdp.send('Performance.getMetrics');
  const m = Object.fromEntries(metrics.map((x) => [x.name, x.value]));
  await cdp.detach();
  return { heap_mb: +(m.JSHeapUsedSize / 1048576).toFixed(2), nodos_dom: m.Nodes, listeners: m.JSEventListeners };
}

/** Run something and wait until the page shows another first row (a new page). */
async function hastaOtraPagina(page, accion) {
  const antes = await primera(page);
  const t0 = performance.now();
  await accion();
  await page.waitForFunction((id) => {
    const fila = document.querySelector('tr.tabla-fila');
    return fila && fila.dataset.id !== id && !document.querySelector('.tabla-lienzo[aria-busy]');
  }, antes);
  return performance.now() - t0;
}

/* ---- 1. operator, the 3,000-record base: first usable page ---------------- */
{
  const { context, page, llamadas } = await sesion('olga');
  await cargada(page, 100);
  // A fresh load of the app with the session already open, to the first usable 100 rows.
  const tiempos = [];
  let peticiones = null;
  for (let i = 0; i < 5; i += 1) {
    llamadas.length = 0;
    const t0 = performance.now();
    await page.reload();
    await cargada(page, 100);
    await page.locator('tr.tabla-fila td[data-col="core:terreno"]').first().focus();
    tiempos.push(performance.now() - t0);
    peticiones = llamadas.map((l) => ({ ...l }));
  }
  const lista = peticiones.find((l) => /\/terrenos$/.test(l.ruta));
  informe.primera_pagina_operador = {
    que: 'recarga completa de la app con sesión abierta hasta 100 filas pintadas y una celda enfocada (base de 3,000)',
    ...resumen(tiempos), objetivo_ms: 2000,
    peticiones_api: peticiones.map((l) => `${l.ruta} ${l.estado} ${l.bytes} B`),
    bytes_de_la_lista: lista.bytes,
    filas_dom: await filas(page), celdas_dom: await page.locator('td.tabla-celda').count(),
    total_mostrado: (await page.locator('.tabla-cuenta').innerText()).trim(),
  };
  assert.equal(informe.primera_pagina_operador.filas_dom, 100);

  /* ---- 2. typing and focus feedback ------------------------------------- */
  const id = await primera(page);
  const medirTecla = (selector, tecla) => page.evaluate(([sel, key]) => new Promise((resolve) => {
    const objetivo = document.querySelector(sel);
    objetivo.focus();
    let t0 = 0;
    document.addEventListener('keydown', () => { t0 = performance.now(); }, { capture: true, once: true });
    const listo = () => requestAnimationFrame(() => requestAnimationFrame(() => resolve(performance.now() - t0)));
    document.addEventListener('keydown', listo, { once: true });
    window.__tecla = key;
  }), [selector, tecla]);
  const abrirEditor = [];
  const teclear = [];
  const mover = [];
  for (let i = 0; i < 15; i += 1) {
    const celda = `tr[data-id="${id}"] td[data-col="core:municipio"]`;
    // typing on a focused cell opens its editor with that character
    let espera = medirTecla(celda, 'M');
    await page.keyboard.press('M');
    abrirEditor.push(await espera);
    assert.equal(await page.locator('.tabla-editor').inputValue(), 'M');
    espera = page.evaluate(() => new Promise((resolve) => {
      const campo = document.querySelector('.tabla-editor');
      campo.addEventListener('input', () => {
        const t0 = performance.now();
        requestAnimationFrame(() => requestAnimationFrame(() => resolve(performance.now() - t0)));
      }, { once: true });
    }));
    await page.keyboard.press('u');
    teclear.push(await espera);
    await page.keyboard.press('Escape');
    espera = medirTecla(celda, 'ArrowDown');
    await page.keyboard.press('ArrowDown');
    mover.push(await espera);
  }
  informe.respuesta_al_teclado = {
    que: 'de la tecla a dos cuadros pintados después (página de 100 filas); incluye ~2 cuadros de espera por diseño de la medida',
    objetivo_ms: 100,
    abrir_editor_tecleando: resumen(abrirEditor), tecla_dentro_del_editor: resumen(teclear), mover_foco_con_flecha: resumen(mover),
  };

  /* ---- 3. save feedback -------------------------------------------------- */
  const aPendiente = [];
  const aGuardado = [];
  const idsDePagina = await page.locator('tr.tabla-fila').evaluateAll((fs) => fs.slice(0, 20).map((f) => f.dataset.id));
  for (const [i, tid] of idsDePagina.entries()) {
    const sel = `tr[data-id="${tid}"] td[data-col="core:municipio"]`;
    await page.locator(sel).focus();
    await page.keyboard.press('Enter');
    await page.locator('.tabla-editor').fill(`Medido ${i}`);
    const t0 = performance.now();
    await page.keyboard.press('Enter');
    await page.waitForFunction((s) => /is-pendiente/.test(document.querySelector(s).className)
      || document.querySelector(s).textContent.startsWith('Medido'), sel);
    aPendiente.push(performance.now() - t0);
    await page.waitForFunction((s) => !/is-pendiente|is-editando/.test(document.querySelector(s).className), sel);
    aGuardado.push(performance.now() - t0);
  }
  informe.guardar_una_celda = {
    que: 'de Enter a la celda marcada "guardando" y a guardada (PATCH real)',
    a_estado_guardando: resumen(aPendiente), a_guardada: resumen(aGuardado),
  };

  /* ---- 4. paging, sorting, searching; memory after repetition ------------ */
  await page.reload();
  await cargada(page, 100);
  const base = await memoria(page);
  const paginas = [];
  for (let vuelta = 0; vuelta < 3; vuelta += 1) {
    for (let i = 0; i < 10; i += 1) paginas.push(await hastaOtraPagina(page, () => page.getByRole('button', { name: 'Siguiente' }).click()));
    for (let i = 0; i < 10; i += 1) paginas.push(await hastaOtraPagina(page, () => page.getByRole('button', { name: 'Anterior' }).click()));
  }
  const trasPaginar = await memoria(page);
  assert.equal(await filas(page), 100, 'pages replace each other; rows never accumulate');
  const ordenar = await hastaOtraPagina(page, () => page.locator('#tabla-orden').selectOption('terreno'));
  const buscar = await hastaOtraPagina(page, () => page.locator('#tabla-buscar').fill('nandu 12'));
  const coincidencias = (await page.locator('.tabla-cuenta').innerText()).trim();
  await page.locator('#tabla-buscar').fill('');
  await page.locator('#tabla-limite').selectOption('200');
  await cargada(page, 200);
  const con200 = await memoria(page);
  informe.paginar_base_3000 = {
    que: '60 cambios de página (100 filas) con Siguiente/Anterior en la base de 3,000',
    ...resumen(paginas),
    ordenar_por_nombre_ms: Math.round(ordenar), buscar_ms_incluye_300_de_espera: Math.round(buscar), coincidencias,
    memoria_inicial: base, memoria_tras_60_paginas: trasPaginar, memoria_con_200_filas: con200,
    filas_dom_con_200: await filas(page),
  };
  assert.equal(informe.paginar_base_3000.filas_dom_con_200, 200);
  await context.close();
}

/* ---- 5. administrator: master table over 25,000, base switches ------------- */
{
  const { context, page, llamadas } = await sesion('ada');
  await page.goto(`${URL_BASE}/#/tabla/maestra`);
  await cargada(page, 100);
  const tiempos = [];
  for (let i = 0; i < 5; i += 1) {
    llamadas.length = 0;
    const t0 = performance.now();
    await page.reload();
    await cargada(page, 100);
    tiempos.push(performance.now() - t0);
  }
  const lista = llamadas.find((l) => l.ruta === 'GET /api/inventario/terrenos');
  const inicial = await memoria(page);
  const paginas = [];
  for (let i = 0; i < 20; i += 1) paginas.push(await hastaOtraPagina(page, () => page.getByRole('button', { name: 'Siguiente' }).click()));
  const vistas = await page.locator('#tabla-vista option').evaluateAll((os) => os.map((o) => o.value));
  const cambios = [];
  for (let i = 0; i < 24; i += 1) {
    cambios.push(await hastaOtraPagina(page, () => page.locator('#tabla-vista').selectOption(vistas[2 + (i % (vistas.length - 2))])));
  }
  const trasCambios = await memoria(page);
  informe.tabla_maestra_25000 = {
    que: 'administradora, tabla maestra sobre 25,000',
    primera_pagina: { ...resumen(tiempos), objetivo_ms: 2000 }, bytes_de_la_lista: lista.bytes,
    total_mostrado: (await page.locator('.tabla-cuenta').innerText()).trim(),
    siguiente_pagina: resumen(paginas), cambio_de_base: resumen(cambios),
    memoria_inicial: inicial, memoria_tras_20_paginas_y_24_cambios_de_base: trasCambios,
    filas_dom: await filas(page),
  };
  assert.ok(informe.tabla_maestra_25000.filas_dom <= 100);
  await context.close();
}

/* ---- 6. five sessions editing at once ---------------------------------- */
{
  const sesiones = await Promise.all(OPERADORES.map((u) => sesion(u)));
  for (const s of sesiones) await cargada(s.page, 100);
  const ids = await sesiones[0].page.locator('tr.tabla-fila').evaluateAll((fs) => fs.map((f) => f.dataset.id));
  const versionDe = async (id) => sesiones[0].page.evaluate(async (t) =>
    (await (await fetch(`/api/inventario/terrenos/${t}`)).json()).terreno, id);

  // 5 x 10 different rows, all at once.
  const latencias = [];
  await Promise.all(sesiones.map(async ({ page }, n) => {
    for (let i = 0; i < 10; i += 1) {
      const sel = `tr[data-id="${ids[30 + n * 10 + i]}"] td[data-col="core:estado"]`;
      await page.locator(sel).focus();
      await page.keyboard.press('Enter');
      await page.locator('.tabla-editor').fill(`Sesión ${n}`);
      const t0 = performance.now();
      await page.keyboard.press('Enter');
      await page.waitForFunction((s) => !/is-pendiente|is-editando/.test(document.querySelector(s).className), sel);
      latencias.push(performance.now() - t0);
    }
  }));
  let guardadas = 0;
  for (let n = 0; n < 5; n += 1) {
    for (let i = 0; i < 10; i += 1) {
      const t = await versionDe(ids[30 + n * 10 + i]);
      if (t.draft.estado === `Sesión ${n}` && t.version === 2) guardadas += 1;   // untouched rows: one save each
    }
  }
  const sinResolver = await Promise.all(sesiones.map(({ page }) => page.locator('.tabla-pendiente').count()));

  // All five write the same cell of one row from the same version.
  const disputada = ids[25];
  const antes = (await versionDe(disputada)).version;
  const sel = `tr[data-id="${disputada}"] td[data-col="core:estado"]`;
  for (const [n, { page }] of sesiones.entries()) {
    await page.locator(sel).focus();
    await page.keyboard.press('Enter');
    await page.locator('.tabla-editor').fill(`Disputa ${n}`);
  }
  await Promise.all(sesiones.map(({ page }) => page.keyboard.press('Enter')));
  await Promise.all(sesiones.map(({ page }) => page.waitForFunction(
    (s) => !/is-pendiente|is-editando/.test(document.querySelector(s).className), sel)));
  const conflictos = await Promise.all(sesiones.map(({ page }) => page.locator('.tabla-pendiente.is-conflicto').count()));
  const final = await versionDe(disputada);
  informe.cinco_sesiones = {
    que: 'cinco operadores en la base de 3,000, cada uno en su navegador',
    cincuenta_ediciones_en_filas_distintas: { guardadas, cambios_sin_resolver: sinResolver, ...resumen(latencias) },
    misma_celda_a_la_vez: { conflictos_mostrados_por_sesion: conflictos, version_final: final.version, valor_final: final.draft.estado },
  };
  assert.equal(guardadas, 50);
  assert.equal(final.version, antes + 1, 'one of the five won; nobody overwrote it');
  assert.equal(conflictos.reduce((a, b) => a + b, 0), 4);
  for (const s of sesiones) await s.context.close();
}

await browser.close();
const texto = JSON.stringify(informe, null, 2);
if (SALIDA) writeFileSync(SALIDA, `${texto}\n`);
console.log(texto);

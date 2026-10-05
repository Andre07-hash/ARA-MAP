/* End-to-end checks against a running ARA Map.
 *
 * Self-provisioning: it creates the bases and the comparison map it needs
 * through the API, then removes them again, so it can run against any
 * instance without depending on what is already stored.
 *
 * Point it at a throwaway database -- see README.md.
 */

import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const URL_BASE = (process.env.ARA_URL ?? 'http://localhost:8420').replace(/\/$/, '');
const FIXTURE = fileURLToPath(new globalThis.URL('../fixtures/base_terrenos_09_26.xlsx', import.meta.url));
const FIXTURE_AGOSTO = fileURLToPath(new globalThis.URL('../fixtures/base_terrenos_08_26_sintetica.xlsx', import.meta.url));

const api = async (path, options = {}) => {
  const response = await fetch(`${URL_BASE}/api${path}`, options);
  if (!response.ok) throw new Error(`${path} -> ${response.status} ${await response.text()}`);
  return response.status === 204 ? null : response.json();
};

async function importBase(bytes, nombre) {
  const preview = await api('/importar/vista-previa', {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream', 'X-Archivo': 'fixture.xlsx' },
    body: bytes,
  });
  const { base } = await api('/importar/confirmar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: preview.token, nombre }),
  });
  return base;
}

const created = { bases: [], mapas: [], carpetas: [], formatos: [] };

async function saveAsMap(base, nombre) {
  const { mapa } = await api('/mapas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      nombre, tipo: 'simple',
      capas: [{ base_id: base.id, color: '#2a78d6' }],
      config: { basemap: 'claro', modoColor: 'precio' },
      nombre_sigue_base: nombre === base.nombre,
    }),
  });
  created.mapas.push(mapa.id);
  return mapa;
}

async function provision() {
  // Two genuinely different months, so the change classification has something
  // real to find.
  const agosto = await importBase(await readFile(FIXTURE_AGOSTO), 'E2E Agosto');
  const septiembre = await importBase(await readFile(FIXTURE), 'E2E Septiembre');
  created.bases.push(agosto.id, septiembre.id);

  const mapaAgosto = await saveAsMap(agosto, 'E2E Mapa Agosto');
  const mapaSeptiembre = await saveAsMap(septiembre, 'E2E Mapa Septiembre');

  // The comparison is a MERGE of two saved maps, which is what the product
  // actually asks for.
  const { mapa } = await api('/mapas/combinar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      nombre: 'E2E Agosto vs Septiembre',
      mapa_ids: [mapaAgosto.id, mapaSeptiembre.id],
      colores: ['#2a78d6', '#eb6834'],
      config: { basemap: 'claro', modoColor: 'base' },
    }),
  });
  created.mapas.push(mapa.id);
  return { agosto, septiembre, mapaAgosto, mapaSeptiembre, mapa };
}

async function cleanup() {
  for (const id of created.mapas) await api(`/mapas/${id}`, { method: 'DELETE' }).catch(() => {});
  for (const id of created.bases) await api(`/bases/${id}`, { method: 'DELETE' }).catch(() => {});
  for (const id of created.carpetas) await api(`/carpetas/${id}`, { method: 'DELETE' }).catch(() => {});
  for (const id of created.formatos) await api(`/formatos/${id}`, { method: 'DELETE' }).catch(() => {});
}

const checks = [];
const check = async (name, fn) => {
  try { await fn(); checks.push(`  PASS  ${name}`); }
  catch (e) { checks.push(`  FAIL  ${name}\n        ${e.message.split('\n')[0]}`); if (process.env.E2E_SHOTS) await page?.screenshot({ path: `${process.env.E2E_SHOTS}/fail-${checks.length}.png` }).catch(() => {}); }
};

const fixtures = await provision();
const browser = await chromium.launch(process.env.ARA_CHROMIUM ? { executablePath: process.env.ARA_CHROMIUM } : { channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

try {
  await page.goto(`${URL_BASE}/?test=1`, { waitUntil: 'load' });
  await page.waitForTimeout(1600);

  // Open the base this run created, so the checks do not depend on load order.
  await page.getByRole('navigation').getByRole('button', { name: 'Bases' }).click();
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: new RegExp(fixtures.septiembre.nombre) }).first().click();
  await page.waitForTimeout(2000);

  await check('the map renders one mark per located terrain', async () => {
    const n = await page.evaluate(async () => {
      const { getState } = await import('/lib/store.js');
      return getState().terrenos.filter(t => t.ubicado).length;
    });
    assert.equal(n, 39);
  });

  await check('the legend reports the unplaced count', async () => {
    assert.ok(await page.getByText(/40 terrenos fuera del mapa/).isVisible());
  });

  await check('the unplaced panel lists every terrain without coordinates', async () => {
    await page.getByRole('button', { name: /Fuera del mapa/i }).click();
    await page.waitForTimeout(400);
    assert.equal(await page.locator('.unplaced-list > li').count(), 40);
    await page.getByRole('button', { name: /Fuera del mapa/i }).click();
  });

  await check('filtering by state narrows the set', async () => {
    await page.getByRole('checkbox', { name: /Nuevo León/ }).check();
    await page.waitForTimeout(400);
    assert.ok(await page.getByText('27 terrenos de 79').isVisible());
    await page.getByRole('button', { name: /Limpiar/ }).click();
    await page.waitForTimeout(300);
    assert.ok(await page.getByText('79 terrenos de 79').isVisible());
  });

  await check('search is accent-insensitive', async () => {
    const box = page.getByPlaceholder('Nombre, municipio o dirección');
    await box.fill('marcenas');
    await page.waitForTimeout(400);
    assert.ok(await page.getByText('1 terreno de 79').isVisible());
    await box.fill('');
    await page.waitForTimeout(300);
  });

  await check('the detail panel shows a terrain and its findings', async () => {
    await page.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Tabla' }).click();
    await page.waitForTimeout(400);
    await page.getByRole('row', { name: /Marce/ }).first().click();
    await page.waitForTimeout(400);
    assert.ok(await page.getByRole('heading', { name: 'Marceñas' }).isVisible());
    assert.ok(await page.getByText(/error de un dígito/).isVisible());
    assert.match(await page.locator('.detail .figure-lead').first().textContent(), /388,689,722/);
  });

  await check('Escape closes the detail panel', async () => {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.detail').count(), 0);
  });

  await check('the table sorts by unit price', async () => {
    await page.getByRole('button', { name: /Asking \$\/m/ }).click();
    await page.waitForTimeout(400);
    assert.match(await page.locator('tbody tr').first().textContent(), /Los Caudales/);
  });

  await check('the map stays inside its column when the panel is open', async () => {
    await page.getByRole('row', { name: /Marce/ }).first().click();
    await page.waitForTimeout(400);
    await page.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Mapa' }).click();
    await page.waitForTimeout(1200);
    const boxes = await page.evaluate(() => {
      const r = s => document.querySelector(s).getBoundingClientRect();
      return { mapRight: Math.round(r('.map-host').right), panelLeft: Math.round(r('.detail-slot').x) };
    });
    assert.ok(boxes.mapRight <= boxes.panelLeft,
      `map right ${boxes.mapRight} overlaps panel at ${boxes.panelLeft}`);
    await page.keyboard.press('Escape');
  });

  await check('the basemap switches to satellite', async () => {
    await page.getByRole('radio', { name: 'Satélite' }).click();
    await page.waitForTimeout(1800);
    const src = await page.locator('.leaflet-tile').first().getAttribute('src');
    assert.match(src, /World_Imagery/);
  });

  await check('a saved comparison opens with both layers in different colours', async () => {
    await page.getByRole('navigation').getByRole('button', { name: 'Mapas guardados' }).click();
    await page.waitForTimeout(600);
    await page.getByRole('button', { name: new RegExp(fixtures.mapa.nombre) }).first().click();
    await page.waitForTimeout(2200);
    const colours = await page.evaluate(async () => {
      const { getState } = await import('/lib/store.js');
      return getState().capas.map(c => c.color);
    });
    assert.equal(colours.length, 2);
    assert.notEqual(colours[0], colours[1], 'layers share a colour');
  });

  await check('both layers are actually drawn, not hidden behind each other', async () => {
    const drawn = await page.evaluate(async () => {
      const { getState } = await import('/lib/store.js');
      const s = getState();
      const colores = new Set(s.capas.map(c => c.color));
      const used = new Set(s.terrenos.filter(t => t.ubicado).map(t => colores.has(t.color) ? t.color : null));
      return [...used].filter(Boolean).length;
    });
    assert.equal(drawn, 2, 'expected both layer colours among the drawn terrains');
  });

  await check('hiding a layer removes its terrains', async () => {
    assert.equal(await page.locator('.legend-item').count(), 2);
    await page.locator('.legend-item input').first().uncheck();
    await page.waitForTimeout(500);
    assert.ok(await page.getByText('79 terrenos de 79').isVisible());
    await page.locator('.legend-item input').first().check();
    await page.waitForTimeout(400);
  });

  await check('the comparison table names the source of every row', async () => {
    await page.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Tabla' }).click();
    await page.waitForTimeout(700);
    const encabezados = await page.locator('thead th').allTextContents();
    assert.ok(encabezados.some((h) => /Base/.test(h)), 'missing Base column');
    assert.ok(encabezados.some((h) => /Cambio/.test(h)), 'missing Cambio column');
    const fuentes = await page.locator('tbody tr .cell-source').count();
    assert.ok(fuentes > 0, 'no row names its source');
  });

  await check('the comparison reports new, removed and changed terrains', async () => {
    const estados = await page.locator('tbody .cambio').allTextContents();
    const texto = estados.join(' ');
    for (const esperado of ['Nuevo', 'Eliminado', 'Cambiado']) {
      assert.ok(texto.includes(esperado), `no row reported as ${esperado}`);
    }
  });

  await check('a changed row names the fields that changed', async () => {
    // Scoped to a "cambiado" row: removals use the same element to say which
    // layers a terrain is missing from.
    const campos = await page.locator('tbody .cambio-cambiado .cambio-campos')
      .first().textContent();
    assert.match(campos, /Asking|Ubicación|Dirección/);
  });

  await check('a saved map ignores later changes to its base', async () => {
    const antes = await api(`/mapas/${fixtures.mapaSeptiembre.id}/terrenos`);
    await api(`/bases/${fixtures.septiembre.id}/terrenos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ terreno: 'E2E Terreno nuevo', estado: 'Jalisco',
                             municipio: 'Tala', superficie_m2: 5000 }),
    });
    const despues = await api(`/mapas/${fixtures.mapaSeptiembre.id}/terrenos`);
    assert.equal(despues.terrenos.length, antes.terrenos.length,
      'the frozen map changed when its base did');
  });

  await check('updating a saved map pulls the base change in', async () => {
    const antes = await api(`/mapas/${fixtures.mapaSeptiembre.id}/terrenos`);
    await api(`/mapas/${fixtures.mapaSeptiembre.id}/actualizar`, { method: 'POST' });
    const despues = await api(`/mapas/${fixtures.mapaSeptiembre.id}/terrenos`);
    assert.equal(despues.terrenos.length, antes.terrenos.length + 1);
  });

  await check('marks start as symbols and become real footprints on zoom in', async () => {
    await page.getByRole('navigation').getByRole('button', { name: 'Bases' }).click();
    await page.waitForTimeout(500);
    await page.getByRole('button', { name: new RegExp(fixtures.septiembre.nombre) }).first().click();
    await page.waitForTimeout(2200);
    // The legend only exists in map view, and an earlier check left the table on.
    await page.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Mapa' }).click();
    await page.waitForTimeout(1200);

    const lejos = await page.locator('.legend-escala').textContent();
    assert.match(lejos, /símbolos/, `zoomed out the marks should be symbols, got: ${lejos}`);

    const acercar = page.locator('.leaflet-control-zoom-in');
    for (let i = 0; i < 8; i += 1) {
      await acercar.click();
      await page.waitForTimeout(350);
    }
    await page.waitForTimeout(1200);

    const cerca = await page.locator('.legend-escala').textContent();
    assert.ok(/escala real|superficie real/.test(cerca),
      `zoomed in the marks should be to scale, got: ${cerca}`);
  });

  await check('R1 typing letter by letter keeps focus and the whole word', async () => {
    const buscar = page.locator('#buscar');
    await buscar.fill('');
    await buscar.click();
    // Real keystrokes: fill() assigns the value at once and would not catch a
    // rebuild that destroys the focused node between characters.
    await page.keyboard.type('Marce', { delay: 60 });
    await page.waitForTimeout(400);
    assert.equal(await buscar.inputValue(), 'Marce');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'buscar');
  });

  await check('R1 editing mid-caret and clearing keeps the field usable', async () => {
    const buscar = page.locator('#buscar');
    await buscar.press('Home');
    await page.keyboard.type('El ', { delay: 50 });
    await page.waitForTimeout(300);
    assert.equal(await buscar.inputValue(), 'El Marce');
    const total = await page.evaluate(async () => {
      const { getState } = await import('/lib/store.js');
      return getState().terrenos.length;
    });
    await buscar.fill('');
    await page.waitForTimeout(400);
    const resultado = await page.locator('.rail-result').textContent();
    assert.match(resultado, new RegExp(`de ${total}`),
      `clearing the search did not restore all ${total} rows: ${resultado}`);
  });

  await check('R1 numeric filters accept continuous typing', async () => {
    const min = page.locator('#superficie-min');
    await min.click();
    await page.keyboard.type('25000', { delay: 50 });
    await page.waitForTimeout(400);
    assert.equal(await min.inputValue(), '25000');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'superficie-min');
    await min.fill('');
    await page.waitForTimeout(400);
  });

  await check('R4 double click zooms a terrain to its own scale', async () => {
    const objetivo = await page.evaluate(async () => {
      const { getState } = await import('/lib/store.js');
      const t = getState().terrenos
        .filter((x) => x.ubicado && x.superficie_m2 > 20000)
        .sort((a, b) => b.superficie_m2 - a.superficie_m2)[0];
      return t ? { id: t.id, lat: t.lat, lon: t.lon, m2: t.superficie_m2 } : null;
    });
    assert.ok(objetivo, 'no located terrain to test with');

    const requerido = await page.evaluate(async ([m2, lat]) => {
      const g = await import('/lib/geo.js');
      return g.trueScaleZoom(m2, lat, 7);
    }, [objetivo.m2, objetivo.lat]);

    await page.evaluate(([lat, lon]) => window.__araTest.irA(lat, lon, 7),
                        [objetivo.lat, objetivo.lon]);
    await page.waitForTimeout(900);

    const punto = await page.evaluate((id) => window.__araTest.puntoDe(id), objetivo.id);
    await page.mouse.dblclick(punto.x, punto.y);
    await page.waitForTimeout(2600);

    const zoom = await page.evaluate(() => window.__araTest.zoom());
    assert.ok(zoom >= requerido, `expected zoom >= ${requerido}, got ${zoom}`);

    const aEscala = await page.evaluate(async ([id]) => {
      const { getState } = await import('/lib/store.js');
      const { markRadius } = await import('/lib/geo.js');
      const t = getState().terrenos.find((x) => x.id === id);
      return markRadius(t.superficie_m2, t.lat, window.__araTest.zoom()).aEscala;
    }, [objetivo.id]);
    assert.equal(aEscala, true, 'the circle did not reach its real size');
  });

  await check('R4 background double click still zooms the map normally', async () => {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    const antes = await page.evaluate(() => window.__araTest.zoom());
    await page.mouse.dblclick(700, 240);
    await page.waitForTimeout(1300);
    assert.ok(await page.evaluate(() => window.__araTest.zoom()) > antes);
  });

  await check('R2 the supplied logo is shown and decodes', async () => {
    const logo = page.locator('.brand-logo');
    assert.ok(await logo.isVisible());
    const info = await logo.evaluate((img) => ({
      completo: img.complete, w: img.naturalWidth, h: img.naturalHeight,
      src: img.currentSrc,
    }));
    assert.ok(info.completo && info.w > 0, 'the logo did not decode');
    assert.equal(info.w, 522);
    assert.equal(info.h, 478);
    assert.match(info.src, /ara-logo\.png$/);
    assert.equal(await page.locator('.brand-mark').count(), 0, 'the old pin is still there');
  });

  await check('R5 renaming a source updates the saved maps that show it', async () => {
    const mapa = await saveAsMap(fixtures.septiembre, fixtures.septiembre.nombre);
    const nuevo = 'E2E Renombrada';
    await api(`/bases/${fixtures.septiembre.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre: nuevo }),
    });

    const { mapa: recargado } = await api(`/mapas/${mapa.id}`);
    assert.equal(recargado.nombre, nuevo, 'the following title did not change');
    assert.equal(recargado.capas[0].nombre, nuevo, 'the layer label did not change');

    const { mapa: comparacion } = await api(`/mapas/${fixtures.mapa.id}`);
    assert.ok(comparacion.capas.some((c) => c.nombre.includes(nuevo)),
      'the comparison layer kept the old name');
  });

  await check('R3 a comparison exports one sheet per source', async () => {
    const respuesta = await fetch(`${URL_BASE}/api/exportar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mapa_id: fixtures.mapa.id, nombre: 'e2e' }),
    });
    assert.ok(respuesta.ok, `export failed: ${respuesta.status}`);
    const bytes = Buffer.from(await respuesta.arrayBuffer());
    // A .xlsx is a zip; its central directory lists one entry per sheet.
    const texto = bytes.toString('latin1');
    const hojas = (texto.match(/xl\/worksheets\/sheet\d+\.xml/g) ?? []);
    assert.ok(new Set(hojas).size >= 2, `expected at least 2 sheets, saw ${new Set(hojas).size}`);
  });

  await check('the preview accounts for rows it will not import', async () => {
    // A row carrying data but no name must be reported, never dropped quietly.
    const { readFile: leer } = await import('node:fs/promises');
    const bytes = await leer(FIXTURE);
    const preview = await api('/importar/vista-previa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream', 'X-Archivo': 'f.xlsx' },
      body: bytes,
    });
    assert.equal(preview.filas_con_datos,
                 preview.conteo + preview.rechazadas.length,
                 'rows with data are unaccounted for');
    assert.ok('sin_coordenadas' in preview && 'ubicacion_invalida' in preview,
      'the preview does not separate missing from impossible coordinates');
  });

  await check('impossible coordinates are kept off the map', async () => {
    const { terrenos } = await api(`/bases/${fixtures.septiembre.id}/terrenos`);
    for (const t of terrenos) {
      if (t.ubicacion === 'invalida') {
        assert.equal(t.ubicado, false, `${t.terreno} plotted with bad coordinates`);
      }
    }
    // Every plotted terrain must have a usable location.
    assert.ok(terrenos.filter((t) => t.ubicado).every((t) => t.ubicacion === 'valida'));
  });

  await check('a deleted source cannot be inherited by a later import', async () => {
    const bytes = await (await import('node:fs/promises')).readFile(FIXTURE);
    const victima = await importBase(bytes, 'E2E Efímera');
    const mapa = await saveAsMap(victima, 'E2E Mapa Efímero');
    const antes = (await api(`/mapas/${mapa.id}/terrenos`)).terrenos.length;

    await api(`/bases/${victima.id}`, { method: 'DELETE' });
    const reemplazo = await importBase(bytes, 'E2E Reemplazo');
    created.bases.push(reemplazo.id);

    await api(`/mapas/${mapa.id}/actualizar`, { method: 'POST' });
    const despues = (await api(`/mapas/${mapa.id}/terrenos`)).terrenos.length;
    assert.equal(despues, antes, 'the saved map absorbed an unrelated source');

    const { mapa: recargado } = await api(`/mapas/${mapa.id}`);
    assert.equal(recargado.capas[0].base_id, null, 'the deleted source id was retained');
    assert.equal(recargado.capas[0].base_existe, false);
  });

  await check('merging two versions of one source keeps both', async () => {
    const bytes = await (await import('node:fs/promises')).readFile(FIXTURE);
    const fuente = await importBase(bytes, 'E2E Versionada');
    created.bases.push(fuente.id);
    const v1 = await saveAsMap(fuente, 'E2E Versión 1');

    await api(`/bases/${fuente.id}/terrenos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ terreno: 'E2E Añadido', estado: 'Jalisco',
                             municipio: 'Tala', superficie_m2: 5000 }),
    });
    const v2 = await saveAsMap(fuente, 'E2E Versión 2');

    const plan = await api('/mapas/combinar/vista-previa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mapa_ids: [v1.id, v2.id] }),
    });
    assert.equal(plan.total, 2, 'a version was dropped from the merge');
    assert.ok(plan.capas.every((c) => c.es_version), 'versions are not labelled');
  });

  // --- The import assistant through the real UI ---
  // Semicolon-separated with decimal commas. Nobody is asked about the number
  // format: read with a decimal point the coordinates would be impossible, so
  // the values settle it. A correction can still re-read it the other way.
  const CSV_NOMBRE = 'E2E CSV Octubre';
  const csvBase = [
    'Terreno;Estado;Municipio;Dirección;X;Y;Afectaciones %',
    'E2E CSV Norte;Jalisco;Tala;"Camino 8; lote 2";20,653;-103,701;10%',
    'E2E CSV Sin Mapa;Sonora;Hermosillo;;;;0,25',
  ];
  const csvFile = (lines, name) => ({
    name, mimeType: 'text/csv', buffer: Buffer.from(lines.join('\r\n') + '\r\n', 'utf8'),
  });
  const fixture = (nombre) => fileURLToPath(new globalThis.URL(`../fixtures/asistente/${nombre}`, import.meta.url));
  const dialogo = () => page.locator('dialog[open]');
  const stat = (titulo) => dialogo().locator('.stat').filter({ hasText: titulo }).locator('.figure-lead');
  const enMapa = () => stat('En el mapa');
  const botonImportar = () => dialogo().locator('#assistant-importar');
  const esperarStat = (titulo, valor) => page.waitForFunction(
    ([t, v]) => [...document.querySelectorAll('dialog[open] .stat')]
      .find((s) => s.textContent.includes(t))?.querySelector('.figure-lead')?.textContent === v,
    [titulo, valor]);

  async function pickFile(trigger, file) {
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), trigger()]);
    assert.match(await chooser.element().getAttribute('accept'), /\.csv/, 'the picker does not offer .csv');
    await chooser.setFiles(file);
  }
  async function importar(file) {
    // A check that failed may have left its dialog open; do not let it cascade.
    while (await dialogo().count()) await page.keyboard.press('Escape');
    await page.getByRole('navigation', { name: 'Secciones' }).getByRole('button', { name: 'Bases' }).click();
    await pickFile(() => page.getByRole('button', { name: 'Importar archivo' }).first().click(), file);
  }
  /* Waits for the preview. A file whose prices carry no currency marker asks
   * for it once; the fictional fixtures always meant pesos, so that is the
   * default answer. The real workbook's check answers USD explicitly. */
  const PREGUNTA_MONEDA = '¿En qué moneda están los precios?';
  async function listoParaImportar(moneda = 'MXN') {
    // Either the preview is ready, or the currency is being asked and not yet
    // answered. Not merely "a question": an answered one stays on screen
    // until the reply lands.
    const sinResponder = (texto) => [...(document.querySelector('dialog[open]')?.querySelectorAll('.question') ?? [])]
      .some((q) => q.textContent.includes(texto) && !q.querySelector('input:checked'));
    await page.waitForFunction((texto) => {
      const pendiente = [...(document.querySelector('dialog[open]')?.querySelectorAll('.question') ?? [])]
        .some((q) => q.textContent.includes(texto) && !q.querySelector('input:checked'));
      return Boolean(document.querySelector('dialog[open] #assistant-importar:not([disabled])') || pendiente);
    }, PREGUNTA_MONEDA);
    const pregunta = dialogo().locator('.question').filter({ hasText: PREGUNTA_MONEDA });
    if (await page.evaluate(sinResponder, PREGUNTA_MONEDA)) {
      await pregunta.getByRole('radio', { name: new RegExp(`\\(${moneda}\\)`) }).check();
      await dialogo().locator('#assistant-continuar').click();
    }
    await botonImportar().waitFor();
    await page.waitForFunction(() => !document.querySelector('#assistant-importar')?.disabled);
  }
  async function sinEleccionDeIA() {
    const texto = await dialogo().textContent();
    assert.doesNotMatch(texto, /usar (la )?ia|inteligencia artificial|elige (un )?modelo/i, 'an AI choice was offered');
  }

  await check('a CSV is read with its number convention detected, and a correction re-reads it', async () => {
    await page.goto(`${URL_BASE}/?test=1`, { waitUntil: 'load' });
    await importar(csvFile(csvBase, 'e2e-octubre.csv'));
    await listoParaImportar();
    await sinEleccionDeIA();
    assert.equal(await enMapa().textContent(), '1');

    await dialogo().getByText('Corregir interpretación').click();
    await dialogo().locator('#corr-decimal').selectOption('dot');
    await page.waitForFunction(() => [...document.querySelectorAll('dialog[open] .stat')]
      .find((s) => s.textContent.includes('En el mapa'))?.querySelector('.figure-lead')?.textContent === '0');
    await dialogo().locator('#corr-decimal').selectOption('comma');
    await page.waitForFunction(() => [...document.querySelectorAll('dialog[open] .stat')]
      .find((s) => s.textContent.includes('En el mapa'))?.querySelector('.figure-lead')?.textContent === '1');
    await listoParaImportar();

    await dialogo().locator('#nombre-base').fill(CSV_NOMBRE);
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });

    const { bases } = await api('/bases');
    const base = bases.find((b) => b.nombre === CSV_NOMBRE);
    assert.ok(base, 'the CSV base was not created');
    created.bases.push(base.id);
    assert.equal(base.hoja, 'CSV');
    assert.equal(base.ubicados, 1);
    const { terrenos } = await api(`/bases/${base.id}/terrenos`);
    const norte = terrenos.find((t) => t.terreno === 'E2E CSV Norte');
    assert.deepEqual([norte.lat, norte.lon, norte.afectaciones_pct], [20.653, -103.701, 0.1]);
    assert.equal(norte.direccion, 'Camino 8; lote 2');
  });

  await check('a CSV appends to a base and reports its lines', async () => {
    // An import refreshes whichever base was open, which can leave the gallery.
    await page.getByRole('navigation', { name: 'Secciones' }).getByRole('button', { name: 'Bases' }).click();
    const card = page.locator('.card').filter({ hasText: CSV_NOMBRE });
    const lines = [...csvBase, 'E2E CSV Nuevo;Jalisco;Tala;;20,7;-103,6;', ';Jalisco;Tala;;;;'];
    await pickFile(() => card.getByRole('button', { name: 'Agregar terrenos' }).click(),
                   csvFile(lines, 'e2e-agregado.csv'));
    await listoParaImportar();
    assert.equal(await stat('Nuevas').textContent(), '1');
    assert.equal(await stat('Duplicadas').textContent(), '2');
    await dialogo().locator('.rechazadas-list').getByText('Línea 5').waitFor();  // the nameless row, by CSV line
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });

    const { bases } = await api('/bases');
    assert.equal(bases.find((b) => b.nombre === CSV_NOMBRE).conteo, 3);
  });

  await check('assistant 1/3: a familiar file goes upload → review → import', async () => {
    await importar(fixture('familiar_reordenado.csv'));
    await listoParaImportar();
    assert.equal(await dialogo().locator('.question').count(), 0, 'a familiar file asked something');
    await sinEleccionDeIA();
    assert.equal(await enMapa().textContent(), '4');
    assert.equal(await dialogo().locator('.leaflet-interactive').count(), 4, 'the preview map is missing points');
    await dialogo().locator('#nombre-base').fill('E2E Familiar');
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });
    const base = (await api('/bases')).bases.find((b) => b.nombre === 'E2E Familiar');
    created.bases.push(base.id);
    assert.equal(base.conteo, 4);
  });

  await check('assistant 2/3: an unfamiliar layout is interpreted without questions', async () => {
    await importar(fixture('desconocido_titulos.xlsx'));
    await listoParaImportar();
    assert.equal(await dialogo().locator('.question').count(), 0);
    await dialogo().getByText(/Se omiten 2 filas de título/).waitFor();
    await dialogo().getByText('Fila de totales («Total»)').waitFor();
    assert.equal(await stat('Terrenos').textContent(), '4');
    await dialogo().getByRole('button', { name: 'Cancelar' }).click();
    await dialogo().waitFor({ state: 'detached' });
  });

  await check('assistant 2/3 (automatic): unresolved headers are read automatically or asked', async () => {
    await importar(fixture('desconocido_ia.csv'));
    await dialogo().locator('#assistant-importar, #assistant-continuar').first().waitFor();
    await sinEleccionDeIA();
    if (await dialogo().locator('.question').count()) {
      // No automatic assistance on this server: focused questions, each with real samples.
      assert.ok(await dialogo().locator('.question').count() <= 4, 'too many questions at once');
      await dialogo().getByText('¿Cuál columna contiene el nombre del terreno?').waitFor();
    } else {
      await dialogo().getByText('Detalles de la detección').click();
      await dialogo().getByText(/Se usó asistencia automática/).waitFor();
    }
    await dialogo().getByRole('button', { name: 'Cancelar' }).click();
    await dialogo().waitFor({ state: 'detached' });
  });

  await check('assistant 3/3: an ambiguous file asks one question, answered by keyboard', async () => {
    await importar(fixture('ambiguo_valor.csv'));
    await dialogo().getByText('¿Qué representa la columna «Valor»?').waitFor();
    assert.equal(await dialogo().locator('.question').count(), 1);
    assert.equal(await dialogo().locator('#assistant-continuar').isDisabled(), true, 'nothing chosen yet');
    await dialogo().getByRole('radio', { name: /Precio total/ }).focus();
    await page.keyboard.press('Space');
    await dialogo().locator('#assistant-continuar').focus();
    await page.keyboard.press('Enter');
    await listoParaImportar();
    assert.equal(await stat('Con precio').textContent(), '4');
    assert.ok(await dialogo().locator('#recordar-formato').isChecked(), '"Recordar este formato" should default on');
    await dialogo().locator('#nombre-base').fill('E2E Ambiguo');
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });
    const base = (await api('/bases')).bases.find((b) => b.nombre === 'E2E Ambiguo');
    created.bases.push(base.id);
    const { formatos } = await api('/formatos');
    created.formatos.push(...formatos.map((f) => f.id));
    assert.ok(formatos.some((f) => f.nombre === 'Formato de «ambiguo_valor»'), 'the format was not remembered');
  });

  await check('assistant: the remembered format is reused on the next upload', async () => {
    await importar(fixture('ambiguo_valor.csv'));
    await listoParaImportar();
    assert.equal(await dialogo().locator('.question').count(), 0, 'the remembered answer was asked again');
    await dialogo().getByText('Detalles de la detección').click();
    await dialogo().getByText(/Formato guardado: «Formato de «ambiguo_valor»»/).waitFor();
    await dialogo().getByRole('button', { name: 'Cancelar' }).click();
    await dialogo().waitFor({ state: 'detached' });
  });

  await check('assistant: same-named columns from a saved format are reconfirmed, not guessed', async () => {
    const precios = (a, b) => csvFile(['Terreno,Precio,Precio,Latitud,Longitud', `E2E Repetidas,${a},${b},19.5,-99.1`],
                                      'e2e-repetidas.csv');
    await importar(precios(1000000, 500));
    // First time: the ordinary question -- which «Precio» is the total?
    await dialogo().getByText('¿Cuál columna contiene el dato «Precio total»?').waitFor();
    await dialogo().getByRole('radio', { name: /«Precio \(1\)»/ }).check();
    // Asked alongside it: the prices carry no currency marker.
    await dialogo().getByRole('radio', { name: /\(MXN\)/ }).check();
    await dialogo().locator('#assistant-continuar').click();
    await listoParaImportar();
    // ...and the other one is the price per m², set in the correction editor.
    await dialogo().getByText('Corregir interpretación').click();
    await dialogo().locator('#corr-col-2').selectOption('asking_m2');
    await page.waitForFunction(() => !document.querySelector('#assistant-importar')?.disabled);
    await dialogo().locator('#nombre-base').fill('E2E Repetidas 1');
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });
    created.bases.push((await api('/bases')).bases.find((b) => b.nombre === 'E2E Repetidas 1').id);
    created.formatos.push(...(await api('/formatos')).formatos.map((f) => f.id));

    // Same headings, columns swapped: the format cannot know, so it asks.
    await importar(precios(500, 1000000));
    await dialogo().getByText('El archivo tiene 2 columnas «Precio». ¿Cuál es cuál?').waitFor();
    assert.equal(await dialogo().locator('.question').count(), 1, 'only the repeated columns should be asked');
    await dialogo().getByRole('radio', { name: /^Al revés/ }).focus();
    await page.keyboard.press('Space');
    await dialogo().locator('#assistant-continuar').click();
    await listoParaImportar();
    const filas = await dialogo().locator('.preview-table tbody tr').first().textContent();
    assert.match(filas, /MXN\s1,000,000/, 'the total price was not the column the user named');
    await dialogo().getByRole('button', { name: 'Cancelar' }).click();
    await dialogo().waitFor({ state: 'detached' });
  });

  await check('assistant: dollars declared by the cell format stay dollars, never MXN', async () => {
    await importar(fixture('moneda_formato.xlsx'));
    await botonImportar().waitFor();
    await page.waitForFunction(() => !document.querySelector('#assistant-importar')?.disabled);
    assert.equal(await dialogo().locator('.question').count(), 0, 'the file says USD; nothing to ask');
    assert.equal(await stat('Con precio').textContent(), '4');
    await dialogo().getByText(/dólares estadounidenses \(USD\) — lo indica el archivo/).first().waitFor();
    await dialogo().locator('#recordar-formato').uncheck();
    await dialogo().locator('#nombre-base').fill('E2E Moneda');
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });
    const base = (await api('/bases')).bases.find((b) => b.nombre === 'E2E Moneda');
    created.bases.push(base.id);
    const { terrenos } = await api(`/bases/${base.id}/terrenos`);
    assert.equal(terrenos.length, 4);
    assert.ok(terrenos.every((t) => t.asking_price !== null && t.moneda === 'USD'), 'a dollar price lost its currency');
  });

  await check('incident 2026-10-01: the real ARA workbook imports in the browser with USD prices', async () => {
    await importar(FIXTURE);
    await dialogo().getByText('¿En qué moneda están los precios?').waitFor();
    assert.equal(await dialogo().locator('.question').count(), 1, 'only the currency should be asked');
    await listoParaImportar('USD');
    assert.equal(await stat('Terrenos').textContent(), '79');
    assert.equal(await enMapa().textContent(), '39');
    assert.equal(await stat('Con precio').textContent(), '59');
    assert.match(await dialogo().locator('.stat').filter({ hasText: 'Con precio' }).textContent(),
      /total en USD; 60 con precio por m²/);
    await dialogo().getByText(/Moneda de los precios: dólares estadounidenses \(USD\) — según tu respuesta/).waitFor();
    const fila = async (nombre) => (await dialogo().locator('.preview-table tbody tr')
      .filter({ hasText: nombre }).first().textContent()).replace(/\s/g, ' ');
    assert.match(await fila('Marceñas'), /USD 388,689,722.*USD 600\/m²/);
    assert.match(await fila('El Dorado'), /USD 122\.50\/m²/);
    await dialogo().locator('#recordar-formato').uncheck();
    await dialogo().locator('#nombre-base').fill('E2E Real USD');
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });
    const base = (await api('/bases')).bases.find((b) => b.nombre === 'E2E Real USD');
    created.bases.push(base.id);
    assert.deepEqual([base.conteo, base.ubicados], [79, 39]);
    const { terrenos } = await api(`/bases/${base.id}/terrenos`);
    const t = Object.fromEntries(terrenos.map((x) => [x.terreno, x]));
    assert.deepEqual([t['Marceñas'].asking_price, t['Marceñas'].asking_m2, t['Marceñas'].moneda], [388689722, 600, 'USD']);
    assert.deepEqual([t['El Dorado'].asking_m2, t['El Dorado'].moneda], [122.5, 'USD']);

    // Reopened: the table shows the stored dollars, cents kept.
    await page.getByRole('navigation', { name: 'Secciones' }).getByRole('button', { name: 'Bases' }).click();
    await page.getByRole('button', { name: /E2E Real USD/ }).first().click();
    await page.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Tabla' }).click();
    const celda = (await page.locator('.table tbody tr').filter({ hasText: 'El Dorado' }).first().textContent())
      .replace(/\s/g, ' ');
    assert.match(celda, /USD 133,072,446.*USD 122\.50\/m²/);
    await page.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Mapa' }).click();
  });

  await check('assistant: a footer is set aside, restored from the preview, and removed again', async () => {
    await importar(fixture('nota_al_pie.csv'));
    await listoParaImportar();
    assert.equal(await stat('Terrenos').textContent(), '4');
    // A name that starts with "Total" is a terrain, not a summary.
    await dialogo().locator('.preview-table').getByText('Total Predio Alfa').first().waitFor();
    await dialogo().getByText(/Nota al pie/).waitFor();

    await dialogo().getByRole('button', { name: 'Sí es un terreno: importarla' }).click();
    await esperarStat('Terrenos', '5');
    await dialogo().locator('.preview-table tbody tr').last()
      .getByRole('button', { name: 'No importar' }).click();
    await esperarStat('Terrenos', '4');
    await listoParaImportar();

    await dialogo().locator('#recordar-formato').uncheck();
    await dialogo().locator('#nombre-base').fill('E2E Nota');
    await botonImportar().click();
    await dialogo().waitFor({ state: 'detached' });
    const base = (await api('/bases')).bases.find((b) => b.nombre === 'E2E Nota');
    created.bases.push(base.id);
    const { terrenos } = await api(`/bases/${base.id}/terrenos`);
    assert.equal(terrenos.length, 4);
    assert.ok(terrenos.some((t) => t.terreno === 'Total Predio Alfa'), 'a real terrain was dropped');
    assert.ok(!terrenos.some((t) => t.terreno.startsWith('NOTA')), 'the footer was imported as a terrain');
  });

  await check('assistant: a header below a page of notes is found, and named by its printed row', async () => {
    await importar(fixture('encabezado_tardio.xlsx'));
    await listoParaImportar();
    assert.equal(await dialogo().locator('.question').count(), 0, 'the real header was not found');
    assert.equal(await stat('Terrenos').textContent(), '4');

    await dialogo().getByText('Corregir interpretación').click();
    await dialogo().locator('#corr-encabezado-linea').fill('56');   // the row Excel shows
    await dialogo().getByRole('button', { name: 'Usar' }).click();
    await listoParaImportar();
    assert.equal(await stat('Terrenos').textContent(), '4');

    await dialogo().locator('#corr-encabezado-linea').fill('999');
    await dialogo().getByRole('button', { name: 'Usar' }).click();
    await dialogo().getByText(/El archivo tiene datos de la fila 1 a la 60/).waitFor();
    await dialogo().getByRole('button', { name: 'Cancelar' }).click();
    await dialogo().waitFor({ state: 'detached' });
  });

  // --- Folders, through the real UI on both dashboards ---
  const secciones = () => page.getByRole('navigation', { name: 'Secciones' });
  const carpetasNav = (tipo) => page.getByRole('navigation', { name: `Carpetas de ${tipo}` });
  const irA = async (seccion) => { await secciones().getByRole('button', { name: seccion }).click(); };
  const buscarCarpeta = async (tipo, nombre) =>
    (await api(`/carpetas?tipo=${tipo}`)).carpetas.find((c) => c.nombre === nombre);
  const cardDe = (nombre) => page.locator('.card').filter({
    has: page.getByRole('heading', { name: nombre, exact: true }) });

  await check('a base folder is created, filled, browsed and imported into', async () => {
    await page.goto(`${URL_BASE}/?test=1`, { waitUntil: 'load' });
    await irA('Bases');
    await page.getByRole('button', { name: 'Nueva carpeta' }).click();
    await dialogo().getByLabel('Nombre de la carpeta').fill('E2E Cliente');
    await page.keyboard.press('Enter');                       // Enter submits the form
    await dialogo().waitFor({ state: 'detached' });
    const carpeta = await buscarCarpeta('bases', 'E2E Cliente');
    assert.ok(carpeta, 'the folder was not created');
    created.carpetas.push(carpeta.id);
    await page.getByRole('heading', { name: 'E2E Cliente', level: 2 }).waitFor();
    await page.getByText('Esta carpeta está vacía.', { exact: false }).waitFor();

    // Move a base in from the all-bases view.
    await carpetasNav('bases').getByRole('button', { name: /^Todas las bases/ }).click();
    // By id: an earlier check renames this base.
    const { base: septiembre } = await api(`/bases/${fixtures.septiembre.id}`);
    const card = cardDe(septiembre.nombre);
    await card.getByRole('button', { name: 'Mover a carpeta…' }).click();
    await dialogo().getByRole('radio', { name: /E2E Cliente/ }).check();
    await dialogo().getByRole('button', { name: 'Mover' }).click();
    await dialogo().waitFor({ state: 'detached' });
    await card.getByText('E2E Cliente').waitFor();            // the folder label on the card
    const movida = (await api(`/bases/${fixtures.septiembre.id}`)).base;
    assert.equal(movida.carpeta_id, carpeta.id);
    await page.waitForFunction(() => document.activeElement?.id === 'folder-heading-bases',
      null, { timeout: 5000 }).catch(async () => {
      const foco = await page.evaluate(() => `${document.activeElement?.tagName}#${document.activeElement?.id}`);
      throw new Error(`focus was not restored after the move: ${foco}`);
    });

    // Browse the folder: exactly that base, and the count agrees.
    await carpetasNav('bases').getByRole('button', { name: /^E2E Cliente/ }).click();
    assert.equal(await page.locator('.folder-content .card').count(), 1);
    assert.match(await carpetasNav('bases').getByRole('button', { name: /^E2E Cliente/ }).textContent(), /1$/);

    // Importing from inside the folder defaults to it.
    await pickFile(() => page.getByRole('button', { name: 'Importar archivo' }).click(),
                   csvFile(csvBase, 'e2e-carpeta.csv'));
    await listoParaImportar();
    const destino = dialogo().getByLabel('Carpeta');
    assert.equal(await destino.locator('option:checked').textContent(), 'E2E Cliente');
    await dialogo().locator('#nombre-base').fill('E2E En carpeta');
    await dialogo().getByRole('button', { name: /^Importar 2 terrenos/ }).click();
    await dialogo().waitFor({ state: 'detached' });
    const { bases } = await api('/bases');
    const importada = bases.find((b) => b.nombre === 'E2E En carpeta');
    created.bases.push(importada.id);
    assert.equal(importada.carpeta_id, carpeta.id);
  });

  await check('renaming and deleting a base folder keeps every base', async () => {
    await irA('Bases');
    await carpetasNav('bases').getByRole('button', { name: /^E2E Cliente/ }).click();
    await page.locator('.folder-actions').getByRole('button', { name: 'Renombrar' }).click();
    await dialogo().getByLabel('Nombre de la carpeta').fill('E2E Cliente Renombrado');
    await dialogo().getByRole('button', { name: 'Guardar' }).click();
    await dialogo().waitFor({ state: 'detached' });
    await page.getByRole('heading', { name: 'E2E Cliente Renombrado', level: 2 }).waitFor();

    const antes = (await api('/bases')).bases.length;
    await page.locator('.folder-actions').getByRole('button', { name: 'Eliminar carpeta' }).click();
    await dialogo().getByText(/Sus 2 bases pasarán a «Sin carpeta»/).waitFor();
    await dialogo().getByRole('button', { name: 'Eliminar carpeta' }).click();
    await dialogo().waitFor({ state: 'detached' });
    await page.getByRole('heading', { name: 'Sin carpeta', level: 2 }).waitFor();

    const { bases } = await api('/bases');
    assert.equal(bases.length, antes, 'deleting a folder deleted a base');
    assert.equal(bases.find((b) => b.id === fixtures.septiembre.id).carpeta_id, null);
    assert.equal(await buscarCarpeta('bases', 'E2E Cliente Renombrado'), undefined);
  });

  await check('a comparison draws on every folder and lands in the open one', async () => {
    await irA('Mapas guardados');
    await page.getByRole('button', { name: 'Nueva carpeta' }).click();
    await dialogo().getByLabel('Nombre de la carpeta').fill('E2E Informes');
    await dialogo().getByRole('button', { name: 'Crear carpeta' }).click();
    await dialogo().waitFor({ state: 'detached' });
    const carpeta = await buscarCarpeta('mapas', 'E2E Informes');
    created.carpetas.push(carpeta.id);

    // The open folder is empty, yet every saved map is offered as a source.
    await page.getByRole('button', { name: 'Nueva comparación' }).click();
    const { mapas } = await api('/mapas');
    assert.equal(await dialogo().locator('.pick-list li').count(), mapas.length);
    assert.equal(await dialogo().getByLabel('Carpeta').locator('option:checked').textContent(), 'E2E Informes');
    await dialogo().getByRole('checkbox').nth(0).check();
    await dialogo().getByRole('checkbox').nth(1).check();
    await dialogo().getByLabel('Nombre del mapa').fill('E2E Comparación en carpeta');
    await dialogo().getByRole('button', { name: 'Crear mapa' }).click();
    await dialogo().waitFor({ state: 'detached' });
    const nuevo = (await api('/mapas')).mapas.find((m) => m.nombre === 'E2E Comparación en carpeta');
    created.mapas.push(nuevo.id);
    assert.equal(nuevo.carpeta_id, carpeta.id);
  });

  await check('moving the open map keeps its view and its snapshot', async () => {
    const nuevo = (await api('/mapas')).mapas.find((m) => m.nombre === 'E2E Comparación en carpeta');
    const antes = await api(`/mapas/${nuevo.id}/terrenos`);
    const filtro = await page.evaluate(async () => {
      const { getState, setFilter } = await import('/lib/store.js');
      setFilter({ busqueda: 'lo' });
      return { texto: getState().filtros.busqueda, mapa: getState().mapaActivo?.nombre };
    });
    assert.equal(filtro.mapa, 'E2E Comparación en carpeta', 'the new comparison is not open');

    await irA('Mapas guardados');
    await carpetasNav('mapas').getByRole('button', { name: /^E2E Informes/ }).click();
    await cardDe('E2E Comparación en carpeta').getByRole('button', { name: 'Mover a carpeta…' }).click();
    await dialogo().getByRole('radio', { name: /Sin carpeta/ }).check();
    await dialogo().getByRole('button', { name: 'Mover' }).click();
    await dialogo().waitFor({ state: 'detached' });
    await page.getByText('Esta carpeta está vacía.', { exact: false }).waitFor();

    const estado = await page.evaluate(async () => {
      const { getState } = await import('/lib/store.js');
      const s = getState();
      return { texto: s.filtros.busqueda, mapa: s.mapaActivo?.nombre, carpeta: s.mapaActivo?.carpeta_id };
    });
    assert.deepEqual(estado, { texto: 'lo', mapa: 'E2E Comparación en carpeta', carpeta: null });
    const despues = await api(`/mapas/${nuevo.id}/terrenos`);
    assert.deepEqual(despues.terrenos, antes.terrenos, 'the frozen terrains changed');
    assert.equal(despues.mapa.actualizado_en, antes.mapa.actualizado_en);
  });

  await check('a saved map survives deletion of its base', async () => {
    await api(`/bases/${fixtures.agosto.id}`, { method: 'DELETE' });
    created.bases = created.bases.filter((id) => id !== fixtures.agosto.id);

    const { mapa } = await api(`/mapas/${fixtures.mapa.id}`);
    assert.equal(mapa.capas.length, 2, 'a layer disappeared with its base');
    const huerfana = mapa.capas.find((c) => c.base_existe === false);
    assert.ok(huerfana, 'the orphaned layer is not flagged');
    assert.ok(huerfana.conteo > 0, 'the orphaned layer lost its terrains');
  });

  // Layout: every header mode at phone, tablet and desktop widths, with the
  // busiest toolbar (a saved comparison). The cloud modes are simulated by
  // answering /api/config in the browser; everything else is the real server.
  const MODOS = {
    local: null,
    'cloud visitor': { readOnly: true, cloud: true, authRequired: true, maxUploadBytes: 4194304 },
    'cloud editor': { readOnly: false, cloud: true, authRequired: true, maxUploadBytes: 4194304 },
  };
  for (const [modo, config] of Object.entries(MODOS)) {
    for (const width of [320, 375, 700, 768, 1024, 1440]) {
      await check(`layout ${modo} @${width}px: header and toolbar fit, no stray text`, async () => {
        const vista = await browser.newPage({ viewport: { width, height: 800 } });
        try {
          if (config) {
            await vista.route('**/api/config', (route) => route.fulfill({ json: config }));
          }
          await vista.goto(`${URL_BASE}/?test=1`, { waitUntil: 'load' });
          await vista.getByRole('navigation').getByRole('button', { name: 'Mapas guardados' }).click();
          await vista.getByRole('button', { name: new RegExp(fixtures.mapa.nombre) }).first().click();
          await vista.locator('.toolbar h1', { hasText: fixtures.mapa.nombre }).waitFor();
          if (process.env.E2E_LAYOUT_SHOTS) {
            await vista.screenshot({ path: `${process.env.E2E_LAYOUT_SHOTS}/${modo.replace(' ', '-')}-${width}.png` });
          }
          const medida = await vista.evaluate(() => {
            const header = document.querySelector('.app-header');
            const fuera = [...document.querySelectorAll('.app-header *, .toolbar *')]
              .filter((n) => n.children.length === 0 || n.matches('button, .chip, .segmented'))
              .filter((n) => n.getClientRects().length)
              .map((n) => [n.textContent.trim() || n.className, n.getBoundingClientRect()])
              .filter(([, r]) => r.left < -0.5 || r.right > window.innerWidth + 0.5)
              .map(([nombre, r]) => `${nombre} (${Math.round(r.left)}–${Math.round(r.right)})`);
            return {
              texto: header.innerText,
              alto: header.getBoundingClientRect().height,
              desborde: header.scrollHeight - header.clientHeight,
              ancho: document.documentElement.scrollWidth,
              fuera,
              botonesNav: [...header.querySelectorAll('.nav-item')].map((b) => b.getBoundingClientRect().width > 0),
            };
          });
          assert.doesNotMatch(medida.texto, /\b(false|true|null|undefined)\b/, `stray text in the header: ${medida.texto}`);
          assert.deepEqual(medida.fuera, [], 'controls cut off at the viewport edge');
          assert.ok(medida.ancho <= width, `page is ${medida.ancho}px wide`);
          assert.ok(medida.desborde <= 0, `header content spills ${medida.desborde}px below it`);
          assert.deepEqual(medida.botonesNav, [true, true, true]);
          if (width >= 1024) assert.equal(Math.round(medida.alto), 52, 'desktop header should stay one 52px row');
        } finally {
          await vista.close();
        }
      });
    }
  }
} finally {
  await browser.close();
  await cleanup();
}

console.log(checks.join('\n'));
console.log(errors.length ? '\nCONSOLE ERRORS:\n' + errors.join('\n') : '\nno console errors');
const failed = checks.filter(c => c.includes('FAIL')).length;
console.log(`\n${checks.length - failed}/${checks.length} checks passed`);
process.exit(failed || errors.length ? 1 : 0);

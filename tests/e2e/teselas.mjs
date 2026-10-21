/* Basemap tile retries (#93) in a real browser.
 *
 *   cd tests/e2e && npm ci && node teselas.mjs
 *
 * Self-contained like contornos.mjs: serves the repository root on a local
 * port, opens contornos.html (the REAL createMapCanvas with the vendored
 * Leaflet) and switches it to an Esri basemap. Every tile request is
 * intercepted and answered here with a plain grey PNG, a 503 or nothing, so
 * no tile is downloaded from Esri or OpenStreetMap.
 *
 *   CHROMIUM=/path/to/chrome   use that binary instead of the "chrome" channel
 */

import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import zlib from 'node:zlib';
import { opcionesNavegador, servir } from './servidor-estatico.mjs';

/* A 256 px grey PNG, built here so the check needs no image file. */
function pngGris() {
  const lado = 256;
  const fila = Buffer.concat([Buffer.from([0]), Buffer.alloc(lado * 3, 200)]);
  const tabla = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (datos) => {
    let c = 0xffffffff;
    for (const b of datos) c = tabla[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const bloque = (tipo, datos) => {
    const cuerpo = Buffer.concat([Buffer.from(tipo), datos]);
    const largo = Buffer.alloc(4); largo.writeUInt32BE(datos.length);
    const suma = Buffer.alloc(4); suma.writeUInt32BE(crc(cuerpo));
    return Buffer.concat([largo, cuerpo, suma]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(lado, 0); ihdr.writeUInt32BE(lado, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), bloque('IHDR', ihdr),
    bloque('IDAT', zlib.deflateSync(Buffer.concat(Array(lado).fill(fila)))),
    bloque('IEND', Buffer.alloc(0)),
  ]);
}
const GRIS = pngGris();

const servidor = await servir();
const browser = await chromium.launch(opcionesNavegador());
const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
const sinConsulta = (url) => url.replace(/\?.*/, '');

/* Open the harness on Claro. `politica(url, intento)` answers each tile request
 * with 'ok', 'falla' (503) or 'pendiente' (never answered). */
async function abrir(politica) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 640 } });
  const peticiones = [];
  const intentos = new Map();
  await page.route(/arcgisonline\.com|openstreetmap\.org/, (route) => {
    const url = route.request().url();
    const n = (intentos.get(sinConsulta(url)) ?? 0) + 1;
    intentos.set(sinConsulta(url), n);
    peticiones.push(url);
    const accion = politica(url, n);
    if (accion === 'pendiente') return undefined;
    if (accion === 'falla') return route.fulfill({ status: 503, body: '' });
    return route.fulfill({ status: 200, contentType: 'image/png', body: GRIS });
  });
  await page.goto(`${servidor.url}/tests/e2e/contornos.html`);
  await page.waitForFunction(() => document.title === 'listo');
  await page.evaluate(() => __harness.canvas.setBasemap('claro'));
  return { page, peticiones };
}

/* The tiles the visible zoom level needs, per layer, with what was drawn. */
function teselasActuales(page) {
  return page.evaluate(() => {
    const capas = [];
    __harness.canvas.map.eachLayer((l) => { if (l instanceof L.TileLayer) capas.push(l); });
    return capas.flatMap((l) => Object.values(l._tiles).filter((t) => t.current).map((t) => ({
      clave: `${t.coords.z}/${t.coords.y}/${t.coords.x}`,
      src: t.el.src.replace(/^.*\/tile\//, ''),
      visible: t.el.classList.contains('leaflet-tile-loaded')
        && getComputedStyle(t.el).visibility !== 'hidden',
      ancho: t.el.naturalWidth,
    })));
  });
}

function alejar(page, niveles) {
  return page.evaluate((n) => new Promise((ok) => {
    const mapa = __harness.canvas.map;
    mapa.once('zoomend', ok);
    mapa.setZoom(mapa.getZoom() - n);
  }), niveles);
}

let fallos = 0;
async function paso(nombre, cuerpo) {
  try {
    await cuerpo();
    console.log(`  ok  ${nombre}`);
  } catch (error) {
    fallos += 1;
    console.log(`  FALLA  ${nombre}\n        ${String(error.message ?? error).split('\n').slice(0, 6).join(' ')}`);
  }
}

await paso('sin fallos: cada tesela visible con su propia URL al alejar', async () => {
  const { page, peticiones } = await abrir(() => 'ok');
  await espera(600);
  await alejar(page, 4);
  await espera(600);
  const teselas = await teselasActuales(page);
  assert.ok(teselas.length > 0);
  assert.deepEqual(teselas.filter((t) => !t.visible || t.src !== t.clave), []);
  assert.equal(peticiones.filter((u) => u.includes('reintento')).length, 0);
  await page.close();
});

await paso('un fallo pasajero se reintenta con la misma URL y se dibuja', async () => {
  const { page } = await abrir((url, n) => (n === 1 ? 'falla' : 'ok'));
  await espera(400);
  assert.ok((await teselasActuales(page)).every((t) => !t.visible), 'aún no deberían verse');
  await espera(1500);
  const teselas = await teselasActuales(page);
  assert.ok(teselas.length > 0);
  assert.deepEqual(
    teselas.filter((t) => !t.visible || t.ancho !== 256 || t.src !== `${t.clave}?reintento=1`), []);
  await page.close();
});

await paso('un fallo persistente se pide cuatro veces y se deja', async () => {
  const { page, peticiones } = await abrir(() => 'falla');
  await espera(7000);
  const porTesela = new Map();
  for (const u of peticiones) porTesela.set(sinConsulta(u), (porTesela.get(sinConsulta(u)) ?? 0) + 1);
  assert.deepEqual([...new Set(porTesela.values())], [4]);
  await page.close();
});

/* The defect behind this check: the retry asked layer.getTileUrl(coords),
 * which takes the zoom the map shows WHEN THE TIMER FIRES, not the tile's own.
 * Zooming out during the wait sent the old x/y with the new zoom: a different
 * place on the map or, a few levels out, a tile that does not exist. */
await paso('alejar con reintentos pendientes no pide teselas que nadie pidió', async () => {
  for (const niveles of [1, 3]) {
    const { page, peticiones } = await abrir((url, n) => (n === 1 ? 'falla' : 'ok'));
    await espera(300);
    await alejar(page, niveles);
    await espera(4500);
    const pedidas = new Set(peticiones.filter((u) => !u.includes('reintento')).map(sinConsulta));
    const ajenas = peticiones.filter((u) => u.includes('reintento') && !pedidas.has(sinConsulta(u)));
    assert.deepEqual(ajenas.map((u) => u.replace(/^.*\/services\//, '')), [],
                     `alejando ${niveles} nivel(es)`);
    const teselas = await teselasActuales(page);
    assert.deepEqual(teselas.filter((t) => !t.visible || !t.src.startsWith(t.clave)), []);
    await page.close();
  }
});

await paso('cambiar de fondo o salir detiene los reintentos del fondo anterior', async () => {
  for (const salida of ['calles', 'salir']) {
    const { page, peticiones } = await abrir((url, n) => (n === 1 ? 'falla' : 'ok'));
    await espera(300);
    const antes = peticiones.length;
    await page.evaluate((s) => (s === 'salir'
      ? __harness.canvas.map.remove()
      : __harness.canvas.setBasemap(s)), salida);
    await espera(4000);
    const tarde = peticiones.slice(antes).filter((u) => u.includes('arcgisonline'));
    assert.deepEqual(tarde, [], salida);
    await page.close();
  }
});

/* Not a defect claim: a request that never answers fires no tileerror, so it
 * is not retried and its tile stays blank until Leaflet drops it. Recorded so
 * a change to that behaviour is noticed, not to assert it is right. */
await paso('una petición que nunca responde no se reintenta (observación)', async () => {
  const { page, peticiones } = await abrir((url) => (/\/\d*[02468]$/.test(url) ? 'pendiente' : 'ok'));
  await espera(4000);
  const teselas = await teselasActuales(page);
  console.log(`        ${teselas.filter((t) => !t.visible).length} de ${teselas.length} teselas sin`
              + ' dibujar tras 4 s; reintentos: '
              + `${peticiones.filter((u) => u.includes('reintento')).length}`);
  await page.close();
});

await browser.close();
servidor.cerrar();
if (fallos) {
  console.log(`\n${fallos} comprobación(es) fallaron`);
  process.exit(1);
}
console.log('\nteselas: todo bien');

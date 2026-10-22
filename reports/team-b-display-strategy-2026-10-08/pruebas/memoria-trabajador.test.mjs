/* F3 correction checks (supervisory review of PR #16): the worker's copies
 * of prepared bodies are bounded and coordinated with the main cache.
 *
 *   node --test reports/team-b-display-strategy-2026-10-08/pruebas/memoria-trabajador.test.mjs
 *
 * The client (prototipo/raster.js) talks to the REAL worker message handler
 * (prototipo/trabajador-raster.js, crearManejador) through a fake Worker that
 * copies every message with structuredClone and delivers it in a later task,
 * as postMessage does. The fake also counts the bytes of body copies still
 * queued, so "worker memory" here is retained + queued, measured, not assumed.
 * Rasterization is replaced by fake bitmaps (no OffscreenCanvas in Node);
 * the browser run is memoria-trabajador.mjs.
 */

import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';

const aqui = path.dirname(new URL(import.meta.url).pathname);
const importar = (f) => import(pathToFileURL(path.join(aqui, '..', 'prototipo', f)));
const { crearClienteRaster, PRESUPUESTO_TRABAJADOR_BYTES } = await importar('raster.js');
const { crearManejador, bytesCopia } = await importar('trabajador-raster.js');
const { crearCache, PRESUPUESTO_CACHE_BYTES } = await importar('planificador.js');
const { bytesDe } = await importar('preparar.js');

const tarea = () => new Promise((ok) => setImmediate(ok));
async function drenar(n = 20) { for (let i = 0; i < n; i += 1) await tarea(); }

function trabajadorFalso() {
  const t = { onmessage: null, terminado: false, bytesEnCola: 0, rasters: 0, mensajes: [] };
  const manejar = crearManejador({
    enviar: (m) => setImmediate(() => { if (!t.terminado) t.onmessage?.({ data: m }); }),
    programar: (fn) => setImmediate(() => { if (!t.terminado) fn(); }),
    raster: (c, d) => { t.rasters += 1; return d.estilos.map(() => ({ width: d.ancho, height: d.alto, close() {} })); },
  });
  t.manejar = manejar;
  t.postMessage = (m) => {
    const copia = structuredClone(m);                 // what postMessage copies
    const b = m.tipo === 'cuerpo' ? bytesCopia(copia) : 0;
    t.bytesEnCola += b;
    t.mensajes.push(m.tipo);
    setImmediate(() => { t.bytesEnCola -= b; if (!t.terminado) manejar(copia); });
  };
  t.terminate = () => { t.terminado = true; };
  t.retenidos = () => { let b = 0; for (const c of manejar.cuerpos.values()) b += bytesCopia(c); return b; };
  return t;
}

/** A prepared body with n positions (one ring), as preparar.js would make it. */
function sintetico(n) {
  return { estado: 'cargado', x: new Float64Array(n), y: new Float64Array(n),
           inicioAnillo: new Int32Array([0, n]), inicioParte: new Int32Array([0, 1]),
           cajasParte: new Float64Array(4), partes: 1 };
}
const AREA = { escala: 1, x0: 0, y0: 0, ancho: 100, alto: 50, dpr: 1, estilos: [{}, {}] };

function montar(presupuesto = PRESUPUESTO_TRABAJADOR_BYTES) {
  const t = trabajadorFalso();
  const cliente = crearClienteRaster({ presupuesto, crearTrabajador: () => t });
  const cache = crearCache(PRESUPUESTO_CACHE_BYTES, { alExpulsar: (id) => cliente.expulsado(id) });
  // Invariant checked after every step: what the worker holds plus what is
  // still queued never exceeds the budget, and the client's count covers it.
  const peor = { trabajador: 0 };
  const comprobar = () => {
    const real = t.retenidos() + t.bytesEnCola;
    peor.trabajador = Math.max(peor.trabajador, real);
    assert.ok(real <= presupuesto, `worker-side ${real} > budget ${presupuesto}`);
    assert.ok(cliente.bytesTrabajador >= real, `client counts ${cliente.bytesTrabajador} < real ${real}`);
  };
  return { t, cliente, cache, comprobar, peor };
}

/** One map visit: prepare, cache, pin for a layer, raster once, leave. */
async function visita({ cliente, cache, comprobar }, id, p) {
  cache.guardar({ id, bbox: [0, 0, 1, 1] }, p);
  comprobar();
  const estado = cliente.asegurar(id, p, { enCache: cache.contiene(id) });
  comprobar();
  let respuesta = null;
  if (estado !== 'rechazado') cliente.pedir({ id, ...AREA }, (r) => { respuesta = r; });
  for (let i = 0; i < 50 && !respuesta && estado !== 'rechazado'; i += 1) { await tarea(); comprobar(); }
  if (respuesta) cliente.soltarBitmaps(respuesta.bitmaps);
  cliente.liberar(id);
  comprobar();
  return { estado, respuesta };
}

test('45 visits of 60,000 positions: worker and main cache both bounded', async () => {
  const m = montar();
  const ids = [];
  for (let i = 0; i < 45; i += 1) {
    const { estado, respuesta } = await visita(m, `cuerpo-${i}`, sintetico(60_000));
    assert.notEqual(estado, 'rechazado');
    assert.equal(respuesta.bitmaps.length, 2, `visit ${i} drew`);
    assert.ok(!respuesta.sinCuerpo);
    ids.push(`cuerpo-${i}`);
  }
  await drenar();
  const stats = await m.cliente.estadisticas();
  const unCuerpo = bytesDe(sintetico(60_000));
  assert.ok(stats.bytes <= PRESUPUESTO_TRABAJADOR_BYTES, `worker ${stats.bytes}`);
  assert.ok(m.cache.bytes <= PRESUPUESTO_CACHE_BYTES);
  // Worker ⊆ main cache (nothing is pinned after the visits).
  for (const id of m.t.manejar.cuerpos.keys()) assert.ok(m.cache.contiene(id), `${id} only in worker`);
  assert.equal(stats.entradas, m.cache.tamano);
  assert.equal(stats.bytes, m.cache.bytes);
  assert.equal(m.cliente.bytesTrabajador, stats.bytes);   // every forget acknowledged
  assert.equal(m.cliente.metricas.bitmapsBytes, 0);        // every bitmap released
  console.log(`  45 visits: main ${m.cache.bytes} B / ${m.cache.tamano}, worker ${stats.bytes} B / ${stats.entradas}, `
              + `total ${m.cache.bytes + stats.bytes} B; worst worker-side incl. queue ${m.peor.trabajador} B; body ${unCuerpo} B`);
});

test('revisit after eviction: the body is sent again and drawn', async () => {
  const m = montar();
  for (let i = 0; i < 45; i += 1) await visita(m, `cuerpo-${i}`, sintetico(60_000));
  await drenar();
  assert.ok(!m.cache.contiene('cuerpo-0'));
  assert.ok(!m.t.manejar.cuerpos.has('cuerpo-0'));
  const enviadas = m.cliente.metricas.copiasEnviadas;
  const { estado, respuesta } = await visita(m, 'cuerpo-0', sintetico(60_000));
  // The worker is full, so the body waits for the eviction's acknowledgement.
  assert.ok(['listo', 'esperando'].includes(estado), estado);
  assert.equal(m.cliente.metricas.copiasEnviadas, enviadas + 1);
  assert.equal(respuesta.bitmaps.length, 2);
  assert.ok(!respuesta.sinCuerpo);
});

test('pinned bodies beyond the budget are refused, never posted', async () => {
  // The supervisor's probe pattern: 45 bodies pinned and never released.
  const m = montar();
  const estados = [];
  for (let i = 0; i < 45; i += 1) {
    const id = `fijo-${i}`;
    const p = sintetico(60_000);
    m.cache.guardar({ id, bbox: [0, 0, 1, 1] }, p);
    estados.push(m.cliente.asegurar(id, p, { enCache: m.cache.contiene(id) }));
    m.comprobar();
  }
  await drenar();
  const aceptados = estados.filter((e) => e !== 'rechazado').length;
  const unCuerpo = bytesDe(sintetico(60_000));
  assert.equal(aceptados, Math.floor(PRESUPUESTO_TRABAJADOR_BYTES / unCuerpo));
  assert.equal(m.cliente.metricas.rechazados, 45 - aceptados);
  assert.equal(m.cliente.metricas.copiasEnviadas, aceptados);
  const stats = await m.cliente.estadisticas();
  assert.ok(stats.bytes <= PRESUPUESTO_TRABAJADOR_BYTES);
  assert.equal(stats.entradas, aceptados);
  // Releasing one pin lets a refused body in (after the forget is acknowledged).
  m.cliente.liberar('fijo-0');
  m.cache.guardar({ id: 'otro', bbox: [0, 0, 1, 1] }, sintetico(60_000));  // evicts fijo-0 from main
  m.comprobar();
  await drenar();
  assert.ok(!m.t.manejar.cuerpos.has('fijo-0'));
  assert.notEqual(m.cliente.asegurar('fijo-44', sintetico(60_000)), 'rechazado');
});

test('a burst without waiting: queued copies stay inside the budget', async () => {
  const m = montar(8 * 1024 * 1024);       // small budget: ~8 bodies
  for (let i = 0; i < 45; i += 1) {
    const id = `rafaga-${i}`;
    const p = sintetico(60_000);
    m.cache.guardar({ id, bbox: [0, 0, 1, 1] }, p);
    const e = m.cliente.asegurar(id, p, { enCache: m.cache.contiene(id) });
    assert.notEqual(e, 'rechazado');
    m.cliente.pedir({ id, ...AREA }, (r) => m.cliente.soltarBitmaps(r.bitmaps));
    m.cliente.liberar(id);
    m.comprobar();
  }
  assert.ok(m.cliente.metricas.esperas > 0, 'some bodies waited for acknowledgements');
  for (let i = 0; i < 400 && m.cliente.enVuelo; i += 1) { await tarea(); m.comprobar(); }
  await drenar();
  assert.equal(m.cliente.enVuelo, 0);
  assert.ok(m.peor.trabajador <= 8 * 1024 * 1024);
  console.log(`  burst: worst worker-side incl. queue ${m.peor.trabajador} B of ${8 * 1024 * 1024} B budget; `
              + `${m.cliente.metricas.esperas} bodies waited`);
});

test('a discarded raster request that has not started is cancelled, not run', async () => {
  const m = montar();
  const p = sintetico(1000);
  m.cliente.asegurar('a', p);
  const avisos = [];
  const n1 = m.cliente.pedir({ id: 'a', ...AREA }, (r) => avisos.push(r.pedido));
  const n2 = m.cliente.pedir({ id: 'a', ...AREA }, (r) => avisos.push(r.pedido));
  m.cliente.descartar(n1);
  await drenar();
  assert.deepEqual(avisos, [n2]);
  assert.equal(m.t.rasters, 1, 'only the wanted request was rasterized');
  assert.equal(m.cliente.metricas.cancelados, 1);
  assert.equal(m.cliente.enVuelo, 0);
});

test('a request for a body the worker lacks is answered, not left pending', async () => {
  const t = trabajadorFalso();
  const cliente = crearClienteRaster({ crearTrabajador: () => t });
  let r = null;
  cliente.pedir({ id: 'nunca-enviado', ...AREA }, (x) => { r = x; });
  await drenar();
  assert.ok(r?.sinCuerpo);
  assert.equal(cliente.enVuelo, 0);
});

test('reset is acknowledged; teardown terminates', async () => {
  const m = montar();
  for (let i = 0; i < 5; i += 1) await visita(m, `r-${i}`, sintetico(60_000));
  const confirmado = m.cliente.olvidarTodo();
  assert.ok(m.cliente.bytesTrabajador > 0, 'not yet acknowledged: still counted');
  assert.equal(await confirmado, true);
  assert.equal(m.cliente.bytesTrabajador, 0);
  assert.deepEqual(await m.cliente.estadisticas(), { tipo: 'estadisticas', entradas: 0, bytes: 0, pendientes: 0 });
  m.cliente.cerrar();
  assert.equal(m.t.terminado, true);
  assert.equal(m.cliente.asegurar('x', sintetico(10)), 'rechazado');
  assert.equal(await m.cliente.estadisticas(), null);
});

test('cache reports every eviction', () => {
  const expulsados = [];
  const p = sintetico(1000);
  const cache = crearCache(bytesDe(p) * 2, { alExpulsar: (id) => expulsados.push(id) });
  for (const id of ['a', 'b', 'c', 'd']) cache.guardar({ id, bbox: [0, 0, 1, 1] }, sintetico(1000));
  assert.deepEqual(expulsados, ['a', 'b']);
  assert.ok(cache.contiene('c') && cache.contiene('d'));
});

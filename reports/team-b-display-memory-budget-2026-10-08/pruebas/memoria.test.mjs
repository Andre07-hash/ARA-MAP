/* Node checks of the E5 memory admission and lifecycles (not application tests).
 *
 *   node --test reports/team-b-display-memory-budget-2026-10-08/pruebas/
 *
 * The worker client runs against the REAL worker message handler
 * (prototipo/trabajador.js) behind a fake Worker that copies messages with
 * structuredClone and delivers them in later tasks; canvases are fakes with
 * real dimensions. The browser runs are memoria.mjs and comprobaciones.mjs.
 */

import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';

const aqui = path.dirname(new URL(import.meta.url).pathname);
const imp = (f) => import(pathToFileURL(path.join(aqui, '..', 'prototipo', f)));
const { crearPresupuesto } = await imp('presupuesto.js');
const { crearRegistro } = await imp('registro.js');
const { crearPlanificador } = await imp('planificador.js');
const { crearCliente } = await imp('cliente.js');
const { crearManejador, bytesCopia } = await imp('trabajador.js');
const { bytesDe } = await imp('preparar.js');

const tarea = () => new Promise((ok) => setImmediate(ok));
/** Wait (keeping Node's loop alive) until `f()` returns something. */
async function hasta(f, maxTareas = 5000) {
  for (let i = 0; i < maxTareas; i += 1) { const v = f(); if (v) return v; await tarea(); }
  return f();
}
async function drenar(n = 30) { for (let i = 0; i < n; i += 1) await tarea(); }
const MiB = 1024 * 1024;

/** A prepared body of n positions in one ring (what preparar.js makes). */
function preparado(n) {
  return { estado: 'cargado', x: new Float64Array(n), y: new Float64Array(n), inicioAnillo: new Int32Array([0, n]),
           inicioParte: new Int32Array([0, 1]), cajasParte: new Float64Array(4), partes: 1 };
}

/** A valid body (one closed ring of n positions) and its descriptor. */
function cuerpoValido(id, n) {
  const anillo = Array.from({ length: n - 1 }, (_, k) => [-100.4 + 0.01 * Math.cos(2 * Math.PI * k / (n - 1)),
                                                         20.6 + 0.01 * Math.sin(2 * Math.PI * k / (n - 1))]);
  anillo.push([...anillo[0]]);
  let w = Infinity; let s = Infinity; let e = -Infinity; let nn = -Infinity;
  for (const [x, y] of anillo) { w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); nn = Math.max(nn, y); }
  const bbox = [w, s, e, nn];
  const punto = { type: 'Point', coordinates: [-100.4, 20.6] };
  return { descriptor: { id, utilizable: true, bbox, punto_interior: punto },
           cuerpo: { geojson: { type: 'MultiPolygon', coordinates: [[anillo]] }, bbox, punto_interior: punto } };
}

function trabajadorFalso({ simular = null, sinListo = false } = {}) {
  const t = { onmessage: null, onerror: null, onmessageerror: null, terminado: false, bytesEnCola: 0, mensajes: [] };
  t.bitmaps = [];
  const lienzo = (w, h) => ({ width: w, height: h, getContext: () => new Proxy({}, { get: () => () => {} }),
                              transferToImageBitmap: () => {
                                const b = { width: w, height: h, cerrado: false, close() { this.cerrado = true; } };
                                t.bitmaps.push(b);
                                return b;
                              } });
  const manejar = crearManejador({
    enviar: (m) => setImmediate(() => { if (!t.terminado) t.onmessage?.({ data: m }); }),
    programar: (fn) => setImmediate(() => {
      if (t.terminado) return;
      try { fn(); } catch { t.onerror?.({ preventDefault() {} }); }
    }),
    crearLienzo: lienzo,
    simular,
  });
  t.manejar = manejar;
  t.postMessage = (m) => {
    const copia = structuredClone(m);
    const b = m.tipo === 'cuerpo' ? bytesCopia(copia) : 0;
    t.bytesEnCola += b;
    t.mensajes.push(m.tipo);
    setImmediate(() => { t.bytesEnCola -= b; if (!t.terminado) manejar(copia); });
  };
  t.terminate = () => { t.terminado = true; };
  t.retenidos = () => { let b = 0; for (const c of manejar.cuerpos.values()) b += bytesCopia(c); return b; };
  if (!sinListo) setImmediate(() => t.onmessage?.({ data: { tipo: 'listo', offscreen: simular !== 'sinOffscreen' } }));
  return t;
}

function cliente(presupuesto, opciones = {}) {
  const t = trabajadorFalso(opciones);
  const fallos = [];
  const c = crearCliente({ presupuesto, dueno: 'prueba', crearTrabajador: () => t, plazoMs: opciones.plazoMs ?? 5000,
                           alFallar: (m) => fallos.push(m), ...(opciones.simular === 'constructor' ? { simular: 'constructor' } : {}) });
  return { c, t, fallos };
}

// ---------------------------------------------------------------- budget ledger

test('budget: reserve before allocation, refuse beyond the total, peak and categories', () => {
  const p = crearPresupuesto(10);
  const a = p.reservar('preparado', 6);
  assert.ok(a);
  assert.equal(p.reservar('raster', 5), null);
  assert.equal(p.rechazos, 1);
  const b = p.reservar('copia', 4);
  assert.equal(p.usados, 10);
  p.liberar(a); p.liberar(a);                       // idempotent
  assert.equal(p.usados, 4);
  assert.equal(p.pico, 10);
  assert.deepEqual(p.porCategoria(), { preparado: 0, copia: 4, raster: 0, capa: 0 });
  p.liberar(b);
  assert.equal(p.vivas().length, 0);
});

test('budget: relievers run before refusing; release notifications are coalesced', async () => {
  const p = crearPresupuesto(10);
  const viejas = [p.reservar('preparado', 4), p.reservar('preparado', 4)];
  let avisos = 0;
  p.alLiberar(() => { avisos += 1; });
  p.registrarAliviador(() => p.liberar(viejas.shift()));
  assert.ok(p.reservar('raster', 5));
  assert.equal(p.usados, 9);
  await tarea();
  assert.equal(avisos, 1);
});

// ---------------------------------------------------------------- registry

test('registry: one reservation per body, pinned bodies are never evicted and stay counted', () => {
  const p = crearPresupuesto(3 * bytesDe(preparado(1000)));
  const reg = crearRegistro(p, 'm');
  const una = bytesDe(preparado(1000));
  for (const id of ['a', 'b', 'c']) {
    const r = reg.reservar(una);
    reg.guardar({ id, bbox: [0, 0, 1, 1] }, preparado(1000), r);
  }
  reg.fijar('a');                                  // a layer uses 'a'
  assert.equal(p.usados, 3 * una);
  // Room for a fourth: the reliever drops the least recently used UNPINNED body ('b').
  const r = reg.reservar(una);
  assert.ok(r);
  assert.equal(reg.obtener({ id: 'a', bbox: [0, 0, 1, 1] }) !== null, true);
  assert.equal(reg.obtener({ id: 'b', bbox: [0, 0, 1, 1] }), null);
  assert.equal(reg.metricas.expulsados, 1);
  p.liberar(r);
  // Reset keeps the pinned body (its layer still holds it) and counts it.
  reg.vaciar();
  assert.equal(reg.tamano, 1);
  assert.equal(p.usados, una);
  assert.equal(reg.bytesReales(), reg.bytesReservados());
  reg.soltar('a');                                 // layer gone, not cached: released
  assert.equal(p.usados, 0);
});

// ---------------------------------------------------------------- planner

test('planner: exact reservation before allocation, cap on jobs, release on cancel', async () => {
  const p = crearPresupuesto(64 * MiB);
  const reg = crearRegistro(p, 'm');
  const plan = crearPlanificador({ registro: reg, presupuesto: p, alPreparar: (d, r, res) => reg.guardar(d, r, res) });
  const casos = [1, 2, 3, 4].map((i) => cuerpoValido(`g${i}`, 50_000));
  const recibidos = [];
  let maxEnMemoria = 0;
  for (const { descriptor, cuerpo } of casos) plan.pedir(descriptor, new Map([[descriptor.id, cuerpo]]), (r) => recibidos.push(r));
  while (recibidos.length < 4) { maxEnMemoria = Math.max(maxEnMemoria, plan.enMemoria); await tarea(); }
  assert.ok(maxEnMemoria <= 2, `at most 2 preparations hold memory (${maxEnMemoria})`);
  assert.ok(recibidos.every((r) => r.estado === 'cargado'));
  assert.equal(p.porCategoria().preparado, recibidos.reduce((a, r) => a + bytesDe(r), 0));
  assert.equal(reg.bytesReales(), reg.bytesReservados());
  plan.detener();
  // Cancelled mid-preparation (slices stepped by hand): its reservation goes.
  // R4: the slice deadline runs on an injected clock that advances one unit
  // per reading, so a slice reads a fixed number of positions (a few thousand)
  // whatever the machine's speed: one slice can never finish 90,000.
  const pasos = [];
  let lecturas = 0;
  const plan2 = crearPlanificador({ registro: reg, presupuesto: p, alPreparar: (d, r, res) => reg.guardar(d, r, res),
                                    ceder: (fn) => pasos.push(fn), ahora: () => { lecturas += 1; return lecturas; } });
  const { descriptor, cuerpo } = cuerpoValido('g9', 90_000);
  plan2.pedir(descriptor, new Map([[descriptor.id, cuerpo]]), () => assert.fail('cancelled job reported'));
  pasos.shift()();                                 // one slice: structure read, arrays reserved and allocated
  assert.equal(plan2.pendientes, 1, 'still mid-work after one slice');
  assert.equal(pasos.length, 1, 'another slice is scheduled');
  assert.equal(plan2.bytesReservados, bytesDe(preparado(90_000)));
  plan2.conservarSolo(new Set());
  assert.equal(plan2.bytesReservados, 0);
  while (pasos.length) pasos.shift()();
  assert.equal(p.porCategoria().preparado, recibidos.reduce((a, r) => a + bytesDe(r), 0));
});

test('planner: refused memory is "sin_memoria" with nothing allocated; waits while releases are pending', async () => {
  const p = crearPresupuesto(100_000);              // smaller than one 50,000-position body (800 KB)
  const reg = crearRegistro(p, 'm');
  const plan = crearPlanificador({ registro: reg, presupuesto: p, alPreparar: (d, r, res) => reg.guardar(d, r, res) });
  const { descriptor, cuerpo } = cuerpoValido('grande', 50_000);
  let r = null;
  plan.pedir(descriptor, new Map([[descriptor.id, cuerpo]]), (x) => { r = x; });
  await hasta(() => r);
  assert.equal(r.estado, 'sin_memoria');
  assert.equal(p.usados, 0);
  // With a release announced but not yet acknowledged, the job waits, then proceeds.
  const p2 = crearPresupuesto(bytesDe(preparado(10_000)) + 1000);
  const reg2 = crearRegistro(p2, 'm');
  const plan2 = crearPlanificador({ registro: reg2, presupuesto: p2, alPreparar: (d, x, res) => reg2.guardar(d, x, res) });
  const ocupada = p2.reservar('copia', 2000);
  p2.anunciarPorConfirmar(2000);
  const c2 = cuerpoValido('espera', 10_000);
  let hecho = null;
  plan2.pedir(c2.descriptor, new Map([[c2.descriptor.id, c2.cuerpo]]), (x) => { hecho = x; });
  await drenar(10);
  assert.equal(hecho, null);
  assert.ok(plan2.metricas.esperas > 0);
  p2.anunciarPorConfirmar(-2000); p2.liberar(ocupada);
  await hasta(() => hecho);
  assert.equal(hecho?.estado, 'cargado');
  plan.detener(); plan2.detener();
});

// ---------------------------------------------------------------- worker client

test('client: copies reserved before posting and counted until the worker acknowledges', async () => {
  const una = bytesDe(preparado(10_000));
  const p = crearPresupuesto(3 * una);
  const { c, t } = cliente(p);
  await drenar(2);
  for (const id of ['a', 'b', 'c']) assert.equal(c.asegurar(id, preparado(10_000)), 'listo');
  assert.ok(t.bytesEnCola + t.retenidos() <= p.porCategoria().copia);
  assert.equal(c.asegurar('d', preparado(10_000)), 'esperar');   // LRU 'a' forgotten, ack pending
  assert.equal(p.pendienteDeLiberar, una);
  assert.equal(p.porCategoria().copia, 3 * una);                // still counted
  await drenar();
  assert.equal(p.porCategoria().copia, 2 * una);
  assert.equal(p.pendienteDeLiberar, 0);
  assert.equal(c.asegurar('d', preparado(10_000)), 'listo');
  await drenar();
  assert.equal(t.retenidos(), p.porCategoria().copia);
  assert.ok(!t.manejar.cuerpos.has('a'));
  // Revisit after eviction: posted again.
  const antes = c.metricas.copiasEnviadas;
  assert.equal(c.asegurar('a', preparado(10_000)), 'esperar');
  await drenar();
  assert.equal(c.asegurar('a', preparado(10_000)), 'listo');
  assert.equal(c.metricas.copiasEnviadas, antes + 1);
  c.cerrar();
  assert.equal(p.usados, 0);
});

test('client: pinned copies are not evicted; a refused post posts nothing', async () => {
  const una = bytesDe(preparado(10_000));
  const p = crearPresupuesto(2 * una);
  const { c, t } = cliente(p);
  await drenar(2);
  c.asegurar('a', preparado(10_000)); c.asegurar('b', preparado(10_000));
  c.fijar(['a', 'b']);
  const enviados = t.mensajes.filter((m) => m === 'cuerpo').length;
  assert.equal(c.asegurar('c', preparado(10_000)), 'sin_memoria');
  assert.equal(t.mensajes.filter((m) => m === 'cuerpo').length, enviados);
  assert.equal(p.pendienteDeLiberar, 0);
  c.soltar(['a']);
  assert.equal(c.asegurar('c', preparado(10_000)), 'esperar');  // 'a' forgotten now
  c.cerrar();
});

test('registry eviction while the worker copy is posted, then while its forget awaits acknowledgement', async () => {
  const u = bytesDe(preparado(10_000));
  const p = crearPresupuesto(2 * u);
  const reg = crearRegistro(p, 'm');               // reliever registered first: main cache before worker copies
  const { c, t } = cliente(p);
  await drenar(2);
  const d = (id) => ({ id, bbox: [0, 0, 1, 1] });
  reg.guardar(d('x'), preparado(10_000), reg.reservar(u));
  assert.equal(c.asegurar('x', preparado(10_000)), 'listo');
  // 1. A copy of 'y' needs room: the cached main body 'x' is evicted while x's worker copy stays posted.
  assert.equal(c.asegurar('y', preparado(10_000)), 'listo');
  assert.equal(reg.obtener(d('x')), null);
  await drenar();
  assert.ok(t.manejar.cuerpos.has('x'));
  // 2. Revisiting 'x' on the main thread: the unpinned worker copy 'x' is forgotten, and its
  //    bytes stay counted until the acknowledgement, so the preparation must wait.
  assert.equal(reg.reservar(u), null);
  assert.equal(p.pendienteDeLiberar, u);
  assert.equal(p.porCategoria().copia, 2 * u);
  await drenar();
  const r = reg.reservar(u);
  assert.ok(r, 'room after the acknowledgement');
  reg.guardar(d('x'), preparado(10_000), r);
  reg.fijar('x');
  // 3. The worker needs 'x' again: no stale "already sent" state; it is posted afresh once
  //    the forget of the unpinned copy 'y' is acknowledged. The pinned main body is kept.
  assert.equal(c.asegurar('x', preparado(10_000)), 'esperar');
  await drenar();
  assert.equal(c.asegurar('x', preparado(10_000)), 'listo');
  await drenar();
  assert.deepEqual([...t.manejar.cuerpos.keys()], ['x']);
  assert.deepEqual(p.porCategoria(), { preparado: u, copia: u, raster: 0, capa: 0 });
  assert.equal(reg.bytesReales(), u);
  assert.equal(t.retenidos(), u);
  c.cerrar(); reg.soltar('x'); reg.cerrar();
  assert.equal(p.usados, 0);
});

test('client: a request cancelled before it starts is not run; one cancelled late has its bitmap closed', async () => {
  const p = crearPresupuesto(64 * MiB);
  const { c, t } = cliente(p);
  await drenar(2);
  c.asegurar('a', preparado(1000));
  await drenar();
  const area = { ancho: 100, alto: 50, m: 1, bmin: [0, 0], origen: [0, 0], escala: 1, capas: [{ id: 'a', estilo: {} }] };
  const n1 = c.raster(area, () => assert.fail('cancelled request delivered'));
  c.descartar(n1);
  await drenar();
  assert.equal(t.bitmaps.length, 0, 'never rasterized');
  const n2 = c.raster(area, () => assert.fail('late-cancelled request delivered'));
  await tarea(); await tarea();
  c.descartar(n2);
  await drenar();
  assert.equal(t.bitmaps.length, 1);
  assert.ok(t.bitmaps.every((b) => b.cerrado), 'the late bitmap was closed');
  assert.equal(c.metricas.cancelados, 1);
  assert.equal(c.metricas.descartados, 1);
  assert.equal(c.enVuelo, 0);
  c.asegurar('b', preparado(5000)); c.asegurar('c', preparado(5000));
  const confirmado = c.olvidarTodo();
  assert.ok(p.porCategoria().copia > 0, 'counted until acknowledged');
  assert.equal(await confirmado, true);
  assert.equal(p.porCategoria().copia, 0);
  assert.equal(t.retenidos(), 0);
  c.cerrar();
});

for (const [simular, motivo] of [['error', 'error'], ['silencio', 'sinRespuesta'], ['sinOffscreen', 'sinOffscreen'],
                                 ['constructor', 'constructor']]) {
  test(`client failure "${simular}": explicit reason, worker gone, every reservation released`, async () => {
    const p = crearPresupuesto(64 * MiB);
    const { c, t, fallos } = cliente(p, { simular, plazoMs: 200 });
    await drenar(2);
    if (simular !== 'constructor' && simular !== 'sinOffscreen') {
      assert.equal(c.asegurar('a', preparado(1000)), 'listo');
      let respuesta = null;
      c.raster({ ancho: 10, alto: 10, m: 1, bmin: [0, 0], origen: [0, 0], escala: 1, capas: [{ id: 'a', estilo: {} }] },
               (r) => { respuesta = r; });
      for (let i = 0; i < 400 && !respuesta; i += 1) await new Promise((ok) => setTimeout(ok, 2));
      assert.equal(respuesta?.fallo, motivo);
    }
    assert.equal(c.estado, 'fallido');
    assert.equal(c.motivo, motivo);
    if (simular !== 'constructor') assert.equal(t.terminado, true);
    if (simular !== 'constructor' && simular !== 'sinOffscreen') assert.deepEqual(fallos, [motivo]);
    assert.equal(p.usados, 0);
    assert.equal(c.asegurar('z', preparado(10)), 'fallido');
    c.cerrar();
  });
}

/* The map controller against a minimal fake of Leaflet's Canvas renderer:
 * enough for decidir() (draw order, bounds, container size, pixel origin). */
const { crearControlador } = await imp('e5.js');
function controladorFalso({ presupuesto, capas: n = 2, alEstado, cliente }) {
  const oyentes = [];
  const renderer = {
    _bounds: { min: { x: 0, y: 0 }, max: { x: 100, y: 50 } }, _container: { width: 100, height: 50 }, _layers: {},
    _drawFirst: null, _redraw() {}, _updatePaths() {},
    on(ev, f) { oyentes.push(f); }, off() {},
  };
  const map = { getPixelOrigin: () => ({ x: 0, y: 0 }), getZoom: () => 10, options: { crs: { scale: (z) => 256 * 2 ** z } } };
  class CapaBitmap { constructor() {} addTo() { return this; } bringToBack() {} redraw() {} get _map() { return map; } }
  const ctl = crearControlador({ L: null, map, CapaBitmap, presupuesto, dueno: 'mapa', alEstado,
                                 crearCliente: () => cliente });
  const capas = [];
  let previo = null;
  for (let i = 0; i < n; i += 1) {
    const capa = { _id: `g-${i}`, _renderer: renderer, _map: map, _nVisibles: 1, _carga: { anillos: 5000, posiciones: 50000 },
                   _prep: preparado(10), options: { color: '#123456', weight: 2 } };
    const nodo = { layer: capa, next: null };
    if (previo) previo.next = nodo; else renderer._drawFirst = nodo;
    previo = nodo;
    capas.push(capa);
    ctl.agregar(capa);
  }
  return { ctl, capas };
}
const clienteFalso = () => ({ estado: 'listo', asegurar: () => 'listo', fijar() {}, soltar() {}, raster() { return 1; },
                              descartar() {}, bytesReservados: () => 0, cerrar() {} });

test('controller: a refused raster reports only the final state and does not loop', async () => {
  const p = crearPresupuesto(30_000);
  const otro = p.reservar('raster', 15_000, 'otro mapa');     // another map's image: 100x50x4 = 20,000 B cannot fit now
  assert.ok(otro);
  const informados = [];
  let ctl;
  // As MapCanvas does: a reported state re-applies the outline's (unchanged) style in a microtask.
  // (Capped so that a regression fails the assertions instead of hanging the test run.)
  const alEstado = (capa, estado) => {
    informados.push([capa._id, estado]);
    if (informados.length < 400) queueMicrotask(() => ctl.cambioDeEstilo(capa));
  };
  ({ ctl } = controladorFalso({ presupuesto: p, alEstado, cliente: clienteFalso() }));
  await drenar(50);
  assert.ok(ctl.metricas.decisiones < 10, `${ctl.metricas.decisiones} decisions: the controller keeps re-deciding`);
  assert.deepEqual(informados, [['g-0', 'sin_memoria'], ['g-1', 'sin_memoria']]);   // never a transient "dibujando"
  assert.equal(p.porCategoria().raster, 15_000);              // nothing reserved for the refused image
  // The other map releases its image: one new decision, and the raster is requested.
  const antes = ctl.metricas.decisiones;
  p.liberar(otro);
  await drenar(50);
  assert.ok(ctl.metricas.decisiones - antes <= 3);
  assert.equal(ctl.metricas.rasters, 1);
  assert.equal(p.porCategoria().raster, 20_000);
  assert.deepEqual(informados.slice(2), [['g-0', 'dibujando'], ['g-1', 'dibujando']]);
  ctl.cerrar();
  assert.equal(p.usados, 0);
});

test('budget: relievers free only the remaining shortage, counting releases still awaiting acknowledgement', () => {
  const p = crearPresupuesto(10_000);
  const a = p.reservar('copia', 4_000); const b = p.reservar('copia', 4_000);
  const llamadas = [];
  // First reliever: a worker forget, announced now, acknowledged later.
  p.registrarAliviador((faltan) => { llamadas.push(['uno', faltan]); p.anunciarPorConfirmar(4_000); });
  p.registrarAliviador((faltan) => { llamadas.push(['dos', faltan]); });
  assert.equal(p.reservar('raster', 5_000), null);            // nothing freed yet: refused, caller waits
  assert.deepEqual(llamadas, [['uno', 3_000]]);                // the second reliever was not asked: 4,000 already coming
  llamadas.length = 0;
  assert.equal(p.reservar('raster', 5_000), null);            // still pending: no further eviction
  assert.deepEqual(llamadas, []);
  p.anunciarPorConfirmar(-4_000); p.liberar(a);                 // acknowledged
  assert.ok(p.reservar('raster', 5_000));
  p.liberar(b);
});

test('controller: a refused map retries when held items become evictable, without any release', async () => {
  const p = crearPresupuesto(30_000);
  let fijado = true;
  const otro = p.reservar('copia', 15_000, 'otro mapa');      // the other map's copy, pinned by its request in flight
  p.registrarAliviador(() => { if (!fijado && otro.viva) p.liberar(otro); });
  const { ctl } = controladorFalso({ presupuesto: p, alEstado: () => {}, cliente: clienteFalso() });
  await drenar(30);
  assert.equal(ctl.metricas.rasters, 0);
  assert.deepEqual(ctl.estado().modos.map(([, , e]) => e), ['sin_memoria', 'sin_memoria']);
  fijado = false;                                              // the other request returned: unpinned, nothing released
  p.avisarDisponible();
  await drenar(30);
  assert.equal(ctl.metricas.rasters, 1);
  assert.equal(p.porCategoria().raster, 20_000);
  assert.equal(otro.viva, false);
  ctl.cerrar();
});

test('worker copies follow registry membership: forgotten when the body leaves, deferred while a request pins it', async () => {
  const u = bytesDe(preparado(10_000));
  const p = crearPresupuesto(4 * u);
  const reg = crearRegistro(p, 'm');
  const { c, t } = cliente(p);
  reg.alQuitar((id) => c.expulsado(id));                  // as MapCanvas (e5) wires it
  await drenar(2);
  const d = (id) => ({ id, bbox: [0, 0, 1, 1] });
  reg.guardar(d('x'), preparado(10_000), reg.reservar(u));
  reg.guardar(d('y'), preparado(10_000), reg.reservar(u));
  assert.equal(c.asegurar('x', preparado(10_000)), 'listo');
  assert.equal(c.asegurar('y', preparado(10_000)), 'listo');
  await drenar();
  assert.equal(p.usados, 4 * u);
  // 1. 'x' is evicted from the main cache to make room: its worker copy is forgotten too.
  assert.ok(reg.reservar(u));
  assert.equal(reg.obtener(d('x')), null);
  assert.deepEqual(c.ids(), ['y']);
  await drenar();
  assert.deepEqual([...t.manejar.cuerpos.keys()], ['y']);
  // 2. 'y' is pinned by a request in flight when its body leaves: forgotten only when unpinned.
  c.fijar(['y']);
  reg.vaciar();
  assert.equal(reg.tamano, 0);
  await drenar();
  assert.ok(t.manejar.cuerpos.has('y'), 'a pinned copy stays while its request needs it');
  c.soltar(['y']);
  await drenar();
  assert.equal(t.manejar.cuerpos.size, 0);
  assert.equal(p.porCategoria().copia, 0);
  // 3. Re-admitted before unpinning: the copy is wanted again and is kept.
  reg.guardar(d('z'), preparado(10_000), reg.reservar(u));
  assert.equal(c.asegurar('z', preparado(10_000)), 'listo');
  c.fijar(['z']); c.expulsado('z'); assert.equal(c.asegurar('z', preparado(10_000)), 'listo'); c.soltar(['z']);
  await drenar();
  assert.ok(t.manejar.cuerpos.has('z'));
  c.cerrar(); reg.cerrar();
});

// ------------------------------------------------- R1-R3 corrections (2026-10-09)

import v8 from 'node:v8';
import vm from 'node:vm';

/* A minimal Leaflet class system, enough to construct the real CapaContorno /
 * CapaContornoE5 classes (the supervisor's probe uses the same double). */
function leafletMinimo() {
  function Base() {}
  Base.extend = function extend(metodos) {
    const Padre = this;
    function Hija(...args) { this.initialize?.(...args); }
    Hija.prototype = Object.assign(Object.create(Padre.prototype), metodos);
    Hija.extend = Padre.extend;
    return Hija;
  };
  return { Polygon: Base, Path: Base, Util: { setOptions: (o, op) => { o.options = { ...o.options, ...op }; } } };
}
const { crearClases } = await import(pathToFileURL(path.join(aqui, '..', '..', 'team-b-display-strategy-2026-10-08',
                                                             'prototipo', 'capa.js')));
const { crearClasesE5, bytesDeCapa } = await imp('e5.js');
const LM = leafletMinimo();
const { CapaContornoE5 } = crearClasesE5(LM, crearClases(LM).CapaContorno);

/** A prepared body with `partes` one-ring parts of five positions each. */
function preparadoPartes(partes) {
  return { estado: 'cargado', partes, x: new Float64Array(partes * 5), y: new Float64Array(partes * 5),
           inicioAnillo: new Int32Array(partes + 1), inicioParte: new Int32Array(partes + 1),
           cajasParte: new Float64Array(partes * 4) };
}

test('R1: a layer\'s own array is admitted before it is allocated, or not built at all', () => {
  const q = preparadoPartes(20_000);
  // The supervisor's case: the budget holds exactly the prepared body.
  const justo = crearPresupuesto(bytesDe(q));
  justo.reservar('preparado', bytesDe(q), 'probe');
  assert.equal(CapaContornoE5.crear(q, {}, { id: 'g', controlador: {}, presupuesto: justo, dueno: 'probe' }), null);
  assert.equal(justo.usados, bytesDe(q));
  assert.equal(justo.porCategoria().capa, 0);
  // Room for one layer: the ledger equals every typed array actually held.
  const p = crearPresupuesto(bytesDe(q) + bytesDeCapa(q));
  p.reservar('preparado', bytesDe(q), 'probe');
  const capa = CapaContornoE5.crear(q, {}, { id: 'g', controlador: {}, presupuesto: p, dueno: 'probe' });
  assert.ok(capa);
  assert.equal(bytesDeCapa(q), 80_000);
  assert.equal(capa._visibles.byteLength, bytesDeCapa(q));
  assert.equal(p.usados, bytesDe(q) + capa._visibles.byteLength);
  assert.equal(p.porCategoria().capa, capa.bytesCapaE5());
  // A second layer of the SAME body needs its own array: refused here, nothing allocated.
  assert.equal(CapaContornoE5.crear(q, {}, { id: 'g', controlador: {}, presupuesto: p, dueno: 'probe' }), null);
  // Without a live 'capa' reservation the class refuses to build.
  assert.throws(() => new CapaContornoE5(q, {}, { id: 'g', controlador: {}, presupuesto: p, reserva: null }));
  capa.liberarMemoriaE5(); capa.liberarMemoriaE5();           // idempotent
  // A reservation admitted earlier (MapCanvas's cache-hit path) is taken over, not doubled.
  const previa = p.reservar('capa', bytesDeCapa(q), 'probe');
  const otra = CapaContornoE5.crear(q, {}, { id: 'g', controlador: {}, presupuesto: p, dueno: 'probe', reserva: previa });
  assert.equal(otra._reservaCapa, previa);
  assert.equal(p.porCategoria().capa, bytesDeCapa(q));
  otra.liberarMemoriaE5();
  assert.equal(p.porCategoria().capa, 0);
  assert.equal(capa.bytesCapaE5(), 0);
});

test('R1: multiplicity, replacement, teardown and allocation failure keep the ledger exact', () => {
  const q = preparadoPartes(1000);
  const p = crearPresupuesto(64 * MiB);
  const crear = (dueno) => CapaContornoE5.crear(q, {}, { id: 'g', controlador: {}, presupuesto: p, dueno });
  const mapaA = [crear('a'), crear('a')];                     // two layers of one body in one map
  const mapaB = [crear('b')];                                  // and one in another map
  const real = () => [...mapaA, ...mapaB].reduce((s, c) => s + c.bytesCapaE5(), 0);
  assert.equal(p.porCategoria().capa, 3 * bytesDeCapa(q));
  assert.equal(p.porCategoria().capa, real());
  // Replacement (render): the old layer is released before its successor is built.
  mapaA[0].liberarMemoriaE5(); mapaA[0] = crear('a');
  assert.equal(p.porCategoria().capa, real());
  assert.equal(p.picoPorCategoria().capa, 3 * bytesDeCapa(q));
  // Teardown of map B, then of map A.
  for (const c of mapaB) c.liberarMemoriaE5();
  assert.equal(p.porCategoria().capa, 2 * bytesDeCapa(q));
  for (const c of mapaA) c.liberarMemoriaE5();
  assert.equal(p.porCategoria().capa, 0);
  // The allocation itself fails after admission: the reservation is released.
  const enorme = { ...preparadoPartes(1), partes: 2 ** 32 };
  const grande = crearPresupuesto(Number.MAX_SAFE_INTEGER);
  assert.throws(() => CapaContornoE5.crear(enorme, {}, { id: 'h', controlador: {}, presupuesto: grande, dueno: 'x' }),
                RangeError);
  assert.equal(grande.usados, 0);
});

// R2: one synchronous send failure at each stage of the client.
function trabajadorQueFalla(tipo) {
  const t = trabajadorFalso();
  const real = t.postMessage;
  t.postMessage = (m) => { if (m.tipo === tipo) throw new Error(`injected ${tipo} failure`); return real(m); };
  return t;
}

for (const etapa of ['cuerpo', 'olvidar', 'raster', 'cancelar', 'olvidarTodo', 'estadisticas']) {
  test(`R2: a synchronous ${etapa} post failure terminates, releases and answers through one path`, async () => {
    const p = crearPresupuesto(4 * MiB);
    const t = trabajadorQueFalla(etapa);
    const fallos = [];
    const c = crearCliente({ presupuesto: p, dueno: 'prueba', crearTrabajador: () => t, plazoMs: 5000,
                             alFallar: (m) => fallos.push(m) });
    await drenar(2);
    assert.equal(c.estado, 'listo');
    if (etapa !== 'cuerpo') { assert.equal(c.asegurar('a', preparado(1000)), 'listo'); await drenar(); }
    const respuestas = [];
    let resultado = null;
    let esperado = 'listo';
    if (etapa === 'cuerpo') resultado = c.asegurar('a', preparado(1000));
    else if (etapa === 'olvidar') c.expulsado('a');
    else if (etapa === 'raster' || etapa === 'cancelar') {
      const area = { ancho: 10, alto: 10, m: 1, bmin: [0, 0], origen: [0, 0], escala: 1, capas: [{ id: 'a', estilo: {} }] };
      resultado = c.raster(area, (r) => respuestas.push(r));
      if (etapa === 'cancelar') c.descartar(resultado);
    } else if (etapa === 'olvidarTodo') resultado = await c.olvidarTodo();
    else resultado = await c.estadisticas();
    if (etapa === 'cuerpo') esperado = 'fallido';
    assert.equal(c.estado, 'fallido');
    assert.equal(c.motivo, 'envio');
    assert.ok(t.terminado, 'the worker was terminated');
    assert.deepEqual(fallos, ['envio']);
    assert.equal(p.usados, 0, 'no reservation stays owned');
    assert.equal(p.pendienteDeLiberar, 0);
    assert.equal(c.bytesReservados(), 0);
    if (etapa === 'cuerpo') assert.equal(resultado, esperado);
    if (etapa === 'raster') { assert.equal(resultado, null); assert.deepEqual(respuestas, [{ fallo: 'envio' }]); }
    if (etapa === 'olvidarTodo') assert.equal(resultado, false);
    if (etapa === 'estadisticas') assert.equal(resultado, null);
    // Late traffic after the failure is ignored and changes nothing.
    t.onmessage?.({ data: { tipo: 'listo', offscreen: true } });
    assert.equal(c.estado, 'fallido');
    assert.equal(c.asegurar('b', preparado(10)), 'fallido');
    assert.equal(p.usados, 0);
    c.cerrar();
  });
}

test('R2: a worker that never says "listo" fails within its startup bound', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const p = crearPresupuesto(MiB);
  const w = trabajadorFalso({ sinListo: true });
  const fallos = [];
  const c = crearCliente({ presupuesto: p, dueno: 'prueba', crearTrabajador: () => w, plazoMs: 10,
                           alFallar: (m) => fallos.push(m) });
  t.mock.timers.tick(9);
  assert.equal(c.estado, 'iniciando');
  t.mock.timers.tick(1);
  assert.equal(c.estado, 'fallido');
  assert.equal(c.motivo, 'sinInicio');
  assert.ok(w.terminado);
  assert.deepEqual(fallos, ['sinInicio']);
  w.onmessage?.({ data: { tipo: 'listo', offscreen: true } });  // a late handshake
  assert.equal(c.estado, 'fallido');
  // A prompt handshake clears the bound.
  const w2 = trabajadorFalso({ sinListo: true });
  const c2 = crearCliente({ presupuesto: p, dueno: 'prueba', crearTrabajador: () => w2, plazoMs: 10 });
  w2.onmessage({ data: { tipo: 'listo', offscreen: true } });
  t.mock.timers.tick(100);
  assert.equal(c2.estado, 'listo');
  c.cerrar(); c2.cerrar();
});

test('R2: the controller settles to "sin_trabajador" on a failed send and retries with a fresh worker', async () => {
  for (const etapa of ['cuerpo', 'raster']) {
    const p = crearPresupuesto(4 * MiB);
    const informados = [];
    const creados = [];
    const fabrica = (o) => {
      const w = creados.length === 0 ? trabajadorQueFalla(etapa) : trabajadorFalso();
      const c = crearCliente({ presupuesto: p, dueno: 'mapa', crearTrabajador: () => w, plazoMs: 5000, ...o });
      creados.push({ w, c });
      return c;
    };
    const renderer = { _bounds: { min: { x: 0, y: 0 }, max: { x: 100, y: 50 } }, _container: { width: 100, height: 50 },
                       _layers: {}, _drawFirst: null, _redraw() {}, _updatePaths() {}, on() {}, off() {} };
    const map = { getPixelOrigin: () => ({ x: 0, y: 0 }), getZoom: () => 10, options: { crs: { scale: (z) => 256 * 2 ** z } } };
    class CapaBitmap { constructor() {} addTo() { return this; } bringToBack() {} redraw() {} get _map() { return map; } }
    const ctl = crearControlador({ L: null, map, CapaBitmap, presupuesto: p, dueno: 'mapa', crearCliente: fabrica,
                                   alEstado: (capa, estado) => informados.push([capa._id, estado]) });
    const capa = { _id: 'g-0', _renderer: renderer, _map: map, _nVisibles: 1, _carga: { anillos: 5000, posiciones: 50000 },
                   _prep: preparado(10), options: { color: '#123456', weight: 2 } };
    renderer._drawFirst = { layer: capa, next: null };
    ctl.agregar(capa);
    await hasta(() => informados.some(([, e]) => e === 'sin_trabajador'));
    assert.deepEqual(informados.at(-1), ['g-0', 'sin_trabajador'], etapa);
    assert.equal(ctl.cliente.motivo, 'envio');
    assert.equal(p.usados, 0, `${etapa}: nothing stays reserved after the failure`);
    // Explicit retry (the next render()): one fresh worker, and the outline becomes final.
    ctl.reintentar();
    capa.options = { color: '#654321', weight: 2 };
    ctl.cambioDeEstilo(capa);
    await hasta(() => ctl.mostrada);
    assert.equal(creados.length, 2);
    assert.deepEqual(informados.at(-1), ['g-0', 'listo']);
    ctl.cerrar();
    assert.equal(p.usados, 0);
  }
});

// R3: finite admission of waiting preparations and bounded retained input.
function exponerGc() {
  try { v8.setFlagsFromString('--expose_gc'); return vm.runInNewContext('gc'); } catch { return null; }
}

test('R3: a burst of distinct requests is admitted up to a finite bound; the rest are refused explicitly', async () => {
  const p = crearPresupuesto(64 * MiB);
  const reg = crearRegistro(p, 'm');
  const pasos = [];
  const plan = crearPlanificador({ registro: reg, presupuesto: p, alPreparar: (d, r, res) => reg.guardar(d, r, res),
                                   ceder: (fn) => pasos.push(fn) });
  const avisos = new Map();
  const casos = Array.from({ length: 100 }, (_, i) => cuerpoValido(`g${i}`, 50));
  for (const { descriptor, cuerpo } of casos) {
    plan.pedir(descriptor, new Map([[descriptor.id, cuerpo]]), (r) => avisos.set(descriptor.id, r));
  }
  assert.equal(plan.capacidad, 32);
  assert.equal(plan.pendientes, 32, 'only the bounded number of jobs is kept');
  assert.equal(plan.cuerposRetenidos, 32);
  assert.equal(avisos.size, 0, 'refusals are delivered after the call returns');
  await tarea();
  assert.equal(avisos.size, 68);
  assert.ok([...avisos.values()].every((r) => r.estado === 'sin_memoria' && r.motivo === 'cola_llena'));
  assert.equal(plan.metricas.colaLlena, 68);
  assert.equal(p.usados, 0, 'waiting and refused jobs reserve nothing');
  // Supersession: a newer view keeps only what it needs; the bound frees up.
  plan.conservarSolo(new Set(['g0', 'g1']));
  assert.equal(plan.pendientes, 2);
  const nuevo = cuerpoValido('nuevo', 50);
  plan.pedir(nuevo.descriptor, new Map([[nuevo.descriptor.id, nuevo.cuerpo]]), (r) => avisos.set('nuevo', r));
  while (pasos.length) pasos.shift()();
  assert.equal(avisos.get('nuevo').estado, 'cargado');
  assert.equal(avisos.get('g0').estado, 'cargado');
  assert.equal(plan.pendientes, 0);
  // Two maps (two planners) are bounded independently; a stopped planner admits nothing.
  const otro = crearPlanificador({ registro: crearRegistro(p, 'n'), presupuesto: p, alPreparar: () => {},
                                   ceder: () => {}, maxEnEspera: 3 });
  for (const { descriptor, cuerpo } of casos.slice(0, 10)) otro.pedir(descriptor, new Map([[descriptor.id, cuerpo]]), () => {});
  assert.equal(otro.pendientes, 5);
  otro.detener();
  otro.pedir(casos[50].descriptor, new Map(), () => {});
  assert.equal(otro.pendientes, 0);
  plan.detener(); reg.cerrar();
});

test('R3: an admitted job keeps only its own body reachable, not the caller\'s Map', async () => {
  const gc = exponerGc();
  const p = crearPresupuesto(64 * MiB);
  const reg = crearRegistro(p, 'm');
  const plan = crearPlanificador({ registro: reg, presupuesto: p, alPreparar: (d, r, res) => reg.guardar(d, r, res),
                                   ceder: () => {} });                // never runs: every job stays waiting
  const mapas = []; const cuerpos = []; const ajenos = [];
  (() => {
    for (let i = 0; i < 20; i += 1) {
      const { descriptor, cuerpo } = cuerpoValido(`g${i}`, 50);
      const ajeno = { geojson: { relleno: new Float64Array(1000) } };  // another row's body in the same Map
      const m = new Map([[descriptor.id, cuerpo], [`otro-${i}`, ajeno]]);
      plan.pedir(descriptor, m, () => {});
      mapas.push(new WeakRef(m)); cuerpos.push(new WeakRef(cuerpo)); ajenos.push(new WeakRef(ajeno));
    }
  })();
  assert.equal(plan.cuerposRetenidos, 20);
  if (!gc) return;                                   // no collector access: the counts above still hold
  await tarea(); gc(); await tarea(); gc();
  assert.equal(mapas.filter((r) => r.deref()).length, 0, 'no caller Map is retained');
  assert.equal(ajenos.filter((r) => r.deref()).length, 0, 'no other body is retained');
  assert.equal(cuerpos.filter((r) => r.deref()).length, 20, 'each waiting job keeps its own body (caller-owned)');
  plan.conservarSolo(new Set());
  await tarea(); gc(); await tarea(); gc();
  assert.equal(cuerpos.filter((r) => r.deref()).length, 0, 'cancellation drops every retained body');
  plan.detener(); reg.cerrar();
});

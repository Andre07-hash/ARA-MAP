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
  assert.deepEqual(p.porCategoria(), { preparado: 0, copia: 4, raster: 0 });
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
  const pasos = [];
  const plan2 = crearPlanificador({ registro: reg, presupuesto: p, alPreparar: (d, r, res) => reg.guardar(d, r, res),
                                    ceder: (fn) => pasos.push(fn) });
  const { descriptor, cuerpo } = cuerpoValido('g9', 90_000);
  plan2.pedir(descriptor, new Map([[descriptor.id, cuerpo]]), () => assert.fail('cancelled job reported'));
  pasos.shift()();                                 // one slice: structure read, arrays reserved and allocated
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
  assert.deepEqual(p.porCategoria(), { preparado: u, copia: u, raster: 0 });
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

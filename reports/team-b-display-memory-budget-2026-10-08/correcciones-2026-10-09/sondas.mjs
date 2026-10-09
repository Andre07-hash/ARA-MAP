/* The supervisor's four memory probes (reproduce_memory.mjs at review commit
 * 009a724), adapted to the corrected prototype. Same scenarios and doubles;
 * the only API change is that an E5 layer is built with CapaContornoE5.crear,
 * which admits its own array first (`new` without a reservation now throws).
 * Not browser evidence.   Run: node correcciones-2026-10-09/sondas.mjs
 */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const aqui = path.dirname(fileURLToPath(import.meta.url));
const imp = (f) => import(pathToFileURL(path.join(aqui, '..', 'prototipo', f)));
const { crearPresupuesto } = await imp('presupuesto.js');
const { crearCliente } = await imp('cliente.js');
const { crearRegistro } = await imp('registro.js');
const { crearPlanificador } = await imp('planificador.js');
const { crearClasesE5 } = await imp('e5.js');
const { bytesDe } = await imp('preparar.js');
const { crearClases } = await import(pathToFileURL(path.join(aqui, '..', '..', 'team-b-display-strategy-2026-10-08',
                                                            'prototipo', 'capa.js')));
const print = (probe, observed) => console.log(JSON.stringify({ probe, observed }));

function Base() {}
Base.extend = function extend(methods) {
  const Parent = this;
  function Child(...args) { this.initialize?.(...args); }
  Child.prototype = Object.assign(Object.create(Parent.prototype), methods);
  Child.extend = Parent.extend;
  return Child;
};
const L = { Polygon: Base, Path: Base, Util: { setOptions: (o, op) => { o.options = { ...o.options, ...op }; } } };
const { CapaContornoE5 } = crearClasesE5(L, crearClases(L).CapaContorno);
const parts = 20000;
const prepared = { estado: 'cargado', partes: parts, x: new Float64Array(parts * 5), y: new Float64Array(parts * 5),
                   inicioAnillo: new Int32Array(parts + 1), inicioParte: new Int32Array(parts + 1),
                   cajasParte: new Float64Array(parts * 4) };

{ // R1: same budget as the review (exactly the prepared body), then room for one layer.
  const p = crearPresupuesto(bytesDe(prepared));
  p.reservar('preparado', bytesDe(prepared), 'probe');
  const refused = CapaContornoE5.crear(prepared, {}, { id: 'probe', controlador: {}, presupuesto: p, dueno: 'probe' });
  const roomy = crearPresupuesto(bytesDe(prepared) + 4 * parts);
  roomy.reservar('preparado', bytesDe(prepared), 'probe');
  const layer = CapaContornoE5.crear(prepared, {}, { id: 'probe', controlador: {}, presupuesto: roomy, dueno: 'probe' });
  print('unaccounted_layer_array', {
    tightBudget: { budget: p.total, ledger: p.usados, layerBuilt: refused !== null },
    roomyBudget: { budget: roomy.total, ledger: roomy.usados, ledgerCapa: roomy.porCategoria().capa,
                   visibleArrayBytes: layer._visibles.byteLength,
                   actualTypedArrayBytes: bytesDe(prepared) + layer._visibles.byteLength },
  });
}

{ // R2: synchronous post failure.
  const failures = [];
  let terminated = false;
  const worker = { postMessage() { throw new Error('injected synchronous post failure'); },
                   terminate() { terminated = true; } };
  const cp = crearPresupuesto(1024 * 1024);
  const client = crearCliente({ presupuesto: cp, dueno: 'probe', crearTrabajador: () => worker, plazoMs: 10,
                                alFallar: (why) => failures.push(why) });
  worker.onmessage({ data: { tipo: 'listo', offscreen: true } });
  let thrown = null; let returned = null;
  try {
    returned = client.asegurar('small', { estado: 'cargado', x: new Float64Array(5), y: new Float64Array(5),
      inicioAnillo: new Int32Array([0, 5]), inicioParte: new Int32Array([0, 1]), cajasParte: new Float64Array(4), partes: 1 });
  } catch (error) { thrown = error.message; }
  print('synchronous_post_failure', { thrown, returned, state: client.estado, reason: client.motivo, failures,
                                      terminated, retainedBytes: cp.usados, copies: client.copias });
  client.cerrar();
}

{ // R2: silent startup.
  const silent = { postMessage() {}, terminate() {} };
  const waiting = crearCliente({ presupuesto: crearPresupuesto(1024), dueno: 'silent', crearTrabajador: () => silent,
                                 plazoMs: 10 });
  await new Promise((resolve) => setTimeout(resolve, 60));
  print('silent_startup', { deadlineMs: 10, waitedMs: 60, state: waiting.estado, reason: waiting.motivo });
  waiting.cerrar();
}

{ // R3: 100 distinct requests and maps.
  const queueBudget = crearPresupuesto(1024);
  const registry = crearRegistro(queueBudget, 'queue');
  const callbacks = [];
  const refused = [];
  const planner = crearPlanificador({ registro: registry, presupuesto: queueBudget,
    alPreparar: (d, r, res) => registry.guardar(d, r, res), ceder: (fn) => callbacks.push(fn) });
  for (let i = 0; i < 100; i += 1) planner.pedir({ id: `g${i}` }, new Map(), (r) => { if (r.motivo) refused.push(r.motivo); });
  await new Promise((resolve) => setTimeout(resolve, 0));
  print('uncapped_waiting_jobs', { queued: planner.pendientes, capacity: planner.capacidad,
                                   retainedBodiesAtMost: planner.cuerposRetenidos, allocatedJobs: planner.enMemoria,
                                   refusedExplicitly: refused.length, refusalReason: refused[0] ?? null,
                                   scheduledCallbacks: callbacks.length });
  planner.detener();
}

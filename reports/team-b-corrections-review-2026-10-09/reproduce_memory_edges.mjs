// Independent correction-edge probes. No browser, application edits or giant allocations.
// Usage: node reproduce_memory_edges.mjs /path/to/exact-pr21-archive
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const root = process.argv[2];
const folder = 'reports/team-b-display-memory-budget-2026-10-08/prototipo';
const imp = (name) => import(pathToFileURL(path.join(root, folder, name)));
const { crearPresupuesto } = await imp('presupuesto.js');
const { crearCliente } = await imp('cliente.js');
const { crearRegistro } = await imp('registro.js');
const { crearClasesE5, bytesDeCapa } = await imp('e5.js');
const { bytesDe } = await imp('preparar.js');
const { crearClases } = await import(pathToFileURL(path.join(root,
  'reports/team-b-display-strategy-2026-10-08/prototipo/capa.js')));
function Base() {}
Base.extend = function(methods) {
  const Parent = this;
  function Child(...args) { this.initialize?.(...args); }
  Child.prototype = Object.assign(Object.create(Parent.prototype), methods);
  Child.extend = Parent.extend;
  return Child;
};
const L = { Polygon: Base, Path: Base,
  Util: { setOptions: (obj, opts) => { obj.options = { ...obj.options, ...opts }; } } };
const { CapaContornoE5 } = crearClasesE5(L, crearClases(L).CapaContorno);
function prepared(parts) {
  return { estado: 'cargado', partes: parts, x: new Float64Array(parts * 5),
    y: new Float64Array(parts * 5), inicioAnillo: new Int32Array(parts + 1),
    inicioParte: new Int32Array(parts + 1), cajasParte: new Float64Array(parts * 4) };
}
const print = (probe, observed) => console.log(JSON.stringify({ probe, observed }));

{
  // MapCanvas cache-hit order: obtain, reserve layer, create, then pin.
  const body = prepared(20);
  const p = crearPresupuesto(bytesDe(body) + bytesDeCapa(body) - 1);
  const registry = crearRegistro(p, 'map');
  const descriptor = { id: 'body', bbox: [0, 0, 1, 1] };
  registry.guardar(descriptor, body, registry.reservar(bytesDe(body)));
  const cached = registry.obtener(descriptor);
  const reservation = p.reservar('capa', bytesDeCapa(cached), 'map');
  const layer = CapaContornoE5.crear(cached, {}, {
    id: descriptor.id, controlador: {}, presupuesto: p, dueno: 'map', reserva: reservation });
  registry.fijar(descriptor.id);
  const actual = bytesDe(layer._prep) + layer._visibles.byteLength;
  print('prepared_body_evicted_during_layer_admission', {
    budget: p.total, ledger: p.usados, registryEntries: registry.tamano,
    registryBytes: registry.bytesReales(), layerOwnBytes: layer.bytesCapaE5(),
    layerRetainsPreparedBytes: bytesDe(layer._prep), actualTypedArrayBytes: actual,
    exceedsBudget: actual > p.total,
    currentAuditSum: registry.bytesReales() + layer.bytesCapaE5(),
  });
  layer.liberarMemoriaE5(); registry.cerrar();
}

{
  // Failure during reservar's synchronous pressure-relief callback.
  const body = prepared(1);
  const p = crearPresupuesto(bytesDe(body));
  let terminated = false;
  const sent = [];
  const worker = {
    postMessage(message) {
      sent.push({ type: message.tipo, afterTermination: terminated });
      if (message.tipo === 'olvidar') throw new Error('injected forget failure');
    },
    terminate() { terminated = true; },
  };
  const failures = [];
  const client = crearCliente({ presupuesto: p, dueno: 'probe', crearTrabajador: () => worker,
    alFallar: (why) => failures.push(why) });
  worker.onmessage({ data: { tipo: 'listo', offscreen: true } });
  client.asegurar('first', body);
  const result = client.asegurar('second', body);
  print('send_failure_during_budget_relief', {
    result, clientState: client.estado, failures, terminated, ledger: p.usados,
    clientCopies: client.copias, sent,
  });
  client.cerrar();
}

{
  // Deterministic check of allocation-failure cleanup without a 16-GiB request.
  const FailingLayer = Base.extend({ initialize() { throw new RangeError('injected allocation failure'); } });
  const { CapaContornoE5: FailingE5 } = crearClasesE5(L, FailingLayer);
  const body = prepared(1);
  const p = crearPresupuesto(1024);
  let error = null;
  try { FailingE5.crear(body, {}, { id: 'failure', controlador: {}, presupuesto: p, dueno: 'probe' }); }
  catch (exc) { error = exc.name; }
  print('deterministic_layer_allocation_failure', { error, ledgerAfterFailure: p.usados });
}

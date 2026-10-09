/* The supervisor's three correction-edge probes (reproduce_memory_edges.mjs at
 * review commit c39f8aa), adapted to the corrected prototype. Same budgets,
 * fixtures and doubles. Probe 1 builds the layer the way MapCanvas now does
 * (CapaContornoE5.crearFijada: pin, then reserve) and reports the new
 * inventarioCapas audit; probe 2 is unchanged; probe 3 also checks the pinned
 * constructor's unwinding. Not browser evidence.
 *   Run: node correcciones-2026-10-09/sondas-bordes.mjs
 */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const aqui = path.dirname(fileURLToPath(import.meta.url));
const imp = (f) => import(pathToFileURL(path.join(aqui, '..', 'prototipo', f)));
const { crearPresupuesto } = await imp('presupuesto.js');
const { crearCliente } = await imp('cliente.js');
const { crearRegistro } = await imp('registro.js');
const { crearClasesE5, bytesDeCapa, inventarioCapas } = await imp('e5.js');
const { bytesDe } = await imp('preparar.js');
const { crearClases } = await import(pathToFileURL(path.join(aqui, '..', '..', 'team-b-display-strategy-2026-10-08',
                                                            'prototipo', 'capa.js')));
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
function prepared(parts) {
  return { estado: 'cargado', partes: parts, x: new Float64Array(parts * 5), y: new Float64Array(parts * 5),
           inicioAnillo: new Int32Array(parts + 1), inicioParte: new Int32Array(parts + 1), cajasParte: new Float64Array(parts * 4) };
}
const print = (probe, observed) => console.log(JSON.stringify({ probe, observed }));

{
  const body = prepared(20);
  const p = crearPresupuesto(bytesDe(body) + bytesDeCapa(body) - 1);
  const registry = crearRegistro(p, 'map');
  const descriptor = { id: 'body', bbox: [0, 0, 1, 1] };
  registry.guardar(descriptor, body, registry.reservar(bytesDe(body)));
  const cached = registry.obtener(descriptor);
  const layer = CapaContornoE5.crearFijada(cached, {}, { id: descriptor.id, controlador: {}, presupuesto: p, dueno: 'map',
                                                         registro: registry });
  const roomy = crearPresupuesto(bytesDe(body) + bytesDeCapa(body));
  const registry2 = crearRegistro(roomy, 'map');
  registry2.guardar(descriptor, body, registry2.reservar(bytesDe(body)));
  const built = CapaContornoE5.crearFijada(registry2.obtener(descriptor), {}, { id: descriptor.id, controlador: {},
    presupuesto: roomy, dueno: 'map', registro: registry2 });
  print('prepared_body_evicted_during_layer_admission', {
    tight: { budget: p.total, ledger: p.usados, layerBuilt: layer !== null, registryEntries: registry.tamano,
             registryBytes: registry.bytesReales(), pins: registry.entrada('body')?.fijos },
    roomy: { budget: roomy.total, ledger: roomy.usados,
             actualTypedArrayBytes: bytesDe(built._prep) + built._visibles.byteLength,
             exceedsBudget: bytesDe(built._prep) + built._visibles.byteLength > roomy.total,
             audit: inventarioCapas([built], registry2) },
  });
  built.liberarMemoriaE5(); registry.cerrar(); registry2.cerrar();
}

{
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
  print('send_failure_during_budget_relief', { result, clientState: client.estado, failures, terminated, ledger: p.usados,
                                               clientCopies: client.copias, sent });
  client.cerrar();
}

{
  const FailingLayer = Base.extend({ initialize() { throw new RangeError('injected allocation failure'); } });
  const { CapaContornoE5: FailingE5 } = crearClasesE5(L, FailingLayer);
  const body = prepared(1);
  const p = crearPresupuesto(1024);
  let error = null;
  try { FailingE5.crear(body, {}, { id: 'failure', controlador: {}, presupuesto: p, dueno: 'probe' }); } catch (exc) { error = exc.name; }
  const ledgerAfterFailure = p.usados;
  const registry = crearRegistro(p, 'map');
  registry.guardar({ id: 'failure', bbox: [0, 0, 1, 1] }, body, registry.reservar(bytesDe(body)));
  let error2 = null;
  try { FailingE5.crearFijada(body, {}, { id: 'failure', controlador: {}, presupuesto: p, dueno: 'probe', registro: registry }); }
  catch (exc) { error2 = exc.name; }
  print('deterministic_layer_allocation_failure', { error, ledgerAfterFailure,
    pinnedPath: { error: error2, pinsAfterFailure: registry.entrada('failure').fijos, ledger: p.usados, bodyBytes: bytesDe(body) } });
  registry.cerrar();
}

// Run: node reproduce_memory.mjs /path/to/pr21/archive
// Fakes exercise ownership/failure transitions; these are not browser paint tests.
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root = process.argv[2];
const folder = 'reports/team-b-display-memory-budget-2026-10-08/prototipo';
const imp = (name) => import(pathToFileURL(path.join(root, folder, name)));
const {crearPresupuesto} = await imp('presupuesto.js');
const {crearCliente} = await imp('cliente.js');
const {crearRegistro} = await imp('registro.js');
const {crearPlanificador} = await imp('planificador.js');
const {crearClasesE5} = await imp('e5.js');
const {bytesDe} = await imp('preparar.js');
const {crearClases} = await import(pathToFileURL(path.join(root,
    'reports/team-b-display-strategy-2026-10-08/prototipo/capa.js')));
const print = (probe, observed) => console.log(JSON.stringify({probe, observed}));

function baseClass() {}
baseClass.extend = function(methods) {
    const Parent = this;
    function Child(...args) { this.initialize?.(...args); }
    Child.prototype = Object.assign(Object.create(Parent.prototype), methods);
    Child.extend = Parent.extend;
    return Child;
};
const L = {Polygon: baseClass, Path: baseClass,
    Util: {setOptions: (obj, opts) => {obj.options = {...obj.options, ...opts};}}};
const {CapaContorno} = crearClases(L);
const {CapaContornoE5} = crearClasesE5(L, CapaContorno);
const parts = 20000;
const prepared = {estado:'cargado', partes:parts, x:new Float64Array(parts*5),
    y:new Float64Array(parts*5), inicioAnillo:new Int32Array(parts+1),
    inicioParte:new Int32Array(parts+1), cajasParte:new Float64Array(parts*4)};
const p = crearPresupuesto(bytesDe(prepared));
p.reservar('preparado', bytesDe(prepared), 'probe');
const layer = new CapaContornoE5(prepared, {}, {id:'probe', controlador:{}});
print('unaccounted_layer_array', {budget:p.total, ledger:p.usados,
    visibleArrayBytes:layer._visibles.byteLength,
    actualTypedArrayBytes:bytesDe(prepared)+layer._visibles.byteLength});

const failures = [];
let terminated = false;
const worker = {postMessage(){throw new Error('injected synchronous post failure');},
    terminate(){terminated=true;}};
const cp = crearPresupuesto(1024*1024);
const client = crearCliente({presupuesto:cp, dueno:'probe', crearTrabajador:()=>worker,
    plazoMs:10, alFallar:(why)=>failures.push(why)});
worker.onmessage({data:{tipo:'listo',offscreen:true}});
let thrown = null;
try {client.asegurar('small',{estado:'cargado',x:new Float64Array(5),y:new Float64Array(5),
    inicioAnillo:new Int32Array([0,5]),inicioParte:new Int32Array([0,1]),
    cajasParte:new Float64Array(4),partes:1});} catch(error){thrown=error.message;}
print('synchronous_post_failure',{thrown,state:client.estado,failures,terminated,
    retainedBytes:cp.usados,copies:client.copias});
client.cerrar();

const silent = {postMessage(){},terminate(){}};
const waiting = crearCliente({presupuesto:crearPresupuesto(1024),dueno:'silent',
    crearTrabajador:()=>silent,plazoMs:10});
await new Promise(resolve=>setTimeout(resolve,60));
print('silent_startup',{deadlineMs:10,waitedMs:60,state:waiting.estado,reason:waiting.motivo});
waiting.cerrar();

const queueBudget = crearPresupuesto(1024);
const registry = crearRegistro(queueBudget,'queue');
const callbacks=[];
const planner = crearPlanificador({registro:registry,presupuesto:queueBudget,
    alPreparar:(d,r,res)=>registry.guardar(d,r,res),ceder:(fn)=>callbacks.push(fn)});
for(let i=0;i<100;i++) planner.pedir({id:`g${i}`},new Map(),()=>{});
print('uncapped_waiting_jobs',{queued:planner.pendientes,allocatedJobs:planner.enMemoria,
    scheduledCallbacks:callbacks.length});
planner.detener();

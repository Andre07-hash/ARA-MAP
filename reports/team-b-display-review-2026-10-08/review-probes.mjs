/* Supervisory diagnostics only. No production code changes. */
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
// Arguments: disposable PR16 archive, accepted B2 archive, generated cases.
// Install/reuse playwright-core under the disposable archive's tests/e2e first.
const [pr16,b2,casos]=process.argv.slice(2).map(p=>path.resolve(p));
if(!pr16||!b2||!casos)throw new Error('Usage: node review-probes.mjs PR16_DIR B2_DIR CASES_DIR');
const require=createRequire(path.join(pr16,'tests/e2e/package.json'));
const {chromium}=require('playwright-core');
const d=path.join(pr16,'reports/team-b-display-strategy-2026-10-08');
const {servir}=await import(d+'/servidor.mjs');
const server=await servir({b2,casos});
const browser=await chromium.launch(process.env.CHROMIUM ? {executablePath:process.env.CHROMIUM} : {channel:'chrome'});
try {
 console.log('BROWSER',browser.version());
 const page=await browser.newPage({viewport:{width:1200,height:640}});
 await page.goto(server.url+'/proto/banco.html?impl=e1');
 await page.waitForFunction(()=>document.title==='listo');
 const dims=await page.evaluate(async()=>{
   const b=window.__banco;const d=await b.cargarFixture();b.canvas.render(d.filas,{colorFor:b.colorFor,geometrias:d.geometrias});
   await new Promise(ok=>requestAnimationFrame(()=>requestAnimationFrame(ok)));
   const c=document.querySelector('.leaflet-overlay-pane canvas');return {width:c.width,height:c.height,maskPixels:c.width*c.height,coverageLoopPixels:1200*640};
 });
 console.log('CANVAS_DIMENSIONS',JSON.stringify(dims));
 const timings=await page.evaluate(async()=>{
   const entries=[]; const observer=new PerformanceObserver(l=>entries.push(...l.getEntries().map(e=>({start:e.startTime,duration:e.duration}))));
   observer.observe({type:'longtask',buffered:false});
   await new Promise(ok=>setTimeout(ok,40));
   const prelude=performance.now()+5;while(performance.now()<prelude){}
   const t0=performance.now();const end=t0+150;while(performance.now()<end){}
   const t1=performance.now();await new Promise(ok=>setTimeout(ok,150));observer.disconnect();
   return {t0,t1,entries,reportedByStartFilter:entries.filter(e=>e.start>=t0),overlapping:entries.filter(e=>e.start+e.duration>t0&&e.start<t1)};
 });
 console.log('LONG_TASK_NEGATIVE_CONTROL',JSON.stringify(timings));
 await page.route('**/trabajador-raster.js',async route=>{
   const body=await readFile(d+'/prototipo/trabajador-raster.js','utf8');
   await route.fulfill({contentType:'text/javascript',body:body+'\nconst original=self.onmessage;self.onmessage=(e)=>{if(e.data.tipo==="reviewStats"){let bytes=0;for(const c of cuerpos.values())for(const key of ["x","y","inicioAnillo","inicioParte","cajasParte"])bytes+=c[key].byteLength;self.postMessage({reviewStats:true,entries:cuerpos.size,bytes});}else original(e);};'});
 });
 const memory=await page.evaluate(async()=>{
   const RealWorker=window.Worker;let worker;
   window.Worker=class extends RealWorker {constructor(...args){super(...args);worker=this;}};
   const {crearClienteRaster}=await import('/proto/prototipo/raster.js');
   const {crearCache}=await import('/proto/prototipo/planificador.js');
   const client=crearClienteRaster();const cache=crearCache();
   // Intercept only reviewStats; original handling still receives all ordinary replies.
   const original=worker.onmessage;let reply;
   worker.onmessage=e=>e.data.reviewStats?reply?.(e.data):original(e);
   const stats=()=>new Promise(ok=>{reply=ok;worker.postMessage({tipo:'reviewStats'});});
   for(let i=0;i<45;i++){
     const p={estado:'cargado',x:new Float64Array(60000),y:new Float64Array(60000),inicioAnillo:new Int32Array([0,60000]),inicioParte:new Int32Array([0,1]),cajasParte:new Float64Array(4),partes:1};
     cache.guardar({id:'body-'+i,bbox:[0,0,1,1]},p);client.asegurar('body-'+i,p);
   }
   const before={mainBytes:cache.bytes,mainEntries:cache.tamano,worker:await stats()};
   cache.vaciar();client.olvidarTodo();const reset=await stats();client.cerrar();window.Worker=RealWorker;
   return {before,reset};
 });
 console.log('WORKER_MEMORY',JSON.stringify(memory));
 await page.close();
} finally {await browser.close();server.cerrar();}

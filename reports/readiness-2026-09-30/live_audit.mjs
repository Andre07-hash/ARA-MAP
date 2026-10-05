/* Read-only production audit. The only allowed POSTs are login/logout/export. */
import {chromium} from '../../tests/e2e/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const origin='https://ara-map-ivory.vercel.app';
const evidence=new URL('./evidence/',import.meta.url);
const browser=await chromium.launch({channel:'chrome'});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const checks=[],errors=[],failedRequests=[],blockedWrites=[];
await context.route('**/api/**',async route=>{
  const r=route.request(),u=new URL(r.url());
  if(r.method()!=='GET' && !['/api/login','/api/logout','/api/exportar'].includes(u.pathname)) {
    blockedWrites.push({method:r.method(),path:u.pathname});await route.abort();return;
  }
  await route.continue();
});
const page=await context.newPage();
page.on('pageerror',e=>errors.push(e.message));
page.on('requestfailed',r=>{if(!r.failure()?.errorText.includes('ABORTED'))failedRequests.push({url:r.url(),error:r.failure()?.errorText});});
async function check(name,fn){try{checks.push({name,status:'PASS',detail:await fn()});}catch(e){checks.push({name,status:'FAIL',detail:e.message});}}
const nav=name=>page.getByRole('navigation',{name:'Secciones'}).getByRole('button',{name,exact:true});
const shot=name=>page.screenshot({path:fileURLToPath(new URL(name,evidence)),fullPage:true});
async function base(){await nav('Bases').click();await page.locator('.card-main').filter({hasText:'Base Terrenos 09.26 Gerardo'}).click();await page.locator('#buscar').waitFor();}
try {
 await page.goto(origin,{waitUntil:'networkidle'});
 await check('Fresh entry describes its empty map honestly',async()=>{
   const text=await page.locator('body').innerText();assert.match(text,/34 terrenos fuera del mapa/);return {defaultBase:'Copy of REPORTE RESERVA ARA',located:0,total:34};
 });
 await base();
 await check('Live search preserves focus during real keystrokes',async()=>{
   const field=page.locator('#buscar');await field.click();await page.keyboard.type('marcenas',{delay:70});
   assert.equal(await field.inputValue(),'marcenas');assert.equal(await page.evaluate(()=>document.activeElement.id),'buscar');
   await page.getByText('1 terreno de 79',{exact:true}).waitFor();await field.fill('');
 });
 await check('Live detail opens and Escape closes it',async()=>{
   await page.getByRole('group',{name:'Vista'}).getByRole('button',{name:'Tabla',exact:true}).click();
   await page.getByRole('row',{name:/Marce/}).first().click();await page.locator('.detail').waitFor();
   assert.match(await page.locator('.detail').innerText(),/Coordenadas/);await shot('live-detail.png');
   await page.keyboard.press('Escape');assert.equal(await page.locator('.detail').count(),0);
 });
 await check('Live table exports a downloadable workbook',async()=>{
   const dl=page.waitForEvent('download');await page.getByRole('button',{name:'Exportar',exact:true}).click();
   const download=await dl;assert.match(download.suggestedFilename(),/\.xlsx$/);assert.equal(await download.failure(),null);return {filename:download.suggestedFilename()};
 });
 await page.getByRole('group',{name:'Vista'}).getByRole('button',{name:'Mapa',exact:true}).click();
 await check('Basemap controls load satellite and street tiles',async()=>{
   for(const label of ['Satélite','Calles','Claro']){await page.getByRole('radio',{name:label,exact:true}).check();await page.waitForTimeout(1500);}
   const images=await page.locator('.leaflet-tile').evaluateAll(xs=>({count:xs.length,loaded:xs.filter(x=>x.complete&&x.naturalWidth>0).length}));
   assert.ok(images.loaded>0);return images;
 });
 await check('Both live saved comparisons reopen with their layers',async()=>{
   const result=[];
   for(const text of ['prueba comparación','Base Terrenos 09.26 Ficticia vs']){
     await nav('Mapas guardados').click();await page.locator('.card-main').filter({hasText:text}).click();
     await page.locator('.legend-item').first().waitFor();
     const labels=await page.locator('.legend-item').allTextContents();result.push({name:text,layers:labels.length});
     assert.equal(labels.length,text==='prueba comparación'?2:3);
   }
   await shot('live-comparison.png');return result;
 });
 await check('Layer visibility is reversible in the browser',async()=>{
   const toggle=page.locator('.legend-item input').first();await toggle.uncheck();assert.equal(await toggle.isChecked(),false);await toggle.check();assert.equal(await toggle.isChecked(),true);
 });
 await check('Live comparison export downloads',async()=>{
   const dl=page.waitForEvent('download');await page.getByRole('button',{name:'Exportar',exact:true}).click();const d=await dl;assert.equal(await d.failure(),null);return {filename:d.suggestedFilename()};
 });
 await check('Unauthenticated import settings are protected',async()=>{
   const r=await context.request.get(origin+'/api/formatos');assert.equal(r.status(),401);return {status:r.status()};
 });
 for(const width of [320,375,768,1440])await check(`Live visitor layout at ${width}px`,async()=>{
   await page.setViewportSize({width,height:900});await page.waitForTimeout(400);
   const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,header:document.querySelector('header')?.getBoundingClientRect().width}));
   assert.ok(size.document<=width+1,JSON.stringify(size));await shot(`live-visitor-${width}.png`);return size;
 });
 await page.setViewportSize({width:1440,height:1000});
 await check('Editor signs in with the existing configured credential',async()=>{
   const env=await fs.readFile(new URL('../../.env.local',import.meta.url),'utf8');
   const line=env.split(/\r?\n/).find(s=>s.startsWith('ARA_MAP_EDIT_PASSWORD='));assert.ok(line,'No saved editor credential');
   let password=line.slice(line.indexOf('=')+1).trim();if(/^['"]/.test(password))password=password.slice(1,-1);
   await page.getByRole('button',{name:'Iniciar sesión',exact:true}).click();await page.locator('#editor-password').fill(password);
   const login=page.waitForResponse(r=>r.url().endsWith('/api/login'));
   await page.locator('dialog[open]').getByRole('button',{name:'Entrar',exact:true}).click();
   assert.equal((await login).status(),200);await page.getByRole('button',{name:'Cerrar sesión',exact:true}).waitFor();
   const config=await (await context.request.get(origin+'/api/config')).json();assert.equal(config.readOnly,false);return {editor:true};
 });
 if(await page.getByRole('button',{name:'Cerrar sesión',exact:true}).count()){
   await check('Editor tools and folder navigation are present',async()=>{
     await nav('Bases').click();await page.getByRole('button',{name:'Importar archivo',exact:true}).first().waitFor();
     assert.ok(await page.getByRole('button',{name:'Nueva carpeta',exact:true}).count());
     await page.getByRole('button',{name:/GErman 1/}).click();assert.equal(await page.locator('.card-main').count(),1);
     await page.getByRole('button',{name:/Todas las bases 4/}).click();return {bases:await page.locator('.card-main').count()};
   });
   for(const width of [320,375,768,1440])await check(`Live editor layout at ${width}px`,async()=>{
     await page.setViewportSize({width,height:900});await page.waitForTimeout(250);
     const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
     assert.ok(size.document<=width+1);await shot(`live-editor-${width}.png`);return size;
   });
   await check('Editor can sign out',async()=>{
     await page.getByRole('button',{name:'Cerrar sesión',exact:true}).click();await page.getByRole('button',{name:'Iniciar sesión',exact:true}).waitFor();
     assert.equal((await (await context.request.get(origin+'/api/config')).json()).readOnly,true);
   });
 }
} finally {
 await fs.writeFile(new URL('live-browser.json',evidence),JSON.stringify({checks,errors,failedRequests,blockedWrites},null,2));
 await browser.close();
}
console.log(JSON.stringify({checks,errors,failedRequests,blockedWrites},null,2));

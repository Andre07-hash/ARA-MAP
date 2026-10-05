import {chromium} from '../../tests/e2e/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const browser=await chromium.launch({channel:'chrome'}),page=await browser.newPage({viewport:{width:1440,height:1000}});
const results=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
const evidence=new URL('./evidence/',import.meta.url);
const nav=n=>page.getByRole('navigation',{name:'Secciones'}).getByRole('button',{name:n,exact:true});
async function check(name,fn){try{results.push({name,status:'PASS',detail:await fn()});}catch(e){results.push({name,status:'FAIL',detail:e.message});}}
await page.route('**/api/**',async route=>{if(route.request().method()!=='GET')await route.abort();else await route.continue();});
try {
 await page.goto('https://ara-map-ivory.vercel.app/?test=1',{waitUntil:'networkidle'});
 await nav('Bases').click();await page.locator('.card-main').filter({hasText:'Base Terrenos 09.26 Gerardo'}).click();await page.locator('#buscar').waitFor();
 await check('Detail and Escape (case-insensitive text assertion)',async()=>{
  await page.getByRole('group',{name:'Vista'}).getByRole('button',{name:'Tabla',exact:true}).click();
  await page.getByRole('row',{name:/Marce/}).first().click();await page.locator('.detail').waitFor();assert.match(await page.locator('.detail').innerText(),/coordenadas/i);
  await page.screenshot({path:fileURLToPath(new URL('live-detail.png',evidence)),fullPage:true});
  await page.keyboard.press('Escape');assert.equal(await page.locator('.detail').count(),0);
 });
 await page.getByRole('group',{name:'Vista'}).getByRole('button',{name:'Mapa',exact:true}).click();
 await check('Live double-click reaches terrain scale',async()=>{
  const target=await page.evaluate(async()=>{const {getState}=await import('/lib/store.js');return getState().terrenos.filter(t=>t.ubicado&&t.superficie_m2>20000).sort((a,b)=>b.superficie_m2-a.superficie_m2)[0];});
  const required=await page.evaluate(async([m2,lat])=>(await import('/lib/geo.js')).trueScaleZoom(m2,lat,7),[target.superficie_m2,target.lat]);
  await page.evaluate(([lat,lon])=>window.__araTest.irA(lat,lon,7),[target.lat,target.lon]);await page.waitForTimeout(1000);
  const point=await page.evaluate(id=>window.__araTest.puntoDe(id),target.id);await page.mouse.dblclick(point.x,point.y);await page.waitForTimeout(2700);
  const actual=await page.evaluate(()=>window.__araTest.zoom());assert.ok(actual>=required);await page.keyboard.press('Escape');return {required,actual};
 });
 for(const width of [375,768,960,1024])await check(`Search is reachable at ${width}px`,async()=>{
  await page.setViewportSize({width,height:900});await page.waitForTimeout(200);
  const state=await page.evaluate(()=>({searchVisible:document.querySelector('#buscar')?.getClientRects().length>0,railDisplay:getComputedStyle(document.querySelector('.rail-slot')).display,buttons:[...document.querySelectorAll('button')].filter(x=>x.getClientRects().length).map(x=>x.innerText)}));
  if(width===375)await page.screenshot({path:fileURLToPath(new URL('live-mobile-no-search.png',evidence)),fullPage:true});
  assert.ok(state.searchVisible,JSON.stringify(state));return state;
 });
 await page.setViewportSize({width:1440,height:1000});await nav('Mapas guardados').click();
 await page.locator('.card-main').filter({hasText:'Base Terrenos 09.26 Ficticia vs'}).click();await page.locator('.legend-item').first().waitFor();
 await check('Layer visibility uses the intended source and restores it',async()=>{
  const before=await page.evaluate(async()=>(await import('/lib/store.js')).getState().capas.map(x=>({orden:x.orden,visible:x.visible})));
  const label=page.locator('.legend-item').first();const name=await label.innerText();
  await label.locator('input').uncheck();await page.waitForTimeout(400);
  const off=await page.evaluate(async()=>(await import('/lib/store.js')).getState().capas.map(x=>({orden:x.orden,visible:x.visible})));
  await page.locator('.legend-item').first().locator('input').check();await page.waitForTimeout(400);
  const after=await page.evaluate(async()=>(await import('/lib/store.js')).getState().capas.map(x=>({orden:x.orden,visible:x.visible})));
  assert.deepEqual(after,before);assert.equal(off[0].visible,false);return {name,before,off,after};
 });
} finally {
 await fs.writeFile(new URL('live-focused.json',evidence),JSON.stringify({results,errors},null,2));await browser.close();
}
console.log(JSON.stringify({results,errors},null,2));

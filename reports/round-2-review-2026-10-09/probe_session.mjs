// Independent checks against A's disposable tabla_servidor fixture only.
import { chromium } from '../../tests/e2e/node_modules/playwright-core/index.mjs';
import { readFileSync } from 'node:fs';
const fixture = process.env.REVIEW_TREE;
const password = /TEST_PASSWORD = "([^"]+)"/.exec(readFileSync(`${fixture}/tests/support.py`, 'utf8'))[1];
const browser = await chromium.launch({channel:'chrome'});
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  await context.request.post('http://localhost:8458/api/login', {data:{username:'olga',password}});
  await page.goto('http://localhost:8458/#/tabla');
  const cell = page.locator('td[data-col="core:notas_internas"]').first();
  await cell.waitFor();
  await cell.dblclick();
  await cell.locator('textarea').fill('PRIVATE-UNSAVED-FICTIONAL-MARKER');
  // Expire the actual current session server-side without changing app state.
  await context.request.post('http://localhost:8458/api/logout');
  await page.keyboard.press('Enter');
  await page.getByRole('dialog',{name:'Iniciar sesión'}).waitFor();
  const expiry = await page.evaluate(async()=>{
    const {getState}=await import('/lib/store.js');
    const values=[...document.querySelectorAll('input,textarea')].map(x=>x.value);
    return {session:getState().sesion,privateMarkerInDOM:document.body.textContent.includes('PRIVATE-UNSAVED-FICTIONAL-MARKER')||values.includes('PRIVATE-UNSAVED-FICTIONAL-MARKER'),tableRows:document.querySelectorAll('tr[data-id]').length};
  });
  console.log(JSON.stringify({probe:'expiry_with_unsaved_cell',...expiry}));
  await context.close();

  const second = await browser.newContext();
  const p = await second.newPage();
  p.setDefaultTimeout(10000);
  await second.request.post('http://localhost:8458/api/login',{data:{username:'olga',password}});
  await p.goto('http://localhost:8458/#/tabla');
  await p.locator('tr[data-id]').first().waitFor();
  const terrainId=await p.locator('tr[data-id]').first().getAttribute('data-id');
  const current=await (await second.request.get(`http://localhost:8458/api/inventario/terrenos/${terrainId}`)).json();
  await second.request.patch(`http://localhost:8458/api/inventario/terrenos/${terrainId}`,{data:{expected_version:current.terreno.version,changes:{notas_internas:'PRIVATE-SAVED-FICTIONAL-MARKER'}}});
  await p.reload();
  await p.locator('.tabla-abrir').first().click();
  await p.getByRole('dialog').waitFor();
  // A different account signs in using this browser's shared cookie jar.
  await second.request.post('http://localhost:8458/api/login',{data:{username:'otto',password}});
  await p.evaluate(()=>window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
  await p.waitForFunction(async()=>{const {getState}=await import('/lib/store.js');return getState().sesion?.login==='otto'||getState().sesion?.display_name==='Otto Ficticia';});
  console.log(JSON.stringify({probe:'account_switch_with_detail',...(await p.evaluate(async()=>{
    const {getState}=await import('/lib/store.js');
    return {account:getState().sesion?.display_name,openPrivateDialogs:document.querySelectorAll('dialog[open] .detalle-datos').length,detailHasOldPrivateComment:document.body.textContent.includes('PRIVATE-SAVED-FICTIONAL-MARKER')};
  }))}));
  console.log(JSON.stringify({probe:'new_account_backend_denial',status:(await second.request.get(`http://localhost:8458/api/inventario/terrenos/${terrainId}`)).status()}));
  await second.close();
  const third=await browser.newContext();
  const q=await third.newPage();
  q.setDefaultTimeout(10000);
  await third.request.post('http://localhost:8458/api/login',{data:{username:'olga',password}});
  await q.goto('http://localhost:8458/#/tabla');
  const name=q.locator('td[data-col="core:terreno"]').first();
  await name.waitFor();
  let release, reached;
  const hold=new Promise(r=>{release=r;});
  const sent=new Promise(r=>{reached=r;});
  await q.route('**/api/inventario/terrenos/*',async route=>{
    if(route.request().method()!=='PATCH') return route.continue();
    const response=await route.fetch();
    reached();
    await hold;
    await route.fulfill({response});
  });
  await name.dblclick();
  await name.locator('input').fill(`Fictional save ${Date.now()}`);
  await q.keyboard.press('Enter');
  await sent;
  const notes=q.locator('td[data-col="core:notas_internas"]').first();
  await notes.dblclick();
  await notes.locator('textarea').fill('SECOND-CELL-UNSAVED-MARKER');
  release();
  await q.locator('td[data-col="core:terreno"].is-pendiente').waitFor({state:'detached'});
  console.log(JSON.stringify({probe:'first_save_response_during_second_cell_edit',...(await q.evaluate(()=>({
    editorsInDOM:document.querySelectorAll('.tabla-editor').length,
    unsavedTextInDOM:[...document.querySelectorAll('textarea,input')].some(x=>x.value==='SECOND-CELL-UNSAVED-MARKER'),
    focusedTag:document.activeElement.tagName,
  })))}));
  await third.close();
} finally {await browser.close();}

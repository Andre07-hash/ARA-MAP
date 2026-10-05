import {chromium} from '../../../tests/e2e/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
const errors = [], results = [];
page.on('pageerror', e => errors.push(e.message));
const out = new URL('./evidence/', import.meta.url);
async function upload(name, buffer) {
  await page.goto(process.env.ARA_URL, {waitUntil:'networkidle'});
  await page.getByRole('navigation',{name:'Secciones'}).getByRole('button',{name:'Bases',exact:true}).click();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Importar archivo',exact:true}).first().click();
  await (await chooser).setFiles({name,mimeType:'application/octet-stream',buffer});
  await page.locator('#assistant-importar, #assistant-continuar').first().waitFor();
  return page.locator('dialog[open]');
}
async function change(action) {
  const response = page.waitForResponse(r=>r.url().includes('/api/importar/preparar') && r.request().method()==='POST');
  await action();
  const body = await (await response).json();
  await page.waitForFunction(()=> !document.querySelector('dialog[open] .spinner'));
  return body;
}
try {
  let d = await upload('one.csv', Buffer.from('Terreno,Precio,Latitud,Longitud\nFictional single,1200000,19,-99\n'));
  const empty = await change(()=>d.getByRole('button',{name:'No importar',exact:true}).click());
  await d.getByRole('alert').waitFor();
  results.push({case:'last-row',state:empty.estado,error:empty.error,restoreButtons:await d.getByRole('button',{name:'Sí es un terreno: importarla',exact:true}).count(),text:await d.innerText()});
  await page.screenshot({path:fileURLToPath(new URL('last-row.png',out)),fullPage:true});

  const csv = 'Terreno,Precio,Latitud,Longitud\nFictional real,1200000,19,-99\n'+Array.from({length:13},(_,i)=>`NOTA: fictional ${i+1},,,`).join('\n');
  d = await upload('thirteen-notes.csv',Buffer.from(csv));
  results.push({case:'thirteen-exclusions',restoreButtons:await d.getByRole('button',{name:'Sí es un terreno: importarla',exact:true}).count(),lastNoteShown:(await d.innerText()).includes('fictional 13'),text:await d.innerText()});
  await page.screenshot({path:fileURLToPath(new URL('thirteen-exclusions.png',out)),fullPage:true});

  d = await upload('two-sheets.xlsx',await fs.readFile(process.env.ARA_REVIEW_WORKBOOK));
  await d.getByText('Corregir interpretación',{exact:true}).click();
  await change(()=>d.locator('#corr-hoja').selectOption('sheet:0'));
  await d.locator('#assistant-importar').waitFor();
  await change(()=>d.getByRole('button',{name:'No importar',exact:true}).first().click());
  const switched = await change(()=>d.locator('#corr-hoja').selectOption('sheet:1'));
  await page.waitForFunction(()=>document.querySelector('dialog[open]')?.textContent.includes('Fictional 1-1'));
  results.push({case:'worksheet-switch',count:switched.vista_previa?.conteo,exclusions:switched.interpretacion.excluir,names:switched.vista_previa?.filas.map(r=>r.terreno)});
  await page.screenshot({path:fileURLToPath(new URL('worksheet-switch.png',out)),fullPage:true});
} finally {
  await fs.writeFile(new URL('browser.json',out),JSON.stringify({results,errors},null,2));
  await browser.close();
}
console.log(JSON.stringify({cases:results.map(({text,...r})=>r),errors},null,2));

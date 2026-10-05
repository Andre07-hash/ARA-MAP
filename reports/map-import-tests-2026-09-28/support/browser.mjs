import {chromium} from '../../../tests/e2e/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const output=[];
try {
 for(const id of [1,20,22,23,35]) {
  await page.goto(process.env.ARA_URL,{waitUntil:'networkidle'});
  await page.getByRole('navigation',{name:'Secciones'}).getByRole('button',{name:'Bases',exact:true}).click();
  const chooserPromise=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Importar archivo',exact:true}).first().click();
  const chooser=await chooserPromise;
  const responsePromise=page.waitForResponse(r=>r.url().includes('/api/importar/analizar')&&r.request().method()==='POST');
  const file=`MapTest${id}.${[1,20,35].includes(id)?'xlsx':'csv'}`;
  await chooser.setFiles(path.join(root,'files',file));
  const response=await responsePromise;
  await page.locator('#assistant-importar, #assistant-continuar').first().waitFor();
  const dialog=page.locator('dialog[open]');
  const record={file,httpStatus:response.status(),stats:await dialog.locator('.stat').allTextContents()};
  if(id===35) {
   await dialog.getByText('Corregir interpretación',{exact:true}).click();
   record.headerOptions=await dialog.locator('#corr-encabezado option').evaluateAll(os=>os.map(o=>({value:o.value,text:o.textContent})));
   record.canChooseRow56=record.headerOptions.some(o=>o.value==='55');
  }
  record.text=await dialog.innerText();
  await page.screenshot({path:path.join(root,'evidence',`browser-MapTest${id}.png`),fullPage:true});
  if(id===20 || id===22) {
   const checkbox=dialog.getByRole('checkbox',{name:/Recordar/});
   if(await checkbox.count())await checkbox.uncheck();
   const committed=page.waitForResponse(r=>r.url().includes('/api/importar/confirmar')&&r.request().method()==='POST');
   await dialog.locator('#assistant-importar').click();
   const result=await committed;record.commitStatus=result.status();
   record.bases=await (await fetch(process.env.ARA_URL+'/api/bases')).json();
  }
  output.push(record);
 }
} finally {
 await fs.writeFile(path.join(root,'evidence','browser-results.json'),JSON.stringify({cases:output,pageErrors:errors},null,2));
 await browser.close();
}
console.log(JSON.stringify(output.map(({file,httpStatus,count,priced,canChooseRow56,commitStatus})=>({file,httpStatus,count,priced,canChooseRow56,commitStatus})),null,2));
console.log('pageErrors',errors.length);

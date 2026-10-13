// Supervisor diagnostic: synthetic base archive from the global master view.
import { chromium } from './tests/e2e/node_modules/playwright-core/index.mjs';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
const origin = 'http://localhost:8486';
const password = readFileSync(new URL('./tests/support.py', import.meta.url), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
try {
  const admin = await browser.newContext();
  const viewer = await browser.newContext();
  const api = async (ctx, method, path, data) => {
    const r = await ctx.request.fetch(origin + path, { method, data, headers: { 'Idempotency-Key': randomUUID() } });
    const body = await r.json();
    if (r.status() !== 200) throw new Error(JSON.stringify({ path, status: r.status(), body }));
    return body;
  };
  await api(admin, 'POST', '/api/login', { username: 'ada', password });
  await api(viewer, 'POST', '/api/login', { username: 'alan', password });
  const { base } = await api(admin, 'POST', '/api/maestra/bases', { nombre: 'Supervisor master archive synthetic' });
  const { terreno } = await api(admin, 'POST', `/api/maestra/bases/${base.id}/terrenos`, { terreno: 'Supervisor master archive lot' });
  const p = await viewer.newPage();
  p.setDefaultTimeout(5000);
  await p.goto(origin + '/?test=1#/tabla/maestra');
  const row = p.locator(`tr[data-id="${terreno.id}"]`);
  await row.waitFor();
  await row.getByRole('button', { name: /Abrir terreno/ }).click();
  const detail = p.locator('dialog[open]').last();
  const pdf = detail.locator('.archivos-detalle[data-tipo="pdf"]');
  let release, enter;
  const held = new Promise(r => { release = r; });
  const entered = new Promise(r => { enter = r; });
  await p.route('**/api/archivos/versiones/*/completar', async r => { enter(); await held; await r.continue(); });
  await pdf.locator('input[type=file]').setInputFiles({ name: 'synthetic-master.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nsynthetic\n%%EOF') });
  await entered;
  await p.waitForTimeout(300);
  const fresh = await api(admin, 'GET', `/api/maestra/bases/${base.id}/acceso`);
  await api(admin, 'POST', `/api/maestra/bases/${base.id}/archivar`, { expected_version: fresh.base.version });
  const response = p.waitForResponse(r => r.url().endsWith('/completar'));
  release();
  const rejected = await response;
  await p.waitForTimeout(1200);
  const detailReadonly = await pdf.getAttribute('data-solo-lectura');
  await detail.getByRole('button', { name: 'Cerrar', exact: true }).click();
  const cell = row.locator('td[data-col="core:municipio"]');
  const readonly = await cell.getAttribute('aria-readonly');
  await cell.dblclick();
  console.log(JSON.stringify({ probe: 'base_archive_global_master', completionStatus: rejected.status(), detailReadonly,
    cellAriaReadonly: readonly, newEditorOpened: await cell.locator('.tabla-editor').count(),
    fileCellReadonly: await row.locator('.archivos-celda').evaluateAll(nodes => nodes.map(n => n.getAttribute('data-solo-lectura'))),
  }, null, 2));
} finally { await browser.close(); }

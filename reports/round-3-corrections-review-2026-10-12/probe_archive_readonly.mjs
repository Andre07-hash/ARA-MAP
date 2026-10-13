// Independent real-app archive/read-only revalidation probe. Disposable harness at loopback only.
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
if (!process.argv[2]) throw new Error('Pass the exact archived repository directory.');
const root = resolve(process.argv[2]);
const { chromium } = await import(pathToFileURL(resolve(root, 'tests/e2e/node_modules/playwright-core/index.mjs')));
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
const baseURL = process.argv[3] ?? 'http://localhost:8484';
if (!['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname)) throw new Error('Disposable loopback harness only.');
const password = readFileSync(resolve(root, 'tests/support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const admin = await browser.newContext(), operator = await browser.newContext();
async function api(ctx, method, path, data) {
  const response = await ctx.request.fetch(baseURL + path, { method, data, headers: { 'Idempotency-Key': randomUUID() } });
  return { status: response.status(), data: await response.json() };
}
try {
  await api(admin, 'POST', '/api/login', { username: 'ada', password });
  const b = await api(admin, 'POST', '/api/maestra/bases', { nombre: 'Supervisor archive probe synthetic' });
  if (b.status !== 200) throw new Error(`base setup ${b.status}`);
  const ops = await api(admin, 'GET', '/api/maestra/operadores?limit=200');
  const uid = ops.data.usuarios.find(x => x.login === 'olga').id;
  const grant = await api(admin, 'PUT', `/api/maestra/bases/${b.data.base.id}/acceso`, { expected_version: b.data.base.version, usuarios: [uid] });
  if (grant.status !== 200) throw new Error(`grant ${grant.status}`);
  const t = await api(admin, 'POST', `/api/maestra/bases/${b.data.base.id}/terrenos`, { terreno: 'Synthetic private upload row' });
  if (t.status !== 200) throw new Error(`terrain ${t.status}`);
  await api(operator, 'POST', '/api/login', { username: 'olga', password });
  const p = await operator.newPage();
  await p.goto(baseURL + '/?test=1#/tabla');
  const row = p.locator(`tr[data-id="${t.data.terreno.id}"]`);
  await row.waitFor();
  await row.getByRole('button', { name: /Abrir terreno/ }).click();
  const detail = p.locator('dialog[open]').last();
  let release, entered;
  const barrier = new Promise(r => { release = r; });
  const observed = new Promise(r => { entered = r; });
  await p.route('**/api/archivos/versiones/*/completar', async route => { entered(); await barrier; await route.continue(); });
  const pdf = detail.locator('.archivos-detalle[data-tipo="pdf"]');
  await pdf.locator('input[type=file]').setInputFiles({ name: 'synthetic-private.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nsynthetic\n%%EOF') });
  await observed;
  // Let start-triggered refreshes settle before archive; only completion then observes the lost write right.
  await p.waitForTimeout(300);
  const fresh = await api(admin, 'GET', `/api/inventario/terrenos/${t.data.terreno.id}`);
  const revoke = await api(admin, 'POST', `/api/inventario/terrenos/${t.data.terreno.id}/archivar`, { expected_version: fresh.data.terreno.version });
  if (revoke.status !== 200) throw new Error(`revoke ${revoke.status}`);
  const responsePromise = p.waitForResponse(r => r.url().endsWith('/completar'));
  release();
  const response = await responsePromise;
  await p.waitForTimeout(1200);
  console.log(JSON.stringify({ probe: 'real_upload_archived_readonly', completionStatus: response.status(),
    pickerVisibleAfterArchive: await pdf.locator('.archivos-elegir').isVisible(),
    pickerEnabledAfterArchive: await pdf.locator('.archivos-elegir').isEnabled().catch(() => false),
    detailReadonly: await pdf.getAttribute('data-solo-lectura').catch(() => null),
    rowStillPresent: await row.count(), detailStillOpen: await p.locator('dialog[open]').count(),
    privateFilenameStillPresent: (await p.locator('body').innerText()).includes('synthetic-private.pdf'),
    uploadPhase: await pdf.locator('.archivos-subida').last().getAttribute('data-fase').catch(() => null),
  }, null, 2));
} finally { await browser.close(); }

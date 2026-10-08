/* F1 diagnostic: is synchronous work run directly by page.evaluate (a
 * DevTools-protocol task) reported by the Long Tasks API?
 *
 *   CHROMIUM=/path/to/chrome node reports/team-b-display-strategy-2026-10-08/control-tarea-cdp.mjs
 *
 * Three cases, 150 ms of busy work each, then the long tasks overlapping
 * that interval: (1) directly in the evaluate, (2) after setTimeout(0), i.e.
 * in a page timer task, (3) after requestAnimationFrame. The original
 * banco.mjs ran its cold render, first direct redraw, first cancellation
 * render and visits in position (1).
 */

import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(AQUI, '..', '..', 'tests', 'e2e', 'package.json'));
const { chromium } = require('playwright-core');
const browser = await chromium.launch(process.env.CHROMIUM
  ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' });
const page = await browser.newPage();
await page.goto('data:text/html,<title>control</title>');
await page.evaluate(() => {
  window.__t = [];
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__t.push([e.startTime, e.duration]); })
    .observe({ type: 'longtask', buffered: true });
});
const salida = { navegador: browser.version(), casos: [] };
for (let rep = 0; rep < 3; rep += 1) {
  for (const modo of ['evaluate directo', 'tras setTimeout(0)', 'tras requestAnimationFrame']) {
    const t0 = await page.evaluate(async (modo) => {
      if (modo === 'tras setTimeout(0)') await new Promise((ok) => setTimeout(ok, 0));
      if (modo === 'tras requestAnimationFrame') await new Promise((ok) => requestAnimationFrame(ok));
      const inicio = performance.now();
      const fin = inicio + 150;
      while (performance.now() < fin) { /* busy */ }
      return inicio;
    }, modo);
    await page.waitForTimeout(300);
    const tareas = await page.evaluate((t) => window.__t.filter(([s, d]) => s < t + 150 && s + d > t)
      .map(([, d]) => d), t0);
    salida.casos.push({ repeticion: rep, modo, tareasLargasQueSolapan: tareas });
  }
}
console.log(`Chromium ${salida.navegador}`);
console.table(salida.casos.map((c) => ({ ...c, tareasLargasQueSolapan: JSON.stringify(c.tareasLargasQueSolapan) })));
await browser.close();

/* «Asistente IA» in the table's record detail (issue #65), with the REAL
 * table, detail dialog and file widgets on the real local server
 * (tests/e2e/tabla_servidor.py on a folder it creates and deletes), real
 * sessions and Chromium. Fictional accounts and terrains only.
 *
 *   cd tests/e2e && node tabla-asistente.mjs
 *
 * By default the two assistant routes are answered IN THE BROWSER by this
 * script with fictional answers that follow the contract of #65, so the
 * interface can be checked without the server half or any provider. Those
 * answers exist only here. With ASISTENTE_CONECTADO=1 nothing is intercepted
 * and the checks that need a scripted answer are skipped: the script starts
 * asistente_servidor.py instead, the real server with the assistant on and a
 * fictional provider that never connects. That provider writes what it was
 * sent to a file (ASISTENTE_REGISTRO, or one in the temporary folder), to
 * check that the terrain's name, id and base never leave the server.
 *
 * Checks: who sees the entry point (operator, administrator with it off, on
 * but unconfigured, on); the three actions and a question, sending one query
 * per click; waiting, errors and a manual retry; answers that arrive after
 * giving up, closing the detail, leaving the view or the session; answers
 * drawn as text; nothing kept in storage or the URL; and the table keeping
 * its scroll, its focus, its keyboard and a PDF upload in the same detail.
 * Optional: ASISTENTE_CAPTURAS=dir, CHROMIUM=/path, ASISTENTE_PUERTO.
 */

import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..', '..');
const PY = process.env.PYTHON ?? 'python3';
const PUERTO = Number(process.env.ASISTENTE_PUERTO ?? 8491);
const URLBASE = `http://127.0.0.1:${PUERTO}`;
const SHOTS = process.env.ASISTENTE_CAPTURAS ?? null;
const CONECTADO = process.env.ASISTENTE_CONECTADO === '1';
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const CLAVE = readFileSync(join(RAIZ, 'tests', 'support.py'), 'utf8').match(/TEST_PASSWORD\s*=\s*"([^"]+)"/)[1];
const FILAS = 40;
const TOLERANCIA = 2;

const CARPETA = mkdtempSync(join(tmpdir(), 'ara-asistente-'));
const F = JSON.parse(execFileSync(PY, ['-c',
  'import json, sys\nfrom pathlib import Path\nsys.path.insert(0, "tests/e2e")\n' +
  'from archivos_servidor import escribir_fixtures\n' +
  'd = Path(sys.argv[1]); d.mkdir()\nprint(json.dumps(escribir_fixtures(d)))', join(CARPETA, 'fixtures')],
  { cwd: RAIZ, encoding: 'utf8' }));

// Connected: the real server with the assistant on and its fictional provider
// (asistente_servidor.py), which records what it was sent.
const REGISTRO = CONECTADO ? (process.env.ASISTENTE_REGISTRO ?? join(CARPETA, 'enviado.jsonl')) : null;
const servidor = spawn(PY, CONECTADO
  ? [join(AQUI, 'asistente_servidor.py'), '--puerto', String(PUERTO), '--carpeta', join(CARPETA, 'instalacion'), '--registro', REGISTRO]
  : [join(AQUI, 'tabla_servidor.py'), '--puerto', String(PUERTO), '--carpeta', join(CARPETA, 'instalacion')],
  { cwd: RAIZ, stdio: ['ignore', 'pipe', 'ignore'] });
await new Promise((resolve, reject) => {
  let texto = '';
  servidor.stdout.on('data', (d) => { texto += d; if (/LISTO/.test(texto)) resolve(); });
  servidor.on('exit', (c) => reject(new Error(`el servidor salió (${c}): ${texto}`)));
});

/* ------------------------------------------------------------ harness */

let fallos = 0;
let omitidas = 0;
const sesiones = [];
async function revisar(nombre, fn, { simulado = false, conectado = false } = {}) {
  if (simulado && CONECTADO) { omitidas += 1; console.log(`--   ${nombre} (omitida: necesita respuestas guionizadas)`); return; }
  if (conectado && !CONECTADO) { omitidas += 1; console.log(`--   ${nombre} (omitida: sólo con ASISTENTE_CONECTADO=1)`); return; }
  try {
    await fn();
    console.log(`ok   ${nombre}`);
  } catch (error) {
    fallos += 1;
    console.log(`FALLO ${nombre}\n     ${String(error?.stack ?? error).split('\n').slice(0, 6).join('\n     ')}`);
    for (const s of sesiones) {
      if (SHOTS && !s.page.isClosed()) await s.page.screenshot({ path: join(SHOTS, `fallo-${fallos}-${s.usuario}.png`) }).catch(() => {});
      if (!s.page.isClosed()) await s.page.keyboard.press('Escape').catch(() => {});
    }
  }
}
const igual = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const cierto = (v, m) => { if (!v) throw new Error(m); };
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
async function hasta(fn, mensaje = 'no ocurrió a tiempo', ms = 30000) {
  const fin = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > fin) throw new Error(typeof mensaje === 'function' ? await mensaje() : mensaje);
    await esperar(50);
  }
}

/* The fictional half of the contract, answered in the page. `guion` decides
 * the next answer of each route; `retener()` holds the next consultation. */
const ASISTENTE = /\/api\/asistente-terreno\//;
function simulador(s) {
  s.config = { habilitado: true, disponible: true, max_pregunta: 500 };
  s.consultas = [];
  s.siguiente = null;              // (cuerpo, id) => {status, body} for the next consultation
  s.retenida = null;
  return s.page.route(ASISTENTE, async (ruta) => {
    const req = ruta.request();
    const url = new URL(req.url());
    if (url.pathname === '/api/asistente-terreno/config') {
      return ruta.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(s.config) });
    }
    const id = url.pathname.split('/')[3];
    const cuerpo = JSON.parse(req.postData() ?? '{}');
    s.consultas.push({ id, cuerpo });
    const guion = s.siguiente ?? respuestaFicticia;
    s.siguiente = null;
    if (s.retenida) { const r = s.retenida; s.retenida = null; r.llego(); await r.suelta; }
    const { status = 200, body } = guion(cuerpo, id, s);
    await ruta.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) }).catch(() => {});
  });
}
function retener(s) {
  let soltar, llego;
  const suelta = new Promise((r) => { soltar = r; });
  const llegada = new Promise((r) => { llego = r; });
  s.retenida = { suelta, llego };
  return { llegada, soltar: () => soltar() };
}
const VERSIONES = new Map();
function respuestaFicticia({ accion }, id) {
  const reglas = accion === 'faltantes';
  return { body: {
    terreno_id: id, version: VERSIONES.get(id) ?? 1, accion,
    respuesta: reglas ? 'Faltan 2 campos registrados.' : `Respuesta ficticia de ${accion}.`,
    campos_usados: [
      { campo: 'estado', etiqueta: 'Estado', valor: 'Estado Ficticio' },
      { campo: 'superficie_m2', etiqueta: 'Superficie (m²)', valor: '12,500 m²' },
    ],
    faltantes: [{ campo: 'asking_price', etiqueta: 'Precio total' }, { campo: 'availability', etiqueta: 'Disponibilidad' }],
    advertencias: [], origen: reglas ? 'reglas' : 'modelo',
  } };
}
const error = (status, code) => () => ({ status, body: { error: `Texto crudo ${code} sk-ficticio`, detalle: { code } } });

const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium' });
async function abrir(usuario) {
  const contexto = await navegador.newContext({ viewport: { width: 1100, height: 700 }, locale: 'es-MX' });
  contexto.setDefaultTimeout(20000);
  await contexto.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: URLBASE });
  const page = await contexto.newPage();
  const s = { usuario, page, errores: [], lecturas: [] };
  page.on('pageerror', (e) => s.errores.push(String(e)));
  page.on('request', (r) => { if (r.url().includes('/api/')) s.lecturas.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  await page.route(/arcgisonline|tile\.openstreetmap\.org|cartocdn/, (r) => r.fulfill({ status: 204, body: '' }));
  if (!CONECTADO) await simulador(s);
  await page.goto(`${URLBASE}/?test=1`);
  await entrar(s);
  sesiones.push(s);
  return s;
}
async function entrar(s) {
  await s.page.getByRole('button', { name: 'Iniciar sesión' }).click().catch(() => {});
  await s.page.getByLabel('Usuario').fill(s.usuario);
  await s.page.getByLabel('Contraseña').fill(CLAVE);
  await s.page.getByRole('button', { name: 'Entrar' }).click();
  await s.page.locator('.session-user').waitFor();
  s.desde = Date.now();
}
const llamar = (page, metodo, ruta, cuerpo) => page.evaluate(async ([m, r, c]) => {
  const res = await fetch(r, { method: m, headers: c ? { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() } : {},
    body: c ? JSON.stringify(c) : undefined });
  return { status: res.status, datos: await res.json().catch(() => null) };
}, [metodo, ruta, cuerpo ?? null]);

const celda = (page, id, col) => page.locator(`tr[data-id="${id}"] td[data-col="${col}"]`);
const posicion = (page) => page.evaluate(() => {
  const l = document.querySelector('.tabla-lienzo');
  return { top: Math.round(l.scrollTop), left: Math.round(l.scrollLeft), pageX: Math.round(window.scrollX), pageY: Math.round(window.scrollY) };
});
function mismaPosicion(antes, despues, m) {
  for (const k of Object.keys(antes)) {
    cierto(Math.abs(antes[k] - despues[k]) <= TOLERANCIA, `${m}: ${k} saltó de ${antes[k]} a ${despues[k]}`);
  }
}
const enfocada = (page) => page.evaluate(() => {
  const td = document.activeElement?.closest?.('td[data-col]');
  return td ? `${td.closest('tr').dataset.id}|${td.dataset.col}` : document.activeElement?.tagName ?? null;
});
const listas = (s) => s.lecturas.filter((l) => /^GET \/api\/(maestra\/bases\/[^/]+|inventario)\/terrenos$/.test(l)).length;
const asistentes = (s) => s.lecturas.filter((l) => /\/api\/asistente-terreno\//.test(l));

async function irA(page, vista) {
  await page.goto(`${URLBASE}/?test=1#/tabla/${vista}`);
  await page.locator('.tabla-pantalla').waitFor();
  await page.locator('.tabla-lienzo:not([aria-busy])').waitFor();
  await hasta(async () => (await page.locator('tr.tabla-fila').count()) === FILAS, 'la página no tiene todas las filas');
}
async function abrirDetalle(s, id) {
  await s.page.locator(`tr[data-id="${id}"]`).getByRole('button', { name: /Abrir terreno/ }).click();
  const d = s.page.getByRole('dialog', { name: /Lote Asistente/ });
  await d.waitFor();
  return d;
}
async function abrirPanel(s, d) {
  const b = d.getByRole('button', { name: 'Asistente IA' });
  await b.waitFor();
  await b.click();
  const panel = d.locator('section.asistente-terreno');
  await panel.waitFor();
  return panel;
}
const respuestas = (panel) => panel.locator('.asistente-terreno-respuesta');
const cerrarDetalle = (d) => d.getByRole('button', { name: 'Cerrar', exact: true }).last().click();

/* --------------------------------------------------------------- data */

const ada = await abrir('ada');
const admin = (m, r, c) => llamar(ada.page, m, r, c);
const base = (await admin('POST', '/api/maestra/bases', { nombre: 'Base Asistente Ficticia' })).datos.base;
const otra = (await admin('POST', '/api/maestra/bases', { nombre: 'Otra Base Ficticia' })).datos.base;
const ops = Object.fromEntries((await admin('GET', '/api/maestra/operadores?limit=200')).datos.usuarios.map((o) => [o.login, o.id]));
igual((await admin('PUT', `/api/maestra/bases/${base.id}/acceso`, { expected_version: base.version, usuarios: [ops.olga] })).status, 200, 'acceso');
for (let n = 1; n <= FILAS; n += 1) {
  const t = (await admin('POST', `/api/maestra/bases/${base.id}/terrenos`,
    { terreno: `Lote Asistente ${String(n).padStart(2, '0')} Ficticio`, estado: 'Estado Ficticio', superficie_m2: 12500 })).datos.terreno;
  VERSIONES.set(t.id, t.version);
}
await admin('POST', `/api/maestra/bases/${otra.id}/terrenos`, { terreno: 'Lote Otro Ficticio' });
await ada.page.reload();
await ada.page.locator('.tabla-pantalla').waitFor();
ada.desde = Date.now();

let filas = [];
await revisar('preparación: 40 filas que se desplazan', async () => {
  await irA(ada.page, base.id);
  filas = await ada.page.locator('tr.tabla-fila').evaluateAll((trs) => trs.map((t) => t.dataset.id));
  for (const id of filas) VERSIONES.set(id, VERSIONES.get(id) ?? 1);
});

/* --------------------------------------------------------- visibility */

const olga = await abrir('olga');
await revisar('operador: el detalle no ofrece el asistente ni lo consulta', async () => {
  await irA(olga.page, base.id);
  const d = await abrirDetalle(olga, filas[3]);
  await d.getByRole('button', { name: 'Historial' }).waitFor();
  await esperar(400);
  igual(await d.getByRole('button', { name: 'Asistente IA' }).count(), 0, 'botón para el operador');
  igual(asistentes(olga), [], 'peticiones del operador al asistente');
  await cerrarDetalle(d);
});

await revisar('administrador con la función apagada: no aparece el botón', async () => {
  ada.config = { habilitado: false, disponible: false, max_pregunta: 500 };
  await irA(ada.page, base.id);
  const d = await abrirDetalle(ada, filas[3]);
  await hasta(async () => asistentes(ada).includes('GET /api/asistente-terreno/config'), 'no se leyó la configuración');
  await esperar(300);
  igual(await d.getByRole('button', { name: 'Asistente IA' }).count(), 0, 'botón con la función apagada');
  await cerrarDetalle(d);
}, { simulado: true });

await revisar('administrador con la función encendida sin configurar: lo dice y no ofrece acciones', async () => {
  ada.config = { habilitado: true, disponible: false, max_pregunta: 500 };
  const d = await abrirDetalle(ada, filas[3]);
  const panel = await abrirPanel(ada, d);
  cierto(/no está configurado/.test(await panel.innerText()), 'sin aviso de configuración');
  igual(await panel.getByRole('button', { name: 'Resumir el terreno' }).count(), 0, 'acciones sin configurar');
  igual(await panel.locator('textarea').count(), 0, 'pregunta sin configurar');
  await cerrarDetalle(d);
  ada.config = { habilitado: true, disponible: true, max_pregunta: 500 };
}, { simulado: true });

/* ------------------------------------------------------------ actions */

await revisar('administrador: el panel muestra el terreno, el aviso de datos y toma el foco', async () => {
  const d = await abrirDetalle(ada, filas[5]);
  const panel = await abrirPanel(ada, d);
  const texto = await panel.innerText();
  cierto(/Lote Asistente \d+ Ficticio · versión \d+/.test(texto), `sin contexto: ${texto}`);
  cierto(/Claude/.test(texto) && /Evita escribir información sensible/.test(texto), 'sin aviso de datos enviados');
  cierto(/dirección exacta ni las coordenadas/.test(texto) && !/ubicación/.test(texto), 'el aviso no precisa qué parte de la ubicación no se envía');
  cierto(/Precio total/.test(texto) && /No se envían el nombre/.test(texto), 'sin lista de campos enviados');
  igual(await ada.page.evaluate(() => document.activeElement?.textContent), 'Asistente IA', 'foco en el título del panel');
  igual(await d.getByRole('button', { name: 'Asistente IA' }).getAttribute('aria-expanded'), 'true', 'aria-expanded');
  await d.getByRole('button', { name: 'Asistente IA' }).click();
  cierto(await panel.isHidden(), 'el panel no se ocultó');
  igual(await ada.page.evaluate(() => document.activeElement?.textContent), 'Asistente IA', 'el foco vuelve al botón');
  await cerrarDetalle(d);
});

await revisar('resumen: espera visible, un doble clic envía una sola consulta, borrador y campos consultados', async () => {
  const d = await abrirDetalle(ada, filas[5]);
  const panel = await abrirPanel(ada, d);
  const antes = ada.consultas.length;
  const r = retener(ada);
  await panel.getByRole('button', { name: 'Resumir el terreno' }).dblclick();
  await r.llegada;
  await panel.getByText(/Consultando: resumen/).waitFor();
  // aria-disabled while waiting: a forced click reaches the button and sends nothing.
  await panel.getByRole('button', { name: 'Resumir el terreno' }).click({ force: true });
  await panel.getByRole('button', { name: 'Preguntar' }).click({ force: true });
  igual(await panel.getByRole('button', { name: 'Resumir el terreno' }).getAttribute('aria-disabled'), 'true', 'aria-disabled');
  await esperar(300);
  r.soltar();
  await respuestas(panel).first().waitFor();
  igual(ada.consultas.length - antes, 1, 'consultas enviadas');
  igual(ada.consultas.at(-1), { id: filas[5], cuerpo: { accion: 'resumen', pregunta: '' } }, 'cuerpo');
  const t = await respuestas(panel).first().innerText();
  cierto(/Respuesta ficticia de resumen/.test(t), 'sin respuesta');
  cierto(/Basado en los datos registrados/.test(t) && /Borrador generado con IA \(Claude\)/.test(t), `sin rótulos: ${t}`);
  await panel.getByText(/Campos consultados \(2\)/).click();
  cierto(/12,500 m²/.test(await respuestas(panel).first().innerText()), 'campos consultados no visibles');
  await panel.getByRole('button', { name: 'Copiar borrador' }).click();
  igual(await ada.page.evaluate(() => navigator.clipboard.readText()), 'Respuesta ficticia de resumen.', 'portapapeles');
  await cerrarDetalle(d);
}, { simulado: true });

await revisar('faltantes por reglas y descripción: rótulos distintos, nada de IA en las reglas', async () => {
  const d = await abrirDetalle(ada, filas[6]);
  const panel = await abrirPanel(ada, d);
  await panel.getByRole('button', { name: 'Campos sin información' }).click();
  await hasta(async () => (await respuestas(panel).count()) === 1, 'faltantes no llegó');
  const f = await respuestas(panel).first().innerText();
  cierto(/Calculado por el programa con reglas, sin IA/.test(f) && !/IA \(Claude\)/.test(f), `rótulo de reglas: ${f}`);
  cierto(/Sin información registrada:\s*Precio total\s*Disponibilidad/.test(f), `lista de faltantes: ${f}`);
  cierto(/no significa que el dato no exista/.test(f), 'sin nota de faltantes');
  await panel.getByRole('button', { name: 'Redactar descripción breve' }).click();
  await hasta(async () => (await respuestas(panel).count()) === 2, 'descripción no llegó');
  cierto(/Respuesta ficticia de descripcion/.test(await respuestas(panel).first().innerText()), 'la más nueva va primero');
  igual(ada.consultas.slice(-2).map((c) => c.cuerpo.accion), ['faltantes', 'descripcion'], 'acciones');
  await cerrarDetalle(d);
}, { simulado: true });

await revisar('pregunta: Enter envía el texto recortado; vacía o larga no se envía', async () => {
  const d = await abrirDetalle(ada, filas[7]);
  const panel = await abrirPanel(ada, d);
  const caja = panel.getByLabel('Pregunta sobre este terreno');
  const antes = ada.consultas.length;
  await caja.fill('   ');
  await caja.press('Enter');
  cierto(/Escribe una pregunta/.test(await panel.innerText()), 'sin aviso de pregunta vacía');
  igual(await caja.getAttribute('maxlength'), '500', 'maxlength');
  await caja.fill('  ¿Qué superficie tiene registrada?  ');
  await hasta(async () => /\d+ \/ 500/.test(await panel.innerText()), 'sin contador');
  await caja.press('Enter');
  await hasta(async () => (await respuestas(panel).count()) === 1, 'la pregunta no llegó');
  igual(ada.consultas.length - antes, 1, 'consultas');
  igual(ada.consultas.at(-1).cuerpo, { accion: 'pregunta', pregunta: '¿Qué superficie tiene registrada?' }, 'cuerpo');
  cierto(/Pregunta: ¿Qué superficie tiene registrada\?/.test(await respuestas(panel).first().innerText()), 'pregunta visible');
  igual(await caja.inputValue(), '', 'la caja se vacía');
  await cerrarDetalle(d);
}, { simulado: true });

await revisar('texto seguro: HTML, Markdown y enlaces de la respuesta se ven como texto', async () => {
  const d = await abrirDetalle(ada, filas[8]);
  const panel = await abrirPanel(ada, d);
  const malicioso = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script> **negritas** [enlace](https://example.invalid) javascript:alert(1)';
  ada.siguiente = (c, id) => ({ body: { ...respuestaFicticia(c, id).body, respuesta: malicioso,
    campos_usados: [{ campo: 'estado', etiqueta: '<b>Estado</b>', valor: '<a href="https://example.invalid">x</a>' }],
    advertencias: ['<i>aviso</i>'] } });
  await panel.getByRole('button', { name: 'Resumir el terreno' }).click();
  await respuestas(panel).first().waitFor();
  igual(await respuestas(panel).first().locator('.asistente-terreno-texto').textContent(), malicioso, 'texto literal');
  igual(await panel.locator('img, script, a, b, i, iframe').count(), 0, 'elementos creados por la respuesta');
  igual(await ada.page.evaluate(() => window.__xss ?? null), null, 'código ejecutado');
  cierto(/<a href=/.test(await panel.locator('details').textContent()), 'el valor se muestra literal');
  await cerrarDetalle(d);
}, { simulado: true });

/* ------------------------------------------------------------- errors */

await revisar('errores: mensajes propios, reintento manual sólo cuando sirve', async () => {
  const d = await abrirDetalle(ada, filas[9]);
  const panel = await abrirPanel(ada, d);
  ada.siguiente = error(503, 'chat_no_disponible');
  await panel.getByRole('button', { name: 'Resumir el terreno' }).click();
  await panel.getByRole('alert').filter({ hasText: /no está disponible ahora/ }).waitFor();
  cierto(!/sk-ficticio|Texto crudo/.test(await panel.innerText()), 'texto crudo del servidor visible');
  const antes = ada.consultas.length;
  await panel.getByRole('button', { name: 'Reintentar' }).click();
  await respuestas(panel).first().waitFor();
  igual(ada.consultas.length - antes, 1, 'el reintento repite una vez');
  igual(ada.consultas.at(-1).cuerpo.accion, 'resumen', 'el reintento repite la acción');
  for (const [status, code, patron, reintento] of [
    [504, 'chat_tiempo', /tardó demasiado/, true], [429, 'chat_limite', /límite de consultas/, true],
    [503, 'chat_presupuesto', /presupuesto/, false], [503, 'chat_deshabilitado', /está apagado/, false],
    [404, 'no_encontrado', /ya no está disponible/, false], [502, 'chat_respuesta_invalida', /no era válida/, true],
  ]) {
    ada.siguiente = error(status, code);
    await panel.getByRole('button', { name: 'Campos sin información' }).click();
    await panel.getByRole('alert').filter({ hasText: patron }).waitFor();
    igual(await panel.getByRole('button', { name: 'Reintentar' }).count(), reintento ? 1 : 0, `reintento ${code}`);
  }
  ada.siguiente = (c, id) => ({ body: { ...respuestaFicticia(c, id).body, terreno_id: filas[0] } });
  await panel.getByRole('button', { name: 'Campos sin información' }).click();
  await panel.getByRole('alert').filter({ hasText: /no era válida/ }).waitFor();
  ada.siguiente = (c, id) => ({ body: { ...respuestaFicticia(c, id).body, version: 999 } });
  await panel.getByRole('button', { name: 'Campos sin información' }).click();
  await panel.getByRole('alert').filter({ hasText: /El terreno cambió/ }).waitFor();
  igual(await respuestas(panel).count(), 1, 'ninguna respuesta errónea se muestra');
  await cerrarDetalle(d);
}, { simulado: true });

/* --------------------------------------------- against the real server */

await revisar('conectado: las cuatro acciones pasan por el servidor y muestran sus campos', async () => {
  const id = filas[15];
  const d = await abrirDetalle(ada, id);
  const panel = await abrirPanel(ada, d);
  const nombre = await d.getByRole('heading', { level: 2 }).innerText();
  for (const [boton, n] of [['Resumir el terreno', 1], ['Campos sin información', 2], ['Redactar descripción breve', 3]]) {
    await panel.getByRole('button', { name: boton }).click();
    await hasta(async () => (await respuestas(panel).count()) === n, `${boton} no llegó`);
  }
  await panel.getByLabel('Pregunta sobre este terreno').fill('¿Qué superficie tiene registrada?');
  await panel.getByRole('button', { name: 'Preguntar' }).click();
  await hasta(async () => (await respuestas(panel).count()) === 4, 'la pregunta no llegó');
  const origenes = await respuestas(panel).evaluateAll((li) => li.map((x) => `${x.dataset.accion}:${x.dataset.origen}`));
  igual(origenes, ['pregunta:modelo', 'descripcion:modelo', 'faltantes:reglas', 'resumen:modelo'], 'orígenes');
  await respuestas(panel).last().getByText(/Campos consultados/).click();
  cierto(/Estado Ficticio/.test(await respuestas(panel).last().innerText()), 'el servidor no usó el estado registrado');
  igual(await panel.locator('b').count(), 0, 'HTML del proveedor interpretado');
  {
    const enviado = readFileSync(REGISTRO, 'utf8');
    cierto(enviado.includes('Estado Ficticio') && enviado.includes('¿Qué superficie tiene registrada?'), 'lo enviado no tiene los campos');
    cierto(!enviado.includes(nombre) && !enviado.includes(id) && !enviado.includes(base.id), 'nombre, id o base enviados al proveedor');
  }
  await cerrarDetalle(d);
}, { conectado: true });

/* ------------------------------------------------- late answers / scope */

await revisar('dejar de esperar: la respuesta tardía se descarta', async () => {
  const d = await abrirDetalle(ada, filas[10]);
  const panel = await abrirPanel(ada, d);
  const r = retener(ada);
  await panel.getByRole('button', { name: 'Resumir el terreno' }).click();
  await r.llegada;
  await panel.getByRole('button', { name: 'Dejar de esperar' }).click();
  r.soltar();
  await esperar(500);
  igual(await respuestas(panel).count(), 0, 'respuesta tardía mostrada');
  cierto(!/Consultando/.test(await panel.innerText()), 'sigue esperando');
  await cerrarDetalle(d);
}, { simulado: true });

await revisar('cerrar el detalle mientras responde: nada vuelve a aparecer al reabrirlo', async () => {
  const d = await abrirDetalle(ada, filas[11]);
  const panel = await abrirPanel(ada, d);
  await panel.getByRole('button', { name: 'Campos sin información' }).click();
  await respuestas(panel).first().waitFor();
  const r = retener(ada);
  await panel.getByRole('button', { name: 'Resumir el terreno' }).click();
  await r.llegada;
  await ada.page.keyboard.press('Escape');
  await d.waitFor({ state: 'detached' });
  r.soltar();
  await esperar(500);
  const d2 = await abrirDetalle(ada, filas[11]);
  await d2.getByRole('button', { name: 'Asistente IA' }).waitFor();
  igual(await d2.getByRole('button', { name: 'Asistente IA' }).getAttribute('aria-expanded'), 'false', 'panel reabierto solo');
  const p2 = await abrirPanel(ada, d2);
  igual(await respuestas(p2).count(), 0, 'respuestas de la apertura anterior');
  igual(await ada.page.locator('.asistente-terreno-respuesta').count(), 0, 'respuestas en el documento');
  await cerrarDetalle(d2);
}, { simulado: true });

await revisar('cambiar de base mientras responde: el detalle y su respuesta desaparecen', async () => {
  const d = await abrirDetalle(ada, filas[12]);
  const panel = await abrirPanel(ada, d);
  const r = retener(ada);
  await panel.getByRole('button', { name: 'Resumir el terreno' }).click();
  await r.llegada;
  await ada.page.evaluate((v) => { location.hash = `#/tabla/${v}`; }, otra.id);
  await hasta(async () => (await ada.page.locator('dialog').count()) === 0, 'el detalle sigue abierto');
  r.soltar();
  await esperar(500);
  igual(await ada.page.locator('.asistente-terreno, .asistente-terreno-respuesta').count(), 0, 'restos del panel');
  cierto(!/Respuesta ficticia/.test(await ada.page.locator('body').innerText()), 'texto de la respuesta visible');
}, { simulado: true });

await revisar('terminar la sesión mientras responde: se descarta y otra cuenta no la ve', async () => {
  await irA(ada.page, base.id);
  const d = await abrirDetalle(ada, filas[13]);
  const panel = await abrirPanel(ada, d);
  const r = retener(ada);
  await panel.getByRole('button', { name: 'Redactar descripción breve' }).click();
  await r.llegada;
  // The session ends elsewhere (another tab); the window's next focus finds it gone.
  igual((await llamar(ada.page, 'POST', '/api/logout')).status, 200, 'logout');
  await esperar(Math.max(0, 10_500 - (Date.now() - ada.desde)));
  await ada.page.evaluate(() => window.dispatchEvent(new Event('focus')));
  // The sign-in dialog opens in its place.
  await hasta(async () => (await ada.page.getByRole('dialog', { name: /Lote Asistente/ }).count()) === 0,
    'el detalle sigue abierto tras el logout');
  igual(await ada.page.locator('.asistente-terreno').count(), 0, 'el panel sigue en el documento');
  r.soltar();
  await esperar(500);
  cierto(!/Respuesta ficticia|Lote Asistente/.test(await ada.page.locator('body').innerText()), 'datos privados visibles');
  ada.usuario = 'alan';
  await entrar(ada);
  await irA(ada.page, base.id);
  const d2 = await abrirDetalle(ada, filas[13]);
  const p2 = await abrirPanel(ada, d2);
  igual(await respuestas(p2).count(), 0, 'la conversación de ada aparece a alan');
  await cerrarDetalle(d2);
}, { simulado: true });

await revisar('sin almacenamiento: ni localStorage, ni sessionStorage, ni la URL guardan la conversación', async () => {
  const d = await abrirDetalle(ada, filas[14]);
  const panel = await abrirPanel(ada, d);
  await panel.getByLabel('Pregunta sobre este terreno').fill('¿Pregunta ficticia de almacenamiento?');
  await panel.getByRole('button', { name: 'Preguntar' }).click();
  await respuestas(panel).first().waitFor();
  const guardado = await ada.page.evaluate(() => JSON.stringify([{ ...localStorage }, { ...sessionStorage }, location.href]));
  cierto(!/almacenamiento|Respuesta ficticia|asistente/i.test(guardado), `algo quedó guardado: ${guardado}`);
  await cerrarDetalle(d);
}, { simulado: true });

/* ---------------------------------------------- the table is untouched */

await revisar('la tabla conserva desplazamiento, foco y teclado; no se recarga al usar el asistente', async () => {
  await irA(ada.page, base.id);
  const id = filas[30];
  await celda(ada.page, id, 'core:lon').evaluate((td) => td.scrollIntoView({ block: 'center', inline: 'center' }));
  await celda(ada.page, id, 'core:lon').focus();
  await esperar(150);
  const antes = await posicion(ada.page);
  cierto(antes.top > 100 && antes.left > 100, `la celda no queda lejos del inicio: ${JSON.stringify(antes)}`);
  const listasAntes = listas(ada);
  // A mark on each drawn row survives only if the row is not rebuilt.
  await ada.page.locator('tr.tabla-fila').evaluateAll((trs) => trs.forEach((t) => { t.__marca = true; }));
  const d = await abrirDetalle(ada, id);
  const panel = await abrirPanel(ada, d);
  if (!CONECTADO) {
    await panel.getByRole('button', { name: 'Resumir el terreno' }).click();
    await respuestas(panel).first().waitFor();
  }
  await d.getByRole('button', { name: 'Asistente IA' }).click();
  await abrirPanel(ada, d);
  await cerrarDetalle(d);
  await esperar(400);
  mismaPosicion(antes, await posicion(ada.page), 'al cerrar el detalle');
  igual(listas(ada), listasAntes, 'lecturas de la lista');
  igual(await ada.page.locator('tr.tabla-fila').evaluateAll((trs) => trs.length > 0 && trs.every((t) => t.__marca === true)),
    true, 'las filas se reconstruyeron');
  cierto(await ada.page.evaluate((fila) => document.activeElement?.closest?.('tr')?.dataset.id === fila, id), 'el foco vuelve a la fila');
  await celda(ada.page, id, 'core:lon').focus();
  await ada.page.keyboard.press('ArrowDown');
  igual(await enfocada(ada.page), `${filas[31]}|core:lon`, 'la flecha baja a la fila siguiente');
});

await revisar('un PDF subido en el mismo detalle con el panel abierto llega a su terreno', async () => {
  const id = filas[20];
  const d = await abrirDetalle(ada, id);
  await abrirPanel(ada, d);
  const p = d.locator('.archivos-detalle[data-tipo="pdf"]');
  const [selector] = await Promise.all([ada.page.waitForEvent('filechooser'), p.locator('.archivos-elegir').click()]);
  await selector.setFiles({ name: 'Avalúo ficticio.pdf', buffer: readFileSync(F.pdf), mimeType: 'application/pdf' });
  await hasta(async () => /guardado/i.test(await p.locator('.archivos-subidas li').first().innerText().catch(() => '')),
    'la subida del detalle no terminó', 60000);
  await cerrarDetalle(d);
  const t = (await llamar(ada.page, 'GET', `/api/inventario/terrenos/${id}`)).datos.terreno;
  igual(t.archivos.pdf_total, 1, 'el PDF quedó en su terreno');
});

if (SHOTS) {
  await revisar('captura del panel', async () => {
    const d = await abrirDetalle(ada, filas[2]);
    const panel = await abrirPanel(ada, d);
    if (!CONECTADO) {
      await panel.getByRole('button', { name: 'Campos sin información' }).click();
      await respuestas(panel).first().waitFor();
      await panel.getByRole('button', { name: 'Resumir el terreno' }).click();
      await hasta(async () => (await respuestas(panel).count()) === 2);
    }
    await panel.scrollIntoViewIfNeeded();
    await ada.page.screenshot({ path: join(SHOTS, 'panel.png') });
    await cerrarDetalle(d);
  });
}

await revisar('sin errores de página', async () => {
  for (const s of sesiones) igual(s.errores, [], `errores de ${s.usuario}`);
});

await navegador.close();
servidor.kill('SIGTERM');
rmSync(CARPETA, { recursive: true, force: true });
console.log(fallos ? `\n${fallos} comprobación(es) fallaron` : `\ntodo bien${omitidas ? ` (${omitidas} omitidas)` : ''}`);
process.exit(fallos ? 1 : 0);

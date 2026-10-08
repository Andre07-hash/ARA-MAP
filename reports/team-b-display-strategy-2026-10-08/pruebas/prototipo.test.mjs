/* Checks for the display-strategy prototype (not application tests).
 *
 *   B2_DIR=<git archive 5d8e2dc> CASOS_DIR=<generar_casos.py output> \
 *     node --test reports/team-b-display-strategy-2026-10-08/pruebas/
 *
 * 1. preparar.js accepts/rejects exactly what B-2's cuerpoLeaflet does, on
 *    the B-2 fixture, the generated limit cases and targeted mutations.
 * 2. Sliced preparation (tiny budgets, fake clock) equals one-shot output.
 * 3. Planner cancellation and the cache's byte bound.
 */

import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';

const B2 = process.env.B2_DIR;
const CASOS = process.env.CASOS_DIR;
if (!B2 || !CASOS) throw new Error('set B2_DIR and CASOS_DIR (see the report)');

const aqui = path.dirname(new URL(import.meta.url).pathname);
const proto = await import(pathToFileURL(path.join(aqui, '..', 'prototipo', 'preparar.js')));
const { crearCache, crearPlanificador } = await import(
  pathToFileURL(path.join(aqui, '..', 'prototipo', 'planificador.js')));
const b2 = await import(pathToFileURL(path.join(B2, 'web', 'lib', 'geometria.js')));

const clon = (v) => structuredClone(v);

function cuerposDePrueba() {
  const lista = [];
  const fixture = JSON.parse(readFileSync(path.join(B2, 'tests/js/fixtures/geometria/contornos.json')));
  for (const fila of fixture.filas) {
    if (fila.geometria) lista.push({ nombre: `fixture ${fila.id}`, d: fila.geometria, c: fixture.cuerpos[fila.geometria.id] });
  }
  for (const nombre of ['circulo-100k', 'multiparte-20000', 'grande-mas-19999', 'denso-grande-mas-19999']) {
    const archivo = path.join(CASOS, `${nombre}.json`);
    if (!existsSync(archivo)) throw new Error(`missing ${archivo}: run generar_casos.py`);
    const { descriptor, cuerpo } = JSON.parse(readFileSync(archivo));
    lista.push({ nombre, d: descriptor, c: cuerpo });
  }
  return lista;
}

/** Mutations of a valid body; each name says what it breaks (or keeps valid). */
function mutaciones(d, c) {
  const m = [];
  const con = (nombre, f, dd = d) => { const cc = clon(c); const d2 = clon(dd); f(cc, d2); m.push({ nombre, d: d2, c: cc }); };
  con('desplazada +2 grados', (cc) => { cc.geojson.coordinates[0][0][1][0] += 2; });
  con('anillo colapsado', (cc) => { const p = cc.geojson.coordinates[0][0][0]; cc.geojson.coordinates[0][0] = [p, p, p, p].map((q) => [...q]); });
  con('sin punto de cierre', (cc) => { cc.geojson.coordinates[0][0].pop(); cc.geojson.coordinates[0][0].push([...cc.geojson.coordinates[0][0][1]]); });
  con('posicion no arreglo', (cc) => { cc.geojson.coordinates[0][0][1] = 'x'; });
  con('NaN', (cc) => { cc.geojson.coordinates[0][0][1][1] = NaN; });
  con('anillo de 3', (cc) => { cc.geojson.coordinates[0][0] = cc.geojson.coordinates[0][0].slice(0, 3); });
  con('poligono vacio', (cc) => { cc.geojson.coordinates.push([]); });
  con('tipo Polygon', (cc) => { cc.geojson.type = 'Polygon'; });
  con('coordenadas vacias', (cc) => { cc.geojson.coordinates = []; });
  con('bbox distinta del descriptor', (cc) => { cc.bbox = [...cc.bbox]; cc.bbox[2] += 0.01; });
  con('caja mayor que las conchas', (cc, dd) => { cc.bbox[2] += 0.01; dd.bbox[2] += 0.01; });
  con('tolerancia dentro', (cc, dd) => { cc.bbox[2] += 5e-10; dd.bbox[2] += 5e-10; });
  con('tolerancia fuera', (cc, dd) => { cc.bbox[2] += 3e-9; dd.bbox[2] += 3e-9; });
  con('descriptor no utilizable', (_cc, dd) => { dd.utilizable = false; });
  con('punto interior fuera', (_cc, dd) => { dd.punto_interior = { type: 'Point', coordinates: [dd.bbox[0] - 1, dd.bbox[1]] }; });
  con('hueco fuera de la caja', (cc) => {
    const [w, s] = cc.bbox; cc.geojson.coordinates[0].push([[w - 1, s], [w - 0.9, s], [w - 0.9, s + 0.1], [w - 1, s]]);
  });
  con('hueco valido', (cc) => {
    const r = cc.geojson.coordinates[0][0]; const xs = r.map((p) => p[0]); const ys = r.map((p) => p[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2; const cy = (Math.min(...ys) + Math.max(...ys)) / 2; const e = 1e-5;
    cc.geojson.coordinates[0].push([[cx - e, cy - e], [cx + e, cy - e], [cx + e, cy + e], [cx - e, cy - e]]);
  });
  return m;
}

function comparar(d, c) {
  const mapa = new Map([[d.id, c]]);
  const esperado = b2.cuerpoLeaflet(d, mapa);
  const obtenido = proto.prepararAhora(d, mapa);
  assert.equal(obtenido.estado, esperado.estado);
  if (esperado.estado === 'cargado') {
    assert.equal(obtenido.posiciones, esperado.posiciones);
    assert.deepEqual(obtenido.cajaMayor, esperado.cajaMayor);
    assert.equal(obtenido.partes, esperado.partes.length);
    assert.equal(obtenido.anillos, esperado.partes.reduce((a, p) => a + p.length, 0));
    // Every position kept, in order: world coordinates invert to the input.
    let i = 0;
    for (const parte of c.geojson.coordinates) for (const anillo of parte) for (const [lon] of anillo) {
      assert.ok(Math.abs(proto.mundoX(lon) - obtenido.x[i]) === 0);
      i += 1;
    }
    assert.equal(i, obtenido.posiciones);
  }
  return esperado.estado;
}

test('constants equal B-2', () => {
  assert.equal(proto.MAX_POSICIONES_CUERPO, b2.MAX_POSICIONES_CUERPO);
  assert.equal(proto.TOLERANCIA_GRADOS, b2.TOLERANCIA_GRADOS);
});

test('same verdict as cuerpoLeaflet on fixtures, limit cases and mutations', () => {
  const estados = {};
  for (const { nombre, d, c } of cuerposDePrueba()) {
    estados[nombre] = comparar(d, c);
    if (nombre.startsWith('fixture') || nombre === 'circulo-100k') {
      for (const mm of mutaciones(d, c)) estados[`${nombre} / ${mm.nombre}`] = comparar(mm.d, mm.c);
    }
  }
  // Missing body and a non-Map are "no_disponible" in both.
  const { d } = cuerposDePrueba()[0];
  assert.equal(proto.prepararAhora(d, new Map()).estado, b2.cuerpoLeaflet(d, new Map()).estado);
  assert.equal(proto.prepararAhora(d, null).estado, b2.cuerpoLeaflet(d, null).estado);
  const valores = Object.values(estados);
  assert.ok(valores.includes('cargado') && valores.includes('invalido'));
  console.log(`  ${Object.keys(estados).length} bodies compared:`,
              valores.filter((v) => v === 'cargado').length, 'cargado,',
              valores.filter((v) => v === 'invalido').length, 'invalido');
});

test('over the position limit is invalid in both', () => {
  const n = 100_001;
  const anillo = Array.from({ length: n - 1 }, (_, k) => [-100 + 0.01 * Math.cos(k / n * 6.28), 20 + 0.01 * Math.sin(k / n * 6.28)]);
  anillo.push([...anillo[0]]);
  const xs = anillo.map((p) => p[0]); const ys = anillo.map((p) => p[1]);
  const bbox = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  const d = { id: 'g', archivo_version_id: 'v', utilizable: true, bbox, punto_interior: { type: 'Point', coordinates: [-100, 20] } };
  const c = { geojson: { type: 'MultiPolygon', coordinates: [[anillo]] }, bbox };
  assert.equal(comparar(d, c), 'invalido');
});

test('sliced preparation equals one-shot preparation', () => {
  const { d, c } = cuerposDePrueba().find((x) => x.nombre === 'grande-mas-19999');
  const mapa = new Map([[d.id, c]]);
  const completo = proto.prepararAhora(d, mapa);
  let reloj = 0;
  const p = proto.crearPreparacion(d, mapa, () => { reloj += 1; return reloj; });
  let pasos = 0;
  let r = null;
  while (r === null) { r = p.paso(1); pasos += 1; }
  assert.ok(pasos > 50, `expected many slices, got ${pasos}`);
  for (const k of ['estado', 'posiciones', 'partes', 'anillos']) assert.equal(r[k], completo[k]);
  assert.deepEqual(r.cajaMayor, completo.cajaMayor);
  for (const k of ['x', 'y', 'inicioAnillo', 'inicioParte', 'cajasParte']) assert.deepEqual(r[k], completo[k]);
});

test('planner: shared job, cancellation, no late result', async () => {
  const { d, c } = cuerposDePrueba().find((x) => x.nombre === 'circulo-100k');
  const plan = crearPlanificador();
  const recibidos = [];
  plan.pedir(d, new Map([[d.id, c]]), (r) => recibidos.push(['a', r.estado]));
  plan.pedir(d, new Map([[d.id, c]]), (r) => recibidos.push(['b', r.estado]));
  assert.equal(plan.pendientes, 1);
  await new Promise((ok) => setTimeout(ok, 400));
  assert.deepEqual(recibidos, [['a', 'cargado'], ['b', 'cargado']]);
  plan.pedir(d, new Map([[d.id, c]]), (r) => recibidos.push(['c', r.estado]));
  plan.conservarSolo(new Set());                 // filter/reset: nobody needs it
  await new Promise((ok) => setTimeout(ok, 200));
  assert.equal(recibidos.length, 2);
  assert.equal(plan.pendientes, 0);
  assert.ok(plan.metricas.porcionMaxMs < 30, `slice ${plan.metricas.porcionMaxMs} ms`);
  plan.detener();
  plan.pedir(d, new Map([[d.id, c]]), (r) => recibidos.push(['d', r.estado]));
  await new Promise((ok) => setTimeout(ok, 100));
  assert.equal(recibidos.length, 2);             // stopped: nothing runs after teardown
});

test('cache: LRU within a byte budget, checked against the descriptor bbox', () => {
  const casos = cuerposDePrueba().filter((x) => !x.nombre.startsWith('fixture'));
  const preparados = casos.map(({ d, c }) => [d, proto.prepararAhora(d, new Map([[d.id, c]]))]);
  const unCuerpo = proto.bytesDe(preparados[0][1]);
  const cache = crearCache(Math.floor(unCuerpo * 2.5));
  for (const [d, p] of preparados) cache.guardar(d, p);
  assert.ok(cache.bytes <= Math.floor(unCuerpo * 2.5));
  assert.ok(cache.tamano <= 2);
  assert.equal(cache.obtener(preparados[0][0]), null);     // oldest evicted
  const [dUltimo, pUltimo] = preparados.at(-1);
  assert.equal(cache.obtener(dUltimo), pUltimo);
  assert.equal(cache.obtener({ ...dUltimo, bbox: [0, 0, 1, 1] }), null);   // other descriptor
  cache.vaciar();
  assert.equal(cache.bytes, 0);
});

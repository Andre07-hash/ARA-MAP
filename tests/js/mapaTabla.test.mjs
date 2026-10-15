/* The tables' map rules (web/lib/mapaTabla.js). Run with: node --test tests/js/mapaTabla.test.mjs
 * Fictional terrains only. */

import test from "node:test";
import assert from "node:assert/strict";

import { PRICE_RAMP, priceBreaks } from "../../web/lib/colors.js";
import { activeCount, deriveOptions, EMPTY_FILTERS, matches } from "../../web/lib/filters.js";
import {
  camposDeFicha, CAMPOS_DE_FICHA, colorDeFila, conteoDeUbicacion, filaDeMapa, filtrarMapa, FILTROS_MAPA,
  personalizadasDeFicha, ubicacionDeFicha,
} from "../../web/lib/mapaTabla.js";

const GRIS = "#9a9892";
const CONTORNO = {
  id: "g-ficticia", archivo_version_id: "v-ficticia", utilizable: true,
  bbox: [-110.1, 29.0, -110.0, 29.1], punto_interior: { type: "Point", coordinates: [-110.05, 29.05] },
};

let n = 0;
function registro(draft = {}, extra = {}) {
  n += 1;
  return {
    id: `t-${n}`, version: 1, base_id: "b-uno",
    draft: { terreno: `Lote Ficticio ${n}`, estado: "Sonora", municipio: "Hermosillo", ...draft },
    custom: {}, archivos: { pdf_total: 0, pdf_recientes: [], kmz: null }, ...extra,
  };
}

test("a row with an active boundary and no X/Y is located; X/Y alone too; neither is not", () => {
  const contorno = filaDeMapa(registro({}, { ubicacion: { geometria: CONTORNO } }));
  const punto = filaDeMapa(registro({ lat: 29.1, lon: -110.9 }));
  const nada = filaDeMapa(registro());
  assert.equal(contorno.ubicado, true);
  assert.equal(contorno.lat, undefined, "no X/Y copied from the boundary");
  assert.equal(punto.ubicado, true);
  assert.equal(nada.ubicado, false);
  assert.deepEqual(conteoDeUbicacion([contorno, punto, nada]), { ubicados: 2, sinUbicacion: 1 });
  // "Solo con ubicación" keeps the boundary row although it has no X/Y.
  const { visibles } = filtrarMapa([contorno, punto, nada], { ...FILTROS_MAPA, soloUbicados: true });
  assert.deepEqual(visibles.map((f) => f.id), [contorno.id, punto.id]);
});

test("search, states, municipalities and the three ranges narrow the set", () => {
  const filas = [
    registro({ terreno: "Rancho Uno", estado: "Sonora", municipio: "Hermosillo", superficie_m2: 1000, asking_price: 100, asking_m2: 10 }),
    registro({ terreno: "Rancho Dos", estado: "Sonora", municipio: "Cajeme", superficie_m2: 5000, asking_price: 900, asking_m2: 30 }),
    registro({ terreno: "Parcela Tres", estado: "Jalisco", municipio: "Zapopan", superficie_m2: 20000, asking_price: null, asking_m2: null }),
  ].map(filaDeMapa);
  const ids = (f) => filtrarMapa(filas, { ...FILTROS_MAPA, ...f }).visibles.map((t) => t.terreno);
  assert.deepEqual(ids({ busqueda: "rancho" }), ["Rancho Uno", "Rancho Dos"]);
  assert.deepEqual(ids({ estados: ["Jalisco"] }), ["Parcela Tres"]);
  assert.deepEqual(ids({ municipios: ["Cajeme"] }), ["Rancho Dos"]);
  assert.deepEqual(ids({ superficieMin: 2000 }), ["Rancho Dos", "Parcela Tres"]);
  assert.deepEqual(ids({ precioMax: 500 }), ["Rancho Uno"], "a missing price is not zero");
  assert.deepEqual(ids({ unitarioMin: 20 }), ["Rancho Dos"]);
  assert.deepEqual(ids({}), ["Rancho Uno", "Rancho Dos", "Parcela Tres"]);
});

test("the terrain type is a local map filter over the stored values; Limpiar clears it", () => {
  const filas = [
    registro({ terreno: "Rancho Uno", tipo_terreno: "Industrial" }),
    registro({ terreno: "Rancho Dos", tipo_terreno: "Habitacional" }),
    registro({ terreno: "Parcela Tres", tipo_terreno: null }),
    registro({ terreno: "Parcela Cuatro", tipo_terreno: "industrial" }),
  ].map(filaDeMapa);
  const ids = (f) => filtrarMapa(filas, { ...FILTROS_MAPA, ...f }).visibles.map((t) => t.terreno);
  assert.deepEqual(FILTROS_MAPA.tipos, [], "starts without a type");
  assert.deepEqual(ids({}), ["Rancho Uno", "Rancho Dos", "Parcela Tres", "Parcela Cuatro"]);
  // Values are compared as stored: no folding, no invented classes; a row without a type is left out.
  assert.deepEqual(ids({ tipos: ["Industrial"] }), ["Rancho Uno"]);
  assert.deepEqual(ids({ tipos: ["Industrial", "Habitacional"] }), ["Rancho Uno", "Rancho Dos"]);
  assert.deepEqual(ids({ tipos: ["Industrial"], busqueda: "parcela" }), [], "combined with the other filters");
  assert.equal(activeCount({ ...FILTROS_MAPA, tipos: ["Industrial"] }), 1, "counted as one active filter");
  assert.equal(activeCount(FILTROS_MAPA), 0, "Limpiar (FILTROS_MAPA) leaves no type");
  // The rail's options are counted from the set's own values.
  assert.deepEqual(deriveOptions(filas).tipos, [
    { valor: "Habitacional", conteo: 1 }, { valor: "industrial", conteo: 1 }, { valor: "Industrial", conteo: 1 },
  ]);
});

test("the other screens' filters are unchanged: no type in EMPTY_FILTERS, and absent means no filter", () => {
  assert.equal("tipos" in EMPTY_FILTERS, false);
  const fila = filaDeMapa(registro({ tipo_terreno: "Industrial" }));
  assert.equal(matches(fila, EMPTY_FILTERS), true);
  assert.equal(activeCount(EMPTY_FILTERS), 0);
});

test("colour thresholds come from the whole set, so filtering never changes a colour", () => {
  const filas = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((v) => filaDeMapa(registro({ asking_m2: v * 100, moneda: "MXN" })));
  const todo = filtrarMapa(filas);
  const filtrado = filtrarMapa(filas, { ...FILTROS_MAPA, unitarioMin: 800 });
  assert.equal(filtrado.visibles.length, 3);
  assert.deepEqual(filtrado.breaks, todo.breaks);
  assert.deepEqual(todo.breaks, priceBreaks(filas.map((f) => f.asking_m2)));
  const caro = filas[9];
  assert.equal(colorDeFila(caro, filtrado.breaks), colorDeFila(caro, todo.breaks));
  assert.equal(colorDeFila(caro, todo.breaks), PRICE_RAMP.at(-1));
  assert.equal(colorDeFila(filas[0], todo.breaks), PRICE_RAMP[0]);
});

test("fewer than five prices per m² and missing prices keep the fallback", () => {
  const pocos = [10, 20, 30, 40].map((v) => filaDeMapa(registro({ asking_m2: v, moneda: "MXN" })));
  const r = filtrarMapa(pocos);
  assert.equal(r.breaks, null);
  assert.equal(colorDeFila(pocos[0], r.breaks), GRIS);

  const conFaltante = [...[1, 2, 3, 4, 5].map((v) => filaDeMapa(registro({ asking_m2: v, moneda: "MXN" }))),
    filaDeMapa(registro({ asking_m2: null }))];
  const f = filtrarMapa(conFaltante);
  assert.notEqual(f.breaks, null);
  assert.equal(colorDeFila(conFaltante[5], f.breaks), GRIS, "a missing price is grey, not the cheapest step");
});

test("every price shares one scale and one filter, whatever currency a row recorded", () => {
  const filas = [...[1, 2, 3, 4, 5].map((v) => filaDeMapa(registro({ asking_m2: v, moneda: "MXN" }))),
    filaDeMapa(registro({ asking_m2: 6, moneda: null }))];
  const m = filtrarMapa(filas, { ...FILTROS_MAPA, unitarioMin: 4 });
  assert.notEqual(m.breaks, null);
  assert.equal(m.visibles.length, 3);
});

test("the record lists the table's fields as stored, with comments", () => {
  const r = registro({ tipo_terreno: "Rústico", superficie_m2: 12345.5, asking_price: null, notas_internas: "Línea 1\nLínea 2" });
  const campos = Object.fromEntries(camposDeFicha(r));
  assert.deepEqual(CAMPOS_DE_FICHA.map((c) => c.etiqueta), ["Tipo de terreno", "Estado", "Municipio", "Superficie",
    "HA", "Afectaciones %", "Asking price", "Asking $/m2", "Comentarios"]);
  assert.equal(campos["Tipo de terreno"], "Rústico");
  assert.equal(campos.Superficie, "12,345.5", "every stored digit, with thousands commas");
  assert.equal(campos["Asking price"], "—", "missing, not zero");
  assert.equal(campos.Comentarios, "Línea 1\nLínea 2");
});

test("custom columns are the terrain's own base's, without retired ones", () => {
  const r = registro({}, { custom: { "custom:a": "Visita pendiente", "custom:b": 7, "custom:z": "de otra base" } });
  const defs = [
    { id: "custom:a", nombre: "Seguimiento", tipo: "texto", retirada: false },
    { id: "custom:b", nombre: "Prioridad", tipo: "numero", retirada: false },
    { id: "custom:c", nombre: "Vieja", tipo: "texto", retirada: true },
    { id: "custom:d", nombre: "Vacía", tipo: "texto", retirada: false },
  ];
  assert.deepEqual(personalizadasDeFicha(r, defs), [["Seguimiento", "Visita pendiente"], ["Prioridad", "7"], ["Vacía", "—"]]);
  assert.deepEqual(personalizadasDeFicha(r, []), []);
});

test("the location says what places it and shows the stored X/Y, never the boundary's point", () => {
  const contorno = ubicacionDeFicha(registro({}, { ubicacion: { geometria: CONTORNO } }));
  assert.equal(contorno.modo, "geometria");
  assert.match(contorno.texto, /contorno KMZ activo/);
  assert.deepEqual([contorno.x, contorno.y], ["—", "—"]);
  assert.doesNotMatch(contorno.texto, /círculo|sin coordenadas/i);

  const punto = ubicacionDeFicha(registro({ lat: 29.1, lon: -110.9 }));
  assert.equal(punto.modo, "punto");
  assert.deepEqual([punto.x, punto.y], ["29.1", "-110.9"], "X is latitude, Y is longitude");

  const ambos = ubicacionDeFicha(registro({ lat: 29.2, lon: -110.8 }, { ubicacion: { geometria: CONTORNO } }));
  assert.equal(ambos.modo, "geometria");
  assert.deepEqual([ambos.x, ambos.y], ["29.2", "-110.8"]);

  assert.match(ubicacionDeFicha(registro()).texto, /ni coordenadas X\/Y/);
  assert.match(ubicacionDeFicha(registro({ lat: -29, lon: 110 })).texto, /no son coordenadas válidas/);
});

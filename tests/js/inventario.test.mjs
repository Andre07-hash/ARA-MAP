/* Inventory contract helpers against the shared contract-v1 fixtures.
 * Run with: node --test tests/js/inventario.test.mjs */

import assert from "node:assert/strict";
import test from "node:test";

import {
  analizarConflicto, avisoDisponibilidadPendiente, cambiosDelFormulario, consultaDe,
  consultaDePagina, contarFiltros, crearIntento, erroresDeCampo, estadoPublicacion,
  estadoUbicacion, itemDeInventario, itemPublico, leerNumero, normalizarEvento,
  opcionesDeFacetas, pickPublic, PUBLIC_FIELDS, reunirPaginas, textosIniciales,
} from "../../web/lib/inventario.js";
import { fixture, paginate, publicTerrains } from "./fixtures/inventario/index.mjs";

const SENTINELA = "SENTINELA-PRIVADO-7731";

/* ---------------------------------------------------------- public fields */

test("the public projection keeps exactly the contract allowlist and no private text", () => {
  const { terreno } = fixture("internal-terrain-draft");
  const publico = pickPublic({ ...terreno.draft, ...terreno, contacto: "x" });
  assert.deepEqual(Object.keys(publico).sort(), [...PUBLIC_FIELDS].sort());
  assert.ok(!JSON.stringify(publico).includes(SENTINELA));
});

test("a public row drops any field outside the allowlist, even if the server sent one", () => {
  const { terreno } = fixture("public-terrain");
  const fila = itemPublico({ ...terreno, contacto: SENTINELA, notas_internas: SENTINELA });
  assert.ok(!JSON.stringify(fila).includes(SENTINELA));
  assert.equal(fila.price_on_request, true);
  assert.equal(fila.asking_price, null);       // null stays null, never 0
  assert.equal(fila.ubicado, true);
});

/* ------------------------------------------------------- lifecycle labels */

test("publication status uses the agreed Spanish labels", () => {
  const borrador = fixture("internal-terrain-draft").terreno;
  const pendiente = fixture("internal-terrain-published-pending").terreno;
  assert.equal(estadoPublicacion(borrador).etiqueta, "Borrador · No publicado");
  assert.equal(estadoPublicacion(pendiente).etiqueta, "Publicado · Cambios pendientes");
  assert.equal(estadoPublicacion({ ...pendiente, has_pending_changes: false }).etiqueta, "Publicado");
  assert.equal(estadoPublicacion({ ...pendiente, has_pending_changes: false, public_visible: false }).etiqueta,
    "Fuera del catálogo · Vendido");
  assert.equal(estadoPublicacion({ ...borrador, publication_state: "unpublished" }).etiqueta, "No publicado");
  assert.equal(estadoPublicacion({ ...borrador, publication_state: "archived" }).etiqueta, "Archivado");
});

test("a saved 'sold' draft over a live publication is flagged as not yet public", () => {
  const pendiente = fixture("internal-terrain-published-pending").terreno;
  assert.match(avisoDisponibilidadPendiente(pendiente), /Vendido.*sigue mostrando la versión publicada/);
  assert.equal(avisoDisponibilidadPendiente(fixture("internal-terrain-draft").terreno), null);
});

test("inventory rows flatten the draft and classify location like the server", () => {
  const fila = itemDeInventario(fixture("internal-terrain-unplaced").terreno);
  assert.equal(fila.ubicacion, "sin_dato");
  assert.equal(fila.ubicado, false);
  assert.equal(estadoUbicacion(-103.3, 20.6), "invalida");   // X/Y swapped
  assert.equal(estadoUbicacion(20.6736, -103.344), "valida");
  assert.equal(estadoUbicacion(40.7, -74), "invalida");      // outside Mexico
});

/* ---------------------------------------------------------------- queries */

test("geography is repeated parameters; price only travels with its currency", () => {
  const sinMoneda = consultaDe({ estados: ["Jalisco", "Nuevo León"], municipios: ["Zapopan"],
    precioMin: 100, busqueda: "  ánimas " }, "catalogo");
  assert.deepEqual(sinMoneda.getAll("estado"), ["Jalisco", "Nuevo León"]);
  assert.deepEqual(sinMoneda.getAll("municipio"), ["Zapopan"]);
  assert.equal(sinMoneda.get("q"), "ánimas");
  assert.equal(sinMoneda.has("price_min"), false);
  assert.equal(sinMoneda.has("moneda"), false);

  const conMoneda = consultaDe({ moneda: "USD", precioBase: "per_m2", precioMin: 100, superficieMax: 5000 }, "catalogo");
  assert.equal(conMoneda.get("moneda"), "USD");
  assert.equal(conMoneda.get("price_basis"), "per_m2");
  assert.equal(conMoneda.get("price_min"), "100");
  assert.equal(conMoneda.get("area_max_m2"), "5000");
});

test("internal-only filters never reach the public catalog query", () => {
  const filtros = { publicacion: "draft", disponibilidad: "sold", incluirArchivados: true };
  assert.equal(consultaDe(filtros, "catalogo").toString(), "");
  const interna = consultaDe(filtros, "inventario");
  assert.equal(interna.get("publication_state"), "draft");
  assert.equal(interna.get("availability"), "sold");
  assert.equal(interna.get("include_archived"), "true");
  assert.equal(contarFiltros(filtros, "catalogo"), 0);
  assert.equal(contarFiltros(filtros, "inventario"), 3);
});

test("a page query keeps the filters and adds the cursor and the maximum limit", () => {
  const q = new URLSearchParams(consultaDePagina(consultaDe({ estados: ["A", "B"] }), "abc"));
  assert.deepEqual(q.getAll("estado"), ["A", "B"]);
  assert.equal(q.get("cursor"), "abc");
  assert.equal(q.get("limit"), "250");
});

/* ------------------------------------------------------------- pagination */

async function reunir(items, limit) {
  const pedidas = [];
  const resultado = await reunirPaginas(async (cursor) => {
    pedidas.push(cursor);
    return paginate(items, { limit, cursor });
  });
  return { resultado, pedidas };
}

test("251 matching records assemble across the 250 page boundary with no gaps or repeats", async () => {
  const items = publicTerrains(251);
  const { resultado, pedidas } = await reunir(items, 250);
  assert.equal(pedidas.length, 2);
  assert.equal(resultado.terrenos.length, 251);
  assert.equal(new Set(resultado.terrenos.map((t) => t.id)).size, 251);
  assert.deepEqual(resultado.terrenos.map((t) => t.id), items.map((t) => t.id));
  assert.equal(resultado.totalServidor, 251);
});

test("the default 100-row page also assembles completely", async () => {
  const { resultado, pedidas } = await reunir(publicTerrains(251), 100);
  assert.equal(pedidas.length, 3);
  assert.equal(resultado.terrenos.length, 251);
});

test("facets come from the server's first page, for the whole candidate set", async () => {
  const { resultado } = await reunir(publicTerrains(251), 250);
  const opciones = opcionesDeFacetas(resultado.facets);
  assert.equal(opciones.estados.length, 4);
  assert.ok(opciones.municipios.some((o) => o.valor === "El Marqués"));
  assert.equal(opciones.estados[0].conteo, null);   // names only: no invented counts
});

test("a server that repeats a cursor is reported, not looped on", async () => {
  await assert.rejects(
    reunirPaginas(async () => ({ terrenos: [{ id: "a" }], total: 9, next_cursor: "a" })),
    /repitió una página/);
});

/* ------------------------------------------------------------------ forms */

test("numbers are read as typed in Mexico, and ambiguous commas are refused", () => {
  assert.deepEqual(leerNumero("1,200,000.50"), { valor: 1200000.5 });
  assert.deepEqual(leerNumero(" 122.5 "), { valor: 122.5 });
  assert.deepEqual(leerNumero("-103.3848"), { valor: -103.3848 });
  assert.deepEqual(leerNumero(""), { valor: null });
  assert.match(leerNumero("122,5").error, /punto decimal/);
  assert.match(leerNumero("abc").error, /número/);
});

test("an untouched form sends nothing; cents and unknown currency survive byte for byte", () => {
  const { draft } = fixture("internal-terrain-draft").terreno;
  const iniciales = textosIniciales(draft);
  assert.equal(iniciales.asking_m2, "122.5");
  assert.equal(iniciales.afectaciones_pct, "7");          // shown as a percentage
  assert.deepEqual(cambiosDelFormulario({ ...iniciales }, iniciales), { cambios: {}, errores: {} });

  const sinMoneda = textosIniciales({ ...draft, moneda: null, availability: null });
  assert.equal(sinMoneda.moneda, "");
  assert.equal(sinMoneda.availability, "unknown");
});

test("only edited fields are parsed and sent, in the server's units", () => {
  const { draft } = fixture("internal-terrain-draft").terreno;
  const iniciales = textosIniciales(draft);
  const { cambios, errores } = cambiosDelFormulario({
    ...iniciales, asking_price: "1,600,000", afectaciones_pct: "12.5", direccion: "  ",
    price_on_request: true,
  }, iniciales);
  assert.deepEqual(errores, {});
  assert.deepEqual(cambios, {
    asking_price: 1600000, afectaciones_pct: 0.125, direccion: null, price_on_request: true,
  });
});

test("half a coordinate pair saves as a draft (§9.1); a decimal comma is still refused", () => {
  const iniciales = textosIniciales({});
  const { cambios, errores } = cambiosDelFormulario({ ...iniciales, lat: "20.67" }, iniciales);
  assert.deepEqual(errores, {});
  assert.deepEqual(cambios, { lat: 20.67 });
  assert.match(cambiosDelFormulario({ ...iniciales, lat: "20,67" }, iniciales).errores.lat, /punto decimal/);
});

test("server field errors map onto form fields", () => {
  const { detalle } = fixture("error-422-validation");
  assert.deepEqual(Object.keys(erroresDeCampo(detalle)).sort(), ["lat", "moneda"]);
  assert.deepEqual(erroresDeCampo({ code: "x", fields: [{ field: "terreno", message: "Falta" }] }),
    { terreno: "Falta" });
  assert.deepEqual(erroresDeCampo(null), {});
});

/* --------------------------------------------------------------- conflict */

test("a conflict names what the other user changed and where both of us did", () => {
  const base = fixture("internal-terrain-draft").terreno.draft;
  const actual = fixture("error-409-conflict").detalle.terreno.draft;
  const mios = { asking_price: 1550000, terreno: "Lote Las Ánimas Norte" };
  const { delServidor, choques } = analizarConflicto(base, actual, mios);
  assert.deepEqual(delServidor.sort(), ["asking_price", "notas_internas"]);
  assert.deepEqual(choques, ["asking_price"]);
  // Typing the same value the other user saved is not a clash.
  assert.deepEqual(analizarConflicto(base, actual, { asking_price: 1600000 }).choques, []);
});

/* ------------------------------------------------------------ idempotency */

test("one create attempt keeps its key across retries; a changed body gets a new key", () => {
  let n = 0;
  const intento = crearIntento(() => `clave-${++n}`);
  const cuerpo = { terreno: "A", superficie_m2: 10 };
  const primera = intento.claveParaCuerpo(cuerpo);
  assert.equal(intento.claveParaCuerpo({ ...cuerpo }), primera);       // uncertain retry
  const cambiada = intento.claveParaCuerpo({ ...cuerpo, superficie_m2: 11 });
  assert.notEqual(cambiada, primera);                                  // never reused for another body
  intento.completar();
  assert.notEqual(intento.claveParaCuerpo(cuerpo), primera);           // a new logical create
});

/* ---------------------------------------------------------------- history */

test("history events normalise action, actor, time, confirmations and field changes", () => {
  const [e3, e2] = fixture("historial").eventos.map(normalizarEvento);
  assert.equal(e3.accion, "Guardó el borrador");
  assert.equal(e3.actor, "Ana Prueba");
  assert.deepEqual(e3.confirmados, ["Precio"]);
  assert.deepEqual(e3.cambios, [{ campo: "asking_m2", antes: 120, despues: 122.5 }]);
  assert.equal(e2.actor, "Beto Prueba");
  assert.equal(normalizarEvento(fixture("historial-page2").eventos[0]).accion, "Creó el borrador");
});

/* The employee table's rules, with no DOM: columns, cell values, list queries,
 * the per-row save queue and how an uncertain save is resolved.
 *
 * Nothing here converts or derives a value. A number keeps every digit it
 * was stored with; it is only written with thousands commas and its $ or %.
 * X is latitude and Y is longitude, written as they are; a missing value is
 * empty, never zero and never a default currency.
 */

import { leerNumero } from "./inventario.js";

export const VISTA_MAESTRA = "maestra";
export const VISTA_SIN_ASIGNAR = "sin_asignar";
export const LIMITES = Object.freeze([50, 100, 200]);   // the server's maximum is 200
export const LIMITE_INICIAL = 100;

/* The fourteen core columns, in the order of the team's spreadsheet. `campo`
 * is the stored field; the two file columns have none: they are mounts. */
export const COLUMNAS_BASICAS = Object.freeze([
  { id: "core:tipo_terreno", campo: "tipo_terreno", etiqueta: "Tipo de terreno", tipo: "texto", max: 100, orden: "tipo_terreno" },
  { id: "core:terreno", campo: "terreno", etiqueta: "Nombre de terreno", tipo: "texto", max: 200, orden: "terreno" },
  { id: "core:estado", campo: "estado", etiqueta: "Estado", tipo: "texto", max: 100, orden: "estado" },
  { id: "core:municipio", campo: "municipio", etiqueta: "Municipio", tipo: "texto", max: 100, orden: "municipio" },
  { id: "core:superficie_m2", campo: "superficie_m2", etiqueta: "Superficie", tipo: "numero", orden: "superficie_m2" },
  { id: "core:superficie_ha", campo: "superficie_ha", etiqueta: "HA", tipo: "numero" },
  { id: "core:afectaciones_pct", campo: "afectaciones_pct", etiqueta: "Afectaciones %", tipo: "numero", formato: "pct" },
  { id: "core:asking_price", campo: "asking_price", etiqueta: "Asking price", tipo: "numero", orden: "asking_price", formato: "precio" },
  { id: "core:asking_m2", campo: "asking_m2", etiqueta: "Asking $/m2", tipo: "numero", formato: "precio" },
  { id: "core:notas_internas", campo: "notas_internas", etiqueta: "Comentarios", tipo: "largo", max: 10000 },
  { id: "core:lat", campo: "lat", etiqueta: "X", ayuda: "X es la latitud", tipo: "numero", formato: "coordenada" },
  { id: "core:lon", campo: "lon", etiqueta: "Y", ayuda: "Y es la longitud", tipo: "numero", formato: "coordenada" },
  { id: "core:archivos", etiqueta: "Archivos", tipo: "archivo", archivo: "pdf" },
  { id: "core:kmz", etiqueta: "KMZ / KML", tipo: "archivo", archivo: "kmz" },
].map(Object.freeze));

const COLUMNA_BASE = Object.freeze({ id: "base", etiqueta: "Base", tipo: "base" });

export const esGlobal = (vista) => vista === VISTA_MAESTRA || vista === VISTA_SIN_ASIGNAR;

/**
 * The columns of a view. The global table adds Base and never shows custom
 * columns; a selected base shows its own live custom columns after the core.
 */
export function columnasDe(vista, definiciones = []) {
  if (esGlobal(vista)) return [...COLUMNAS_BASICAS, COLUMNA_BASE];
  return [...COLUMNAS_BASICAS, ...definiciones.filter((d) => !d.retirada).map((d) => ({
    id: d.id, etiqueta: d.nombre, tipo: d.tipo, opciones: d.opciones ?? [], custom: true,
    max: d.tipo === "texto" ? 2000 : undefined,
  }))];
}

export const esEditable = (columna) => Boolean(columna.campo || columna.custom);

/** The stored value of a cell (null when there is none). */
export function valorDe(terreno, columna) {
  if (columna.custom) return terreno.custom?.[columna.id] ?? null;
  if (columna.campo) return terreno.draft?.[columna.campo] ?? null;
  return null;
}

/** A number's text with thousands commas in its whole part; decimals untouched. */
const conComas = (texto) => texto.replace(/^(-?)(\d+)/, (_, signo, entero) =>
  signo + entero.replace(/\B(?=(\d{3})+(?!\d))/g, ","));

/** $ before a price (after a minus sign), % after a percentage. */
function conSigno(columna, texto) {
  if (columna.formato === "precio") return texto.startsWith("-") ? `-$${texto.slice(1)}` : `$${texto}`;
  if (columna.formato === "pct") return `${texto}%`;
  return texto;
}

/**
 * What a cell shows and what its editor starts with. A number column writes
 * the stored digits with commas and its sign; coordinates and other values
 * are shown exactly as stored.
 */
export function textoDe(valor, columna = null) {
  if (valor == null) return "";
  if (columna?.tipo !== "numero" || columna.formato === "coordenada" || typeof valor !== "number") {
    return String(valor);
  }
  return conSigno(columna, conComas(String(valor)));
}

/**
 * The editor's text while a number is being typed: commas and the column's
 * sign added as the person writes, the caret kept after the same digit.
 * Returns { texto, cursor }. Text with anything but digits, a point, a minus,
 * commas, spaces, $ or % is left exactly as typed, so the save shows "Escribe
 * un número." and keeps it instead of dropping a letter typed by mistake.
 */
export function escribirNumero(columna, texto, cursor = texto.length) {
  if (columna.formato === "coordenada" || /[^\d.,\s$%-]/.test(texto)) return { texto, cursor };
  const util = (c) => /[\d.-]/.test(c);
  const antes = [...texto.slice(0, cursor)].filter(util).length;
  let crudo = [...texto].filter(util).join("");
  const negativo = crudo.startsWith("-");
  crudo = crudo.replace(/-/g, "");
  const punto = crudo.indexOf(".");
  const entero = punto < 0 ? crudo : crudo.slice(0, punto);
  const decimales = punto < 0 ? null : crudo.slice(punto + 1).replace(/\./g, "");
  if (!negativo && entero === "" && decimales === null) return { texto: "", cursor: 0 };
  const cuerpo = (negativo ? "-" : "") + conComas(entero) + (decimales === null ? "" : `.${decimales}`);
  const salida = conSigno(columna, cuerpo);
  // The caret goes after as many digits, points and minus signs as were before it.
  let vistos = 0;
  let nuevo = columna.formato === "precio" && !negativo ? 1 : 0;   // after a leading $
  if (antes > 0) {
    for (let i = 0; i < salida.length; i += 1) {
      if (util(salida[i])) vistos += 1;
      if (vistos === antes) { nuevo = i + 1; break; }
    }
  }
  return { texto: salida, cursor: nuevo };
}

const FECHA = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Whether "AAAA-MM-DD" names a real calendar day. No timezone is involved. */
export function esFechaReal(texto) {
  const m = FECHA.exec(texto);
  if (!m) return false;
  const [a, mes, dia] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const d = new Date(Date.UTC(a, mes - 1, dia));
  d.setUTCFullYear(a);   // years below 100 are not 19xx
  return a >= 1 && d.getUTCMonth() === mes - 1 && d.getUTCDate() === dia;
}

/**
 * Typed text to the value to send: { valor } or { error }. Empty clears the
 * cell (null). The server validates again; this only spares a round trip.
 */
export function leerCelda(columna, texto) {
  const crudo = String(texto ?? "");
  if (columna.tipo === "numero") return leerNumero(crudo.replace(/%\s*$/, "").replace(/^(-?)\$/, "$1"));
  if (columna.tipo === "fecha") {
    const limpio = crudo.trim();
    if (limpio === "") return { valor: null };
    return esFechaReal(limpio) ? { valor: limpio } : { error: "Usa una fecha real con la forma AAAA-MM-DD." };
  }
  if (columna.tipo === "opcion") {
    if (crudo === "") return { valor: null };
    return columna.opciones.includes(crudo) ? { valor: crudo } : { error: "Elige una de las opciones." };
  }
  // The server single-spaces short text and trims long text; mirror it so an
  // unchanged cell is recognised as unchanged.
  const limpio = columna.tipo === "largo" || columna.custom ? crudo.trim() : crudo.split(/\s+/).filter(Boolean).join(" ");
  if (columna.max && limpio.length > columna.max) return { error: `Admite hasta ${columna.max} caracteres.` };
  return { valor: limpio === "" ? null : limpio };
}

/* Fields the table fills in by itself (owner's decision, 2026-10-16): m² ⇄ HA
 * and total price ⇄ price per m², each only while that field is empty, so a
 * value someone entered or imported is never overwritten. */
const M2_POR_HA = 10000;
const redondear = (n, decimales) => Number(n.toFixed(decimales));
const vacio = (v) => v === null || v === undefined || v === "";
const REGLAS = [
  ["superficie_ha", ["superficie_m2"], (d) => d.superficie_m2 > 0 && redondear(d.superficie_m2 / M2_POR_HA, 4)],
  ["superficie_m2", ["superficie_ha"], (d) => d.superficie_ha > 0 && redondear(d.superficie_ha * M2_POR_HA, 2)],
  ["asking_m2", ["superficie_m2", "asking_price"], (d) => d.superficie_m2 > 0
    && Number.isFinite(d.asking_price) && redondear(d.asking_price / d.superficie_m2, 2)],
  ["asking_price", ["superficie_m2", "asking_m2"], (d) => d.superficie_m2 > 0
    && Number.isFinite(d.asking_m2) && redondear(d.asking_m2 * d.superficie_m2, 2)],
];

/**
 * What saving `valor` in `campo` fills in by itself on a row whose stored
 * values are `draft`: { campo: valor } of the empty fields computed from the
 * edited one (or from one computed here). Clearing a cell computes nothing.
 */
export function calculados(draft, campo, valor) {
  if (!Number.isFinite(valor)) return {};
  const d = { ...draft, [campo]: valor };
  const nuevos = new Set([campo]);
  const extra = {};
  // Twice, so HA typed into a row with a price also yields the price per m².
  for (let vuelta = 0; vuelta < 2; vuelta += 1) {
    for (const [destino, desde, calcular] of REGLAS) {
      if (nuevos.has(destino) || !vacio(d[destino]) || !desde.some((c) => nuevos.has(c))) continue;
      const v = calcular(d);
      // A zero is never written: a missing price stays without a price.
      if (Number.isFinite(v) && v > 0) { d[destino] = v; extra[destino] = v; nuevos.add(destino); }
    }
  }
  return extra;
}

/** The PATCH body for one cell, with what it fills in by itself (see calculados). */
export function cuerpoDeCelda(columna, valor, expectedVersion, draft = {}) {
  return columna.custom
    ? { expected_version: expectedVersion, custom: { [columna.id]: valor } }
    : { expected_version: expectedVersion,
        changes: { ...calculados(draft, columna.campo, valor), [columna.campo]: valor } };
}

/* ------------------------------------------------------------------ lists */

export const CONSULTA_VACIA = Object.freeze({
  q: "", sort: "id",
  // Several states, municipalities and types at once.
  estado: Object.freeze([]), municipio: Object.freeze([]), tipo_terreno: Object.freeze([]),
  area_min_m2: "", area_max_m2: "",   // the area range, as typed
  limit: LIMITE_INICIAL,
});

export const ORDENES = Object.freeze([
  ["id", "Sin ordenar"],
  ...COLUMNAS_BASICAS.filter((c) => c.orden).map((c) => [c.orden, c.etiqueta]),
  ["updated_at", "Última edición"],
]);

/** The query string of one page. Everything is the server's to filter. */
/** The map's pages: the server's largest, without what only the grid shows. */
export const PAGINA_MAPA = 1000;

/** ``mapa``: one of the map's light pages (mapa=1) instead of a grid page. */
export function consultaDeLista(vista, consulta, cursor = null, { mapa = false } = {}) {
  const c = { ...CONSULTA_VACIA, ...consulta };
  const q = new URLSearchParams();
  if (c.q.trim()) q.set("q", c.q.trim());
  // Several values are one repeated parameter; the server matches any of them.
  for (const campo of ["estado", "municipio", "tipo_terreno"]) {
    for (const valor of [].concat(c[campo] || [])) q.append(campo, valor);
  }
  for (const campo of ["area_min_m2", "area_max_m2"]) if (c[campo]) q.set(campo, c[campo]);
  if (vista === VISTA_SIN_ASIGNAR) q.set("base", VISTA_SIN_ASIGNAR);
  if (c.sort && c.sort !== "id") q.set("sort", c.sort);
  if (mapa) q.set("mapa", "1");
  q.set("limit", String(mapa ? PAGINA_MAPA : LIMITES.includes(c.limit) ? c.limit : LIMITE_INICIAL));
  if (cursor) q.set("cursor", cursor);
  return q.toString();
}

/** The API path of a view's list (and of its blank create). */
export const rutaDeLista = (vista) =>
  (esGlobal(vista) ? "/inventario/terrenos" : `/maestra/bases/${encodeURIComponent(vista)}/terrenos`);

/* ------------------------------------------------------------ save queue */

/**
 * Saves of one row run one after another, each built when its turn comes so
 * it carries the version the previous one returned. Rows do not wait for each
 * other. A task's failure does not stop the row's later tasks.
 */
export function crearCola() {
  const colas = new Map();
  return {
    enFila(id, tarea) {
      const previa = colas.get(id) ?? Promise.resolve();
      const turno = previa.then(tarea, tarea);
      const fin = turno.catch(() => {});
      colas.set(id, fin);
      fin.then(() => { if (colas.get(id) === fin) colas.delete(id); });
      return turno;
    },
    pendientes: () => colas.size,
    olvidar() { colas.clear(); },
  };
}

/**
 * A save whose response never arrived. Given what was sent and the row the
 * server holds now, say what happened instead of sending it again blindly:
 *   "guardado"     it is there: the version moved by one and the value is ours
 *   "sin_guardar"  the row is as we left it: sending again is safe
 *   "conflicto"    something else changed it: the person decides
 */
export function resolverIncierto(columna, enviado, versionEnviada, actual) {
  const igual = (a, b) => (a ?? null) === (b ?? null);
  if (actual.version === versionEnviada) return "sin_guardar";
  if (actual.version === versionEnviada + 1 && igual(valorDe(actual, columna), enviado)) return "guardado";
  return "conflicto";
}

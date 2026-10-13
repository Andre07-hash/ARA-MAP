/* The employee table's rules, with no DOM: columns, cell values, list queries,
 * the per-row save queue and how an uncertain save is resolved.
 *
 * Nothing here converts or derives a value. A number is shown as stored and
 * sent as typed; X is latitude and Y is longitude; a missing value is empty,
 * never zero and never a default currency.
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
  { id: "core:afectaciones_pct", campo: "afectaciones_pct", etiqueta: "Afectaciones %", tipo: "numero" },
  { id: "core:asking_price", campo: "asking_price", etiqueta: "Asking price", tipo: "numero", orden: "asking_price" },
  { id: "core:asking_m2", campo: "asking_m2", etiqueta: "Asking $/m2", tipo: "numero" },
  { id: "core:notas_internas", campo: "notas_internas", etiqueta: "Comentarios", tipo: "largo", max: 10000 },
  { id: "core:lat", campo: "lat", etiqueta: "X", ayuda: "X es la latitud", tipo: "numero" },
  { id: "core:lon", campo: "lon", etiqueta: "Y", ayuda: "Y es la longitud", tipo: "numero" },
  { id: "core:archivos", etiqueta: "Archivos", tipo: "archivo", archivo: "pdf" },
  { id: "core:kmz", etiqueta: "KMZ", tipo: "archivo", archivo: "kmz" },
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

/** What a cell shows and what its editor starts with: the value as stored. */
export const textoDe = (valor) => (valor == null ? "" : String(valor));

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
  if (columna.tipo === "numero") return leerNumero(crudo);
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

/** The PATCH body for one cell. */
export function cuerpoDeCelda(columna, valor, expectedVersion) {
  return columna.custom
    ? { expected_version: expectedVersion, custom: { [columna.id]: valor } }
    : { expected_version: expectedVersion, changes: { [columna.campo]: valor } };
}

/* ------------------------------------------------------------------ lists */

export const CONSULTA_VACIA = Object.freeze({
  q: "", sort: "id", estado: "", municipio: "", tipo_terreno: "", incluirArchivados: false,
  limit: LIMITE_INICIAL,
});

export const ORDENES = Object.freeze([
  ["id", "Sin ordenar"],
  ...COLUMNAS_BASICAS.filter((c) => c.orden).map((c) => [c.orden, c.etiqueta]),
  ["updated_at", "Última edición"],
]);

/** The query string of one page. Everything is the server's to filter. */
export function consultaDeLista(vista, consulta, cursor = null) {
  const c = { ...CONSULTA_VACIA, ...consulta };
  const q = new URLSearchParams();
  if (c.q.trim()) q.set("q", c.q.trim());
  for (const campo of ["estado", "municipio", "tipo_terreno"]) if (c[campo]) q.set(campo, c[campo]);
  if (c.incluirArchivados) q.set("include_archived", "true");
  if (vista === VISTA_SIN_ASIGNAR) q.set("base", VISTA_SIN_ASIGNAR);
  if (c.sort && c.sort !== "id") q.set("sort", c.sort);
  q.set("limit", String(LIMITES.includes(c.limit) ? c.limit : LIMITE_INICIAL));
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

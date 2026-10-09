/* The shared terrain inventory: contract-v1 vocabulary as pure functions.
 *
 * Nothing here touches the DOM or the network, so every rule the interface
 * relies on -- labels, the public field allowlist, query serialisation, page
 * assembly, form diffing, conflict analysis, idempotency keys -- is testable
 * in Node against the shared fixtures in tests/js/fixtures/inventario/.
 */

import { MONEDAS } from "./format.js";

/* The server's maximum page. Fewer round trips; the default (100) is the
 * server's business, and the assembly loop works with either. */
export const PAGE_LIMIT = 200;   // the server's list maximum

export const DISPONIBILIDAD = Object.freeze({
  unknown: "Sin confirmar",
  available: "Disponible",
  negotiation: "En negociación",
  sold: "Vendido",
  withdrawn: "Retirado",
});

export const PUBLICACION = Object.freeze({
  draft: "Borrador",
  published: "Publicado",
  unpublished: "No publicado",
  archived: "Archivado",
});

/* INTEGRATION_DECISIONS §5: the complete PublicTerrain allowlist. */
export const PUBLIC_FIELDS = Object.freeze([
  "id", "revision_id", "terreno", "estado", "municipio", "direccion",
  "superficie_m2", "superficie_ha", "afectaciones_pct", "afectaciones_m2",
  "lat", "lon", "asking_price", "asking_m2", "moneda", "price_on_request",
  "availability", "public_description", "published_at",
]);

/** Copy only the allowlisted public fields. Never copy-then-delete. */
export function pickPublic(source) {
  return Object.fromEntries(PUBLIC_FIELDS.map((k) => [k, source?.[k] ?? null]));
}

/* ------------------------------------------------------------ geography */

/* Mirrors server/validation.py location_state: usable, absent or impossible. */
const MEXICO_LAT = [14.0, 33.0];
const MEXICO_LON = [-118.5, -86.0];
const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function estadoUbicacion(lat, lon) {
  if (!isNum(lat) || !isNum(lon)) return "sin_dato";
  if (lat < 0 && lon > 0) return "invalida";
  const dentro = lat >= MEXICO_LAT[0] && lat <= MEXICO_LAT[1]
    && lon >= MEXICO_LON[0] && lon <= MEXICO_LON[1];
  return dentro ? "valida" : "invalida";
}

const ubicacion = (lat, lon) => {
  const estado = estadoUbicacion(lat, lon);
  return { ubicacion: estado, ubicado: estado === "valida" };
};

/* ---------------------------------------------------- publication status */

/**
 * The team-facing status. `tono` drives the marker only; the label always
 * carries the meaning (FRONTEND_PACKET, "Publication states and preview").
 */
export function estadoPublicacion(t) {
  const estado = t?.publication_state;
  if (estado === "archived" || t?.archived_at) return { etiqueta: "Archivado", tono: "archivado" };
  if (estado === "draft") return { etiqueta: "Borrador · No publicado", tono: "borrador" };
  if (estado === "unpublished") return { etiqueta: "No publicado", tono: "borrador" };
  if (estado === "published") {
    if (t.public_visible === false) {
      const disp = t.draft?.availability;
      const motivo = !t.has_pending_changes && (disp === "sold" || disp === "withdrawn")
        ? ` · ${DISPONIBILIDAD[disp]}` : "";
      return { etiqueta: `Fuera del catálogo${motivo}`, tono: "fuera" };
    }
    return t.has_pending_changes
      ? { etiqueta: "Publicado · Cambios pendientes", tono: "pendiente" }
      : { etiqueta: "Publicado", tono: "publicado" };
  }
  return { etiqueta: estado ? String(estado) : "Sin estado", tono: "borrador" };
}

/**
 * A saved draft that would take a published terrain off the market only does
 * so once published. Say that loudly instead of letting "Vendido" look live.
 */
export function avisoDisponibilidadPendiente(t) {
  const disp = t?.draft?.availability;
  if (t?.publication_state !== "published" || !t.has_pending_changes) return null;
  if (disp !== "sold" && disp !== "withdrawn") return null;
  return `El borrador marca este terreno como «${DISPONIBILIDAD[disp]}», pero el catálogo ` +
    "sigue mostrando la versión publicada hasta que se publique este cambio.";
}

/* ------------------------------------------------------------ list items */

/** An InternalTerrain as a row the existing map/table/rail understand. */
export function itemDeInventario(t) {
  const d = t.draft ?? {};
  return {
    ...d,
    terreno: d.terreno || "Sin nombre",
    id: t.id,
    version: t.version,
    publication_state: t.publication_state,
    estadoPublicacion: estadoPublicacion(t),
    ...ubicacion(d.lat, d.lon),
    // The active boundary descriptor of the record's `ubicacion`, when the
    // record carries one (null when it has none; absent on records that
    // predate it, which stay plain XY rows). `ubicacion` above remains the XY
    // diagnostic string and `lat`/`lon` the raw X/Y: nothing is copied from
    // the boundary. Whether the row is located is geometria.js's ubicacionDe.
    ...(t.ubicacion ? { geometria: t.ubicacion.geometria ?? null } : {}),
    registro: t,
  };
}

/** A PublicTerrain as a row. Only allowlisted fields survive. */
export function itemPublico(p) {
  const publico = pickPublic(p);
  return { ...publico, terreno: publico.terreno || "Sin nombre", ...ubicacion(publico.lat, publico.lon) };
}

/* --------------------------------------------------------------- filters */

export const FILTROS_VACIOS = Object.freeze({
  busqueda: "",
  estados: [],
  municipios: [],
  superficieMin: null,
  superficieMax: null,
  moneda: null,           // one explicit currency, never a mix
  precioBase: "total",    // total | per_m2
  precioMin: null,
  precioMax: null,
  publicacion: null,      // internal only
  disponibilidad: null,   // internal only
  incluirArchivados: false,
});

/**
 * The server query for a filter state. Geography is repeated parameters
 * (estado=A&estado=B); a price range is only ever sent with its currency.
 */
export function consultaDe(filtros, tipo) {
  const f = { ...FILTROS_VACIOS, ...filtros };
  const q = new URLSearchParams();
  if (f.busqueda.trim()) q.set("q", f.busqueda.trim());
  for (const estado of f.estados) q.append("estado", estado);
  for (const municipio of f.municipios) q.append("municipio", municipio);
  if (f.superficieMin != null) q.set("area_min_m2", String(f.superficieMin));
  if (f.superficieMax != null) q.set("area_max_m2", String(f.superficieMax));
  if (MONEDAS.includes(f.moneda)) {
    q.set("moneda", f.moneda);
    if (f.precioMin != null || f.precioMax != null) {
      q.set("price_basis", f.precioBase === "per_m2" ? "per_m2" : "total");
      if (f.precioMin != null) q.set("price_min", String(f.precioMin));
      if (f.precioMax != null) q.set("price_max", String(f.precioMax));
    }
  }
  if (tipo === "inventario") {
    if (f.publicacion) q.set("publication_state", f.publicacion);
    if (f.disponibilidad) q.set("availability", f.disponibilidad);
    if (f.incluirArchivados) q.set("include_archived", "true");
  }
  return q;
}

/** The query for one page of it. */
export function consultaDePagina(consulta, cursor) {
  const q = new URLSearchParams(consulta);
  q.set("limit", String(PAGE_LIMIT));
  if (cursor != null) q.set("cursor", String(cursor));
  return q.toString();
}

export function contarFiltros(filtros, tipo) {
  const f = { ...FILTROS_VACIOS, ...filtros };
  let n = 0;
  if (f.busqueda.trim()) n += 1;
  if (f.estados.length) n += 1;
  if (f.municipios.length) n += 1;
  if (f.superficieMin != null || f.superficieMax != null) n += 1;
  if (f.moneda) n += 1;
  if (f.moneda && (f.precioMin != null || f.precioMax != null)) n += 1;
  if (tipo === "inventario") {
    if (f.publicacion) n += 1;
    if (f.disponibilidad) n += 1;
    if (f.incluirArchivados) n += 1;
  }
  return n;
}

/* ------------------------------------------------------------ pagination */

/**
 * Fetch every page of one query. The map, the table and the count all use
 * the single assembled result, so they cannot disagree.
 *
 * ponytail: the browser holds the whole result; contract v1 accepts this for
 * the small-team baseline. Server-side map aggregation if it grows.
 */
export async function reunirPaginas(pedirPagina, { onProgreso } = {}) {
  const porId = new Map();
  const cursores = new Set();
  let cursor = null;
  let primera = null;
  do {
    const pagina = await pedirPagina(cursor);
    primera ??= pagina;
    for (const t of pagina.terrenos ?? []) porId.set(t.id, t);
    cursor = pagina.next_cursor ?? null;
    if (cursor != null) {
      if (cursores.has(cursor)) throw new Error("El servidor repitió una página; la lista no está completa.");
      cursores.add(cursor);
    }
    onProgreso?.(porId.size, primera.total ?? null);
  } while (cursor != null);
  return {
    terrenos: [...porId.values()],
    totalServidor: primera.total ?? porId.size,
    facets: primera.facets ?? {},
  };
}

/* Facet shape is tolerant on purpose: arrays of names, of {valor,conteo} or
 * {value,count}, or a {name: count} map all become [{valor, conteo}]. */
function opcionesDe(valor) {
  if (!valor) return [];
  const pares = Array.isArray(valor)
    ? valor.map((x) => (typeof x === "string"
      ? [x, null]
      : [x.valor ?? x.value ?? x.nombre ?? x.name, x.conteo ?? x.count ?? x.total ?? null]))
    : Object.entries(valor);
  return pares
    .filter(([v]) => v != null && v !== "")
    .map(([v, conteo]) => ({ valor: String(v), conteo: isNum(conteo) ? conteo : null }))
    .sort((a, b) => (b.conteo ?? 0) - (a.conteo ?? 0) || a.valor.localeCompare(b.valor, "es"));
}

export function opcionesDeFacetas(facets = {}) {
  return {
    estados: opcionesDe(facets.estados ?? facets.estado),
    municipios: opcionesDe(facets.municipios ?? facets.municipio),
    monedas: opcionesDe(facets.monedas ?? facets.moneda),
  };
}

/* ------------------------------------------------------------ the editor */

/* The editable draft fields, in form order: exactly the backend's EDITABLE
 * set (server/inventario.py). Confirmation stamps are not fields: they are
 * requested with PATCH `confirm` and recorded by the server. */
export const SECCIONES = Object.freeze([
  { id: "identificacion", titulo: "Identificación" },
  { id: "ubicacion", titulo: "Ubicación" },
  { id: "superficie", titulo: "Superficie" },
  { id: "comercial", titulo: "Condiciones comerciales" },
  { id: "privado", titulo: "Solo equipo", nota: "Nunca se publica." },
]);

export const CAMPOS = Object.freeze([
  { clave: "terreno", seccion: "identificacion", etiqueta: "Nombre", tipo: "texto" },
  { clave: "availability", seccion: "identificacion", etiqueta: "Disponibilidad", tipo: "opcion",
    opciones: Object.entries(DISPONIBILIDAD) },
  { clave: "estado", seccion: "ubicacion", etiqueta: "Estado", tipo: "texto" },
  { clave: "municipio", seccion: "ubicacion", etiqueta: "Municipio", tipo: "texto" },
  { clave: "direccion", seccion: "ubicacion", etiqueta: "Dirección", tipo: "texto", ancho: true },
  { clave: "lat", seccion: "ubicacion", etiqueta: "Latitud (X)", tipo: "numero",
    ayuda: "Grados decimales, p. ej. 20.6736" },
  { clave: "lon", seccion: "ubicacion", etiqueta: "Longitud (Y)", tipo: "numero",
    ayuda: "Grados decimales, p. ej. -103.3440" },
  { clave: "superficie_m2", seccion: "superficie", etiqueta: "Superficie (m²)", tipo: "numero" },
  { clave: "superficie_ha", seccion: "superficie", etiqueta: "Superficie (ha)", tipo: "numero",
    ayuda: "Valor registrado; no se calcula a partir de los m²." },
  { clave: "afectaciones_pct", seccion: "superficie", etiqueta: "Afectaciones (%)", tipo: "numero", escala: 100 },
  { clave: "afectaciones_m2", seccion: "superficie", etiqueta: "Afectaciones (m²)", tipo: "numero" },
  { clave: "moneda", seccion: "comercial", etiqueta: "Moneda", tipo: "opcion",
    opciones: [["", "Sin moneda registrada"], ...MONEDAS.map((m) => [m, m])] },
  { clave: "asking_price", seccion: "comercial", etiqueta: "Asking Price (total)", tipo: "numero" },
  { clave: "asking_m2", seccion: "comercial", etiqueta: "Asking $/m²", tipo: "numero",
    ayuda: "Valor registrado; no se recalcula con el total." },
  { clave: "price_on_request", seccion: "comercial", etiqueta: "Precio a consultar", tipo: "bool" },
  { clave: "public_description", seccion: "comercial", etiqueta: "Descripción pública", tipo: "largo",
    ayuda: "Lo único de texto libre que verá el público al publicar.", ancho: true },
  { clave: "contacto", seccion: "privado", etiqueta: "Contacto", tipo: "largo", ancho: true },
  { clave: "notas_internas", seccion: "privado", etiqueta: "Notas internas", tipo: "largo", ancho: true },
]);

const PORCAMPO = new Map(CAMPOS.map((c) => [c.clave, c]));
export const campo = (clave) => PORCAMPO.get(clave);

/**
 * A number as typed in Mexico: "1,200,000.50", "122.5", "-103.344".
 * A comma that is not a thousands separator is refused rather than guessed.
 */
export function leerNumero(texto) {
  const limpio = String(texto ?? "").trim().replace(/^\$/, "").replace(/\s+/g, "");
  if (limpio === "") return { valor: null };
  const sinMiles = /^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(limpio) ? limpio.replace(/,/g, "") : limpio;
  if (!/^-?(\d+(\.\d*)?|\.\d+)$/.test(sinMiles)) {
    return { error: sinMiles.includes(",") ? "Usa punto decimal (p. ej. 122.5)." : "Escribe un número." };
  }
  return { valor: Number(sinMiles) };
}

/** What a field shows for a stored value. Exact, unformatted: it round-trips. */
export function textoDeValor(c, valor) {
  if (c.tipo === "bool") return Boolean(valor);
  if (c.tipo === "opcion") {
    // A select can only show one of its options; an absent value shows the first.
    const v = valor == null ? "" : String(valor);
    return c.opciones.some(([o]) => o === v) ? v : c.opciones[0][0];
  }
  if (valor == null) return "";
  if (c.tipo === "numero" && c.escala) return String(Number((valor * c.escala).toPrecision(15)));
  return String(valor);
}

/** A field's text (as the form holds it) for people to read. */
export function mostrarTexto(c, texto) {
  if (c.tipo === "bool") return texto ? "Sí" : "No";
  if (c.tipo === "opcion") return new Map(c.opciones).get(texto) ?? "—";
  if (texto === "" || texto == null) return "—";
  return c.escala ? `${texto} %` : String(texto);
}

export const mostrarValor = (c, valor) => mostrarTexto(c, textoDeValor(c, valor));

export function textosIniciales(draft = {}) {
  return Object.fromEntries(CAMPOS.map((c) => [c.clave, textoDeValor(c, draft[c.clave])]));
}

function valorDeTexto(c, texto) {
  if (c.tipo === "bool") return { valor: Boolean(texto) };
  if (c.tipo === "numero") {
    const leido = leerNumero(texto);
    if (leido.error || leido.valor == null || !c.escala) return leido;
    return { valor: leido.valor / c.escala };
  }
  const limpio = String(texto).trim();
  return { valor: limpio === "" ? null : limpio };
}

/**
 * The changes a form represents. Only fields whose text differs from what was
 * loaded are parsed and sent, so an untouched value is never re-serialised:
 * cents, original units and unknowns survive a save byte for byte.
 *
 * Drafts may be incomplete (INTEGRATION_DECISIONS §9.1): half a coordinate
 * pair saves and only blocks publication, so it is a warning, not an error.
 */
export function cambiosDelFormulario(textos, iniciales) {
  const cambios = {};
  const errores = {};
  for (const c of CAMPOS) {
    if (textos[c.clave] === iniciales[c.clave]) continue;
    const { valor, error } = valorDeTexto(c, textos[c.clave]);
    if (error) errores[c.clave] = error;
    else cambios[c.clave] = valor;
  }

  return { cambios, errores };
}

const iguales = (a, b) => (a ?? null) === (b ?? null);

/** Which fields the server changed under us, and which of those we changed too. */
export function analizarConflicto(baseDraft = {}, actualDraft = {}, misCambios = {}) {
  const delServidor = CAMPOS
    .filter((c) => !iguales(baseDraft[c.clave], actualDraft[c.clave]))
    .map((c) => c.clave);
  const choques = delServidor.filter((k) => k in misCambios
    && !iguales(misCambios[k], actualDraft[k]));
  return { delServidor, choques };
}

/** Field errors from a 422 `detalle`, whatever its exact container. */
export function erroresDeCampo(detalle) {
  const fuente = detalle?.fields ?? detalle?.campos ?? detalle?.errores ?? detalle?.errors;
  if (!fuente) return {};
  const pares = Array.isArray(fuente)
    ? fuente.map((e) => [e.field ?? e.campo, e.message ?? e.mensaje ?? e.error])
    : Object.entries(fuente).map(([k, v]) => [k, Array.isArray(v) ? v.join(" ") : v]);
  return Object.fromEntries(pares.filter(([k, v]) => k && v).map(([k, v]) => [k, String(v)]));
}

/* ----------------------------------------------------------- idempotency */

export function nuevaClave() {
  if (globalThis.crypto?.randomUUID) {
    try { return globalThis.crypto.randomUUID(); } catch { /* insecure context */ }
  }
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * One key per logical create attempt: the same body after an uncertain
 * failure reuses its key (so the server replays the original result), a
 * changed body gets a fresh one (never the same key for a different request).
 */
export function crearIntento(generar = nuevaClave) {
  let actual = null;
  return {
    claveParaCuerpo(cuerpo) {
      const firma = JSON.stringify(cuerpo);
      if (!actual || actual.firma !== firma) actual = { firma, clave: generar() };
      return actual.clave;
    },
    completar() { actual = null; },
  };
}

/* What a team member can confirm as checked today (PATCH `confirm`). */
export const CONFIRMABLES = Object.freeze({ price: "Precio", availability: "Disponibilidad" });

/* --------------------------------------------------------------- history */

export const ACCIONES = Object.freeze({
  create: "Creó el borrador",
  created: "Creó el borrador",
  save: "Guardó el borrador",
  saved: "Guardó el borrador",
  update: "Guardó el borrador",
  updated: "Guardó el borrador",
  publish: "Publicó",
  published: "Publicó",
  unpublish: "Retiró del catálogo",
  unpublished: "Retiró del catálogo",
  archive: "Archivó",
  archived: "Archivó",
  restore: "Restauró",
  restored: "Restauró",
  import: "Importó",
  adopt: "Incorporó al inventario",
});

/** One history event in a single shape, whatever the server's spelling. */
export function normalizarEvento(e) {
  const accion = e.action ?? e.accion ?? "";
  const cambios = Array.isArray(e.changes)
    ? e.changes.map((c) => ({ campo: c.field ?? c.campo, antes: c.before ?? c.antes, despues: c.after ?? c.despues }))
    : Object.entries(e.changes ?? e.cambios ?? {}).map(([k, v]) => ({
      campo: k, antes: v?.before ?? v?.antes ?? null, despues: v?.after ?? v?.despues ?? null,
    }));
  return {
    id: e.id,
    accion: ACCIONES[accion] ?? accion,
    actor: e.actor?.display_name ?? e.actor_display_name ?? e.actor_name ?? "—",
    fecha: e.at ?? e.created_at ?? e.timestamp ?? null,
    version: e.version ?? e.resulting_version ?? null,
    confirmados: (e.confirmed ?? []).map((c) => CONFIRMABLES[c] ?? c),
    cambios,
  };
}

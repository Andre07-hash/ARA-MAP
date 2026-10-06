/* Connected Excel workbooks: what a source's state means for the person
 * looking at it, and the client half of the refresh contract. No DOM here, so
 * it is unit-tested (tests/js/excel.test.mjs).
 *
 * The server is the authority on every rule (concurrency, idempotency, which
 * base may be written). This module only words its answers and makes sure a
 * retry after a lost response reuses the same Idempotency-Key.
 */

import { LOCALE, plural } from "./format.js";
import { nuevaClave } from "./inventario.js";

const fechaHora = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });

/** "6 oct 2026, 14:05": refresh times need the hour, not only the day. */
export function fmtFechaHora(iso) {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.valueOf()) ? fechaHora.format(d) : "nunca";
}

/* What the Microsoft callback sends back in the hash: #/bases?excel=<valor>. */
export const AVISOS = Object.freeze({
  conectado: { tipo: "ok", mensaje: "Cuenta de Microsoft conectada. Ya puedes elegir el libro." },
  cancelado: { tipo: "aviso", mensaje: "Se canceló la conexión con Microsoft; no se guardó nada." },
  error: {
    tipo: "error",
    mensaje: "No se pudo conectar la cuenta de Microsoft. Inténtalo de nuevo desde «Conectar Excel».",
  },
});

/** Split "#/bases?excel=conectado" into the route hash and a known notice. */
export function avisoDeHash(hash) {
  const texto = String(hash ?? "");
  const i = texto.indexOf("?");
  if (i < 0) return { hash: texto, aviso: null };
  const valor = new URLSearchParams(texto.slice(i + 1)).get("excel");
  return { hash: texto.slice(0, i), aviso: Object.hasOwn(AVISOS, valor ?? "") ? valor : null };
}

export const MONEDAS_EXCEL = Object.freeze([
  ["USD", "Dólares (USD)"],
  ["MXN", "Pesos (MXN)"],
  ["columna", "Una columna del libro indica la moneda"],
  ["desconocida", "No se sabe (se muestran sin moneda)"],
]);

const ESPERA_REINTENTO = new Set(["no_disponible", "archivo_cambiando", "interrumpida", "interno", "restauracion"]);

/**
 * The card's reading of a source: a tone, a headline, details and which
 * actions make sense. `ocupada` is this browser's own request in flight.
 */
export function estadoDeFuente(fuente, { ocupada = false } = {}) {
  const v = fuente.version_activa;
  const ultima = fuente.ultima_ejecucion;
  const datos = v
    ? `Versión ${v.numero} · ${plural(v.filas, "fila")} activas`
    : "Sin datos activos";
  const detalles = [
    datos,
    `Última revisión: ${fmtFechaHora(fuente.ultima_revision_en)}`,
    `Última actualización correcta: ${fmtFechaHora(fuente.ultima_exitosa_en)}`,
  ];
  const acciones = new Set(["abrir"]);
  const base = { detalles, acciones, problemas: [] };

  if (fuente.estado === "desconectada") {
    acciones.add("reactivar");
    return {
      ...base, tono: "aviso", titulo: "Desconectada de Excel",
      nota: "Los datos se conservan, pero ya no se actualizan desde el libro.",
    };
  }
  acciones.add("desconectar");
  if (ocupada || fuente.en_curso) {
    if (!ocupada) acciones.add("comprobar");   // started elsewhere: re-read on demand
    const quien = ultima?.iniciada_por?.display_name;
    return {
      ...base, tono: "curso", titulo: "Actualizando desde Excel…",
      nota: `Iniciada${quien ? ` por ${quien}` : ""} ${fmtFechaHora(ultima?.iniciada_en)}. ` +
            "Mientras tanto se siguen mostrando los datos anteriores.",
    };
  }
  if (fuente.cuenta?.requiere_reconexion) {
    acciones.add("reconectar_cuenta");
    return {
      ...base, tono: "error", titulo: "Hay que volver a conectar la cuenta de Microsoft",
      nota: `Conecta de nuevo ${fuente.cuenta.correo ?? "la cuenta dueña del libro"}. ` +
            "Los datos actuales se conservan.",
    };
  }
  acciones.add("actualizar");
  if (!ultima) return { ...base, tono: "ok", titulo: "Conectada a Excel", nota: null };

  switch (ultima.estado) {
    case "revision":
      return {
        ...base, tono: "aviso", titulo: "El libro está vacío: falta confirmar",
        nota: "La base sigue mostrando la versión anterior hasta que alguien confirme vaciarla.",
      };
    case "error":
    case "conflicto":
    case "interrumpida": {
      const codigo = ultima.error?.codigo ?? ultima.estado;
      if (codigo === "reconectar") acciones.add("reconectar_cuenta");
      return {
        ...base, tono: "error",
        titulo: ESPERA_REINTENTO.has(codigo) || ultima.estado !== "error"
          ? "La última actualización no terminó"
          : "La última actualización falló",
        nota: `${mensajeDeEjecucion(ultima)} ${v ? `Se conservan los datos de la versión ${v.numero}.` : ""}`.trim(),
        problemas: ultima.problemas ?? [],
      };
    }
    default:
      return { ...base, tono: "ok", titulo: "Conectada a Excel", nota: null };
  }
}

/** "2 agregados, 1 actualizado, 0 eliminados" -- the run's real counts. */
export function textoConteos(conteos) {
  if (!conteos) return "";
  return [
    plural(conteos.agregados, "agregado"),
    plural(conteos.actualizados, "actualizado"),
    plural(conteos.eliminados, "eliminado"),
  ].join(", ");
}

/** One sentence for the outcome of a finished run. */
export function mensajeDeEjecucion(e) {
  switch (e.estado) {
    case "ok": return `Actualizada desde Excel: ${textoConteos(e.conteos)}.`;
    case "sin_cambios": return "El libro no tiene cambios desde la última actualización.";
    case "revision": return "El libro no tiene filas. Confirma si la base debe quedar vacía.";
    case "conflicto":
      return "El archivo cambió mientras se leía. Espera a que termine de guardarse y vuelve a intentarlo.";
    case "interrumpida":
      return "La actualización se interrumpió antes de terminar; no se aplicó nada.";
    case "en_curso": return "La actualización sigue en curso.";
    default:
      if (e.error?.codigo === "datos_invalidos") {
        return `El libro tiene ${plural(e.problemas?.length ?? 0, "fila")} con problemas; no se aplicó nada.`;
      }
      return e.error?.mensaje ?? "La actualización falló; no se aplicó nada.";
  }
}

/** Whether a run changed the live data (so map, table and export reload). */
export const cambioDatos = (e) => e?.estado === "ok";

/* ------------------------------------------------------------ refresh keys */

/* A lost answer is retried promptly or not at all: after this long, pressing
 * "Actualizar" again means "refresh now", not "tell me what happened then". */
export const VIGENCIA_REINTENTO_MS = 120_000;

/**
 * The key for one refresh request. A request whose answer never arrived (a
 * dropped connection) is retried with the SAME key and body, so the server
 * returns its recorded outcome instead of running again. A different body
 * (say, confirming an empty candidate) gets a new key.
 *
 * Kept in memory, on purpose: after a reload the server's state is what the
 * card shows (a run still in progress is watched, a finished one is listed),
 * so the next press must start a new refresh rather than replay an old one.
 */
export function crearClavesDeActualizacion({ generar = nuevaClave, ahora = Date.now } = {}) {
  const pendientes = new Map();   // fuente id -> { clave, firma, desde }
  const leer = (id) => {
    const p = pendientes.get(id);
    if (p && ahora() - p.desde > VIGENCIA_REINTENTO_MS) { pendientes.delete(id); return null; }
    return p ?? null;
  };
  return {
    preparar(id, cuerpo) {
      const firma = JSON.stringify(cuerpo ?? {});
      const pendiente = leer(id);
      if (pendiente && pendiente.firma === firma) return pendiente.clave;
      const clave = `excel-${generar()}`;
      pendientes.set(id, { clave, firma, desde: ahora() });
      return clave;
    },
    pendiente: (id) => leer(id),
    /** The server answered (any recorded outcome or a definitive refusal). */
    resolver(id) { pendientes.delete(id); },
  };
}

/** Whether an error means the answer may still exist on the server. */
export const respuestaIncierta = (error) => Boolean(error?.red) || (error?.status ?? 0) >= 500;

/** Prevent double clicks per source; the server still enforces concurrency. */
export function crearOcupadas() {
  const activas = new Set();
  return {
    tomar(id) { if (activas.has(id)) return false; activas.add(id); return true; },
    soltar(id) { activas.delete(id); },
    tiene: (id) => activas.has(id),
  };
}

/* A run in progress elsewhere is re-read every few seconds, for at most a
 * bounded time (the server's lease plus a margin): then the card says it is
 * still running and offers to check again, never spinning forever. */
export const SONDEO_MS = 4000;
export const SONDEO_MAX_MS = 150_000;

/** Base name suggested from the workbook's file name. */
export const nombreSugerido = (archivo) => String(archivo ?? "").replace(/\.(xlsx|xlsm)$/i, "").trim();

/** Best guesses for the setup form, from the server's preview. */
export function configuracionInicial(vista) {
  const columnas = vista?.columnas ?? [];
  const moneda = columnas.find((c) => c.es_moneda);
  return {
    hoja: vista?.hoja ?? null,
    columna_id: vista?.id_sugerido ?? columnas.find((c) => c.puede_ser_id)?.encabezado ?? "",
    moneda: moneda ? "columna" : "USD",
    columna_moneda: moneda?.encabezado ?? "",
  };
}

/** Client-side reasons the setup cannot be submitted yet (the server re-checks). */
export function faltantesDeConfiguracion(config, vista, nombre) {
  const faltan = [];
  if (!String(nombre ?? "").trim()) faltan.push("Ponle un nombre a la base.");
  if (!config.columna_id) faltan.push("Elige la columna con el ID único de cada terreno.");
  if (config.moneda === "columna" && !config.columna_moneda) faltan.push("Elige la columna de moneda.");
  if (vista && !vista.tiene_terreno) faltan.push("La hoja no tiene las columnas de terreno necesarias.");
  if (vista?.ya_conectada) faltan.push("Ese archivo ya está conectado a otra base.");
  return faltan;
}

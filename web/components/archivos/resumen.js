/* What a terrain's file summary says, in words. Pure: no DOM, no network.
 *
 * `resumen` is the caller-aware 1B per-terrain summary, unchanged:
 *   {pdf_total, pdf_recientes: [fila], kmz: fila | null}
 *   fila = {id, tipo, revision, retirado, version_actual_id, geometria_activa_id,
 *           ultima_version: {id, numero, estado, nombre_original, tamano, ...}
 *                         | {estado, propia: false}    (another account's pending upload)
 *                         | null}
 * Undefined means "not available yet", never zero files.
 */

export const ESTADO = Object.freeze({
  CARGANDO: "cargando",      // no summary yet
  VACIO: "vacio",            // known: no file of this kind
  LISTO: "listo",            // current usable content
  PENDIENTE: "pendiente",    // an upload is in progress (own or another account's)
  FALLIDO: "fallido",        // the latest upload failed or expired
  SIN_ACTIVAR: "sin_activar", // KMZ stored without an active boundary
});

const pendienteDe = (v) => v && (v.estado === "subiendo" || v.estado === "expirado");

/* The latest upload's state, said for a reader who cannot see private metadata. */
function nota(v, actual) {
  if (!v) return null;
  if (v.propia === false) {
    return v.estado === "expirado" ? "Una subida de otra cuenta venció" : "Otra cuenta está subiendo una versión";
  }
  if (v.estado === "subiendo") return "Tienes una subida sin terminar";
  if (v.estado === "expirado") return "Tu última subida venció";
  if (v.estado === "fallido") return "La última subida falló";
  if (v.estado === "disponible" && actual && v.id !== actual) return "Hay una versión nueva sin activar";
  return null;
}

/**
 * {estado, texto, nota}: `texto` is the compact cell text; `nota` adds what
 * the latest upload is doing, if anything worth saying.
 */
export function describirResumen(resumen, tipo) {
  if (resumen === undefined || resumen === null || typeof resumen !== "object") {
    return { estado: ESTADO.CARGANDO, texto: "…", nota: "Cargando la información de archivos" };
  }
  if (tipo === "pdf") {
    const total = Number.isInteger(resumen.pdf_total) ? resumen.pdf_total : null;
    const ultima = resumen.pdf_recientes?.[0]?.ultima_version ?? null;
    const n = nota(ultima, resumen.pdf_recientes?.[0]?.version_actual_id);
    if (total === null) return { estado: ESTADO.CARGANDO, texto: "…", nota: "Cargando la información de archivos" };
    if (total === 0) return { estado: ESTADO.VACIO, texto: "Sin PDF", nota: null };
    const texto = total === 1 ? "1 PDF" : `${total} PDF`;
    const estado = pendienteDe(ultima) ? ESTADO.PENDIENTE
      : ultima?.estado === "fallido" ? ESTADO.FALLIDO : ESTADO.LISTO;
    return { estado, texto, nota: n };
  }
  const k = resumen.kmz;
  if (!k) return { estado: ESTADO.VACIO, texto: "Sin KMZ", nota: null };
  const ultima = k.ultima_version ?? null;
  const n = nota(ultima, k.version_actual_id);
  if (k.geometria_activa_id) {
    return { estado: pendienteDe(ultima) ? ESTADO.PENDIENTE : ultima?.estado === "fallido" ? ESTADO.FALLIDO : ESTADO.LISTO,
      texto: "Contorno activo", nota: n };
  }
  if (pendienteDe(ultima)) return { estado: ESTADO.PENDIENTE, texto: "KMZ en curso", nota: n };
  if (ultima?.estado === "fallido") return { estado: ESTADO.FALLIDO, texto: "KMZ falló", nota: n };
  return { estado: ESTADO.SIN_ACTIVAR, texto: "KMZ sin contorno activo", nota: n };
}

/** A size in bytes, for people. */
export function tamanoLegible(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString("es-MX", { maximumFractionDigits: 1 })} KB`;
  return `${(bytes / 1024 / 1024).toLocaleString("es-MX", { maximumFractionDigits: 1 })} MB`;
}

/** A download file name: the stored name without separators or control characters. */
export function nombreSeguro(nombre, tipo) {
  const limpio = String(nombre ?? "").replace(/[\u0000-\u001f\u007f/\\:*?"<>|]+/g, "_").trim().slice(0, 200);
  const base = limpio || "archivo";
  return new RegExp(`\\.${tipo}$`, "i").test(base) ? base : `${base}.${tipo}`;
}

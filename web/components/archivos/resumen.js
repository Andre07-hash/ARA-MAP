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

const pendienteDe = (v) => v?.estado === "subiendo";
const vencidaDe = (v) => v?.estado === "expirado";

/* The latest upload's state, said for a reader who cannot see private metadata.
 * "Vencida" is the upload's deadline to finish, never a stored PDF expiring. */
function nota(v, actual) {
  if (!v) return null;
  if (v.propia === false) {
    return v.estado === "expirado" ? "Una subida de otra cuenta venció sin terminar" : "Otra cuenta está subiendo una versión";
  }
  if (v.estado === "subiendo") return "Tienes una subida sin terminar";
  if (v.estado === "expirado") return "Tu última subida venció sin terminar (subida vencida)";
  if (v.estado === "fallido") return "La última subida fue rechazada";
  if (v.estado === "disponible" && actual && v.id !== actual) return "Hay una versión nueva sin activar";
  return null;
}

/* What a PDF attachment with no saved version is: [singular, plural]. */
function sinGuardar(v) {
  if (!v) return ["adjunto sin versión", "adjuntos sin versión"];
  if (v.estado === "subiendo") {
    return v.propia === false ? ["subida de otra cuenta en curso", "subidas de otra cuenta en curso"]
      : ["subida sin terminar", "subidas sin terminar"];
  }
  if (v.estado === "expirado") return ["subida vencida", "subidas vencidas"];
  if (v.estado === "fallido") return ["subida rechazada", "subidas rechazadas"];
  if (v.estado === "cancelado") return ["subida cancelada", "subidas canceladas"];
  return ["adjunto sin guardar", "adjuntos sin guardar"];
}

const contar = (formas) => {
  const n = new Map();
  for (const [uno, varios] of formas) n.set(uno, { varios, k: (n.get(uno)?.k ?? 0) + 1 });
  return [...n].map(([uno, { varios, k }]) => (k === 1 ? `1 ${uno}` : `${k} ${varios}`));
};

/**
 * The PDF side. An attachment counts as a PDF only when it has a saved
 * (current) version; one whose upload never finished says so instead. The
 * server lists at most a few recent attachments: when it lists fewer than it
 * counts, nothing is totalled from the ones it did not list.
 */
function describirPdf(resumen) {
  const total = Number.isInteger(resumen.pdf_total) ? resumen.pdf_total : null;
  const filas = Array.isArray(resumen.pdf_recientes) ? resumen.pdf_recientes : [];
  if (total === null) return { estado: ESTADO.CARGANDO, texto: "…", nota: "Cargando la información de archivos" };
  if (total === 0) return { estado: ESTADO.VACIO, texto: "Sin PDF", nota: null };
  const completo = filas.length >= total;
  const guardados = filas.filter((f) => f.version_actual_id);
  const pendientes = filas.filter((f) => !f.version_actual_id);
  const notas = [
    ...contar(pendientes.map((f) => sinGuardar(f.ultima_version))),
    ...guardados.map((f) => nota(f.ultima_version, f.version_actual_id)).filter(Boolean),
  ];
  if (!completo) notas.unshift(`se resumen los ${filas.length} más recientes`);
  const ultima = filas[0]?.ultima_version ?? null;
  const enCurso = filas.some((f) => pendienteDe(f.ultima_version));
  const fallo = filas.some((f) => vencidaDe(f.ultima_version) || f.ultima_version?.estado === "fallido");
  const estado = enCurso ? ESTADO.PENDIENTE : guardados.length ? ESTADO.LISTO : fallo ? ESTADO.FALLIDO
    : ESTADO.VACIO;
  let texto;
  if (!completo) texto = `${total} adjuntos PDF`;
  else if (guardados.length) texto = guardados.length === 1 ? "1 PDF" : `${guardados.length} PDF`;
  else texto = "Sin PDF guardado";
  const unica = notas.length ? notas.join(" · ") : null;
  // The single-attachment wording the cell has always used, when it fits.
  if (completo && filas.length === 1 && !guardados.length && ultima) {
    return { estado, texto, nota: nota(ultima, null) ?? unica };
  }
  return { estado, texto, nota: unica ? unica.charAt(0).toUpperCase() + unica.slice(1) : null };
}

/**
 * {estado, texto, nota}: `texto` is the compact cell text; `nota` adds what
 * the latest upload is doing, if anything worth saying.
 */
export function describirResumen(resumen, tipo) {
  if (resumen === undefined || resumen === null || typeof resumen !== "object") {
    return { estado: ESTADO.CARGANDO, texto: "…", nota: "Cargando la información de archivos" };
  }
  if (tipo === "pdf") return describirPdf(resumen);
  const k = resumen.kmz;
  if (!k) return { estado: ESTADO.VACIO, texto: "Sin KMZ", nota: null };
  const ultima = k.ultima_version ?? null;
  const n = nota(ultima, k.version_actual_id);
  if (k.geometria_activa_id) {
    return { estado: pendienteDe(ultima) ? ESTADO.PENDIENTE
      : vencidaDe(ultima) || ultima?.estado === "fallido" ? ESTADO.FALLIDO : ESTADO.LISTO,
    texto: "Contorno activo", nota: n };
  }
  if (pendienteDe(ultima)) return { estado: ESTADO.PENDIENTE, texto: "KMZ en curso", nota: n };
  if (vencidaDe(ultima)) return { estado: ESTADO.FALLIDO, texto: "Subida KMZ vencida", nota: n };
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

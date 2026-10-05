/* Pure helpers for the import assistant's dialog. No DOM, no network.
 *
 * Corrections are queued, never raced: while one request is in flight, later
 * edits are merged into a single pending patch and sent after it, against the
 * revision it returns. So the newest choice always wins and an older response
 * can never replace a newer one.
 */

/** Merge correction patches the way the server merges decisions. */
export function mergeCorrecciones(a = {}, b = {}) {
  const merged = { ...a };
  for (const [clave, valor] of Object.entries(b)) {
    merged[clave] = clave === "columnas" ? { ...(a.columnas ?? {}), ...valor } : valor;
  }
  return merged;
}

/** Initial answers: the suggested option where there is one, else none. */
export function respuestasIniciales(preguntas = []) {
  const respuestas = {};
  for (const p of preguntas) {
    if (p.sugerida !== null && p.sugerida !== undefined) respuestas[p.id] = p.sugerida;
  }
  return respuestas;
}

/** Keep answers the user already gave to questions that are still open. */
export function conservarRespuestas(previas, preguntas = []) {
  const vigentes = new Set(preguntas.map((p) => p.id));
  const kept = respuestasIniciales(preguntas);
  for (const [id, opcion] of Object.entries(previas ?? {})) {
    if (vigentes.has(id)) kept[id] = opcion;
  }
  return kept;
}

export const todasRespondidas = (preguntas = [], respuestas = {}) =>
  preguntas.every((p) => Number.isInteger(respuestas[p.id]));

export const aRespuestas = (respuestas = {}) =>
  Object.entries(respuestas).map(([pregunta, opcion]) => ({ pregunta, opcion }));

/** "Línea" for CSV (physical lines), "Fila" for a worksheet. */
export const etiquetaFila = (formato) => (formato === "csv" ? "Línea" : "Fila");

/** A queue that serializes preparar requests and coalesces edits. */
export function createCorrectionQueue(send) {
  let enVuelo = false;
  let pendiente = null;
  const esperas = [];

  async function flush() {
    if (enVuelo || !pendiente) return;
    const parche = pendiente;
    pendiente = null;
    enVuelo = true;
    try {
      await send(parche);
    } finally {
      enVuelo = false;
      if (pendiente) flush();
      else esperas.splice(0).forEach((resolve) => resolve());
    }
  }

  return {
    push(parche) {
      pendiente = mergeCorrecciones(pendiente ?? {}, parche);
      flush();
    },
    get ocupado() { return enVuelo || Boolean(pendiente); },
    /** Resolves once nothing is queued or in flight. */
    idle() {
      return enVuelo || pendiente ? new Promise((resolve) => esperas.push(resolve)) : Promise.resolve();
    },
  };
}

/** Plain-language description of how automatic assistance went, for details. */
export function estadoAutomatico(automatico) {
  const e = automatico?.estado;
  if (!e || e === "no_necesario") return "No hizo falta: la detección bastó.";
  if (e === "ok") {
    return `Se usó asistencia automática: ${automatico.aplicadas} columna(s) interpretada(s)` +
      (automatico.descartadas ? `, ${automatico.descartadas} sugerencia(s) descartada(s) por no coincidir con los datos.` : ".") +
      (automatico.proveedor === "simulado" ? " (Proveedor simulado de pruebas.)" : "");
  }
  if (e === "no_configurado") return "La asistencia automática no está configurada; se usaron detección y preguntas.";
  if (e === "en_curso") return "La asistencia automática está en proceso.";
  return "La asistencia automática no respondió a tiempo o no estaba disponible; se usaron detección y preguntas.";
}

/**
 * Whether a failed confirmation used up the preview. After the server claims
 * the draft, any failure closes it (the error says so in `detalle`); a stale
 * or expired preview (409/410) and an unexpected server error (5xx) are spent
 * too. Anything else -- a folder refused before the token was taken, say --
 * leaves the preview usable for another try.
 */
export function vistaConsumida(error) {
  if (!error) return false;
  return Boolean(error.detalle?.vista_previa_consumida) ||
    error.status === 409 || error.status === 410 || (error.status ?? 0) >= 500;
}

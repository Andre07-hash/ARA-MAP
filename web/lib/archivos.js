/* Client for the private attachment API (packet 2B routes; 3B client).
 *
 * Every call goes through the host's `peticionPrivada` bridge (Round 3
 * INTERFACES §2): same-origin, no-store, cancelled with the private session.
 * This module never calls fetch itself, never decodes an unbounded body and
 * never keeps a private payload after the call returns.
 *
 * Errors:
 * - Cancellation (the caller's signal, or the private session ending) is
 *   re-thrown as the platform AbortError: callers release and stay silent.
 * - Everything else is an ErrorArchivos {codigo, mensaje, status, detalle,
 *   incierto, reintentarDespuesDe}. `incierto` means the request may have
 *   reached the server (a dropped connection or an unreadable reply), so a
 *   mutation must be resolved by its replay rule, never by starting another.
 * - `mensaje` is plain text, safe to put in textContent.
 */

export const TIPOS = Object.freeze(["pdf", "kmz"]);

/* Declared-size limits, equal to the server's (1B lifecycle). */
export const LIMITE_BYTES = Object.freeze({ pdf: 25 * 1024 * 1024, kmz: 20 * 1024 * 1024 });

/* The content type each kind is staged with (route 3 accepts these). */
export const TIPO_CONTENIDO = Object.freeze({
  pdf: "application/pdf",
  kmz: "application/vnd.google-earth.kmz",
});

const EXTENSION = Object.freeze({ pdf: /\.pdf$/i, kmz: /\.kmz$/i });

/* Bounds for what this client is willing to read. JSON pages hold at most 100
 * items (an attempt detail at most the parser's 500 candidate descriptions);
 * an error envelope is a few hundred bytes. */
export const JSON_MAX_BYTES = 2 * 1024 * 1024;
export const ERROR_MAX_BYTES = 64 * 1024;

export const LIMITE_PAGINA = 20;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HEX64 = /^[0-9a-f]{64}$/;

export class ErrorArchivos extends Error {
  constructor(codigo, mensaje, { status = 0, detalle = null, incierto = false,
    reintentarDespuesDe = null } = {}) {
    super(mensaje);
    this.name = "ErrorArchivos";
    this.codigo = codigo;
    this.status = status;
    this.detalle = detalle;
    this.incierto = incierto;
    this.reintentarDespuesDe = reintentarDespuesDe;
  }
}

/* Readable text for the codes this client produces itself, and a fallback for
 * server codes whose envelope carried no message. */
const MENSAJES = {
  red: "No se pudo confirmar la respuesta del servidor. Revisa la conexión y vuelve a intentarlo.",
  respuesta_ilegible: "La respuesta del servidor llegó incompleta. Vuelve a intentarlo.",
  respuesta_excesiva: "La respuesta del servidor es más grande de lo permitido.",
  tipo_no_permitido: "El archivo no es del tipo esperado.",
  archivo_vacio: "El archivo está vacío.",
  archivo_grande: "El archivo supera el tamaño permitido.",
  descarga_inconsistente: "El archivo descargado no coincide con el registrado. No se abrió.",
  not_found: "Este archivo ya no está disponible.",
  unauthenticated: "Tu sesión terminó. Vuelve a entrar.",
};

export function mensajeDe(codigo, respaldo) {
  return MENSAJES[codigo] ?? respaldo ?? "No se pudo completar la operación.";
}

const esAbort = (error) => error?.name === "AbortError";

export function abortError() {
  return new DOMException("La operación se canceló.", "AbortError");
}

/** Throw AbortError when `signal` (or any of several) has been aborted. */
export function comprobar(...senales) {
  for (const s of senales) if (s?.aborted) throw abortError();
}

/** A fresh idempotency key: one per logical operation, reused only with the same body. */
export function nuevaClave() {
  return crypto.randomUUID();
}

/** Lowercase hex SHA-256 of bytes (ArrayBuffer or view). */
export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Read a response body into one Uint8Array, refusing more than `maximo` bytes.
 * A declared Content-Length above the bound is refused before reading; an
 * undeclared or lying length is stopped as soon as the bound is passed.
 */
export async function leerBytes(response, maximo) {
  const declarada = response.headers.get("Content-Length");
  if (declarada !== null && /^[0-9]{1,16}$/.test(declarada) && Number(declarada) > maximo) {
    await cancelarCuerpo(response);
    throw new ErrorArchivos("respuesta_excesiva", mensajeDe("respuesta_excesiva"));
  }
  if (!response.body) return new Uint8Array(0);
  const lector = response.body.getReader();
  const partes = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await lector.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximo) {
        await lector.cancel().catch(() => {});
        throw new ErrorArchivos("respuesta_excesiva", mensajeDe("respuesta_excesiva"));
      }
      partes.push(value);
    }
  } finally {
    lector.releaseLock();
  }
  if (partes.length === 1) return partes[0];
  const salida = new Uint8Array(total);
  let desplazamiento = 0;
  for (const parte of partes) {
    salida.set(parte, desplazamiento);
    desplazamiento += parte.byteLength;
  }
  return salida;
}

async function cancelarCuerpo(response) {
  try { await response.body?.cancel(); } catch { /* already closed */ }
}

const DECODIFICADOR = new TextDecoder("utf-8", { fatal: true });

/** Strict UTF-8 then JSON; anything else is an unreadable reply. */
export function jsonDeBytes(bytes) {
  try {
    return JSON.parse(DECODIFICADOR.decode(bytes));
  } catch {
    throw new ErrorArchivos("respuesta_ilegible", mensajeDe("respuesta_ilegible"), { incierto: true });
  }
}

/* The established envelope {"error": text, "detalle": {"code": ..., ...}}. */
async function errorDeRespuesta(response) {
  let envelope = null;
  try {
    envelope = jsonDeBytes(await leerBytes(response, ERROR_MAX_BYTES));
  } catch (error) {
    if (esAbort(error)) throw error;
  }
  const detalle = envelope && typeof envelope.detalle === "object" ? envelope.detalle : null;
  const codigo = typeof detalle?.code === "string" ? detalle.code : `http_${response.status}`;
  const texto = typeof envelope?.error === "string" ? envelope.error.slice(0, 500) : null;
  const espera = Number.isInteger(detalle?.reintentar_despues_de) ? detalle.reintentar_despues_de : null;
  return new ErrorArchivos(codigo, texto ?? mensajeDe(codigo, `Error ${response.status}`), {
    status: response.status, detalle, reintentarDespuesDe: espera,
  });
}

/**
 * The attachment client over the injected private bridge.
 *
 * peticionPrivada(ruta, {method, headers, body, signal})
 *   -> Promise<{response, signal}>   (rejects AbortError when cancelled)
 */
export function crearClienteArchivos({ peticionPrivada }) {
  if (typeof peticionPrivada !== "function") throw new TypeError("peticionPrivada es obligatoria");

  async function llamar(ruta, opciones) {
    let resultado;
    try {
      resultado = await peticionPrivada(ruta, opciones);
    } catch (error) {
      if (esAbort(error)) throw error;
      // fetch reports a connection that failed or dropped as a TypeError; the
      // request may or may not have reached the server.
      throw new ErrorArchivos("red", mensajeDe("red"), { incierto: true });
    }
    return resultado;
  }

  async function json(ruta, { method = "GET", datos, clave, signal } = {}) {
    const headers = {};
    if (datos !== undefined) headers["Content-Type"] = "application/json";
    if (clave) headers["Idempotency-Key"] = clave;
    const { response, signal: alcance } = await llamar(ruta, {
      method, headers, body: datos === undefined ? undefined : JSON.stringify(datos), signal,
    });
    try {
      comprobar(alcance, signal);
      if (!response.ok) throw await errorDeRespuesta(response);
      const bytes = await leerBytes(response, JSON_MAX_BYTES);
      comprobar(alcance, signal);
      return jsonDeBytes(bytes);
    } catch (error) {
      if (esAbort(error) || alcance?.aborted || signal?.aborted) throw abortError();
      if (error instanceof ErrorArchivos) throw error;
      // The reply started but could not be read: the server may have acted.
      throw new ErrorArchivos("red", mensajeDe("red"), { incierto: true });
    }
  }

  const id = (valor) => {
    if (typeof valor !== "string" || !UUID.test(valor)) {
      throw new ErrorArchivos("not_found", mensajeDe("not_found"), { status: 404 });
    }
    return encodeURIComponent(valor.toLowerCase());
  };
  const pagina = ({ cursor, limite = LIMITE_PAGINA } = {}) => {
    const q = new URLSearchParams({ limite: String(limite) });
    if (cursor != null) q.set("cursor", String(cursor));
    return `?${q}`;
  };

  return {
    /* Route 1. `datos` = {tipo, nombre_original, tamano_declarado, sha256_declarado}. */
    iniciar: async (terrenoId, datos, clave, { signal } = {}) =>
      json(`/api/inventario/terrenos/${id(terrenoId)}/archivos`, { method: "POST", datos, clave, signal }),

    /* Route 3: the exact bytes as the body. The browser sets Content-Length. */
    async subir(versionId, tipo, blob, { signal } = {}) {
      const { response, signal: alcance } = await llamar(`/api/archivos/versiones/${id(versionId)}/contenido`, {
        method: "PUT", headers: { "Content-Type": TIPO_CONTENIDO[tipo] }, body: blob, signal,
      });
      try {
        comprobar(alcance, signal);
        if (!response.ok) throw await errorDeRespuesta(response);
        return jsonDeBytes(await leerBytes(response, JSON_MAX_BYTES));
      } catch (error) {
        if (esAbort(error) || alcance?.aborted || signal?.aborted) throw abortError();
        if (error instanceof ErrorArchivos) throw error;
        throw new ErrorArchivos("red", mensajeDe("red"), { incierto: true });
      }
    },

    /* Route 4. Repeating it on a terminal version replays the stored outcome. */
    completar: async (versionId, { signal } = {}) =>
      json(`/api/archivos/versiones/${id(versionId)}/completar`, { method: "POST", signal }),

    cancelar: async (versionId, { signal } = {}) =>
      json(`/api/archivos/versiones/${id(versionId)}/cancelar`, { method: "POST", signal }),

    /* Route 6: `seleccion` is a list of candidate indices, or null to reprocess. */
    procesar: async (versionId, seleccion, clave, { signal } = {}) =>
      json(`/api/archivos/versiones/${id(versionId)}/procesar`,
        { method: "POST", datos: { seleccion }, clave, signal }),

    activar: async (archivoId, { versionId, geometriaId, revision }, clave, { signal } = {}) =>
      json(`/api/archivos/${id(archivoId)}/activar`, {
        method: "POST", clave, signal,
        datos: { version_id: versionId, ...(geometriaId ? { geometria_id: geometriaId } : {}),
          expected_revision: revision },
      }),

    retirar: async (archivoId, revision, clave, { signal } = {}) =>
      json(`/api/archivos/${id(archivoId)}/retirar`,
        { method: "POST", datos: { expected_revision: revision }, clave, signal }),

    listar: async (terrenoId, opciones = {}) =>
      json(`/api/inventario/terrenos/${id(terrenoId)}/archivos${pagina(opciones)}`, opciones),
    historial: async (archivoId, opciones = {}) =>
      json(`/api/archivos/${id(archivoId)}/historial${pagina(opciones)}`, opciones),
    versiones: async (archivoId, opciones = {}) =>
      json(`/api/archivos/${id(archivoId)}/versiones${pagina(opciones)}`, opciones),
    intentos: async (versionId, opciones = {}) =>
      json(`/api/archivos/versiones/${id(versionId)}/intentos${pagina(opciones)}`, opciones),
    intento: async (intentoId, { signal } = {}) => json(`/api/archivos/intentos/${id(intentoId)}`, { signal }),

    /**
     * Route 9: the exact bytes of one finalized version, bounded by its kind's
     * limit and checked against the version id and SHA-256 the server sends.
     * Returns {bytes, tipoContenido, sha256}. Nothing is cached.
     */
    async descargar(versionId, tipo, { signal } = {}) {
      const { response, signal: alcance } = await llamar(
        `/api/archivos/versiones/${id(versionId)}/descarga`, { signal });
      try {
        comprobar(alcance, signal);
        if (!response.ok) throw await errorDeRespuesta(response);
        const tipoContenido = (response.headers.get("Content-Type") ?? "").split(";")[0].trim();
        const firma = response.headers.get("X-Archivo-Sha256") ?? "";
        if (tipoContenido !== TIPO_CONTENIDO[tipo] || !HEX64.test(firma)
            || (response.headers.get("X-Archivo-Version-Id") ?? "").toLowerCase() !== versionId.toLowerCase()) {
          await cancelarCuerpo(response);
          throw new ErrorArchivos("descarga_inconsistente", mensajeDe("descarga_inconsistente"));
        }
        const bytes = await leerBytes(response, LIMITE_BYTES[tipo]);
        comprobar(alcance, signal);
        const calculado = await sha256Hex(bytes);
        comprobar(alcance, signal);
        if (calculado !== firma) {
          throw new ErrorArchivos("descarga_inconsistente", mensajeDe("descarga_inconsistente"));
        }
        return { bytes, tipoContenido, sha256: calculado };
      } catch (error) {
        if (esAbort(error) || alcance?.aborted || signal?.aborted) throw abortError();
        if (error instanceof ErrorArchivos) throw error;
        throw new ErrorArchivos("red", mensajeDe("red"));
      }
    },
  };
}

/**
 * Check a chosen file before reading a byte of it: its kind (by extension,
 * since browsers report KMZ inconsistently), emptiness and the kind's limit.
 * Returns null when acceptable, else an ErrorArchivos.
 */
export function validarArchivoLocal(archivo, tipo) {
  if (!archivo || typeof archivo.size !== "number" || !TIPOS.includes(tipo)) {
    return new ErrorArchivos("tipo_no_permitido", mensajeDe("tipo_no_permitido"));
  }
  if (!EXTENSION[tipo].test(String(archivo.name ?? ""))) {
    return new ErrorArchivos("tipo_no_permitido",
      tipo === "pdf" ? "Elige un archivo PDF (.pdf)." : "Elige un archivo KMZ (.kmz).");
  }
  if (archivo.size === 0) return new ErrorArchivos("archivo_vacio", mensajeDe("archivo_vacio"));
  if (archivo.size > LIMITE_BYTES[tipo]) {
    const mb = LIMITE_BYTES[tipo] / 1024 / 1024;
    return new ErrorArchivos("archivo_grande", `El archivo supera el límite de ${mb} MB para ${tipo.toUpperCase()}.`);
  }
  return null;
}

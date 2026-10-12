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
  parte_invalida: "Una parte del archivo no es válida. Vuelve a intentarlo.",
  transferencia_inconsistente: "El servidor propuso un envío que no corresponde a este archivo.",
  contenido_temporal_ausente: "Al servidor le faltan partes de esta subida.",
  almacen_no_configurado: "El almacenamiento de archivos no está disponible en este entorno.",
  almacen_no_disponible: "El almacenamiento de archivos no respondió. Vuelve a intentarlo.",
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

/* The bounded transfer (M1 contract): 3 MiB parts, at most 9 per file. */
export const PARTE_BYTES = 3 * 1024 * 1024;
export const MAX_PARTES = 9;

/** The number of parts a file of `tamano` bytes travels in. */
export const partesDe = (tamano) => Math.ceil(tamano / PARTE_BYTES);

const DECIMAL = /^(0|[1-9][0-9]{0,8})$/;
const decimal = (texto) => (texto !== null && DECIMAL.test(texto) ? Number(texto) : null);
const inconsistente = () => new ErrorArchivos("descarga_inconsistente", mensajeDe("descarga_inconsistente"));

/* One download slice's headers, checked against each other: null when any is
 * missing, malformed or contradictory. */
function cabecerasDeTramo(response, versionId, tipo) {
  const tipoContenido = (response.headers.get("Content-Type") ?? "").split(";")[0].trim().toLowerCase();
  const sha256 = response.headers.get("X-Archivo-Sha256") ?? "";
  const vid = (response.headers.get("X-Archivo-Version-Id") ?? "").toLowerCase();
  const bytes = decimal(response.headers.get("X-Archivo-Bytes"));
  const desde = decimal(response.headers.get("X-Archivo-Desde"));
  const longitud = decimal(response.headers.get("X-Archivo-Longitud"));
  const siguiente = response.headers.get("X-Archivo-Siguiente");
  if (tipoContenido !== "application/octet-stream" || !HEX64.test(sha256) || vid !== versionId.toLowerCase()
      || bytes === null || desde === null || longitud === null) return null;
  if (bytes < 1 || bytes > LIMITE_BYTES[tipo] || desde % PARTE_BYTES !== 0 || desde >= bytes
      || longitud !== Math.min(PARTE_BYTES, bytes - desde)) return null;
  const fin = desde + longitud;
  if (fin === bytes ? siguiente !== "fin" : siguiente !== String(fin)) return null;
  return { sha256, bytes, desde, longitud };
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
      // The bridge has already run the expiry teardown for a 401.
      if (error?.status === 401) throw new ErrorArchivos("unauthenticated", mensajeDe("unauthenticated"), { status: 401 });
      // A connection that failed or dropped: the request may or may not have
      // reached the server.
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

  const cliente = {
    /* Route 1. `datos` = {tipo, nombre_original, tamano_declarado, sha256_declarado}. */
    iniciar: async (terrenoId, datos, clave, { signal } = {}) =>
      json(`/api/inventario/terrenos/${id(terrenoId)}/archivos`, { method: "POST", datos, clave, signal }),

    /* Route 3, one part: PUT ?parte=N with exactly that part's bytes. The
     * browser sets Content-Length. Returns the server's part receipt. */
    async subirParte(versionId, tipo, parte, blob, { signal } = {}) {
      if (!Number.isInteger(parte) || parte < 0 || parte >= MAX_PARTES) {
        throw new ErrorArchivos("parte_invalida", mensajeDe("parte_invalida"));
      }
      const { response, signal: alcance } = await llamar(
        `/api/archivos/versiones/${id(versionId)}/contenido?parte=${parte}`, {
          method: "PUT", headers: { "Content-Type": TIPO_CONTENIDO[tipo] }, body: blob, signal,
        });
      try {
        comprobar(alcance, signal);
        if (!response.ok) throw await errorDeRespuesta(response);
        const bytes = await leerBytes(response, JSON_MAX_BYTES);
        comprobar(alcance, signal);      // the scope may end while the reply is read
        return jsonDeBytes(bytes);
      } catch (error) {
        if (esAbort(error) || alcance?.aborted || signal?.aborted) throw abortError();
        if (error instanceof ErrorArchivos) throw error;
        throw new ErrorArchivos("red", mensajeDe("red"), { incierto: true });
      }
    },

    /**
     * Route 3, the whole file: its parts in order, one request at a time.
     * `transferencia` is the start reply's {parte_bytes, partes}; it must match
     * this file's size, or nothing is sent. `partes` limits the indices sent
     * (the ones still missing); `alParte(i)` reports each confirmed part. The
     * first failure stops the sequence and is thrown as is.
     */
    async subir(versionId, tipo, blob, { signal, transferencia = null, partes = null, alParte } = {}) {
      const total = partesDe(blob.size);
      if (transferencia && (transferencia.parte_bytes !== PARTE_BYTES || transferencia.partes !== total)) {
        throw new ErrorArchivos("transferencia_inconsistente", mensajeDe("transferencia_inconsistente"));
      }
      const indices = partes ? [...new Set(partes)].sort((a, b) => a - b) : [...Array(total).keys()];
      for (const i of indices) {
        if (!Number.isInteger(i) || i < 0 || i >= total) {
          throw new ErrorArchivos("parte_invalida", mensajeDe("parte_invalida"));
        }
      }
      let ultimo = {};
      for (const i of indices) {
        comprobar(signal);
        const inicio = i * PARTE_BYTES;
        ultimo = await cliente.subirParte(versionId, tipo, i,
          blob.slice(inicio, Math.min(blob.size, inicio + PARTE_BYTES)), { signal });
        alParte?.(i, total);
      }
      return ultimo;
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
     * Route 9: the exact bytes of one finalized version, read in slices of at
     * most 3 MiB (`?desde=O`). Every slice must name the same version, total
     * size and SHA-256, start where the previous one ended and carry exactly
     * the length announced; the whole file is then hashed before it is
     * returned. Nothing is kept on failure or cancellation, and nothing is
     * cached. The total is bounded by the kind's limit before a byte is kept.
     * Returns {bytes, tipoContenido, sha256}; `alProgreso(recibidos, total)`.
     */
    async descargar(versionId, tipo, { signal, alProgreso } = {}) {
      const ruta = `/api/archivos/versiones/${id(versionId)}/descarga`;
      let salida = null;
      let firma = null;
      let total = null;
      let desde = 0;
      try {
        for (let vuelta = 0; vuelta < MAX_PARTES; vuelta += 1) {
          const { response, signal: alcance } = await llamar(desde ? `${ruta}?desde=${desde}` : ruta, { signal });
          try {
            comprobar(alcance, signal);
            if (!response.ok) throw await errorDeRespuesta(response);
            const tramo = cabecerasDeTramo(response, versionId, tipo);
            if (!tramo || tramo.desde !== desde || (firma !== null && (tramo.sha256 !== firma || tramo.bytes !== total))) {
              await cancelarCuerpo(response);
              throw inconsistente();
            }
            firma = tramo.sha256;
            total = tramo.bytes;
            salida ??= new Uint8Array(total);
            const bytes = await leerBytes(response, tramo.longitud);
            comprobar(alcance, signal);
            if (bytes.byteLength !== tramo.longitud) throw inconsistente();
            salida.set(bytes, desde);
            desde += tramo.longitud;
            alProgreso?.(desde, total);
          } catch (error) {
            if (esAbort(error) || alcance?.aborted || signal?.aborted) throw abortError();
            throw error;
          }
          if (desde === total) {
            const calculado = await sha256Hex(salida);
            comprobar(signal);
            if (calculado !== firma) throw inconsistente();
            const resultado = { bytes: salida, tipoContenido: TIPO_CONTENIDO[tipo], sha256: calculado };
            salida = null;
            return resultado;
          }
        }
        throw inconsistente();
      } catch (error) {
        salida = null;                  // a partial or unverified file is never handed out
        if (esAbort(error) || signal?.aborted) throw abortError();
        if (error instanceof ErrorArchivos) throw error;
        throw new ErrorArchivos("red", mensajeDe("red"));
      }
    },
  };
  return cliente;
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

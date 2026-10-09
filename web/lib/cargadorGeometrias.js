/* Bounded, cancellable loader for ONE selected boundary body (Round 3, 3B).
 *
 *   crearCargadorGeometrias({peticionPrivada})
 *     -> {cargar({terrenoId, geometria}, {signal}) -> Promise<cuerpo>, reset(), destroy()}
 *
 * `geometria` is the record's active descriptor (shared contract §4). The
 * body comes from the frozen 2B routes: one metadata POST, then 512 KiB byte
 * chunks. Every metadata field and chunk header is checked against what was
 * asked for; the bytes are reassembled across chunk boundaries, the whole-body
 * SHA-256 is verified, and only then is the text strictly decoded as UTF-8 and
 * parsed. `cuerpo` is the accepted B-2 body shape the unchanged renderer takes
 * in `options.geometrias`: {geojson, bbox, punto_interior, partes, huecos,
 * vertices, area_aproximada_m2} plus the identifiers it was verified against.
 *
 * Residency (deliberately narrow for Round 3): one load in flight, at most one
 * latest replacement waiting, one ready body kept. A newer request cancels the
 * one in flight and replaces any waiting one, which rejects with AbortError.
 * reset()/destroy() forget everything and forbid late installs. No cache, no
 * worker, no simplification. A failure is an ErrorGeometria, never a partial
 * body.
 */

import { descriptorActivo, bboxValido, puntoValido } from "./geometria.js";

export const METADATOS_MAX_BYTES = 128 * 1024;
export const FRAGMENTO_BYTES = 512 * 1024;
export const CUERPO_MAX_BYTES = 16 * 1024 * 1024;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const ENTERO = /^[0-9]{1,9}$/;

const MENSAJES = {
  descriptor_invalido: "Este terreno no tiene un contorno activo que se pueda cargar.",
  no_disponible: "El contorno ya no está disponible. Actualiza la información del terreno.",
  obsoleta: "El contorno cambió. Actualiza la información del terreno.",
  metadatos_invalidos: "La información del contorno no coincide con la del terreno. No se dibujó.",
  demasiado_grande: "El contorno supera el tamaño permitido. No se dibujó.",
  fragmento_invalido: "Una parte del contorno llegó alterada. No se dibujó.",
  hash_no_coincide: "El contorno descargado no coincide con el registrado. No se dibujó.",
  contenido_invalido: "El contorno descargado no es válido. No se dibujó.",
  red: "No se pudo descargar el contorno. Revisa la conexión y vuelve a intentarlo.",
  servidor: "El servidor no pudo entregar el contorno. Vuelve a intentarlo.",
  destruido: "El cargador ya no está activo.",
};

export class ErrorGeometria extends Error {
  constructor(codigo, { status = 0, detalle = null } = {}) {
    super(MENSAJES[codigo] ?? MENSAJES.servidor);
    this.name = "ErrorGeometria";
    this.codigo = codigo;
    this.status = status;
    this.detalle = detalle;
  }
}

const abortError = () => new DOMException("La carga se canceló.", "AbortError");
const esAbort = (e) => e?.name === "AbortError";
const DECODIFICADOR = new TextDecoder("utf-8", { fatal: true });

function hex(digest) {
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

const mismaCaja = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === 4
  && a.every((v, i) => v === b[i]);
const mismoPunto = (a, b) => puntoValido(a) && puntoValido(b)
  && a.coordinates[0] === b.coordinates[0] && a.coordinates[1] === b.coordinates[1];

/* Bounded read of one response body; `exacto` demands that many bytes. */
async function leer(response, maximo, exacto) {
  const declarada = response.headers.get("Content-Length");
  if (declarada !== null) {
    if (!ENTERO.test(declarada) || Number(declarada) > maximo
        || (exacto !== undefined && Number(declarada) !== exacto)) {
      try { await response.body?.cancel(); } catch { /* closed */ }
      throw new ErrorGeometria(exacto === undefined ? "demasiado_grande" : "fragmento_invalido");
    }
  }
  const salida = new Uint8Array(exacto ?? maximo);
  let total = 0;
  if (response.body) {
    const lector = response.body.getReader();
    try {
      for (;;) {
        const { done, value } = await lector.read();
        if (done) break;
        if (total + value.byteLength > salida.byteLength) {
          await lector.cancel().catch(() => {});
          throw new ErrorGeometria(exacto === undefined ? "demasiado_grande" : "fragmento_invalido");
        }
        salida.set(value, total);
        total += value.byteLength;
      }
    } finally {
      lector.releaseLock();
    }
  }
  if (exacto !== undefined && total !== exacto) throw new ErrorGeometria("fragmento_invalido");
  return exacto === undefined ? salida.subarray(0, total) : salida;
}

async function errorHttp(response) {
  let detalle = null;
  try {
    const envelope = JSON.parse(DECODIFICADOR.decode(await leer(response, 64 * 1024)));
    detalle = envelope?.detalle ?? null;
  } catch (e) {
    if (esAbort(e)) throw e;
  }
  const codigo = response.status === 404 ? "no_disponible" : "servidor";
  return new ErrorGeometria(codigo, { status: response.status, detalle });
}

/* The descriptor this loader accepts: active, usable, well-formed, with UUIDs. */
function validarPeticion(terrenoId, geometria) {
  if (typeof terrenoId !== "string" || !UUID.test(terrenoId)
      || !descriptorActivo(geometria) || !UUID.test(geometria.id)
      || typeof geometria.archivo_version_id !== "string" || !UUID.test(geometria.archivo_version_id)) {
    throw new ErrorGeometria("descriptor_invalido");
  }
}

/* The metadata must describe exactly the requested, still active geometry. */
function validarMetadatos(meta, terrenoId, geometria) {
  if (meta === null || typeof meta !== "object") throw new ErrorGeometria("metadatos_invalidos");
  if (meta.id !== geometria.id || meta.terreno_id !== terrenoId
      || meta.archivo_version_id !== geometria.archivo_version_id) {
    throw new ErrorGeometria("metadatos_invalidos");
  }
  if (meta.activa !== true || meta.utilizable !== true) throw new ErrorGeometria("obsoleta");
  if (!bboxValido(meta.bbox) || !mismaCaja(meta.bbox, geometria.bbox)
      || !mismoPunto(meta.punto_interior, geometria.punto_interior)) {
    throw new ErrorGeometria("metadatos_invalidos");
  }
  if (!Number.isInteger(meta.bytes) || meta.bytes < 1) throw new ErrorGeometria("metadatos_invalidos");
  if (meta.bytes > CUERPO_MAX_BYTES) throw new ErrorGeometria("demasiado_grande");
  if (![meta.partes, meta.huecos, meta.vertices].every((n) => Number.isInteger(n) && n >= 0)
      || !(meta.area_aproximada_m2 === null || Number.isFinite(meta.area_aproximada_m2))) {
    throw new ErrorGeometria("metadatos_invalidos");
  }
  if (typeof meta.sha256 !== "string" || !HEX64.test(meta.sha256)
      || meta.fragmento_bytes !== FRAGMENTO_BYTES
      || meta.fragmentos !== Math.ceil(meta.bytes / FRAGMENTO_BYTES)) {
    throw new ErrorGeometria("metadatos_invalidos");
  }
}

/* Every header of one chunk against what the sequence requires. */
function validarFragmento(h, meta, desde, longitud) {
  const final = desde + longitud === meta.bytes;
  if ((h.get("Content-Type") ?? "").split(";")[0].trim() !== "application/octet-stream"
      || h.get("X-Geometria-Id") !== meta.id
      || h.get("X-Geometria-Desde") !== String(desde)
      || h.get("X-Geometria-Longitud") !== String(longitud)
      || h.get("X-Geometria-Bytes") !== String(meta.bytes)
      || h.get("X-Geometria-Sha256") !== meta.sha256
      || h.get("X-Geometria-Final") !== (final ? "1" : "0")
      || h.get("X-Geometria-Siguiente") !== (final ? "fin" : String(desde + longitud))) {
    throw new ErrorGeometria("fragmento_invalido");
  }
}

function cuerpoDe(geojson, meta) {
  if (geojson === null || typeof geojson !== "object" || geojson.type !== "MultiPolygon"
      || !Array.isArray(geojson.coordinates) || geojson.coordinates.length === 0) {
    throw new ErrorGeometria("contenido_invalido");
  }
  return {
    geojson,
    bbox: meta.bbox.slice(),
    punto_interior: { type: "Point", coordinates: meta.punto_interior.coordinates.slice() },
    partes: meta.partes,
    huecos: meta.huecos,
    vertices: meta.vertices,
    area_aproximada_m2: meta.area_aproximada_m2,
    id: meta.id,
    archivo_version_id: meta.archivo_version_id,
    terreno_id: meta.terreno_id,
    bytes: meta.bytes,
    sha256: meta.sha256,
  };
}

export function crearCargadorGeometrias({ peticionPrivada }) {
  if (typeof peticionPrivada !== "function") throw new TypeError("peticionPrivada es obligatoria");

  let generacion = 0;
  let destruido = false;
  let enCurso = null;     // {clave, control, promesa}
  let espera = null;      // {clave, control, resolve, reject, peticion}
  let listo = null;       // {clave, cuerpo}

  const claveDe = (terrenoId, geometria) => `${terrenoId}|${geometria.id}|${geometria.archivo_version_id}`;

  async function pedir(ruta, opciones, senales) {
    let resultado;
    try {
      resultado = await peticionPrivada(ruta, opciones);
    } catch (e) {
      if (esAbort(e)) throw e;
      throw new ErrorGeometria("red");
    }
    for (const s of [...senales, resultado.signal]) if (s?.aborted) throw abortError();
    return resultado;
  }

  /* One verified load. Throws AbortError as soon as it becomes obsolete. */
  async function descargar(terrenoId, geometria, control, signalExterna) {
    const gen = generacion;
    const senales = [control.signal, signalExterna];
    const vigente = (alcance) => {
      if (gen !== generacion || destruido || control.signal.aborted || signalExterna?.aborted
          || alcance?.aborted) {
        throw abortError();
      }
    };
    const signal = signalExterna ? AbortSignal.any([control.signal, signalExterna]) : control.signal;

    const { response: rm, signal: alcanceMeta } = await pedir("/api/archivos/geometrias/metadatos", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: [geometria.id] }), signal,
    }, senales);
    vigente(alcanceMeta);
    if (!rm.ok) throw await errorHttp(rm);
    let sobre;
    try {
      sobre = JSON.parse(DECODIFICADOR.decode(await leer(rm, METADATOS_MAX_BYTES)));
    } catch (e) {
      if (esAbort(e) || e instanceof ErrorGeometria) throw e;
      throw new ErrorGeometria("metadatos_invalidos");
    }
    vigente(alcanceMeta);
    if (Array.isArray(sobre?.no_disponibles) && sobre.no_disponibles.includes(geometria.id)) {
      throw new ErrorGeometria("no_disponible");
    }
    const meta = sobre?.geometrias?.[geometria.id];
    validarMetadatos(meta, terrenoId, geometria);

    // The whole body is bounded (<= 16 MiB) and allocated once.
    let bytes = new Uint8Array(meta.bytes);
    try {
      for (let desde = 0; desde < meta.bytes; desde += FRAGMENTO_BYTES) {
        const longitud = Math.min(FRAGMENTO_BYTES, meta.bytes - desde);
        const { response: rc, signal: alcance } = await pedir(
          `/api/archivos/geometrias/${encodeURIComponent(meta.id)}/contenido?desde=${desde}`,
          { signal }, senales);
        vigente(alcance);
        if (!rc.ok) throw await errorHttp(rc);
        validarFragmento(rc.headers, meta, desde, longitud);
        const parte = await leer(rc, FRAGMENTO_BYTES, longitud);
        vigente(alcance);
        bytes.set(parte, desde);
      }
      const digest = hex(await crypto.subtle.digest("SHA-256", bytes));
      vigente();
      if (digest !== meta.sha256) throw new ErrorGeometria("hash_no_coincide");
      let geojson;
      try {
        geojson = JSON.parse(DECODIFICADOR.decode(bytes));
      } catch {
        throw new ErrorGeometria("contenido_invalido");
      }
      vigente();
      return cuerpoDe(geojson, meta);
    } finally {
      bytes = null;   // the raw buffer is released whatever happens
    }
  }

  function iniciar(peticion) {
    const control = new AbortController();
    const actual = { clave: peticion.clave, control, promesa: null };
    actual.promesa = (async () => {
      try {
        const cuerpo = await descargar(peticion.terrenoId, peticion.geometria, control, peticion.signal);
        if (enCurso !== actual || destruido) throw abortError();
        listo = { clave: peticion.clave, cuerpo };      // replaces (releases) the previous one
        return cuerpo;
      } catch (error) {
        if (esAbort(error) || control.signal.aborted) throw abortError();
        throw error;
      } finally {
        if (enCurso === actual) enCurso = null;
        siguiente();
      }
    })();
    enCurso = actual;
    return actual.promesa;
  }

  /* Start the waiting request once the obsolete one has let go. */
  function siguiente() {
    if (enCurso || !espera) return;
    const p = espera;
    espera = null;
    if (p.signal?.aborted || destruido) { p.reject(abortError()); return; }
    iniciar(p).then(p.resolve, p.reject);
  }

  function cargar({ terrenoId, geometria } = {}, { signal } = {}) {
    if (destruido) return Promise.reject(new ErrorGeometria("destruido"));
    try {
      validarPeticion(terrenoId, geometria);
    } catch (e) {
      return Promise.reject(e);
    }
    if (signal?.aborted) return Promise.reject(abortError());
    const clave = claveDe(terrenoId, geometria);
    if (listo?.clave === clave) return Promise.resolve(listo.cuerpo);
    if (enCurso?.clave === clave) return enCurso.promesa;
    if (espera?.clave === clave) return espera.promesa;

    // A different body is wanted: what is ready or in flight is obsolete.
    listo = null;
    if (espera) { espera.reject(abortError()); espera = null; }
    if (!enCurso) return iniciar({ clave, terrenoId, geometria, signal });
    enCurso.control.abort();
    const nueva = { clave, terrenoId, geometria, signal };
    nueva.promesa = new Promise((resolve, reject) => { nueva.resolve = resolve; nueva.reject = reject; });
    espera = nueva;
    signal?.addEventListener("abort", () => {
      if (espera === nueva) { espera = null; nueva.reject(abortError()); }
    }, { once: true });
    return nueva.promesa;
  }

  function reset() {
    generacion += 1;
    listo = null;
    if (espera) { espera.reject(abortError()); espera = null; }
    if (enCurso) enCurso.control.abort();
  }

  return {
    cargar,
    reset,
    destroy() {
      if (destruido) return;
      reset();
      destruido = true;
    },
    /** For tests and the host's diagnostics: counts only, never bodies. */
    estado: () => ({ enCurso: enCurso ? 1 : 0, enEspera: espera ? 1 : 0, listos: listo ? 1 : 0,
      destruido }),
  };
}

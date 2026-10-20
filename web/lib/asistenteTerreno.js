/* The terrain assistant's client (issue #65): the contract of
 * /api/asistente-terreno and one panel's request state, without the DOM.
 *
 * Everything goes through peticionPrivada, so a request is tied to the
 * private session it was made in: a logout cancels it and its answer is
 * never shown. The answers live only in the controller's memory; nothing is
 * written to storage or to the URL, and destroying the panel forgets them.
 *
 * What the browser sends is the action and, for a question, its text. The
 * server reads the terrain itself; the client never sends records, history
 * or instructions.
 */

import { peticionPrivada } from "./api.js";

export const ACCIONES = Object.freeze([
  Object.freeze({ accion: "resumen", etiqueta: "Resumir el terreno" }),
  Object.freeze({ accion: "faltantes", etiqueta: "Campos sin información" }),
  Object.freeze({ accion: "descripcion", etiqueta: "Redactar descripción breve" }),
]);
const ETIQUETAS = { resumen: "Resumen", faltantes: "Campos sin información", descripcion: "Descripción breve", pregunta: "Pregunta" };
const VALIDAS = new Set(Object.keys(ETIQUETAS));

/** The registered fields the server may send to the model (contract of #65), as the UI names them. */
export const CAMPOS_ENVIADOS = Object.freeze([
  "Estado", "Municipio", "Tipo de terreno", "Superficie (m²)", "Superficie (ha)", "Precio total",
  "Precio por m²", "Moneda", "Precio a consultar", "Disponibilidad",
]);

export const MAX_PREGUNTA = 500;
/* The server gives up on the provider well before this; the browser stops
 * waiting here so a stalled connection never keeps the panel busy. */
export const ESPERA_MAXIMA_MS = 60_000;
/* Answers kept on screen for one terrain; older ones are dropped. */
export const MAX_ENTRADAS = 20;

const RUTA = "/api/asistente-terreno";
const APAGADO = Object.freeze({ habilitado: false, disponible: false, max_pregunta: MAX_PREGUNTA });

/** Length in characters as the server counts them (code points, not UTF-16 units). */
export const largo = (texto) => [...texto].length;

/**
 * Whether the assistant is on, for an administrator. Anything but a valid
 * 200 reads as off: the button simply does not appear. A 401 runs the
 * session teardown inside peticionPrivada; a cancellation rejects.
 */
export async function leerConfig(signal) {
  const { response } = await peticionPrivada(`${RUTA}/config`, { headers: { Accept: "application/json" }, signal });
  if (!response.ok) { response.body?.cancel().catch(() => {}); return APAGADO; }
  let datos;
  try { datos = await response.json(); } catch { return APAGADO; }
  if (signal?.aborted) throw new DOMException("La petición se canceló.", "AbortError");
  return normalizarConfig(datos);
}

export function normalizarConfig(datos) {
  if (!datos || typeof datos !== "object") return APAGADO;
  const max = Number.isInteger(datos.max_pregunta) && datos.max_pregunta > 0
    ? Math.min(datos.max_pregunta, MAX_PREGUNTA) : MAX_PREGUNTA;
  const habilitado = datos.habilitado === true;
  return Object.freeze({ habilitado, disponible: habilitado && datos.disponible === true, max_pregunta: max });
}

/* ------------------------------------------------------------- errors */

const MENSAJES = {
  chat_deshabilitado: "El asistente está apagado.",
  chat_no_configurado: "El asistente no está configurado en el servidor.",
  chat_limite: "Se alcanzó el límite de consultas o ya hay otra en curso. Espera un momento y vuelve a intentarlo.",
  chat_presupuesto: "Se agotó el presupuesto aprobado para el asistente.",
  chat_no_disponible: "El servicio de IA no está disponible ahora. Inténtalo más tarde.",
  chat_tiempo: "El asistente tardó demasiado en responder. Puedes volver a intentarlo.",
  chat_respuesta_invalida: "La respuesta del asistente no era válida y se descartó. Puedes volver a intentarlo.",
};
const POR_ESTADO = {
  401: "Inicia sesión para continuar.",
  403: "Tu cuenta no tiene permiso para usar el asistente.",
  404: "Este terreno ya no está disponible.",
  409: "El terreno cambió durante la consulta y la respuesta se descartó. Cierra y vuelve a abrir el detalle.",
  422: "La consulta no es válida. Revisa la pregunta e inténtalo de nuevo.",
  429: MENSAJES.chat_limite,
  503: MENSAJES.chat_no_disponible,
  504: MENSAJES.chat_tiempo,
};
/* Retrying cannot help these: the person has to do something else first. */
const SIN_REINTENTO = new Set([401, 403, 404, 409]);
const CODIGOS_SIN_REINTENTO = new Set(["chat_deshabilitado", "chat_no_configurado", "chat_presupuesto", "version"]);

/** A readable error for a status and contract code. Never the server's raw text. */
export function errorDeConsulta(status, codigo) {
  const mensaje = MENSAJES[codigo] ?? POR_ESTADO[status] ??
    `No se pudo completar la consulta${status ? ` (error ${status})` : ""}. Puedes volver a intentarlo.`;
  const reintentable = !SIN_REINTENTO.has(status) && !CODIGOS_SIN_REINTENTO.has(codigo);
  return Object.assign(new Error(mensaje), { status: status ?? null, codigo: codigo ?? null, reintentable });
}

/* ---------------------------------------------------------- the answer */

const texto = (v) => (typeof v === "string" ? v : typeof v === "number" && Number.isFinite(v) ? String(v) : null);

/**
 * The 200 body checked against the contract, as plain strings and frozen
 * lists, or null when it does not match: another terrain or action, a
 * missing answer, an unknown origin. List items that are not well formed
 * are dropped. Nothing here is ever treated as markup or as a link.
 */
export function validarRespuesta(datos, { terrenoId, accion }) {
  if (!datos || typeof datos !== "object") return null;
  if (datos.terreno_id !== terrenoId || datos.accion !== accion) return null;
  if (!Number.isInteger(datos.version)) return null;
  if (typeof datos.respuesta !== "string" || !datos.respuesta.trim()) return null;
  if (datos.origen !== "modelo" && datos.origen !== "reglas") return null;
  const lista = (v) => (Array.isArray(v) ? v : []);
  const campos = lista(datos.campos_usados).flatMap((c) => {
    const campo = texto(c?.campo), etiqueta = texto(c?.etiqueta), valor = texto(c?.valor);
    return campo && etiqueta && valor != null ? [Object.freeze({ campo, etiqueta, valor })] : [];
  });
  const faltantes = lista(datos.faltantes).flatMap((c) => {
    const campo = texto(c?.campo), etiqueta = texto(c?.etiqueta);
    return campo && etiqueta ? [Object.freeze({ campo, etiqueta })] : [];
  });
  const advertencias = lista(datos.advertencias).flatMap((a) => (typeof a === "string" && a.trim() ? [a] : []));
  return Object.freeze({
    terreno_id: datos.terreno_id, version: datos.version, accion: datos.accion,
    respuesta: datos.respuesta.trim(), origen: datos.origen,
    campos_usados: Object.freeze(campos), faltantes: Object.freeze(faltantes),
    advertencias: Object.freeze(advertencias),
  });
}

/**
 * POST one independent query. Resolves the validated answer; rejects with
 * errorDeConsulta(...) or, when cancelled, an AbortError.
 */
export async function consultar(terrenoId, { accion, pregunta = "" }, signal) {
  const ruta = `${RUTA}/${encodeURIComponent(terrenoId)}/consultar`;
  let response;
  try {
    ({ response } = await peticionPrivada(ruta, {
      method: "POST", signal,
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ accion, pregunta: accion === "pregunta" ? pregunta : "" }),
    }));
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    if (error?.status === 401) throw errorDeConsulta(401);
    throw Object.assign(new Error(error?.message || "No se pudo conectar con el servidor."),
      { status: null, codigo: null, reintentable: true });
  }
  let datos = null;
  try { datos = await response.json(); } catch {
    if (signal?.aborted) throw new DOMException("La petición se canceló.", "AbortError");
  }
  if (signal?.aborted) throw new DOMException("La petición se canceló.", "AbortError");
  if (!response.ok) throw errorDeConsulta(response.status, datos?.detalle?.code);
  const valida = validarRespuesta(datos, { terrenoId, accion });
  if (!valida) throw errorDeConsulta(null, "chat_respuesta_invalida");
  return valida;
}

/* ------------------------------------------------------ one panel's state */

/**
 * The request state of one panel, for one terrain at one version.
 *
 *   const a = crearAsistente({ terrenoId, version, onCambio });
 *   a.pedir("resumen");  a.pedir("pregunta", "¿…?");  a.reintentar();
 *   a.dejarDeEsperar();  a.destroy();
 *
 * `a.estado` is replaced on every change, never mutated:
 *   { fase: "inactivo" | "esperando" | "error", pendiente, error, entradas }
 * One request at a time: pedir() answers false while one is in flight, so a
 * double click sends nothing twice. An answer that arrives after
 * dejarDeEsperar(), destroy() or the session's end is dropped. An answer for
 * another version than the one on screen is not shown as current.
 */
export function crearAsistente({ terrenoId, version, onCambio = () => {}, consultarCon = consultar,
  esperaMaxima = ESPERA_MAXIMA_MS }) {
  let vivo = true;
  let control = null;
  let ultima = null;           // the last request, for a manual retry
  let numero = 0;
  let estado = Object.freeze({ fase: "inactivo", pendiente: null, error: null, entradas: Object.freeze([]) });

  const cambiar = (cambios) => {
    estado = Object.freeze({ ...estado, ...cambios });
    if (vivo) onCambio(estado);
  };
  const soltar = () => {
    control?.abort();
    control = null;
  };

  async function enviar(peticion) {
    const yo = control = new AbortController();
    const n = numero += 1;
    ultima = peticion;
    cambiar({ fase: "esperando", pendiente: peticion, error: null });
    const reloj = setTimeout(() => yo.abort(new DOMException("tiempo", "TimeoutError")), esperaMaxima);
    try {
      const respuesta = await consultarCon(terrenoId, peticion, yo.signal);
      if (!vivo || n !== numero) return;
      if (respuesta.version !== version) {
        throw errorDeConsulta(409, "version");
      }
      const entrada = Object.freeze({ n, ...peticion, ...respuesta });
      cambiar({ fase: "inactivo", pendiente: null, error: null,
        entradas: Object.freeze([...estado.entradas, entrada].slice(-MAX_ENTRADAS)) });
    } catch (error) {
      if (!vivo || n !== numero) return;
      if (error?.name === "AbortError" || error?.name === "TimeoutError") {
        if (yo.signal.reason?.name !== "TimeoutError") return;       // abandoned or the session ended
        error = errorDeConsulta(null, "chat_tiempo");
      }
      cambiar({ fase: "error", pendiente: null, error: Object.freeze({
        mensaje: error.message, reintentable: error.reintentable !== false, codigo: error.codigo ?? null,
      }) });
    } finally {
      clearTimeout(reloj);
      if (control === yo) control = null;
    }
  }

  return {
    get estado() { return estado; },
    get ocupado() { return estado.fase === "esperando"; },
    /** Send one action. False when one is already waiting or the input is not valid. */
    pedir(accion, pregunta = "") {
      if (!vivo || estado.fase === "esperando" || !VALIDAS.has(accion)) return false;
      const limpia = accion === "pregunta" ? pregunta.trim() : "";
      if (accion === "pregunta" && (!limpia || largo(limpia) > MAX_PREGUNTA)) return false;
      enviar(Object.freeze({ accion, pregunta: limpia }));
      return true;
    },
    reintentar() {
      if (!vivo || estado.fase !== "error" || !estado.error?.reintentable || !ultima) return false;
      enviar(ultima);
      return true;
    },
    /** Stop waiting. The server may still finish it; its answer is dropped. */
    dejarDeEsperar() {
      if (!vivo || estado.fase !== "esperando") return;
      numero += 1;
      soltar();
      cambiar({ fase: "inactivo", pendiente: null, error: null });
    },
    /** Forget everything: what is pending is cancelled and the answers are dropped. */
    destroy() {
      if (!vivo) return;
      vivo = false;
      numero += 1;
      soltar();
      ultima = null;
      estado = Object.freeze({ fase: "inactivo", pendiente: null, error: null, entradas: Object.freeze([]) });
    },
  };
}

export const etiquetaDeAccion = (accion) => ETIQUETAS[accion] ?? accion;

/* The assistant over the master table (issue #69): search by a question and
 * compare two or three results. The contract of /api/asistente-terreno/
 * {buscar,resultados,comparar} and one panel's state, without the DOM.
 *
 * As with the one-terrain assistant (asistenteTerreno.js), every request goes
 * through peticionPrivada, so a logout cancels it and its answer is never
 * shown; the state lives only in memory and destroy() forgets it. One request
 * at a time per panel; an answer that arrives after a newer action, after
 * giving up or after closing is dropped.
 */

import { peticionPrivada } from "./api.js";
import { ESPERA_MAXIMA_MS, MAX_PREGUNTA, errorDeConsulta, largo } from "./asistenteTerreno.js";

export const MAX_SELECCION = 3;
export const MIN_SELECCION = 2;
export const SIN_INFORMACION = "Sin información registrada";
const RUTA = "/api/asistente-terreno";

/* ------------------------------------------------------------ requests */

async function enviar(ruta, cuerpo, signal) {
  let response;
  try {
    ({ response } = await peticionPrivada(`${RUTA}/${ruta}`, {
      method: "POST", signal,
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(cuerpo),
    }));
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    if (error?.status === 401) throw errorDeConsulta(401);
    throw Object.assign(new Error(error?.message || "No se pudo conectar con el servidor."),
      { status: null, codigo: null, reintentable: true });
  }
  let datos = null;
  try { datos = await response.json(); } catch { /* checked below */ }
  if (signal?.aborted) throw new DOMException("La petición se canceló.", "AbortError");
  if (!response.ok) throw errorDeConsulta(response.status, datos?.detalle?.code);
  return datos;
}

const texto = (v) => (typeof v === "string" ? v : null);
const lista = (v) => (Array.isArray(v) ? v : []);
const campos = (v) => Object.freeze(lista(v).flatMap((c) => {
  const campo = texto(c?.campo), etiqueta = texto(c?.etiqueta), valor = texto(c?.valor);
  return campo && etiqueta && valor != null ? [Object.freeze({ campo, etiqueta, valor })] : [];
}));

/** A search or page answer checked against the contract, or null. */
export function validarBusqueda(d) {
  if (!d || typeof d !== "object" || !["modelo", "reglas"].includes(d.origen)) return null;
  if (d.estado === "aclaracion") {
    return typeof d.aclaracion === "string" && d.aclaracion.trim()
      ? Object.freeze({ estado: "aclaracion", aclaracion: d.aclaracion.trim(), origen: d.origen }) : null;
  }
  if (d.estado !== "resultados" || !Number.isInteger(d.total) || d.total < 0) return null;
  if (!d.filtros || typeof d.filtros !== "object" || Array.isArray(d.filtros)) return null;
  if (d.next_cursor !== null && typeof d.next_cursor !== "string") return null;
  const terrenos = lista(d.terrenos).flatMap((t) => (
    typeof t?.terreno_id === "string" && Number.isInteger(t.version) && typeof t.nombre === "string"
      ? [Object.freeze({ terreno_id: t.terreno_id, version: t.version, nombre: t.nombre,
        base_id: typeof t.base_id === "string" ? t.base_id : null, campos_usados: campos(t.campos_usados) })]
      : []));
  if (terrenos.length !== lista(d.terrenos).length) return null;
  const criterios = Object.freeze(lista(d.criterios).flatMap((c) => (typeof c?.texto === "string" ? [c.texto] : [])));
  return Object.freeze({ estado: "resultados", origen: d.origen, criterios, filtros: d.filtros,
    total: d.total, terrenos: Object.freeze(terrenos), next_cursor: d.next_cursor });
}

/** A comparison answer checked against the request, or null. */
export function validarComparacion(d, seleccion) {
  if (!d || typeof d !== "object") return null;
  const terrenos = lista(d.terrenos);
  if (terrenos.length !== seleccion.length) return null;
  const ok = terrenos.every((t, i) => t?.terreno_id === seleccion[i].terreno_id
    && t.version === seleccion[i].version && typeof t.alias === "string" && typeof t.nombre === "string");
  if (!ok) return null;
  const filas = lista(d.filas).flatMap((f) => (
    typeof f?.etiqueta === "string" && lista(f.valores).length === terrenos.length
      && f.valores.every((v) => typeof v === "string")
      ? [Object.freeze({ campo: String(f.campo ?? ""), etiqueta: f.etiqueta, valores: Object.freeze([...f.valores]) })]
      : []));
  if (!filas.length) return null;
  const r = d.resumen;
  const resumen = r?.estado === "ok" && typeof r.texto === "string" && r.texto.trim() && r.origen === "modelo"
    ? Object.freeze({ estado: "ok", texto: r.texto.trim(), origen: "modelo" })
    : Object.freeze({ estado: "error", codigo: typeof r?.code === "string" ? r.code : null });
  return Object.freeze({
    terrenos: Object.freeze(terrenos.map((t) => Object.freeze({ alias: t.alias, terreno_id: t.terreno_id,
      version: t.version, nombre: t.nombre, base_id: typeof t.base_id === "string" ? t.base_id : null }))),
    filas: Object.freeze(filas),
    advertencias: Object.freeze(lista(d.advertencias).filter((a) => typeof a === "string" && a.trim())),
    resumen,
  });
}

export const buscar = (pregunta, signal) => enviar("buscar", { pregunta }, signal);
export const resultados = (filtros, cursor, signal) => enviar("resultados", { filtros, cursor }, signal);
export const comparar = (seleccion, signal) => enviar("comparar",
  { terrenos: seleccion.map((t) => ({ id: t.terreno_id, version: t.version })) }, signal);

/* ------------------------------------------------------ one panel's state */

const VACIO = Object.freeze({ fase: "inactivo", busqueda: null, seleccion: Object.freeze([]),
  comparacion: null, error: null });

/**
 * The state of one search panel. `estado` is replaced on every change:
 *   { fase: "inactivo" | "buscando" | "paginando" | "comparando",
 *     busqueda, seleccion, comparacion, error }
 * A new search drops the previous results, selection and comparison; a
 * page adds to the results and keeps the selection. Nothing is retried on
 * its own: a retry is the person pressing the button again.
 */
export function crearBusqueda({ onCambio = () => {}, api = { buscar, resultados, comparar },
  esperaMaxima = ESPERA_MAXIMA_MS } = {}) {
  let vivo = true;
  let control = null;
  let numero = 0;
  let estado = VACIO;

  const cambiar = (cambios) => {
    estado = Object.freeze({ ...estado, ...cambios });
    if (vivo) onCambio(estado);
  };

  /** Start one request now; true when it was started. */
  function pedir(fase, hacer, aplicar) {
    if (!vivo || estado.fase !== "inactivo") return false;
    correr(fase, hacer, aplicar);
    return true;
  }

  async function correr(fase, hacer, aplicar) {
    control?.abort();
    const yo = control = new AbortController();
    const n = numero += 1;
    cambiar({ fase, error: null });
    const reloj = setTimeout(() => yo.abort(new DOMException("tiempo", "TimeoutError")), esperaMaxima);
    try {
      const datos = await hacer(yo.signal);
      if (!vivo || n !== numero) return;
      aplicar(datos);
    } catch (error) {
      if (!vivo || n !== numero) return;
      let e = error;
      if (e?.name === "AbortError" || e?.name === "TimeoutError") {
        if (yo.signal.reason?.name !== "TimeoutError") return;   // given up, or the session ended
        e = errorDeConsulta(null, "chat_tiempo");
      }
      cambiar({ fase: "inactivo", error: Object.freeze({ mensaje: e.message, codigo: e.codigo ?? null,
        status: e.status ?? null, reintentable: e.reintentable !== false, de: fase }) });
    } finally {
      clearTimeout(reloj);
      if (control === yo) control = null;
    }
  }

  const invalida = () => { throw errorDeConsulta(null, "chat_respuesta_invalida"); };

  return {
    get estado() { return estado; },
    get ocupado() { return estado.fase !== "inactivo"; },
    /** A new question: everything shown before is dropped. */
    buscar(pregunta) {
      const limpia = String(pregunta ?? "").trim();
      if (!limpia || largo(limpia) > MAX_PREGUNTA || estado.fase !== "inactivo") return false;
      cambiar({ busqueda: null, seleccion: Object.freeze([]), comparacion: null });
      return pedir("buscando", (s) => api.buscar(limpia, s), (datos) => {
        const b = validarBusqueda(datos) ?? invalida();
        cambiar({ fase: "inactivo", busqueda: Object.freeze({ ...b, pregunta: limpia }) });
      });
    },
    /** The next page of the same search: no new interpretation. */
    mas() {
      const b = estado.busqueda;
      if (b?.estado !== "resultados" || !b.next_cursor) return false;
      return pedir("paginando", (s) => api.resultados(b.filtros, b.next_cursor, s), (datos) => {
        const p = validarBusqueda(datos);
        if (!p || p.estado !== "resultados") invalida();
        const vistos = new Set(b.terrenos.map((t) => t.terreno_id));
        cambiar({ fase: "inactivo", busqueda: Object.freeze({ ...b, total: p.total, next_cursor: p.next_cursor,
          terrenos: Object.freeze([...b.terrenos, ...p.terrenos.filter((t) => !vistos.has(t.terreno_id))]) }) });
      });
    },
    /** Select or unselect a result; at most three. False when refused. */
    alternar(terrenoId) {
      if (!vivo || estado.fase !== "inactivo") return false;
      const ya = estado.seleccion.some((t) => t.terreno_id === terrenoId);
      if (ya) {
        cambiar({ seleccion: Object.freeze(estado.seleccion.filter((t) => t.terreno_id !== terrenoId)), comparacion: null });
        return true;
      }
      const t = estado.busqueda?.terrenos?.find((x) => x.terreno_id === terrenoId);
      if (!t || estado.seleccion.length >= MAX_SELECCION) return false;
      cambiar({ seleccion: Object.freeze([...estado.seleccion, t]), comparacion: null });
      return true;
    },
    comparar() {
      const sel = estado.seleccion;
      if (sel.length < MIN_SELECCION || sel.length > MAX_SELECCION) return false;
      return pedir("comparando", (s) => api.comparar(sel, s), (datos) => {
        cambiar({ fase: "inactivo", comparacion: validarComparacion(datos, sel) ?? invalida() });
      });
    },
    /** Stop waiting. The server may still finish it; its answer is dropped. */
    dejarDeEsperar() {
      if (!vivo || estado.fase === "inactivo") return;
      numero += 1;
      control?.abort();
      control = null;
      cambiar({ fase: "inactivo" });
    },
    destroy() {
      if (!vivo) return;
      vivo = false;
      numero += 1;
      control?.abort();
      control = null;
      estado = VACIO;
    },
  };
}

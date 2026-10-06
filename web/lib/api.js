/* Thin wrapper over the local JSON API. Every call surfaces a readable error. */

import { consultaDePagina } from "./inventario.js";

const BASE = "/api";
let maxUploadBytes = 25 * 1024 * 1024;

export function configureApi(config) {
  maxUploadBytes = config.maxUploadBytes ?? maxUploadBytes;
}

/* csvDecimal ("dot" | "comma") only matters for a .csv; Excel ignores it. */
function previewWorkbook(file, baseId, csvDecimal) {
  if (file.size > maxUploadBytes) {
    return Promise.reject(new Error(`El archivo supera el límite de ${maxUploadBytes / 1024 / 1024} MB.`));
  }
  const params = new URLSearchParams();
  if (baseId) params.set("base_id", baseId);
  if (csvDecimal) params.set("csv_decimal", csvDecimal);
  const query = params.toString();
  return request(`/importar/vista-previa${query ? `?${query}` : ""}`, {
    method: "POST", raw: true, body: file,
    headers: { "Content-Type": "application/octet-stream", "X-Archivo": encodeURIComponent(file.name) },
  });
}

/* The import assistant's first step: raw bytes, like the preview. */
function analyzeFile(file, baseId) {
  if (file.size > maxUploadBytes) {
    return Promise.reject(new Error(`El archivo supera el límite de ${maxUploadBytes / 1024 / 1024} MB.`));
  }
  return request(`/importar/analizar${baseId ? `?base_id=${baseId}` : ""}`, {
    method: "POST", raw: true, body: file,
    headers: { "Content-Type": "application/octet-stream", "X-Archivo": encodeURIComponent(file.name) },
  });
}

/* Everything except these is private, and is cancelled when the session ends. */
const PUBLIC_PATH = /^\/(config|session|login|logout|publico\/)/;

let privado = new AbortController();
let alExpirar = null;

/** Called with the error when a private request comes back 401. */
export function onSessionExpired(handler) { alExpirar = handler; }

/**
 * End the private scope: every pending private request is cancelled, and any
 * response that still arrives is dropped instead of reaching the screen.
 */
export function abortPrivate() {
  privado.abort();
  privado = new AbortController();
}

/* A cancelled private request never settles. Its caller simply stops, so no
 * late response repaints private data and no "aborted" error is toasted after
 * a logout. The pending closure is garbage once nothing references it. */
const nunca = () => new Promise(() => {});

const errorDeRed = () => Object.assign(
  new Error("No se pudo conectar con el servidor. Revisa la conexión e inténtalo de nuevo."),
  { red: true },
);

async function request(path, { method = "GET", body, headers = {}, raw, signal } = {}) {
  const sesion = PUBLIC_PATH.test(path) ? null : privado.signal;
  const senales = [signal, sesion].filter(Boolean);
  const senal = senales.length > 1 ? AbortSignal.any(senales) : senales[0];

  try {
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers: raw
        ? headers
        : { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
      body: raw ? body : body ? JSON.stringify(body) : undefined,
      signal: senal,
    });

    if (!response.ok) {
      let message = `Error ${response.status}`;
      let detalle = null;
      try {
        const payload = await response.json();
        if (payload?.error) message = payload.error;
        detalle = payload?.detalle ?? null;
      } catch { /* a non-JSON error body: keep the status line */ }
      if (sesion?.aborted) return nunca();
      // The status travels with the message so a caller can tell, say, a folder
      // that no longer exists (404) from a name that is taken (409).
      const error = Object.assign(new Error(message), { status: response.status, detalle });
      if (response.status === 401 && sesion) alExpirar?.(error);
      throw error;
    }
    const data = response.status === 204 ? null : await response.json();
    if (sesion?.aborted) return nunca();
    return data;
  } catch (error) {
    if (sesion?.aborted) return nunca();
    // fetch reports an unreachable server as a TypeError; anything else is real.
    if (error instanceof TypeError) throw errorDeRed();
    throw error;
  }
}

const page = (consulta, cursor) => consultaDePagina(consulta, cursor);
const enc = encodeURIComponent;

export const api = {
  config:       () => request("/config"),
  session:      () => request("/session"),
  login:        (username, password) =>
                  request("/login", { method: "POST", body: { username, password } }),
  logout:       () => request("/logout", { method: "POST" }),

  publicoTerrenos:    (consulta, cursor, signal) =>
                        request(`/publico/terrenos?${page(consulta, cursor)}`, { signal }),
  publicoTerreno:     (id, signal) => request(`/publico/terrenos/${enc(id)}`, { signal }),
  inventarioTerrenos: (consulta, cursor, signal) =>
                        request(`/inventario/terrenos?${page(consulta, cursor)}`, { signal }),
  inventarioTerreno:  (id, signal) => request(`/inventario/terrenos/${enc(id)}`, { signal }),
  // Idempotency-Key: one per logical create, reused only to retry that same body.
  crearTerreno:       (campos, clave) => request("/inventario/terrenos", {
                        method: "POST", body: campos, headers: { "Idempotency-Key": clave },
                      }),
  // `confirm` (["price", "availability"]) stamps a confirmation with this user and time.
  guardarBorrador:    (id, expected_version, changes, confirm = []) => request(`/inventario/terrenos/${enc(id)}`, {
                        method: "PATCH",
                        body: { expected_version, changes, ...(confirm.length ? { confirm } : {}) },
                      }),
  historial:          (id, cursor) => request(`/inventario/terrenos/${enc(id)}/historial` +
                        (cursor != null ? `?cursor=${enc(cursor)}` : "")),

  bases:        () => request("/bases"),
  base:         (id) => request(`/bases/${id}`),
  terrenos:     (id) => request(`/bases/${id}/terrenos`),
  renameBase:   (id, nombre) => request(`/bases/${id}`, { method: "PATCH", body: { nombre } }),
  deleteBase:   (id) => request(`/bases/${id}`, { method: "DELETE" }),
  addTerreno:   (id, datos) => request(`/bases/${id}/terrenos`, { method: "POST", body: datos }),

  preview: previewWorkbook,
  analizar: analyzeFile,
  preparar: (payload) => request("/importar/preparar", { method: "POST", body: payload }),
  formatos: () => request("/formatos"),
  renameFormato: (id, nombre) => request(`/formatos/${id}`, { method: "PATCH", body: { nombre } }),
  deleteFormato: (id) => request(`/formatos/${id}`, { method: "DELETE" }),
  confirmImport: (payload) => request("/importar/confirmar", { method: "POST", body: payload }),
  appendToBase:  (id, payload) => request(`/bases/${id}/adjuntar`, { method: "POST", body: payload }),

  moveBase:     (id, carpeta_id) => request(`/bases/${id}/carpeta`,
                                           { method: "PATCH", body: { carpeta_id } }),

  carpetas:       (tipo) => request(`/carpetas?tipo=${encodeURIComponent(tipo)}`),
  createCarpeta:  (tipo, nombre) => request("/carpetas", { method: "POST", body: { tipo, nombre } }),
  renameCarpeta:  (id, nombre) => request(`/carpetas/${id}`, { method: "PATCH", body: { nombre } }),
  deleteCarpeta:  (id) => request(`/carpetas/${id}`, { method: "DELETE" }),

  // Connected Excel (cloud only). Mutations carry an Idempotency-Key.
  microsoftEstado:   () => request("/microsoft/estado"),
  microsoftConectar: () => request("/microsoft/conectar", { method: "POST" }),
  microsoftArchivos: (cuentaId, { carpeta, q } = {}) => {
                       const p = new URLSearchParams();
                       if (carpeta) p.set("carpeta", carpeta);
                       if (q) p.set("q", q);
                       const query = p.toString();
                       return request(`/microsoft/cuentas/${enc(cuentaId)}/archivos${query ? `?${query}` : ""}`);
                     },
  excelFuentes:      () => request("/excel/fuentes"),
  excelFuente:       (id) => request(`/excel/fuentes/${enc(id)}`),
  excelVistaPrevia:  (payload) => request("/excel/vista-previa", { method: "POST", body: payload }),
  excelConectar:     (payload, clave) => request("/excel/fuentes", {
                       method: "POST", body: payload, headers: { "Idempotency-Key": clave },
                     }),
  excelActualizar:   (id, cuerpo, clave) => request(`/excel/fuentes/${enc(id)}/actualizar`, {
                       method: "POST", body: cuerpo, headers: { "Idempotency-Key": clave },
                     }),
  excelDesconectar:  (id, generacion) => request(`/excel/fuentes/${enc(id)}/desconectar`,
                                                 { method: "POST", body: { generacion } }),
  excelReactivar:    (id, generacion) => request(`/excel/fuentes/${enc(id)}/reconectar`,
                                                 { method: "POST", body: { generacion } }),

  mapas:        () => request("/mapas"),
  mapa:         (id) => request(`/mapas/${id}`),
  mapaTerrenos: (id) => request(`/mapas/${id}/terrenos`),
  createMapa:   (payload) => request("/mapas", { method: "POST", body: payload }),
  planMerge:    (mapa_ids) => request("/mapas/combinar/vista-previa",
                                      { method: "POST", body: { mapa_ids } }),
  mergeMapas:   (payload) => request("/mapas/combinar", { method: "POST", body: payload }),
  refreshMapa:  (id) => request(`/mapas/${id}/actualizar`, { method: "POST" }),
  updateMapa:   (id, payload) => request(`/mapas/${id}`, { method: "PATCH", body: payload }),
  deleteMapa:   (id) => request(`/mapas/${id}`, { method: "DELETE" }),
  moveMapa:     (id, carpeta_id) => request(`/mapas/${id}/carpeta`,
                                           { method: "PATCH", body: { carpeta_id } }),
};

/** Download an .xlsx of the given terrains, letting the browser save it. */
export async function exportXlsx({ base_id, mapa_id, ids, nombre }) {
  const response = await fetch(`${BASE}/exportar`, {
    method: "POST",
    signal: privado.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_id, mapa_id, ids, nombre }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "No se pudo exportar.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), {
    href: url, download: `${nombre || "terrenos"}.xlsx`,
  });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

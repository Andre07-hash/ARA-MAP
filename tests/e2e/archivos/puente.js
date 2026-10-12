/* Test-only stand-in for A's peticionPrivada (Round 3 INTERFACES §2), used by
 * the 3B harness ONLY when web/lib/api.js does not export the real one yet
 * (before C1). Same contract:
 *
 *   peticionPrivada(ruta, {method, headers, body, signal})
 *     -> Promise<{response, signal}>
 *
 * Same-origin /api/ paths only; same-origin credentials and no-store; the
 * caller's signal combined with the current private-session signal; a private
 * 401 runs the expiry teardown before anything reaches the caller, and the call
 * rejects AbortError like any cancelled or obsolete call. Successful bodies are
 * neither decoded nor buffered. This file is not part of the product.
 */

let privado = new AbortController();
let alExpirar = null;

const abortError = () => new DOMException("La sesión privada terminó.", "AbortError");

export function alExpirarSesion(fn) { alExpirar = fn; }

/** End the private scope: everything in flight is cancelled. */
export function terminarSesionPrivada() {
  privado.abort();
  privado = new AbortController();
}

export async function peticionPrivada(ruta, { method = "GET", headers, body, signal } = {}) {
  if (typeof ruta !== "string" || !ruta.startsWith("/api/") || ruta.startsWith("//")) {
    throw new TypeError("peticionPrivada solo acepta rutas /api/ del mismo origen");
  }
  const sesion = privado.signal;
  const senal = signal ? AbortSignal.any([signal, sesion]) : sesion;
  if (senal.aborted) throw abortError();
  const response = await fetch(ruta, { method, headers, body, signal: senal,
    credentials: "same-origin", cache: "no-store", redirect: "error" });
  if (senal.aborted) throw abortError();
  if (response.status === 401) {
    try { await response.body?.cancel(); } catch { /* closed */ }
    terminarSesionPrivada();
    alExpirar?.();
    throw abortError();
  }
  return { response, signal: senal };
}

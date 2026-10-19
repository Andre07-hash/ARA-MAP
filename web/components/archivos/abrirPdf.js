/* Opening one saved PDF version in a new tab, shared by the record detail
 * ("Abrir", "Abrir guardada") and the table cell's link and chooser.
 *
 * The bytes always come through the application's authenticated download
 * (cliente.descargar: bounded, checked against the version id and SHA-256);
 * nothing here builds a storage URL. The tab is reserved in the click itself,
 * before any await, because popup blockers only allow a window opened while
 * handling the gesture. It is cut off from this page (no opener) and shows a
 * short wait text until the PDF arrives. If the download fails or is
 * cancelled, the reserved tab is closed, so no empty tab is left behind. If
 * the browser refused the tab, the caller gets the object URL to offer as an
 * ordinary link, which the person can follow with a new click.
 *
 * A tab still waiting when this page goes away (reload, close, another
 * address) is closed too: nothing would ever fill it.
 *
 * Object URLs live in a registry that revokes each one after VIDA_URL_MS,
 * late enough for the new tab to have read it, and all of them when the
 * registry is emptied (the session ends).
 */

import { el } from "../../lib/dom.js";
import { abortError } from "../../lib/archivos.js";

export const VIDA_URL_MS = 60_000;

/** Object URLs that outlive the mount that made them, revoked by time or all at once. */
export function crearRegistroUrls() {
  const vivas = new Map();          // url -> timer
  const revocar = (url) => {
    if (!vivas.has(url)) return;
    clearTimeout(vivas.get(url));
    vivas.delete(url);
    URL.revokeObjectURL(url);
  };
  return {
    agregar(url) {
      vivas.set(url, setTimeout(() => revocar(url), VIDA_URL_MS));
      return url;
    },
    revocar,
    vaciar() { for (const url of [...vivas.keys()]) revocar(url); },
  };
}

/* Reserved tabs whose PDF has not arrived yet. */
const enEspera = new Set();
let vigilando = false;
function vigilarSalida() {
  if (vigilando || typeof window.addEventListener !== "function") return;
  vigilando = true;
  window.addEventListener("pagehide", () => {
    for (const p of enEspera) cerrarPestana(p);
    enEspera.clear();
  });
}

/**
 * Call synchronously from the click, keydown or other user gesture. Returns
 * the reserved tab, or null when the browser refused it.
 */
export function reservarPestana() {
  let pestana = null;
  try { pestana = window.open("", "_blank"); } catch { pestana = null; }
  if (!pestana) return null;
  enEspera.add(pestana);
  vigilarSalida();
  try {
    pestana.opener = null;
    pestana.document.title = "Abriendo archivo…";
    pestana.document.body.textContent = "Abriendo el archivo…";
  } catch { /* the tab is still usable without the wait text */ }
  return pestana;
}

export function cerrarPestana(pestana) {
  enEspera.delete(pestana);
  try { if (pestana && !pestana.closed) pestana.close(); } catch { /* already gone */ }
}

/**
 * Download version `versionId` and show it in `pestana` (from reservarPestana).
 * Resolves {abierta: true} when the tab received it, or {abierta: false, url,
 * cerrada} when there was no tab to receive it (`cerrada`: the person closed
 * the reserved tab; otherwise the browser refused it). Rejects with the download's error
 * (AbortError when `signal` ended); the reserved tab is closed first.
 */
export async function abrirPdf({ cliente, versionId, pestana, signal, urls }) {
  let r;
  try {
    r = await cliente.descargar(versionId, "pdf", { signal });
    if (signal?.aborted) throw abortError();
  } catch (error) {
    cerrarPestana(pestana);
    throw error;
  }
  const url = urls.agregar(URL.createObjectURL(new Blob([r.bytes], { type: r.tipoContenido || "application/pdf" })));
  enEspera.delete(pestana);
  if (pestana && !pestana.closed) {
    try {
      pestana.location.replace(url);
      return { abierta: true };
    } catch {
      cerrarPestana(pestana);
    }
  }
  return { abierta: false, url, cerrada: Boolean(pestana) };
}

/** The link offered when the tab was refused: a plain new-tab link, valid while its URL lives. */
export function enlaceDeRespaldo(url, texto = "Abrir el archivo") {
  return el("a", { href: url, target: "_blank", rel: "noopener noreferrer", class: "archivos-respaldo" }, texto);
}

export const MENSAJE_BLOQUEADO = "El navegador no permitió abrir una pestaña nueva.";
export const MENSAJE_CERRADA = "La pestaña se cerró antes de recibir el archivo.";

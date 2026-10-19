/* Choosing a KMZ/KML's contour right in the table cell.
 *
 * When a boundary file holds several contours, the cell lists them (name,
 * approximate area, parts) and "Listo" does in one step what the detail does
 * in two: process the selection (route 6) and activate the resulting
 * boundary (route 7). Nothing is activated without that click, and the
 * server's rules are the detail's: an invalid contour cannot be chosen, and a
 * changed attachment (another revision) is a conflict, not an overwrite.
 *
 * The candidates come with the upload's completion, or, for a file uploaded
 * earlier, from the version's latest attempt (routes 8 and 8b), fetched only
 * when the person asks for the list.
 */

import { el } from "../../lib/dom.js";
import { fmtArea, fmtHectares } from "../../lib/format.js";
import { ErrorArchivos, nuevaClave } from "../../lib/archivos.js";

/**
 * "Lote 2 · 1.23 ha (12,345 m²) · 2 partes · Rancho / Lotes" — what a person
 * needs to choose. The contour's own name comes first: a narrow cell wraps
 * the rest, and the folder is usually the same for every candidate.
 */
export function etiquetaCandidato(c, posicion = 0) {
  const indice = Number.isInteger(c?.indice) ? c.indice : posicion;
  const carpeta = Array.isArray(c?.carpeta) ? c.carpeta.join(" / ") : c?.carpeta;
  const area = Number.isFinite(c?.area_aproximada_m2)
    ? `${fmtHectares(c.area_aproximada_m2 / 10000)} (${fmtArea(c.area_aproximada_m2)})` : null;
  const partes = c?.partes > 1 ? `${c.partes} partes` : null;
  return [c?.nombre || `Contorno ${indice + 1}`, area, partes, carpeta].filter(Boolean).join(" · ");
}

/** The candidates of an attempt (completion or route 8b reply), or []. */
export const candidatosDe = (intento) =>
  (Array.isArray(intento?.resultado_detalle?.candidatos) ? intento.resultado_detalle.candidatos : []);

/**
 * The latest attempt of `versionId` when it asks for a choice, with its
 * candidates; null when there is nothing to choose.
 */
export async function intentoPorElegir(cliente, versionId, { signal } = {}) {
  const pagina = await cliente.intentos(versionId, { limite: 1, signal });
  const ultimo = pagina?.intentos?.[0];
  if (!ultimo || ultimo.resultado !== "requiere_seleccion") return null;
  return cliente.intento(ultimo.id, { signal });
}

/**
 * Process `seleccion` (candidate indices) of `versionId` and activate the
 * boundary it yields. Resolves with the activation's reply; rejects with an
 * ErrorArchivos (the selection's own message when it is not usable).
 *
 * The activation is at `revision`, the attachment's revision when the list
 * was shown, never a fresher one: if someone changed the file since, the
 * server answers revision_conflictiva instead of replacing their boundary.
 * `claves` keeps one idempotency key per logical step until it succeeds, and
 * a processed selection's boundary, so a retry after a failed activation
 * does not process it again.
 */
export async function elegirYActivar(cliente, { versionId, archivoId, revision, seleccion, claves, signal }) {
  const clave = (operacion) => {
    if (!claves.has(operacion)) claves.set(operacion, nuevaClave());
    return claves.get(operacion);
  };
  const paso1 = `procesar|${versionId}|${JSON.stringify(seleccion)}`;
  const hecho = `geometria|${paso1}`;
  if (!claves.has(hecho)) {
    const r = await cliente.procesar(versionId, seleccion, clave(paso1), { signal });
    claves.delete(paso1);
    if (!r?.geometria_id || r?.intento?.resultado !== "listo") {
      throw new ErrorArchivos("seleccion_invalida",
        r?.intento?.resultado_detalle?.error?.mensaje ?? "La selección no produjo un contorno utilizable.");
    }
    claves.set(hecho, r.geometria_id);
  }
  const geometriaId = claves.get(hecho);
  const paso2 = `activar|${archivoId}|${versionId}|${geometriaId}|${revision}`;
  const activado = await cliente.activar(archivoId, { versionId, geometriaId, revision }, clave(paso2), { signal });
  claves.delete(paso2);
  claves.delete(hecho);
  return activado;
}

/**
 * The inline list. `onListo` runs after a successful activation; `onCerrar`
 * when the person closes the list. Returns {element, destroy}.
 */
export function montarSelectorContornos({
  cliente, versionId, archivoId, revision, candidatos, onListo, onCerrar, onError,
}) {
  let vivo = true;
  let control = null;
  const claves = new Map();
  const casillas = [];
  const opciones = candidatos.map((c, posicion) => {
    const indice = Number.isInteger(c.indice) ? c.indice : posicion;
    const casilla = el("input", { type: "checkbox", value: String(indice), disabled: !c.valido });
    casillas.push(casilla);
    return el("label", { class: "archivos-candidato", dataset: { valido: c.valido ? "1" : "0" } }, casilla,
      el("span", {}, etiquetaCandidato(c, posicion)),
      c.error?.mensaje ? el("span", { class: "archivos-error" }, c.error.mensaje) : null);
  });
  // A single valid contour is the obvious choice: it starts checked.
  const validas = casillas.filter((x) => !x.disabled);
  if (validas.length === 1) validas[0].checked = true;

  const estado = el("p", { class: "archivos-celda-nota", role: "status", "aria-live": "polite" });
  const listo = el("button", { type: "button", class: "btn btn-principal btn-small archivos-contorno-listo" }, "Listo");
  const cerrar = el("button", { type: "button", class: "btn btn-quiet btn-small" }, "Cerrar");
  const element = el("fieldset", { class: "archivos-candidatos archivos-celda-contornos" },
    el("legend", {}, "¿Cuál es el contorno del terreno?"),
    el("p", { class: "archivos-celda-nota" },
      "Marca el contorno (o varios, si el terreno tiene varias partes) y pulsa Listo."),
    el("div", { class: "archivos-celda-contornos-lista" }, ...opciones),
    el("span", { class: "archivos-acciones" }, listo, cerrar), estado);

  listo.addEventListener("click", async () => {
    const seleccion = casillas.filter((x) => x.checked).map((x) => Number(x.value));
    if (!seleccion.length) { estado.textContent = "Marca al menos un contorno."; return; }
    control = new AbortController();
    listo.disabled = true;
    estado.textContent = "Activando el contorno…";
    try {
      await elegirYActivar(cliente, { versionId, archivoId, revision, seleccion, claves, signal: control.signal });
      if (vivo) onListo?.();
    } catch (error) {
      if (!vivo || error?.name === "AbortError") return;
      estado.textContent = error?.codigo === "revision_conflictiva"
        ? "El archivo cambió mientras tanto (otra persona lo actualizó). La tabla se actualiza; revisa antes de volver a elegir."
        : (error instanceof ErrorArchivos ? error.message : "No se pudo activar el contorno.");
      onError?.(error);
    } finally {
      control = null;
      if (vivo) listo.disabled = false;
    }
  });
  cerrar.addEventListener("click", () => onCerrar?.());
  element.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); onCerrar?.(); }
  });
  queueMicrotask(() => { if (vivo) (validas[0] ?? listo).focus(); });

  return {
    element,
    destroy() {
      vivo = false;
      control?.abort();
      element.remove();
    },
  };
}

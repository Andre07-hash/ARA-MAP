/* The mount the table reserves for a terrain's files (core:archivos, core:kmz).
 *
 * This is the host side of the adapter frozen in
 * reports/round-2-instructions-2026-10-09/INTERFACES.md:
 *
 *   mount({container, terrenoId, tipo, soloLectura, resumen, onCambio, onError})
 *     -> {update({soloLectura, resumen}), destroy()}
 *
 * Team B's widgets implement it (3B) and are registered with
 * registrarWidgetDeArchivos(); the 3A host supplies the real `resumen`. Until
 * then the slot says the integration is not available: no file count, no
 * upload control, nothing that looks like zero files.
 *
 * A mount belongs to one terrain in one scope. The table makes a new one when
 * the terrain, the account or the base changes and calls destroy() on the old
 * one, which must cancel its work and drop what it holds.
 */

import { el } from "../../lib/dom.js";

const ETIQUETA = { pdf: "Archivos", kmz: "KMZ" };

/* The placeholder widget: the same contract, showing an honest "not yet". */
function sinIntegrar({ container, tipo }) {
  const nodo = el("span", {
    class: "ranura-pendiente",
    title: `${ETIQUETA[tipo]}: esta columna se conectará en una etapa posterior. No indica que no haya archivos.`,
  }, "No disponible aún");
  container.replaceChildren(nodo);
  return {
    update() {},
    destroy() { nodo.remove(); },
  };
}

let widget = sinIntegrar;

/** 3B: replace the placeholder with the real widget factory (same contract). */
export function registrarWidgetDeArchivos(fabrica) {
  widget = typeof fabrica === "function" ? fabrica : sinIntegrar;
}

/**
 * Mount one file slot. `tipo` is "pdf" or "kmz"; `resumen` is the caller-aware
 * 1B summary when the host has one, otherwise undefined.
 */
export function montarRanura({ container, terrenoId, tipo, soloLectura, resumen, onCambio, onError }) {
  let vivo = true;
  const montado = widget({
    container, terrenoId, tipo, soloLectura: Boolean(soloLectura), resumen,
    // A result that arrives after destroy() belongs to a scope that is gone.
    onCambio: (e) => { if (vivo) onCambio?.({ terrenoId: e?.terrenoId ?? terrenoId }); },
    onError: (e) => { if (vivo) onError?.({ codigo: String(e?.codigo ?? ""), mensaje: String(e?.mensaje ?? "") }); },
  });
  return {
    container,
    update(cambios) { if (vivo) montado.update?.(cambios); },
    destroy() {
      if (!vivo) return;
      vivo = false;
      montado.destroy?.();
      container.replaceChildren();
    },
  };
}

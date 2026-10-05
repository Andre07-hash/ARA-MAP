/* Entry points for importing: pick a file, then hand it to the assistant.
 *
 * Both "Importar archivo" and "Agregar terrenos" go through the same
 * assistant (components/import/ImportAssistant.js): upload, automatic
 * analysis, only the questions that are needed, review with a map, import.
 */

import { el } from "../../lib/dom.js";
import { runAssistant } from "../import/ImportAssistant.js";

export function pickWorkbook() {
  return new Promise((resolve) => {
    const input = el("input", {
      type: "file",
      accept: ".xlsx,.xlsm,.csv",
      style: { display: "none" },
      onchange: () => { resolve(input.files?.[0] ?? null); input.remove(); },
    });
    document.body.append(input);
    input.click();
  });
}

/**
 * Import a new base. Resolves with the created base, or null if cancelled.
 * `carpetas` are the base folders it can go into; `carpetaInicial` is the one
 * preselected (the folder open in the gallery, or null for "Sin carpeta").
 */
export async function importWorkbook({ onDone, carpetas = [], carpetaInicial = null }) {
  const file = await pickWorkbook();
  return file ? runAssistant(file, { modo: "nueva", carpetas, carpetaInicial, onDone }) : null;
}

/** Append a file to an existing base, resolving conflicts row by row. */
export async function appendWorkbook(base, { onDone }) {
  const file = await pickWorkbook();
  return file ? runAssistant(file, { modo: "agregar", base, onDone }) : null;
}

/* Modal dialogs built on the native <dialog> element, which brings its own
 * focus trap, Escape handling and inert background. */

import { el } from "../../lib/dom.js";

let abiertos = 0;
const vivos = new Set();   // every dialog currently in the document

/**
 * Remove every dialog now, contents included. For when what they show stops
 * belonging to whoever is looking: a closed <dialog> left in the document
 * still holds its text.
 */
export function closeAllDialogs() {
  for (const dialog of [...vivos]) {
    vivos.delete(dialog);
    if (dialog.open) dialog.close();
    dialog.remove();
  }
}

/**
 * `antesDeCerrar` (optional) is asked before the person closes the dialog
 * (an action, Escape, the backdrop): a false answer keeps it open. Code that
 * removes every dialog (closeAllDialogs) is not asked. `close()` resolves
 * whether the dialog closed.
 */
export function openDialog({ titulo, descripcion, contenido, acciones, ancho = "34rem", antesDeCerrar = null }) {
  // One id per dialog: a dialog opened over another must be named by its own title.
  const idTitulo = `dialog-title-${abiertos += 1}`;
  const dialog = el("dialog", { class: "dialog", style: { maxWidth: ancho } });
  const body = el("div", { class: "dialog-body" });

  const header = el("header", { class: "dialog-header" },
    el("h2", { id: idTitulo }, titulo),
    descripcion && el("p", { class: "secondary" }, descripcion),
  );

  const footer = el("footer", { class: "dialog-footer" });
  let preguntando = false;
  const cerrarYa = (value) => {
    dialog.close(value ?? "");
    dialog.remove();
  };
  const close = async (value) => {
    if (!dialog.isConnected) return true;
    if (antesDeCerrar) {
      if (preguntando) return false;
      preguntando = true;
      let seguir = false;
      try { seguir = await antesDeCerrar(); } finally { preguntando = false; }
      if (!seguir || !dialog.isConnected) return !dialog.isConnected;
    }
    cerrarYa(value);
    return true;
  };

  for (const accion of acciones ?? []) {
    footer.append(
      el("button", {
        type: "button",
        class: ["btn", accion.variante ? `btn-${accion.variante}` : "btn-quiet"],
        onclick: () => accion.onClick?.(close),
      }, accion.etiqueta)
    );
  }

  body.append(contenido);
  dialog.append(header, body, footer);
  dialog.setAttribute("aria-labelledby", idTitulo);

  // A click on the backdrop (outside the dialog's own box) dismisses it.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close();
  });
  dialog.addEventListener("cancel", (event) => {
    if (!antesDeCerrar) { dialog.remove(); return; }
    event.preventDefault();      // Escape asks first, like the close button
    close();
  });
  // However it closes (a button, Escape, or code calling close()), it leaves the document.
  dialog.addEventListener("close", () => { vivos.delete(dialog); dialog.remove(); });
  vivos.add(dialog);

  document.body.append(dialog);
  dialog.showModal();
  dialog.querySelector("input, select, textarea, button")?.focus();

  return { dialog, close };
}

/** A yes/no confirmation. Resolves true only if the user confirms. */
export function confirmDialog({ titulo, mensaje, confirmar = "Confirmar", cancelar = "Cancelar", peligro = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => { if (!settled) { settled = true; resolve(value); } };

    const { dialog } = openDialog({
      titulo,
      contenido: el("p", { class: "secondary" }, mensaje),
      ancho: "28rem",
      acciones: [
        { etiqueta: cancelar, onClick: (close) => { finish(false); close(); } },
        {
          etiqueta: confirmar,
          variante: peligro ? "peligro" : "principal",
          onClick: (close) => { finish(true); close(); },
        },
      ],
    });
    dialog.addEventListener("close", () => finish(false));
  });
}

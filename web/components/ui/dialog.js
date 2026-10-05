/* Modal dialogs built on the native <dialog> element, which brings its own
 * focus trap, Escape handling and inert background. */

import { el } from "../../lib/dom.js";

export function openDialog({ titulo, descripcion, contenido, acciones, ancho = "34rem" }) {
  const dialog = el("dialog", { class: "dialog", style: { maxWidth: ancho } });
  const body = el("div", { class: "dialog-body" });

  const header = el("header", { class: "dialog-header" },
    el("h2", { id: "dialog-title" }, titulo),
    descripcion && el("p", { class: "secondary" }, descripcion),
  );

  const footer = el("footer", { class: "dialog-footer" });
  const close = (value) => {
    dialog.close(value ?? "");
    dialog.remove();
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
  dialog.setAttribute("aria-labelledby", "dialog-title");

  // A click on the backdrop (outside the dialog's own box) dismisses it.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close();
  });
  dialog.addEventListener("cancel", () => dialog.remove());

  document.body.append(dialog);
  dialog.showModal();
  dialog.querySelector("input, select, textarea, button")?.focus();

  return { dialog, close };
}

/** A yes/no confirmation. Resolves true only if the user confirms. */
export function confirmDialog({ titulo, mensaje, confirmar = "Confirmar", peligro = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => { if (!settled) { settled = true; resolve(value); } };

    const { dialog } = openDialog({
      titulo,
      contenido: el("p", { class: "secondary" }, mensaje),
      ancho: "28rem",
      acciones: [
        { etiqueta: "Cancelar", onClick: (close) => { finish(false); close(); } },
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

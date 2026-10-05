/* The filter rail as a drawer on narrow screens.
 *
 * The rail is not rebuilt: the same persistent element moves into a native
 * modal <dialog> (focus trap, Escape and an inert background for free) and
 * back to its slot on close, so every typed value and checked box survives.
 */

import { el } from "../../lib/dom.js";

export function openFiltersDrawer({ rail, slot, onClosed }) {
  const cerrar = el("button", {
    type: "button", class: "icon-btn", "aria-label": "Cerrar filtros",
  }, "×");
  const listo = el("button", { type: "button", class: "btn btn-principal" }, "Ver resultados");
  const dialog = el("dialog", { class: "drawer", "aria-labelledby": "drawer-titulo" },
    el("header", { class: "drawer-header" },
      el("h2", { id: "drawer-titulo" }, "Filtros"),
      cerrar,
    ),
    el("div", { class: "drawer-body" }, rail.element),
    el("footer", { class: "drawer-footer" }, listo),
  );

  cerrar.addEventListener("click", () => dialog.close());
  listo.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => {
    slot.append(rail.element);
    dialog.remove();
    onClosed?.();   // the caller returns focus to its trigger and re-measures the map
  });

  document.body.append(dialog);
  // showModal focuses the close button: no keyboard pops up over the filters.
  dialog.showModal();
  return dialog;
}

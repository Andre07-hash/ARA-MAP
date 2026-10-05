/* Transient confirmations and errors. Errors persist until dismissed, because
 * a failed import is not something to notice in passing. */

import { el } from "../../lib/dom.js";

let host = null;

function ensureHost() {
  if (!host) {
    host = el("div", { class: "toast-host", role: "status", "aria-live": "polite" });
    document.body.append(host);
  }
  return host;
}

export function toast(mensaje, { tipo = "ok", duracion = 4200 } = {}) {
  const node = el("div", { class: ["toast", `toast-${tipo}`] },
    el("span", { class: "toast-text" }, mensaje),
    el("button", {
      type: "button",
      class: "toast-close",
      "aria-label": "Cerrar aviso",
      onclick: () => dismiss(node),
    }, "×"),
  );

  ensureHost().append(node);
  requestAnimationFrame(() => node.classList.add("is-visible"));

  if (tipo !== "error") setTimeout(() => dismiss(node), duracion);
  return node;
}

export const toastError = (mensaje) => toast(mensaje, { tipo: "error" });

function dismiss(node) {
  node.classList.remove("is-visible");
  node.addEventListener("transitionend", () => node.remove(), { once: true });
  setTimeout(() => node.remove(), 400); // in case transitions are disabled
}

/** Remove every toast at once: some name private records. */
export function clearToasts() {
  host?.replaceChildren();
}

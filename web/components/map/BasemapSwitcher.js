/* Choosing the backdrop: quiet grey, satellite imagery, or street names. */

import { el } from "../../lib/dom.js";
import { BASEMAPS } from "./basemaps.js";

export function BasemapSwitcher({ activo, onChange }) {
  return el("div", {
    class: "basemap-switcher",
    role: "radiogroup",
    "aria-label": "Mapa base",
  },
    Object.entries(BASEMAPS).map(([key, spec]) =>
      el("button", {
        type: "button",
        role: "radio",
        "aria-checked": String(key === activo),
        class: ["basemap-option", key === activo && "is-active"],
        title: spec.descripcion,
        onclick: () => onChange(key),
      }, spec.etiqueta)
    )
  );
}

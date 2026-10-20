/* Small stroke icons for buttons. Decorative: the button's text or
 * aria-label names it. Static markup only, never data. */

import { el } from "../../lib/dom.js";

const TRAZOS = {
  tabla: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>',
  mapa: '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z"/><path d="M9 3v15M15 6v15"/>',
  filtros: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  mas: '<path d="M12 5v14M5 12h14"/>',
  puntos: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
  buscar: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  bajar: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  subir: '<path d="M12 15V4M7 9l5-5 5 5M5 20h14"/>',
  personas: '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.5a3.5 3.5 0 0 1 0 7M21 20c0-2.6-1.6-4.8-4-5.6"/>',
  columnas: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
  actualizar: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  cerrar: '<path d="M6 6l12 12M18 6 6 18"/>',
  abajo: '<path d="m6 9 6 6 6-6"/>',
};

export function icono(nombre) {
  const span = el("span", { class: "icono", "aria-hidden": "true" });
  span.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"'
    + ` stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${TRAZOS[nombre]}</svg>`;
  return span;
}

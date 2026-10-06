/* The public facts of a terrain, and the public detail panel built on them.
 *
 * TerrainFacts receives an object that has already been through pickPublic,
 * so nothing outside the PublicTerrain allowlist can be rendered here even by
 * accident. The internal panel reuses it for the draft's business fields and
 * adds its private sections around it.
 */

import { el } from "../../lib/dom.js";
import {
  fmtArea, fmtCoord, fmtDate, fmtHectares, fmtPercent, fmtPrice, fmtText, fmtUnitPrice,
} from "../../lib/format.js";
import { DISPONIBILIDAD, estadoUbicacion, pickPublic } from "../../lib/inventario.js";

export function TerrainFacts(publico) {
  const ubicado = estadoUbicacion(publico.lat, publico.lon) === "valida";
  const consultar = publico.price_on_request === true;

  return [
    el("div", { class: "detail-lead" },
      el("div", {},
        el("span", { class: "eyebrow" }, "Asking Price"),
        el("p", { class: "figure-lead" },
          consultar ? "Precio a consultar" : fmtPrice(publico.asking_price, publico.moneda)),
      ),
      !consultar && el("div", { class: "detail-lead-sub" },
        el("span", { class: "eyebrow" }, "Asking $/m²"),
        el("p", { class: "figure-sub" }, fmtUnitPrice(publico.asking_m2, publico.moneda)),
      ),
    ),

    publico.public_description && el("p", { class: "detail-descripcion" }, publico.public_description),

    Section("Superficie", [
      ["Superficie", fmtArea(publico.superficie_m2)],
      ["En hectáreas", fmtHectares(publico.superficie_ha)],
      ["Afectaciones", fmtPercent(publico.afectaciones_pct)],
      ["Afectaciones m²", fmtArea(publico.afectaciones_m2)],
    ]),

    Section("Ubicación", [
      ["Estado", fmtText(publico.estado)],
      ["Municipio", fmtText(publico.municipio)],
      ["Dirección", fmtText(publico.direccion)],
    ]),

    ubicado && [
      Section("Coordenadas", [
        ["Latitud (X)", el("span", { class: "mono" }, String(publico.lat))],
        ["Longitud (Y)", el("span", { class: "mono" }, String(publico.lon))],
        ["Par", el("span", { class: "mono" }, fmtCoord(publico.lat, publico.lon))],
      ]),
      el("p", { class: "detail-nota muted" },
        "El círculo en el mapa cubre la superficie registrada, centrado en este punto. " +
        "No se dibujan linderos: la forma es una aproximación."),
    ],
  ];
}

export function Section(titulo, filas) {
  return el("section", { class: "detail-section" },
    el("h3", { class: "eyebrow" }, titulo),
    el("dl", { class: "detail-grid" },
      filas.map(([etiqueta, valor]) => [
        el("dt", {}, etiqueta),
        el("dd", { class: "figure" }, valor),
      ])
    )
  );
}

/** The availability label; negotiation is always said out loud. */
export function DisponibilidadChip(availability) {
  if (!availability) return null;
  return el("span", { class: ["estado-chip", `disp-${availability}`] },
    DISPONIBILIDAD[availability] ?? availability);
}

/**
 * What a visitor sees for one published terrain. The publication preview
 * renders the same component with `vistaPrevia`: same facts, same layout,
 * marked as not yet published, and nothing but the PublicTerrain fields.
 */
export function PublicTerrainDetail({ terreno, onZoomAEscala, onClose, vistaPrevia = false }) {
  const publico = pickPublic(terreno);
  const lugar = [publico.municipio, publico.estado].filter(Boolean).join(", ");
  const ubicado = estadoUbicacion(publico.lat, publico.lon) === "valida";

  return el(vistaPrevia ? "section" : "aside", {
    class: ["detail", vistaPrevia && "detail-vista-previa"],
    role: vistaPrevia ? null : "complementary",
    "aria-label": `${vistaPrevia ? "Vista previa" : "Detalle"} de ${publico.terreno ?? "terreno"}`,
    tabindex: "-1",
  },
    el("header", { class: "detail-header" },
      el("div", { class: "detail-heading" },
        el("span", { class: ["eyebrow", vistaPrevia && "eyebrow-vista-previa"] },
          vistaPrevia ? "Vista previa · Aún no publicada" : "Catálogo"),
        el("h2", {}, publico.terreno ?? "Sin nombre"),
        lugar && el("p", { class: "secondary" }, lugar),
        DisponibilidadChip(publico.availability),
      ),
      onClose && el("button", {
        type: "button", class: "icon-btn", "aria-label": "Cerrar detalle", onclick: onClose,
      }, "×"),
    ),
    ubicado && onZoomAEscala && el("button", {
      type: "button", class: "btn btn-quiet detail-escala",
      title: "Acerca el mapa hasta que el círculo cubra la superficie real",
      onclick: onZoomAEscala,
    }, "Ver a escala"),
    TerrainFacts(publico),
    el("footer", { class: "detail-footer muted" },
      vistaPrevia
        ? `Revisión ${String(publico.revision_id ?? "").slice(0, 8)} · sin fecha de publicación todavía`
        : publico.published_at ? `Publicado el ${fmtDate(publico.published_at)}` : ""),
  );
}

/** Loading, missing and failed states share the panel's frame. */
export function DetailMessage({ titulo, mensaje, onClose, onRetry }) {
  return el("aside", { class: "detail", role: "complementary", "aria-label": titulo, tabindex: "-1" },
    el("header", { class: "detail-header" },
      el("div", { class: "detail-heading" }, el("h2", {}, titulo)),
      el("button", {
        type: "button", class: "icon-btn", "aria-label": "Cerrar detalle", onclick: onClose,
      }, "×"),
    ),
    el("p", { class: "secondary", role: "status" }, mensaje),
    onRetry && el("button", { type: "button", class: "btn btn-quiet", onclick: onRetry }, "Reintentar"),
  );
}

/* The legend.
 *
 * Always present, and always naming what each colour means: the comparison
 * palette sits below 3:1 against the map, so the colour-vision guidance
 * requires visible labels as relief rather than colour alone. Layers past the
 * validated colour range are marked as relying on their dashed ring too.
 */

import { CAPAS_SEGURAS, PRICE_RAMP, layerNeedsPattern } from "../../lib/colors.js";
import { el } from "../../lib/dom.js";
import { fmtPriceShort, nombraMonedas, plural } from "../../lib/format.js";

export function Legend({
  modo, capas, breaks, monedas = [], conteo, sinUbicacion, invalidas = 0, escala, onToggleCapa,
}) {
  const cuerpo = modo === "base"
    ? capasLegend(capas, onToggleCapa)
    : priceLegend(breaks, monedas);

  const excede = modo === "base" && capas.length > CAPAS_SEGURAS;
  const huerfanas = capas.filter((c) => c.base_existe === false).length;

  return el("section", { class: "legend", "aria-label": "Leyenda" },
    el("header", { class: "legend-header" },
      el("span", { class: "eyebrow" }, modo === "base" ? "Capas" : "Asking $/m²"),
      el("span", { class: "legend-count figure" }, plural(conteo, "terreno")),
    ),
    cuerpo,
    // Updated in place as the map zooms, so it never triggers a re-render.
    el("p", { class: "legend-note legend-escala" }, escalaTexto(escala)),
    sinUbicacion > 0 && el("p", { class: "legend-note" },
      `${plural(sinUbicacion, "terreno")} fuera del mapa`,
      invalidas > 0
        ? `: ${invalidas} con coordenadas imposibles y ` +
          `${sinUbicacion - invalidas} sin coordenadas.`
        : " por falta de coordenadas.",
    ),
    modo === "base" && capas.length > 1 && el("p", { class: "legend-note" },
      "Los círculos concéntricos marcan un terreno presente en varias capas."),
    excede && el("p", { class: "legend-note legend-aviso" },
      `Más de ${CAPAS_SEGURAS} capas: los colores extra se distinguen menos, ` +
      "por eso llevan el borde punteado."),
    huerfanas > 0 && el("p", { class: "legend-note legend-aviso" },
      `${plural(huerfanas, "capa", "capas")} sin base de origen: se conserva lo guardado.`),
  );
}

/** Says plainly whether a circle is a measurement or just a symbol. */
export function escalaTexto(escala) {
  if (!escala || !escala.total) return "";
  if (escala.aEscala === 0) {
    return "Los círculos son símbolos, no el tamaño real. Acércate para verlos a escala.";
  }
  if (escala.aEscala === escala.total) {
    return "Cada círculo cubre la superficie real del terreno (forma aproximada).";
  }
  return `${escala.aEscala} de ${escala.total} círculos están a escala real; ` +
         "los demás siguen siendo símbolos. Acércate más.";
}

function capasLegend(capas, onToggleCapa) {
  return el("ul", { class: "legend-list" },
    capas.map((capa, index) =>
      el("li", {},
        el("label", { class: ["legend-item", !capa.visible && "is-off"] },
          el("input", {
            type: "checkbox",
            checked: capa.visible,
            onchange: () => onToggleCapa?.(capa.orden ?? index),
          }),
          el("span", {
            class: ["legend-swatch", layerNeedsPattern(index) && "is-dashed"],
            style: { background: capa.color },
          }),
          el("span", { class: "legend-label truncate", title: capa.nombre }, capa.nombre),
          capa.base_existe === false && el("span", {
            class: "legend-orphan",
            title: "La base de origen ya no existe; se muestra lo que se guardó.",
            "aria-label": "Base eliminada",
          }, "!"),
          el("span", { class: "legend-count figure muted" }, String(capa.ubicados ?? 0)),
        )
      )
    )
  );
}

function priceLegend(breaks, monedas) {
  if (monedas.length > 1) {
    // One scale for two currencies would rank 100 USD and 100 MXN as equal.
    return el("p", { class: "legend-note legend-aviso" },
      `Los precios están en ${nombraMonedas(monedas)}; no se gradúan juntos. ` +
      "Muestra una sola capa o colorea por capa; la ubicación se compara igual.");
  }
  if (!breaks) {
    return el("p", { class: "legend-note" },
      "No hay suficientes precios por m² para graduar el color.");
  }

  const moneda = monedas[0];
  const etiquetas = ["menor", ...breaks.map((b) => fmtPriceShort(b, moneda))];
  return el("div", { class: "legend-ramp" },
    PRICE_RAMP.map((color, index) =>
      el("div", { class: "ramp-step" },
        el("span", { class: "ramp-swatch", style: { background: color } }),
        el("span", { class: "ramp-label figure" },
          index === 0 ? `< ${fmtPriceShort(breaks[0], moneda)}` : `≥ ${etiquetas[index]}`),
      )
    ),
    el("div", { class: "ramp-step ramp-step-unknown" },
      el("span", { class: "ramp-swatch", style: { background: "#9a9892" } }),
      el("span", { class: "ramp-label" }, "sin dato"),
    )
  );
}

/* Terrains the map cannot show.
 *
 * Nothing is ever placed by guesswork, so these stay visible here instead of
 * silently disappearing -- half of a typical workbook has no coordinates.
 */

import { el } from "../../lib/dom.js";
import { fmtArea, googleMapsSearch, plural } from "../../lib/format.js";

/* `instruccion` replaces the spreadsheet advice where a terrain can be
 * corrected directly (the inventory's editor). */
export function UnplacedList({ terrenos, seleccionado, abierto, instruccion = null, onSelect, onToggle }) {
  if (!terrenos.length) return el("div", { class: "unplaced is-empty" });

  // Two different problems, two different fixes: one needs coordinates added,
  // the other needs existing coordinates corrected.
  const invalidos = terrenos.filter((t) => t.ubicacion === "invalida");
  const sinDato = terrenos.filter((t) => t.ubicacion !== "invalida");

  return el("section", {
    class: ["unplaced", abierto && "is-open"],
    "aria-label": "Terrenos sin ubicación",
  },
    el("button", {
      type: "button",
      class: "unplaced-toggle",
      "aria-expanded": String(abierto),
      onclick: onToggle,
    },
      el("span", { class: "unplaced-caret", "aria-hidden": "true" }, abierto ? "▾" : "▸"),
      el("span", { class: "eyebrow" }, "Fuera del mapa"),
      invalidos.length > 0 && el("span", {
        class: "unplaced-count unplaced-count-error figure",
        title: `${invalidos.length} con coordenadas imposibles`,
      }, String(invalidos.length)),
      el("span", { class: "unplaced-count figure" }, String(terrenos.length)),
    ),

    abierto && el("div", { class: "unplaced-body" },
      invalidos.length > 0 && el("p", { class: "unplaced-note unplaced-note-error" },
        `${plural(invalidos.length, "terreno")} con coordenadas imposibles ` +
        "(fuera de México o con X y Y invertidas). No se dibujan hasta corregirlas" +
        (instruccion ? "" : " en el archivo") + "; aquí se muestran tal como vienen."),
      sinDato.length > 0 && el("p", { class: "unplaced-note muted" },
        instruccion
          ? `${plural(sinDato.length, "terreno")} sin coordenadas. ${instruccion}`
          : `${plural(sinDato.length, "terreno")} sin coordenadas en el archivo. ` +
            "Agrega X (latitud) y Y (longitud) y vuelve a importar para verlos en el mapa."),
      instruccion && invalidos.length > 0 && el("p", { class: "unplaced-note muted" }, instruccion),
      el("ul", { class: "unplaced-list" },
        [...invalidos, ...sinDato].map((terreno) =>
          el("li", {},
            el("div", {
              class: [
                "unplaced-item",
                terreno.id === seleccionado && "is-selected",
                terreno.ubicacion === "invalida" && "is-invalid",
              ],
            },
              el("button", {
                type: "button",
                class: "unplaced-name",
                onclick: () => onSelect(terreno.id),
              },
                el("span", { class: "truncate" }, terreno.terreno),
                el("span", { class: "muted truncate" },
                  [terreno.municipio, terreno.estado].filter(Boolean).join(", ") || "—"),
              ),
              terreno.ubicacion === "invalida"
                ? el("span", {
                    class: "unplaced-badge",
                    title: `Coordenadas imposibles: ${terreno.lat}, ${terreno.lon}`,
                  }, "X/Y")
                : el("span", { class: "unplaced-area figure muted" },
                    fmtArea(terreno.superficie_m2)),
              el("a", {
                class: "unplaced-link",
                href: googleMapsSearch(terreno),
                target: "_blank",
                rel: "noopener noreferrer",
                title: `Buscar ${terreno.terreno} en Google Maps`,
                "aria-label": `Buscar ${terreno.terreno} en Google Maps`,
              }, "↗"),
            )
          )
        )
      )
    )
  );
}

/* The detail panel: everything the workbook holds about one terrain. */

import { el } from "../../lib/dom.js";
import {
  fmtArea, fmtCoord, fmtDate, fmtHectares, fmtPercent, fmtPrice,
  fmtText, fmtUnitPrice, googleMapsSearch,
} from "../../lib/format.js";

export function TerrainDetail({ terreno, baseNombre, onZoomAEscala, onClose }) {
  if (!terreno) return el("div");

  const lugar = [terreno.municipio, terreno.estado].filter(Boolean).join(", ");

  return el("aside", {
    class: "detail",
    role: "complementary",
    "aria-label": `Detalle de ${terreno.terreno}`,
    tabindex: "-1",
  },
    el("header", { class: "detail-header" },
      el("div", { class: "detail-heading" },
        el("span", { class: "eyebrow" }, baseNombre ?? "Terreno"),
        el("h2", {}, terreno.terreno),
        lugar && el("p", { class: "secondary" }, lugar),
      ),
      el("button", {
        type: "button", class: "icon-btn", "aria-label": "Cerrar detalle", onclick: onClose,
      }, "×"),
    ),

    // The same action as double-clicking the mark, reachable from the keyboard.
    terreno.ubicado && onZoomAEscala && el("button", {
      type: "button", class: "btn btn-quiet detail-escala",
      title: "Acerca el mapa hasta que el círculo cubra la superficie real",
      onclick: onZoomAEscala,
    }, "Ver a escala"),

    terreno.incidencias?.length > 0 && Findings(terreno.incidencias),

    el("div", { class: "detail-lead" },
      el("div", {},
        el("span", { class: "eyebrow" }, "Asking Price"),
        el("p", { class: "figure-lead" }, fmtPrice(terreno.asking_price, terreno.moneda)),
      ),
      el("div", { class: "detail-lead-sub" },
        el("span", { class: "eyebrow" }, "Asking $/m²"),
        el("p", { class: "figure-sub" }, fmtUnitPrice(terreno.asking_m2, terreno.moneda)),
      ),
    ),

    Section("Superficie", [
      ["Superficie", fmtArea(terreno.superficie_m2)],
      ["En hectáreas", fmtHectares(terreno.superficie_ha)],
      ["Afectaciones", fmtPercent(terreno.afectaciones_pct)],
      ["Afectaciones m²", fmtArea(terreno.afectaciones_m2)],
    ]),

    Section("Ubicación", [
      ["Estado", fmtText(terreno.estado)],
      ["Municipio", fmtText(terreno.municipio)],
      ["Dirección", fmtText(terreno.direccion)],
    ]),

    terreno.ubicado
      ? [
          Section("Coordenadas", [
            ["Latitud (X)", el("span", { class: "mono" }, String(terreno.lat))],
            ["Longitud (Y)", el("span", { class: "mono" }, String(terreno.lon))],
            ["Par", el("span", { class: "mono" }, fmtCoord(terreno.lat, terreno.lon))],
          ]),
          el("p", { class: "detail-nota muted" },
            "El círculo en el mapa cubre la superficie registrada, centrado en " +
            "este punto. El archivo no trae los linderos, así que la forma es " +
            "una aproximación: el área y la ubicación sí son las del registro."),
        ]
      : Unplaced(terreno),

    Object.keys(terreno.extra ?? {}).length > 0 &&
      Section("Otros campos del archivo",
        Object.entries(terreno.extra).map(([k, v]) => [k, fmtText(v)])),

    el("footer", { class: "detail-footer" },
      el("span", { class: "muted" }, `Fila ${terreno.fila || terreno.orden} · ID de origen `),
      el("span", { class: "mono muted" }, String(terreno.id_origen ?? "—")),
    ),
  );
}

function Section(titulo, filas) {
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

function Unplaced(terreno) {
  return el("section", { class: "detail-section detail-unplaced" },
    el("h3", { class: "eyebrow" }, "Sin coordenadas"),
    el("p", { class: "secondary" },
      "Este terreno no aparece en el mapa porque el archivo no trae X ni Y. " +
      "Búscalo en Google Maps, copia las coordenadas y agrégalas al archivo " +
      "(X = latitud, Y = longitud)."),
    el("a", {
      class: "btn btn-quiet", href: googleMapsSearch(terreno),
      target: "_blank", rel: "noopener noreferrer",
    }, "Buscar en Google Maps"),
  );
}

function Findings(incidencias) {
  const errores = incidencias.filter((i) => i.severidad === "error");
  const avisos = incidencias.filter((i) => i.severidad !== "error");

  return el("section", { class: "findings" },
    [...errores, ...avisos].map((incidencia) =>
      el("p", { class: ["finding", `finding-${incidencia.severidad}`] },
        el("span", { class: "finding-icon", "aria-hidden": "true" },
          incidencia.severidad === "error" ? "!" : "i"),
        el("span", {},
          el("strong", {}, incidencia.severidad === "error" ? "Error: " : "Aviso: "),
          incidencia.mensaje),
      )
    )
  );
}

export function TerrainDetailEmpty() {
  return el("aside", { class: "detail detail-empty" },
    el("p", { class: "muted" }, "Selecciona un terreno para ver su información."));
}

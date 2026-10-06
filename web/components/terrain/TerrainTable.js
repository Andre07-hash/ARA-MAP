/* The table view.
 *
 * For screening, sorting by $/m2 is often faster than reading the map, so the
 * same filtered set is available either way.
 *
 * In a comparison the table also answers "which one is this?": every row names
 * its source layer with its colour, and says how it differs from the reference
 * layer. Without that, two nearly identical rows are indistinguishable.
 */

import { el } from "../../lib/dom.js";
import { ESTADOS } from "../../lib/comparar.js";
import { SORTS, sortTerrenos } from "../../lib/filters.js";
import { DISPONIBILIDAD } from "../../lib/inventario.js";
import { foldText } from "../../lib/format.js";
import {
  fmtArea, fmtHectares, fmtPercent, fmtPrice, fmtText, fmtUnitPrice,
} from "../../lib/format.js";

const BASE_COLUMNS = [
  { key: "terreno",    titulo: "Terreno",      render: (t) => t.terreno },
  { key: "estado",     titulo: "Estado",       render: (t) => fmtText(t.estado) },
  { key: null,         titulo: "Municipio",    render: (t) => fmtText(t.municipio) },
  { key: "superficie", titulo: "Superficie",   render: (t) => fmtArea(t.superficie_m2), num: true },
  { key: null,         titulo: "Ha",           render: (t) => fmtHectares(t.superficie_ha), num: true },
  { key: null,         titulo: "Afect.",       render: (t) => fmtPercent(t.afectaciones_pct), num: true },
  { key: "precio",     titulo: "Asking Price", render: (t) => fmtPrice(t.asking_price, t.moneda), num: true },
  { key: "unitario",   titulo: "Asking $/m²",  render: (t) => fmtUnitPrice(t.asking_m2, t.moneda), num: true },
];
const PRECIOS = new Set(["precio", "unitario"]);

/* Sorting by source and by change state, available only while comparing.
 * Change sorts by how much attention the row deserves, not alphabetically. */
const PRIORIDAD_CAMBIO = {
  nuevo: 0, eliminado: 1, cambiado: 2, sin_cambio: 3, base: 4,
};

export const COMPARISON_SORTS = {
  capa:   { etiqueta: "Base", get: (t) => foldText(t.base_nombre ?? ""), texto: true },
  cambio: {
    etiqueta: "Cambio",
    get: (t) => PRIORIDAD_CAMBIO[t.comparacion?.estado] ?? 9,
  },
};

/* The team inventory's status column: publication state in words, then
 * availability. Never shown in the public catalog. */
const PUBLICACION_COLUMN = {
  key: null, titulo: "Publicación", clase: "col-publicacion",
  render: (t) => el("span", { class: "cell-publicacion" },
    el("span", { class: ["estado-chip", `estado-${t.estadoPublicacion?.tono ?? "borrador"}`] },
      t.estadoPublicacion?.etiqueta ?? "—"),
    t.availability && el("span", { class: "muted" }, ` ${DISPONIBILIDAD[t.availability] ?? t.availability}`)),
};

export function TerrainTable({
  terrenos, orden, direccion, seleccionado, comparando = false, preciosComparables = true,
  conPublicacion = false, onSort, onSelect,
}) {
  // Prices in different currencies cannot be ranked against each other:
  // 100 USD and 100 MXN are not equal. Their columns stop being sortable.
  const ordenEfectivo = !preciosComparables && PRECIOS.has(orden) ? "orden" : orden;
  const sorts = comparando ? { ...SORTS, ...COMPARISON_SORTS } : SORTS;
  const filas = sortTerrenos(terrenos, ordenEfectivo, direccion, sorts);
  const base = preciosComparables
    ? BASE_COLUMNS
    : BASE_COLUMNS.map((c) => (PRECIOS.has(c.key) ? { ...c, key: null } : c));

  const columnas = conPublicacion
    ? [base[0], PUBLICACION_COLUMN, ...base.slice(1)]
    : comparando
    ? [
        {
          key: "capa", titulo: "Base", clase: "col-base",
          render: (t) => el("span", { class: "cell-source", title: fmtText(t.base_nombre) },
            el("span", { class: "legend-swatch", style: { background: t.color } }),
            el("span", { class: "truncate" }, fmtText(t.base_nombre)),
          ),
        },
        { key: "cambio", titulo: "Cambio", clase: "col-cambio", render: (t) => ChangeCell(t) },
        ...base,
      ]
    : base;

  return el("div", { class: "table-wrap", tabindex: "0" },
    el("table", { class: "table" },
      el("thead", {},
        el("tr", {},
          columnas.map((columna) => {
            const activa = columna.key && columna.key === ordenEfectivo;
            return el("th", {
              scope: "col",
              class: [columna.num && "is-num", columna.key && "is-sortable",
                      activa && "is-active", columna.clase],
              "aria-sort": activa ? (direccion === "asc" ? "ascending" : "descending") : "none",
            },
              columna.key
                ? el("button", {
                    type: "button",
                    class: "th-btn",
                    onclick: () => onSort(columna.key),
                    title: `Ordenar por ${sorts[columna.key]?.etiqueta ?? columna.titulo}`,
                  },
                    columna.titulo,
                    el("span", { class: "sort-caret", "aria-hidden": "true" },
                      activa ? (direccion === "asc" ? "▲" : "▼") : "")
                  )
                : columna.titulo
            );
          })
        )
      ),
      el("tbody", {},
        filas.map((terreno) =>
          el("tr", {
            class: [
              terreno.id === seleccionado && "is-selected",
              !terreno.ubicado && "is-unplaced",
            ],
            tabindex: "0",
            onclick: () => onSelect(terreno.id),
            onkeydown: (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(terreno.id);
              }
            },
          },
            columnas.map((columna) =>
              el("td", { class: [columna.num && "is-num figure", columna.clase] },
                columna.titulo === "Terreno"
                  ? el("span", { class: "cell-name" },
                      !terreno.ubicado && el("span", {
                        class: "pin-off", title: "Sin coordenadas",
                        "aria-label": "Sin coordenadas",
                      }, "○"),
                      terreno.terreno)
                  : columna.render(terreno)
              )
            )
          )
        )
      )
    ),
    !filas.length && el("p", { class: "empty-note muted" },
      "Ningún terreno coincide con los filtros actuales.")
  );
}

/* State is never colour alone: each one carries its own word. */
function ChangeCell(terreno) {
  const comparacion = terreno.comparacion;
  if (!comparacion) return "—";

  const spec = ESTADOS[comparacion.estado];
  const ausente = comparacion.ausenteEn ?? [];
  const titulo = comparacion.campos?.length
    ? `Cambió: ${comparacion.campos.join(", ")}`
    : ausente.length
      ? `No está en: ${ausente.join(", ")}`
      : spec?.descripcion ?? "";

  return el("span", { class: ["cambio", `cambio-${comparacion.estado}`], title: titulo },
    spec?.etiqueta ?? comparacion.estado,
    comparacion.campos?.length
      ? el("span", { class: "cambio-campos muted" }, ` ${comparacion.campos.join(", ")}`)
      : ausente.length
        ? el("span", { class: "cambio-campos muted" }, ` no está en ${ausente.join(", ")}`)
        : null,
  );
}

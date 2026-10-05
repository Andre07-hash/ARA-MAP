/* Pieces of an import preview shared by every import path: headline figures,
 * rows that will not be imported, data findings and append conflicts. */

import { el } from "../../lib/dom.js";
import { fmtCount, plural } from "../../lib/format.js";
import { esError, etiqueta } from "../../lib/incidencias.js";

const isCsvPreview = (preview) => preview.formato === "csv";
/* A CSV has lines, not spreadsheet rows; numbering is by physical line. */
export const lineaLabel = (preview) => (isCsvPreview(preview) ? "Línea" : "Fila");

/* Columns kept as extra data, and why. A second column naming a field that
 * another already took is called out separately: it is a known name, not an
 * unknown one, and only the first is used. */
export function ColumnNotes(preview) {
  const duplicadas = preview.columnas_duplicadas ?? [];
  const otras = (preview.columnas_no_reconocidas ?? []).filter((c) => !duplicadas.includes(c));
  return [
    otras.length > 0 && el("p", { class: "note" },
      `Columnas no reconocidas, se guardan como datos extra: ${otras.join(", ")}.`),
    duplicadas.length > 0 && el("p", { class: "note" },
      `Columnas repetidas: ${duplicadas.join(", ")}. Nombran un dato que ya toma ` +
      "otra columna; se usa la primera y estas se guardan como datos extra."),
  ];
}

export function Summary(preview) {
  const invalidas = preview.ubicacion_invalida ?? 0;
  return el("div", {},
    el("div", { class: "stat-row" },
      Stat("Terrenos", preview.conteo, "se importarán"),
      Stat("En el mapa", preview.ubicados, "con coordenadas válidas"),
      Stat("Fuera del mapa", preview.sin_ubicacion,
           invalidas ? `${invalidas} con coordenadas imposibles` : "sin X / Y"),
    ),
    RejectedRows(preview),
  );
}

/* Every non-blank row is accounted for: nothing may vanish silently. */
export function RejectedRows(preview) {
  const rechazadas = preview.rechazadas ?? [];
  if (!rechazadas.length) return null;

  return el("section", { class: "note note-aviso" },
    el("p", {},
      el("strong", {}, `${plural(rechazadas.length, "fila", "filas")} no se importará`),
      preview.filas_con_datos
        ? ` (de ${preview.filas_con_datos} con datos en ${isCsvPreview(preview) ? "el archivo CSV" : "la hoja"}).`
        : ".",
    ),
    el("ul", { class: "rechazadas-list" },
      rechazadas.slice(0, 12).map((r) =>
        el("li", {},
          el("span", { class: "figure muted" }, `${lineaLabel(preview)} ${r.fila}`),
          " ", r.resumen,
        )
      ),
      rechazadas.length > 12 && el("li", { class: "muted" },
        `+${rechazadas.length - 12} más`),
    ),
  );
}

export function Stat(titulo, valor, nota) {
  return el("div", { class: "stat" },
    el("span", { class: "eyebrow" }, titulo),
    el("p", { class: "figure-lead" }, fmtCount(valor)),
    el("span", { class: "muted" }, nota),
  );
}

export function Findings(preview) {
  const hallazgos = preview.hallazgos;
  const linea = lineaLabel(preview);
  if (!hallazgos?.length) {
    return el("p", { class: "note note-ok" }, "No se encontró ningún problema en los datos.");
  }

  const conteos = new Map();
  for (const fila of hallazgos) {
    for (const incidencia of fila.incidencias) {
      conteos.set(incidencia.codigo, (conteos.get(incidencia.codigo) ?? 0) + 1);
    }
  }

  const chips = [...conteos.entries()].sort((a, b) => b[1] - a[1]);

  return el("section", { class: "import-findings" },
    el("h3", { class: "eyebrow" }, "Revisión de datos"),
    el("ul", { class: "chip-row" },
      chips.map(([codigo, conteo]) =>
        el("li", { class: ["chip", esError(codigo) ? "chip-error" : "chip-aviso"] },
          el("span", { class: "chip-count figure" }, String(conteo)),
          etiqueta(codigo),
        )
      )
    ),
    el("details", { class: "findings-details" },
      el("summary", {}, isCsvPreview(preview)
        ? `Ver ${plural(hallazgos.length, "terreno")} con observaciones (por línea del archivo CSV)`
        : `Ver ${plural(hallazgos.length, "fila", "filas")} con observaciones`),
      el("ul", { class: "findings-list" },
        hallazgos.map((fila) =>
          el("li", {},
            el("span", { class: "findings-row muted figure" }, `${linea} ${fila.fila}`),
            el("strong", {}, fila.terreno),
            el("ul", {},
              fila.incidencias.map((incidencia) =>
                el("li", { class: `finding-${incidencia.severidad}` }, incidencia.mensaje))
            )
          )
        )
      )
    ),
    el("p", { class: "note" },
      "Los datos se importan tal como están. Nada se corrige automáticamente: " +
      "corrige el archivo original y vuelve a importar si hace falta."),
  );
}

export function Conflicts(detalle, resoluciones, linea = "Fila") {
  const conflictos = detalle.filter((d) => d.disposicion === "conflicto");
  if (!conflictos.length) return null;

  return el("section", { class: "conflicts" },
    el("h3", { class: "eyebrow" }, "Cambios respecto a lo guardado"),
    el("p", { class: "secondary" },
      "Estos terrenos ya existen con datos distintos. Se muestra el valor " +
      "guardado y el del archivo; elige cuál conservar."),
    el("ul", { class: "conflict-list" },
      conflictos.map((conflicto) => {
        // A field that was empty and now has a value is a correction: default
        // to taking it. A field that had a value and now differs is a real
        // decision, so the stored value stays selected until told otherwise.
        const preferirNuevo = Boolean(conflicto.solo_completa);
        return el("li", { class: "conflict" },
          el("div", { class: "conflict-detalle" },
            el("strong", {}, conflicto.terreno),
            el("p", { class: "muted figure" }, `${linea} ${conflicto.fila}`),
            el("ul", { class: "diff-list" },
              (conflicto.diferencias ?? []).map((d) =>
                el("li", { class: "diff" },
                  el("span", { class: "diff-campo muted" }, d.etiqueta),
                  el("span", { class: "diff-anterior figure" }, formatDiff(d.anterior)),
                  el("span", { class: "diff-flecha", "aria-label": "cambia a" }, "→"),
                  el("span", { class: "diff-nuevo figure" }, formatDiff(d.nuevo)),
                )
              )
            ),
            preferirNuevo && el("p", { class: "muted diff-nota" },
              "Sólo completa datos que faltaban."),
          ),
          el("div", { class: "conflict-choice" },
            Radio(conflicto.indice, "omitir", "Conservar el actual", !preferirNuevo, resoluciones),
            Radio(conflicto.indice, "actualizar", "Usar el del archivo", preferirNuevo, resoluciones),
          )
        );
      })
    )
  );
}

function formatDiff(valor) {
  if (valor === null || valor === undefined || valor === "") return "vacío";
  return typeof valor === "number" ? fmtCount(valor) : String(valor);
}

function Radio(indice, valor, etiquetaTexto, checked, resoluciones) {
  if (checked) resoluciones[indice] = valor;
  return el("label", { class: "check" },
    el("input", {
      type: "radio", name: `conflicto-${indice}`, checked,
      onchange: () => { resoluciones[indice] = valor; },
    }),
    el("span", {}, etiquetaTexto),
  );
}

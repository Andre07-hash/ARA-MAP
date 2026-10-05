/* Folder navigation for one dashboard, and the frame a gallery sits in.
 *
 * Wide screens get a list beside the cards; narrow ones a labelled select
 * above them. Both are rendered and CSS shows one, so the choice follows the
 * viewport without any script. Counts are of saved items (a comparison map is
 * one map), derived from the complete lists.
 */

import { el } from "../../lib/dom.js";
import { fmtCount, plural } from "../../lib/format.js";
import {
  SIN_CARPETA, TEXTOS, TODAS, filterByFolder, folderCounts, isFolderId, selectionLabel,
} from "../../lib/carpetas.js";

/**
 * The navigation, the heading of the open folder and the cards it holds.
 * `renderItems(visibles)` draws the cards; `emptyAll` is shown when there is
 * nothing at all and no folders either (the dashboard's original empty state).
 */
export function FolderedGallery({
  tipo, items, carpetas, seleccion, error, readOnly,
  onSelect, onRenameFolder, onDeleteFolder, onRetry,
  renderItems, emptyAll,
}) {
  if (!items.length && !carpetas.length && !error) return emptyAll;

  const visibles = filterByFolder(items, seleccion);
  const counts = folderCounts(items, carpetas);
  const textos = TEXTOS[tipo];

  return el("div", { class: "folder-layout" },
    FolderNav({ tipo, carpetas, counts, seleccion, error, onSelect, onRetry }),
    el("section", { class: "folder-content", "aria-labelledby": `folder-heading-${tipo}` },
      el("div", { class: "folder-heading" },
        el("div", {},
          el("h2", { id: `folder-heading-${tipo}`, class: "folder-title", tabindex: "-1" },
            selectionLabel(tipo, seleccion, carpetas)),
          el("p", { class: "muted figure" },
            plural(visibles.length, textos.singular, textos.plural)),
        ),
        !readOnly && isFolderId(seleccion) && el("div", { class: "folder-actions" },
          el("button", {
            type: "button", class: "link-btn",
            onclick: () => onRenameFolder(carpetas.find((c) => c.id === seleccion)),
          }, "Renombrar"),
          el("button", {
            type: "button", class: "link-btn link-peligro",
            onclick: () => onDeleteFolder(carpetas.find((c) => c.id === seleccion)),
          }, "Eliminar carpeta"),
        ),
      ),
      visibles.length
        ? renderItems(visibles)
        : el("p", { class: "folder-empty secondary" }, emptyText(tipo, seleccion, readOnly)),
    ),
  );
}

const VACIO = {
  bases: {
    [TODAS]: "Todavía no hay bases.",
    [SIN_CARPETA]: "Todas las bases están en alguna carpeta.",
    carpeta: "Esta carpeta está vacía. Usa «Mover a carpeta…» en una base para traerla aquí.",
  },
  mapas: {
    [TODAS]: "Todavía no hay mapas guardados.",
    [SIN_CARPETA]: "Todos los mapas están en alguna carpeta.",
    carpeta: "Esta carpeta está vacía. Usa «Mover a carpeta…» en un mapa para traerlo aquí.",
  },
};

function emptyText(tipo, seleccion, readOnly) {
  if (!isFolderId(seleccion)) return VACIO[tipo][seleccion];
  return readOnly ? "Esta carpeta está vacía." : VACIO[tipo].carpeta;
}

function FolderNav({ tipo, carpetas, counts, seleccion, error, onSelect, onRetry }) {
  const entradas = [
    { valor: TODAS, nombre: TEXTOS[tipo].todas, conteo: counts.todas },
    { valor: SIN_CARPETA, nombre: "Sin carpeta", conteo: counts.sinCarpeta },
    ...carpetas.map((c) => ({ valor: c.id, nombre: c.nombre, conteo: counts.porCarpeta.get(c.id) ?? 0 })),
  ];
  const selectId = `carpeta-select-${tipo}`;

  return el("nav", { class: "folder-nav", "aria-label": `Carpetas de ${TEXTOS[tipo].plural}` },
    el("ul", { class: "folder-nav-list" },
      entradas.map((entrada, index) =>
        el("li", { class: index === 2 ? "folder-nav-first" : null },
          el("button", {
            type: "button",
            class: ["folder-nav-item", entrada.valor === seleccion && "is-active"],
            "aria-current": entrada.valor === seleccion ? "true" : null,
            onclick: () => onSelect(entrada.valor),
          },
            el("span", { class: "truncate", title: entrada.nombre }, entrada.nombre),
            el("span", { class: "folder-nav-count figure" }, fmtCount(entrada.conteo)),
          )
        )
      ),
    ),
    el("div", { class: "folder-nav-select" },
      el("label", { class: "field-label", for: selectId }, "Carpeta"),
      el("select", {
        id: selectId, class: "input",
        onchange: (event) => {
          const valor = event.target.value;
          onSelect(valor === TODAS || valor === SIN_CARPETA ? valor : Number(valor));
        },
      },
        entradas.map((entrada) =>
          el("option", { value: String(entrada.valor), selected: entrada.valor === seleccion },
            `${entrada.nombre} (${fmtCount(entrada.conteo)})`))
      ),
    ),
    error && el("p", { class: "note note-aviso folder-nav-error", role: "alert" },
      `No se pudieron cargar las carpetas: ${error} `,
      el("button", { type: "button", class: "link-btn", onclick: onRetry }, "Reintentar"),
    ),
  );
}

/** The small "which folder is this in" line on a card, for the all-items view. */
export function FolderLabel(nombre) {
  return el("p", { class: "card-folder" },
    el("span", { class: "card-folder-icon", "aria-hidden": "true" }),
    el("span", { class: "visually-hidden" }, "Carpeta: "),
    nombre);
}

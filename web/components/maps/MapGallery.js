/* Saved maps, shown as titles first: the point is to scan names and open one.
 * Folders only change which cards are listed; "Nueva comparación" still draws
 * on every saved map and base, whatever folder is open. */

import { el } from "../../lib/dom.js";
import { TODAS, folderNameOf } from "../../lib/carpetas.js";
import { fmtCount, fmtDate } from "../../lib/format.js";
import { FolderLabel, FolderedGallery } from "../folders/FolderNav.js";

export function MapGallery({
  mapas, bases, carpetas = [], seleccion = TODAS, carpetasError = null,
  onOpen, onRename, onDelete, onCompare, onMove,
  onSelectFolder, onCreateFolder, onRenameFolder, onDeleteFolder, onRetryFolders,
  readOnly = false,
}) {
  return el("div", { class: "screen" },
    el("header", { class: "screen-header" },
      el("div", {},
        el("span", { class: "eyebrow" }, "Mapas"),
        el("h1", {}, "Mapas guardados"),
        el("p", { class: "secondary" },
          "Un mapa guardado conserva los terrenos tal como estaban al guardarlo. " +
          (readOnly ? "Abre uno para explorarlo." : "Combina dos o más para compararlos.")),
      ),
      !readOnly && el("div", { class: "screen-actions" },
        el("button", { type: "button", class: "btn btn-quiet", onclick: onCreateFolder },
          "Nueva carpeta"),
        el("button", {
          type: "button", class: "btn btn-principal",
          disabled: mapas.length < 2 && bases.length < 2,
          title: mapas.length < 2 && bases.length < 2
            ? "Necesitas al menos dos mapas guardados o dos bases"
            : "",
          onclick: onCompare,
        }, "Nueva comparación"),
      ),
    ),

    FolderedGallery({
      tipo: "mapas", items: mapas, carpetas, seleccion, error: carpetasError, readOnly,
      onSelect: onSelectFolder, onRenameFolder, onDeleteFolder, onRetry: onRetryFolders,
      emptyAll: el("div", { class: "empty-state" },
          el("h2", {}, "Todavía no hay mapas guardados"),
          el("p", { class: "secondary" },
            readOnly ? "Los mapas aparecerán aquí cuando se publiquen." :
            "Abre una base desde la pestaña Bases y guárdala como mapa. " +
            "Con dos mapas guardados podrás combinarlos en una comparación."),
        ),
      renderItems: (visibles) => el("ul", { class: "card-grid card-grid-maps" },
          visibles.map((mapa) =>
            el("li", { class: "card card-map" },
              el("button", {
                type: "button", class: "card-main", onclick: () => onOpen(mapa),
              },
                el("h2", { class: "card-title", title: mapa.nombre }, mapa.nombre),
                el("p", { class: "card-meta muted" },
                  mapa.tipo === "comparacion" ? "Comparación" : "Mapa simple",
                  " · ", fmtCount(mapa.conteo), " terrenos",
                ),
                el("p", { class: "card-meta muted" },
                  "Guardado el ", fmtDate(mapa.creado_en),
                  mapa.actualizado_en && mapa.actualizado_en !== mapa.creado_en
                    ? ` · actualizado el ${fmtDate(mapa.actualizado_en)}`
                    : null,
                ),
                mapa.capas.some((c) => c.base_existe === false) && el("p", { class: "card-warn" },
                  "Alguna base de origen ya no existe; se conserva lo guardado."),
                el("ul", { class: "chip-row chip-row-tight" },
                  mapa.capas.map((capa, index) =>
                    el("li", { class: ["chip", "chip-capa", capa.base_existe === false && "chip-huerfana"] },
                      el("span", {
                        class: ["legend-swatch", index >= 4 && "is-dashed"],
                        style: { background: capa.color },
                      }),
                      el("span", { class: "truncate" }, capa.nombre),
                      el("span", { class: "figure muted" }, fmtCount(capa.ubicados)),
                    )
                  )
                ),
                seleccion === TODAS && FolderLabel(folderNameOf(mapa, carpetas)),
              ),
              !readOnly && el("div", { class: "card-actions" },
                el("button", { type: "button", class: "link-btn", onclick: () => onMove(mapa) },
                  "Mover a carpeta…"),
                el("button", { type: "button", class: "link-btn", onclick: () => onRename(mapa) },
                  "Renombrar"),
                el("button", {
                  type: "button", class: "link-btn link-peligro", onclick: () => onDelete(mapa),
                }, "Eliminar"),
              ),
            )
          )
        ),
    }),
  );
}

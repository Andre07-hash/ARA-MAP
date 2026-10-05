/* The list of imported workbooks, organized in folders. */

import { el } from "../../lib/dom.js";
import { TODAS, folderNameOf } from "../../lib/carpetas.js";
import { fmtCount, fmtDate, plural } from "../../lib/format.js";
import { FolderLabel, FolderedGallery } from "../folders/FolderNav.js";

export function BaseGallery({
  bases, carpetas = [], seleccion = TODAS, carpetasError = null,
  onOpen, onAppend, onRename, onDelete, onImport, onMove, onFormats,
  onSelectFolder, onCreateFolder, onRenameFolder, onDeleteFolder, onRetryFolders,
  readOnly = false,
}) {
  return el("div", { class: "screen" },
    el("header", { class: "screen-header" },
      el("div", {},
        el("span", { class: "eyebrow" }, "Bases"),
        el("h1", {}, "Bases de terrenos"),
        el("p", { class: "secondary" },
          readOnly ? "Abre una base para explorar sus terrenos en el mapa." :
          "Cada base es un archivo de Excel o CSV importado. Ábrela para verla en el mapa " +
          "o agrégale terrenos de otro archivo."),
      ),
      !readOnly && el("div", { class: "screen-actions" },
        el("button", { type: "button", class: "btn btn-quiet", onclick: onFormats },
          "Formatos de importación"),
        el("button", { type: "button", class: "btn btn-quiet", onclick: onCreateFolder },
          "Nueva carpeta"),
        el("button", { type: "button", class: "btn btn-principal", onclick: onImport },
          "Importar archivo"),
      ),
    ),

    FolderedGallery({
      tipo: "bases", items: bases, carpetas, seleccion, error: carpetasError, readOnly,
      onSelect: onSelectFolder, onRenameFolder, onDeleteFolder, onRetry: onRetryFolders,
      emptyAll: readOnly ? el("p", {}, "Todavía no hay bases publicadas.") : Empty(onImport),
      renderItems: (visibles) => el("ul", { class: "card-grid" },
          visibles.map((base) =>
            el("li", { class: "card" },
              el("button", {
                type: "button", class: "card-main", onclick: () => onOpen(base),
              },
                el("h2", { class: "card-title truncate", title: base.nombre }, base.nombre),
                el("p", { class: "card-figures figure" },
                  el("strong", {}, fmtCount(base.conteo)),
                  " terrenos · ",
                  el("span", { class: base.ubicados ? "" : "muted" }, fmtCount(base.ubicados)),
                  " en el mapa",
                ),
                base.sin_ubicacion > 0 && el("p", { class: "card-warn" },
                  `${plural(base.sin_ubicacion, "terreno")} fuera del mapa`,
                  base.ubicacion_invalida > 0
                    ? ` · ${base.ubicacion_invalida} con coordenadas imposibles`
                    : "",
                ),
                el("p", { class: "card-meta muted" },
                  `Importada el ${fmtDate(base.importado_en)}`),
                seleccion === TODAS && FolderLabel(folderNameOf(base, carpetas)),
              ),
              !readOnly && el("div", { class: "card-actions" },
                el("button", { type: "button", class: "link-btn", onclick: () => onAppend(base) },
                  "Agregar terrenos"),
                el("button", { type: "button", class: "link-btn", onclick: () => onMove(base) },
                  "Mover a carpeta…"),
                el("button", { type: "button", class: "link-btn", onclick: () => onRename(base) },
                  "Renombrar"),
                el("button", {
                  type: "button", class: "link-btn link-peligro", onclick: () => onDelete(base),
                }, "Eliminar"),
              ),
            )
          )
        ),
    }),
  );
}

function Empty(onImport) {
  return el("div", { class: "empty-state" },
    el("h2", {}, "Todavía no hay ninguna base"),
    el("p", { class: "secondary" },
      "Archivos admitidos: Excel (.xlsx, .xlsm) y CSV (.csv). En Excel se lee la " +
      "hoja «Registro Análisis»; en un CSV, la primera fila debe contener los " +
      "encabezados, con Terreno y, para ubicarlo en el mapa, X (latitud) e Y (longitud). " +
      "Si usas Numbers, expórtalo a Excel o CSV UTF-8."),
    el("button", { type: "button", class: "btn btn-principal", onclick: onImport },
      "Importar archivo"),
  );
}

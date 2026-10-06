/* The list of imported workbooks, organized in folders. */

import { el } from "../../lib/dom.js";
import { TODAS, folderNameOf } from "../../lib/carpetas.js";
import { estadoDeFuente } from "../../lib/excel.js";
import { fmtCount, fmtDate, plural } from "../../lib/format.js";
import { AyudaActualizar } from "../excel/excelActions.js";
import { FolderLabel, FolderedGallery } from "../folders/FolderNav.js";

export function BaseGallery({
  bases, carpetas = [], seleccion = TODAS, carpetasError = null,
  onOpen, onAppend, onRename, onDelete, onImport, onMove, onFormats,
  onSelectFolder, onCreateFolder, onRenameFolder, onDeleteFolder, onRetryFolders,
  fuentes = [], ocupada = () => false, onConnectExcel, excel = {},
  readOnly = false,
}) {
  const fuentePorBase = new Map(fuentes.map((f) => [f.base_id, f]));
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
        el("button", { type: "button", class: "btn btn-quiet", onclick: onConnectExcel },
          "Conectar Excel"),
        el("button", { type: "button", class: "btn btn-principal", onclick: onImport },
          "Importar archivo"),
      ),
    ),
    !readOnly && fuentes.length > 0 && AyudaActualizar(),

    FolderedGallery({
      tipo: "bases", items: bases, carpetas, seleccion, error: carpetasError, readOnly,
      onSelect: onSelectFolder, onRenameFolder, onDeleteFolder, onRetry: onRetryFolders,
      emptyAll: readOnly ? el("p", {}, "Todavía no hay bases publicadas.") : Empty(onImport),
      renderItems: (visibles) => el("ul", { class: "card-grid" },
          visibles.map((base) => {
            const fuente = fuentePorBase.get(base.id);
            const estado = fuente && estadoDeFuente(fuente, { ocupada: ocupada(fuente.id) });
            return el("li", { class: ["card", fuente && "card-excel"] },
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
                fuente
                  ? el("p", { class: "card-meta muted" },
                    `Conectada a «${fuente.archivo.nombre}» · ${fuente.cuenta.correo ?? fuente.cuenta.nombre ?? ""}`)
                  : el("p", { class: "card-meta muted" },
                    `Importada el ${fmtDate(base.importado_en)}`),
                seleccion === TODAS && FolderLabel(folderNameOf(base, carpetas)),
              ),
              estado && EstadoExcel(estado),
              !readOnly && el("div", { class: "card-actions" },
                fuente
                  ? AccionesExcel(fuente, estado, excel)
                  : el("button", { type: "button", class: "link-btn", onclick: () => onAppend(base) },
                    "Agregar terrenos"),
                el("button", { type: "button", class: "link-btn", onclick: () => onMove(base) },
                  "Mover a carpeta…"),
                el("button", { type: "button", class: "link-btn", onclick: () => onRename(base) },
                  "Renombrar"),
                // A connected base's rows belong to the workbook: the server
                // refuses deleting it, so the action is not offered.
                !fuente && el("button", {
                  type: "button", class: "link-btn link-peligro", onclick: () => onDelete(base),
                }, "Eliminar"),
              ),
            );
          })
        ),
    }),
  );
}

function EstadoExcel(estado) {
  return el("div", { class: ["excel-estado", `excel-${estado.tono}`], role: "status" },
    el("p", { class: "excel-estado-titulo" },
      el("span", { class: "excel-tag" }, "Excel"), " ", estado.titulo),
    estado.nota && el("p", { class: "excel-estado-nota" }, estado.nota),
    el("ul", { class: "excel-estado-datos muted" }, estado.detalles.map((d) => el("li", {}, d))),
  );
}

function AccionesExcel(fuente, estado, excel) {
  const a = estado.acciones;
  const boton = (accion, texto, fn, extra = {}) => a.has(accion) && el("button", {
    type: "button", class: "link-btn", onclick: () => fn?.(fuente), ...extra,
  }, texto);
  return [
    estado.tono === "curso" && !a.has("comprobar")
      ? el("button", { type: "button", class: "link-btn", disabled: true, "aria-disabled": "true" },
        "Actualizando…")
      : boton("actualizar", "Actualizar desde Excel", excel.actualizar, { class: "link-btn link-principal" }),
    boton("comprobar", "Comprobar", excel.comprobar),
    boton("reconectar_cuenta", "Volver a conectar la cuenta", excel.reconectar),
    boton("reactivar", "Volver a activar", excel.reactivar),
    fuente.archivo.web_url && el("a", {
      class: "link-btn", href: fuente.archivo.web_url, target: "_blank", rel: "noopener noreferrer",
    }, "Abrir en Excel"),
    boton("desconectar", "Desconectar", excel.desconectar),
  ];
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

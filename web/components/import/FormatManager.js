/* Optional management of remembered import formats, outside the import flow.
 *
 * Formats are remembered automatically on a confirmed import; this is only for
 * renaming or forgetting one. Forgetting a format changes no imported data and
 * no saved map.
 */

import { api } from "../../lib/api.js";
import { el } from "../../lib/dom.js";
import { fmtDate, plural } from "../../lib/format.js";
import { promptFolderName } from "../folders/FolderDialogs.js";
import { confirmDialog, openDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";

export async function openFormatManager() {
  const lista = el("div", { class: "format-list", "aria-live": "polite" }, el("p", { class: "secondary" }, "Cargando…"));

  async function cargar() {
    try {
      const { formatos } = await api.formatos();
      lista.replaceChildren(formatos.length
        ? el("ul", { class: "format-items" }, formatos.map(Formato))
        : el("p", { class: "secondary" },
            "Todavía no hay formatos. Se guardan solos al importar un archivo con «Recordar este formato»."));
    } catch (error) {
      lista.replaceChildren(el("p", { class: "note note-aviso", role: "alert" }, error.message));
    }
  }

  function Formato(f) {
    return el("li", { class: ["format-item", !f.vigente && "is-replaced"] },
      el("div", {},
        el("strong", {}, f.nombre),
        el("p", { class: "muted" },
          `Versión ${f.version}${f.vigente ? "" : " · reemplazada por una más reciente"} · ` +
          `usado ${plural(f.usos, "vez", "veces")} · actualizado el ${fmtDate(f.actualizado_en)}`),
        el("details", {},
          el("summary", {}, "Columnas"),
          el("ul", { class: "format-fields" }, f.campos.map((c) =>
            el("li", {}, el("span", { class: "figure" }, c.encabezado), " → ", c.destino)))),
      ),
      el("div", { class: "card-actions-inline" },
        el("button", { type: "button", class: "link-btn", onclick: () => renombrar(f) }, "Renombrar"),
        el("button", { type: "button", class: "link-btn link-peligro", onclick: () => olvidar(f) }, "Olvidar"),
      ),
    );
  }

  function renombrar(f) {
    promptFolderName({
      titulo: "Renombrar formato", nombre: f.nombre, etiqueta: "Nombre del formato",
      onSave: async (nombre) => { await api.renameFormato(f.id, nombre); await cargar(); toast("Formato renombrado."); },
    });
  }

  async function olvidar(f) {
    const ok = await confirmDialog({
      titulo: "Olvidar formato",
      mensaje: `¿Olvidar «${f.nombre}»? Las próximas importaciones con estos encabezados se volverán a ` +
               "interpretar. No cambia ninguna base, terreno ni mapa ya guardado.",
      confirmar: "Olvidar", peligro: true,
    });
    if (!ok) return;
    try { await api.deleteFormato(f.id); await cargar(); toast("Formato olvidado."); }
    catch (error) { toastError(error.message); }
  }

  openDialog({
    titulo: "Formatos de importación",
    descripcion: "Se reconocen solos cuando un archivo tiene los mismos encabezados, aunque estén en otro orden.",
    ancho: "40rem",
    contenido: el("div", {},
      lista,
      el("p", { class: "note" },
        "¿Vas a preparar un archivo nuevo? ",
        el("a", { class: "link-btn", href: "assets/plantilla-terrenos.csv", download: "plantilla-terrenos.csv" },
          "Descargar plantilla CSV")),
    ),
    acciones: [{ etiqueta: "Cerrar", onClick: (close) => close() }],
  });
  await cargar();
}

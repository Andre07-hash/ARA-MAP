/* Folder dialogs: name a folder, move an item, confirm a folder's removal, and
 * the destination field shared by every dialog that creates something.
 *
 * All are native <dialog>s (focus trap, Escape to cancel) with labelled fields
 * inside a <form>, so Enter submits. Typing never touches global state, so the
 * gallery re-rendering behind a dialog cannot steal its focus.
 */

import { el } from "../../lib/dom.js";
import { TEXTOS } from "../../lib/carpetas.js";
import { confirmDialog, openDialog } from "../ui/dialog.js";
import { toastError } from "../ui/toast.js";

const MAX_NOMBRE = 100;

/* A dialog whose body is a form: the primary action submits it. */
function formDialog({ titulo, descripcion, campos, etiqueta, onSubmit }) {
  // The footer buttons live outside the form, so a visually hidden submit
  // button gives Enter something to press in every field, radios included.
  const form = el("form", { class: "folder-form", novalidate: true }, campos,
    el("button", {
      type: "submit", class: "visually-hidden", tabindex: "-1", "aria-hidden": "true",
    }, etiqueta));
  let enviando = false;
  const { dialog, close } = openDialog({
    titulo, descripcion, contenido: form, ancho: "28rem",
    acciones: [
      { etiqueta: "Cancelar", onClick: (cerrar) => cerrar() },
      { etiqueta, variante: "principal", onClick: () => form.requestSubmit() },
    ],
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (enviando) return;
    enviando = true;
    try { await onSubmit(close); } finally { enviando = false; }
  });
  return { dialog, close, form };
}

/** Ask for a folder name; `onSave(nombre)` may throw to keep the dialog open. */
export function promptFolderName({
  titulo, nombre = "", confirmar = "Guardar", etiqueta = "Nombre de la carpeta", onSave,
}) {
  const input = el("input", {
    class: "input", id: "carpeta-nombre", value: nombre, maxlength: String(MAX_NOMBRE),
    autocomplete: "off", required: true,
  });
  const { dialog } = formDialog({
    titulo,
    campos: el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: "carpeta-nombre" }, etiqueta),
      input,
    ),
    etiqueta: confirmar,
    onSubmit: async (close) => {
      const limpio = input.value.replace(/\s+/g, " ").trim();
      if (!limpio) {
        toastError("El nombre no puede estar vacío.");
        input.focus();
        return;
      }
      try {
        await onSave(limpio);
        close();
      } catch (error) {
        toastError(error.message);
        input.focus();
        input.select();
      }
    },
  });
  input.select();
  return dialog;
}

/**
 * Choose where an item goes. `onMove(carpetaId)` performs the move; if it
 * fails because the destination vanished (404), `reload()` fetches the current
 * folders and the choices are rebuilt, never silently substituted.
 */
export function moveToFolderDialog({ tipo, item, carpetas, onMove, reload }) {
  let opciones = carpetas;
  const lista = el("fieldset", { class: "folder-choices" },
    el("legend", { class: "field-label" }, "Carpeta de destino"));
  const nombreGrupo = `destino-${tipo}-${item.id}`;

  function renderOpciones(seleccion) {
    lista.replaceChildren(
      lista.firstChild,
      ...[{ id: null, nombre: "Sin carpeta" }, ...opciones].map((carpeta) =>
        el("label", { class: "check" },
          el("input", {
            type: "radio", name: nombreGrupo, value: carpeta.id == null ? "" : String(carpeta.id),
            checked: carpeta.id === seleccion,
          }),
          el("span", { class: "truncate" }, carpeta.nombre),
          carpeta.id === (item.carpeta_id ?? null) && el("span", { class: "muted" }, "actual"),
        )
      )
    );
  }
  renderOpciones(item.carpeta_id ?? null);

  const elegido = () => {
    const input = lista.querySelector(`input[name="${nombreGrupo}"]:checked`);
    return input && input.value !== "" ? Number(input.value) : null;
  };

  const { dialog } = formDialog({
    titulo: "Mover a carpeta",
    descripcion: `«${item.nombre}»`,
    campos: [
      lista,
      opciones.length === 0 && el("p", { class: "note" },
        `Todavía no hay carpetas de ${TEXTOS[tipo].plural}. Crea una con «Nueva carpeta».`),
    ],
    etiqueta: "Mover",
    onSubmit: async (close) => {
      const destino = elegido();
      try {
        await onMove(destino);
        close();
      } catch (error) {
        toastError(error.message);
        if (error.status === 404 && reload) {
          opciones = await reload();
          renderOpciones(opciones.some((c) => c.id === destino) ? destino : item.carpeta_id ?? null);
        }
      }
    },
  });
  // Focus the current placement rather than the first radio.
  lista.querySelector("input:checked")?.focus();
  return dialog;
}

/** Confirm a folder's removal, saying exactly what happens to its contents. */
export function confirmDeleteFolder({ tipo, carpeta, conteo }) {
  const { plural } = TEXTOS[tipo];
  const contenido = conteo === 0
    ? "La carpeta está vacía."
    : tipo === "bases"
      ? `Sus ${conteo === 1 ? "1 base pasará" : `${conteo} ${plural} pasarán`} a «Sin carpeta». ` +
        "No se eliminarán bases ni terrenos."
      : `Sus ${conteo === 1 ? "1 mapa pasará" : `${conteo} ${plural} pasarán`} a «Sin carpeta». ` +
        "No se eliminará ningún mapa.";
  return confirmDialog({
    titulo: "Eliminar carpeta",
    mensaje: `¿Eliminar la carpeta «${carpeta.nombre}»? ${contenido}`,
    confirmar: "Eliminar carpeta",
    peligro: true,
  });
}

/**
 * A labelled "Carpeta" select for creation dialogs. Its value is a folder id
 * or null; the destination is read when the dialog submits, not inferred.
 */
export function FolderSelect({ id, carpetas, value = null }) {
  const select = el("select", { class: "input", id },
    el("option", { value: "", selected: value == null }, "Sin carpeta"),
    carpetas.map((carpeta) =>
      el("option", { value: String(carpeta.id), selected: carpeta.id === value }, carpeta.nombre)),
  );
  return {
    element: el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: id }, "Carpeta"),
      select,
    ),
    value: () => (select.value === "" ? null : Number(select.value)),
  };
}

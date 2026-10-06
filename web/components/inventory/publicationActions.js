/* Lifecycle actions on one inventory terrain: preview/publish, withdraw from
 * the catalog, archive and restore. Every team member has all of them; each
 * sends the version on screen and a 409 means "look again", never a retry.
 */

import { api } from "../../lib/api.js";
import { getState, setDataset } from "../../lib/store.js";
import { confirmDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";
import { cargarDetalle, pedirCarga, reemplazarRegistro } from "./datasets.js";
import { openPublicationPreview } from "./PublicationPreview.js";

const nombreDe = (t) => t?.draft?.terreno || "Este terreno";

/**
 * A record changed (here or by someone else): show the new version, reload
 * the inventory list, and make the public catalog reload when next shown --
 * or now, if it is loaded -- so it reflects the commit.
 */
export function registroCambiado(terreno) {
  if (terreno) reemplazarRegistro(terreno);
  else {
    const { detalle } = getState();
    if (detalle?.tipo === "inventario") cargarDetalle("inventario", detalle.id);
  }
  pedirCarga("inventario", { inmediato: true });
  if (getState().catalogo.cargado) pedirCarga("catalogo", { inmediato: true });
  else setDataset("catalogo", { cargado: false });
}

/** `alPublicar(terreno)` runs after a successful publish (the editor uses it
 * to step back to the record, whose version just moved on). */
export function vistaPrevia(terreno, { alPublicar } = {}) {
  return openPublicationPreview({
    terreno,
    onPublished: (publicado) => { registroCambiado(publicado); alPublicar?.(publicado); },
    onChanged: registroCambiado,
  });
}

export async function retirarDelCatalogo(terreno) {
  const ok = await confirmDialog({
    titulo: "Retirar del catálogo",
    mensaje: `«${nombreDe(terreno)}» dejará de verse en el catálogo público en cuanto confirmes. ` +
      "El borrador, su historial y sus datos privados se conservan, y se puede volver a publicar.",
    confirmar: "Retirar del catálogo",
    peligro: true,
  });
  if (ok) await ejecutar(terreno, "despublicar", "Retirado del catálogo público.");
}

export async function archivar(terreno) {
  const publicado = terreno.publication_state === "published";
  const ok = await confirmDialog({
    titulo: "Archivar terreno",
    mensaje: `«${nombreDe(terreno)}» saldrá del inventario activo` +
      (publicado ? " y dejará de verse en el catálogo público en cuanto confirmes" : "") +
      ". Su historial se conserva y se puede restaurar desde «Incluir archivados».",
    confirmar: "Archivar",
    peligro: true,
  });
  if (ok) await ejecutar(terreno, "archivar", "Terreno archivado.");
}

export async function restaurar(terreno) {
  const ok = await confirmDialog({
    titulo: "Restaurar terreno",
    mensaje: `«${nombreDe(terreno)}» vuelve al inventario activo como no publicado. ` +
      "No aparece en el catálogo hasta que alguien lo publique de nuevo.",
    confirmar: "Restaurar",
  });
  if (ok) await ejecutar(terreno, "restaurar", "Terreno restaurado · no publicado.");
}

async function ejecutar(terreno, accion, mensaje) {
  try {
    const { terreno: actualizado } = await api[accion](terreno.id, terreno.version);
    toast(mensaje);
    registroCambiado(actualizado);
  } catch (error) {
    if (error.status === 409) {
      toastError(error.detalle?.code === "conflict"
        ? "Otra persona cambió este terreno. Revisa la versión actual; no se aplicó nada."
        : error.message);
      registroCambiado(error.detalle?.terreno);
      return;
    }
    toastError(error.message);
  }
}

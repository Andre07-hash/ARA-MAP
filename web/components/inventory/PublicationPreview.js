/* Vista previa and Publicar.
 *
 * The preview is the server's own public projection of the SAVED draft,
 * rendered with the public detail component. Publish then sends exactly the
 * reviewed {version, revision_id}; if anyone saved in between, the server
 * answers 409 and the user is taken back to review the new draft -- another
 * person's edit is never published unseen.
 */

import { api } from "../../lib/api.js";
import { el } from "../../lib/dom.js";
import { cambiosPendientes, valorPendiente } from "../../lib/inventario.js";
import { openDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";
import { PublicTerrainDetail } from "./TerrainFacts.js";

/**
 * Open the preview of `terreno`'s saved draft. `onPublished(terreno)` gets the
 * updated InternalTerrain; `onChanged(terreno?)` is told whenever the record
 * turned out to be newer than what was on screen.
 */
export async function openPublicationPreview({ terreno, onPublished, onChanged, aviso = null }) {
  let vista;
  try {
    vista = await api.vistaPublica(terreno.id, terreno.draft_revision_id);
  } catch (error) {
    if (error.status === 409) {
      // The draft moved on since this screen was drawn: review the new one.
      const actual = error.detalle?.terreno;
      onChanged?.(actual);
      if (actual) {
        return openPublicationPreview({
          terreno: actual, onPublished, onChanged,
          aviso: "El borrador cambió desde que abriste este terreno. Esta es la versión guardada más reciente.",
        });
      }
    }
    toastError(`No se pudo preparar la vista previa: ${error.message}`);
    return undefined;
  }
  return mostrar({ terreno, vista, onPublished, onChanged, aviso });
}

function mostrar({ terreno, vista, onPublished, onChanged, aviso }) {
  const bloqueado = vista.blockers.length > 0;
  const estado = el("p", { class: "secondary", role: "status" });
  const pendientes = cambiosPendientes(terreno);
  const ya = terreno.published_revision_id && terreno.published_revision_id === vista.revision_id;

  const contenido = el("div", { class: "vista-previa" },
    aviso && el("p", { class: "note note-aviso" }, aviso),
    el("p", { class: "secondary" },
      "Así verá el público este terreno cuando se publique. Solo se publica lo guardado; " +
      "contacto, notas internas y datos del archivo nunca se muestran."),
    bloqueado && el("section", { class: "findings", "aria-label": "No se puede publicar todavía" },
      el("h3", { class: "eyebrow" }, "No se puede publicar todavía"),
      vista.blockers.map((b) => el("p", { class: "finding finding-error" },
        el("span", { class: "finding-icon", "aria-hidden": "true" }, "!"),
        el("span", {}, b.message)))),
    vista.warnings.length > 0 && el("section", { class: "findings", "aria-label": "Avisos" },
      el("h3", { class: "eyebrow" }, "Revisa antes de publicar"),
      vista.warnings.map((w) => el("p", { class: "finding finding-aviso" },
        el("span", { class: "finding-icon", "aria-hidden": "true" }, "i"),
        el("span", {}, w.message)))),
    pendientes.length > 0 && CambiosAlPublicar(pendientes),
    ya && el("p", { class: "note" }, "Esta revisión ya es la publicada."),
    PublicTerrainDetail({ terreno: vista.terreno, vistaPrevia: true }),
    estado,
  );

  let enCurso = false;
  const { dialog, close } = openDialog({
    titulo: "Vista previa · Aún no publicada",
    descripcion: `Revisión ${String(vista.revision_id).slice(0, 8)} · versión ${vista.version}`,
    ancho: "44rem",
    contenido,
    acciones: [
      { etiqueta: "Cerrar", onClick: (cerrar) => cerrar() },
      ...(bloqueado || ya ? [] : [{
        etiqueta: "Publicar", variante: "principal",
        onClick: async (cerrar) => {
          if (enCurso) return;
          enCurso = true;
          estado.textContent = "Publicando…";
          try {
            const { terreno: publicado } = await api.publicar(terreno.id, vista.version, vista.revision_id);
            cerrar();
            toast(publicado.public_visible
              ? `Publicado · revisión ${String(vista.revision_id).slice(0, 8)}.`
              : "Publicado: este terreno queda fuera del catálogo público.");
            onPublished?.(publicado);
          } catch (error) {
            enCurso = false;
            estado.textContent = "";
            if (error.status === 409 && error.detalle?.terreno) {
              // Someone saved (or published) meanwhile: back to review.
              cerrar();
              const actual = error.detalle.terreno;
              onChanged?.(actual);
              if (actual.publication_state === "archived") {
                toastError("Otra persona archivó este terreno. No se publicó nada.");
                return;
              }
              openPublicationPreview({
                terreno: actual, onPublished, onChanged,
                aviso: "Otra persona cambió este terreno mientras lo revisabas. No se publicó nada: " +
                  "revisa esta versión antes de publicar.",
              });
              return;
            }
            if (error.status === 409) {
              cerrar();
              toastError(error.message);
              onChanged?.();
              return;
            }
            estado.textContent = error.status === 422
              ? `No se publicó: ${(error.detalle?.blockers ?? []).map((b) => b.message).join(" ") || error.message}`
              : `No se publicó: ${error.message}`;
          }
        },
      }]),
    ],
  });
  dialog.classList.add("dialog-vista-previa");
  return { dialog, close };
}

/* What publishing would change in the catalog; price and availability first
 * and marked, so they cannot be missed. */
export function CambiosAlPublicar(cambios) {
  return el("section", { class: "cambios-pendientes", "aria-label": "Cambios sin publicar" },
    el("h3", { class: "eyebrow" }, "Cambios guardados sin publicar"),
    el("ul", { class: "diff-list" },
      cambios.map((c) => el("li", { class: ["diff", c.destacado && "diff-destacado"] },
        el("span", { class: "diff-campo muted" }, c.etiqueta),
        el("span", { class: "diff-anterior" }, valorPendiente(c.clave, c.publicado)),
        el("span", { class: "diff-flecha", "aria-hidden": "true" }, "→"),
        el("span", { class: "diff-nuevo" }, valorPendiente(c.clave, c.borrador)),
      ))),
  );
}

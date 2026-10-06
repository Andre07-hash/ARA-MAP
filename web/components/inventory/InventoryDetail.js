/* The team's detail panel for one inventory terrain.
 *
 * The draft's business fields go through the same public renderer the catalog
 * uses; everything private (status, contacts, notes, verification, source
 * fields, attribution) is added around it, never passed into it.
 */

import { el } from "../../lib/dom.js";
import { fmtDate, fmtText, googleMapsSearch } from "../../lib/format.js";
import {
  accionesDePublicacion, avisoDisponibilidadPendiente, cambiosPendientes, estadoPublicacion,
  estadoUbicacion, pickPublic,
} from "../../lib/inventario.js";
import { CambiosAlPublicar } from "./PublicationPreview.js";
import { DisponibilidadChip, Section, TerrainFacts } from "./TerrainFacts.js";

export function InventoryDetail({
  terreno, onEdit, onHistory, onZoomAEscala, onClose,
  onPreview, onUnpublish, onArchive, onRestore,
}) {
  const draft = terreno.draft ?? {};
  const estado = estadoPublicacion(terreno);
  const ubicacion = estadoUbicacion(draft.lat, draft.lon);
  const lugar = [draft.municipio, draft.estado].filter(Boolean).join(", ");
  const aviso = avisoDisponibilidadPendiente(terreno);
  const atencion = motivosDeAtencion(terreno.attention);
  const extra = Object.entries(terreno.source_extra ?? {});
  const confirmaciones = terreno.confirmations ?? {};
  const acciones = accionesDePublicacion(terreno);
  const pendientes = cambiosPendientes(terreno);
  const pendienteComercial = pendientes.some((c) => c.destacado);

  return el("aside", {
    class: "detail", role: "complementary",
    "aria-label": `Detalle de ${draft.terreno ?? "terreno"}`, tabindex: "-1",
  },
    el("header", { class: "detail-header" },
      el("div", { class: "detail-heading" },
        el("span", { class: "eyebrow" }, "Inventario"),
        el("h2", {}, draft.terreno || "Sin nombre"),
        lugar && el("p", { class: "secondary" }, lugar),
        el("p", { class: "estado-row" },
          EstadoChip(estado),
          DisponibilidadChip(draft.availability),
        ),
        terreno.published_at && el("p", { class: "muted estado-fecha" },
          `Publicado el ${fmtDate(terreno.published_at)}`),
      ),
      el("button", {
        type: "button", class: "icon-btn", "aria-label": "Cerrar detalle", onclick: onClose,
      }, "×"),
    ),

    el("div", { class: "detail-actions" },
      el("button", { type: "button", class: "btn btn-principal", onclick: onEdit }, "Editar"),
      acciones.vistaPrevia && onPreview && el("button", {
        type: "button", class: "btn btn-quiet", id: "vista-previa-btn", onclick: onPreview,
        title: "Ve lo que verá el público y publica esta versión guardada",
      }, terreno.publication_state === "published" && !terreno.has_pending_changes
        ? "Vista previa" : "Vista previa y publicar"),
      // A stable id: the history dialog gives focus back to it when it closes,
      // even if the panel was redrawn meanwhile (D-1).
      el("button", { type: "button", class: "btn btn-quiet", id: "historial-btn", onclick: onHistory },
        "Historial"),
      ubicacion === "valida" && onZoomAEscala && el("button", {
        type: "button", class: "btn btn-quiet", onclick: onZoomAEscala,
        title: "Acerca el mapa hasta que el círculo cubra la superficie real",
      }, "Ver a escala"),
    ),

    aviso && el("p", { class: "note note-aviso", role: "status" }, aviso),
    pendientes.length > 0 && el("div", {
      class: ["note", "nota-pendiente", pendienteComercial && "note-aviso"], role: "status",
    },
      el("p", {}, pendienteComercial
        ? "Precio o disponibilidad guardados sin publicar: el catálogo sigue mostrando la versión publicada."
        : "Hay cambios guardados sin publicar: el catálogo sigue mostrando la versión publicada."),
      CambiosAlPublicar(pendientes),
    ),

    atencion.length > 0 && el("section", { class: "findings", "aria-label": "Necesita atención" },
      el("h3", { class: "eyebrow" }, "Necesita atención"),
      atencion.map((motivo) => el("p", { class: "finding finding-aviso" },
        el("span", { class: "finding-icon", "aria-hidden": "true" }, "i"),
        el("span", {}, motivo),
      ))),

    TerrainFacts(pickPublic(draft)),

    ubicacion !== "valida" && el("section", { class: "detail-section detail-unplaced" },
      el("h3", { class: "eyebrow" }, ubicacion === "invalida" ? "Coordenadas imposibles" : "Sin coordenadas"),
      el("p", { class: "secondary" },
        ubicacion === "invalida"
          ? `Las coordenadas (${draft.lat}, ${draft.lon}) caen fuera de México o tienen X y Y ` +
            "invertidas, así que no se dibuja. Corrígelas directamente en «Editar»."
          : "Este terreno no aparece en el mapa porque no tiene coordenadas. Búscalo en " +
            "Google Maps, copia la latitud (X) y la longitud (Y) y escríbelas en «Editar»; " +
            "no hace falta volver a importar ningún archivo."),
      el("div", { class: "detail-actions" },
        el("button", { type: "button", class: "btn btn-quiet", onclick: onEdit }, "Editar ubicación"),
        el("a", {
          class: "btn btn-quiet", href: googleMapsSearch(draft),
          target: "_blank", rel: "noopener noreferrer",
        }, "Buscar en Google Maps"),
      ),
    ),

    el("div", { class: "privado" },
      el("p", { class: "eyebrow privado-titulo" }, "Solo equipo · nunca se publica"),
      Section("Contacto y notas", [
        ["Contacto", el("span", { class: "pre" }, fmtText(draft.contacto))],
        ["Notas internas", el("span", { class: "pre" }, fmtText(draft.notas_internas))],
      ]),
      Section("Verificación", [
        ["Precio confirmado", confirmacion(confirmaciones.price)],
        ["Disponibilidad confirmada", confirmacion(confirmaciones.availability)],
      ]),
      extra.length > 0 && Section("Otros campos del archivo",
        extra.map(([k, v]) => [k, fmtText(v)])),
    ),

    (acciones.retirar || acciones.archivar || acciones.restaurar) && el("section", {
      class: "detail-section detail-ciclo", "aria-label": "Publicación y archivo",
    },
      el("h3", { class: "eyebrow" }, "Publicación y archivo"),
      el("div", { class: "detail-actions" },
        acciones.retirar && onUnpublish && el("button", {
          type: "button", class: "btn btn-quiet", onclick: onUnpublish,
        }, "Retirar del catálogo"),
        acciones.archivar && onArchive && el("button", {
          type: "button", class: "btn btn-quiet", onclick: onArchive,
        }, "Archivar"),
        acciones.restaurar && onRestore && el("button", {
          type: "button", class: "btn btn-principal", onclick: onRestore,
        }, "Restaurar"),
      ),
    ),

    el("footer", { class: "detail-footer" },
      el("p", { class: "muted" }, "ID ", el("span", { class: "mono" }, terreno.id)),
      el("p", { class: "muted" },
        `Versión ${terreno.version}`,
        terreno.updated_at ? ` · modificado el ${fmtDate(terreno.updated_at)}` : "",
        actorDe(terreno.updated_by) ? ` por ${actorDe(terreno.updated_by)}` : ""),
    ),
  );
}

export function EstadoChip(estado) {
  return el("span", { class: ["estado-chip", `estado-${estado.tono}`] }, estado.etiqueta);
}

const actorDe = (a) => (typeof a === "string" ? a : a?.display_name ?? null);

/** A confirmation stamp {at, by}; its date is never the last edit's. */
export function confirmacion(stamp) {
  if (!stamp?.at) return "Nunca confirmado";
  return `${fmtDate(stamp.at)}${actorDe(stamp.by) ? ` · ${actorDe(stamp.by)}` : ""}`;
}

/* Attention reasons come from the server; this only displays them. */
function motivosDeAtencion(attention) {
  const lista = Array.isArray(attention) ? attention : attention?.reasons ?? [];
  return lista
    .map((m) => (typeof m === "string" ? m : m?.message ?? m?.mensaje ?? m?.code))
    .filter(Boolean);
}

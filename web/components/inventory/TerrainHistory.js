/* The history of one inventory terrain: who did what, when, and the values
 * before and after. Authenticated only; private values appear here because
 * every team member may read them. */

import { api } from "../../lib/api.js";
import { el } from "../../lib/dom.js";
import { fmtText } from "../../lib/format.js";
import { campo, mostrarValor, normalizarEvento } from "../../lib/inventario.js";
import { openDialog } from "../ui/dialog.js";

const fechaHora = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" });
const cuando = (iso) => {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.valueOf()) ? fechaHora.format(d) : "—";
};

export function openTerrainHistory({ id, nombre }) {
  const lista = el("ol", { class: "historial" });
  const estado = el("p", { class: "secondary", role: "status" }, "Cargando historial…");
  const mas = el("button", { type: "button", class: "btn btn-quiet", hidden: true }, "Cargar más");
  let cursor = null;

  async function cargar() {
    mas.disabled = true;
    estado.textContent = "Cargando historial…";
    estado.hidden = false;
    try {
      const pagina = await api.historial(id, cursor);
      const eventos = (pagina.eventos ?? pagina.events ?? pagina.historial ?? []).map(normalizarEvento);
      lista.append(...eventos.map(Evento));
      cursor = pagina.next_cursor ?? null;
      mas.hidden = cursor == null;
      estado.hidden = lista.childElementCount > 0;
      estado.textContent = "Todavía no hay cambios registrados.";
    } catch (error) {
      estado.hidden = false;
      estado.replaceChildren(
        `No se pudo cargar el historial: ${error.message} `,
        el("button", { type: "button", class: "link-btn", onclick: cargar }, "Reintentar"),
      );
    } finally {
      mas.disabled = false;
    }
  }
  mas.addEventListener("click", cargar);

  openDialog({
    titulo: "Historial",
    descripcion: nombre,
    ancho: "40rem",
    contenido: el("div", {}, estado, lista, mas),
    acciones: [{ etiqueta: "Cerrar", onClick: (close) => close() }],
  });
  cargar();
}

function Evento(evento) {
  return el("li", { class: "historial-evento" },
    el("p", { class: "historial-cabecera" },
      el("strong", {}, evento.accion),
      el("span", { class: "muted" }, ` · ${evento.actor} · ${cuando(evento.fecha)}`),
      evento.version != null && el("span", { class: "muted figure" }, ` · versión ${evento.version}`),
    ),
    evento.confirmados.length > 0 && el("p", { class: "secondary" },
      `Confirmó: ${evento.confirmados.join(" y ").toLowerCase()}.`),
    evento.cambios.length > 0 && el("ul", { class: "diff-list" },
      evento.cambios.map(({ campo: clave, antes, despues }) => {
        const c = campo(clave);
        const ver = (v) => (c ? mostrarValor(c, v) : fmtText(v));
        return el("li", { class: "diff" },
          el("span", { class: "diff-campo muted" }, c?.etiqueta ?? clave),
          el("span", { class: "diff-anterior" }, ver(antes)),
          el("span", { class: "diff-flecha", "aria-hidden": "true" }, "→"),
          el("span", { class: "diff-nuevo" }, ver(despues)),
        );
      })),
  );
}

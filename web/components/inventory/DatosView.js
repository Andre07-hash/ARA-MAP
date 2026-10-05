/* Presentational pieces of the catalog and inventory workspace: the toolbar
 * and the empty/failed/loading message over the map. Pure: data and
 * callbacks in, nodes out. */

import { el } from "../../lib/dom.js";
import { fmtCount, plural } from "../../lib/format.js";
import { contarFiltros } from "../../lib/inventario.js";
import { routeHash } from "../../lib/router.js";

export const segment = (etiqueta, activo, onClick) =>
  el("button", {
    type: "button",
    class: ["segment", activo && "is-active"],
    "aria-pressed": String(activo),
    onclick: onClick,
  }, etiqueta);

/* The count is only stated once every page of the query has arrived. */
function estadoDeCarga(datos, items) {
  if (datos.cargando) {
    return datos.progreso?.total != null
      ? `Cargando ${fmtCount(datos.progreso.recibidos)} de ${fmtCount(datos.progreso.total)}…`
      : "Cargando…";
  }
  if (datos.error) {
    return datos.consulta != null ? `${plural(items.length, "terreno")} · no se pudo actualizar` : "Sin datos";
  }
  return plural(items.length, "terreno");
}

export function DatosToolbar({ tipo, datos, items, panel, filtros, onPanel, onEncuadrar }) {
  const catalogo = tipo === "catalogo";
  return [
    el("div", { class: "toolbar-title" },
      el("span", { class: "eyebrow" }, catalogo ? "Catálogo público" : "Inventario"),
      el("h1", { class: "truncate" }, catalogo ? "Terrenos disponibles" : "Inventario de terrenos"),
      el("p", { class: "toolbar-estado secondary figure", role: "status", "aria-live": "polite" },
        estadoDeCarga(datos, items)),
    ),
    el("div", { class: "toolbar-actions" },
      filtros,
      el("div", { class: "segmented", role: "group", "aria-label": "Vista" },
        segment("Mapa", panel === "mapa", () => onPanel("mapa")),
        segment("Tabla", panel === "tabla", () => onPanel("tabla")),
      ),
      el("button", { type: "button", class: "btn btn-quiet", onclick: onEncuadrar }, "Encuadrar"),
      !catalogo && el("a", {
        class: "btn btn-principal", href: routeHash({ nombre: "nuevo" }),
      }, "Nuevo terreno"),
    ),
  ];
}

/* Empty, failed and first-load states, drawn over the map. */
export function MensajeDatos({ tipo, datos, items, onRetry, onClear }) {
  if (items.length || (datos.cargado && datos.cargando)) return null;
  const catalogo = tipo === "catalogo";
  let titulo;
  let texto;
  let accion = null;

  if (datos.error) {
    titulo = catalogo ? "No se pudo cargar el catálogo" : "No se pudo cargar el inventario";
    texto = datos.error;
    accion = el("button", { type: "button", class: "btn btn-quiet", onclick: onRetry }, "Reintentar");
  } else if (!datos.cargado) {
    titulo = "Cargando…";
    texto = catalogo ? "Buscando terrenos publicados." : "Reuniendo el inventario completo.";
  } else if (contarFiltros(datos.filtros, tipo) > 0) {
    titulo = "Ningún terreno coincide con los filtros";
    texto = "Prueba con menos filtros.";
    accion = el("button", { type: "button", class: "btn btn-quiet", onclick: onClear }, "Limpiar filtros");
  } else if (catalogo) {
    titulo = "Todavía no hay terrenos publicados";
    texto = "Cuando el equipo publique terrenos, aparecerán aquí con su precio y ubicación. " +
      "Vuelve a cargar la página para ver lo más reciente.";
  } else {
    titulo = "El inventario está vacío";
    texto = "Agrega el primer terreno. Se guarda como borrador y no se publica.";
    accion = el("a", { class: "btn btn-principal", href: routeHash({ nombre: "nuevo" }) }, "Nuevo terreno");
  }

  return el("section", { class: "stage-mensaje", role: "status" },
    el("h2", {}, titulo),
    el("p", { class: "secondary" }, texto),
    accion,
  );
}

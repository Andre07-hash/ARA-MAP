/* The tables' map as the old map screen was laid out: filters on the left,
 * the map in the middle with its legend and basemaps over it, and the
 * selected terrain's read-only record on the right.
 *
 * It wraps the table's map (vistaPrevia.js) and keeps its contract: the table
 * hands it every terrain of the view and query (the set), and this narrows
 * that set with the map's OWN filters before drawing. Those filters are not
 * the table's query: they never reach the grid, its page or its cursors, and
 * "Limpiar" only clears them. reiniciar() drops them when the view, the scope
 * or the account changes. The terrain type is one of them (the table's own
 * type filter, when set, already bounds the set it hands over).
 *
 * The map takes the whole centre: no header strip above it. The "Filtros"
 * button (narrow screens) and the host's notices (avisos) float in its
 * top-left corner. The count of filtered terrains is the rail's, the placed /
 * not placed ones the legend's.
 *
 * The record is read-only. It shows the row as the table holds it now, the
 * live custom columns of the terrain's OWN base (the current base's, or, from
 * the master table, one request for the selected terrain's base, with stale
 * answers dropped) and the file summaries. Uploads, activation and retirement
 * stay in the table's own controls.
 */

import { el } from "../../lib/dom.js";
import { activeCount } from "../../lib/filters.js";
import { fmtCount, fmtPrice, fmtUnitPrice, plural } from "../../lib/format.js";
import {
  camposDeFicha, colorDeFila, conteoDeUbicacion, filaDeMapa, filtrarMapa, FILTROS_MAPA,
  personalizadasDeFicha, ubicacionDeFicha,
} from "../../lib/mapaTabla.js";
import { describirResumen } from "../archivos/resumen.js";
import { Section } from "../inventory/TerrainFacts.js";
import { Legend } from "../map/Legend.js";
import { createFilterRail } from "../terrain/FilterRail.js";
import { openFiltersDrawer } from "../terrain/FiltersDrawer.js";
import { createVistaPrevia } from "./vistaPrevia.js";

/* Rows are derived once per set the table hands over, not on every keystroke. */
const filasCache = new WeakMap();
function filasDe(registros) {
  if (!filasCache.has(registros)) filasCache.set(registros, registros.map(filaDeMapa));
  return filasCache.get(registros);
}

export function createMapaPaneles({
  cargador, onSeleccion, onDeseleccion, onError, nombreDeBase, definicionesDe,
}) {
  let vivo = true;
  let filtros = FILTROS_MAPA;
  let registros = [];             // the view's whole set, as the table holds it
  let resultado = filtrarMapa([]);
  // The selected terrain's custom columns: { id, baseId, estado, definiciones, control }.
  let columnas = null;
  let pedidoColumnas = 0;

  const previa = createVistaPrevia({
    cargador,
    onSeleccion: (id) => { pintarFicha(); onSeleccion?.(id); },
    onError,
  });

  const rail = createFilterRail({
    conIncidencias: false,
    conTipo: true,
    onChange: (cambio) => { filtros = { ...filtros, ...cambio }; aplicarFiltros(); },
    onReset: () => { filtros = FILTROS_MAPA; aplicarFiltros(); },
  });
  const railSlot = el("div", { class: "mapa-tabla-rail rail-slot" }, rail.element);
  const btnFiltros = el("button", {
    type: "button", id: "mapa-tabla-filtros", class: "btn btn-small filtros-btn", "aria-haspopup": "dialog",
    onclick: () => abrirFiltros(),
  }, "Filtros");
  let avisos = [];
  const pintarArriba = () => previa.arriba(btnFiltros, ...avisos);
  pintarArriba();
  const ficha = el("aside", {
    class: "mapa-tabla-ficha detail-slot", "aria-label": "Ficha del terreno", hidden: true,
  });
  const centro = el("div", { class: "mapa-tabla-centro" }, previa.element);
  const element = el("div", { class: "mapa-tabla" }, railSlot, centro, ficha);

  function abrirFiltros() {
    openFiltersDrawer({
      rail, slot: railSlot,
      onClosed: () => { btnFiltros.focus(); previa.mostrar(); },
    });
  }

  /* ------------------------------------------------------------- drawing */

  const filtrosActivos = () => activeCount(filtros);

  /**
   * Filter the set, draw what is kept, and patch the rail and the legend. A
   * selected terrain the filters now leave out loses its record and body, and
   * the table is told: the selection is one, shared with the grid.
   */
  function dibujar({ nuevaPagina }) {
    const antes = previa.seleccion;
    const filas = filasDe(registros);
    resultado = filtrarMapa(filas, filtros);
    const { visibles, monedas, breaks } = resultado;
    previa.pintar(visibles.map((f) => f.registro), {
      nuevaPagina, colorFor: (fila) => colorDeFila(fila, breaks),
    });
    rail.update({ terrenos: filas, filtros, visibles: visibles.length, monedas });
    const activos = filtrosActivos();
    btnFiltros.textContent = activos ? `Filtros (${activos})` : "Filtros";
    const { ubicados, sinUbicacion } = conteoDeUbicacion(visibles);
    previa.capas(Legend({
      modo: "precio", capas: [], breaks, monedas, conteo: ubicados, sinUbicacion,
      textos: {
        mezcla: "No se convierten entre monedas: los terrenos se muestran en gris.",
        sinUbicacion: `${plural(sinUbicacion, "terreno")} fuera del mapa: sin contorno activo ni X/Y válidas.`,
      },
    }));
    pintarFicha();
    // Only when the map's filters left it out; a set that no longer holds it is the table's to handle.
    if (antes && !previa.seleccion && registroDe(antes)) onDeseleccion?.(antes);
  }

  function aplicarFiltros() {
    if (vivo) dibujar({ nuevaPagina: false });
  }

  const visible = (id) => resultado.visibles.some((f) => f.id === id);

  /* -------------------------------------------------------------- record */

  const registroDe = (id) => registros.find((t) => t.id === id) ?? null;

  function soltarColumnas() {
    pedidoColumnas += 1;
    columnas?.control?.abort();
    columnas = null;
  }

  /** The custom columns of the terrain's own base: known, or asked for once. */
  function columnasDeFicha(registro) {
    const baseId = registro.base_id ?? null;
    // The current base's columns are the table's own, always as they are now.
    const conocidas = baseId ? definicionesDe?.(baseId, null) : [];
    if (Array.isArray(conocidas)) {
      if (columnas?.control) soltarColumnas();
      columnas = { id: registro.id, baseId, estado: "listo", definiciones: conocidas };
      return columnas;
    }
    if (columnas?.id === registro.id && columnas.baseId === baseId) return columnas;
    soltarColumnas();
    const control = new AbortController();
    const mio = ++pedidoColumnas;
    columnas = { id: registro.id, baseId, estado: "cargando", definiciones: [], control };
    Promise.resolve(definicionesDe?.(baseId, control.signal)).then((definiciones) => {
      if (!vivo || mio !== pedidoColumnas) return;
      columnas = { id: registro.id, baseId, estado: "listo", definiciones: definiciones ?? [] };
      pintarFicha();
    }, (error) => {
      if (!vivo || mio !== pedidoColumnas) return;
      // Still the selection's own request, yet dropped: forget it so the next paint asks again.
      if (error?.name === "AbortError") { columnas = null; return; }
      columnas = { id: registro.id, baseId, estado: "error", definiciones: [], mensaje: error?.message ?? "" };
      pintarFicha();
    });
    return columnas;
  }

  function cerrarFicha() {
    // Only the selection: the terrain's saved boundary is not touched.
    const id = previa.seleccion;
    previa.seleccionar(null);
    pintarFicha();
    if (id) onDeseleccion?.(id);
  }

  function pintarFicha() {
    if (!vivo) return;
    const registro = previa.seleccion ? registroDe(previa.seleccion) : null;
    if (!registro) {
      soltarColumnas();
      if (!ficha.hidden) {
        const teniaFoco = ficha.contains(document.activeElement);
        ficha.hidden = true;
        ficha.replaceChildren();
        element.classList.remove("con-ficha");
        if (teniaFoco) previa.element.querySelector(".previa-mapa")?.focus?.();
        previa.mostrar();
      }
      return;
    }
    const abierta = !ficha.hidden;
    const enFoco = ficha.contains(document.activeElement) ? document.activeElement.dataset.ficha : null;
    ficha.replaceChildren(Ficha(registro, columnasDeFicha(registro)));
    ficha.hidden = false;
    element.classList.add("con-ficha");
    if (enFoco) ficha.querySelector(`[data-ficha="${enFoco}"]`)?.focus();
    if (!abierta) previa.mostrar();          // the map is narrower now
  }

  function Ficha(registro, custom) {
    const d = registro.draft ?? {};
    const nombre = d.terreno || "Sin nombre";
    const lugar = [d.municipio, d.estado].filter(Boolean).join(", ");
    const ubicacion = ubicacionDeFicha(registro);
    const baseNombre = registro.base_id ? (nombreDeBase?.(registro.base_id) ?? "—") : "Sin asignar";
    const archivo = (tipo) => {
      const { texto, nota } = describirResumen(registro.archivos, tipo);
      return nota ? `${texto} · ${nota}` : texto;
    };
    let personalizadas;
    if (custom.estado === "cargando") personalizadas = el("p", { class: "muted" }, "Cargando las columnas de su base…");
    else if (custom.estado === "error") {
      personalizadas = el("p", { class: "field-error" },
        `No se pudieron cargar las columnas personalizadas de su base. ${custom.mensaje ?? ""}`.trim());
    } else {
      const filas = personalizadasDeFicha(registro, custom.definiciones);
      personalizadas = filas.length ? null
        : el("p", { class: "muted" }, registro.base_id ? "Su base no tiene columnas personalizadas." : "Sin base: no tiene columnas personalizadas.");
      if (filas.length) personalizadas = Section("Columnas personalizadas", filas);
    }

    return el("div", { class: "detail mapa-tabla-detalle", role: "region", "aria-label": `Ficha de ${nombre}` },
      el("header", { class: "detail-header" },
        el("div", { class: "detail-heading" },
          el("span", { class: "eyebrow" }, baseNombre),
          el("h2", {}, nombre),
          lugar && el("p", { class: "secondary" }, lugar),
        ),
        el("button", {
          type: "button", class: "icon-btn", "aria-label": "Cerrar detalle", dataset: { ficha: "cerrar" },
          onclick: () => cerrarFicha(),
        }, "×"),
      ),
      ubicacion.modo !== "ninguna" && el("button", {
        type: "button", class: "btn btn-quiet detail-escala", dataset: { ficha: "escala" },
        title: "Acerca el mapa hasta ver el terreno seleccionado a su tamaño real",
        onclick: () => previa.verAEscala(),
      }, "Ver a escala"),
      el("div", { class: "detail-lead" },
        el("div", {},
          el("span", { class: "eyebrow" }, "Asking price"),
          el("p", { class: "figure-lead" }, fmtPrice(d.asking_price, d.moneda)),
        ),
        el("div", { class: "detail-lead-sub" },
          el("span", { class: "eyebrow" }, "Asking $/m2"),
          el("p", { class: "figure-sub" }, fmtUnitPrice(d.asking_m2, d.moneda)),
        ),
      ),
      Section("Datos", camposDeFicha(registro)),
      el("section", { class: "detail-section" },
        el("h3", { class: "eyebrow" }, "Ubicación"),
        el("p", { class: "mapa-tabla-ubicacion" }, ubicacion.texto),
        el("dl", { class: "detail-grid" },
          el("dt", {}, "X (latitud)"), el("dd", { class: "figure mono" }, ubicacion.x),
          el("dt", {}, "Y (longitud)"), el("dd", { class: "figure mono" }, ubicacion.y),
        ),
      ),
      personalizadas,
      Section("Archivos", [["PDF", archivo("pdf")], ["KMZ", archivo("kmz")]]),
      el("p", { class: "detail-nota muted" },
        "Ficha de solo lectura. Para editar, subir, activar o retirar archivos usa la tabla."),
      el("footer", { class: "detail-footer muted" },
        `Última edición: ${registro.updated_by?.display_name ?? "—"} · versión ${fmtCount(registro.version)}`),
    );
  }

  return {
    element,
    /** The view's whole set (the table's rows). `nuevaPagina`: another view or query.
     * An incomplete set is the host's to say (its notices). */
    pintar(nuevos, { nuevaPagina = true } = {}) {
      if (!vivo) return;
      registros = nuevos;
      dibujar({ nuevaPagina });
    },
    /** The host's notices about the set (loading, errors, incomplete), over the map. */
    avisos(...nodos) { avisos = nodos.filter(Boolean); pintarArriba(); },
    seleccionar(id) {
      if (!vivo) return;
      // Chosen in the grid but left out by the map's filters: not selected here.
      if (id && registroDe(id) && !visible(id)) { previa.seleccionar(null); pintarFicha(); onDeseleccion?.(id); return; }
      previa.seleccionar(id);
      pintarFicha();
    },
    get seleccion() { return previa.seleccion; },
    get estado() { return { ...previa.estado, filtros: filtrosActivos(), ficha: ficha.hidden ? null : previa.seleccion }; },
    mostrar() { previa.mostrar(); },
    posicionDe: (id) => previa.posicionDe(id),
    /** Another view, scope or account: the map's own filters start empty. */
    reiniciar() {
      filtros = FILTROS_MAPA;
      // The rail never overwrites the box being typed in: let go of it first.
      if (rail.element.contains(document.activeElement)) document.activeElement.blur();
      soltarColumnas();
      rail.element.closest("dialog")?.close();
    },
    destroy() {
      if (!vivo) return;
      vivo = false;
      soltarColumnas();
      rail.element.closest("dialog")?.close();
      rail.destroy();
      previa.destroy();
      element.remove();
    },
  };
}

/* The table's map: the "Mapa" side of Tabla / Mapa (Round 3, INTERFACES §5).
 *
 * It draws the rows it is handed (the table gives it every terrain of the
 * view and its filters, gathered page by page): their active boundary
 * descriptors and valid X/Y. It never fetches rows itself. One boundary body
 * is loaded at a time, for the selected terrain, through Team B's loader, and
 * handed to the unchanged renderer as `geometrias` (at most one entry). Every
 * other boundary stays at its descriptor's interior point with the renderer's
 * "outline not loaded" symbol. Rows with neither are counted here as without
 * location, never placed.
 *
 * The body, the selection and the map belong to one set of one scope:
 * pintar() with a new set drops the body and any load in flight, and
 * destroy() removes the map itself.
 *
 * The host decides the marks' colour (`colorFor`) and what floats over the
 * map beside the basemap selector (`capas`, e.g. the price legend) and in its
 * top-left corner (`arriba`, e.g. the filters button and the set's notices).
 * "Ver a escala" is the host's to offer, next to the selected terrain's record.
 *
 * Nothing takes a strip of its own above or below the map: the boundary
 * status and its retry float in the top-left corner only while there is
 * something to say, "Encuadrar todo" and the explanation (behind a small
 * info toggle) float beside the zoom control. The counts are the host's
 * (its filters and legend).
 */

import { el } from "../../lib/dom.js";
import { ubicacionDe } from "../../lib/geometria.js";
import { itemDeInventario } from "../../lib/inventario.js";
import { createMapCanvas } from "../map/MapCanvas.js";
import { BasemapSwitcher } from "../map/BasemapSwitcher.js";

const COLOR = "#1f6feb";

export function createVistaPrevia({ cargador = () => null, onSeleccion, onError, colorFor = () => COLOR } = {}) {
  let vivo = true;
  let canvas = null;
  let basemap = "claro";
  let filas = [];                 // renderer rows of the page
  let seleccion = null;           // terrain id
  let geometrias = new Map();     // at most one loaded body, by geometry id
  let carga = null;               // { id, control } of the load in flight
  let pedido = 0;
  let encuadrar = false;
  let fallida = null;             // geometry id whose last load failed: not retried on a repaint
  let colorear = colorFor;        // renderer row -> fill colour

  // The live region stays in the page while empty, so what it says next is announced.
  const estado = el("p", { class: "previa-estado", role: "status", "aria-live": "polite" });
  const reintentar = el("button", {
    type: "button", class: "btn btn-quiet btn-small previa-reintentar", hidden: true,
    onclick: () => { if (seleccion) cargarContorno(seleccion); },
  }, "Reintentar");
  const encuadre = el("button", {
    type: "button", class: "btn btn-small previa-encuadre", onclick: () => encuadrarTodo(),
    title: "Encuadrar todos los terrenos que el mapa muestra",
  }, "Encuadrar todo");
  const info = el("details", { class: "previa-info" },
    el("summary", { "aria-label": "Cómo funciona este mapa", title: "Cómo funciona este mapa" }, "i"),
    el("p", { class: "previa-nota", tabindex: "-1" },
      "Muestra todos los terrenos de esta vista con los filtros actuales, no sólo la página de la tabla. " +
      "El contorno activo de un terreno se carga al seleccionarlo; los demás se muestran como un símbolo " +
      "en su punto interior. Un KMZ subido sin activar no cambia el mapa."));
  info.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && info.open) { e.stopPropagation(); info.open = false; info.querySelector("summary").focus(); }
  });
  info.addEventListener("focusout", (e) => { if (!info.contains(e.relatedTarget)) info.open = false; });
  const lienzo = el("div", { class: "previa-mapa", role: "application", "aria-label": "Mapa de los terrenos de la vista" });
  const fondos = el("div", { class: "previa-fondos" });
  const capas = el("div", { class: "previa-capas" });
  const sobreMapa = el("div", { class: "previa-sobre-mapa" }, capas, fondos);
  const delAnfitrion = el("div", { class: "previa-anfitrion" });
  const arriba = el("div", { class: "previa-arriba" }, delAnfitrion,
    el("div", { class: "previa-aviso" }, estado, reintentar));
  const herramientas = el("div", { class: "previa-herramientas" }, encuadre, info);
  function pintarFondos() {
    fondos.replaceChildren(BasemapSwitcher({
      activo: basemap,
      onChange: (key) => {
        basemap = key;
        canvas?.setBasemap(key);
        pintarFondos();
        fondos.querySelector('[aria-checked="true"]')?.focus();
      },
    }));
  }
  pintarFondos();
  const element = el("section", { class: "previa", "aria-label": "Mapa de la vista" },
    el("div", { class: "previa-escenario" }, lienzo, arriba, herramientas, sobreMapa));

  const filaDe = (id) => filas.find((f) => f.id === id) ?? null;
  const decir = (texto, conReintento = false) => {
    estado.textContent = texto;
    reintentar.hidden = !conReintento;
  };

  function soltarCarga() {
    pedido += 1;
    carga?.control.abort();
    carga = null;
  }

  /** Forget the loaded body and whatever was loading. */
  function soltarCuerpo() {
    soltarCarga();
    geometrias = new Map();
    cargador()?.reset?.();
  }

  function dibujar() {
    if (!vivo) return;
    if (!canvas) {
      // Only once it is on screen: Leaflet cannot measure a hidden container.
      if (!lienzo.isConnected || lienzo.offsetParent === null || typeof L === "undefined") return;
      canvas = createMapCanvas(lienzo, {
        onSelect: (id) => { seleccionar(id, { desdeMapa: true }); },
        onDoubleSelect: (id) => { canvas.zoomToScale(id); },
      });
      canvas.setBasemap(basemap);
      encuadrar = true;
    }
    canvas.invalidate();
    canvas.render(filas, { colorFor: colorear, geometrias });
    if (encuadrar) { canvas.fitTo(filas); encuadrar = false; }
    canvas.select(seleccion);
  }

  /** Frame every row; like encuadrarSeleccion, it waits for a zoom step that is running. */
  function encuadrarTodo() {
    if (!canvas) return;
    const { map } = canvas;
    const ir = () => { if (vivo && canvas) canvas.fitTo(filas); };
    if (map._animatingZoom) map.once("zoomend", ir); else ir();
  }

  /**
   * Frame the selected terrain. Leaflet silently ignores a view change asked
   * for while a zoom animation is running (a framing that just started, a
   * selection made a moment ago), so the request waits for that step to end.
   */
  function encuadrarSeleccion() {
    if (!canvas || !seleccion) return;
    const { map } = canvas;
    const id = seleccion;
    const ir = () => { if (vivo && canvas && seleccion === id) canvas.select(id, { pan: true }); };
    if (map._animatingZoom) map.once("zoomend", ir); else ir();
  }

  /**
   * Show a set of records (the table's own row objects). `nuevaPagina` says
   * the set is a different one (another view or query): the body and the
   * framing start over. Otherwise the selection is kept if that terrain is
   * still there with the same boundary.
   */
  function pintar(registros, { nuevaPagina = true, colorFor: color = null } = {}) {
    if (!vivo) return;
    if (color) colorear = color;
    const antes = filaDe(seleccion)?.geometria?.id ?? null;
    filas = registros.map(itemDeInventario);
    const actual = filaDe(seleccion);
    if (!actual) seleccion = null;
    if (nuevaPagina || !actual || (actual.geometria?.id ?? null) !== antes) soltarCuerpo();
    if (nuevaPagina) encuadrar = true;
    dibujar();
    if (seleccion && actual?.geometria && !geometrias.size && !carga && actual.geometria.id !== fallida) {
      cargarContorno(seleccion);
    } else if (seleccion && actual?.geometria && actual.geometria.id === fallida && !geometrias.size) {
      decir("No se pudo cargar el contorno; el terreno se muestra en su punto interior.", true);
    }
    else if (!seleccion) decir("");
  }

  function seleccionar(id, { desdeMapa = false, mover = true } = {}) {
    if (!vivo) return;
    const fila = filaDe(id);
    if (id === seleccion && (carga || geometrias.size || !fila?.geometria)) {
      if (desdeMapa) onSeleccion?.(id);
      return;
    }
    seleccion = fila ? id : null;
    fallida = null;
    soltarCuerpo();
    if (desdeMapa && seleccion) onSeleccion?.(seleccion);
    if (!fila) { canvas?.select(null); decir(""); return; }
    const { modo } = ubicacionDe(fila);
    dibujar();
    if (modo === "ninguna") {
      decir("Este terreno no tiene ubicación: se cuenta como sin ubicación y no se dibuja en el mapa.");
      return;
    }
    if (mover) encuadrarSeleccion();
    if (modo === "geometria") cargarContorno(seleccion);
    else decir("Ubicado por sus coordenadas X/Y; no tiene contorno activo.");
  }

  async function cargarContorno(id) {
    const fila = filaDe(id);
    if (!vivo || !fila?.geometria) return;
    soltarCarga();
    const origen = cargador();
    if (!origen) {
      decir("El contorno no se puede cargar: el módulo de contornos no está disponible. " +
        "El terreno se muestra en su punto interior.", true);
      return;
    }
    const control = new AbortController();
    const mio = ++pedido;
    carga = { id, control };
    fallida = null;
    decir("Cargando el contorno del terreno seleccionado…");
    try {
      const cuerpo = await origen.cargar({ terrenoId: id, geometria: fila.geometria }, { signal: control.signal });
      if (!vivo || mio !== pedido) return;
      carga = null;
      geometrias = new Map([[fila.geometria.id, cuerpo]]);
      dibujar();
      encuadrarSeleccion();
      decir("Contorno activo cargado. Los demás contornos se cargan al seleccionarlos.");
    } catch (error) {
      if (!vivo || mio !== pedido) return;        // superseded, or the scope ended
      carga = null;
      if (error?.name === "AbortError") return;
      // Not retried by the next repaint: only by "Reintentar", another
      // selection, or a different active boundary after the host revalidates.
      fallida = fila.geometria.id;
      decir("No se pudo cargar el contorno; el terreno se muestra en su punto interior." +
        (error?.message ? ` ${error.message}` : ""), true);
      onError?.({ id, codigo: String(error?.codigo ?? error?.status ?? ""), mensaje: String(error?.message ?? "") });
    }
  }

  return {
    element,
    pintar,
    seleccionar,
    get seleccion() { return seleccion; },
    /** Zoom until the selected terrain is shown at its real size. */
    verAEscala() { if (seleccion) canvas?.zoomToScale(seleccion); },
    /** What floats over the map beside the basemap selector (the legend). */
    capas(...nodos) { capas.replaceChildren(...nodos.filter(Boolean)); },
    /** What floats in the map's top-left corner, above the boundary status. */
    arriba(...nodos) { delAnfitrion.replaceChildren(...nodos.filter(Boolean)); },
    /** For checks: how many boundary bodies are held (0 or 1) and loading. */
    get estado() { return { cuerpos: geometrias.size, cargando: Boolean(carga), filas: filas.length, zoom: canvas?.map.getZoom() ?? null }; },
    /** The panel became visible or changed size. */
    mostrar() { requestAnimationFrame(() => dibujar()); },
    posicionDe: (id) => canvas?.posicionDe(id) ?? null,
    destroy() {
      if (!vivo) return;
      vivo = false;
      soltarCuerpo();
      filas = [];
      seleccion = null;
      element.remove();
      if (canvas) {
        const { map } = canvas;
        canvas.render([], { colorFor: () => COLOR });   // every row and outline goes now
        canvas = null;
        // Leaflet finishes a zoom animation on a timer that map.remove() does
        // not cancel and that then reads panes it has deleted. And a
        // synchronous canvas redraw (a fitBounds, for instance) forgets the
        // handle of a redraw already queued for the next frame, so
        // map.remove() cannot cancel that one either: it would then draw on a
        // removed canvas. The map is already empty and off the page; it is
        // removed after the next frame, and after the zoom step if one runs.
        const quitar = () => { try { map.remove(); } catch { /* already gone */ } };
        const trasElCuadro = () => requestAnimationFrame(quitar);
        if (map._animatingZoom) map.once("moveend", trasElCuadro); else trasElCuadro();
      }
    },
  };
}

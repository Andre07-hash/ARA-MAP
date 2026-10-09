/* The map preview of the table's CURRENT PAGE (Round 3, INTERFACES §5).
 *
 * It draws only the rows the table is showing: their active boundary
 * descriptors and valid X/Y. It never asks for another page. One boundary
 * body is loaded at a time, for the selected terrain, through Team B's loader,
 * and handed to the unchanged renderer as `geometrias` (at most one entry).
 * Every other boundary stays at its descriptor's interior point with the
 * renderer's "outline not loaded" symbol. Rows with neither stay in the table
 * and are counted here, never placed.
 *
 * The body, the selection and the map belong to one page of one scope:
 * pintar() with a new page drops the body and any load in flight, and
 * destroy() removes the map itself.
 */

import { el } from "../../lib/dom.js";
import { fmtCount } from "../../lib/format.js";
import { ubicacionDe } from "../../lib/geometria.js";
import { itemDeInventario } from "../../lib/inventario.js";
import { createMapCanvas } from "../map/MapCanvas.js";

const COLOR = "#1f6feb";
const BASEMAP = "claro";

export function createVistaPrevia({ cargador = () => null, onSeleccion, onError } = {}) {
  let vivo = true;
  let canvas = null;
  let filas = [];                 // renderer rows of the page
  let seleccion = null;           // terrain id
  let geometrias = new Map();     // at most one loaded body, by geometry id
  let carga = null;               // { id, control } of the load in flight
  let pedido = 0;
  let encuadrar = false;

  const titulo = el("h2", { class: "previa-titulo" }, "Mapa de esta página");
  const cuenta = el("p", { class: "previa-cuenta" });
  const nota = el("p", { class: "previa-nota" },
    "Sólo se dibujan las filas de la página actual de la tabla. El contorno de un terreno se " +
    "carga al seleccionarlo; los demás se muestran como un símbolo en su punto interior.");
  const estado = el("p", { class: "previa-estado", role: "status", "aria-live": "polite" });
  const reintentar = el("button", {
    type: "button", class: "btn btn-quiet previa-reintentar", hidden: true,
    onclick: () => { if (seleccion) cargarContorno(seleccion); },
  }, "Reintentar");
  const escala = el("button", {
    type: "button", class: "btn btn-quiet", disabled: true,
    title: "Acerca el mapa hasta ver el terreno seleccionado a su tamaño real",
    onclick: () => { if (seleccion) canvas?.zoomToScale(seleccion); },
  }, "Ver a escala");
  const encuadre = el("button", {
    type: "button", class: "btn btn-quiet", onclick: () => canvas?.fitTo(filas),
  }, "Encuadrar página");
  const lienzo = el("div", { class: "previa-mapa", role: "application", "aria-label": "Mapa de la página actual" });
  const element = el("section", { class: "previa", "aria-labelledby": "previa-titulo" },
    el("header", { class: "previa-cabecera" }, Object.assign(titulo, { id: "previa-titulo" }), cuenta),
    nota, lienzo,
    el("div", { class: "previa-pie" }, estado, reintentar, escala, encuadre));

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
      canvas.setBasemap(BASEMAP);
      encuadrar = true;
    }
    canvas.invalidate();
    canvas.render(filas, { colorFor: () => COLOR, geometrias });
    if (encuadrar) { canvas.fitTo(filas); encuadrar = false; }
    canvas.select(seleccion);
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
   * Show a page of records (the table's own row objects). The selection is
   * kept only if that terrain is still on the page with the same boundary.
   */
  function pintar(registros, { total = 0, nuevaPagina = true } = {}) {
    if (!vivo) return;
    const antes = filaDe(seleccion)?.geometria?.id ?? null;
    filas = registros.map(itemDeInventario);
    const actual = filaDe(seleccion);
    if (!actual) seleccion = null;
    if (nuevaPagina || !actual || (actual.geometria?.id ?? null) !== antes) soltarCuerpo();
    if (nuevaPagina) encuadrar = true;
    const ubicadas = filas.filter((f) => ubicacionDe(f).ubicado).length;
    const contornos = filas.filter((f) => ubicacionDe(f).modo === "geometria").length;
    cuenta.textContent = filas.length
      ? `${fmtCount(ubicadas)} de ${fmtCount(filas.length)} filas de esta página con ubicación ` +
        `(${fmtCount(contornos)} con contorno, ${fmtCount(filas.length - ubicadas)} sin ubicar)` +
        (total > filas.length ? ` · la vista tiene ${fmtCount(total)} terrenos en total` : "")
      : "Esta página no tiene filas.";
    escala.disabled = !seleccion;
    dibujar();
    if (seleccion && actual?.geometria && !geometrias.size && !carga) cargarContorno(seleccion);
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
    soltarCuerpo();
    escala.disabled = !seleccion;
    if (desdeMapa && seleccion) onSeleccion?.(seleccion);
    if (!fila) { canvas?.select(null); decir(""); return; }
    const { modo } = ubicacionDe(fila);
    dibujar();
    if (modo === "ninguna") {
      decir("Este terreno no tiene ubicación: sigue en la tabla y no se dibuja en el mapa.");
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
    decir("Cargando el contorno del terreno seleccionado…");
    try {
      const cuerpo = await origen.cargar({ terrenoId: id, geometria: fila.geometria }, { signal: control.signal });
      if (!vivo || mio !== pedido) return;
      carga = null;
      geometrias = new Map([[fila.geometria.id, cuerpo]]);
      dibujar();
      encuadrarSeleccion();
      decir("Contorno cargado. Los demás contornos de la página se cargan al seleccionarlos.");
    } catch (error) {
      if (!vivo || mio !== pedido) return;        // superseded, or the scope ended
      carga = null;
      if (error?.name === "AbortError") return;
      decir("No se pudo cargar el contorno; el terreno se muestra en su punto interior.", true);
      onError?.({ id, codigo: String(error?.codigo ?? error?.status ?? ""), mensaje: String(error?.message ?? "") });
    }
  }

  return {
    element,
    pintar,
    seleccionar,
    get seleccion() { return seleccion; },
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
        // not cancel and that then reads panes it has deleted. The map is
        // already empty and off the page; it is removed when that step ends.
        const quitar = () => { try { map.remove(); } catch { /* already gone */ } };
        if (map._animatingZoom) map.once("moveend", quitar); else quitar();
      }
    },
  };
}

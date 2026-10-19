/* The compact file cell of the table, for one terrain and one kind (pdf | kmz).
 *
 * It shows the caller-aware summary as before and, when the row may be
 * changed, an "Elegir PDF…" / "Elegir KMZ o KML…" button that runs the same upload
 * as the record detail (subida.js, with the factory's shared client, pipeline
 * turn and count of unfinished uploads). The cell never fetches on its own:
 * once the server has the upload it tells the host (onCambio), which hands
 * back the fresh summary through update().
 *
 * When a KMZ/KML holds several contours, the cell lists them right away and
 * activates the one chosen (elegirContorno.js); a file uploaded earlier gets
 * the same list from "Elegir contorno…". Versions, history and retirement
 * stay in the detail. Choosing a file here activates nothing the detail
 * would not.
 *
 * Reading (issue #48). A PDF cell whose summary names saved PDFs turns its
 * count into a link: "1 PDF" opens that saved version in a new tab; a larger
 * count opens a small chooser of the terrain's saved PDFs, and a summary that
 * lists only the most recent attachments asks the authorized list, page by
 * page, when the chooser opens. Uploads that never finished, expired or were
 * refused are not offered; a saved version whose newer upload failed is.
 * Opening uses the detail's own flow (abrirPdf.js) and does not depend on the
 * right to write. The chooser, the list and a download in flight end when the
 * cell is destroyed or the chooser closes; late answers are dropped.
 *
 * Its controls live inside a table cell that edits on double click and on
 * keys. Their clicks and keys stop here, so they never reach the row.
 */

import { el } from "../../lib/dom.js";
import { crearSubida, FASE, esTerminal } from "./subida.js";
import { describirResumen, ESTADO, pdfsDelResumen, opcionPdf } from "./resumen.js";
import { candidatosDe, intentoPorElegir, montarSelectorContornos } from "./elegirContorno.js";
import { EN_PROGRESO, FASE_TEXTO } from "./detalle.js";
import {
  abrirPdf, enlaceDeRespaldo, MENSAJE_BLOQUEADO, MENSAJE_CERRADA, reservarPestana, VIDA_URL_MS,
} from "./abrirPdf.js";
import { ErrorArchivos, LIMITE_PAGINA } from "../../lib/archivos.js";

const ETIQUETA = { pdf: "Archivos PDF o JPG", kmz: "KMZ / KML" };

/* What a cell can say in a few words after the upload; the full message goes in the title. */
const NOTA_CORTA = {
  [FASE.REQUIERE_SELECCION]: "Varios contornos: elige cuál es el del terreno.",
};

const esAbort = (e) => e?.name === "AbortError";
const nombreDe = (o) => o.nombre ?? "Archivo guardado (versión anterior)";

export function montarCelda({ container, terrenoId, tipo, soloLectura, resumen, onCambio, onError }, ctx) {
  let vivo = true;
  let fuera = false;            // the terrain left this account's scope
  let solo = Boolean(soloLectura);
  let subida = null;            // the cell's last upload, until a new one replaces it
  let cambioPendiente = false;
  // The picker is open: coming back from it gives the window focus (which may
  // reload the table) before the chosen file arrives. Until then this cell is
  // busy too, so a repaint keeps it instead of dropping the choice.
  let eligiendo = false;
  // Reading (PDF only): the summary last shown, its link, an opening in
  // flight (its AbortController) and the chooser with its list request.
  let ultimoResumen = resumen;
  let abriendo = null;
  let selector = null, listaOpciones = null, estadoSelector = null, masOpciones = null;
  let listado = null;
  let cursorOpciones = null;
  let ocultasOpciones = 0;
  let avisoTimer = null;
  // KMZ: the contour chooser shown in the cell ({versionId, selector}) and a
  // request for an earlier upload's candidates in flight.
  let eleccion = null;
  let buscandoContornos = null;

  const texto = el("span", { class: "archivos-celda", dataset: { tipo } });
  const enlace = el("button", { type: "button", class: "archivos-celda-abrir",
    onclick: () => (enlace.dataset.modo === "directo" ? abrirDirecto() : alternarSelector()) });
  const entrada = el("input", { type: "file", class: "archivos-entrada", tabindex: "-1", "aria-hidden": "true",
    accept: tipo === "pdf" ? ".pdf,.jpg,.jpeg,application/pdf,image/jpeg" : ".kmz,.kml" });
  const elegir = el("button", { type: "button", class: "btn btn-quiet btn-small archivos-celda-elegir" },
    tipo === "pdf" ? "Elegir PDF o JPG…" : "Elegir KMZ o KML…");
  const progreso = el("span", { class: "archivos-celda-subida", role: "status", "aria-live": "polite" });
  const aviso = el("span", { class: "archivos-celda-aviso", role: "status", "aria-live": "polite", hidden: true });
  const elegirContorno = el("button", { type: "button", class: "btn btn-quiet btn-small archivos-celda-elegir-contorno",
    hidden: true, onclick: () => buscarContornos() }, "Elegir contorno…");
  const contornos = el("span", { class: "archivos-celda-contornos-caja" });
  const raiz = el("span", { class: "archivos-celda-caja", dataset: { tipo } },
    el("span", { class: "archivos-celda-linea" }, texto, elegir), entrada, progreso, elegirContorno, contornos, aviso);
  container.replaceChildren(raiz);

  // A cell edits on double click and on Enter, F2 or a typed key; the row
  // selects on click. None of that belongs to these controls.
  for (const evento of ["click", "dblclick", "keydown"]) {
    raiz.addEventListener(evento, (e) => { if (e.target !== texto) e.stopPropagation(); });
  }

  function notificarCambio() {
    if (!vivo || cambioPendiente) return;
    cambioPendiente = true;
    queueMicrotask(() => {
      cambioPendiente = false;
      if (vivo) onCambio?.({ terrenoId });
    });
  }

  /* As in the detail: a 404 means the terrain left this account's scope; a
   * 403 or an archive means only the right to write was lost. */
  function accesoPerdido(error) {
    if (!vivo || fuera) return;
    if (error.status === 404) {
      fuera = true;
      subida?.abortar();
      detenerLectura();
      pintarResumen(ultimoResumen);
      onError?.({ codigo: "no_encontrado", mensaje: "El archivo ya no está disponible." });
    } else {
      onError?.({ codigo: error.codigo, mensaje: error.message });
    }
    notificarCambio();
    pintar();
  }

  function pintarResumen(r) {
    ultimoResumen = r;
    const d = describirResumen(r, tipo);
    texto.dataset.estado = d.estado;
    const titulo = d.nota ? `${ETIQUETA[tipo]}: ${d.texto}. ${d.nota}.` : `${ETIQUETA[tipo]}: ${d.texto}`;
    texto.title = titulo;
    const modo = modoApertura(r);
    if (modo !== "lista") cerrarSelector({ enfocar: false });
    if (!modo) {
      // Nothing to open: plain text, never something that looks like a link.
      texto.textContent = d.texto;
      texto.setAttribute("aria-label", titulo);
      return;
    }
    // The same button across repaints, so a refreshed summary keeps its focus.
    enlace.dataset.modo = modo;
    enlace.textContent = d.texto;
    enlace.title = modo === "directo" ? "Abrir el archivo en una pestaña nueva"
      : "Elegir un archivo para abrirlo en una pestaña nueva";
    enlace.setAttribute("aria-label", `${titulo}. ${enlace.title}`);
    if (modo === "lista") {
      enlace.setAttribute("aria-haspopup", "dialog");
      enlace.setAttribute("aria-expanded", String(Boolean(selector)));
    } else {
      enlace.removeAttribute("aria-haspopup");
      enlace.removeAttribute("aria-expanded");
    }
    texto.removeAttribute("aria-label");
    if (texto.firstChild !== enlace || texto.childNodes.length !== 1) texto.replaceChildren(enlace);
  }

  /* "directo" (one saved PDF the summary names with certainty), "lista"
   * (several, or a summary that lists only the most recent) or null (no saved
   * PDF, nothing known yet, or the terrain left this account's scope). */
  function modoApertura(r) {
    if (tipo !== "pdf" || fuera) return null;
    const g = pdfsDelResumen(r);
    if (!g || g.opciones.length === 0 && g.completo) return null;
    return g.completo && g.opciones.length === 1 ? "directo" : "lista";
  }

  /* ------------------------------------------------------------ reading */

  /* A message under the summary: an opening in progress, its error, or the
   * link offered when the browser refused the tab. */
  function avisar(textoAviso, { tipoAviso = "info", respaldo = null } = {}) {
    clearTimeout(avisoTimer);
    aviso.dataset.tipo = tipoAviso;
    aviso.replaceChildren(...[textoAviso, respaldo].filter(Boolean));
    aviso.hidden = !textoAviso && !respaldo;
    if (respaldo) avisoTimer = setTimeout(() => { if (vivo) avisar(""); }, VIDA_URL_MS);
  }

  function marcarAbriendo(valor) {
    abriendo = valor;
    if (valor) enlace.setAttribute("aria-busy", "true"); else enlace.removeAttribute("aria-busy");
    // aria-disabled, not disabled: a disabled button drops the focus, and the
    // chooser must still take Escape while its choice downloads (abrir() ignores clicks).
    for (const b of selector?.querySelectorAll(".archivos-opcion") ?? []) {
      if (valor) b.setAttribute("aria-disabled", "true"); else b.removeAttribute("aria-disabled");
    }
  }

  /* A 404 on one version may only mean someone deleted that file: only a 404
   * from the terrain's own list says the terrain left this account's scope. */
  async function revalidar(signal) {
    try {
      await ctx.cliente.listar(terrenoId, { limite: 1, signal });
    } catch (error) {
      if (esAbort(error)) return;
      if (error instanceof ErrorArchivos && error.status === 404) { accesoPerdido(error); return; }
    }
    if (!vivo || fuera) return;
    avisar("Ese archivo ya no existe; alguien lo borró. La información se actualizó.", { tipoAviso: "error" });
    notificarCambio();
    if (selector) cargarOpciones({ reiniciar: true });
  }

  /* Open one saved version. The tab is reserved here, in the gesture. */
  async function abrir(versionId) {
    if (!vivo || fuera || abriendo || !ctx.vivo()) return;
    const pestana = reservarPestana();
    const control = new AbortController();
    marcarAbriendo(control);
    avisar("Abriendo el archivo…");
    try {
      const r = await abrirPdf({ cliente: ctx.cliente, versionId, pestana, signal: control.signal, urls: ctx.urls });
      if (!vivo || abriendo !== control) return;
      if (r.abierta) {
        marcarAbriendo(null);          // done: closing the chooser now cancels nothing
        avisar("");
        cerrarSelector();
      }
      else {
        avisar(`${r.cerrada ? MENSAJE_CERRADA : MENSAJE_BLOQUEADO} `,
          { tipoAviso: r.cerrada ? "info" : "error", respaldo: enlaceDeRespaldo(r.url) });
      }
    } catch (error) {
      if (!vivo || abriendo !== control || esAbort(error)) return;
      // Still this opening's: destroying the cell cancels the check too.
      if (error instanceof ErrorArchivos && error.status === 404) { await revalidar(control.signal); return; }
      avisar(`No se pudo abrir el archivo: ${error?.message ?? "error"}`, { tipoAviso: "error" });
      if (error instanceof ErrorArchivos && (error.status === 403 || error.status === 401)) notificarCambio();
    } finally {
      if (abriendo === control) marcarAbriendo(null);
    }
  }

  function abrirDirecto() {
    const unica = pdfsDelResumen(ultimoResumen)?.opciones;
    if (unica?.length === 1) abrir(unica[0].versionId);
  }

  /* ----------------------------------------------------------- chooser */

  function alternarSelector() {
    if (selector) cerrarSelector();
    else abrirSelector();
  }

  function abrirSelector() {
    if (!vivo || fuera || selector) return;
    listaOpciones = el("ul", { class: "archivos-opciones" });
    estadoSelector = el("p", { class: "archivos-opciones-estado", role: "status", "aria-live": "polite" });
    masOpciones = el("button", { type: "button", class: "btn btn-quiet btn-small", hidden: true,
      onclick: () => cargarOpciones() }, "Cargar más");
    selector = el("div", { class: "archivos-selector", role: "dialog", "aria-label": "Archivos guardados de este terreno" },
      el("div", { class: "archivos-selector-cabecera" },
        el("strong", {}, "Archivos guardados"),
        el("button", { type: "button", class: "btn btn-quiet btn-small", "aria-label": "Cerrar la lista de archivos",
          onclick: () => cerrarSelector() }, "Cerrar")),
      listaOpciones, estadoSelector, masOpciones);
    selector.addEventListener("keydown", teclaSelector);
    selector.addEventListener("focusout", (e) => {
      // Tab or a click elsewhere in the page; leaving the window keeps it open.
      if (e.relatedTarget && selector && !selector.contains(e.relatedTarget) && e.relatedTarget !== enlace) {
        cerrarSelector({ enfocar: false });
      }
    });
    document.body.append(selector);
    document.addEventListener("pointerdown", fueraDelSelector, true);
    window.addEventListener("resize", colocarSelector);
    window.addEventListener("scroll", colocarSelector, true);
    enlace.setAttribute("aria-expanded", "true");
    colocarSelector();
    const g = pdfsDelResumen(ultimoResumen);
    if (g?.completo) {
      pintarOpciones(g.opciones, { reiniciar: true, ocultas: ultimoResumen.pdf_recientes.length - g.opciones.length });
    } else cargarOpciones({ reiniciar: true });
    enfocarOpcion(0);
  }

  /* Closing the chooser (Escape, «Cerrar», a click outside, a repaint) also
   * cancels an opening chosen from it: its reserved tab closes and the PDF
   * never arrives after the person dismissed the list. */
  function cerrarSelector({ enfocar = true } = {}) {
    if (!selector) return;
    listado?.abort();
    listado = null;
    if (abriendo) {
      abriendo.abort();
      marcarAbriendo(null);
      avisar("");
    }
    document.removeEventListener("pointerdown", fueraDelSelector, true);
    window.removeEventListener("resize", colocarSelector);
    window.removeEventListener("scroll", colocarSelector, true);
    const tenia = selector.contains(document.activeElement);
    selector.remove();
    selector = listaOpciones = estadoSelector = masOpciones = null;
    cursorOpciones = null;
    ocultasOpciones = 0;
    if (enlace.hasAttribute("aria-expanded")) enlace.setAttribute("aria-expanded", "false");
    if (enfocar && tenia && enlace.isConnected) enlace.focus();
  }

  function fueraDelSelector(e) {
    if (selector && !selector.contains(e.target) && e.target !== enlace) cerrarSelector({ enfocar: false });
  }

  /* Fixed by the link, inside the window: a table cell clips what overflows
   * it. Below the link when it fits, else on the side with more room; its
   * height never passes the window's edge (the list scrolls instead). */
  function colocarSelector() {
    if (!selector) return;
    const ancla = (enlace.isConnected ? enlace : texto).getBoundingClientRect();
    const ancho = Math.min(360, window.innerWidth - 16);
    selector.style.width = `${ancho}px`;
    selector.style.left = `${Math.max(8, Math.min(ancla.left, window.innerWidth - ancho - 8))}px`;
    const abajo = window.innerHeight - ancla.bottom - 12;
    const arriba = ancla.top - 12;
    selector.style.setProperty("--archivos-alto-libre", "none");
    const alto = selector.offsetHeight;
    const debajo = alto <= abajo || abajo >= arriba;
    const libre = Math.max(96, debajo ? abajo : arriba);
    selector.style.setProperty("--archivos-alto-libre", `${libre}px`);
    selector.style.top = debajo ? `${ancla.bottom + 4}px` : `${Math.max(8, ancla.top - 4 - Math.min(alto, libre))}px`;
  }

  function teclaSelector(e) {
    e.stopPropagation();
    if (e.key === "Escape") { e.preventDefault(); cerrarSelector(); return; }
    const opciones = [...selector.querySelectorAll(".archivos-opcion")];
    const i = opciones.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!opciones.length) return;
      const paso = e.key === "ArrowDown" ? 1 : -1;
      opciones[(i + paso + opciones.length) % opciones.length].focus();
    }
  }

  function enfocarOpcion(i) {
    const opciones = selector?.querySelectorAll(".archivos-opcion");
    (opciones?.[i] ?? selector?.querySelector("button"))?.focus();
  }

  function pintarOpciones(opciones, { reiniciar = false, ocultas = 0 } = {}) {
    if (reiniciar) { listaOpciones.replaceChildren(); ocultasOpciones = 0; }
    ocultasOpciones += Math.max(0, ocultas);
    for (const o of opciones) {
      const b = el("button", { type: "button", class: "archivos-opcion", "aria-disabled": abriendo ? "true" : null,
        onclick: () => abrir(o.versionId) },
      el("span", { class: "archivos-opcion-nombre" }, nombreDe(o)),
      o.nota ? el("span", { class: "archivos-opcion-nota" }, o.nota) : null);
      b.title = o.nota ? `${nombreDe(o)}. ${o.nota}` : nombreDe(o);
      listaOpciones.append(el("li", {}, b));
    }
    const n = listaOpciones.children.length;
    const partes = [];
    if (!n && cursorOpciones == null) partes.push("Este terreno no tiene un archivo guardado que se pueda abrir.");
    if (ocultasOpciones) {
      partes.push(ocultasOpciones === 1 ? "1 adjunto sin archivo guardado no se muestra."
        : `${ocultasOpciones} adjuntos sin archivo guardado no se muestran.`);
    }
    estadoSelector.dataset.tipo = "info";
    estadoSelector.textContent = partes.join(" ");
    masOpciones.hidden = cursorOpciones == null;
    colocarSelector();
  }

  /* One page of the terrain's authorized list, kept to its PDFs. */
  async function cargarOpciones({ reiniciar = false } = {}) {
    if (!selector || !vivo || fuera) return;
    listado?.abort();
    const control = new AbortController();
    listado = control;
    if (reiniciar) cursorOpciones = null;
    masOpciones.disabled = true;
    estadoSelector.dataset.tipo = "info";
    estadoSelector.textContent = "Cargando la lista…";
    try {
      const r = await ctx.cliente.listar(terrenoId,
        { cursor: reiniciar ? null : cursorOpciones, limite: LIMITE_PAGINA, signal: control.signal });
      if (!vivo || listado !== control || !selector) return;
      const pdfs = (r.archivos ?? []).filter((a) => a?.tipo === "pdf");
      const opciones = pdfs.map(opcionPdf).filter(Boolean);
      cursorOpciones = r.cursor_siguiente ?? null;
      const desde = reiniciar ? 0 : listaOpciones.children.length;
      const conFoco = selector.contains(document.activeElement);
      pintarOpciones(opciones, { reiniciar, ocultas: pdfs.length - opciones.length });
      masOpciones.disabled = false;
      if (conFoco) enfocarOpcion(desde);
    } catch (error) {
      if (!vivo || listado !== control || esAbort(error)) return;
      if (error instanceof ErrorArchivos && error.status === 404) { accesoPerdido(error); return; }
      masOpciones.disabled = false;
      masOpciones.hidden = false;
      masOpciones.textContent = "Reintentar";
      estadoSelector.dataset.tipo = "error";
      estadoSelector.textContent = `No se pudo cargar la lista: ${error?.message ?? "error"}`;
      if (error instanceof ErrorArchivos && (error.status === 403 || error.status === 401)) notificarCambio();
      return;
    } finally {
      if (listado === control) listado = null;
    }
    masOpciones.textContent = "Cargar más";
  }

  /* Everything this cell is reading: the chooser and its list, a download in
   * flight (its reserved tab closes), and the message about it. */
  function detenerLectura() {
    cerrarSelector({ enfocar: false });
    if (abriendo) { abriendo.abort(); marcarAbriendo(null); }
    avisar("");
  }

  const boton = (etiqueta, onclick, peligro = false) => el("button", {
    type: "button", class: ["btn", "btn-small", peligro ? "btn-peligro" : "btn-quiet"], onclick,
  }, etiqueta);

  function pintarSubida() {
    if (!subida || fuera) { progreso.replaceChildren(); progreso.hidden = true; return; }
    const e = subida.estado();
    const controles = [];
    if (!solo && e.reintentable) {
      const espera = e.reintentarDesde ? Math.ceil((e.reintentarDesde - Date.now()) / 1000) : 0;
      const b = boton(espera > 0 ? `Reintentar (${espera} s)` : "Reintentar", () => subida?.reintentar());
      b.disabled = espera > 0;
      if (espera > 0) setTimeout(() => { if (vivo) pintarSubida(); }, 1000);
      controles.push(b);
    }
    if (!solo && e.cancelable && !esTerminal(e.fase)) {
      controles.push(boton("Cancelar", () => subida?.cancelar(), true));
    }
    if (!e.cancelable && !e.versionId && !esTerminal(e.fase) && e.reintentable) {
      // Nothing reached the server (the pipeline was busy): it can just be dropped.
      controles.push(boton("Descartar", () => descartar()));
    }
    const ocupada = EN_PROGRESO.has(e.fase) && !e.reintentable;
    // A stored upload is already said by the summary; its full message stays in the title.
    const nota = NOTA_CORTA[e.fase] ?? (ocupada || e.fase === FASE.LISTO ? "" : e.mensaje);
    progreso.hidden = false;
    progreso.dataset.fase = e.fase;
    progreso.title = [e.nombre, e.mensaje].filter(Boolean).join(": ");
    progreso.replaceChildren(...[
      el("span", { class: "archivos-celda-fase" }, FASE_TEXTO[e.fase] ?? e.fase),
      ocupada ? el("progress", { class: "archivos-progreso", "aria-label": FASE_TEXTO[e.fase] }) : null,
      nota ? el("span", { class: "archivos-celda-nota" }, nota) : null,
      ...controles,
    ].filter(Boolean));
    if (esTerminal(e.fase)) ctx.subidas.quitar(subida);
  }

  function descartar() {
    if (!subida) return;
    subida.abortar();
    ctx.subidas.quitar(subida);
    subida = null;
    pintar();
    elegir.focus();
  }

  const enCurso = () => Boolean(subida && !esTerminal(subida.estado().fase));

  function pintar() {
    const sinEscritura = solo || fuera;
    raiz.dataset.soloLectura = sinEscritura ? "1" : "0";
    elegir.hidden = sinEscritura;
    elegir.disabled = sinEscritura || enCurso();
    pintarSubida();
    pintarContornos();
  }

  /* ------------------------------------------------ contour choice (KMZ) */

  /** The latest version of the summary's boundary file, when it waits for a contour. */
  function versionSinActivar() {
    const k = ultimoResumen?.kmz;
    const v = k?.ultima_version;
    if (tipo !== "kmz" || !k || k.geometria_activa_id || v?.estado !== "disponible") return null;
    return describirResumen(ultimoResumen, tipo).estado === ESTADO.SIN_ACTIVAR ? { archivo: k, version: v } : null;
  }

  function pintarContornos() {
    if (tipo !== "kmz") return;
    const sinEscritura = solo || fuera;
    let e = subida?.estado();
    const porElegir = e?.fase === FASE.REQUIERE_SELECCION;
    // Activated elsewhere (the detail, another tab): this version needs no choice any more.
    const k = ultimoResumen?.kmz;
    const versionId = eleccion?.versionId ?? (porElegir ? e.versionId : null);
    if (sinEscritura || (versionId && k?.geometria_activa_id && k?.ultima_version?.id === versionId)) {
      cerrarContornos();
      if (porElegir) { ctx.subidas.quitar(subida); subida = null; e = null; pintarSubida(); }
    } else if (porElegir && !eleccion && e.resultado?.archivo && candidatosDe(e.resultado.intento).length > 1) {
      abrirContornos({ versionId: e.versionId, archivo: e.resultado.archivo, candidatos: candidatosDe(e.resultado.intento) });
    }
    elegirContorno.hidden = sinEscritura || Boolean(eleccion) || enCurso() || !versionSinActivar()
      || e?.fase === FASE.REQUIERE_SELECCION;
    elegirContorno.disabled = Boolean(buscandoContornos);
  }

  function abrirContornos({ versionId, archivo, candidatos }) {
    cerrarContornos();
    const selector = montarSelectorContornos({
      cliente: ctx.cliente, versionId, archivoId: archivo.id, revision: archivo.revision, candidatos,
      onListo: () => {
        cerrarContornos();
        if (subida && !enCurso()) { ctx.subidas.quitar(subida); subida = null; }
        avisar("Contorno activado.");
        avisoTimer = setTimeout(() => { if (vivo) avisar(""); }, 5000);
        notificarCambio();
        pintar();
        elegir.focus();
      },
      onCerrar: () => {
        cerrarContornos();
        if (subida && !enCurso()) { ctx.subidas.quitar(subida); subida = null; }
        pintar();
        (elegirContorno.hidden ? elegir : elegirContorno).focus();
      },
    });
    eleccion = { versionId, selector };
    contornos.replaceChildren(selector.element);
  }

  function cerrarContornos() {
    eleccion?.selector.destroy();
    eleccion = null;
    contornos.replaceChildren();
  }

  /** "Elegir contorno…" for a file uploaded earlier: its latest attempt's candidates. */
  async function buscarContornos() {
    const pendiente = versionSinActivar();
    if (!pendiente || buscandoContornos || !vivo) return;
    const control = new AbortController();
    buscandoContornos = control;
    pintarContornos();
    avisar("Cargando los contornos…");
    try {
      const intento = await intentoPorElegir(ctx.cliente, pendiente.version.id, { signal: control.signal });
      if (!vivo || buscandoContornos !== control) return;
      const candidatos = candidatosDe(intento);
      if (candidatos.length < 2) {
        avisar("Este archivo no tiene varios contornos para elegir. Abre el detalle (⋯) para ver por qué no se activó.",
          { tipoAviso: "error" });
        return;
      }
      avisar("");
      abrirContornos({ versionId: pendiente.version.id, archivo: pendiente.archivo, candidatos });
    } catch (error) {
      if (!vivo || esAbort(error)) return;
      if (error instanceof ErrorArchivos && (error.status === 404 || error.status === 403)) accesoPerdido(error);
      else avisar(`No se pudieron cargar los contornos: ${error?.message ?? "error"}`, { tipoAviso: "error" });
    } finally {
      if (buscandoContornos === control) buscandoContornos = null;
      if (vivo) pintarContornos();
    }
  }

  function empezar(archivo) {
    if (solo || fuera || !vivo || !ctx.vivo() || enCurso()) return;
    if (!ctx.subidas.hayLugar()) {
      onError?.({ codigo: "subidas_llenas",
        mensaje: "Ya hay cinco subidas sin terminar. Termina o cancela alguna antes de empezar otra." });
      return;
    }
    if (subida) ctx.subidas.quitar(subida);
    const s = crearSubida({
      cliente: ctx.cliente, terrenoId, tipo, archivo, turno: ctx.turno,
      alCambiar: () => { if (vivo && s === subida) pintar(); },
      alServidor: () => notificarCambio(),
      alPerderAcceso: (error) => accesoPerdido(error),
    });
    subida = s;
    ctx.subidas.agregar(s);
    pintar();
    s.ejecutar();
  }

  elegir.addEventListener("click", () => {
    if (elegir.disabled) return;
    eligiendo = true;
    entrada.click();
  });
  entrada.addEventListener("cancel", () => { eligiendo = false; });
  entrada.addEventListener("change", () => {
    eligiendo = false;
    const archivo = entrada.files?.[0] ?? null;
    entrada.value = "";
    if (archivo) empezar(archivo);         // a cancelled picker sends nothing
  });

  pintarResumen(resumen);
  pintar();

  return {
    update({ soloLectura: nuevoSolo, resumen: nuevo } = {}) {
      if (!vivo) return;
      if (nuevoSolo !== undefined) solo = Boolean(nuevoSolo);
      pintarResumen(nuevo);
      pintar();
    },
    /** Whether destroying this cell now would drop an unfinished upload, or
     * the PDF chooser or an opening the person is waiting for. */
    ocupado: () => vivo && (enCurso() || eligiendo || Boolean(abriendo) || Boolean(selector)
      || Boolean(eleccion) || Boolean(buscandoContornos)),
    /** Whether that upload is being read, sent or verified right now. */
    activo: () => vivo && Boolean(subida) && EN_PROGRESO.has(subida.estado().fase),
    destroy() {
      if (!vivo) return;
      detenerLectura();
      clearTimeout(avisoTimer);
      buscandoContornos?.abort();
      cerrarContornos();
      vivo = false;
      if (subida) { subida.abortar(); ctx.subidas.quitar(subida); }
      subida = null;
      entrada.value = "";
      raiz.remove();
    },
  };
}

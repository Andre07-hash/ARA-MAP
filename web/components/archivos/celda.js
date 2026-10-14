/* The compact file cell of the table, for one terrain and one kind (pdf | kmz).
 *
 * It shows the caller-aware summary as before and, when the row may be
 * changed, an "Elegir PDF…" / "Elegir KMZ…" button that runs the same upload
 * as the record detail (subida.js, with the factory's shared client, pipeline
 * turn and count of unfinished uploads). The cell never fetches on its own:
 * once the server has the upload it tells the host (onCambio), which hands
 * back the fresh summary through update().
 *
 * What the cell does not do is everything after the upload: choosing among a
 * KMZ's contours, activating one, versions, history and retirement stay in
 * the detail. Choosing a file here activates nothing the detail would not.
 *
 * Its controls live inside a table cell that edits on double click and on
 * keys. Their clicks and keys stop here, so they never reach the row.
 */

import { el } from "../../lib/dom.js";
import { crearSubida, FASE, esTerminal } from "./subida.js";
import { describirResumen } from "./resumen.js";
import { EN_PROGRESO, FASE_TEXTO } from "./detalle.js";

const ETIQUETA = { pdf: "Archivos PDF", kmz: "KMZ" };

/* What a cell can say in a few words after the upload; the full message goes in the title. */
const NOTA_CORTA = {
  [FASE.REQUIERE_SELECCION]: "Varios contornos: elige en el detalle (⋯). Nada se activó.",
};

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

  const texto = el("span", { class: "archivos-celda", dataset: { tipo } });
  const entrada = el("input", { type: "file", class: "archivos-entrada", tabindex: "-1", "aria-hidden": "true",
    accept: tipo === "pdf" ? ".pdf,application/pdf" : ".kmz" });
  const elegir = el("button", { type: "button", class: "btn btn-quiet btn-small archivos-celda-elegir" },
    tipo === "pdf" ? "Elegir PDF…" : "Elegir KMZ…");
  const progreso = el("span", { class: "archivos-celda-subida", role: "status", "aria-live": "polite" });
  const raiz = el("span", { class: "archivos-celda-caja", dataset: { tipo } },
    el("span", { class: "archivos-celda-linea" }, texto, elegir), entrada, progreso);
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
      onError?.({ codigo: "no_encontrado", mensaje: "El archivo ya no está disponible." });
    } else {
      onError?.({ codigo: error.codigo, mensaje: error.message });
    }
    notificarCambio();
    pintar();
  }

  function pintarResumen(r) {
    const d = describirResumen(r, tipo);
    texto.dataset.estado = d.estado;
    texto.textContent = d.texto;
    const titulo = d.nota ? `${ETIQUETA[tipo]}: ${d.texto}. ${d.nota}.` : `${ETIQUETA[tipo]}: ${d.texto}`;
    texto.title = titulo;
    texto.setAttribute("aria-label", titulo);
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
    /** Whether destroying this cell now would drop an unfinished upload. */
    ocupado: () => vivo && (enCurso() || eligiendo),
    /** Whether that upload is being read, sent or verified right now. */
    activo: () => vivo && Boolean(subida) && EN_PROGRESO.has(subida.estado().fase),
    destroy() {
      if (!vivo) return;
      vivo = false;
      if (subida) { subida.abortar(); ctx.subidas.quitar(subida); }
      subida = null;
      entrada.value = "";
      raiz.remove();
    },
  };
}

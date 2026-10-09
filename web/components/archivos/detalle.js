/* The full file controls for one terrain and one kind (pdf | kmz).
 *
 * Mounted by A's host outside the table cell (a detail panel or dialog) with
 * the same arguments and lifetime as the cell. Everything private this mount
 * shows or holds belongs to the scope it was created in: destroy() cancels
 * requests and local uploads, closes its dialogs, revokes object URLs and
 * empties its container. Results that arrive afterwards are dropped.
 *
 * Nothing here decides authorization: read-only state only disables controls,
 * and every action is checked by the server again. Text from the server or a
 * file (names, folders, parser messages) is set as text, never as HTML.
 */

import { el } from "../../lib/dom.js";
import { fmtDate } from "../../lib/format.js";
import { openDialog } from "../ui/dialog.js";
import { ErrorArchivos, LIMITE_BYTES, TIPO_CONTENIDO, nuevaClave } from "../../lib/archivos.js";
import { crearSubida, FASE, esTerminal } from "./subida.js";
import { describirResumen, nombreSeguro, tamanoLegible } from "./resumen.js";

const PAGINA_ARCHIVOS = 20;
const PAGINA_DETALLE = 10;

const ACCIONES = {
  subida_iniciada: "Subida iniciada",
  version_disponible: "Versión guardada",
  version_fallida: "Versión rechazada en la verificación",
  procesado: "KMZ procesado",
  capa_activada: "Contorno activado",
  version_actual_cambiada: "Versión actual cambiada",
  decision_superada: "Resultado no aplicado (otro cambio llegó antes)",
  subida_expirada: "Subida vencida",
  subida_cancelada: "Subida cancelada",
  retirado: "Archivo retirado",
};

const ESTADO_VERSION = {
  subiendo: "Subiendo", disponible: "Guardada", fallido: "Rechazada", cancelado: "Cancelada", expirado: "Vencida",
};

const RESULTADO_INTENTO = {
  listo: "Contorno válido", requiere_seleccion: "Requiere elegir contornos",
  rechazado: "Sin contorno utilizable", error_interno: "Error al procesar",
};

const FASE_TEXTO = {
  [FASE.LEYENDO]: "Calculando huella", [FASE.INICIANDO]: "Registrando", [FASE.SUBIENDO]: "Enviando",
  [FASE.COMPLETANDO]: "Verificando", [FASE.LISTO]: "Listo", [FASE.REQUIERE_SELECCION]: "Elige contornos",
  [FASE.NO_APLICADA]: "Guardado sin activar", [FASE.RECHAZADO]: "Sin contorno utilizable",
  [FASE.FALLIDO]: "Falló", [FASE.INCIERTO]: "Sin confirmar", [FASE.EN_CURSO]: "En proceso",
  [FASE.EXPIRADO]: "Vencida", [FASE.REQUIERE_ARCHIVO]: "Falta el archivo", [FASE.CANCELANDO]: "Cancelando",
  [FASE.CANCELADO]: "Cancelada",
};
const EN_PROGRESO = new Set([FASE.LEYENDO, FASE.INICIANDO, FASE.SUBIENDO, FASE.COMPLETANDO, FASE.CANCELANDO]);

const esAbort = (e) => e?.name === "AbortError";

export function montarDetalle({ container, terrenoId, tipo, soloLectura, resumen, onCambio, onError }, ctx) {
  const vida = new AbortController();
  let vivo = true;
  let solo = Boolean(soloLectura);
  let ultimoResumen = resumen;
  const urls = new Set();            // object URLs to revoke
  const dialogos = new Set();        // close() of dialogs this mount opened
  const subidas = new Map();         // subida -> its <li>
  const claves = new Map();          // logical operation -> idempotency key (reused for the same body)
  let cambioPendiente = false;
  let listaGen = 0;

  const ETIQUETA = tipo === "pdf" ? "PDF" : "KMZ";

  /* ---------------------------------------------------------- skeleton */

  const resumenLinea = el("p", { class: "archivos-resumen secondary" });
  const estado = el("p", { class: "archivos-mensaje", role: "status", "aria-live": "polite" });
  const entrada = el("input", { type: "file", class: "archivos-entrada", accept: tipo === "pdf" ? ".pdf,application/pdf" : ".kmz",
    tabindex: "-1", "aria-hidden": "true" });
  const botonElegir = el("button", { type: "button", class: "btn btn-quiet btn-small archivos-elegir" },
    tipo === "pdf" ? "Elegir PDF…" : "Elegir KMZ…");
  const zona = el("div", { class: "archivos-zona" },
    botonElegir,
    el("span", { class: "secondary" }, ` o arrastra un archivo aquí. Máximo ${LIMITE_BYTES[tipo] / 1024 / 1024} MB.`),
    entrada);
  const listaSubidas = el("ul", { class: "archivos-subidas", "aria-label": `Subidas de ${ETIQUETA}` });
  const lista = el("ul", { class: "archivos-lista", "aria-label": `${ETIQUETA} de este terreno` });
  const masArchivos = el("button", { type: "button", class: "btn btn-quiet btn-small", hidden: true }, "Cargar más");
  const avisoLista = el("button", { type: "button", class: "btn btn-quiet btn-small", hidden: true },
    "La lista cambió: actualizar");
  const raiz = el("section", { class: "archivos-detalle", dataset: { tipo } },
    el("h3", { class: "archivos-titulo" }, tipo === "pdf" ? "Archivos PDF" : "KMZ del terreno"),
    resumenLinea, zona, listaSubidas, estado, avisoLista, lista, masArchivos);
  container.replaceChildren(raiz);

  /* ------------------------------------------------------------ helpers */

  function avisar(texto, tipoMensaje = "info") {
    if (!vivo) return;
    estado.textContent = texto;
    estado.dataset.tipo = tipoMensaje;
  }

  function notificarCambio() {
    if (!vivo || cambioPendiente) return;
    cambioPendiente = true;
    queueMicrotask(() => {
      cambioPendiente = false;
      if (vivo) onCambio?.({ terrenoId });
    });
  }

  /* A failure the person should read. 404 means the resource left this scope:
   * clear what was shown and ask the host to revalidate. */
  function fallo(error, contexto) {
    if (!vivo || esAbort(error)) return;
    if (error instanceof ErrorArchivos && error.status === 404) {
      lista.replaceChildren();
      masArchivos.hidden = true;
      avisar("Este archivo ya no está disponible. Se actualizará la información del terreno.", "error");
      onError?.({ codigo: "no_encontrado", mensaje: "El archivo ya no está disponible." });
      notificarCambio();
      return;
    }
    const mensaje = error instanceof ErrorArchivos ? error.message : "No se pudo completar la operación.";
    avisar(contexto ? `${contexto}: ${mensaje}` : mensaje, "error");
    onError?.({ codigo: error?.codigo ?? "error", mensaje });
  }

  const senal = () => vida.signal;

  /** One key per logical operation; the same body reuses it until it succeeds. */
  function claveDe(operacion) {
    if (!claves.has(operacion)) claves.set(operacion, nuevaClave());
    return claves.get(operacion);
  }

  /* `escritura` marks a control that changes server state: read-only mode hides it at once. */
  function boton(texto, onclick, { peligro = false, deshabilitado = false, etiqueta, escritura = false } = {}) {
    return el("button", { type: "button", class: ["btn", "btn-small", peligro ? "btn-peligro" : "btn-quiet"],
      disabled: deshabilitado, "aria-label": etiqueta, onclick, dataset: escritura ? { escritura: "1" } : null,
      hidden: escritura && solo }, texto);
  }

  /* A confirmation built on the shared dialog, so this mount can close it. */
  function confirmar({ titulo, mensaje, accion }) {
    return new Promise((resolve) => {
      const regreso = document.activeElement;
      let hecho = false;
      const terminar = (v) => { if (!hecho) { hecho = true; resolve(v); } };
      const { dialog, close } = openDialog({
        titulo, contenido: el("p", { class: "secondary" }, mensaje), ancho: "28rem",
        acciones: [
          { etiqueta: "Cancelar", onClick: (c) => { terminar(false); c(); } },
          { etiqueta: accion, variante: "peligro", onClick: (c) => { terminar(true); c(); } },
        ],
      });
      dialogos.add(close);
      dialog.addEventListener("close", () => {
        dialogos.delete(close);
        terminar(false);
        if (vivo && regreso?.isConnected) regreso.focus();
      });
    });
  }

  /* --------------------------------------------------------- uploads */

  function pintarSubida(s) {
    const li = subidas.get(s);
    if (!li || !vivo) return;
    const e = s.estado();
    const controles = [];
    if (e.fase === FASE.REQUIERE_ARCHIVO && !solo) {
      controles.push(boton("Elegir el archivo…", () => elegirPara(s)));
    }
    if (e.reintentable && !solo) {
      const espera = e.reintentarDesde ? Math.ceil((e.reintentarDesde - Date.now()) / 1000) : 0;
      const b = boton(espera > 0 ? `Reintentar (${espera} s)` : "Reintentar", () => s.reintentar(),
        { deshabilitado: espera > 0 });
      if (espera > 0) setTimeout(() => pintarSubida(s), Math.min(espera, 1) * 1000);
      controles.push(b);
    }
    if (e.cancelable && !solo && !esTerminal(e.fase)) {
      controles.push(boton("Cancelar subida", () => s.cancelar(), { peligro: true }));
    }
    if (esTerminal(e.fase)) {
      controles.push(boton("Quitar de la lista", () => quitarSubida(s)));
    }
    li.dataset.fase = e.fase;
    li.replaceChildren(...[
      el("span", { class: "archivos-subida-nombre" }, e.nombre || ETIQUETA),
      el("span", { class: "archivos-subida-fase" }, FASE_TEXTO[e.fase] ?? e.fase),
      EN_PROGRESO.has(e.fase) ? el("progress", { class: "archivos-progreso", "aria-label": FASE_TEXTO[e.fase] }) : null,
      el("span", { class: "archivos-subida-mensaje secondary" }, e.mensaje),
      e.limpiezaPendiente ? el("span", { class: "archivos-subida-mensaje secondary" },
        "El servidor aún debe limpiar contenido temporal.") : null,
      el("span", { class: "archivos-acciones" }, controles),
    ].filter(Boolean));       // native replaceChildren would print "null"
    if (esTerminal(e.fase)) ctx.subidas.quitar(s);
  }

  function quitarSubida(s) {
    s.abortar();
    ctx.subidas.quitar(s);
    subidas.get(s)?.remove();
    subidas.delete(s);
    botonElegir.focus();
  }

  function nuevaSubida({ archivo = null, pendiente = null }) {
    if (!ctx.vivo() || !vivo) return null;
    if (!ctx.subidas.hayLugar()) {
      avisar("Ya hay cinco subidas sin terminar. Termina o cancela alguna antes de empezar otra.", "error");
      return null;
    }
    const li = el("li", { class: "archivos-subida" });
    const s = crearSubida({
      cliente: ctx.cliente, terrenoId, tipo, archivo, pendiente, turno: ctx.turno,
      alCambiar: () => pintarSubida(s),
      alServidor: () => { notificarCambio(); refrescarLista(); },
    });
    subidas.set(s, li);
    ctx.subidas.agregar(s);
    listaSubidas.append(li);
    pintarSubida(s);
    return s;
  }

  function empezar(archivo) {
    if (solo || !vivo) return;
    const s = nuevaSubida({ archivo });
    s?.ejecutar();
  }

  let elegirDestino = null;          // a reloaded pending upload waiting for its file
  function elegirPara(s) {
    elegirDestino = s;
    entrada.click();
  }

  entrada.addEventListener("change", () => {
    const archivo = entrada.files?.[0] ?? null;
    entrada.value = "";
    if (!archivo || !vivo) return;
    const destino = elegirDestino;
    elegirDestino = null;
    if (destino) destino.elegirArchivo(archivo);
    else empezar(archivo);
  });
  botonElegir.addEventListener("click", () => { elegirDestino = null; entrada.click(); });

  function arrastre(evento) {
    if (solo) return;
    evento.preventDefault();
    zona.classList.toggle("archivos-zona-activa", evento.type === "dragover" || evento.type === "dragenter");
  }
  zona.addEventListener("dragenter", arrastre);
  zona.addEventListener("dragover", arrastre);
  zona.addEventListener("dragleave", arrastre);
  zona.addEventListener("drop", (evento) => {
    arrastre(evento);
    if (solo || !vivo) return;
    const archivos = evento.dataTransfer?.files ?? [];
    if (archivos.length !== 1) {
      avisar(archivos.length > 1 ? "Suelta un solo archivo a la vez." : "No se recibió ningún archivo.", "error");
      return;
    }
    empezar(archivos[0]);
  });

  /* ------------------------------------------------------- downloads */

  async function descargar(version, abrir = false) {
    try {
      avisar("Descargando…");
      const r = await ctx.cliente.descargar(version.id, tipo, { signal: senal() });
      if (!vivo) return;
      const url = URL.createObjectURL(new Blob([r.bytes], { type: TIPO_CONTENIDO[tipo] }));
      urls.add(url);
      if (abrir) {
        window.open(url, "_blank", "noopener");
      } else {
        const a = el("a", { href: url, download: nombreSeguro(version.nombre_original, tipo), hidden: true });
        document.body.append(a);
        a.click();
        a.remove();
        // Revoking in the same task can cancel the save in some browsers; destroy() revokes it anyway.
        setTimeout(() => { if (urls.delete(url)) URL.revokeObjectURL(url); }, 30_000);
      }
      avisar(abrir ? "Archivo abierto en una pestaña nueva." : "Descarga lista.");
    } catch (error) {
      fallo(error, "No se pudo descargar");
    }
  }

  /* ---------------------------------------------- activation, retire */

  async function activar(archivo, versionId, geometriaId) {
    if (solo) return;
    const operacion = `activar|${archivo.id}|${versionId}|${geometriaId ?? ""}|${archivo.revision}`;
    try {
      avisar("Activando…");
      await ctx.cliente.activar(archivo.id, { versionId, geometriaId, revision: archivo.revision },
        claveDe(operacion), { signal: senal() });
      claves.delete(operacion);
      if (!vivo) return;
      avisar(geometriaId ? "Contorno activado." : "Versión activada.");
      notificarCambio();
      cargarLista({ forzar: true });
    } catch (error) {
      if (error instanceof ErrorArchivos && error.codigo === "revision_conflictiva") {
        claves.delete(operacion);
        avisar("El archivo cambió mientras tanto. Se actualizó la lista: revisa y vuelve a elegir.", "error");
        cargarLista({ forzar: true });
        return;
      }
      fallo(error, "No se pudo activar");
    }
  }

  async function retirar(archivo, disparador) {
    if (solo) return;
    const ok = await confirmar({
      titulo: `¿Retirar este ${ETIQUETA}?`,
      mensaje: "Dejará de ser un archivo actual del terreno y se cancelarán sus subidas pendientes. " +
        "Sus versiones guardadas y su historial se conservan. En esta versión de ARA Map no se puede deshacer.",
      accion: "Retirar",
    });
    if (!ok || !vivo) return;
    const operacion = `retirar|${archivo.id}|${archivo.revision}`;
    try {
      avisar("Retirando…");
      const r = await ctx.cliente.retirar(archivo.id, archivo.revision, claveDe(operacion), { signal: senal() });
      claves.delete(operacion);
      if (!vivo) return;
      avisar(r?.limpieza_pendiente ? "Archivo retirado. El servidor terminará de limpiar el contenido temporal."
        : "Archivo retirado.");
      notificarCambio();
      cargarLista({ forzar: true });
    } catch (error) {
      if (error instanceof ErrorArchivos && error.codigo === "revision_conflictiva") {
        claves.delete(operacion);
        avisar("El archivo cambió mientras tanto; no se retiró. Revisa la lista actualizada.", "error");
        cargarLista({ forzar: true });
        return;
      }
      fallo(error, "No se pudo retirar");
    } finally {
      if (vivo && disparador?.isConnected) disparador.focus();
    }
  }

  /* ------------------------------------------------------ paged panels */

  /* A toggled, paged panel under one file. `cargar(cursor)` returns {items, cursor}. */
  function panel(titulo, toggle, contenedor, cargar, pintarItem) {
    let abierto = false;
    let gen = 0;
    const ul = el("ul", { class: "archivos-panel-lista" });
    const mas = el("button", { type: "button", class: "btn btn-quiet btn-small", hidden: true }, "Cargar más");
    const caja = el("div", { class: "archivos-panel", hidden: true, role: "region", "aria-label": titulo }, ul, mas);
    contenedor.append(caja);
    let cursor = null;
    async function pagina(reiniciar) {
      const mia = reiniciar ? ++gen : gen;
      if (reiniciar) { cursor = null; ul.replaceChildren(el("li", { class: "secondary" }, "Cargando…")); }
      try {
        const r = await cargar(cursor);
        if (!vivo || mia !== gen) return;
        if (reiniciar) ul.replaceChildren();
        for (const item of r.items) ul.append(pintarItem(item, () => pagina(true)));
        if (reiniciar && r.items.length === 0) ul.append(el("li", { class: "secondary" }, "Sin elementos."));
        cursor = r.cursor;
        mas.hidden = cursor == null;
      } catch (error) {
        if (mia !== gen) return;
        ul.replaceChildren();
        fallo(error, titulo);
      }
    }
    mas.addEventListener("click", () => pagina(false));
    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("click", () => {
      abierto = !abierto;
      caja.hidden = !abierto;
      toggle.setAttribute("aria-expanded", String(abierto));
      if (abierto) pagina(true);
      else { gen += 1; ul.replaceChildren(); }       // closed: drop what it showed
    });
    return { recargar: () => abierto && pagina(true) };
  }

  function lineaVersion(archivo, v, recargar) {
    const actual = v.id && v.id === archivo.version_actual_id;
    const partes = [];
    if (v.propia === false) {
      return el("li", { class: "archivos-version" },
        el("span", {}, `${ESTADO_VERSION[v.estado] ?? v.estado}: subida en curso de otra cuenta.`));
    }
    partes.push(el("span", { class: "archivos-version-num" }, `v${v.numero}`),
      el("span", {}, ESTADO_VERSION[v.estado] ?? v.estado),
      actual ? el("span", { class: "archivos-chip archivos-chip-actual" }, "Actual") : null,
      el("span", { class: "secondary" }, [v.nombre_original, tamanoLegible(v.tamano ?? v.tamano_declarado),
        fmtDate(v.terminado_en ?? v.finalizado_en ?? v.iniciado_en)].filter(Boolean).join(" · ")));
    if (v.error?.mensaje) partes.push(el("span", { class: "archivos-error" }, v.error.mensaje));
    const acciones = [];
    if (v.estado === "disponible") {
      acciones.push(boton("Descargar", () => descargar(v), { etiqueta: `Descargar versión ${v.numero}` }));
      if (tipo === "pdf") acciones.push(boton("Abrir", () => descargar(v, true), { etiqueta: `Abrir versión ${v.numero}` }));
      if (tipo === "pdf" && !actual && !archivo.retirado_en && !solo) {
        acciones.push(boton("Hacer actual", () => activar(archivo, v.id, null), { escritura: true }));
      }
    }
    if (v.estado === "subiendo" && v.propia && !solo) {
      acciones.push(boton("Continuar subida", () => {
        const s = nuevaSubida({ pendiente: { ...v, archivo_id: archivo.id } });
        s?.ejecutar();
      }, { escritura: true }));
    }
    partes.push(el("span", { class: "archivos-acciones" }, acciones));
    return el("li", { class: "archivos-version", dataset: { estado: v.estado } }, partes);
  }

  function lineaEvento(e) {
    if (e.privado) {
      return el("li", { class: "archivos-evento" }, el("span", {}, fmtDate(e.at)),
        el("span", {}, `${ACCIONES[e.accion] ?? e.accion} (subida de otra cuenta)`));
    }
    return el("li", { class: "archivos-evento" }, el("span", {}, fmtDate(e.at)),
      el("span", {}, ACCIONES[e.accion] ?? e.accion),
      e.actor?.display_name ? el("span", { class: "secondary" }, e.actor.display_name) : null);
  }

  /* KMZ: attempts of the version, candidate choice and explicit activation. */
  function lineaIntento(archivo, version, intento, recargar) {
    const li = el("li", { class: "archivos-intento", dataset: { resultado: intento.resultado } },
      el("span", {}, `Intento ${intento.numero}`),
      el("span", {}, RESULTADO_INTENTO[intento.resultado] ?? intento.resultado),
      el("span", { class: "secondary" }, `${intento.candidatos} contorno${intento.candidatos === 1 ? "" : "s"} en el archivo`));
    const acciones = el("span", { class: "archivos-acciones" });
    li.append(acciones);
    const activa = intento.geometria_id && intento.geometria_id === archivo.geometria_activa_id;
    if (activa) acciones.append(el("span", { class: "archivos-chip archivos-chip-actual" }, "Contorno activo"));
    if (intento.resultado === "listo" && intento.geometria_id && !activa && !archivo.retirado_en && !solo) {
      acciones.append(boton("Activar este contorno", () => activar(archivo, version.id, intento.geometria_id), { escritura: true }));
    }
    if (intento.candidatos > 1 && !solo && !archivo.retirado_en) {
      acciones.append(boton("Elegir contornos…", () => elegirCandidatos(archivo, version, intento, li, recargar), { escritura: true }));
    }
    return li;
  }

  async function elegirCandidatos(archivo, version, intento, li, recargar) {
    li.querySelector(".archivos-candidatos")?.remove();
    const caja = el("fieldset", { class: "archivos-candidatos" }, el("legend", {}, "Contornos del archivo"),
      el("p", { class: "secondary" }, "Cargando…"));
    li.append(caja);
    let detalle;
    try {
      detalle = await ctx.cliente.intento(intento.id, { signal: senal() });
    } catch (error) {
      caja.remove();
      return fallo(error, "No se pudieron cargar los contornos");
    }
    if (!vivo) return;
    const candidatos = Array.isArray(detalle?.resultado_detalle?.candidatos) ? detalle.resultado_detalle.candidatos : [];
    const casillas = [];
    const opciones = candidatos.map((c, posicion) => {
      const indice = Number.isInteger(c.indice) ? c.indice : posicion;
      const id = `cand-${intento.id}-${indice}`;
      const casilla = el("input", { type: "checkbox", id, value: String(indice), disabled: !c.valido });
      casillas.push(casilla);
      const carpeta = Array.isArray(c.carpeta) ? c.carpeta.join(" / ") : c.carpeta;
      const nombre = [carpeta, c.nombre].filter(Boolean).join(" / ") || `Contorno ${indice + 1}`;
      return el("div", { class: "archivos-candidato" }, casilla,
        el("label", { for: id }, `${nombre} · ${c.partes} parte${c.partes === 1 ? "" : "s"}, ${c.vertices} vértices`),
        c.error?.mensaje ? el("span", { class: "archivos-error" }, c.error.mensaje) : null);
    });
    const resultado = el("p", { class: "secondary", role: "status" });
    const procesar = boton("Procesar selección", async () => {
      const seleccion = casillas.filter((x) => x.checked).map((x) => Number(x.value));
      if (seleccion.length === 0) { resultado.textContent = "Elige al menos un contorno."; return; }
      const operacion = `procesar|${version.id}|${JSON.stringify(seleccion)}`;
      procesar.disabled = true;
      try {
        resultado.textContent = "Procesando la selección…";
        const r = await ctx.cliente.procesar(version.id, seleccion, claveDe(operacion), { signal: senal() });
        claves.delete(operacion);
        if (!vivo) return;
        notificarCambio();
        // The attempts panel reloads below, so the outcome goes to the mount's status line.
        if (r?.geometria_id && r?.intento?.resultado === "listo") {
          avisar("Selección válida. Todavía no está activa: usa «Activar este contorno» en el intento nuevo.");
        } else {
          avisar(r?.intento?.resultado_detalle?.error?.mensaje ?? "La selección no produjo un contorno utilizable.", "error");
        }
        recargar();
      } catch (error) {
        resultado.textContent = error instanceof ErrorArchivos ? error.message : "No se pudo procesar.";
        if (!(error instanceof ErrorArchivos && error.incierto)) claves.delete(operacion);
        fallo(error, "No se pudo procesar la selección");
      } finally {
        procesar.disabled = false;
      }
    });
    caja.replaceChildren(el("legend", {}, "Contornos del archivo"),
      ...(opciones.length ? opciones : [el("p", { class: "secondary" }, "Este intento no tiene contornos para elegir.")]),
      el("span", { class: "archivos-acciones" }, opciones.length ? procesar : null), resultado);
    casillas.find((x) => !x.disabled)?.focus();
  }

  /* ------------------------------------------------------- file list */

  function lineaArchivo(archivo) {
    const v = archivo.ultima_version;
    const nombre = v?.nombre_original ?? (v?.propia === false ? "Subida de otra cuenta" : ETIQUETA);
    const li = el("li", { class: "archivos-item", dataset: { retirado: archivo.retirado_en ? "1" : "0" } });
    const cabecera = el("div", { class: "archivos-item-cabecera" },
      el("span", { class: "archivos-item-nombre" }, nombre),
      archivo.retirado_en ? el("span", { class: "archivos-chip archivos-chip-retirado" }, "Retirado")
        : archivo.version_actual_id ? el("span", { class: "archivos-chip archivos-chip-actual" }, "Actual")
          : el("span", { class: "archivos-chip" }, "Sin versión actual"),
      tipo === "kmz" && archivo.geometria_activa_id && !archivo.retirado_en
        ? el("span", { class: "archivos-chip archivos-chip-actual" }, "Contorno activo") : null,
      v ? el("span", { class: "secondary" }, v.propia === false
        ? `Otra cuenta está subiendo una versión (${ESTADO_VERSION[v.estado] ?? v.estado}).`
        : `Última versión: v${v.numero} · ${ESTADO_VERSION[v.estado] ?? v.estado}`) : null);
    const acciones = el("div", { class: "archivos-acciones" });
    const cuerpo = el("div", { class: "archivos-item-paneles" });
    li.append(cabecera, acciones, cuerpo);

    if (archivo.version_actual_id && v && v.id === archivo.version_actual_id && v.estado === "disponible") {
      acciones.append(boton("Descargar", () => descargar(v), { etiqueta: `Descargar ${nombre}` }));
      if (tipo === "pdf") acciones.append(boton("Abrir", () => descargar(v, true), { etiqueta: `Abrir ${nombre}` }));
    }
    const verVersiones = boton("Versiones", null);
    const verHistorial = boton("Historial", null);
    acciones.append(verVersiones, verHistorial);
    panel(`Versiones de ${nombre}`, verVersiones, cuerpo, async (cursor) => {
      const r = await ctx.cliente.versiones(archivo.id, { cursor, limite: PAGINA_DETALLE, signal: senal() });
      return { items: r.versiones ?? [], cursor: r.cursor_siguiente };
    }, (version, recargar) => {
      const linea = lineaVersion(archivo, version, recargar);
      if (tipo === "kmz" && version.estado === "disponible") {
        const verIntentos = boton("Contornos", null, { etiqueta: `Contornos de la versión ${version.numero}` });
        linea.querySelector(".archivos-acciones").append(verIntentos);
        if (!solo && !archivo.retirado_en) {
          linea.querySelector(".archivos-acciones").append(boton("Volver a procesar", async () => {
            const operacion = `procesar|${version.id}|null`;
            try {
              avisar("Procesando el KMZ…");
              await ctx.cliente.procesar(version.id, null, claveDe(operacion), { signal: senal() });
              claves.delete(operacion);
              if (!vivo) return;
              avisar("KMZ procesado. Revisa sus contornos; nada se activó.");
              notificarCambio();
            } catch (error) {
              fallo(error, "No se pudo procesar");
            }
          }, { escritura: true }));
        }
        let panelIntentos = null;
        panelIntentos = panel(`Intentos de la versión ${version.numero}`, verIntentos, linea, async (cursor) => {
          const r = await ctx.cliente.intentos(version.id, { cursor, limite: PAGINA_DETALLE, signal: senal() });
          return { items: r.intentos ?? [], cursor: r.cursor_siguiente };
        }, (intento) => lineaIntento(archivo, version, intento, () => panelIntentos?.recargar()));
      }
      return linea;
    });
    panel(`Historial de ${nombre}`, verHistorial, cuerpo, async (cursor) => {
      const r = await ctx.cliente.historial(archivo.id, { cursor, limite: PAGINA_DETALLE, signal: senal() });
      return { items: r.eventos ?? [], cursor: r.cursor_siguiente };
    }, lineaEvento);
    if (!archivo.retirado_en && !solo) {
      const b = boton("Retirar…", () => retirar(archivo, b), { peligro: true, etiqueta: `Retirar ${nombre}`, escritura: true });
      acciones.append(b);
    }
    return li;
  }

  /* A change from elsewhere must not wipe a panel or a choice the person has
   * open: offer to refresh instead. Actions taken here reload the list. */
  const enUso = () => Boolean(lista.querySelector(".archivos-panel:not([hidden]), .archivos-candidatos"));
  function refrescarLista() {
    if (!vivo) return;
    if (enUso()) { avisoLista.hidden = false; return; }
    cargarLista();
  }
  avisoLista.addEventListener("click", () => cargarLista({ forzar: true }));

  /* `forzar`: replace the list even if a panel is open (after an action taken
   * here). Otherwise a page that arrives while the person is using a panel
   * only offers the refresh. */
  let cursorLista = null;
  async function cargarLista({ siguiente = false, forzar = false } = {}) {
    if (!vivo) return;
    if (!siguiente) avisoLista.hidden = true;
    const mia = siguiente ? listaGen : ++listaGen;
    if (!siguiente) cursorLista = null;
    try {
      const r = await ctx.cliente.listar(terrenoId, { cursor: siguiente ? cursorLista : null, limite: PAGINA_ARCHIVOS, signal: senal() });
      if (!vivo || mia !== listaGen) return;
      if (!siguiente && !forzar && enUso()) { avisoLista.hidden = false; return; }
      const propios = (r.archivos ?? []).filter((a) => a.tipo === tipo);
      if (!siguiente) lista.replaceChildren();
      for (const a of propios) lista.append(lineaArchivo(a));
      if (!siguiente && lista.children.length === 0 && !r.cursor_siguiente) {
        lista.append(el("li", { class: "secondary" }, tipo === "pdf" ? "Este terreno no tiene PDF." : "Este terreno no tiene KMZ."));
      }
      cursorLista = r.cursor_siguiente;
      masArchivos.hidden = cursorLista == null;
    } catch (error) {
      if (mia === listaGen) fallo(error, "No se pudo cargar la lista");
    }
  }
  masArchivos.addEventListener("click", () => cargarLista({ siguiente: true }));

  /* ---------------------------------------------------------- render */

  function pintarResumen() {
    const d = describirResumen(ultimoResumen, tipo);
    resumenLinea.textContent = d.nota ? `${d.texto}. ${d.nota}.` : d.texto;
    resumenLinea.dataset.estado = d.estado;
  }

  function pintarModo() {
    raiz.dataset.soloLectura = solo ? "1" : "0";
    zona.hidden = solo;
    botonElegir.disabled = solo;
    for (const b of raiz.querySelectorAll("[data-escritura]")) b.hidden = solo;
    for (const s of subidas.keys()) pintarSubida(s);
  }

  const huella = (r) => JSON.stringify(r ?? null);

  pintarResumen();
  pintarModo();
  cargarLista();       // one bounded page; versions, history and attempts load only when opened

  return {
    update({ soloLectura: nuevoSolo, resumen: nuevoResumen } = {}) {
      if (!vivo) return;
      const antesSolo = solo;
      if (nuevoSolo !== undefined) solo = Boolean(nuevoSolo);
      const cambioResumen = nuevoResumen !== undefined && huella(nuevoResumen) !== huella(ultimoResumen);
      if (nuevoResumen !== undefined) ultimoResumen = nuevoResumen;
      pintarResumen();
      if (solo !== antesSolo) pintarModo();
      if (cambioResumen) refrescarLista();
    },
    destroy() {
      if (!vivo) return;
      vivo = false;
      vida.abort();
      for (const s of subidas.keys()) { s.abortar(); ctx.subidas.quitar(s); }
      subidas.clear();
      for (const close of [...dialogos]) close();
      dialogos.clear();
      for (const url of urls) URL.revokeObjectURL(url);
      urls.clear();
      claves.clear();
      entrada.value = "";
      raiz.remove();
    },
  };
}

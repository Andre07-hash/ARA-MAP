/* The draft editor: create or correct one inventory terrain directly.
 *
 * Built once per terrain and kept alive like the filter rail: the inputs are
 * the form's state, so nothing the user typed is lost to a re-render, a failed
 * request or a conflict. Only fields whose text changed are sent.
 *
 *   createTerrainEditor({ terreno, onSaved, onClose, onHistory })
 *     -> { element, id, dirty, destroy() }
 *
 * `terreno` is an InternalTerrain, or null for a new draft.
 */

import { api } from "../../lib/api.js";
import { el } from "../../lib/dom.js";
import { googleMapsSearch } from "../../lib/format.js";
import {
  analizarConflicto, CAMPOS, cambiosDelFormulario, campo, CONFIRMABLES, crearIntento, erroresDeCampo,
  estadoPublicacion, estadoUbicacion, leerNumero, mostrarTexto, mostrarValor, SECCIONES,
  textosIniciales,
} from "../../lib/inventario.js";
import { confirmDialog } from "../ui/dialog.js";
import { confirmacion, EstadoChip } from "./InventoryDetail.js";

export function createTerrainEditor({ terreno, onSaved, onClose, onHistory, onPreview }) {
  let base = terreno;                       // the server version the form is based on
  let iniciales = textosIniciales(base?.draft);
  let enVuelo = false;
  let conflictoPendiente = false;
  const intento = crearIntento();
  const entradas = new Map();               // clave -> { input, error, fila }

  /* ---- fields --------------------------------------------------------- */

  function crearEntrada(c) {
    const id = `ed-${c.clave}`;
    const errorId = `${id}-error`;
    const ayudaId = c.ayuda ? `${id}-ayuda` : null;
    const comun = { id, name: c.clave, "aria-describedby": [ayudaId, errorId].filter(Boolean).join(" ") };

    const input = c.tipo === "opcion"
      ? el("select", { ...comun, class: "input" },
        c.opciones.map(([valor, etiqueta]) => el("option", { value: valor }, etiqueta)))
      : c.tipo === "largo"
        ? el("textarea", { ...comun, class: "input", rows: "3" })
        : c.tipo === "bool"
          ? el("input", { ...comun, type: "checkbox" })
          : el("input", {
            ...comun, type: "text", class: ["input", c.tipo === "numero" && "input-num"],
            autocomplete: "off", ...(c.tipo === "numero" ? { inputmode: "decimal" } : {}),
          });
    const error = el("p", { id: errorId, class: "field-error", hidden: true });
    const extra = el("div", { class: "field-extra" });

    const fila = c.tipo === "bool"
      ? el("div", { class: "editor-field" },
        el("label", { class: "check", for: id }, input, el("span", {}, c.etiqueta)), error, extra)
      : el("div", { class: ["editor-field", c.ancho && "editor-field-ancho"] },
        el("label", { class: "field-label", for: id }, c.etiqueta),
        input,
        c.ayuda && el("p", { id: ayudaId, class: "field-help muted" }, c.ayuda),
        error, extra);

    entradas.set(c.clave, { input, error, fila, extra });
    return fila;
  }

  const leerUno = (clave) => {
    const { input } = entradas.get(clave);
    return input.type === "checkbox" ? input.checked : input.value;
  };
  const leer = () => Object.fromEntries(CAMPOS.map((c) => [c.clave, leerUno(c.clave)]));

  function escribir(clave, texto) {
    const { input } = entradas.get(clave);
    if (input.type === "checkbox") input.checked = Boolean(texto);
    else input.value = texto;
  }

  /* ---- layout --------------------------------------------------------- */

  const eyebrow = el("span", { class: "eyebrow" });
  const titulo = el("h1", {});
  const chips = el("p", { class: "estado-row" });
  const alertas = el("div", { class: "editor-alertas", "aria-live": "polite" });
  const resumen = el("div", { class: "editor-resumen", role: "alert", tabindex: "-1", hidden: true });
  const estadoTexto = el("p", { class: "editor-estado secondary", role: "status" });
  const ubicacionNota = el("p", { class: "field-help" });
  const mapsLink = el("a", {
    class: "link-btn", target: "_blank", rel: "noopener noreferrer",
  }, "Buscar en Google Maps");
  const comercialNota = el("p", { class: "note note-aviso", hidden: true });

  /* Confirming price/availability is its own deliberate act (PATCH
   * `confirm`), recorded with who and when; editing never implies it. */
  const confirmar = {};
  const sellos = {};
  const verificacion = el("fieldset", { class: "editor-seccion editor-verificacion" },
    el("legend", { class: "eyebrow" }, "Verificación"),
    el("p", { class: "secondary editor-instruccion" },
      "La fecha de confirmación no es la de la última edición: solo cambia cuando alguien " +
      "confirma el dato aquí."),
    el("div", { class: "editor-grid" }, Object.entries(CONFIRMABLES).map(([clave, etiqueta]) => {
      confirmar[clave] = el("input", { type: "checkbox", id: `confirmar-${clave}` });
      sellos[clave] = el("p", { class: "figure" });
      return el("div", { class: "editor-field" },
        el("p", { class: "field-label" }, `${etiqueta} confirmado`),
        sellos[clave],
        el("label", { class: "check", for: `confirmar-${clave}` }, confirmar[clave],
          el("span", {}, clave === "price" ? "Confirmo hoy el precio" : "Confirmo hoy la disponibilidad")),
      );
    })),
  );
  const confirmados = () => Object.keys(confirmar).filter((k) => confirmar[k].checked);

  const guardar = el("button", { type: "submit", class: "btn btn-principal" }, "Guardar borrador");
  const historial = el("button", { type: "button", class: "btn btn-quiet" }, "Historial");
  // Preview shows the SAVED draft: unsaved input has to be saved first.
  const vistaPrevia = el("button", { type: "button", class: "btn btn-quiet", hidden: true }, "Vista previa");
  const cerrar = el("button", { type: "button", class: "btn btn-quiet" }, "Cerrar");

  const barra = el("footer", { class: "editor-acciones" },
    estadoTexto,
    el("div", { class: "screen-actions" }, cerrar, historial, vistaPrevia, guardar),
  );
  // Toasts on a phone sit above this bar (styles/inventory.css): publish its
  // real height, which changes when its buttons wrap.
  const medirBarra = typeof ResizeObserver === "function"
    ? new ResizeObserver(() => document.documentElement.style.setProperty(
      "--editor-barra", `${Math.ceil(barra.getBoundingClientRect().height)}px`))
    : null;
  medirBarra?.observe(barra);

  const form = el("form", { class: "editor-form", novalidate: true },
    SECCIONES.map((s) => el("fieldset", { class: ["editor-seccion", `editor-${s.id}`] },
      el("legend", { class: "eyebrow" }, s.titulo, s.nota && el("span", { class: "muted" }, ` · ${s.nota}`)),
      s.id === "ubicacion" && el("p", { class: "secondary editor-instruccion" },
        "Corrige la ubicación aquí mismo: escribe latitud (X) y longitud (Y) en grados " +
        "decimales. No hace falta cambiar ni volver a importar el archivo."),
      el("div", { class: "editor-grid" },
        CAMPOS.filter((c) => c.seccion === s.id).map(crearEntrada)),
      s.id === "ubicacion" && el("div", { class: "editor-ubicacion-nota" }, ubicacionNota, mapsLink),
      s.id === "comercial" && comercialNota,
    )).flatMap((fieldset, i) => (SECCIONES[i].id === "privado" ? [verificacion, fieldset] : [fieldset])),
    barra,
  );

  const element = el("div", { class: "screen editor" },
    el("header", { class: "screen-header" },
      el("div", {}, eyebrow, titulo, chips,
        el("p", { class: "secondary" },
          "Guardar crea una nueva versión del borrador. El catálogo público no cambia al guardar.")),
    ),
    resumen,
    alertas,
    form,
  );

  /* ---- live state ----------------------------------------------------- */

  const esSucio = () => confirmados().length > 0
    || CAMPOS.some((c) => leerUno(c.clave) !== iniciales[c.clave]);

  function pintarCabecera() {
    const nombre = base?.draft?.terreno;
    eyebrow.textContent = base ? `Inventario · ID ${base.id}` : "Inventario · Nuevo terreno";
    titulo.textContent = base ? (nombre || "Sin nombre") : "Nuevo terreno";
    chips.replaceChildren(base
      ? EstadoChip(estadoPublicacion(base))
      : EstadoChip({ etiqueta: "Borrador nuevo · sin guardar", tono: "borrador" }));
    if (base) chips.append(el("span", { class: "muted figure" }, ` Versión ${base.version}`));
    historial.hidden = !base;
    // A new draft has nothing to confirm yet; its first save creates it.
    verificacion.hidden = !base;
    for (const clave of Object.keys(sellos)) sellos[clave].textContent = confirmacion(base?.confirmations?.[clave]);
  }

  function pintarEstado(texto) {
    vistaPrevia.hidden = !base || !onPreview || base.publication_state === "archived";
    if (texto != null) { estadoTexto.textContent = texto; return; }
    estadoTexto.textContent = enVuelo ? "Guardando…"
      : conflictoPendiente ? "Resuelve el conflicto antes de guardar."
        : esSucio() ? "Cambios sin guardar." : "Sin cambios.";
  }

  function pintarAyudas() {
    const lat = leerNumero(leerUno("lat")).valor;
    const lon = leerNumero(leerUno("lon")).valor;
    const ubic = estadoUbicacion(lat, lon);
    const mitad = (lat == null) !== (lon == null);
    ubicacionNota.className = ["field-help", (ubic === "invalida" || mitad) && "field-warn"].filter(Boolean).join(" ");
    ubicacionNota.textContent = mitad
      ? `Falta la ${lat == null ? "latitud (X)" : "longitud (Y)"}: se puede guardar así, pero no ` +
        "aparecerá en el mapa ni se podrá publicar hasta completar el par."
      : ubic === "valida"
      ? "Coordenadas válidas: aparecerá en el mapa."
      : ubic === "invalida"
        ? "Fuera de México o con X y Y invertidas: no aparecerá en el mapa ni se podrá publicar así."
        : "Sin coordenadas: no aparecerá en el mapa.";
    mapsLink.href = googleMapsSearch({
      terreno: leerUno("terreno"), direccion: leerUno("direccion"),
      municipio: leerUno("municipio"), estado: leerUno("estado"),
    });

    const consultar = leerUno("price_on_request");
    const conMonto = leerUno("asking_price").trim() !== "" || leerUno("asking_m2").trim() !== "";
    const sinMoneda = conMonto && leerUno("moneda") === "";
    comercialNota.hidden = !(consultar && conMonto) && !sinMoneda;
    comercialNota.textContent = consultar && conMonto
      ? "«Precio a consultar» y un monto no pueden publicarse juntos. Deja vacíos los montos " +
        "o desmarca «Precio a consultar»; los precios anteriores quedan en el historial."
      : "Este precio no tiene moneda registrada. Elige USD o MXN para poder publicarlo; " +
        "no se asume ni se convierte.";
  }

  function rellenar() {
    for (const c of CAMPOS) escribir(c.clave, iniciales[c.clave]);
  }

  /* ---- errors --------------------------------------------------------- */

  function limpiarErrores() {
    resumen.hidden = true;
    resumen.replaceChildren();
    for (const { input, error } of entradas.values()) {
      input.removeAttribute("aria-invalid");
      error.hidden = true;
      error.textContent = "";
    }
  }

  function mostrarErrores(errores, mensaje = "Revisa estos campos:") {
    limpiarErrores();
    const claves = Object.keys(errores);
    if (!claves.length) return;
    const ajenos = [];
    for (const clave of claves) {
      const entrada = entradas.get(clave);
      if (!entrada) { ajenos.push(`${clave}: ${errores[clave]}`); continue; }
      entrada.input.setAttribute("aria-invalid", "true");
      entrada.error.textContent = errores[clave];
      entrada.error.hidden = false;
    }
    resumen.replaceChildren(
      el("p", {}, el("strong", {}, mensaje)),
      el("ul", {}, claves.filter((k) => entradas.has(k)).map((k) =>
        el("li", {}, el("button", {
          type: "button", class: "link-btn",
          onclick: () => entradas.get(k).input.focus(),
        }, `${campo(k).etiqueta}: ${errores[k]}`))),
        ajenos.map((t) => el("li", {}, t))),
    );
    resumen.hidden = false;
    resumen.focus();
  }

  function aviso(texto, tipo = "aviso") {
    alertas.replaceChildren(el("p", { class: ["note", `note-${tipo}`] }, texto));
  }

  /* ---- save ----------------------------------------------------------- */

  async function onSubmit(event) {
    event.preventDefault();
    if (enVuelo || conflictoPendiente) return;

    const enviados = leer();
    const { cambios, errores } = cambiosDelFormulario(enviados, iniciales);
    if (Object.keys(errores).length) return mostrarErrores(errores);
    limpiarErrores();
    const confirma = base ? confirmados() : [];
    if (!Object.keys(cambios).length && !confirma.length) return pintarEstado("No hay cambios que guardar.");

    enVuelo = true;
    guardar.disabled = true;
    pintarEstado();
    const eraNuevo = !base;
    try {
      const respuesta = base
        ? await api.guardarBorrador(base.id, base.version, cambios, confirma)
        : await api.crearTerreno(cambios, intento.claveParaCuerpo(cambios));
      intento.completar();
      alertas.replaceChildren();
      rebasar(respuesta.terreno, enviados);
      onSaved?.(respuesta.terreno, { creado: eraNuevo, sucio: esSucio() });
    } catch (error) {
      await trasFallo(error, eraNuevo);
    } finally {
      enVuelo = false;
      guardar.disabled = conflictoPendiente;
      pintarEstado();
    }
  }

  async function trasFallo(error, eraNuevo) {
    if (error.status === 422) {
      const porCampo = erroresDeCampo(error.detalle);
      if (Object.keys(porCampo).length) mostrarErrores(porCampo, error.message);
      else aviso(error.message, "error");
    } else if (error.status === 409 && !eraNuevo) {
      await revisarConflicto();
    } else if (error.status === 409) {
      // The same key with another body: start a genuinely new attempt.
      intento.completar();
      aviso(`${error.message} Revisa los datos y vuelve a guardar.`, "error");
    } else if (error.status === 401) {
      aviso("Tu sesión terminó. Inicia sesión para guardar: lo que escribiste sigue aquí.", "error");
    } else if (error.red && eraNuevo) {
      aviso("No se pudo confirmar si el borrador se creó. Vuelve a guardar: se reutiliza la " +
        "misma solicitud, así que no se creará un duplicado.", "error");
    } else if (error.red) {
      await verificarTrasCorte();
    } else {
      aviso(error.message, "error");
    }
  }

  /* After a lost response the save may or may not have happened: reread
   * instead of resending blindly. */
  async function verificarTrasCorte() {
    try {
      const { terreno: actual } = await api.inventarioTerreno(base.id);
      if (actual.version === base.version) {
        aviso("No se guardó: no hubo conexión con el servidor. Tus cambios siguen aquí; " +
          "vuelve a intentarlo.", "error");
      } else {
        mostrarConflicto(actual, { incierto: true });
      }
    } catch {
      aviso("No hay conexión con el servidor y no se pudo comprobar si se guardó. Tus cambios " +
        "siguen aquí; vuelve a intentarlo cuando haya conexión.", "error");
    }
  }

  /** Accept the server's version as the new base, keeping anything typed since. */
  function rebasar(nuevo, enviados) {
    const nuevos = textosIniciales(nuevo.draft);
    for (const c of CAMPOS) {
      if (leerUno(c.clave) === enviados[c.clave]) escribir(c.clave, nuevos[c.clave]);
    }
    for (const caja of Object.values(confirmar)) caja.checked = false;
    base = nuevo;
    iniciales = nuevos;
    pintarCabecera();
    pintarAyudas();
  }

  /* ---- conflicts ------------------------------------------------------ */

  async function revisarConflicto() {
    try {
      const { terreno: actual } = await api.inventarioTerreno(base.id);
      mostrarConflicto(actual);
    } catch (error) {
      aviso(`Otra persona guardó cambios en este terreno y no se pudo cargar la versión ` +
        `actual (${error.message}). Tus cambios siguen aquí.`, "error");
    }
  }

  function mostrarConflicto(actual, { incierto = false } = {}) {
    const { cambios } = cambiosDelFormulario(leer(), iniciales);
    const { delServidor, choques } = analizarConflicto(base.draft, actual.draft, cambios);
    conflictoPendiente = true;
    guardar.disabled = true;
    pintarEstado();

    const quien = actual.updated_by?.display_name ?? actual.updated_by ?? null;
    const valor = (clave, draft) => mostrarValor(campo(clave), draft[clave]);
    const ciclo = actual.publication_state !== base.publication_state || actual.archived_at
      ? `Su estado ahora es «${estadoPublicacion(actual).etiqueta}».` : null;

    alertas.replaceChildren(el("section", { class: "conflicto note note-aviso" },
      el("h2", { class: "conflicto-titulo" }, incierto
        ? "No se pudo confirmar tu guardado y el servidor tiene una versión más nueva"
        : "Otra persona guardó este terreno mientras lo editabas"),
      el("p", {},
        `Tu formulario parte de la versión ${base.version}; la actual es la ${actual.version}`,
        quien ? `, guardada por ${quien}` : "", ". Nada se sobrescribió."),
      ciclo && el("p", {}, el("strong", {}, ciclo)),
      delServidor.length
        ? el("ul", { class: "diff-list" }, delServidor.map((clave) =>
          el("li", { class: "diff" },
            el("span", { class: "diff-campo" }, campo(clave).etiqueta),
            el("span", { class: "diff-anterior" }, valor(clave, base.draft)),
            el("span", { class: "diff-flecha", "aria-hidden": "true" }, "→"),
            el("span", { class: "diff-nuevo" }, valor(clave, actual.draft),
              choques.includes(clave) ? el("span", { class: "conflicto-tuyo" },
                ` · tu valor: ${mostrarTexto(campo(clave), leerUno(clave))}`) : null),
          )))
        : el("p", { class: "secondary" }, "Los campos de este formulario no cambiaron; cambió el estado o la versión del terreno."),
      el("div", { class: "screen-actions" },
        el("button", {
          type: "button", class: "btn btn-principal", onclick: () => conservarMios(actual, choques),
        }, "Revisar cambios"),
        el("button", {
          type: "button", class: "btn btn-quiet", onclick: () => recargarActual(actual),
        }, "Recargar versión actual"),
      ),
    ));
    alertas.querySelector("button")?.focus();
  }

  /* Rebase on the newer version: their changes fill the fields we did not
   * touch, ours stay, and every field both of us changed is marked. */
  function conservarMios(actual, choques) {
    const { cambios } = cambiosDelFormulario(leer(), iniciales);
    const nuevos = textosIniciales(actual.draft);
    for (const c of CAMPOS) if (!(c.clave in cambios)) escribir(c.clave, nuevos[c.clave]);
    base = actual;
    iniciales = nuevos;
    conflictoPendiente = false;
    guardar.disabled = false;
    for (const clave of choques) marcarChoque(clave, nuevos[clave]);
    pintarCabecera();
    pintarAyudas();
    pintarEstado();
    aviso(choques.length
      ? `El formulario ya parte de la versión ${actual.version}. Conservamos tus valores; ` +
        "revisa los campos marcados y vuelve a guardar."
      : `El formulario ya parte de la versión ${actual.version} con tus cambios encima. ` +
        "Revísalo y vuelve a guardar.");
    (choques.length ? entradas.get(choques[0]).input : guardar).focus();
  }

  function marcarChoque(clave, textoServidor) {
    const { fila, extra } = entradas.get(clave);
    fila.classList.add("is-conflicto");
    extra.replaceChildren(el("p", { class: "field-help field-warn" },
      `En el servidor: ${mostrarTexto(campo(clave), textoServidor)} `,
      el("button", {
        type: "button", class: "link-btn",
        onclick: () => {
          escribir(clave, textoServidor);
          fila.classList.remove("is-conflicto");
          extra.replaceChildren();
          pintarEstado();
          pintarAyudas();
        },
      }, "Usar este valor")));
  }

  async function recargarActual(actual) {
    if (esSucio()) {
      const ok = await confirmDialog({
        titulo: "Recargar versión actual",
        mensaje: "Se descartarán los cambios que escribiste y el formulario mostrará la versión " +
          `${actual.version}.`,
        confirmar: "Descartar y recargar",
        peligro: true,
      });
      if (!ok) return;
    }
    base = actual;
    iniciales = textosIniciales(actual.draft);
    rellenar();
    for (const caja of Object.values(confirmar)) caja.checked = false;
    for (const { fila, extra } of entradas.values()) { fila.classList.remove("is-conflicto"); extra.replaceChildren(); }
    conflictoPendiente = false;
    guardar.disabled = false;
    alertas.replaceChildren();
    limpiarErrores();
    pintarCabecera();
    pintarAyudas();
    pintarEstado();
  }

  /* ---- wiring --------------------------------------------------------- */

  const alCambiar = () => { pintarEstado(); pintarAyudas(); };
  form.addEventListener("input", alCambiar);
  form.addEventListener("change", alCambiar);
  form.addEventListener("submit", onSubmit);
  cerrar.addEventListener("click", () => onClose?.());
  historial.addEventListener("click", () => base && onHistory?.(base));
  vistaPrevia.addEventListener("click", () => {
    if (!base) return;
    if (esSucio() || conflictoPendiente) {
      aviso("Guarda el borrador antes de la vista previa: solo se publica lo guardado.", "aviso");
      return;
    }
    onPreview?.(base);
  });

  rellenar();
  pintarCabecera();
  pintarAyudas();
  pintarEstado();

  return {
    element,
    get id() { return base?.id ?? null; },
    get dirty() { return esSucio(); },
    focus() { entradas.get("terreno").input.focus(); },
    destroy() {
      medirBarra?.disconnect();
      document.documentElement.style.removeProperty("--editor-barra");
      element.remove();
    },
  };
}

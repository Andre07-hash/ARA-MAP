/* «Asistente IA» of the master table (issue #69): search the whole master
 * table by a question and compare two or three results. Administrators only,
 * and only when the server has the assistant on.
 *
 * It is a dialog of its own: the table's query, selection, scroll and file
 * widgets are never touched, and the detail of a result opens over it with
 * the existing detail dialog. Closing it forgets the search, the selection
 * and the comparison. Every server text is drawn with textContent; a result
 * of rules is never labelled as AI, and the factual table is kept apart from
 * Claude's summary.
 */

import { el } from "../../lib/dom.js";
import { CAMPOS_ENVIADOS, largo, leerConfig } from "../../lib/asistenteTerreno.js";
import { MAX_SELECCION, MIN_SELECCION, crearBusqueda } from "../../lib/asistenteMaestra.js";
import { openDialog } from "../ui/dialog.js";

const ESPERANDO = {
  buscando: "Interpretando la búsqueda…", paginando: "Cargando más resultados…", comparando: "Comparando…",
};
/* Comparison errors about the selection, in its own words. */
const DE_SELECCION = {
  404: "Un terreno elegido ya no existe o ya no está disponible. Vuelve a buscar y elegir.",
  409: "Un terreno elegido cambió mientras se comparaba. Vuelve a buscar para ver sus datos actuales.",
};
const RESUMEN_FALLIDO = {
  chat_tiempo: "el asistente tardó demasiado",
  chat_limite: "hay otra consulta en curso o se alcanzó el límite por hora",
  chat_presupuesto: "se agotó el presupuesto aprobado",
  chat_no_configurado: "el asistente no está configurado en el servidor",
  chat_respuesta_invalida: "la respuesta no era válida",
};

/**
 * `abrirDetalle(id, signal)` opens a result's detail, and must open nothing
 * once `signal` is aborted (the panel closed meanwhile); `nombreDeBase(id)`
 * names a base locally. Returns { boton, mostrar(visible), cerrar(), destroy() }.
 */
export function montarAsistenteMaestra({ abrirDetalle, nombreDeBase = () => null }) {
  const config = new AbortController();
  let ajustes = null;
  let visible = false;
  let vivo = true;
  let abierto = null;           // { close, busqueda }

  const boton = el("button", { type: "button", class: "btn btn-quiet", hidden: true,
    "aria-haspopup": "dialog", onclick: () => abrir() }, "Asistente IA");
  leerConfig(config.signal).then((c) => {
    if (!vivo || !c.habilitado) return;
    ajustes = c;
    boton.hidden = !visible;
  }).catch(() => {});

  function abrir() {
    if (!ajustes || abierto) return;
    const panel = construir();
    const { dialog, close } = openDialog({
      titulo: "Asistente IA de la tabla maestra", ancho: "52rem", contenido: panel.nodo,
      acciones: [{ etiqueta: "Cerrar", onClick: (c) => c() }],
    });
    dialog.classList.add("asistente-maestra-dialogo");
    abierto = { close, panel };
    dialog.addEventListener("close", () => {
      panel.destroy();
      abierto = null;
      if (vivo && boton.isConnected && !boton.hidden) boton.focus();
    });
    panel.enfocar();
  }

  /* ------------------------------------------------------------ the panel */

  function construir() {
    const busqueda = crearBusqueda({ onCambio: pintar });
    // A detail asked for from this panel opens only while the panel is open.
    const detalles = new AbortController();
    const aviso = el("p", { class: "asistente-terreno-aviso" },
      "Al buscar, el servidor envía a Claude (Anthropic) sólo tu pregunta y la lista fija de filtros " +
      "admitidos, ningún terreno. Al comparar, envía sólo estos campos registrados de los terrenos elegidos, " +
      `nombrados Terreno A, B o C: ${CAMPOS_ENVIADOS.join(", ")}. Los nombres, las bases, la dirección exacta, ` +
      "las coordenadas, contactos, notas y archivos se quedan aquí. Lo que escribas en la pregunta sí se envía: " +
      "no incluyas información sensible; no se detecta automáticamente.");
    const pregunta = el("textarea", { id: "asistente-maestra-pregunta", class: "input", rows: "2",
      autocomplete: "off", maxlength: String(ajustes.max_pregunta),
      placeholder: "Por ejemplo: terrenos industriales en Jalisco de más de 10,000 m²" });
    const btnBuscar = el("button", { type: "submit", class: "btn btn-small btn-principal" }, "Buscar");
    const formulario = el("form", { class: "asistente-terreno-pregunta", novalidate: true },
      el("label", { class: "field-label", for: pregunta.id }, "¿Qué terrenos buscas?"), pregunta,
      el("div", { class: "asistente-terreno-enviar" }, btnBuscar));
    formulario.addEventListener("submit", (event) => {
      event.preventDefault();
      const valor = pregunta.value.trim();
      if (!valor) { decir("Escribe qué terrenos buscas."); return; }
      if (largo(valor) > ajustes.max_pregunta) { decir(`La pregunta admite hasta ${ajustes.max_pregunta} caracteres.`); return; }
      busqueda.buscar(valor);
    });
    pregunta.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        formulario.requestSubmit();
      }
    });
    const estadoNodo = el("div", { class: "asistente-terreno-estado", role: "status", "aria-live": "polite" });
    const resultadosNodo = el("section", { class: "asistente-maestra-resultados", "aria-label": "Resultados" });
    const comparacionNodo = el("section", { class: "asistente-maestra-comparacion", "aria-label": "Comparación" });
    const nodo = el("div", { class: "asistente-maestra" }, aviso,
      ...(ajustes.disponible ? [formulario] : []), estadoNodo, resultadosNodo, comparacionNodo);
    if (!ajustes.disponible) decir("El asistente no está configurado en el servidor.");

    function decir(mensaje) {
      estadoNodo.replaceChildren(el("p", { class: "field-error", role: "alert" }, mensaje));
    }

    let pintados = null;          // the busqueda object last drawn, to redraw only on change
    let comparada = null;
    function pintar(s) {
      const ocupado = s.fase !== "inactivo";
      btnBuscar.setAttribute("aria-disabled", String(ocupado));
      formulario.setAttribute("aria-busy", String(ocupado));
      if (ocupado) {
        estadoNodo.replaceChildren(el("p", { class: "asistente-terreno-esperando" }, ESPERANDO[s.fase]),
          el("button", { type: "button", class: "btn btn-small btn-quiet", onclick: () => busqueda.dejarDeEsperar() },
            "Dejar de esperar"),
          el("p", { class: "secondary asistente-terreno-nota" },
            "Si dejas de esperar o cierras, la respuesta se descarta; la consulta puede terminar en el servidor."));
      } else if (s.error) {
        const propio = s.error.de === "comparando" ? DE_SELECCION[s.error.status] : null;
        estadoNodo.replaceChildren(el("p", { class: "field-error", role: "alert" }, propio ?? s.error.mensaje));
      } else {
        estadoNodo.replaceChildren();
      }
      if (s.busqueda !== pintados) { pintados = s.busqueda; pintarResultados(s); }
      else marcarSeleccion(s);
      if (s.comparacion !== comparada) { comparada = s.comparacion; pintarComparacion(s.comparacion); }
    }

    function pintarResultados(s) {
      const b = s.busqueda;
      barra = null;
      if (!b) { resultadosNodo.replaceChildren(); return; }
      if (b.estado === "aclaracion") {
        resultadosNodo.replaceChildren(el("div", { class: "asistente-maestra-aclaracion" },
          el("p", {}, b.aclaracion),
          el("p", { class: "secondary" }, (b.origen === "modelo" ? "Aclaración del asistente (Claude). "
            : "Aclaración del programa, sin IA. ") + "No se buscó nada: reformula la consulta completa.")));
        return;
      }
      const lista = el("ol", { class: "asistente-maestra-lista" }, b.terrenos.map((t) => fila(t)));
      resultadosNodo.replaceChildren(
        el("div", { class: "asistente-maestra-criterios" },
          el("p", { class: "field-label" }, "Criterios interpretados por Claude"),
          el("ul", {}, b.criterios.map((c) => el("li", {}, c)))),
        el("p", { class: "asistente-maestra-total" },
          b.total === 1 ? "1 terreno coincide." : `${b.total.toLocaleString("es-MX")} terrenos coinciden.`,
          b.total ? ` Mostrando ${b.terrenos.length.toLocaleString("es-MX")}.` : ""),
        b.total ? lista : el("p", { class: "secondary" }, "Ningún terreno cumple estos criterios."),
        b.next_cursor && el("button", { type: "button", class: "btn btn-small btn-quiet asistente-maestra-mas",
          onclick: () => busqueda.mas() }, "Más resultados"),
        b.total > 0 && el("p", { class: "secondary asistente-terreno-nota" },
          "Cada página se lee del inventario al pedirla: si otras personas editan, la lista puede cambiar."),
        b.total > 0 && barraComparar(),
      );
      marcarSeleccion(s);
    }

    function fila(t) {
      const id = `asistente-maestra-${t.terreno_id}`;
      const valor = (campo) => t.campos_usados.find((c) => c.campo === campo)?.valor;
      const base = t.base_id ? (nombreDeBase(t.base_id) ?? "Base") : "Sin base asignada";
      const datos = [valor("estado"), valor("municipio"), valor("tipo_terreno"), valor("superficie_m2"),
        valor("asking_price")].filter(Boolean).join(" · ");
      return el("li", { class: "asistente-maestra-fila", dataset: { id: t.terreno_id } },
        el("input", { type: "checkbox", id, class: "asistente-maestra-elegir",
          onchange: (e) => { if (!busqueda.alternar(t.terreno_id)) e.target.checked = !e.target.checked; } }),
        el("label", { for: id, class: "asistente-maestra-nombre" }, t.nombre),
        el("span", { class: "secondary asistente-maestra-datos" }, `${base}${datos ? ` · ${datos}` : ""}`),
        el("button", { type: "button", class: "btn btn-small btn-quiet", onclick: () => abrirDetalle(t.terreno_id, detalles.signal) },
          "Ver detalle"));
    }

    let barra = null;
    function barraComparar() {
      barra = {
        texto: el("span", { class: "secondary", "aria-live": "polite" }),
        boton: el("button", { type: "button", class: "btn btn-small btn-principal",
          onclick: () => busqueda.comparar() }, "Comparar seleccionados"),
      };
      return el("div", { class: "asistente-maestra-barra" }, barra.texto, barra.boton);
    }

    function marcarSeleccion(s) {
      const elegidos = new Set(s.seleccion.map((t) => t.terreno_id));
      for (const caja of resultadosNodo.querySelectorAll(".asistente-maestra-elegir")) {
        const id = caja.closest("li").dataset.id;
        caja.checked = elegidos.has(id);
        caja.disabled = !elegidos.has(id) && elegidos.size >= MAX_SELECCION;
      }
      if (!barra) return;
      const n = s.seleccion.length;
      barra.texto.textContent = `Elegidos para comparar: ${n} de ${MAX_SELECCION} (mínimo ${MIN_SELECCION}).`;
      barra.boton.setAttribute("aria-disabled", String(n < MIN_SELECCION || s.fase !== "inactivo"));
    }

    function pintarComparacion(c) {
      if (!c) { comparacionNodo.replaceChildren(); return; }
      const nombre = (t) => `${t.nombre} (${t.base_id ? (nombreDeBase(t.base_id) ?? "Base") : "Sin base asignada"})`;
      const tabla = el("table", { class: "asistente-maestra-tabla" },
        el("caption", { class: "secondary" }, "Datos registrados, sin cálculos ni conversiones."),
        el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Campo"),
          c.terrenos.map((t) => el("th", { scope: "col", title: nombre(t) }, `Terreno ${t.alias}`)))),
        el("tbody", {}, c.filas.map((f) => el("tr", {}, el("th", { scope: "row" }, f.etiqueta),
          f.valores.map((v) => el("td", { class: v === "Sin información registrada" ? "secondary" : null }, v))))));
      const resumen = c.resumen.estado === "ok"
        ? el("div", { class: "asistente-maestra-resumen" },
          el("p", { class: "asistente-terreno-texto" }, c.resumen.texto),
          el("p", { class: "secondary asistente-terreno-origen" },
            "Resumen generado con IA (Claude) a partir de la tabla. Revísalo antes de usarlo."))
        : el("p", { class: "field-error", role: "alert" },
          `No se pudo generar el resumen: ${RESUMEN_FALLIDO[c.resumen.codigo] ?? "el servicio de IA no está disponible"}. ` +
          "La tabla muestra los datos registrados.");
      comparacionNodo.replaceChildren(
        el("h3", { class: "asistente-terreno-titulo" }, "Comparación"),
        el("ul", { class: "asistente-maestra-leyenda" }, c.terrenos.map((t) =>
          el("li", {}, el("strong", {}, `Terreno ${t.alias}: `), nombre(t)))),
        tabla,
        c.advertencias.length > 0 && el("ul", { class: "asistente-terreno-advertencias" },
          c.advertencias.map((a) => el("li", {}, a))),
        resumen);
    }

    return {
      nodo,
      enfocar: () => (ajustes.disponible ? pregunta : nodo).focus?.(),
      destroy: () => { detalles.abort(); busqueda.destroy(); },
    };
  }

  return {
    boton,
    /** Shown only in the master table, as a grid. Hiding it closes the panel. */
    mostrar(si) {
      visible = Boolean(si);
      boton.hidden = !(visible && ajustes);
      if (!visible) abierto?.close();
    },
    cerrar() { abierto?.close(); },
    destroy() {
      if (!vivo) return;
      vivo = false;
      config.abort();
      abierto?.close();
      abierto = null;
    },
  };
}

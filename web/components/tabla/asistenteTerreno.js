/* «Asistente IA» in the table's record detail (issue #65): administrators
 * only, and only when the server says the feature is on.
 *
 * It lives inside the detail dialog and touches nothing else: opening or
 * closing it never repaints the grid, its scroll, filters or file widgets.
 * One terrain per panel; closing the detail (or the session, or the view)
 * destroys it with whatever is pending and every answer it holds.
 *
 * Every text from the server is put on screen with textContent, never as
 * markup, and nothing in an answer becomes a link. A generated answer is a
 * draft to review, and says so; an answer the program computed by rules is
 * never labelled as AI.
 */

import { el } from "../../lib/dom.js";
import {
  ACCIONES, CAMPOS_ENVIADOS, crearAsistente, etiquetaDeAccion, largo, leerConfig,
} from "../../lib/asistenteTerreno.js";

let paneles = 0;

/**
 * Mount the entry point. `boton` is appended by the caller next to the
 * detail's actions; `panel` below them. Nothing is visible until the
 * configuration arrives and says the assistant is on.
 */
export function montarAsistente({ terreno }) {
  const id = `asistente-terreno-${paneles += 1}`;
  const config = new AbortController();
  let asistente = null;
  let ajustes = null;
  let vivo = true;

  const boton = el("button", {
    type: "button", class: "btn btn-small btn-quiet", hidden: true,
    "aria-expanded": "false", "aria-controls": id,
  }, "Asistente IA");
  const panel = el("section", { id, class: "asistente-terreno", hidden: true, "aria-labelledby": `${id}-titulo` });

  leerConfig(config.signal).then((c) => {
    if (!vivo || !c.habilitado) return;
    ajustes = c;
    boton.hidden = false;
  }).catch(() => {});      // cancelled, or no answer: the entry point stays hidden

  boton.addEventListener("click", () => {
    if (panel.hidden) abrir(); else cerrarPanel();
  });

  /* ------------------------------------------------------------ panel */

  const titulo = el("h3", { id: `${id}-titulo`, class: "asistente-terreno-titulo", tabindex: "-1" }, "Asistente IA");
  const contexto = el("p", { class: "asistente-terreno-contexto secondary" });
  const aviso = el("p", { class: "asistente-terreno-aviso" });
  // aria-disabled, not disabled, while waiting: a disabled button drops the
  // keyboard focus to the page. The controller refuses a second request anyway.
  const sugeridas = el("div", { class: "asistente-terreno-acciones" },
    ACCIONES.map(({ accion, etiqueta }) => el("button", {
      type: "button", class: "btn btn-small btn-quiet", dataset: { accion },
      onclick: () => asistente?.pedir(accion),
    }, etiqueta)));
  const pregunta = el("textarea", {
    id: `${id}-pregunta`, class: "input", rows: "2", autocomplete: "off",
    placeholder: "Por ejemplo: ¿qué datos de precio tiene registrados?",
  });
  const contador = el("span", { class: "asistente-terreno-contador secondary", "aria-live": "polite" });
  const preguntar = el("button", { type: "submit", class: "btn btn-small btn-principal" }, "Preguntar");
  const formulario = el("form", { class: "asistente-terreno-pregunta", novalidate: true },
    el("label", { class: "field-label", for: `${id}-pregunta` }, "Pregunta sobre este terreno"),
    pregunta, el("div", { class: "asistente-terreno-enviar" }, contador, preguntar));
  const estado = el("div", { class: "asistente-terreno-estado", role: "status", "aria-live": "polite" });
  const historial = el("ol", { class: "asistente-terreno-respuestas", "aria-label": "Respuestas" });

  formulario.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!asistente || asistente.ocupado) return;
    const valor = pregunta.value.trim();
    if (!valor) { decirError("Escribe una pregunta."); pregunta.focus(); return; }
    if (largo(valor) > ajustes.max_pregunta) {
      decirError(`La pregunta admite hasta ${ajustes.max_pregunta} caracteres.`);
      pregunta.focus();
      return;
    }
    if (asistente.pedir("pregunta", valor)) pregunta.value = "";
    contar();
  });
  pregunta.addEventListener("input", () => contar());
  pregunta.addEventListener("keydown", (event) => {
    // Enter sends, Shift+Enter breaks the line, as in a chat box.
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      formulario.requestSubmit();
    }
  });

  function contar() {
    if (!ajustes) return;
    const n = largo(pregunta.value);
    contador.textContent = `${n} / ${ajustes.max_pregunta}`;
    contador.classList.toggle("asistente-terreno-excedido", n > ajustes.max_pregunta);
  }

  function decirError(mensaje, reintento) {
    estado.replaceChildren(el("p", { class: "field-error", role: "alert" }, mensaje),
      ...(reintento ? [el("button", { type: "button", class: "btn btn-small btn-quiet", onclick: reintento }, "Reintentar")] : []));
  }

  function abrir() {
    if (!ajustes) return;
    asistente = crearAsistente({ terrenoId: terreno.id, version: terreno.version, onCambio: pintar });
    contexto.textContent = `${terreno.draft?.terreno || "Terreno sin nombre"} · versión ${terreno.version}`;
    aviso.replaceChildren(
      "Al consultar, el servidor envía a Claude (Anthropic) tu pregunta y sólo estos campos registrados: ",
      CAMPOS_ENVIADOS.join(", "),
      ". No se envían el nombre, la dirección exacta ni las coordenadas, ni contactos, notas o archivos. " +
      "Evita escribir información sensible en la pregunta. Cada consulta es independiente: no se reenvían " +
      "las anteriores.",
    );
    pregunta.maxLength = ajustes.max_pregunta;
    pregunta.value = "";
    contar();
    panel.replaceChildren(titulo, contexto, aviso,
      ...(ajustes.disponible ? [sugeridas, formulario] : []),
      estado, historial);
    pintar(asistente.estado);
    if (!ajustes.disponible) decirError("El asistente no está configurado en el servidor.");
    panel.hidden = false;
    boton.setAttribute("aria-expanded", "true");
    titulo.focus();
  }

  /** Hide and forget: what is pending is dropped and the answers are gone. */
  function cerrarPanel({ devolverFoco = true } = {}) {
    asistente?.destroy();
    asistente = null;
    panel.hidden = true;
    panel.replaceChildren();
    historial.replaceChildren();
    estado.replaceChildren();
    pregunta.value = "";
    boton.setAttribute("aria-expanded", "false");
    if (devolverFoco && boton.isConnected) boton.focus();
  }

  /* ------------------------------------------------------------ paint */

  function pintar(s) {
    if (!vivo || !asistente) return;
    const esperando = s.fase === "esperando";
    for (const b of [...sugeridas.children, preguntar]) b.setAttribute("aria-disabled", String(esperando));
    formulario.setAttribute("aria-busy", String(esperando));
    if (esperando) {
      estado.replaceChildren(
        el("p", { class: "asistente-terreno-esperando" },
          `Consultando: ${etiquetaDeAccion(s.pendiente.accion).toLowerCase()}…`),
        el("button", { type: "button", class: "btn btn-small btn-quiet", onclick: () => asistente?.dejarDeEsperar() },
          "Dejar de esperar"),
        el("p", { class: "secondary asistente-terreno-nota" },
          "Si dejas de esperar o cierras, la respuesta se descarta; la consulta puede terminar en el servidor."),
      );
    } else if (s.error) {
      decirError(s.error.mensaje, s.error.reintentable ? () => asistente?.reintentar() : null);
    } else if (ajustes.disponible) {
      estado.replaceChildren();
    }
    // Only new answers are drawn, newest first; earlier ones stay as they were.
    const ultima = Number(historial.firstElementChild?.dataset.n ?? 0);
    for (const entrada of s.entradas) if (entrada.n > ultima) historial.prepend(respuesta(entrada));
    while (historial.childElementCount > s.entradas.length) historial.lastElementChild.remove();
  }

  function respuesta(e) {
    const texto = el("p", { class: "asistente-terreno-texto" });
    texto.textContent = e.respuesta;
    const copiar = el("button", { type: "button", class: "btn btn-small btn-quiet" }, "Copiar borrador");
    copiar.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(e.respuesta);
        copiar.textContent = "Copiado";
      } catch { copiar.textContent = "No se pudo copiar"; }
    });
    const origen = e.origen === "modelo"
      ? "Borrador generado con IA (Claude). Revísalo antes de usarlo."
      : "Calculado por el programa con reglas, sin IA.";
    const campos = el("details", { class: "asistente-terreno-campos" },
      el("summary", {}, `Campos consultados (${e.campos_usados.length})`),
      e.campos_usados.length
        ? el("dl", { class: "detalle-datos" }, e.campos_usados.map((c) => [el("dt", {}, c.etiqueta), el("dd", {}, c.valor)]))
        : el("p", { class: "secondary" }, "Ninguno."));
    return el("li", { class: "asistente-terreno-respuesta", dataset: { n: e.n, accion: e.accion, origen: e.origen } },
      el("p", { class: "asistente-terreno-pedido" },
        e.accion === "pregunta" ? `Pregunta: ${e.pregunta}` : etiquetaDeAccion(e.accion)),
      texto,
      e.faltantes.length > 0 && el("div", { class: "asistente-terreno-faltantes" },
        el("p", {}, "Sin información registrada:"),
        el("ul", {}, e.faltantes.map((f) => el("li", {}, f.etiqueta))),
        el("p", { class: "secondary" }, "«Sin información registrada» no significa que el dato no exista.")),
      e.advertencias.length > 0 && el("ul", { class: "asistente-terreno-advertencias" },
        e.advertencias.map((a) => el("li", {}, a))),
      el("p", { class: "asistente-terreno-origen secondary" }, `Basado en los datos registrados. ${origen}`),
      campos,
      el("div", { class: "asistente-terreno-copiar" }, copiar),
    );
  }

  return {
    boton,
    panel,
    /** The detail is going away: cancel, forget, and let nothing paint again. */
    destroy() {
      if (!vivo) return;
      config.abort();
      cerrarPanel({ devolverFoco: false });
      vivo = false;
      ajustes = null;
    },
  };
}

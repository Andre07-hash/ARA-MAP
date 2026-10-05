/* The import assistant: upload -> analysis -> (questions) -> review -> import.
 *
 * One dialog, updated in place. The manager never picks an algorithm, a model
 * or a format: analysis runs by itself, questions appear only when something
 * is genuinely unclear, and a clear file goes straight to the review.
 *
 * Nothing is written until "Importar"/"Agregar". Every correction produces a
 * new server revision and a new preview; saving is disabled while a preview is
 * missing or being rebuilt, and corrections are queued so the newest wins.
 */

import { api } from "../../lib/api.js";
import {
  aRespuestas, conservarRespuestas, createCorrectionQueue, todasRespondidas, vistaConsumida,
} from "../../lib/asistente.js";
import { append, clear, el } from "../../lib/dom.js";
import { plural } from "../../lib/format.js";
import { FolderSelect } from "../folders/FolderDialogs.js";
import { openDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";
import {
  Analizando, Correcciones, Detalles, ErrorArchivo, Preguntas, VistaPrevia,
} from "./AssistantViews.js";
import { PreviewMap } from "./PreviewMap.js";

/**
 * modo "nueva": create a base (carpetas/carpetaInicial choose its folder).
 * modo "agregar": append to `base`, keeping its folder and conflict choices.
 * Resolves with the created base / append result, or null if cancelled.
 */
export function runAssistant(file, { modo, base = null, carpetas = [], carpetaInicial = null, onDone }) {
  return new Promise((resolve) => {
    let data = null;              // the latest server response
    let error = null;
    let cargando = true;
    let respuestas = {};
    let nombre = null;
    let recordar = true;
    let resoluciones = {};
    let abiertos = { correcciones: false, detalles: false };
    let mapa = null;
    let mapaToken = null;
    let settled = false;
    const finish = (valor) => { if (!settled) { settled = true; resolve(valor); } };

    const cuerpo = el("div", { class: "assistant", "aria-live": "polite" });
    const pie = el("div", { class: "assistant-footer" });
    const destino = modo === "nueva" ? FolderSelect({ id: "carpeta-base", carpetas, value: carpetaInicial }) : null;

    const { dialog, close } = openDialog({
      titulo: modo === "agregar" ? `Agregar a «${base.nombre}»` : "Importar base",
      descripcion: file.name,
      contenido: el("div", {}, cuerpo, pie),
      ancho: "62rem",
      acciones: [],
    });
    dialog.addEventListener("close", () => { mapa?.destruir(); finish(null); });

    const cola = createCorrectionQueue((correcciones) => enviar({ correcciones }));

    async function enviar(payload) {
      cargando = true;
      render();
      try {
        aplicar(await api.preparar({ borrador: data.borrador, revision: data.revision, ...payload }));
      } catch (e) {
        error = e.status === 410 ? "El análisis expiró. Cierra y vuelve a seleccionar el archivo." : e.message;
        if (e.status === 410) data = null;
      } finally {
        cargando = false;
        render();
      }
    }

    function aplicar(respuesta) {
      data = respuesta;
      error = respuesta.error ?? null;
      respuestas = conservarRespuestas(respuestas, respuesta.preguntas);
      resoluciones = {};
      if (nombre === null && respuesta.vista_previa) nombre = respuesta.vista_previa.nombre_sugerido;
    }

    /* ------------------------------------------------------------ render */

    function render() {
      const foco = document.activeElement;
      const idFoco = foco && dialog.contains(foco) ? foco.id : "";
      const scroller = cuerpo.closest(".dialog-body");
      const scroll = scroller?.scrollTop ?? 0;

      renderCuerpo();
      renderPie();

      if (idFoco) document.getElementById(idFoco)?.focus();
      if (scroller) scroller.scrollTop = scroll;
      mapa?.montar();
    }

    function renderCuerpo() {
      if (!data) {
        cuerpo.replaceChildren(cargando ? Analizando() : ErrorArchivo(error ?? "No se pudo analizar el archivo."));
        return;
      }
      const vista = data.vista_previa;
      if (vista && vista.token !== mapaToken) {
        mapa?.destruir();
        mapa = PreviewMap(vista.puntos);
        mapaToken = vista.token;
      }
      cuerpo.setAttribute("aria-busy", String(cargando));
      // append() skips the false/null of conditional pieces; replaceChildren
      // would print them as text.
      append(clear(cuerpo), [
        cargando && el("p", { class: "assistant-updating", role: "status" }, "Actualizando la vista previa…"),
        error && ErrorArchivo(error),
        data.estado === "preguntas" && Preguntas({
          preguntas: data.preguntas, respuestas,
          onChange: (id, opcion) => { respuestas = { ...respuestas, [id]: opcion }; renderPie(); },
        }),
        vista && Datos(vista),
        vista && VistaPrevia({
          vista, modo, resoluciones, mapa, interpretacion: data.interpretacion,
          onCorregir: (parche) => { cola.push(parche); cola.idle().then(renderPie); },
        }),
        Correcciones({
          interpretacion: data.interpretacion, formato: vista?.formato ?? formatoArchivo(),
          abierto: abiertos.correcciones || data.estado === "revisar",
          onToggle: (abierto) => { abiertos = { ...abiertos, correcciones: abierto }; },
          // The queue reports idle only after its last request settles, so
          // the footer (and the import button) is redrawn at that moment.
          onCorregir: (parche) => { cola.push(parche); cola.idle().then(renderPie); },
        }),
        Detalles({
          interpretacion: data.interpretacion, abierto: abiertos.detalles,
          onToggle: (abierto) => { abiertos = { ...abiertos, detalles: abierto }; },
        }),
        data.interpretacion.asistencia_configurada && el("p", { class: "assistant-privacy muted" },
          "Privacidad: para interpretar columnas que no reconoce, ARA puede enviar a un servicio " +
          "externo los encabezados, un resumen de los valores y hasta 3 valores cortos de esas " +
          "columnas. Nunca el archivo completo, ni datos de contacto o notas."),
      ]);
    }

    const formatoArchivo = () => (/\.csv$/i.test(file.name) ? "csv" : "xlsx");

    function Datos(vista) {
      if (modo !== "nueva") return Recordar();
      const input = el("input", {
        class: "input", id: "nombre-base", value: nombre ?? vista.nombre_sugerido,
        oninput: (e) => { nombre = e.target.value; },
      });
      return el("div", { class: "assistant-fields" },
        el("div", { class: "field-pair" },
          el("div", { class: "rail-field" },
            el("label", { class: "field-label", for: "nombre-base" }, "Nombre de la base"), input),
          destino.element),
        Recordar(),
      );
    }

    function Recordar() {
      return el("label", { class: "check assistant-remember", for: "recordar-formato" },
        el("input", {
          type: "checkbox", id: "recordar-formato", checked: recordar,
          onchange: (e) => { recordar = e.target.checked; },
        }),
        el("span", {}, "Recordar este formato para la próxima vez"));
    }

    function renderPie() {
      const cerrar = data?.estado === "consumida" ? "Cerrar" : "Cancelar";
      const botones = [el("button", { type: "button", class: "btn btn-quiet", onclick: () => close() }, cerrar)];
      if (data?.estado === "preguntas") {
        botones.push(el("button", {
          type: "button", class: "btn btn-principal", id: "assistant-continuar",
          disabled: cargando || !todasRespondidas(data.preguntas, respuestas),
          onclick: () => enviar({ respuestas: aRespuestas(respuestas) }),
        }, "Continuar"));
      } else if (data?.estado === "vista_previa") {
        const vista = data.vista_previa;
        botones.push(el("button", {
          type: "button", class: "btn btn-principal", id: "assistant-importar",
          disabled: cargando || cola.ocupado,
          onclick: confirmar,
        }, modo === "agregar" ? "Agregar" : `Importar ${plural(vista.conteo, "terreno")}`));
      }
      pie.replaceChildren(...botones);
    }

    /* ----------------------------------------------------------- commit */

    async function confirmar() {
      await cola.idle();
      const vista = data?.vista_previa;
      if (!vista || cargando) return;
      cargando = true;
      renderPie();
      try {
        if (modo === "agregar") {
          const result = await api.appendToBase(base.id, {
            token: vista.token, resoluciones, recordar_formato: recordar,
          });
          toast(
            `${plural(result.agregados, "terreno agregado", "terrenos agregados")}` +
            (result.actualizados ? `, ${result.actualizados} actualizados` : "") +
            (result.omitidos ? `, ${result.omitidos} omitidos` : "") + "."
          );
          close();
          onDone?.(result.base);
          finish(result);
        } else {
          const result = await api.confirmImport({
            token: vista.token, nombre: (nombre ?? vista.nombre_sugerido).trim(),
            carpeta_id: destino.value(), recordar_formato: recordar,
          });
          toast(`Se importó «${result.base.nombre}» con ${plural(result.base.conteo, "terreno")}.`);
          close();
          onDone?.(result.base);
          finish(result.base);
        }
      } catch (e) {
        toastError(e.message);
        cargando = false;
        if (vistaConsumida(e)) {
          // Nothing was imported and this preview cannot be confirmed again.
          data = { ...data, estado: "consumida" };
          error = `${e.message} Esta vista previa ya no se puede usar: cierra y vuelve a seleccionar el archivo.`;
          render();
        } else {
          renderPie();
        }
      }
    }

    api.analizar(file, modo === "agregar" ? base.id : null)
      .then((respuesta) => aplicar(respuesta))
      .catch((e) => { error = e.message; })
      .finally(() => { cargando = false; render(); });
    render();
  });
}

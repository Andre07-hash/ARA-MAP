/* File widgets for the table host (Round 3 INTERFACES §3, packet 3B).
 *
 *   crearWidgetsArchivos({peticionPrivada}) -> {mount, mountDetalle, destroy}
 *
 *   mount / mountDetalle({container, terrenoId, tipo, soloLectura, resumen, onCambio, onError})
 *     -> {update({soloLectura, resumen}), destroy()}
 *
 * `mount` is the compact cell: it only renders the caller-aware summary and
 * never fetches. `mountDetalle` holds the full controls: upload (picker and
 * drag & drop), pending uploads with retry/cancel, paged files, versions,
 * history and KMZ attempts, candidate selection, explicit activation,
 * downloads and retirement.
 *
 * The host (A) registers `mount` with registrarWidgetDeArchivos, owns every
 * mount's lifetime and refreshes summaries when told `onCambio({terrenoId})`.
 * A file change is never a terrain-version change.
 *
 * The factory holds what must be shared by its mounts: the client over the
 * injected private bridge, the single upload/hash pipeline turn and the count
 * of unfinished uploads (no more than the server's five). destroy() tears
 * every mount down; after it nothing is sent and nothing is shown.
 */

import { el } from "../../lib/dom.js";
import { crearClienteArchivos } from "../../lib/archivos.js";
import { describirResumen } from "./resumen.js";
import { montarDetalle } from "./detalle.js";

export const MAX_SUBIDAS_PENDIENTES = 5;

const ETIQUETA = { pdf: "Archivos PDF", kmz: "KMZ" };

function montarCelda({ container, tipo, resumen }) {
  const nodo = el("span", { class: "archivos-celda", dataset: { tipo } });
  container.replaceChildren(nodo);
  function pintar(r) {
    const d = describirResumen(r, tipo);
    nodo.dataset.estado = d.estado;
    nodo.textContent = d.texto;
    const titulo = d.nota ? `${ETIQUETA[tipo]}: ${d.texto}. ${d.nota}.` : `${ETIQUETA[tipo]}: ${d.texto}`;
    nodo.title = titulo;
    nodo.setAttribute("aria-label", titulo);
  }
  pintar(resumen);
  return {
    update({ resumen: nuevo } = {}) { pintar(nuevo); },
    destroy() { nodo.remove(); },
  };
}

export function crearWidgetsArchivos({ peticionPrivada } = {}) {
  const cliente = crearClienteArchivos({ peticionPrivada });
  const montajes = new Set();
  const subidas = new Set();          // unfinished uploads across this factory's mounts
  let enTurno = false;
  let destruido = false;

  const contexto = {
    cliente,
    turno: {
      intentar() { if (enTurno || destruido) return false; enTurno = true; return true; },
      liberar() { enTurno = false; },
    },
    subidas: {
      hayLugar: () => subidas.size < MAX_SUBIDAS_PENDIENTES,
      agregar: (s) => subidas.add(s),
      quitar: (s) => subidas.delete(s),
    },
    vivo: () => !destruido,
  };

  function validar(args) {
    if (!args?.container || (args.tipo !== "pdf" && args.tipo !== "kmz") || typeof args.terrenoId !== "string") {
      throw new TypeError("mount requiere container, terrenoId y tipo pdf|kmz");
    }
  }

  function registrar(montado, args) {
    let vivo = true;
    const envoltura = {
      update(cambios = {}) { if (vivo && !destruido) montado.update(cambios); },
      destroy() {
        if (!vivo) return;
        vivo = false;
        montajes.delete(envoltura);
        montado.destroy();
        args.container.replaceChildren();
      },
    };
    montajes.add(envoltura);
    return envoltura;
  }

  return {
    mount(args) {
      if (destruido) throw new Error("Los widgets de archivos ya se destruyeron.");
      validar(args);
      return registrar(montarCelda(args), args);
    },
    mountDetalle(args) {
      if (destruido) throw new Error("Los widgets de archivos ya se destruyeron.");
      validar(args);
      return registrar(montarDetalle(args, contexto), args);
    },
    destroy() {
      if (destruido) return;
      destruido = true;
      for (const m of [...montajes]) m.destroy();
      subidas.clear();
      enTurno = false;
    },
  };
}

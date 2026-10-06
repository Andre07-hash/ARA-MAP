/* Refreshing and managing connected workbooks from the Bases screen.
 *
 * Each refresh is one bounded request: the server claims the run, reads the
 * workbook and activates it (or records why not) before answering. A double
 * click is absorbed here; concurrency, idempotency and fencing are the
 * server's. When a run started elsewhere (another person, or this browser
 * before a reload) is still in progress, its card is re-read every few
 * seconds for a bounded time; the server itself marks a run whose lease
 * expired as interrupted, and the previous data stays active throughout.
 */

import { api } from "../../lib/api.js";
import { el } from "../../lib/dom.js";
import {
  SONDEO_MAX_MS, SONDEO_MS, cambioDatos, crearClavesDeActualizacion, crearOcupadas,
  mensajeDeEjecucion, respuestaIncierta,
} from "../../lib/excel.js";
import { fmtCount, plural } from "../../lib/format.js";
import { getState, setState } from "../../lib/store.js";
import { confirmDialog, openDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";
import { Problemas } from "./ConnectExcel.js";

const claves = crearClavesDeActualizacion();
export const ocupadas = crearOcupadas();
const sondeos = new Map();   // fuente id -> timer
let generacionPrivada = 0;   // bumps on logout so late answers are dropped

function reemplazar(fuente) {
  setState((s) => ({ fuentes: [...s.fuentes.filter((f) => f.id !== fuente.id), fuente] }));
}

/** Load every source and the connector's availability. Never hides bases. */
export async function cargarFuentes() {
  const gen = generacionPrivada;
  try {
    const { fuentes, conector } = await api.excelFuentes();
    if (gen !== generacionPrivada) return;
    setState({ fuentes, conectorExcel: conector });
    for (const f of fuentes) if (f.en_curso) sondear(f.id);
  } catch (error) {
    if (error.status !== 401) setState({ conectorExcel: { disponible: false, motivo: error.message } });
  }
}

/** Forget timers and in-flight markers (logout). */
export function detenerExcel() {
  generacionPrivada += 1;
  for (const t of sondeos.values()) clearTimeout(t);
  sondeos.clear();
}

/* `inicio` is set only when a poll schedules its own continuation. */
function sondear(id, inicio = null) {
  if (inicio === null && sondeos.has(id)) return;   // already being watched
  const desde = inicio ?? Date.now();
  const gen = generacionPrivada;
  sondeos.set(id, setTimeout(async () => {
    sondeos.delete(id);
    if (gen !== generacionPrivada) return;
    try {
      const { fuente } = await api.excelFuente(id);
      if (gen !== generacionPrivada) return;
      const antes = getState().fuentes.find((f) => f.id === id);
      reemplazar(fuente);
      if (fuente.en_curso) {
        if (Date.now() - desde < SONDEO_MAX_MS) sondear(id, desde);
        return;
      }
      const e = fuente.ultima_ejecucion;
      if (antes?.en_curso && e) {
        (e.estado === "ok" ? toast : toastError)(mensajeDeEjecucion(e));
        if (cambioDatos(e)) alCambiarDatos?.(fuente);
      }
    } catch { /* the card keeps its last state; "Comprobar" retries */ }
  }, SONDEO_MS));
}

/** Re-read one source now (the card's "Comprobar" button). */
export async function comprobar(fuente) {
  try {
    const { fuente: f } = await api.excelFuente(fuente.id);
    reemplazar(f);
    if (f.en_curso) sondear(f.id);
  } catch (error) { toastError(error.message); }
}

let alCambiarDatos = null;
/** What to reload after new data is activated (bases, the open map/table). */
export function alActivar(fn) { alCambiarDatos = fn; }

export async function actualizar(fuente, { confirmarVacio = null } = {}) {
  if (!ocupadas.tomar(fuente.id)) return;
  setState({});
  const cuerpo = confirmarVacio ? { confirmar_vacio: confirmarVacio } : {};
  const gen = generacionPrivada;
  let siguiente = null;
  try {
    const r = await api.excelActualizar(fuente.id, cuerpo, claves.preparar(fuente.id, cuerpo));
    claves.resolver(fuente.id);
    if (gen !== generacionPrivada) return;
    reemplazar(r.fuente);
    siguiente = () => resultado(r.fuente, r.ejecucion);
  } catch (error) {
    if (gen !== generacionPrivada) return;
    if (respuestaIncierta(error)) {
      // The server may have finished it: the next press replays the same key
      // and shows the recorded outcome instead of running again.
      toastError("No llegó la respuesta del servidor. Pulsa «Actualizar» otra vez para ver el resultado; " +
                 "no se repetirá la actualización.");
    } else {
      claves.resolver(fuente.id);
      if (error.detalle?.code === "en_curso") {
        toast("Alguien ya está actualizando esta base; se mostrará el resultado al terminar.");
        await comprobar(fuente);
      } else {
        toastError(error.message);
      }
    }
  } finally {
    ocupadas.soltar(fuente.id);
    setState({});
  }
  await siguiente?.();
}

async function resultado(fuente, e) {
  if (e.estado === "ok") {
    toast(mensajeDeEjecucion(e));
    await alCambiarDatos?.(fuente);
  } else if (e.estado === "sin_cambios") {
    toast(mensajeDeEjecucion(e));
  } else if (e.estado === "revision") {
    const v = fuente.version_activa;
    const ok = await confirmDialog({
      titulo: "El libro está vacío",
      mensaje: `«${fuente.archivo.nombre}» ya no tiene filas en la hoja «${fuente.configuracion.hoja}». ` +
        `Si confirmas, la base quedará vacía (el historial se conserva). Hasta entonces se siguen ` +
        `mostrando los ${fmtCount(v?.filas ?? 0)} terrenos de la versión ${v?.numero ?? "anterior"}.`,
      confirmar: "Vaciar la base",
      peligro: true,
    });
    // The confirmation is bound to this exact candidate: if the file changed
    // since, the server re-evaluates instead of emptying.
    if (ok) await actualizar(fuente, { confirmarVacio: e.candidato });
  } else if (e.problemas?.length) {
    openDialog({
      titulo: "No se aplicó la actualización",
      descripcion: `Se conservan los datos de la versión ${fuente.version_activa?.numero ?? "anterior"}.`,
      contenido: Problemas(e.problemas),
      ancho: "40rem",
      acciones: [{ etiqueta: "Cerrar", variante: "principal", onClick: (close) => close() }],
    });
  } else {
    toastError(mensajeDeEjecucion(e));
  }
}

export async function reconectarCuenta() {
  try {
    const { url } = await api.microsoftConectar();
    window.location.assign(url);
  } catch (error) { toastError(error.message); }
}

export async function desconectar(fuente) {
  const ok = await confirmDialog({
    titulo: "Desconectar de Excel",
    mensaje: `«${fuente.archivo.nombre}» dejará de actualizar esta base. Los ` +
      `${plural(fuente.version_activa?.filas ?? 0, "terreno")} actuales y todo el historial se conservan, ` +
      "y puedes volver a activarla después.",
    confirmar: "Desconectar",
  });
  if (!ok) return;
  try {
    reemplazar((await api.excelDesconectar(fuente.id, fuente.generacion)).fuente);
    toast("Se desconectó del libro. Los datos se conservan.");
  } catch (error) { toastError(error.message); }
}

export async function reactivar(fuente) {
  try {
    reemplazar((await api.excelReactivar(fuente.id, fuente.generacion)).fuente);
    toast("Conectada de nuevo. Pulsa «Actualizar desde Excel» para traer los cambios.");
  } catch (error) { toastError(error.message); }
}

/* The short explanation shown near the Refresh buttons. */
export const AyudaActualizar = () => el("p", { class: "excel-help muted" },
  "«Actualizar desde Excel» lee la última versión guardada del libro en OneDrive; los cambios sin " +
  "guardar en Excel de escritorio no se ven hasta que se guardan y sincronizan. Los mapas guardados " +
  "no cambian.");

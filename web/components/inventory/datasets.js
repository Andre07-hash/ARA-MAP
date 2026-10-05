/* Loading the catalog and the inventory: every page of the current query,
 * one query at a time.
 *
 * A newer query aborts the older one, so a late response can never replace
 * a newer result. Private loads are additionally cancelled by api.abortPrivate
 * when the session ends.
 */

import { api } from "../../lib/api.js";
import { consultaDe, reunirPaginas } from "../../lib/inventario.js";
import { getState, setDataset, setState } from "../../lib/store.js";

const ESPERA_MS = 250;   // typing settles before a query is sent
const controladores = {};
const esperas = {};
let detalleCtl = null;

const pedirPagina = {
  catalogo: api.publicoTerrenos,
  inventario: api.inventarioTerrenos,
};

/** Reload a dataset for its current filters, after a short pause by default. */
export function pedirCarga(tipo, { inmediato = false } = {}) {
  clearTimeout(esperas[tipo]);
  if (inmediato) return cargar(tipo);
  esperas[tipo] = setTimeout(() => cargar(tipo), ESPERA_MS);
  return undefined;
}

export async function cargar(tipo) {
  clearTimeout(esperas[tipo]);
  controladores[tipo]?.abort();
  const controlador = new AbortController();
  controladores[tipo] = controlador;
  const { signal } = controlador;

  const consulta = consultaDe(getState()[tipo].filtros, tipo);
  const clave = consulta.toString();
  setDataset(tipo, { cargando: true, error: null, progreso: { recibidos: 0, total: null } });

  try {
    const resultado = await reunirPaginas(
      (cursor) => pedirPagina[tipo](consulta, cursor, signal),
      {
        onProgreso: (recibidos, total) => {
          if (!signal.aborted) setDataset(tipo, { progreso: { recibidos, total } });
        },
      },
    );
    if (signal.aborted) return;
    setDataset(tipo, {
      registros: resultado.terrenos,
      facets: resultado.facets,
      consulta: clave,
      cargando: false,
      cargado: true,
      progreso: null,
    });
  } catch (error) {
    if (signal.aborted || error.name === "AbortError") return;
    // A failed refresh of the same query keeps what is on screen, labelled
    // stale; a failed new query must not leave the old query's rows standing
    // under the new filters.
    const misma = getState()[tipo].consulta === clave;
    setDataset(tipo, {
      cargando: false,
      progreso: null,
      error: error.message,
      ...(misma ? {} : { registros: [], facets: {}, consulta: null }),
    });
  }
}

/** Load the terrain behind `#/catalogo/:id` or `#/inventario/:id`. */
export async function cargarDetalle(tipo, id) {
  detalleCtl?.abort();
  detalleCtl = new AbortController();
  const { signal } = detalleCtl;
  setState({ detalle: { tipo, id, terreno: null, cargando: true, error: null } });
  try {
    const respuesta = tipo === "catalogo"
      ? await api.publicoTerreno(id, signal)
      : await api.inventarioTerreno(id, signal);
    if (signal.aborted) return;
    setState({ detalle: { tipo, id, terreno: respuesta?.terreno ?? respuesta, cargando: false, error: null } });
  } catch (error) {
    if (signal.aborted || error.name === "AbortError") return;
    const mensaje = error.status === 404
      ? (tipo === "catalogo"
        ? "Este terreno no está en el catálogo público."
        : "Este terreno no existe en el inventario.")
      : error.message;
    setState({ detalle: { tipo, id, terreno: null, cargando: false, error: mensaje } });
  }
}

/** Replace one inventory record in place after a save, without a reload. */
export function reemplazarRegistro(terreno) {
  const { inventario, detalle } = getState();
  setState({
    inventario: {
      ...inventario,
      registros: inventario.registros.map((t) => (t.id === terreno.id ? terreno : t)),
    },
    ...(detalle?.tipo === "inventario" && detalle.id === terreno.id
      ? { detalle: { ...detalle, terreno } } : {}),
  });
}

export function cancelarCargas() {
  for (const tipo of Object.keys(controladores)) {
    clearTimeout(esperas[tipo]);
    controladores[tipo]?.abort();
  }
  detalleCtl?.abort();
}

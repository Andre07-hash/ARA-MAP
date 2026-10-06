/* The catalog and inventory views: server-filtered data on the shared map
 * workspace, with the public or the internal detail panel. */

import { priceBreaks } from "../../lib/colors.js";
import { clear, el } from "../../lib/dom.js";
import { monedasDe } from "../../lib/format.js";
import {
  contarFiltros, FILTROS_VACIOS, itemDeInventario, itemPublico, opcionesDeFacetas,
} from "../../lib/inventario.js";
import { navigate } from "../../lib/router.js";
import { setDataset, setState } from "../../lib/store.js";
import { cargar, cargarDetalle, pedirCarga } from "../inventory/datasets.js";
import { InventoryDetail } from "../inventory/InventoryDetail.js";
import { DatosToolbar, MensajeDatos } from "../inventory/DatosView.js";
import { DetailMessage, PublicTerrainDetail } from "../inventory/TerrainFacts.js";
import { openTerrainHistory } from "../inventory/TerrainHistory.js";
import {
  archivar, restaurar, retirarDelCatalogo, vistaPrevia,
} from "../inventory/publicationActions.js";
import { BasemapSwitcher } from "../map/BasemapSwitcher.js";
import { Legend } from "../map/Legend.js";
import { TerrainTable } from "../terrain/TerrainTable.js";
import { UnplacedList } from "../terrain/UnplacedList.js";
import { shell } from "./context.js";
import {
  changeBasemap, drawMap, ensureWorkspace, FiltrosBoton, ordenarTabla, replaceKeepingFocus,
  selectTerreno, usarRail, zoomTerrenoAEscala,
} from "./workspace.js";

/* Rows are derived once per assembled result, not on every render. */
const itemsCache = new WeakMap();
function itemsDe(tipo, datos) {
  if (!itemsCache.has(datos.registros)) {
    itemsCache.set(datos.registros,
      datos.registros.map(tipo === "catalogo" ? itemPublico : itemDeInventario));
  }
  return itemsCache.get(datos.registros);
}

export function renderDatos(host, state, tipo) {
  const datos = state[tipo];
  const items = itemsDe(tipo, datos);
  shell.itemsActuales = items;
  const monedas = monedasDe(items);
  const preciosComparables = monedas.length <= 1;
  const sinUbicacion = items.filter((t) => !t.ubicado);
  const breaks = preciosComparables ? priceBreaks(items.map((t) => t.asking_m2)) : null;
  const seleccionado = state.ruta.id;

  const ws = ensureWorkspace();
  if (ws.root.parentNode !== host) clear(host).append(ws.root);

  usarRail(tipo).update({
    terrenos: items,
    filtros: datos.filtros,
    visibles: items.length,
    monedas,
    opciones: opcionesDeFacetas(datos.facets),
    cargando: datos.cargando,
  });

  replaceKeepingFocus(ws.toolbar, DatosToolbar({
    tipo, datos, items, panel: state.panel,
    filtros: FiltrosBoton(tipo, contarFiltros(datos.filtros, tipo)),
    onPanel: (panel) => setState({ panel }),
    onEncuadrar: () => shell.canvas?.fitTo(items),
  }));

  ws.tableSlot.replaceChildren(
    ...(state.panel === "tabla"
      ? [el("div", { class: "table-panel" },
          TerrainTable({
            terrenos: items,
            orden: shell.tableSort.campo,
            direccion: shell.tableSort.direccion,
            seleccionado,
            preciosComparables,
            conPublicacion: tipo === "inventario",
            onSort: ordenarTabla,
            onSelect: (id) => selectTerreno(id, { pan: true }),
          })
        )]
      : [])
  );

  ws.overlays.replaceChildren(
    ...(state.panel === "mapa"
      ? [
          Legend({
            modo: "precio",
            capas: [],
            breaks,
            monedas,
            conteo: items.length - sinUbicacion.length,
            sinUbicacion: sinUbicacion.length,
            invalidas: sinUbicacion.filter((t) => t.ubicacion === "invalida").length,
            escala: shell.escalaActual,
          }),
          BasemapSwitcher({ activo: state.basemap, onChange: changeBasemap }),
        ]
      : [])
  );

  const mensaje = state.panel === "mapa" && MensajeDatos({
    tipo, datos, items,
    onRetry: () => cargar(tipo),
    onClear: () => { setDataset(tipo, { filtros: FILTROS_VACIOS }); pedirCarga(tipo, { inmediato: true }); },
  });
  ws.mensaje.replaceChildren(...(mensaje ? [mensaje] : []));

  ws.unplacedSlot.replaceChildren(
    ...(state.panel === "mapa"
      ? [UnplacedList({
          terrenos: sinUbicacion,
          seleccionado,
          abierto: shell.unplacedOpen,
          instruccion: tipo === "inventario"
            ? "Ábrelo y escribe su latitud (X) y longitud (Y) en «Editar»; no hace falta volver a importar."
            : null,
          onSelect: (id) => selectTerreno(id),
          onToggle: () => { shell.unplacedOpen = !shell.unplacedOpen; setState({}); },
        })]
      : [])
  );

  const panel = seleccionado ? DetalleDatos(tipo, state, items, seleccionado) : null;
  if (panel) {
    ws.detailSlot.replaceChildren(panel);
    if (ws.detailSlot.parentNode !== ws.root) ws.root.append(ws.detailSlot);
  } else {
    ws.detailSlot.remove();
  }

  const encuadrar = datos.cargado && !datos.cargando && !shell.encuadrado[tipo];
  if (encuadrar) shell.encuadrado[tipo] = true;
  drawMap({ basemap: state.basemap, capas: [], modoColor: "precio", seleccionado }, items, breaks, { encuadrar });
}

function DetalleDatos(tipo, state, items, id) {
  const cerrar = () => navigate({ nombre: tipo }, { replace: true });
  const { detalle } = state;
  const fresco = detalle?.tipo === tipo && detalle.id === id ? detalle : null;
  const item = items.find((t) => t.id === id);
  const terreno = fresco?.terreno ?? (item ? (tipo === "inventario" ? item.registro : item) : null);

  if (!terreno) {
    return fresco?.error
      ? DetailMessage({ titulo: "Terreno no disponible", mensaje: fresco.error, onClose: cerrar,
        onRetry: () => cargarDetalle(tipo, id) })
      : DetailMessage({ titulo: "Cargando…", mensaje: "Cargando el terreno…", onClose: cerrar });
  }
  if (tipo === "catalogo") {
    return PublicTerrainDetail({ terreno, onZoomAEscala: () => zoomTerrenoAEscala(id), onClose: cerrar });
  }
  return InventoryDetail({
    terreno,
    onEdit: () => navigate({ nombre: "editar", id }),
    onHistory: () => openTerrainHistory({ id, nombre: terreno.draft?.terreno }),
    onZoomAEscala: () => zoomTerrenoAEscala(id),
    onClose: cerrar,
    onPreview: () => vistaPrevia(terreno),
    onUnpublish: () => retirarDelCatalogo(terreno),
    onArchive: () => archivar(terreno),
    onRestore: () => restaurar(terreno),
  });
}

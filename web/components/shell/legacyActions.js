/* Legacy workspace actions: the bases and saved-map galleries, opening,
 * renaming, deleting, refreshing and exporting. Signed in only. */

import { api, exportXlsx } from "../../lib/api.js";
import { defaultDestination } from "../../lib/carpetas.js";
import { layerColor } from "../../lib/colors.js";
import { compareLayers } from "../../lib/comparar.js";
import { clear, el } from "../../lib/dom.js";
import { EMPTY_FILTERS } from "../../lib/filters.js";
import { fmtCount, plural } from "../../lib/format.js";
import { navigate } from "../../lib/router.js";
import { getState, setState } from "../../lib/store.js";
import { appendWorkbook, importWorkbook } from "../bases/ImportDialog.js";
import { BaseGallery } from "../bases/BaseGallery.js";
import {
  createFolder, deleteFolder, loadCarpetas, moveItem, renameFolder, selectFolder,
} from "../folders/folderActions.js";
import { openFormatManager } from "../import/FormatManager.js";
import { MapGallery } from "../maps/MapGallery.js";
import { openOverlayBuilder } from "../maps/OverlayBuilder.js";
import { confirmDialog, openDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";
import { shell, SORT_COMPARACION } from "./context.js";

/* The folder props both galleries share, for one dashboard. */
function folderProps(tipo, state) {
  return {
    carpetas: state.carpetas[tipo],
    seleccion: state.carpetaVista[tipo],
    carpetasError: state.carpetasError[tipo],
    onMove: (item) => moveItem(tipo, item),
    onSelectFolder: (seleccion) => selectFolder(tipo, seleccion),
    onCreateFolder: () => createFolder(tipo),
    onRenameFolder: (carpeta) => renameFolder(tipo, carpeta),
    onDeleteFolder: (carpeta) => deleteFolder(tipo, carpeta),
    onRetryFolders: () => loadCarpetas(tipo),
  };
}

/* Galleries are rebuilt on every state change. An element that had focus
 * and carries an id (the folder heading, say) gets it back afterwards, so a
 * background update cannot drop keyboard focus onto the page body. */
function renderKeepingFocus(host, build) {
  const active = document.activeElement;
  const id = active && host.contains(active) ? active.id : "";
  clear(host).append(build());
  if (id) document.getElementById(id)?.focus();
}

export function renderBases(host, state) {
  renderKeepingFocus(host, () => BaseGallery({
    readOnly: shell.readOnly,
    bases: state.bases,
    ...folderProps("bases", state),
    onImport: () => importWorkbook({
      onDone: afterBaseChange,
      carpetas: state.carpetas.bases,
      carpetaInicial: defaultDestination(state.carpetaVista.bases),
    }),
    onOpen: (base) => openBase(base),
    onAppend: (base) => appendWorkbook(base, { onDone: afterBaseChange }),
    onFormats: () => openFormatManager(),
    onRename: (base) => renameBase(base),
    onDelete: (base) => deleteBase(base),
  }));
}

export function renderMapas(host, state) {
  renderKeepingFocus(host, () => MapGallery({
    readOnly: shell.readOnly,
    mapas: state.mapas,
    bases: state.bases,
    ...folderProps("mapas", state),
    onOpen: (mapa) => openMapa(mapa),
    onRename: (mapa) => renameMapa(mapa),
    onDelete: (mapa) => deleteMapa(mapa),
    // The complete collections, never the open folder's subset.
    onCompare: () => openOverlayBuilder({
      mapas: state.mapas,
      bases: state.bases,
      carpetasMapas: state.carpetas.mapas,
      carpetasBases: state.carpetas.bases,
      carpetaInicial: defaultDestination(state.carpetaVista.mapas),
      basemap: state.basemap,
      onCreated: async (mapa) => {
        const { mapas } = await api.mapas();
        setState({ mapas });
        openMapa(mapa);
      },
    }),
  }));
}

export async function openBase(base, { silencioso = false } = {}) {
  try {
    setState({ cargando: true });
    const { terrenos } = await api.terrenos(base.id);
    setState({
      baseActiva: base,
      mapaActivo: null,
      terrenos: terrenos.map((t) => ({ ...t, capa: 0, base_nombre: base.nombre })),
      capas: [{
        orden: 0, base_id: base.id, nombre: base.nombre,
        color: layerColor(0, getState().basemap), visible: true,
        base_existe: true, conteo: terrenos.length,
        ubicados: terrenos.filter((t) => t.ubicado).length,
      }],
      modoColor: "precio",
      seleccionado: null,
      filtros: { ...EMPTY_FILTERS },
      cargando: false,
    });
    navigate({ nombre: "mapa" });
    shell.canvas?.fitTo(terrenos);
    if (!silencioso) toast(`«${base.nombre}»: ${plural(terrenos.length, "terreno")}.`);
  } catch (error) {
    setState({ cargando: false });
    toastError(error.message);
  }
}

export async function openMapa(mapa) {
  try {
    setState({ cargando: true });
    const payload = await api.mapaTerrenos(mapa.id);
    const config = payload.mapa.config ?? {};
    const basemap = config.basemap ?? getState().basemap;

    const capas = payload.mapa.capas.map((capa, index) => ({
      ...capa,
      color: layerColor(index, basemap),
      visible: config.capasOcultas ? !config.capasOcultas.includes(capa.orden) : true,
    }));
    const colores = new Map(capas.map((c) => [c.orden, c.color]));

    const terrenos = payload.terrenos.map((t) => ({
      ...t, color: colores.get(t.capa ?? 0),
    }));
    // A comparison also says how each terrain differs from the first layer.
    const comparados = payload.mapa.tipo === "comparacion"
      ? compareLayers(terrenos, capas)
      : terrenos;
    // A comparison opens ranked by what changed rather than by file order.
    if (payload.mapa.tipo === "comparacion") shell.tableSort = { ...SORT_COMPARACION };

    setState({
      mapaActivo: payload.mapa,
      baseActiva: null,
      terrenos: comparados,
      capas,
      basemap,
      modoColor: payload.mapa.tipo === "comparacion"
        ? "base"
        : config.modoColor ?? "precio",
      panel: config.panel ?? "mapa",
      seleccionado: null,
      filtros: { ...EMPTY_FILTERS, ...(config.filtros ?? {}) },
      cargando: false,
    });

    navigate({ nombre: "mapa" });
    // Restore the saved viewport if there is one; otherwise frame the data.
    if (config.vista?.center && config.vista?.zoom) {
      shell.canvas?.setView(config.vista.center, config.vista.zoom);
    } else {
      shell.canvas?.fitTo(payload.terrenos);
    }
  } catch (error) {
    setState({ cargando: false });
    toastError(error.message);
  }
}

/** Everything worth restoring when this map is reopened. */
export function vistaActual(state) {
  return {
    filtros: state.filtros,
    panel: state.panel,
    capasOcultas: state.capas.filter((c) => !c.visible).map((c) => c.orden ?? 0),
    vista: shell.canvas?.viewport?.() ?? null,
  };
}

export async function guardarVista(mapa) {
  try {
    const state = getState();
    await api.updateMapa(mapa.id ?? state.mapaActivo.id, {
      config: {
        basemap: state.basemap,
        modoColor: state.modoColor,
        ...vistaActual(state),
      },
    });
    const { mapas } = await api.mapas();
    setState({ mapas });
    toast("Vista guardada: filtros, mapa base y encuadre.");
  } catch (error) { toastError(error.message); }
}

export async function actualizarMapa(mapa) {
  const ok = await confirmDialog({
    titulo: "Actualizar mapa",
    mensaje:
      `«${mapa.nombre}» se volverá a copiar desde las bases de origen. ` +
      "Lo que se ve ahora se reemplaza por los datos actuales. " +
      "Las capas cuya base ya no exista se conservan tal como están.",
    confirmar: "Actualizar",
  });
  if (!ok) return;

  try {
    const resultado = await api.refreshMapa(mapa.id);
    const { mapas } = await api.mapas();
    setState({ mapas });
    await openMapa(resultado.mapa);
    toast(
      `${plural(resultado.actualizadas, "capa actualizada", "capas actualizadas")}` +
      (resultado.conservadas
        ? `, ${plural(resultado.conservadas, "capa conservada", "capas conservadas")}.`
        : ".")
    );
  } catch (error) { toastError(error.message); }
}

/**
 * Apply a source rename to what is already on screen.
 *
 * Deliberately not a reload of the map: reopening it would throw away the
 * filters, selection, zoom and hidden layers the user has set. Only the names
 * change, so only the names are patched.
 */
function aplicarRenombreDeBase(baseId, nombre, respuesta) {
  setState((state) => {
    const bases = state.bases.map((b) => (b.id === baseId ? { ...b, nombre } : b));
    const capas = state.capas.map((capa) =>
      capa.base_id === baseId
        ? {
            ...capa,
            base_nombre: nombre,
            nombre: capa.version_etiqueta ? `${nombre} · ${capa.version_etiqueta}` : nombre,
          }
        : capa);
    const porOrden = new Map(capas.map((c) => [c.orden ?? 0, c.nombre]));

    return {
      bases,
      mapas: respuesta.mapas ?? state.mapas,
      capas,
      terrenos: state.terrenos.map((t) =>
        t.base_id === baseId
          ? { ...t, base_nombre: porOrden.get(t.capa ?? 0) ?? t.base_nombre }
          : t),
      baseActiva: state.baseActiva?.id === baseId
        ? { ...state.baseActiva, nombre }
        : state.baseActiva,
      mapaActivo: state.mapaActivo
        ? (respuesta.mapas ?? []).find((m) => m.id === state.mapaActivo.id)
          ?? state.mapaActivo
        : null,
    };
  });
}

export async function afterBaseChange() {
  const { bases } = await api.bases();
  setState({ bases });
  const activa = getState().baseActiva;
  if (activa) {
    const refrescada = bases.find((b) => b.id === activa.id);
    if (refrescada) await openBase(refrescada, { silencioso: true });
  }
}

/* One rename dialog for bases and for saved maps: same field, same rules, only
 * the title and what it saves to differ. */
function promptRename({ titulo, nombre: actual, onSave }) {
  const input = el("input", { class: "input", id: "nuevo-nombre", value: actual });
  openDialog({
    titulo,
    ancho: "28rem",
    contenido: el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: "nuevo-nombre" }, "Nombre"),
      input,
    ),
    acciones: [
      { etiqueta: "Cancelar", onClick: (close) => close() },
      {
        etiqueta: "Guardar", variante: "principal",
        onClick: async (close) => {
          const nombre = input.value.trim();
          if (!nombre) return toastError("El nombre no puede estar vacío.");
          try {
            await onSave(nombre);
            close();
            toast("Nombre actualizado.");
          } catch (error) { toastError(error.message); }
        },
      },
    ],
  });
}

function renameBase(base) {
  promptRename({
    titulo: "Renombrar base",
    nombre: base.nombre,
    onSave: async (nombre) => {
      await api.renameBase(base.id, nombre);
      await afterBaseChange();
    },
  });
}

function renameMapa(mapa) {
  promptRename({
    titulo: "Renombrar mapa",
    nombre: mapa.nombre,
    onSave: async (nombre) => {
      await api.updateMapa(mapa.id, { nombre });
      const { mapas } = await api.mapas();
      const activo = getState().mapaActivo;
      setState({
        mapas,
        ...(activo?.id === mapa.id ? { mapaActivo: { ...activo, nombre } } : {}),
      });
    },
  });
}

async function deleteBase(base) {
  const ok = await confirmDialog({
    titulo: "Eliminar base",
    mensaje: `Se eliminará «${base.nombre}» con sus ${fmtCount(base.conteo)} terrenos, ` +
             "y desaparecerá de los mapas guardados que la usen. No se puede deshacer.",
    confirmar: "Eliminar",
    peligro: true,
  });
  if (!ok) return;

  try {
    await api.deleteBase(base.id);
    // Folders load alongside and report their own failure, so a folder
    // problem never hides the bases and maps themselves.
    const [{ bases }, { mapas }] = await Promise.all([
      api.bases(), api.mapas(), loadCarpetas("bases"), loadCarpetas("mapas"),
    ]);
    const eraActiva = getState().baseActiva?.id === base.id;
    setState({
      bases, mapas,
      ...(eraActiva ? { baseActiva: null, terrenos: [], capas: [], seleccionado: null } : {}),
    });
    toast(`Se eliminó «${base.nombre}».`);
  } catch (error) { toastError(error.message); }
}

async function deleteMapa(mapa) {
  const ok = await confirmDialog({
    titulo: "Eliminar mapa",
    mensaje: `Se eliminará el mapa «${mapa.nombre}». Las bases de terrenos no se tocan.`,
    confirmar: "Eliminar",
    peligro: true,
  });
  if (!ok) return;

  try {
    await api.deleteMapa(mapa.id);
    const { mapas } = await api.mapas();
    const eraActivo = getState().mapaActivo?.id === mapa.id;
    setState({ mapas, ...(eraActivo ? { mapaActivo: null, terrenos: [], capas: [] } : {}) });
    toast(`Se eliminó «${mapa.nombre}».`);
  } catch (error) { toastError(error.message); }
}

export async function exportar(state, filtrados) {
  // A saved map exports its frozen rows, with the source base named; a live
  // base exports itself.
  const destino = state.mapaActivo
    ? { mapa_id: state.mapaActivo.id, nombre: state.mapaActivo.nombre }
    : state.baseActiva
      ? { base_id: state.baseActiva.id, nombre: state.baseActiva.nombre }
      : null;

  if (!destino) return toastError("No hay nada que exportar.");
  try {
    await exportXlsx({ ...destino, ids: filtrados.map((t) => t.id) });
    // The sheet count comes from the export contract, not from how many groups
    // happen to be non-empty: a filtered-out layer still gets its own sheet.
    const hojas = state.mapaActivo?.tipo === "comparacion" ? state.capas.length : 1;
    toast(
      hojas > 1
        ? `Se exportaron ${plural(filtrados.length, "terreno")} en ${hojas} hojas, una por base.`
        : `Se exportaron ${plural(filtrados.length, "terreno")}.`
    );
  } catch (error) { toastError(error.message); }
}

/* What the folder controls do: load, create, rename, delete and move.
 *
 * Every change goes to the server first and the screen follows its answer; a
 * failed request leaves the previous placement visible and says why. Moving an
 * item patches that one object by id in the full list (and in the open map or
 * base, if it is that one), so an open map keeps its filters, selection and
 * zoom: nothing is reopened.
 */

import { api } from "../../lib/api.js";
import {
  SIN_CARPETA, TEXTOS, resolveSelection, selectionLabel, withFolder,
} from "../../lib/carpetas.js";
import { plural } from "../../lib/format.js";
import { getState, setState } from "../../lib/store.js";
import { toast, toastError } from "../ui/toast.js";
import { confirmDeleteFolder, moveToFolderDialog, promptFolderName } from "./FolderDialogs.js";

/** Fetch one dashboard's folders. Resolves with the list (the old one on error). */
export async function loadCarpetas(tipo) {
  try {
    const { carpetas } = await api.carpetas(tipo);
    setState((s) => ({
      carpetas: { ...s.carpetas, [tipo]: carpetas },
      carpetasError: { ...s.carpetasError, [tipo]: null },
      // A folder someone else deleted cannot stay selected.
      carpetaVista: { ...s.carpetaVista, [tipo]: resolveSelection(s.carpetaVista[tipo], carpetas) },
    }));
    return carpetas;
  } catch (error) {
    setState((s) => ({ carpetasError: { ...s.carpetasError, [tipo]: error.message } }));
    return getState().carpetas[tipo];
  }
}

export function selectFolder(tipo, seleccion) {
  setState((s) => ({ carpetaVista: { ...s.carpetaVista, [tipo]: seleccion } }));
}

export function createFolder(tipo) {
  promptFolderName({
    titulo: `Nueva carpeta de ${TEXTOS[tipo].plural}`,
    confirmar: "Crear carpeta",
    onSave: async (nombre) => {
      const { carpeta } = await api.createCarpeta(tipo, nombre);
      await loadCarpetas(tipo);
      selectFolder(tipo, carpeta.id);
      toast(`Carpeta «${carpeta.nombre}» creada.`);
      focusHeading(tipo);
    },
  });
}

export function renameFolder(tipo, carpeta) {
  if (!carpeta) return;
  promptFolderName({
    titulo: "Renombrar carpeta",
    nombre: carpeta.nombre,
    onSave: async (nombre) => {
      try {
        await api.renameCarpeta(carpeta.id, nombre);
      } catch (error) {
        if (error.status === 404) await loadCarpetas(tipo);
        throw error;
      }
      await loadCarpetas(tipo);
      toast("Carpeta renombrada.");
      focusHeading(tipo);
    },
  });
}

export async function deleteFolder(tipo, carpeta) {
  if (!carpeta) return;
  const conteo = getState()[tipo].filter((item) => item.carpeta_id === carpeta.id).length;
  if (!(await confirmDeleteFolder({ tipo, carpeta, conteo }))) return;

  try {
    const { trasladados } = await api.deleteCarpeta(carpeta.id);
    // Re-read the items rather than guess: another editor may have moved some.
    await reloadItems(tipo);
    await loadCarpetas(tipo);
    if (getState().carpetaVista[tipo] === carpeta.id) selectFolder(tipo, SIN_CARPETA);
    toast(
      `Se eliminó la carpeta «${carpeta.nombre}».` +
      (trasladados
        ? ` ${plural(trasladados, TEXTOS[tipo].singular, TEXTOS[tipo].plural)} ` +
          `${trasladados === 1 ? "pasó" : "pasaron"} a «Sin carpeta».`
        : "")
    );
    focusHeading(tipo);
  } catch (error) {
    toastError(error.message);
    if (error.status === 404) await loadCarpetas(tipo);
  }
}

/** Open the move dialog for one base (tipo "bases") or saved map ("mapas"). */
export function moveItem(tipo, item) {
  moveToFolderDialog({
    tipo,
    item,
    carpetas: getState().carpetas[tipo],
    reload: () => loadCarpetas(tipo),
    onMove: async (carpetaId) => {
      const respuesta = tipo === "bases"
        ? await api.moveBase(item.id, carpetaId)
        : await api.moveMapa(item.id, carpetaId);
      const actualizado = respuesta.base ?? respuesta.mapa;
      applyMembership(tipo, item.id, actualizado.carpeta_id);
      const destino = selectionLabel(tipo, actualizado.carpeta_id ?? SIN_CARPETA, getState().carpetas[tipo]);
      toast(`«${item.nombre}» está en «${destino}».`);
      focusHeading(tipo);
    },
  });
}

function applyMembership(tipo, id, carpetaId) {
  setState((s) => ({
    [tipo]: withFolder(s[tipo], id, carpetaId),
    ...(tipo === "bases" && s.baseActiva?.id === id
      ? { baseActiva: { ...s.baseActiva, carpeta_id: carpetaId } } : {}),
    ...(tipo === "mapas" && s.mapaActivo?.id === id
      ? { mapaActivo: { ...s.mapaActivo, carpeta_id: carpetaId } } : {}),
  }));
}

async function reloadItems(tipo) {
  const lista = tipo === "bases" ? (await api.bases()).bases : (await api.mapas()).mapas;
  const porId = new Map(lista.map((item) => [item.id, item]));
  setState((s) => ({
    [tipo]: lista,
    ...(tipo === "bases" && s.baseActiva && porId.has(s.baseActiva.id)
      ? { baseActiva: { ...s.baseActiva, carpeta_id: porId.get(s.baseActiva.id).carpeta_id } } : {}),
    ...(tipo === "mapas" && s.mapaActivo && porId.has(s.mapaActivo.id)
      ? { mapaActivo: { ...s.mapaActivo, carpeta_id: porId.get(s.mapaActivo.id).carpeta_id } } : {}),
  }));
}

/* The card that held focus is gone after a re-render; the folder's heading is
 * the sensible place to land. Deferred by one task so it runs after the modal
 * dialog has closed (focus cannot move outside an open modal). A task rather
 * than an animation frame: frames can be held back in a background tab. */
function focusHeading(tipo) {
  setTimeout(() => document.getElementById(`folder-heading-${tipo}`)?.focus(), 0);
}

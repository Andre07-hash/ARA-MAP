/* The host's connection to Team B's file modules (Round 3, INTERFACES §3, §5).
 *
 *   web/components/archivos/index.js   crearWidgetsArchivos({peticionPrivada})
 *                                        -> {mount, mountDetalle, destroy}
 *   web/lib/cargadorGeometrias.js      crearCargadorGeometrias({peticionPrivada})
 *                                        -> {cargar, reset, destroy}
 *
 * One connection per table, that is per signed-in session: it is made when
 * the table is, and destroy() ends it with the table (logout, expiry, another
 * account). The modules are loaded on demand so that a failure to load them
 * leaves the table working, with file slots that say they are unavailable,
 * instead of leaving the application blank.
 */

import { peticionPrivada } from "../../lib/api.js";
import { registrarWidgetDeArchivos } from "./ranuraArchivos.js";

const MODULOS = { widgets: "../archivos/index.js", cargador: "../../lib/cargadorGeometrias.js" };

/** Overridable in tests; the application always loads the real modules. */
export const cargarModulo = { de: (ruta) => import(ruta) };

export function conectarArchivos({ onListo } = {}) {
  let vivo = true;
  let widgets = null;
  let cargador = null;
  const faltan = [];

  const listo = Promise.allSettled([
    cargarModulo.de(MODULOS.widgets).then((m) => m.crearWidgetsArchivos({ peticionPrivada })),
    cargarModulo.de(MODULOS.cargador).then((m) => m.crearCargadorGeometrias({ peticionPrivada })),
  ]).then(([w, c]) => {
    if (w.status === "fulfilled") widgets = w.value; else faltan.push("archivos");
    if (c.status === "fulfilled") cargador = c.value; else faltan.push("contornos");
    if (!vivo) {             // the session ended while they loaded
      widgets?.destroy?.();
      cargador?.destroy?.();
      widgets = cargador = null;
      return;
    }
    if (widgets) registrarWidgetDeArchivos(widgets.mount, widgets.mountDetalle);
    onListo?.({ faltan: [...faltan] });
  });

  return {
    listo,
    /** The geometry loader, or null while it is loading or if it is missing. */
    get cargador() { return cargador; },
    get faltan() { return [...faltan]; },
    destroy() {
      if (!vivo) return;
      vivo = false;
      registrarWidgetDeArchivos(null);
      widgets?.destroy?.();
      cargador?.destroy?.();
      widgets = cargador = null;
    },
  };
}

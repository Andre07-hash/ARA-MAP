/* Building a comparison.
 *
 * Two ways in: combine saved maps (which keeps their frozen contents, so a
 * comparison of two historical snapshots stays historical), or draw two live
 * bases together. Colours come from the validated palette; past four layers the
 * dialog says plainly that colour alone stops being reliable.
 */

import { api } from "../../lib/api.js";
import { folderNameOf } from "../../lib/carpetas.js";
import { CAPAS_SEGURAS, MAX_CAPAS, comparisonPalette } from "../../lib/colors.js";
import { el } from "../../lib/dom.js";
import { fmtCount, fmtDate, plural } from "../../lib/format.js";
import { FolderSelect } from "../folders/FolderDialogs.js";
import { openDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";

/**
 * `mapas` and `bases` are the complete collections: sources can come from any
 * folder. `carpetasMapas` are the destinations for the new map, starting on
 * `carpetaInicial`; `carpetasBases` only label where each base lives.
 */
export function openOverlayBuilder({
  mapas, bases, basemap = "claro", onCreated,
  carpetasMapas = [], carpetasBases = [], carpetaInicial = null,
}) {
  const palette = comparisonPalette(basemap);
  const destino = FolderSelect({ id: "carpeta-mapa", carpetas: carpetasMapas, value: carpetaInicial });
  let fuente = mapas.length >= 2 ? "mapas" : "bases";
  const seleccion = { mapas: [], bases: [] };

  const nombreInput = el("input", {
    class: "input", id: "nombre-mapa", placeholder: "Agosto vs Septiembre",
  });
  const lista = el("ul", { class: "pick-list" });
  const resumen = el("div", { class: "merge-resumen" });
  const aviso = el("p", { class: "note" });
  const selector = el("div", { class: "segmented", role: "group", "aria-label": "Qué combinar" });

  nombreInput.addEventListener("input", () => { nombreInput.dataset.touched = "1"; });

  function suggestName() {
    if (nombreInput.dataset.touched) return;
    const fuenteDatos = fuente === "mapas" ? mapas : bases;
    const nombres = seleccion[fuente]
      .map((id) => fuenteDatos.find((x) => x.id === id)?.nombre)
      .filter(Boolean);
    nombreInput.value = nombres.length >= 2 ? nombres.join(" vs ") : nombres[0] ?? "";
  }

  async function refreshPlan() {
    const elegidos = seleccion.mapas;
    if (fuente !== "mapas" || elegidos.length < 2) {
      resumen.replaceChildren();
      return;
    }
    try {
      const plan = await api.planMerge(elegidos);
      resumen.replaceChildren(PlanSummary(plan, palette));
    } catch (error) {
      resumen.replaceChildren(el("p", { class: "note note-error" }, error.message));
    }
  }

  function renderSelector() {
    selector.replaceChildren(
      ...[["mapas", "Mapas guardados"], ["bases", "Bases"]].map(([key, etiqueta]) =>
        el("button", {
          type: "button",
          class: ["segment", fuente === key && "is-active"],
          "aria-pressed": String(fuente === key),
          disabled: key === "mapas" ? mapas.length < 2 : bases.length < 2,
          onclick: () => { fuente = key; suggestName(); render(); },
        }, etiqueta)
      )
    );
  }

  function render() {
    renderSelector();
    const items = fuente === "mapas" ? mapas : bases;
    const elegidos = seleccion[fuente];

    lista.replaceChildren(
      ...items.map((item) => {
        const index = elegidos.indexOf(item.id);
        const marcado = index >= 0;
        const lleno = elegidos.length >= MAX_CAPAS;

        return el("li", {},
          el("label", {
            class: ["pick", marcado && "is-picked", !marcado && lleno && "is-disabled"],
          },
            el("input", {
              type: "checkbox",
              checked: marcado,
              disabled: !marcado && lleno,
              onchange: () => {
                if (marcado) elegidos.splice(index, 1);
                else if (elegidos.length < MAX_CAPAS) elegidos.push(item.id);
                suggestName();
                render();
                refreshPlan();
              },
            }),
            el("span", {
              class: "legend-swatch",
              style: {
                background: marcado ? palette[index % palette.length] : "transparent",
                borderColor: marcado ? "transparent" : "var(--rule-strong)",
              },
            }),
            el("span", { class: "pick-name truncate" }, item.nombre,
              el("span", { class: "pick-folder muted" },
                folderNameOf(item, fuente === "mapas" ? carpetasMapas : carpetasBases))),
            el("span", { class: "figure muted" },
              fuente === "mapas"
                ? `${plural(item.capas?.length ?? 0, "capa", "capas")} · ${fmtDate(item.creado_en)}`
                : `${fmtCount(item.ubicados)} en el mapa`),
          )
        );
      })
    );

    const n = elegidos.length;
    aviso.className = n > CAPAS_SEGURAS ? "note note-aviso" : "note";
    aviso.textContent = n > CAPAS_SEGURAS
      ? `${n} capas seleccionadas. Más de ${CAPAS_SEGURAS} colores dejan de ` +
        "distinguirse con seguridad, sobre todo en satélite: las capas extra se " +
        "dibujan con borde punteado y siempre aparecen nombradas en la leyenda."
      : `Elige de 2 a ${MAX_CAPAS}. Seleccionadas: ${n}.`;
  }

  render();

  openDialog({
    titulo: "Nueva comparación",
    descripcion: "Combina mapas guardados, o dibuja varias bases juntas.",
    ancho: "40rem",
    contenido: el("div", { class: "overlay-builder" },
      selector,
      lista,
      resumen,
      aviso,
      el("div", { class: "field-pair" },
        el("div", { class: "rail-field" },
          el("label", { class: "field-label", for: "nombre-mapa" }, "Nombre del mapa"),
          nombreInput,
        ),
        destino.element,
      ),
    ),
    acciones: [
      { etiqueta: "Cancelar", onClick: (close) => close() },
      {
        etiqueta: "Crear mapa",
        variante: "principal",
        onClick: async (close) => {
          const elegidos = seleccion[fuente];
          if (elegidos.length < 2) {
            toastError("Elige al menos dos para comparar.");
            return;
          }
          const nombre = nombreInput.value.trim();
          if (!nombre) {
            toastError("Ponle un nombre al mapa.");
            return;
          }

          try {
            const colores = elegidos.map((_, i) => palette[i % palette.length]);
            const carpeta_id = destino.value();
            const payload = fuente === "mapas"
              ? await api.mergeMapas({
                  nombre, mapa_ids: elegidos, colores, carpeta_id,
                  config: { basemap, modoColor: "base" },
                })
              : await api.createMapa({
                  nombre, tipo: "comparacion", carpeta_id,
                  capas: elegidos.map((base_id, i) => ({ base_id, color: colores[i] })),
                  config: { basemap, modoColor: "base" },
                });

            close();
            const omitidas = payload.duplicadas?.length ?? 0;
            toast(
              `Mapa «${payload.mapa.nombre}» creado con ` +
              `${plural(payload.mapa.capas.length, "capa", "capas")}` +
              (omitidas ? `; ${plural(omitidas, "capa repetida", "capas repetidas")} omitidas.` : ".")
            );
            onCreated?.(payload.mapa);
          } catch (error) {
            toastError(error.message);
          }
        },
      },
    ],
  });
}

function PlanSummary(plan, palette) {
  return el("div", { class: "merge-plan" },
    el("h3", { class: "eyebrow" }, `Resultado: ${plural(plan.total, "capa", "capas")}`),
    el("ul", { class: "merge-list" },
      plan.capas.map((capa, index) =>
        el("li", {},
          el("span", {
            class: ["legend-swatch", index >= plan.capas_seguras && "is-dashed"],
            style: { background: palette[index % palette.length] },
          }),
          el("span", { class: "truncate", title: capa.etiqueta ?? capa.base_nombre },
            capa.etiqueta ?? capa.base_nombre),
          el("span", { class: "muted figure" },
            `${fmtCount(capa.conteo)} terrenos · ${fmtCount(capa.ubicados)} en el mapa`),
        )
      )
    ),
    plan.capas.some((c) => c.es_version) && el("p", { class: "note" },
      "Hay varias versiones guardadas de una misma base. Se conservan todas y " +
      "se distinguen por el mapa del que vienen."),
    plan.duplicadas.length > 0 && el("p", { class: "note" },
      `Se omite ${plural(plan.duplicadas.length, "capa idéntica", "capas idénticas")}: ` +
      plan.duplicadas
        .map((d) => `${d.base_nombre} (igual a «${d.igual_a}»)`)
        .join(", ") + ".",
    ),
  );
}

/**
 * Save the base currently on screen as a named, frozen map. It goes into one
 * of `carpetas` (map folders), "Sin carpeta" by default: the base's own folder
 * is a different dashboard's organization and is not carried over.
 */
export function openSaveMapDialog({ base, basemap, modoColor, vista, onCreated, carpetas = [] }) {
  const nombreInput = el("input", { class: "input", id: "nombre-mapa", value: base.nombre });
  const destino = FolderSelect({ id: "carpeta-mapa", carpetas, value: null });

  openDialog({
    titulo: "Guardar como mapa",
    descripcion:
      "Guarda una copia de los terrenos tal como están ahora. El mapa no cambiará " +
      "aunque después edites la base; podrás actualizarlo cuando quieras.",
    ancho: "32rem",
    contenido: el("div", {},
      el("div", { class: "rail-field" },
        el("label", { class: "field-label", for: "nombre-mapa" }, "Nombre del mapa"),
        nombreInput,
      ),
      destino.element,
    ),
    acciones: [
      { etiqueta: "Cancelar", onClick: (close) => close() },
      {
        etiqueta: "Guardar",
        variante: "principal",
        onClick: async (close) => {
          const nombre = nombreInput.value.trim();
          if (!nombre) {
            toastError("Ponle un nombre al mapa.");
            return;
          }
          try {
            const { mapa } = await api.createMapa({
              nombre,
              tipo: "simple",
              carpeta_id: destino.value(),
              capas: [{ base_id: base.id, color: comparisonPalette(basemap)[0] }],
              config: { basemap, modoColor, ...vista },
              // Left at the source's name means "keep following it"; anything
              // else is a deliberate title and stays put when the source is
              // renamed.
              nombre_sigue_base: nombre === base.nombre,
            });
            close();
            toast(`Mapa «${mapa.nombre}» guardado con ${plural(mapa.conteo, "terreno")}.`);
            onCreated?.(mapa);
          } catch (error) {
            toastError(error.message);
          }
        },
      },
    ],
  });
}

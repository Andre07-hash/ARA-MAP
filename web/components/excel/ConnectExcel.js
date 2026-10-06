/* "Conectar Excel": account -> workbook -> sheet/ID/currency review -> import.
 *
 * One dialog, updated in place. The workbook lives in the OneDrive of the
 * account that connects once (its owner); employees later refresh through that
 * connection without signing in to Microsoft themselves. Nothing is stored
 * until "Conectar e importar"; the server validates every row and connects
 * nothing if any row has a problem.
 */

import { api } from "../../lib/api.js";
import {
  MONEDAS_EXCEL, configuracionInicial, faltantesDeConfiguracion, fmtFechaHora, nombreSugerido,
} from "../../lib/excel.js";
import { append, clear, el } from "../../lib/dom.js";
import { fmtCount, plural } from "../../lib/format.js";
import { crearIntento } from "../../lib/inventario.js";
import { FolderSelect } from "../folders/FolderDialogs.js";
import { openDialog } from "../ui/dialog.js";
import { toast } from "../ui/toast.js";

const AYUDA_GUARDADO =
  "«Actualizar desde Excel» lee la última versión GUARDADA del libro en OneDrive. " +
  "Los cambios sin guardar en Excel de escritorio no se ven hasta que se guardan y se sincronizan.";

/** Resolves with the created source, or null if closed. */
export function connectExcel({ carpetas = [], carpetaInicial = null, onDone } = {}) {
  return new Promise((resolve) => {
    let paso = "cuenta";
    let cargando = true;
    let error = null;
    let conector = null;
    let cuentas = [];
    let cuenta = null;
    let ruta = [];            // [{ id, nombre }] folders opened, root first
    let busqueda = "";
    let elementos = [];
    let archivo = null;       // { id, nombre, drive_id }
    let vista = null;         // the server's preview of the chosen workbook
    let config = null;
    let nombre = "";
    let problemas = [];
    let enviando = false;
    let settled = false;
    const intento = crearIntento();
    const finish = (v) => { if (!settled) { settled = true; resolve(v); } };

    const cuerpo = el("div", { class: "excel-connect", "aria-live": "polite" });
    const pie = el("div", { class: "assistant-footer" });
    const destino = FolderSelect({ id: "carpeta-excel", carpetas, value: carpetaInicial });
    const { dialog, close } = openDialog({
      titulo: "Conectar un libro de Excel",
      descripcion: "La base se mantiene al día con el libro: cualquiera del equipo puede actualizarla.",
      contenido: el("div", {}, cuerpo, pie),
      ancho: "52rem",
      acciones: [],
    });
    dialog.addEventListener("close", () => finish(null));

    async function cargarCuentas() {
      cargando = true; error = null; render();
      try {
        ({ conector, cuentas } = await api.microsoftEstado());
      } catch (e) { error = e.message; }
      cargando = false; render();
    }

    async function cargarArchivos() {
      cargando = true; error = null; render();
      try {
        const carpeta = busqueda ? null : ruta.at(-1)?.id ?? null;
        ({ elementos } = await api.microsoftArchivos(cuenta.id, { carpeta, q: busqueda || null }));
      } catch (e) {
        error = e.message;
        elementos = [];
        if (e.detalle?.code === "reconectar") cuenta = { ...cuenta, requiere_reconexion: true };
      }
      cargando = false; render();
    }

    async function cargarVista(hoja = null) {
      cargando = true; error = null; problemas = []; render();
      try {
        vista = await api.excelVistaPrevia({
          cuenta_id: cuenta.id, drive_id: archivo.drive_id, item_id: archivo.id, ...(hoja ? { hoja } : {}),
        });
        config = { ...configuracionInicial(vista), ...(config && hoja ? { moneda: config.moneda } : {}) };
        if (!nombre) nombre = nombreSugerido(vista.archivo?.nombre ?? archivo.nombre);
      } catch (e) { error = e.message; vista = null; }
      cargando = false; render();
    }

    async function iniciarMicrosoft() {
      cargando = true; error = null; render();
      try {
        const { url } = await api.microsoftConectar();
        // Microsoft brings the browser back to #/bases?excel=<resultado>.
        window.location.assign(url);
      } catch (e) { error = e.message; cargando = false; render(); }
    }

    async function conectar() {
      if (enviando) return;
      const payload = {
        cuenta_id: cuenta.id, drive_id: archivo.drive_id, item_id: archivo.id, nombre: nombre.trim(),
        hoja: config.hoja, columna_id: config.columna_id, moneda: config.moneda,
        ...(config.moneda === "columna" ? { columna_moneda: config.columna_moneda } : {}),
        carpeta_id: destino.value(),
      };
      enviando = true; error = null; problemas = []; render();
      try {
        const r = await api.excelConectar(payload, intento.claveParaCuerpo(payload));
        intento.completar();
        toast(`«${payload.nombre}» conectada: ${plural(r.fuente.version_activa?.filas ?? 0, "terreno")}.`);
        close();
        finish(r.fuente);
        onDone?.(r.fuente);
        return;
      } catch (e) {
        // A lost answer keeps the key, so pressing again replays the result.
        if (!e.red && (e.status ?? 0) < 500) intento.completar();
        error = e.message;
        problemas = e.detalle?.problemas ?? [];
      }
      enviando = false; render();
    }

    /* ------------------------------------------------------------ render */

    function render() {
      cuerpo.setAttribute("aria-busy", String(cargando || enviando));
      append(clear(cuerpo), [
        Pasos(paso),
        error && el("p", { class: "note note-error", role: "alert" }, error),
        paso === "cuenta" && PasoCuenta(),
        paso === "archivo" && PasoArchivo(),
        paso === "revision" && PasoRevision(),
      ]);
      append(clear(pie), Pie());
    }

    function PasoCuenta() {
      if (cargando) return el("p", { role: "status" }, "Cargando…");
      if (conector && !conector.disponible) {
        return el("div", { class: "empty-state" },
          el("h2", {}, "La conexión con Excel no está disponible aquí"),
          el("p", { class: "secondary" }, conector.motivo ?? ""),
        );
      }
      return el("div", {},
        el("p", { class: "secondary" },
          "Conecta una sola vez la cuenta de Microsoft DUEÑA del libro (la del OneDrive donde está guardado). " +
          "Los demás no necesitan conectar sus cuentas: actualizan a través de esta conexión, " +
          "y queda registrado quién actualizó y cuándo."),
        cuentas.length > 0 && el("ul", { class: "excel-list" }, cuentas.map((c) =>
          el("li", {},
            el("button", {
              type: "button", class: "excel-item", disabled: c.requiere_reconexion,
              onclick: () => { cuenta = c; paso = "archivo"; ruta = []; busqueda = ""; cargarArchivos(); },
            },
              el("strong", {}, c.correo ?? c.nombre ?? "Cuenta de Microsoft"),
              el("span", { class: "muted" },
                ` · ${c.tipo === "personal" ? "OneDrive personal" : "Cuenta de trabajo o escuela"}` +
                ` · conectada por ${c.conectada_por?.display_name ?? "—"} ${fmtFechaHora(c.conectada_en)}`),
              c.requiere_reconexion && el("span", { class: "excel-tag excel-tag-error" }, "Hay que volver a conectarla"),
            ),
          ))),
        el("p", { class: "excel-help muted" },
          "Al conectar, Microsoft te pedirá permiso de solo lectura para tus archivos. ARA Map nunca " +
          "modifica el libro."),
      );
    }

    function PasoArchivo() {
      const buscar = el("input", {
        class: "input", id: "excel-buscar", type: "search", value: busqueda,
        placeholder: "Buscar un libro por nombre", "aria-label": "Buscar un libro por nombre",
        onkeydown: (ev) => {
          if (ev.key === "Enter") { ev.preventDefault(); busqueda = ev.target.value.trim(); cargarArchivos(); }
        },
      });
      return el("div", {},
        el("p", { class: "secondary" }, `OneDrive de ${cuenta.correo ?? cuenta.nombre}. Elige un libro .xlsx o .xlsm.`),
        el("div", { class: "excel-toolbar" },
          buscar,
          el("button", { type: "button", class: "btn btn-quiet",
            onclick: () => { busqueda = buscar.value.trim(); cargarArchivos(); } }, "Buscar"),
        ),
        el("nav", { class: "excel-breadcrumb", "aria-label": "Carpeta" },
          el("button", { type: "button", class: "link-btn",
            onclick: () => { ruta = []; busqueda = ""; cargarArchivos(); } }, "OneDrive"),
          ruta.map((c, i) => [" / ", el("button", { type: "button", class: "link-btn",
            onclick: () => { ruta = ruta.slice(0, i + 1); busqueda = ""; cargarArchivos(); } }, c.nombre)]),
          busqueda && ` / resultados de «${busqueda}»`,
        ),
        cargando ? el("p", { role: "status" }, "Cargando…") :
        elementos.length === 0 ? el("p", { class: "muted" }, "No hay libros de Excel aquí.") :
        el("ul", { class: "excel-list" }, elementos.map((it) =>
          el("li", {},
            el("button", {
              type: "button", class: "excel-item",
              onclick: () => {
                if (it.carpeta) { ruta = [...ruta, { id: it.id, nombre: it.nombre }]; busqueda = ""; cargarArchivos(); }
                else { archivo = it; paso = "revision"; vista = null; config = null; nombre = ""; cargarVista(); }
              },
            },
              el("span", { "aria-hidden": "true" }, it.carpeta ? "📁 " : "📗 "),
              el("strong", {}, it.nombre),
              !it.carpeta && it.modificado_en && el("span", { class: "muted" }, ` · modificado ${fmtFechaHora(it.modificado_en)}`),
            ),
          ))),
      );
    }

    function PasoRevision() {
      if (cargando && !vista) return el("p", { role: "status" }, "Leyendo el libro…");
      if (!vista) return el("p", { class: "muted" }, "No se pudo leer el libro.");
      const columnas = vista.columnas ?? [];
      const select = (id, valor, opciones, onchange) => el("select", { class: "input", id, onchange },
        opciones.map(([v, t]) => el("option", { value: v, selected: v === valor }, t)));
      const faltan = faltantesDeConfiguracion(config, vista, nombre);
      return el("div", { class: "excel-review" },
        el("p", {},
          el("strong", {}, vista.archivo?.nombre ?? archivo.nombre),
          el("span", { class: "muted" },
            ` · guardado ${fmtFechaHora(vista.archivo?.modificado_en)}` +
            (vista.archivo?.modificado_por ? ` por ${vista.archivo.modificado_por}` : "")),
        ),
        vista.ya_conectada && el("p", { class: "note note-aviso" }, "Ese archivo ya está conectado a otra base."),
        el("div", { class: "excel-grid" },
          Campo("excel-nombre", "Nombre de la base",
            el("input", { class: "input", id: "excel-nombre", value: nombre,
              oninput: (ev) => { nombre = ev.target.value; append(clear(pie), Pie()); } })),
          Campo("excel-hoja", "Hoja",
            select("excel-hoja", vista.hoja, (vista.hojas ?? []).map((h) => [h, h]),
              (ev) => cargarVista(ev.target.value))),
          Campo("excel-id", "Columna con el ID único de cada terreno",
            select("excel-id", config.columna_id, [["", "Elige una columna…"],
              ...columnas.map((c) => [c.encabezado,
                `${c.encabezado}${c.puede_ser_id ? " (sin repetidos ni vacíos)" : ` (${c.unicas} distintos de ${fmtCount(vista.filas)})`}`])],
              (ev) => { config = { ...config, columna_id: ev.target.value }; render(); })),
          Campo("excel-moneda", "Moneda de los precios",
            select("excel-moneda", config.moneda, MONEDAS_EXCEL,
              (ev) => { config = { ...config, moneda: ev.target.value }; render(); })),
          config.moneda === "columna" && Campo("excel-col-moneda", "Columna de moneda",
            select("excel-col-moneda", config.columna_moneda,
              [["", "Elige una columna…"], ...columnas.map((c) => [c.encabezado, c.encabezado])],
              (ev) => { config = { ...config, columna_moneda: ev.target.value }; render(); })),
          destino.element,
        ),
        el("p", { class: "secondary" },
          `${plural(vista.filas ?? 0, "fila")} en la hoja. ` +
          "El ID identifica cada terreno entre actualizaciones: si una fila se mueve o cambia de nombre, " +
          "sigue siendo el mismo terreno. No uses el número de fila ni el nombre."),
        !vista.tiene_terreno && el("p", { class: "note note-aviso" },
          "La hoja no tiene las columnas de terreno que ARA Map necesita (al menos el nombre del terreno)."),
        problemas.length > 0 && Problemas(problemas),
        el("details", { class: "findings-details" },
          el("summary", {}, "Columnas del libro"),
          el("table", { class: "excel-table" },
            el("thead", {}, el("tr", {}, el("th", {}, "Encabezado"), el("th", {}, "Se usa como"),
              el("th", {}, "Con valor"), el("th", {}, "Distintos"))),
            el("tbody", {}, columnas.map((c) => el("tr", {},
              el("td", {}, c.encabezado), el("td", {}, c.campo ?? "—"),
              el("td", {}, fmtCount(c.llenas)), el("td", {}, fmtCount(c.unicas))))),
          ),
        ),
        faltan.length > 0 && el("ul", { class: "excel-faltan muted" }, faltan.map((f) => el("li", {}, f))),
        el("p", { class: "excel-help muted" }, AYUDA_GUARDADO),
      );
    }

    function Pie() {
      const atras = (destinoPaso) => el("button", {
        type: "button", class: "btn btn-quiet", disabled: enviando,
        onclick: () => { paso = destinoPaso; error = null; problemas = []; if (paso === "archivo") cargarArchivos(); else render(); },
      }, "Atrás");
      const cerrar = el("button", { type: "button", class: "btn btn-quiet", onclick: () => close() }, "Cancelar");
      if (paso === "cuenta") {
        return [cerrar, (!conector || conector.disponible) && el("button", {
          type: "button", class: "btn btn-principal", disabled: cargando,
          onclick: iniciarMicrosoft,
        }, cuentas.length ? "Conectar otra cuenta de Microsoft" : "Conectar cuenta de Microsoft")];
      }
      if (paso === "archivo") {
        return [atras("cuenta"), cuenta?.requiere_reconexion && el("button", {
          type: "button", class: "btn btn-principal", onclick: iniciarMicrosoft,
        }, "Volver a conectar la cuenta")];
      }
      const listo = vista && config && faltantesDeConfiguracion(config, vista, nombre).length === 0;
      return [atras("archivo"), el("button", {
        type: "button", class: "btn btn-principal", disabled: !listo || cargando || enviando, onclick: conectar,
      }, enviando ? "Leyendo y validando todo el libro…" : "Conectar e importar")];
    }

    cargarCuentas();
  });
}

function Pasos(actual) {
  const pasos = [["cuenta", "Cuenta"], ["archivo", "Libro"], ["revision", "Revisión"]];
  const i = pasos.findIndex(([k]) => k === actual);
  return el("ol", { class: "excel-steps" }, pasos.map(([k, t], j) =>
    el("li", { class: [j === i && "is-active", j < i && "is-done"], "aria-current": j === i ? "step" : null }, t)));
}

function Campo(id, etiqueta, control) {
  return el("div", { class: "rail-field" }, el("label", { class: "field-label", for: id }, etiqueta), control);
}

/** Row-specific problems from the server (never more than it sent). */
export function Problemas(problemas) {
  return el("div", { class: "excel-problems", role: "alert" },
    el("p", {}, el("strong", {}, `${plural(problemas.length, "problema")} en el libro. No se aplicó nada.`)),
    el("ul", {}, problemas.slice(0, 50).map((p) =>
      el("li", {}, p.fila ? `Fila ${p.fila}: ` : "", p.mensaje))),
    problemas.length > 50 && el("p", { class: "muted" }, `…y ${problemas.length - 50} más.`),
  );
}

/* What the import assistant shows. Pure rendering: every handler comes in. */

import { estadoAutomatico, etiquetaFila } from "../../lib/asistente.js";
import { el } from "../../lib/dom.js";
import { fmtArea, fmtCount, fmtHectares, fmtPrice, fmtUnitPrice, plural } from "../../lib/format.js";
import { Conflicts, Findings, RejectedRows, Stat } from "./partes.js";

const ORIGENES = {
  usuario: "Tu elección", formato: "Formato guardado", nombre: "Nombre conocido", alias: "Sinónimo conocido",
  valores: "Por sus valores", ia: "Asistencia automática", predeterminado: "Sin reconocer", pendiente: "Pendiente",
};
const SEPARADORES = { ",": "Comas", ";": "Punto y coma", "\t": "Tabulaciones" };
const MONEDAS = { USD: "dólares estadounidenses (USD)", MXN: "pesos mexicanos (MXN)" };
const ORIGEN_MONEDA = {
  archivo: "lo indica el archivo", usuario: "según tu respuesta", formato: "del formato guardado",
};
/* Which currency the prices are in, and who said so. Never left implicit. */
const monedaTexto = (moneda, origen) =>
  `${MONEDAS[moneda] ?? moneda}${ORIGEN_MONEDA[origen] ? ` — ${ORIGEN_MONEDA[origen]}` : ""}`;
const idSeguro = (texto) => String(texto).replace(/[^a-zA-Z0-9_-]/g, "-");

export function Analizando() {
  return el("div", { class: "assistant-status", role: "status", "aria-live": "polite" },
    el("span", { class: "spinner", "aria-hidden": "true" }),
    el("div", {},
      el("p", { class: "assistant-status-title" }, "Analizando archivo…"),
      el("p", { class: "secondary" }, "Identificando la tabla, los encabezados, las columnas y cómo están escritos los números."),
    ),
  );
}

export function ErrorArchivo(mensaje) {
  return el("div", { class: "note note-aviso", role: "alert" }, mensaje);
}

export function Preguntas({ preguntas, respuestas, onChange }) {
  return el("section", { class: "assistant-questions", "aria-labelledby": "assistant-preguntas" },
    el("h3", { id: "assistant-preguntas", class: "eyebrow" },
      preguntas.length === 1 ? "Una pregunta antes de revisar" : `${preguntas.length} preguntas antes de revisar`),
    preguntas.map((p) =>
      el("fieldset", { class: "question" },
        el("legend", { class: "question-title" }, p.texto),
        p.detalle && el("p", { class: "secondary question-detail" }, p.detalle),
        p.opciones.map((o) => {
          const id = `q-${idSeguro(p.id)}-${o.indice}`;
          return el("label", { class: "question-option", for: id },
            el("input", {
              type: "radio", id, name: `q-${idSeguro(p.id)}`, checked: respuestas[p.id] === o.indice,
              onchange: () => onChange(p.id, o.indice),
            }),
            el("span", { class: "question-option-text" },
              el("span", {}, o.etiqueta),
              o.detalle && el("span", { class: "question-sample figure" }, o.detalle)),
          );
        }),
      )),
  );
}

/* ------------------------------------------------------------- preview */

export function VistaPrevia({ vista, modo, resoluciones, mapa, interpretacion, onCorregir }) {
  const linea = etiquetaFila(vista.formato);
  const clasificacion = vista.clasificacion;
  // Row decisions are sent as whole lists; the server takes a row off the
  // opposite list by itself, so a row is never both kept and dropped.
  const excluir = interpretacion?.excluir ?? [];
  const incluir = interpretacion?.incluir ?? [];
  const quitar = (indice) => onCorregir?.({ excluir: [...excluir.filter((i) => i !== indice), indice] });
  const restaurar = (indice) => onCorregir?.({ incluir: [...incluir.filter((i) => i !== indice), indice] });
  return el("div", { class: "assistant-preview" },
    el("div", { class: "stat-row" },
      Stat("Terrenos", vista.conteo, modo === "agregar" ? "en el archivo" : "se importarán"),
      Stat("En el mapa", vista.ubicados, "con coordenadas válidas"),
      Stat("Con precio", vista.con_precio, vista.moneda
        ? `total en ${vista.moneda}; ${fmtCount(vista.con_precio_m2 ?? 0)} con precio por m²`
        : "no se importan precios"),
      Stat("Fuera del mapa", vista.sin_ubicacion,
        vista.ubicacion_invalida ? `${vista.ubicacion_invalida} con coordenadas imposibles` : "sin coordenadas"),
    ),
    clasificacion && el("div", { class: "stat-row" },
      Stat("Nuevas", clasificacion.nuevas, "se agregarán"),
      Stat("Duplicadas", clasificacion.duplicadas, "se omiten"),
      Stat("Conflictos", clasificacion.conflictos, "decide abajo"),
    ),
    clasificacion?.conflictos > 0 && Conflicts(clasificacion.detalle, resoluciones, linea),
    el("figure", { class: "preview-map-figure" },
      mapa.element,
      el("figcaption", { class: "muted" },
        `${plural(vista.puntos.length, "punto")} según las coordenadas del archivo. ` +
        "Son ubicaciones aproximadas, no los linderos del terreno."),
    ),
    vista.moneda && el("p", { class: "note" },
      el("strong", {}, "Moneda de los precios: "), monedaTexto(vista.moneda, vista.moneda_origen),
      ". Los importes se guardan tal cual; no se convierten."),
    MonedasNoAdmitidas(vista),
    Filas(vista, linea, onCorregir && quitar),
    RejectedRows(vista),
    Excluidas(vista, linea, onCorregir && restaurar),
    Findings(vista),
  );
}

/* Prices in an unsupported currency, or mixing two: kept with their amount,
 * never relabelled or converted. */
function MonedasNoAdmitidas(vista) {
  const columnas = vista.monedas_no_admitidas ?? [];
  if (!columnas.length) return null;
  return el("section", { class: "note note-aviso" },
    el("p", {}, el("strong", {}, "No se importan como precio:")),
    el("ul", { class: "rechazadas-list" }, columnas.map((c) => el("li", {},
      `«${c.columna}» (${c.letra}) ${c.motivo ?? `está en ${c.monedas.join(", ")}`}` +
      (c.por_formato ? " según el formato de celda de Excel" : "") +
      ". Se conserva como dato adicional con su importe original; no se convierten monedas."))),
  );
}

function Filas(vista, linea, quitar) {
  const mostradas = vista.filas.length;
  return el("section", { class: "preview-rows" },
    el("h3", { class: "eyebrow" },
      mostradas < vista.conteo ? `Primeros ${mostradas} de ${fmtCount(vista.conteo)} terrenos` : "Terrenos"),
    el("div", { class: "preview-table-wrap" },
      el("table", { class: "table preview-table" },
        el("thead", {}, el("tr", {},
          ["", "Terreno", "Estado · Municipio", "Superficie", "Precio total", "Precio por m²", "Ubicación", "Original",
            ...(quitar ? ["Importar"] : [])]
            .map((t) => el("th", { scope: "col" }, t || linea)))),
        el("tbody", {}, vista.filas.map((f) => el("tr", {},
          el("td", { class: "figure muted" }, String(f.fila)),
          el("td", {}, f.terreno),
          el("td", {}, [f.estado, f.municipio].filter(Boolean).join(" · ") || "—"),
          el("td", { class: "figure" },
            f.superficie_m2 != null ? fmtArea(f.superficie_m2) : fmtHectares(f.superficie_ha)),
          el("td", { class: "figure" }, f.asking_price != null ? fmtPrice(f.asking_price, f.moneda) : "Sin precio"),
          el("td", { class: "figure" }, f.asking_m2 != null ? fmtUnitPrice(f.asking_m2, f.moneda) : "—"),
          el("td", { class: ["figure", !f.ubicado && "muted"] }, f.ubicado ? "En el mapa" : "Fuera del mapa"),
          el("td", {},
            el("details", { class: "original" },
              el("summary", {}, "Ver"),
              el("dl", {}, f.originales.map((o) => [el("dt", {}, o.columna), el("dd", {}, o.valor)])))),
          quitar && f.indice >= 0 && el("td", {},
            el("button", {
              type: "button", class: "btn btn-quiet btn-small",
              onclick: () => quitar(f.indice),
            }, "No importar")),
        ))),
      ),
    ),
  );
}

function Excluidas(vista, linea, restaurar) {
  const excluidas = vista.excluidas ?? [];
  const preambulo = vista.preambulo ?? [];
  if (!excluidas.length && !preambulo.length) return null;
  return el("section", { class: "note" },
    preambulo.length > 0 && el("p", {},
      `Se omiten ${plural(preambulo.length, "fila", "filas")} de título arriba de los encabezados ` +
      `(${linea.toLowerCase()} ${preambulo.join(", ")}).`),
    excluidas.length > 0 && el("p", {},
      el("strong", {}, `${plural(excluidas.length, "fila", "filas")} no son terrenos y no se importan:`)),
    excluidas.length > 0 && el("ul", { class: "rechazadas-list" },
      excluidas.slice(0, 12).map((e) => el("li", {},
        el("span", { class: "figure muted" }, `${linea} ${e.fila}`), " ", e.resumen,
        restaurar && e.indice >= 0 && el("button", {
          type: "button", class: "btn btn-quiet btn-small",
          onclick: () => restaurar(e.indice),
        }, "Sí es un terreno: importarla")))),
  );
}

/* ---------------------------------------------------------- corrections */

export function Correcciones({ interpretacion, formato, abierto, onToggle, onCorregir }) {
  const { hojas, encabezado, encabezados, columnas, destinos } = interpretacion;
  const linea = etiquetaFila(formato);
  const select = (id, etiqueta, opciones, valor, onchange) =>
    el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: id }, etiqueta),
      el("select", { class: "input", id, onchange: (e) => onchange(e.target.value) },
        opciones.map(([v, t]) => el("option", { value: String(v), selected: String(v) === String(valor) }, t))));

  const details = el("details", { class: "corrections", open: abierto },
    el("summary", {}, "Corregir interpretación"),
    el("p", { class: "secondary" },
      "Opcional. Cada cambio vuelve a generar la vista previa; nada se guarda hasta que importes."),
    el("div", { class: "corrections-grid" },
      hojas.length > 1 && select("corr-hoja", formato === "csv" ? "Separador de columnas" : "Tabla",
        hojas.map((h) => [h.id, SEPARADORES[h.separador] ?? `${h.nombre} (${h.filas} filas)`]),
        interpretacion.hoja.id, (v) => onCorregir({ hoja: v })),
      select("corr-encabezado", "Fila de encabezados",
        encabezados.map((e) => [e.indice, `${linea} ${e.linea}: ${e.vista || "(vacía)"}`.slice(0, 90)]),
        encabezado.indice, (v) => onCorregir({ encabezado: Number(v) })),
      OtraFila({ hoja: interpretacion.hoja, encabezado, linea, onCorregir }),
      select("corr-decimal", "Números escritos como texto",
        [["dot", "Punto decimal (1,234.56)"], ["comma", "Coma decimal (1.234,56)"]],
        interpretacion.decimal ?? "dot", (v) => onCorregir({ decimal: v })),
      // Only offered when the file itself does not say: its own markers win.
      interpretacion.hay_precios && interpretacion.moneda_origen !== "archivo" &&
        select("corr-moneda", "Moneda de los precios",
          [["", "Sin definir"], ...Object.entries(MONEDAS)],
          interpretacion.moneda ?? "", (v) => v && onCorregir({ moneda: v })),
    ),
    el("table", { class: "table corrections-table" },
      el("thead", {}, el("tr", {},
        ["Columna del archivo", "Ejemplos", "Se importa como"].map((t) => el("th", { scope: "col" }, t)))),
      el("tbody", {}, columnas.map((c, i) => el("tr", {},
        el("td", {}, el("strong", {}, c.visible), el("span", { class: "muted figure" }, ` · ${c.letra}`)),
        el("td", { class: "muted" }, c.muestras.join(" · ") || "vacía"),
        el("td", {},
          el("label", { class: "visually-hidden", for: `corr-col-${i}` }, `Destino de ${c.visible}`),
          el("select", {
            class: "input", id: `corr-col-${i}`,
            onchange: (e) => onCorregir({ columnas: { [c.id]: e.target.value } }),
          }, destinos.map((d) => el("option", { value: d.valor, selected: d.valor === c.destino }, d.etiqueta)))),
      ))),
    ),
  );
  details.addEventListener("toggle", () => onToggle(details.open));
  return details;
}

/* The header can sit past the rows listed above: name it by the row number
 * printed in the file, which the server translates to the row itself. */
function OtraFila({ hoja, encabezado, linea, onCorregir }) {
  const desde = hoja.primera_linea ?? 1;
  const hasta = hoja.ultima_linea ?? 1;
  const ayuda = el("p", { class: "secondary", "aria-live": "polite" },
    `${linea}s con datos: ${desde} a ${hasta}. Es el número que ves en el archivo, ` +
    "no una posición interna.");
  const entrada = el("input", {
    class: "input", id: "corr-encabezado-linea", type: "number", inputmode: "numeric",
    min: String(desde), max: String(hasta), placeholder: String(encabezado.linea),
  });
  const usar = () => {
    const numero = Number(entrada.value);
    // Out of range is answered here: a row the file does not have is not a
    // question for the server, and the server checks it again anyway.
    if (!Number.isInteger(numero) || numero < desde || numero > hasta) {
      ayuda.textContent = `El archivo tiene datos de la ${linea.toLowerCase()} ${desde} a la ${hasta}; ` +
        "escribe un número de ese rango.";
      entrada.focus();
      return;
    }
    onCorregir({ encabezado_linea: numero });
  };
  return el("div", { class: "rail-field" },
    el("label", { class: "field-label", for: "corr-encabezado-linea" },
      `Otra ${linea.toLowerCase()} del archivo`),
    el("div", { class: "field-pair" },
      entrada,
      el("button", { type: "button", class: "btn btn-quiet", onclick: usar }, "Usar")),
    ayuda,
  );
}

export function Detalles({ interpretacion, abierto, onToggle }) {
  const { columnas, destinos, avisos, formato, automatico, encabezado } = interpretacion;
  const etiqueta = Object.fromEntries(destinos.map((d) => [d.valor, d.etiqueta]));
  const details = el("details", { class: "detection-details", open: abierto },
    el("summary", {}, "Detalles de la detección"),
    el("ul", { class: "detection-facts" },
      el("li", {}, `Encabezados en la fila/línea ${encabezado.linea}.`),
      el("li", {}, interpretacion.decimal === "comma"
        ? "Números escritos como texto: coma decimal." : "Números escritos como texto: punto decimal."),
      el("li", {}, interpretacion.moneda
        ? `Precios en ${monedaTexto(interpretacion.moneda, interpretacion.moneda_origen)}; no se convierten.`
        : interpretacion.hay_precios ? "Moneda de los precios: falta indicarla." : "No se importan precios."),
      ...columnas.filter((c) => c.monedas?.length).map((c) => el("li", {},
        `«${c.visible}»: marcada en ${c.monedas.join(", ")}` +
        (c.monedas_formato?.length ? " según el formato de celda de Excel" : "") + ".")),
      el("li", {}, formato ? `Formato guardado: «${formato.nombre}» (versión ${formato.version}).`
        : "Ningún formato guardado coincidió."),
      el("li", {}, estadoAutomatico(automatico)),
    ),
    avisos.length > 0 && el("ul", { class: "detection-facts" }, avisos.map((a) => el("li", {}, a))),
    el("table", { class: "table corrections-table" },
      el("thead", {}, el("tr", {}, ["Columna", "Se importa como", "Por qué"].map((t) => el("th", { scope: "col" }, t)))),
      el("tbody", {}, columnas.map((c) => el("tr", {},
        el("td", {}, c.visible),
        el("td", {}, etiqueta[c.destino] ?? c.destino),
        el("td", { class: "muted" }, `${ORIGENES[c.origen] ?? c.origen}. ${c.motivo}`),
      ))),
    ),
  );
  details.addEventListener("toggle", () => onToggle(details.open));
  return details;
}

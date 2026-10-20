// Pieces several directions share: the scenario (scope, filters, sort), the
// spreadsheet grid, the terrain record sections and the annotation layout.

import { DESTACADOS, porId, TODOS } from "./datos.mjs";
import { docs, esc, ha, ic, m2, num, pct, precio, SD, sdTexto, ubic, UBIC, coord } from "./comun.mjs";

/* -------------------------------------------------------------- scenario */

// Same task for every direction: in «Bajío Industrial 2026», Guanajuato and
// Querétaro, Industrial and Comercial, sorted by Asking $/m² (high first).
export const FILTRO = { estados: ["Guanajuato", "Querétaro"], tipos: ["Industrial", "Comercial"] };
export const filtrados = TODOS.filter((t) => FILTRO.estados.includes(t.estado) && FILTRO.tipos.includes(t.tipo));
const porPm2 = (a, b) => (a.pm2 == null) - (b.pm2 == null) || (b.pm2 ?? 0) - (a.pm2 ?? 0) || a.nombre.localeCompare(b.nombre);
export const ordenados = [...filtrados].sort(porPm2);
export const enMapa = filtrados.filter((t) => t.ubic !== "ninguna" && (t.x ?? t.cx) != null);
export const sinUbic = filtrados.length - enMapa.length;
export const SEL = porId.apaseo;
export const TOTAL_BASE = 48;

/* ------------------------------------------------------------ the logo */

export const logo = (texto = true) => `<span class="logo"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M12 1.5 22.5 12 12 22.5 1.5 12z" fill="#233fc4"/><path d="M12 7 17 12l-5 5-5-5z" fill="#fff"/><path d="M12 9.6 14.4 12 12 14.4 9.6 12z" fill="#233fc4"/></svg>${texto ? "<b>ARA Map</b>" : ""}</span>`;

/* --------------------------------------------------------------- the grid */

export const COLS = {
  check: { w: 34, h: "" },
  nombre: { w: 282, h: "Nombre de terreno", f: (t) => `<span class="nom">${esc(t.nombre)}</span>` },
  ubic: { w: 108, h: "Ubicación", f: (t) => ubic(t) },
  docs: { w: 74, h: "PDF/JPG", f: (t) => docs(t) },
  tipo: { w: 96, h: "Tipo", f: (t) => t.tipo ? esc(t.tipo) : SD },
  estado: { w: 104, h: "Estado", f: (t) => esc(t.estado) },
  municipio: { w: 132, h: "Municipio", f: (t) => esc(t.municipio) },
  m2: { w: 98, h: "Superficie m²", n: true, f: (t) => m2(t.m2) },
  ha: { w: 80, h: "HA", n: true, f: (t) => ha(t.ha) },
  afect: { w: 80, h: "Afect. %", n: true, f: (t) => pct(t.afect) },
  precio: { w: 122, h: "Asking price", n: true, f: (t) => precio(t.precio) },
  pm2: { w: 104, h: "Asking $/m²", n: true, f: (t) => precio(t.pm2) },
  etapa: { w: 104, h: "Etapa", custom: true, f: (t) => t.etapa ? esc(t.etapa) : SD },
  visita: { w: 112, h: "Fecha de visita", custom: true, f: (t) => t.visita ? esc(t.visita) : SD },
  broker: { w: 190, h: "Broker", custom: true, f: (t) => t.broker ? esc(t.broker) : SD },
  x: { w: 82, h: "X (lat.)", n: true, f: (t) => coord(t.x) },
  y: { w: 92, h: "Y (long.)", n: true, f: (t) => coord(t.y) },
};

export function grid({ filas, cols, sel = null, marcados = new Set(), orden = "pm2", celdas = {}, hover = null, foco = null, ancho }) {
  const cab = cols.map((c) => {
    const d = COLS[c];
    if (c === "check") return `<th class="c-check"><span class="cb${marcados.size ? " mixto" : ""}"></span></th>`;
    const flecha = c === orden ? ic("abajo", "ord") : "";
    return `<th class="${d.n ? "n" : ""}${c === orden ? " ordenada" : ""}${c === "nombre" ? " c-nom" : ""}" style="width:${d.w}px">${d.custom ? `<span class="th-custom" title="Columna de esta base">${esc(d.h)}</span>` : esc(d.h)}${flecha}</th>`;
  }).join("");
  const cuerpo = filas.map((t) => {
    const cls = [t.id === sel ? "sel" : "", marcados.has(t.id) ? "marcada" : "", t.id === hover ? "hover" : ""].join(" ");
    return `<tr class="${cls}">${cols.map((c) => {
      if (c === "check") return `<td class="c-check"><span class="cb${marcados.has(t.id) ? " on" : ""}"></span></td>`;
      const d = COLS[c]; const k = `${t.id}|${c}`; const extra = celdas[k];
      const f = foco === k ? " foco-celda" : "";
      if (extra) return `<td class="${d.n ? "n" : ""} ${extra.cls ?? ""}${f}">${extra.html}</td>`;
      return `<td class="${d.n ? "n" : ""}${c === "nombre" ? " c-nom" : ""}${f}">${d.f(t)}</td>`;
    }).join("")}</tr>`;
  }).join("");
  return `<div class="grid-envoltura"${ancho ? ` style="width:${ancho}px"` : ""}><table class="grid"><thead><tr>${cab}</tr></thead><tbody>${cuerpo}</tbody></table></div>`;
}

export const CSS_GRID = `
.grid-envoltura{overflow:hidden;position:relative;height:100%;background:var(--raised)}
.grid{border-collapse:separate;border-spacing:0;table-layout:fixed;width:max-content;font-size:13px}
.grid th{position:sticky;top:0;height:32px;padding:0 10px;text-align:left;font-weight:600;font-size:12px;color:var(--ink-2);background:var(--paper);border-bottom:1px solid var(--rule-2);border-right:1px solid var(--rule);white-space:nowrap;overflow:hidden}
.grid th.n{text-align:right}
.grid th.ordenada{color:var(--ink)}
.grid th .ord{width:12px;height:12px;margin-left:3px;vertical-align:-1px}
.grid th .th-custom{border-bottom:1px dashed var(--ink-3)}
.grid td{height:34px;padding:0 10px;border-bottom:1px solid var(--rule);border-right:1px solid var(--rule);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:0}
.grid td.n{text-align:right;font-variant-numeric:tabular-nums}
.grid td.c-nom,.grid th.c-nom{position:sticky;left:34px;background:inherit;z-index:1;border-right:1px solid var(--rule-2)}
.grid th.c-nom{background:var(--paper);z-index:2}
.grid .c-check{width:34px;padding:0 0 0 10px;position:sticky;left:0;background:inherit;z-index:1}
.grid th.c-check{background:var(--paper);z-index:2}
.grid tbody tr{background:var(--raised)}
.grid tbody tr:nth-child(even){background:#faf9f7}
.grid tr.sel{background:var(--sel-bg)!important}
.grid tr.sel td:first-child{box-shadow:inset 3px 0 0 var(--ink)}
.grid tr.sel .nom{font-weight:600}
.grid tr.marcada{background:#eceae5!important}
.grid tr.hover{background:var(--hover-bg)!important}
.cb{display:inline-block;width:14px;height:14px;border:1.4px solid var(--ink-3);border-radius:3px;vertical-align:-2px;background:#fff;position:relative}
.cb.on{background:var(--ink);border-color:var(--ink)}
.cb.on::after{content:"";position:absolute;left:3.5px;top:1px;width:4px;height:7px;border:solid #fff;border-width:0 1.6px 1.6px 0;transform:rotate(45deg)}
.cb.mixto{background:var(--ink);border-color:var(--ink)}
.cb.mixto::after{content:"";position:absolute;left:2px;top:5px;width:7px;height:1.6px;background:#fff}
.foco-celda{outline:2px solid var(--ink);outline-offset:-2px}
.celda-edit{background:#fff!important;box-shadow:inset 0 0 0 2px var(--ink)}
.celda-guardando{color:var(--ink-2)}
.celda-guardando i,.celda-conflicto i,.celda-incierta i{font-style:normal;font-size:11px;margin-left:4px}
.celda-conflicto{background:var(--err-bg)!important;box-shadow:inset 0 0 0 1.5px var(--err)}
.celda-conflicto i{color:var(--err);font-weight:600}
.celda-incierta{background:var(--warn-bg)!important}
.celda-incierta i{color:var(--warn);font-weight:600}
`;

/* ------------------------------------------------------- record sections */

export function dl(pares, cls = "") {
  return `<dl class="dl ${cls}">${pares.map(([k, v, extra = ""]) => `<div class="dl-f ${extra}"><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
}

export function seccionesFicha(t, { editando = {}, rol = "operador", compacta = false } = {}) {
  const e = (campo, html) => editando[campo] ?? html;
  const precioS = dl([
    ["Asking price <small>MXN</small>", e("precio", `<span class="n grande">${precio(t.precio)}</span>`)],
    ["Asking $/m² <small>MXN</small>", e("pm2", `<span class="n grande">${precio(t.pm2)}</span>`)],
  ], "dos");
  const sup = dl([
    ["Superficie <small>m²</small>", e("m2", `<span class="n">${m2(t.m2)}</span>`)],
    ["HA", e("ha", `<span class="n">${ha(t.ha)}</span>`)],
    ["Afectaciones", e("afect", `<span class="n">${pct(t.afect)}</span>`)],
  ], "tres");
  const ident = dl([
    ["Tipo de terreno", e("tipo", sdTexto(t.tipo))],
    ["Estado", esc(t.estado)],
    ["Municipio", esc(t.municipio)],
  ], "tres");
  return { precioS, sup, ident };
}

export function ubicacionFicha(t) {
  const fuente = t.ubic === "contorno" ? `Se dibuja con el contorno activo de <b>${esc(t.kmz)}</b>.` : t.ubic === "punto" ? "Se dibuja como punto con sus X/Y. No tiene contorno." : t.ubic === "elegir" ? `<b>${esc(t.kmz)}</b> trae 2 contornos; elige cuál es el del terreno.` : "No se dibuja: no tiene contorno activo ni X/Y válidas.";
  return `<div class="ubic-ficha">${ubic(t, "largo")}<p>${fuente}</p>${dl([["X <small>latitud</small>", `<span class="mono">${coord(t.x)}</span>`], ["Y <small>longitud</small>", `<span class="mono">${coord(t.y)}</span>`]], "dos")}</div>`;
}

export function archivosFicha(t, { subiendo = null, soloLectura = false } = {}) {
  const pdfs = t.pdf.map((n) => `<li class="arch">${ic("doc")}<div><b>${esc(n)}</b><span>PDF · 1.2 MB · versión 1 · Olga Ficticia, 12 oct</span></div><span class="btn sm">Abrir</span></li>`).join("");
  const sube = subiendo ? `<li class="arch subiendo">${ic("subir")}<div><b>${esc(subiendo.nombre)}</b><span>Subiendo · ${subiendo.pct}% de 3.8 MB</span><i class="barra"><i style="width:${subiendo.pct}%"></i></i></div><span class="btn sm quiet">Cancelar</span></li>` : "";
  const vacio = !t.pdf.length && !subiendo ? `<li class="arch vacio">Sin PDF ni JPG.</li>` : "";
  const kmz = t.kmz ? `<li class="arch">${ic(t.ubic === "elegir" ? "elegir" : "contorno")}<div><b>${esc(t.kmz)}</b><span>${t.ubic === "elegir" ? "2 contornos · ninguno activo" : "Contorno activo · versión 1"}</span></div>${t.ubic === "elegir" ? '<span class="btn sm prim">Elegir contorno</span>' : '<span class="btn sm">Descargar</span>'}</li>` : `<li class="arch vacio">Sin KMZ ni KML.</li>`;
  return `<div class="archivos">
    <div class="arch-grupo"><div class="arch-cab"><span>PDF y JPG</span>${soloLectura ? "" : `<span class="btn sm quiet">${ic("mas")}Agregar</span>`}</div><ul>${pdfs}${sube}${vacio}</ul></div>
    <div class="arch-grupo"><div class="arch-cab"><span>KMZ o KML</span>${soloLectura ? "" : `<span class="btn sm quiet">${ic("subir")}${t.kmz ? "Reemplazar" : "Agregar"}</span>`}</div><ul>${kmz}</ul></div>
    ${soloLectura ? "" : '<p class="arch-ayuda">También puedes arrastrar el archivo sobre la ficha. PDF/JPG hasta 25 MiB · KMZ 20 MiB · KML 16 MiB.</p>'}
  </div>`;
}

export function personalizadas(t, editando = {}) {
  return dl([
    ["Etapa <small>opción</small>", editando.etapa ?? sdTexto(t.etapa)],
    ["Fecha de visita", editando.visita ?? sdTexto(t.visita)],
    ["Broker", sdTexto(t.broker)],
    ["Uso de suelo", sdTexto(t.uso)],
  ], "dos");
}

export const CSS_FICHA = `
.dl{margin:0;display:grid;gap:10px 16px}
.dl.dos{grid-template-columns:1fr 1fr}
.dl.tres{grid-template-columns:1fr 1fr 1fr}
.dl-f dt{font-size:11.5px;color:var(--ink-2);margin-bottom:2px}
.dl-f dt small{font-size:10.5px;color:var(--ink-3);margin-left:3px}
.dl-f dd{margin:0;font-size:13px}
.dl-f dd .grande{font-size:17px;font-weight:600;letter-spacing:-.01em}
.dl-f.editable dd{border-radius:5px;margin:-3px -6px;padding:3px 6px;background:var(--hover-bg)}
.mono{font-family:var(--mono);font-size:12px}
.sec{padding:14px 18px;border-top:1px solid var(--rule)}
.sec h3{margin:0 0 10px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);font-weight:600;display:flex;justify-content:space-between;align-items:center}
.sec h3 em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;color:var(--ink-3)}
.ubic-ficha p{margin:6px 0 10px;color:var(--ink-2);font-size:12.5px}
.ubic-ficha .ubic{font-size:13px;color:var(--ink);font-weight:500}
.archivos{display:grid;gap:12px}
.arch-cab{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--ink-2);margin-bottom:4px}
.archivos ul{list-style:none;margin:0;padding:0;border:1px solid var(--rule);border-radius:8px;background:var(--overlay)}
.arch{display:flex;align-items:center;gap:10px;padding:8px 10px}
.arch+.arch{border-top:1px solid var(--rule)}
.arch div{flex:1;min-width:0}
.arch b{display:block;font-weight:500;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arch span:not(.btn){display:block;font-size:11.5px;color:var(--ink-2)}
.arch.vacio{color:var(--ink-3);font-size:12px;font-style:italic}
.arch.subiendo{background:#fafaf8}
.barra{display:block;height:4px;border-radius:2px;background:var(--rule);margin-top:5px;overflow:hidden}
.barra i{display:block;height:100%;background:var(--ink)}
.arch-ayuda{margin:0;font-size:11.5px;color:var(--ink-2)}
.campo-edit{display:flex;align-items:center;gap:6px;height:32px;padding:0 8px;border:2px solid var(--ink);border-radius:6px;background:#fff;font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.campo-edit small{font-size:11px;font-weight:500;color:var(--ink-2);margin-left:auto}
.campo-edit .cursor{display:inline-block;width:1.5px;height:17px;background:var(--ink);margin-left:-4px}
.ayuda-campo{display:block;font-size:11px;color:var(--ink-2);margin-top:4px}
.guardado-campo{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--ok);margin-left:6px}
.guardado-campo .ic{width:13px;height:13px}
.guardando-campo{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--ink-2);margin-left:6px}
.select-edit{display:flex;align-items:center;justify-content:space-between;height:30px;padding:0 8px;border:2px solid var(--ink);border-radius:6px;background:#fff}
`;

/* --------------------------------------------- annotated frame + notes */

export function conNotas({ w, h, ui, marcas = [], notas = [], titulo, subtitulo }) {
  const pins = marcas.map(([n, x, y]) => `<i class="pin" style="left:${x}px;top:${y}px">${n}</i>`).join("");
  return `<div class="hoja">
  <div class="hoja-ui"><div class="lienzo" style="width:${w}px;height:${h}px">${ui}${pins}</div></div>
  <aside class="notas"><p class="notas-dir">${esc(subtitulo)}</p><h1>${esc(titulo)}</h1><ol>${notas.map((n, i) => `<li><i class="pin">${i + 1}</i><div>${n}</div></li>`).join("")}</ol>
  <p class="notas-pie">Mockup estático con datos ficticios. Las notas no forman parte de la interfaz.</p></aside></div>`;
}

export const CSS_NOTAS = `
.hoja{display:flex;align-items:stretch;width:max-content}
.hoja-ui{flex:none}
.notas{width:330px;flex:none;background:#26231f;color:#efede9;padding:22px 22px 18px;font-size:12.5px;line-height:1.45;position:relative}
.notas h1{font-size:19px;line-height:1.2;margin:0 0 16px;font-weight:600;color:#fff;letter-spacing:-.01em}
.notas-dir{margin:0 0 4px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#c4bfb6}
.notas ol{list-style:none;margin:0;padding:0;display:grid;gap:12px}
.notas li{display:flex;gap:10px}
.notas li div{flex:1}
.notas li b{color:#fff}
.notas-pie{position:absolute;bottom:14px;left:22px;right:22px;margin:0;font-size:11px;color:#a9a399}
.pin{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:10px;background:#e8562a;color:#fff;font:700 11px/1 var(--font);font-style:normal;flex:none;box-shadow:0 0 0 2px #fff}
.lienzo>.pin{position:absolute;z-index:60}
.notas .pin{box-shadow:none;margin-top:1px}
`;

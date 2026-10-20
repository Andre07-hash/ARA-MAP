// Direction C — «Atlas de expedientes» (exploration).
// The map is the ground everything sits on. Each terrain is an expediente
// whose completeness is visible (datos, precio, ubicación, PDF), so the work
// queue is "what is missing" rather than "which page of the table". The
// spreadsheet is a drawer («Hoja») that rises over the map.

import { porId } from "./datos.mjs";
import { CSS_TEL, docs, esc, ic, leyendaPrecio, m2, mapa, precio, SD, telefono, ubic } from "./comun.mjs";
import {
  archivosFicha, conNotas, CSS_FICHA, CSS_GRID, CSS_NOTAS, enMapa, filtrados, grid, logo, ordenados, personalizadas,
  SEL, sinUbic, TOTAL_BASE, ubicacionFicha,
} from "./piezas.mjs";

const W = 1440, H = 900;

/* ----------------------------------------------- completeness of a record */

// Only presence is read; no value is computed or converted.
export function completitud(t) {
  return {
    datos: t.tipo && t.estado && t.municipio && (t.m2 != null || t.ha != null) ? "si" : "no",
    precio: t.precio != null || t.pm2 != null ? "si" : "no",
    ubic: t.ubic === "contorno" ? "si" : t.ubic === "punto" ? "parcial" : t.ubic === "elegir" ? "aviso" : "no",
    pdf: t.pdf.length ? "si" : "no",
  };
}
const NOMBRES = { datos: "Datos", precio: "Precio", ubic: "Ubicación", pdf: "PDF" };
const faltan = (t) => {
  const c = completitud(t), f = [];
  if (c.datos === "no") f.push(t.tipo ? "datos" : "tipo");
  if (c.precio === "no") f.push("precio");
  if (c.ubic === "no") f.push("ubicación");
  if (c.ubic === "aviso") f.push("elegir contorno");
  if (c.pdf === "no") f.push("PDF");
  return f;
};
export function tira(t, { grande = false } = {}) {
  const c = completitud(t);
  return `<span class="tira${grande ? " grande" : ""}" role="img" aria-label="${esc(Object.entries(c).map(([k, v]) => `${NOMBRES[k]}: ${v === "si" ? "completo" : v === "parcial" ? "sólo punto X/Y" : v === "aviso" ? "por elegir" : "falta"}`).join(", "))}">${Object.entries(c).map(([k, v]) => `<i class="seg-${v}" title="${NOMBRES[k]}">${grande ? `<b>${NOMBRES[k]}</b><small>${v === "si" ? (k === "ubic" ? "Contorno" : "Completo") : v === "parcial" ? "Punto X/Y" : v === "aviso" ? "Elegir" : "Falta"}</small>` : ""}</i>`).join("")}</span>`;
}
const cuenta = (pred) => filtrados.filter(pred).length;
const PEND = {
  todos: filtrados.length,
  precio: cuenta((t) => completitud(t).precio === "no"),
  ubic: cuenta((t) => completitud(t).ubic === "no"),
  punto: cuenta((t) => completitud(t).ubic === "parcial"),
  pdf: cuenta((t) => completitud(t).pdf === "no"),
};

const CSS = `${CSS_GRID}${CSS_FICHA}${CSS_NOTAS}
.vidrio{background:rgba(253,253,252,.86);-webkit-backdrop-filter:blur(14px) saturate(1.15);backdrop-filter:blur(14px) saturate(1.15);border:1px solid rgba(203,199,193,.9);box-shadow:0 1px 2px rgba(0,0,0,.06),0 10px 30px rgba(0,0,0,.12)}
.top-c{position:absolute;left:12px;right:12px;top:12px;height:52px;border-radius:14px;display:flex;align-items:center;gap:10px;padding:0 10px 0 14px;z-index:6}
.top-c .der{margin-left:auto;display:flex;gap:10px;align-items:center}
.ambito-c{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:8px;font-weight:600;font-size:14px}
.cmd{display:flex;align-items:center;gap:8px;height:34px;width:380px;padding:0 10px;border-radius:9px;background:#fff;border:1px solid var(--borde-campo);color:var(--ink-3)}
.cmd .kbd{margin-left:auto}
.pend{position:absolute;left:12px;top:74px;display:flex;gap:6px;z-index:6;align-items:center}
.pend .chip{height:28px;padding:0 10px;border-radius:14px;font-size:12.5px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.pend .chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.pend .chip.on .ic{color:#fff}
.pend .chip em{font-style:normal;color:var(--ink-2);font-variant-numeric:tabular-nums}
.pend .chip.on em{color:#d9d6cf}
.pend .lbl{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);font-weight:600;background:rgba(236,235,230,.9);padding:3px 6px;border-radius:5px}
.panel{position:absolute;left:12px;top:112px;bottom:64px;width:384px;border-radius:14px;z-index:5;overflow:hidden;display:flex;flex-direction:column}
.panel-cab{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--rule);font-size:12.5px;color:var(--ink-2)}
.panel-cab b{color:var(--ink)}
.panel-cab .der{margin-left:auto;display:flex;gap:6px;align-items:center}
.panel ul{list-style:none;margin:0;padding:0;overflow:hidden}
.panel li{padding:9px 14px;border-bottom:1px solid var(--rule);display:grid;grid-template-columns:1fr auto;gap:3px 10px}
.panel li b{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.panel li .pm{font-weight:600;font-variant-numeric:tabular-nums;text-align:right}
.panel li .pm small{font-weight:400;font-size:11px;color:var(--ink-2)}
.panel li .s{color:var(--ink-2);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.panel li .f{font-size:11.5px;color:var(--ink-2);text-align:right;white-space:nowrap}
.panel li .f b{font-size:11.5px;font-weight:600;color:var(--warn)}
.panel li.sel{background:rgba(232,229,223,.95);box-shadow:inset 3px 0 0 var(--ink)}
.panel li.hover{background:rgba(241,239,235,.9)}
.tira{display:inline-flex;gap:3px;align-items:center}
.tira i{display:inline-block;width:14px;height:8px;border-radius:2px;border:1.4px solid var(--ink)}
.tira i.seg-si{background:var(--ink)}
.tira i.seg-parcial{background:linear-gradient(90deg,var(--ink) 50%,transparent 50%)}
.tira i.seg-aviso{border-color:var(--warn);background:repeating-linear-gradient(45deg,var(--warn) 0 2px,transparent 2px 4px)}
.tira i.seg-no{background:#fff;border-style:dashed;border-color:var(--ink-3)}
.tira.grande{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;width:100%;max-width:560px}
.tira.grande i{width:auto;height:auto;border-radius:8px;padding:6px 9px;display:flex;flex-direction:column;border-width:1.5px;min-width:0}
.tira.grande i b{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-2);font-weight:600}
.tira.grande i small{font-size:12.5px;font-weight:600;white-space:nowrap}
.tira.grande i.seg-si{background:var(--ok-bg);border-color:#a9cfab;color:var(--ink)}
.tira.grande i.seg-si small::before{content:"✓ ";color:var(--ok)}
.tira.grande i.seg-parcial{background:#fff;border-color:var(--ink-3);color:var(--ink)}
.tira.grande i.seg-no{background:#fff;color:var(--warn)}
.tira.grande i.seg-aviso{background:var(--warn-bg);color:var(--warn)}
.cajon{position:absolute;left:50%;transform:translateX(-50%);bottom:12px;height:40px;border-radius:20px;display:flex;align-items:center;gap:10px;padding:0 16px;font-size:13px;z-index:6}
.cajon .kbd{margin-left:4px}
.exp{position:absolute;right:12px;top:112px;width:392px;border-radius:14px;z-index:6;overflow:hidden;background:var(--overlay)}
.exp-cab{padding:14px 16px 10px}
.exp-cab h2{margin:0;font-size:16px;line-height:1.3;font-weight:650}
.exp-cab .sub{margin:3px 0 10px;font-size:12px;color:var(--ink-2)}
.exp .sec{padding:12px 16px}
.exp-pie{display:flex;gap:8px;padding:12px 16px;border-top:1px solid var(--rule)}
.ctrl-c{position:absolute;right:12px;z-index:5}
.pag{position:absolute;inset:0;background:var(--paper)}
.pag-cab{height:56px;display:flex;align-items:center;gap:12px;padding:0 20px;border-bottom:1px solid var(--rule);background:var(--raised)}
.pag-cab .migas{display:flex;gap:6px;align-items:center;color:var(--ink-2);font-size:13px}
.pag-cab .migas b{color:var(--ink)}
.pag-cab .der{margin-left:auto;display:flex;gap:8px;align-items:center}
.pag-cuerpo{position:absolute;top:56px;left:0;right:0;bottom:0;display:grid;grid-template-columns:1fr 470px;gap:0}
.pag-izq{padding:22px 28px;overflow:hidden;border-right:1px solid var(--rule)}
.pag-der{padding:22px 24px;overflow:hidden;background:var(--raised)}
.pag h1{margin:0 0 4px;font-size:24px;line-height:1.2;font-weight:650;letter-spacing:-.015em;max-width:760px}
.pag .sub{margin:0 0 16px;color:var(--ink-2);font-size:13px}
.bloque{background:var(--raised);border:1px solid var(--rule);border-radius:12px;margin-top:16px}
.bloque h3{margin:0;padding:12px 16px;border-bottom:1px solid var(--rule);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);font-weight:600;display:flex;justify-content:space-between}
.bloque h3 em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;color:var(--ink-3)}
.bloque .cuerpo{padding:14px 16px}
.actividad{list-style:none;margin:0;padding:0;display:grid;gap:12px;font-size:12.5px}
.actividad li{display:grid;grid-template-columns:18px 1fr;gap:8px}
.actividad li .ic{color:var(--ink-2);margin-top:1px}
.actividad li span{color:var(--ink-2);display:block;font-size:11.5px}
.mini-mapa{border-radius:10px;overflow:hidden;border:1px solid var(--rule-2);position:relative}
.aviso-red{display:flex;gap:10px;align-items:center;padding:10px 14px;background:var(--err-bg);border-bottom:1px solid #eab9b9;color:var(--err);font-size:12.5px}
.aviso-red b{color:var(--err)}
.aviso-red span{color:var(--ink)}
.aviso-red .der{margin-left:auto;display:flex;gap:8px}
.cajon-alto{position:absolute;left:0;right:0;bottom:0;height:560px;border-radius:16px 16px 0 0;z-index:7;overflow:hidden;background:var(--raised);box-shadow:0 -8px 30px rgba(0,0,0,.18);border:1px solid var(--rule-2)}
.cajon-cab{height:46px;display:flex;align-items:center;gap:10px;padding:0 16px;border-bottom:1px solid var(--rule)}
.cajon-cab .der{margin-left:auto;display:flex;gap:8px;align-items:center}
.agarre{width:38px;height:5px;border-radius:3px;background:var(--rule-2);position:absolute;left:50%;top:6px;transform:translateX(-50%)}
${CSS_TEL}
`;

function topBar({ rol = "admin", est = `<span class="estado-guardado ok">${ic("ok")}Todo guardado</span>` } = {}) {
  return `<div class="top-c vidrio">${logo(false)}<span class="ambito-c">Bajío Industrial 2026 ${ic("abajo")}</span>
  <span class="cmd">${ic("buscar")}Buscar terreno, municipio o acción…<span class="kbd">⌘K</span></span>
  <span class="btn">${ic("filtro")}Filtros <span class="cont" style="display:inline-flex;min-width:18px;height:18px;border-radius:9px;background:var(--ink);color:#fff;font-size:11px;align-items:center;justify-content:center;padding:0 5px">2</span></span>
  <div class="der">${est}<span class="btn prim">${ic("mas")}Agregar</span><span class="btn icono quiet" title="${rol === "admin" ? "Ada Ficticia · Administradora" : "Olga Ficticia · Operadora"}">${ic("usuario")}</span></div></div>`;
}

function pendientes(activo = "todos") {
  const c = (k, txt, n, icono) => `<span class="chip vidrio${activo === k ? " on" : ""}">${icono ? ic(icono) : ""}${txt} <em>${n}</em></span>`;
  return `<div class="pend"><span class="lbl">22 filtrados · Ver</span>${c("todos", "Todos", PEND.todos)}${c("precio", "Sin precio", PEND.precio, "aviso")}${c("ubic", "Sin ubicación", PEND.ubic, "ninguna")}${c("punto", "Sólo punto X/Y", PEND.punto, "punto")}${c("pdf", "Sin PDF", PEND.pdf, "doc")}
  <span class="chip vidrio" style="margin-left:6px">Estado: <b>GTO, QRO</b>${ic("cerrar")}</span><span class="chip vidrio">Tipo: <b>Industrial, Comercial</b>${ic("cerrar")}</span></div>`;
}

function panel({ sel = "apaseo", hover = null, desde = 0, n = 13 }) {
  const filas = ordenados.slice(desde, desde + n).map((t) => {
    const f = faltan(t);
    return `<li class="${t.id === sel ? "sel" : ""} ${t.id === hover ? "hover" : ""}"><b title="${esc(t.nombre)}">${esc(t.nombre)}</b><span class="pm">${t.pm2 == null ? SD : precio(t.pm2)}<small>/m²</small></span>
    <span class="s">${t.tipo ?? "Sin tipo"} · ${esc(t.municipio)} · ${m2(t.m2)} m²</span><span class="f">${tira(t)}</span>
    <span class="s" style="grid-column:1/3;font-size:11.5px">${f.length ? `Falta: <b style="font-size:11.5px;color:var(--warn)">${f.join(", ")}</b>` : `<span style="color:var(--ok)">${ic("ok")} Expediente completo</span>`}</span></li>`;
  }).join("");
  return `<section class="panel vidrio" aria-label="Expedientes"><div class="panel-cab"><b>${filtrados.length} expedientes</b><span>· Asking $/m² ↓</span><div class="der"><span class="btn sm quiet">${ic("lista")}</span><span class="btn sm quiet">${ic("cerrar")}</span></div></div><ul>${filas}</ul></section>`;
}

const cajon = () => `<div class="cajon vidrio">${ic("tabla")}<b>Hoja</b> · 22 terrenos · todas las columnas ${ic("arriba")}<span class="kbd">H</span></div>`;
const controles = (top = 112) => `<div class="mapa-ctrl ctrl-c" style="top:${top}px"><span>+</span><span>−</span><span style="font-size:13px">${ic("encuadrar")}</span><span style="font-size:13px">${ic("capas")}</span></div>`;

/* ------------------------------------------------------------- screens */

function c1() {
  const { svg, px } = mapa({ w: W, h: H, centro: [20.92, -101.25], spanLon: 3.0, filas: filtrados, sel: "apaseo", hover: "silao", id: "c1" });
  const ui = `${svg}${topBar()}${pendientes()}${panel({ sel: "apaseo", hover: "silao", desde: 4 })}${controles()}
  <div class="flota" style="right:12px;bottom:64px">${leyendaPrecio({ total: enMapa.length, fuera: sinUbic })}</div>${cajon()}
  <span class="ilustrativo" style="right:12px;bottom:20px">Mapa base ilustrativo</span>`;
  return conNotas({
    w: W, h: H, ui, titulo: "1 · Atlas: el mapa como mesa de trabajo", subtitulo: "C · Atlas de expedientes — exploración",
    marcas: [[1, 470, 20], [2, 92, 70], [3, 380, 160], [4, 760, 858], [5, 330, 116]],
    notas: [
      "<b>Una sola caja de búsqueda y acciones</b> (⌘K): terrenos, municipios y comandos como «Agregar terreno» o «Ir a Península y Sureste».",
      "<b>Pendientes como forma de trabajar:</b> los mismos 22 terrenos filtrados, agrupados por lo que les falta. Sólo se lee si el dato existe; nada se calcula ni se convierte.",
      "<b>Tira de expediente</b> en cada renglón: Datos · Precio · Ubicación · PDF. Relleno, mitad, rayado o punteado, y además el texto «Falta: …». No depende del color.",
      "<b>La tabla es un cajón</b> («Hoja», tecla H) que sube sobre el mapa con todas las columnas y la edición tipo hoja de cálculo.",
      "<b>Material translúcido sólo en la capa de controles</b>, nunca en el contenido (HIG, materials › Liquid Glass). Con «Reducir transparencia» se vuelve opaco.",
    ],
  });
}

function expTarjeta(t, { rol = "operador" } = {}) {
  return `<aside class="exp vidrio" aria-label="Expediente"><div class="exp-cab"><div style="display:flex;justify-content:space-between;gap:8px"><span class="etq">Expediente</span><span style="display:flex;gap:4px"><span class="btn icono quiet sm">${ic("expandir")}</span><span class="btn icono quiet sm">${ic("cerrar")}</span></span></div>
  <h2 style="margin-top:6px">${esc(t.nombre)}</h2><p class="sub">${esc(t.tipo)} · ${esc(t.municipio)}, ${esc(t.estado)}</p>${tira(t, { grande: true })}</div>
  <div class="sec" style="border-top:1px solid var(--rule)"><dl class="dl dos"><div class="dl-f"><dt>Asking price <small>MXN</small></dt><dd class="n" style="font-size:16px;font-weight:600">${precio(t.precio)}</dd></div><div class="dl-f"><dt>Asking $/m² <small>MXN</small></dt><dd class="n" style="font-size:16px;font-weight:600">${precio(t.pm2)}</dd></div><div class="dl-f"><dt>Superficie</dt><dd class="n">${m2(t.m2)} m² · ${t.ha} ha</dd></div><div class="dl-f"><dt>Afectaciones</dt><dd class="n">${t.afect}%</dd></div></dl></div>
  <div class="sec" style="border-top:1px solid var(--rule)"><h3>Archivos</h3>${archivosFicha(t, { soloLectura: true })}</div>
  <div class="exp-pie"><span class="btn prim" style="flex:1;justify-content:center">${ic("expandir")}Abrir expediente</span><span class="btn">${ic("historial")}Actividad</span></div></aside>`;
}

function c2() {
  const { svg, px } = mapa({ w: W, h: H, centro: [20.63, -100.72], spanLon: 0.95, filas: filtrados, sel: "apaseo", escala: "local", id: "c2" });
  const [sx, sy] = px(SEL.x, SEL.y);
  const ui = `${svg}<span class="etq-sel" style="position:absolute;left:${sx + 16}px;top:${sy - 13}px;display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:6px;background:var(--ink);color:#fff;font-size:12px;font-weight:500">${ic("contorno")}Polígono Apaseo El Grande…</span>
  ${topBar({ rol: "operador" })}${pendientes()}${panel({ sel: "apaseo", desde: 12, n: 6 }).replace('bottom:64px', 'bottom:auto;height:520px').replace('class="panel vidrio"', 'class="panel vidrio" style="bottom:auto;height:452px"')}
  ${expTarjeta(SEL)}${controles(112).replace("right:12px", "right:416px")}${cajon()}<span class="ilustrativo" style="left:12px;bottom:20px">Mapa base ilustrativo</span>`;
  return conNotas({
    w: W, h: H, ui, titulo: "2 · Terreno seleccionado: expediente sobre el mapa", subtitulo: "C · Atlas de expedientes — exploración",
    marcas: [[1, sx - 30, sy - 30], [2, 1032, 230], [3, 1032, 410], [4, 1032, 622]],
    notas: [
      "<b>Seleccionar acerca el mapa al contorno</b> sin perder la lista ni los pendientes; la etiqueta nombra lo seleccionado.",
      "<b>La tira grande dice el estado del expediente en palabras</b>: datos completos, precio, contorno activo, PDF.",
      "<b>Archivos de consulta directa</b>: abrir el PDF o descargar el KMZ sin cambiar de pantalla.",
      "<b>«Abrir expediente»</b> pasa al detalle completo (pantalla 3). Esc vuelve aquí con el mismo encuadre.",
    ],
  });
}

function c3() {
  const t = SEL;
  const { svg } = mapa({ w: 420, h: 236, centro: [20.565, -100.69], spanLon: 0.11, filas: filtrados, sel: "apaseo", escala: "local", id: "c3", etiquetas: false });
  const campo = (k, v, extra = "") => `<div class="dl-f ${extra}"><dt>${k}</dt><dd>${v}</dd></div>`;
  const ui = `<div class="pag"><header class="pag-cab">${logo(false)}<span class="btn quiet">${ic("izq")}Atlas</span><span class="migas">Bajío Industrial 2026 ${ic("der")} <b>Expediente</b></span>
  <div class="der"><span class="estado-guardado trabajando">${ic("pendiente")}Guardando Asking price…</span><span class="btn icono" title="Anterior (K)">${ic("arriba")}</span><span class="btn icono" title="Siguiente (J)">${ic("abajo")}</span><span style="font-size:12px;color:var(--ink-2)">10 de 22</span><span class="btn icono">${ic("mas3")}</span></div></header>
  <div class="pag-cuerpo"><div class="pag-izq">
    <h1>${esc(t.nombre)}</h1><p class="sub">${esc(t.tipo)} · ${esc(t.municipio)}, ${esc(t.estado)} · versión 3 · editado por Olga Ficticia hoy 10:42</p>
    ${tira(t, { grande: true })}
    <div class="bloque"><h3>Precio y superficie <em>Clic en un dato para editarlo</em></h3><div class="cuerpo"><dl class="dl tres">
      ${campo("Asking price <small>MXN</small>", `<span class="campo-edit" style="font-size:16px">$92,500,000<span class="cursor"></span><small>MXN</small></span>`)}
      ${campo("Asking $/m² <small>MXN</small>", `<span class="n grande">$500</span><span class="ayuda-campo">Ya tiene valor: no se recalcula.</span>`)}
      ${campo("Afectaciones", `<span class="n grande">12%</span>`)}
      ${campo("Superficie <small>m²</small>", `<span class="n">184,500</span>`)}${campo("HA", `<span class="n">18.45</span>`)}${campo("Tipo de terreno", "Industrial")}
    </dl></div></div>
    <div class="bloque"><h3>Columnas de Bajío Industrial 2026 <em>4 columnas · Gestionar</em></h3><div class="cuerpo">${personalizadas(t, { etapa: `Oferta <span class="guardado-campo">${ic("ok")}Guardado</span>` })}</div></div>
    <div class="bloque"><h3>Comentarios</h3><div class="cuerpo"><p style="margin:0">${esc(t.notas)}</p></div></div>
  </div>
  <div class="pag-der">
    <div class="mini-mapa">${svg}<span class="flota" style="left:10px;top:10px;padding:5px 8px;font-size:12px;display:flex;gap:6px;align-items:center;border-radius:7px">${ic("contorno")}Contorno activo · poligono-apaseo.kmz</span><span class="btn sm" style="position:absolute;right:10px;bottom:10px">${ic("mapa")}Ver en el atlas</span></div>
    <p style="font-size:12px;color:var(--ink-2);margin:8px 0 0">X 20.555 · Y −100.7 también capturadas; el mapa usa el contorno.</p>
    <div class="bloque"><h3>Documentos <em>1 PDF · 1 KMZ</em></h3><div class="cuerpo">${archivosFicha(t)}</div></div>
    <div class="bloque"><h3>Actividad <em>datos y archivos</em></h3><div class="cuerpo"><ul class="actividad">
      <li>${ic("editar")}<div>Olga Ficticia cambió <b>Etapa</b> a «Oferta»<span>hoy 10:42 · versión 3</span></div></li>
      <li>${ic("contorno")}<div>Ada Ficticia subió <b>poligono-apaseo.kmz</b>; contorno activado<span>12 oct · versión 2</span></div></li>
      <li>${ic("doc")}<div>Olga Ficticia agregó <b>ficha-tecnica.pdf</b><span>12 oct</span></div></li>
      <li>${ic("mas")}<div>Ada Ficticia creó el terreno en Bajío Industrial 2026<span>3 oct · versión 1</span></div></li></ul></div></div>
  </div></div></div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "3 · Expediente completo en edición", subtitulo: "C · Atlas de expedientes — exploración",
    marcas: [[1, 14, 76], [2, 30, 140], [3, 30, 234], [4, 1440 - 470 + 8, 66], [5, 1440 - 470 + 8, 560], [6, 640, 14]],
    notas: [
      "<b>Una página por terreno</b> con dirección propia: se puede enviar el enlace a otra persona con acceso. «Atlas» y Esc regresan al mismo encuadre y filtros.",
      "<b>El nombre completo manda</b>, sin truncar; debajo, versión y última edición.",
      "<b>La tira grande</b> resume el expediente y lleva a lo que falta (clic en «Falta»).",
      "<b>Ubicación con su fuente</b> y un mapa pequeño con el contorno; «Ver en el atlas» vuelve al mapa completo.",
      "<b>Actividad en una sola línea de tiempo</b>: cambios de datos y de archivos juntos. Hoy viven en dos historiales distintos; unirlos en la vista no exige datos nuevos.",
      "<b>Recorrer los 22 en serie</b> con J/K, guardando cada campo con su versión.",
    ],
  });
}

function c4() {
  const t = SEL;
  const { svg } = mapa({ w: 390, h: 844, centro: [20.62, -100.66], spanLon: 0.62, filas: filtrados, sel: "apaseo", escala: "local", id: "c4" });
  const p1 = `<div style="position:absolute;inset:0">${svg}</div><div class="tel-estado" style="position:relative;z-index:2"><span>9:41</span><span>●●● ▮</span></div>
  <div class="vidrio" style="position:absolute;left:12px;right:12px;top:50px;height:44px;border-radius:22px;display:flex;align-items:center;gap:8px;padding:0 14px;color:var(--ink-2)">${ic("buscar")}Bajío Industrial 2026<span class="btn sm" style="margin-left:auto">${ic("filtro")}2</span></div>
  <div style="position:absolute;left:12px;top:104px;display:flex;gap:6px"><span class="chip vidrio" style="height:30px">Sin precio <em>${PEND.precio}</em></span><span class="chip vidrio" style="height:30px">Sin PDF <em>${PEND.pdf}</em></span></div>
  <div class="vidrio" style="position:absolute;left:12px;right:12px;bottom:86px;border-radius:16px;padding:12px 14px;background:rgba(255,255,255,.95)">
    <div style="display:flex;justify-content:space-between;gap:8px"><b style="font-size:15px;line-height:1.3">${esc(t.nombre)}</b><span class="btn icono quiet sm">${ic("cerrar")}</span></div>
    <p style="margin:2px 0 8px;color:var(--ink-2);font-size:12.5px">Apaseo el Grande · 184,500 m² · $500/m²</p>
    <div style="display:flex;justify-content:space-between;align-items:center">${tira(t)}<span class="btn prim">${ic("expandir")}Expediente</span></div></div>
  <div class="vidrio" style="position:absolute;left:50%;transform:translateX(-50%);bottom:28px;height:42px;border-radius:21px;display:flex;align-items:center;gap:8px;padding:0 18px;font-weight:600">${ic("lista")}Lista · 22</div>`;
  const p2 = `<div class="tel-estado"><span>9:41</span><span>●●● ▮</span></div>
  <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 12px 4px 8px"><span class="btn quiet">${ic("izq")}Atlas</span><span style="font-size:12px;color:var(--ink-2)">10 de 22 ${ic("arriba")}${ic("abajo")}</span></div>
  <h1 style="margin:4px 16px 4px;font-size:21px;line-height:1.22;font-weight:650">${esc(t.nombre)}</h1><p style="margin:0 16px 10px;color:var(--ink-2)">Industrial · Apaseo el Grande, Gto.</p>
  <div style="padding:0 16px;overflow:hidden">${tira(t, { grande: true }).replace(/min-width:96px/g, "")}</div>
  <div class="bloque" style="margin:14px 16px 0"><div class="cuerpo"><dl class="dl dos"><div class="dl-f"><dt>Asking price <small>MXN</small></dt><dd class="n" style="font-weight:600;font-size:16px">$92,250,000</dd></div><div class="dl-f"><dt>Asking $/m²</dt><dd class="n" style="font-weight:600;font-size:16px">$500</dd></div><div class="dl-f"><dt>Superficie</dt><dd>184,500 m²</dd></div><div class="dl-f"><dt>Afectaciones</dt><dd>12%</dd></div></dl></div></div>
  <div class="bloque" style="margin:12px 16px 0"><h3>Documentos</h3><div class="cuerpo">${archivosFicha(t, { soloLectura: true })}</div></div>`;
  const ui = `<div class="tels">${telefono(p1, "Atlas: mapa a pantalla completa y tarjeta del terreno")}${telefono(p2.replace(/class="tira grande"/, 'class="tira grande" style="display:grid;grid-template-columns:1fr 1fr;gap:6px"'), "Expediente en una columna")}</div>`;
  return conNotas({
    w: 900, h: H, ui, titulo: "4 · Ancho reducido (390 px)", subtitulo: "C · Atlas de expedientes — exploración",
    marcas: [[1, 12, 64], [2, 12, 120], [3, 12, 650], [4, 448, 190]],
    notas: [
      "<b>En el teléfono, el atlas es literal</b>: mapa completo, búsqueda flotante y el botón «Lista · 22».",
      "<b>Los pendientes caben</b> como chips desplazables; sirven para preparar una visita (qué falta de cada terreno).",
      "<b>Tarjeta del terreno</b> sobre el mapa, al alcance del pulgar, con su tira y acceso al expediente.",
      "<b>Expediente en una columna</b>: la tira en dos filas, datos clave y documentos. La edición está disponible campo por campo.",
    ],
  }).replace('class="lienzo"', 'class="lienzo" style="background:#e9e6df"');
}

function c5() {
  const { svg } = mapa({ w: W, h: H, centro: [20.92, -101.25], spanLon: 3.0, filas: filtrados, sel: null, id: "c5" });
  const filas = ordenados.filter((t) => completitud(t).precio === "no");
  const celdas = {
    "sanmiguel|precio": { cls: "celda-incierta", html: `<span class="marca-celda">${ic("pendiente")}</span>$48,000,000` },
    "sanmiguel|pm2": { cls: "celda-incierta", html: `<span class="marca-celda">${ic("pendiente")}</span>$500` },
    "r0|precio": { cls: "foco-celda celda-edit", html: `$9,000,0<span class="cursor" style="display:inline-block;width:1.5px;height:15px;background:var(--ink);vertical-align:-2px"></span>` },
  };
  const ui = `${svg}${topBar({ est: `<span class="estado-guardado alerta">${ic("error")}Sin conexión · 2 cambios por confirmar</span>` })}${pendientes("precio")}
  <div class="cajon-alto" style="height:470px" role="region" aria-label="Hoja"><span class="agarre"></span>
  <div class="cajon-cab" style="margin-top:6px">${ic("tabla")}<b>Hoja</b><span style="color:var(--ink-2);font-size:12.5px">Sin precio · ${PEND.precio} de 22 · las filas completadas siguen aquí hasta actualizar · Enter guarda y baja</span><div class="der"><span class="btn sm">${ic("columnas")}Columnas</span><span class="btn sm">${ic("abajo")}Bajar</span></div></div>
  <div class="aviso-red" role="alert">${ic("error")}<div><b>No hay conexión con el servidor.</b> <span>Tus 2 cambios siguen aquí. Al reconectar se comprueba cada uno antes de reenviarlo; nada se envía dos veces.</span></div><div class="der"><span class="btn sm">${ic("reintentar")}Comprobar ahora</span></div></div>
  <div style="position:absolute;top:96px;left:0;right:0;bottom:0">${grid({ filas, cols: ["check", "nombre", "ubic", "docs", "tipo", "municipio", "m2", "ha", "afect", "precio", "pm2", "etapa", "visita"], orden: "pm2", celdas })}
</div></div>
  <div class="panel vidrio" style="left:12px;top:112px;bottom:auto;height:186px;width:384px;padding:18px 18px"><span class="etq">Otro estado · sin resultados</span><p style="margin:10px 0 4px;font-weight:600">Ningún expediente «Sin PDF» coincide con «Silao»</p><p style="margin:0 0 12px;color:var(--ink-2);font-size:12.5px">«Silao Puerto Interior, ampliación sur» ya tiene PDF; aparece en «Todos».</p><span class="btn">Ver en Todos</span></div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "5 · Hoja sobre el mapa: error recuperable", subtitulo: "C · Atlas de expedientes — exploración",
    marcas: [[1, 1030, 20], [2, 236, 70], [3, 14, 474], [4, 380, 120]],
    notas: [
      "<b>Error recuperable, dicho en la barra</b> y en la hoja: qué pasó, qué se conserva y qué hacer. Sin ventanas modales.",
      `<b>El pendiente activo filtra también la Hoja</b>: aquí, los ${PEND.precio} sin precio para capturarlos en serie con el teclado. Las filas no saltan al completarse.`,
      "<b>Se respeta la regla vigente</b>: una respuesta perdida se comprueba contra el servidor antes de reenviar. Las celdas lo dicen con icono y texto.",
      "<b>Sin resultados</b> explica por qué y ofrece la salida; no deja un panel vacío.",
    ],
  });
}

export function generarC() {
  return {
    "C1-atlas.html": ["C · Atlas de expedientes — Atlas", c1()],
    "C2-expediente-mapa.html": ["C · Atlas de expedientes — Selección", c2()],
    "C3-expediente-pagina.html": ["C · Atlas de expedientes — Expediente", c3()],
    "C4-estrecho.html": ["C · Atlas de expedientes — Ancho reducido", c4()],
    "C5-hoja-error.html": ["C · Atlas de expedientes — Hoja y error", c5()],
    css: CSS + `.marca-celda{float:left}.celda-incierta .marca-celda{color:var(--warn)}`,
  };
}

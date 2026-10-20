// Direction B — «Mesa dividida» (reorganisation).
// Bases become a sidebar; the list and the map are on screen at the same
// time and answer each other (hover, selection, filters). The record opens
// inside the list pane, so the map never leaves. The spreadsheet survives as
// «Hoja», a full-width mode for bulk editing.

import { porId, TODOS } from "./datos.mjs";
import { CSS_TEL, docs, esc, ic, leyendaPrecio, m2, mapa, precio, SD, sdTexto, telefono, ubic } from "./comun.mjs";
import {
  archivosFicha, conNotas, CSS_FICHA, CSS_GRID, CSS_NOTAS, enMapa, filtrados, grid, logo, ordenados, personalizadas,
  SEL, sinUbic, TOTAL_BASE, ubicacionFicha,
} from "./piezas.mjs";

const W = 1440, H = 900, SIDE = 232, LISTA = 520, TOP = 90;

const CSS = `${CSS_GRID}${CSS_FICHA}${CSS_NOTAS}
.side{position:absolute;left:0;top:0;bottom:0;width:${SIDE}px;background:#f0eee9;border-right:1px solid var(--rule-2);padding:12px 10px;display:flex;flex-direction:column;gap:2px}
.side .logo{padding:2px 8px 12px}
.side h4{margin:14px 8px 4px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);font-weight:600;display:flex;justify-content:space-between}
.side a{display:flex;align-items:center;gap:8px;height:30px;padding:0 8px;border-radius:6px;color:var(--ink);text-decoration:none;font-size:13px}
.side a span.c{margin-left:auto;color:var(--ink-2);font-size:12px;font-variant-numeric:tabular-nums}
.side a.on{background:var(--ink);color:#fff}
.side a.on span.c{color:#d9d6cf}
.side a.sec{color:var(--ink-2)}
.side .pie{margin-top:auto;border-top:1px solid var(--rule-2);padding-top:10px;display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink-2);padding-left:8px}
.side .pie em{font-style:normal;font-size:11px;padding:1px 6px;border-radius:9px;background:var(--sunken)}
.cont-b{position:absolute;left:${SIDE}px;right:0;top:0;bottom:0}
.tb{height:52px;display:flex;align-items:center;gap:10px;padding:0 14px;background:var(--raised);border-bottom:1px solid var(--rule)}
.tb h1{margin:0;font-size:16px;font-weight:650;letter-spacing:-.01em;white-space:nowrap}
.tb h1 small{font-weight:400;color:var(--ink-2);font-size:12px;margin-left:6px}
.tb .der{margin-left:auto;display:flex;align-items:center;gap:8px}
.chips{height:38px;display:flex;align-items:center;gap:8px;padding:0 14px;background:var(--paper);border-bottom:1px solid var(--rule-2)}
.chips .alc{font-size:12.5px;color:var(--ink-2)}
.chips .alc b{color:var(--ink)}
.cont{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;border-radius:9px;background:var(--ink);color:#fff;font-size:11px;font-weight:600;padding:0 5px}
.panes{position:absolute;top:${TOP}px;left:0;right:0;bottom:0;display:flex}
.lista{width:${LISTA}px;flex:none;background:var(--raised);border-right:1px solid var(--rule-2);position:relative;overflow:hidden}
.lista-cab{height:34px;display:flex;align-items:center;gap:8px;padding:0 12px 0 14px;border-bottom:1px solid var(--rule);font-size:12px;color:var(--ink-2);background:var(--paper)}
.lista-cab .der{margin-left:auto;display:flex;gap:6px;align-items:center}
.lista ul{list-style:none;margin:0;padding:0}
.lista li{display:grid;grid-template-columns:22px 1fr auto;gap:2px 10px;padding:8px 14px 8px 12px;border-bottom:1px solid var(--rule);position:relative}
.lista li .cb{margin-top:2px;opacity:0}
.lista li.marcada .cb,.lista li.hover .cb,.lista li.sel .cb{opacity:1}
.lista li .nm{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lista li .pm{font-weight:600;text-align:right;font-variant-numeric:tabular-nums}
.lista li .pm small{font-weight:400;color:var(--ink-2);font-size:11px}
.lista li .ln2{grid-column:2;color:var(--ink-2);font-size:12px;display:flex;gap:10px;white-space:nowrap;overflow:hidden}
.lista li .ln2r{grid-column:3;display:flex;gap:10px;justify-content:flex-end}
.lista li.sel{background:var(--sel-bg);box-shadow:inset 3px 0 0 var(--ink)}
.lista li.hover{background:var(--hover-bg)}
.lista li.marcada{background:#eceae5}
.lote{position:absolute;left:0;right:0;top:0;height:34px;display:flex;align-items:center;gap:8px;padding:0 12px 0 14px;background:var(--ink);color:#fff;font-size:12.5px;z-index:3}
.lote .btn{height:24px;font-size:12px;background:transparent;border-color:#6b6764;color:#fff}
.lote .der{margin-left:auto;display:flex;gap:6px}
.mapa-p{flex:1;position:relative;overflow:hidden}
.tarjeta{position:absolute;width:350px;z-index:5;background:var(--overlay);border:1px solid var(--rule-2);border-radius:12px;box-shadow:0 2px 4px rgba(0,0,0,.06),0 14px 34px rgba(0,0,0,.16);overflow:hidden}
.tarjeta .t-cab{padding:14px 16px 10px}
.tarjeta h2{margin:0;font-size:15.5px;line-height:1.3;font-weight:650}
.tarjeta .sub{margin:3px 0 0;color:var(--ink-2);font-size:12px}
.tarjeta .t-datos{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px;padding:10px 16px;border-top:1px solid var(--rule)}
.tarjeta .t-datos dt{font-size:11px;color:var(--ink-2)}
.tarjeta .t-datos dd{margin:0;font-weight:600;font-variant-numeric:tabular-nums}
.tarjeta .t-pie{display:flex;gap:8px;padding:10px 16px 14px;border-top:1px solid var(--rule)}
.tarjeta .t-arch{padding:8px 16px;border-top:1px solid var(--rule);display:flex;flex-direction:column;gap:6px;font-size:12.5px}
.tarjeta .t-arch div{display:flex;gap:8px;align-items:center}
.tarjeta .t-arch div span{margin-left:auto}
.etq-sel{position:absolute;display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:6px;background:var(--ink);color:#fff;font-size:12px;font-weight:500;white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,.2)}
.etq-sel .ic{width:13px;height:13px}
.etq-hover{position:absolute;padding:2px 7px;border-radius:5px;background:var(--overlay);border:1px solid var(--rule-2);font-size:12px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.12)}
.det{position:absolute;inset:0;background:var(--raised);overflow:hidden}
.det-cab{height:44px;display:flex;align-items:center;gap:8px;padding:0 10px 0 8px;border-bottom:1px solid var(--rule);background:var(--paper)}
.det-cab .der{margin-left:auto;display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-2)}
.det h2{margin:14px 18px 2px;font-size:18px;line-height:1.3;font-weight:650;letter-spacing:-.01em}
.det .sub{margin:0 18px 10px;color:var(--ink-2);font-size:12.5px}
.form{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px 14px}
.form label{display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--ink-2)}
.form label.ancho2{grid-column:span 2}
.form label.ancho3{grid-column:span 3}
.form .in{height:32px;display:flex;align-items:center;padding:0 9px;border:1px solid var(--borde-campo);border-radius:6px;background:#fff;font-size:13px;color:var(--ink);font-variant-numeric:tabular-nums;gap:6px}
.form .in small{margin-left:auto;font-size:11px;color:var(--ink-3)}
.form .in.vacio{color:var(--ink-3);font-style:italic}
.form .in.foco{border:2px solid var(--ink);padding:0 8px}
.form .in.ok{border-color:#9cc59e}
.form .est{font-size:11px;display:flex;align-items:center;gap:4px}
.form .est.ok{color:var(--ok)}
.form .est .ic{width:12px;height:12px}
.form .in.area{height:52px;align-items:flex-start;padding-top:7px}
.hoja-b .side{width:56px;padding:12px 8px;align-items:center}
.hoja-b .cont-b{left:56px}
.seg span{white-space:nowrap}
.form .tag{display:inline-block;font-size:10px;padding:0 5px;border-radius:7px;background:var(--sunken);color:var(--ink-2);margin-left:4px;vertical-align:1px}
.tels .tel-pantalla{background:var(--map)}
.hoja-sheet{position:absolute;left:0;right:0;bottom:0;background:var(--raised);border-radius:16px 16px 0 0;box-shadow:0 -6px 20px rgba(0,0,0,.14)}
.agarre{width:38px;height:5px;border-radius:3px;background:var(--rule-2);margin:8px auto 6px}
.pop-b{position:absolute;z-index:20;background:var(--overlay);border:1px solid var(--rule-2);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.16)}
${CSS_TEL}
`;

function sidebar({ rol = "admin", sel = "bajio", compacta = false }) {
  if (compacta) {
    return `<nav class="side" aria-label="Bases">${logo(false)}<span class="btn icono quiet" style="margin-top:14px" title="Mostrar barra lateral">${ic("barra")}</span><span class="btn icono quiet" title="Bases">${ic("capas")}</span></nav>`;
  }
  const admin = rol === "admin";
  return `<nav class="side" aria-label="Bases">${logo()}
  ${admin ? `<h4>Tabla maestra</h4><a>${ic("tabla")}Todas las bases<span class="c">54</span></a><a>${ic("ninguna")}Sin asignar<span class="c">2</span></a>` : ""}
  <h4>${admin ? "Bases de trabajo" : "Mis bases"}${admin ? `<span>${ic("mas")}</span>` : ""}</h4>
  <a class="${sel === "bajio" ? "on" : ""}">${ic("capas")}Bajío Industrial 2026<span class="c">48</span></a>
  ${admin || rol === "omar" ? `<a>${ic("capas")}Península y Sureste<span class="c">4</span></a>` : ""}
  <h4>Consulta</h4><a class="sec">${ic("ojo")}Catálogo público</a>
  ${admin ? `<h4>Herramientas</h4><a class="sec">${ic("doc")}Bases importadas</a><a class="sec">${ic("mapa")}Mapas guardados</a>` : ""}
  <div class="pie">${ic("usuario")}${admin ? "Ada Ficticia <em>Admin.</em>" : "Olga Ficticia <em>Operadora</em>"}</div></nav>`;
}

function barraB({ modo = "lista", estado = `<span class="estado-guardado ok">${ic("ok")}Todo guardado</span>`, rol = "admin" }) {
  return `<div class="tb"><h1>Bajío Industrial 2026<small>${rol === "admin" ? "2 con acceso" : "48 terrenos"}</small></h1>
  <span class="campo" style="width:230px;margin-left:8px">${ic("buscar")}Buscar en esta base</span>
  <span class="btn">${ic("filtro")}Filtros <span class="cont">2</span></span>
  <div class="der">${estado}<span class="seg"><span class="${modo === "lista" ? "on" : ""}">${ic("barra")}Lista y mapa</span><span class="${modo === "hoja" ? "on" : ""}">${ic("tabla")}Hoja</span></span>
  ${rol === "admin" ? `<span class="btn icono" title="Accesos y columnas de la base">${ic("mas3")}</span>` : ""}<span class="btn prim">${ic("mas")}Agregar</span></div></div>`;
}

function chipsB(extra = "", soloEstado = null) {
  const alc = soloEstado ? `<b>${soloEstado}</b> de ${TOTAL_BASE} terrenos` : `<b>${filtrados.length}</b> de ${TOTAL_BASE} · ${enMapa.length} en el mapa · ${sinUbic} sin ubicación`;
  return `<div class="chips"><span class="alc">${alc}</span>
  <span class="chip">Estado: <b>Guanajuato, Querétaro</b>${ic("cerrar")}</span>${soloEstado ? "" : `<span class="chip">Tipo: <b>Industrial, Comercial</b>${ic("cerrar")}</span>`}${extra}
  <span style="font-size:12px;text-decoration:underline;text-underline-offset:2px">Quitar filtros</span></div>`;
}

function lista({ sel = "apaseo", hover = null, marcados = new Set(), desde = 0, n = 16, lote = false, rol = "admin" }) {
  const filas = ordenados.slice(desde, desde + n).map((t) => `<li class="${t.id === sel ? "sel" : ""} ${t.id === hover ? "hover" : ""} ${marcados.has(t.id) ? "marcada" : ""}">
    <span class="cb${marcados.has(t.id) ? " on" : ""}"></span><span class="nm" title="${esc(t.nombre)}">${esc(t.nombre)}</span><span class="pm">${t.pm2 == null ? SD : precio(t.pm2)}<small>/m²</small></span>
    <span class="ln2">${t.tipo ? esc(t.tipo) : SD} · ${esc(t.municipio)} · <span class="n">${m2(t.m2)} m²</span></span><span class="ln2r">${ubic(t)}${docs(t)}</span></li>`).join("");
  const loteBar = lote ? `<div class="lote"><b>${marcados.size} seleccionados</b><div class="der">${rol === "admin" ? `<span class="btn">${ic("transferir")}Transferir…</span>` : ""}<span class="btn">${ic("borrar")}Borrar…</span><span class="btn">${ic("cerrar")}</span></div></div>` : "";
  return `<section class="lista" aria-label="Lista de terrenos">${loteBar}<div class="lista-cab"><span class="cb${marcados.size ? " mixto" : ""}"></span><span>${filtrados.length} terrenos</span><div class="der">${ic("orden")}<b style="color:var(--ink)">Asking $/m²</b>, mayor primero ${ic("abajo")}</div></div><ul>${filas}</ul></section>`;
}

/* ------------------------------------------------------------- screens */

function b1() {
  const mw = W - SIDE - LISTA, mh = H - TOP;
  const marcados = new Set(["corredor57", "iturbide"]);
  const { svg, px } = mapa({ w: mw, h: mh, centro: [20.86, -100.98], spanLon: 2.1, filas: filtrados, sel: "apaseo", hover: "corredor57", atenuar: null, id: "b1" });
  const [hx, hy] = px(porId.corredor57.x, porId.corredor57.y);
  const ui = `${sidebar({})}<div class="cont-b">${barraB({})}${chipsB()}
  <div class="panes">${lista({ sel: "apaseo", hover: "corredor57", marcados, desde: 4, lote: true })}
  <div class="mapa-p">${svg}<span class="etq-hover" style="right:${mw - hx + 14}px;top:${hy - 30}px">Corredor 57 – Santa Rosa Jáuregui · $750/m²</span>
  <div class="base-mapa" style="left:12px;top:12px"><span class="on">Claro</span><span>Satélite</span><span>Calles</span></div>
  <div class="mapa-ctrl" style="right:12px;top:12px"><span>+</span><span>−</span><span style="font-size:13px">${ic("encuadrar")}</span></div>
  <div class="flota" style="left:12px;bottom:12px">${leyendaPrecio({ total: enMapa.length, fuera: sinUbic })}</div>
  <span class="chip sug" style="position:absolute;right:12px;bottom:12px">${ic("encuadrar")}Limitar la lista al área visible</span>
  <span class="ilustrativo" style="right:12px;bottom:44px">Mapa base ilustrativo</span></div></div></div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "1 · Lista y mapa a la vez", subtitulo: "B · Mesa dividida — reorganización",
    marcas: [[1, 180, 64], [2, 1086, 4], [3, SIDE + 500, 132], [4, SIDE + LISTA + hx - 30, TOP + hy - 22], [5, W - 230, H - 62]],
    notas: [
      "<b>Las bases son lugares, no un filtro.</b> Barra lateral con las bases de trabajo y sus conteos. La administradora ve además «Todas» y «Sin asignar»; la operadora sólo «Mis bases». La barra se puede ocultar.",
      "<b>Lista y mapa en pantalla al mismo tiempo.</b> Se elimina el cambio Tabla / Mapa para consultar; «Hoja» queda para la edición masiva.",
      "<b>Renglón de dos líneas pensado para comparar:</b> nombre, Asking $/m², tipo, municipio, superficie, ubicación y PDF. La selección múltiple activa una barra de acciones por rol.",
      "<b>Pasar el puntero por un renglón lo señala en el mapa</b> (y viceversa) con anillo punteado y etiqueta: la relación entre fila y lugar es inmediata.",
      "<b>Exploración futura:</b> limitar la lista al área visible del mapa. Es un filtro nuevo sobre datos existentes; no cambia reglas de negocio.",
    ],
  });
}

function tarjeta(t, x, y) {
  return `<div class="tarjeta" style="left:${x}px;top:${y}px" role="dialog" aria-label="Resumen del terreno">
  <div class="t-cab"><div style="display:flex;justify-content:space-between;gap:8px"><h2>${esc(t.nombre)}</h2><span class="btn icono quiet">${ic("cerrar")}</span></div><p class="sub">${esc(t.tipo)} · ${esc(t.municipio)}, ${esc(t.estado)}</p></div>
  <dl class="t-datos"><div><dt>Asking price · MXN</dt><dd>${precio(t.precio)}</dd></div><div><dt>Asking $/m² · MXN</dt><dd>${precio(t.pm2)}</dd></div>
  <div><dt>Superficie</dt><dd>${m2(t.m2)} m² · ${t.ha} ha</dd></div><div><dt>Afectaciones</dt><dd>${t.afect}%</dd></div></dl>
  <div class="t-arch"><div>${ubic(t, "largo")}</div><div>${ic("doc")}${esc(t.pdf[0])}<span class="btn sm">Abrir</span></div></div>
  <div class="t-pie"><span class="btn prim" style="flex:1;justify-content:center">${ic("editar")}Abrir ficha</span><span class="btn">${ic("encuadrar")}Acercar</span></div></div>`;
}

function b2() {
  const mw = W - SIDE - LISTA, mh = H - TOP;
  const { svg, px } = mapa({ w: mw, h: mh, centro: [20.66, -100.55], spanLon: 0.95, filas: filtrados, sel: "apaseo", escala: "local", id: "b2" });
  const [sx, sy] = px(SEL.x, SEL.y);
  const ui = `${sidebar({ rol: "operador" })}<div class="cont-b">${barraB({ rol: "operador" })}${chipsB()}
  <div class="panes">${lista({ sel: "apaseo", desde: 9, rol: "operador" })}
  <div class="mapa-p">${svg}
  <div class="base-mapa" style="left:12px;top:12px"><span class="on">Claro</span><span>Satélite</span><span>Calles</span></div>
  <div class="mapa-ctrl" style="left:12px;top:56px"><span>+</span><span>−</span><span style="font-size:13px">${ic("encuadrar")}</span></div>
  ${tarjeta(SEL, mw - 362, 12)}
  <div class="flota" style="left:12px;bottom:12px">${leyendaPrecio({ total: enMapa.length, fuera: sinUbic, compacta: true })}</div>
  <span class="ilustrativo" style="right:12px;bottom:12px">Mapa base ilustrativo</span></div></div></div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "2 · Mapa con un terreno seleccionado (operadora)", subtitulo: "B · Mesa dividida — reorganización",
    marcas: [[1, SIDE + 4, TOP + 34 + 3 * 52 + 6], [2, SIDE + LISTA + sx - 34, TOP + sy - 30], [3, W - 374, TOP + 6], [4, W - 120, TOP + 420]],
    notas: [
      "<b>La selección vive en los dos paneles</b>: el renglón se resalta y la lista se desplaza para mostrarlo; el mapa se acerca al contorno.",
      "<b>Contorno real a escala</b> con trazo negro y halo; los demás terrenos siguen visibles para comparar el entorno.",
      "<b>Tarjeta de resumen</b> flotante sobre el mapa: los datos para decidir, la fuente de la ubicación y el PDF a un clic. No tapa el terreno seleccionado.",
      "<b>«Abrir ficha»</b> lleva el detalle editable al panel de la lista (pantalla 3); el mapa permanece. «Acercar» encuadra el contorno.",
    ],
  });
}

function b3() {
  const t = SEL, mw = W - SIDE - LISTA, mh = H - TOP;
  const { svg } = mapa({ w: mw, h: mh, centro: [20.565, -100.69], spanLon: 0.16, filas: filtrados, sel: "apaseo", escala: "local", id: "b3" });
  const det = `<section class="lista" aria-label="Ficha del terreno"><div class="det">
  <div class="det-cab"><span class="btn quiet">${ic("izq")}22 terrenos</span><span class="btn icono" title="Anterior (K)">${ic("arriba")}</span><span class="btn icono" title="Siguiente (J)">${ic("abajo")}</span><span style="font-size:12px;color:var(--ink-2)">10 de 22</span>
  <div class="der"><span class="estado-guardado ok">${ic("ok")}Guardado hace 3 s</span><span class="btn icono">${ic("historial")}</span><span class="btn icono">${ic("mas3")}</span></div></div>
  <h2>${esc(t.nombre)}</h2><p class="sub">Bajío Industrial 2026 · ${esc(t.municipio)}, ${esc(t.estado)}</p>
  <div class="sec"><h3>Datos del terreno</h3><div class="form">
    <label class="ancho3">Nombre de terreno<span class="in">${esc(t.nombre)}</span></label>
    <label>Tipo<span class="in">Industrial ${ic("abajo")}</span></label><label>Estado<span class="in">Guanajuato</span></label><label>Municipio<span class="in">Apaseo el Grande</span></label>
    <label>Superficie<span class="in">184,500<small>m²</small></span></label><label>HA<span class="in">18.45</span></label><label>Afectaciones<span class="in">12<small>%</small></span></label>
    <label>Asking price<span class="in foco">$92,500,000<small>MXN</small></span><span class="est">Enter guarda · Esc deshace</span></label><label>Asking $/m²<span class="in">$500<small>MXN</small></span><span class="est">No se recalcula: ya tiene valor</span></label><label><span>Etapa<span class="tag">de la base</span></span><span class="in ok">Oferta ${ic("abajo")}</span><span class="est ok">${ic("ok")}Guardado</span></label>
    <label>Fecha de visita<span class="in">2026-09-14</span></label><label class="ancho2">Broker<span class="in">Inmobiliaria Bajío Centro</span></label>
    <label class="ancho3">Comentarios<span class="in area">Frente a carretera federal 45. Revisar derecho de vía CFE.</span></label>
  </div></div>
  <div class="sec"><h3>Archivos <em>1 PDF · 1 KMZ</em></h3>${archivosFicha(t)}</div>
  </div></section>`;
  const ui = `${sidebar({ rol: "operador" })}<div class="cont-b">${barraB({ rol: "operador", estado: "" })}${chipsB()}
  <div class="panes">${det}<div class="mapa-p">${svg}
  <div class="flota" style="left:12px;top:12px;padding:10px 12px;width:300px;font-size:12px"><b style="display:flex;gap:6px;align-items:center">${ic("contorno")}Contorno activo · poligono-apaseo.kmz</b><span style="color:var(--ink-2)">X 20.555 · Y −100.7 también capturadas. El mapa usa el contorno.</span></div>
  <div class="mapa-ctrl" style="right:12px;top:12px"><span>+</span><span>−</span><span style="font-size:13px">${ic("encuadrar")}</span></div>
  <div class="base-mapa" style="right:12px;bottom:12px"><span class="on">Claro</span><span>Satélite</span><span>Calles</span></div>
  <span class="ilustrativo" style="left:12px;bottom:12px">Mapa base ilustrativo</span></div></div></div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "3 · Ficha editable en el panel de la lista", subtitulo: "B · Mesa dividida — reorganización",
    marcas: [[1, SIDE + 6, TOP + 6], [2, SIDE + 262, TOP + 6], [3, SIDE + 180, TOP + 300], [4, SIDE + LISTA + 6, TOP + 6], [5, SIDE + 6, TOP + 600]],
    notas: [
      "<b>El detalle sustituye a la lista, no al mapa.</b> «‹ 22 terrenos» vuelve a la misma posición, filtros y selección.",
      "<b>Recorrer el conjunto filtrado</b> sin volver a la lista: anterior/siguiente (J/K), «10 de 22». Útil para completar datos en serie.",
      "<b>Formulario siempre editable</b>, con guardado por campo y versión. Los campos propios de la base llevan la marca «de la base». Sin dato se ve como campo vacío, nunca como cero.",
      "<b>El mapa explica la fuente de la ubicación</b> y muestra el contorno a escala. El fondo elegido se conserva.",
      "<b>Archivos en el mismo flujo</b> que los datos; se arrastran sobre el panel.",
    ],
  });
}

function b4() {
  const { svg } = mapa({ w: 390, h: 520, centro: [20.6, -100.62], spanLon: 0.75, filas: filtrados, sel: "apaseo", escala: "local", id: "b4" });
  const filas = ordenados.slice(9, 13).map((t) => `<li class="${t.id === "apaseo" ? "sel" : ""}" style="grid-template-columns:1fr auto;padding:10px 16px"><span class="nm" style="font-size:14px;white-space:normal">${esc(t.nombre)}</span><span class="pm">${t.pm2 == null ? SD : precio(t.pm2)}<small>/m²</small></span><span class="ln2" style="grid-column:1">${t.tipo ?? "—"} · ${esc(t.municipio)}</span><span class="ln2r" style="grid-column:2">${ubic(t)}</span></li>`).join("");
  const p1 = `<div style="position:absolute;inset:0">${svg}</div><div class="tel-estado" style="position:relative;z-index:2"><span>9:41</span><span>●●● ▮</span></div>
  <div style="position:absolute;top:50px;left:12px;right:12px;display:flex;gap:8px;z-index:2"><span class="campo" style="flex:1;height:40px;box-shadow:0 2px 8px rgba(0,0,0,.12)">${ic("buscar")}Bajío Industrial 2026</span><span class="btn" style="height:40px;box-shadow:0 2px 8px rgba(0,0,0,.12)">${ic("filtro")}<span class="cont">2</span></span></div>
  <div class="hoja-sheet" style="top:430px"><div class="agarre"></div><div style="display:flex;justify-content:space-between;padding:0 16px 8px;font-size:13px"><b>22 terrenos</b><span style="color:var(--ink-2)">Asking $/m² ↓</span></div><ul class="lista" style="width:auto;border:0">${filas}</ul></div>`;
  const t = SEL;
  const { svg: mini } = mapa({ w: 390, h: 250, centro: [20.565, -100.69], spanLon: 0.08, filas: filtrados, sel: "apaseo", escala: "local", id: "b4m", etiquetas: false });
  const p2 = `<div style="position:absolute;top:0;left:0;right:0;height:250px">${mini}</div><div class="tel-estado" style="position:relative;z-index:2"><span>9:41</span><span>●●● ▮</span></div>
  <div class="hoja-sheet" style="top:200px;overflow:hidden"><div class="agarre"></div>
  <div style="display:flex;justify-content:space-between;align-items:center;padding:0 16px"><span class="btn quiet" style="padding:0">${ic("izq")}Lista</span><span style="font-size:12px;color:var(--ink-2)">10 de 22 ${ic("arriba")} ${ic("abajo")}</span></div>
  <h2 style="margin:6px 16px 2px;font-size:19px;line-height:1.25">${esc(t.nombre)}</h2><p style="margin:0 16px 10px;color:var(--ink-2)">${esc(t.tipo)} · ${esc(t.municipio)}</p>
  <div class="sec" style="padding:12px 16px"><div class="form" style="grid-template-columns:1fr 1fr"><label>Asking price<span class="in">$92,250,000<small>MXN</small></span></label><label>Asking $/m²<span class="in">$500<small>MXN</small></span></label><label>Superficie<span class="in">184,500<small>m²</small></span></label><label>Afectaciones<span class="in">12<small>%</small></span></label></div></div>
  <div class="sec" style="padding:12px 16px"><h3>Archivos</h3>${archivosFicha(t, { soloLectura: true })}</div></div>`;
  const ui = `<div class="tels">${telefono(p1, "Mapa arriba, lista en una hoja deslizable")}${telefono(p2, "Ficha en la hoja; el contorno sigue a la vista")}</div>`;
  return conNotas({
    w: 900, h: H, ui, titulo: "4 · Ancho reducido (390 px)", subtitulo: "B · Mesa dividida — reorganización",
    marcas: [[1, 12, 64], [2, 378, 460], [3, 448, 120], [4, 448, 470]],
    notas: [
      "<b>El mapa no se pierde</b>: en pantalla estrecha se apila. La búsqueda flota arriba con el nombre de la base como texto de ayuda.",
      "<b>Lista en una hoja de tres alturas</b> (mínima, media, completa). Con la hoja completa se trabaja como lista; con la mínima, como mapa.",
      "<b>El contorno queda visible</b> sobre la ficha: ayuda a confirmar en campo que se mira el terreno correcto.",
      "<b>Campos con el mismo formulario</b> que en escritorio; la edición masiva («Hoja») no se ofrece en este ancho. <i>Por validar:</i> si en campo se suben fotos JPG.",
    ],
  }).replace('class="lienzo"', 'class="lienzo" style="background:#e9e6df"');
}

function b5() {
  const cols = ["check", "nombre", "ubic", "docs", "tipo", "estado", "municipio", "m2", "ha", "afect", "precio", "pm2", "etapa", "visita", "broker"];
  const celdas = {
    "celaya|ubic": { cls: "", html: `<span class="ubic ubic-elegir">${ic("elegir")}<span>Elegir</span></span>` },
    "silao|docs": { cls: "", html: `<span class="docs">${ic("pendiente")}<span>40%</span></span>` },
  };
  const filas = TODOS.filter((t) => ["Guanajuato", "Querétaro"].includes(t.estado))
    .sort((a, b) => (a.pm2 == null) - (b.pm2 == null) || (b.pm2 ?? 0) - (a.pm2 ?? 0));
  const yc = 90 + 32 + 34 * filas.findIndex((x) => x.id === "celaya");
  const { svg: c1 } = mapa({ w: 150, h: 110, centro: [20.53, -100.81], spanLon: 0.03, filas: [], id: "c1", etiquetas: false });
  const ui = `<div class="hoja-b">${sidebar({ compacta: true })}<div class="cont-b">${barraB({ modo: "hoja", estado: `<span class="estado-guardado trabajando">${ic("pendiente")}1 subiendo · 1 contorno por elegir</span>` })}${chipsB("", filas.length)}
  <div class="panes"><div style="flex:1;position:relative">${grid({ filas, cols, orden: "pm2", celdas, sel: "celaya" })}
  <div class="pop-b" style="left:300px;top:${yc - 90 - 352}px;width:420px;padding:14px 16px" role="dialog" aria-label="Elegir contorno">
    <p style="margin:0 0 2px;font-weight:600">varios-lotes-celaya.kml trae 2 contornos</p><p style="margin:0 0 12px;color:var(--ink-2);font-size:12.5px">Marca el del terreno (o los dos, si son partes del mismo). Hasta elegir, el mapa usa sus X/Y.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
      <label style="border:2px solid var(--ink);border-radius:8px;padding:8px;display:grid;gap:6px;font-size:12px"><span style="display:flex;gap:6px;align-items:center"><span class="cb on"></span><b>Lote 1</b></span><svg viewBox="0 0 150 80" style="background:#ecebe6;border-radius:4px"><path d="M30 20 75 10 120 30 112 64 60 72 24 52z" fill="#2f6fc4" fill-opacity=".3" stroke="#1d1b19" stroke-width="2"/></svg><span style="color:var(--ink-2)">55.81 ha en el KML</span></label>
      <label style="border:1px solid var(--rule-2);border-radius:8px;padding:8px;display:grid;gap:6px;font-size:12px"><span style="display:flex;gap:6px;align-items:center"><span class="cb"></span><b>Lote 2</b></span><svg viewBox="0 0 150 80" style="background:#ecebe6;border-radius:4px"><path d="M40 26 96 18 118 46 88 68 42 60z" fill="none" stroke="#5b5754" stroke-width="2" stroke-dasharray="4 3"/></svg><span style="color:var(--ink-2)">43.23 ha en el KML</span></label></div>
    <p style="margin:0 0 10px;font-size:11.5px;color:var(--warn);display:flex;gap:6px;align-items:center">${ic("aviso")}La tabla registra 4.18 ha: el área del KML no reemplaza la superficie.</p>
    <div style="display:flex;justify-content:flex-end;gap:8px"><span class="btn">Después</span><span class="btn prim">Activar Lote 1</span></div></div>
  </div></div></div></div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "5 · Hoja completa: archivo en proceso y contorno por elegir", subtitulo: "B · Mesa dividida — reorganización",
    marcas: [[1, 1086, 4], [2, 18, 140], [3, 290, yc - 352], [5, 380, yc - 10], [4, 488, (() => 90 + 32 + 34 * filas.findIndex((x) => x.id === "silao"))() + 6]],
    notas: [
      "<b>«Hoja» es la tabla de hoy, mejorada</b>, para editar en masa: todas las columnas, teclado tipo hoja de cálculo y selección múltiple.",
      "<b>La barra lateral se pliega</b> para ganar ancho; los filtros y la base activa no cambian.",
      "<b>Contorno por elegir en su sitio:</b> vista previa de cada candidato y activación explícita. Se sigue la regla vigente: con varios candidatos no se activa nada solo.",
      "<b>Archivo en proceso en la celda</b> (PDF de Silao al 40%). Repintar o filtrar la tabla no interrumpe la subida, como hoy.",
      "<b>Datos que no se sustituyen:</b> el área calculada del KML se muestra como referencia y se avisa que no cambia la superficie capturada.",
    ],
  });
}

export function generarB() {
  return {
    "B1-lista-y-mapa.html": ["B · Mesa dividida — Lista y mapa", b1()],
    "B2-mapa-seleccion.html": ["B · Mesa dividida — Mapa con selección", b2()],
    "B3-ficha-edicion.html": ["B · Mesa dividida — Ficha en edición", b3()],
    "B4-estrecho.html": ["B · Mesa dividida — Ancho reducido", b4()],
    "B5-hoja-archivos.html": ["B · Mesa dividida — Hoja y archivos", b5()],
    css: CSS,
  };
}

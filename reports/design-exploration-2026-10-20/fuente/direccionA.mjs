// Direction A — «Hoja con ficha» (evolution).
// The spreadsheet stays the centre. One record panel (the Ficha) is shared by
// Tabla and Mapa; one filter model drives both; files and location move next
// to the name; save state lives in the toolbar, next to the work.

import { porId } from "./datos.mjs";
import { CSS_TEL, esc, ic, leyendaPrecio, mapa, telefono, ubic, docs, m2, precio, SD, sdTexto } from "./comun.mjs";
import {
  archivosFicha, conNotas, CSS_FICHA, CSS_GRID, CSS_NOTAS, enMapa, filtrados, grid, logo, ordenados, personalizadas,
  seccionesFicha, SEL, sinUbic, TOTAL_BASE, ubicacionFicha,
} from "./piezas.mjs";

const W = 1440, H = 900, FICHA = 384;

const CSS = `${CSS_GRID}${CSS_FICHA}${CSS_NOTAS}
.cab{height:48px;display:flex;align-items:center;gap:14px;padding:0 14px 0 16px;border-bottom:1px solid var(--rule);background:var(--raised)}
.logo{display:inline-flex;align-items:center;gap:8px;font-size:14px}
.ambito{display:inline-flex;align-items:center;gap:8px;height:32px;padding:0 10px;border-radius:7px;border:1px solid transparent}
.ambito:hover,.ambito.abierto{background:var(--sunken);border-color:var(--rule-2)}
.ambito b{font-size:15px;font-weight:600;letter-spacing:-.01em}
.ambito small{color:var(--ink-2);font-size:12px}
.sep{width:1px;height:22px;background:var(--rule)}
.nav{display:flex;gap:2px}
.nav span{padding:6px 10px;border-radius:6px;color:var(--ink-2)}
.nav span.on{color:var(--ink);background:var(--sunken);font-weight:500}
.cab .der{margin-left:auto;display:flex;align-items:center;gap:14px}
.usuario{display:inline-flex;align-items:center;gap:6px;color:var(--ink-2)}
.usuario em{font-style:normal;font-size:11px;padding:1px 6px;border-radius:9px;background:var(--sunken);color:var(--ink-2)}
.barra-h{height:48px;display:flex;align-items:center;gap:10px;padding:0 14px 0 16px;background:var(--raised);border-bottom:1px solid var(--rule)}
.barra-h .der{margin-left:auto;display:flex;gap:8px;align-items:center}
.buscar{width:340px}
.cont{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;border-radius:9px;background:var(--ink);color:#fff;font-size:11px;font-weight:600;padding:0 5px}
.chips{height:38px;display:flex;align-items:center;gap:8px;padding:0 14px 0 16px;background:var(--paper);border-bottom:1px solid var(--rule-2)}
.chips .alcance{font-size:12.5px;color:var(--ink-2);margin-right:4px}
.chips .alcance b{color:var(--ink)}
.chips .limpiar{font-size:12px;color:var(--ink);text-decoration:underline;text-underline-offset:2px;margin-left:2px}
.chips .der{margin-left:auto;font-size:12px;color:var(--ink-2);display:flex;gap:6px;align-items:center}
.principal{position:absolute;top:134px;left:0;right:0;bottom:0;display:flex}
.zona{flex:1;min-width:0;position:relative;overflow:hidden}
.ficha{width:${FICHA}px;flex:none;border-left:1px solid var(--rule-2);background:var(--raised);overflow:hidden;position:relative}
.ficha-cab{padding:14px 18px 12px}
.ficha-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.ficha h2{margin:0;font-size:17px;line-height:1.3;font-weight:650;letter-spacing:-.01em}
.ficha .sub{margin:4px 0 0;color:var(--ink-2);font-size:12.5px}
.ficha-acc{display:flex;gap:6px;margin-top:12px}
.ficha-pegada{position:absolute;left:0;right:0;top:0;height:44px;display:flex;align-items:center;gap:6px;padding:0 10px 0 18px;background:rgba(253,253,252,.97);border-bottom:1px solid var(--rule-2);box-shadow:0 2px 8px rgba(0,0,0,.05)}
.ficha-pegada b{flex:1;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ficha-pie{position:absolute;left:0;right:0;bottom:0;padding:9px 18px;border-top:1px solid var(--rule);background:var(--raised);font-size:11.5px;color:var(--ink-2);display:flex;justify-content:space-between}
.coment{margin:0;font-size:12.5px;color:var(--ink)}
.desplaza{position:absolute;right:6px;width:4px;border-radius:2px;background:var(--rule-2)}
.menu{position:absolute;z-index:40;width:250px;background:var(--overlay);border:1px solid var(--rule-2);border-radius:9px;box-shadow:0 10px 30px rgba(0,0,0,.16);padding:5px;font-size:13px}
.menu div{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:5px}
.menu div.on{background:var(--sunken)}
.menu hr{border:0;border-top:1px solid var(--rule);margin:4px 0}
.menu .peligro{color:var(--err)}
.menu .no{color:var(--ink-3)}
.menu small{margin-left:auto;font-size:11px;color:var(--ink-3)}
.pop{position:absolute;z-index:40;background:var(--overlay);border:1px solid var(--rule-2);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.16)}
.flecha-pop{position:absolute;width:12px;height:12px;background:var(--overlay);border-left:1px solid var(--rule-2);border-top:1px solid var(--rule-2);transform:rotate(45deg)}
.etq-sel{position:absolute;display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:6px;background:var(--ink);color:#fff;font-size:12px;font-weight:500;white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,.2)}
.etq-sel .ic{width:13px;height:13px}
.marca-celda{float:left;color:inherit}
.celda-conflicto .marca-celda{color:var(--err)}
.celda-incierta .marca-celda{color:var(--warn)}
.otro-estado{width:384px;flex:none;border-left:1.5px dashed var(--ink-3);background:var(--paper);padding:34px 24px;position:relative}
.otro-estado .tit,.otro-estado .tit2{display:block;font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-2);margin-bottom:14px}
.vacio-ilus{width:44px;height:44px;border-radius:22px;background:var(--sunken);display:flex;align-items:center;justify-content:center;margin-bottom:12px}
.vacio-ilus .ic{width:20px;height:20px;color:var(--ink-2)}
.esq{display:grid;gap:9px}
.esq i{display:block;height:12px;border-radius:4px;background:linear-gradient(90deg,var(--sunken),#e6e3dd,var(--sunken))}
.mini-estado{position:absolute;border:1.5px dashed var(--ink-3);border-radius:12px;background:var(--paper)}
.mini-estado .tit{position:absolute;top:-10px;left:12px;background:var(--paper);padding:0 6px;font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-2)}
${CSS_TEL}
`;

function cabecera({ rol = "admin", estado = '<span class="estado-guardado ok">' + ic("ok") + "Todo guardado</span>", ambitoAbierto = false }) {
  const nav = rol === "admin" ? '<span class="on">Terrenos</span><span>Herramientas ' + ic("abajo") + "</span><span>Catálogo público</span>" : '<span class="on">Terrenos</span><span>Catálogo público</span>';
  return `<header class="cab">${logo()}<span class="sep"></span>
  <span class="ambito${ambitoAbierto ? " abierto" : ""}" title="Cambiar de base"><b>Bajío Industrial 2026</b><small>${TOTAL_BASE} terrenos</small>${ic("abajo")}</span>
  <nav class="nav" aria-label="Secciones">${nav}</nav>
  <div class="der">${estado}<span class="sep"></span><span class="usuario">${ic("usuario")}${rol === "admin" ? "Ada Ficticia <em>Administradora</em>" : "Olga Ficticia <em>Operadora</em>"}${ic("abajo")}</span></div></header>`;
}

function barra({ modo = "tabla", rol = "admin" }) {
  return `<div class="barra-h" role="toolbar" aria-label="Terrenos">
  <span class="campo buscar">${ic("buscar")}<span>Buscar nombre, municipio o comentario</span><span class="kbd" style="margin-left:auto">/</span></span>
  <span class="btn">${ic("filtro")}Filtros <span class="cont">2</span></span>
  <span class="seg" role="tablist" aria-label="Vista"><span class="${modo === "tabla" ? "on" : ""}">${ic("tabla")}Tabla</span><span class="${modo === "mapa" ? "on" : ""}">${ic("mapa")}Mapa</span></span>
  <div class="der">${modo === "tabla" ? `<span class="btn">${ic("columnas")}Columnas</span>` : `<span class="btn">${ic("encuadrar")}Encuadrar filtrados</span>`}
  ${rol === "admin" ? `<span class="btn icono" title="Más acciones de la base">${ic("mas3")}</span>` : ""}
  <span class="btn prim">${ic("mas")}Agregar terreno</span></div></div>`;
}

function chips({ modo = "tabla" }) {
  const alcance = modo === "tabla"
    ? `<span class="alcance"><b>${filtrados.length}</b> de ${TOTAL_BASE} terrenos</span>`
    : `<span class="alcance"><b>${filtrados.length}</b> de ${TOTAL_BASE} · ${enMapa.length} en el mapa · ${sinUbic} sin ubicación</span>`;
  return `<div class="chips">${alcance}
  <span class="chip">Estado: <b>Guanajuato, Querétaro</b>${ic("cerrar")}</span>
  <span class="chip">Tipo: <b>Industrial, Comercial</b>${ic("cerrar")}</span>
  <a class="limpiar">Quitar filtros</a>
  <span class="der">${ic("orden")}Orden: <b style="color:var(--ink)">Asking $/m², mayor primero</b> · sin dato al final</span></div>`;
}

function ficha({ t = SEL, rol = "admin", editando = {}, subiendo = null, menu = false, top = 0, campoEditable = null }) {
  const { precioS, sup, ident } = seccionesFicha(t, { editando });
  const pegada = top ? `<div class="ficha-pegada"><b>${esc(t.nombre)}</b><span class="btn icono quiet sm">${ic("mapa")}</span><span class="btn icono quiet sm">${ic("cerrar")}</span></div>` : "";
  return `<aside class="ficha" aria-label="Ficha del terreno">
  <div style="position:absolute;left:0;right:0;bottom:0;overflow:hidden;top:${top}px">
  <div class="ficha-cab"><div class="ficha-top"><span class="etq">Ficha</span><span class="btn icono quiet" title="Cerrar ficha (Esc)">${ic("cerrar")}</span></div>
    <h2>${esc(t.nombre)}</h2><p class="sub">${esc(t.tipo ?? "Sin tipo")} · ${esc(t.municipio)}, ${esc(t.estado)}</p>
    <div class="ficha-acc"><span class="btn">${ic("mapa")}Ver en mapa</span><span class="btn">${ic("historial")}Historial</span><span class="btn icono" title="Más acciones">${ic("mas3")}</span></div></div>
  <div class="sec"><h3>Precio</h3>${precioS}</div>
  <div class="sec"><h3>Superficie</h3>${sup}</div>
  <div class="sec"><h3>Ubicación</h3>${ubicacionFicha(t)}</div>
  <div class="sec"><h3>Archivos <em>${t.pdf.length + (subiendo ? 1 : 0)} PDF · ${t.kmz ? 1 : 0} KMZ</em></h3>${archivosFicha(t, { subiendo })}</div>
  <div class="sec"><h3>Datos generales</h3>${ident}</div>
  <div class="sec"><h3>Columnas de esta base</h3>${personalizadas(t, editando)}</div>
  <div class="sec"><h3>Comentarios</h3><p class="coment">${t.notas ? esc(t.notas) : '<span class="sd-t">Sin comentarios</span>'}</p></div>
  </div>
  ${pegada}<div class="ficha-pie"><span>Editado por ${esc(t.editado ?? "Ada Ficticia")}</span><span>versión ${t.version ?? 1}</span></div>
  ${menu ? `<div class="menu" style="right:14px;top:126px;display:none"><div>${ic("historial")}Historial de cambios</div><div>${ic("bajar")}Descargar archivos</div><hr>${rol === "admin" ? `<div>${ic("transferir")}Transferir a otra base…</div>` : `<div class="no">${ic("transferir")}Transferir a otra base…<small>Sólo admin.</small></div>`}<div class="peligro">${ic("borrar")}Borrar terreno…</div></div>` : ""}
  </aside>`;
}

const COLS_A = ["check", "nombre", "ubic", "docs", "tipo", "municipio", "m2", "precio", "pm2", "etapa", "visita"];

/* ------------------------------------------------------------- screens */

const fila = (id) => ordenados.findIndex((x) => x.id === id);
const yFila = (id) => 134 + 32 + 34 * fila(id);   // top of a row in the grid

const menuContexto = (rol, x, y) => `<div class="menu" style="left:${x}px;top:${y}px" role="menu" aria-label="Acciones del terreno">
  <div class="on">${ic("barra")}Abrir ficha<small>Espacio</small></div><div>${ic("mapa")}Ver en mapa<small>M</small></div><div>${ic("historial")}Historial de cambios</div><div>${ic("subir")}Agregar PDF o JPG…</div><hr>
  ${rol === "admin" ? `<div>${ic("transferir")}Transferir a otra base…</div>` : `<div class="no">${ic("transferir")}Transferir a otra base…<small>Sólo administración</small></div>`}
  <div class="peligro">${ic("borrar")}Borrar terreno…</div></div>`;

function a1() {
  const ui = `${cabecera({})}${barra({})}${chips({})}
  <div class="principal"><div class="zona">${grid({ filas: ordenados, cols: COLS_A, sel: "apaseo", orden: "pm2", foco: "apaseo|nombre" })}</div>${ficha({})}</div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "1 · Tabla con la ficha abierta", subtitulo: "A · Hoja con ficha — evolución",
    marcas: [[1, 404, 14], [2, 344, 62], [3, 1072, 104], [4, 400, 141], [5, 1412, 196], [6, 1058, 14]],
    notas: [
      "<b>La base es el título.</b> El selector «Vista» pasa a la cabecera como nombre del documento. Las «Bases» heredadas y los mapas guardados se agrupan en <b>Herramientas</b> (sólo administración).",
      "<b>Un solo modelo de filtros</b> para Tabla y Mapa: búsqueda + botón Filtros. Lo activo aparece siempre como chips, con el alcance en palabras: 22 de 48.",
      "<b>Ordenar desde el encabezado</b> (clic; otro clic invierte). Se retiran «Ordenar por» y «Descendente». El orden vigente se dice en voz alta; los valores sin dato van al final.",
      "<b>Ubicación y archivos junto al nombre.</b> Forma + texto: contorno, punto X/Y, elegir contorno o sin ubicación. Los 96 botones «Elegir…» de la tabla actual pasan a la ficha y al menú de la fila.",
      "<b>Una sola ficha</b> para Tabla y Mapa, editable: precio, superficie, ubicación, archivos, columnas de la base e historial. Sustituye al detalle (⋯) y a la ficha de sólo lectura del mapa.",
      "<b>Estado de guardado arriba</b>, junto al trabajo, y no en el pie de la ventana. Cada celda conserva además su estado propio.",
    ],
  });
}

function a2() {
  const mw = W - FICHA, mh = H - 134;
  const { svg, px } = mapa({ w: mw, h: mh, centro: [20.74, -100.66], spanLon: 1.3, filas: filtrados, sel: "apaseo", escala: "local", id: "a2" });
  const [sx, sy] = px(SEL.x, SEL.y);
  const ui = `${cabecera({})}${barra({ modo: "mapa" })}${chips({ modo: "mapa" })}
  <div class="principal"><div class="zona">${svg}
    <span class="etq-sel" style="left:${sx + 16}px;top:${sy - 13}px">${ic("contorno")}Polígono Apaseo El Grande – Fracción N…</span>
    <div class="mapa-ctrl" style="right:14px;top:14px"><span>+</span><span>−</span></div>
    <div class="base-mapa" style="left:14px;top:14px"><span class="on">Claro</span><span>Satélite</span><span>Calles</span></div>
    <div class="flota" style="left:14px;bottom:14px">${leyendaPrecio({ total: enMapa.length, fuera: sinUbic })}</div>
    <span class="ilustrativo" style="right:14px;bottom:14px">Mapa base ilustrativo</span>
  </div>${ficha({})}</div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "2 · Mapa con un terreno seleccionado", subtitulo: "A · Hoja con ficha — evolución",
    marcas: [[1, 648, 62], [2, 268, 104], [3, sx - 30, sy + 134 - 30], [4, 236, 650], [5, 1412, 196]],
    notas: [
      "<b>Tabla / Mapa conserva todo:</b> búsqueda, filtros, orden y selección. Al volver a Tabla, la fila seleccionada queda a la vista.",
      "<b>Los mismos chips</b> que en la tabla. El alcance distingue filtrados, dibujados y sin ubicación (22 · 20 · 2).",
      "<b>Selección inequívoca:</b> trazo negro con halo blanco y una etiqueta con el nombre. Contorno real y punto X/Y se distinguen por la forma, no sólo por el color.",
      "<b>La leyenda explica forma y color</b>: clases de Asking $/m², hueco para «sin precio por m²» y un enlace a los terrenos que no aparecen.",
      "<b>La misma ficha</b> que en la tabla, también editable. Ya no hace falta volver a la tabla para corregir un dato o subir un KMZ.",
    ],
  });
}

function a3() {
  const editando = {
    precio: `<span class="campo-edit">$92,500,000<span class="cursor"></span><small>MXN</small></span><span class="ayuda-campo">Enter guarda · Esc cancela. Asking $/m² ya tiene valor: no se recalcula.</span>`,
    etapa: `Oferta <span class="guardado-campo">${ic("ok")}Guardado</span>`,
  };
  const est = `<span class="estado-guardado trabajando">${ic("pendiente")}Editando 1 dato · 1 archivo subiendo</span>`;
  const y = yFila("apaseo");
  const ui = `${cabecera({ rol: "operador", estado: est })}${barra({ rol: "operador" })}${chips({})}
  <div class="principal"><div class="zona">${grid({ filas: ordenados, cols: COLS_A, sel: "apaseo", orden: "pm2" })}</div>
  ${ficha({ rol: "operador", editando, subiendo: { nombre: "levantamiento-topografico.pdf", pct: 64 }, top: -112 })}</div>
  ${menuContexto("operador", 300, y - 134 + 134 - 232)}`;
  return conNotas({
    w: W, h: H, ui, titulo: "3 · Ficha en edición (operadora)", subtitulo: "A · Hoja con ficha — evolución",
    marcas: [[1, 1062, 238], [2, 1062, 286], [3, 925, 14], [4, 1062, 700], [5, 290, y - 240], [6, 1062, 147]],
    notas: [
      "<b>Edición en el sitio:</b> cada dato de la ficha se edita como una celda (Enter guarda, Esc cancela) con la misma cola de guardado por versión.",
      "<b>Regla de autollenado a la vista:</b> la ayuda dice qué se completará y qué no. Nunca se sobrescribe un valor existente.",
      "<b>Estado global honesto:</b> qué se edita y cuántos archivos suben. Si se intenta salir, avisa antes de interrumpir.",
      "<b>Archivos con progreso</b>, versión y autor. Se suben desde la ficha, arrastrando sobre la fila o con el menú de la fila.",
      "<b>Menú contextual de la fila</b> (clic derecho o ⋯) con atajos. Para la operadora, «Transferir» aparece deshabilitado con su razón; el servidor sigue siendo la autoridad.",
      "<b>El encabezado de la ficha se queda arriba</b> al desplazarse: el nombre y «Ver en mapa» no se pierden.",
    ],
  });
}

function a4() {
  const i0 = Math.max(0, ordenados.findIndex((x) => x.id === "apaseo") - 3);
  const lista = ordenados.slice(i0, i0 + 7).map((t) => `<li class="${t.id === "apaseo" ? "sel" : ""}"><div class="l1"><b>${esc(t.nombre)}</b><span class="n">${t.pm2 == null ? SD : precio(t.pm2)}<small>/m²</small></span></div>
    <div class="l2"><span>${esc(t.tipo ?? "Sin tipo")} · ${esc(t.municipio)}</span><span class="n">${m2(t.m2)} m²</span></div><div class="l3">${ubic(t)}${docs(t)}</div></li>`).join("");
  const t = SEL;
  const pant1 = `<div class="tel-estado"><span>9:41</span><span>●●● ▮</span></div>
  <div class="m-cab"><span class="ambito"><b>Bajío Industrial 2026</b>${ic("abajo")}</span><span class="btn icono quiet">${ic("usuario")}</span></div>
  <div class="m-barra"><span class="campo" style="flex:1">${ic("buscar")}Buscar</span><span class="btn">${ic("filtro")}<span class="cont">2</span></span></div>
  <div class="m-chips"><span class="chip">GTO, QRO${ic("cerrar")}</span><span class="chip">Industrial, Comercial${ic("cerrar")}</span></div>
  <div class="m-seg"><span class="seg" style="width:100%"><span class="on" style="flex:1;justify-content:center">${ic("lista")}Lista</span><span style="flex:1;justify-content:center">${ic("mapa")}Mapa</span></span></div>
  <p class="m-alc"><b>${filtrados.length}</b> de ${TOTAL_BASE} · Asking $/m², mayor primero</p>
  <ul class="m-lista">${lista}</ul>
  <span class="fab">${ic("mas")}Agregar</span>`;
  const { precioS, sup } = seccionesFicha(t);
  const pant2 = `<div class="tel-estado"><span>9:41</span><span>●●● ▮</span></div>
  <div class="m-nav"><span>${ic("izq")}${filtrados.length} terrenos</span><span class="btn sm">${ic("mas3")}</span></div>
  <div class="m-ficha"><h2>${esc(t.nombre)}</h2><p class="sub">${esc(t.tipo)} · ${esc(t.municipio)}, ${esc(t.estado)}</p>
  <div class="m-acc"><span class="btn" style="flex:1;justify-content:center">${ic("mapa")}Ver en mapa</span><span class="btn" style="flex:1;justify-content:center">${ic("doc")}Abrir PDF</span></div>
  <div class="sec"><h3>Precio</h3>${precioS}</div><div class="sec"><h3>Superficie</h3>${sup}</div>
  <div class="sec"><h3>Ubicación</h3>${ubicacionFicha(t)}</div>
  <div class="sec"><h3>Archivos</h3>${archivosFicha(t)}</div></div>`;
  const ui = `<div class="tels">${telefono(pant1, "Lista: la tabla se vuelve renglones de dos líneas")}${telefono(pant2, "Ficha a pantalla completa, editable campo por campo")}</div>`;
  return conNotas({
    w: 900, h: H, ui, titulo: "4 · Ancho reducido (390 px, operadora)", subtitulo: "A · Hoja con ficha — evolución",
    marcas: [[1, 12, 84], [2, 378, 160], [3, 380, 272], [4, 446, 226]],
    notas: [
      "<b>Hipótesis:</b> en el teléfono se consulta (buscar, ubicar, abrir un PDF) y se corrige poco. La cabecera y la base caben en una línea.",
      "<b>Los filtros no se pierden:</b> los mismos chips, desplazables. Lista / Mapa sustituye a Tabla / Mapa.",
      "<b>Renglón de dos líneas:</b> nombre completo, Asking $/m², superficie, ubicación y PDF. Sin desplazamiento horizontal.",
      "<b>Misma ficha que en escritorio:</b> las tareas siguen disponibles (editar, subir) aunque cambie su presentación (HIG, layout › Size classes).",
    ],
  }).replace('class="lienzo"', 'class="lienzo" style="background:#e9e6df"');
}

function a5() {
  const celdas = {
    "silao|m2": { cls: "celda-conflicto", html: `<span class="marca-celda">${ic("error")}</span>72,500` },
    "corredor57|precio": { cls: "celda-incierta", html: `<span class="marca-celda">${ic("pendiente")}</span>$153,750,000` },
  };
  const est = `<span class="estado-guardado alerta">${ic("error")}1 conflicto · 1 sin confirmar</span><span class="btn sm">Revisar</span>`;
  const ys = yFila("silao"), yc = yFila("corredor57");
  const ui = `${cabecera({ estado: est })}${barra({})}${chips({})}
  <div class="principal"><div class="zona">${grid({ filas: ordenados, cols: COLS_A, orden: "pm2", celdas, sel: "silao" })}
  <div class="pop" style="left:420px;top:${ys - 134 + 40}px;width:390px;padding:14px 16px" role="dialog" aria-label="Conflicto en Superficie">
    <div class="flecha-pop" style="left:300px;top:-7px"></div>
    <p style="margin:0 0 4px;font-weight:600;display:flex;gap:6px;align-items:center;color:var(--err)">${ic("error")}Superficie: alguien guardó antes</p>
    <p style="margin:0 0 10px;color:var(--ink-2);font-size:12.5px">Omar Ficticio cambió este dato mientras lo editabas. Nada se sobrescribió.</p>
    <dl class="dl dos" style="margin-bottom:12px"><div class="dl-f"><dt>Lo que escribiste</dt><dd class="n" style="font-size:15px;font-weight:600">72,500 m²</dd></div><div class="dl-f"><dt>Guardado ahora · hace 1 min</dt><dd class="n" style="font-size:15px;font-weight:600">72,300 m²</dd></div></dl>
    <div style="display:flex;gap:8px;justify-content:flex-end"><span class="btn">Conservar 72,300</span><span class="btn prim">Guardar 72,500</span></div>
  </div>
  <div class="pop" style="left:650px;top:${yc - 134 + 40}px;width:300px;padding:10px 12px;font-size:12.5px"><div class="flecha-pop" style="left:240px;top:-7px"></div>
    <b style="display:flex;gap:6px;align-items:center;color:var(--warn)">${ic("pendiente")}Sin confirmar</b><span style="color:var(--ink-2)">No llegó respuesta. Se comprueba con el servidor antes de volver a enviar.</span></div>
  </div>
  <aside class="otro-estado"><span class="tit">Otro estado · sin resultados</span>
    <div class="vacio-ilus">${ic("buscar")}</div>
    <p style="margin:0 0 6px;font-weight:600;font-size:15px">Ningún terreno coincide con «Fresnos» y estos filtros</p>
    <p style="margin:0 0 14px;color:var(--ink-2);font-size:12.5px">En esta base hay 1 coincidencia que el filtro <b>Tipo</b> deja fuera: «Rancho Los Fresnos (temporal)», Agrícola.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><span class="btn">Quitar el filtro Tipo</span><span class="btn quiet">Quitar todos los filtros</span></div>
    <hr style="border:0;border-top:1px solid var(--rule);margin:22px 0 16px">
    <span class="tit2">Otro estado · cargando</span>
    <div class="esq"><i style="width:80%"></i><i style="width:55%"></i><i style="width:70%"></i><i style="width:40%"></i></div>
    <p style="margin:8px 0 0;font-size:12px;color:var(--ink-2)">${ic("pendiente")} Cargando 22 terrenos… La búsqueda y los filtros siguen activos.</p>
  </aside></div>`;
  return conNotas({
    w: W, h: H, ui, titulo: "5 · Conflicto, sin confirmar, sin resultados y carga", subtitulo: "A · Hoja con ficha — evolución",
    marcas: [[1, 926, 14], [2, 410, ys - 134 + 134 + 30], [3, 960, yc + 4], [4, 1062, 150], [5, 1062, 520]],
    notas: [
      "<b>Un contador que lleva al problema.</b> «Revisar» recorre las celdas pendientes sin perder la posición en la tabla.",
      "<b>El conflicto se resuelve en su celda</b>, con los dos valores y quién guardó. Se conserva la regla vigente: nada se reintenta ni se sobrescribe solo.",
      "<b>Sin confirmar no es error:</b> la app comprueba con el servidor antes de reenviar (comportamiento actual). Ámbar, icono y texto.",
      "<b>Sin resultados que orienta:</b> dice qué filtro excluye lo buscado y ofrece la salida. Contar lo oculto requiere una consulta adicional; no es una capacidad de negocio nueva.",
      "<b>Carga sin bloquear:</b> esqueleto con la forma de la tabla; los controles siguen disponibles (HIG, loading › Best practices).",
    ],
  });
}

const CSS_M = `
.m-cab{display:flex;justify-content:space-between;align-items:center;padding:4px 12px 6px 6px}
.m-cab .ambito b{font-size:17px}
.m-barra{display:flex;gap:8px;padding:0 16px 8px}
.m-barra .campo{height:36px}
.m-barra .btn{height:36px}
.m-chips{display:flex;gap:6px;padding:0 16px 8px;overflow:hidden}
.m-seg{padding:0 16px 6px}
.m-seg .seg span{height:30px}
.m-alc{margin:4px 16px 6px;font-size:12px;color:var(--ink-2)}
.m-lista{list-style:none;margin:0;padding:0;border-top:1px solid var(--rule)}
.m-lista li{padding:10px 16px;border-bottom:1px solid var(--rule);background:var(--raised)}
.m-lista li.sel{background:var(--sel-bg);box-shadow:inset 3px 0 0 var(--ink)}
.m-lista .l1{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.m-lista .l1 b{font-size:14px;font-weight:600;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.m-lista .l1 .n{font-size:14px;font-weight:600;white-space:nowrap}
.m-lista .l1 small{font-weight:400;color:var(--ink-2);font-size:11px}
.m-lista .l2{display:flex;justify-content:space-between;color:var(--ink-2);font-size:12.5px;margin-top:2px}
.m-lista .l3{display:flex;gap:12px;margin-top:5px}
.fab{position:absolute;right:16px;bottom:24px;display:inline-flex;gap:6px;align-items:center;height:44px;padding:0 16px;border-radius:22px;background:var(--ink);color:#fff;font-weight:600;box-shadow:0 6px 16px rgba(0,0,0,.25)}
.m-nav{display:flex;justify-content:space-between;align-items:center;padding:6px 14px 6px 8px;font-size:15px;color:var(--ink)}
.m-nav>span:first-child{display:inline-flex;align-items:center;gap:2px}
.m-ficha h2{margin:0 16px;font-size:20px;line-height:1.25;font-weight:650;letter-spacing:-.01em}
.m-ficha .sub{margin:4px 16px 10px;color:var(--ink-2)}
.m-acc{display:flex;gap:8px;padding:0 16px 12px}
.m-acc .btn{height:40px;font-weight:500}
.m-ficha .sec{padding:12px 16px}
`;

export function generarA() {
  return {
    "A1-tabla.html": ["A · Hoja con ficha — Tabla", a1()],
    "A2-mapa.html": ["A · Hoja con ficha — Mapa", a2()],
    "A3-ficha-edicion.html": ["A · Hoja con ficha — Ficha en edición", a3()],
    "A4-estrecho.html": ["A · Hoja con ficha — Ancho reducido", a4()],
    "A5-estados.html": ["A · Hoja con ficha — Estados", a5()],
    css: CSS + CSS_M,
  };
}

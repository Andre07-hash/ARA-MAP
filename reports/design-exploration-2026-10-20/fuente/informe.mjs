// Renders the report twice from contenido.mjs: README.md (for GitHub) and
// index.html (the comparison page, opened directly from disk).
//   node informe.mjs

import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { A11Y, CONSERVAR, CONTEXTO, CRITERIOS, DECISIONES, DIAGNOSTICO, DIRECCIONES, META, RECOMENDACION, VERIFICACION } from "./contenido.mjs";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const ETIQ = ["Tabla o espacio principal", "Mapa con un terreno seleccionado", "Detalle y edición", "Ancho reducido (390 px)", "Estados complementarios"];

/* ------------------------------------------------------------- README.md */

function markdown() {
  const L = [];
  L.push(`# ${META.titulo}`, "", `${META.fecha} · base revisada: \`origin/main\` @ \`${META.commitCorto}\` (${META.commitTitulo}) · rama \`${META.rama}\``, "");
  L.push("Auditoría de la experiencia actual y tres direcciones de rediseño con mockups comparables. **No se implementó nada en la aplicación.** Para ver los mockups, abre [`index.html`](index.html) en el navegador (lámina comparativa) o cualquier archivo de [`mockups/`](mockups/).", "");
  L.push("Skill de referencia: `apple-design` (" + META.skill + "), con su proceso de revisión y su modo de mejora. Las citas indican el archivo y la sección de `references/hig/`. Lo que no lleva cita es criterio propio, y lo que hay que comprobar con usuarios se marca como hipótesis.", "");
  L.push("## Qué se verificó", "", ...VERIFICACION.hecho.map((x) => `- ${x}`), "", "**Límites:**", "", ...VERIFICACION.noHecho.map((x) => `- ${x}`), "");
  L.push("## 1. Contexto", "", `**Hipótesis de entorno.** ${CONTEXTO.hipotesis}`, "", "**Roles (verificados en `server/auth.py` y `web/components/app.js`):**", "", ...CONTEXTO.roles.map(([r, d]) => `- **${r}.** ${d}`), "");
  L.push(`**Tareas frecuentes:** ${CONTEXTO.tareas.frecuentes.join(" · ")}.`, "", `**Tareas delicadas:** ${CONTEXTO.tareas.delicadas.join(" · ")}.`, "", `**Tabla, mapa, filtros y ficha hoy.** ${CONTEXTO.relacion}`, "", `**Guardado hoy.** ${CONTEXTO.guardado}`, "");
  L.push("## 2. Diagnóstico: siete oportunidades de mayor impacto", "");
  DIAGNOSTICO.forEach((d, i) => {
    L.push(`### ${i + 1}. ${d.titulo}`, "", `- **Evidencia (observado):** ${d.evidencia}`, `- **Tarea afectada:** ${d.tarea}`, `- **Consecuencia:** ${d.consecuencia}`, `- **Cambio propuesto:** ${d.cambio}`, `- Captura: [\`actual/${d.actual}\`](actual/${d.actual})`, "");
  });
  L.push("### Qué conviene conservar", "", ...CONSERVAR.map((x) => `- ${x}`), "");
  L.push("Principios citados (leídos en la skill):", "",
    "- `layout.md › Desktop (macOS)`: «Avoid placing controls or critical information at the bottom of a window.»",
    "- `layout.md › Size classes`: «Keep functionality the same as size classes change… you can change the amount of functionality that’s visible onscreen.»",
    "- `layout.md › Visual hierarchy`: «Use progressive disclosure to make layouts cleaner and easier to interact with.»",
    "- `accessibility.md › Vision`: contraste mínimo de 4.5:1 para texto de hasta 17 pt; «Convey information with more than color alone.»",
    "- `lists-and-tables.md › Desktop`: «let people click a column heading to sort a table view based on that column.»",
    "- `searching.md › Best practices`: «Clearly display the current scope of a search.»",
    "- `maps.md › Best practices`: «Clearly identify elements that people select.» · `maps.md › Place cards`: «Keep the location on your map visible when displaying a place card.»",
    "- `feedback.md › Best practices`: «Consider integrating status feedback into your interface.»",
    "- `modality.md`: «Present content modally only when there’s a clear benefit.»",
    "- `panels.md`: el inspector «displays the details of the currently selected item, automatically updating its contents».",
    "- `materials.md › Liquid Glass`: «Don’t use Liquid Glass in the content layer.»",
    "- `split-views.md › Best practices`: «persistently highlight the current selection in each pane».", "");
  L.push("## 3. Vista comparativa", "", "| | " + DIRECCIONES.map((d) => `${d.id} · ${d.nombre} (${d.nivel})`).join(" | ") + " |", "|---|---|---|---|");
  ETIQ.forEach((e, i) => L.push(`| ${i + 1}. ${e} | ` + DIRECCIONES.map((d) => `[![${d.id}${i + 1}](capturas/${d.pantallas[i]}.png)](mockups/${d.pantallas[i]}.html)`).join(" | ") + " |"));
  L.push("");
  L.push("## 4. Las tres direcciones", "");
  for (const d of DIRECCIONES) {
    L.push(`### ${d.id} · ${d.nombre} — ${d.nivel}`, "", `**Idea central.** ${d.idea}`, "", `- **Beneficia:** ${d.beneficia}`, `- **Organización:** ${d.organiza}`, `- **Conserva:** ${d.conserva}`, `- **Cambia:** ${d.cambia}`, `- **Elimina:** ${d.elimina}`, `- **Principal ventaja:** ${d.ventaja}`, `- **Principal sacrificio o riesgo:** ${d.riesgo}`, `- **Rasgo distintivo:** ${d.rasgo}`, "");
    L.push("**Recorrido** (encontrar → verlo en el mapa → revisar información y archivos → volver):", "", ...d.recorrido.map((r, i) => `${i + 1}. ${r}`), "", `*Pendiente de validar:* ${d.validar}`, "");
    L.push("Mockups: " + d.pantallas.map((p) => `[${p}](mockups/${p}.html)`).join(" · "), "");
  }
  L.push("## 5. Comparación cualitativa", "", "| Criterio | A · Hoja con ficha | B · Mesa dividida | C · Atlas de expedientes |", "|---|---|---|---|", ...CRITERIOS.map((r) => `| ${r.join(" | ")} |`), "", "Sin puntuaciones: las diferencias se explican con observaciones y razonamiento, no con números inventados.", "");
  L.push("## 6. Recomendación", "", `**${RECOMENDACION.eleccion}.**`, "", ...RECOMENDACION.razones.map((x) => `- ${x}`), "", "**Elementos rescatables de las otras direcciones:**", "", ...RECOMENDACION.rescates.map((x) => `- ${x}`), "", "**Riesgos:**", "", ...RECOMENDACION.riesgos.map((x) => `- ${x}`), "", "**Orden sugerido si más adelante se autoriza implementar** (un PR por paso; esta tarea no lo autoriza):", "", ...RECOMENDACION.orden.map((x, i) => `${i + 1}. ${x}`), "");
  L.push("## 7. Accesibilidad, teclado y comportamiento responsive", "", "Contraste medido con la fórmula de WCAG 2.x sobre los valores hexadecimales de los mockups:", "", "| Par | Contraste |", "|---|---|", ...A11Y.contraste.map(([a, b]) => `| ${a} | ${b} |`), "");
  L.push(`- **Foco.** ${A11Y.foco}`, `- **Teclado.** ${A11Y.teclado}`, `- **Lector de pantalla.** ${A11Y.lector}`, `- **Movimiento y transparencia.** ${A11Y.movimiento}`, `- **Tamaños.** ${A11Y.tamanos}`, `- **Responsive.** ${A11Y.responsive}`, "", `> ${A11Y.limite}`, "");
  L.push("## 8. Autocrítica aplicada antes de entregar", "",
    "- Las marcas numeradas tapaban texto: se movieron a los márgenes de cada elemento.",
    "- En A, la columna por la que se ordena quedaba oculta tras la ficha. Se reordenaron y ajustaron los anchos para que «Asking $/m²» siempre quede a la vista.",
    "- En A3, el menú «⋯» tapaba el campo que se estaba editando. Pasó a ser un menú contextual de la fila, y la ficha conserva su encabezado al desplazarse.",
    "- En B3, el fondo «Satélite» aparecía marcado sobre un mapa claro. Se corrigió para no afirmar algo que la imagen no muestra.",
    "- En B5, el terreno con dos contornos quedaba fuera de los filtros del escenario. Ese estado usa ahora su propio filtro, y lo dice.",
    "- En C, la tira grande en bloques negros dominaba la pantalla y se desbordaba. Pasó a un tono suave con texto y marca ✓, y se cuenta con la misma rejilla en cualquier ancho.",
    "- La nota de C5 decía «4 sin precio» cuando el conjunto tenía 2. Ahora los conteos salen de los datos, no del texto.",
    "- ¿Podría pertenecer a cualquier dashboard? La respuesta está en lo que se conserva y se refuerza: el cromo acromático con el color reservado al precio por m², la forma que distingue un contorno de un punto X/Y, «sin dato» distinto de cero y los X/Y nombrados como latitud y longitud. C añade la tira de expediente, propia de un inventario de terrenos.", "");
  L.push("## 9. Decisiones que necesito", "", ...DECISIONES.map((x, i) => `${i + 1}. ${x}`), "");
  L.push("## 10. Archivos", "",
    "| Ruta | Contenido |", "|---|---|",
    "| `index.html` | Lámina comparativa: diagnóstico, las tres direcciones lado a lado, comparación y recomendación |",
    "| `mockups/*.html` | Los 15 mockups (5 por dirección) en HTML/CSS estático; se abren sin servidor |",
    "| `capturas/*.png` | Render de cada mockup con sus notas numeradas |",
    "| `actual/*.png` | Capturas del producto actual con datos ficticios en un entorno local aislado |",
    "| `fuente/` | Generador de los mockups y de este informe (`node generar.mjs --png`, `node informe.mjs`) y datos ficticios |", "",
    "Los mockups no tienen interacciones: son estáticos. Las notas de la columna oscura no forman parte de la interfaz.", "");
  return L.join("\n");
}

/* ------------------------------------------------------------ index.html */

function html() {
  const fig = (p, alt) => `<a class="mini" href="mockups/${p}.html"><img src="capturas/${p}.png" alt="${esc(alt)}" loading="lazy"></a>`;
  const diag = DIAGNOSTICO.map((d, i) => `<article class="diag"><a class="diag-img" href="actual/${d.actual}"><img src="actual/${d.actual}" alt="Captura del producto actual: ${esc(d.titulo)}" loading="lazy"></a>
    <div><h3><span class="num">${i + 1}</span>${esc(d.titulo)}</h3><dl><dt>Evidencia</dt><dd>${esc(d.evidencia)}</dd><dt>Tarea</dt><dd>${esc(d.tarea)}</dd><dt>Consecuencia</dt><dd>${esc(d.consecuencia)}</dd><dt>Cambio</dt><dd>${esc(d.cambio)}</dd></dl></div></article>`).join("");
  const tarjetas = DIRECCIONES.map((d) => `<article class="dir"><p class="eyebrow">${d.id} · ${d.nivel}</p><h3>${esc(d.nombre)}</h3><p class="idea">${esc(d.idea)}</p>${fig(d.pantallas[0], `${d.nombre}: pantalla principal`)}
    <dl><dt>Rasgo</dt><dd>${esc(d.rasgo)}</dd><dt>Ventaja</dt><dd>${esc(d.ventaja)}</dd><dt>Sacrificio</dt><dd>${esc(d.riesgo)}</dd></dl><a class="ir" href="#dir-${d.id}">Detalle y recorrido ↓</a></article>`).join("");
  const rejilla = ETIQ.map((e, i) => `<div class="fila-et">${i + 1}. ${esc(e)}</div>${DIRECCIONES.map((d) => fig(d.pantallas[i], `${d.nombre}: ${e}`)).join("")}`).join("");
  const detalle = DIRECCIONES.map((d) => `<section class="det" id="dir-${d.id}"><p class="eyebrow">${d.id} · ${d.nivel}</p><h2>${esc(d.nombre)}</h2><p class="lead">${esc(d.idea)}</p>
    <div class="det-cols"><dl><dt>Beneficia</dt><dd>${esc(d.beneficia)}</dd><dt>Organización</dt><dd>${esc(d.organiza)}</dd><dt>Conserva</dt><dd>${esc(d.conserva)}</dd><dt>Cambia</dt><dd>${esc(d.cambia)}</dd><dt>Elimina</dt><dd>${esc(d.elimina)}</dd></dl>
    <div><h4>Recorrido</h4><ol>${d.recorrido.map((r) => `<li>${esc(r)}</li>`).join("")}</ol><p class="validar"><b>Pendiente de validar.</b> ${esc(d.validar)}</p></div></div>
    <div class="tira-mini">${d.pantallas.map((p, i) => fig(p, `${d.nombre}: ${ETIQ[i]}`)).join("")}</div></section>`).join("");
  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Exploración de diseño</title>
<meta name="description" content="ARA Map: auditoría de experiencia y tres direcciones de diseño comparables, con mockups estáticos y datos ficticios.">
<style>
:root{--paper:#f7f6f3;--raised:#fdfdfc;--sunken:#efede9;--ink:#1d1b19;--ink-2:#55524f;--ink-3:#6b6764;--rule:#e2dfda;--rule-2:#cbc7c1;--acento:#e8562a;
--font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,system-ui,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--font);-webkit-font-smoothing:antialiased}
a{color:inherit}
a:focus-visible{outline:2px solid var(--ink);outline-offset:3px;border-radius:3px}
.envoltura{max-width:1240px;margin:0 auto;padding:0 24px}
header.cab{padding:48px 0 28px;border-bottom:1px solid var(--rule)}
.eyebrow{margin:0 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2);font-weight:600}
h1{margin:0 0 12px;font-size:clamp(28px,4vw,40px);line-height:1.12;letter-spacing:-.02em;font-weight:700;max-width:860px}
h2{font-size:24px;line-height:1.2;letter-spacing:-.01em;margin:0 0 8px}
h3{font-size:17px;margin:0 0 8px;line-height:1.3}
h4{margin:0 0 8px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2)}
.meta{color:var(--ink-2);font-size:13.5px;margin:0}
.meta code{font-size:12.5px;background:var(--sunken);padding:1px 5px;border-radius:4px}
nav.indice{position:sticky;top:0;z-index:5;background:rgba(247,246,243,.96);border-bottom:1px solid var(--rule);backdrop-filter:blur(8px)}
nav.indice ul{list-style:none;margin:0;padding:10px 0;display:flex;gap:18px;flex-wrap:wrap;font-size:13.5px}
nav.indice a{text-decoration:none;color:var(--ink-2)}
nav.indice a:hover{color:var(--ink);text-decoration:underline}
section{padding:40px 0;border-bottom:1px solid var(--rule)}
.lead{font-size:17px;color:var(--ink);max-width:860px;margin:0 0 18px}
.dos{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.caja{background:var(--raised);border:1px solid var(--rule);border-radius:12px;padding:18px 20px}
.caja ul{margin:0;padding-left:18px}
.caja li+li{margin-top:6px}
.diag{display:grid;grid-template-columns:320px 1fr;gap:22px;padding:20px 0;border-top:1px solid var(--rule)}
.diag:first-of-type{border-top:0}
.diag-img img{width:100%;border:1px solid var(--rule-2);border-radius:8px;display:block}
.diag dl,.dir dl,.det dl{margin:0;display:grid;grid-template-columns:120px 1fr;gap:6px 14px;font-size:14px}
.diag dt,.dir dt,.det dt{color:var(--ink-2);font-weight:600}
.diag dd,.dir dd,.det dd{margin:0}
.num{display:inline-flex;width:26px;height:26px;border-radius:13px;background:var(--ink);color:#fff;font-size:13px;align-items:center;justify-content:center;margin-right:10px;vertical-align:2px}
.dirs{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.dir{background:var(--raised);border:1px solid var(--rule);border-radius:14px;padding:18px;display:flex;flex-direction:column;gap:12px}
.dir h3{font-size:21px;margin:0}
.dir .idea{margin:0;color:var(--ink-2);font-size:14px}
.dir dl{grid-template-columns:86px 1fr;font-size:13.5px}
.dir .ir{margin-top:auto;font-size:13.5px}
.mini{display:block;border:1px solid var(--rule-2);border-radius:8px;overflow:hidden;background:#fff}
.mini img{display:block;width:100%;height:auto}
.mini:hover{border-color:var(--ink)}
.rejilla{display:grid;grid-template-columns:150px repeat(3,1fr);gap:14px;align-items:center}
.rejilla .col{font-weight:700;font-size:14px}
.fila-et{font-size:13.5px;font-weight:600;color:var(--ink-2)}
.det-cols{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-bottom:18px}
.det dl{grid-template-columns:110px 1fr}
.det ol{margin:0;padding-left:20px;font-size:14px}
.det ol li+li{margin-top:6px}
.validar{font-size:13.5px;color:var(--ink-2);background:#fffbe6;border:1px solid #e6d58a;border-radius:8px;padding:10px 12px;margin:14px 0 0}
.tira-mini{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--raised);border:1px solid var(--rule);border-radius:12px;overflow:hidden}
th,td{text-align:left;vertical-align:top;padding:10px 12px;border-bottom:1px solid var(--rule)}
th{background:var(--sunken);font-size:13px}
td:first-child{font-weight:600;width:190px}
.reco{background:var(--ink);color:#f7f6f3;border-radius:16px;padding:26px 28px}
.reco h2{color:#fff}
.reco .eyebrow{color:#c4bfb6}
.reco ul,.reco ol{margin:6px 0 16px;padding-left:20px}
.reco h4{color:#c4bfb6}
.reco .cols{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.decisiones li{margin-bottom:8px}
code{font-size:13px}
footer{padding:28px 0 60px;color:var(--ink-2);font-size:13px}
@media (max-width:600px){.diag dl,.dir dl,.det dl{grid-template-columns:1fr;gap:2px}.diag dd,.dir dd,.det dd{margin-bottom:8px}nav.indice ul{flex-wrap:nowrap;overflow-x:auto;white-space:nowrap}}
@media (max-width:900px){.dos,.det-cols,.reco .cols{grid-template-columns:1fr}.dirs{grid-template-columns:1fr}.diag{grid-template-columns:1fr}.rejilla{grid-template-columns:1fr}.rejilla .vacia{display:none}.tira-mini{grid-template-columns:repeat(2,1fr)}td:first-child{width:auto}table{display:block;overflow-x:auto}}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style></head><body>
<header class="cab"><div class="envoltura"><p class="eyebrow">${esc(META.titulo)} · ${esc(META.fecha)}</p>
<h1>Tres maneras de trabajar con terrenos, comparadas con los mismos datos</h1>
<p class="meta">Base revisada: <code>origin/main</code> @ <code>${META.commitCorto}</code> (${esc(META.commitTitulo)}). Rama: <code>${META.rama}</code>. Datos ficticios. Auditoría y mockups estáticos; no se implementó nada en la app.</p></div></header>
<nav class="indice" aria-label="Secciones"><div class="envoltura"><ul><li><a href="#contexto">Contexto</a></li><li><a href="#diagnostico">Diagnóstico</a></li><li><a href="#direcciones">Direcciones</a></li><li><a href="#comparativa">Comparativa</a></li><li><a href="#criterios">Criterios</a></li><li><a href="#recomendacion">Recomendación</a></li><li><a href="#a11y">Accesibilidad</a></li><li><a href="#decisiones">Decisiones</a></li></ul></div></nav>
<main class="envoltura">
<section id="contexto"><h2>Contexto y método</h2><p class="lead">${esc(CONTEXTO.hipotesis)}</p>
<div class="dos"><div class="caja"><h4>Qué se verificó</h4><ul>${VERIFICACION.hecho.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div><div class="caja"><h4>Límites</h4><ul>${VERIFICACION.noHecho.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>
<div class="dos" style="margin-top:20px"><div class="caja"><h4>Roles</h4><ul>${CONTEXTO.roles.map(([r, d]) => `<li><b>${esc(r)}.</b> ${esc(d)}</li>`).join("")}</ul></div><div class="caja"><h4>Tabla, mapa, filtros y guardado hoy</h4><p style="margin:0 0 10px;font-size:14px">${esc(CONTEXTO.relacion)}</p><p style="margin:0;font-size:14px">${esc(CONTEXTO.guardado)}</p></div></div></section>
<section id="diagnostico"><h2>Diagnóstico: siete oportunidades</h2><p class="lead">Ordenadas por su efecto en encontrar, comparar, actuar y recuperarse de errores. Las imágenes son capturas del producto actual con datos ficticios.</p>${diag}
<div class="caja" style="margin-top:20px"><h4>Qué conviene conservar</h4><ul>${CONSERVAR.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></section>
<section id="direcciones"><h2>Las tres direcciones</h2><p class="lead">Cambian la organización, la jerarquía y el modelo de interacción, no la paleta. Ninguna agrega capacidades de negocio; lo que sería trabajo nuevo está marcado como exploración.</p><div class="dirs">${tarjetas}</div></section>
<section id="comparativa"><h2>Misma tarea, tres respuestas</h2><p class="lead">Mismo escenario en cada fila: «Bajío Industrial 2026», filtrado por Guanajuato y Querétaro, tipos Industrial y Comercial, ordenado por Asking $/m², con «Polígono Apaseo El Grande…» seleccionado. Clic en una imagen para abrir el mockup.</p>
<div class="rejilla"><div class="vacia"></div>${DIRECCIONES.map((d) => `<div class="col">${d.id} · ${esc(d.nombre)}</div>`).join("")}${rejilla}</div></section>
${detalle}
<section id="criterios"><h2>Comparación cualitativa</h2><p class="lead">Sin puntuaciones: cada celda resume una observación.</p><table><thead><tr><th>Criterio</th>${DIRECCIONES.map((d) => `<th>${d.id} · ${esc(d.nombre)}</th>`).join("")}</tr></thead><tbody>${CRITERIOS.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></section>
<section id="recomendacion"><div class="reco"><p class="eyebrow">Recomendación</p><h2>${esc(RECOMENDACION.eleccion)}</h2><ul>${RECOMENDACION.razones.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
<div class="cols"><div><h4>Elementos rescatables</h4><ul>${RECOMENDACION.rescates.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><h4>Riesgos</h4><ul>${RECOMENDACION.riesgos.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
<div><h4>Orden sugerido si más adelante se autoriza implementar</h4><ol>${RECOMENDACION.orden.map((x) => `<li>${esc(x)}</li>`).join("")}</ol><p style="font-size:13px;color:#c4bfb6">Esta entrega no autoriza implementar, fusionar ni desplegar.</p></div></div></div></section>
<section id="a11y"><h2>Accesibilidad, teclado y responsive</h2><p class="lead">Contraste medido con la fórmula de WCAG 2.x sobre los valores hexadecimales usados en los mockups.</p>
<table><thead><tr><th>Par de colores</th><th>Contraste</th></tr></thead><tbody>${A11Y.contraste.map(([a, b]) => `<tr><td style="font-weight:400;width:auto">${esc(a)}</td><td>${esc(b)}</td></tr>`).join("")}</tbody></table>
<div class="dos" style="margin-top:20px"><div class="caja"><h4>Foco y teclado</h4><p style="margin:0 0 8px;font-size:14px">${esc(A11Y.foco)}</p><p style="margin:0;font-size:14px">${esc(A11Y.teclado)}</p></div><div class="caja"><h4>Lector, movimiento, tamaños</h4><p style="margin:0 0 8px;font-size:14px">${esc(A11Y.lector)}</p><p style="margin:0 0 8px;font-size:14px">${esc(A11Y.movimiento)}</p><p style="margin:0;font-size:14px">${esc(A11Y.tamanos)}</p></div></div>
<div class="caja" style="margin-top:20px"><h4>Responsive</h4><p style="margin:0;font-size:14px">${esc(A11Y.responsive)}</p><p style="margin:10px 0 0;font-size:13.5px;color:var(--ink-2)">${esc(A11Y.limite)}</p></div></section>
<section id="decisiones"><h2>Decisiones que necesito</h2><ol class="decisiones">${DECISIONES.map((x) => `<li>${esc(x)}</li>`).join("")}</ol></section>
</main>
<footer><div class="envoltura">Archivos: <code>index.html</code> (esta lámina), <code>README.md</code> (informe completo), <code>mockups/</code> (15 HTML), <code>capturas/</code> (PNG con notas), <code>actual/</code> (producto actual), <code>fuente/</code> (generador y datos ficticios).</div></footer>
</body></html>`;
}

writeFileSync(join(RAIZ, "README.md"), markdown());
writeFileSync(join(RAIZ, "index.html"), html());
console.log("README.md e index.html listos");

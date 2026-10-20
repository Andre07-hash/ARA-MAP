// Shared pieces of the static mockups: tokens, formatting, icons and an
// illustrative SVG map drawn from the fictitious dataset. Output is plain
// HTML/CSS; nothing here runs in ARA Map.

import { colorPrecio, contorno, cortes, RAMPA, TAMANO_CONTORNO, TODOS } from "./datos.mjs";

/* ------------------------------------------------------------- formatting */

export const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const comas = (n) => String(n).replace(/^(-?)(\d+)/, (_, s, e) => s + e.replace(/\B(?=(\d{3})+(?!\d))/g, ","));
export const SD = '<span class="sd" title="Sin dato">—</span>';
export const num = (n) => (n == null ? SD : comas(n));
export const m2 = (n) => (n == null ? SD : `${comas(n)}`);
export const ha = (n) => (n == null ? SD : String(n));
export const pct = (n) => (n == null ? SD : `${n}%`);
export const precio = (n) => (n == null ? SD : `$${comas(n)}`);
export const coord = (n) => (n == null ? SD : String(n));
export const sdTexto = (v, f = (x) => esc(x)) => (v == null || v === "" ? '<span class="sd-t">Sin dato</span>' : f(v));
export const cortoM = (n) => (n == null ? SD : n >= 1e6 ? `$${(n / 1e6).toFixed(n >= 1e8 ? 0 : 1)} M` : `$${comas(n)}`);

/* ------------------------------------------------------------------ icons */

const P = {
  buscar: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/>',
  filtro: '<path d="M2.5 4h11M4.5 8h7M6.5 12h3"/>',
  abajo: '<path d="m4 6 4 4 4-4"/>',
  arriba: '<path d="m4 10 4-4 4 4"/>',
  der: '<path d="m6 4 4 4-4 4"/>',
  izq: '<path d="m10 4-4 4 4 4"/>',
  mas: '<path d="M8 3v10M3 8h10"/>',
  cerrar: '<path d="m4 4 8 8M12 4l-8 8"/>',
  tabla: '<rect x="2.5" y="3" width="11" height="10" rx="1"/><path d="M2.5 6.5h11M2.5 10h11M6.5 3v10"/>',
  mapa: '<path d="M2.5 4.2 6 2.8l4 1.6 3.5-1.4v9l-3.5 1.4-4-1.6-3.5 1.4z"/><path d="M6 2.8v9M10 4.4v9"/>',
  doc: '<path d="M4 2.5h5l3 3v8H4z"/><path d="M9 2.5v3h3"/>',
  contorno: '<path d="M3 6 7 2.6l6 2.2-.8 6.6-6.6 2.2L2.6 10z"/>',
  punto: '<circle cx="8" cy="8" r="3.2" fill="currentColor"/>',
  ninguna: '<circle cx="8" cy="8" r="4.5" stroke-dasharray="2 2"/>',
  elegir: '<path d="M2.6 6.5 5.5 3.5l3.6 1.6-.5 4L5 10.4 2.6 9z"/><path d="m8.8 8.2 3.4-1.4 1.4 3.4-2.6 2.4-2.8-1.2z" stroke-dasharray="1.6 1.4"/>',
  historial: '<path d="M2.8 8a5.2 5.2 0 1 0 1.6-3.8"/><path d="M2.5 2.8v2.6h2.6M8 5v3.2l2.2 1.4"/>',
  mas3: '<circle cx="3.5" cy="8" r="1" fill="currentColor"/><circle cx="8" cy="8" r="1" fill="currentColor"/><circle cx="12.5" cy="8" r="1" fill="currentColor"/>',
  subir: '<path d="M8 11V3M4.5 6.5 8 3l3.5 3.5M3 13h10"/>',
  bajar: '<path d="M8 3v8M4.5 7.5 8 11l3.5-3.5M3 13h10"/>',
  ok: '<path d="m3.5 8.5 3 3 6-7"/>',
  aviso: '<path d="M8 2.5 14 13H2z"/><path d="M8 6.5v3M8 11.2v.3"/>',
  error: '<circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.5M8 10.8v.3"/>',
  capas: '<path d="m8 2.5 5.5 3L8 8.5l-5.5-3z"/><path d="m2.5 8.5 5.5 3 5.5-3M2.5 11 8 14l5.5-3"/>',
  encuadrar: '<path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10"/>',
  columnas: '<rect x="2.5" y="3" width="11" height="10" rx="1"/><path d="M6.2 3v10M9.8 3v10"/>',
  editar: '<path d="M10.5 3 13 5.5 6 12.5H3.5V10z"/>',
  expandir: '<path d="M9.5 2.5h4v4M13.5 2.5 9 7M6.5 13.5h-4v-4M2.5 13.5 7 9"/>',
  reintentar: '<path d="M13 8a5 5 0 1 1-1.5-3.6"/><path d="M13.2 2.6v2.8h-2.8"/>',
  usuario: '<circle cx="8" cy="5.5" r="2.6"/><path d="M3 13.5c.8-2.6 2.8-3.8 5-3.8s4.2 1.2 5 3.8"/>',
  orden: '<path d="M5 3v10M2.8 10.8 5 13l2.2-2.2M11 13V3M8.8 5.2 11 3l2.2 2.2"/>',
  ojo: '<path d="M1.8 8S4 3.8 8 3.8 14.2 8 14.2 8 12 12.2 8 12.2 1.8 8 1.8 8z"/><circle cx="8" cy="8" r="2"/>',
  lista: '<path d="M5.5 4h8M5.5 8h8M5.5 12h8"/><circle cx="2.8" cy="4" r=".6" fill="currentColor"/><circle cx="2.8" cy="8" r=".6" fill="currentColor"/><circle cx="2.8" cy="12" r=".6" fill="currentColor"/>',
  barra: '<rect x="2.5" y="3" width="11" height="10" rx="1"/><path d="M6 3v10"/>',
  teclado: '<rect x="1.8" y="4" width="12.4" height="8" rx="1"/><path d="M4 6.5h.5M6.5 6.5H7M9 6.5h.5M11.5 6.5h.5M5 9.5h6"/>',
  pendiente: '<circle cx="8" cy="8" r="5.5"/><path d="M8 4.8V8l2.2 1.6"/>',
  borrar: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5"/>',
  transferir: '<path d="M3 5.5h9.5M10 3l2.5 2.5L10 8M13 10.5H3.5M6 8l-2.5 2.5L6 13"/>',
};
export const ic = (n, cls = "") => `<svg class="ic ${cls}" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">${P[n]}</svg>`;

/* Location of a terrain: shape + words, never colour alone. */
export const UBIC = {
  contorno: { ic: "contorno", corto: "Contorno", largo: "Contorno activo (KMZ/KML)" },
  punto: { ic: "punto", corto: "Punto X/Y", largo: "Punto por X/Y; sin contorno" },
  elegir: { ic: "elegir", corto: "Elegir", largo: "KML con 2 contornos: falta elegir" },
  ninguna: { ic: "ninguna", corto: "Sin ubicación", largo: "Sin contorno ni X/Y válidas" },
};
export const ubic = (t, modo = "corto") => `<span class="ubic ubic-${t.ubic}">${ic(UBIC[t.ubic].ic)}<span>${UBIC[t.ubic][modo]}</span></span>`;
export const docs = (t) => (t.pdf.length ? `<span class="docs">${ic("doc")}<span>${t.pdf.length} PDF</span></span>` : `<span class="docs docs-0">${ic("doc")}<span>0</span></span>`);

/* ---------------------------------------------------------------- the map */

const CIUDADES = {
  QRO: ["Querétaro", 20.593, -100.392, 1], CEL: ["Celaya", 20.523, -100.815, 1], IRA: ["Irapuato", 20.676, -101.354, 1],
  SIL: ["Silao", 20.944, -101.427, 2], LEO: ["León", 21.123, -101.683, 1], LAG: ["Lagos de Moreno", 21.357, -101.932, 2],
  AGS: ["Aguascalientes", 21.882, -102.296, 1], SLP: ["San Luis Potosí", 22.151, -100.976, 1], SMA: ["San Miguel de Allende", 20.914, -100.744, 2],
  DOL: ["Dolores Hidalgo", 21.157, -100.934, 2], SJR: ["San Juan del Río", 20.389, -99.996, 2], APA: ["Apaseo el Grande", 20.546, -100.686, 3],
  SJI: ["San José Iturbide", 21.0, -100.384, 2], COL: ["Colón", 20.78, -100.05, 3], VDR: ["Villa de Reyes", 21.80, -100.93, 3],
  SAL: ["Salamanca", 20.57, -101.19, 2], JM: ["Jesús María", 21.96, -102.34, 3], OCO: ["Ocotlán", 20.35, -102.77, 2],
  COR: ["Corregidora", 20.54, -100.44, 3], PES: ["Pedro Escobedo", 20.50, -100.14, 3], MAR: ["El Marqués", 20.65, -100.28, 3],
  APL: ["Apaseo el Alto", 20.458, -100.62, 3], VIL: ["Villagrán", 20.515, -100.996, 3], JUV: ["Juventino Rosas", 20.643, -100.993, 3],
};
const CARRETERAS = [
  [["QRO", "COR", "APA", "CEL", "VIL", "SAL", "IRA", "SIL", "LEO", "LAG", "AGS", "JM"], 1],
  [["SJR", "PES", "QRO", "SJI", "VDR", "SLP"], 1],
  [["QRO", "MAR", "COL"], 2], [["QRO", "SMA", "DOL", "SLP"], 2], [["CEL", "JUV", "SMA"], 2], [["CEL", "APL", "SJR"], 2],
  [["IRA", "OCO"], 2], [["LEO", "DOL"], 3], [["SAL", "JUV"], 3],
];

export function mapa({ w, h, centro, spanLon, filas = TODOS, sel = null, escala = "region", hover = null, atenuar = null, etiquetas = true, id = "m", cargando = false, sinBase = false }) {
  const [latc, lonc] = centro;
  const spanLat = spanLon * (h / w) * Math.cos((latc * Math.PI) / 180);
  const lon0 = lonc - spanLon / 2, lat1 = latc + spanLat / 2;
  const px = (lat, lon) => [((lon - lon0) / spanLon) * w, ((lat1 - lat) / spanLat) * h];
  const br = cortes();
  const nivel = spanLon > 1.5 ? 2 : 3;
  let s = `<svg class="mapa-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Mapa ilustrativo de terrenos">`;
  s += `<defs><pattern id="${id}-rel" width="22" height="22" patternUnits="userSpaceOnUse"><path d="M0 22 22 0" stroke="#e4e2db" stroke-width=".6"/></pattern></defs>`;
  s += `<rect width="${w}" height="${h}" fill="#ecebe6"/>`;
  if (!sinBase) {
    // a few soft landform patches, purely illustrative
    for (const [la, lo, r] of [[21.5, -101.2, 0.45], [20.85, -100.15, 0.3], [21.9, -100.4, 0.5], [20.45, -101.6, 0.35], [20.62, -100.95, 0.12], [20.68, -100.55, 0.09]]) {
      const [x, y] = px(la, lo); const rr = (r / spanLon) * w;
      s += `<ellipse cx="${x}" cy="${y}" rx="${rr}" ry="${rr * 0.7}" fill="url(#${id}-rel)" opacity=".9"/>`;
    }
    for (const [ruta, tipo] of CARRETERAS) {
      const pts = ruta.map((c) => px(CIUDADES[c][1], CIUDADES[c][2]).map((v) => v.toFixed(1)).join(",")).join(" ");
      const ancho = tipo === 1 ? 4 : tipo === 2 ? 2.6 : 1.8;
      s += `<polyline points="${pts}" fill="none" stroke="#d6d3cb" stroke-width="${ancho + 2}" stroke-linejoin="round"/>`;
      s += `<polyline points="${pts}" fill="none" stroke="${tipo === 1 ? "#fbfaf6" : "#f6f4ee"}" stroke-width="${ancho}" stroke-linejoin="round"/>`;
    }
  }
  const marcas = [];
  for (const t of filas) {
    const la = t.x ?? t.cx, lo = t.y ?? t.cy;
    if (t.ubic === "ninguna" || la == null) continue;
    const [x, y] = px(la, lo);
    if (x < -20 || y < -20 || x > w + 20 || y > h + 20) continue;
    const c = colorPrecio(t, br);
    const fill = c ?? "#ffffff", stroke = c ? "#ffffff" : "#5b5754";
    const dim = atenuar && !atenuar.has(t.id) ? ' opacity=".28"' : "";
    let m;
    if (t.ubic === "contorno" && escala === "local") {
      const [cw, ch] = TAMANO_CONTORNO[t.id] ?? [0.008, 0.006];
      const pts = contorno(t, cw, ch).map(([a, b]) => px(a, b).map((v) => v.toFixed(1)).join(",")).join(" ");
      m = `<polygon points="${pts}" fill="${c ?? "#ffffff"}" fill-opacity="${c ? 0.32 : 0.7}" stroke="${c ?? "#5b5754"}" stroke-width="2" ${c ? "" : 'stroke-dasharray="5 3"'}${dim}/>`;
    } else if (t.ubic === "contorno") {
      const r = 6.8; const hex = Array.from({ length: 6 }, (_, i) => { const a = Math.PI / 6 + (i * Math.PI) / 3; return `${(x + r * Math.cos(a)).toFixed(1)},${(y + r * Math.sin(a)).toFixed(1)}`; }).join(" ");
      m = `<polygon points="${hex}" fill="${fill}" stroke="${stroke}" stroke-width="${c ? 1.6 : 2}"${dim}/><polygon points="${hex}" fill="none" stroke="#1d1b19" stroke-opacity=".35" stroke-width=".8" transform="translate(0 0)"${dim}/>`;
    } else {
      m = `<circle cx="${x}" cy="${y}" r="5.6" fill="${fill}" stroke="${stroke}" stroke-width="${c ? 1.6 : 2}"${dim}/><circle cx="${x}" cy="${y}" r="6.6" fill="none" stroke="#1d1b19" stroke-opacity=".3" stroke-width=".8"${dim}/>`;
    }
    marcas.push({ t, x, y, m });
  }
  s += marcas.map((k) => k.m).join("");
  if (etiquetas && !sinBase) {
    for (const [nombre, la, lo, rango] of Object.values(CIUDADES)) {
      if (rango > nivel) continue;
      const [x, y] = px(la, lo);
      if (x < 10 || y < 14 || x > w - 60 || y > h - 8) continue;
      s += `<text x="${x + 7}" y="${y - 6}" class="mapa-ciudad${rango === 1 ? " mayor" : ""}">${esc(nombre)}</text>`;
    }
  }
  for (const k of marcas) {
    if (k.t.id === hover) s += `<circle cx="${k.x}" cy="${k.y}" r="11" fill="none" stroke="#1d1b19" stroke-width="1.5" stroke-dasharray="3 2"/>`;
    if (k.t.id !== sel) continue;
    if (escala === "local" && k.t.ubic === "contorno") {
      const [cw, ch] = TAMANO_CONTORNO[k.t.id] ?? [0.008, 0.006];
      const pts = contorno(k.t, cw, ch).map(([a, b]) => px(a, b).map((v) => v.toFixed(1)).join(",")).join(" ");
      s += `<polygon points="${pts}" fill="none" stroke="#ffffff" stroke-width="7" stroke-linejoin="round"/><polygon points="${pts}" fill="none" stroke="#1d1b19" stroke-width="3" stroke-linejoin="round"/>`;
    } else {
      s += `<circle cx="${k.x}" cy="${k.y}" r="12" fill="none" stroke="#ffffff" stroke-width="5"/><circle cx="${k.x}" cy="${k.y}" r="12" fill="none" stroke="#1d1b19" stroke-width="2.5"/>`;
    }
  }
  if (cargando) s += `<rect width="${w}" height="${h}" fill="#ecebe6" opacity=".55"/>`;
  s += "</svg>";
  return { svg: s, px };
}

export function leyendaPrecio({ compacta = false, total = 45, fuera = 3 } = {}) {
  const br = cortes();
  const filas = [`&lt; ${comas(br[0])}`, `${comas(br[0])} – ${comas(br[1] - 1)}`, `${comas(br[1])} – ${comas(br[2] - 1)}`, `${comas(br[2])} – ${comas(br[3] - 1)}`, `≥ ${comas(br[3])}`];
  return `<div class="leyenda${compacta ? " compacta" : ""}">
    <div class="ley-titulo"><b>Asking $/m²</b> <span>MXN · ${total} en el mapa</span></div>
    <ul class="ley-rampa">${filas.map((f, i) => `<li><i style="background:${RAMPA[i]}"></i>${f}</li>`).join("")}<li><i class="hueco"></i>Sin precio por m²</li></ul>
    <div class="ley-formas"><span>${ic("contorno")} Contorno KMZ/KML</span><span>${ic("punto")} Punto X/Y</span></div>
    ${fuera ? `<a class="ley-fuera" href="#">${ic("ninguna")} ${fuera} sin ubicación — ver en la lista</a>` : ""}
  </div>`;
}

/* --------------------------------------------------------------- the page */

export const CSS_BASE = `
:root{
  --paper:#f7f6f3;--raised:#fdfdfc;--sunken:#efede9;--overlay:#ffffff;
  --ink:#1d1b19;--ink-2:#55524f;--ink-3:#6b6764;--rule:#e2dfda;--rule-2:#cbc7c1;
  --sel-bg:#e8e5df;--hover-bg:#f1efeb;
  --err:#b42f2f;--err-bg:#fbeaea;--warn:#7a5b16;--warn-bg:#fbf3e3;--ok:#2f7d32;--ok-bg:#eaf4ea;
  --map:#ecebe6;--borde-campo:#8d8984;
  --font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,"JetBrains Mono",monospace;
}
*{box-sizing:border-box}
html,body{margin:0;background:#d9d6cf}
body{font:13px/1.4 var(--font);color:var(--ink);-webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss03"}
.lienzo{position:relative;overflow:hidden;background:var(--paper);margin:0 auto}
button,input,select{font:inherit;color:inherit}
.ic{width:16px;height:16px;flex:none;vertical-align:-3px}
.num,td.n,.n{font-variant-numeric:tabular-nums}
.sd{color:var(--ink-3)}
.sd-t{color:var(--ink-3);font-style:italic}
.btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border:1px solid var(--rule-2);border-radius:6px;background:var(--raised);font-size:13px;white-space:nowrap;cursor:default}
.btn.prim{background:var(--ink);border-color:var(--ink);color:#fff}
.btn.quiet{border-color:transparent;background:transparent}
.btn.sm{height:24px;padding:0 8px;font-size:12px}
.btn.icono{width:28px;padding:0;justify-content:center}
.btn.peligro{color:var(--err);border-color:#e4b9b9}
.seg{display:inline-flex;border:1px solid var(--rule-2);border-radius:7px;padding:2px;background:var(--sunken);gap:2px}
.seg span{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;border-radius:5px;color:var(--ink-2)}
.seg span.on{background:var(--overlay);color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.12);font-weight:500}
.campo{display:flex;align-items:center;gap:6px;height:30px;padding:0 10px;border:1px solid var(--borde-campo);border-radius:7px;background:var(--overlay);color:var(--ink-3)}
.campo b{font-weight:400;color:var(--ink)}
.kbd{font:11px var(--mono);color:var(--ink-2);border:1px solid var(--rule-2);border-bottom-width:2px;border-radius:4px;padding:0 4px;background:var(--raised)}
.chip{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 4px 0 9px;border-radius:12px;background:var(--overlay);border:1px solid var(--rule-2);font-size:12px;white-space:nowrap}
.chip b{font-weight:600}
.chip .ic{width:14px;height:14px;color:var(--ink-2)}
.chip.sug{border-style:dashed;padding-right:9px;color:var(--ink-2);background:transparent}
.ubic,.docs{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;font-size:12px;color:var(--ink-2)}
.ubic-contorno .ic{color:var(--ink)}
.ubic-elegir{color:var(--warn);font-weight:500}
.ubic-ninguna{color:var(--ink-3)}
.docs-0{color:var(--ink-3)}
.etq{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);font-weight:600}
.nota-mock{position:absolute;z-index:50;background:#fffbe6;border:1px solid #e6d58a;color:#4d4211;font-size:11.5px;line-height:1.35;padding:7px 9px;border-radius:6px;max-width:260px;box-shadow:0 2px 6px rgba(0,0,0,.12)}
.nota-mock b{display:block;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:2px}
.nota-mock .n{display:inline-flex;width:18px;height:18px;border-radius:9px;background:#4d4211;color:#fffbe6;align-items:center;justify-content:center;font-size:11px;font-weight:700;margin-right:4px}
.foco{outline:2px solid var(--ink);outline-offset:2px;box-shadow:0 0 0 5px rgba(255,255,255,.9)}
.estado-guardado{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-2);white-space:nowrap}
.estado-guardado.ok .ic{color:var(--ok)}
.estado-guardado.trabajando .ic{color:var(--ink-2)}
.estado-guardado.alerta{color:var(--err);font-weight:600}
.mapa-svg{display:block}
.mapa-ciudad{font:11px var(--font);fill:#55524f;paint-order:stroke;stroke:#ecebe6;stroke-width:3px}
.mapa-ciudad.mayor{font-weight:600;fill:#3d3a37}
.mapa-ctrl{position:absolute;display:flex;flex-direction:column;background:var(--overlay);border:1px solid var(--rule-2);border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.12)}
.mapa-ctrl span{width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:17px;color:var(--ink)}
.mapa-ctrl span+span{border-top:1px solid var(--rule)}
.flota{position:absolute;background:rgba(253,253,252,.94);border:1px solid var(--rule-2);border-radius:10px;box-shadow:0 1px 2px rgba(0,0,0,.06),0 8px 24px rgba(0,0,0,.10)}
.leyenda{width:228px;padding:10px 12px;font-size:12px}
.leyenda .ley-titulo{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.leyenda .ley-titulo span{color:var(--ink-2);font-size:11px}
.ley-rampa{list-style:none;margin:0 0 8px;padding:0;display:grid;gap:3px}
.ley-rampa li{display:flex;align-items:center;gap:8px;font-variant-numeric:tabular-nums}
.ley-rampa i{width:14px;height:10px;border-radius:2px;display:inline-block}
.ley-rampa i.hueco{background:#fff;border:2px solid #5b5754;border-radius:6px;width:12px}
.ley-formas{display:flex;gap:12px;color:var(--ink-2);border-top:1px solid var(--rule);padding-top:7px}
.ley-formas .ic{width:14px;height:14px;color:var(--ink)}
.ley-fuera{display:flex;gap:6px;align-items:center;margin-top:7px;color:var(--ink);text-decoration:underline;text-underline-offset:2px}
.ley-fuera .ic{width:14px;height:14px}
.leyenda.compacta .ley-rampa{grid-template-columns:1fr 1fr}
.base-mapa{position:absolute;display:flex;gap:2px;padding:2px;background:var(--overlay);border:1px solid var(--rule-2);border-radius:8px;font-size:12px}
.base-mapa span{padding:4px 9px;border-radius:6px;color:var(--ink-2)}
.base-mapa span.on{background:var(--ink);color:#fff}
.ilustrativo{position:absolute;font-size:10px;color:var(--ink-2);background:rgba(236,235,230,.85);padding:1px 5px;border-radius:3px}
`;

export function pagina({ titulo, w, h, cuerpo, css = "", nota = "" }) {
  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(titulo)}</title>
<style>${CSS_BASE}${css}</style></head>
<body><main class="lienzo" style="width:${w}px;height:${h}px" aria-label="${esc(titulo)}">${cuerpo}</main>${nota}</body></html>`;
}

/* A phone frame for compact widths (390 × 844 CSS px). */
export const telefono = (contenido, etiqueta) => `<figure class="tel"><div class="tel-pantalla">${contenido}</div><figcaption>${esc(etiqueta)}</figcaption></figure>`;
export const CSS_TEL = `
.tels{display:flex;gap:40px;justify-content:center;align-items:flex-start;padding:22px 0 0}
.tel{margin:0;display:flex;flex-direction:column;align-items:center;gap:10px}
.tel-pantalla{width:390px;height:844px;border-radius:38px;border:10px solid #1d1b19;overflow:hidden;position:relative;background:var(--paper);box-shadow:0 10px 30px rgba(0,0,0,.18)}
.tel figcaption{font-size:12px;color:var(--ink-2)}
.tel-estado{height:44px;display:flex;align-items:flex-end;justify-content:space-between;padding:0 26px 6px;font-size:13px;font-weight:600}
`;

/* The 3B harness page: a stand-in host for B's widgets and geometry loader.
 *
 * It does what INTERFACES §3–5 ask of A's host, minimally and only for tests:
 * mounts the cells and the detail controls, refreshes one terrain's summary on
 * onCambio, tears everything down on logout/expiry, and shows the CURRENT
 * PAGE (the seeded terrains) on the unchanged map with only the selected
 * terrain's boundary body loaded. State for the browser scripts is exposed as
 * window.__arnes. It is not the product.
 */

import * as api from "/lib/api.js";
import * as puente from "/__arnes/puente.js";
import * as dialogos from "/components/ui/dialog.js";
import { crearWidgetsArchivos } from "/components/archivos/index.js";
import { crearCargadorGeometrias } from "/lib/cargadorGeometrias.js";
import { createMapCanvas } from "/components/map/MapCanvas.js";

const real = typeof api.peticionPrivada === "function";
const peticionPrivada = real ? api.peticionPrivada : puente.peticionPrivada;
const terminarPrivado = real ? api.abortPrivate : puente.terminarSesionPrivada;

const terrenos = JSON.parse(decodeURIComponent(location.hash.slice(1) || "[]"));
const h = {
  puente: real ? "peticionPrivada de web/lib/api.js (C1)" : "sustituto de prueba (tests/e2e/archivos/puente.js)",
  modo: null, usuario: null, terrenos, seleccionado: null, soloLectura: false,
  cambios: [], errores: [], cargas: [], refrescos: 0, expiraciones: 0, estados: {}, descriptores: {},
  widgets: null, cargador: null, celdas: [], detalles: [],
};
window.__arnes = h;

function alExpirar() {
  h.expiraciones += 1;
  desmontar("Tu sesión terminó.");
}
if (real) api.onSessionExpired(alExpirar); else puente.alExpirarSesion(alExpirar);

const $ = (s) => document.querySelector(s);
const canvas = createMapCanvas($("#mapa"), { onSelect: (id) => seleccionar(id) });
h.canvas = canvas;

/* ---------------------------------------------------------------- session */

$("#entrar").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const datos = new FormData(evento.target);
  const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: datos.get("usuario"), password: datos.get("clave") }) });
  $("#quien").textContent = r.ok ? `Sesión: ${datos.get("usuario")}` : "No se pudo entrar";
  if (r.ok) { h.usuario = datos.get("usuario"); await montar(); }
});
$("#salir").addEventListener("click", async () => {
  desmontar("Sesión cerrada.");
  await fetch("/api/logout", { method: "POST" });
  h.usuario = null;
});

/* ------------------------------------------------------------- the host */

const pendientes = new Set();
function onCambio({ terrenoId }) {
  h.cambios.push(terrenoId);
  if (pendientes.has(terrenoId)) return;           // coalesced: one refresh per terrain per tick
  pendientes.add(terrenoId);
  queueMicrotask(() => { pendientes.delete(terrenoId); refrescar(terrenoId); });
}
function onError(e) {
  h.errores.push(e);
  if (e.codigo === "no_encontrado") refrescar(h.seleccionado);
}

async function estadoDe(id) {
  const { response } = await peticionPrivada(`/api/__arnes/terrenos/${id}/archivos-estado`);
  if (!response.ok) return { error: response.status };
  return response.json();
}

async function refrescar(id) {
  if (!h.widgets || !id) return;
  h.refrescos += 1;
  try {
    const e = await estadoDe(id);
    if (!h.widgets) return;
    if (e.error) {
      h.estados[id] = undefined;
      h.descriptores[id] = null;
    } else {
      h.modo = e.modo;
      h.estados[id] = e.resumen;
      const antes = h.descriptores[id]?.id ?? null;
      h.descriptores[id] = e.geometria;
      if (id === h.seleccionado && (e.geometria?.id ?? null) !== antes) cargarContorno(id);
    }
    for (const m of [...h.celdas, ...h.detalles]) {
      if (m.terrenoId === id) m.montado.update({ resumen: h.estados[id], soloLectura: h.soloLectura });
    }
    pintarMapa();
  } catch (error) {
    if (error?.name !== "AbortError") h.errores.push({ codigo: "harness", mensaje: String(error) });
  }
}

async function montar() {
  desmontar("");
  h.widgets = crearWidgetsArchivos({ peticionPrivada });
  h.cargador = crearCargadorGeometrias({ peticionPrivada });
  const tabla = $("#tabla");
  for (const t of terrenos) {
    const pdf = document.createElement("span");
    const kmz = document.createElement("span");
    const boton = Object.assign(document.createElement("button"), { type: "button", className: "btn btn-quiet btn-small" });
    boton.textContent = t.nombre;
    boton.dataset.id = t.id;
    boton.addEventListener("click", () => seleccionar(t.id));
    const fila = Object.assign(document.createElement("div"), { className: "fila" });
    fila.dataset.id = t.id;
    pdf.dataset.celda = "pdf";
    kmz.dataset.celda = "kmz";
    fila.append(boton, pdf, kmz);
    tabla.append(fila);
    for (const [container, tipo] of [[pdf, "pdf"], [kmz, "kmz"]]) {
      h.celdas.push({ terrenoId: t.id, tipo, montado: h.widgets.mount({ container, terrenoId: t.id, tipo,
        soloLectura: h.soloLectura, resumen: undefined, onCambio, onError }) });
    }
  }
  const modo = await (await fetch("/api/__arnes/modo")).json().catch(() => ({}));
  h.modo = modo.modo ?? null;
  $("#modo").textContent = `Modo del servidor: ${h.modo}. Transporte: ${h.puente}.`;
  await Promise.all(terrenos.map((t) => refrescar(t.id)));
  if (terrenos[0]) seleccionar(terrenos[0].id);
}

function desmontar(texto) {
  terminarPrivado();                         // cancel everything private in flight
  for (const m of [...h.celdas, ...h.detalles]) m.montado.destroy();
  h.celdas = [];
  h.detalles = [];
  h.widgets?.destroy();
  h.widgets = null;
  h.cargador?.destroy();
  h.cargador = null;
  dialogos.closeAllDialogs?.();
  h.estados = {};
  h.descriptores = {};
  h.seleccionado = null;
  $("#tabla").replaceChildren();
  $("#detalles").replaceChildren();
  canvas.render([]);
  $("#aviso-mapa").textContent = texto;
}

function seleccionar(id) {
  if (!h.widgets || id === h.seleccionado) return;
  h.seleccionado = id;
  for (const m of h.detalles) m.montado.destroy();
  h.detalles = [];
  const detalles = $("#detalles");
  detalles.replaceChildren();
  for (const tipo of ["pdf", "kmz"]) {
    const container = document.createElement("div");
    container.dataset.detalle = tipo;
    detalles.append(container);
    h.detalles.push({ terrenoId: id, tipo, montado: h.widgets.mountDetalle({ container, terrenoId: id, tipo,
      soloLectura: h.soloLectura, resumen: h.estados[id], onCambio, onError }) });
  }
  for (const b of document.querySelectorAll(".fila button")) b.setAttribute("aria-pressed", String(b.dataset.id === id));
  cargarContorno(id);
}

h.ponerSoloLectura = (valor) => {
  h.soloLectura = Boolean(valor);
  for (const m of [...h.celdas, ...h.detalles]) m.montado.update({ soloLectura: h.soloLectura });
};

/* ---------------------------------------------- map: current page only */

let cuerpoSeleccionado = null;     // {descriptorId, cuerpo}: at most one body handed to the renderer

function filas() {
  return terrenos.map((t) => ({ id: t.id, terreno: t.nombre, lat: t.lat, lon: t.lon,
    geometria: h.descriptores[t.id] ?? null }));
}

function pintarMapa() {
  const geometrias = new Map();
  const d = h.descriptores[h.seleccionado];
  if (cuerpoSeleccionado && d && cuerpoSeleccionado.descriptorId === d.id) geometrias.set(d.id, cuerpoSeleccionado.cuerpo);
  else cuerpoSeleccionado = null;
  const colocados = canvas.render(filas(), { colorFor: () => "#2a78d6", geometrias });
  h.ultimoRender = { colocados, cuerpos: geometrias.size };
  return colocados;
}

async function cargarContorno(id) {
  if (!h.cargador) return;
  const d = h.descriptores[id];
  cuerpoSeleccionado = null;
  pintarMapa();
  const pagina = `Página actual: ${terrenos.length} terrenos.`;
  if (!d) {
    $("#aviso-mapa").textContent = `${pagina} El terreno seleccionado no tiene un contorno activo.`;
    return;
  }
  $("#aviso-mapa").textContent = `${pagina} Cargando el contorno del terreno seleccionado; los demás se cargan al seleccionarlos.`;
  const registro = { id, geometria: d.id, inicio: performance.now() };
  h.cargas.push(registro);
  try {
    const cuerpo = await h.cargador.cargar({ terrenoId: id, geometria: d });
    registro.cargado = performance.now();
    if (h.seleccionado !== id || h.descriptores[id]?.id !== d.id) { registro.resultado = "obsoleto"; return; }
    cuerpoSeleccionado = { descriptorId: d.id, cuerpo };
    pintarMapa();
    canvas.fitTo(filas().filter((t) => t.id === id));
    registro.dibujado = performance.now();
    registro.resultado = "cargado";
    registro.bytes = cuerpo.bytes;
    registro.vertices = cuerpo.vertices;
    registro.sha256 = cuerpo.sha256;
    $("#aviso-mapa").textContent = `${pagina} Contorno del terreno seleccionado cargado; los demás se cargan al seleccionarlos.`;
  } catch (error) {
    registro.resultado = error?.name === "AbortError" ? "cancelado" : error?.codigo ?? "error";
    if (error?.name !== "AbortError") $("#aviso-mapa").textContent = `${pagina} ${error.message}`;
  }
}

h.refrescarTerreno = (id) => refrescar(id ?? h.seleccionado);
h.recargarContorno = (id) => { cuerpoSeleccionado = null; return cargarContorno(id ?? h.seleccionado); };
h.estadoCargador = () => h.cargador?.estado() ?? null;
document.title = "listo";

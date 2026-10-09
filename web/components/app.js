/* The application shell: routing, session, navigation and the map workspace.
 *
 * The Leaflet container is created once and kept alive across re-renders --
 * everything around it is rebuilt from state, but the map itself is not.
 *
 * Anonymous visitors get the public catalog and nothing else: startup asks
 * only for /api/config, /api/session and the public catalog. The team's
 * inventory, bases and saved maps load only after an individual sign-in, and
 * are cancelled and cleared on logout or session expiry.
 */

import { abortPrivate, api, configureApi, exportXlsx } from "../lib/api.js";
import { defaultDestination } from "../lib/carpetas.js";
import { layerColor, layerDash, priceBreaks, priceColor } from "../lib/colors.js";
import { compareLayers } from "../lib/comparar.js";
import { append, clear, el } from "../lib/dom.js";
import { activeCount, applyFilters, EMPTY_FILTERS, sinFiltrosDePrecio } from "../lib/filters.js";
import { fmtCount, monedasDe, plural } from "../lib/format.js";
import { ubicacionDe } from "../lib/geometria.js";
import {
  contarFiltros, FILTROS_VACIOS, itemDeInventario, itemPublico, opcionesDeFacetas,
} from "../lib/inventario.js";
import {
  defaultRoute, isPrivateRoute, navigate, parseRoute, routeAllowed, routeHash, sameRoute,
} from "../lib/router.js";
import {
  clearPrivateState, getState, resetFilters, setDataset, setFilter, setState, subscribe,
} from "../lib/store.js";
import { appendWorkbook, importWorkbook } from "./bases/ImportDialog.js";
import { BaseGallery } from "./bases/BaseGallery.js";
import { BasemapSwitcher } from "./map/BasemapSwitcher.js";
import {
  createFolder, deleteFolder, loadCarpetas, moveItem, renameFolder, selectFolder,
} from "./folders/folderActions.js";
import { createMapCanvas } from "./map/MapCanvas.js";
import { Legend, escalaTexto } from "./map/Legend.js";
import { openFormatManager } from "./import/FormatManager.js";
import {
  cancelarCargas, cargar, cargarDetalle, pedirCarga, reemplazarRegistro,
} from "./inventory/datasets.js";
import { InventoryDetail } from "./inventory/InventoryDetail.js";
import { DatosToolbar, MensajeDatos, segment } from "./inventory/DatosView.js";
import { createTerrainEditor } from "./inventory/TerrainEditor.js";
import { DetailMessage, PublicTerrainDetail } from "./inventory/TerrainFacts.js";
import { openTerrainHistory } from "./inventory/TerrainHistory.js";
import { MapGallery } from "./maps/MapGallery.js";
import { openOverlayBuilder, openSaveMapDialog } from "./maps/OverlayBuilder.js";
import { createSession } from "./session/session.js";
import { createTabla } from "./tabla/Tabla.js";
import { createFilterRail } from "./terrain/FilterRail.js";
import { openFiltersDrawer } from "./terrain/FiltersDrawer.js";
import { TerrainDetail } from "./terrain/TerrainDetail.js";
import { TerrainTable } from "./terrain/TerrainTable.js";
import { UnplacedList } from "./terrain/UnplacedList.js";
import { closeAllDialogs, confirmDialog, openDialog } from "./ui/dialog.js";
import { clearToasts, toast, toastError } from "./ui/toast.js";

/* Operators get the table of their work bases and the public catalog. The
 * unscoped inventory and the legacy workspace are the administrators'. */
const NAV_OPERADOR = [["tabla", "Tabla"], ["catalogo", "Catálogo público"]];
const NAV_EQUIPO = [
  ["tabla", "Tabla maestra"],
  ["inventario", "Inventario"],
  ["mapa", "Mapa"],
  ["bases", "Bases"],
  ["mapas", "Mapas guardados"],
  ["catalogo", "Catálogo público"],
];
const NAV_PUBLICO = [["catalogo", "Catálogo"]];
const REVALIDAR_MS = 10_000;   // focus/visibility revalidation, at most this often

let canvas = null;          // the Leaflet wrapper, created on first map render
let mapHost = null;         // its persistent container element
let unplacedOpen = false;
let escalaActual = null;   // { aEscala, total, zoom }
let tableSort = { campo: "orden", direccion: "asc" };
const SORT_COMPARACION = { campo: "cambio", direccion: "asc" };

let readOnly = true;        // legacy workspace actions: signed in only
let configReadOnly = false;
let cloud = false;

let session = null;
let tabla = null;           // the employee table of the signed-in account, kept alive
let tablaDe = null;         // "id|rol" of the account that table belongs to
let editor = null;          // the open TerrainEditor, kept alive across renders
let editorEstado = null;    // { id, error } while an editor loads or failed to
let legacyCargado = false;  // bases/maps/folders loaded for this session
let itemsActuales = [];     // what the map currently shows, for selection lookups
const encuadrado = { catalogo: false, inventario: false };
let ultimaRevalidacion = 0;

export async function mount(root) {
  try {
    const config = await api.config();
    configReadOnly = config.readOnly === true;
    cloud = config.cloud === true;
    configureApi(config);
  } catch (error) {
    root.textContent = `No se pudo cargar la aplicación: ${error.message}`;
    return;
  }
  const header = el("header", { class: "app-header" });
  const main = el("main", { class: "app-main", id: "vista" });
  root.append(header, main);

  subscribe(() => {
    renderHeader(header);
    renderView(main);
  });

  // Escape closes the detail panel. Native <dialog> handles its own Escape and
  // stops the event, so this only ever fires when no dialog is open.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const { ruta, seleccionado } = getState();
    if ((ruta.nombre === "catalogo" || ruta.nombre === "inventario") && ruta.id) {
      navigate({ nombre: ruta.nombre }, { replace: true });
    } else if (ruta.nombre === "mapa" && seleccionado != null) {
      setState({ seleccionado: null });
    }
  });

  session = createSession({
    onSignedIn: alEntrar,
    onSignedOut: limpiarPrivado,
    hasUnsavedWork: () => Boolean(editor?.dirty || tabla?.dirty),
  });

  window.addEventListener("hashchange", aplicarRuta);
  window.addEventListener("beforeunload", (event) => {
    if (editor?.dirty || tabla?.dirty) { event.preventDefault(); event.returnValue = ""; }
  });
  // An open public page catches up when it is looked at again; nothing polls.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") revalidar();
  });
  window.addEventListener("focus", revalidar);
  window.addEventListener("pageshow", (event) => { if (event.persisted) revalidar({ forzar: true }); });

  renderHeader(header);
  renderView(main);
  await session.refresh();
  ultimaRevalidacion = Date.now();
  aplicarRuta();
}

/* ---------------------------------------------------------------- session */

function alEntrar(usuario, { returnTo, startup }) {
  // A table left by another account (it signed in over an expired session
  // that had unsaved cells) is never shown to this one.
  if (tabla && tablaDe !== `${usuario.id}|${usuario.rol}`) {
    const habia = tabla.dirty;
    cerrarTabla();
    if (habia) toast("Se descartó trabajo sin guardar de la sesión anterior.");
  }
  if (usuario.rol === "admin") loadIndex();
  // /api/config's readOnly depends on the session, so it is read again now.
  if (startup) { readOnly = configReadOnly; return; }
  api.config().then((config) => { readOnly = config.readOnly === true; setState({}); tabla?.permisos(); })
    .catch(() => { readOnly = false; tabla?.permisos(); });
  const destino = returnTo && routeAllowed(returnTo, usuario.rol) ? returnTo : defaultRoute(true, usuario.rol);
  if (!navigate(destino, { replace: true })) aplicarRuta();
}

function cerrarTabla() {
  tabla?.destroy();
  tabla = null;
  tablaDe = null;
}

/**
 * Forget the session's private data: cancel its requests, close what shows
 * it, and reset its state. The public catalog stays.
 */
function limpiarPrivado() {
  abortPrivate();
  cancelarCargas();
  cerrarTabla();
  editor?.destroy();
  editor = null;
  editorEstado = null;
  closeAllDialogs();   // removed, not only closed: a detail or a history holds private text
  clearToasts();
  if (workspace) {
    for (const modo of ["inventario", "local"]) {
      workspace.rails[modo]?.destroy();
      delete workspace.rails[modo];
    }
    workspace.detailSlot.replaceChildren();
    workspace.tableSlot.replaceChildren();
    canvas?.render([], { colorFor: () => "" });
  }
  itemsActuales = [];
  readOnly = true;
  legacyCargado = false;
  encuadrado.inventario = false;
  tableSort = { campo: "orden", direccion: "asc" };
  clearPrivateState();
  if (isPrivateRoute(getState().ruta)) setState({ ruta: defaultRoute(false) });
  navigate(defaultRoute(false), { replace: true });
}

/* The legacy workspace's lists: signed in only, never at anonymous startup. */
async function loadIndex({ forzar = false } = {}) {
  if (legacyCargado && !forzar) return;
  legacyCargado = true;
  try {
    // Folders load alongside and report their own failure, so a folder
    // problem never hides the bases and maps themselves.
    const [{ bases }, { mapas }] = await Promise.all([
      api.bases(), api.mapas(), loadCarpetas("bases"), loadCarpetas("mapas"),
    ]);
    setState({ bases, mapas });
  } catch (error) {
    legacyCargado = false;
    if (error.status !== 401) toastError(`No se pudieron cargar las bases y los mapas: ${error.message}`);
  }
}

async function cerrarSesion() {
  if ((editor?.dirty || tabla?.dirty) && !(await confirmarDescarte())) return;
  session.signOut();
}

const confirmarDescarte = () => confirmDialog({
  titulo: "¿Descartar cambios?",
  mensaje: "Tienes cambios sin guardar. Si sales ahora, se pierden.",
  confirmar: "Descartar cambios",
  peligro: true,
});

async function revalidar({ forzar = false } = {}) {
  if (!session || (!forzar && Date.now() - ultimaRevalidacion < REVALIDAR_MS)) return;
  ultimaRevalidacion = Date.now();
  await session.refresh();
  const { ruta, sesion } = getState();
  // Another account, or another role for this one, since the table was built.
  if (tabla && sesion && tablaDe !== `${sesion.id}|${sesion.rol}`) {
    cerrarTabla();
    aplicarRuta();
    return;
  }
  if (ruta.nombre === "tabla") tabla?.revalidar();
  else if (ruta.nombre === "catalogo") pedirCarga("catalogo", { inmediato: true });
  else if (ruta.nombre === "inventario" && sesion) pedirCarga("inventario", { inmediato: true });
}

/* ---------------------------------------------------------------- routing */

const rutaDelEditor = () => (editor?.id ? { nombre: "editar", id: editor.id } : { nombre: "nuevo" });

async function aplicarRuta() {
  const ruta = parseRoute(location.hash);
  const { sesion } = getState();
  if (!ruta) {
    if (!navigate(defaultRoute(Boolean(sesion), sesion?.rol), { replace: true })) aplicarRuta();
    return;
  }
  // An operator who follows a link into the administrators' screens lands on the table.
  if (sesion && !routeAllowed(ruta, sesion.rol)) {
    navigate(defaultRoute(true, sesion.rol), { replace: true });
    return;
  }

  // Leaving an editor with unsaved input asks first; staying puts the URL back.
  if (editor && !sameRoute(ruta, rutaDelEditor())) {
    if (editor.dirty && !(await confirmarDescarte())) {
      navigate(rutaDelEditor());
      return;
    }
    editor.destroy();
    editor = null;
  }

  if (isPrivateRoute(ruta) && !sesion) {
    // A private link opened without a session: offer sign-in, show nothing private.
    setState({ ruta: defaultRoute(false) });
    navigate(defaultRoute(false), { replace: true });
    session.signIn({ returnTo: ruta });
    return;
  }

  setState({ ruta, ...(ruta.nombre === "mapa" ? {} : { seleccionado: null }) });
  efectosDeRuta(ruta);
}

function efectosDeRuta(ruta) {
  const state = getState();
  if (ruta.nombre === "catalogo" || ruta.nombre === "inventario") {
    if (!state[ruta.nombre].cargado && !state[ruta.nombre].cargando) cargar(ruta.nombre);
    if (ruta.id) cargarDetalle(ruta.nombre, ruta.id);
    else if (state.detalle) setState({ detalle: null });
  } else if (ruta.nombre === "tabla") {
    abrirTabla(ruta);
  } else if (ruta.nombre === "editar" || ruta.nombre === "nuevo") {
    if (!editor) abrirEditor(ruta);
  } else if (ruta.nombre === "mapa" && !state.baseActiva && !state.mapaActivo) {
    navigate({ nombre: "bases" }, { replace: true });
  } else if (ruta.nombre === "bases" || ruta.nombre === "mapas") {
    // Other team members add bases and maps too: revalidate on entry.
    loadIndex({ forzar: true });
  }
}

/* ------------------------------------------------------------------ table */

function abrirTabla(ruta) {
  const { sesion } = getState();
  if (!sesion) return;
  if (tabla) { tabla.abrir(ruta.id); return; }
  tablaDe = `${sesion.id}|${sesion.rol}`;
  tabla = createTabla({
    sesion, soloConsulta: () => readOnly, vistaInicial: ruta.id,
    // The table says which view it ended up showing; the address follows it.
    onVista: (vista) => {
      if (getState().ruta.nombre === "tabla") navigate({ nombre: "tabla", id: vista }, { replace: true });
    },
    // The server refused something the role allowed a moment ago: ask who we are now.
    onPermisos: async () => {
      cerrarTabla();
      await session.refresh();
      if (getState().sesion) aplicarRuta();
    },
  });
  setState({});
}

function renderTabla(host) {
  if (tabla) {
    if (tabla.element.parentNode !== host) clear(host).append(tabla.element);
    return;
  }
  clear(host).append(el("div", { class: "screen" }, el("p", { class: "secondary", role: "status" }, "Cargando…")));
}

/* ----------------------------------------------------------------- editor */

async function abrirEditor(ruta) {
  if (ruta.nombre === "nuevo") {
    editor = crearEditor(null);
    editorEstado = null;
    setState({});
    editor.focus();
    return;
  }
  editorEstado = { id: ruta.id, error: null };
  setState({});
  try {
    const { terreno } = await api.inventarioTerreno(ruta.id);
    if (!sameRoute(getState().ruta, ruta) || editor) return;
    editor = crearEditor(terreno);
    editorEstado = null;
    setState({});
    editor.focus();
  } catch (error) {
    if (!sameRoute(getState().ruta, ruta)) return;
    editorEstado = {
      id: ruta.id,
      error: error.status === 404 ? "Este terreno no existe en el inventario." : error.message,
    };
    setState({});
  }
}

function crearEditor(terreno) {
  return createTerrainEditor({
    terreno,
    onClose: () => navigate(editor?.id ? { nombre: "inventario", id: editor.id } : { nombre: "inventario" }),
    onHistory: (t) => openTerrainHistory({ id: t.id, nombre: t.draft?.terreno }),
    onSaved: (guardado, { creado, sucio }) => {
      reemplazarRegistro(guardado);
      pedirCarga("inventario", { inmediato: true });   // revalidate after a write
      const revision = guardado.draft_revision_id ? ` · revisión ${String(guardado.draft_revision_id).slice(0, 8)}` : "";
      toast(creado
        ? `Borrador creado · ID ${guardado.id} · versión ${guardado.version}${revision}.`
        : `Borrador guardado · versión ${guardado.version}${revision}.`);
      // Typed something while it was saving: stay, so that is not lost.
      if (sucio) {
        if (creado) navigate({ nombre: "editar", id: guardado.id }, { replace: true });
        return;
      }
      editor?.destroy();
      editor = null;
      navigate({ nombre: "inventario", id: guardado.id }, { replace: true });
    },
  });
}

function renderEditor(host) {
  if (editor) {
    if (editor.element.parentNode !== host) clear(host).append(editor.element);
    return;
  }
  clear(host).append(el("div", { class: "screen" },
    el("div", { class: "empty-state" },
      el("h2", {}, editorEstado?.error ? "No se pudo abrir el terreno" : "Cargando el terreno…"),
      editorEstado?.error && el("p", { class: "secondary" }, editorEstado.error),
      editorEstado?.error && el("a", { class: "btn btn-quiet", href: routeHash({ nombre: "inventario" }) },
        "Volver al inventario"),
    )));
}

/* ---------------------------------------------------------------- header */

let headerClave = null;

function renderHeader(host) {
  const { ruta, sesion, sesionLista, baseActiva, mapaActivo } = getState();
  const admin = sesion?.rol === "admin";
  const activa = ruta.nombre === "editar" || ruta.nombre === "nuevo" ? "inventario" : ruta.nombre;
  const legacyAbierto = Boolean(baseActiva || mapaActivo);
  // Rebuilding the header on every keystroke is wasted work and a focus hazard
  // for anything inside it, so it is rebuilt only when what it shows changes.
  const clave = [activa, sesion?.id, sesion?.display_name, sesion?.rol, sesionLista, legacyAbierto].join("|");
  if (headerClave === clave && host.childElementCount) return;
  headerClave = clave;

  const items = (!sesion ? NAV_PUBLICO : admin ? NAV_EQUIPO : NAV_OPERADOR)
    .filter(([key]) => key !== "mapa" || legacyAbierto);

  // append() skips the false of the conditional pieces; the native
  // Element.append would print it as text.
  append(clear(host), [
    el("div", { class: "brand" },
      // Decorative: the name sits right beside it, so an alt text would make a
      // screen reader announce the brand twice. Intrinsic size is declared to
      // keep the header from shifting while the image loads.
      el("img", {
        class: "brand-logo",
        src: "assets/ara-logo.png",
        alt: "",
        width: "522",
        height: "478",
        decoding: "async",
      }),
      el("span", { class: "brand-name" }, "ARA Map"),
      cloud && sesion && el("span", { class: "chip" }, "Espacio compartido"),
    ),
    el("nav", { class: "nav", "aria-label": "Secciones" },
      items.map(([key, etiqueta]) =>
        el("a", {
          class: ["nav-item", key === activa && "is-active"],
          href: routeHash({ nombre: key }),
          "aria-current": key === activa ? "page" : null,
        }, etiqueta)
      )
    ),
    sesionLista && el("div", { class: "session" },
      sesion && el("span", { class: "session-user truncate", title: `Sesión de ${sesion.display_name}` },
        sesion.display_name),
      el("button", {
        type: "button", class: "btn btn-quiet",
        onclick: sesion ? cerrarSesion : () => session.signIn({ returnTo: null }),
      }, sesion ? "Cerrar sesión" : "Iniciar sesión"),
    ),
  ]);
}

/* ------------------------------------------------------------------ views */

function renderView(host) {
  const state = getState();
  if (!state.sesionLista) {
    clear(host).append(el("div", { class: "screen" },
      el("p", { class: "secondary", role: "status" }, "Cargando…")));
    return undefined;
  }
  switch (state.ruta.nombre) {
    case "tabla": return renderTabla(host);
    case "bases": return renderBases(host, state);
    case "mapas": return renderMapas(host, state);
    case "editar":
    case "nuevo": return renderEditor(host);
    case "mapa": return renderMapa(host, state);
    case "inventario": return renderDatos(host, state, "inventario");
    default: return renderDatos(host, state, "catalogo");
  }
}

/* The folder props both galleries share, for one dashboard. */
function folderProps(tipo, state) {
  return {
    carpetas: state.carpetas[tipo],
    seleccion: state.carpetaVista[tipo],
    carpetasError: state.carpetasError[tipo],
    onMove: (item) => moveItem(tipo, item),
    onSelectFolder: (seleccion) => selectFolder(tipo, seleccion),
    onCreateFolder: () => createFolder(tipo),
    onRenameFolder: (carpeta) => renameFolder(tipo, carpeta),
    onDeleteFolder: (carpeta) => deleteFolder(tipo, carpeta),
    onRetryFolders: () => loadCarpetas(tipo),
  };
}

/* Galleries are rebuilt on every state change. An element that had focus
 * and carries an id (the folder heading, say) gets it back afterwards, so a
 * background update cannot drop keyboard focus onto the page body. */
function renderKeepingFocus(host, build) {
  const active = document.activeElement;
  const id = active && host.contains(active) ? active.id : "";
  clear(host).append(build());
  if (id) document.getElementById(id)?.focus();
}

/* The toolbar is rebuilt on every change (a reload, a page arriving); a
 * focused control with an id is focused again, so keyboard users keep place. */
function replaceKeepingFocus(host, children) {
  const active = document.activeElement;
  const id = active && host.contains(active) ? active.id : "";
  host.replaceChildren(...children);
  if (id) document.getElementById(id)?.focus();
}

function renderBases(host, state) {
  renderKeepingFocus(host, () => BaseGallery({
    readOnly,
    bases: state.bases,
    ...folderProps("bases", state),
    onImport: () => importWorkbook({
      onDone: afterBaseChange,
      carpetas: state.carpetas.bases,
      carpetaInicial: defaultDestination(state.carpetaVista.bases),
    }),
    onOpen: (base) => openBase(base),
    onAppend: (base) => appendWorkbook(base, { onDone: afterBaseChange }),
    onFormats: () => openFormatManager(),
    onRename: (base) => renameBase(base),
    onDelete: (base) => deleteBase(base),
  }));
}

function renderMapas(host, state) {
  renderKeepingFocus(host, () => MapGallery({
    readOnly,
    mapas: state.mapas,
    bases: state.bases,
    ...folderProps("mapas", state),
    onOpen: (mapa) => openMapa(mapa),
    onRename: (mapa) => renameMapa(mapa),
    onDelete: (mapa) => deleteMapa(mapa),
    // The complete collections, never the open folder's subset.
    onCompare: () => openOverlayBuilder({
      mapas: state.mapas,
      bases: state.bases,
      carpetasMapas: state.carpetas.mapas,
      carpetasBases: state.carpetas.bases,
      carpetaInicial: defaultDestination(state.carpetaVista.mapas),
      basemap: state.basemap,
      onCreated: async (mapa) => {
        const { mapas } = await api.mapas();
        setState({ mapas });
        openMapa(mapa);
      },
    }),
  }));
}

/* ------------------------------------------------------------- map screen */

/* The map workspace is built once and kept. Rebuilding it on every state
 * change is what destroyed the focused search box after each character, and it
 * also threw away Leaflet's markers between a click and its double-click. */
let workspace = null;

function ensureWorkspace() {
  if (workspace) return workspace;

  mapHost = el("div", { class: "map-host", id: "map-host" });

  const toolbar = el("div", { class: "toolbar" });
  const overlays = el("div", { class: "stage-overlays" });
  const mensaje = el("div", { class: "stage-mensaje-slot" });
  const unplacedSlot = el("div", { class: "unplaced-slot" });
  const tableSlot = el("div", { class: "table-slot" });
  const stage = el("div", { class: "stage" }, mapHost, tableSlot, overlays, mensaje, unplacedSlot);

  const railSlot = el("div", { class: "rail-slot" });
  const detailSlot = el("div", { class: "detail-slot" });
  const root = el("div", { class: "workspace" },
    railSlot,
    el("div", { class: "stage-slot" }, toolbar, stage),
  );

  workspace = {
    root, rails: {}, railSlot, toolbar, overlays, mensaje, unplacedSlot, tableSlot, detailSlot,
  };
  return workspace;
}

/* One persistent rail per context: a legacy base ("local"), the catalog and
 * the inventory each keep their own typed values and checked boxes. */
function usarRail(modo) {
  const ws = ensureWorkspace();
  if (!ws.rails[modo]) {
    ws.rails[modo] = modo === "local"
      ? createFilterRail({ onChange: (patch) => setFilter(patch), onReset: () => resetFilters() })
      : createFilterRail({
        modo,
        onChange: (patch) => {
          setDataset(modo, { filtros: { ...getState()[modo].filtros, ...patch } });
          pedirCarga(modo);
        },
        onReset: () => {
          setDataset(modo, { filtros: FILTROS_VACIOS });
          pedirCarga(modo, { inmediato: true });
        },
      });
  }
  const rail = ws.rails[modo];
  // While the phone drawer holds the rail, it stays there.
  if (!rail.element.closest("dialog") && rail.element.parentNode !== ws.railSlot) {
    ws.railSlot.replaceChildren(rail.element);
  }
  return rail;
}

function abrirFiltros(modo) {
  const ws = ensureWorkspace();
  openFiltersDrawer({
    rail: usarRail(modo),
    slot: ws.railSlot,
    onClosed: () => {
      document.getElementById("filtros-btn")?.focus();
      canvas?.invalidate();
    },
  });
}

/* Shown only below 960px, where the rail itself is hidden. */
const FiltrosBoton = (modo, activos) => el("button", {
  type: "button", id: "filtros-btn", class: "btn btn-quiet filtros-btn", "aria-haspopup": "dialog",
  onclick: () => abrirFiltros(modo),
}, activos ? `Filtros (${activos})` : "Filtros");

/* ------------------------------------------------- catalog and inventory */

/* An internal row is located by its active boundary or by valid X/Y
 * (geometria.js ubicacionDe); `ubicacion` stays the X/Y diagnostic. */
function filaInterna(registro) {
  const fila = itemDeInventario(registro);
  return { ...fila, ubicado: ubicacionDe(fila).ubicado };
}

/* Rows are derived once per assembled result, not on every render. */
const itemsCache = new WeakMap();
function itemsDe(tipo, datos) {
  if (!itemsCache.has(datos.registros)) {
    itemsCache.set(datos.registros,
      datos.registros.map(tipo === "catalogo" ? itemPublico : filaInterna));
  }
  return itemsCache.get(datos.registros);
}

function renderDatos(host, state, tipo) {
  const datos = state[tipo];
  const items = itemsDe(tipo, datos);
  itemsActuales = items;
  const monedas = monedasDe(items);
  const preciosComparables = monedas.length <= 1;
  const sinUbicacion = items.filter((t) => !t.ubicado);
  const breaks = preciosComparables ? priceBreaks(items.map((t) => t.asking_m2)) : null;
  const seleccionado = state.ruta.id;

  const ws = ensureWorkspace();
  if (ws.root.parentNode !== host) clear(host).append(ws.root);

  usarRail(tipo).update({
    terrenos: items,
    filtros: datos.filtros,
    visibles: items.length,
    monedas,
    opciones: opcionesDeFacetas(datos.facets),
    cargando: datos.cargando,
  });

  replaceKeepingFocus(ws.toolbar, DatosToolbar({
    tipo, datos, items, panel: state.panel,
    filtros: FiltrosBoton(tipo, contarFiltros(datos.filtros, tipo)),
    onPanel: (panel) => setState({ panel }),
    onEncuadrar: () => canvas?.fitTo(items),
  }));

  ws.tableSlot.replaceChildren(
    ...(state.panel === "tabla"
      ? [el("div", { class: "table-panel" },
          TerrainTable({
            terrenos: items,
            orden: tableSort.campo,
            direccion: tableSort.direccion,
            seleccionado,
            preciosComparables,
            onSort: ordenarTabla,
            onSelect: (id) => selectTerreno(id, { pan: true }),
          })
        )]
      : [])
  );

  ws.overlays.replaceChildren(
    ...(state.panel === "mapa"
      ? [
          Legend({
            modo: "precio",
            capas: [],
            breaks,
            monedas,
            conteo: items.length - sinUbicacion.length,
            sinUbicacion: sinUbicacion.length,
            invalidas: sinUbicacion.filter((t) => t.ubicacion === "invalida").length,
            escala: escalaActual,
          }),
          BasemapSwitcher({ activo: state.basemap, onChange: changeBasemap }),
        ]
      : [])
  );

  const mensaje = state.panel === "mapa" && MensajeDatos({
    tipo, datos, items,
    onRetry: () => cargar(tipo),
    onClear: () => { setDataset(tipo, { filtros: FILTROS_VACIOS }); pedirCarga(tipo, { inmediato: true }); },
  });
  ws.mensaje.replaceChildren(...(mensaje ? [mensaje] : []));

  ws.unplacedSlot.replaceChildren(
    ...(state.panel === "mapa"
      ? [UnplacedList({
          terrenos: sinUbicacion,
          seleccionado,
          abierto: unplacedOpen,
          instruccion: tipo === "inventario"
            ? "Ábrelo y escribe su latitud (X) y longitud (Y) en «Editar»; no hace falta volver a importar."
            : null,
          onSelect: (id) => selectTerreno(id),
          onToggle: () => { unplacedOpen = !unplacedOpen; setState({}); },
        })]
      : [])
  );

  const panel = seleccionado ? DetalleDatos(tipo, state, items, seleccionado) : null;
  if (panel) {
    ws.detailSlot.replaceChildren(panel);
    if (ws.detailSlot.parentNode !== ws.root) ws.root.append(ws.detailSlot);
  } else {
    ws.detailSlot.remove();
  }

  const encuadrar = datos.cargado && !datos.cargando && !encuadrado[tipo];
  if (encuadrar) encuadrado[tipo] = true;
  drawMap({ basemap: state.basemap, capas: [], modoColor: "precio", seleccionado }, items, breaks, { encuadrar });
}

function DetalleDatos(tipo, state, items, id) {
  const cerrar = () => navigate({ nombre: tipo }, { replace: true });
  const { detalle } = state;
  const fresco = detalle?.tipo === tipo && detalle.id === id ? detalle : null;
  const item = items.find((t) => t.id === id);
  const terreno = fresco?.terreno ?? (item ? (tipo === "inventario" ? item.registro : item) : null);

  if (!terreno) {
    return fresco?.error
      ? DetailMessage({ titulo: "Terreno no disponible", mensaje: fresco.error, onClose: cerrar,
        onRetry: () => cargarDetalle(tipo, id) })
      : DetailMessage({ titulo: "Cargando…", mensaje: "Cargando el terreno…", onClose: cerrar });
  }
  if (tipo === "catalogo") {
    return PublicTerrainDetail({ terreno, onZoomAEscala: () => zoomTerrenoAEscala(id), onClose: cerrar });
  }
  return InventoryDetail({
    terreno,
    onEdit: () => navigate({ nombre: "editar", id }),
    onHistory: () => openTerrainHistory({ id, nombre: terreno.draft?.terreno }),
    onZoomAEscala: () => zoomTerrenoAEscala(id),
    onClose: cerrar,
  });
}

function ordenarTabla(campo) {
  tableSort = campo === tableSort.campo
    ? { campo, direccion: tableSort.direccion === "asc" ? "desc" : "asc" }
    : { campo, direccion: "asc" };
  setState({});
}

function renderMapa(host, state) {
  if (!state.terrenos.length && !state.baseActiva && !state.mapaActivo) {
    clear(host).append(el("div", { class: "screen" },
      el("div", { class: "empty-state" },
        el("h2", {}, "Nada que mostrar todavía"),
        el("p", { class: "secondary" },
          readOnly ? "Todavía no hay terrenos publicados." : "Importa una base de terrenos para verla en el mapa."),
        !readOnly && el("button", {
          type: "button", class: "btn btn-principal",
          onclick: () => importWorkbook({
            onDone: afterBaseChange, carpetas: getState().carpetas.bases,
          }),
        }, "Importar archivo"),
      )));
    return;
  }

  const visibles = visibleTerrenos(state);
  // Prices in more than one currency (or with an unrecorded one) share no
  // scale: no common colour bands, price filters or price sorting. Location
  // and everything else still compare normally.
  const monedas = monedasDe(visibles);
  const preciosComparables = monedas.length <= 1;
  const filtrados = applyFilters(visibles,
    preciosComparables ? state.filtros : sinFiltrosDePrecio(state.filtros));
  const ubicados = filtrados.filter((t) => t.ubicado);
  const sinUbicacion = filtrados.filter((t) => !t.ubicado);
  const breaks = preciosComparables ? priceBreaks(visibles.map((t) => t.asking_m2)) : null;
  const seleccionado = filtrados.find((t) => t.id === state.seleccionado) ?? null;

  itemsActuales = state.terrenos;
  const ws = ensureWorkspace();
  if (ws.root.parentNode !== host) clear(host).append(ws.root);
  ws.mensaje.replaceChildren();

  usarRail("local").update({
    terrenos: visibles,
    filtros: state.filtros,
    visibles: filtrados.length,
    monedas,
  });

  replaceKeepingFocus(ws.toolbar, MapToolbar(state, filtrados));

  ws.tableSlot.replaceChildren(
    ...(state.panel === "tabla"
      ? [el("div", { class: "table-panel" },
          TerrainTable({
            terrenos: filtrados,
            orden: tableSort.campo,
            direccion: tableSort.direccion,
            seleccionado: state.seleccionado,
            comparando: state.capas.length > 1,
            preciosComparables,
            onSort: ordenarTabla,
            onSelect: (id) => selectTerreno(id, { pan: true }),
          })
        )]
      : [])
  );

  // The table covers the map entirely, so the map's own furniture is not drawn
  // behind it -- it would otherwise float over the rows.
  ws.overlays.replaceChildren(
    ...(state.panel === "mapa"
      ? [
          Legend({
            modo: state.modoColor,
            capas: state.capas,
            breaks,
            monedas,
            conteo: ubicados.length,
            sinUbicacion: sinUbicacion.length,
            invalidas: sinUbicacion.filter((t) => t.ubicacion === "invalida").length,
            escala: escalaActual,
            onToggleCapa: toggleCapa,
          }),
          BasemapSwitcher({ activo: state.basemap, onChange: changeBasemap }),
        ]
      : [])
  );

  ws.unplacedSlot.replaceChildren(
    ...(state.panel === "mapa"
      ? [UnplacedList({
          terrenos: sinUbicacion,
          seleccionado: state.seleccionado,
          abierto: unplacedOpen,
          onSelect: (id) => selectTerreno(id),
          onToggle: () => { unplacedOpen = !unplacedOpen; setState({}); },
        })]
      : [])
  );

  if (seleccionado) {
    ws.detailSlot.replaceChildren(TerrainDetail({
      terreno: seleccionado,
      baseNombre: baseNameFor(state, seleccionado),
      onZoomAEscala: () => zoomTerrenoAEscala(seleccionado.id),
      onClose: () => setState({ seleccionado: null }),
    }));
    if (ws.detailSlot.parentNode !== ws.root) ws.root.append(ws.detailSlot);
  } else {
    ws.detailSlot.remove();
  }

  drawMap(state, filtrados, breaks);
}

/** The toolbar's children. The toolbar element itself persists. */
function MapToolbar(state, filtrados) {
  const titulo = state.mapaActivo?.nombre ?? state.baseActiva?.nombre ?? "Mapa";

  return [
    el("div", { class: "toolbar-title" },
      el("span", { class: "eyebrow" },
        state.mapaActivo ? (state.mapaActivo.tipo === "comparacion" ? "Comparación" : "Mapa guardado") : "Base"),
      el("h1", { class: "truncate", title: titulo }, titulo),
    ),
    el("div", { class: "toolbar-actions" },
      FiltrosBoton("local", activeCount(state.filtros)),
      state.capas.length > 1 && el("div", { class: "segmented", role: "group", "aria-label": "Colorear por" },
        segment("Por base", state.modoColor === "base", () => setState({ modoColor: "base" })),
        segment("Por precio", state.modoColor === "precio", () => setState({ modoColor: "precio" })),
      ),
      el("div", { class: "segmented", role: "group", "aria-label": "Vista" },
        segment("Mapa", state.panel === "mapa", () => setState({ panel: "mapa" })),
        segment("Tabla", state.panel === "tabla", () => setState({ panel: "tabla" })),
      ),
      el("button", {
        type: "button", class: "btn btn-quiet",
        onclick: () => canvas?.fitTo(filtrados),
      }, "Encuadrar"),
      el("button", {
        type: "button", class: "btn btn-quiet",
        onclick: () => exportar(state, filtrados),
      }, "Exportar"),
      !readOnly && state.mapaActivo && el("button", {
        type: "button", class: "btn btn-quiet",
        title: "Vuelve a copiar los terrenos desde las bases de origen",
        onclick: () => actualizarMapa(state.mapaActivo),
      }, "Actualizar"),
      !readOnly && state.mapaActivo && el("button", {
        type: "button", class: "btn btn-quiet",
        title: "Guarda los filtros, el mapa base y la vista actual en este mapa",
        onclick: () => guardarVista(state),
      }, "Guardar vista"),
      !readOnly && state.baseActiva && !state.mapaActivo && el("button", {
        type: "button", class: "btn btn-principal",
        onclick: () => openSaveMapDialog({
          base: state.baseActiva,
          carpetas: getState().carpetas.mapas,
          basemap: state.basemap,
          modoColor: state.modoColor,
          vista: vistaActual(state),
          onCreated: async () => {
            const { mapas } = await api.mapas();
            setState({ mapas });
          },
        }),
      }, "Guardar como mapa"),
    ),
  ].filter(Boolean);
}


/* --------------------------------------------------------------- map draw */

/* `vista` is { basemap, capas, modoColor, seleccionado }; `encuadrar` frames
 * the data once, when a dataset first arrives. */
function drawMap(vista, filtrados, breaks, { encuadrar = false } = {}) {
  // The container must be in the document before Leaflet measures it.
  requestAnimationFrame(() => {
    const primeraVez = !canvas;
    if (primeraVez) {
      canvas = createMapCanvas(mapHost, {
        onSelect: (id) => selectTerreno(id),
        onDoubleSelect: (id) => zoomTerrenoAEscala(id),
        // Written straight into the legend: routing it through the store would
        // re-render the map, which would report the scale again, and so on.
        onScaleChange: (escala) => {
          escalaActual = escala;
          const nota = document.querySelector(".legend-escala");
          if (nota) nota.textContent = escalaTexto(escala);
        },
      });

      // Opt-in hook so browser tests can turn a terrain's coordinates into
      // screen pixels and send a real double click at it. It exists only when
      // asked for with ?test=1, never in normal use.
      if (new URLSearchParams(location.search).has("test")) {
        window.__araTest = {
          puntoDe(id) {
            const t = itemsActuales.find((x) => x.id === id);
            if (!t?.ubicado) return null;
            const punto = canvas.map.latLngToContainerPoint([t.lat, t.lon]);
            const caja = mapHost.getBoundingClientRect();
            return { x: caja.left + punto.x, y: caja.top + punto.y };
          },
          zoom: () => canvas.map.getZoom(),
          irA: (lat, lon, z) => canvas.setView([lat, lon], z),
        };
      }
    }
    canvas.setBasemap(vista.basemap);
    // Leaflet has to know its real size before it can frame anything, so the
    // first fit happens after the container has been measured -- otherwise it
    // frames a zero-sized viewport and lands zoomed far out.
    canvas.invalidate();
    if (primeraVez || encuadrar) canvas.fitTo(filtrados);

    const porBase = vista.modoColor === "base" && vista.capas.length > 0;
    const colores = new Map(vista.capas.map((c) => [c.orden ?? 0, c.color]));
    const indices = new Map(vista.capas.map((c, i) => [c.orden ?? 0, i]));

    canvas.render(filtrados, {
      colorFor: (t) => (porBase
        ? colores.get(t.capa ?? 0) ?? layerColor(0, vista.basemap)
        : priceColor(t.asking_m2, breaks)),
      dashFor: (t) => (porBase ? layerDash(indices.get(t.capa ?? 0) ?? 0) : null),
    });
    canvas.select(vista.seleccionado);
  });
}

/* ----------------------------------------------------------------- actions */

function visibleTerrenos(state) {
  if (!state.capas.length) return state.terrenos;
  const ocultas = new Set(
    state.capas.filter((c) => !c.visible).map((c) => c.orden ?? 0)
  );
  return ocultas.size
    ? state.terrenos.filter((t) => !ocultas.has(t.capa ?? 0))
    : state.terrenos;
}

function baseNameFor(state, terreno) {
  return terreno.base_nombre
    ?? state.capas.find((c) => (c.orden ?? 0) === (terreno.capa ?? 0))?.nombre
    ?? state.baseActiva?.nombre;
}

function selectTerreno(id, { pan = false } = {}) {
  const { ruta } = getState();
  if (ruta.nombre === "catalogo" || ruta.nombre === "inventario") {
    navigate({ nombre: ruta.nombre, id }, { replace: true });
  } else {
    setState({ seleccionado: id });
  }
  canvas?.select(id, { pan });
}

function toggleCapa(orden) {
  setState((state) => ({
    capas: state.capas.map((capa) =>
      (capa.orden ?? 0) === orden ? { ...capa, visible: !capa.visible } : capa),
  }));
}

function changeBasemap(basemap) {
  setState((state) => ({
    basemap,
    // Layer colours are stepped for the surface they sit on, so switching to
    // satellite re-steps them rather than keeping the light-surface values.
    capas: state.capas.map((capa, index) => ({ ...capa, color: layerColor(index, basemap) })),
    terrenos: state.terrenos.map((t) => ({
      ...t,
      color: layerColor(
        state.capas.findIndex((c) => (c.orden ?? 0) === (t.capa ?? 0)),
        basemap,
      ),
    })),
  }));
}

async function openBase(base, { silencioso = false } = {}) {
  try {
    setState({ cargando: true });
    const { terrenos } = await api.terrenos(base.id);
    setState({
      baseActiva: base,
      mapaActivo: null,
      terrenos: terrenos.map((t) => ({ ...t, capa: 0, base_nombre: base.nombre })),
      capas: [{
        orden: 0, base_id: base.id, nombre: base.nombre,
        color: layerColor(0, getState().basemap), visible: true,
        base_existe: true, conteo: terrenos.length,
        ubicados: terrenos.filter((t) => t.ubicado).length,
      }],
      modoColor: "precio",
      seleccionado: null,
      filtros: { ...EMPTY_FILTERS },
      cargando: false,
    });
    navigate({ nombre: "mapa" });
    canvas?.fitTo(terrenos);
    if (!silencioso) toast(`«${base.nombre}»: ${plural(terrenos.length, "terreno")}.`);
  } catch (error) {
    setState({ cargando: false });
    toastError(error.message);
  }
}

async function openMapa(mapa) {
  try {
    setState({ cargando: true });
    const payload = await api.mapaTerrenos(mapa.id);
    const config = payload.mapa.config ?? {};
    const basemap = config.basemap ?? getState().basemap;

    const capas = payload.mapa.capas.map((capa, index) => ({
      ...capa,
      color: layerColor(index, basemap),
      visible: config.capasOcultas ? !config.capasOcultas.includes(capa.orden) : true,
    }));
    const colores = new Map(capas.map((c) => [c.orden, c.color]));

    const terrenos = payload.terrenos.map((t) => ({
      ...t, color: colores.get(t.capa ?? 0),
    }));
    // A comparison also says how each terrain differs from the first layer.
    const comparados = payload.mapa.tipo === "comparacion"
      ? compareLayers(terrenos, capas)
      : terrenos;
    // A comparison opens ranked by what changed rather than by file order.
    if (payload.mapa.tipo === "comparacion") tableSort = { ...SORT_COMPARACION };

    setState({
      mapaActivo: payload.mapa,
      baseActiva: null,
      terrenos: comparados,
      capas,
      basemap,
      modoColor: payload.mapa.tipo === "comparacion"
        ? "base"
        : config.modoColor ?? "precio",
      panel: config.panel ?? "mapa",
      seleccionado: null,
      filtros: { ...EMPTY_FILTERS, ...(config.filtros ?? {}) },
      cargando: false,
    });

    navigate({ nombre: "mapa" });
    // Restore the saved viewport if there is one; otherwise frame the data.
    if (config.vista?.center && config.vista?.zoom) {
      canvas?.setView(config.vista.center, config.vista.zoom);
    } else {
      canvas?.fitTo(payload.terrenos);
    }
  } catch (error) {
    setState({ cargando: false });
    toastError(error.message);
  }
}

/**
 * Zoom until the terrain's circle covers its real area, and centre it.
 *
 * The detail panel is opened first and the map re-measured before framing,
 * because the panel takes a third of the width: framing before it lands would
 * leave the terrain sitting behind it.
 */
async function zoomTerrenoAEscala(id) {
  selectTerreno(id);
  await new Promise((listo) =>
    requestAnimationFrame(() => requestAnimationFrame(listo)));
  canvas?.invalidate();

  const resultado = canvas?.zoomToScale(id);
  if (!resultado) return;

  const terreno = itemsActuales.find((t) => t.id === id);
  const nombre = terreno?.terreno ?? "El terreno";

  if (resultado.estado === "a_escala") {
    toast(`${nombre}: el círculo ya cubre su superficie real.`);
  } else if (resultado.estado === "limite_de_zoom") {
    toastError(
      "Este terreno necesita más acercamiento del disponible para verse a escala."
    );
  } else if (resultado.estado === "sin_area") {
    toastError(`${nombre} no tiene superficie registrada, así que no se puede dibujar a escala.`);
  } else if (resultado.estado === "sin_ubicacion") {
    toastError(`${nombre} no tiene coordenadas válidas para centrarlo.`);
  }
}

/** Everything worth restoring when this map is reopened. */
function vistaActual(state) {
  return {
    filtros: state.filtros,
    panel: state.panel,
    capasOcultas: state.capas.filter((c) => !c.visible).map((c) => c.orden ?? 0),
    vista: canvas?.viewport?.() ?? null,
  };
}

async function guardarVista(mapa) {
  try {
    const state = getState();
    await api.updateMapa(mapa.id ?? state.mapaActivo.id, {
      config: {
        basemap: state.basemap,
        modoColor: state.modoColor,
        ...vistaActual(state),
      },
    });
    const { mapas } = await api.mapas();
    setState({ mapas });
    toast("Vista guardada: filtros, mapa base y encuadre.");
  } catch (error) { toastError(error.message); }
}

async function actualizarMapa(mapa) {
  const ok = await confirmDialog({
    titulo: "Actualizar mapa",
    mensaje:
      `«${mapa.nombre}» se volverá a copiar desde las bases de origen. ` +
      "Lo que se ve ahora se reemplaza por los datos actuales. " +
      "Las capas cuya base ya no exista se conservan tal como están.",
    confirmar: "Actualizar",
  });
  if (!ok) return;

  try {
    const resultado = await api.refreshMapa(mapa.id);
    const { mapas } = await api.mapas();
    setState({ mapas });
    await openMapa(resultado.mapa);
    toast(
      `${plural(resultado.actualizadas, "capa actualizada", "capas actualizadas")}` +
      (resultado.conservadas
        ? `, ${plural(resultado.conservadas, "capa conservada", "capas conservadas")}.`
        : ".")
    );
  } catch (error) { toastError(error.message); }
}

/**
 * Apply a source rename to what is already on screen.
 *
 * Deliberately not a reload of the map: reopening it would throw away the
 * filters, selection, zoom and hidden layers the user has set. Only the names
 * change, so only the names are patched.
 */
function aplicarRenombreDeBase(baseId, nombre, respuesta) {
  setState((state) => {
    const bases = state.bases.map((b) => (b.id === baseId ? { ...b, nombre } : b));
    const capas = state.capas.map((capa) =>
      capa.base_id === baseId
        ? {
            ...capa,
            base_nombre: nombre,
            nombre: capa.version_etiqueta ? `${nombre} · ${capa.version_etiqueta}` : nombre,
          }
        : capa);
    const porOrden = new Map(capas.map((c) => [c.orden ?? 0, c.nombre]));

    return {
      bases,
      mapas: respuesta.mapas ?? state.mapas,
      capas,
      terrenos: state.terrenos.map((t) =>
        t.base_id === baseId
          ? { ...t, base_nombre: porOrden.get(t.capa ?? 0) ?? t.base_nombre }
          : t),
      baseActiva: state.baseActiva?.id === baseId
        ? { ...state.baseActiva, nombre }
        : state.baseActiva,
      mapaActivo: state.mapaActivo
        ? (respuesta.mapas ?? []).find((m) => m.id === state.mapaActivo.id)
          ?? state.mapaActivo
        : null,
    };
  });
}

async function afterBaseChange() {
  const { bases } = await api.bases();
  setState({ bases });
  const activa = getState().baseActiva;
  if (activa) {
    const refrescada = bases.find((b) => b.id === activa.id);
    if (refrescada) await openBase(refrescada, { silencioso: true });
  }
}

/* One rename dialog for bases and for saved maps: same field, same rules, only
 * the title and what it saves to differ. */
function promptRename({ titulo, nombre: actual, onSave }) {
  const input = el("input", { class: "input", id: "nuevo-nombre", value: actual });
  openDialog({
    titulo,
    ancho: "28rem",
    contenido: el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: "nuevo-nombre" }, "Nombre"),
      input,
    ),
    acciones: [
      { etiqueta: "Cancelar", onClick: (close) => close() },
      {
        etiqueta: "Guardar", variante: "principal",
        onClick: async (close) => {
          const nombre = input.value.trim();
          if (!nombre) return toastError("El nombre no puede estar vacío.");
          try {
            await onSave(nombre);
            close();
            toast("Nombre actualizado.");
          } catch (error) { toastError(error.message); }
        },
      },
    ],
  });
}

function renameBase(base) {
  promptRename({
    titulo: "Renombrar base",
    nombre: base.nombre,
    onSave: async (nombre) => {
      await api.renameBase(base.id, nombre);
      await afterBaseChange();
    },
  });
}

function renameMapa(mapa) {
  promptRename({
    titulo: "Renombrar mapa",
    nombre: mapa.nombre,
    onSave: async (nombre) => {
      await api.updateMapa(mapa.id, { nombre });
      const { mapas } = await api.mapas();
      const activo = getState().mapaActivo;
      setState({
        mapas,
        ...(activo?.id === mapa.id ? { mapaActivo: { ...activo, nombre } } : {}),
      });
    },
  });
}

async function deleteBase(base) {
  const ok = await confirmDialog({
    titulo: "Eliminar base",
    mensaje: `Se eliminará «${base.nombre}» con sus ${fmtCount(base.conteo)} terrenos, ` +
             "y desaparecerá de los mapas guardados que la usen. No se puede deshacer.",
    confirmar: "Eliminar",
    peligro: true,
  });
  if (!ok) return;

  try {
    await api.deleteBase(base.id);
    // Folders load alongside and report their own failure, so a folder
    // problem never hides the bases and maps themselves.
    const [{ bases }, { mapas }] = await Promise.all([
      api.bases(), api.mapas(), loadCarpetas("bases"), loadCarpetas("mapas"),
    ]);
    const eraActiva = getState().baseActiva?.id === base.id;
    setState({
      bases, mapas,
      ...(eraActiva ? { baseActiva: null, terrenos: [], capas: [], seleccionado: null } : {}),
    });
    toast(`Se eliminó «${base.nombre}».`);
  } catch (error) { toastError(error.message); }
}

async function deleteMapa(mapa) {
  const ok = await confirmDialog({
    titulo: "Eliminar mapa",
    mensaje: `Se eliminará el mapa «${mapa.nombre}». Las bases de terrenos no se tocan.`,
    confirmar: "Eliminar",
    peligro: true,
  });
  if (!ok) return;

  try {
    await api.deleteMapa(mapa.id);
    const { mapas } = await api.mapas();
    const eraActivo = getState().mapaActivo?.id === mapa.id;
    setState({ mapas, ...(eraActivo ? { mapaActivo: null, terrenos: [], capas: [] } : {}) });
    toast(`Se eliminó «${mapa.nombre}».`);
  } catch (error) { toastError(error.message); }
}

async function exportar(state, filtrados) {
  // A saved map exports its frozen rows, with the source base named; a live
  // base exports itself.
  const destino = state.mapaActivo
    ? { mapa_id: state.mapaActivo.id, nombre: state.mapaActivo.nombre }
    : state.baseActiva
      ? { base_id: state.baseActiva.id, nombre: state.baseActiva.nombre }
      : null;

  if (!destino) return toastError("No hay nada que exportar.");
  try {
    await exportXlsx({ ...destino, ids: filtrados.map((t) => t.id) });
    // The sheet count comes from the export contract, not from how many groups
    // happen to be non-empty: a filtered-out layer still gets its own sheet.
    const hojas = state.mapaActivo?.tipo === "comparacion" ? state.capas.length : 1;
    toast(
      hojas > 1
        ? `Se exportaron ${plural(filtrados.length, "terreno")} en ${hojas} hojas, una por base.`
        : `Se exportaron ${plural(filtrados.length, "terreno")}.`
    );
  } catch (error) { toastError(error.message); }
}

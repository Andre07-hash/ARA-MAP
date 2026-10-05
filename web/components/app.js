/* The application shell: session, routing, the draft editor and view dispatch.
 *
 * The Leaflet container is created once and kept alive across re-renders --
 * everything around it is rebuilt from state, but the map itself is not.
 *
 * Anonymous visitors get the public catalog and nothing else: startup asks
 * only for /api/config, /api/session and the public catalog. The team's
 * inventory, bases and saved maps load only after an individual sign-in, and
 * are cancelled and cleared on logout or session expiry.
 *
 * The header, the map workspace, the catalog/inventory views, the legacy map
 * view and the legacy actions live in ./shell/; their shared state is
 * shell/context.js.
 */

import { abortPrivate, api, configureApi } from "../lib/api.js";
import { clear, el } from "../lib/dom.js";
import {
  defaultRoute, isPrivateRoute, navigate, parseRoute, routeHash, sameRoute,
} from "../lib/router.js";
import { clearPrivateState, getState, setState, subscribe } from "../lib/store.js";
import { loadCarpetas } from "./folders/folderActions.js";
import {
  cancelarCargas, cargar, cargarDetalle, pedirCarga, reemplazarRegistro,
} from "./inventory/datasets.js";
import { createTerrainEditor } from "./inventory/TerrainEditor.js";
import { openTerrainHistory } from "./inventory/TerrainHistory.js";
import { createSession } from "./session/session.js";
import { shell } from "./shell/context.js";
import { renderDatos } from "./shell/datosView.js";
import { renderHeader as dibujarCabecera } from "./shell/header.js";
import { renderBases, renderMapas } from "./shell/legacyActions.js";
import { renderMapa } from "./shell/mapaView.js";
import { confirmDialog } from "./ui/dialog.js";
import { clearToasts, toast, toastError } from "./ui/toast.js";

const REVALIDAR_MS = 10_000;   // focus/visibility revalidation, at most this often

let configReadOnly = false;
let session = null;
let editor = null;          // the open TerrainEditor, kept alive across renders
let editorEstado = null;    // { id, error } while an editor loads or failed to
let legacyCargado = false;  // bases/maps/folders loaded for this session
let ultimaRevalidacion = 0;

export async function mount(root) {
  try {
    const config = await api.config();
    configReadOnly = config.readOnly === true;
    shell.cloud = config.cloud === true;
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
    hasUnsavedWork: () => Boolean(editor?.dirty),
  });

  window.addEventListener("hashchange", aplicarRuta);
  window.addEventListener("beforeunload", (event) => {
    if (editor?.dirty) { event.preventDefault(); event.returnValue = ""; }
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

function alEntrar(_usuario, { returnTo, startup }) {
  loadIndex();
  // /api/config's readOnly depends on the session, so it is read again now.
  if (startup) { shell.readOnly = configReadOnly; return; }
  api.config().then((config) => { shell.readOnly = config.readOnly === true; setState({}); })
    .catch(() => { shell.readOnly = false; });
  if (!navigate(returnTo ?? defaultRoute(true), { replace: true })) aplicarRuta();
}

/**
 * Forget the session's private data: cancel its requests, close what shows
 * it, and reset its state. The public catalog stays.
 */
function limpiarPrivado() {
  abortPrivate();
  cancelarCargas();
  editor?.destroy();
  editor = null;
  editorEstado = null;
  for (const dialog of document.querySelectorAll("dialog[open]")) dialog.close();
  clearToasts();
  const { workspace } = shell;
  if (workspace) {
    for (const modo of ["inventario", "local"]) {
      workspace.rails[modo]?.destroy();
      delete workspace.rails[modo];
    }
    workspace.detailSlot.replaceChildren();
    workspace.tableSlot.replaceChildren();
    shell.canvas?.render([], { colorFor: () => "" });
  }
  shell.itemsActuales = [];
  shell.readOnly = true;
  legacyCargado = false;
  shell.encuadrado.inventario = false;
  shell.tableSort = { campo: "orden", direccion: "asc" };
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
  if (editor?.dirty && !(await confirmarDescarte())) return;
  session.signOut();
}

const confirmarDescarte = () => confirmDialog({
  titulo: "¿Descartar cambios?",
  mensaje: "Tienes cambios sin guardar en este terreno. Si sales ahora, se pierden.",
  confirmar: "Descartar cambios",
  peligro: true,
});

async function revalidar({ forzar = false } = {}) {
  if (!session || (!forzar && Date.now() - ultimaRevalidacion < REVALIDAR_MS)) return;
  ultimaRevalidacion = Date.now();
  await session.refresh();
  const { ruta, sesion } = getState();
  if (ruta.nombre === "catalogo") pedirCarga("catalogo", { inmediato: true });
  else if (ruta.nombre === "inventario" && sesion) pedirCarga("inventario", { inmediato: true });
}

/* ---------------------------------------------------------------- routing */

const rutaDelEditor = () => (editor?.id ? { nombre: "editar", id: editor.id } : { nombre: "nuevo" });

async function aplicarRuta() {
  const ruta = parseRoute(location.hash);
  const { sesion } = getState();
  if (!ruta) {
    if (!navigate(defaultRoute(Boolean(sesion)), { replace: true })) aplicarRuta();
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
  } else if (ruta.nombre === "editar" || ruta.nombre === "nuevo") {
    if (!editor) abrirEditor(ruta);
  } else if (ruta.nombre === "mapa" && !state.baseActiva && !state.mapaActivo) {
    navigate({ nombre: "bases" }, { replace: true });
  } else if (ruta.nombre === "bases" || ruta.nombre === "mapas") {
    // Other team members add bases and maps too: revalidate on entry.
    loadIndex({ forzar: true });
  }
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

/* ------------------------------------------------------------------ views */

function renderHeader(host) {
  dibujarCabecera(host, {
    onSignIn: () => session.signIn({ returnTo: null }),
    onSignOut: cerrarSesion,
  });
}

function renderView(host) {
  const state = getState();
  if (!state.sesionLista) {
    clear(host).append(el("div", { class: "screen" },
      el("p", { class: "secondary", role: "status" }, "Cargando…")));
    return undefined;
  }
  switch (state.ruta.nombre) {
    case "bases": return renderBases(host, state);
    case "mapas": return renderMapas(host, state);
    case "editar":
    case "nuevo": return renderEditor(host);
    case "mapa": return renderMapa(host, state);
    case "inventario": return renderDatos(host, state, "inventario");
    default: return renderDatos(host, state, "catalogo");
  }
}
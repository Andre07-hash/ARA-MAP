/* The employee table: one bounded, server-filtered page of terrains with
 * inline editing.
 *
 * It owns its own state and DOM instead of living in the shared store: the
 * grid must not be rebuilt under a focused cell. Everything it holds belongs
 * to one account looking at one view (a work base, the unassigned records or
 * the master table). `generacion` names that scope: it moves whenever the
 * view, the query or the page changes, and a response that comes back to an
 * older generation is dropped, so an old request is never shown under a newly
 * selected account or base.
 *
 * Saving is per cell, with the row's real version. Saves of one row queue
 * behind each other; nothing is retried blindly and nothing is overwritten
 * silently: a conflict keeps what the person typed beside the row as it is
 * now, and an unanswered save is checked against the server before anything
 * is sent again.
 *
 * Files and location (Round 3). Each row carries the server's `archivos`
 * summary and `ubicacion`; the file cells and the record detail hand the
 * summary to Team B's widgets. Neither is part of the terrain's version: when
 * a widget reports a change, one request refreshes that terrain and only
 * those two fields of the row are replaced. No cell is repainted, so an open
 * or unresolved editor is not touched.
 *
 * Tabla / Mapa. The same view, with the same filters, shows either the grid
 * (one page) or a map of EVERY terrain that matches (vistaPrevia.js). The
 * map's set is gathered page by page from the view's own authorized list
 * route, kept while its view and query stay the same (switching back and
 * forth, or paging the grid, does not fetch it again) and patched by this
 * table's own writes. "Actualizar" gathers it again. Leaving the view, the
 * account or the scope drops it with any gathering in flight.
 *
 * Uploads in progress (issue #39). A repaint or reload of the same view
 * (focus revalidation, Actualizar, a filter, a page, a new row, a late
 * answer of a request already in flight) never destroys a file mount whose
 * upload is unfinished: it is set aside and put back in its terrain's new
 * row. A mount whose terrain is no longer drawn keeps running detached while
 * its upload is being sent or verified, and is released once it stops (an
 * unfinished version stays on the server, to continue from the detail).
 * Leaving the view, or the session, asks first; losing the scope does not.
 *
 * The map screen (mapaPaneles.js) adds its own filters, a price legend and a
 * read-only record on top of that set. Its filters are not this table's
 * query: they narrow what the map draws, never the grid, its page or its
 * cursors, and they start empty again whenever the view is left.
 *
 * On the map, the bar keeps only the view, Tabla / Mapa and Actualizar. The
 * grid's query controls are hidden, never cleared: their values still bound
 * the set, and a small "Filtros de la tabla (N)" note lists them when there
 * are any. The footer's count and status are the grid's; on the map the
 * footer shows only alerts and unfinished uploads.
 */

import { api } from "../../lib/api.js";
import { clear, el } from "../../lib/dom.js";
import { fmtCount } from "../../lib/format.js";
import { nuevaClave } from "../../lib/inventario.js";
import {
  columnasDe, CONSULTA_VACIA, consultaDeLista, crearCola, cuerpoDeCelda, esEditable, esGlobal,
  escribirNumero, leerCelda, LIMITES, ORDENES, resolverIncierto, rutaDeLista, textoDe, valorDe, VISTA_MAESTRA,
  VISTA_SIN_ASIGNAR,
} from "../../lib/tabla.js";
import { openTerrainHistory } from "../inventory/TerrainHistory.js";
import { closeAllDialogs, confirmarBorrado, confirmDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";
import { conectarArchivos } from "./archivosAnfitrion.js";
import { reunirPaginas } from "../../lib/inventario.js";
import { segment } from "../inventory/DatosView.js";
import {
  abrirBases, abrirColumnas, abrirDetalle, abrirTransferencia, pedirDestino, pedirNombreDeBase,
} from "./dialogos.js";
import { montarRanura } from "./ranuraArchivos.js";
import { createMapaPaneles } from "./mapaPaneles.js";

const BUSCAR_MS = 300;
const PAGINA_MAPA = 200;          // the list's largest page
const MAXIMO_MAPA = 5000;         // a map set larger than this is drawn as partial and said so
const ESTADOS = {
  pendiente: "guardando", error: "sin guardar", conflicto: "en conflicto", incierto: "sin confirmar",
};

/* What Team B's widgets report when a write was refused although the content
 * may still be read (server codes): not a scope loss, a permission change. */
const SIN_ESCRITURA = new Set(["forbidden"]);

export function createTabla({
  sesion, soloConsulta = () => false, vistaInicial = null, modoInicial = null, onVista, onPermisos, onRevalidar,
}) {
  const admin = sesion.rol === "admin";

  let vivo = true;
  let generacion = 0;
  let carga = null;               // AbortController of the list in flight
  let bases = [];                 // work bases this account may open
  let basesListas = false;
  let vista = null;
  let definiciones = [];          // the selected base's live custom columns
  let columnas = columnasDe(VISTA_MAESTRA);
  let consulta = { ...CONSULTA_VACIA };
  let pagina = { filas: [], total: 0, facets: {}, siguiente: null };
  let cursor = null;
  let anteriores = [];            // cursors of the pages before this one
  let nuevos = new Set();         // ids created on this page, shown until it reloads
  let editando = null;            // { id, col, campo, inicial }
  let foco = null;                // { id, colId } of the last focused cell
  let creacion = null;            // { clave, estado } while a blank create is unresolved
  let buscarTimer = null;
  let errorDeCarga = null;
  let perdidas = 0;               // scope losses in a row with no successful load between them
  const celdas = new Map();       // "id|col" -> { estado, valor, texto, mensaje, version }
  const enVuelo = new Set();
  const cola = crearCola();
  let ranuras = [];
  const apartadas = new Map();    // "id|tipo" -> a busy file mount whose row is being repainted
  const porPintar = new Set();    // keys set aside since the last paint: theirs is not decided yet
  let vigiaApartadas = null;
  let seleccion = null;           // terrain id shared with the map preview
  // Rows ticked for a bulk action, id -> the version seen. They belong to one
  // view and query (`marcadosClave`) and may span pages.
  const marcados = new Map();
  let marcadosClave = null;
  let enLote = false;             // a bulk action is running
  let detalleAbierto = null;      // the open record detail, for file refreshes
  let modo = modoInicial === "mapa" ? "mapa" : "tabla";
  let aperturas = 0;              // abrir() calls; only the latest may set the view
  // The map's set: every terrain of the view for one query (`clave`).
  let conjunto = { clave: null, filas: [], total: 0, incompleto: false, obsoleto: false, error: null };
  let reunion = null;             // { clave, control } while the set is being gathered
  let reunionGen = 0;
  let mapaPintado = null;         // the set key the map last framed
  let paginaObsoleta = false;     // the grid was not revalidated while the map was shown
  const refrescos = new Map();    // terrain id -> "pedido" | "repetir" (coalesced file refreshes)
  // Team B's widgets and geometry loader, for this session only.
  const archivos = conectarArchivos({
    onListo: ({ faltan }) => {
      if (!vivo) return;
      remontarRanuras();
      if (faltan.length) alerta.textContent = `No se pudo cargar el módulo de ${faltan.join(" ni el de ")}.`;
    },
  });
  const previa = createMapaPaneles({
    cargador: () => archivos.cargador,
    onSeleccion: (id) => seleccionar(id, { desdeMapa: true }),
    // The map's filters left the selected terrain out, or its record was closed.
    onDeseleccion: (id) => { if (seleccion === id) { seleccion = null; marcarSeleccion(); } },
    nombreDeBase: (id) => baseDe(id)?.nombre ?? null,
    definicionesDe: (baseId, signal) => definicionesDeBase(baseId, signal),
    // A boundary that is no longer available (retired, replaced, or out of
    // scope) means this row may be stale: ask for the terrain again, which
    // either updates its location or removes it from the view.
    onError: ({ id, codigo }) => { if (codigo === "no_disponible" || codigo === "404") refrescarArchivos(id); },
  });

  /* ------------------------------------------------------------ skeleton */

  const selVista = el("select", { id: "tabla-vista", class: "input", onchange: () => abrir(selVista.value) });
  const buscar = el("input", {
    id: "tabla-buscar", class: "input", type: "search", placeholder: "Nombre, municipio, estado…",
    oninput: () => {
      clearTimeout(buscarTimer);
      buscarTimer = setTimeout(() => consultar({ q: buscar.value }), BUSCAR_MS);
    },
  });
  const filtro = (id, campo) => el("select", {
    id, class: "input", onchange: (e) => consultar({ [campo]: e.target.value }),
  });
  const selEstado = filtro("tabla-estado", "estado");
  const selMunicipio = filtro("tabla-municipio", "municipio");
  const selTipo = filtro("tabla-tipo", "tipo_terreno");
  const selOrden = el("select", { id: "tabla-orden", class: "input", onchange: () => ordenar() },
    ORDENES.map(([valor, etiqueta]) => el("option", { value: valor }, etiqueta)));
  const chkDesc = el("input", { id: "tabla-desc", type: "checkbox", onchange: () => ordenar() });
  const selLimite = el("select", {
    id: "tabla-limite", class: "input", onchange: () => consultar({ limit: Number(selLimite.value) }),
  }, LIMITES.map((n) => el("option", { value: n, selected: n === consulta.limit }, String(n))));

  const btnAgregar = el("button", { type: "button", class: "btn btn-principal", onclick: () => agregar() },
    "Agregar terreno");
  const btnColumnas = el("button", { type: "button", class: "btn btn-quiet", onclick: () => columnasDialogo() },
    "Columnas");
  const btnBases = admin && el("button", { type: "button", class: "btn btn-quiet", onclick: () => basesDialogo() },
    "Bases y accesos");
  const btnRecargar = el("button", {
    type: "button", class: "btn btn-quiet", onclick: () => (modo === "mapa" ? actualizarMapa() : actualizarTabla()),
  }, "Actualizar");
  const btnModoTabla = segment("Tabla", modo === "tabla", () => mostrarComo("tabla"));
  const btnModoMapa = segment("Mapa", modo === "mapa", () => mostrarComo("mapa"));
  const selectorModo = el("div", { class: "segmented tabla-modo", role: "group", "aria-label": "Mostrar como" },
    btnModoTabla, btnModoMapa);

  const campoDe = (control, etiqueta) => el("div", { class: "tabla-campo" },
    el("label", { class: "field-label", for: control.id }, etiqueta), control);
  const casilla = (control, etiqueta) => el("label", { class: "check tabla-casilla", for: control.id }, control, etiqueta);

  // The grid's query controls. The map does not show them: it keeps their
  // values (they bound its set) and says so in the inherited-filters note.
  const deLaConsulta = [
    campoDe(buscar, "Buscar"),
    campoDe(selEstado, "Estado"),
    campoDe(selMunicipio, "Municipio"),
    campoDe(selTipo, "Tipo"),
    campoDe(selOrden, "Ordenar por"),
    casilla(chkDesc, "Descendente"),
  ];
  const listaHeredados = el("ul", { class: "tabla-heredados-lista" });
  const heredados = el("details", { class: "tabla-heredados", hidden: true },
    el("summary", { class: "btn btn-small" }),
    el("div", {
      class: "tabla-heredados-panel", role: "note", "aria-label": "Filtros de la tabla en el mapa", tabindex: "-1",
    },
      el("p", {}, "El mapa sólo incluye los terrenos que cumplen estos filtros de la tabla:"),
      listaHeredados,
      el("p", { class: "muted" }, "Los filtros del mapa se aplican dentro de este conjunto. " +
        "Para cambiar estos, vuelve a Tabla."),
    ));
  heredados.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !heredados.open) return;
    e.stopPropagation();
    heredados.open = false;
    heredados.querySelector("summary").focus();
  });
  // Closes when the focus leaves it; the panel takes the focus of a click on its text.
  heredados.addEventListener("focusout", (e) => { if (!heredados.contains(e.relatedTarget)) heredados.open = false; });
  const barra = el("div", { class: "tabla-barra" },
    campoDe(selVista, "Vista"),
    heredados,
    ...deLaConsulta,
    el("div", { class: "tabla-acciones" }, selectorModo, btnAgregar, btnColumnas, btnBases, btnRecargar),
  );

  const aviso = el("p", { class: "tabla-aviso", hidden: true });
  const bandeja = el("section", { class: "tabla-bandeja", "aria-label": "Cambios sin resolver", hidden: true });
  const thead = el("thead");
  const tbody = el("tbody");
  const grid = el("table", { class: "tabla-grid", role: "grid", "aria-label": "Terrenos" }, thead, tbody);
  // Busy from the start: it has nothing to show until the first page arrives.
  const lienzo = el("div", { class: "tabla-lienzo", tabindex: "-1", "aria-busy": "true" }, grid);
  const vacio = el("div", { class: "tabla-vacio", hidden: true });
  const cuenta = el("span", { class: "tabla-cuenta" });
  const btnAnterior = el("button", { type: "button", class: "btn btn-quiet", onclick: () => paginar(-1) }, "Anterior");
  const btnSiguiente = el("button", { type: "button", class: "btn btn-quiet", onclick: () => paginar(1) }, "Siguiente");
  const estado = el("span", { class: "tabla-estado", role: "status", "aria-live": "polite" });
  const alerta = el("span", { class: "tabla-alerta", role: "alert" });
  const avisoSubidas = el("span", { class: "tabla-subidas", role: "status", hidden: true });
  const campoLimite = campoDe(selLimite, "Filas por página");
  const pie = el("div", { class: "tabla-pie" }, cuenta, campoLimite,
    btnAnterior, btnSiguiente, estado, avisoSubidas, alerta);

  const avisoMapa = el("p", { class: "tabla-mapa-aviso", role: "status", "aria-live": "polite" });
  const btnMapaReintentar = el("button", {
    type: "button", class: "btn btn-quiet btn-small", hidden: true, onclick: () => actualizarMapa(),
  }, "Volver a intentar");
  // The set's notices float over the map, not in a strip of their own.
  previa.avisos(el("div", { class: "tabla-mapa-estado" }, avisoMapa, btnMapaReintentar));
  const panelMapa = el("div", { id: "tabla-previa", class: "tabla-previa", hidden: true }, previa.element);
  const cuerpo = el("div", { class: "tabla-cuerpo" }, lienzo, panelMapa);
  const lote = el("div", { class: "tabla-lote", role: "region", "aria-label": "Terrenos seleccionados", hidden: true });
  const element = el("div", { class: "tabla-pantalla" }, barra, aviso, bandeja, lote, cuerpo, vacio, pie);

  tbody.addEventListener("focusin", (e) => {
    const celda = e.target.closest("td[data-col]");
    if (!celda) return;
    foco = { id: celda.parentNode.dataset.id, colId: celda.dataset.col };
    seleccionar(foco.id);
  });
  tbody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (tr) seleccionar(tr.dataset.id);
  });
  tbody.addEventListener("dblclick", (e) => {
    const celda = e.target.closest("td[data-col]");
    if (celda && !editando) editar(celda.parentNode.dataset.id, celda.dataset.col);
  });
  tbody.addEventListener("keydown", alTeclear);

  /* --------------------------------------------------------------- scope */

  const baseDe = (id) => bases.find((b) => b.id === id) ?? null;
  const baseActual = () => (esGlobal(vista) ? null : baseDe(vista));
  const vistaSoloLectura = () => soloConsulta();
  const filaDe = (id) => pagina.filas.find((t) => t.id === id) ?? null;
  const colDe = (colId) => columnas.find((c) => c.id === colId) ?? null;
  const clave = (id, colId) => `${id}|${colId}`;
  /** Whether the record's detail offers changes at all (delete, files): not in read-only mode. */
  const puedeCambiarFila = () => !soloConsulta();
  /** Whether this row's cells and file cells may be written. */
  const filaEditable = () => !vistaSoloLectura();

  const sinResolver = () => [...celdas.values()].filter((c) => c.estado !== "pendiente").length
    + (creacion?.estado === "incierto" ? 1 : 0);
  const sucio = () => sinResolver() > 0 || enVuelo.size > 0
    || Boolean(editando && editando.campo.value !== editando.inicial);

  /** Drop everything that belongs to the scope being left. Leaving the view
   * itself (``deVista``) also drops what names it: its column headers and the
   * values its filters offered. */
  function limpiarAlcance(deVista = true) {
    generacion += 1;
    carga?.abort();
    carga = null;
    clearTimeout(buscarTimer);
    editando = null;
    foco = null;
    creacion = null;
    celdas.clear();
    cola.olvidar();
    enVuelo.clear();
    nuevos = new Set();
    if (deVista) marcados.clear();
    // Within the view a busy upload outlives the repaint; leaving the view ends it.
    if (deVista) soltarRanuras(); else apartarRanuras();
    refrescos.clear();
    detalleAbierto = null;
    pagina = { filas: [], total: 0, facets: {}, siguiente: null };
    definiciones = [];
    cursor = null;
    anteriores = [];
    errorDeCarga = null;
    tbody.replaceChildren();
    bandeja.replaceChildren();
    bandeja.hidden = true;
    alerta.textContent = "";
    if (deVista) {
      // The map's set, its boundary body and any gathering or load in flight
      // belong to the view being left. Within a view, a new query or page
      // keeps them: the set is kept or gathered again by its own key.
      previa.reiniciar();          // the map's own filters belong to the view being left
      olvidarConjunto();
      seleccion = null;
      // A detail, a history, the columns or the grants of the view being left.
      closeAllDialogs();
      columnas = columnasDe(VISTA_MAESTRA);
      thead.replaceChildren();
      for (const control of [selEstado, selMunicipio, selTipo]) control.replaceChildren();
      cuenta.textContent = "";
      estado.textContent = "";
    }
  }

  /** Let saves in flight finish, then ask before discarding what is unsaved.
   * Leaving the view (`deVista`) also asks before interrupting an upload. */
  async function puedeSalir({ deVista = false } = {}) {
    if (editando) confirmar();
    if (enVuelo.size) {
      decir("Terminando de guardar…");
      await Promise.allSettled([...enVuelo]);
    }
    if (!vivo) return false;
    if (sinResolver() && !(await confirmDialog({
      titulo: "¿Descartar cambios sin guardar?",
      mensaje: "Hay celdas con cambios que no se guardaron. Si continúas, se pierden.",
      confirmar: "Descartar", peligro: true,
    }))) return false;
    if (!deVista || !vivo) return vivo;
    const n = archivos.pendientes();
    if (!n) return true;
    return confirmDialog({
      titulo: "¿Interrumpir la subida de archivos?",
      mensaje: `${n === 1 ? "Hay una subida de archivo sin terminar" : `Hay ${n} subidas de archivos sin terminar`} ` +
        "en esta vista. Si cambias de vista ahora, se interrumpe: los archivos ya guardados se conservan, y una " +
        "subida sin terminar puede continuarse desde el detalle del terreno eligiendo otra vez el mismo archivo. " +
        "Para no interrumpirla, quédate en esta vista hasta que diga «Listo».",
      confirmar: "Interrumpir y cambiar de vista", cancelar: "Seguir en esta vista", peligro: true,
    });
  }

  async function cargarBases() {
    const gen = generacion;
    try {
      const respuesta = await api.maestraBases();
      if (!vivo || gen !== generacion) return false;
      bases = respuesta.bases ?? [];
      basesListas = true;
      return true;
    } catch (error) {
      if (!vivo || gen !== generacion) return false;
      basesListas = true;
      errorDeCarga = `No se pudieron cargar las bases de trabajo: ${error.message}`;
      return false;
    }
  }

  const vistaValida = (v) => Boolean(v) && ((admin && esGlobal(v)) || Boolean(baseDe(v)));
  const vistaPorDefecto = () => (admin ? VISTA_MAESTRA : bases[0]?.id ?? null);

  /** Open a view: a base id, or (administrators) the master table / unassigned. */
  async function abrir(pedida, { forzar = false } = {}) {
    if (!vivo) return;
    if (!forzar && pedida === vista) return;
    const mia = ++aperturas;
    if (vista !== null && !(await puedeSalir({ deVista: true }))) {
      if (mia !== aperturas) return;
      selVista.value = vista ?? "";
      onVista?.(vista, modoDeRuta());
      return;
    }
    limpiarAlcance();
    lienzo.setAttribute("aria-busy", "true");
    if (!basesListas) await cargarBases();
    // A later opening (another view asked for while the bases loaded) wins:
    // this one must not put its view, or its address, back over that one.
    if (!vivo || mia !== aperturas) return;
    vista = vistaValida(pedida) ? pedida : vistaPorDefecto();
    consulta = { ...CONSULTA_VACIA, limit: consulta.limit };
    buscar.value = "";
    chkDesc.checked = false;
    selOrden.value = "id";
    pintarMarco();
    onVista?.(vista, modoDeRuta());
    if (vista) await cargar();
    else lienzo.removeAttribute("aria-busy");
  }

  /** The base, the grant or the role is gone: show nothing of it any more. */
  async function alcancePerdido(mensaje, { permisos = false } = {}) {
    const habia = sucio();
    limpiarAlcance();
    basesListas = false;
    vista = null;
    perdidas += 1;
    toastError(mensaje + (habia ? " Lo que estaba sin guardar en esa vista se descartó." : ""));
    // The role itself may have changed: the shell asks the server who we are
    // and builds a new table for that answer. Twice in a row, stop and say so.
    if (permisos || perdidas > 1) {
      errorDeCarga = "Tu acceso cambió. Vuelve a comprobar, o inicia sesión de nuevo.";
      bases = [];
      pintarMarco();
      onPermisos?.();
      return;
    }
    await abrir(null, { forzar: true });
  }

  /* ----------------------------------------------------------------- list */

  /** Change what the list asks for. Unless told to stay, it starts at page one:
   * a cursor belongs to the scope, filters and order it came from. */
  async function cambiar(aplicar, { mismaPagina = false } = {}) {
    if (!(await puedeSalir())) { sincronizarControles(); return; }
    const previo = { definiciones, cursor, anteriores };
    limpiarAlcance(false);
    definiciones = previo.definiciones;
    if (mismaPagina) ({ cursor, anteriores } = previo);
    // What is typed in the search box counts even if its own timer had not fired yet.
    consulta = { ...consulta, q: buscar.value };
    aplicar();
    // A gathering for the query being left stops now, and the map never keeps
    // the old query's rows while the new page loads.
    if (reunion && reunion.clave !== claveConjunto()) soltarReunion();
    pintarMapa();
    await cargar();
  }

  const consultar = (cambio) => cambiar(() => { consulta = { ...consulta, ...cambio }; });
  const ordenar = () => consultar({
    sort: selOrden.value === "id" ? "id" : `${chkDesc.checked ? "-" : ""}${selOrden.value}`,
  });
  const recargar = () => cambiar(() => {}, { mismaPagina: true });

  function paginar(paso) {
    const destino = paso > 0 ? pagina.siguiente : anteriores[anteriores.length - 1];
    if (paso > 0 && !pagina.siguiente) return;
    if (paso < 0 && !anteriores.length) return;
    const pila = paso > 0 ? [...anteriores, cursor] : anteriores.slice(0, -1);
    cambiar(() => { cursor = destino ?? null; anteriores = pila; }).then(() => lienzo.scrollTo?.({ top: 0 }));
  }

  function sincronizarControles() {
    buscar.value = consulta.q;
    selOrden.value = consulta.sort.replace(/^-/, "");
    chkDesc.checked = consulta.sort.startsWith("-");
    selLimite.value = String(consulta.limit);
    for (const [control, campo] of [[selEstado, "estado"], [selMunicipio, "municipio"], [selTipo, "tipo_terreno"]]) {
      control.value = consulta[campo];
    }
  }

  async function cargar() {
    const gen = generacion;
    carga?.abort();
    carga = new AbortController();
    const { signal } = carga;
    errorDeCarga = null;
    decir("Cargando…");
    lienzo.setAttribute("aria-busy", "true");
    try {
      const [lista, cols] = await Promise.all([
        api.tablaLista(rutaDeLista(vista), consultaDeLista(vista, consulta, cursor), signal),
        esGlobal(vista) ? null : api.columnas(vista, signal),
      ]);
      if (!vivo || gen !== generacion) return;
      if (cols) definiciones = cols.columnas ?? [];
      columnas = columnasDe(vista, definiciones);
      pagina = {
        filas: lista.terrenos ?? [], total: lista.total ?? 0, facets: lista.facets ?? {},
        siguiente: lista.next_cursor ?? null,
      };
      perdidas = 0;
      pintarTodo();
      decir(`${fmtCount(pagina.total)} ${pagina.total === 1 ? "terreno" : "terrenos"}.`);
    } catch (error) {
      if (!vivo || gen !== generacion || error.name === "AbortError") return;
      if (error.status === 404 || error.status === 403) {
        alcancePerdido("Ya no tienes acceso a esa vista.", { permisos: error.status === 403 });
        return;
      }
      errorDeCarga = `No se pudo cargar la tabla: ${error.message}`;
      pintarTodo();
    } finally {
      if (gen === generacion) lienzo.removeAttribute("aria-busy");
    }
  }

  /* ------------------------------------------------------------- painting */

  const decir = (texto) => { estado.textContent = texto; };

  function opcion(valor, etiqueta, seleccionada) {
    return el("option", { value: valor, selected: seleccionada }, etiqueta);
  }

  function pintarMarco() {
    const opciones = [];
    if (admin) {
      opciones.push(opcion(VISTA_MAESTRA, "Tabla maestra (todas las bases)", vista === VISTA_MAESTRA),
        opcion(VISTA_SIN_ASIGNAR, "Sin asignar", vista === VISTA_SIN_ASIGNAR));
    }
    const deTrabajo = bases.map((b) => opcion(b.id, b.nombre, b.id === vista));
    opciones.push(admin ? el("optgroup", { label: "Bases de trabajo" }, deTrabajo) : deTrabajo);
    selVista.replaceChildren(...opciones.flat());
    selVista.value = vista ?? "";

    const sinAcceso = !vista;
    for (const nodo of [pie, bandeja]) nodo.hidden = sinAcceso || (nodo === bandeja && !bandeja.childElementCount);
    for (const control of [buscar, selEstado, selMunicipio, selTipo, selOrden, chkDesc, selVista]) {
      control.disabled = sinAcceso;
    }
    vacio.hidden = !sinAcceso;
    if (sinAcceso) {
      clear(vacio).append(
        el("h2", {}, errorDeCarga ? "No se pudo abrir la tabla" : "Todavía no tienes una base de trabajo"),
        el("p", { class: "secondary" }, errorDeCarga ?? ("Un administrador tiene que darte acceso a una base de " +
          "trabajo para que puedas ver y editar terrenos aquí.")),
        el("button", {
          type: "button", class: "btn btn-quiet",
          onclick: () => { basesListas = false; abrir(null, { forzar: true }); },
        }, "Volver a comprobar"),
      );
    }
    pintarModo();          // the grid or the map, and what may be written
  }

  function pintarPermisos() {
    pintarLote();
    const lectura = vistaSoloLectura();
    btnAgregar.hidden = !vista || lectura || modo === "mapa";
    btnAgregar.disabled = creacion?.estado === "enviando";
    btnColumnas.hidden = !vista || esGlobal(vista) || modo === "mapa";
    btnRecargar.hidden = !vista;
    aviso.hidden = !(vista && lectura);
    aviso.textContent = soloConsulta() ? "ARA Map está en modo de solo consulta: no se puede editar." : "";
  }

  function facetas(control, valores, actual, todos) {
    const lista = [...new Set([...(valores ?? []), ...(actual ? [actual] : [])])];
    control.replaceChildren(opcion("", todos, !actual), ...lista.map((v) => opcion(v, v, v === actual)));
  }

  function pintarCuenta() {
    const desde = pagina.filas.length ? anteriores.length * consulta.limit + 1 : 0;
    cuenta.textContent = errorDeCarga ?? (pagina.total
      ? `${fmtCount(desde)}–${fmtCount(desde + pagina.filas.length - 1)} de ${fmtCount(pagina.total)}`
      : "Sin terrenos en esta vista");
  }

  function pintarTodo() {
    const tenia = tbody.contains(document.activeElement) && !editando ? foco : null;
    apartarRanuras();
    pintarMarco();
    facetas(selEstado, pagina.facets.estados, consulta.estado, "Todos");
    facetas(selMunicipio, pagina.facets.municipios, consulta.municipio, "Todos");
    facetas(selTipo, pagina.facets.tipos, consulta.tipo_terreno, "Todos");

    thead.replaceChildren(el("tr", {},
      el("th", { scope: "col", class: "tabla-th tabla-th-fila" }, casillaDePagina(),
        el("span", { class: "sr-only" }, "Terreno")),
      columnas.map((c) => el("th", {
        scope: "col", class: ["tabla-th", `tabla-col-${c.tipo}`], title: c.ayuda ?? null, "data-col": c.id,
      }, c.etiqueta, c.custom && el("span", { class: "tabla-th-tipo" }, ` · ${c.tipo}`))),
    ));
    tbody.replaceChildren(...pagina.filas.map((t, i) => Fila(t, i)));
    vigilarApartadas();          // what was not put back runs detached until it stops

    pintarCuenta();
    btnAnterior.disabled = !anteriores.length;
    btnSiguiente.disabled = !pagina.siguiente;
    if (errorDeCarga) alerta.textContent = errorDeCarga;
    pintarBandeja();
    if (tenia) enfocar(tenia.id, tenia.colId);
    if (seleccion && !existe(seleccion)) seleccion = null;
    marcarSeleccion();
    pintarLote();
    pintarMapa();
  }

  /* ------------------------------------------------------- bulk actions */

  const puedeMarcar = () => Boolean(vista) && !vistaSoloLectura() && modo === "tabla";
  const terrenos = (n) => `${fmtCount(n)} ${n === 1 ? "terreno" : "terrenos"}`;

  /** The selection belongs to one view and query; another one starts empty. */
  function seleccionVigente() {
    if (marcadosClave !== claveConjunto()) { marcados.clear(); marcadosClave = claveConjunto(); }
  }

  function marcar(t, si) {
    seleccionVigente();
    if (si) marcados.set(t.id, t.version); else marcados.delete(t.id);
    pintarLote();
  }

  function casillaDePagina() {
    if (!puedeMarcar() || !pagina.filas.length) return null;
    const marcadas = pagina.filas.filter((t) => marcados.has(t.id)).length;
    const casilla = el("input", {
      type: "checkbox", class: "tabla-marca", "aria-label": "Seleccionar los terrenos de esta página",
      checked: marcadas === pagina.filas.length,
      onchange: (e) => { for (const t of pagina.filas) marcar(t, e.target.checked); pintarCasillas(); },
    });
    casilla.indeterminate = marcadas > 0 && marcadas < pagina.filas.length;
    return casilla;
  }

  /** The ticks on screen follow `marcados` without repainting any cell. */
  function pintarCasillas() {
    for (const c of tbody.querySelectorAll("input.tabla-marca")) c.checked = marcados.has(c.dataset.id);
    thead.querySelector(".tabla-th-fila input.tabla-marca")?.replaceWith(casillaDePagina() ?? "");
  }

  function pintarLote() {
    seleccionVigente();
    const n = marcados.size;
    lote.hidden = !puedeMarcar() || n === 0;
    if (lote.hidden) { lote.replaceChildren(); return; }
    const boton = (texto, onclick, clase = "btn btn-small btn-quiet") =>
      el("button", { type: "button", class: clase, disabled: enLote, onclick }, texto);
    const faltan = pagina.total - n;
    lote.replaceChildren(...[
      el("strong", {}, `${terrenos(n)} ${n === 1 ? "seleccionado" : "seleccionados"}`),
      faltan > 0 && boton(`Seleccionar los ${terrenos(pagina.total)} de esta vista`, () => marcarVista()),
      admin && boton("Crear base con ellos…", () => loteNuevaBase()),
      admin && boton("Transferir…", () => loteTransferir()),
      boton("Borrar…", () => loteBorrar(), "btn btn-small btn-peligro"),
      boton("Quitar selección", () => { marcados.clear(); pintarCasillas(); pintarLote(); }),
    ].filter(Boolean));
  }

  /** Every terrain of this view and query, gathered page by page like the map's set. */
  async function marcarVista() {
    const clave = claveConjunto();
    const deVista = vista;
    const deConsulta = { ...consulta, limit: PAGINA_MAPA };
    decir("Reuniendo los terrenos de esta vista…");
    try {
      const r = conjuntoVigente() && !conjunto.incompleto ? { terrenos: conjunto.filas } : await reunirPaginas(
        (siguiente) => api.tablaLista(rutaDeLista(deVista), consultaDeLista(deVista, deConsulta, siguiente)),
        { maximo: MAXIMO_MAPA });
      if (!vivo || claveConjunto() !== clave) return;
      for (const t of r.terrenos) marcar(t, true);
      pintarCasillas();
      decir(`${terrenos(marcados.size)} seleccionados.`);
    } catch (error) {
      if (vivo) toastError(`No se pudieron reunir los terrenos: ${error.message}`);
    }
  }

  /**
   * Run one write per selected terrain, one after another, then reload. Each
   * sends the version this table last saw for it, so a terrain someone else
   * changed meanwhile is refused and reported, never overwritten.
   */
  // ponytail: one request per terrain, sequential; a bulk endpoint if pilots outgrow ~hundreds.
  async function enLoteHacer(verbo, accion) {
    const ids = [...marcados.keys()];
    const fallos = [];
    enLote = true;
    pintarLote();
    let hechos = 0;
    for (const [i, id] of ids.entries()) {
      decir(`${verbo} ${i + 1} de ${ids.length}…`);
      try {
        await accion(id, filaDe(id)?.version ?? marcados.get(id));
        hechos += 1;
        marcados.delete(id);
      } catch (error) {
        fallos.push(error.message);
      }
      if (!vivo) return { hechos, fallos };
    }
    enLote = false;
    actualizarTabla();
    return { hechos, fallos };
  }

  function informar(resultado, hecho) {
    const { hechos, fallos } = resultado;
    if (!fallos.length) { toast(`${terrenos(hechos)} ${hecho}.`); return; }
    const motivos = [...new Set(fallos)].join(" ");
    toastError(`${terrenos(hechos)} ${hecho}; ${fallos.length} no se pudieron: ${motivos} ` +
      "Siguen seleccionados.");
  }

  async function loteBorrar() {
    const n = marcados.size;
    if (!(await confirmarBorrado({
      titulo: `¿Borrar ${terrenos(n)}?`,
      mensaje: `Se borran ${n === 1 ? "ese terreno" : `esos ${fmtCount(n)} terrenos`} con todos sus datos, su historial y sus archivos adjuntos (PDF, KMZ y KML).`,
    }))) return;
    informar(await enLoteHacer("Borrando", (id, version) => api.borrarTerreno(id, version)),
      n === 1 ? "borrado" : "borrados");
  }

  async function loteTransferir() {
    const n = marcados.size;
    const destino = await pedirDestino({ cantidad: n, bases });
    if (!destino) return;
    const baseId = destino === "sin_asignar" ? null : destino;
    informar(await enLoteHacer("Transfiriendo", (id, version) => api.transferirTerreno(id, version, baseId)),
      n === 1 ? "transferido" : "transferidos");
  }

  async function loteNuevaBase() {
    const n = marcados.size;
    const nombre = await pedirNombreDeBase({ cantidad: n });
    if (!nombre) return;
    let base;
    try {
      ({ base } = await api.crearBaseDeTrabajo(nombre));
    } catch (error) {
      toastError(`No se pudo crear la base: ${error.message}`);
      return;
    }
    await refrescarBases();
    informar(await enLoteHacer("Moviendo", (id, version) => api.transferirTerreno(id, version, base.id)),
      `${n === 1 ? "movido" : "movidos"} a «${base.nombre}»`);
  }

  /* ------------------------------------------------ files, location, map */

  const modoDeRuta = () => (modo === "mapa" ? "mapa" : null);
  /** The map set's key: the view and its query (filters and order), not the page. */
  const claveConjunto = () =>
    (vista ? `${vista}?${consultaDeLista(vista, { ...consulta, limit: PAGINA_MAPA })}` : null);
  const conjuntoVigente = () => conjunto.clave !== null && conjunto.clave === claveConjunto();
  const filaDelConjunto = (id) => (conjuntoVigente() ? conjunto.filas.find((t) => t.id === id) ?? null : null);
  /** A terrain this view shows: on the grid's page or in the map's current set. */
  const existe = (id) => Boolean(filaDe(id) || filaDelConjunto(id));
  const CONJUNTO_VACIO = Object.freeze({
    clave: null, filas: [], total: 0, incompleto: false, obsoleto: false, error: null, errorDe: null,
  });

  function soltarReunion() {
    reunionGen += 1;
    reunion?.control.abort();
    reunion = null;
  }

  /** Drop the map's set, its boundary body and whatever is gathering or loading. */
  function olvidarConjunto() {
    soltarReunion();
    conjunto = CONJUNTO_VACIO;
    mapaPintado = null;
    previa.pintar([]);
    pintarAvisoMapa();
  }

  /** Show the view as its grid or as its map. The page of the grid, the query
   * and the selection stay; the map's set is gathered only if it is missing,
   * stale or for another query. */
  function mostrarComo(pedido, { desdeRuta = false } = {}) {
    const nuevo = pedido === "mapa" ? "mapa" : "tabla";
    if (!vivo || nuevo === modo) return;
    modo = nuevo;
    pintarModo();
    // The address already says it when the change came from it.
    if (!desdeRuta) onVista?.(vista, modoDeRuta());
    if (modo === "mapa") {
      pintarMapa();
      previa.mostrar();                    // Leaflet measures the map once it is visible
      return;
    }
    // The grid was not revalidated while hidden: look again, keeping its page.
    if (paginaObsoleta && vista && !sucio()) { paginaObsoleta = false; recargar(); }
    marcarSeleccion()?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function pintarModo() {
    const mapa = modo === "mapa";
    for (const [boton, activo] of [[btnModoTabla, !mapa], [btnModoMapa, mapa]]) {
      boton.classList.toggle("is-active", activo);
      boton.setAttribute("aria-pressed", String(activo));
    }
    const sinAcceso = !vista;
    selectorModo.hidden = sinAcceso;
    lienzo.hidden = sinAcceso || mapa;
    panelMapa.hidden = sinAcceso || !mapa;
    cuerpo.classList.toggle("modo-mapa", mapa);
    element.classList.toggle("modo-mapa", mapa);
    // The page controls belong to the grid; the map shows the whole view.
    for (const nodo of [cuenta, campoLimite, btnAnterior, btnSiguiente]) nodo.hidden = mapa;
    // Hidden, never cleared: the grid finds its query as it left it.
    for (const nodo of deLaConsulta) nodo.hidden = mapa;
    if (btnBases) btnBases.hidden = mapa;
    pintarHeredados();
    pintarPermisos();
  }

  /**
   * A base's live custom columns, for the map's record. The selected base's
   * are already here; from the master table, only the terrain's own base is
   * asked for, by the same authorized route as the columns dialog. Without a
   * signal, says only what is known (null: it has to be asked).
   */
  function definicionesDeBase(baseId, signal) {
    if (!esGlobal(vista) && baseId === vista) return definiciones;
    if (!signal) return null;
    // Bound to the view, not to a page or query of it: leaving the view aborts it (reiniciar).
    const deVista = vista;
    return api.columnas(baseId, signal).then((r) => {
      if (!vivo || deVista !== vista) throw Object.assign(new Error("fuera de alcance"), { name: "AbortError" });
      return r.columnas ?? [];
    });
  }

  /** The table's own filters, which bound the map's set: [label, value]. */
  function filtrosHeredados() {
    return [
      consulta.q.trim() && ["Búsqueda", `«${consulta.q.trim()}»`],
      consulta.estado && ["Estado", consulta.estado],
      consulta.municipio && ["Municipio", consulta.municipio],
      consulta.tipo_terreno && ["Tipo de terreno", consulta.tipo_terreno],
    ].filter(Boolean);
  }

  /** On the map, a small note of the table's filters, only when there are any. */
  function pintarHeredados() {
    const partes = modo === "mapa" && vista ? filtrosHeredados() : [];
    heredados.hidden = !partes.length;
    if (!partes.length) { heredados.open = false; return; }
    heredados.querySelector("summary").textContent = `Filtros de la tabla (${partes.length})`;
    listaHeredados.replaceChildren(...partes.map(([etiqueta, valor]) =>
      el("li", {}, el("span", { class: "muted" }, `${etiqueta}: `), valor)));
  }

  /** Hand the map the view's whole set, gathering it first when needed. Never
   * shows another query's or another view's rows under this one. */
  function pintarMapa() {
    if (!vivo || modo !== "mapa") return;
    const clave = claveConjunto();
    if (!clave) { previa.pintar([]); pintarAvisoMapa(); return; }
    const vigente = conjuntoVigente();
    if (!vigente) { previa.pintar([]); mapaPintado = null; }
    if ((!vigente || conjunto.obsoleto) && conjunto.errorDe !== clave) reunir(clave);
    else if (vigente) entregarAlMapa();
    pintarAvisoMapa();
  }

  function entregarAlMapa() {
    previa.pintar(conjunto.filas, { nuevaPagina: mapaPintado !== conjunto.clave });
    mapaPintado = conjunto.clave;
    if (seleccion && seleccion !== previa.seleccion && filaDelConjunto(seleccion)) previa.seleccionar(seleccion);
  }

  /**
   * Gather every page of the view for the map, through the view's own list
   * route (the same authorization as the grid; nothing global is fetched for
   * an operator). One gathering at a time: a newer one, a new view or the end
   * of the session aborts it, and an answer for another query is dropped.
   */
  async function reunir(clave) {
    if (reunion?.clave === clave) return;
    reunion?.control.abort();
    const control = new AbortController();
    const mia = ++reunionGen;
    reunion = { clave, control, recibidos: 0, total: null };
    const deVista = vista;
    const deConsulta = { ...consulta, limit: PAGINA_MAPA };
    pintarAvisoMapa();
    try {
      const r = await reunirPaginas(
        (siguiente) => api.tablaLista(rutaDeLista(deVista), consultaDeLista(deVista, deConsulta, siguiente), control.signal),
        {
          maximo: MAXIMO_MAPA,
          onProgreso: (recibidos, total) => {
            if (mia !== reunionGen) return;
            reunion = { ...reunion, recibidos, total };
            pintarAvisoMapa();
          },
        },
      );
      if (!vivo || mia !== reunionGen) return;
      const cambiado = reunion.cambiado;
      reunion = null;
      if (claveConjunto() !== clave) { pintarMapa(); return; }
      conjunto = {
        ...CONJUNTO_VACIO, clave, filas: r.terrenos, total: r.totalServidor, incompleto: r.incompleto,
        // This table wrote while the pages were on their way: they may predate it. Gather once more.
        obsoleto: Boolean(cambiado),
      };
      if (seleccion && !existe(seleccion)) seleccion = null;
      marcarSeleccion();
      if (modo === "mapa") entregarAlMapa();
      if (cambiado) pintarMapa();
    } catch (error) {
      if (!vivo || mia !== reunionGen || error.name === "AbortError") return;
      reunion = null;
      if (error.status === 404 || error.status === 403) {
        alcancePerdido("Ya no tienes acceso a esa vista.", { permisos: error.status === 403 });
        return;
      }
      // A failed refresh keeps the set it had, said to be stale. It is not
      // retried by itself: "Volver a intentar" or "Actualizar" does.
      conjunto = conjunto.clave === clave
        ? { ...conjunto, error: error.message, errorDe: clave }
        : { ...CONJUNTO_VACIO, error: error.message, errorDe: clave };
    }
    pintarAvisoMapa();
  }

  function pintarAvisoMapa() {
    let texto = "";
    let tipo = "";
    if (reunion) {
      tipo = "cargando";
      texto = reunion.total != null
        ? `Reuniendo los terrenos de esta vista para el mapa: ${fmtCount(reunion.recibidos)} de ${fmtCount(reunion.total)}…`
        : "Reuniendo los terrenos de esta vista para el mapa…";
    } else if (conjunto.error && conjunto.errorDe === claveConjunto()) {
      tipo = "error";
      texto = conjuntoVigente()
        ? `No se pudo actualizar el mapa: muestra lo que se reunió antes${conjunto.incompleto ? ", que está incompleto" : ""}. ${conjunto.error}`
        : `No se pudieron reunir los terrenos para el mapa. ${conjunto.error}`;
    } else if (conjuntoVigente() && conjunto.incompleto) {
      tipo = "aviso";
      texto = `Mapa incompleto: muestra ${fmtCount(conjunto.filas.length)} de ${fmtCount(conjunto.total)} ` +
        "terrenos, el máximo que se reúne a la vez. Usa los filtros para acotar la vista.";
    } else if (conjuntoVigente() && !conjunto.filas.length) {
      texto = "Ningún terreno coincide con esta vista y sus filtros.";
    }
    avisoMapa.textContent = texto;
    avisoMapa.dataset.tipo = tipo;
    avisoMapa.hidden = !texto;
    btnMapaReintentar.hidden = tipo !== "error";
  }

  /** "Actualizar" on the map, or a revalidation while it is shown: gather the
   * set again, keeping the selection if it is still there. */
  function actualizarMapa() {
    if (!vivo || !vista) return;
    paginaObsoleta = true;
    conjunto = { ...conjunto, obsoleto: true, error: null, errorDe: null };
    pintarMapa();
  }

  /** "Actualizar" on the grid, or a revalidation while it is shown: reload its
   * page, and gather the map's set again the next time the map is shown. */
  function actualizarTabla() {
    if (conjunto.clave) conjunto = { ...conjunto, obsoleto: true };
    return recargar();
  }

  /** Whether a row, as it is now, still belongs in this view's list. */
  function fueraDeLaVista(fila) {
    return vista === VISTA_SIN_ASIGNAR ? Boolean(fila.base_id) : !esGlobal(vista) && fila.base_id !== vista;
  }

  /* This table's own writes keep the map's set current without gathering it
   * again. A set kept for another query (the filters moved since) cannot be
   * patched, so it is marked stale; a set being gathered is gathered again.
   * Under a search or a filter on the terrain's own fields, whether an edited
   * or created row still belongs is the server's query to say, not this
   * table's: such a write drops the set, and it is gathered again when the
   * map is shown. Without those, only the base decides. */
  const filtraPorCampos = () =>
    Boolean(consulta.q.trim() || consulta.estado || consulta.municipio || consulta.tipo_terreno);
  function descartarConjunto() {
    olvidarConjunto();
    pintarMapa();
  }
  function anotarEscritura() {
    if (conjunto.clave && !conjuntoVigente()) conjunto = { ...conjunto, obsoleto: true };
    if (reunion) reunion = { ...reunion, cambiado: true };
  }
  function cambiarConjunto(filas, total = conjunto.total) {
    conjunto = { ...conjunto, filas, total };
    if (modo === "mapa") entregarAlMapa();
    pintarAvisoMapa();
  }
  function reemplazarEnConjunto(terreno, { campos = true } = {}) {
    anotarEscritura();
    if (!filaDelConjunto(terreno.id)) return;
    if (campos && filtraPorCampos()) { descartarConjunto(); return; }
    if (fueraDeLaVista(terreno)) { quitarDelConjunto(terreno.id); return; }
    cambiarConjunto(conjunto.filas.map((t) => (t.id === terreno.id ? terreno : t)));
  }
  function quitarDelConjunto(id) {
    anotarEscritura();
    if (!filaDelConjunto(id)) return;
    if (seleccion === id && !filaDe(id)) seleccion = null;
    cambiarConjunto(conjunto.filas.filter((t) => t.id !== id), Math.max(0, conjunto.total - 1));
  }
  function agregarAlConjunto(terreno) {
    anotarEscritura();
    if (!conjuntoVigente() || filaDelConjunto(terreno.id)) return;
    if (filtraPorCampos()) { descartarConjunto(); return; }
    cambiarConjunto([terreno, ...conjunto.filas], conjunto.total + 1);
  }

  function marcarSeleccion() {
    for (const tr of tbody.querySelectorAll("tr.is-seleccionada")) {
      tr.classList.remove("is-seleccionada");
      tr.removeAttribute("aria-selected");
    }
    const tr = seleccion && tbody.querySelector(`tr[data-id="${CSS.escape(seleccion)}"]`);
    if (tr) { tr.classList.add("is-seleccionada"); tr.setAttribute("aria-selected", "true"); }
    return tr || null;
  }

  /** One selected terrain, by id, in the table and on the map. Choosing it on
   * the map marks its row if it is on the grid's page; the page itself stays. */
  function seleccionar(id, { desdeMapa = false } = {}) {
    if (!vivo || !existe(id)) return;
    const cambio = id !== seleccion;
    seleccion = id;
    const tr = marcarSeleccion();
    if (desdeMapa) { if (modo === "tabla") tr?.scrollIntoView({ block: "nearest", inline: "nearest" }); }
    else if (cambio && modo === "mapa") previa.seleccionar(id);
  }

  /** The widgets arrived after rows were drawn: mount them where the
   * placeholders are. Only file cells are touched. */
  function remontarRanuras() {
    apartarRanuras();
    for (const t of pagina.filas) {
      const tr = tbody.querySelector(`tr[data-id="${CSS.escape(t.id)}"]`);
      for (const c of columnas) {
        if (c.tipo !== "archivo" || !tr) continue;
        tr.querySelector(`td[data-col="${CSS.escape(c.id)}"]`)?.replaceWith(Celda(t, c, filaEditable(t)));
      }
    }
    vigilarApartadas();
  }

  /* ---------------------------------------------------- busy file mounts */

  const claveRanura = (id, tipo) => `${id}|${tipo}`;

  /** Before a repaint: keep the mounts whose upload is unfinished, end the rest. */
  function apartarRanuras() {
    for (const r of ranuras) {
      if (r.ocupado?.()) {
        apartadas.set(claveRanura(r.terrenoId, r.tipo), r);
        porPintar.add(claveRanura(r.terrenoId, r.tipo));
      } else r.destroy();
    }
    ranuras = [];
  }

  /** Leaving the view or the scope: every mount ends, busy or not. */
  function soltarRanuras() {
    for (const r of ranuras) r.destroy();
    ranuras = [];
    for (const r of apartadas.values()) r.destroy();
    apartadas.clear();
    porPintar.clear();
    clearInterval(vigiaApartadas);
    vigiaApartadas = null;
    pintarApartadas();
  }

  /** A set-aside mount for this cell, put back in the new row. */
  function recuperarRanura(t, c, editable) {
    const r = apartadas.get(claveRanura(t.id, c.archivo));
    if (!r) return null;
    apartadas.delete(claveRanura(t.id, c.archivo));
    porPintar.delete(claveRanura(t.id, c.archivo));
    r.update({ soloLectura: !editable, resumen: t.archivos ?? undefined });
    ranuras.push(r);
    return r.container;
  }

  /* Mounts left out of the new rows (their terrain is on another page or out
   * of the filters) keep sending while they are active; once they stop they
   * are released, and the server keeps the unfinished version. Called after a
   * paint: what that paint did not put back is decided now. A mount set aside
   * by a reload still on its way waits for that paint (porPintar). */
  function vigilarApartadas() {
    porPintar.clear();
    const revisar = () => {
      for (const [k, r] of apartadas) {
        if (!porPintar.has(k) && !r.activo?.()) { r.destroy(); apartadas.delete(k); }
      }
      if (!apartadas.size) { clearInterval(vigiaApartadas); vigiaApartadas = null; }
      pintarApartadas();
    };
    revisar();
    if (apartadas.size && !vigiaApartadas) vigiaApartadas = setInterval(() => { if (vivo) revisar(); }, 1000);
  }

  function pintarApartadas() {
    const n = [...apartadas.keys()].filter((k) => !porPintar.has(k)).length;
    avisoSubidas.hidden = !n;
    avisoSubidas.textContent = n ? `${n === 1 ? "Una subida sigue" : `${n} subidas siguen`} en curso para ` +
      `${n === 1 ? "un terreno que no está" : "terrenos que no están"} en esta página. Al terminar, su resumen ` +
      "se actualiza cuando vuelvas a verlo." : "";
  }

  /**
   * A widget changed a terrain's files (upload, activation, retirement), or
   * was refused a write. Refresh that terrain once however many reports arrive
   * while the request is out. The row's version, draft and custom values stay
   * as the table has them: this answer may be older than a cell save still in
   * flight. Only what the files and the permissions depend on is taken.
   */
  async function refrescarArchivos(id) {
    if (!vivo || !existe(id)) return;
    if (refrescos.has(id)) { refrescos.set(id, "repetir"); return; }
    const gen = generacion;
    try {
      do {
        refrescos.set(id, "pedido");
        const { terreno } = await api.inventarioTerreno(id);
        if (!vivo || gen !== generacion) return;
        aplicarArchivos(terreno);
      } while (refrescos.get(id) === "repetir");
    } catch (error) {
      if (!vivo || gen !== generacion) return;
      if (error.status === 404) alcanceDeArchivoPerdido(id);
      else alerta.textContent = `No se pudo actualizar los archivos del terreno: ${error.message}`;
    } finally {
      if (gen === generacion) refrescos.delete(id);
    }
  }

  /** Whether the row has work of the person's that removing it would lose. */
  const conTrabajo = (id) => editando?.id === id || [...celdas.keys()].some((k) => k.startsWith(`${id}|`));

  /**
   * Take from a fresh record its files, its location and which base it is in.
   * The base decides whether the row belongs in this view; it is taken only
   * from an answer at least as new as the row (an older one could undo a
   * transfer this table already knows about). Nothing else of the row is
   * replaced and no cell with an editor or an unresolved change is repainted.
   */
  function aplicarArchivos(terreno) {
    // The map's set takes the same fields under the same rule, whether or not
    // the terrain is on the grid's page.
    const enMapa = filaDelConjunto(terreno.id);
    if (enMapa) {
      // Files, location and base only: no field a search or filter reads.
      reemplazarEnConjunto({
        ...enMapa, archivos: terreno.archivos, ubicacion: terreno.ubicacion,
        ...(terreno.version >= enMapa.version ? { base_id: terreno.base_id ?? null } : {}),
      }, { campos: false });
    }
    const actual = filaDe(terreno.id);
    if (!actual) return;
    const vigente = terreno.version >= actual.version;
    const fila = {
      ...actual, archivos: terreno.archivos, ubicacion: terreno.ubicacion,
      ...(vigente ? { base_id: terreno.base_id ?? null } : {}),
    };
    const cambioDeEstado = fila.base_id !== actual.base_id;
    pagina.filas = pagina.filas.map((t) => (t.id === fila.id ? fila : t));
    if (cambioDeEstado && !conTrabajo(fila.id) && fueraDeLaVista(fila)) {
      // As when this person transfers it: it leaves a view it no longer belongs to.
      quitarFila(fila.id);
      toast("Ese terreno se movió a otra base y ya no está en esta vista.");
      return;
    }
    if (cambioDeEstado) pintarFila(fila.id);     // cell by cell; an open editor stays as it is
    else {
      const editable = filaEditable(fila);
      for (const r of ranuras) {
        if (r.terrenoId === fila.id) r.update({ soloLectura: !editable, resumen: fila.archivos ?? undefined });
      }
    }
    permisosDelDetalle(fila);
  }

  /** The open detail, if it is this terrain's, learns what may be changed now. */
  function permisosDelDetalle(t) {
    if (detalleAbierto?.terrenoId !== t.id) return;
    detalleAbierto.permisos({ puedeCambiar: puedeCambiarFila(t), resumen: t.archivos });
  }

  /**
   * The view's own write permission moved (the application's read-only mode): every row, file mount and the open detail
   * follow. Rows are repainted cell by cell, so an open editor and what is
   * unresolved in the tray stay exactly as they are.
   */
  function aplicarPermisos() {
    pintarPermisos();
    for (const t of pagina.filas) pintarFila(t.id);
    const abierto = detalleAbierto && filaDe(detalleAbierto.terrenoId);
    if (abierto) permisosDelDetalle(abierto);
  }

  /** The terrain a widget was working on is no longer in this account's
   * scope: drop it and look at the bases again; do not just say so. */
  function alcanceDeArchivoPerdido(id) {
    quitarFila(id);
    toastError("Ese terreno ya no está en esta vista.");
    refrescarBases();
  }

  /**
   * A write was refused but reading is still allowed. Ask the server for
   * exactly what the refusal names and apply it; nothing is assumed about the
   * session and no row is dropped on the widget's word alone.
   */
  function sinPermisoDeEscritura(id, codigo, mensaje) {
    toastError(mensaje || "Ya no se puede cambiar este terreno.");
    refrescarArchivos(id);                                  // the record and its base
    if (codigo === "forbidden") onRevalidar?.();            // the role and the read-only mode
  }

  function errorDeArchivo(id, { codigo, mensaje }) {
    if (!vivo) return;
    if (codigo === "404" || codigo === "not_found" || codigo === "no_encontrado") {
      // A deleted file is a 404 too: the record decides whether the terrain left the view.
      refrescarArchivos(id);
      return;
    }
    if (SIN_ESCRITURA.has(codigo)) {
      sinPermisoDeEscritura(id, codigo, mensaje);
      return;
    }
    toastError(mensaje || "No se pudo completar la operación con el archivo.");
  }

  const clasesDeFila = (t) => ["tabla-fila", nuevos.has(t.id) && "is-nueva"]
    .filter(Boolean).join(" ");

  function CabeceraDeFila(t, indice) {
    const nombre = t.draft?.terreno || "sin nombre";
    return el("th", { scope: "row", class: "tabla-th-fila" },
      puedeMarcar() && el("input", {
        type: "checkbox", class: "tabla-marca", dataset: { id: t.id }, checked: marcados.has(t.id),
        "aria-label": `Seleccionar terreno ${nombre}, fila ${indice + 1}`,
        onchange: (e) => { marcar(t, e.target.checked); pintarCasillas(); },
      }),
      el("button", {
        type: "button", class: "icon-btn tabla-abrir", "aria-label": `Abrir terreno ${nombre}, fila ${indice + 1}`,
        title: "Detalle, historial, transferir y borrar", onclick: () => detalle(t.id),
      }, "⋯"),
      nuevos.has(t.id) && el("span", { class: "chip tabla-chip" }, "Nuevo"),
    );
  }

  function Fila(t, indice) {
    const editable = filaEditable(t);
    const tr = el("tr", { class: clasesDeFila(t), dataset: { id: t.id } }, CabeceraDeFila(t, indice));
    for (const c of columnas) tr.append(Celda(t, c, editable));
    return tr;
  }

  function Celda(t, c, editable) {
    if (c.tipo === "archivo") {
      const conservada = recuperarRanura(t, c, editable);
      if (conservada) return conservada;
      const td = el("td", { class: "tabla-celda tabla-celda-archivo", dataset: { col: c.id } });
      ranuras.push(montarRanura({
        container: td, terrenoId: t.id, tipo: c.archivo, soloLectura: !editable,
        resumen: t.archivos ?? undefined,
        onCambio: (e) => refrescarArchivos(e.terrenoId),
        onError: (e) => errorDeArchivo(t.id, e),
      }));
      return td;
    }
    if (c.tipo === "base") {
      const base = t.base_id ? baseDe(t.base_id) : null;
      return el("td", { class: "tabla-celda", dataset: { col: c.id }, tabindex: "0" },
        t.base_id ? (base?.nombre ?? "—") : "Sin asignar");
    }
    const pendiente = celdas.get(clave(t.id, c.id));
    // A conflict shows the row as it is now; the person's own text waits in the tray.
    const texto = pendiente && pendiente.estado !== "conflicto" ? pendiente.texto : textoDe(valorDe(t, c), c);
    return el("td", {
      class: ["tabla-celda", `tabla-col-${c.tipo}`, pendiente && `is-${pendiente.estado}`,
        !editable && "is-lectura"],
      dataset: { col: c.id }, tabindex: "0",
      "aria-readonly": editable ? null : "true",
      "aria-busy": pendiente?.estado === "pendiente" ? "true" : null,
      "aria-invalid": pendiente?.estado === "error" ? "true" : null,
      title: pendiente?.mensaje ?? null,
    }, texto, pendiente && el("span", { class: "tabla-marca" }, ` (${ESTADOS[pendiente.estado]})`));
  }

  function celdaDom(id, colId) {
    return tbody.querySelector(`tr[data-id="${CSS.escape(id)}"] td[data-col="${CSS.escape(colId)}"]`);
  }

  function enfocar(id, colId) {
    const nodo = celdaDom(id, colId);
    if (nodo) nodo.focus({ preventScroll: false });
    return Boolean(nodo);
  }

  /**
   * Repaint one row in place, cell by cell. The cell whose editor is open is
   * left exactly as it is: another cell's save, conflict or error coming back
   * must not take away what is being typed, its selection or its focus. The
   * file mounts stay too; they are told about read-only changes.
   */
  function pintarFila(id) {
    const tr = tbody.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
    const t = filaDe(id);
    if (!tr) return;
    const mias = new Map(ranuras.filter((r) => tr.contains(r.container)).map((r) => [r.container, r]));
    if (!t) {
      for (const r of mias.values()) r.destroy();
      ranuras = ranuras.filter((r) => !mias.has(r.container));
      if (editando?.id === id) editando = null;
      tr.remove();
      return;
    }
    const abierta = editando?.id === id ? editando.col.id : null;
    const tenia = !abierta && tr.contains(document.activeElement) ? foco : null;
    const editable = filaEditable(t);
    tr.className = clasesDeFila(t);
    tr.firstElementChild.replaceWith(CabeceraDeFila(t, pagina.filas.indexOf(t)));
    for (const c of columnas) {
      const previa = tr.querySelector(`td[data-col="${CSS.escape(c.id)}"]`);
      if (!previa || c.id === abierta) continue;
      if (c.tipo === "archivo") mias.get(previa)?.update({ soloLectura: !editable, resumen: t.archivos ?? undefined });
      else previa.replaceWith(Celda(t, c, editable));
    }
    if (tenia && tenia.id === id) enfocar(id, tenia.colId);
    if (id === seleccion) marcarSeleccion();
  }

  function pintarBandeja() {
    const items = [];
    if (creacion?.estado === "incierto") {
      items.push(el("li", { class: "tabla-pendiente" },
        el("span", {}, "No se confirmó si el terreno en blanco se creó. Reintentar no lo duplica."),
        el("button", { type: "button", class: "btn btn-small", onclick: () => agregar() }, "Reintentar"),
        el("button", { type: "button", class: "btn btn-small btn-quiet", onclick: () => { creacion = null; pintarBandeja(); pintarPermisos(); } },
          "Descartar"),
      ));
    }
    for (const [k, c] of celdas) {
      if (c.estado === "pendiente") continue;
      const [id, colId] = k.split("|");
      const t = filaDe(id);
      const col = colDe(colId);
      if (!t || !col) continue;
      const donde = `${col.etiqueta} · ${t.draft?.terreno || "terreno sin nombre"}`;
      const tuyo = el("span", { class: "tabla-tuyo" }, `Tu valor: «${c.texto}»`);
      const descartar = el("button", {
        type: "button", class: "btn btn-small btn-quiet",
        onclick: () => { celdas.delete(k); pintarFila(id); pintarBandeja(); enfocar(id, colId); },
      }, "Descartar el mío");
      if (c.estado === "conflicto") {
        items.push(el("li", { class: "tabla-pendiente is-conflicto" },
          el("strong", {}, donde),
          el("span", {}, ` — Otra persona guardó cambios en este terreno. Valor actual: «${textoDe(valorDe(t, col), col)}». `),
          tuyo,
          el("button", { type: "button", class: "btn btn-small", onclick: () => guardar(id, col, c.valor, c.texto) },
            "Guardar el mío"),
          descartar));
      } else if (c.estado === "incierto") {
        items.push(el("li", { class: "tabla-pendiente" },
          el("strong", {}, donde),
          el("span", {}, " — No se confirmó si se guardó. "), tuyo,
          el("button", { type: "button", class: "btn btn-small", onclick: () => comprobar(id, col) }, "Comprobar"),
          descartar));
      } else {
        items.push(el("li", { class: "tabla-pendiente is-error" },
          el("strong", {}, donde), el("span", {}, ` — ${c.mensaje} `), tuyo,
          el("button", { type: "button", class: "btn btn-small", onclick: () => editar(id, colId) }, "Corregir"),
          descartar));
      }
    }
    bandeja.replaceChildren(...(items.length
      ? [el("h2", { class: "tabla-bandeja-titulo" }, "Cambios sin resolver"), el("ul", {}, items)] : []));
    bandeja.hidden = !items.length || !vista;
  }

  /* -------------------------------------------------------------- editing */

  function editar(id, colId, { reemplazo = null } = {}) {
    if (editando) confirmar();
    const t = filaDe(id);
    const col = colDe(colId);
    const td = celdaDom(id, colId);
    if (!t || !col || !td || !esEditable(col) || !filaEditable(t)) return;
    if (celdas.get(clave(id, colId))?.estado === "pendiente") return;
    const previo = celdas.get(clave(id, colId));
    const inicial = textoDe(valorDe(t, col), col);
    const texto = reemplazo ?? previo?.texto ?? inicial;
    const etiqueta = `${col.etiqueta}, ${t.draft?.terreno || "terreno sin nombre"}`;
    let campo;
    if (col.tipo === "opcion") {
      const opciones = col.opciones.includes(texto) || texto === "" ? col.opciones : [...col.opciones, texto];
      campo = el("select", { class: "tabla-editor", "aria-label": etiqueta },
        opcion("", "— sin valor —", texto === ""), opciones.map((o) => opcion(o, o, o === texto)));
    } else if (col.tipo === "largo") {
      campo = el("textarea", { class: "tabla-editor", rows: "3", "aria-label": etiqueta });
      campo.value = texto;
    } else {
      campo = el("input", {
        class: "tabla-editor", "aria-label": etiqueta, type: col.tipo === "fecha" ? "date" : "text",
        inputmode: col.tipo === "numero" ? "decimal" : null, autocomplete: "off", spellcheck: "false",
      });
      campo.value = texto;
      if (col.tipo === "numero") {
        // Commas and the $ or % appear as the number is typed.
        const formatear = () => {
          const { texto: nuevo, cursor } = escribirNumero(col, campo.value, campo.selectionStart ?? campo.value.length);
          if (nuevo !== campo.value) { campo.value = nuevo; campo.setSelectionRange(cursor, cursor); }
        };
        campo.addEventListener("input", formatear);
        if (reemplazo != null) formatear();
      }
    }
    editando = { id, col, campo, inicial };
    td.classList.add("is-editando");
    td.replaceChildren(campo);
    // Deferred: the click that took the focus away lands on its target first,
    // so repainting this row does not swallow it.
    campo.addEventListener("blur", () => setTimeout(() => { if (vivo && editando?.campo === campo) confirmar(); }, 0));
    campo.focus();
    if (reemplazo == null) campo.select?.();
    else if (col.tipo !== "numero") campo.setSelectionRange?.(texto.length, texto.length);
  }

  /** Leave the editor without saving. What was stored stays as it was. */
  function cancelar() {
    if (!editando) return;
    const { id, col } = editando;
    editando = null;
    pintarFila(id);
    enfocar(id, col.id);
    decir("Edición cancelada.");
  }

  /** Close the editor and save what it holds, if it changed and is valid. */
  function confirmar() {
    if (!editando) return;
    const { id, col, campo, inicial } = editando;
    editando = null;
    const texto = campo.value;
    const t = filaDe(id);
    const k = clave(id, col.id);
    if (!t) return;
    const leido = leerCelda(col, texto);
    if (leido.error) {
      celdas.set(k, { estado: "error", texto, mensaje: leido.error });
      alerta.textContent = `${col.etiqueta}: ${leido.error}`;
    } else if ((leido.valor ?? null) === (valorDe(t, col) ?? null)) {
      celdas.delete(k);
    } else if (textoDe(valorDe(t, col), col) !== inicial) {
      // The row was refreshed while this editor was open and THIS cell is no
      // longer what the person started from. Saving at the row's new version
      // would overwrite someone else's value unseen: show both and let them choose.
      celdas.set(k, { estado: "conflicto", valor: leido.valor, texto: textoDe(leido.valor, col) });
      alerta.textContent = `${col.etiqueta}: este valor cambió mientras lo editabas. El tuyo no se guardó ni se perdió.`;
    } else {
      guardar(id, col, leido.valor, textoDe(leido.valor, col));
      return;
    }
    pintarFila(id);
    pintarBandeja();
  }

  function guardar(id, col, valor, texto) {
    const k = clave(id, col.id);
    const gen = generacion;
    celdas.set(k, { estado: "pendiente", valor, texto });
    alerta.textContent = "";
    pintarFila(id);
    pintarBandeja();
    decir("Guardando…");
    const turno = cola.enFila(id, async () => {
      const t = filaDe(id);
      if (!vivo || gen !== generacion || !t) return;
      const version = t.version;
      try {
        const { terreno } = await api.guardarCelda(id, cuerpoDeCelda(col, valor, version));
        if (!vivo || gen !== generacion) return;
        celdas.delete(k);
        reemplazar(terreno);
        decir(`Guardado · ${col.etiqueta} · versión ${terreno.version}.`);
      } catch (error) {
        if (!vivo || gen !== generacion) return;
        fallo(error, id, col, { valor, texto, version });
      }
    });
    enVuelo.add(turno);
    turno.finally(() => { enVuelo.delete(turno); });
  }

  function reemplazar(terreno) {
    reemplazarEnConjunto(terreno);
    const i = pagina.filas.findIndex((t) => t.id === terreno.id);
    if (i < 0) return;
    pagina.filas = pagina.filas.map((t, n) => (n === i ? terreno : t));
    pintarFila(terreno.id);
    pintarBandeja();
    permisosDelDetalle(terreno);
  }

  function quitarFila(id) {
    closeAllDialogs();   // its detail, history or transfer may be open
    for (const k of [...celdas.keys()]) if (k.startsWith(`${id}|`)) celdas.delete(k);
    const enPagina = Boolean(filaDe(id));
    pagina.filas = pagina.filas.filter((t) => t.id !== id);
    if (enPagina) pagina.total = Math.max(0, pagina.total - 1);
    quitarDelConjunto(id);
    if (seleccion === id) seleccion = null;
    marcados.delete(id);
    pintarFila(id);
    pintarCuenta();
    pintarLote();
    pintarBandeja();
  }

  function fallo(error, id, col, enviado) {
    const k = clave(id, col.id);
    decir("");
    const codigo = error.detalle?.code;
    if (error.status === 409 && codigo === "conflict" && error.detalle?.terreno) {
      celdas.set(k, { estado: "conflicto", ...enviado });
      reemplazar(error.detalle.terreno);
      alerta.textContent = `${col.etiqueta}: otra persona guardó cambios en este terreno. Tu valor no se perdió.`;
      return;
    }
    if (error.status === 404) {
      const habia = [...celdas.keys()].some((x) => x.startsWith(`${id}|`));
      quitarFila(id);
      toastError("Un terreno ya no está en esta vista (se movió, o cambió tu acceso)." +
        (habia ? " Lo que estabas escribiendo para él se descartó." : ""));
      return;
    }
    if (error.status === 403 && codigo === "forbidden") {
      alcancePerdido("Tu cuenta ya no puede editar aquí.", { permisos: true });
      return;
    }
    if (error.red) {
      celdas.set(k, { estado: "incierto", ...enviado });
      alerta.textContent = `${col.etiqueta}: no hubo respuesta del servidor. Comprueba antes de reintentar.`;
    } else {
      const campos = error.detalle?.fields ?? {};
      const mensaje = campos[col.custom ? col.id : col.campo] ?? Object.values(campos)[0] ?? error.message;
      celdas.set(k, { estado: "error", ...enviado, mensaje });
      alerta.textContent = `${col.etiqueta}: ${mensaje}`;
    }
    pintarFila(id);
    pintarBandeja();
  }

  /** An unanswered save: look at the row before deciding anything. */
  async function comprobar(id, col) {
    const k = clave(id, col.id);
    const c = celdas.get(k);
    const gen = generacion;
    if (!c || c.estado !== "incierto") return;
    decir("Comprobando…");
    try {
      const { terreno } = await api.inventarioTerreno(id);
      if (!vivo || gen !== generacion) return;
      const resultado = resolverIncierto(col, c.valor, c.version, terreno);
      if (resultado === "guardado") {
        celdas.delete(k);
        reemplazar(terreno);
        decir("Sí se había guardado.");
      } else if (resultado === "sin_guardar") {
        reemplazar(terreno);
        guardar(id, col, c.valor, c.texto);
      } else {
        celdas.set(k, { ...c, estado: "conflicto" });
        reemplazar(terreno);
        alerta.textContent = `${col.etiqueta}: el terreno cambió mientras tanto. Decide qué valor queda.`;
      }
    } catch (error) {
      if (!vivo || gen !== generacion) return;
      if (error.status === 404) quitarFila(id);
      else alerta.textContent = `No se pudo comprobar: ${error.message}`;
    }
  }

  const FLECHAS = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] };

  function alTeclear(e) {
    const td = e.target.closest("td[data-col]");
    if (!td) return;
    const id = td.parentNode.dataset.id;
    const colId = td.dataset.col;
    if (editando && e.target === editando.campo) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancelar(); }
      else if (e.key === "Enter" && !(editando.col.tipo === "largo" && e.shiftKey)) {
        // Saves and goes down a row, as in a spreadsheet.
        e.preventDefault();
        confirmar();
        mover(id, colId, 0, 1) || enfocar(id, colId);
      } else if (FLECHAS[e.key] && !e.shiftKey && !["opcion", "fecha", "largo"].includes(editando.col.tipo)) {
        // In a one-line text or number editor the arrows save and move; a
        // choice, a date and a comment keep them for their own control.
        e.preventDefault();
        confirmar();
        mover(id, colId, ...FLECHAS[e.key]) || enfocar(id, colId);
      } else if (e.key === "Tab") {
        e.preventDefault();
        confirmar();
        mover(id, colId, e.shiftKey ? -1 : 1, 0) || enfocar(id, colId);
      }
      return;
    }
    if (e.target !== td) return;
    const pasos = FLECHAS[e.key];
    if (pasos) { e.preventDefault(); mover(id, colId, pasos[0], pasos[1]); return; }
    if (e.key === "Enter" || e.key === "F2") { e.preventDefault(); editar(id, colId); return; }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && e.key !== " ") {
      const col = colDe(colId);
      // Typing replaces the value, as in a spreadsheet; a choice or a date opens its control.
      if (col && esEditable(col) && col.tipo !== "opcion" && col.tipo !== "fecha") {
        e.preventDefault();
        editar(id, colId, { reemplazo: e.key });
      }
    }
  }

  /** Move the focus by cells; sideways moves wrap to the next or previous row. */
  function mover(id, colId, dx, dy) {
    const celdasDeFila = (tr) => [...tr.querySelectorAll("td[tabindex]")];
    let tr = tbody.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
    if (!tr) return false;
    let lista = celdasDeFila(tr);
    let i = lista.findIndex((n) => n.dataset.col === colId);
    if (dy) {
      tr = dy > 0 ? tr.nextElementSibling : tr.previousElementSibling;
      if (!tr) return false;
      lista = celdasDeFila(tr);
      const misma = lista.find((n) => n.dataset.col === colId);
      (misma ?? lista[Math.min(i, lista.length - 1)])?.focus();
      return true;
    }
    i += dx;
    if (i < 0 || i >= lista.length) {
      tr = dx > 0 ? tr.nextElementSibling : tr.previousElementSibling;
      if (!tr) return false;
      lista = celdasDeFila(tr);
      i = dx > 0 ? 0 : lista.length - 1;
    }
    lista[i]?.focus();
    return Boolean(lista[i]);
  }

  /* --------------------------------------------------------------- create */

  /** A blank terrain. Its Idempotency-Key is kept until the outcome is known,
   * so an unanswered request is repeated with the same key and never doubles. */
  async function agregar() {
    if (!vista || vistaSoloLectura() || creacion?.estado === "enviando") return;
    const gen = generacion;
    creacion = { clave: creacion?.clave ?? nuevaClave(), estado: "enviando" };
    pintarPermisos();
    pintarBandeja();
    decir("Agregando un terreno en blanco…");
    try {
      const { terreno } = await api.tablaCrear(rutaDeLista(vista), creacion.clave);
      if (!vivo || gen !== generacion) return;
      creacion = null;
      if (!filaDe(terreno.id)) {
        nuevos.add(terreno.id);
        pagina.filas = [terreno, ...pagina.filas].slice(0, consulta.limit);   // the page stays bounded
        pagina.total += 1;
      }
      agregarAlConjunto(terreno);
      pintarTodo();
      enfocar(terreno.id, columnas[1].id);
      decir("Terreno en blanco agregado. Está al principio de esta página.");
    } catch (error) {
      if (!vivo || gen !== generacion) return;
      if (error.red) {
        creacion = { ...creacion, estado: "incierto" };
        alerta.textContent = "No hubo respuesta al crear el terreno. Reintentar no lo duplica.";
      } else if (error.status === 404 || error.status === 403) {
        creacion = null;
        alcancePerdido("Ya no puedes agregar terrenos en esa vista.");
        return;
      } else {
        creacion = null;
        alerta.textContent = `No se pudo agregar el terreno: ${error.message}`;
      }
      pintarPermisos();
      pintarBandeja();
    }
  }

  /* -------------------------------------------------------------- dialogs */

  async function refrescarBases() {
    if (!(await cargarBases())) return;
    pintarMarco();
    if (vista && !vistaValida(vista)) alcancePerdido("Esa base ya no está disponible.");
    else if (vista) aplicarPermisos();
  }

  // Focus goes back to the row a dialog was opened from only if nothing else
  // has it: a dialog's `close` event arrives a task after it closes, and by
  // then the person may already be in another cell or typing in an editor.
  const volverA = (id, colId) => () => {
    const libre = !document.activeElement || document.activeElement === document.body;
    if (vivo && libre) enfocar(id, colId ?? columnas[1].id);
  };

  function detalle(id) {
    const t = filaDe(id);
    if (!t) return;
    const regresar = volverA(id, foco?.id === id ? foco.colId : null);
    const abierto = abrirDetalle({
      terreno: t, columnas, base: t.base_id ? baseDe(t.base_id) : null, admin,
      puedeCambiar: puedeCambiarFila(t),
      onCerrar: () => { if (detalleAbierto === abierto) detalleAbierto = null; regresar(); },
      onArchivos: (e) => refrescarArchivos(e.terrenoId),
      onErrorDeArchivos: (e) => errorDeArchivo(id, e),
      onHistorial: () => openTerrainHistory({ id: t.id, nombre: t.draft?.terreno }),
      onBorrar: () => borrar(id),
      onTransferir: () => abrirTransferencia({
        terreno: filaDe(id) ?? t, bases,
        onHecho: (movido) => transferido(movido), onConflicto: (actual) => reemplazar(actual),
      }),
    });
    detalleAbierto = abierto;
  }

  async function borrar(id) {
    const t = filaDe(id);
    const gen = generacion;
    if (!t) return;
    try {
      await api.borrarTerreno(id, t.version);
      if (!vivo || gen !== generacion) return;
      toast("Terreno borrado.");
      quitarFila(id);
    } catch (error) {
      if (!vivo || gen !== generacion) return;
      if (error.status === 409 && error.detalle?.terreno) {
        reemplazar(error.detalle.terreno);
        toastError("Otra persona cambió este terreno. Revisa la fila actualizada y vuelve a intentarlo.");
      } else if (error.status === 404) {
        quitarFila(id);
        toastError("Ese terreno ya no está en esta vista.");
      } else toastError(error.message);
    }
  }

  function transferido(terreno) {
    toast("Terreno transferido.");
    // In a base's list it has left; in the global table it stays, with its new base.
    if (esGlobal(vista) && !(vista === VISTA_SIN_ASIGNAR && terreno.base_id)) reemplazar(terreno);
    else quitarFila(terreno.id);
  }

  function columnasDialogo() {
    const base = baseActual();
    if (!base) return;
    abrirColumnas({
      base, soloLectura: vistaSoloLectura(),
      onCerrar: (cambio) => { if (vivo && cambio) recargar(); },
      onAlcancePerdido: () => alcancePerdido("Ya no tienes acceso a esa base."),
    });
  }

  function basesDialogo() {
    abrirBases({
      onCerrar: async (cambio) => {
        if (!vivo || !cambio) return;
        await refrescarBases();
        if (vista && vistaValida(vista)) recargar();
      },
    });
  }

  // Opt-in hook for browser checks (only with ?test=1, as in app.js): what
  // the preview holds and where a terrain is drawn. Never in normal use.
  if (new URLSearchParams(location.search).has("test")) {
    window.__araTabla = {
      previa: () => previa.estado, posicion: (id) => previa.posicionDe(id),
      mapa: () => ({ modo, clave: conjunto.clave, filas: conjunto.filas.map((t) => t.id), total: conjunto.total,
        incompleto: conjunto.incompleto, reuniendo: Boolean(reunion), seleccion }),
    };
  }

  /* ------------------------------------------------------------ lifecycle */

  abrir(vistaInicial, { forzar: true });

  return {
    element,
    get dirty() { return sucio(); },
    /** Unfinished uploads of this session's file widgets: logging out would stop them. */
    get subiendo() { return archivos.pendientes(); },
    get vista() { return vista; },
    abrir,
    /** The application's read-only mode became known or changed. */
    permisos() {
      if (!vivo || !vista) return;
      if (editando) aplicarPermisos();     // an open editor is not rebuilt under the person
      else { pintarTodo(); const t = detalleAbierto && filaDe(detalleAbierto.terrenoId); if (t) permisosDelDetalle(t); }
    },
    /** Look again when the window regains attention, unless work is open. The
     * map gathers its set again; the hidden grid waits until it is shown. */
    revalidar() {
      if (!vivo || !vista || sucio() || editando || document.querySelector("dialog[open]")) return;
      if (modo === "mapa") actualizarMapa();
      else actualizarTabla();
    },
    get modo() { return modo; },
    mostrarComo,
    /** The shell put the table back on screen: the map measures its area again. */
    alMostrar() { if (vivo && modo === "mapa") previa.mostrar(); },
    /** The account is leaving (logout, expiry, another user): forget it all. */
    destroy() {
      vivo = false;
      limpiarAlcance();
      previa.destroy();
      archivos.destroy();          // widgets, loader, their requests and object URLs
      delete window.__araTabla;
      bases = [];
      element.remove();
    },
  };
}

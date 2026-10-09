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
 */

import { api } from "../../lib/api.js";
import { clear, el } from "../../lib/dom.js";
import { fmtCount } from "../../lib/format.js";
import { nuevaClave } from "../../lib/inventario.js";
import {
  columnasDe, CONSULTA_VACIA, consultaDeLista, crearCola, cuerpoDeCelda, esEditable, esGlobal,
  leerCelda, LIMITES, ORDENES, resolverIncierto, rutaDeLista, textoDe, valorDe, VISTA_MAESTRA,
  VISTA_SIN_ASIGNAR,
} from "../../lib/tabla.js";
import { openTerrainHistory } from "../inventory/TerrainHistory.js";
import { confirmDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";
import { abrirBases, abrirColumnas, abrirDetalle, abrirTransferencia } from "./dialogos.js";
import { montarRanura } from "./ranuraArchivos.js";

const BUSCAR_MS = 300;
const ESTADOS = {
  pendiente: "guardando", error: "sin guardar", conflicto: "en conflicto", incierto: "sin confirmar",
};

export function createTabla({ sesion, soloConsulta = () => false, vistaInicial = null, onVista, onPermisos }) {
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
  const chkArchivados = el("input", {
    id: "tabla-archivados", type: "checkbox",
    onchange: () => consultar({ incluirArchivados: chkArchivados.checked }),
  });
  const selLimite = el("select", {
    id: "tabla-limite", class: "input", onchange: () => consultar({ limit: Number(selLimite.value) }),
  }, LIMITES.map((n) => el("option", { value: n, selected: n === consulta.limit }, String(n))));

  const btnAgregar = el("button", { type: "button", class: "btn btn-principal", onclick: () => agregar() },
    "Agregar terreno");
  const btnColumnas = el("button", { type: "button", class: "btn btn-quiet", onclick: () => columnasDialogo() },
    "Columnas");
  const btnBases = admin && el("button", { type: "button", class: "btn btn-quiet", onclick: () => basesDialogo() },
    "Bases y accesos");
  const btnRecargar = el("button", { type: "button", class: "btn btn-quiet", onclick: () => recargar() },
    "Actualizar");

  const campoDe = (control, etiqueta) => el("div", { class: "tabla-campo" },
    el("label", { class: "field-label", for: control.id }, etiqueta), control);
  const casilla = (control, etiqueta) => el("label", { class: "check tabla-casilla", for: control.id }, control, etiqueta);

  const barra = el("div", { class: "tabla-barra" },
    campoDe(selVista, "Vista"),
    campoDe(buscar, "Buscar"),
    campoDe(selEstado, "Estado"),
    campoDe(selMunicipio, "Municipio"),
    campoDe(selTipo, "Tipo"),
    campoDe(selOrden, "Ordenar por"),
    casilla(chkDesc, "Descendente"),
    casilla(chkArchivados, "Incluir archivados"),
    el("div", { class: "tabla-acciones" }, btnAgregar, btnColumnas, btnBases, btnRecargar),
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
  const pie = el("div", { class: "tabla-pie" }, cuenta, campoDe(selLimite, "Filas por página"),
    btnAnterior, btnSiguiente, estado, alerta);

  const element = el("div", { class: "tabla-pantalla" }, barra, aviso, bandeja, lienzo, vacio, pie);

  tbody.addEventListener("focusin", (e) => {
    const celda = e.target.closest("td[data-col]");
    if (celda) foco = { id: celda.parentNode.dataset.id, colId: celda.dataset.col };
  });
  tbody.addEventListener("dblclick", (e) => {
    const celda = e.target.closest("td[data-col]");
    if (celda && !editando) editar(celda.parentNode.dataset.id, celda.dataset.col);
  });
  tbody.addEventListener("keydown", alTeclear);

  /* --------------------------------------------------------------- scope */

  const baseDe = (id) => bases.find((b) => b.id === id) ?? null;
  const baseActual = () => (esGlobal(vista) ? null : baseDe(vista));
  const vistaSoloLectura = () => soloConsulta() || Boolean(baseActual()?.archivada);
  const filaDe = (id) => pagina.filas.find((t) => t.id === id) ?? null;
  const colDe = (colId) => columnas.find((c) => c.id === colId) ?? null;
  const clave = (id, colId) => `${id}|${colId}`;
  const filaEditable = (t) => !vistaSoloLectura() && !t.archived_at;

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
    for (const r of ranuras) r.destroy();
    ranuras = [];
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
      columnas = columnasDe(VISTA_MAESTRA);
      thead.replaceChildren();
      for (const control of [selEstado, selMunicipio, selTipo]) control.replaceChildren();
      cuenta.textContent = "";
      estado.textContent = "";
    }
  }

  /** Let saves in flight finish, then ask before discarding what is unsaved. */
  async function puedeSalir() {
    if (editando) confirmar();
    if (enVuelo.size) {
      decir("Terminando de guardar…");
      await Promise.allSettled([...enVuelo]);
    }
    if (!vivo) return false;
    if (!sinResolver()) return true;
    return confirmDialog({
      titulo: "¿Descartar cambios sin guardar?",
      mensaje: "Hay celdas con cambios que no se guardaron. Si continúas, se pierden.",
      confirmar: "Descartar", peligro: true,
    });
  }

  async function cargarBases() {
    const gen = generacion;
    try {
      const respuesta = await api.maestraBases(admin);
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
    if (vista !== null && !(await puedeSalir())) {
      selVista.value = vista ?? "";
      onVista?.(vista);
      return;
    }
    limpiarAlcance();
    lienzo.setAttribute("aria-busy", "true");
    if (!basesListas) await cargarBases();
    if (!vivo) return;
    vista = vistaValida(pedida) ? pedida : vistaPorDefecto();
    consulta = { ...CONSULTA_VACIA, limit: consulta.limit };
    buscar.value = "";
    chkDesc.checked = false;
    chkArchivados.checked = false;
    selOrden.value = "id";
    pintarMarco();
    onVista?.(vista);
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
    chkArchivados.checked = consulta.incluirArchivados;
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
        esGlobal(vista) ? null : api.columnas(vista, false, signal),
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
    const deTrabajo = bases.map((b) => opcion(b.id, b.nombre + (b.archivada ? " · archivada" : ""), b.id === vista));
    opciones.push(admin ? el("optgroup", { label: "Bases de trabajo" }, deTrabajo) : deTrabajo);
    selVista.replaceChildren(...opciones.flat());
    selVista.value = vista ?? "";

    const sinAcceso = !vista;
    for (const nodo of [lienzo, pie, bandeja]) nodo.hidden = sinAcceso || (nodo === bandeja && !bandeja.childElementCount);
    for (const control of [buscar, selEstado, selMunicipio, selTipo, selOrden, chkDesc, chkArchivados, selVista]) {
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
    pintarPermisos();
  }

  function pintarPermisos() {
    const base = baseActual();
    const lectura = vistaSoloLectura();
    btnAgregar.hidden = !vista || lectura;
    btnAgregar.disabled = creacion?.estado === "enviando";
    btnColumnas.hidden = !vista || esGlobal(vista);
    btnRecargar.hidden = !vista;
    aviso.hidden = !(vista && lectura);
    aviso.textContent = soloConsulta()
      ? "ARA Map está en modo de solo consulta: no se puede editar."
      : base?.archivada ? "Esta base de trabajo está archivada: se puede consultar, no editar. " +
        "Un administrador puede restaurarla." : "";
  }

  function facetas(control, valores, actual, todos) {
    const lista = [...new Set([...(valores ?? []), ...(actual ? [actual] : [])])];
    control.replaceChildren(opcion("", todos, !actual), ...lista.map((v) => opcion(v, v, v === actual)));
  }

  function pintarTodo() {
    const tenia = tbody.contains(document.activeElement) && !editando ? foco : null;
    for (const r of ranuras) r.destroy();
    ranuras = [];
    pintarMarco();
    facetas(selEstado, pagina.facets.estados, consulta.estado, "Todos");
    facetas(selMunicipio, pagina.facets.municipios, consulta.municipio, "Todos");
    facetas(selTipo, pagina.facets.tipos, consulta.tipo_terreno, "Todos");

    thead.replaceChildren(el("tr", {},
      el("th", { scope: "col", class: "tabla-th tabla-th-fila" }, el("span", { class: "sr-only" }, "Terreno")),
      columnas.map((c) => el("th", {
        scope: "col", class: ["tabla-th", `tabla-col-${c.tipo}`], title: c.ayuda ?? null, "data-col": c.id,
      }, c.etiqueta, c.custom && el("span", { class: "tabla-th-tipo" }, ` · ${c.tipo}`))),
    ));
    tbody.replaceChildren(...pagina.filas.map((t, i) => Fila(t, i)));

    const desde = pagina.filas.length ? anteriores.length * consulta.limit + 1 : 0;
    cuenta.textContent = errorDeCarga ?? (pagina.total
      ? `${fmtCount(desde)}–${fmtCount(desde + pagina.filas.length - 1)} de ${fmtCount(pagina.total)}`
      : "Sin terrenos en esta vista");
    btnAnterior.disabled = !anteriores.length;
    btnSiguiente.disabled = !pagina.siguiente;
    if (errorDeCarga) alerta.textContent = errorDeCarga;
    pintarBandeja();
    if (tenia) enfocar(tenia.id, tenia.colId);
  }

  function Fila(t, indice) {
    const editable = filaEditable(t);
    const nombre = t.draft?.terreno || "sin nombre";
    const tr = el("tr", {
      class: ["tabla-fila", t.archived_at && "is-archivada", nuevos.has(t.id) && "is-nueva"],
      dataset: { id: t.id },
    },
      el("th", { scope: "row", class: "tabla-th-fila" },
        el("button", {
          type: "button", class: "icon-btn tabla-abrir", "aria-label": `Abrir terreno ${nombre}, fila ${indice + 1}`,
          title: "Detalle, historial, archivar y transferir", onclick: () => detalle(t.id),
        }, "⋯"),
        t.archived_at && el("span", { class: "chip tabla-chip" }, "Archivado"),
        nuevos.has(t.id) && el("span", { class: "chip tabla-chip" }, "Nuevo"),
      ),
    );
    for (const c of columnas) tr.append(Celda(t, c, editable));
    return tr;
  }

  function Celda(t, c, editable) {
    if (c.tipo === "archivo") {
      const td = el("td", { class: "tabla-celda tabla-celda-archivo", dataset: { col: c.id } });
      ranuras.push(montarRanura({
        container: td, terrenoId: t.id, tipo: c.archivo, soloLectura: !editable, resumen: undefined,
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
    const texto = pendiente && pendiente.estado !== "conflicto" ? pendiente.texto : textoDe(valorDe(t, c));
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

  /** Repaint one row, keeping the keyboard where it was. */
  function pintarFila(id) {
    const previa = tbody.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
    const t = filaDe(id);
    if (!previa) return;
    const tenia = previa.contains(document.activeElement) && !editando ? foco : null;
    const mias = new Set([...previa.querySelectorAll("td.tabla-celda-archivo")]);
    ranuras = ranuras.filter((r) => { if (mias.has(r.container)) { r.destroy(); return false; } return true; });
    if (!t) { previa.remove(); return; }
    previa.replaceWith(Fila(t, pagina.filas.indexOf(t)));
    if (tenia && tenia.id === id) enfocar(id, tenia.colId);
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
          el("span", {}, ` — Otra persona guardó cambios en este terreno. Valor actual: «${textoDe(valorDe(t, col))}». `),
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
    const inicial = textoDe(valorDe(t, col));
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
    }
    editando = { id, col, campo, inicial };
    td.classList.add("is-editando");
    td.replaceChildren(campo);
    // Deferred: the click that took the focus away lands on its target first,
    // so repainting this row does not swallow it.
    campo.addEventListener("blur", () => setTimeout(() => { if (vivo && editando?.campo === campo) confirmar(); }, 0));
    campo.focus();
    if (reemplazo == null) campo.select?.();
    else campo.setSelectionRange?.(texto.length, texto.length);
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
    const { id, col, campo } = editando;
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
    } else {
      guardar(id, col, leido.valor, textoDe(leido.valor));
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
    const i = pagina.filas.findIndex((t) => t.id === terreno.id);
    if (i < 0) return;
    pagina.filas = pagina.filas.map((t, n) => (n === i ? terreno : t));
    pintarFila(terreno.id);
    pintarBandeja();
  }

  function quitarFila(id) {
    for (const k of [...celdas.keys()]) if (k.startsWith(`${id}|`)) celdas.delete(k);
    pagina.filas = pagina.filas.filter((t) => t.id !== id);
    pagina.total = Math.max(0, pagina.total - 1);
    pintarFila(id);
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
      if (codigo === "base_archivada" || codigo === "terreno_archivado") refrescarBases();
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

  function alTeclear(e) {
    const td = e.target.closest("td[data-col]");
    if (!td) return;
    const id = td.parentNode.dataset.id;
    const colId = td.dataset.col;
    if (editando && e.target === editando.campo) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancelar(); }
      else if (e.key === "Enter" && !(editando.col.tipo === "largo" && e.shiftKey)) {
        e.preventDefault();
        confirmar();
        enfocar(id, colId);
      } else if (e.key === "Tab") {
        e.preventDefault();
        confirmar();
        mover(id, colId, e.shiftKey ? -1 : 1, 0) || enfocar(id, colId);
      }
      return;
    }
    if (e.target !== td) return;
    const pasos = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] }[e.key];
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
        if (error.detalle?.code === "base_archivada") refrescarBases();
      }
      pintarPermisos();
      pintarBandeja();
    }
  }

  /* -------------------------------------------------------------- dialogs */

  async function refrescarBases() {
    if (await cargarBases()) { pintarMarco(); if (vista && !vistaValida(vista)) alcancePerdido("Esa base ya no está disponible."); }
  }

  const volverA = (id, colId) => () => { if (vivo) enfocar(id, colId ?? columnas[1].id); };

  function detalle(id) {
    const t = filaDe(id);
    if (!t) return;
    const regresar = volverA(id, foco?.id === id ? foco.colId : null);
    abrirDetalle({
      terreno: t, columnas, base: t.base_id ? baseDe(t.base_id) : null, admin,
      puedeCambiar: !soloConsulta() && !(t.base_id && baseDe(t.base_id)?.archivada),
      onCerrar: regresar,
      onHistorial: () => openTerrainHistory({ id: t.id, nombre: t.draft?.terreno }),
      onArchivar: (restaurar) => archivar(id, restaurar),
      onTransferir: () => abrirTransferencia({
        terreno: filaDe(id) ?? t, bases: bases.filter((b) => !b.archivada),
        onHecho: (movido) => transferido(movido), onConflicto: (actual) => reemplazar(actual),
      }),
    });
  }

  async function archivar(id, restaurar) {
    const t = filaDe(id);
    const gen = generacion;
    if (!t) return;
    try {
      const { terreno } = await api.archivarTerreno(id, t.version, restaurar);
      if (!vivo || gen !== generacion) return;
      toast(restaurar ? "Terreno restaurado." : "Terreno archivado. Puedes verlo con «Incluir archivados».");
      if (!restaurar && !consulta.incluirArchivados) quitarFila(id);
      else reemplazar(terreno);
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

  /* ------------------------------------------------------------ lifecycle */

  abrir(vistaInicial, { forzar: true });

  return {
    element,
    get dirty() { return sucio(); },
    get vista() { return vista; },
    abrir,
    /** The application's read-only mode became known or changed. */
    permisos() { if (vivo && vista && !editando) pintarTodo(); },
    /** Look again when the window regains attention, unless work is open. */
    revalidar() { if (vivo && vista && !sucio() && !editando && !document.querySelector("dialog[open]")) recargar(); },
    /** The account is leaving (logout, expiry, another user): forget it all. */
    destroy() {
      vivo = false;
      limpiarAlcance();
      bases = [];
      element.remove();
    },
  };
}

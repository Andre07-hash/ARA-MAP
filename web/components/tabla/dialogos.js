/* The table's dialogs: one terrain's detail and actions, the transfer with its
 * preview, a base's custom columns, and the work bases with their grants.
 *
 * Every change sends the version the person was looking at. A 409 is shown
 * with what the server holds now and is never retried on its own: the person
 * looks, then decides.
 */

import { api } from "../../lib/api.js";
import { el } from "../../lib/dom.js";
import { crearIntento } from "../../lib/inventario.js";
import { textoDe, valorDe } from "../../lib/tabla.js";
import { confirmarBorrado, confirmDialog, openDialog } from "../ui/dialog.js";
import { montarAsistente } from "./asistenteTerreno.js";
import { montarRanura } from "./ranuraArchivos.js";

const TIPOS = [["texto", "Texto"], ["numero", "Número"], ["opcion", "Opción"], ["fecha", "Fecha"]];
const cerrar = { etiqueta: "Cerrar", onClick: (close) => close() };
const boton = (texto, onclick, clase = "btn btn-small btn-quiet") =>
  el("button", { type: "button", class: clase, onclick }, texto);

/** A message area a dialog writes its errors to. */
function Aviso() {
  const nodo = el("p", { class: "field-error", role: "alert" });
  return { nodo, decir: (texto) => { nodo.textContent = texto ?? ""; } };
}

/* ------------------------------------------------- several terrains at once */

const terrenos = (n) => `${n} ${n === 1 ? "terreno" : "terrenos"}`;

/* A one-field dialog that answers once: the button's value, or null when it
 * is cancelled or dismissed. The answer is given before the dialog closes,
 * because a dialog removed as it closes never fires its "close" event. */
function preguntar({ titulo, descripcion, contenido, accion, valor }) {
  return new Promise((resolve) => {
    let hecho = false;
    const responder = (v) => { if (!hecho) { hecho = true; resolve(v); } };
    const { dialog } = openDialog({
      titulo, descripcion, contenido,
      acciones: [
        { etiqueta: "Cancelar", onClick: (close) => { responder(null); close(); } },
        { etiqueta: accion, variante: "principal", onClick: (close) => {
          const v = valor();
          if (v == null) return;
          responder(v);
          close();
        } },
      ],
    });
    dialog.addEventListener("close", () => responder(null));
  });
}

/**
 * Where to move the selected terrains. Resolves a base id, "sin_asignar",
 * or null when the person cancels.
 */
export function pedirDestino({ cantidad, bases }) {
  const destino = el("select", { id: "multiple-destino", class: "input" },
    el("option", { value: "" }, "Elige un destino…"),
    el("option", { value: "sin_asignar" }, "Sin base (sólo administradores)"),
    bases.map((b) => el("option", { value: b.id }, b.nombre)));
  const aviso = Aviso();
  return preguntar({
    titulo: `Transferir ${terrenos(cantidad)}`,
    descripcion: "Cada terreno conserva sus datos, archivos e historial. Las columnas propias de su " +
      "base actual dejan de mostrarse en la nueva.",
    contenido: el("div", {},
      el("label", { class: "field-label", for: "multiple-destino" }, "Base de destino"), destino, aviso.nodo),
    accion: "Transferir",
    valor: () => destino.value || (aviso.decir("Elige una base de destino."), null),
  });
}

/** The name of a new base for the selected terrains, or null when cancelled. */
export function pedirNombreDeBase({ cantidad }) {
  const nombre = el("input", { id: "multiple-base", class: "input", maxlength: "100", autocomplete: "off" });
  const aviso = Aviso();
  return preguntar({
    titulo: `Crear una base con ${terrenos(cantidad)}`,
    descripcion: "Se crea una base de trabajo nueva y los terrenos seleccionados pasan a ella. " +
      "Después puedes darle acceso a los operadores en «Bases y accesos».",
    contenido: el("div", {},
      el("label", { class: "field-label", for: "multiple-base" }, "Nombre de la base"), nombre, aviso.nodo),
    accion: "Crear y mover",
    valor: () => (nombre.value.trim() ? nombre.value : (aviso.decir("Escribe un nombre."), null)),
  });
}

/* ------------------------------------------------------------- one terrain */

export function abrirDetalle({
  terreno, columnas, base, admin, puedeCambiar, onCerrar, onHistorial, onBorrar, onTransferir,
  onArchivos, onErrorDeArchivos,
}) {
  // What may be changed can move while the dialog is open (a grant changed by
  // someone else): permisos() below updates it.
  let soloLectura = !puedeCambiar;
  const montadas = [];
  const ranura = (tipo) => {
    const container = el("dd", { class: "detalle-ranura" });
    montadas.push(montarRanura({
      container, terrenoId: terreno.id, tipo, soloLectura, detalle: true,
      resumen: terreno.archivos ?? undefined, onCambio: onArchivos, onError: onErrorDeArchivos,
    }));
    return container;
  };
  const datos = el("dl", { class: "detalle-datos" },
    el("dt", {}, "Base"), el("dd", {}, terreno.base_id ? (base?.nombre ?? "—") : "Sin asignar"),
    columnas.filter((c) => c.tipo !== "base").map((c) => [
      el("dt", {}, c.etiqueta),
      c.tipo === "archivo" ? ranura(c.archivo) : el("dd", {}, textoDe(valorDe(terreno, c), c) || "—"),
    ]),
    el("dt", {}, "Última edición"),
    el("dd", {}, `${terreno.updated_by?.display_name ?? "—"} · versión ${terreno.version}`),
  );
  const acciones = el("div", { class: "detalle-acciones" });
  // Administrators only; it stays hidden unless the server has it on.
  const asistente = admin ? montarAsistente({ terreno }) : null;
  function pintarEstado() {
    acciones.replaceChildren(...[
      boton("Historial", () => onHistorial()),
      asistente?.boton,
      admin && puedeCambiar && boton("Transferir a otra base…", async () => {
        if (await close()) onTransferir();
      }),
      // A published terrain changes what the public sees: administrators only (the server agrees).
      puedeCambiar && (admin || !terreno.published_revision_id) && boton("Borrar terreno…", async () => {
        if (!(await confirmarBorrado({
          titulo: `¿Borrar «${terreno.draft?.terreno || "Terreno sin nombre"}»?`,
          mensaje: "Se borran el terreno, todos sus datos, su historial y sus archivos adjuntos (PDF, JPG, KMZ y KML).",
        }))) return;
        if (await close()) onBorrar();
      }, "btn btn-small btn-peligro"),
    ].filter(Boolean));
  }
  const { dialog, close } = openDialog({
    titulo: terreno.draft?.terreno || "Terreno sin nombre",
    ancho: "38rem",
    contenido: el("div", {}, datos, acciones, asistente?.panel),
    acciones: [cerrar],
    // Closing destroys the file controls: never silently while an upload is unfinished.
    antesDeCerrar: () => (montadas.some((m) => m.ocupado?.()) ? confirmDialog({
      titulo: "¿Cerrar e interrumpir la subida?",
      mensaje: "Una subida de archivo de este terreno no ha terminado. Si cierras el detalle ahora, se " +
        "interrumpe: los archivos ya guardados se conservan, y la subida puede continuarse después desde " +
        "aquí eligiendo otra vez el mismo archivo. También puedes cancelarla con su botón «Cancelar».",
      confirmar: "Cerrar e interrumpir", cancelar: "Seguir en el detalle", peligro: true,
    }) : true),
  });
  pintarEstado();
  dialog.addEventListener("close", () => {
    asistente?.destroy();
    for (const m of montadas.splice(0)) m.destroy();
    onCerrar?.();
  });
  return {
    terrenoId: terreno.id,
    /** A fresh summary for the same terrain; nothing else of the dialog changes. */
    archivos(resumen) { for (const m of montadas) m.update({ soloLectura, resumen: resumen ?? undefined }); },
    /**
     * What this account may do with the terrain now. The file mounts and the
     * actions follow; what is being read (lists, an open history) stays.
     */
    permisos({ puedeCambiar: puede, resumen }) {
      puedeCambiar = Boolean(puede);
      soloLectura = !puedeCambiar;
      pintarEstado();
      for (const m of montadas) m.update({ soloLectura, resumen: resumen ?? undefined });
    },
  };
}

/* ---------------------------------------------------------------- transfer */

export function abrirTransferencia({ terreno, bases, onHecho, onConflicto }) {
  let actual = terreno;
  let vista = null;                // the preview being shown
  let pedido = 0;
  const aviso = Aviso();
  const destino = el("select", { id: "transferir-destino", class: "input" },
    el("option", { value: "" }, "Elige un destino…"),
    el("option", { value: "sin_asignar" }, "Sin base (sólo administradores)"),
    bases.map((b) => el("option", { value: b.id }, b.nombre)));
  const resumen = el("div", { class: "transferir-resumen", "aria-live": "polite" });
  const entiendo = el("input", { id: "transferir-entiendo", type: "checkbox" });
  const confirmacion = el("label", { class: "check", for: "transferir-entiendo", hidden: true },
    entiendo, "Revisé quién podrá abrirlo y qué columnas dejarán de mostrarse.");
  const mover = el("button", { type: "button", class: "btn btn-principal", disabled: true }, "Transferir");
  const habilitar = () => { mover.disabled = !(vista && !vista.sin_cambio && entiendo.checked); };
  entiendo.addEventListener("change", habilitar);

  async function previsualizar() {
    const elegido = destino.value;
    const n = pedido += 1;
    vista = null;
    entiendo.checked = false;
    confirmacion.hidden = true;
    habilitar();
    aviso.decir("");
    resumen.replaceChildren();
    if (!elegido) return;
    resumen.textContent = "Consultando qué cambia…";
    try {
      const previa = await api.vistaDeTransferencia(actual.id, elegido);
      if (n !== pedido) return;     // an answer for a destination no longer selected
      vista = previa;
      const quienes = previa.acceso.length
        ? el("ul", {}, previa.acceso.map((u) => el("li", {}, `${u.display_name} (${u.login})` +
            (u.active ? "" : " · cuenta inactiva"))))
        : el("p", { class: "secondary" }, previa.destino
          ? "Ningún operador tiene acceso a esa base todavía." : "Ningún operador: queda sin base.");
      const ocultas = previa.columnas_que_se_ocultan.length
        ? el("ul", {}, previa.columnas_que_se_ocultan.map((c) => el("li", {},
            c.nombre + (c.con_valor ? " · este terreno tiene un valor, que se conserva sin mostrarse" : ""))))
        : el("p", { class: "secondary" }, "Ninguna.");
      resumen.replaceChildren(...(previa.sin_cambio
        ? [el("p", {}, "El terreno ya está ahí: no hay nada que mover.")]
        : [el("h3", {}, "Quién podrá abrirlo"), quienes,
          el("p", { class: "secondary" }, "Los administradores siempre pueden. Quien sólo tenga la base de " +
            "origen dejará de verlo."),
          el("h3", {}, "Columnas que dejarán de mostrarse"), ocultas,
          el("p", { class: "secondary" }, "El terreno conserva su identificador, sus archivos, su trazo y su historial.")]));
      confirmacion.hidden = previa.sin_cambio;
    } catch (error) {
      if (n !== pedido) return;
      resumen.replaceChildren();
      aviso.decir(error.status === 404 ? "Ese terreno ya no está disponible." : error.message);
    }
  }
  destino.addEventListener("change", previsualizar);

  mover.addEventListener("click", async () => {
    if (!vista) return;
    mover.disabled = true;
    aviso.decir("");
    try {
      // The version the person saw in the row; the server checks it again on its own.
      const { terreno: movido } = await api.transferirTerreno(actual.id, actual.version, vista.destino);
      close();
      onHecho(movido);
    } catch (error) {
      if (error.status === 409 && error.detalle?.terreno) {
        actual = error.detalle.terreno;
        onConflicto?.(actual);
        aviso.decir("El terreno cambió mientras revisabas. Vuelve a revisar antes de transferir.");
        previsualizar();
      } else {
        aviso.decir(error.message);
        habilitar();
      }
    }
  });

  const { close } = openDialog({
    titulo: "Transferir terreno",
    descripcion: terreno.draft?.terreno || "Terreno sin nombre",
    ancho: "36rem",
    contenido: el("div", {},
      el("div", { class: "rail-field" },
        el("label", { class: "field-label", for: "transferir-destino" }, "Base de destino"), destino),
      resumen, confirmacion, aviso.nodo, el("div", { class: "detalle-acciones" }, mover)),
    acciones: [{ etiqueta: "Cancelar", onClick: (c) => c() }],
  });
}

/* ------------------------------------------------------------ custom columns */

export function abrirColumnas({ base, soloLectura, onCerrar, onAlcancePerdido }) {
  let cambio = false;
  let vivas = 0;
  const intento = crearIntento();
  const aviso = Aviso();
  const lista = el("ul", { class: "columnas-lista" });
  const nombre = el("input", { id: "columna-nombre", class: "input", maxlength: "100", autocomplete: "off" });
  const tipo = el("select", { id: "columna-tipo", class: "input" },
    TIPOS.map(([v, e]) => el("option", { value: v }, e)));
  const opciones = el("textarea", { id: "columna-opciones", class: "input", rows: "3" });
  const campoOpciones = el("div", { class: "rail-field", hidden: true },
    el("label", { class: "field-label", for: "columna-opciones" }, "Opciones (una por línea)"), opciones);
  tipo.addEventListener("change", () => { campoOpciones.hidden = tipo.value !== "opcion"; });
  const lineas = (texto) => texto.split("\n").map((l) => l.trim()).filter(Boolean);

  function fallo(error) {
    if (error.status === 404) { close(); onAlcancePerdido?.(); return; }
    const campos = Object.values(error.detalle?.fields ?? {});
    aviso.decir(campos.length ? campos.join(" ") : error.message);
    // After a conflict, show the definitions as they are before anything is repeated.
    if (error.status === 409) cargar();
  }

  async function hacer(accion) {
    aviso.decir("");
    try {
      await accion();
      cambio = true;
      await cargar();
    } catch (error) { fallo(error); }
  }

  function Definicion(c, indice) {
    const nuevoNombre = el("input", {
      class: "input", value: c.nombre, maxlength: "100", "aria-label": `Nombre de la columna ${c.nombre}`,
      disabled: soloLectura,
    });
    const nuevaOpcion = c.tipo === "opcion" && !soloLectura && el("input", {
      class: "input", placeholder: "Agregar opción", "aria-label": `Agregar opción a ${c.nombre}`,
    });
    const cambiar = (cuerpo) => hacer(() =>
      api.cambiarColumna(base.id, c.id, { expected_version: c.version, ...cuerpo }));
    return el("li", { class: "columnas-item" },
      nuevoNombre,
      el("span", { class: "secondary columnas-tipo" },
        TIPOS.find(([v]) => v === c.tipo)?.[1] ?? c.tipo,
        c.tipo === "opcion" && `: ${c.opciones.join(", ")}`),
      nuevaOpcion,
      !soloLectura && el("div", { class: "columnas-botones" },
        boton("Guardar", () => {
          const cuerpo = {};
          if (nuevoNombre.value.trim() !== c.nombre) cuerpo.nombre = nuevoNombre.value;
          if (nuevaOpcion && nuevaOpcion.value.trim()) cuerpo.opciones = [...c.opciones, nuevaOpcion.value];
          if (Object.keys(cuerpo).length) cambiar(cuerpo);
        }),
        indice > 0 && boton("Subir", () => cambiar({ posicion: indice - 1 })),
        indice < vivas - 1 && boton("Bajar", () => cambiar({ posicion: indice + 1 })),
        boton("Borrar…", async () => {
          if (!(await confirmarBorrado({
            titulo: `¿Borrar la columna «${c.nombre}»?`,
            mensaje: "La columna desaparece de esta base y sus valores dejan de mostrarse en todos sus terrenos.",
          }))) return;
          hacer(() => api.borrarColumna(base.id, c.id, c.version));
        }, "btn btn-small btn-peligro"),
      ),
    );
  }

  async function cargar() {
    try {
      const { columnas } = await api.columnas(base.id);
      vivas = columnas.length;
      lista.replaceChildren(...(columnas.length
        ? columnas.map((c, i) => Definicion(c, i))
        : [el("li", { class: "secondary" }, "Esta base todavía no tiene columnas propias.")]));
    } catch (error) { fallo(error); }
  }

  const crear = el("form", { class: "columnas-nueva" },
    el("h3", {}, "Nueva columna"),
    el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: "columna-nombre" }, "Nombre"), nombre),
    el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: "columna-tipo" }, "Tipo (no se puede cambiar después)"), tipo),
    campoOpciones,
    el("button", { type: "submit", class: "btn btn-principal" }, "Crear columna"),
  );
  crear.addEventListener("submit", (event) => {
    event.preventDefault();
    const cuerpo = { nombre: nombre.value, tipo: tipo.value,
      ...(tipo.value === "opcion" ? { opciones: lineas(opciones.value) } : {}) };
    // The same body after an unanswered request reuses its key: no second column.
    hacer(async () => {
      await api.crearColumna(base.id, cuerpo, intento.claveParaCuerpo(cuerpo));
      intento.completar();
      nombre.value = "";
      opciones.value = "";
    });
  });

  const { dialog, close } = openDialog({
    titulo: "Columnas de la base",
    descripcion: `${base.nombre}. Sólo existen en esta base; las catorce columnas básicas no se pueden quitar.`,
    ancho: "44rem",
    contenido: el("div", {}, lista, aviso.nodo, !soloLectura && crear),
    acciones: [cerrar],
  });
  dialog.addEventListener("close", () => onCerrar?.(cambio));
  cargar();
}

/* ------------------------------------------------------- bases and grants */

export function abrirBases({ onCerrar }) {
  let cambio = false;
  const aviso = Aviso();
  const lista = el("ul", { class: "bases-lista" });
  const nombre = el("input", { id: "base-nombre", class: "input", maxlength: "100", autocomplete: "off" });

  async function hacer(accion) {
    aviso.decir("");
    try {
      await accion();
      cambio = true;
    } catch (error) {
      const campos = Object.values(error.detalle?.fields ?? {});
      aviso.decir(campos.length ? campos.join(" ") : error.message);
    }
    await cargar();   // on a conflict too: show the base as it is now
  }

  function Base(b) {
    const nuevo = el("input", {
      class: "input", value: b.nombre, maxlength: "100", "aria-label": `Nombre de la base ${b.nombre}`,
    });
    return el("li", { class: "bases-item" },
      nuevo,
      el("span", { class: "secondary" }, `${b.terrenos} ${b.terrenos === 1 ? "terreno" : "terrenos"}`),
      el("div", { class: "columnas-botones" },
        boton("Renombrar", () => hacer(() => api.renombrarBaseDeTrabajo(b.id, b.version, nuevo.value))),
        boton("Accesos…", () => abrirAccesos({ base: b, onCerrar: (c) => { cambio = cambio || c; cargar(); } })),
        boton("Borrar…", async () => {
          if (b.terrenos > 0) {
            aviso.decir(`«${b.nombre}» todavía tiene ${b.terrenos} ${b.terrenos === 1 ? "terreno" : "terrenos"}. ` +
              "Bórralos o transfiérelos a otra base antes de borrarla.");
            return;
          }
          if (!(await confirmarBorrado({
            titulo: `¿Borrar la base «${b.nombre}»?`,
            mensaje: "Se borran la base, sus columnas y sus accesos.",
          }))) return;
          hacer(() => api.borrarBaseDeTrabajo(b.id, b.version));
        }, "btn btn-small btn-peligro"),
      ),
    );
  }

  async function cargar() {
    try {
      const { bases } = await api.maestraBases();
      lista.replaceChildren(...(bases.length ? bases.map(Base)
        : [el("li", { class: "secondary" }, "Todavía no hay bases de trabajo.")]));
    } catch (error) { aviso.decir(error.message); }
  }

  const crear = el("form", { class: "columnas-nueva" },
    el("h3", {}, "Nueva base de trabajo"),
    el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: "base-nombre" }, "Nombre"), nombre),
    el("button", { type: "submit", class: "btn btn-principal" }, "Crear base"),
  );
  crear.addEventListener("submit", (event) => {
    event.preventDefault();
    hacer(async () => { await api.crearBaseDeTrabajo(nombre.value); nombre.value = ""; });
  });

  const { dialog } = openDialog({
    titulo: "Bases de trabajo y accesos",
    descripcion: "Una base agrupa terrenos y dice qué operadores pueden abrirlos.",
    ancho: "44rem",
    contenido: el("div", {}, lista, aviso.nodo, crear),
    acciones: [cerrar],
  });
  dialog.addEventListener("close", () => onCerrar?.(cambio));
  cargar();
}

function abrirAccesos({ base, onCerrar }) {
  let cambio = false;
  let version = base.version;
  let elegidos = new Set();
  let conocidos = new Map();       // id -> account, for the ones granted or listed
  const aviso = Aviso();
  const lista = el("ul", { class: "check-list accesos-lista" });
  const buscar = el("input", {
    id: "accesos-buscar", class: "input", type: "search", placeholder: "Nombre o usuario",
  });
  const guardar = el("button", { type: "button", class: "btn btn-principal" }, "Guardar accesos");
  let timer = null;

  function pintar(visibles, total) {
    const filas = visibles.map((u) => {
      const caja = el("input", {
        type: "checkbox", id: `acceso-${u.id}`, checked: elegidos.has(u.id),
        // An inactive account can keep a grant or lose it, never gain one.
        disabled: !u.active && !elegidos.has(u.id),
        onchange: () => { if (caja.checked) elegidos.add(u.id); else elegidos.delete(u.id); },
      });
      return el("li", {}, el("label", { class: "check", for: caja.id }, caja,
        `${u.display_name} (${u.login})${u.active ? "" : " · cuenta inactiva"}`));
    });
    lista.replaceChildren(...(filas.length ? filas : [el("li", { class: "secondary" }, "Ningún operador coincide.")]),
      ...(total > visibles.length ? [el("li", { class: "secondary" },
        `Se muestran ${visibles.length} de ${total}. Usa la búsqueda para encontrar a alguien más.`)] : []));
  }

  async function listar() {
    try {
      const { usuarios, total } = await api.operadores(buscar.value.trim());
      for (const u of usuarios) conocidos.set(u.id, u);
      // Whoever is selected stays visible, whatever the search shows.
      const fuera = [...elegidos].filter((id) => !usuarios.some((u) => u.id === id))
        .map((id) => conocidos.get(id)).filter(Boolean);
      pintar([...fuera, ...usuarios], total + fuera.length);
    } catch (error) { aviso.decir(error.message); }
  }

  async function cargar() {
    try {
      const actual = await api.accesoDeBase(base.id);
      version = actual.base.version;
      elegidos = new Set(actual.usuarios.map((u) => u.id));
      conocidos = new Map(actual.usuarios.map((u) => [u.id, u]));
      await listar();
    } catch (error) { aviso.decir(error.message); }
  }

  buscar.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(listar, 250); });
  guardar.addEventListener("click", async () => {
    aviso.decir("");
    guardar.disabled = true;
    try {
      await api.reemplazarAcceso(base.id, version, [...elegidos]);
      cambio = true;
      close();
    } catch (error) {
      if (error.status === 409 && error.detalle?.code === "conflict") {
        // Someone else changed this base. Their result is shown; nothing of ours was written.
        aviso.decir("Otra persona cambió esta base mientras editabas. Se muestran los accesos actuales: " +
          "revísalos y vuelve a marcar lo que quieras cambiar.");
        await cargar();
      } else {
        const motivos = Object.keys(error.detalle?.usuarios ?? {}).length;
        aviso.decir(motivos ? "Hay cuentas que no pueden recibir acceso (inactivas, o no son operadores)."
          : error.message);
      }
    } finally { guardar.disabled = false; }
  });

  const { dialog, close } = openDialog({
    titulo: `Accesos · ${base.nombre}`,
    descripcion: "Marca los operadores que pueden abrir esta base. Los administradores siempre pueden.",
    ancho: "34rem",
    contenido: el("div", {},
      el("div", { class: "rail-field" },
        el("label", { class: "field-label", for: "accesos-buscar" }, "Buscar operador"), buscar),
      lista, aviso.nodo, el("div", { class: "detalle-acciones" }, guardar)),
    acciones: [{ etiqueta: "Cancelar", onClick: (c) => c() }],
  });
  dialog.addEventListener("close", () => onCerrar?.(cambio));
  cargar();
}

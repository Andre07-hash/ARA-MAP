/* The screening filters, as a persistent view.
 *
 * This is deliberately NOT a render-from-scratch component. The search box and
 * the numeric boxes are edited character by character, and rebuilding them on
 * every keystroke destroys the focused node: the caret lands in the void and
 * typing stops after one letter. So the rail is built once and `update` patches
 * what changed, leaving the node the user is typing into untouched.
 *
 *   createFilterRail({ onChange, onReset, modo })
 *     -> { element, update({ terrenos, filtros, visibles, monedas, opciones, cargando }), destroy() }
 *
 * `modo` is "local" (a legacy base or saved map, filtered in the browser) or
 * "catalogo" / "inventario" (filtered by the server). In the server modes the
 * state/municipality options come from the server's facets for the whole
 * candidate set (`opciones`), and price filtering takes one explicit currency
 * and one basis, never a mix.
 *
 * `monedas` are the currencies of the priced terrains in view. With more than
 * one, the local price ranges are disabled: a range in one currency would
 * silently apply to amounts in another.
 */

import { el } from "../../lib/dom.js";
import { activeCount, deriveOptions } from "../../lib/filters.js";
import { fmtCount, fmtPriceShort, MONEDAS, nombraMonedas, plural } from "../../lib/format.js";
import { contarFiltros, DISPONIBILIDAD, PUBLICACION } from "../../lib/inventario.js";

const RANGOS = [
  { campo: "superficie", titulo: "Superficie (m²)", formato: fmtCount },
  { campo: "precio", titulo: "Asking Price", formato: fmtPriceShort, dinero: true },
  { campo: "unitario", titulo: "Asking $/m²", formato: fmtPriceShort, dinero: true },
];

/* Separator for the option-set signature; a value can never contain it. */
const SEP = "␟";

/* Option lists show this many until expanded; every value stays reachable. */
const LIMITES = { estados: 6, municipios: 8 };

export function createFilterRail({ onChange, onReset, modo = "local" }) {
  const servidor = modo !== "local";
  let estado = { terrenos: [], filtros: {}, visibles: 0 };
  let componiendo = false;
  const limpiar = [];

  const escucha = (nodo, evento, handler) => {
    nodo.addEventListener(evento, handler);
    limpiar.push(() => nodo.removeEventListener(evento, handler));
  };

  /* ---- search ------------------------------------------------------- */

  const buscar = el("input", {
    id: "buscar", type: "search", class: "input",
    placeholder: "Nombre, municipio o dirección",
    autocomplete: "off",
  });

  // While a composed character is being assembled (accents, IME), the value is
  // intentionally not pushed through state: replacing it mid-composition
  // cancels the composition.
  escucha(buscar, "compositionstart", () => { componiendo = true; });
  escucha(buscar, "compositionend", () => {
    componiendo = false;
    onChange({ busqueda: buscar.value });
  });
  escucha(buscar, "input", () => {
    if (!componiendo) onChange({ busqueda: buscar.value });
  });

  const resultado = el("p", { class: "rail-result figure" });

  /* ---- reset -------------------------------------------------------- */

  const limpiarBtn = el("button", { type: "button", class: "link-btn" }, "Limpiar");
  escucha(limpiarBtn, "click", () => onReset());

  const cabecera = el("header", { class: "rail-header" },
    el("span", { class: "eyebrow" }, "Filtros"),
    limpiarBtn,
  );

  /* ---- checkbox groups ---------------------------------------------- */

  const grupos = {
    estados: crearGrupo("Estado", "estados"),
    municipios: crearGrupo("Municipio", "municipios"),
  };

  function crearGrupo(titulo, campo) {
    const lista = el("ul", { class: "check-list", id: `lista-${campo}` });
    const mas = el("button", {
      type: "button", class: "link-btn check-more", "aria-controls": `lista-${campo}`,
    });
    const grupo = { fieldset: null, lista, mas, campo, firma: null, expandido: false };
    escucha(mas, "click", () => {
      grupo.expandido = !grupo.expandido;
      update({});
    });
    grupo.fieldset = el("fieldset", { class: "rail-field" },
      el("legend", { class: "field-label" }, titulo),
      lista,
      mas,
    );
    return grupo;
  }

  /* ---- numeric ranges ------------------------------------------------ */

  const rangos = RANGOS.filter((r) => !servidor || !r.dinero).map(({ campo, titulo, formato, dinero }) => {
    const min = crearNumero(`${campo}-min`, "mín", `${campo}Min`);
    const max = crearNumero(`${campo}-max`, "máx", `${campo}Max`);
    const pista = el("p", { class: "range-hint muted figure" });
    const fieldset = el("fieldset", { class: "rail-field" },
      el("legend", { class: "field-label" }, titulo),
      el("div", { class: "range-row" },
        min, el("span", { class: "range-dash", "aria-hidden": "true" }, "–"), max),
      pista,
    );
    return { campo, formato, dinero, min, max, pista, fieldset };
  });

  function crearNumero(id, placeholder, clave) {
    const input = el("input", {
      id, type: "number", class: "input input-num",
      placeholder, autocomplete: "off",
    });
    escucha(input, "input", () => {
      const bruto = input.value.trim();
      // An empty box means "no limit"; a partial entry such as "1." is not a
      // number yet and must not be normalised away while still being typed.
      if (bruto === "") return onChange({ [clave]: null });
      const valor = Number(bruto);
      if (Number.isFinite(valor)) onChange({ [clave]: valor });
    });
    return input;
  }

  /* ---- toggles ------------------------------------------------------- */

  const soloUbicados = crearToggle("solo-ubicados", "Solo con ubicación", "soloUbicados");
  const soloIncidencias = crearToggle(
    "solo-incidencias", "Solo con incidencias", "soloConIncidencias");

  function crearToggle(id, etiqueta, clave) {
    const input = el("input", { id, type: "checkbox" });
    escucha(input, "change", () => onChange({ [clave]: input.checked }));
    return { input, label: el("label", { class: "check" }, input, el("span", {}, etiqueta)) };
  }

  const toggles = el("div", { class: "rail-field rail-toggles" },
    soloUbicados.label, soloIncidencias.label);

  /* ---- server modes: one currency, one basis, one range ----------------- */

  function crearSelect(id, opciones, clave, vacioEsNull = true) {
    const select = el("select", { id, class: "input" },
      opciones.map(([valor, etiqueta]) => el("option", { value: valor }, etiqueta)));
    escucha(select, "change", () => onChange({ [clave]: vacioEsNull && select.value === "" ? null : select.value }));
    return select;
  }

  const precio = servidor && (() => {
    const moneda = crearSelect("precio-moneda",
      [["", "Cualquier moneda"], ...MONEDAS.map((m) => [m, m])], "moneda");
    const base = crearSelect("precio-base",
      [["total", "Precio total"], ["per_m2", "Precio por m²"]], "precioBase", false);
    const min = crearNumero("precio-min", "mín", "precioMin");
    const max = crearNumero("precio-max", "máx", "precioMax");
    const pista = el("p", { class: "range-hint muted" });
    const fieldset = el("fieldset", { class: "rail-field" },
      el("legend", { class: "field-label" }, "Precio"),
      el("label", { class: "visually-hidden", for: "precio-moneda" }, "Moneda"),
      moneda,
      el("label", { class: "visually-hidden", for: "precio-base" }, "Base del precio"),
      base,
      el("div", { class: "range-row" },
        min, el("span", { class: "range-dash", "aria-hidden": "true" }, "–"), max),
      pista,
    );
    fieldset.classList.add("rail-precio");
    return { moneda, base, min, max, pista, fieldset };
  })();

  const internos = modo === "inventario" && (() => {
    const publicacion = crearSelect("filtro-publicacion",
      [["", "Todas"], ...Object.entries(PUBLICACION).filter(([k]) => k !== "archived")], "publicacion");
    const disponibilidad = crearSelect("filtro-disponibilidad",
      [["", "Todas"], ...Object.entries(DISPONIBILIDAD)], "disponibilidad");
    const archivados = crearToggle("incluir-archivados", "Incluir archivados", "incluirArchivados");
    const fieldset = el("div", { class: "rail-field rail-toggles" },
      el("label", { class: "field-label", for: "filtro-publicacion" }, "Publicación"),
      publicacion,
      el("label", { class: "field-label rail-sublabel", for: "filtro-disponibilidad" }, "Disponibilidad"),
      disponibilidad,
      archivados.label,
    );
    return { publicacion, disponibilidad, archivados, fieldset };
  })();

  /* ---- assembly ------------------------------------------------------ */

  const element = el("form", { class: "rail", "aria-label": "Filtros" },
    cabecera,
    el("div", { class: "rail-field" },
      el("label", { class: "field-label", for: "buscar" }, "Buscar"),
      buscar,
    ),
    resultado,
    grupos.estados.fieldset,
    grupos.municipios.fieldset,
    ...rangos.map((r) => r.fieldset),
    precio && precio.fieldset,
    internos ? internos.fieldset : !servidor && toggles,
  );
  escucha(element, "submit", (event) => event.preventDefault());

  /* ---- patching ------------------------------------------------------ */

  /** Set a control's value only when it is not the one being edited. */
  function asignarSiOcioso(input, valor) {
    if (document.activeElement === input) return;
    const texto = valor == null ? "" : String(valor);
    if (input.value !== texto) input.value = texto;
  }

  function actualizarGrupo(grupo, opciones, seleccion, limite) {
    // Selected values are always listed, even past the limit or if the
    // server's facets no longer include them, so they can be unticked.
    const todas = [
      ...opciones,
      ...seleccion.filter((v) => !opciones.some((o) => o.valor === v)).map((valor) => ({ valor, conteo: 0 })),
    ];
    const visibles = grupo.expandido || seleccion.length || todas.length <= limite + 1
      ? todas
      : todas.slice(0, limite);
    const ocultos = todas.length - visibles.length;
    const firma = visibles.map((o) => `${o.valor}:${o.conteo}`).join(SEP) + `${SEP}${ocultos}`;

    if (grupo.firma !== firma) {
      // The option set itself changed, so this list is rebuilt. Focus goes back
      // to the equivalent control if it was inside the group.
      const activo = document.activeElement;
      const idActivo = grupo.lista.contains(activo) ? activo.id : null;

      grupo.lista.replaceChildren(
        ...visibles.map((opcion) => {
          const caja = el("input", {
            id: `${grupo.campo}-${opcion.valor}`, type: "checkbox", value: opcion.valor,
          });
          caja.addEventListener("change", () => {
            const actual = estado.filtros[grupo.campo] ?? [];
            onChange({
              [grupo.campo]: caja.checked
                ? [...actual, opcion.valor]
                : actual.filter((v) => v !== opcion.valor),
            });
          });
          return el("li", {},
            el("label", { class: "check" },
              caja,
              el("span", { class: "truncate" }, opcion.valor),
              opcion.conteo != null && el("span", { class: "figure muted" }, String(opcion.conteo)),
            )
          );
        }),
      );
      grupo.firma = firma;
      if (idActivo) {
        for (const caja of grupo.lista.querySelectorAll("input[type=checkbox]")) {
          if (caja.id === idActivo) caja.focus();
        }
      }
    }

    for (const caja of grupo.lista.querySelectorAll("input[type=checkbox]")) {
      const deberia = seleccion.includes(caja.value);
      if (caja.checked !== deberia) caja.checked = deberia;
    }
    grupo.mas.hidden = !grupo.expandido || seleccion.length ? ocultos === 0 : false;
    grupo.mas.textContent = grupo.expandido ? "Ver menos" : `Ver todos (${ocultos} más)`;
    grupo.mas.setAttribute("aria-expanded", String(grupo.expandido));
    grupo.fieldset.hidden = todas.length === 0
      || (grupo.campo === "municipios" && todas.length < 2 && !seleccion.length);
  }

  function update(siguiente) {
    estado = { ...estado, ...siguiente };
    const { terrenos, filtros, visibles, monedas = [], cargando = false } = estado;
    const mezcla = monedas.length > 1;
    const derivadas = deriveOptions(terrenos, filtros);
    const opciones = servidor ? { ...derivadas, ...estado.opciones } : derivadas;
    const activos = servidor ? contarFiltros(filtros, modo) : activeCount(filtros);

    asignarSiOcioso(buscar, filtros.busqueda ?? "");
    limpiarBtn.hidden = activos === 0;
    limpiarBtn.textContent = `Limpiar (${activos})`;
    resultado.textContent = servidor
      ? (cargando ? "Buscando…" : plural(visibles, "terreno"))
      : `${plural(visibles, "terreno")} de ${terrenos.length}`;

    actualizarGrupo(grupos.estados, opciones.estados, filtros.estados ?? [], LIMITES.estados);
    actualizarGrupo(grupos.municipios, opciones.municipios, filtros.municipios ?? [], LIMITES.municipios);

    for (const rango of rangos) {
      const extremos = opciones.rangos[rango.campo];
      // A server-filtered range stays reachable even when the current result
      // is empty: otherwise a filter could hide the box that set it.
      rango.fieldset.hidden = !extremos && !servidor;
      asignarSiOcioso(rango.min, filtros[`${rango.campo}Min`]);
      asignarSiOcioso(rango.max, filtros[`${rango.campo}Max`]);
      if (!extremos) { rango.pista.textContent = ""; continue; }
      const bloqueado = rango.dinero && mezcla;
      rango.min.disabled = bloqueado;
      rango.max.disabled = bloqueado;
      rango.pista.textContent = bloqueado
        ? `Precios en ${nombraMonedas(monedas)}: no se filtran juntos.`
        : `${rango.formato(extremos.min, monedas[0])} – ${rango.formato(extremos.max, monedas[0])}`;
    }

    if (precio) {
      const moneda = MONEDAS.includes(filtros.moneda) ? filtros.moneda : "";
      if (precio.moneda.value !== moneda) precio.moneda.value = moneda;
      const baseValor = filtros.precioBase === "per_m2" ? "per_m2" : "total";
      if (precio.base.value !== baseValor) precio.base.value = baseValor;
      asignarSiOcioso(precio.min, filtros.precioMin);
      asignarSiOcioso(precio.max, filtros.precioMax);
      for (const control of [precio.base, precio.min, precio.max]) control.disabled = !moneda;
      precio.pista.textContent = moneda
        ? `Solo terrenos con precio en ${moneda}; los demás quedan fuera de este filtro.`
        : "Elige una moneda para filtrar por precio. Los precios no se convierten entre monedas.";
    }

    if (internos) {
      const pub = filtros.publicacion ?? "";
      if (internos.publicacion.value !== pub) internos.publicacion.value = pub;
      const disp = filtros.disponibilidad ?? "";
      if (internos.disponibilidad.value !== disp) internos.disponibilidad.value = disp;
      const arch = Boolean(filtros.incluirArchivados);
      if (internos.archivados.input.checked !== arch) internos.archivados.input.checked = arch;
    }

    if (soloUbicados.input.checked !== Boolean(filtros.soloUbicados)) {
      soloUbicados.input.checked = Boolean(filtros.soloUbicados);
    }
    if (soloIncidencias.input.checked !== Boolean(filtros.soloConIncidencias)) {
      soloIncidencias.input.checked = Boolean(filtros.soloConIncidencias);
    }
  }

  function destroy() {
    for (const quitar of limpiar) quitar();
    limpiar.length = 0;
    element.remove();
  }

  return { element, update, destroy };
}

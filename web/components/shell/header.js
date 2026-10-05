/* The application header: brand, section navigation and the session button. */

import { append, clear, el } from "../../lib/dom.js";
import { routeHash } from "../../lib/router.js";
import { getState } from "../../lib/store.js";
import { shell } from "./context.js";

const NAV_EQUIPO = [
  ["inventario", "Inventario"],
  ["mapa", "Mapa"],
  ["bases", "Bases"],
  ["mapas", "Mapas guardados"],
  ["catalogo", "Catálogo público"],
];
const NAV_PUBLICO = [["catalogo", "Catálogo"]];

let headerClave = null;

export function renderHeader(host, { onSignIn, onSignOut }) {
  const { ruta, sesion, sesionLista, baseActiva, mapaActivo } = getState();
  const activa = ruta.nombre === "editar" || ruta.nombre === "nuevo" ? "inventario" : ruta.nombre;
  const legacyAbierto = Boolean(baseActiva || mapaActivo);
  // Rebuilding the header on every keystroke is wasted work and a focus hazard
  // for anything inside it, so it is rebuilt only when what it shows changes.
  const clave = [activa, sesion?.id, sesion?.display_name, sesionLista, legacyAbierto].join("|");
  if (headerClave === clave && host.childElementCount) return;
  headerClave = clave;

  const items = (sesion ? NAV_EQUIPO : NAV_PUBLICO)
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
      shell.cloud && sesion && el("span", { class: "chip" }, "Espacio compartido"),
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
        onclick: sesion ? onSignOut : onSignIn,
      }, sesion ? "Cerrar sesión" : "Iniciar sesión"),
    ),
  ]);
}

/* Hash routes: bookmarkable public and internal contexts.
 *
 *   #/catalogo[/id]              public catalog, optionally one terrain open
 *   #/inventario[/id]            team inventory
 *   #/inventario/nuevo           new draft
 *   #/inventario/id/editar       draft editor
 *   #/tabla[/vista][/mapa]       the employee table: a work base id, or for
 *                                administrators "maestra" / "sin_asignar";
 *                                "/mapa" shows the same view as a map
 *   #/bases  #/mapas  #/mapa     legacy workspace (administrators)
 *
 * The server is the security boundary; a route only decides what to show.
 */

const CON_ID = new Set(["catalogo", "inventario", "editar", "tabla"]);

export function parseRoute(hash) {
  const partes = String(hash ?? "").replace(/^#\/?/, "").split("/").filter(Boolean);
  let decod;
  try { decod = partes.map(decodeURIComponent); } catch { return null; }
  const [a, b, c, d] = decod;
  if (a === "catalogo" && !c) return { nombre: "catalogo", id: b ?? null };
  if (a === "inventario") {
    if (b === "nuevo" && !c) return { nombre: "nuevo", id: null };
    if (b && c === "editar") return { nombre: "editar", id: b };
    if (!c) return { nombre: "inventario", id: b ?? null };
  }
  if (a === "tabla") {
    // A view id is a base UUID or "maestra"/"sin_asignar", never "mapa".
    if (b === "mapa" && !c) return { nombre: "tabla", id: null, modo: "mapa" };
    if (!c) return { nombre: "tabla", id: b ?? null };
    if (c === "mapa" && !d) return { nombre: "tabla", id: b, modo: "mapa" };
  }
  if ((a === "bases" || a === "mapas" || a === "mapa") && !b) return { nombre: a, id: null };
  return null;
}

export function routeHash({ nombre, id = null, modo = null }) {
  const enc = id == null ? "" : `/${encodeURIComponent(id)}`;
  if (nombre === "nuevo") return "#/inventario/nuevo";
  if (nombre === "editar") return `#/inventario${enc}/editar`;
  if (nombre === "tabla" && modo === "mapa") return `#/tabla${enc}/mapa`;
  return `#/${nombre}${CON_ID.has(nombre) ? enc : ""}`;
}

export const isPrivateRoute = (ruta) => ruta.nombre !== "catalogo";

/* Everyone signed in starts in the table: administrators in the master table,
 * operators in their work base. The routes of the legacy workspace and the
 * unscoped inventory stay administrators' only. */
export const defaultRoute = (autenticado) =>
  ({ nombre: !autenticado ? "catalogo" : "tabla", id: null });

export const routeAllowed = (ruta, rol) =>
  rol === "admin" || ruta.nombre === "tabla" || ruta.nombre === "catalogo";

export const sameRoute = (a, b) =>
  Boolean(a && b) && a.nombre === b.nombre && (a.id ?? null) === (b.id ?? null)
  && (a.modo ?? null) === (b.modo ?? null);

/**
 * Go somewhere. `replace` keeps selection changes out of the Back stack.
 * Both forms fire hashchange; an unchanged hash does not, so the caller is
 * told and can apply the route itself.
 */
export function navigate(ruta, { replace = false } = {}) {
  const hash = routeHash(ruta);
  if (location.hash === hash) return false;
  if (replace) location.replace(hash);
  else location.hash = hash;
  return true;
}

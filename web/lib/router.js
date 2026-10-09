/* Hash routes: bookmarkable public and internal contexts.
 *
 *   #/catalogo[/id]              public catalog, optionally one terrain open
 *   #/inventario[/id]            team inventory
 *   #/inventario/nuevo           new draft
 *   #/inventario/id/editar       draft editor
 *   #/tabla[/vista]              the employee table: a work base id, or for
 *                                administrators "maestra" / "sin_asignar"
 *   #/bases  #/mapas  #/mapa     legacy workspace (administrators)
 *
 * The server is the security boundary; a route only decides what to show.
 */

const CON_ID = new Set(["catalogo", "inventario", "editar", "tabla"]);

export function parseRoute(hash) {
  const partes = String(hash ?? "").replace(/^#\/?/, "").split("/").filter(Boolean);
  let decod;
  try { decod = partes.map(decodeURIComponent); } catch { return null; }
  const [a, b, c] = decod;
  if (a === "catalogo" && !c) return { nombre: "catalogo", id: b ?? null };
  if (a === "inventario") {
    if (b === "nuevo" && !c) return { nombre: "nuevo", id: null };
    if (b && c === "editar") return { nombre: "editar", id: b };
    if (!c) return { nombre: "inventario", id: b ?? null };
  }
  if (a === "tabla" && !c) return { nombre: "tabla", id: b ?? null };
  if ((a === "bases" || a === "mapas" || a === "mapa") && !b) return { nombre: a, id: null };
  return null;
}

export function routeHash({ nombre, id = null }) {
  const enc = id == null ? "" : `/${encodeURIComponent(id)}`;
  if (nombre === "nuevo") return "#/inventario/nuevo";
  if (nombre === "editar") return `#/inventario${enc}/editar`;
  return `#/${nombre}${CON_ID.has(nombre) ? enc : ""}`;
}

export const isPrivateRoute = (ruta) => ruta.nombre !== "catalogo";

/* Operators work in the table and nowhere else in the private app; the
 * routes of the legacy workspace and the unscoped inventory are administrators'. */
export const defaultRoute = (autenticado, rol = "admin") =>
  ({ nombre: !autenticado ? "catalogo" : rol === "admin" ? "inventario" : "tabla", id: null });

export const routeAllowed = (ruta, rol) =>
  rol === "admin" || ruta.nombre === "tabla" || ruta.nombre === "catalogo";

export const sameRoute = (a, b) =>
  Boolean(a && b) && a.nombre === b.nombre && (a.id ?? null) === (b.id ?? null);

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

/* Hash routes: bookmarkable public and internal contexts.
 *
 *   #/catalogo[/id]              public catalog, optionally one terrain open
 *   #/inventario[/id]            team inventory
 *   #/inventario/nuevo           new draft
 *   #/inventario/id/editar       draft editor
 *   #/bases  #/mapas  #/mapa     legacy workspace (signed in)
 *
 * The server is the security boundary; a route only decides what to show.
 */

const CON_ID = new Set(["catalogo", "inventario", "editar"]);

export function parseRoute(hash) {
  // A query (#/bases?excel=conectado, from the Microsoft callback) is a
  // one-off notice for the page, never part of the route.
  const partes = String(hash ?? "").split("?")[0].replace(/^#\/?/, "").split("/").filter(Boolean);
  let decod;
  try { decod = partes.map(decodeURIComponent); } catch { return null; }
  const [a, b, c] = decod;
  if (a === "catalogo" && !c) return { nombre: "catalogo", id: b ?? null };
  if (a === "inventario") {
    if (b === "nuevo" && !c) return { nombre: "nuevo", id: null };
    if (b && c === "editar") return { nombre: "editar", id: b };
    if (!c) return { nombre: "inventario", id: b ?? null };
  }
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

export const defaultRoute = (autenticado) =>
  ({ nombre: autenticado ? "inventario" : "catalogo", id: null });

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

/* Contract-v1 fixtures for the inventory/catalog interface.
 *
 * The JSON files beside this module are plain contract payloads (same shapes
 * as server/api/inventario.py and server/repo/inventario.py produce), so the
 * backend and the verifier can load them too. This module adds a generator for
 * page-boundary cases and a pager that mimics the server's stable-id cursor.
 */

import { readFileSync } from "node:fs";

export const fixture = (name) =>
  JSON.parse(readFileSync(new URL(`./${name}.json`, import.meta.url), "utf8"));

const ESTADOS = [["Jalisco", "Zapopan"], ["Jalisco", "Tlajomulco"], ["Guanajuato", "León"],
  ["Nuevo León", "Apodaca"], ["Querétaro", "El Marqués"]];

/** `n` published PublicTerrain records with ids that sort in creation order. */
export function publicTerrains(n) {
  return Array.from({ length: n }, (_, i) => {
    const [estado, municipio] = ESTADOS[i % ESTADOS.length];
    const usd = i % 3 === 0;
    return {
      id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`,
      revision_id: `10000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`,
      terreno: `Terreno sintético ${i + 1}`,
      estado, municipio, direccion: null,
      superficie_m2: 1000 + i * 37, superficie_ha: null, afectaciones_pct: null, afectaciones_m2: null,
      lat: 20 + (i % 50) * 0.01, lon: -103 + (i % 40) * 0.01,
      asking_price: usd ? 100000 + i : 2000000 + i * 10, asking_m2: usd ? 122.5 : 1500,
      moneda: usd ? "USD" : "MXN", price_on_request: false,
      availability: i % 7 === 0 ? "negotiation" : "available",
      public_description: null, published_at: "2026-10-05T12:00:00Z",
    };
  });
}

/** One page the way the server cuts it: id order, cursor = last id returned. */
export function paginate(items, { limit = 100, cursor = null } = {}) {
  const ordered = [...items].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const rest = cursor ? ordered.filter((t) => t.id > cursor) : ordered;
  const chunk = rest.slice(0, limit);
  return {
    terrenos: chunk,
    total: items.length,
    next_cursor: rest.length > limit ? chunk.at(-1).id : null,
    facets: {
      estados: [...new Set(items.map((t) => t.estado))].sort(),
      municipios: [...new Set(items.map((t) => t.municipio))].sort(),
      monedas: [...new Set(items.map((t) => t.moneda).filter(Boolean))].sort(),
    },
  };
}

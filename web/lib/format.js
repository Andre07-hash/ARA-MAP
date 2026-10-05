/* Display formatting, Spanish (Mexico).
 *
 * Every price carries its own currency ("USD" or "MXN"), recorded when it was
 * imported, and is shown with that code: a bare "$" means dollars and pesos
 * alike. Nothing is assumed from magnitudes or places, and nothing is
 * converted. A price whose currency was never recorded (data from before
 * prices carried one) says so rather than borrowing a currency.
 */

export const LOCALE = "es-MX";
export const MONEDAS = ["USD", "MXN"];

const formatosDinero = new Map();
function dinero(moneda, decimales) {
  const clave = `${moneda}:${decimales}`;
  if (!formatosDinero.has(clave)) {
    formatosDinero.set(clave, new Intl.NumberFormat(LOCALE, {
      style: "currency", currency: moneda, currencyDisplay: "code",
      minimumFractionDigits: decimales, maximumFractionDigits: decimales,
    }));
  }
  return formatosDinero.get(clave);
}
const conMoneda = (texto, moneda) => (MONEDAS.includes(moneda) ? texto : `${texto} · sin moneda`);
const integer = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 });
const hectares = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 2, maximumFractionDigits: 4,
});
const percent = new Intl.NumberFormat(LOCALE, {
  style: "percent", maximumFractionDigits: 2,
});
const dateTime = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric", month: "short", year: "numeric",
});

const EMPTY = "—";

const isNumber = (v) => typeof v === "number" && Number.isFinite(v);

/** An amount in its own currency: "USD 388,689,722". */
export function fmtPrice(v, moneda) {
  if (!isNumber(v)) return EMPTY;
  return MONEDAS.includes(moneda) ? dinero(moneda, 0).format(v) : conMoneda(`$${integer.format(v)}`, moneda);
}
// Unit prices are small numbers where a rounded cent changes the meaning:
// the real data has 122.5 per m², which must show as 122.50, not 123.
export function fmtUnitPrice(v, moneda) {
  if (!isNumber(v)) return EMPTY;
  const decimales = Number.isInteger(v) ? 0 : 2;
  if (MONEDAS.includes(moneda)) return `${dinero(moneda, decimales).format(v)}/m²`;
  return conMoneda(`$${decimales ? decimal.format(v) : integer.format(v)}/m²`, moneda);
}

/**
 * The currencies of the priced terrains in a list. An unrecorded currency
 * counts as its own value (null): it may be either, so it never shares a
 * price scale with a known one. More than one entry means the prices cannot
 * be ranked, filtered or banded together.
 */
export function monedasDe(terrenos) {
  const vistas = new Set();
  for (const t of terrenos) {
    if (isNumber(t.asking_price) || isNumber(t.asking_m2)) vistas.add(t.moneda ?? null);
  }
  return [...vistas];
}

/** "USD y MXN", "USD y precios sin moneda" -- for messages about a mix. */
export function nombraMonedas(monedas) {
  const nombres = monedas.map((m) => m ?? "precios sin moneda registrada");
  return nombres.length > 1 ? `${nombres.slice(0, -1).join(", ")} y ${nombres.at(-1)}` : (nombres[0] ?? "");
}
export const fmtArea = (v) => (isNumber(v) ? `${integer.format(v)} m²` : EMPTY);
export const fmtHectares = (v) => (isNumber(v) ? `${hectares.format(v)} ha` : EMPTY);
export const fmtPercent = (v) => (isNumber(v) ? percent.format(v) : EMPTY);
export const fmtNumber = (v) => (isNumber(v) ? decimal.format(v) : EMPTY);
export const fmtCount = (v) => integer.format(v ?? 0);
export const fmtText = (v) => (v == null || v === "" ? EMPTY : String(v));

export const fmtCoord = (lat, lon) =>
  isNumber(lat) && isNumber(lon) ? `${lat.toFixed(6)}, ${lon.toFixed(6)}` : EMPTY;

export function fmtDate(iso) {
  if (!iso) return EMPTY;
  const parsed = new Date(iso);
  return Number.isNaN(parsed.valueOf()) ? EMPTY : dateTime.format(parsed);
}

/** "3 terrenos" / "1 terreno" -- Spanish pluralisation for the few nouns used. */
export function plural(count, singular, pluralForm = `${singular}s`) {
  return `${integer.format(count)} ${count === 1 ? singular : pluralForm}`;
}

/** A compact price for dense contexts: USD 1.2 M, USD 388 M, USD 122.5. */
export function fmtPriceShort(v, moneda) {
  if (!isNumber(v)) return EMPTY;
  const signo = MONEDAS.includes(moneda) ? `${moneda} ` : "$";
  if (Math.abs(v) >= 1_000_000) return `${signo}${decimal.format(v / 1_000_000)} M`;
  // Below ten thousand, keep a decimal: rounding 1,300 and 1,900 both to
  // "1 k" makes a legend show the same label for different bands.
  if (Math.abs(v) >= 10_000) return `${signo}${integer.format(Math.round(v / 1_000))} k`;
  if (Math.abs(v) >= 1_000) return `${signo}${decimal.format(v / 1_000)} k`;
  return `${signo}${decimal.format(v)}`;
}

/** A Google Maps search link, used by the unplaced list to find coordinates. */
export function googleMapsSearch(terreno) {
  const parts = [terreno.direccion, terreno.municipio, terreno.estado, "México"]
    .filter(Boolean);
  const query = parts.length > 1 ? parts.join(", ") : `${terreno.terreno}, México`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

/** Strip accents and case so search matches the way people actually type. */
export function foldText(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

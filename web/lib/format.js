/* Display formatting, Spanish (Mexico).
 *
 * Every price is in Mexican pesos and is shown as MXN. Nothing is converted.
 */

export const LOCALE = "es-MX";

const pesos = [0, 2].map((decimales) => new Intl.NumberFormat(LOCALE, {
  style: "currency", currency: "MXN", currencyDisplay: "code",
  minimumFractionDigits: decimales, maximumFractionDigits: decimales,
}));
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

/** An amount in pesos: "MXN 388,689,722". */
export function fmtPrice(v) {
  return isNumber(v) ? pesos[0].format(v) : EMPTY;
}
// Unit prices are small numbers where a rounded cent changes the meaning:
// the real data has 122.5 per m², which must show as 122.50, not 123.
export function fmtUnitPrice(v) {
  if (!isNumber(v)) return EMPTY;
  return `${pesos[Number.isInteger(v) ? 0 : 1].format(v)}/m²`;
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

/** A compact price for dense contexts: MXN 1.2 M, MXN 388 M, MXN 122.5. */
export function fmtPriceShort(v) {
  if (!isNumber(v)) return EMPTY;
  const signo = "MXN ";
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

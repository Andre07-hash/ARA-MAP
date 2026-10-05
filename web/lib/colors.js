/* Colour assignment for the map.
 *
 * Every palette here was checked with the dataviz validator rather than chosen
 * by eye. Map markers are scatter-like, so the ALL-PAIRS gate applies, not the
 * easier adjacent-pairs one.
 *
 * Validation record (validate_palette.js, surfaces below, --pairs all):
 *
 *   Comparison, light basemap  #2a78d6,#eb6834,#1baf7a  vs #f4f4f2
 *     PASS band · PASS chroma · PASS CVD dE 9.2 · PASS normal dE 24.0 · WARN contrast
 *   Comparison, satellite      #3987e5,#d95926,#199e70  vs #3a3f38
 *     PASS band · PASS chroma · PASS CVD dE 9.4 · PASS normal dE 20.9 · WARN contrast
 *   Price ramp, ordinal gate   #6da7ec..#0d366b        vs #f4f4f2
 *     PASS monotone · PASS step gaps · PASS light end 2.27:1 · PASS single hue
 *
 * Measured all-pairs results for this ordering on the light basemap:
 *   3 layers  CVD dE 9.2  normal dE 24.0   PASS
 *   4 layers  CVD dE 9.2  normal dE 16.3   PASS
 *   5 layers  CVD dE 9.1  normal dE 13.7   normal-vision floor FAILS
 *   6 layers  CVD dE 6.1  normal dE 12.9   both fail
 *   8 layers  CVD dE 3.2  normal dE  7.1   both fail badly
 *
 * Four is therefore the honest limit for hue alone. Layers beyond it are
 * allowed, but they are drawn with a dashed ring and flagged in the interface,
 * so identity never rests on colour by itself.
 *
 * The contrast WARN obliges "relief": the legend is always present and names
 * every layer, a table view exists, and every marker carries a white ring --
 * which is also what keeps markers legible over arbitrary satellite imagery.
 */

/* Colours alone stay reliably distinguishable up to CAPAS_SEGURAS layers.
 * Past that the marks carry a dashed ring as a second channel and the legend
 * says so, which is what the colour-vision guidance requires when a palette is
 * pushed beyond its validated range. MAX_CAPAS is the size of the palette. */
export const CAPAS_SEGURAS = 4;
export const MAX_CAPAS = 8;

const COMPARISON = {
  claro:    ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7",
             "#eda100", "#e87ba4", "#008300", "#e34948"],
  calles:   ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7",
             "#eda100", "#e87ba4", "#008300", "#e34948"],
  satelite: ["#3987e5", "#d95926", "#199e70", "#9085e9",
             "#c98500", "#d55181", "#008300", "#e66767"],
};

/* Sequential, one hue, light to dark: blue steps 300-700. Starts at 300 rather
 * than the ramp's lightest step because the map surface is darker than the
 * reference chart surface and step 250 missed the 2:1 floor against it. */
export const PRICE_RAMP = ["#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];

/* A single hue for the one-base map when price is unknown or not in play. */
export const NEUTRAL_MARK = "#256abf";

export const MARK_RING = "#ffffff";

export function comparisonPalette(basemap = "claro") {
  return COMPARISON[basemap] ?? COMPARISON.claro;
}

/** The colour for layer `index` of a comparison, on a given basemap. */
export function layerColor(index, basemap = "claro") {
  const palette = comparisonPalette(basemap);
  return palette[index % palette.length];
}

/** Layers past the validated range get a second, non-colour channel. */
export function layerNeedsPattern(index) {
  return index >= CAPAS_SEGURAS;
}

/** The dash pattern for a layer's ring, or null for a solid ring. */
export function layerDash(index) {
  return layerNeedsPattern(index) ? "3 2" : null;
}

/** Re-colour saved layers for the basemap now showing, keeping layer order. */
export function recolorLayers(capas, basemap) {
  const palette = comparisonPalette(basemap);
  return capas.map((capa, index) => ({ ...capa, color: palette[index % palette.length] }));
}

/**
 * Quantile thresholds for the price ramp.
 * Quantiles rather than equal intervals because asking prices are heavily
 * skewed -- a few very large parcels would otherwise flatten every other mark
 * into the lightest bin.
 */
export function priceBreaks(values) {
  const sorted = values
    .filter((v) => typeof v === "number" && Number.isFinite(v))
    .sort((a, b) => a - b);
  if (sorted.length < PRICE_RAMP.length) return null;

  const breaks = [];
  for (let i = 1; i < PRICE_RAMP.length; i += 1) {
    breaks.push(sorted[Math.floor((sorted.length * i) / PRICE_RAMP.length)]);
  }
  return breaks;
}

/** Pick a ramp step for one value. Unknown values fall back to a neutral grey. */
export function priceColor(value, breaks) {
  if (!breaks || typeof value !== "number" || !Number.isFinite(value)) return "#9a9892";
  let step = 0;
  while (step < breaks.length && value >= breaks[step]) step += 1;
  return PRICE_RAMP[step];
}

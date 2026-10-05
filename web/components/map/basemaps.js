/* Basemap definitions.
 *
 * All layers here are free and need no API key. CARTO's Positron was the first
 * choice and was dropped: its tiles return HTTP 200 but the image itself is
 * stamped "API KEY REQUIRED", which only shows up when you actually look at a
 * rendered tile. Esri's Light Gray Canvas gives the same quiet grey with no
 * key and no watermark, and it pairs with the imagery layer already in use.
 *
 * Esri splits its cartographic basemaps into a base and a separate reference
 * layer carrying the place names, so "capas" stacks both.
 */

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";

export const BASEMAPS = {
  claro: {
    etiqueta: "Claro",
    descripcion: "Mapa gris y discreto: los terrenos resaltan",
    capas: [
      `${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
      `${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
    ],
    attribution: "Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
    maxZoom: 16,
    oscuro: false,
  },
  satelite: {
    etiqueta: "Satélite",
    descripcion: "Imagen aérea: se ve el terreno real",
    capas: [
      `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
      `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`,
    ],
    attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
    maxZoom: 19,
    oscuro: true,
  },
  calles: {
    etiqueta: "Calles",
    descripcion: "Mapa con nombres de calles y referencias",
    capas: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
    oscuro: false,
  },
};

/* Framing continental Mexico plus Baja and the Yucatan. */
export const MEXICO_BOUNDS = [[14.3, -118.5], [32.8, -86.5]];

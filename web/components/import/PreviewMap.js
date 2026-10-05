/* A small map of what an import would place, shown before anything is saved.
 *
 * Points only: a dot per located terrain. It does not draw parcel footprints,
 * and the text beside it says the points are the file's coordinates, not a
 * surveyed boundary. Leaflet needs a laid-out container, so it is created
 * after the dialog is open and removed whenever the preview is replaced.
 */

import { el } from "../../lib/dom.js";
import { BASEMAPS, MEXICO_BOUNDS } from "../map/basemaps.js";

export function PreviewMap(puntos = []) {
  const contenedor = el("div", { class: "preview-map", role: "img",
    "aria-label": `Mapa de vista previa con ${puntos.length} terrenos ubicados` });
  let mapa = null;

  function montar() {
    if (mapa || !window.L || !contenedor.isConnected) return;
    mapa = L.map(contenedor, { zoomControl: true, scrollWheelZoom: false, attributionControl: true });
    mapa.attributionControl.setPrefix("");
    const spec = BASEMAPS.claro;
    spec.capas.forEach((url, i) => L.tileLayer(url, {
      attribution: i === 0 ? spec.attribution : "", maxNativeZoom: spec.maxZoom, maxZoom: 18,
    }).addTo(mapa));
    const capa = L.featureGroup(puntos.map(([lat, lon, nombre]) =>
      L.circleMarker([lat, lon], { radius: 5, weight: 2, color: "#ffffff", fillColor: "#2a78d6", fillOpacity: 0.9 })
        .bindTooltip(String(nombre)))).addTo(mapa);
    if (puntos.length) mapa.fitBounds(capa.getBounds().pad(0.2), { maxZoom: 12 });
    else mapa.fitBounds(MEXICO_BOUNDS);
  }

  function destruir() {
    mapa?.remove();
    mapa = null;
  }

  return { element: contenedor, montar, destruir };
}

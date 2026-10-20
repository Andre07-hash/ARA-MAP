// Fictitious dataset shared by every mockup (and by the local seed used to
// capture the current product). No real terrains, people or contacts.
// X is the latitude and Y the longitude, as in ARA's files.

const T = (o) => ({ base: "Bajío Industrial 2026", ...o });

// ubic: "contorno" (active KMZ/KML contour), "punto" (X/Y only),
//       "elegir" (KML with several candidates, none active), "ninguna"
export const DESTACADOS = [
  T({ id: "apaseo", tipo: "Industrial", nombre: "Polígono Apaseo El Grande – Fracción Norte del Rancho San Bartolo", estado: "Guanajuato", municipio: "Apaseo el Grande", m2: 184500, ha: 18.45, afect: 12, precio: 92250000, pm2: 500, notas: "Frente a carretera federal 45. Revisar derecho de vía CFE.", x: 20.555, y: -100.700, ubic: "contorno", kmz: "poligono-apaseo.kmz", pdf: ["ficha-tecnica.pdf"], etapa: "Oferta", visita: "2026-09-14", broker: "Inmobiliaria Bajío Centro", uso: "Industrial ligera", editado: "Olga Ficticia · hoy 10:42", version: 3 }),
  T({ id: "sanmiguel", tipo: "Industrial", nombre: "Parque Logístico San Miguel Oriente", estado: "Guanajuato", municipio: "San Miguel de Allende", m2: 96000, ha: 9.6, afect: null, precio: null, pm2: null, notas: "Precio a consultar con el propietario.", x: 20.905, y: -100.760, ubic: "contorno", kmz: "parque-sanmiguel.kmz", pdf: [], etapa: "En análisis", visita: "2026-10-02", broker: null, uso: "Mixto" }),
  T({ id: "colon", tipo: "Industrial", nombre: "Colón km 12 – Lote A", estado: "Querétaro", municipio: "Colón", m2: 250000, ha: 25, afect: 4.5, precio: 112500000, pm2: 450, x: 20.780, y: -100.050, ubic: "contorno", kmz: "colon-km12.kmz", pdf: ["escrituras-folio-real.pdf"], etapa: "Oferta", visita: "2026-08-28", broker: "Grupo Arvo Bienes Raíces", uso: "Industrial pesada" }),
  T({ id: "silao", tipo: "Industrial", nombre: "Silao Puerto Interior, ampliación sur", estado: "Guanajuato", municipio: "Silao de la Victoria", m2: 72300, ha: 7.23, afect: 0, precio: 65070000, pm2: 900, notas: "Afectaciones confirmadas en cero por el topógrafo.", x: 20.960, y: -101.420, ubic: "contorno", kmz: "silao-puerto.kmz", pdf: ["levantamiento-topografico.pdf"], etapa: "Prospecto", broker: "Directo con propietario", uso: "Industrial ligera" }),
  T({ id: "villareyes", tipo: "Industrial", nombre: "Villa de Reyes – Predio La Ventilla", estado: "San Luis Potosí", municipio: "Villa de Reyes", m2: 310000, ha: 31, afect: 18, precio: null, pm2: 380, notas: "Sólo hay precio por m².", x: 21.800, y: -100.930, ubic: "contorno", kmz: "villa-reyes.kmz", pdf: [], etapa: "En análisis", visita: "2026-09-30", broker: "Inmobiliaria Bajío Centro", uso: "Industrial pesada" }),
  T({ id: "penuelas", tipo: "Comercial", nombre: "Peñuelas frente a libramiento", estado: "Aguascalientes", municipio: "Aguascalientes", m2: 18250, ha: 1.825, afect: null, precio: 41062500, pm2: 2250, x: 21.770, y: -102.310, ubic: "contorno", kmz: "penuelas.kmz", pdf: ["uso-de-suelo-dictamen.pdf"], etapa: "Prospecto" }),
  T({ id: "marques", tipo: "Industrial", nombre: "El Marqués – Polígono sin coordenadas capturadas", estado: "Querétaro", municipio: "El Marqués", m2: 128000, ha: 12.8, afect: 6, precio: 89600000, pm2: 700, notas: "Las X/Y del Excel venían vacías; sólo hay KMZ.", x: null, y: null, cx: 20.640, cy: -100.300, ubic: "contorno", kmz: "sin-coordenadas-elmarques.kmz", pdf: ["ficha-tecnica.pdf"], etapa: "Oferta", visita: "2026-10-10", broker: "Grupo Arvo Bienes Raíces", uso: "Industrial ligera" }),
  T({ id: "celaya", tipo: "Habitacional", nombre: "Celaya Poniente – Lotes 4 y 5", estado: "Guanajuato", municipio: "Celaya", m2: 41800, ha: 4.18, afect: 2, precio: 25080000, pm2: 600, notas: "El KML trae dos lotes; falta elegir contorno.", x: 20.530, y: -100.810, ubic: "elegir", kmz: "varios-lotes-celaya.kml", pdf: [], etapa: "En análisis", visita: "2026-09-21", broker: "Casas del Laja", uso: "Habitacional H4" }),
  T({ id: "fresnos", tipo: "Agrícola", nombre: "Rancho Los Fresnos (temporal)", estado: "Guanajuato", municipio: "Dolores Hidalgo", m2: 1250000, ha: 125, afect: null, precio: null, pm2: null, x: 21.160, y: -100.930, ubic: "punto", pdf: [], etapa: "Descartado", visita: "2026-07-03", uso: "Agrícola" }),
  T({ id: "corredor57", tipo: "Industrial", nombre: "Corredor 57 – Santa Rosa Jáuregui", estado: "Querétaro", municipio: "Querétaro", m2: 205000, ha: 20.5, afect: 9, precio: 153750000, pm2: 750, x: 20.745, y: -100.450, ubic: "punto", pdf: ["ficha-tecnica.pdf"], etapa: "Oferta", visita: "2026-10-06", broker: "Inmobiliaria Bajío Centro", uso: "Industrial ligera" }),
  T({ id: "juriquilla", tipo: "Comercial", nombre: "Plaza Juriquilla esquina Boulevard", estado: "Querétaro", municipio: "Querétaro", m2: 8600, ha: 0.86, afect: null, precio: 60200000, pm2: 7000, x: 20.710, y: -100.445, ubic: "punto", pdf: [], etapa: "Prospecto", uso: "Comercial" }),
  T({ id: "sintipo", tipo: null, nombre: "Terreno sin tipo – Pedro Escobedo", estado: "Querétaro", municipio: "Pedro Escobedo", m2: 54000, ha: 5.4, afect: null, precio: null, pm2: null, notas: "Pendiente clasificar.", x: 20.500, y: -100.140, ubic: "punto", pdf: [] }),
  T({ id: "leon", tipo: "Industrial", nombre: "León Norte, Parque Santa Fe III", estado: "Guanajuato", municipio: "León", m2: 67000, ha: 6.7, afect: 3, precio: 53600000, pm2: 800, x: 21.180, y: -101.640, ubic: "punto", pdf: ["escrituras-folio-real.pdf"], etapa: "En análisis", visita: "2026-09-11", broker: "Grupo Arvo Bienes Raíces", uso: "Industrial ligera" }),
  T({ id: "irapuato", tipo: "Industrial", nombre: "Irapuato – Castro del Río, fracción B", estado: "Guanajuato", municipio: "Irapuato", m2: 143000, ha: 14.3, afect: null, precio: 78650000, pm2: 550, x: 20.690, y: -101.360, ubic: "punto", pdf: [], etapa: "Prospecto" }),
  T({ id: "sanisidro", tipo: "Habitacional", nombre: "Fraccionamiento San Isidro (2ª etapa)", estado: "Querétaro", municipio: "Corregidora", m2: 36500, ha: 3.65, afect: 0, precio: 54750000, pm2: 1500, x: 20.540, y: -100.420, ubic: "punto", pdf: [], etapa: "Oferta", visita: "2026-08-19", broker: "Casas del Laja", uso: "Habitacional H3" }),
  T({ id: "lagos", tipo: "Industrial", nombre: "Lagos de Moreno – Puerta Norte", estado: "Jalisco", municipio: "Lagos de Moreno", m2: 188000, ha: 18.8, afect: 22, precio: null, pm2: null, notas: "Afectación alta por arroyo.", x: 21.370, y: -101.900, ubic: "punto", pdf: [], etapa: "Descartado", visita: "2026-06-30" }),
  T({ id: "griega", tipo: "Agrícola", nombre: "Ejido La Griega, parcelas 31–36", estado: "Querétaro", municipio: "El Marqués", m2: 420000, ha: 42, afect: null, precio: null, pm2: 95, x: 20.640, y: -100.210, ubic: "punto", pdf: [], etapa: "Prospecto", uso: "Agrícola" }),
  T({ id: "iturbide", tipo: "Industrial", nombre: "San José Iturbide – Parque Opción", estado: "Guanajuato", municipio: "San José Iturbide", m2: 99000, ha: 9.9, afect: 5, precio: 59400000, pm2: 600, x: 21.010, y: -100.390, ubic: "punto", pdf: [], etapa: "En análisis", visita: "2026-10-01", broker: "Inmobiliaria Bajío Centro", uso: "Industrial ligera" }),
];

// The other 30 rows of the base, the same deterministic filler the local seed wrote.
const MUN = [["Guanajuato", "Celaya", 20.52, -100.82], ["Querétaro", "Querétaro", 20.6, -100.39], ["San Luis Potosí", "San Luis Potosí", 22.15, -100.98], ["Aguascalientes", "Jesús María", 21.96, -102.34], ["Guanajuato", "León", 21.12, -101.68], ["Querétaro", "San Juan del Río", 20.39, -99.99], ["Jalisco", "Ocotlán", 20.35, -102.77]];
const PRE = ["Fracción", "Lote", "Predio", "Parcela", "Polígono", "Reserva"];
const SUF = ["El Sauz", "La Estancia", "Los Ángeles", "San Antonio de la Cal", "El Pueblito", "Santa Teresa", "La Purísima", "Tres Cruces", "El Retoño", "Buenavista"];
export const RELLENO = Array.from({ length: 30 }, (_, i) => {
  const [estado, municipio, la, lo] = MUN[i % MUN.length];
  const m2 = 15000 + ((i * 7919) % 260000);
  const pm2 = i % 6 === 0 ? null : 300 + ((i * 131) % 1400);
  const sinXY = i % 13 === 0;
  return T({
    id: `r${i}`, tipo: ["Industrial", "Comercial", "Habitacional", "Agrícola", "Industrial"][i % 5],
    nombre: `${PRE[i % 6]} ${SUF[i % 10]} ${i % 4 === 0 ? "– frente a vialidad primaria, con servidumbre de paso" : i + 3}`,
    estado, municipio, m2, ha: i % 9 === 0 ? null : +(m2 / 10000).toFixed(4), afect: i % 3 === 0 ? null : (i * 3) % 25,
    precio: pm2 && i % 4 !== 1 ? m2 * pm2 : null, pm2, notas: i % 5 === 0 ? "Visita pendiente." : null,
    x: sinXY ? null : +(la + ((i * 37) % 40 - 20) / 200).toFixed(4), y: sinXY ? null : +(lo + ((i * 53) % 40 - 20) / 200).toFixed(4),
    ubic: sinXY ? "ninguna" : "punto", pdf: [], etapa: ["Prospecto", "En análisis", "Oferta", null, "Descartado"][i % 5],
    visita: i % 3 ? null : `2026-${String(7 + (i % 4)).padStart(2, "0")}-${String(3 + (i % 25)).padStart(2, "0")}`,
    broker: i % 2 ? null : "Directo con propietario",
  });
});

export const TODOS = [...DESTACADOS, ...RELLENO];
export const porId = Object.fromEntries(TODOS.map((t) => [t.id, t]));

// Other scopes, for the base switcher.
export const BASES = [
  { nombre: "Bajío Industrial 2026", n: 48, operadores: ["Olga Ficticia", "Omar Ficticio"] },
  { nombre: "Península y Sureste", n: 4, operadores: ["Omar Ficticio"] },
];
export const SIN_ASIGNAR = 2;
export const MAESTRA = 54;

// Deterministic contour around a centre (same idea as the KMZ fixtures).
export function contorno(t, w = 0.010, h = 0.007, n = 6) {
  const la = t.cx ?? t.x, lo = t.cy ?? t.y;
  let s = Math.abs(Math.round(la * 1000 + lo * 100));
  const rnd = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  return Array.from({ length: n }, (_, i) => {
    const a = (2 * Math.PI * i) / n, r = 1 + (rnd() - 0.5) * 0.5;
    return [la + h * r * Math.sin(a), lo + w * r * Math.cos(a)];
  });
}
export const TAMANO_CONTORNO = { apaseo: [0.010, 0.007], sanmiguel: [0.008, 0.006], colon: [0.012, 0.008], silao: [0.009, 0.006], villareyes: [0.011, 0.009], penuelas: [0.006, 0.005], marques: [0.007, 0.005] };

/* Asking $/m² classes: quantile breaks over the rows that have one (as the
 * app's priceBreaks does). Nothing is computed for a row without the value. */
export const RAMPA = ["#4384d4", "#2f6fc4", "#1f58a6", "#164382", "#0d2f5e"];
export function cortes(filas = TODOS) {
  const v = filas.map((t) => t.pm2).filter((n) => n != null).sort((a, b) => a - b);
  return [0.2, 0.4, 0.6, 0.8].map((q) => v[Math.floor(q * (v.length - 1))]);
}
export function colorPrecio(t, br = cortes()) {
  if (t.pm2 == null) return null;
  let i = 0; while (i < br.length && t.pm2 >= br[i]) i++;
  return RAMPA[i];
}

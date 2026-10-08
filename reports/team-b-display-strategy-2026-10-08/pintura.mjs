/* Paint comparison helpers (correction F2, supervisory review of PR #16).
 *
 * Every mask carries the REAL canvas width and height it was captured
 * from; every spatial operation uses that stride, and comparing masks of
 * different sizes is an error. Three different measures, none of which alone
 * proves that every polygon and hole is semantically correct:
 *   - RGBA identity: equal SHA-256 of the complete RGBA buffers;
 *   - alpha-mask overlap: IoU of painted (alpha > 0) pixels;
 *   - tolerance coverage: the share of one side's painted pixels with a
 *     painted pixel of the other within r pixels (square neighbourhood).
 * Pure functions; Node tests in pruebas/pintura.test.mjs.
 */

/** {ancho, alto, bits} from RGBA bytes: bits[i] = 1 where alpha > 0. */
export function mascaraDeRGBA(rgba, ancho, alto) {
  if (rgba.length !== ancho * alto * 4) throw new Error(`RGBA length ${rgba.length} != ${ancho}x${alto}x4`);
  const bits = new Uint8Array(ancho * alto);
  for (let i = 3, k = 0; i < rgba.length; i += 4, k += 1) if (rgba[i]) bits[k] = 1;
  return { ancho, alto, bits };
}

export function crearMascara(ancho, alto) {
  return { ancho, alto, bits: new Uint8Array(ancho * alto) };
}

export function mismasDimensiones(a, b) {
  if (a.ancho !== b.ancho || a.alto !== b.alto || a.bits.length !== a.ancho * a.alto
      || b.bits.length !== b.ancho * b.alto) {
    throw new Error(`mask sizes differ: ${a.ancho}x${a.alto} vs ${b.ancho}x${b.alto}`);
  }
}

export function pintados(m) {
  let n = 0;
  for (let i = 0; i < m.bits.length; i += 1) n += m.bits[i];
  return n;
}

/** Intersection over union of painted pixels (1 when both are blank). */
export function iou(a, b) {
  mismasDimensiones(a, b);
  let inter = 0; let union = 0;
  for (let i = 0; i < a.bits.length; i += 1) { inter += a.bits[i] & b.bits[i]; union += a.bits[i] | b.bits[i]; }
  return union ? inter / union : 1;
}

/** Square dilation by r pixels (separable max filter), in the mask's own stride. */
export function dilatar(m, r) {
  const { ancho, alto } = m;
  if (r === 0) return m;
  const h = new Uint8Array(ancho * alto);
  for (let y = 0; y < alto; y += 1) {
    const fila = y * ancho;
    for (let x = 0; x < ancho; x += 1) {
      if (!m.bits[fila + x]) continue;
      const x0 = Math.max(0, x - r); const x1 = Math.min(ancho - 1, x + r);
      for (let xx = x0; xx <= x1; xx += 1) h[fila + xx] = 1;
    }
  }
  const v = new Uint8Array(ancho * alto);
  for (let y = 0; y < alto; y += 1) {
    for (let x = 0; x < ancho; x += 1) {
      if (!h[y * ancho + x]) continue;
      const y0 = Math.max(0, y - r); const y1 = Math.min(alto - 1, y + r);
      for (let yy = y0; yy <= y1; yy += 1) v[yy * ancho + x] = 1;
    }
  }
  return { ancho, alto, bits: v };
}

/** Share of a's painted pixels with a painted pixel of b within r px (1 when a is blank). */
export function cobertura(a, b, r) {
  mismasDimensiones(a, b);
  const d = dilatar(b, r);
  let total = 0; let cubiertos = 0;
  for (let i = 0; i < a.bits.length; i += 1) {
    if (!a.bits[i]) continue;
    total += 1;
    cubiertos += d.bits[i];
  }
  return total ? cubiertos / total : 1;
}

/** The mask moved by (dx, dy) px; pixels leaving the canvas are dropped. */
export function desplazar(m, dx, dy) {
  const { ancho, alto } = m;
  const out = crearMascara(ancho, alto);
  for (let y = 0; y < alto; y += 1) {
    const yy = y + dy;
    if (yy < 0 || yy >= alto) continue;
    for (let x = 0; x < ancho; x += 1) {
      const xx = x + dx;
      if (xx < 0 || xx >= ancho || !m.bits[y * ancho + x]) continue;
      out.bits[yy * ancho + xx] = 1;
    }
  }
  return out;
}

/** Copy with every pixel at linear index >= desde cleared (negative control). */
export function borrarDesde(m, desde) {
  const out = { ancho: m.ancho, alto: m.alto, bits: m.bits.slice() };
  out.bits.fill(0, desde);
  return out;
}

/** Painted pixels in the last `n` columns / rows (edge effects of desplazar). */
export function enBorde(m, n) {
  let c = 0;
  for (let y = 0; y < m.alto; y += 1) {
    for (let x = 0; x < m.ancho; x += 1) {
      if ((x >= m.ancho - n || y >= m.alto - n) && m.bits[y * m.ancho + x]) c += 1;
    }
  }
  return c;
}

/* Browser side: capture the overlay canvas (call inside page.evaluate via
 * its source). Returns real dimensions, full SHA-256 of the RGBA buffer, the
 * painted count and the alpha mask as base64 (one byte per pixel). */
export const CAPTURAR = `async () => {
  const lienzo = document.querySelector('.leaflet-overlay-pane canvas');
  const { data, width, height } = lienzo.getContext('2d').getImageData(0, 0, lienzo.width, lienzo.height);
  const bits = new Uint8Array(width * height);
  let pintados = 0;
  for (let i = 3, k = 0; i < data.length; i += 4, k += 1) if (data[i]) { bits[k] = 1; pintados += 1; }
  const h = await crypto.subtle.digest('SHA-256', data);
  const sha256 = [...new Uint8Array(h)].map((x) => x.toString(16).padStart(2, '0')).join('');
  let s = '';
  for (let i = 0; i < bits.length; i += 8192) s += String.fromCharCode(...bits.subarray(i, i + 8192));
  return { ancho: width, alto: height, dpr: window.devicePixelRatio, pintados, sha256, mascara: btoa(s) };
}`;

export function mascaraDeCaptura(c) {
  const bits = Uint8Array.from(Buffer.from(c.mascara, 'base64'));
  const m = { ancho: c.ancho, alto: c.alto, bits };
  mismasDimensiones(m, m);
  return m;
}

/* PROTOTYPE (display-strategy investigation; not application code).
 *
 * Two ways to draw a boundary on Leaflet 1.9.4's shared canvas renderer.
 *
 * 1. PoligonoSinClosePath (E1): an ordinary L.Polygon whose rings are closed
 *    with lineTo(first point) instead of ctx.closePath(). In Chromium 141 each
 *    closePath() on a path that already has many subpaths costs time
 *    proportional to those subpaths, so a 20,000-ring polygon spends ~2 s per
 *    redraw in closePath alone (see the report's microbenchmark). Fill closes
 *    subpaths implicitly; with Leaflet's round caps and joins the stroke is
 *    the same pixels (asserted by the paint-identity check).
 *
 * 2. CapaContorno (E2/E3): draws a body prepared by preparar.js. Positions
 *    are already projected (world units), so a view change is a multiply-add
 *    per visible position: no LatLng objects, no re-projection, no clipping or
 *    screen simplification. Parts whose box is wholly outside the renderer's
 *    padded bounds are skipped (culled); every part that can be on screen is
 *    drawn exactly. Hit testing uses the same visible parts and the same
 *    even-odd rule Leaflet uses for polygons, plus the stroke tolerance.
 */

export function crearClases(L) {
  const PoligonoSinClosePath = L.Polygon.extend({
    _updatePath() {
      const r = this._renderer;
      if (!r._drawing) return;
      const partes = this._parts;
      if (!partes.length) return;
      const ctx = r._ctx;
      ctx.beginPath();
      for (let i = 0; i < partes.length; i += 1) {
        const anillo = partes[i];
        for (let j = 0; j < anillo.length; j += 1) {
          const p = anillo[j];
          if (j) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y);
        }
        if (anillo.length) ctx.lineTo(anillo[0].x, anillo[0].y);   // instead of closePath()
      }
      r._fillStroke(ctx, this);
    },
  });

  /* 1b. PoligonoPath2D (e1p, added after the supervisory review): the
   *    lineTo(first) closing of E1 is NOT stroke-identical to closePath() at
   *    each ring's seam (round caps meet instead of a round join; anti-aliasing
   *    differs there). Here each ring is its own Path2D closed with
   *    closePath() (cheap: one subpath), merged with addPath, then filled and
   *    stroked by Leaflet's own _fillStroke through a context view whose
   *    fill()/stroke() use that path. Byte-identical to closePath() drawing in
   *    the measured cases; see the report's follow-up section. */
  const PoligonoPath2D = L.Polygon.extend({
    _updatePath() {
      const r = this._renderer;
      if (!r._drawing) return;
      const partes = this._parts;
      if (!partes.length) return;
      const trazo = new Path2D();
      for (let i = 0; i < partes.length; i += 1) {
        const anillo = partes[i];
        if (!anillo.length) continue;
        const a = new Path2D();
        a.moveTo(anillo[0].x, anillo[0].y);
        for (let j = 1; j < anillo.length; j += 1) a.lineTo(anillo[j].x, anillo[j].y);
        a.closePath();
        trazo.addPath(a);
      }
      r._ctx.beginPath();
      r._fillStroke(conTrazo(r._ctx, trazo), this);
    },
  });

  const CapaContorno = L.Path.extend({
    options: { fill: true },

    initialize(preparado, options) {
      L.Util.setOptions(this, options);
      this._prep = preparado;
      this._visibles = new Int32Array(preparado.partes);
      this._nVisibles = 0;
      this._escala = 1;
      this._origen = { x: 0, y: 0 };
    },

    getBounds() {
      const c = this._prep.cajaMundo;
      const crs = L.CRS.EPSG3857;
      // World units back to lat/lng only for the overall box (cheap, rare).
      const sw = crs.pointToLatLng(L.point(c[0] * 256, c[3] * 256), 0);
      const ne = crs.pointToLatLng(L.point(c[2] * 256, c[1] * 256), 0);
      return L.latLngBounds(sw, ne);
    },

    /** Zoom-dependent state: scale and pixel origin (Leaflet calls this on zoom/reset). */
    _project() {
      const map = this._map;
      this._escala = map.options.crs.scale(map.getZoom());
      this._origen = map.getPixelOrigin();
      this._updateBounds();
    },

    /** Pixel bounds of the whole body plus the stroke (Leaflet's redraw bookkeeping). */
    _updateBounds() {
      if (!this._map) return;
      const c = this._prep.cajaMundo;
      const k = this._escala;
      const o = this._origen;
      const w = this._clickTolerance();
      this._pxBounds = L.bounds([c[0] * k - o.x - w, c[1] * k - o.y - w],
                                [c[2] * k - o.x + w, c[3] * k - o.y + w]);
    },

    /** View-dependent state: which parts can be on screen (called on every moveend). */
    _update() {
      if (!this._map) return;
      const b = this._renderer._bounds;
      const k = this._escala;
      const o = this._origen;
      const tol = (this._clickTolerance() + 1) / k;
      const minX = (b.min.x + o.x) / k - tol;
      const minY = (b.min.y + o.y) / k - tol;
      const maxX = (b.max.x + o.x) / k + tol;
      const maxY = (b.max.y + o.y) / k + tol;
      const cajas = this._prep.cajasParte;
      let n = 0;
      for (let p = 0; p < this._prep.partes; p += 1) {
        const c = p * 4;
        if (cajas[c] > maxX || cajas[c + 2] < minX || cajas[c + 1] > maxY || cajas[c + 3] < minY) continue;
        this._visibles[n] = p;
        n += 1;
      }
      this._nVisibles = n;
      this._updatePath();
    },

    _updatePath() {
      const r = this._renderer;
      if (!r._drawing || this._nVisibles === 0) return;
      const ctx = r._ctx;
      const { x, y, inicioAnillo, inicioParte } = this._prep;
      const k = this._escala;
      const ox = this._origen.x;
      const oy = this._origen.y;
      ctx.beginPath();
      for (let v = 0; v < this._nVisibles; v += 1) {
        const p = this._visibles[v];
        for (let a = inicioParte[p]; a < inicioParte[p + 1]; a += 1) {
          const desde = inicioAnillo[a];
          const hasta = inicioAnillo[a + 1];
          ctx.moveTo(x[desde] * k - ox, y[desde] * k - oy);
          // Stored rings are closed (last == first), so the final lineTo closes them.
          for (let i = desde + 1; i < hasta; i += 1) ctx.lineTo(x[i] * k - ox, y[i] * k - oy);
        }
      }
      r._fillStroke(ctx, this);
    },

    /** Even-odd inside test over the drawn parts, or within the stroke tolerance. */
    _containsPoint(punto) {
      if (!this._pxBounds || this._nVisibles === 0) return false;
      const k = this._escala;
      const px = (punto.x + this._origen.x) / k;
      const py = (punto.y + this._origen.y) / k;
      const tol = this._clickTolerance() / k;
      const tol2 = tol * tol;
      const { x, y, inicioAnillo, inicioParte, cajasParte } = this._prep;
      let dentro = false;
      for (let v = 0; v < this._nVisibles; v += 1) {
        const p = this._visibles[v];
        const c = p * 4;
        if (px < cajasParte[c] - tol || px > cajasParte[c + 2] + tol
            || py < cajasParte[c + 1] - tol || py > cajasParte[c + 3] + tol) continue;
        for (let a = inicioParte[p]; a < inicioParte[p + 1]; a += 1) {
          for (let i = inicioAnillo[a], j = inicioAnillo[a + 1] - 1; i < inicioAnillo[a + 1]; j = i, i += 1) {
            const xi = x[i]; const yi = y[i]; const xj = x[j]; const yj = y[j];
            if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) dentro = !dentro;
            // Distance from the point to segment j-i, for clicks on the stroke.
            const dx = xi - xj; const dy = yi - yj;
            const l2 = dx * dx + dy * dy;
            let t = l2 ? ((px - xj) * dx + (py - yj) * dy) / l2 : 0;
            t = t < 0 ? 0 : t > 1 ? 1 : t;
            const ex = xj + t * dx - px; const ey = yj + t * dy - py;
            if (ex * ex + ey * ey <= tol2) return true;
          }
        }
      }
      return dentro;
    },
  });

  /* E4: when the parts that can be on screen exceed a measured budget, the
   * outline is rasterized by the worker (exact same path, both styles) for
   * an area larger than the view; the main thread only draws the bitmap.
   * Until a bitmap for THIS zoom covering THIS view arrives, nothing is
   * drawn or hit-testable and the state is "dibujando".
   *
   * F3 correction: the body is sent to the worker only when the layer first
   * needs a raster, and pinned there while the layer is on the map; it is
   * released on removal. If the worker budget is held by other pinned
   * outlines the state is "sin_memoria" (explicit, not pending). At most one
   * raster request per layer is in flight; a newer need waits in _siguiente
   * and replaces any older waiting one. */
  const CapaContornoRaster = CapaContorno.extend({
    initialize(preparado, options, { id, cliente, estilos, alCambiarEstado, enCache }) {
      CapaContorno.prototype.initialize.call(this, preparado, options);
      this._id = id;
      this._cliente = cliente;
      this._estilos = estilos;               // [normal, selected] Leaflet path options
      this._avisar = alCambiarEstado;
      this._enCache = enCache ?? (() => false);
      this._raster = null;                    // {escala, x0, y0, ancho, alto, bitmaps}
      this._pedido = null;                    // in flight: {numero, escala, x0, y0, ancho, alto}
      this._siguiente = null;                 // waiting: {area, vista}
      this._fijado = false;
      this._estado = "listo";
      this._pesado = false;
    },

    onRemove(map) {
      if (this._pedido) this._cliente.descartar(this._pedido.numero);
      this._pedido = null;
      this._siguiente = null;
      this._soltarRaster();
      if (this._fijado) { this._cliente.liberar(this._id); this._fijado = false; }
      CapaContorno.prototype.onRemove.call(this, map);
    },

    _soltarRaster() {
      if (this._raster) this._cliente.soltarBitmaps(this._raster.bitmaps);
      this._raster = null;
    },

    _ponerEstado(estado) {
      if (estado === this._estado) return;
      this._estado = estado;
      this._avisar?.(estado);
    },

    _cubre(r, minX, minY, maxX, maxY) {
      return r && r.escala === this._escala && r.x0 <= minX && r.y0 <= minY
        && r.x0 + r.ancho >= maxX && r.y0 + r.alto >= maxY;
    },

    /** Pin the body in the worker; false when the worker budget refuses it. */
    _asegurar() {
      if (this._fijado) return true;
      const r = this._cliente.asegurar(this._id, this._prep, { enCache: this._enCache() });
      if (r === "rechazado") return false;
      this._fijado = true;                    // "listo" or "esperando": requests queue behind it
      return true;
    },

    _lanzar(area) {
      const numero = this._cliente.pedir({ id: this._id, ...area, dpr: window.devicePixelRatio || 1,
                                           estilos: this._estilos }, (respuesta) => this._recibir(respuesta));
      this._pedido = numero === null ? null : { numero, ...area };
    },

    _recibir(respuesta) {
      if (!this._pedido || respuesta.pedido !== this._pedido.numero) {
        this._cliente.soltarBitmaps(respuesta.bitmaps);
        return;
      }
      const area = this._pedido;
      this._pedido = null;
      const siguiente = this._siguiente;
      this._siguiente = null;
      if (siguiente || !respuesta.bitmaps.length) {
        // A newer view needs a different area (or the worker had no body):
        // this reply is not shown; ask for what the view needs now.
        this._cliente.soltarBitmaps(respuesta.bitmaps);
        if (siguiente) this._lanzar(siguiente.area);
        return;
      }
      this._soltarRaster();
      this._raster = { escala: area.escala, x0: area.x0, y0: area.y0, ancho: area.ancho,
                       alto: area.alto, bitmaps: respuesta.bitmaps };
      if (this._map) this.redraw();           // re-checks coverage; becomes "listo" if it fits
    },

    _update() {
      if (!this._map) return;
      // Visible parts, as in E2/E3, then the measured weight of drawing them.
      const b = this._renderer._bounds;
      const k = this._escala;
      const o = this._origen;
      const tol = (this._clickTolerance() + 1) / k;
      const vx0 = (b.min.x + o.x) / k - tol; const vy0 = (b.min.y + o.y) / k - tol;
      const vx1 = (b.max.x + o.x) / k + tol; const vy1 = (b.max.y + o.y) / k + tol;
      const { cajasParte, inicioParte, inicioAnillo, partes } = this._prep;
      let n = 0; let posiciones = 0; let anillos = 0;
      for (let p = 0; p < partes; p += 1) {
        const c = p * 4;
        if (cajasParte[c] > vx1 || cajasParte[c + 2] < vx0 || cajasParte[c + 1] > vy1 || cajasParte[c + 3] < vy0) continue;
        this._visibles[n] = p; n += 1;
        anillos += inicioParte[p + 1] - inicioParte[p];
        posiciones += inicioAnillo[inicioParte[p + 1]] - inicioAnillo[inicioParte[p]];
      }
      this._nVisibles = n;
      this._pesado = posiciones > UMBRAL_POSICIONES || anillos > UMBRAL_ANILLOS;
      if (!this._pesado) {
        this._ponerEstado("listo");
        this._updatePath();
        return;
      }
      // Absolute pixel area of the view; a raster must cover it at this zoom.
      const minX = b.min.x + o.x; const minY = b.min.y + o.y;
      const maxX = b.max.x + o.x; const maxY = b.max.y + o.y;
      if (this._cubre(this._raster, minX, minY, maxX, maxY)) {
        this._ponerEstado("listo");
        this._updatePath();
        return;
      }
      if (!this._asegurar()) {
        this._ponerEstado("sin_memoria");
        return;
      }
      this._ponerEstado("dibujando");
      if (this._cubre(this._pedido, minX, minY, maxX, maxY)) { this._siguiente = null; return; }
      // Area: the view plus half its size on every side, so pans reuse it.
      const mx = (maxX - minX) / 2; const my = (maxY - minY) / 2;
      const area = { escala: k, x0: Math.floor(minX - mx), y0: Math.floor(minY - my),
                     ancho: Math.ceil(maxX - minX + 2 * mx), alto: Math.ceil(maxY - minY + 2 * my) };
      if (this._pedido) {
        // One request in flight per outline: the newest need waits, replacing older ones.
        this._siguiente = { area };
        return;
      }
      this._lanzar(area);
    },

    _updatePath() {
      if (!this._pesado) { CapaContorno.prototype._updatePath.call(this); return; }
      const r = this._renderer;
      if (!r._drawing || this._estado !== "listo" || !this._raster) return;
      const ctx = r._ctx;
      const bitmap = this._raster.bitmaps[this.options.seleccionado ? 1 : 0];
      ctx.globalAlpha = 1;
      ctx.drawImage(bitmap, this._raster.x0 - this._origen.x, this._raster.y0 - this._origen.y,
                    this._raster.ancho, this._raster.alto);
    },

    _containsPoint(punto) {
      // Hit testing follows what is painted: nothing while "dibujando" or "sin_memoria".
      if (this._pesado && this._estado !== "listo") return false;
      return CapaContorno.prototype._containsPoint.call(this, punto);
    },
  });

  return { PoligonoSinClosePath, PoligonoPath2D, CapaContorno, CapaContornoRaster };
}

/** The 2D context, with fill(rule) and stroke() applied to `trazo`. */
function conTrazo(ctx, trazo) {
  return new Proxy(ctx, {
    get(t, k) {
      if (k === "fill") return (regla) => t.fill(trazo, regla);
      if (k === "stroke") return () => t.stroke(trazo);
      const v = t[k];
      return typeof v === "function" ? v.bind(t) : v;
    },
    set(t, k, v) { t[k] = v; return true; },
  });
}

/* Above these, drawing on the main thread exceeds the 50 ms task budget on
 * the recorded machine (software raster: ~6 ms per 1,000 stroked rings,
 * ~1.5 ms per 1,000 stroked positions); see the report's microbenchmark. */
export const UMBRAL_ANILLOS = 2_000;
export const UMBRAL_POSICIONES = 20_000;

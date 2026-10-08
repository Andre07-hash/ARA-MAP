/* PROTOTYPE (memory-budget investigation; not application code).
 *
 * "E5": E4 (exact prepared drawing, sliced preparation, worker raster) with
 * every managed allocation admitted by a shared byte budget, and ONE
 * combined raster per map instead of a bitmap pair per heavy outline.
 *
 * Per map, a controller decides after every view update, layer change,
 * style change, raster reply, worker event or budget release:
 * - If the visible outlines together are light (<= UMBRAL_ANILLOS rings and
 *   <= UMBRAL_POSICIONES positions in the view), every outline draws itself
 *   on the main thread, as E3 does ("directo"). No raster memory is held.
 * - Otherwise ("compartido"), the worker draws ALL visible outlines, in the
 *   canvas renderer's order and with their current styles, into one bitmap
 *   of the canvas's real device size; one layer at the back of the canvas
 *   draws it 1:1. Outlines are always behind every symbol and XY mark (B-2's
 *   rule), so one image keeps the layering, the colours, the alpha and the
 *   overlaps; holes are each outline's own even-odd path, never combined
 *   with another outline's path. The selected outline is drawn once, in its
 *   own order, with the selected style.
 * - Until a bitmap for the current view exists, outlines are drawn directly
 *   while their running total stays light, in draw order; the rest show
 *   their interior-point symbol, "Cargando contorno…" ("dibujando").
 * - Memory, reserved before anything is allocated: worker copies of every
 *   outline in the request ("copia"), then the bitmap ("raster", canvas
 *   width x height x 4). If the new bitmap does not fit while the old one is
 *   shown, the old one is released first (its outlines wait as "dibujando").
 *   If it still does not fit: "demasiado_grande" when it could never fit the
 *   whole budget, else "sin_memoria"; waiting instead when releases are
 *   still being acknowledged.
 * - One raster request in flight per map. A newer view or style waits for
 *   it; an obsolete reply is closed and its reservation released, never
 *   painted.
 * - The worker failing in any way ("constructor", "sinOffscreen", "error",
 *   "sinRespuesta"): outlines that are light on their own are drawn directly
 *   while the running total stays light; the rest are "sin_trabajador" with
 *   their symbol. Never a synchronous heavy drawing. A new worker is tried
 *   on the next render() (reintentar).
 * Hit testing follows paint: an outline that is not painted (directly or in
 * the current bitmap) is not hit-testable; its symbol is.
 *
 * Leaflet 1.9.4 assumptions, explicit: the Canvas renderer's _drawFirst
 * order list, _bounds, _container, _ctx, _drawing, _redraw and the
 * _updatePaths loop (wrapped here to decide between the layer updates and
 * the redraw).
 */

export const UMBRAL_ANILLOS = 2_000;
export const UMBRAL_POSICIONES = 20_000;

const ESTILO = ["fill", "fillColor", "fillOpacity", "fillRule", "stroke", "color", "weight", "opacity",
                "lineCap", "lineJoin", "dashArray"];

function estiloDe(o) {
  const e = {};
  for (const k of ESTILO) e[k] = o[k];
  if (typeof e.dashArray === "string") e.dashArray = e.dashArray.split(/[, ]+/).map(Number);
  else if (!e.dashArray) e.dashArray = null;
  return e;
}

export function crearClasesE5(L, CapaContorno) {
  /** An outline drawn directly, from the bitmap, or not at all, as its controller decides. */
  const CapaContornoE5 = CapaContorno.extend({
    initialize(preparado, options, { id, controlador }) {
      CapaContorno.prototype.initialize.call(this, preparado, options);
      this._id = id;
      this._ctl = controlador;
      this._modo = "nada";                    // "directo" | "bitmap" | "nada"
      this._carga = { anillos: 0, posiciones: 0 };
    },
    onAdd(map) {
      CapaContorno.prototype.onAdd.call(this, map);
      this._ctl.agregar(this);
    },
    onRemove(map) {
      this._ctl.quitar(this);
      CapaContorno.prototype.onRemove.call(this, map);
    },
    bringToBack() {
      CapaContorno.prototype.bringToBack.call(this);
      this._ctl.alFondo();
      return this;
    },
    setStyle(estilo) {
      CapaContorno.prototype.setStyle.call(this, estilo);
      this._ctl.cambioDeEstilo(this);
      return this;
    },
    /** Visible parts and their weight; drawing is decided by the controller. */
    _update() {
      if (!this._map) return;
      const b = this._renderer._bounds;
      const k = this._escala; const o = this._origen;
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
      this._carga = { anillos, posiciones };
    },
    _updatePath() {
      if (this._modo === "directo") CapaContorno.prototype._updatePath.call(this);
    },
    _containsPoint(punto) {
      if (this._modo === "nada") return false;
      return CapaContorno.prototype._containsPoint.call(this, punto);
    },
  });

  /** The map's combined raster, at the back of the canvas, drawn 1:1. */
  const CapaBitmap = L.Path.extend({
    options: { interactive: false, fill: false, stroke: false },
    initialize(controlador, options) { L.Util.setOptions(this, options); this._ctl = controlador; },
    _project() { this._updateBounds(); },
    _updateBounds() { const b = this._renderer?._bounds; if (b) this._pxBounds = L.bounds(b.min, b.max); },
    _update() { this._updateBounds(); },
    _updatePath() {
      const r = this._renderer;
      const m = this._ctl.mostrada;
      if (!r._drawing || !m || !this._ctl.bitmapVigente()) return;
      const ctx = r._ctx;
      ctx.globalAlpha = 1;
      ctx.drawImage(m.bitmap, m.area.bmin[0], m.area.bmin[1], m.area.css[0], m.area.css[1]);
    },
    _containsPoint() { return false; },
    _empty() { return !this._ctl.mostrada; },
  });

  return { CapaContornoE5, CapaBitmap };
}

/**
 * The controller of one map. `crearCliente()` makes its worker client;
 * `alEstado(capa, estado)` reports "listo" | "dibujando" | "sin_memoria" |
 * "demasiado_grande" | "sin_trabajador" for an outline layer.
 */
export function crearControlador({ L, map, CapaBitmap, presupuesto, crearCliente, alEstado, dueno,
                                   umbralAnillos = UMBRAL_ANILLOS, umbralPosiciones = UMBRAL_POSICIONES }) {
  const capas = new Set();
  let renderer = null;
  let capaBitmap = null;
  let cliente = null;
  let mostrada = null;      // {bitmap, reserva, area, claveArea, lista: [{id, clave}]}
  let enVuelo = null;       // {numero, reserva, claveArea, claveLista, lista, obsoleto}
  let cerrado = false;
  let programado = false;
  const metricas = { decisiones: 0, rasters: 0, obsoletos: 0, liberadasParaCaber: 0, sinMemoria: 0,
                     demasiadoGrande: 0, esperas: 0, fallos: 0, ultimoFallo: null };

  const ctl = {
    get mostrada() { return mostrada; },
    get cliente() { return cliente; },
    get enVuelo() { return enVuelo; },
    metricas,
  };

  function asegurarCliente() {
    if (!cliente) {
      cliente = crearCliente({
        alFallar: (motivo) => { metricas.fallos += 1; metricas.ultimoFallo = motivo; liberarEnVuelo(); programar(); },
        alListo: () => programar(),
      });
    }
    return cliente;
  }

  function asegurarRenderer(capa) {
    if (renderer) return;
    renderer = capa._renderer;
    // Decide between the layer updates and the redraw (Leaflet 1.9.4
    // Canvas._updatePaths). Leaflet registered its own method as the
    // renderer's "update" listener in onAdd: replace that listener, so that
    // view changes and resizes reach this decision before any drawing.
    renderer.off("update", renderer._updatePaths, renderer);
    renderer._updatePaths = function updatePathsE5() {
      if (this._postponeUpdatePaths) return;
      this._redrawBounds = null;
      for (const id in this._layers) this._layers[id]._update();
      decidir();
      this._redraw();
    };
    renderer.on("update", renderer._updatePaths, renderer);
    capaBitmap = new CapaBitmap(ctl, { renderer });
    capaBitmap.addTo(map);
    capaBitmap.bringToBack();
  }

  const quitarOyente = presupuesto.alLiberar(() => programar());

  function programar() {
    if (programado || cerrado) return;
    programado = true;
    queueMicrotask(() => { programado = false; if (!cerrado && decidir()) redibujar(); });
  }

  function redibujar() {
    if (capaBitmap?._map) capaBitmap.redraw();
  }

  function soltarMostrada() {
    if (!mostrada) return;
    mostrada.bitmap.close();
    presupuesto.liberar(mostrada.reserva);
    mostrada = null;
  }

  function liberarEnVuelo() {
    if (!enVuelo) return;
    cliente?.soltar(enVuelo.lista.map((x) => x.id));
    presupuesto.liberar(enVuelo.reserva);
    enVuelo = null;
  }

  function areaActual() {
    const b = renderer._bounds;
    const c = renderer._container;
    const css = [b.max.x - b.min.x, b.max.y - b.min.y];
    const o = map.getPixelOrigin();
    const zoom = map.getZoom();
    return { bmin: [b.min.x, b.min.y], css, ancho: c.width, alto: c.height, m: c.width / css[0],
             origen: [o.x, o.y], zoom, escala: map.options.crs.scale(zoom) };
  }
  const claveDeArea = (a) => `${a.zoom}|${a.origen}|${a.bmin}|${a.ancho}x${a.alto}`;

  /** Visible outline layers in the renderer's draw order. */
  function enOrden() {
    const lista = [];
    for (let n = renderer?._drawFirst; n; n = n.next) {
      const c = n.layer;
      if (capas.has(c) && c._map && c._nVisibles > 0) lista.push(c);
    }
    return lista;
  }

  function poner(capa, modo, estado) {
    let cambio = false;
    if (capa._modo !== modo) { capa._modo = modo; cambio = true; }
    if (capa._estadoE5 !== estado) { capa._estadoE5 = estado; alEstado(capa, estado); cambio = true; }
    return cambio;
  }

  /** Direct drawing for a running-light prefix, `estado` for the rest. */
  function directosLigeros(lista, estado) {
    let anillos = 0; let posiciones = 0; let cambio = false;
    for (const c of lista) {
      anillos += c._carga.anillos; posiciones += c._carga.posiciones;
      const ligero = anillos <= umbralAnillos && posiciones <= umbralPosiciones;
      cambio = poner(c, ligero ? "directo" : "nada", ligero ? "listo" : estado) || cambio;
    }
    return cambio;
  }

  /** Decide modes and requests; returns whether anything visible changed. */
  function decidir() {
    if (cerrado || !renderer) return false;
    metricas.decisiones += 1;
    let cambio = false;
    // Layers not in view: nothing to draw, nothing claimed missing.
    for (const c of capas) if (!(c._map && c._nVisibles > 0)) cambio = poner(c, "nada", "listo") || cambio;
    const lista = enOrden();
    let anillos = 0; let posiciones = 0;
    for (const c of lista) { anillos += c._carga.anillos; posiciones += c._carga.posiciones; }

    if (anillos <= umbralAnillos && posiciones <= umbralPosiciones) {
      if (mostrada) { soltarMostrada(); cambio = true; }
      if (enVuelo) enVuelo.obsoleto = true;
      for (const c of lista) cambio = poner(c, "directo", "listo") || cambio;
      return cambio;
    }
    const cl = asegurarCliente();
    if (cl.estado === "fallido") {
      if (mostrada) { soltarMostrada(); cambio = true; }
      return directosLigeros(lista, "sin_trabajador") || cambio;
    }
    const area = areaActual();
    const claveArea = claveDeArea(area);
    const deseada = lista.map((c) => ({ id: c._id, capa: c, estilo: estiloDe(c.options) }));
    for (const d of deseada) d.clave = `${d.id}|${JSON.stringify(d.estilo)}`;

    // An image this size can never fit the budget: say so; post no copies.
    const bytes = area.ancho * area.alto * 4;
    if (!presupuesto.cabe(bytes)) {
      if (mostrada) soltarMostrada();
      if (enVuelo) enVuelo.obsoleto = true;
      metricas.demasiadoGrande += 1;
      return directosLigeros(lista, "demasiado_grande") || true;
    }

    // Worker copies (reserved before posting), each pinned as soon as it is
    // admitted so that admitting a later outline never evicts an earlier one
    // of the same image. An outline refused here is "sin_memoria" and is left
    // out of the image; the pins are dropped again unless a request is posted.
    const incluidas = [];
    const sinMemoria = new Set();
    let esperar = false;
    for (const d of deseada) {
      const r = cl.asegurar(d.id, d.capa._prep);
      if (r === "listo") { cl.fijar([d.id]); incluidas.push(d); }
      else if (r === "esperar") { esperar = true; break; }
      else sinMemoria.add(d.capa);
    }
    let fijadas = incluidas.map((d) => d.id);
    const soltarFijadas = () => { cl.soltar(fijadas); fijadas = []; };
    const claveLista = incluidas.map((d) => d.clave).join(";");

    // The image shown is usable when it is for this exact area and holds no
    // outline that has left the view; a style change (selection) keeps it
    // until its replacement arrives.
    const ids = new Set(deseada.map((d) => d.id));
    const vale = mostrada && mostrada.claveArea === claveArea && mostrada.lista.every((x) => ids.has(x.id));
    if (mostrada && !vale) { soltarMostrada(); cambio = true; }
    const enImagen = new Set(vale ? mostrada.lista.map((x) => x.id) : []);
    const completa = vale && !esperar && mostrada.claveLista === claveLista;

    if (vale) {
      for (const d of deseada) {
        const estado = sinMemoria.has(d.capa) ? "sin_memoria" : "dibujando";
        cambio = (enImagen.has(d.id) ? poner(d.capa, "bitmap", "listo") : poner(d.capa, "nada", estado)) || cambio;
      }
    } else {
      cambio = directosLigeros(lista, "dibujando") || cambio;
      for (const c of sinMemoria) if (c._modo === "nada") cambio = poner(c, "nada", "sin_memoria") || cambio;
    }
    if (sinMemoria.size) metricas.sinMemoria += 1;
    if (completa) {
      soltarFijadas();
      if (enVuelo) enVuelo.obsoleto = true;
      return cambio;
    }
    if (enVuelo) {
      soltarFijadas();
      if (enVuelo.claveArea !== claveArea || enVuelo.claveLista !== claveLista) enVuelo.obsoleto = true;
      return cambio;                          // one in flight per map; decide again when it returns
    }
    if (cl.estado !== "listo" || esperar || !incluidas.length) {
      soltarFijadas();                        // worker starting / releases pending / nothing admitted
      if (esperar) metricas.esperas += 1;
      return cambio;
    }
    let reserva = presupuesto.reservar("raster", bytes, dueno);
    if (!reserva && mostrada) {               // no room for both: give up the image shown first
      metricas.liberadasParaCaber += 1;
      soltarMostrada();
      cambio = directosLigeros(lista, "dibujando") || true;
      reserva = presupuesto.reservar("raster", bytes, dueno);
    }
    if (!reserva) {
      soltarFijadas();
      if (presupuesto.pendienteDeLiberar > 0) { metricas.esperas += 1; return cambio; }
      metricas.sinMemoria += 1;
      return directosLigeros(lista, "sin_memoria") || cambio;
    }
    const pedidoLista = incluidas.map((d) => ({ id: d.id, clave: d.clave }));   // pins held until the reply
    const vuelo = { numero: null, reserva, area, claveArea, claveLista, lista: pedidoLista, obsoleto: false };
    enVuelo = vuelo;
    metricas.rasters += 1;
    vuelo.numero = cl.raster({ ancho: area.ancho, alto: area.alto, m: area.m, bmin: area.bmin, origen: area.origen,
                               escala: area.escala, capas: incluidas.map((d) => ({ id: d.id, estilo: d.estilo })) },
                             (respuesta) => recibir(vuelo, respuesta));
    return cambio;
  }

  function recibir(vuelo, respuesta) {
    if (enVuelo !== vuelo) { respuesta.bitmap?.close(); return; }
    cliente?.soltar(vuelo.lista.map((x) => x.id));
    enVuelo = null;
    if (respuesta.fallo || respuesta.cancelado || vuelo.obsoleto || cerrado || !respuesta.bitmap) {
      if (vuelo.obsoleto) metricas.obsoletos += 1;
      respuesta.bitmap?.close();
      presupuesto.liberar(vuelo.reserva);
      programar();
      return;
    }
    // Replace the image: both were reserved, the old one is released now.
    soltarMostrada();
    const faltan = new Set(respuesta.faltan ?? []);
    mostrada = { bitmap: respuesta.bitmap, reserva: vuelo.reserva, area: vuelo.area, claveArea: vuelo.claveArea,
                 claveLista: faltan.size ? "" : vuelo.claveLista, lista: vuelo.lista.filter((x) => !faltan.has(x.id)) };
    programar();
    redibujar();
  }

  Object.assign(ctl, {
    agregar(capa) {
      asegurarRenderer(capa);
      capas.add(capa);
      capa._modo = "nada";
      programar();
    },
    quitar(capa) {
      capas.delete(capa);
      programar();
    },
    alFondo() { capaBitmap?.bringToBack(); },
    cambioDeEstilo() { programar(); },
    bitmapVigente() {
      return Boolean(mostrada && renderer && mostrada.claveArea === claveDeArea(areaActual()));
    },
    /** Next render(): a failed worker is replaced once. */
    reintentar() {
      if (cliente?.estado === "fallido") { cliente.cerrar(); cliente = null; }
    },
    /** Reset (render([])): images and worker copies go. Resolves when the worker acknowledges. */
    vaciar() {
      soltarMostrada();
      if (enVuelo) enVuelo.obsoleto = true;
      redibujar();
      return cliente?.olvidarTodo() ?? Promise.resolve(true);
    },
    cerrar() {
      cerrado = true;
      quitarOyente();
      soltarMostrada();
      if (enVuelo) { cliente?.descartar(enVuelo.numero); liberarEnVuelo(); }
      cliente?.cerrar();
    },
    /** Raster bytes actually held: displayed bitmap (width x height x 4) and in flight (reserved). */
    bytesRaster() {
      return { mostrada: mostrada ? mostrada.bitmap.width * mostrada.bitmap.height * 4 : 0,
               reservadaMostrada: mostrada?.reserva.bytes ?? 0, enVuelo: enVuelo?.reserva.bytes ?? 0 };
    },
    estado: () => ({ modos: [...capas].map((c) => [c._id, c._modo, c._estadoE5]), cliente: cliente?.estado ?? null,
                     motivo: cliente?.motivo ?? null }),
  });
  return ctl;
}

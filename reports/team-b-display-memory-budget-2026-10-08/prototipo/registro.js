/* PROTOTYPE (memory-budget investigation; not application code).
 *
 * The prepared bodies of ONE map, each counted once in the shared budget
 * ("preparado") however many owners it has:
 *   - the cache (enCache), which keeps a body after its layer leaves so a
 *     revisit need not prepare it again;
 *   - layers on the map that use it (fijos, a pin count).
 * Bytes are released only when neither owns it. Under pressure the budget
 * calls this map's reliever, which drops unpinned cached bodies, least
 * recently used first; a pinned body is never dropped while a layer uses
 * it (an active reference keeps its memory, so it stays counted).
 */

function claveCaja(b) { return b.join(","); }

export function crearRegistro(presupuesto, dueno) {
  const entradas = new Map();              // id -> {caja, preparado, reserva, enCache, fijos}; order = LRU
  const metricas = { expulsados: 0 };

  function soltarSiHuerfana(id, e) {
    if (e.enCache || e.fijos > 0) return;
    entradas.delete(id);
    presupuesto.liberar(e.reserva);
  }

  const quitarAliviador = presupuesto.registrarAliviador((faltan) => {
    let liberado = 0;
    for (const [id, e] of entradas) {
      if (liberado >= faltan) break;
      if (e.fijos > 0 || !e.enCache) continue;
      e.enCache = false;
      metricas.expulsados += 1;
      liberado += e.reserva.bytes;
      soltarSiHuerfana(id, e);
    }
  });

  return {
    /** Reserve for a preparation about to allocate. Reservation, "esperar" or null. */
    reservar(bytes) {
      return presupuesto.reservar("preparado", bytes, dueno);
    },
    /** A finished preparation hands its reservation over (cached, unpinned). */
    guardar(descriptor, preparado, reserva) {
      const anterior = entradas.get(descriptor.id);
      if (anterior) {                       // same immutable ID prepared twice: keep one
        presupuesto.liberar(reserva);
        return anterior.preparado;
      }
      entradas.set(descriptor.id, { caja: claveCaja(descriptor.bbox), preparado, reserva, enCache: true, fijos: 0 });
      return preparado;
    },
    obtener(descriptor) {
      const e = entradas.get(descriptor.id);
      if (!e || e.caja !== claveCaja(descriptor.bbox)) return null;
      entradas.delete(descriptor.id);
      entradas.set(descriptor.id, e);       // most recently used
      e.enCache = true;
      return e.preparado;
    },
    fijar(id) { const e = entradas.get(id); if (e) e.fijos += 1; },
    soltar(id) {
      const e = entradas.get(id);
      if (!e) return;
      e.fijos = Math.max(0, e.fijos - 1);
      soltarSiHuerfana(id, e);
    },
    /** Reset or teardown: drop the cache; pinned bodies go when their layers leave. */
    vaciar() {
      for (const [id, e] of entradas) { e.enCache = false; soltarSiHuerfana(id, e); }
    },
    cerrar() {
      quitarAliviador();
      for (const [id, e] of entradas) { e.enCache = false; e.fijos = 0; soltarSiHuerfana(id, e); }
    },
    /** Bytes actually held (typed-array byteLength), for validating the ledger. */
    bytesReales() {
      let b = 0;
      for (const { preparado: q } of entradas.values()) {
        b += q.x.byteLength + q.y.byteLength + q.inicioAnillo.byteLength + q.inicioParte.byteLength
          + q.cajasParte.byteLength;
      }
      return b;
    },
    bytesReservados() { let b = 0; for (const e of entradas.values()) b += e.reserva.bytes; return b; },
    get tamano() { return entradas.size; },
    fijados() { let n = 0; for (const e of entradas.values()) if (e.fijos) n += 1; return n; },
    metricas,
  };
}

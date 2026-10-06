/* Tests for the connected-Excel client logic. Run with: node --test tests/js/excel.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

const {
  avisoDeHash, cambioDatos, configuracionInicial, crearClavesDeActualizacion, crearOcupadas,
  estadoDeFuente, faltantesDeConfiguracion, mensajeDeEjecucion, nombreSugerido, respuestaIncierta,
  textoConteos, VIGENCIA_REINTENTO_MS,
} = await import("../../web/lib/excel.js");

const fuente = (extra = {}) => ({
  id: "f1", estado: "activa", en_curso: false,
  cuenta: { correo: "dueno@example.com", requiere_reconexion: false },
  version_activa: { numero: 3, filas: 104 },
  ultima_revision_en: "2026-10-06T12:00:00Z", ultima_exitosa_en: "2026-10-06T11:00:00Z",
  ultima_ejecucion: { estado: "ok", conteos: { agregados: 1, actualizados: 2, eliminados: 0 } },
  ...extra,
});

test("the callback notice is read from the hash and only known values count", () => {
  assert.deepEqual(avisoDeHash("#/bases?excel=conectado"), { hash: "#/bases", aviso: "conectado" });
  assert.deepEqual(avisoDeHash("#/bases?excel=cancelado"), { hash: "#/bases", aviso: "cancelado" });
  assert.deepEqual(avisoDeHash("#/bases?excel=<script>"), { hash: "#/bases", aviso: null });
  assert.deepEqual(avisoDeHash("#/bases?excel=toString"), { hash: "#/bases", aviso: null });
  assert.deepEqual(avisoDeHash("#/inventario"), { hash: "#/inventario", aviso: null });
});

test("a healthy source can refresh and shows its version and real times", () => {
  const e = estadoDeFuente(fuente());
  assert.equal(e.tono, "ok");
  assert.ok(e.acciones.has("actualizar") && e.acciones.has("abrir"));
  assert.match(e.detalles[0], /Versión 3 · 104 filas/);
  assert.match(e.detalles[1], /^Última revisión: /);
});

test("in progress, here or elsewhere, blocks refresh and keeps old data visible", () => {
  for (const f of [fuente({ en_curso: true }), fuente()]) {
    const e = estadoDeFuente(f, { ocupada: !f.en_curso });
    assert.equal(e.tono, "curso");
    assert.equal(e.acciones.has("actualizar"), false);
    assert.match(e.nota, /datos anteriores/);
  }
  assert.equal(estadoDeFuente(fuente({ en_curso: true })).acciones.has("comprobar"), true);
  assert.equal(estadoDeFuente(fuente(), { ocupada: true }).acciones.has("comprobar"), false);
  const quien = estadoDeFuente(fuente({
    en_curso: true, ultima_ejecucion: { estado: "en_curso", iniciada_por: { display_name: "Beto" } },
  }));
  assert.match(quien.nota, /por Beto/);
});

test("a lost credential asks to reconnect the owner's account, not to refresh", () => {
  const e = estadoDeFuente(fuente({ cuenta: { correo: "dueno@example.com", requiere_reconexion: true } }));
  assert.equal(e.tono, "error");
  assert.ok(e.acciones.has("reconectar_cuenta"));
  assert.equal(e.acciones.has("actualizar"), false);
  assert.match(e.nota, /dueno@example.com/);
});

test("failures keep the previous version and carry row problems", () => {
  const e = estadoDeFuente(fuente({
    ultima_ejecucion: {
      estado: "error", error: { codigo: "datos_invalidos", mensaje: "x" },
      problemas: [{ fila: 4, mensaje: "ID duplicado" }],
    },
  }));
  assert.equal(e.tono, "error");
  assert.match(e.nota, /versión 3/);
  assert.equal(e.problemas.length, 1);
  assert.ok(e.acciones.has("actualizar"));
  const revocada = estadoDeFuente(fuente({
    ultima_ejecucion: { estado: "error", error: { codigo: "reconectar", mensaje: "Vuelve a conectar." } },
  }));
  assert.ok(revocada.acciones.has("reconectar_cuenta"));
  const interrumpida = estadoDeFuente(fuente({ ultima_ejecucion: { estado: "interrumpida" } }));
  assert.equal(interrumpida.titulo, "La última actualización no terminó");
});

test("an empty candidate asks for confirmation; a disconnected source offers reactivation", () => {
  assert.equal(estadoDeFuente(fuente({ ultima_ejecucion: { estado: "revision" } })).tono, "aviso");
  const d = estadoDeFuente(fuente({ estado: "desconectada" }));
  assert.ok(d.acciones.has("reactivar"));
  assert.equal(d.acciones.has("actualizar"), false);
});

test("outcome messages use the run's actual counts and never invent progress", () => {
  assert.equal(textoConteos({ agregados: 1, actualizados: 2, eliminados: 0 }),
    "1 agregado, 2 actualizados, 0 eliminados");
  assert.match(mensajeDeEjecucion({ estado: "ok", conteos: { agregados: 0, actualizados: 1, eliminados: 1 } }),
    /0 agregados, 1 actualizado, 1 eliminado/);
  assert.match(mensajeDeEjecucion({ estado: "sin_cambios" }), /no tiene cambios/);
  assert.match(mensajeDeEjecucion({ estado: "error", error: { codigo: "no_encontrado", mensaje: "Ya no existe." } }),
    /Ya no existe/);
  assert.equal(cambioDatos({ estado: "ok" }), true);
  assert.equal(cambioDatos({ estado: "sin_cambios" }), false);
  assert.equal(cambioDatos({ estado: "revision" }), false);
});

test("a prompt retry after a lost answer reuses the key; anything else gets a new one", () => {
  let n = 0;
  let reloj = 1000;
  const claves = crearClavesDeActualizacion({ generar: () => `k${++n}`, ahora: () => reloj });
  const a = claves.preparar("f1", {});
  assert.match(a, /^excel-k\d+$/);
  reloj += 30_000;
  assert.equal(claves.preparar("f1", {}), a);                    // same body, soon after
  const confirmar = claves.preparar("f1", { confirmar_vacio: "abc" });
  assert.notEqual(confirmar, a);                                  // different body, new key
  claves.resolver("f1");
  assert.equal(claves.pendiente("f1"), null);
  const b = claves.preparar("f1", {});
  assert.notEqual(b, a);                                          // answered: a new refresh
  assert.notEqual(claves.preparar("f2", {}), b);                  // per source
  reloj += VIGENCIA_REINTENTO_MS + 1;
  assert.notEqual(claves.preparar("f1", {}), b);                  // too late to be a retry
  // A reload is a new instance: it never replays an old request.
  assert.equal(crearClavesDeActualizacion({ generar: () => "z" }).pendiente("f1"), null);
});

test("only network errors and 5xx leave the outcome uncertain", () => {
  assert.equal(respuestaIncierta({ red: true }), true);
  assert.equal(respuestaIncierta({ status: 502 }), true);
  assert.equal(respuestaIncierta({ status: 409 }), false);
  assert.equal(respuestaIncierta({ status: 422 }), false);
});

test("double clicks are absorbed per source", () => {
  const o = crearOcupadas();
  assert.equal(o.tomar("f1"), true);
  assert.equal(o.tomar("f1"), false);
  assert.equal(o.tomar("f2"), true);
  o.soltar("f1");
  assert.equal(o.tomar("f1"), true);
});

test("setup starts from the server's suggestions and lists what is missing", () => {
  const vista = {
    hoja: "Registro Análisis", id_sugerido: "ID", tiene_terreno: true, ya_conectada: null,
    columnas: [{ encabezado: "ID", puede_ser_id: true }, { encabezado: "Moneda", es_moneda: true }],
  };
  const cfg = configuracionInicial(vista);
  assert.deepEqual(cfg, { hoja: "Registro Análisis", columna_id: "ID", moneda: "columna", columna_moneda: "Moneda" });
  assert.deepEqual(faltantesDeConfiguracion(cfg, vista, "Terrenos"), []);
  assert.equal(faltantesDeConfiguracion({ ...cfg, columna_id: "" }, vista, " ").length, 2);
  assert.equal(faltantesDeConfiguracion(cfg, { ...vista, ya_conectada: "x" }, "T").length, 1);
  assert.equal(configuracionInicial({ columnas: [{ encabezado: "Clave", puede_ser_id: true }] }).columna_id, "Clave");
  assert.equal(nombreSugerido("Terrenos 2026.xlsx"), "Terrenos 2026");
});

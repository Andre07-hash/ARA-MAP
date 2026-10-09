/* Tests for the bounded geometry loader (web/lib/cargadorGeometrias.js).
 * Run with: node --test tests/js/cargadorGeometrias.test.mjs
 *
 * A fake private bridge serves the frozen 2B wire format (metadata POST, then
 * 512 KiB chunks with their X-Geometria-* headers) from in-memory fictional
 * bodies, and records how many requests are in flight at once.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";

const { crearCargadorGeometrias, ErrorGeometria, FRAGMENTO_BYTES, CUERPO_MAX_BYTES } =
  await import("../../web/lib/cargadorGeometrias.js");

const TERRENO = "11111111-1111-4111-8111-111111111111";
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");

/* A valid MultiPolygon text of about `objetivo` UTF-8 bytes, with a two-byte
 * "é" placed so that it straddles the first chunk boundary. */
function geojsonGrande(objetivo) {
  const cabeza = '{"type":"MultiPolygon","coordinates":[[[[-100.4,20.6],[-100.3,20.6],[-100.3,20.7],[-100.4,20.6]]]],"nota":"';
  const relleno = "a".repeat(FRAGMENTO_BYTES - 1 - Buffer.byteLength(cabeza));
  const resto = "b".repeat(Math.max(0, objetivo - FRAGMENTO_BYTES - 4));
  return `${cabeza}${relleno}é${resto}"}`;
}
const SIMPLE = '{"type":"MultiPolygon","coordinates":[[[[-100.4,20.6],[-100.3,20.6],[-100.3,20.7],[-100.4,20.6]]]]}';

function geometria(texto = SIMPLE, extra = {}) {
  const bytes = Buffer.from(texto, "utf8");
  const id = randomUUID();
  const version = randomUUID();
  const descriptor = { id, archivo_version_id: version, utilizable: true,
    bbox: [-100.4, 20.6, -100.3, 20.7], punto_interior: { type: "Point", coordinates: [-100.35, 20.65] } };
  const meta = {
    id, archivo_id: randomUUID(), archivo_version_id: version, terreno_id: TERRENO,
    intento_id: randomUUID(), bbox: [...descriptor.bbox], punto_interior: structuredClone(descriptor.punto_interior),
    partes: 1, huecos: 0, vertices: 4, area_aproximada_m2: 1.5, utilizable: true, activa: true,
    bytes: bytes.length, sha256: sha(bytes), fragmento_bytes: FRAGMENTO_BYTES,
    fragmentos: Math.ceil(bytes.length / FRAGMENTO_BYTES), creado_en: "2026-10-09T00:00:00+00:00", ...extra,
  };
  return { descriptor, meta, bytes };
}

/* The fake bridge. `alterar(tipo, contexto)` may rewrite any reply. */
function servidor(geos, { alterar, retener } = {}) {
  const porId = new Map(geos.map((g) => [g.meta.id, g]));
  const registro = { peticiones: [], simultaneas: 0, maxSimultaneas: 0 };
  async function peticionPrivada(ruta, { method = "GET", body, signal } = {}) {
    if (signal?.aborted) throw new DOMException("x", "AbortError");
    registro.peticiones.push(`${method} ${ruta}`);
    registro.simultaneas += 1;
    registro.maxSimultaneas = Math.max(registro.maxSimultaneas, registro.simultaneas);
    try {
      if (retener) await retener(ruta, signal);
      if (signal?.aborted) throw new DOMException("x", "AbortError");
      let respuesta;
      if (ruta === "/api/archivos/geometrias/metadatos") {
        const { ids } = JSON.parse(body);
        const sobre = { geometrias: {}, no_disponibles: [] };
        for (const id of ids) {
          if (porId.has(id)) sobre.geometrias[id] = structuredClone(porId.get(id).meta);
          else sobre.no_disponibles.push(id);
        }
        respuesta = { tipo: "meta", status: 200, cuerpo: Buffer.from(JSON.stringify(sobre)),
          headers: { "Content-Type": "application/json" } };
      } else {
        const m = ruta.match(/^\/api\/archivos\/geometrias\/([^/]+)\/contenido\?desde=(\d+)$/);
        const g = porId.get(m[1]);
        const desde = Number(m[2]);
        if (!g) {
          respuesta = { tipo: "fragmento", status: 404, cuerpo: Buffer.from('{"error":"x","detalle":{"code":"not_found"}}'), headers: {} };
        } else {
          const parte = g.bytes.subarray(desde, desde + FRAGMENTO_BYTES);
          const final = desde + parte.length === g.bytes.length;
          respuesta = { tipo: "fragmento", status: 200, desde, cuerpo: parte, headers: {
            "Content-Type": "application/octet-stream", "X-Geometria-Id": g.meta.id,
            "X-Geometria-Desde": String(desde), "X-Geometria-Longitud": String(parte.length),
            "X-Geometria-Bytes": String(g.bytes.length), "X-Geometria-Siguiente": final ? "fin" : String(desde + parte.length),
            "X-Geometria-Final": final ? "1" : "0", "X-Geometria-Sha256": sha(g.bytes) } };
        }
      }
      if (alterar) respuesta = alterar(respuesta) ?? respuesta;
      const cuerpo = respuesta.stream ?? respuesta.cuerpo;
      return { response: new Response(cuerpo, { status: respuesta.status, headers: respuesta.headers }), signal };
    } finally {
      registro.simultaneas -= 1;
    }
  }
  return { peticionPrivada, registro };
}

async function falla(promesa, codigo) {
  await assert.rejects(promesa, (e) => {
    assert.ok(e instanceof ErrorGeometria, `esperaba ErrorGeometria(${codigo}), no ${e?.name}: ${e?.message}`);
    assert.equal(e.codigo, codigo);
    return true;
  });
}
const abortada = (promesa) => assert.rejects(promesa, (e) => e?.name === "AbortError");

/* ------------------------------------------------------------- success */

test("a multichunk body with a codepoint split across chunks is reassembled and verified", async () => {
  const texto = geojsonGrande(FRAGMENTO_BYTES + 200_000);
  const g = geometria(texto);
  const { peticionPrivada, registro } = servidor([g]);
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  const cuerpo = await cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor });
  assert.equal(registro.peticiones.length, 3);                 // metadata + 2 chunks
  assert.equal(cuerpo.geojson.type, "MultiPolygon");
  assert.ok(cuerpo.geojson.nota.includes("é"));
  assert.deepEqual(cuerpo.bbox, g.meta.bbox);
  assert.deepEqual(cuerpo.punto_interior, g.meta.punto_interior);
  assert.equal(cuerpo.sha256, g.meta.sha256);
  assert.equal(cuerpo.bytes, Buffer.byteLength(texto));
  for (const k of ["partes", "huecos", "vertices", "area_aproximada_m2"]) assert.equal(cuerpo[k], g.meta[k]);
  assert.deepEqual(cargador.estado(), { enCurso: 0, enEspera: 0, listos: 1, destruido: false });
  // The same descriptor again is served from the one ready body, without network.
  assert.equal(await cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }), cuerpo);
  assert.equal(registro.peticiones.length, 3);
});

test("an exact multiple of the chunk size ends on a full final chunk", async () => {
  const base = '{"type":"MultiPolygon","coordinates":[[[[-100.4,20.6],[-100.3,20.6],[-100.3,20.7],[-100.4,20.6]]]],"x":"';
  const texto = base + "c".repeat(2 * FRAGMENTO_BYTES - Buffer.byteLength(base) - 2) + '"}';
  assert.equal(Buffer.byteLength(texto), 2 * FRAGMENTO_BYTES);
  const g = geometria(texto);
  const { peticionPrivada, registro } = servidor([g]);
  const cuerpo = await crearCargadorGeometrias({ peticionPrivada }).cargar({ terrenoId: TERRENO, geometria: g.descriptor });
  assert.equal(cuerpo.bytes, 2 * FRAGMENTO_BYTES);
  assert.equal(registro.peticiones.length, 3);
});

/* ---------------------------------------------- requests and metadata */

test("a malformed or inactive descriptor is refused before any request", async () => {
  const g = geometria();
  const { peticionPrivada, registro } = servidor([g]);
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  for (const malo of [null, { ...g.descriptor, utilizable: false }, { ...g.descriptor, id: "geo-1" },
    { ...g.descriptor, bbox: [1, 2, 0, 3] }, { ...g.descriptor, archivo_version_id: undefined }]) {
    await falla(cargador.cargar({ terrenoId: TERRENO, geometria: malo }), "descriptor_invalido");
  }
  await falla(cargador.cargar({ terrenoId: "no-uuid", geometria: g.descriptor }), "descriptor_invalido");
  assert.equal(registro.peticiones.length, 0);
});

test("metadata must describe exactly the requested active geometry", async () => {
  const casos = [
    ["terreno ajeno", { terreno_id: randomUUID() }, "metadatos_invalidos"],
    ["otra version", { archivo_version_id: randomUUID() }, "metadatos_invalidos"],
    ["otra caja", { bbox: [-100.5, 20.6, -100.3, 20.7] }, "metadatos_invalidos"],
    ["otro punto", { punto_interior: { type: "Point", coordinates: [-100.36, 20.65] } }, "metadatos_invalidos"],
    ["ya no activa", { activa: false }, "obsoleta"],
    ["no utilizable", { utilizable: false }, "obsoleta"],
    ["hash mal formado", { sha256: "ABC" }, "metadatos_invalidos"],
    ["otro tamano de fragmento", { fragmento_bytes: 1024 }, "metadatos_invalidos"],
    ["fragmentos inconsistentes", { fragmentos: 9 }, "metadatos_invalidos"],
    ["bytes cero", { bytes: 0 }, "metadatos_invalidos"],
    ["mas de 16 MiB", { bytes: CUERPO_MAX_BYTES + 1, fragmentos: Math.ceil((CUERPO_MAX_BYTES + 1) / FRAGMENTO_BYTES) }, "demasiado_grande"],
    ["conteo no entero", { vertices: 4.5 }, "metadatos_invalidos"],
  ];
  for (const [nombre, cambio, codigo] of casos) {
    const g = geometria();
    Object.assign(g.meta, cambio);
    const { peticionPrivada, registro } = servidor([g]);
    await falla(crearCargadorGeometrias({ peticionPrivada }).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), codigo);
    assert.equal(registro.peticiones.length, 1, `${nombre}: no chunk may be requested`);
  }
  // The id the server answers under must be the one asked for.
  const g = geometria();
  const { peticionPrivada } = servidor([g], { alterar: (r) => {
    if (r.tipo !== "meta") return r;
    const sobre = JSON.parse(r.cuerpo);
    sobre.geometrias[g.meta.id].id = randomUUID();
    return { ...r, cuerpo: Buffer.from(JSON.stringify(sobre)) };
  } });
  await falla(crearCargadorGeometrias({ peticionPrivada }).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "metadatos_invalidos");
});

test("missing, oversized or unreadable metadata is an explicit error", async () => {
  const g = geometria();
  const ausente = servidor([]);
  await falla(crearCargadorGeometrias(ausente).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "no_disponible");
  const grande = servidor([g], { alterar: (r) => (r.tipo === "meta"
    ? { ...r, cuerpo: Buffer.alloc(128 * 1024 + 1, 32), headers: {} } : r) });
  await falla(crearCargadorGeometrias(grande).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "demasiado_grande");
  const declarada = servidor([g], { alterar: (r) => (r.tipo === "meta"
    ? { ...r, headers: { ...r.headers, "Content-Length": String(200 * 1024) } } : r) });
  await falla(crearCargadorGeometrias(declarada).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "demasiado_grande");
  const roto = servidor([g], { alterar: (r) => (r.tipo === "meta" ? { ...r, cuerpo: Buffer.from("{no") } : r) });
  await falla(crearCargadorGeometrias(roto).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "metadatos_invalidos");
  const caido = servidor([g], { alterar: (r) => (r.tipo === "meta" ? { ...r, status: 503 } : r) });
  await falla(crearCargadorGeometrias(caido).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "servidor");
});

/* ------------------------------------------------------------- chunks */

test("every chunk header is checked against the sequence", async () => {
  const texto = geojsonGrande(FRAGMENTO_BYTES + 1000);
  const casos = {
    "otro id": (h) => { h["X-Geometria-Id"] = randomUUID(); },
    "desplazamiento": (h) => { h["X-Geometria-Desde"] = "1"; },
    "longitud": (h) => { h["X-Geometria-Longitud"] = "10"; },
    "total": (h) => { h["X-Geometria-Bytes"] = "99"; },
    "hash": (h) => { h["X-Geometria-Sha256"] = "0".repeat(64); },
    "marca final": (h) => { h["X-Geometria-Final"] = h["X-Geometria-Final"] === "1" ? "0" : "1"; },
    "siguiente": (h) => { h["X-Geometria-Siguiente"] = "fin"; },
    "tipo": (h) => { h["Content-Type"] = "text/html"; },
  };
  for (const [nombre, cambiar] of Object.entries(casos)) {
    for (const fragmento of [0, FRAGMENTO_BYTES]) {
      const g = geometria(texto);
      const { peticionPrivada } = servidor([g], { alterar: (r) => {
        if (r.tipo !== "fragmento" || r.desde !== fragmento) return r;
        const headers = { ...r.headers };
        cambiar(headers);
        return { ...r, headers };
      } });
      if (nombre === "siguiente" && fragmento === FRAGMENTO_BYTES) continue;   // "fin" is right there
      await falla(crearCargadorGeometrias({ peticionPrivada }).cargar({ terrenoId: TERRENO, geometria: g.descriptor }),
        "fragmento_invalido");
    }
  }
});

test("repeated, out-of-order, truncated or oversized chunks are refused", async () => {
  const texto = geojsonGrande(2 * FRAGMENTO_BYTES + 5000);
  const g = geometria(texto);
  const respuestaDe = (desde) => {
    const parte = g.bytes.subarray(desde, desde + FRAGMENTO_BYTES);
    const final = desde + parte.length === g.bytes.length;
    return { "X-Geometria-Desde": String(desde), "X-Geometria-Longitud": String(parte.length),
      "X-Geometria-Final": final ? "1" : "0", "X-Geometria-Siguiente": final ? "fin" : String(desde + parte.length), parte };
  };
  const reemplazar = (desdeServido) => (r) => {
    if (r.tipo !== "fragmento" || r.desde !== FRAGMENTO_BYTES) return r;
    const { parte, ...h } = respuestaDe(desdeServido);
    return { ...r, cuerpo: parte, headers: { ...r.headers, ...h } };
  };
  for (const [nombre, alterar] of [
    ["repetido", reemplazar(0)],
    ["fuera de orden", reemplazar(2 * FRAGMENTO_BYTES)],
    ["truncado", (r) => (r.tipo === "fragmento" && r.desde === 0 ? { ...r, cuerpo: r.cuerpo.subarray(0, 1000) } : r)],
    ["excedido", (r) => (r.tipo === "fragmento" && r.desde === 0 ? { ...r, cuerpo: Buffer.concat([r.cuerpo, Buffer.from("x")]) } : r)],
    ["longitud declarada", (r) => (r.tipo === "fragmento" && r.desde === 0
      ? { ...r, headers: { ...r.headers, "Content-Length": String(FRAGMENTO_BYTES + 1) } } : r)],
  ]) {
    const { peticionPrivada } = servidor([g], { alterar });
    await falla(crearCargadorGeometrias({ peticionPrivada }).cargar({ terrenoId: TERRENO, geometria: g.descriptor }),
      "fragmento_invalido");
  }
});

test("a body whose bytes do not match the recorded hash is never parsed", async () => {
  const g = geometria(geojsonGrande(FRAGMENTO_BYTES + 100));
  const { peticionPrivada } = servidor([g], { alterar: (r) => {
    if (r.tipo !== "fragmento" || r.desde !== FRAGMENTO_BYTES) return r;
    const cuerpo = Buffer.from(r.cuerpo);
    cuerpo[10] ^= 1;                              // same length, same headers, different bytes
    return { ...r, cuerpo };
  } });
  await falla(crearCargadorGeometrias({ peticionPrivada }).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "hash_no_coincide");
});

test("invalid UTF-8, invalid JSON or a non-MultiPolygon with a matching hash are refused", async () => {
  for (const bytes of [Buffer.from([0x7b, 0xc3, 0x28, 0x7d]), Buffer.from("{no json"), Buffer.from('{"type":"Point","coordinates":[0,0]}'),
    Buffer.from('{"type":"MultiPolygon","coordinates":[]}')]) {
    const g = geometria();
    g.bytes = bytes;
    Object.assign(g.meta, { bytes: bytes.length, sha256: sha(bytes), fragmentos: 1 });
    const { peticionPrivada } = servidor([g]);
    await falla(crearCargadorGeometrias({ peticionPrivada }).cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "contenido_invalido");
  }
});

test("revocation or transfer between chunks stops the load and installs nothing", async () => {
  const g = geometria(geojsonGrande(FRAGMENTO_BYTES + 100));
  let revocado = false;
  const { peticionPrivada } = servidor([g], { alterar: (r) => {
    if (r.tipo === "fragmento" && r.desde === 0) { revocado = true; return r; }
    if (r.tipo === "fragmento" && revocado) {
      return { ...r, status: 404, cuerpo: Buffer.from('{"error":"El archivo no existe.","detalle":{"code":"not_found"}}'), headers: {} };
    }
    return r;
  } });
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  await falla(cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "no_disponible");
  assert.equal(cargador.estado().listos, 0);
});

test("a network failure is explicit and a later retry succeeds", async () => {
  const g = geometria(geojsonGrande(FRAGMENTO_BYTES + 100));
  let fallar = true;
  const base = servidor([g]);
  const peticionPrivada = async (ruta, opciones) => {
    if (fallar && ruta.includes("desde=524288")) { fallar = false; throw new TypeError("Failed to fetch"); }
    return base.peticionPrivada(ruta, opciones);
  };
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  await falla(cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "red");
  const cuerpo = await cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor });
  assert.equal(cuerpo.sha256, g.meta.sha256);
  // A body read that fails mid-stream is explicit too.
  const roto = servidor([g], { alterar: (r) => (r.tipo === "fragmento" && r.desde === 0 ? { ...r, stream: new ReadableStream({
    start(c) { c.enqueue(new Uint8Array(r.cuerpo.subarray(0, 10))); c.error(new TypeError("network")); },
  }) } : r) });
  await assert.rejects(crearCargadorGeometrias(roto).cargar({ terrenoId: TERRENO, geometria: g.descriptor }));
});

/* --------------------------------------------- residency and lifetime */

/* Holds every request until released, to make interleavings deterministic. */
function compuerta() {
  const esperando = [];
  return {
    retener: (ruta, signal) => new Promise((resolve, reject) => {
      const item = { ruta, resolve };
      esperando.push(item);
      signal?.addEventListener("abort", () => {
        esperando.splice(esperando.indexOf(item), 1);
        reject(new DOMException("x", "AbortError"));
      }, { once: true });
    }),
    soltar() { const item = esperando.shift(); item?.resolve(); return item?.ruta; },
    get pendientes() { return esperando.length; },
  };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

test("rapid selections keep one load in flight and one replaceable request waiting", async () => {
  const gs = [geometria(), geometria(), geometria(), geometria()];
  const puerta = compuerta();
  const { peticionPrivada, registro } = servidor(gs, { retener: puerta.retener });
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  const a = cargador.cargar({ terrenoId: TERRENO, geometria: gs[0].descriptor });
  await tick();
  assert.deepEqual(cargador.estado(), { enCurso: 1, enEspera: 0, listos: 0, destruido: false });
  const b = cargador.cargar({ terrenoId: TERRENO, geometria: gs[1].descriptor });
  const c = cargador.cargar({ terrenoId: TERRENO, geometria: gs[2].descriptor });
  const d = cargador.cargar({ terrenoId: TERRENO, geometria: gs[3].descriptor });
  await abortada(a);                    // obsolete, cancelled
  await abortada(b);                    // replaced while waiting
  await abortada(c);
  await tick();
  assert.ok(cargador.estado().enCurso + cargador.estado().enEspera <= 2);
  while (puerta.pendientes || cargador.estado().enCurso) { puerta.soltar(); await tick(); }
  const cuerpo = await d;
  assert.equal(cuerpo.id, gs[3].meta.id);
  assert.equal(registro.maxSimultaneas, 1);
  assert.deepEqual(cargador.estado(), { enCurso: 0, enEspera: 0, listos: 1, destruido: false });
  // Only the last selection's chunk was ever requested.
  assert.deepEqual(registro.peticiones.filter((p) => p.includes("contenido")),
    [`GET /api/archivos/geometrias/${gs[3].meta.id}/contenido?desde=0`]);
});

test("a new selection releases the previous ready body", async () => {
  const [g1, g2] = [geometria(), geometria()];
  const { peticionPrivada, registro } = servidor([g1, g2]);
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  await cargador.cargar({ terrenoId: TERRENO, geometria: g1.descriptor });
  await cargador.cargar({ terrenoId: TERRENO, geometria: g2.descriptor });
  assert.equal(cargador.estado().listos, 1);
  const antes = registro.peticiones.length;
  await cargador.cargar({ terrenoId: TERRENO, geometria: g1.descriptor });   // not cached: reloaded
  assert.equal(registro.peticiones.length, antes + 2);
});

test("reset after the network finished but before the digest installs nothing", async () => {
  const g = geometria(geojsonGrande(FRAGMENTO_BYTES + 100));
  let cargador;
  const { peticionPrivada } = servidor([g], { alterar: (r) => {
    if (r.tipo !== "fragmento" || r.desde !== FRAGMENTO_BYTES) return r;
    const bytes = new Uint8Array(r.cuerpo);
    return { ...r, stream: new ReadableStream({
      pull(c) { c.enqueue(bytes); c.close(); queueMicrotask(() => cargador.reset()); },
    }) };
  } });
  cargador = crearCargadorGeometrias({ peticionPrivada });
  await abortada(cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }));
  assert.deepEqual(cargador.estado(), { enCurso: 0, enEspera: 0, listos: 0, destruido: false });
});

test("reset and destroy cancel work, drop the ready body and refuse later loads", async () => {
  const [g1, g2] = [geometria(), geometria()];
  const puerta = compuerta();
  const { peticionPrivada } = servidor([g1, g2], { retener: puerta.retener });
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  const uno = cargador.cargar({ terrenoId: TERRENO, geometria: g1.descriptor });
  const dos = cargador.cargar({ terrenoId: TERRENO, geometria: g2.descriptor });
  cargador.reset();
  await abortada(uno);
  await abortada(dos);
  assert.deepEqual(cargador.estado(), { enCurso: 0, enEspera: 0, listos: 0, destruido: false });
  const tres = cargador.cargar({ terrenoId: TERRENO, geometria: g1.descriptor });
  await tick();
  cargador.destroy();
  await abortada(tres);
  await falla(cargador.cargar({ terrenoId: TERRENO, geometria: g1.descriptor }), "destruido");
  assert.equal(cargador.estado().destruido, true);
  assert.equal(puerta.pendientes, 0);
});

test("the caller's own signal cancels only its request", async () => {
  const g = geometria();
  const puerta = compuerta();
  const { peticionPrivada } = servidor([g], { retener: puerta.retener });
  const cargador = crearCargadorGeometrias({ peticionPrivada });
  const control = new AbortController();
  const p = cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }, { signal: control.signal });
  await tick();
  control.abort();
  await abortada(p);
  await abortada(cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }, { signal: AbortSignal.abort() }));
  const q = cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor });
  while (puerta.pendientes || cargador.estado().enCurso) { puerta.soltar(); await tick(); }
  assert.equal((await q).id, g.meta.id);
});

test("a session-ended bridge (AbortError) is a cancellation, not an error", async () => {
  const g = geometria();
  const cargador = crearCargadorGeometrias({ peticionPrivada: async () => { throw new DOMException("x", "AbortError"); } });
  await abortada(cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }));
  // A bridge whose captured private signal was aborted after it returned is refused too.
  const muerto = new AbortController();
  muerto.abort();
  const tardio = crearCargadorGeometrias({ peticionPrivada: async () => ({
    response: new Response("{}", { status: 200 }), signal: muerto.signal }) });
  await abortada(tardio.cargar({ terrenoId: TERRENO, geometria: g.descriptor }));
});

test("a 401 reported by the bridge is a session error, never a drawn body", async () => {
  const g = geometria();
  const cargador = crearCargadorGeometrias({ peticionPrivada: async () => { throw Object.assign(new Error("x"), { status: 401 }); } });
  await falla(cargador.cargar({ terrenoId: TERRENO, geometria: g.descriptor }), "sesion");
  assert.equal(cargador.estado().listos, 0);
});

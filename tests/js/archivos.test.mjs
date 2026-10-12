/* Tests for the attachment client (web/lib/archivos.js) and the upload state
 * machine (web/components/archivos/subida.js).
 * Run with: node --test tests/js/archivos.test.mjs
 *
 * A fake private bridge implements the accepted lifecycle's idempotency and
 * replay rules over fictional files, and can act on a request and then lose
 * its reply, so every "uncertain" path is deterministic.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";

const A = await import("../../web/lib/archivos.js");
const { crearSubida, FASE } = await import("../../web/components/archivos/subida.js");

const TERRENO = "22222222-2222-4222-8222-222222222222";
const sha = (b) => createHash("sha256").update(b).digest("hex");
const PDF = Buffer.from("%PDF-1.4\n% ficticio\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n");
const archivoDe = (bytes, nombre = "ficticio.pdf") => new File([bytes], nombre);
const tick = () => new Promise((r) => setTimeout(r, 0));

const json = (status, cuerpo, headers = {}) => new Response(JSON.stringify(cuerpo),
  { status, headers: { "Content-Type": "application/json", ...headers } });
const error = (status, code, extra = {}) => json(status, { error: `Fallo ficticio ${code}`, detalle: { code, ...extra } });

/* An in-memory lifecycle with the server's replay rules. */
function lifecycle({ kmzResultado = "listo" } = {}) {
  const porClave = new Map();         // idempotency key -> {hash, dto}
  const versiones = new Map();
  const registro = [];
  const fallos = [];                  // [{coincide(metodo, ruta), modo: "perder" | "antes" | Response}]
  let resultado = kmzResultado;

  function actuar(metodo, ruta, headers, body, consulta = "") {
    let m;
    if (metodo === "POST" && (m = ruta.match(/^\/api\/inventario\/terrenos\/([^/]+)\/archivos$/))) {
      const clave = headers["Idempotency-Key"];
      const hash = sha(Buffer.from(body));
      const previo = porClave.get(clave);
      if (previo) return previo.hash === hash ? json(200, { ...previo.dto, replay: true }) : error(409, "idempotencia_conflictiva");
      const datos = JSON.parse(new TextDecoder().decode(body));
      const dto = { archivo_id: randomUUID(), version_id: randomUUID(), tipo: datos.tipo, numero: 1, estado: "subiendo",
        revision_base: 1, nombre_original: datos.nombre_original, tamano_declarado: datos.tamano_declarado,
        sha256_declarado: datos.sha256_declarado, subida_vence_en: "2026-10-09T12:15:00+00:00",
        completar_antes_de: "2026-10-09T13:00:00+00:00",
        transferencia: { parte_bytes: A.PARTE_BYTES, partes: Math.ceil(datos.tamano_declarado / A.PARTE_BYTES) } };
      porClave.set(clave, { hash, dto });
      versiones.set(dto.version_id, { ...dto, staged: null, final: null, puts: 0 });
      return json(200, dto);
    }
    if ((m = ruta.match(/^\/api\/archivos\/versiones\/([^/]+)\/(contenido|completar|cancelar)$/))) {
      const v = versiones.get(m[1]);
      if (!v) return error(404, "not_found");
      if (m[2] === "contenido") {
        if (v.final) return error(409, "subida_no_pendiente");
        const parte = Number(new URLSearchParams(consulta).get("parte"));
        const partes = Math.ceil(v.tamano_declarado / A.PARTE_BYTES);
        const esperada = Math.min(A.PARTE_BYTES, v.tamano_declarado - parte * A.PARTE_BYTES);
        if (!(parte >= 0 && parte < partes) || body.byteLength !== esperada) return error(400, "parte_invalida");
        (v.staged ??= new Map()).set(parte, body); v.puts += 1;
        return json(200, { version_id: v.version_id, parte, partes, bytes_recibidos: body.byteLength, estado: "subiendo" });
      }
      if (m[2] === "cancelar") {
        if (v.final) return error(409, "subida_no_pendiente");
        v.final = { version: { id: v.version_id, estado: "cancelado" } };
        return json(200, { version_id: v.version_id, estado: "cancelado", limpieza_pendiente: false });
      }
      if (v.final) return json(200, { ...v.final, replay: true });
      const partes = Math.ceil(v.tamano_declarado / A.PARTE_BYTES);
      const faltan = [...Array(partes).keys()].filter((i) => !v.staged?.has(i));
      if (faltan.length) return error(409, "contenido_temporal_ausente", { partes_faltantes: faltan, reintentar: !v.vencida });
      const ok = sha(Buffer.concat(faltan.length ? [] : [...Array(partes).keys()].map((i) => Buffer.from(v.staged.get(i))))) === v.sha256_declarado;
      const version = { id: v.version_id, archivo_id: v.archivo_id, numero: 1,
        estado: ok ? "disponible" : "fallido", error: ok ? null : { codigo: "sha256_no_coincide", mensaje: "No coincide." } };
      const intento = v.tipo === "kmz" && ok ? { id: randomUUID(), resultado } : null;
      v.final = { version, intento, aplicada: ok && (v.tipo === "pdf" || resultado === "listo"),
        motivo_no_aplicada: null, archivo: { id: v.archivo_id, revision: 2 }, limpieza_pendiente: false };
      return json(200, { ...v.final, replay: false });
    }
    return error(404, "not_found");
  }

  async function peticionPrivada(ruta, { method = "GET", headers = {}, body, signal } = {}) {
    if (signal?.aborted) throw new DOMException("x", "AbortError");
    let bytes = body;
    if (body instanceof Blob) bytes = new Uint8Array(await body.arrayBuffer());
    else if (typeof body === "string") bytes = new TextEncoder().encode(body);
    registro.push(`${method} ${ruta.split("?")[0]}`);
    const i = fallos.findIndex((f) => f.coincide(method, ruta));
    const fallo = i >= 0 ? fallos.splice(i, 1)[0] : null;
    if (fallo?.modo === "antes") throw new TypeError("Failed to fetch");     // never reached the server
    if (fallo?.modo instanceof Response) return { response: fallo.modo, signal };
    const response = actuar(method, ruta.split("?")[0], headers, bytes ?? new Uint8Array(), ruta.split("?")[1] ?? "");
    if (fallo?.modo === "perder") throw new TypeError("network dropped");  // acted, reply lost
    return { response, signal };
  }
  return { peticionPrivada, registro, fallos, versiones, porClave, set resultado(v) { resultado = v; } };
}

const falla = (metodo, patron, modo) => ({ coincide: (m, r) => m === metodo && patron.test(r), modo });

/* ------------------------------------------------------------- client */

test("client: bounded reads refuse declared and actual excess", async () => {
  await assert.rejects(A.leerBytes(new Response("x".repeat(10), { headers: { "Content-Length": "10" } }), 5),
    (e) => e.codigo === "respuesta_excesiva");
  const stream = new ReadableStream({ start(c) { c.enqueue(new Uint8Array(4)); c.enqueue(new Uint8Array(4)); c.close(); } });
  await assert.rejects(A.leerBytes(new Response(stream), 5), (e) => e.codigo === "respuesta_excesiva");
  assert.equal((await A.leerBytes(new Response("abc"), 5)).byteLength, 3);
});

test("client: the error envelope becomes a readable ErrorArchivos; a lost reply is uncertain", async () => {
  const cliente = A.crearClienteArchivos({ peticionPrivada: async () => ({
    response: error(409, "procesamiento_en_curso", { reintentar: true, reintentar_despues_de: 7 }) }) });
  await assert.rejects(cliente.completar(randomUUID()), (e) => {
    assert.equal(e.codigo, "procesamiento_en_curso");
    assert.equal(e.status, 409);
    assert.equal(e.reintentarDespuesDe, 7);
    assert.equal(e.incierto, false);
    return true;
  });
  const sinRespuesta = A.crearClienteArchivos({ peticionPrivada: async () => { throw new TypeError("x"); } });
  await assert.rejects(sinRespuesta.completar(randomUUID()), (e) => e.codigo === "red" && e.incierto === true);
  const ilegible = A.crearClienteArchivos({ peticionPrivada: async () => ({ response: new Response("{no", { status: 200 }) }) });
  await assert.rejects(ilegible.listar(TERRENO), (e) => e.codigo === "respuesta_ilegible" && e.incierto);
  const html = A.crearClienteArchivos({ peticionPrivada: async () => ({ response: new Response("<h1>x</h1>", { status: 502 }) }) });
  await assert.rejects(html.listar(TERRENO), (e) => e.codigo === "http_502" && e.message === "Error 502");
});

test("client: cancellation stays an AbortError and malformed ids never reach the bridge", async () => {
  const llamadas = [];
  const cliente = A.crearClienteArchivos({ peticionPrivada: async (ruta) => { llamadas.push(ruta); throw new DOMException("x", "AbortError"); } });
  await assert.rejects(cliente.listar(TERRENO), (e) => e.name === "AbortError");
  await assert.rejects(cliente.historial("../../api/config"), (e) => e.codigo === "not_found");
  await assert.rejects(cliente.descargar("x", "pdf"), (e) => e.codigo === "not_found");
  assert.deepEqual(llamadas, [`/api/inventario/terrenos/${TERRENO}/archivos?limite=20`]);
  // A response that arrives after the captured private scope ended is dropped.
  const fin = new AbortController(); fin.abort();
  const tarde = A.crearClienteArchivos({ peticionPrivada: async () => ({ response: json(200, { archivos: [] }), signal: fin.signal }) });
  await assert.rejects(tarde.listar(TERRENO), (e) => e.name === "AbortError");
});

test("client: requests carry exact paths, bodies and keys; PUT never sets Content-Length", async () => {
  const vistas = [];
  const cliente = A.crearClienteArchivos({ peticionPrivada: async (ruta, o) => { vistas.push({ ruta, ...o }); return { response: json(200, {}) }; } });
  const aid = randomUUID(), vid = randomUUID(), gid = randomUUID();
  await cliente.activar(aid, { versionId: vid, geometriaId: gid, revision: 4 }, "clave-1");
  await cliente.retirar(aid, 5, "clave-2");
  await cliente.procesar(vid, [0, 2], "clave-3");
  await cliente.subir(vid, "kmz", new Blob([new Uint8Array(3)]));
  await cliente.versiones(aid, { cursor: 7, limite: 5 });
  assert.equal(vistas[0].ruta, `/api/archivos/${aid}/activar`);
  assert.deepEqual(JSON.parse(vistas[0].body), { version_id: vid, geometria_id: gid, expected_revision: 4 });
  assert.equal(vistas[0].headers["Idempotency-Key"], "clave-1");
  assert.deepEqual(JSON.parse(vistas[1].body), { expected_revision: 5 });
  assert.deepEqual(JSON.parse(vistas[2].body), { seleccion: [0, 2] });
  assert.equal(vistas[3].method, "PUT");
  assert.equal(vistas[3].ruta, `/api/archivos/versiones/${vid}/contenido?parte=0`);
  assert.deepEqual(vistas[3].headers, { "Content-Type": "application/vnd.google-earth.kmz" });
  assert.ok(vistas[3].body instanceof Blob);
  assert.equal(vistas[4].ruta, `/api/archivos/${aid}/versiones?limite=5&cursor=7`);
});

/* A sliced download server (route 9, M1): `?desde=O`, at most 3 MiB per reply.
 * `alterar(desde, headers, cuerpo)` may change one reply. */
function servidorDescarga(contenido, vid, { alterar = () => {}, vistas = [] } = {}) {
  const firma = sha(contenido);
  return async (ruta, { signal } = {}) => {
    vistas.push(ruta);
    if (signal?.aborted) throw new DOMException("x", "AbortError");
    const desde = Number(new URLSearchParams(ruta.split("?")[1] ?? "").get("desde") ?? 0);
    const fin = Math.min(contenido.length, desde + A.PARTE_BYTES);
    let cuerpo = contenido.subarray(desde, fin);
    const headers = { "Content-Type": "application/octet-stream", "X-Archivo-Version-Id": vid,
      "X-Archivo-Sha256": firma, "X-Archivo-Bytes": String(contenido.length), "X-Archivo-Desde": String(desde),
      "X-Archivo-Longitud": String(fin - desde), "X-Archivo-Siguiente": fin === contenido.length ? "fin" : String(fin) };
    cuerpo = alterar(desde, headers, cuerpo) ?? cuerpo;
    return { response: new Response(cuerpo, { status: 200, headers }), signal };
  };
}

const grande = (n) => { const b = Buffer.alloc(n); for (let i = 0; i < n; i += 1) b[i] = (i * 31 + 7) & 0xff; return b; };

test("client: a single-slice download must match its version id, type, size and SHA-256", async () => {
  const vid = randomUUID();
  const con = (alterar) => A.crearClienteArchivos({ peticionPrivada: servidorDescarga(PDF, vid, { alterar }) });
  const r = await con().descargar(vid, "pdf");
  assert.equal(Buffer.from(r.bytes).toString(), PDF.toString());
  assert.equal(r.tipoContenido, "application/pdf");
  for (const alterar of [
    (d, h) => { h["X-Archivo-Version-Id"] = randomUUID(); },
    (d, h) => { h["Content-Type"] = "text/html"; },
    (d, h) => { h["Content-Type"] = "application/pdf"; },          // the slice type is octet-stream only
    (d, h) => { h["X-Archivo-Sha256"] = "0".repeat(64); },
    (d, h) => { h["X-Archivo-Sha256"] = "ABC"; },
    (d, h) => { h["X-Archivo-Bytes"] = String(PDF.length + 1); },
    (d, h) => { h["X-Archivo-Bytes"] = "0x10"; },
    (d, h) => { h["X-Archivo-Longitud"] = String(PDF.length - 1); },
    (d, h) => { h["X-Archivo-Desde"] = "3145728"; },
    (d, h) => { h["X-Archivo-Siguiente"] = String(PDF.length); },
    (d, h) => { delete h["X-Archivo-Siguiente"]; },
    (d, h, c) => c.subarray(1),                                      // shorter than announced
    (d, h, c) => { const x = Buffer.from(c); x[0] ^= 1; return x; },  // corrupt bytes
  ]) {
    await assert.rejects(con(alterar).descargar(vid, "pdf"), (e) => e.codigo === "descarga_inconsistente", String(alterar));
  }
  await assert.rejects(con((d, h) => { h["X-Archivo-Bytes"] = String(26 * 1024 * 1024); }).descargar(vid, "pdf"),
    (e) => e.codigo === "descarga_inconsistente");                   // above the kind's limit: nothing allocated
  await assert.rejects(con((d, h, c) => Buffer.concat([c, Buffer.from("x")])).descargar(vid, "pdf"),
    (e) => e.codigo === "respuesta_excesiva");                       // more than announced
});

test("client: a 7 MiB download is assembled from three bounded slices and verified whole", async () => {
  const vid = randomUUID();
  const contenido = grande(7 * 1024 * 1024 + 5);
  const vistas = [];
  const progreso = [];
  const cliente = A.crearClienteArchivos({ peticionPrivada: servidorDescarga(contenido, vid, { vistas }) });
  const r = await cliente.descargar(vid, "kmz", { alProgreso: (a, b) => progreso.push([a, b]) });
  assert.ok(Buffer.from(r.bytes).equals(contenido));
  assert.equal(r.sha256, sha(contenido));
  const base = `/api/archivos/versiones/${vid}/descarga`;
  assert.deepEqual(vistas, [base, `${base}?desde=3145728`, `${base}?desde=6291456`]);
  assert.deepEqual(progreso.map(([a]) => a), [3145728, 6291456, contenido.length]);

  const falla = async (alterar) => assert.rejects(
    A.crearClienteArchivos({ peticionPrivada: servidorDescarga(contenido, vid, { alterar }) }).descargar(vid, "kmz"),
    (e) => e.codigo === "descarga_inconsistente");
  await falla((d, h) => { if (d) h["X-Archivo-Sha256"] = "1".repeat(64); });   // the object changed between slices
  await falla((d, h) => { if (d) h["X-Archivo-Bytes"] = String(contenido.length + 1); });
  await falla((d, h) => { if (d === 3145728) h["X-Archivo-Siguiente"] = "fin"; });
  await falla((d, h, c) => { if (d === 6291456) { const x = Buffer.from(c); x[3] ^= 1; return x; } });
  await falla((d, h) => { if (d) h["X-Archivo-Desde"] = "0"; });             // replayed first slice
  // A server that never says "fin" stops after the bounded number of requests.
  const nunca = [];
  await falla((d, h) => { nunca.push(d); h["X-Archivo-Siguiente"] = String(d + Number(h["X-Archivo-Longitud"])); });
  assert.ok(nunca.length <= A.MAX_PARTES);
});

test("client: cancelling a sliced download stops it and keeps nothing", async () => {
  const vid = randomUUID();
  const contenido = grande(7 * 1024 * 1024);
  const control = new AbortController();
  const vistas = [];
  const base = servidorDescarga(contenido, vid, { vistas });
  const cliente = A.crearClienteArchivos({ peticionPrivada: async (ruta, o) => {
    const r = await base(ruta, o);
    if (vistas.length === 2) control.abort();
    return r;
  } });
  await assert.rejects(cliente.descargar(vid, "kmz", { signal: control.signal }), (e) => e.name === "AbortError");
  assert.equal(vistas.length, 2);
});

test("client: local validation happens before any byte is read", () => {
  assert.equal(A.validarArchivoLocal(archivoDe(PDF), "pdf"), null);
  assert.equal(A.validarArchivoLocal(archivoDe(PDF, "x.kmz"), "pdf").codigo, "tipo_no_permitido");
  assert.equal(A.validarArchivoLocal(archivoDe(new Uint8Array(0)), "pdf").codigo, "archivo_vacio");
  const enorme = { name: "a.kmz", size: 20 * 1024 * 1024 + 1, arrayBuffer: () => { throw new Error("no debe leerse"); } };
  assert.equal(A.validarArchivoLocal(enorme, "kmz").codigo, "archivo_grande");
  const justo = { name: "a.kmz", size: 20 * 1024 * 1024 };
  assert.equal(A.validarArchivoLocal(justo, "kmz"), null);
});

/* ---------------------------------------------------- upload pipeline */

function subidaCon(servidor, opciones = {}) {
  const cliente = A.crearClienteArchivos({ peticionPrivada: servidor.peticionPrivada });
  const fases = [];
  let cambios = 0;
  const s = crearSubida({ cliente, terrenoId: TERRENO, tipo: "pdf", archivo: archivoDe(PDF),
    alCambiar: (e) => fases.push(e.fase), alServidor: () => { cambios += 1; }, ...opciones });
  return { s, fases, cambios: () => cambios };
}

test("upload: hash → start → PUT → complete in order, with honest phases", async () => {
  const srv = lifecycle();
  const { s, fases, cambios } = subidaCon(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.deepEqual(srv.registro.map((r) => r.split(" ")[0] + " " + r.split("/").at(-1)),
    ["POST archivos", "PUT contenido", "POST completar"]);
  assert.deepEqual([...new Set(fases)], [FASE.LEYENDO, FASE.INICIANDO, FASE.SUBIENDO, FASE.COMPLETANDO, FASE.LISTO]);
  const v = [...srv.versiones.values()][0];
  assert.equal(v.sha256_declarado, sha(PDF));
  assert.equal(v.tamano_declarado, PDF.length);
  assert.ok(cambios() >= 2);
});

test("upload: a lost start reply is resolved by replaying the same key, not a second version", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("POST", /\/terrenos\/.+\/archivos$/, "perder"));
  const { s } = subidaCon(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.INCIERTO);
  assert.equal(s.estado().reintentable, true);
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.equal(srv.versiones.size, 1);                 // one logical upload, one version
  assert.equal(srv.porClave.size, 1);
});

test("upload: a lost completion reply is resolved by terminal replay", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("POST", /completar$/, "perder"));
  const { s } = subidaCon(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.INCIERTO);
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.equal(s.estado().resultado.replay, true);
  assert.equal(srv.versiones.size, 1);
  assert.equal([...srv.versiones.values()][0].puts, 1);   // content was not sent twice
});

test("upload: a PUT that never arrived is re-staged for the same version only", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("PUT", /contenido(\?|$)/, "antes"));
  const { s } = subidaCon(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.INCIERTO);
  const versionId = s.estado().versionId;
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.equal(s.estado().versionId, versionId);
  assert.equal(srv.versiones.size, 1);
});

test("upload: lease in progress waits for the server's hint; nothing retries by itself", async () => {
  const srv = lifecycle();
  let reloj = 1_000_000;
  srv.fallos.push(falla("POST", /completar$/, error(409, "procesamiento_en_curso", { reintentar: true, reintentar_despues_de: 3 })));
  const { s } = subidaCon(srv, { ahora: () => reloj });
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.EN_CURSO);
  assert.equal(s.estado().reintentarDesde, 1_003_000);
  const antes = srv.registro.length;
  await tick(); await tick();
  assert.equal(srv.registro.length, antes);               // no blind loop
  await s.reintentar();                                    // too early: refused locally
  assert.equal(srv.registro.length, antes);
  reloj += 3000;
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);
});

test("upload: expiry, a known failure and a verification failure are terminal and distinct", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("PUT", /contenido(\?|$)/, error(409, "subida_expirada")));
  const exp = subidaCon(srv).s;
  await exp.ejecutar();
  assert.equal(exp.estado().fase, FASE.EXPIRADO);
  assert.equal(exp.estado().reintentable, false);

  const srv2 = lifecycle();
  srv2.fallos.push(falla("POST", /\/terrenos\/.+\/archivos$/, error(409, "limite_pendientes")));
  const lim = subidaCon(srv2).s;
  await lim.ejecutar();
  assert.equal(lim.estado().fase, FASE.FALLIDO);
  assert.equal(lim.estado().codigo, "limite_pendientes");
  assert.equal(srv2.versiones.size, 0);

  const srv3 = lifecycle();
  const otro = Buffer.from(PDF); otro[3] ^= 1;
  srv3.fallos.push({ coincide: (m, r) => m === "PUT", modo: null });
  const cliente = A.crearClienteArchivos({ peticionPrivada: async (ruta, o) => (o.method === "PUT"
    ? srv3.peticionPrivada(ruta, { ...o, body: new Blob([otro]) }) : srv3.peticionPrivada(ruta, o)) });
  const mal = crearSubida({ cliente, terrenoId: TERRENO, tipo: "pdf", archivo: archivoDe(PDF) });
  await mal.ejecutar();
  assert.equal(mal.estado().fase, FASE.FALLIDO);
  assert.equal(mal.estado().codigo, "sha256_no_coincide");
});

/* ------------------------------------------------- bounded transfer (M1) */

const SIETE = grande(7 * 1024 * 1024 + 11);          // three parts: 3 MiB, 3 MiB, 1 MiB + 11
const rutasPut = (srv) => srv.registro.filter((r) => r.startsWith("PUT"));

function subidaGrande(srv, opciones = {}) {
  const vistas = [];
  const cliente = A.crearClienteArchivos({ peticionPrivada: async (ruta, o) => {
    if (o?.method === "PUT") vistas.push(ruta.split("parte=")[1]);
    return srv.peticionPrivada(ruta, o);
  } });
  const estados = [];
  const s = crearSubida({ cliente, terrenoId: TERRENO, tipo: "pdf", archivo: archivoDe(SIETE),
    alCambiar: (e) => estados.push(e), ...opciones });
  return { s, partesPut: vistas, estados };
}

test("upload M1: a 7 MiB file travels as three sequential parts with part progress", async () => {
  const srv = lifecycle();
  const { s, partesPut, estados } = subidaGrande(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.deepEqual(partesPut, ["0", "1", "2"]);
  const v = [...srv.versiones.values()][0];
  assert.deepEqual([...v.staged.keys()].sort(), [0, 1, 2]);
  assert.deepEqual([...v.staged.values()].map((b) => b.byteLength), [3145728, 3145728, SIETE.length - 6291456]);
  const mensajes = estados.filter((e) => e.fase === FASE.SUBIENDO).map((e) => e.mensaje);
  assert.ok(mensajes.includes("Enviando el archivo (parte 1 de 3)…"));
  assert.ok(mensajes.includes("Enviando el archivo (parte 3 de 3)…"));
  assert.equal(estados.at(-1).partes, 3);
});

test("upload M1: a part that failed is sent again with the parts after it, never the confirmed ones", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("PUT", /parte=1$/, "antes"));
  const { s, partesPut } = subidaGrande(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.INCIERTO);
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.deepEqual(partesPut, ["0", "1", "1", "2"]);
  assert.equal(srv.versiones.size, 1);
});

test("upload M1: missing parts named by completion are the only ones re-sent before the deadline", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("POST", /completar$/, error(409, "contenido_temporal_ausente",
    { partes_faltantes: [1], reintentar: true })));
  const { s, partesPut } = subidaGrande(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.INTERRUMPIDO);
  assert.equal(s.estado().reintentable, true);
  assert.equal(s.estado().reiniciable, false);
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.deepEqual(partesPut, ["0", "1", "2", "1"]);
});

test("upload M1: after the upload window, the user cancels and starts fresh under a new key", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("POST", /completar$/, error(409, "contenido_temporal_ausente",
    { partes_faltantes: [0, 2], reintentar: false })));
  const { s, partesPut } = subidaGrande(srv);
  await s.ejecutar();
  const vieja = s.estado().versionId;
  const claveVieja = s.clave;
  assert.equal(s.estado().fase, FASE.INTERRUMPIDO);
  assert.equal(s.estado().reintentable, false);         // the old version can no longer be fed
  assert.equal(s.estado().reiniciable, true);
  assert.equal(s.estado().cancelable, true);
  await s.reintentar();
  assert.deepEqual(partesPut, ["0", "1", "2"]);          // nothing re-sent
  await s.reiniciar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.notEqual(s.estado().versionId, vieja);
  assert.notEqual(s.clave, claveVieja);
  assert.equal(srv.porClave.size, 2);
  assert.equal(srv.versiones.get(vieja).final.version.estado, "cancelado");
  const orden = srv.registro.map((r) => r.split("/").at(-1));
  assert.deepEqual(orden.slice(-6), ["cancelar", "archivos", "contenido", "contenido", "contenido", "completar"]);
});

test("upload M1: a fresh start is not sent when the old version cannot be cancelled", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("POST", /completar$/, error(409, "contenido_temporal_ausente",
    { partes_faltantes: [1], reintentar: false })));
  srv.fallos.push(falla("POST", /cancelar$/, error(503, "almacen_no_disponible", { reintentar: true })));
  const { s } = subidaGrande(srv);
  await s.ejecutar();
  await s.reiniciar();
  assert.notEqual(s.estado().fase, FASE.CANCELADO);
  assert.match(s.estado().mensaje, /No se pudo cancelar/);
  assert.equal(srv.porClave.size, 1);                    // no second start
});

test("upload M1: an expired upload can be started fresh without a cancel call", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("PUT", /parte=0$/, error(410, "subida_expirada")));
  const { s } = subidaGrande(srv);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.EXPIRADO);
  assert.equal(s.estado().reiniciable, true);
  await s.reiniciar();
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.equal(srv.porClave.size, 2);
  assert.ok(!srv.registro.some((r) => r.endsWith("/cancelar")));
});

test("upload M1: a transfer plan that does not match the file sends no part", async () => {
  const srv = lifecycle();
  const original = srv.peticionPrivada;
  const cliente = A.crearClienteArchivos({ peticionPrivada: async (ruta, o) => {
    const r = await original(ruta, o);
    if (o?.method === "POST" && /\/archivos$/.test(ruta) && r.response.ok) {
      const dto = await r.response.json();
      return { ...r, response: json(200, { ...dto, transferencia: { parte_bytes: 1024, partes: 2 } }) };
    }
    return r;
  } });
  const s = crearSubida({ cliente, terrenoId: TERRENO, tipo: "pdf", archivo: archivoDe(SIETE) });
  await s.ejecutar();
  assert.equal(s.estado().codigo, "transferencia_inconsistente");
  assert.equal(s.estado().cancelable, true);
  assert.equal(rutasPut(srv).length, 0);
});

test("upload M1: store answers keep their retry and cleanup meaning", async () => {
  const noConf = lifecycle();
  noConf.fallos.push(falla("POST", /\/terrenos\/.+\/archivos$/, error(503, "almacen_no_configurado", { reintentar: false })));
  const a = subidaCon(noConf).s;
  await a.ejecutar();
  assert.equal(a.estado().fase, FASE.FALLIDO);
  assert.equal(a.estado().reintentable, false);
  assert.equal(noConf.versiones.size, 0);

  const denegado = lifecycle();
  denegado.fallos.push(falla("POST", /completar$/, error(503, "almacen_no_disponible", { reintentar: false })));
  const b = subidaCon(denegado).s;
  await b.ejecutar();
  assert.equal(b.estado().fase, FASE.INTERRUMPIDO);
  assert.equal(b.estado().reintentable, false);
  assert.equal(b.estado().cancelable, true);

  const incierto = lifecycle();
  incierto.fallos.push(falla("POST", /completar$/, error(503, "almacen_no_disponible",
    { reintentar: true, limpieza_pendiente: true })));
  const c = subidaCon(incierto).s;
  await c.ejecutar();
  assert.equal(c.estado().fase, FASE.INTERRUMPIDO);
  assert.equal(c.estado().reintentable, true);
  assert.equal(c.estado().limpiezaPendiente, true);
  await c.reintentar();                                  // a fresh completion with a fresh nonce
  assert.equal(c.estado().fase, FASE.LISTO);
});

test("upload: KMZ outcomes are reported separately from the upload", async () => {
  for (const [resultado, fase] of [["listo", FASE.LISTO], ["requiere_seleccion", FASE.REQUIERE_SELECCION], ["rechazado", FASE.RECHAZADO]]) {
    const srv = lifecycle({ kmzResultado: resultado });
    const s = crearSubida({ cliente: A.crearClienteArchivos(srv), terrenoId: TERRENO, tipo: "kmz",
      archivo: archivoDe(PDF, "contorno.kmz") });
    await s.ejecutar();
    assert.equal(s.estado().fase, fase, resultado);
  }
});

test("upload: explicit cancellation calls the server and reports its answer", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("PUT", /contenido(\?|$)/, "antes"));
  const { s } = subidaCon(srv);
  await s.ejecutar();
  assert.equal(s.estado().cancelable, true);
  await s.cancelar();
  assert.equal(s.estado().fase, FASE.CANCELADO);
  assert.ok(srv.registro.some((r) => r.endsWith("/cancelar")));
  assert.equal([...srv.versiones.values()][0].final.version.estado, "cancelado");
});

test("upload: cancelling after the server finished says so and shows the real outcome", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("POST", /completar$/, "perder"));     // completed on the server, reply lost
  const { s } = subidaCon(srv);
  await s.ejecutar();
  await s.cancelar();
  assert.equal(s.estado().fase, FASE.INCIERTO);
  assert.match(s.estado().mensaje, /ya había terminado; no se canceló/);
  await s.reintentar();
  assert.equal(s.estado().fase, FASE.LISTO);                  // not hidden as "cancelled"
});

test("upload: a failed cancellation is never shown as success", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("PUT", /contenido(\?|$)/, "antes"));
  srv.fallos.push(falla("POST", /cancelar$/, error(503, "almacen_no_disponible")));
  const { s } = subidaCon(srv);
  await s.ejecutar();
  await s.cancelar();
  assert.notEqual(s.estado().fase, FASE.CANCELADO);
  assert.match(s.estado().mensaje, /No se pudo cancelar/);
  assert.equal(s.estado().cancelable, true);
});

test("upload: cancelling an uncertain start resolves the key first, then cancels that version", async () => {
  const srv = lifecycle();
  srv.fallos.push(falla("POST", /\/terrenos\/.+\/archivos$/, "perder"));
  const { s } = subidaCon(srv);
  await s.ejecutar();
  await s.cancelar();
  assert.equal(s.estado().fase, FASE.CANCELADO);
  assert.equal(srv.versiones.size, 1);
  assert.equal([...srv.versiones.values()][0].final.version.estado, "cancelado");
});

test("upload: one pipeline per factory turn; a second file is refused, not queued", async () => {
  let ocupado = false;
  const turno = { intentar: () => (ocupado ? false : (ocupado = true)), liberar: () => { ocupado = false; } };
  const srv = lifecycle();
  let soltar;
  let retenido = false;
  const lento = { ...srv, peticionPrivada: async (ruta, o) => {
    if (o.method === "PUT" && !retenido) { retenido = true; await new Promise((r) => { soltar = r; }); }
    return srv.peticionPrivada(ruta, o);
  } };
  const uno = subidaCon(lento, { turno }).s;
  const dos = subidaCon(lento, { turno }).s;
  const enCurso = uno.ejecutar();
  while (!soltar) await tick();
  await dos.ejecutar();
  assert.match(dos.estado().mensaje, /Otra subida está en curso/);
  assert.equal(srv.porClave.size, 1);
  soltar();
  await enCurso;
  assert.equal(ocupado, false);
  await dos.reintentar();
  assert.equal(dos.estado().fase, FASE.LISTO);
});

test("upload: local teardown aborts, sends nothing more and installs no late state", async () => {
  const srv = lifecycle();
  let soltar;
  const lento = { peticionPrivada: async (ruta, o) => {
    if (o.method === "PUT") await new Promise((r, j) => { soltar = r; o.signal.addEventListener("abort", () => j(new DOMException("x", "AbortError"))); });
    return srv.peticionPrivada(ruta, o);
  } };
  const vistas = [];
  const s = crearSubida({ cliente: A.crearClienteArchivos(lento), terrenoId: TERRENO, tipo: "pdf",
    archivo: archivoDe(PDF), alCambiar: (e) => vistas.push(e.fase) });
  const p = s.ejecutar();
  while (!soltar) await tick();
  const n = vistas.length;
  s.abortar();
  await p;
  await s.reintentar();
  await s.cancelar();
  assert.equal(vistas.length, n);                          // nothing reported after teardown
  assert.ok(!srv.registro.some((r) => r.includes("completar") || r.includes("cancelar")));
});

test("upload: a reloaded own pending upload needs the same file again", async () => {
  const srv = lifecycle();
  // Create the pending version through the fake server, as another tab would have.
  const cliente = A.crearClienteArchivos(srv);
  const inicio = await cliente.iniciar(TERRENO, { tipo: "pdf", nombre_original: "ficticio.pdf",
    tamano_declarado: PDF.length, sha256_declarado: sha(PDF) }, "clave-previa");
  const s = crearSubida({ cliente, terrenoId: TERRENO, tipo: "pdf", pendiente: {
    id: inicio.version_id, archivo_id: inicio.archivo_id, tamano_declarado: PDF.length, nombre_original: "ficticio.pdf" } });
  assert.equal(s.estado().fase, FASE.REQUIERE_ARCHIVO);
  await s.ejecutar();
  assert.equal(s.estado().fase, FASE.REQUIERE_ARCHIVO);     // no bytes, no request
  await s.elegirArchivo(archivoDe(Buffer.concat([PDF, Buffer.from("x")])));
  assert.equal(s.estado().codigo, "archivo_distinto");
  await s.elegirArchivo(archivoDe(PDF));
  assert.equal(s.estado().fase, FASE.LISTO);
  assert.equal(srv.versiones.size, 1);
});

/* ------------------------------------------------------- summary text */

const R = await import("../../web/components/archivos/resumen.js");
const fila = (extra = {}, ultima = null) => ({ id: randomUUID(), tipo: "pdf", revision: 1, retirado: false,
  version_actual_id: null, geometria_activa_id: null, ultima_version: ultima, ...extra });

test("summary: undefined is loading, not zero; zero is said as such", () => {
  assert.equal(R.describirResumen(undefined, "pdf").estado, R.ESTADO.CARGANDO);
  assert.equal(R.describirResumen(undefined, "kmz").texto, "…");
  assert.equal(R.describirResumen({ pdf_total: 0, pdf_recientes: [], kmz: null }, "pdf").texto, "Sin PDF");
  assert.equal(R.describirResumen({ pdf_total: 0, pdf_recientes: [], kmz: null }, "kmz").texto, "Sin KMZ");
  assert.equal(R.describirResumen({ pdf_recientes: [] }, "pdf").estado, R.ESTADO.CARGANDO);   // no count: not zero
});

test("summary: another account's pending upload stays generic; own states are named", () => {
  const ajena = R.describirResumen({ pdf_total: 1, pdf_recientes: [fila({}, { estado: "subiendo", propia: false })], kmz: null }, "pdf");
  assert.equal(ajena.estado, R.ESTADO.PENDIENTE);
  assert.equal(ajena.nota, "Otra cuenta está subiendo una versión");
  const vid = randomUUID();
  const lista = R.describirResumen({ pdf_total: 3, pdf_recientes: [fila({ version_actual_id: vid },
    { id: vid, numero: 1, estado: "disponible", nombre_original: "a.pdf" })], kmz: null }, "pdf");
  assert.deepEqual([lista.estado, lista.texto, lista.nota], [R.ESTADO.LISTO, "3 PDF", null]);
  const fallida = R.describirResumen({ pdf_total: 1, pdf_recientes: [fila({}, { id: vid, estado: "fallido" })], kmz: null }, "pdf");
  assert.equal(fallida.estado, R.ESTADO.FALLIDO);
});

test("summary: KMZ keeps the active boundary while a replacement is pending or failed", () => {
  const gid = randomUUID(), activa = randomUUID(), nueva = randomUUID();
  const k = (ultima) => ({ pdf_total: 0, pdf_recientes: [], kmz: fila({ tipo: "kmz", version_actual_id: activa,
    geometria_activa_id: gid }, ultima) });
  assert.equal(R.describirResumen(k({ id: activa, estado: "disponible" }), "kmz").texto, "Contorno activo");
  const pendiente = R.describirResumen(k({ estado: "subiendo", propia: false }), "kmz");
  assert.deepEqual([pendiente.texto, pendiente.estado], ["Contorno activo", R.ESTADO.PENDIENTE]);
  const fallo = R.describirResumen(k({ id: nueva, estado: "fallido" }), "kmz");
  assert.deepEqual([fallo.texto, fallo.estado], ["Contorno activo", R.ESTADO.FALLIDO]);
  const sinActivar = R.describirResumen({ pdf_total: 0, pdf_recientes: [], kmz: fila({ tipo: "kmz" },
    { id: nueva, estado: "disponible" }) }, "kmz");
  assert.equal(sinActivar.estado, R.ESTADO.SIN_ACTIVAR);
});

test("summary: download names lose separators and control characters", () => {
  assert.equal(R.nombreSeguro("../../etc/passwd", "pdf"), ".._.._etc_passwd.pdf");
  assert.equal(R.nombreSeguro("Avalúo\r\n\"final\".PDF", "pdf"), "Avalúo_final_.PDF");
  assert.equal(R.nombreSeguro("", "kmz"), "archivo.kmz");
  assert.equal(R.tamanoLegible(1536), "1.5 KB");
  assert.equal(R.tamanoLegible(undefined), "");
});

test("client: a 401 the bridge reports (after its teardown) is a session error, not uncertainty", async () => {
  const cliente = A.crearClienteArchivos({ peticionPrivada: async () => { throw Object.assign(new Error("x"), { status: 401 }); } });
  await assert.rejects(cliente.listar(TERRENO), (e) => e.codigo === "unauthenticated" && e.incierto === false);
});

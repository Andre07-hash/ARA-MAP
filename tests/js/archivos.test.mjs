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

  function actuar(metodo, ruta, headers, body) {
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
        completar_antes_de: "2026-10-09T13:00:00+00:00" };
      porClave.set(clave, { hash, dto });
      versiones.set(dto.version_id, { ...dto, staged: null, final: null, puts: 0 });
      return json(200, dto);
    }
    if ((m = ruta.match(/^\/api\/archivos\/versiones\/([^/]+)\/(contenido|completar|cancelar)$/))) {
      const v = versiones.get(m[1]);
      if (!v) return error(404, "not_found");
      if (m[2] === "contenido") {
        if (v.final) return error(409, "subida_no_pendiente");
        v.staged = body; v.puts += 1;
        return json(200, { version_id: v.version_id, bytes_recibidos: body.byteLength, estado: "subiendo" });
      }
      if (m[2] === "cancelar") {
        if (v.final) return error(409, "subida_no_pendiente");
        v.final = { version: { id: v.version_id, estado: "cancelado" } };
        return json(200, { version_id: v.version_id, estado: "cancelado", limpieza_pendiente: false });
      }
      if (v.final) return json(200, { ...v.final, replay: true });
      if (!v.staged) return error(409, "contenido_temporal_ausente");
      const ok = sha(Buffer.from(v.staged)) === v.sha256_declarado;
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
    const response = actuar(method, ruta.split("?")[0], headers, bytes ?? new Uint8Array());
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
  assert.deepEqual(vistas[3].headers, { "Content-Type": "application/vnd.google-earth.kmz" });
  assert.ok(vistas[3].body instanceof Blob);
  assert.equal(vistas[4].ruta, `/api/archivos/${aid}/versiones?limite=5&cursor=7`);
});

test("client: a download must match its version id, type and SHA-256", async () => {
  const vid = randomUUID();
  const ok = { "Content-Type": "application/pdf", "X-Archivo-Version-Id": vid, "X-Archivo-Sha256": sha(PDF) };
  const con = (headers, cuerpo = PDF) => A.crearClienteArchivos({ peticionPrivada: async () => ({ response: new Response(cuerpo, { status: 200, headers }) }) });
  const r = await con(ok).descargar(vid, "pdf");
  assert.equal(Buffer.from(r.bytes).toString(), PDF.toString());
  for (const malo of [{ ...ok, "X-Archivo-Version-Id": randomUUID() }, { ...ok, "Content-Type": "text/html" },
    { ...ok, "X-Archivo-Sha256": "0".repeat(64) }]) {
    await assert.rejects(con(malo).descargar(vid, "pdf"), (e) => e.codigo === "descarga_inconsistente");
  }
  await assert.rejects(con({ ...ok, "Content-Length": String(26 * 1024 * 1024) }).descargar(vid, "pdf"),
    (e) => e.codigo === "respuesta_excesiva");
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
  srv.fallos.push(falla("PUT", /contenido$/, "antes"));
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
  srv.fallos.push(falla("PUT", /contenido$/, error(409, "subida_expirada")));
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
  srv.fallos.push(falla("PUT", /contenido$/, "antes"));
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
  srv.fallos.push(falla("PUT", /contenido$/, "antes"));
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

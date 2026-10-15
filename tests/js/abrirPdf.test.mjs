/* Opening saved PDFs from the table cell and the detail (issue #48).
 * Run with: node --test tests/js/abrirPdf.test.mjs
 *
 * Pure parts only: which saved PDFs a summary or a list page offers, and the
 * shared open flow over a fake client and fake tabs. Fictional data; no DOM,
 * no network. The cell itself is checked in a browser (tests/e2e/tabla-abrir-pdf.mjs).
 */

import base from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";

const test = (nombre, fn) => base(nombre, { timeout: 10_000 }, fn);

const R = await import("../../web/components/archivos/resumen.js");
const P = await import("../../web/components/archivos/abrirPdf.js");
const { ErrorArchivos } = await import("../../web/lib/archivos.js");

const fila = (extra = {}, ultima = null) => ({ id: randomUUID(), tipo: "pdf", revision: 1, retirado: false,
  version_actual_id: null, geometria_activa_id: null, ultima_version: ultima, ...extra });
const guardado = (nombre = "ficticio.pdf") => {
  const vid = randomUUID();
  return fila({ version_actual_id: vid }, { id: vid, numero: 1, estado: "disponible", nombre_original: nombre });
};
const abortError = () => new DOMException("x", "AbortError");

/* --------------------------------------------------- what can be opened */

test("options: only a saved version is offered; unfinished, expired and refused uploads are not", () => {
  const g = guardado("Avalúo ficticio.pdf");
  assert.deepEqual(R.opcionPdf(g), { archivoId: g.id, versionId: g.version_actual_id,
    nombre: "Avalúo ficticio.pdf", nota: null });
  for (const estado of ["subiendo", "expirado", "fallido", "cancelado"]) {
    assert.equal(R.opcionPdf(fila({}, { id: randomUUID(), estado, propia: true })), null, estado);
  }
  assert.equal(R.opcionPdf(fila({}, { estado: "subiendo", propia: false })), null, "another account's upload");
  assert.equal(R.opcionPdf(fila({}, null)), null, "attachment without versions");
  assert.equal(R.opcionPdf({ ...g, retirado: true }), null, "retired (summary)");
  assert.equal(R.opcionPdf({ ...g, retirado_en: "2026-10-01T00:00:00Z" }), null, "retired (list)");
  assert.equal(R.opcionPdf({ ...g, tipo: "kmz" }), null, "a KMZ is not a PDF");
});

test("options: a failed replacement keeps the earlier saved version openable, without naming it after the failed file", () => {
  const vid = randomUUID();
  for (const estado of ["expirado", "fallido", "subiendo"]) {
    const f = fila({ version_actual_id: vid }, { id: randomUUID(), numero: 2, estado, propia: true,
      nombre_original: "reemplazo-ficticio.pdf" });
    const o = R.opcionPdf(f);
    assert.equal(o.versionId, vid, estado);
    assert.equal(o.nombre, null, "the saved version's own name is unknown");
    assert.ok(o.nota, "says what happened to the newer upload");
  }
  const ajena = R.opcionPdf(fila({ version_actual_id: vid }, { estado: "subiendo", propia: false }));
  assert.equal(ajena.versionId, vid);
});

test("summary: one saved PDF is certain; several, none or a truncated list are said as such", () => {
  assert.equal(R.pdfsDelResumen(undefined), null, "no summary yet");
  assert.equal(R.pdfsDelResumen({ pdf_recientes: [] }), null, "no count");
  assert.deepEqual(R.pdfsDelResumen({ pdf_total: 0, pdf_recientes: [] }), { completo: true, opciones: [] });

  const uno = guardado();
  const pendiente = fila({}, { id: randomUUID(), estado: "expirado", propia: true });
  const r1 = R.pdfsDelResumen({ pdf_total: 2, pdf_recientes: [pendiente, uno] });
  assert.equal(r1.completo, true);
  assert.deepEqual(r1.opciones.map((o) => o.versionId), [uno.version_actual_id], "the saved one, not the newest row");
  assert.equal(R.describirResumen({ pdf_total: 2, pdf_recientes: [pendiente, uno] }, "pdf").texto, "1 PDF");

  const varios = [guardado("a.pdf"), guardado("b.pdf"), guardado("c.pdf")];
  const r3 = R.pdfsDelResumen({ pdf_total: 3, pdf_recientes: varios });
  assert.deepEqual(r3.opciones.map((o) => o.nombre), ["a.pdf", "b.pdf", "c.pdf"]);

  // The server lists five of seven: nothing is concluded about the other two.
  const cinco = [guardado(), ...[1, 2, 3, 4].map(() => fila({}, { id: randomUUID(), estado: "expirado", propia: true }))];
  const truncado = R.pdfsDelResumen({ pdf_total: 7, pdf_recientes: cinco });
  assert.equal(truncado.completo, false);
  assert.equal(truncado.opciones.length, 1);

  assert.deepEqual(R.pdfsDelResumen({ pdf_total: 1, pdf_recientes: [pendiente] }), { completo: true, opciones: [] });
});

/* ------------------------------------------------------- the open flow */

function nuevaPestana() {
  const p = { closed: false, opener: {}, cerrada: 0, destino: null,
    document: { title: "", body: { textContent: "" } },
    close() { p.closed = true; p.cerrada += 1; },
    location: { replace: (url) => { p.destino = url; } } };
  return p;
}
function registro() {
  const agregadas = [];
  const base = P.crearRegistroUrls();
  return { agregadas, agregar: (u) => { agregadas.push(u); return base.agregar(u); }, vaciar: base.vaciar, revocar: base.revocar };
}
const bytes = new TextEncoder().encode("%PDF-1.4\n% ficticio\n%%EOF\n");

test("tab: reserved in the gesture, cut off from this page, with a wait text; a refusal is null", () => {
  const p = nuevaPestana();
  const abiertas = [];
  globalThis.window = { open: (...a) => { abiertas.push(a); return p; } };
  try {
    assert.equal(P.reservarPestana(), p);
    assert.deepEqual(abiertas, [["", "_blank"]]);
    assert.equal(p.opener, null);
    assert.match(p.document.body.textContent, /Abriendo/);
    globalThis.window = { open: () => null };
    assert.equal(P.reservarPestana(), null);
    globalThis.window = { open: () => { throw new Error("bloqueada"); } };
    assert.equal(P.reservarPestana(), null);
  } finally {
    delete globalThis.window;
  }
});

test("open: the verified download goes to the reserved tab as a revocable object URL", async () => {
  const pedidas = [];
  const cliente = { descargar: async (id, tipo, { signal }) => { pedidas.push([id, tipo, Boolean(signal)]); return { bytes }; } };
  const p = nuevaPestana();
  const urls = registro();
  const vid = randomUUID();
  const r = await P.abrirPdf({ cliente, versionId: vid, pestana: p, signal: new AbortController().signal, urls });
  assert.deepEqual(r, { abierta: true });
  assert.deepEqual(pedidas, [[vid, "pdf", true]]);
  assert.match(p.destino, /^blob:/);
  assert.deepEqual(urls.agregadas, [p.destino], "the URL is registered for revocation");
  assert.equal(p.cerrada, 0);
  urls.vaciar();
});

test("open: a refused tab yields the URL for a plain link; a tab the person closed too", async () => {
  const cliente = { descargar: async () => ({ bytes }) };
  const urls = registro();
  const sinPestana = await P.abrirPdf({ cliente, versionId: randomUUID(), pestana: null, urls });
  assert.equal(sinPestana.abierta, false);
  assert.equal(sinPestana.cerrada, false, "refused, not closed");
  assert.match(sinPestana.url, /^blob:/);
  const cerrada = nuevaPestana();
  cerrada.closed = true;
  const r = await P.abrirPdf({ cliente, versionId: randomUUID(), pestana: cerrada, urls });
  assert.deepEqual([r.abierta, r.cerrada], [false, true]);
  urls.vaciar();
});

test("open: errors and cancellation close the reserved tab and register nothing", async () => {
  const urls = registro();
  for (const error of [new ErrorArchivos("not_found", "x", { status: 404 }),
    new ErrorArchivos("descarga_inconsistente", "x"), new ErrorArchivos("unauthenticated", "x", { status: 401 }), abortError()]) {
    const p = nuevaPestana();
    const cliente = { descargar: async () => { throw error; } };
    await assert.rejects(P.abrirPdf({ cliente, versionId: randomUUID(), pestana: p, urls }), (e) => e === error);
    assert.equal(p.cerrada, 1, `${error.name}: no empty tab left`);
  }
  // Cancelled after the bytes arrived: still no tab, no URL.
  const control = new AbortController();
  const p = nuevaPestana();
  const cliente = { descargar: async () => { control.abort(); return { bytes }; } };
  await assert.rejects(P.abrirPdf({ cliente, versionId: randomUUID(), pestana: p, signal: control.signal, urls }),
    (e) => e.name === "AbortError");
  assert.equal(p.cerrada, 1);
  assert.equal(urls.agregadas.length, 0);
});

test("registry: URLs are revoked once, by time or all at once", () => {
  const revocadas = [];
  const original = URL.revokeObjectURL;
  URL.revokeObjectURL = (u) => revocadas.push(u);
  try {
    const r = P.crearRegistroUrls();
    r.agregar("blob:a");
    r.agregar("blob:b");
    r.revocar("blob:a");
    r.revocar("blob:a");
    r.vaciar();
    r.vaciar();
    assert.deepEqual(revocadas, ["blob:a", "blob:b"]);
  } finally {
    URL.revokeObjectURL = original;
  }
});

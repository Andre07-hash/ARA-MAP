/* Tests for the upload side of the API client. Run with: node --test tests/js/api.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";

const { api, configureApi } = await import("../../web/lib/api.js");

function recordFetch() {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => ({ token: "t" }) };
  };
  return calls;
}

const file = (name, size = 10) => ({ name, size });

test("a CSV preview sends the number convention and keeps base_id", async () => {
  const calls = recordFetch();
  await api.preview(file("Terrenos Octubre.csv"), 7, "comma");
  const url = new URL(calls[0].url, "http://localhost");
  assert.equal(url.pathname, "/api/importar/vista-previa");
  assert.equal(url.searchParams.get("base_id"), "7");
  assert.equal(url.searchParams.get("csv_decimal"), "comma");
  assert.equal(calls[0].options.headers["X-Archivo"], "Terrenos%20Octubre.csv");
});

test("an Excel preview sends no query at all", async () => {
  const calls = recordFetch();
  await api.preview(file("base.xlsx"));
  assert.equal(calls[0].url, "/api/importar/vista-previa");
});

test("the configured upload limit applies to CSV before anything is sent", async () => {
  const calls = recordFetch();
  configureApi({ maxUploadBytes: 4 * 1024 * 1024 });
  await assert.rejects(api.preview(file("grande.csv", 4 * 1024 * 1024 + 1), null, "dot"), /4 MB/);
  assert.equal(calls.length, 0);
  configureApi({ maxUploadBytes: 25 * 1024 * 1024 });
});

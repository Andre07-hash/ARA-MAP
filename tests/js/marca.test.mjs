/* The header logo and the name written beside it (web/lib/marca.js).
 * Run with: node --test tests/js/marca.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { logoDe } from "../../web/lib/marca.js";

test("the ARA mark reads «ARA Map»; the Dewa wordmark only «Map»", () => {
  assert.equal(logoDe({ marca: "ara" }).nombre, "ARA Map");
  assert.equal(logoDe({ marca: "dewa" }).nombre, "Map");
  assert.equal(logoDe(null).nombre, "ARA Map");
  assert.equal(logoDe({ marca: "otra" }).nombre, "ARA Map");
});

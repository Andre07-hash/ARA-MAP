/* Negative controls for the geometry loader: break it on purpose and check
 * that tests/js/cargadorGeometrias.test.mjs notices each break.
 *
 *   node reports/team-b-file-ui-geometry-2026-10-09/mutaciones_cargador.mjs
 *
 * Each mutation rewrites one line of a temporary copy of web/ and runs the
 * unchanged test file against it. A mutation the tests do not reject would be
 * a gap. Prints one JSON line per run; exit code 1 if any mutation survives.
 */

import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const MUTACIONES = {
  "sin comprobar el hash completo": ['if (digest !== meta.sha256) throw new ErrorGeometria("hash_no_coincide");', ""],
  "no cancela la carga obsoleta": ["    enCurso.control.abort();\n    const nueva", "    const nueva"],
  "reset no cancela la carga en curso": ["    if (enCurso) enCurso.control.abort();\n  }", "  }"],
  "destroy no impide cargas nuevas": ["    if (destruido) return Promise.reject(new ErrorGeometria(\"destruido\"));\n", ""],
  "acepta un fragmento con otro id": ['      || h.get("X-Geometria-Id") !== meta.id\n', ""],
  "acepta metadatos de otro terreno": ["meta.id !== geometria.id || meta.terreno_id !== terrenoId", "meta.id !== geometria.id"],
};

let sobrevive = 0;
for (const control of [null, ...Object.keys(MUTACIONES)]) {
  const copia = mkdtempSync(join(tmpdir(), "mut-cargador-"));
  try {
    cpSync(join(RAIZ, "web"), join(copia, "web"), { recursive: true });
    cpSync(join(RAIZ, "tests", "js"), join(copia, "tests", "js"), { recursive: true });
    if (control) {
      const ruta = join(copia, "web", "lib", "cargadorGeometrias.js");
      const [antes, despues] = MUTACIONES[control];
      const texto = readFileSync(ruta, "utf8");
      if (!texto.includes(antes)) throw new Error(`la mutación «${control}» no encontró su línea`);
      writeFileSync(ruta, texto.replace(antes, despues));
    }
    const r = spawnSync(process.execPath, ["--test", "--test-timeout=15000", join(copia, "tests", "js", "cargadorGeometrias.test.mjs")],
      { encoding: "utf8", timeout: 180_000 });
    const fallan = (r.stdout.match(/^not ok \d+ - (.*)$/gm) ?? []).map((l) => l.replace(/^not ok \d+ - /, ""));
    const resultado = control === null ? (r.status === 0 ? "control: pasa" : "CONTROL FALLA")
      : (r.status !== 0 ? "detectada" : "SOBREVIVE");
    if (resultado === "SOBREVIVE" || resultado === "CONTROL FALLA") sobrevive += 1;
    console.log(JSON.stringify({ mutacion: control ?? "ninguna", resultado, pruebas_que_fallan: fallan }));
  } finally {
    rmSync(copia, { recursive: true, force: true });
  }
}
process.exit(sobrevive ? 1 : 0);

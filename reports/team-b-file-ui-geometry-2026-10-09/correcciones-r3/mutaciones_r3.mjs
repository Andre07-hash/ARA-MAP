/* Negative controls for the R3-B1..R3-B5 corrections: undo each correction on
 * purpose in a temporary copy of web/ and check that the regressions in
 * tests/js/archivosCorrecciones.test.mjs notice it.
 *
 *   node reports/team-b-file-ui-geometry-2026-10-09/correcciones-r3/mutaciones_r3.mjs
 *
 * A mutation is one or more exact text replacements. A mutation the tests do
 * not reject would be a gap. Prints one JSON line per run; exit code 1 if any
 * mutation survives or the unmutated control fails.
 */

import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const SUBIDA = "web/components/archivos/subida.js";
const CARGADOR = "web/lib/cargadorGeometrias.js";
const CLIENTE = "web/lib/archivos.js";

const MUTACIONES = {
  "R3-B1 la cancelación no lleva la vida de la subida": [[SUBIDA,
    "cliente.cancelar(inicio.version_id, { signal: senal })", "cliente.cancelar(inicio.version_id)"]],
  "R3-B1 la cancelación no revisa la vida tras esperar": [[SUBIDA,
    "if (!(await soltarPaso())) return;", "await soltarPaso();"],
    [SUBIDA, "        if (muerta()) return;\n        const previo", "        const previo"]],
  "R3-B2 no avisa la pérdida de acceso": [[SUBIDA, "if (!muerta()) alPerderAcceso(error);", ""]],
  "R3-B3 contenido ausente vuelve a ser terminal": [[SUBIDA,
    "fase: FASE.INTERRUMPIDO, reintentable: Boolean(archivo)", "fase: FASE.FALLIDO, reintentable: Boolean(archivo)"]],
  "R3-B3 una completación sin resultado se da por terminada": [[SUBIDA, "if (!resuelto(r)) {", "if (false) {"]],
  "R3-B4 abortar suelta el permiso de inmediato": [[SUBIDA, "if (!corriendo) soltarTurno();", "soltarTurno();"]],
  "R3-B4 un permiso viejo suelta el de otro": [[SUBIDA,
    "liberar(permiso) { if (permiso && permiso === actual) actual = null; }", "liberar() { actual = null; }"]],
  "R3-B5 ni el digest ni la instalación revisan el alcance": [
    [CARGADOR, "          || alcances.some((a) => a.aborted)) {", "          ) {"],
    [CARGADOR, "        if (enCurso !== actual || destruido || control.signal.aborted\n            || alcances.some((a) => a.aborted)) throw abortError();",
      "        if (enCurso !== actual || destruido || control.signal.aborted) throw abortError();"]],
  "R3-B5 el cuerpo listo sobrevive a su alcance": [
    [CARGADOR, "    if (listo && listo.alcances.some((a) => a.aborted)) soltarListo();\n", ""],
    [CARGADOR, "      a.addEventListener(\"abort\"", "      void (\"abort\""]],
  "R3-B5 el PUT no revisa el alcance tras leer": [[CLIENTE,
    "        comprobar(alcance, signal);      // the scope may end while the reply is read\n", ""]],
};

let malos = 0;
for (const control of [null, ...Object.keys(MUTACIONES)]) {
  const copia = mkdtempSync(join(tmpdir(), "mut-r3-"));
  try {
    cpSync(join(RAIZ, "web"), join(copia, "web"), { recursive: true });
    cpSync(join(RAIZ, "tests", "js"), join(copia, "tests", "js"), { recursive: true });
    for (const [archivo, antes, despues] of control ? MUTACIONES[control] : []) {
      const ruta = join(copia, archivo);
      const texto = readFileSync(ruta, "utf8");
      if (!texto.includes(antes)) throw new Error(`la mutación «${control}» no encontró su texto en ${archivo}`);
      writeFileSync(ruta, texto.replace(antes, despues));
    }
    const r = spawnSync(process.execPath, ["--test", join(copia, "tests", "js", "archivosCorrecciones.test.mjs")],
      { encoding: "utf8", timeout: 300_000 });
    const fallan = (r.stdout.match(/^not ok \d+ - (.*)$/gm) ?? []).map((l) => l.replace(/^not ok \d+ - /, ""));
    const resultado = control === null ? (r.status === 0 ? "control: pasa" : "CONTROL FALLA")
      : (r.status !== 0 ? "detectada" : "SOBREVIVE");
    if (resultado === "SOBREVIVE" || resultado === "CONTROL FALLA") malos += 1;
    console.log(JSON.stringify({ mutacion: control ?? "ninguna", resultado, pruebas_que_fallan: fallan }));
  } finally {
    rmSync(copia, { recursive: true, force: true });
  }
}
process.exit(malos ? 1 : 0);

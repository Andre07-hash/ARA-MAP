# Bounded-memory E5 research — correction 2 (R1a, R2a, R1-test)

Date: 2026-10-09. Status: **prototype research only; stopped for supervisory review.**

Requested by supervisory review `c39f8aa71552c16e955be69558ca197d4d2b256c`
(`reports/team-b-corrections-review-2026-10-09/`). Continued additively from
`68077cc366dd3e1885da36b8f5c7223093e4bd63` on the same draft PR #21; no force
push, no restart. Only this research folder changed. R3 and R4 are closed and
untouched. PR #23 (accepted at `a9dc8af`) is untouched.

Round-1 documents and evidence (`CORRECCIONES_2026-10-09.md`,
`correcciones-2026-10-09/` outside `ronda-2/`) are kept as history; this file
supersedes their corrected-result claim. New evidence:
[correcciones-2026-10-09/ronda-2/](correcciones-2026-10-09/ronda-2/).

## 1. Heads

| Item | Commit |
|---|---|
| Supervisor review | `c39f8aa71552c16e955be69558ca197d4d2b256c` |
| Reviewed research head | `68077cc366dd3e1885da36b8f5c7223093e4bd63` |
| PR base (unchanged) | `9da0ab10a344e66099d919f2da15d3a638e7292a` |
| Code + tests commit (all evidence below) | `259303d761baacde7aeb63c1017c0a9eefc0f594` |
| Final head | the commit adding this file; authoritative `headRefOid` of PR #21 |

## 2. Reproduction before fixing

`reproduce_memory_edges.mjs` from the review, run on an archive of `68077cc`,
gave the reported results exactly
([`bordes-revisado.jsonl`](correcciones-2026-10-09/ronda-2/bordes-revisado.jsonl)):
budget 2,487 B with 2,488 B of arrays held and an 80 B audit sum; `asegurar`
returning `listo` with a `cuerpo` posted after termination and 128 B / one
copy retained; and a deterministic allocation failure releasing to 0 B.

## 3. Closure

| Finding | Fix | Regression tests (fail on `68077cc`) | Browser evidence |
|---|---|---|---|
| **R1a** layer admission evicting its own body | The body is **pinned before** the layer's own array is reserved, on both paths: cache hit (`MapCanvas`, pin → reserve → build) and preparation completion (`CapaContornoE5.crearFijada`, used by every layer construction). Refusal or allocation failure undoes the pin; nothing else is released. A body no longer in the registry is never built over. The audit (`inventarioCapas`) now inventories every unique prepared body reachable through live layers (shared bodies counted once) and requires it to be the registry's own entry, pinned at least once per layer; any other byte is reported as held outside the ledger, and the per-frame sampler counts it. | reviewed-order + audit detection; cache-hit refusal keeps the body; completion handoff keeps the body; sharing, two maps, pinned raster held, replacement, unpinned-while-held, teardown | `presion`: cache hit one byte short → `sin_memoria`, body kept (0 pins), audit clean, final after the filler goes; new body one byte short at handoff → same; **negative control**: a lost pin + pressure eviction is detected as "live layers retain 480,052 B of prepared bodies outside the registry". All other scenarios: 0 B outside the registry. |
| **R2a** failure inside relief resumes on a dead client | `asegurar` re-checks the client after `reservar` returns; if its own reliever's forget failed, the reservation is released and `fallido` returned: nothing installed, nothing posted. The reliever stops at the first failure. The controller re-checks after the copy loop and after the raster reservation and settles to `sin_trabajador`, releasing that reservation. | forget failure during a new copy's relief with the terminated worker's post returning normally, and throwing; controller settle + one fresh worker on retry | `presion` (`simular=envioOlvido`, 8 MiB): `fallido/envio`, `sin_trabajador`, 0 B copies reserved; explicit retry builds one fresh worker and all three outlines become final. |
| **R1-test** 16 GiB assumption | The allocation-failure test injects a failing initializer on a 3-part fixture and asserts `RangeError` and a 0 B ledger; it also checks the pinned constructor undoes its pin. No large request. | (portability fix) | — |

### Defects found while verifying (disclosed)

1. **Refusal state lost at first paint (R1 follow-up).** An inherited F3 rule in
   `mostrarContorno` resets unpainted states to `listo` when an outline is
   shown as its symbol. For an E5 entry whose layer was refused at creation
   there is no layer, so the explicit `sin_memoria` was erased. Memory was
   correct; the declared state was not. The derivation now keeps that reset
   for entries with a layer (and all of E1–E4). The `presion` cache-hit case
   reported `listo` before this fix and `sin_memoria` after.
2. **Audit snapshot race.** `__auditar` read the ledger, then awaited each
   worker's statistics, then read owners; a forget acknowledged during the
   await split the comparison. Worker statistics are now collected first and
   every ledger/owner reading taken in one synchronous pass.
3. Test fillers (owner `prueba:…`, one reservation, nothing allocated) are
   reported separately by the audit instead of appearing as unowned bytes.

## 4. Status of the accounting claim

Within the prototype's own managed allocations — prepared arrays (registry,
jobs, **and now every body reachable through a live layer**), per-layer
arrays, worker copies and rasters — the corrected audit and pressure cases
found no byte held outside the ledger, and its negative control shows the
audit detects the reviewed defect. This is evidence over the scenarios run,
not a proof for all interleavings. It is **not** a total-browser-memory bound:
caller GeoJSON bodies (count-bounded by R3, not size-bounded), browser
transients (structured clone, path state), Leaflet's canvas, JS overhead and
OS/GPU/process memory stay outside the study ledger. 64/128 MiB remain study
budgets.

## 5. Evidence (this cloud container)

Node 22.22.0; Chromium 141.0.7390.37 headless (`/opt/pw-browsers`); Intel
Xeon 2.80 GHz × 4, Linux. Developer evidence, not CI; CI does not run the
browser matrix.

| Gate | Result | File in `ronda-2/` |
|---|---|---|
| Prototype unit tests | **37/37**, three consecutive runs | `pruebas.log` |
| Negative control: these tests on `68077cc` | 8/8 new tests fail; the 29 earlier ones pass | `pruebas-control-revisado.log` |
| Review edge probes on `68077cc` | reproduced | `bordes-revisado.jsonl` |
| Adapted edge probes on corrected code | tight: 2,408 B ledger, layer refused, body kept; roomy: 2,488 B = budget, 0 B outside registry; R2a `fallido`, 0 B, no post after termination; injected failure 0 B and pin undone | `sondas-bordes.jsonl` (`../sondas-bordes.mjs`) |
| Review edge probes unchanged on corrected code | probe 2 corrected; probe 1 still shows eviction because it hand-codes the reviewed caller order (obtain → reserve → build → pin) instead of the corrected path; probe 3 unchanged | `bordes-original-sobre-corregido.jsonl` |
| Round-1 probes (R1–R4) | unchanged corrected results | `sondas-r1-r4.jsonl` |
| Browser scenarios incl. new `presion` | all checks passed; every audit 0 errors, 0 sampler violations, 0 B outside registry | `escenarios.log`, `evidencia/memoria-*.json`, `resumen-auditorias.txt` |
| Browser 24-case matrix (layer path and audit changed) | 24/24; 64 MiB max 55.7 MiB, 128 MiB max 101.3 MiB | `matriz.log`, `evidencia/memoria-matriz.json` |
| Paint/interaction | **8/12 E5-vs-E3 complete-RGBA identical, the same four differing scenes**; IoU and ±1/±2 px coverage 1.0; 36/36 clicks; unavailable-outline hit test passes. Exit nonzero for the four RGBA assertions, as before. | `pintura.log`, `evidencia/pintura-e5.json` |
| Timing, one repetition E5/E3 | controls detect every deliberate 150 ms task; E5 longest task 0 ms cold and during input in all three scenes (E3 cold: 0 / 52 / 163 ms) | `tiempos.log`, `evidencia/tiempos-*.json` |
| Repository JS / CI | see PR #21 description | — |

Observation: in `cambio` the audited canvas was 4608×2592 (the 1920×1080 step)
rather than round 1's 2160×1200 (the final 900×500 step); the check passed
because the bitmap matched the current canvas and view, but the harness
evidently audited before Leaflet applied the last resize. Reported, not
interpreted as a size claim.

The historical visual limitation stands unchanged: 8/12 on Chromium 141,
historical 4/12 on Chromium 154 (not rerun; unavailable here). Coverage and
click agreement are not pixel identity; no visual difference is accepted.

## 6. Limitations

- A refused layer stays `sin_memoria` until the next `render()`.
- The pin-first rule lives in the prototype's MapCanvas derivation and
  `crearFijada`; a future integration must keep that ordering.
- Browser transients and process memory are not measured from the page.
- Only Chromium 141 headless on Linux was available.

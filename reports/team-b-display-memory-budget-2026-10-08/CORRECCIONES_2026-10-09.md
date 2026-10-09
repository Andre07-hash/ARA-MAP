# Bounded-memory E5 research — corrections R1–R4

Date: 2026-10-09. Status: **prototype research only; stopped for supervisory review.**

These are the corrections requested by supervisory review
`009a724e4534e419e5703bd411425fd06776db62`
(`reports/team-b-round-1-review-2026-10-08/`). They stay inside this research
folder. `REPORT.md` and `evidencia/` are kept unchanged as the historical record
of the reviewed head, except for a notice that marks the two superseded claims.
New evidence is under [correcciones-2026-10-09/](correcciones-2026-10-09/).

## 1. Exact inputs and heads

| Input | Commit |
|---|---|
| Supervisor review | `009a724e4534e419e5703bd411425fd06776db62` |
| Reviewed research head (PR #21 before correction) | `229d424aab2aa7659f5572fce3be41821e435c56` |
| PR base, corrected display investigation (PR #16) | `9da0ab10a344e66099d919f2da15d3a638e7292a` (unchanged) |
| Accepted B-2 / E1 / B-1 inputs | `5d8e2dc…` / `eed9a4c…` / `efc3628…` (unchanged) |
| Code + tests correction commit (all evidence below) | `6fad4a7afe29b280283d6a5fffb3a11c06b37de4` |
| Final head | the commit adding this file; authoritative `headRefOid` of PR #21 |

The remote head of PR #21 matched the reviewed commit; nothing later existed to
preserve. No force push. No file outside this folder changed; PR #16's folder,
the renderers and the parser are inputs only. Generated limit cases match the
recorded manifest SHA-256 values (only the parser timing field differs).

## 2. Finding dispositions

| Finding | Disposition | Evidence |
|---|---|---|
| **R1** P1 per-layer arrays missing from admission and audit | **Fixed, and inventoried.** New ledger category `capa`: each outline layer's own `Int32Array(partes)` is reserved before it is allocated, one per layer (two layers of one body, or two maps, hold two), released when the layer is discarded (render, teardown) and on allocation failure. `CapaContornoE5` cannot be built without a live `capa` reservation of exactly its size; `CapaContornoE5.crear` admits it (or takes one already admitted). A refusal is the explicit `sin_memoria` state with its symbol and wording, retried on the next `render()`. The browser audit now compares the `capa` ledger with every live layer's reservation and actual `byteLength`; a reservation whose layer is gone shows as ledger excess. That audit found a real leak in my first wiring (a cache-hit layer took a second reservation; 48,024 B leaked per render), fixed before any evidence below was recorded. | Unit: `R1:` tests. Probe: `sondas.mjs` `unaccounted_layer_array`. Browser: every scenario and 24-case matrix, `capa` audit included. |
| **R2** P2 synchronous posts and silent startup | **Fixed.** Every send to the worker (body copy, forget, raster, cancel, reset, statistics) goes through one `enviar`; a synchronous throw takes the single failure path (`motivo: "envio"`): terminate, release every copy/forget reservation, answer every waiter (`{fallo}` for a raster, `false` for a reset, `null` for statistics), notify the controller. The controller settles at once to `sin_trabajador` and the next `render()` builds one fresh worker. The handshake is bounded by `plazoInicioMs` (default `plazoMs`): a worker that never says `listo` fails with `sinInicio`. Late messages after a failure are ignored. | Unit: six send stages, startup bound with mock timers, controller settle + retry. Probes: `synchronous_post_failure`, `silent_startup`. Browser `fallos`: `sinInicio`, `envioCuerpo`, `envioRaster` (the latter two recover on the explicit retry). |
| **R3** P2 uncapped queued raw-body references | **Fixed, contract stated.** Per planner (one per map): at most `MAX_TRABAJOS` = 2 jobs hold memory and at most `MAX_EN_ESPERA` = 30 more wait; total 32. A request for a new body beyond that is refused at once, delivered asynchronously as `{estado: "sin_memoria", motivo: "cola_llena"}`, and retains nothing; the next `render()` asks again. Supersession is unchanged (`conservarSolo` cancels what a newer view no longer needs); a stopped planner admits nothing. Each admitted job keeps a reference to **one** caller body (its own entry, not the caller's Map) until it ends. So this prototype keeps at most 32 caller GeoJSON bodies reachable per map (64 for two maps); those bodies are caller-owned, not charged to the byte budget, and their size still needs the upstream file/body contract. They are not described as absent. | Unit: 100-request burst, supersession, two planners, stopped planner, and a GC check (`WeakRef` + forced collection) that no caller Map or other row's body is retained while each waiting job keeps exactly its own. Probe: `uncapped_waiting_jobs`. Browser `cola`: 100 outlines × 2 maps. |
| **R4** P2 evidence: timing-dependent cancellation test | **Fixed in the test only.** The planner test injects the scheduler's existing `ahora` clock (one unit per reading) and steps slices by hand, so one slice reads a fixed few thousand positions on any machine; the test now also asserts the job is still mid-work and another slice is scheduled before cancelling. Fixture size and assertion are unchanged. This is a test-timing correction, not a behavior fix. | 29/29 on three consecutive runs. |

### R1 managed-allocation inventory (E5 path, including inherited code)

| Allocation | Owner | Charged | Notes |
|---|---|---|---|
| Prepared typed arrays (`x`, `y`, `inicioAnillo`, `inicioParte`, `cajasParte`) | registry / job | `preparado`, before allocation | unchanged |
| Layer visible-part index `Int32Array(partes)` (`capa.js` `initialize`) | each layer | **`capa`, before allocation (new)** | 4 B per part per layer |
| Worker copies of the five arrays (structured clone) | worker client | `copia`, before posting until acknowledged | unchanged |
| Worker scratch `OffscreenCanvas` w×h×4 → `ImageBitmap` (transfer, no copy) → main thread until `close()` | controller | `raster`, one reservation per request | unchanged |
| Blank same-size bitmap that the specification gives an `OffscreenCanvas` after `transferToImageBitmap` | worker | not charged | **now shrunk to 0×0 immediately** instead of left to the collector; implementations may allocate it lazily, not measured |
| Structured-clone serialization during `postMessage`; canvas path state for direct drawing | browser | external, transient | not measurable from the page; disclosed |
| Leaflet's own canvas, DOM, JS objects, descriptors, caller GeoJSON | caller / browser | external | caller GeoJSON references now bounded by R3 |

## 3. Corrected result (replaces the `REPORT.md` headline)

Within the prototype, every allocation in the inventory above that the
prototype makes and owns — prepared arrays, per-layer arrays, worker copies,
and scratch/displayed/in-flight rasters — is now reserved in the shared
64/128 MiB ledger before it is made. The independent audit compares all four
categories with what is actually held (typed-array `byteLength`, per-layer
arrays, bitmap width × height × 4, worker counters). In the reruns below it
found zero mismatches and the per-frame sampler zero violations. This is still
**not** a total-browser-memory bound and not approval of E5: browser-internal
transients, Leaflet's canvas, JS overhead and caller GeoJSON stay external
(caller references are now bounded in count by R3, not in size). The 64 and
128 MiB values remain study budgets.

## 4. Corrected browser evidence

Environment: this cloud container, Chromium 141.0.7390.37 headless
(`/opt/pw-browsers`), Intel Xeon 2.80 GHz × 4, Linux. Developer evidence;
not CI (CI does not run this matrix) and not the developer's earlier Apple M3
runs. Files: `correcciones-2026-10-09/evidencia/`, logs alongside.

| Scenario | Result (corrected) | Historical (`REPORT.md`, reviewed head) |
|---|---|---|
| Matrix, 24 cases (64/128 MiB × DPR 1/2 × 2 viewports × 1/6/12) | 24/24 settled; 0 audit errors; 0 sampler violations | 24/24, 0 violations (without `capa`) |
| 64 MiB matrix maximum (12, 1920×1080, DPR 2) | peak 55.7 MiB; replacement released first | 55.6 MiB |
| 128 MiB, same case | peak 101.3 MiB | 101.2 MiB |
| Two maps, 64 / 128 MiB, DPR 2 | both final; peak 63.8 / 88.7 MiB; `capa` 192,080 B; 27 / 0 temporary refusals | 63.9 / 88.5 MiB; 1,166 / 0 refusals |
| 55 visits/revisits, 64 MiB | 55/55 final; 23 evictions; peak 63.7 MiB | 55/55; 63.7 MiB |
| Resize/DPR change during work | current 2160×1200 bitmap only; 3 obsolete replies; peak 55.7 MiB | 55.6 MiB |
| Burst (20 real inputs + selections) | settled; 13 rasters, 11 obsolete; peak 27.0 MiB | 14 rasters, 12 obsolete |
| Small budgets (4, 16, 1 MiB) | same declared states as before; raster peak 0 | same |
| Worker failures: constructor, sinOffscreen, error, silencio | `sin_trabajador`, nothing pending, all reservations released | same |
| **New** `sinInicio` | `sin_trabajador` after the 1.5 s startup bound; released | not covered |
| **New** `envioCuerpo`, `envioRaster` | `sin_trabajador` first; explicit retry → 6/6 heavy outlines final | not covered |
| **New** `cola`: 100 outlines × 2 maps | jobs at request ≤ 32 per map every round; round 1: 32 admitted, 68 `sin_memoria`/`cola_llena`; all 100 final after 5 explicit renders; 0 audit errors | not covered |
| Reset of one of two maps / teardown | copies counted until acknowledged; map 1 untouched; teardown leaves ledger 0 B | same |

Paint and interaction (rerun, `pintura-e5.mjs`): **8/12 E5-vs-E3 captures
complete-RGBA identical; the same four as the historical Chromium 141 run
differ (unselected six/twelve-outline scenes at DPR 1 and 2)**, with alpha IoU
1.0000 and ±1/±2 px coverage 1.0000 in all twelve and painted-count deltas of
0–2 px. Real clicks 36/36 match E3; inside unavailable outlines nothing of
theirs is hit and their symbol selects them. The disclosed RGBA limitation is
unchanged, and coverage/click agreement is still not pixel identity. The
recorded Chromium 154 result (4/12) is historical and was not rerun: only
Chromium 141 is available here.

Timing: the corrections do not change slice scheduling for 32 or fewer jobs
(every timing scene has at most 12) and do not change what is drawn, so the
three-repetition timing table in `REPORT.md` stays historical. A fresh
one-repetition E5/E3 pass on this machine is in §5; its negative controls
detected every deliberate 150 ms task.

## 5. Verification

| Gate | Result | Where |
|---|---|---|
| Supervisor probes on reviewed `229d424` | all four findings reproduced | `correcciones-2026-10-09/sondas-revisado.jsonl` |
| Adapted probes on the corrected code | all four corrected | `correcciones-2026-10-09/sondas-corregido.jsonl`, `sondas.mjs` |
| Prototype unit tests, Node 22.22.0 | **29/29**, three consecutive runs | `correcciones-2026-10-09/pruebas.log` |
| Negative control: corrected tests on reviewed prototype | 12/12 new tests fail, plus 2 category-shape tests | `correcciones-2026-10-09/pruebas-control-revisado.log` |
| Browser memory scenarios (8 + new `cola`) | all checks passed | `memoria-escenarios.log`, `evidencia/memoria-*.json` |
| Browser 24-case matrix | 24/24 passed | `memoria-matriz.log`, `evidencia/memoria-matriz.json` |
| Browser paint/interaction | 8/12 RGBA (disclosed limitation, exit nonzero as before); interactions passed | `pintura.log`, `evidencia/pintura-e5.json` |
| Timing controls + one repetition E5/E3 (3 scenes) | controls detected every deliberate 150 ms task and excluded the one ending before the marker; E5 longest task 0 ms cold and during input in all scenes (E3: 0 / 59 / 148 ms cold); final-contour after input ≤ 682–783 ms both | `tiempos.log`, `evidencia/tiempos-*.json` |
| Repository JS suite / CI (no application file changed) | see PR #21 description | — |

## 6. Limitations

- Prototype in a report folder; no application integration, no budget or UX
  decision, no renderer API.
- `capa` refusals are explicit and retried only on the next `render()`; under
  a budget full of pinned rasters a layer can show `sin_memoria` until then.
- `cola_llena` is reported with the existing `sin_memoria` state and wording;
  a distinct employee-facing wording would be a product decision.
- The browser-internal transients in the inventory are not measurable from
  the page and stay external, as do OS/GPU reclamation timing and RSS.
- Only Chromium 141 headless on Linux was available for these reruns.

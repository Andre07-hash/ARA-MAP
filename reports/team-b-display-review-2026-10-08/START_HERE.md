# Display investigation review — E1 released; E4 evidence needs correction

Reviewed PR [#16](https://github.com/Andre07-hash/ARA-MAP/pull/16) head **`27022841f29ca1c29ef2589b3e412b9066cbb42a`**, using measured prototype `45117497cf1abc3f1ede48e73a5adf2105a7c51d`. Instruction: `84b2b84a05592b9f31b860e831925990274b481b`, `reports/next-parallel-packets-2026-10-08/TEAM_B_DISPLAY.md`. October 8, 2026.

**Disposition:** useful investigation, with a credible isolated `closePath` bottleneck on the measured Chromium. E1 is worth a small implementation PR under [TEAM_B_E1.md](TEAM_B_E1.md). E4 remains a prototype: its performance/fidelity/resource claims need the corrections below before architecture or implementation acceptance. No application merge, deployment or worker rollout is authorized.

This is not a request to repeat the whole investigation or change the accepted parser. Correct the specific measurement paths, bound the worker's retained geometry, append new evidence and narrow any claim the evidence does not support. Keep the original report/results as historical data.

## F1 — [P2] Phase filtering can omit the synchronous task being measured

In `banco.mjs`, `INSTRUMENTOS.__desde(t0)` selects only long-task entries whose **start** is at or after `t0`. The cold/direct-redraw phases record `t0` inside an already running JavaScript task, then call the renderer synchronously. A task that starts just before `t0` and stalls inside the measured operation is excluded. The summary also needs to wait for observer delivery before finalizing a phase.

This is visible in the committed evidence itself: accepted B-2's `circulo-100k` cold runs record **208.2–273.5 ms of synchronous work**, yet all three have `tareaMaxMs = 0`. Similar omissions occur for E1 and other cases. Thus zero does not currently establish the absence of a 50 ms task.

**Independent browser control:** a 5 ms prelude followed by a measured 150 ms busy period in the same task produced a **155 ms** Long Task. The report's start-time filter returned **no task**; selecting entries overlapping the measurement interval found it. Browser: headless Chrome `154.0.8037.98`, macOS. This is a diagnostic control, not a renderer speed measurement.

**Required correction:** measure well-defined phase intervals and account for overlapping tasks, or schedule measured operations in a way that reliably captures the complete task. Drain/await observer delivery appropriately. Include deliberate long-work negative controls for cold render and direct redraw, including a task that starts before the phase marker; those controls must fail the 50 ms criterion. Report synchronous call time separately. Audit other phase helpers for the same issue. Rerun every comparative timing claim retained in the updated recommendation, or explicitly mark its old numbers unvalidated/withdrawn. Do not replace a missing entry with a claim of zero blocking.

## F2 — [P2] Tolerance-based paint comparison uses the wrong canvas dimensions

`comparar-pintura.mjs` creates masks from the actual canvas but `cobertura()` indexes them using constants **1200 × 640**, the viewport dimensions. Leaflet's padded canvas in the test is **1440 × 768** at DPR 1. The helper therefore uses the wrong row stride and inspects only 768,000 of 1,105,920 pixels. Its ±1/±2 pixel neighborhoods are not actual canvas neighborhoods, and part of the image is omitted entirely.

**Independent confirmation:** the real benchmark page reported `width: 1440`, `height: 768`. The affected loop covers about 69.4% of its pixel entries with incorrect spatial indexing. This invalidates the reported full-image E4 tolerance-coverage conclusion. It does **not** invalidate E1's equal full-canvas digest comparison, which uses all RGBA bytes.

**Required correction:** carry actual width/height with every mask, assert matching dimensions or explicitly align captures, and use that stride for every spatial comparison. Cover DPR 1 and 2 and add a negative control that removes paint in the formerly omitted region, plus a moved-edge control that validates neighborhood distances. Keep nonblank guards. Rerun the E4 coverage/visual conclusions and distinguish full RGBA identity, alpha-mask overlap and tolerance coverage: none alone proves semantic correctness of every polygon/hole. Do not claim 100% coverage from the old helper.

## F3 — [P2] The worker geometry cache is unbounded

The main-thread LRU in `planificador.js` is bounded, but `crearClienteRaster().asegurar()` copies every new prepared geometry to `trabajador-raster.js`, where `cuerpos` retains it. Main-thread LRU eviction never sends the worker's `olvidar` message. `enviados` likewise retains every ID until a complete reset. A sequence of visits can therefore grow worker memory without limit even though the main cache counter remains below 32 MiB.

**Independent module-level reproduction:** pass 45 synthetic prepared buffers of 60,000 positions through the actual cache/client/worker. After all messages are processed:

| Location | Entries | Retained typed-array bytes |
|---|---:|---:|
| Main LRU | 34 | 32,641,632 |
| Worker | 45 | 43,202,160 |

The total is approximately **72.3 MiB before bitmaps and other state**, rather than the main cache's reported 31.1 MiB. This diagnostic uses synthetic prepared arrays and an instrumented worker counter, not a rerun of the full 45-map-visit benchmark. Reset correctly clears the worker after its reset message is processed; that does not bound memory between resets.

**Required correction in the prototype:** coordinate worker eviction with retention rules, bound both cached and active/pinned geometry copies, remove obsolete sent-ID entries so evicted bodies can be resent, and test repeated visits and revisits after eviction. Report main/worker bytes separately and together. Account for queued/in-flight copies; a stale reply being discarded does not mean its queued work was cancelled. Keep reset/teardown proofs and make it clear when cleanup is acknowledged rather than merely queued.

Bitmap memory is a separate, already disclosed issue. The estimated ~35 MB per heavy outline is not an application-wide bound. Before an E4 production packet, return a proposed total map budget covering prepared data, worker copies, in-flight work and bitmaps, with multiple simultaneous heavy outlines and DPR 2. For equal CSS dimensions DPR 2 quadruples bitmap pixel storage. Do not recommend a worker rollout based only on a JavaScript heap graph or a single-outline estimate.

## Additional test portability correction

The first independent E4 behavior run passed **20/21** checks. The pending wording assertion failed. It records initial `preparando`, waits two frames, then requires the text still to say `Preparando contorno…`; the state can already have advanced. A diagnostic repeat, adding only state/wording output, passed **21/21** with `preparando` still present at that assertion. The first run did not record the mismatching text, so a timing race is the code-supported explanation to investigate, not a confirmed renderer defect. Capture and assert wording with its corresponding state, or control the asynchronous boundary in a test-only harness. Do not slow production work or require it to remain pending for a minimum duration to satisfy the test. Return the observed state/wording on failure.

## Independent evidence and limits

- Inspected the report, actual prototype/harness code, stored benchmark data and current GitHub checks.
- Generated all four limit fixtures using exact accepted B-1; their hashes match the submitted manifest. The prototype's **6 Node tests pass**, including the 183-body validation corpus.
- On headless Chrome **154.0.8037.98**, reran the submitted paint comparison for four limit cases at three zooms. **E1's 12 comparisons had equal full-canvas digests and pixel counts.** A separate E1 repeat compared complete SHA-256 digests, instead of the harness's displayed truncated prefixes, with the same result. E4's old tolerance columns are not accepted because of F2, regardless of their printed values.
- Reran E4 behavior checks: **20/21**, then **21/21** on a diagnostic repeat as described above. Original repeated Chromium 141 results remain the team's evidence, not independently reproduced results on that browser.
- Independently reproduced F1's timing omission, F2's dimensions and F3's worker retention. [review-probes.mjs](review-probes.mjs) provides those diagnostics using disposable archives.
- GitHub checks at the reviewed PR head are green: Python/disposable Postgres and JavaScript, run [37810134487](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37810134487). CI does not execute the report's benchmark.
- The supervisor did not repeat the ~40-minute performance matrix, test Safari/Firefox/touch, measure external/GPU allocation, or use company geometry. No universal device-performance guarantee follows from this review.

## Decisions and immediate assignments

1. **E1 first: yes, as a separate draft implementation PR.** Its narrow mechanism and independently matching output justify implementation with the targeted regression requirements in TEAM_B_E1.md. This is not permission to merge or deploy, nor a claim that E1 meets the full responsiveness target.
2. **E4 worker architecture: pending.** Off-main-thread rendering is a reasonable candidate, but this prototype does not yet justify approval. Correct F1–F3 and submit the bounded memory/fallback plan. Falling back to E3 does not preserve the 50 ms target; the report already measures stalls there. Unsupported/failed-worker behavior must be an explicit later choice, not an unnoticed regression.
3. **Pending presentation:** recommend the dotted symbol at the accepted interior point and one employee-facing phrase, **“Cargando contorno…”**, for all transient loading/preparation/drawing states. Internal states may remain distinct for orchestration/tests. Keep **“Contorno no disponible”** and **“Contorno no válido”** distinct from progress. This is the direction for a later E4 packet, not an interface change required in E1 or A's current A-2 work.

**Team B:** append corrected investigation evidence to PR #16 in normal commits; keep corrections in its report folder. Implement E1 separately using the packet, carrying the corrected measurement/paint checks needed to review it. Return both exact heads with separate test evidence. Do not bundle E4 modules into E1 or start full B-3.

**Team A:** continues its A-2/P2 packet at `afd4865892972d8ebd39a31bd5b8ec6c72a74d63`, unchanged. Neither these corrections nor E1 needs A to stop or edit map code. The supervisor owns the later architecture decision and attachment handoff.

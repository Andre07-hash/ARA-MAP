# Team B — bounded-memory E4 investigation

Date: 2026-10-08. Status: **prototype research only; stop for supervisory review**.

> **2026-10-09 correction notice.** Supervisory review `009a724` found that the
> ledger omitted each layer's own array (R1), that synchronous sends and a silent
> startup had no terminal path (R2), that queued jobs were uncapped (R3) and that
> one cancellation test depended on machine speed (R4). The headline result and
> the raw-body paragraph below are **superseded** by
> [CORRECCIONES_2026-10-09.md](CORRECCIONES_2026-10-09.md); the measurements in
> this file are kept unchanged as historical evidence of the reviewed head
> `229d424`.
>
> **Correction 2 (2026-10-09):** the round-1 corrected claim is itself superseded by
> [CORRECCIONES_2_2026-10-09.md](CORRECCIONES_2_2026-10-09.md) (R1a, R2a, R1-test).

This report answers the bounded-memory question from instruction commit
`7a71c93c1c1be68dc5ac992ae6ae801cde1d9cd5`. It does not authorize E4/E5 in
the application, select a production budget, merge, deploy, or change a public
renderer API.

## Exact inputs and branch

| Input | Exact commit |
|---|---|
| Stacked PR base, corrected display investigation | `9da0ab10a344e66099d919f2da15d3a638e7292a` |
| Accepted B-1 parser fixture source | `efc362818ba64618dbfc23556db8678cde525336` |
| Accepted B-2 renderer | `5d8e2dcc125a688dbba38a260d5d7eca88a6d223` |
| Accepted E1 renderer | `eed9a4cb404406b8b261803c38947e8297a5edec` |
| First E5 prototype | `779c4c41f7a76121ed0da517b815875edf8a89b3` |
| Final prototype implementation | `879a0981a043123508b717ab15508a1a336ec5d2` |
| Evidence/timing-driver input head | `a9b6970da824a7b561b84bad6fc53f2d9e8ca30f` |

The remote research branch was fetched before work. Its actual tip was
`a9b6970da824a7b561b84bad6fc53f2d9e8ca30f`, exactly the supervisor-observed
head; there was no discrepancy. The final delivery head and draft PR are
recorded in the PR handback because a commit cannot contain its own hash.

Every changed file is under
`reports/team-b-display-memory-budget-2026-10-08/`. No application, schema,
route, CI, dependency, deployment, or real-data file changed.

## Result

*(Historical, superseded by the 2026-10-09 corrections: this audit did not
count per-layer arrays.)*

**Yes, the prototype enforces a shared 64 or 128 MiB admission limit across
the managed allocations it owns, including transient replacement rasters,
worker copies, preparation, and multiple maps.** Across the 24-case matrix,
two-map competition, resize, reset, failure, burst, and 55-visit runs, the
independent ledger-versus-owned-bytes audit found zero violations. Refused or
oversized work showed an explicit symbol/reason and never allocated past the
budget.

That is not a total-browser-RAM bound and not approval of E5. Caller-owned
GeoJSON, ordinary JS object overhead, Leaflet's own canvas, browser internals,
decoded tiles, and GPU/process allocation are external. Resource ownership is
released synchronously by `close()`/worker termination, but operating-system
or GPU memory reclamation was not measured or promised to be immediate.

## Prototype and admission policy

E5 uses one combined raster per visible map, not two bitmaps per heavy
outline. It preserves renderer order, each outline's own fill/stroke, holes,
multipart geometry, overlap, alpha, selection style, light outlines, XY
symbols, and hit testing. Different terrains are never joined into a single
path, so even-odd fill cannot create cross-terrain holes. A selected outline
appears once in the combined image with its selected style.

The shared ledger has three categories:

- `preparado`: unique prepared typed arrays, owned by cache/layer pins or an
  in-progress preparation reservation;
- `copia`: transferred worker bodies, including queued/pinned copies and
  copies whose `olvidar` release is still awaiting acknowledgement;
- `raster`: scratch/output ownership and displayed or in-flight image bytes,
  calculated as actual device width × height × 4.

Admission happens before allocation/posting. One map may have one raster
request in flight. Preparation has a cap of two jobs that hold memory. Newer
views supersede queued work; obsolete replies are closed and cannot paint or
reacquire memory. Worker copies are pinned as admitted so copies in one image
cannot evict one another. If a replacement cannot coexist with the displayed
image, the displayed image is released first and the request is retried. The
recorded peak therefore includes both old and new images whenever both fit;
at 64 MiB the 4608×2592 replacement deliberately uses the release-first path.

*(Historical, unsupported as written — see R3 in the corrections.)* The raw-body
references not charged as prepared arrays are bounded by the two
preparation jobs: each queued/running job holds its descriptor and the caller's
`geometrias` map. The caller's GeoJSON itself is external and must have an
upstream size/count contract. This prototype did not invent a production file
limit or claim those inputs as managed browser memory.

## Memory measurements

Browser evidence was captured in Chromium 141.0.7390.37. The matrix covers 1,
6, and 12 requested heavy outlines with holes, single rings, many tiny parts,
two light outlines, three XY markers, and a selected outline; DPR 1/2;
1200×640 and 1920×1080 viewports; and 64/128 MiB budgets.

| Budget / case | Peak managed | Settled use | Result |
|---|---:|---:|---|
| 64 MiB, matrix maximum (12, 1920×1080, DPR 2) | 55.6 MiB | 55.6 MiB | all eligible outlines final; replacement released first |
| 128 MiB, same case | 101.2 MiB | 55.6 MiB | old + replacement raster admitted concurrently |
| 64 MiB, two maps competing | 63.9 MiB | 62.0 MiB | both final; 1,166 temporary refusals/retries, no overrun |
| 128 MiB, two maps competing | 88.5 MiB | 65.7 MiB | both final; no refusal |
| 64 MiB, 55 visits/revisits | 63.7 MiB | 62.8 MiB | 55/55 final; 23 bodies/copies evicted |
| 64 MiB, resize/DPR change during work | 55.6 MiB | 20.0 MiB | current 2160×1200 bitmap only; 3 obsolete replies ignored |
| Deliberately small: 4 MiB/DPR1 and 16 MiB/DPR2, 1920×1080 | 3.2 MiB | 3.2 MiB | four heavy outlines `demasiado_grande`; two light direct |
| Deliberately small: 1 MiB, 1200×640 | 0.9 MiB | 0.9 MiB | two `demasiado_grande`, four `sin_memoria`, two light direct |

All 24 matrix cases settled. Final-contour time ranged 123–724 ms in the
recorded one-run capacity matrix; selection reraster ranged 31–175 ms. These
are machine observations, not latency guarantees. The raster dimensions and
actual typed-array `byteLength` values were checked against both main and
worker counters on every audit sample; all `nViolaciones` values are zero.

The 55-visit run retained 32 prepared bodies and 32 matching worker copies,
30,721,536 bytes in each category, plus one 4,423,680-byte raster. Reset of one
of two maps counted copies until acknowledgement, then reduced that map's
prepared/copy/raster ownership to zero; teardown reduced all three categories
to zero.

Evidence: [64 MiB matrix DPR 2](evidencia/memoria-matriz-64mib-dpr2.json),
[128 MiB matrix DPR 2](evidencia/memoria-matriz-128mib-dpr2.json),
[two maps](evidencia/memoria-dos-mapas.json),
[55 visits](evidencia/memoria-visitas.json),
[resize](evidencia/memoria-cambio.json), and
[reset/teardown](evidencia/memoria-reinicio.json).

## Failure, fallback, cancellation, and burst behavior

Constructor failure, absent OffscreenCanvas, worker runtime error, and a
silent worker/watchdog timeout all settled to `sin_trabajador`. Heavy outlines
showed their existing interior-point symbol and a clear unavailable reason;
the light prefix remained direct. The silent-worker watchdog settled after
1.641 s in the recorded run. Every failure released the raster, copy, and
worker ownership it held. The next explicit `render()` creates one fresh
worker; there is no automatic synchronous heavy fallback.

Rapid view/selection changes produced 14 rasters, 12 obsolete responses, one
current image, and zero managed-memory violations. Cancel-before-start did not
run; late-cancel replies were closed. Eviction was exercised while posted and
while forget acknowledgement was pending. A stale reply neither painted nor
re-reserved bytes. Hit testing follows paint: all 36 recorded real clicks
matched E3; unavailable outline interiors did not hit that outline, while its
symbol remained selectable.

Evidence: [failure matrix](evidencia/memoria-fallos.json),
[burst](evidencia/memoria-rafaga.json), and
[paint/interactions](evidencia/pintura-e5.json).

## Paint and interaction result

E5 versus E3 has identical geometry coverage in all recorded views: alpha IoU
1.0000 and both ±1/±2 px directional coverages 1.0000. In Chromium 141, eight
of twelve scene × DPR captures are complete-RGBA identical. The four
non-identical captures are the unselected six/twelve-outline scenes at DPR 1
and 2; their painted-count delta is one or two pixels.

The discrepancy was not hidden or converted into an identity claim. An
exact-head Chromium 154 rerun made the browser sensitivity clearer: only four
of twelve E5/E3 captures were complete-RGBA identical, although all twelve
still had alpha IoU and ±1/±2 px coverage of 1.0000, equal painted counts, and
36/36 matching real clicks. A focused probe found 94 and 134 differing RGBA
pixels in the DPR-1 six/twelve scenes; suppressing point symbols reduced those
to zero. At DPR 2 the ordinary focused captures were identical, but one forced
outline-only redraw differed by three pixels. Layer order, styles, dimensions,
and transforms matched. A synchronous readback barrier also changed the
result, but would introduce the main-thread stall this investigation is meant
to avoid. These results identify transferred-bitmap/canvas compositing and
antialiasing as browser-sensitive, but do not prove one universal mechanism.
The prototype keeps the responsive path and records the complete-RGBA
limitation. This needs product acceptance or a different layer/compositing
design before production integration.

E5 is deliberately different from E4/E1/B-2 in complete RGBA, so those
comparisons remain tolerance/coverage evidence only. No ring or part was
simplified or dropped to fit memory.

Evidence: [Chromium 141 paint](evidencia/pintura-e5.json),
[Chromium 154 exact-head paint](evidencia/pintura-e5-chrome154.json), and
[composition diagnostic](evidencia/diagnostico-composicion.json).

## Responsiveness and time to final contour

The corrected overlap/observer/page-task controls ran first. Deliberate 150 ms
cold and drag tasks were detected; the task ending before the marker was
excluded; direct DevTools-protocol work was recorded only as the known
non-measurement reference. Timing uses three fresh-page repetitions per
implementation and scene, real six-drag/four-wheel input, and reports the
input interval separately from the time until the contour is final.

| Scene | Impl | Cold final median | Worst cold long task | Input worst long task | Post-input final median / worst |
|---|---|---:|---:|---:|---:|
| Six mixed outlines | E5 | 91 ms | 0 ms | 0 ms (0/30 ≥50 ms) | 564 / 602 ms |
| Six mixed outlines | E4 | 91 ms | 0 ms | 0 ms (0/30) | 566 / 813 ms |
| Six mixed outlines | E3 | 61 ms | 0 ms | 0 ms (0/30) | 565 / 602 ms |
| Twelve mixed outlines | E5 | 92 ms | 0 ms | 0 ms (0/30) | 564 / 584 ms |
| Twelve mixed outlines | E4 | 91 ms | 0 ms | 0 ms (0/30) | 566 / 570 ms |
| Twelve mixed outlines | E3 | 89 ms | 0 ms | 0 ms (0/30) | 565 / 602 ms |
| Dense parser-limit case | E5 | 72 ms | 0 ms | 0 ms (0/30) | 566 / 600 ms |
| Dense parser-limit case | E4 | 74 ms | 0 ms | 0 ms (0/30) | 566 / 602 ms |
| Dense parser-limit case | E3 | 68 ms | 0 ms | 0 ms (0/30) | 566 / 569 ms |

Environment: Chromium 154.0.8037.98, Apple M3 (8 cores), macOS, 1200×640,
DPR 1, E5 64 MiB. Every run settled without page errors. The worst Event
Timing entry during input was 64 ms for every row; the worst recorded frame
gap was 50 ms (E5 twelve) and 33.4–33.5 ms for the other rows.

Moving work to the worker is not presented as proof of prompt arrival. The
table reports both the main-thread observations and final-contour latency, and
uses no absolute CI threshold.

Evidence: [three-repeat timing run](evidencia/tiempos-e5-1200x640-dpr1-e5_e4_e3-seis_doce_denso-grande-mas-19999.json).

## Verification

- Prototype unit tests: **17/17 passed**. They include pre-allocation
  reservations, relievers, pins, job cap/cancel, copy acknowledgement,
  eviction during post/forget, early/late cancel, all four worker failures,
  controller retry/no-livelock, and registry/worker membership.
- Memory browser evidence at implementation `879a098…`, recorded by
  `a9b6970…`: all 24 matrix cases and the resize, two-map, small-budget,
  failure, reset, burst, and 55-visit scenarios completed with zero audit
  violations.
- Timing browser gate at the delivery worktree: controls and all 27 runs
  passed in Chromium 154.
- Paint/interaction browser gate at the delivery worktree: interaction and
  coverage checks passed; **8/12 complete-RGBA E5/E3 assertions failed** in
  Chromium 154. This is the disclosed limitation above, not a skipped gate.
  The focused composition probe also exited nonzero because one DPR-2 forced
  outline-only redraw differed by three pixels.
- `./verificar.sh`: passed — **672 Python tests** on Python 3.14.6 with 29
  Postgres-only skips, the complete suite passed on **Python 3.9.6**, and
  **98/98 JavaScript tests** passed.
- Ruff: passed. Mypy: passed with no issues in 43 source files.
- Exact-head GitHub CI: recorded in the draft PR handback after push.

Browser, local developer, and GitHub CI evidence are reported separately.
CI does not execute this full browser/memory matrix.

## Limitations and remaining product decisions

- This is a prototype in a report directory, not application integration.
- 64 and 128 MiB are study configurations, not approved minimums or total RAM
  promises. Product must choose a budget, sharing scope, and degraded-view UX.
- The small complete-RGBA compositing divergence described above remains.
- Only Chromium was available. Safari, Firefox, touch, GPU/backend identity,
  browser process RSS, GPU allocation, and release latency were not tested.
- Caller-owned GeoJSON needs a separate accepted file/body size and count
  contract. The two-job reference bound does not bound the caller's map.
- A selection change waits for reraster; the old image may remain visible
  until replacement unless it must be released to fit.
- Private geometry is shared only inside the explicitly supplied in-page
  budget; this is not authorization to share a ledger or worker across users
  or sessions.
- Production would need an accepted retry control, accessibility/wording UX,
  monitoring, and renderer API contract. None is introduced here.

The bounded-memory prototype is ready for supervisory review with those
limitations. It should not gate the independent local attachment milestone.

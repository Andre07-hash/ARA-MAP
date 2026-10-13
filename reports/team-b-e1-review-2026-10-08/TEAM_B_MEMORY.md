# Team B — bounded-memory E4 investigation (prototype only)

## Deliverable and isolation

Build a **reviewable memory-bounded prototype and report**, not an application renderer. This follows the accepted PR #16 research corrections and PR #19 E1 implementation. It does not approve E4 for integration, freeze its API or select a cloud provider. No Team A input is needed to begin.

Repository: `Andre07-hash/ARA-MAP`. Read this packet and `START_HERE.md` at the supplied instruction SHA with `git show`.

Create `claude/team-b/display-memory-budget` from PR #16's exact head **`9da0ab10a344e66099d919f2da15d3a638e7292a`**, targeting `claude/team-b/display-strategy` while that dependency is unmerged. This explicit stacked draft overrides the normal main-only starting rule. Keep PRs #16 and #19 unchanged. If the dependency has merged, report its real ancestry before selecting its accepted descendant.

Work only under **`reports/team-b-display-memory-budget-2026-10-08/`**. Preserve the previous prototype as an input; place new experiments and their tests here. Use disposable archives for E1 `eed9a4cb404406b8b261803c38947e8297a5edec`, B-2 `5d8e2dcc125a688dbba38a260d5d7eca88a6d223` and B-1 `efc362818ba64618dbfc23556db8678cde525336`. Do not merge/cherry-pick unrelated histories to assemble an application. No changes to `web/`, server code, schema, routes, CI, deployment, app dependencies or real data.

## Question to resolve

Can worker rasterization retain its responsiveness and interaction correctness with **enforced admission limits covering every managed rendering allocation**, including bitmaps, in-flight work and multiple visible maps? The current per-outline bitmap pairs consume ~849 MB for six heavy outlines at DPR 2. A fixed-size viewport calculation does not bound arbitrary windows or multiple maps.

Test **64 MiB and 128 MiB budgets shared across the visible map instances** as study configurations. These are experiment settings, not approved production minimums or a total browser-RAM promise. Make the budget configurable. Report when a configuration cannot display every requested outline and what the user would see; never silently exceed it to make a test look successful. A later product decision will select a policy from measured results.

## Required behavior

1. **Reserve before allocation.** Account for unique prepared arrays in the main cache, active layers and preparation jobs; worker copies (queued, pinned and awaiting drop acknowledgement); raster scratch canvases, completed/in-flight/visible/selected bitmaps and transfer transitions. Do not count only the LRU while active references retain evicted data. Avoid double-counting shared buffers. Cap jobs/requests; newest view supersedes obsolete queued work. Define the peak accounting explicitly, including temporary overlap while replacing the displayed image.
2. **Separate controlled memory from external memory.** Report managed byte totals and their enforcement separately from JS object overhead, caller-owned GeoJSON and browser/GPU memory. Identify every retained raw-body reference and bound its count/size input contract; do not label typed-array-plus-bitmap sums as measured total process RAM. Browser resource release after `close()`/termination need not be instantaneous: be clear about ownership release versus observed process memory.
3. **Prototype the proposed shared raster strategy, or a smaller justified alternative.** A bitmap for several outlines may reduce cost, but it must preserve order, colors, alpha, holes, overlaps, selection and hit testing relative to light outlines/XY markers. A selected outline must not be painted twice in the base and selected images. Combining paths must not create unintended even-odd holes between different terrains. If preserving interleaved layers needs extra buffers, count them before allocating. Return any concrete conflict instead of relaxing the visual/selection contract.
4. **No allocation grows silently with viewport or DPR.** Test actual device dimensions and resize events; enforce the same budget on large windows, DPR changes and two maps simultaneously. Sharing a budget does not authorize sharing private data across users/sessions. Reset/removal must cancel work and release ownership; stale replies may neither paint nor reacquire unreserved memory.
5. **Explicit fallback for the prototype.** For oversized views, exhausted budget, absent worker/OffscreenCanvas, constructor failure, runtime worker error or an unanswered worker job, show the existing interior-point symbol with a clear unavailable/retry reason. Use “Cargando contorno…” only while progress can complete; never remain pending indefinitely. Never substitute discrepant XY or claim a complete contour. For this experiment, do not fall back automatically to synchronous heavy drawing that reintroduces long stalls. This experimental behavior still needs product approval before production.
6. **Review edge lifecycles.** Exercise cache eviction both while a body is posted and while it is still waiting for a forget acknowledgement, unpin/revisit, failed posting, late cancellation, reset during allocation and teardown. The current client's `expulsado` only looks in `vigentes`; make sure a waiting body's cache-membership state cannot become stale in the revised implementation. Test behavior, not just counters.

## Evidence required

- One, six and twelve simultaneous heavy outlines, including overlapping outlines, mixed light/XY layers and a selected heavy outline. Use both multipart and single-large-ring controls; retain holes and tiny-part cases.
- DPR 1 and 2; the existing 1200×640 viewport and a 1920×1080 viewport; resize during work. Two maps must compete under one shared budget in at least one stress scenario. At least 45 visits/revisits and a burst of rapid view/selection changes.
- For every allocation path: peak managed bytes never exceed the chosen budget, including transient/in-flight reservations. An intentionally too-small budget must produce the declared fallback before allocating. Validate counters against actual owned buffer dimensions/byte lengths, plus worker-side counters; do not rely only on the admission counter itself.
- The corrected phase/observer/page-task timing controls must run first. Report time to final visible contour separately from input responsiveness; moving a stall off the main thread does not establish that the outline arrives promptly. Use repetitions for retained performance claims, disclose misses and avoid absolute CI-machine thresholds.
- Compare paint and interactions against accepted E1/B-2 and the corrected E4 prototype. Keep complete RGBA identity separate from tolerance comparisons. Preserve accurate hit testing and layering even when some contours are unavailable. No geometric simplification or dropped ring to fit a budget.
- Available Chromium with real input. Use another already-available engine if practical; otherwise record the gap. No new application dependency or broad browser-install task.

Return a separate draft PR with exact inputs/prototype/head SHAs, admission policy, allocation accounting, failure behavior, measured results, tradeoffs and remaining product decisions. Run `./verificar.sh` (or accurately reported components where zsh is unavailable), the prototype checks and exact-head GitHub CI. Keep local/browser evidence separate from CI.

Stop for supervisory review. No merge, deployment, production E4 integration, new renderer API contract or full B-3 authorization is included. Keep this experiment bounded: if the memory goal cannot preserve layering/interaction, report the smallest concrete incompatibility and alternatives. Do not let this research become a gate for the local attachment milestone.

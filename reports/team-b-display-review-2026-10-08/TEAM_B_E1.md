# Team B — E1 boundary drawing optimization

## Assignment

Implement the narrow E1 change proposed in PR #16, separately from its investigation corrections and E4. Read [START_HERE.md](START_HERE.md) first. No Team A input, cloud provider or product choice is needed for this draft implementation.

Fetch and create **`claude/team-b/boundary-path-drawing`** from accepted B-2 **`5d8e2dcc125a688dbba38a260d5d7eca88a6d223`**, PR #11. Target `claude/team-b/map-boundaries` while B-2 remains unmerged. This explicit stacked dependency overrides the normal main-only branch rule. Keep PR #11 and every other accepted branch unchanged. If main has since absorbed B-2, use that ancestry and report it. Read instructions with `git show`; do not develop on the supervisor branch.

## Scope

- B-owned `web/components/map/MapCanvas.js`, dedicated JS/browser regression/measurement files, small fictional generators/fixtures, and `reports/team-b-boundary-path-drawing-2026-10-08/`.
- Extract only the per-boundary Canvas polygon path optimization: close each ring with a line back to its first point instead of repeated `closePath()` calls, retaining the existing fill/stroke/selection pipeline.
- Do not copy the large prototype MapCanvas replacement, change vendored Leaflet globally, modify XY markers or other map layers, or add workers/caches/pending states/interface changes. No parser, body-validation, storage, auth, schema, app-shell, route, CI or deployment changes.
- Preserve compatibility if the active renderer cannot use the optimized Canvas path; do not assume private Canvas fields exist on every Leaflet renderer. Use the ordinary drawing path in unsupported cases. Keep Leaflet 1.9.4 assumptions explicit and narrowly contained.

## Acceptance

1. Existing B-2 helper and real-browser interaction checks still pass: holes, multipart selection, geometry priority, missing/invalid body behavior, scale results, and XY compatibility.
2. Compare **complete RGBA buffers**, with real canvas dimensions, after paint; reject blank captures. Include small normal fixtures and the four deterministic parser-limit cases from PR #16. Record baseline/implementation head, canvas dimensions, paint counts and full hashes.
3. Cover the supported stroke styles actually used by this renderer: normal/selected, solid/dashed (`dashFor`), ring-closing seams and clipped viewport edges, plus holes and several parts. Check DPR 1 and 2. Do not infer that `lineTo` and `closePath` have universally identical stroke semantics for arbitrary caps/joins/dashes. If a supported case differs, retain the original drawing path for that case or return the concrete incompatibility; do not relax the comparison to hide it.
4. Keep geometry/validation/coordinates and hit testing unchanged. No new approximation, omitted ring, or change to terrain identity. Browser screenshots supplement, rather than replace, numeric paint checks.
5. Measure the targeted multi-ring construction/redraw before and after using corrected timing instrumentation from F1. Include a normal/XY control and single-large-ring control. Separate browser-call microbenchmark evidence from whole-renderer timing; record browser/machine and repetitions. Show the expected improvement on an affected environment and disclose if a newer browser already fixes the bottleneck. Do not claim E1 alone meets the 50 ms target or make an absolute timing assertion on an unspecified CI machine.
6. Test on the available Chromium; add another supported engine if the environment already supports it, otherwise record the gap. Do not install a new application dependency to satisfy browser testing. Unsupported browser evidence is not automatically a reason to stall this small draft.

Run `./verificar.sh`, applicable existing checks, the relevant B-2 browser checks and targeted comparisons, then obtain green GitHub checks at the returned head. Keep benchmark results separate from CI claims. If zsh is unavailable, report component commands and limitations accurately.

Return the separate draft PR, exact instruction/main/B-2/head SHAs, minimal diff summary, style/render-fallback behavior, test evidence and remaining responsiveness limitation. PR #16's corrected report/worker prototype stays on its own investigation branch and is returned separately. Stop for supervisory review. No merge, deployment, E4 implementation or full B-3 authorization is included.

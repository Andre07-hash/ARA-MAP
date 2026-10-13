# Team B — corrected investigation and E1 implementation review

October 8, 2026. Instruction reviewed: `75611396a1d085372d5a32cd0c76866d99b3d930`.

| Deliverable | Exact head | Disposition |
|---|---|---|
| [PR #16](https://github.com/Andre07-hash/ARA-MAP/pull/16), investigation corrections | `9da0ab10a344e66099d919f2da15d3a638e7292a`; measured code `14254d620dbe5c0727dc075241fa421bd64637bb` | Accept the corrected investigation as research evidence, within the limits below. E4 is not approved for application integration. |
| [PR #19](https://github.com/Andre07-hash/ARA-MAP/pull/19), E1 | `eed9a4cb404406b8b261803c38947e8297a5edec`; implementation `496233e3c86fac40981f23671633c4fbbd157b97` | **Accepted as the isolated implementation**, stacked on B-2 `5d8e2dcc125a688dbba38a260d5d7eca88a6d223`. No blocking E1 finding in this review. |

Acceptance is a supervisory implementation decision, not permission to merge or deploy. Preserve both reviewed branches and their history.

## Decision on E1's change of mechanism

**Accept `Path2D` constructed from SVG path data (`M…L…Z`) in place of the packet's literal `lineTo(first)`.** The goal was to eliminate the expensive repeated path closing while preserving the actual drawing. The broader seam tests found that the initial line-closing proposal did not preserve complete RGBA output. Choosing a different mechanism after detecting that difference satisfies the goal better than weakening the comparison.

The changed application file is only `web/components/map/MapCanvas.js`. It reuses Leaflet's projected/clipped/smoothed parts and its fill/stroke pipeline; it does not replace body validation, coordinates, hit testing or XY markers. The optimization is limited to Leaflet 1.9.4 Canvas with Path2D and integer positions. The tested alternative paths retain Leaflet's drawing. No E4 worker, cache, pending state or interface expansion entered PR #19.

The earlier “E1 is pixel-identical” conclusion applied only to the tested views and was overgeneralized. The supervisor's earlier 12 captures also lacked the seam coverage that exposed the problem. Those historical results do not establish fidelity of `lineTo(first)` in general. PR #19's actual replacement was independently checked over the expanded matrix below.

## Corrections to the investigation

- **F1, measurement:** phase overlap, observer draining and scheduling measured work in page tasks address the missed-task paths. The same phase helpers now run explicit negative controls. The old performance tables remain historical, superseded by §11. No claim of universally zero blocking is accepted.
- **F2, paint masks:** masks carry actual dimensions, mismatched dimensions are rejected and spatial comparisons use the actual stride. The new controls cover previously omitted pixels, shifts and row boundaries. RGBA identity, alpha overlap and tolerance coverage are separate claims. E4 remains a different rendering from Leaflet; coverage within a pixel is not complete pixel identity or proof of every hole/overlap interaction.
- **F3, geometry retention:** the worker has its own byte budget, queued copies count until acknowledgement, and pins/evictions/revisits/reset are exercised. The original 45-body reproducer now retains **34 worker bodies / 32,641,632 bytes**, matching the main cache, rather than 45 / 43,202,160. Combined prepared-array retention is **65,283,264 bytes**, not a total-browser-memory measurement.
- **Async wording:** the test holds the scheduling boundary only in the harness and reads state/wording together. The independent corrected E4 behavior run passed 26/26. No minimum production delay is required to make the test pass.

These dispositions accept the corrected research and close the original reproductions. They do not certify that every prototype resource lifecycle is ready for production. Memory accounting, bitmap admission and worker failure behavior remain the next bounded investigation.

## Independent checks at the exact heads

Environment: macOS, Apple M3, headless Chrome **154.0.8037.98**. The GPU/software backend was not established; do not equate this environment with Team B's Chromium 141 software-rendering machine.

- Generated all four limit cases from accepted B-1 `efc362818ba64618dbfc23556db8678cde525336`; all hashes match the submitted manifest.
- **E1: 252/252 complete-RGBA SHA-256 comparisons equal to accepted B-2**, DPR 1 and 2, 1440×768 and 2880×1536 canvases. Normal, dashed, selected, seam, clipped, multipart, hole, XY and limit-case views passed. The full capture records are in [evidencia/contornos-trazo.json](evidencia/contornos-trazo.json).
- E1 mechanism checks passed: no repeated context `closePath` on the optimized path; version, missing-Path2D and fractional-position alternatives draw the baseline bytes; SVG uses the SVG drawing path.
- **B-2's 20 browser checks passed** against E1, including real mouse interactions and the painted XY comparison.
- **PR #16's 22 Node tests passed**, including its 183-body validation corpus, worker memory tests and paint-helper controls. **E4 behavior: 26/26 passed** in one independent run, not a repeat of the team's 10-run series.
- The original supervisory probe independently reproduced the corrected worker retention/reset and the 155 ms overlap control. Worker reset returned zero entries/bytes.
- The corrected investigation's seven timing controls passed: six deliberate long phases were detected and the task ending before the marker was excluded. This was a fixture smoke run, not the full six-renderer performance matrix.
- E1 timing was checked separately with one repetition at DPR 1, the fixture/XY controls and the two affected large cases. Its ten deliberate-long-work controls passed. The table below is a diagnostic repeat, not a multi-run capacity guarantee.
- `./verificar.sh` passed in the E1 disposable archive: **672 Python tests, 29 Postgres-only skips**, full Python **3.9.6** suite and **120 JavaScript tests**. No Python changed in E1; no separate local Postgres suite was repeated for these map changes.
- Current GitHub checks are green on both exact heads: PR #16 run [37842171854](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37842171854); PR #19 run [37841753100](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37841753100). CI does not execute the browser matrix.

| Case, single independent run | B-2 → E1 cold longest task | B-2 → E1 worst synchronous direct redraw |
|---|---:|---:|
| Large part + 19,999 small | 802 → 73 ms | 428.3 → 34.1 ms |
| Dense large + 19,999 | 1601 → 76 ms | 824.1 → 33.2 ms |

The eight E1 direct redraws in that run had no reported task ≥50 ms, while the cold loads still exceeded 50 ms. Team B's slower machine also has long redraws. **E1 is useful on newer Chrome too; it does not fulfill a universal 50 ms target.** The independent timing JSON is retained separately from the team's repeated measurements.

The corrected E4 browser paint comparison also completed: **32 views and their negative controls**, DPR 1/2, with every B-2 painted pixel within 1 px of E4 in these captures. The reverse direction and RGBA/alpha results are retained in `evidencia/e4-paint.json`; this is not pixel identity. The previously omitted region contained paint in 30 of the 32 controls. No Safari, Firefox, touch, real company geometry, GPU allocation or hosted application acceptance was tested. The full 25-minute investigation matrix was not rerun.

## What remains open and who works next

The reported six-heavy-outline E4 bitmap retention at DPR 2 is **849.3 MB**, before other browser resources. This is a disclosed prototype limitation, not acceptable evidence of a bounded production renderer. The proposed ~85/138 MB totals depend on a specific viewport and omit an implemented global admission policy; they are a proposal, not an accepted product budget.

**Team B may start the separate prototype-only memory packet in [TEAM_B_MEMORY.md](TEAM_B_MEMORY.md)**. This tests the concrete remaining uncertainty without introducing E4 into the app. Keep PR #19 stable. This research is not a prerequisite for the local attachment milestone and must not expand into a general map rewrite.

**Team A continues its PR #17 corrections** under `0a89e1c0608c4ff19887712bddee398264edf1b1`, `reports/team-a-a2-review-2026-10-08/START_HERE.md`; its current reviewed head remains `1e27715afc74cfe342b1c209d2881c4f05ffef02`. No A input is needed for this B packet. Full B-3 still needs the accepted corrected P2 head and consolidated lifecycle/API packet; this display review does not silently freeze either.

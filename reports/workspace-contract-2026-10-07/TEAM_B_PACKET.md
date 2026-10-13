# Team B — B-2 boundary renderer

## Assignment

Implement **B-2 only**, following [the shared contract](SHARED_CONTRACT.md), especially section 4 and its [example](examples/boundary-terrain.json). The owner approved work bases and the shared interface now permits this packet to start alongside Team A's A-1. Earlier “B-2 pending” instructions are superseded for this scoped work.

B-1 is accepted at PR #9 head `efc362818ba64618dbfc23556db8678cde525336`. Preserve that branch and its accepted parser. Start `claude/team-b/map-boundaries` from freshly fetched main (at issue `09452fd26d38319567dce28a89db100ea61c739a`). Read the instruction commit using `git show`. No need to merge the documentation or parser PR to build a JS renderer against fixed fictional geometry outputs. If regenerating fixtures with B-1, use its exact code in an isolated checkout/archive and record that provenance; never import report experiments into production.

## Owned scope

- New `web/lib/geometria.js`: location/descriptor helpers following the shared interface, reusing the existing X/Y validation. No second coordinate validator and no changes to stored lat/lon.
- `web/components/map/MapCanvas.js`: add polygon/multipart layers alongside the existing circle path. Preserve the factory, current methods, callback identity and XY-only behavior. Accept optional `options.geometrias` as specified.
- Map-specific styles and narrowly required additions to `web/lib/geo.js` for combined symbols/bounds; preserve existing XY functions and tests. Prefer a wrapper/helper over rewriting established XY behavior.
- Feature-owned JS tests, fictional geometry fixtures, and a browser harness that instantiates the real `createMapCanvas` with the repository's vendored Leaflet. No grid implementation is required; a small test list can show terrain selection by ID.

Do not edit A's `web/lib/inventario.js`, app shell, API/store/router, schema, authorization, record DTO producer or CI. Do not implement storage, attachment APIs/widgets, a geometry fetch endpoint or snapshot persistence. Supply exact requests for those A-owned hooks in your report. No new frontend framework/build step/dependency or public data access.

## Required behavior

1. Active usable boundary takes priority over X/Y. Draw actual shells, holes and all parts; one terrain retains one logical selection regardless of part count. Blank X/Y and missing declared area must not prevent a valid boundary from displaying or fitting.
2. At distant zoom, use the geometry's validated interior point for a recognizable symbol. Select an evidence-based handover to a clickable outline at parcel zoom. Do not represent a known polygon as a circle scaled from declared area. Coordinate order stays GeoJSON `[lon,lat]`, converted explicitly only for Leaflet point APIs.
3. `select`, `fitTo`, `zoomToScale`, scale reporting and coincident symbol offsets work with mixed boundary/XY data. Boundary fit includes the whole multipart extent. XY-only return values/behavior stay compatible. Document additive boundary results needed by the caller.
4. Missing/loading geometry body with a valid active descriptor uses a distinctly indicated boundary-unavailable symbol at its interior point. It does not fabricate an outline or jump to different X/Y. With no active usable descriptor, valid X/Y retains today's fallback; otherwise the terrain remains unplaced.
5. Replacement failure/pending state does not remove the previous active descriptor/body. Changing filters removes excluded layers; stale geometry entries in the supplied map never render terrains that are no longer in the supplied list. Clear removed selection/gestures safely. Session/grant invalidation will be A's integration responsibility, and B must expose a reliable clear/reset path using the existing surface where possible.
6. Labels/tooltips must escape supplied names/content. Do not display or fetch KML HTML/resources. Invalid render input must be handled without crashing the existing XY layer or treating invalid data as a validated footprint.

## Evidence and completion

- Focused tests: boundary-only; XY-only unchanged; neither; invalid/unusable descriptor; missing body; both locations disagree without overwriting XY; holes; multipart selection; mixed fit bounds; coincident low-zoom symbols; filtering and rerender cleanup; previous active layout retained during a failed replacement.
- Browser interaction with the real renderer: click a polygon part and verify the same terrain ID is selected in the test list; select from the list and fit/highlight the boundary; inspect hole fill, multipart extent and a legacy XY marker. Use actual mouse interaction, not only a programmatic Leaflet `fire('click')`. Screenshots supplement assertions, not replace them. Record browser/runtime, fixture source and commit.
- Measure representative mixed sets and one accepted-parser-limit fixture (up to 100,000 positions) for rendering time, interaction responsiveness and memory. Record any practical rendering limit rather than claiming all parser-accepted files are already suitable for an interactive browser. Do not change B-1's parser budget to hide a renderer limit or simplify a boundary silently.
- Run existing map JS tests, repository verification and appropriate new tests. Keep local/offline harness results separate from the later hosted employee workflow. No real company geometry is committed.

Return a draft PR, exact instruction/baseline/head, evidence and a short A-integration checklist: DTO-to-renderer adaptation, `ubicado`/unplaced behavior, geometry body loading/invalidation, new result handling, and app test-hook changes. This packet may be accepted as renderer foundation; it does not claim attachments, permissions, or the full table+map workflow are integrated. Return for supervisory review before B-3.

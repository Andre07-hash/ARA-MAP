# Supervisor review of Team B preparation and next packet

Reviewed: October 7, 2026. Repository: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP).

## Decision

**Preparation accepted, with corrections below. Authorize B-1 only: the isolated KMZ parser and its tests.** This lets B work alongside A without committing either team to an unfinished database, permission, storage, or map DTO contract. B-2 and later production integration await the consolidated contract. This is a bounded update to the preparation-first handoff, not approval of every proposal in B's report.

Reviewed [PR #8](https://github.com/Andre07-hash/ARA-MAP/pull/8) at `e93649c460f4b69d1540770a474fadb169721640`, based on application commit `09452fd3` and instruction commit `bbd640dec00c055b43454f61b35861c38063b550`. The report and disposable experiments change no application code. The disclosed account-assigned branch name is acceptable; do not rename or rewrite shared history merely to satisfy the suggested naming pattern. PR #8 need not merge before B-1 starts.

The master plan and ownership split remain in force. A owns shared migrations, authorization, routes, inventory adapters, grid integration, and the application shell. B owns its parser, attachment modules, and eventual map extension. Connected Excel remains parked.

## Evidence and findings

I independently reran the 14 parser tests and seven location-prototype tests in an isolated archive of the exact PR head: all passed. GitHub Actions also reports success for Python/disposable Postgres and JavaScript at that head. These establish preparation evidence, not real-file, storage, hosted, or employee-workflow acceptance. The report's separate local packaging-test failure is disclosed; the PR changes only report files.

Four additional fictional-input probes against `experiment/kmz_experiment.py` exposed production gaps:

| Probe | Observed result | Required result before use in the app |
|---|---|---|
| Four copies of the same coordinate | `listo`, usable, area 0 | Invalid boundary; no usable geometry |
| Self-intersecting bow-tie ring | `listo`, usable, area 0 | Invalid boundary; no usable geometry |
| Candidate selection `[0, 0]` | Same polygon twice; area doubled | Reject duplicate selections |
| Candidate selection `[0.0]` | Unhandled `TypeError` | Structured invalid-selection result |

The repeated coordinate was `-100.4,20.6`. The bow-tie sequence was `-100.4,20.6 -100.396,20.603 -100.4,20.603 -100.396,20.6 -100.4,20.6`. Both were packaged as a single polygon in `doc.kml`. Selection probes used the report's simple rectangle. These are gaps in a disposable experiment, not regressions in the running application.

Two research corrections matter:

- Do not treat the name `doc.kml` as proof that other KML documents are irrelevant. Google's guidance recommends one KML per archive and warns that multiple KML documents are ambiguous. B-1 should return a clear unsupported/ambiguous-package result when there is more than one KML, including duplicate entry names. A document chooser can be considered later. [Google KMZ guidance](https://developers.google.com/kml/documentation/kmzarchives)
- Vercel Blob does have an official Python SDK, including private-storage support. Revise the comparison before choosing a provider; Python support alone does not establish compatibility with this application's Python 3.9 floor, browser delivery, and dependency policy. S3-compatible storage remains a candidate, not a selected service. Do not choose handwritten signing just because it has fewer dependencies. [Vercel private storage](https://vercel.com/docs/vercel-blob/private-storage)

## B-1: work authorized now

Start from freshly fetched `origin/main` on `claude/team-b/kmz-parser`, or disclose an account-mandated branch. Read the instruction commit supplied with this packet using `git show`; do not switch to the supervisor's branch to develop. Read the baseline's `AGENTS.md` and `CLAUDE.md` as well.

Deliver `server/kmz.py`, fictional fixtures under `tests/fixtures/kmz/`, focused parser tests under `tests/`, and a short report in a new dated folder. No production imports of the disposable experiment. This packet adds a tested module without wiring it into the application. No SQL, migrations, routes, roles, storage credentials/provider implementation, map renderer, grid, or deployment edits.

### Minimal parser contract

Input is bounded KMZ bytes and an optional explicit candidate selection. No database, network, filesystem extraction, UI, or identity lookup is needed. Parse the contained KML internally; accepting bare `.kml` in the employee upload UI is outside this packet.

Output has a stable result state, Spanish user-facing error/warning messages with machine-readable codes, candidate descriptions when a choice is needed, and normalized geometry only for a successful validated selection. Keep these processing states separate from future attachment persistence states.

Geometry is GeoJSON `MultiPolygon` with positions `[longitude, latitude]`; bounds are `[west, south, east, north]`. Any representative symbol point must have an explicitly documented coordinate order and lie inside a filled polygon, outside its holes. ARA's existing X/Y fields are untouched. Calculated area, if included, is approximate, separately labeled, and never substitutes for Superficie or HA. The parser does not mint database IDs or decide which attachment version is active.

Support one polygon, multipart geometry, and holes. Multiple polygon-bearing placemarks require an explicit selection before a final boundary is returned. Selected multipart geometry still represents one terrain; do not create terrain records. Ignore supported-to-ignore non-boundary elements with a warning, retain that distinction from a file containing no usable boundary, and never fetch external links or resources.

### Required checks

1. Retain the useful fictional cases from the preparation report. Add the four probes above as regression tests. Candidate indices must be distinct integers (not booleans, floats, or strings), in range, and nonempty when supplied. A bad selection must never crash the service.
2. Validate distinct vertices, nonzero area, self-intersections, and the relationship of holes to shells before labeling geometry usable. Do not silently repair, reorder coordinates, or activate invalid shapes. An unsupported shape must produce a clear result. If robust validation requires a dependency, submit the narrowly scoped proposal and continue the independent work; do not quietly add a package or claim full validation from a few examples.
3. Reject ambiguous multi-KML archives. Convert malformed, truncated, encrypted, unsupported-compression, and corrupt ZIP/XML input into controlled results. Never extract archive paths to disk. Keep DTD/entities and external fetching disabled.
4. Enforce bounds while reading/parsing, including bytes, depth, entries, candidates and vertices. Avoid allocating the full coordinate list before enforcing its vertex limit. Test actual limit boundaries, not just one compressed-padding example. Validation complexity must be compatible with the accepted vertex budget.
5. Preserve the existing Mexico location extent as a separate usability result. Out-of-scope coordinates must not be silently corrected. Geometry validity and geographic eligibility are different results.
6. Measure elapsed time, peak memory, and serialized result size on representative synthetic files near the proposed limits. Byte caps alone do not prove completion within the configured function duration. Report the machine/runtime and limits of these measurements; hosted and real-file acceptance remain later steps.
7. Run focused tests, Python 3.9 compatibility, applicable lint/type checks, and the repository verification command before pushing. If the assigned environment lacks `zsh`, run and report the component commands and limitations explicitly. Open a small draft PR and report its exact head, baseline, instruction SHA, tests, and unresolved items.

The current JSON examples are proposals. B-1 may clarify its pure parser result without freezing A's API names. Provide example outputs so the supervisor can reconcile the parser with the shared contract.

## Contract corrections before B-2/B-3 integration

These are requirements for consolidation with A, not extra B-1 implementation work.

| Area | Required clarification |
|---|---|
| Last usable layout | A new upload that parses but is geographically unusable must not accidentally displace the prior usable layout. Separate uploaded-file version from active layout if necessary. Pending, failed, ambiguous, and invalid replacements preserve the previous active boundary. |
| Concurrent replacements | Define attachment-level revision/compare-and-set behavior. An older upload completing late must not overwrite a newer accepted choice or resurrect a retired file. Completion, selection, cancel, and retire need replay-safe terminal transitions. Test these races on both databases. |
| Immutable evidence | Upload state may change while processing, but finalized bytes and geometry must be immutable. Verify the stored content and prevent a still-valid upload grant from overwriting the object after validation. Snapshot references must bind exact finalized versions. |
| Audit | A separate attachment event stream is a reasonable proposal. If terrain versions do not change on file edits, attachments need their own concurrency token and summary refresh mechanism. A finalizes this with B. |
| Geometry transport | Authorize every requested geometry ID, including mixed authorized/unauthorized batches and snapshot reads. Bound responses: a 200,000-vertex result can exceed the function response limit even if upload bypasses it. Agree pagination/segmentation or a private delivery mechanism before integration. [Function limits](https://vercel.com/docs/functions/limitations) |
| Processing lifecycle | A client polling `procesando` does not create a durable worker. Use a measured, bounded synchronous path initially, or explicitly design durable execution/recovery before promising background processing. |
| Upload widgets | Track each upload by job/version ID as well as terrain and column: multiple PDFs in one cell must not replace each other's progress. Abort/clear private state at logout and ignore late callbacks from an old session. |
| Local limits | The proposed 50 MB PDF limit exceeds the reported local 25 MB body limit. Choose and test a consistent transport/limit policy; do not globally raise request limits incidentally. |
| Map adapter | Resolve `ubicacion.geometria` in the DTO versus `geometria` in the prototype. Document GeoJSON bounds versus Leaflet bounds without ambiguous coordinate-order notes. Extend selection, fit/zoom and coincident symbols for boundary-only terrains. |

A owns the actual next migration number from the accepted main history. Parked PR #6's schema version is a future reconciliation issue; do not reserve or skip migrations blindly, and do not merge the Excel branch to obtain its number.

## Decisions that can wait

Multiple PDFs and one active layout per terrain are useful working assumptions. Final limits, provider, removal permissions, and any additional custom file-column types await consolidation. Upload/replace/choose fit the intended operator editing workflow; destructive removal privileges require the role decision. No new public file/geometry access is authorized. Boundary-only terrains must work internally; public publication policy is a separate decision, preserving existing public behavior.

Real company KMZ samples remain necessary before geography acceptance and should be shared privately. Bare KML uploads and rendering internal roads/lot lines are possible extensions, not additions to the owner's current requirements.

At this review, no Team A preparation PR was visible among the open PRs. A continues its preparation in parallel. After that report is reviewed, the supervisor will publish one shared contract and release B-2 plus the appropriate A integration work. B-1 does not depend on a storage account or the unfinished table.

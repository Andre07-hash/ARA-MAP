# ARA Map — current delivery status and remaining execution plan

October 8, 2026. GitHub-based supervisory report for the owner. **Planning proposal, not a new implementation assignment, merge approval or deployment authorization.** Current packets remain in effect while the owner reviews this plan.

## Executive assessment

We have built much of the foundation, but the employee-facing workflow is still missing. The schema, role/access backend, KMZ parser, standalone byte storage and map renderer exist in separate branches. That is valuable progress; it is not yet an integrated editable master table with working attachments and one-action filtered maps.

My proposed remaining plan is **12 new instruction packets: 6 for Team A and 6 for Team B, in 6 overlapping waves**. The already-assigned A-2 corrections and B memory investigation are not counted again. Supervisory reviews and normal correction requests are checkpoints within packets, not additional feature packets. One packet can produce several small PRs; this is not a promise of exactly 12 PRs, chat messages or development sessions.

The next priority is the first real table → file → map workflow. Map research must not keep that milestone waiting. We will review Team B's current memory work when its final head/report arrive, then use or defer that result in a defined map implementation packet instead of starting an indefinite sequence of display experiments.

## 1. What GitHub currently contains

`main` is still **`09452fd26d38319567dce28a89db100ea61c739a`**. The feature PRs below remain draft/unmerged. Supervisory acceptance of a component is different from integrating or deploying it.

| Area | Evidence / exact state | What it means |
|---|---|---|
| A: schema foundation | [#14](https://github.com/Andre07-hash/ARA-MAP/pull/14), `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`, accepted | Work bases, grants, roles and custom-column storage are defined. No employee table is provided by this schema alone. |
| A: attachment schema | [#15](https://github.com/Andre07-hash/ARA-MAP/pull/15), `edf9bcd1dc51e74a627d54d5ce01d37113206055`, accepted | PDF/KMZ versions, attempts, geometries and audit have storage constraints. The upload workflow does not yet exist. |
| A: roles and transaction authorization | [#17](https://github.com/Andre07-hash/ARA-MAP/pull/17), corrected head **`5d0844cfd678c2f7ec55ddb4b364275482d1a801`** | Corrections are submitted and both CI jobs are green, run [37855959400](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37855959400). The correction diff covers the requested busy-response handling and release-note clarification. Final supervisory exact-head re-review is still a closeout step; this planning report does not claim to have rerun that corrected suite. |
| B: KMZ parser | [#9](https://github.com/Andre07-hash/ARA-MAP/pull/9), `efc362818ba64618dbfc23556db8678cde525336`, accepted | Standalone parsing/validation exists. It is not yet wired to employee uploads. |
| B: boundary renderer | [#11](https://github.com/Andre07-hash/ARA-MAP/pull/11), `5d8e2dcc125a688dbba38a260d5d7eca88a6d223`, accepted | KMZ-first rendering, holes/multipart and existing XY behavior are implemented against supplied bodies. Live authenticated geometry loading is still missing. |
| B: storage core | [#13](https://github.com/Andre07-hash/ARA-MAP/pull/13), `c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53`, accepted | Local/fake byte-storage primitives exist. This is not durable cloud storage or an attachment API. |
| B: isolated drawing optimization | [#19](https://github.com/Andre07-hash/ARA-MAP/pull/19), `eed9a4cb404406b8b261803c38947e8297a5edec`, accepted | E1 preserves the tested drawing while removing the repeated path-closing bottleneck. It does not guarantee every view stays below 50 ms. |
| B: display research | [#16](https://github.com/Andre07-hash/ARA-MAP/pull/16), `9da0ab10a344e66099d919f2da15d3a638e7292a`, accepted as research | Corrected evidence is useful. Its worker prototype is not application-ready; bitmap allocation still needed a bound. |
| B: current memory task | `claude/team-b/display-memory-budget`, visible head **`a9b6970da824a7b561b84bad6fc53f2d9e8ca30f`** | New prototype, tests and browser evidence are pushed. No final `REPORT.md` or draft PR was visible at this check. `HANDOFF.md` explicitly calls itself working notes and includes earlier, stale state; do not treat it as final acceptance evidence. Task still in progress. |
| Attachment design | [#12](https://github.com/Andre07-hash/ARA-MAP/pull/12), `28bf0dbbf718571e35d501a7810d7e7d882ee3dd` | Refined proposal exists, but the complete lifecycle/API contract and applicable D1–D5 decisions have not been consolidated into the B-3 implementation packet. |
| Hosted adapter/Preview | [#4](https://github.com/Andre07-hash/ARA-MAP/pull/4), `077b4e0f1c184b2c2ef6d1c63ebb80381a113316` | Python/JS CI green; Vercel status remains failure. Its report says the Git-triggered deployment was blocked and hosted behavior remains unverified. It is a separate release prerequisite. |
| Excel | [#6](https://github.com/Andre07-hash/ARA-MAP/pull/6), parked | Preserve it. It is not a dependency of the interactive-table release. |

Team B's working notes still label the accepted storage core as awaiting review; that is a stale handoff label. The exact-head supervisory acceptance remains authoritative. [#18](https://github.com/Andre07-hash/ARA-MAP/pull/18) is developer verification documentation, not additional product functionality.

This report checks GitHub heads/status, reports, plan/contract and A's correction diff. It does not accept B's unfinished prototype or turn CI success into hosted/product acceptance.

## 2. What is actually missing

1. **A combined, tested application baseline.** Reviewed parts must be assembled in dependency order, with a designated integrator and combined checks. Separate green PRs are insufficient.
2. **Complete master-record APIs.** Scoped create/list/edit, all optional business fields, current-base custom fields, archive/restore, transfer, audit/history redaction, SQL filtering/sorting/counts and bounded pagination. A-2 explicitly did not implement A-3.
3. **The employee interface.** Role-aware navigation, assigned bases, the editable master grid, simple blank-record creation, keyboard editing/save feedback/conflicts, custom-column management and admin base/grant/transfer controls. The current screen still calls admin-only legacy routes and is not usable by operators.
4. **Attachment lifecycle and transport.** Upload sessions, verification/finalization, immutable versions, retry/cancel/replacement/retirement, KMZ attempts/selection/activation, idempotency, race-safe authorization, audit, download and bounded geometry delivery. The schema and byte store are only prerequisites.
5. **Attachment controls and map integration.** File cells/details, progress/errors/retry, chosen-layout UI, summary invalidation, real geometry loading/cancellation/cache clearing, KMZ-aware located/unplaced filters and table/map selection.
6. **One-action filtered views and saved maps.** Persistent filter definitions/membership semantics, create/open/rename, synchronized table/map, frozen snapshots with immutable geometry/file-version references, and legacy-map compatibility.
7. **Production map behavior at the large-file limits.** Integrate a reviewed bounded strategy or an explicitly accepted fallback, including multi-map/DPR/resize/failure behavior. Completing a research report alone does not implement this.
8. **Durable private cloud files and a working hosted candidate.** Provider choice, authorized isolated storage, adapter/upload flow, access-expiry tests, cleanup/recovery, exact-commit Preview and the hosted API fix.
9. **Migration, administrator setup and pilot acceptance.** Identify approved real source records, preserve provenance/duplicates, establish named administrators/grants, rehearse database-plus-file recovery, test representative company KMZs privately, and verify the end-to-end hosted workflow before rollout.

The original fourteen core columns remain mandatory to *exist*, not mandatory to fill. Comentarios remains private, X remains latitude and Y longitude, unknown values stay unknown, custom columns stay base-local, and no automatic Excel refresh or silent import of historical rows is added.

## 3. Close out existing work before issuing the next feature pair

These are already-assigned tasks and supervisory responsibilities, not new entries in the 12-packet count:

- Finish re-review of A's corrected #17 and name the accepted P2 head if it passes. Its code/doc changes match the requested direction; verify the relevant contention regression before issuing acceptance.
- Let B finish the current memory packet. Review its actual final report, head, tests and limitations; do not send overlapping instructions onto its active branch now.
- Consolidate the attachment contract from accepted P1, P2, B-1/B-3S and PR #12 §9. Settle the local limits/selection/expiry/batch rules before B's implementation begins. Cloud provider approval is not required for local/fake backend work.
- Freeze A/B request/response and component boundaries, route-registration requests, file ownership and initial snapshot-reference requirements. This is supervisor work; neither team should invent conflicting shared contracts.
- Publish exact GitHub instruction SHAs. No desktop path is a dependency for either Claude account.

## 4. The 12 planned instructions

The IDs below are new plan identifiers, not a renumbering of historical A-1/A-2/B-1 milestones. Each packet gets a concrete scope, exact base SHA, owned files, dependencies, acceptance checks and stopping point when released.

| Packet | Team | Assignment | Required result |
|---|---|---|---|
| **1A** | A | **Integration baseline and master-record backend.** First assemble reviewed prerequisites in a draft integration branch; then implement scoped record list/create/edit, optional-field/currency behavior, archive/restore/transfer and SQL query/pagination/history rules. | One versioned terrain source; an operator can create a fully blank business record in an assigned base and cannot reach another base. Transfers retain IDs/files and correctly restrict history. Admin global queries are bounded. |
| **1B** | B | **Attachment lifecycle core.** Build the file/version/attempt state machine on the accepted parser, storage core, schema and transaction authorization. Implement finalization, retries/cancel, replacement/retirement, KMZ selection/activation, idempotency and race/audit rules. | SQLite and disposable Postgres prove atomic state transitions, preserved last-valid layout and denial after scope loss. No cloud provider or UI required. |
| **2A** | A | **Editable table and work-base interface.** Role navigation, assigned-base/admin master views, inline editing, keyboard/save/conflict feedback, custom-column backend and management UI, base/grant controls, archive/restore/transfer UI. | An employee can add/edit/reload records and manage allowed custom columns; core columns remain protected. Admins can manage bases/grants and preview transfers. File cells expose the agreed integration slots. |
| **2B** | B | **Attachment handlers and geometry delivery.** Authenticated upload/content/complete/cancel/download/history/selection/retirement handlers; bounded geometry bodies, per-ID authorization and error/idempotency contracts. Supply exact A-owned registration requests. | Real backend operations work with local/fake storage and actual sessions; no storage keys or signed URLs leak through terrain DTOs. Request-start and transaction-final checks are exercised. |
| **3A** | A | **Connect the application.** Register B's reviewed handlers, add attachment/location summaries, adapt inventory records, connect filters/selection and mount B's widgets/loader in the grid/app shell. | The table uses the real APIs and records with a KMZ but no XY count as located. Routes remain capability-declared and operators have a coherent usable screen. |
| **3B** | B | **File cells, detail controls and geometry client.** Drag/drop or picker, progress/retry/errors, PDF open/download, retained versions and KMZ candidate choice. Add bounded cancellable geometry loading and private cache reset. | Components work against the frozen API and expose the agreed callbacks. Combined with 3A, a real PDF/KMZ persists and its boundary appears after another session reloads. |
| **4A** | A | **Filtered views and frozen maps.** Persist the approved view semantics; one-action creation from current filters, table/map navigation and snapshots that preserve the recorded values and immutable references. | Admin filters → saves view → opens the matching map. Live views and snapshots behave differently by design; old saved maps remain frozen. No copied second editable terrain store. |
| **4B** | B | **Production map strategy and snapshot integrity.** Implement the strategy selected from the memory investigation, or the explicitly approved fallback, in B-owned renderer/client modules. Verify geometry/file-version retention and loading for A's saved-map flow. | Large/dense KMZs, multiple maps, selection, overlap, cancellation, DPR and worker failure have an accepted bounded behavior; frozen maps keep their recorded layout after a replacement or transfer. No further open-ended research mandate. |
| **5A** | A | **Hosted integration and migration readiness.** Resolve the separate adapter/Preview prerequisite, maintain exact-commit deployment/config changes in dedicated PRs, prepare reviewed source-data migration, administrator/bootstrap/grants and recovery steps. | An authorized isolated Preview runs the integrated code with a disposable/approved test database. Migration and access setup have a dry run; production remains untouched. |
| **5B** | B | **Durable private cloud storage and file recovery.** After provider/access approval, implement the chosen backend, upload/download grants, expiry/revocation behavior, orphan cleanup and retained-version/restore support. | Files remain available from another computer with the owner's Mac off; unauthorized access is denied; partial failures and database-plus-file recovery are rehearsed on isolated resources. |
| **6A** | A | **Release-candidate integration and shared fixes.** Assemble the final candidate, address A-owned findings from joint testing, complete operational/account/data checks, release/rollback documentation and the operator/admin pilot walkthrough. | One exact tested candidate with no unresolved release-blocking findings and a concrete owner-reviewable release procedure. Deployment remains a separate explicit authorization. |
| **6B** | B | **Independent end-to-end and load acceptance.** Own the new full-workflow test scenarios; test permissions, concurrent edits/uploads, malformed files, replacement/transfer/revocation races, map fidelity, limits and recovery; fix B-owned findings. | A reproducible acceptance report against the same candidate as 6A, including the synthetic 25,000-record/3,000-record-base/five-session target and hosted file/map journeys. No vague “CI green therefore complete.” |

Account creation/role changes initially retain the reviewed explicit-target operations workflow; this plan does not silently add a full account-management web console. Administrator base/grant controls are included in 2A. If a self-service account console is requested, scope it explicitly rather than hiding it in release work.

## 5. Parallel execution and dependencies

| Wave | Parallel pair | Coordination point / exit gate |
|---|---|---|
| **1** | 1A + 1B | A publishes the small combined prerequisite baseline first. B can prepare its already-frozen fixtures immediately and starts integration against that exact baseline; A continues record APIs while B implements lifecycle. Do not wait for all of 1A before releasing the prerequisite. |
| **2** | 2A + 2B | Table work uses A's record API; B implements attachment endpoints. Widget/summary interfaces are already agreed. Neither edits the other's files. |
| **3** | 3A + 3B | A registers reviewed B handlers at the beginning of 3A, so B can test live APIs. A can prepare mounts against the frozen component interface; final integrated acceptance waits for B's actual widgets. **First complete local employee workflow.** |
| **4** | 4A + 4B | Freeze live-view versus snapshot behavior and immutable references before the pair. A owns saved membership/persistence; B owns rendering/loading and verifies layout retention. **Complete functional local vision.** |
| **5** | 5A + 5B | Cloud access/provider choice is settled beforehand. A owns Preview/schema/shared configuration; B owns storage implementation and supplies configuration requests. Only the designated authorized operator provisions/applies shared resources. **Hosted pilot candidate.** |
| **6** | 6A + 6B | B tests exact candidates and reports reproducible findings; each team fixes only its owned area. A assembles the next candidate; repeat only relevant checks. **Release-ready evidence and owner approval gate.** |

These are dependency waves, not artificial all-or-nothing waiting rooms. A team can start an independent part of its next reviewed packet when the required artifacts are ready, but not silently bypass an acceptance dependency. Both cannot edit `server/app.py`, migrations or shared app state at once.

Only A integrates schema/auth/routes/app shell/shared client/CI/deployment changes. B supplies explicit requests and owns its attachment, geometry and map modules. Keep PRs small, stacked only on named accepted prerequisites, and integrate in dependency order. Do not merge a research branch into application code merely because its tests pass.

## 6. The demonstrations that mark real progress

**After packets 1A–3B (six packets):** operator signs in → opens an assigned base → creates an unnamed terrain with all business fields blank → edits fields → uploads a PDF and KMZ → selects a layout when required → reloads in a second session → sees the stored file and correct boundary without XY. Another operator without access is denied. This is a local/disposable integration milestone, not a promise of durable hosted files yet.

**After 4A/4B (eight packets):** administrator saves a filtered view and opens its map in one action; later record changes follow the agreed live-view rules; a saved snapshot remains frozen when the source KMZ/record changes. Large-contour behavior is explicit and bounded.

**After 5A/5B (ten packets):** the same experience works on an isolated hosted candidate with durable private attachments and the owner's Mac off.

**After 6A/6B (twelve packets):** both roles complete the actual employee workflow, concurrency/data-preservation/access tests and recovery rehearsal pass, approved data/account steps are ready, and the owner can approve a concrete release. No percentage-complete or fixed date is inferred from the number of PRs.

## 7. Decisions and access needed from the owner

| Decision/input | Recommendation / boundary | Needed by |
|---|---|---|
| Initial administrator identities | Name exact account logins; recommend a primary administrator and a trusted backup. No automatic promotion. | Hosted bootstrap/release, not the next local coding pair |
| File limits/selection/access expiry | Consolidate PR #12 D2–D5. Proposed starting defaults remain PDF ≤25 MiB, KMZ ≤20 MiB; a single usable candidate may activate on upload; multiple candidates require choice; short-lived grants and initiator-only completion. These are proposals until the consolidated packet records the decision. | Before the affected 1B/2B behavior is frozen |
| Cloud file provider and service access | Preserve the neutral interface; choose and validate a private-storage backend against the upload/copy/recovery requirements. No provider is selected or purchased by this report. | 5B; does not block 1B–3B |
| Live versus frozen derived views | Recommend live filter-based views plus explicitly frozen snapshots. Keep existing saved maps frozen in all cases. | Before 4A/4B |
| Large-map unavailable behavior | Review B's final measurements and the real user experience before choosing the production memory/fallback policy. The 64/128 MiB experiments are not already-approved product budgets. | 4B; not a blocker to the first local workflow |
| Real source data and example KMZs | Identify the current authoritative records and review ambiguous duplicates. Test representative company files privately; never commit them. No automatic import of every historical Excel row. | Before final import/pilot acceptance |
| Preview/deployment permissions | An authorized account must resolve the recorded deployment block and provide isolated resources. Production cutover needs explicit approval. | Hosted candidate/release |

The supervisor owns routine technical choices and contract consolidation. The owner should only need to decide meaningful business behavior, identities, costs/access and release approval.

## 8. Recommendation

Close the current reviews, then release **1A and 1B** with their exact shared baseline and contract. Focus the next three waves on the working employee journey. Treat B's memory result as an input to 4B, not a reason to postpone the master table or to keep extending research without a delivery boundary.

This plan covers the requested first release. Excel automation, BigQuery, permanent purging, custom attachment-column types, arbitrary cross-base custom-field comparison and a full self-service account console remain outside it. Corrections discovered by review stay within the relevant packet; a genuine scope change is reported with its effect on the 12-packet baseline.


## Round 1 release update

Following the owner's request for the first instructions, packets **1A and 1B** are now released in [round-1-instructions-2026-10-08/START_HERE.md](../round-1-instructions-2026-10-08/START_HERE.md). The earlier status snapshot above is retained as history. Corrected P2 at `5d0844cfd678c2f7ec55ddb4b364275482d1a801` is now accepted after independent correction verification; evidence is linked in that packet. Team B finishes/submits its current memory handback before starting 1B, but need not await that research's review to develop attachments. The consolidated contract selects local lifecycle defaults and leaves provider/hosted decisions for later. Only this first pair is issued; no merge or deployment is authorized.

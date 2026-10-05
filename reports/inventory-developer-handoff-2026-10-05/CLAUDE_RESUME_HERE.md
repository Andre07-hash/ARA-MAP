# Claude restart brief — resume ARA Map Stage 2

Prepared by the project supervisor on October 5, 2026 after the previous developer session exhausted its credits. This is the entry point for a new development session with access to the project. Read the referenced documents and actual code; no earlier chat history is required. This brief is not a standalone replacement for the repository and evidence files.

## Your assignment

Resume and complete **Stage 2: publication and the real public catalog**, integrate backend and interface, and obtain independent verification. Preserve the accepted Stage 1 work. Do not restart the project, rebuild Stage 1 or merely write another plan. Follow the existing staged assignments and return evidence to the supervisor. Do not deploy or proceed automatically into Stage 3.

Workspace: `/Users/andrejasso/Desktop/ARA Map`.

Packet directory: `/Users/andrejasso/Desktop/ARA Map/reports/inventory-developer-handoff-2026-10-05`.

All document names below are relative to that packet directory. The owner works with the supervisor; developers should resolve routine implementation choices within this contract and report material conflicts to the supervisor.

## Read in this order

1. `SUPERVISOR_STATUS_REVIEW.md` — latest independently inspected stopping point and limits of that inspection.
2. `STAGE2_ASSIGNMENTS.md` — the concrete work you must perform now and each workstream's outputs.
3. `INTEGRATION_DECISIONS.md`, including **§9 and §10** — exact data/API/publication rules and later accepted clarifications.
4. `DISPATCH_STATUS.md` — read through the final Stage 1 acceptance, not just the original historical planning text at the top. It records accepted implementation deviations and carry-forward work.
5. `BACKEND_RESPONSE.md` and `FRONTEND_RESPONSE.md` — what was actually built, its DTOs, run instructions and integration details. Do not replace accepted implemented contracts with an older proposal.
6. `VERIFICATION_RESPONSE.md` — independent Stage 1 results, limitations and open items. Supporting scripts/results are under `verification/`.
7. `START_HERE.md`, `BACKEND_PACKET.md`, `FRONTEND_PACKET.md` and `ACCEPTANCE_MATRIX.md` — wider scope, file ownership, interaction specifications and relevant acceptance cases. Only implement the Stage 2 subset now.

Authority: latest explicit owner instructions, then later supervisor decisions in INTEGRATION_DECISIONS and accepted deviations in DISPATCH_STATUS, then STAGE2_ASSIGNMENTS for the current work, then older packets. Older sentences saying “documentation only,” “no code changed,” or “Stage 1 not dispatched” describe prior phases; they do not cancel the issued Stage 2 local implementation assignment. If material contradictions remain, report the exact conflict rather than silently changing product behavior.

## Confirmed product rules

- Exactly one signed-in team user type. The boss and employees have identical powers on every terrain. Individual accounts identify actions; there are no staff roles, owner-only records or manager approvals.
- Anyone can browse published terrain details, prices and map. Contacts, internal notes, imported extras and operational history remain private.
- Save creates/changes a draft. Publish explicitly promotes the exact reviewed saved revision. Pending edits do not alter the public version.
- Existing navigation, Spanish interface, legacy bases/maps, original data, currencies and price precision are retained. USD and MXN are not interchangeable; currency is never guessed.
- At least 100 terrains and three signed-in sessions are the initial business baseline. Pagination was additionally tested with 251 matching records; preserve complete map/table results.
- Detailed client search parameters will arrive later. Do not delay Stage 2 waiting for them or invent extra industry fields.

## Verified stopping point — recheck before writing

Stage 1 was accepted on independent disposable-data evidence. The supervisor subsequently recomputed `verification/runs/CANDIDATE_MANIFEST_stage1_final.sha256`: all 113 listed files matched. Five stored API runs had zero failures; browser results had 90 passes and one minor focus warning. This is a record of past checks, not permission to claim the current candidate was retested.

At that inspection, public list/detail in `server/api/inventario.py` were still empty-list/404 placeholders and lifecycle/preview routes were absent. Only STAGE2_ASSIGNMENTS.md existed; no Stage 2 response or verifier report had been delivered. The previous session's statement “all three are working” does not establish that any agent is alive now. Check for subsequent files/changes and active workers; reuse legitimate partial work and avoid conflicting edits.

The workspace has no Git repository at the inspection point. Do not initialize/reset/clean it to simplify your work. Preserve existing files, compare the source manifest and record a new candidate manifest for your changes. A mismatch is a reason to inspect, not to revert automatically.

The original `datos/ara_map.db` was read-only inspected as **schema v4, without a team_user table**. Do not launch `ARA Map.command` against it for development: launch invokes migration and the owner has no provisioned accounts there. Test on explicit disposable data. The Stage 1 v7→v8 fixture checks do not certify the owner's actual v4 upgrade path; that rehearsal remains part of later handover.

## Implementation sequence

### Backend

Own `server/`, `api/`, relevant `scripts/` and Python tests. Implement the lifecycle endpoints, authenticated saved-draft public preview and real anonymous list/detail exactly as STAGE2_ASSIGNMENTS specifies. Reads and filters must use the immutable revision selected by the published pointer. Use the shared explicit public field serializer; do not introduce a second stored publication copy. Changes, version checks, pointers and history commit atomically.

Implement carry-forwards: generic unexpected-error responses, login throttling keyed by login and client with safe client identification and shared storage, and config.readOnly reflecting only the explicit read-only setting. Preserve security checks while doing so. Do not trust arbitrary spoofable forwarded headers without considering the real deployment adapter.

Deliver `BACKEND_RESPONSE_STAGE2.md` with actual DTOs, changed files, isolated test results, migration impacts and remaining limitations. Communicate any necessary interface adjustment before changing the agreed contract.

### Interface

Own `web/`, JavaScript tests and browser integration tests. First split the oversized `web/components/app.js` as narrowly as necessary, preserving behavior and proving it with the existing tests; do not redesign or rewrite frameworks. Integrate the real public catalog, exact-revision preview, publish/unpublish/archive/restore, lifecycle labels and pending-change warnings.

Fix history focus return, add inventory status visibility, keep phone toasts clear of editor actions and update legacy smoke tests for individual sign-in. Fixtures may enable initial parallel work but do not establish completion. Connect to the actual Stage 2 backend before handoff. Deliver `FRONTEND_RESPONSE_STAGE2.md` with integrated browser evidence and known limitations.

### Independent verification

Use a separate verifier when agent tooling is available. It owns `verification/`, prepares cases while development proceeds, then tests the actual integrated candidate. Do not substitute developer self-reports for an independent pass. If independent execution is unavailable, clearly mark that acceptance step pending rather than claiming it happened.

Run the Stage 2 matrix listed in STAGE2_ASSIGNMENTS: PUB-01/02/03, CON-02, PRE-01, public VIEW-01/02/03, legacy/new anonymous-route audit, REG-01 and Stage 1 regressions. Exercise SQLite and disposable Postgres through the appropriate HTTP adapters, plus the browser. Check public data with actual published records, not just an empty catalog. Private-data leakage is a blocking gate.

Preview `published_at` is null; compare business fields/revision to the public result and check actual commit time separately. Preserve stated limits: Postgres's current workspace lock serializes transactions, so concurrency tests do not establish unrestricted capacity. Produce `VERIFICATION_RESPONSE_STAGE2.md` with precise pass/fail/skip evidence and the exact source manifest tested.

## Coordination and execution boundaries

If agent tooling is available, assign backend and interface work separately and let the verifier prepare independently. Maintain the file boundaries above. Do not assume old process IDs, ports or test databases remain valid; inspect and select free resources. If working sequentially, preserve the same interface contract and handoff files.

No real-data publication, production migration, deployment, credential rotation, paid AI calls or use of production as a test target. Do not read `.env.local` or `.cloud-access.txt` for this assignment. Default cloud setup/migration scripts can load production configuration: use only explicit verified disposable targets and review the existing run instructions first. Create fictional test accounts in those targets only. Do not remove or overwrite original databases, workbooks, saved maps or unrelated changes.

Do not ask the owner to repeat already settled decisions or reapprove routine local development. If genuinely blocked, describe the exact missing dependency and continue independent work where possible. Keep source/evidence progress recorded so another interrupted session can resume safely.

Stage 3 remains deferred: inventory Excel import/adoption, duplicate review and attention-list UI. Full recovery rehearsal, actual account setup, real data adoption and deployment also remain later. The future AI search agent, PDF sheets, client shortlist links and role restrictions are outside this assignment.

## When to report back

Report after Stage 2 implementation and independent verification, or sooner for a concrete blocker. Lead with what now works through the real interface; name remaining failures honestly. Include the three Stage 2 response files, source manifest, commands/results and evidence paths. Append accurate progress to DISPATCH_STATUS.md without leaving its earlier historical entries looking like the current status.

The supervisor decides acceptance from the integrated evidence. Do not declare the entire product finished or ready for production after Stage 2, and do not mark an unexecuted check as passed.

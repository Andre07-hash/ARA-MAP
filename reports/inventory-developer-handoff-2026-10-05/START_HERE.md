# ARA Map — developer instructions from the supervisor

> **Priority 0: GitHub/Vercel readiness now comes first.** Follow the [repository and deployment prerequisite](../github-vercel-readiness-2026-10-05/START_HERE.md) before continuing Excel + BigQuery implementation. The owner requested this order after moving development to GitHub.

**Current implementation instructions:** [Excel + BigQuery developer packet](../excel-bigquery-developer-handoff-2026-10-05/START_HERE.md). The owner has asked to proceed with this plan. Assignments, shared contract, company setup inputs and acceptance criteria are ready; no developer dispatch or software completion is claimed by this notice.

> **Priority changed after the owners’ meeting (October 5, 2026).** Read [Excel + BigQuery realignment](../product-plan-2026-10-05/EXCEL_BIGQUERY_REALIGNMENT.md) first. Connected Excel refresh and company BigQuery storage now come before all further inventory/public-catalog work. The earlier website-authoritative assumption, spreadsheet-sync deferral and database-provider restriction below are superseded. Preserve completed work; do not resume Stage 2 from this historical plan. This notice changes priorities only; no connector, migration or deployment is complete.

Issued October 5, 2026. This packet translates the owner's approved direction into staged implementation work. Read this file first. The detailed packets are reconciled by the supervisor before implementation; do not treat an individual developer's draft contract as independently authoritative.

## The result we are building

ARA Map becomes an ongoing terrain inventory. A small team maintains terrain records directly in the website. Anyone can browse a published catalog. The boss and employees use the same signed-in experience and have identical powers. Excel is a bulk-entry tool, not a requirement for ordinary corrections.

Preserve the recognizable navigation, map, terrain details, imports, saved maps and comparisons. Use the current Python, JavaScript/Leaflet, SQLite and PostgreSQL architecture. A new framework, database provider or design-system rewrite is outside scope.

The first delivery target is this week, subject to evidence and effort assessment. Do not trade away correct prices, publication control, existing data or usable editing to meet an invented deadline.

## Confirmed requirements

1. One logical master inventory with a permanent identity for each terrain. Renaming or correcting a terrain does not create a new identity.
2. Direct add/edit, Excel bulk additions, archive, draft save, publish and unpublish.
3. One signed-in user type. Every signed-in team user can maintain every terrain, regardless of its creator. No administrator/manager/editor hierarchy, ownership restrictions or approval queue.
4. Individual identities provide attribution. They do not provide different powers. Account provisioning must not let anonymous public visitors become team members through open registration.
5. Public visitors see published terrain details, prices and map. Contacts, internal notes, history, unclassified source fields and operational metadata are private.
6. Save and Publish are different actions. A new record starts as a draft; editing an already published record does not expose pending changes. A public visitor sees the last published revision until the user publishes another revision or unpublishes.
7. At least 100 representative terrains and three simultaneous signed-in sessions form the initial acceptance baseline. Do not hard-code 100 as a limit or advertise untested scale.
8. Prices retain their actual USD/MXN currency and precision. Do not convert currencies, guess them, or compare mixed currencies as though they were the same unit.
9. Existing imported data and frozen saved maps survive. Adopting records into the master inventory is deliberate and traceable; legacy data is not automatically published.
10. Detailed business-specific search characteristics will come from the owner later. Build the current core fields and lifecycle now; leave new search parameters out of the committed scope.

## Priority and scope boundaries

P0: lasting inventory identity, editing, equal signed-in access, concurrency protection, publication revisions, public/private data separation, import continuity and preservation of existing records.

P1 after P0 works: a lightweight needs-attention list, duplicate warnings and a public preview before publishing. The attention list should begin with missing core information and never-confirmed price/availability; display confirmation dates. Do not silently invent a business expiration policy. Duplicate warnings must be reversible human decisions, not automatic merges. Preview must use the same server field projection as publication.

Retain desktop navigation and provide usable search/filter controls on phones. Public browsing requires a functional narrow-screen workflow, not merely a page without horizontal overflow.

Deferred: natural-language AI search, new client shortlists/share links, new presentation mode, branded PDF sheets, enhanced comparisons, parcel boundaries, automatic spreadsheet synchronization, differentiated roles, approval chains, notifications, subscriptions and CRM features. Existing saved maps and comparisons remain supported internally.

## Build in reviewable stages

| Stage | Lead work | Exit evidence |
|---|---|---|
| 0 — Freeze interfaces | Backend and UI agree routes, payloads, revision rules, publication validation and auth flow; verification challenges them | A single reconciled contract, clear ownership and a migration approach |
| 1 — Inventory foundation | Backend implements additive schema, stable identity, equal user access, history and version-checked draft edits; UI develops against agreed fixtures | New/edit/reopen workflow works on disposable data; three identities have equal capabilities; conflicting edits return a recoverable conflict |
| 2 — Public catalog | Backend exposes allowlisted published data and closes legacy anonymous reads; UI adds catalog, publication, unpublish and preview | Draft edits stay private; publish updates public detail/map/table; private data cannot be fetched through older routes or exports |
| 3 — Bulk and daily work | Reviewed import/adoption, duplicate review and attention list; retain legacy map behavior | Initial population and repeat additions do not lose records, change currency or silently duplicate identities |
| 4 — Independent acceptance | Verification exercises full flow, migrations, recovery, 100 records/three sessions and desktop/phone | Reproducible evidence, source manifest and a specific release recommendation |

The supervisor reviews each stage. Developers should continue independent authorized work while dependencies are resolved, rather than repeatedly asking the owner routine implementation questions. A failed gate produces a focused repair assignment, not a new feature or broad rewrite.

## Coordination and file ownership

- Backend owns `server/`, `api/index.py`, database/auth tooling under `scripts/`, backend tests and required runtime dependency changes.
- Interface developer owns `web/` and corresponding JavaScript tests. Coordinate common fixtures and HTTP contracts before wiring the app.
- Verification owns its evidence, new independent integration/browser acceptance scenarios and the release report. Do not change implementation code while independently certifying it; report the defect to its owner.
- The supervisor owns this directive, the final integration contract, work allocation and acceptance decisions.
- Do not edit another workstream's files concurrently without agreeing ownership. This workspace may not have Git metadata: do not initialize, reset, clean or discard files to simplify coordination. Record changed paths and checksums when Git diffs are unavailable.
- Preserve unrelated work. Never use the working production-like local database as a disposable test database.

## Migration and existing-public-site behavior

The existing app's legacy datasets and snapshots were readable anonymously. The new catalog policy must be enforced by the server, including exports, detail endpoints, legacy maps and import-related reads. Merely hiding internal navigation is insufficient.

Preserve legacy bases/maps for signed-in use. Public discovery begins from explicitly published master records. Expect an empty public catalog before first publication and provide a useful empty state. Do not publish old demonstration data, old maps or all current bases just to avoid an empty screen.

Rehearse migration on a disposable copy, compare old record values and frozen snapshots, test re-running the migration, and prove recovery. A source-base deletion must not delete adopted master inventory records. Keep source provenance independently of that relationship.

Do not invoke the cloud migration script without an explicit disposable target: its default loads production configuration. Production migration, data adoption/publication, credential changes and deployment are not part of this instruction-writing assignment. Prepare the exact candidate and runbook for supervisor review first. Local implementation and isolated verification can proceed when dispatched; another user permission request is not needed for ordinary reversible development.

## Required developer response at each handoff

Write the response in this packet directory. Lead with the usable behavior delivered, then include:

- Files changed and source revision or checksum manifest.
- Contract/schema decisions and any deviation from the supervisor packet.
- Exact isolated test commands, results and where the evidence lives; distinguish your report from independent verification.
- Migration and compatibility effects, unresolved issues and untested paths.
- The next dependency or concrete supervisor decision, if any.

Use `BACKEND_RESPONSE.md`, `FRONTEND_RESPONSE.md` and `VERIFICATION_RESPONSE.md`. Do not describe code as deployed or production-ready based solely on unit tests. Do not hide missing test coverage behind an aggregate pass count.

## Documents in this packet

- `BACKEND_PACKET.md`: repository-specific backend implementation brief.
- `FRONTEND_PACKET.md`: repository-specific interface and interaction brief.
- `ACCEPTANCE_MATRIX.md`: independent acceptance cases and release gates.
- `INTEGRATION_DECISIONS.md`: final supervisor resolutions; this takes precedence over provisional alternatives in the detailed packets.
- `DISPATCH_STATUS.md`: exact assignments and completed deliverables; distinguish briefing from implementation.

If documents disagree, the user's latest explicit decisions win, then `INTEGRATION_DECISIONS.md`, then this directive, then the specialized packets. Send unresolved contract conflicts to the supervisor, not directly to the owner.

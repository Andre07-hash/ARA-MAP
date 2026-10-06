# ARA Map: shared inventory and client selection plan

> **Priority 0: GitHub/Vercel readiness now comes first.** Follow the [repository and deployment prerequisite](../github-vercel-readiness-2026-10-05/START_HERE.md) before continuing Excel + BigQuery implementation. The owner requested this order after moving development to GitHub.

**Current implementation instructions:** [Excel + BigQuery developer packet](../excel-bigquery-developer-handoff-2026-10-05/START_HERE.md). The owner has asked to proceed with this plan. Assignments, shared contract, company setup inputs and acceptance criteria are ready; no developer dispatch or software completion is claimed by this notice.

> **Priority changed after the owners’ meeting (October 5, 2026).** Read [Excel + BigQuery realignment](EXCEL_BIGQUERY_REALIGNMENT.md) first. Connected Excel refresh and company BigQuery storage now come before all further inventory/public-catalog work. The earlier website-authoritative assumption, spreadsheet-sync deferral and database-provider restriction below are superseded. Preserve completed work; do not resume Stage 2 from this historical plan. This notice changes priorities only; no connector, migration or deployment is complete.

Prepared October 5, 2026. Updated with the user's scope and publication decisions. Status: agreed direction and publication rules; detailed search parameters pending. This is a supervisory planning document, not an implementation authorization or a release-readiness certification.

Developer handoff prepared at the user's request: `reports/inventory-developer-handoff-2026-10-05/START_HERE.md`. That packet and its `INTEGRATION_DECISIONS.md` translate this roadmap into the current staged build instructions. Backend, interface and independent verification specialists reviewed the repository to prepare their packets. No application implementation or production changes were performed during this handoff task.

## Confirmed direction

- Employees edit directly in the website. Excel remains available for bulk additions.
- Anyone can browse a public inventory.
- All authorized employees can publish using an explicit Publish action; no manager approval queue is required.
- There is one signed-in user type. Employees, the boss and other authorized team members have identical capabilities across the shared inventory. Do not build separate administrator, manager or editor roles, per-person restrictions or ownership-based editing limits for the first release. More granular restrictions may be added later.
- Public visitors see published terrain details, prices and the map. Contacts and internal notes remain private.
- Expect 1–3 employee editors and prepare for at least 100 terrains. This is a minimum test baseline, not a storage cap; public visitor concurrency is not yet specified.
- There is no fixed deadline. The preferred target is a focused first release during the week of October 5, 2026, subject to developer estimates and verification.
- The user will provide detailed search parameters later. Do not make those parameters a prerequisite for planning the core inventory workflow or invent them as accepted requirements.

## Product outcome

Employees maintain a shared terrain inventory directly. Public visitors browse the published inventory on the map and open terrain details. The manager searches current inventory, selects suitable terrains and presents them to a client. Later, a natural-language assistant helps express the search and prepare a selection using the same records and search rules.

Keep the navigation, individual-entry workflow, imports, maps, comparisons and useful presentation behavior already accepted by the owner. Add a clearly identifiable master inventory as the default working area.

## Evidence and starting point

Local source and project reports were reviewed; production was not re-audited for this plan.

- The project already supports shared persistence in Neon Postgres. The need is an operational inventory workflow and data model, not simply buying or adding a database.
- The current terrain schema assigns records to imported bases. An individual terrain can be added manually; the reviewed route table does not expose a general terrain-edit endpoint.
- The current authentication implementation uses a shared editor password. Individual accountability will require employee identities.
- Saved maps contain frozen copies of terrain data. Preserve that established behavior; add explicit live selections separately.
- The README is partly behind the current source: the October 1 release evidence confirms USD support for the demonstrated workbook. Do not repeat the README's older MXN-only description.
- The September 30 readiness report and October 1 scoped release decision leave broader import and small-screen concerns for re-verification. They are historical findings, not freshly reproduced defects in this planning exercise.

Sources: `server/db.py`, `server/app.py`, `server/api/bases.py`, `server/repo/terrenos.py`, `server/cloud_auth.py`, `README.md`, `reports/readiness-2026-09-30/READINESS_REPORT.md`, and `reports/urgent-usd-import-2026-10-01/release/LIVE_CONFIRMATION.md`.

## Proposed product decisions

### One lasting terrain record

Give each terrain a stable company identifier independent of its name, spreadsheet row or imported base. Price, location and name corrections must update the same terrain. Imports retain their origin and link to the master record after review. Suspected duplicates require a human decision; names alone cannot establish identity.

Before finalizing the model, determine whether one physical parcel can have several simultaneous offers, brokers, subdivisions, or sale/lease terms. If so, distinguish the parcel from its commercial offers rather than overwriting competing information.

### Employee workflow

Find an existing terrain before creating one. Open its editable data sheet, update its details, review validation messages and save. Record who changed what and when. Protect against two people unknowingly overwriting one another. Archive unavailable inventory rather than erasing its history.

Separate data readiness (draft, ready for presentation) from commercial status (available, under negotiation, sold, withdrawn, unknown). The exact statuses and any approval step require business agreement.

Keep imports for initial population and bulk additions, with preview and deliberate matching. Preserve the existing reviewed-update behavior where supported. Ordinary maintenance should not require another upload. The website is authoritative; spreadsheet synchronization is outside the confirmed scope.

### Public catalog and employee workspace

Public browsing and explicit publication by any signed-in team user are confirmed. All signed-in users have the same access to the internal inventory, contacts, notes and history, and the same ability to add, edit, import, publish, unpublish and archive terrains. Individual accounts identify who made a change; they do not confer different powers. Public visitors remain anonymous readers of published content, not a second configurable staff role. Keep internal access and editing behind sign-in. Proposed publication states are draft, published and unpublished, separate from availability. A new import must not automatically turn every source field or historical dataset into public content.

Confirmed public view: published terrain details, prices and map. Contacts and internal notes stay private. Operational data such as employee identities and edit history remain in the employee workspace. Unclassified attachments and arbitrary imported columns are not automatically public; define a concrete public field allowlist from the agreed terrain details.

Proposed implementation semantics for the explicit Publish decision: saving a new terrain creates a draft. Editing a published terrain saves pending changes while its last published version remains public. Publish validates and promotes those changes together. Unpublish removes the public listing without deleting the internal terrain or its history. Make pending availability changes conspicuous so employees do not mistake a saved draft for a published update. Test these transitions independently from ordinary draft saving.

Apply the agreed rules on the server to detail, list, search, export, attachments and saved-map endpoints; hiding a field in the interface is insufficient. Existing public routes and historic snapshots must be included in this review. Do not change production visibility or publish existing records as part of planning.

Every signed-in team user can explicitly publish a validated record, without a separate approval queue, as confirmed by the user. Record the publishing user and time. Server-side sign-in checks apply to the Publish action as well as editing. All signed-in users can maintain all terrains regardless of who created them. Assignment to a responsible employee is accountability metadata, not an access restriction.

### Three kinds of client selection

| Selection | Membership | Terrain details | Purpose |
|---|---|---|---|
| Saved search | Re-evaluated against agreed filters | Current | See everything currently matching a client brief |
| Curated shortlist | Chosen terrains stay selected | Current, with unavailable records flagged | Keep the manager's preferred options together |
| Dated presentation | Frozen at creation | Frozen and labelled with its date | Retain what was actually presented |

These are views or selections over the master inventory, not independently maintained databases. Preserve existing saved maps as dated copies. Clearly distinguish frozen commercial information from current availability.

### Data employees should capture

Agree the field definitions with a knowledgeable employee using representative real terrains and actual client briefs. Do not make every desirable field mandatory for saving a draft.

| Group | Proposed fields | Rule |
|---|---|---|
| Identity and responsibility | Stable ID, name, responsible employee, source | ID generated by the system; source and ownership traceable |
| Location | State, municipality, address/reference, verified latitude/longitude | A real boundary is optional and distinct from a map point or approximate area circle |
| Size | Area and unit, usable area or recorded restrictions where known | Standardized comparison units; preserve original values and label calculations |
| Commercial terms | Sale/lease, asking amount, total versus per-m² basis, currency, availability | Unknown is explicit; no silent currency conversion or mixing incomparable amounts |
| Search characteristics | Intended/permitted use, road access, water, power, drainage, other client-relevant features | Structured choices where useful; unknown distinct from no; claims carry source/verification status |
| Freshness | Availability last confirmed, price last confirmed, confirmed by, evidence/source | Separate from the ordinary last-edited timestamp |
| Presentation and internal material | Client description, photos/data sheets if needed; separate internal notes and contacts | Decide which fields clients may see before sharing or exporting |

Suggested gate for normal client presentation: identified location, valid area, commercial availability, accountable employee, confirmation date, and either an explicit price with basis/currency or an explicit price-on-request designation. Business rules must decide whether incomplete or stale records remain visible with warnings or are excluded by default. A user can save a draft without meeting this gate.

## Delivery sequence and acceptance

| Phase | Team deliverable | Acceptance evidence |
|---|---|---|
| 0. Confirm scope | Workflow, field dictionary, visibility and approval decisions, sample records, migration inventory | User confirms scope; employee can describe how each required field is obtained; deadline and expected volume recorded |
| 1. Operational master inventory | Stable identity, direct create/edit, individual sign-in with identical capabilities, status, confirmation dates, history, concurrent-edit protection | Any signed-in team user can maintain any terrain; another authorized session sees the saved change without re-import; actor and previous values can be traced; conflicting edits are not silently lost |
| 2. Client search and selection | Agreed filters across map/table, saved search, curated shortlist and explicit dated presentation | Several real client briefs produce the expected selections; unknown fields do not satisfy requirements; an availability change affects live results but does not rewrite a dated presentation |
| 3. Controlled pilot and handover | Reviewed migration, employee guidance, demonstrated backup recovery, working-device checks, defect closure and release evidence | Representative existing records and saved maps survive; employees complete routine tasks unaided; manager finds and presents suitable terrains within an agreed target; expected volume and concurrent usage meet measured targets |
| 4. Future search assistant | Plain-language request translated to inspectable search criteria and a proposed shortlist | Agreed benchmark briefs pass; hard requirements are respected; missing information is identified; result explanations cite actual fields; no unauthorized inventory edits occur |

These phases describe the broader roadmap. The focused first release below is the proposed target for this week; it does not require finishing every feature in phases 1–3. Phase 4 is a separate later milestone. Prepare its data and search foundations now.

### Focused first release: proposed scope for this week

1. One master inventory with stable terrain identifiers and a reviewed path for incorporating existing records.
2. Individual sign-in for 1–3 team users with identical capabilities, direct create/edit, accountable changes and conflict protection. No role hierarchy or role-management interface.
3. Draft/publication control, commercial availability and price/availability confirmation dates, under the user's chosen publication rules.
4. Public map, table and terrain details with existing supported filters; verify core browsing/search on desktop and phone.
5. Excel bulk additions with preview and duplicate review; maintain established map, currency and import behavior.
6. Acceptance with at least 100 representative terrains and three employee sessions, including concurrent edits, public visibility checks and persistence without re-upload.

Use the existing core fields plus inventory lifecycle fields for this release. Additional business-specific search fields will be specified when the user supplies the parameters. Scope adjustment may be needed if those fields become first-release requirements.

Defer the new saved-search/shortlist system, AI search agent, spreadsheet synchronization, client accounts, differentiated staff roles and approval processes unless explicitly reprioritized. Preserve the existing saved-map functionality. Public exports must either use the approved public field set or remain unavailable until that is verified.

Suggested sequence, subject to developer assessment: first specify the confirmed publication rules and migration approach; next implement inventory editing and public presentation; then rehearse migration and exercise all employee/public flows; finally pilot with an employee and the manager. Give a delivery-date recommendation after the developers identify effort and dependencies. This-week delivery is a target, not a promise or evidence of developer staffing.

First-release acceptance includes: a saved edit is visible on a subsequent authorized read without file upload; saving pending changes to a published terrain does not change its public version; a published update reaches subsequent public reads within a defined freshness window; a draft or private field cannot be retrieved anonymously; a published sold/withdrawn status excludes the terrain from the available catalog; dated maps preserve their history without exposing private fields publicly; no existing records are lost; all three editors can complete normal tasks without silent data loss. Define measurable search/load targets and public load assumptions before performance sign-off.

## Migration and continuity

Inventory existing bases, distinguish genuine inventory from demonstrations and historical versions, and obtain business decisions for ambiguous duplicates. Rehearse the migration on a copy. Preserve original source references, currencies, values and dated maps. Produce record-count and field-level reconciliation evidence and a recovery procedure before production changes. Do not silently merge, delete or replace existing bases.

A logical master inventory can use the existing database service. Developers must examine query behavior, indexing, pagination and map rendering against the agreed record volume. Do not promise scale from the existence of a cloud database alone.

## Future assistant behavior

Example brief: “Available industrial terrains in this municipality, at least 20,000 m², under this total USD budget, with confirmed road access.” The assistant extracts hard requirements and preferences, asks about materially ambiguous terms, shows editable criteria, runs the authorized search, and proposes a named selection. Near matches appear separately and explain what fails or remains unknown. Zero matches remain a valid result; requirements must not be silently relaxed.

The assistant should reuse the same search service as manual filters. It must not infer verified utilities, permitted use, availability or price from an attractive description. Initial scope is search and selection; adding or modifying inventory through AI is a separate future decision. Public client selections expose only approved presentation fields. All signed-in team users have equal access; finer permissions are a later enhancement.

## Team supervision

These are ongoing workstream responsibilities. Repository-grounded briefing assignments were dispatched to backend, interface and independent verification specialists for the October 5 developer handoff; implementation status is recorded separately in that packet's `DISPATCH_STATUS.md`:

- Product/data owner: user and designated company employee confirm definitions, real records, priorities and acceptance briefs.
- Data/backend developer: identity, direct editing, uniform signed-in access and public/private separation, history, conflict handling, migration and search behavior. Do not introduce a staff role hierarchy.
- Frontend developer: employee forms, map/table continuity, status visibility and client-selection workflow on agreed devices.
- Verification/release owner: independently exercises full workflows, migration recovery, equal capabilities for all signed-in users, public/private separation and agreed-volume behavior; provides reproducible evidence.
- Supervisor: issues bounded work packets with acceptance criteria, resolves cross-team dependencies, reviews evidence and reports completion, open decisions and release recommendation to the user. Developer self-reports alone do not establish final acceptance.

Report progress by usable outcomes: “employee can update availability,” “manager can reopen a live shortlist,” and “migration preserves the existing records.” Provide estimates only after scope and team capacity are known.

## Questions awaiting answers

1. Detailed search parameters and real client briefs: deferred at the user's request, to be supplied later.
2. During field definition: who confirms availability/prices and how often; are multiple offers per parcel common; which attachments and boundaries are actually needed?
3. Before performance acceptance: expected public traffic and measurable response-time targets. Three employee sessions do not establish public browsing capacity.

Website editing, Excel bulk additions, public browsing, one signed-in user type with equal capabilities, explicit publication by any signed-in team user, public terrain details/prices/map, private contacts/notes, and the minimum 100-terrain/1–3-editor baseline are confirmed user decisions. Individual accounts for attribution and deferring AI to a later release remain product recommendations supporting this scope. Detailed search parameters will follow from the user; no further publication-policy clarification is needed to prepare developer work packets.

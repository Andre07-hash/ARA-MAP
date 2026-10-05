# Supervisor integration decisions — contract v1

October 5, 2026. This document resolves alternatives in the backend/interface briefs. Implement these decisions before introducing a different contract. Routine implementation details remain with the developers. This is a development baseline, not a claim that the resulting application exists or has passed acceptance.

## 1. Scope and sequencing

The owner's confirmed scope is recorded in START_HERE.md. No differentiated staff roles. All signed-in team users can maintain all inventory records and read all internal contacts/notes/history. Anonymous visitors get the public catalog only.

Stage 1 authentication changes can temporarily close old public routes before the new catalog is integrated. Stages 1–3 therefore remain a local, incomplete candidate. Do not deploy a partial backend/frontend stage. Cut over the new authentication, public catalog and legacy-route policy together after integrated acceptance and migration rehearsal.

First inventory bulk import/adoption supports **add and skip only**. Optional reviewed bulk update of master records is deferred. Existing legacy base append/correction remains supported internally. Direct record editing handles ongoing updates.

## 2. Keep the data design focused

Use new additive inventory identity, immutable revision, event, source-provenance and import-batch tables beside existing legacy data. Use UUID text IDs for inventory and individual users; retain integer IDs on legacy routes. A stable identity is never a name or spreadsheet row.

An inventory identity holds its current draft pointer, nullable published pointer, publication timestamp, monotonically increasing version and archive state. Publication time is the time of promotion, not the revision's creation time. The published pointer must reference a revision of that same terrain. Atomic version-checked mutations update revision/pointer/history together. All changes to a record increment the version, including private-note and publication changes.

**Do not require a separate stored `inventory_publication` table in release one.** Derive the public projection from the immutable revision selected by `published_revision_id`, using a shared explicit serializer and public eligibility predicate. Preview calls that same serializer on the reviewed draft. Public queries select only projected fields. Public filters, facets, counts and pagination operate on published revision fields, never draft fields. List/count queries within one response share a consistent transaction or query. This avoids maintaining two authoritative copies of published facts. If measured query needs justify a projection cache later, propose it with consistency tests.

Keep auth-user/session storage and durable idempotency results as needed. Do not put a role field into the user model. Incompatible requests cannot share an idempotency key. Import/addition retries must return the original successful result rather than creating another record.

One inventory item represents one independently tracked terrain listing in release one. Do not auto-merge same-name properties or invent a parcel/offer management system before the owner provides that business need. Separate similar listings may coexist after duplicate acknowledgment.

## 3. Authentication contract

Adopt individual username/password accounts with vetted password hashing, revocable server-side sessions and shared server authentication policy across local/cloud adapters. No open signup. Initial account provisioning/reset/deactivation uses an explicit-target operations command with secret input; it is not a privileged in-app user type. Document this operational setup and test it with fictional users.

The public API allowlist is exactly:

- GET `/api/config` — nonsecret UI/runtime configuration only.
- GET `/api/session` — `{authenticated:false}` or `{authenticated:true,user:{id,display_name}}` for the current cookie.
- POST `/api/login` — `{username,password}`; session cookie, generic errors and bounded/rate-limited attempts.
- POST `/api/logout` — revoke current session if present and clear cookie; idempotent.
- GET `/api/publico/terrenos` and GET `/api/publico/terrenos/:id` — published eligible records only.

Safe static assets remain public. All other API routes require sign-in, including old bases/maps/folders, legacy exports, import previews, history and internal search. Unknown API routes must never bypass this boundary through a fallback. Do not authorize inventory through old shared-password cookies or public-edit bypasses. Preserve same-origin/CSRF defenses, using a documented loopback-only cookie configuration for isolated tests.

Public exports are not required initially. Hide that action publicly and deny legacy export anonymously on the server. Internal exports remain available.

## 4. Common API rules

Use the route vocabulary in BACKEND_PACKET.md with the corrections here. `version` is the record concurrency counter; `revision_id` identifies an immutable content revision. Do not interchange them.

Internal detail/create/patch/action responses use `{terreno: InternalTerrain}`. `InternalTerrain` includes `id`, `version`, `draft_revision_id`, `published_revision_id`, `publication_state`, `public_visible`, `has_pending_changes`, `archived_at`, `draft`, `attention`, and internal change metadata. Mutable domain fields live under `draft`; server IDs, pointers, versions and actor fields are never client-editable.

`publication_state` is `draft`, `published`, `unpublished` or `archived`. A published sold/withdrawn revision can have `public_visible:false`; use an explicit human label such as `Fuera del catálogo · Vendido`, not an ambiguous claim that it is visible. `has_pending_changes` means a saved draft differs from the selected published revision, not merely that a page form is dirty. Unsaved form state is maintained separately in the UI.

PATCH accepts `{expected_version,changes}`. Publish accepts `{expected_version,revision_id}` and only publishes the current saved draft. Other lifecycle actions accept `{expected_version}`. All perform compare-and-set in the same transaction as their effects. Any stale version returns 409 with no partial changes.

Preview returns `{id,version,revision_id,preview:true,terreno:PublicTerrain,blockers:[],warnings:[]}` for the requested saved revision. Its projected `published_at` is null because the future commit time is not yet known. Preview/public equality compares the terrain business fields and revision ID; verify the actual commit timestamp separately. The Publish action must refer to this exact saved draft and current version. A changed draft requires another review. No implicit save within Publish.

Errors use `{error,detalle}` with readable Spanish summaries. `detalle.code` is machine-readable and may include field errors. Use 401 for absent/invalid sign-in, 404 for absent/nonpublic public detail, 409 for stale version/changed preview/idempotency conflict, 410 for expired staged import and 422 for input validation. Public errors never expose internal records or stack traces. Preserve legacy error behavior where unrelated callers depend on it.

Require `Idempotency-Key` on direct inventory create and inventory import/adoption confirmation. Store the operation/request hash and successful result atomically with the business write. Same key/same request returns the original result; same key/different request is 409. Do not claim this prevents independent intentional reimports: those still require duplicate review.

## 5. Public projection and commercial meaning

`PublicTerrain` contains only:

`id`, `revision_id`, `terreno`, `estado`, `municipio`, `direccion`, `superficie_m2`, `superficie_ha`, `afectaciones_pct`, `afectaciones_m2`, `lat`, `lon`, `asking_price`, `asking_m2`, `moneda`, `price_on_request`, `availability`, `public_description`, `published_at`.

Use explicit field selection; never copy a whole revision and delete a few known private fields. Public data is never taken from the current draft. Contacts, internal notes, source extras, source identifiers/files, employee identities, events and import findings are excluded. Unclassified attachments are outside release one. Numbers retain precision and nulls retain their meaning. Frontend location/currency rendering must work from the public DTO without relying on private import findings.

Availability values: `unknown`, `available`, `negotiation`, `sold`, `withdrawn`. Use Spanish labels. The active public catalog includes published `available` and `negotiation` records, clearly labelling negotiation. Unknown availability prevents initial publication. Publishing sold/withdrawn removes a previously public terrain from active public list and direct detail; retain the internal history. Saving a sold draft alone does not change public availability and must show a conspicuous pending-publication warning. Archive and unpublish withdraw immediately after successful commit; restore never republishes.

Supervisor defaults for publication validation: nonblank name, valid map coordinate pair under the existing geographic validation, positive area, known availability and either a valid positive asking amount in explicit USD/MXN or `price_on_request:true`. If price-on-request is chosen, the draft must not simultaneously provide asking amounts; retain old prices in history rather than silently suppressing contradictory values. Missing verification dates remain visible as internal attention warnings and must not be fabricated. Drafts may be incomplete. These defaults are adjustable when the owner supplies business parameters; the developer must implement one consistent rule set now.

Retain warnings for inconsistent total/unit prices; do not replace source amounts with calculated values. Preview must show any such warning to the team before publication. No FX conversion, no cross-currency numerical ranking, and no assumptions from geography or magnitude. Monetary filters require a single explicit supported currency; omit records in other or unknown currencies from that monetary-filter result.

## 6. List, map and filter coherence

Freeze list envelopes as `{terrenos:[],total,next_cursor,facets}`. `facets` contains complete state/municipality/currency options for the authorized candidate set, not merely the current page; honor selected geography when producing dependent municipality options. Return a maximum bounded page size (default 100, maximum 250). Use stable ID ordering and a documented cursor. Invalid filters produce a clear 422; unknown private-field selectors are rejected.

Supported public query fields: `q`, `estado`, `municipio`, `area_min_m2`, `area_max_m2`, `moneda`, `price_min`, `price_max`, `price_basis` (`total` or `per_m2`), `cursor`, `limit`. Reuse existing search normalization and units. The internal list additionally supports `publication_state`, `availability`, `attention` and `include_archived`. Archive is excluded internally by default. Business-specific features such as water or land use are deferred.

Preserve geographic multiselect with repeated query parameters, for example `estado=A&estado=B`. Match OR within the selected states and within the selected municipalities, then AND those categories with other filters. Empty geographic selections mean no restriction. Use the router's multi-value query data rather than a helper that silently returns just the first value. Monetary currency remains a single explicit value. New catalog price filtering uses one selected basis/range; existing internal base/map filter behavior remains compatible.

For this baseline, the UI fetches all pages for the selected query before labelling the map/table/count complete. Both views consume the same assembled result; never silently draw only the first page while showing the full count. Retain an explicit loading state during assembly, cancel obsolete queries and clear accumulated private pages on logout. Revalidate after writes. Test at least 251 matching synthetic records in addition to the 100-record business baseline to cross the page boundary. This is a coverage test, not a promise of unbounded browser loading; revisit server map aggregation after measured growth.

All relevant API responses initially use `Cache-Control: no-store`. A public GET started after a successful publication/withdrawal commit must reflect it. Already open public pages refresh on explicit reload and visibility/focus revalidation; real-time push and polling are not required. UI copy must not promise instantaneous updates to an idle page.

## 7. Import, adoption and duplication

Reuse the existing import assistant's analysis, correction and review pipeline. Do not bypass its header/numeric/currency/row decisions or write a second parser. Extend its private draft context with an explicit inventory destination where needed, and return an inventory batch for confirmation. Backend must provide a fixture showing analyze → question/correction → preview → add/skip → confirmation before UI integration is accepted.

Inventory confirmation accepts only `add` and `skip` row decisions in release one. Warnings show candidate existing IDs and reasons. The user may deliberately create a distinct record after acknowledging a possible duplicate. No automatic update, merge or overwrite. Known source records already adopted are linked to their existing master ID and not adopted again by default; a separate listing requires deliberate review.

Import/adoption preview binds to batch revision, source hashes and current duplicate candidates. Revalidate at commit; changed evidence returns 409 without partial writes. Same successful retry returns original IDs/counts. All additions are private drafts. Cancellation creates no inventory rows. Source-base deletion cannot delete adopted master records or their provenance.

Keep import-format learning and legacy base operations functioning internally. Adopt existing genuine inventory deliberately; no automatic union of demonstrations, historic datasets and current sources.

## 8. Verification and release handoff

Use ACCEPTANCE_MATRIX.md and verify the reconciled rules above. Correct provisional details in the matrix when they differ. At a minimum, challenge actor spoofing; equal user powers; stale save and stale Publish; login/logout/back-navigation leakage; anonymous legacy detail/map/export access; preview/public equality; unpublished ID guessing; repeat creation/import; source deletion; pagination; mixed currency; migration/recovery on both database engines.

No need to run software regression suites for this documentation-only packet. Once implementation exists, run the relevant behavior tests, existing project verification, actual browser flows and disposable PostgreSQL checks. Record any unavailable dependency honestly. No full-release acceptance with untested publication or migration paths.

Developers may send routine design questions to the supervisor. The owner will provide detailed search parameters later; do not hold the inventory foundation waiting for them. The supervisor will issue a concrete release recommendation after inspecting integrated evidence.

## 9. Supervisor clarifications — Stage 1 (October 5, 2026)

1. **Coordinates on draft save.** Drafts may be incomplete: a missing or half-filled coordinate pair saves. Save rejects with 422 only values that cannot be coordinates at all (nonfinite, latitude outside ±90, longitude outside ±180). Values that are numerically possible but fail the existing geographic validation (swapped, outside Mexico) save as a draft and block publication.
2. **Unknown API routes.** Anonymous request to any non-allowlisted `/api/*` path, including unknown ones, returns exactly 401 with no internal payload. Signed-in request to an unknown route returns 404.
3. **Legacy-route closure timing.** Anonymous access to any `/api/inventario/*` route is a Stage 1 blocking defect. Legacy-route anonymous leakage is audited in Stage 1 and reported as findings; it becomes a blocking gate at Stage 2 exit, and nothing deploys before then.
4. **Verifier fault injection.** The verifier may patch calls inside its own wrapper process to force failures; it records exactly what was patched. This is not an implementation change.
5. **Postgres race limits.** While every Postgres session takes the workspace advisory lock, concurrent-request tests there prove version-checked compare-and-set, not overlapping transactions. Report this as a stated limitation.
6. **Test operability.** The account command accepts the password on stdin (`--password-stdin`) for automation, never on argv. Postgres schema setup uses an explicit-target command that refuses to run without a named target. Expiring a session in tests may be done by editing the disposable database directly.

## 10. Supervisor decisions after Stage 1 verification (October 5, 2026)

- **O-1.** Accepted for direct create/edit: a typed price requires explicit USD/MXN; currency is never guessed. Stage 3 must keep adopted NULL-currency records editable (see DISPATCH_STATUS carry-forward).
- **O-2.** Stage 2 public list rejects private-field and unknown selectors with 422, matching the internal list.
- **O-3.** Global Idempotency-Key scope is accepted. Users have equal powers, keys are random per attempt, and a different body still returns 409.
- **O-4.** Accepted as a stated limitation; no Postgres capacity claim is made.
- **O-5.** Stage 2: unexpected 500 responses return a generic Spanish message with `detalle.code: "internal"`; exception text is logged server-side only.
- **O-6.** Logout ends only the current session; password reset and deactivation end all sessions. Accepted.
- **O-7.** Stage 2: key login throttling per login *and* client so a stranger cannot lock out a known account, while keeping it shared across workers.
- **D-1.** Stage 2 interface fix: focus returns to the Historial button when history closes.
- **Non-API path spellings** (`/./api/…`, `/api%2f…`) serving the static app shell with no data are accepted.

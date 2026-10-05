# Backend developer packet — ARA Map shared inventory

Prepared October 5, 2026. Status: reconciled with `INTEGRATION_DECISIONS.md` contract v1, which takes precedence. This briefing packet does not itself authorize application edits, production access, migrations or deployment. No application source was changed to prepare it.

## Objective and scope

Provide a lasting inventory that 1–3 equally authorized team members maintain directly; anonymous visitors read only explicitly published listings. Excel remains a reviewed bulk-addition path. Test at least 100 terrains, without imposing a 100-record limit. Save and Publish are distinct operations. There are no boss/admin/editor role distinctions, ownership restrictions or approval queues.

Preserve existing imported bases, manually entered records, USD/MXN behavior, saved-map snapshots and current import workflows. Detailed client search parameters are deferred: implement existing filters and lifecycle fields, leaving future additions additive. Do not implement an AI search agent, new client shortlists, new PDF generation, spreadsheet synchronization or differentiated permissions.

After the P0 inventory foundation works, the first release includes lightweight attention flags, possible-duplicate warnings and an authenticated public preview. They must reuse validation/projection logic, not become separate workflow engines.

## Repository evidence and hazards

Read these files before implementation:

- `server/db.py`: SQLite schema v7; `terreno` belongs to `base` with cascading deletion. Its primary key alone is not a lasting cross-import inventory identity. `mapa_terreno` holds frozen data, including `extra_json` and incidences. SQLite migrations run on connection and back up before an upgrade; SQLite backup correctly uses the backup API for WAL consistency.
- `server/postgres.py`: translates limited SQLite SQL; `TABLES`, `ID_TABLES`, fresh schema and `migrate_sql()` need explicit changes for new tables. Every session currently takes a workspace advisory lock, including reads; this serializes requests and needs measured review before public-load claims. Logical backups omit tables absent from `TABLES`.
- `server/router.py`: route parameters match arbitrary text, but `Request.param()` casts IDs to integers. New UUID inventory routes need a separate validated string accessor; do not break legacy integer routes.
- `server/cloud_auth.py`: shared password, password-keyed signed cookies and an anonymous `ARA_MAP_PUBLIC_EDIT` bypass. No individual actor identity exists.
- `api/index.py`: only non-GET requests and import/format paths generally require authentication. `POST /api/exportar` is explicitly exempt. This is not an acceptable catalog security boundary.
- `server/app.py`: local routing bypasses cloud authentication entirely. Public/private policy must be shared between local and cloud dispatchers; loopback alone does not establish an employee identity.
- `server/api/bases.py`, `server/repo/terrenos.py`: manual creation exists; no general terrain-edit API is registered. Repository outputs include arbitrary `extra` values. Imported currency may be NULL and must stay unknown.
- `server/api/importar.py`, `server/staging.py`: reviewed parsing and conflict handling already exist. Staged cloud data persists between workers; current preview tokens are consumed separately from business transactions. Preserve existing behavior for bases but do not reuse it as-is for an atomic, replay-safe inventory commit.
- `server/matching.py`: name/location/area heuristics are useful duplicate candidates, not authoritative cross-import identity. The existing classifier may choose one of multiple candidates. Do not automatically merge ambiguous inventory records.
- `server/api/exportar.py`: anonymous callers can currently request all rows of any supplied base/map ID; fields include address, coordinates and prices regardless of publication. The current export column allowlist limits arbitrary extras, but does not enforce listing publication.
- `scripts/migrate_cloud.py`: without explicit `--url-env`, loads `.env.local` and targets production. Do not invoke its default mode for development, including `--check`. `scripts/setup_cloud.py` likewise loads production configuration.

Exact existing surfaces to protect: GET `/api/bases`, `/api/bases/:id`, `/api/bases/:id/terrenos`, `/api/mapas`, `/api/mapas/:id`, `/api/mapas/:id/terrenos`, `/api/carpetas`, plus POST `/api/exportar`. Maps can expose old values, notes in extras, layer/source names and opaque configuration. Protect all existing internal endpoints even if today's fixture happens to contain no private fields. Import/format routes already have partial protection, but must move under the same deny-by-default policy. Historical public URLs will lead to sign-in; the new public catalog is their replacement. Surface that transition to the supervisor before release.

## Data model

Use additive inventory tables beside legacy tables. Do not reparent or rename existing terrain rows, overload a special base as the master inventory, or rewrite snapshots. One inventory record represents one independently marketed terrain/offer for this release; do not infer that similar parcels are one property. If simultaneous offers matter later, introduce an explicit parcel relationship without changing inventory IDs.

Schema responsibilities (concrete DDL details remain developer-owned):

| Table | Required responsibility/columns |
|---|---|
| `team_user` | Stable text UUID `id`, normalized unique login name, display name, password hash with algorithm parameters, active flag, credential revision, created/updated timestamps. No role column. |
| `team_session` | Hash of random session token, user ID, created/expires/revoked timestamps; never store raw tokens. Exclude from business-content backups and revoke after a restore. |
| `inventory_terrain` | Stable text UUID `id`; integer `version`; current `draft_revision_id`; nullable `published_revision_id`; nullable `published_at`; nullable `archived_at`; created/updated actor and time. Persist prior publication/event information so never-published drafts can be distinguished from unpublished listings. Publication pointer and archive state are server controlled. |
| `inventory_revision` | Immutable text UUID `id`, inventory ID, revision number, typed existing terrain columns, availability, optional confirmation dates/actors, private contacts/notes and raw source extras, optional client description, creator/time. Unique `(inventory_id, revision_number)`. |
| `inventory_event` | Append-only event UUID, inventory ID, resulting version, action, actor ID/display name at time, timestamp, before/after revision IDs, private lifecycle details and source/import reference where relevant. |
| `inventory_source` | Inventory ID, source type, original base/terrain IDs as provenance values, source filename/sheet/row when known, import hash/batch ID, adoption timestamp/actor. Preserve evidence independent of legacy base deletion; no cascade from a base. |
| `inventory_import_batch` | Text UUID, staged payload or staging reference, revision, expiry, creating actor, status, commit request key/hash and durable result. Add/skip decisions and successful inventory writes commit together. |
| `inventory_operation_result` | Durable idempotency key, operation/request hash and successful result for direct create as well as import/adoption confirmation; commit in the same transaction as the business write. |

Resolve the inventory↔revision reference cycle explicitly in DDL: create inventory with NULL pointers, insert its initial revision, then set the draft pointer in the same transaction; SQLite/Postgres FK DDL and backup restore order must support the cycle. Revision deletion is not part of release one. Validate that both revision pointers belong to the same inventory record. Consider composite foreign keys for this invariant, with supporting unique constraints, rather than relying only on application checks.

Use text UUIDs to keep generated identities portable. Do not put UUID tables in the existing adapter's generated-integer `ID_TABLES`. Extend backup/restore manifests deliberately. Typed fields allow indexed public filtering without exposing arbitrary JSON. Do not create a separate stored publication table. Join only the immutable revision selected by `published_revision_id`, explicitly select public columns, then apply the shared serializer and public eligibility predicate. Public search, counts, facets and map data must all use published fields, never current draft values. Record `published_at` when publishing; revision creation time is not publication time. Store unknowns as NULL; do not normalize them to false/zero. Avoid duplicating authoritative current draft columns on the identity row.

Retain existing field names/meaning for `terreno`, `estado`, `municipio`, `direccion`, `superficie_m2`, `superficie_ha`, `afectaciones_pct`, `afectaciones_m2`, `asking_price`, `asking_m2`, `moneda`, `lat`, `lon`. No implicit FX conversion. Preserve unconfirmed legacy currency as NULL; priced publication requires explicit USD or MXN. Do not relabel imported values. Reject nonfinite numbers and invalid coordinate pairs. Existing XLSX precision, safe literal text and snapshot currency behavior are regression requirements.

Availability values fixed by supervisor contract v1: `unknown`, `available`, `negotiation`, `sold`, `withdrawn`. These are supervisor implementation defaults pending future business parameters. The public active catalog includes `available` and `negotiation`; sold/withdrawn are removed when their revision is explicitly published. Unknown blocks initial publication pending confirmation. Archive removes public access immediately and retains history. Changing a draft to sold must show a conspicuous pending-publication warning; saving it alone leaves the last published status unchanged.

Confirmation dates are distinct from edit timestamps. Ordinary edits never refresh price/availability confirmation automatically. Use separate optional price/availability confirmed-at/by fields; actors are always private. Configurable stale-age policy is deferred; first-release attention flags may say “not confirmed” without inventing a business SLA.

## Authentication and authorization

Supervisor-selected approach: individual username/password accounts in the existing Python service, using a vetted password KDF available in the runtime (e.g. standard-library scrypt with per-user random salts and benchmarked parameters), server-side revocable sessions, and no external identity-provider dependency for this release. Verify implementation/runtime parameters before coding. Store no plain passwords. Enforce login throttling across workers, generic login failures and bounded request sizes. Do not build password recovery by security question or public account signup.

Provision the initial 1–3 accounts with an explicit local operations command against a named target, entering passwords through a secure prompt, never shell arguments/output. Password reset/deactivation use that same operations path initially; every ordinary team account retains identical product capabilities. This operational provisioning is not a product administrator role. Hand over the runbook. This is operational account setup, not a new user-facing management feature. Implement this selected approach; provider replacement is outside this release.

Successful login returns a random opaque token in a Secure/HttpOnly/SameSite cookie and derives actor identity server-side on every request. Use a distinct development cookie policy only on an explicit loopback test server; do not weaken production cookies. Logout revokes the server-side session. Credential changes and deactivation invalidate existing sessions. Never accept actor IDs from request JSON. Disable/remove `ARA_MAP_PUBLIC_EDIT` as a production inventory authentication bypass. Old shared-password cookies must not grant new inventory access.

Apply authentication and route classification in shared server code, not only the Vercel entry point. The exact anonymous API allowlist is GET `/api/config`, GET `/api/session`, POST `/api/login`, POST `/api/logout`, GET `/api/publico/terrenos`, and GET `/api/publico/terrenos/:id`. Logout revokes a session if present and is idempotent. Safe static assets remain public; every other API route requires sign-in, including unknown routes before a fallback can occur. Every signed-in team user can edit every inventory record. Shared drafts/import batches may be accessed by all team users; do not accidentally add owner-only restrictions. Authentication and CSRF/origin validation are independent: validate same-origin mutations and reject cross-site unsafe requests. Do not reveal user lists, password hashes, sessions or stack traces in public errors.

## API contract

Implement the frozen envelopes, fields, paging/filter rules and defaults in `INTEGRATION_DECISIONS.md`; coordinate frontend fixtures before wiring. Internal create/detail/patch/action responses are `{terreno: InternalTerrain}`; lists are `{terrenos:[],total,next_cursor,facets}`. Internal metadata includes `publication_state`, `public_visible`, `has_pending_changes`, `attention`, IDs/version/pointers, `archived_at`, and mutable fields under `draft`. Preview is `{id,version,revision_id,preview:true,terreno:PublicTerrain,blockers:[],warnings:[]}`. New routes use UUID strings; old routes keep integer IDs. Authenticated internal responses use `Cache-Control: no-store`. Public GETs initially also use `no-store` to make publication visibility straightforward; optimize only with demonstrated invalidation. A successful publish/unpublish must affect the next subsequent API read; UI refresh/revalidation is separately tested.

| Method/path | Contract |
|---|---|
| `POST /api/login` | `{username,password}`; sets session cookie; generic 401 failure; rate-limited. |
| `POST /api/logout` | Revokes current session and clears cookie. |
| `GET /api/session` | Anonymous `{authenticated:false}` or `{authenticated:true,user:{id,display_name}}` for the current cookie. No roles. |
| `GET /api/inventario/terrenos` | Authenticated paginated draft-based list; existing supported field filters plus publication/availability/attention. Include `version`, publication state, public visibility and `has_pending_changes`. |
| `POST /api/inventario/terrenos` | Validated draft fields, no ID/publication/actor input. Requires `Idempotency-Key`; creates stable ID + first revision + event + durable successful result atomically. Incomplete drafts allowed. |
| `GET /api/inventario/terrenos/:id` | Full internal draft, current version, publication metadata, safe concurrency context. |
| `PATCH /api/inventario/terrenos/:id` | `{expected_version, changes}`; strict mutable-field allowlist. Creates new immutable draft revision, increments version and records actor atomically. |
| `GET /api/inventario/terrenos/:id/historial` | Authenticated paginated events/revisions. Never anonymous. |
| `GET /api/inventario/terrenos/:id/vista-publica?revision_id=…` | Authenticated exact-revision public projection plus validation errors and `preview:true`; never publishes. Public allowlist identical to catalog serializer. |
| `POST /api/inventario/terrenos/:id/publicar` | `{expected_version, revision_id}`; revision must equal saved draft pointer. Validate, set published pointer and publication timestamp, increment version and record event in one transaction; public projection is derived on reads. No implicit saving. |
| `POST /api/inventario/terrenos/:id/despublicar` | `{expected_version}`; clears published pointer atomically, keeps drafts/history and prior publication evidence. |
| `POST /api/inventario/terrenos/:id/archivar` | `{expected_version}`; removes public access, retains data/history. |
| `POST /api/inventario/terrenos/:id/restaurar` | `{expected_version}`; restores internal draft only; never republishes automatically. |
| `POST /api/inventario/duplicados` | Candidate terrain fields; returns candidate IDs/reasons for manual comparison. Authenticated, read-only, no implicit merge. |
| `POST /api/inventario/importaciones/vista-previa` | Existing supported upload/mapping pipeline; produces expiring batch, row findings, source hashes and current duplicate-candidate evidence. No inventory write. |
| `POST /api/inventario/importaciones/:id/confirmar` | Batch revision + `Idempotency-Key` header + explicit `add`/`skip` row decisions only. Transactionally creates drafts and records source/history/result. No master-record bulk updates or merges. |
| `POST /api/inventario/adopciones/vista-previa` | Selected existing base/terrain IDs; private preview of source versions/hashes, duplicates and proposed draft records. |
| `POST /api/inventario/adopciones/:id/confirmar` | Same reviewed transaction semantics as import; preserves original bases/maps. Never public automatically. |
| `GET /api/publico/terrenos` | Public projected list/map data and documented paging/filter metadata from eligible published records only. |
| `GET /api/publico/terrenos/:id` | Same allowlist for one eligible published record; uniform 404 for missing/draft/unpublished/archived/ineligible. |

Return structured errors using existing `{error, detalle}` conventions. Proposed `detalle.code`: `conflict`, `validation_failed`, `preview_expired`, `duplicate_review_required`. HTTP 409 on stale expected version, 422 on validation errors, 410 on expired import preview, 401 on absent/invalid session. Conflict response may contain current version/current draft only for authorized employees; frontend retains unsaved local values. Record-level duplicate warnings must be acknowledged or resolved when creating; acknowledgements are reasons, never automatic identity merges.

Public projection allowlist is exactly `id`, `revision_id`, `terreno`, `estado`, `municipio`, `direccion`, `superficie_m2`, `superficie_ha`, `afectaciones_pct`, `afectaciones_m2`, `lat`, `lon`, `asking_price`, `asking_m2`, `moneda`, `price_on_request`, `availability`, `public_description`, `published_at`. Values come only from the selected published revision plus publication metadata. Private: contacts, notes, raw `extra_json`, source filename/row/base IDs, import findings, history, responsible/editor identities and all auth data. Do not concatenate source text into client description automatically. No unclassified attachments or external document URLs enter public payloads. The public serializer must explicitly select these fields, not copy a full row and remove a few fields.

Publication gate fixed by supervisor contract v1: nonblank name, valid map coordinate pair under existing geographic validation, positive area, known availability, and either a positive asking amount in explicit USD/MXN or `price_on_request:true`. Price-on-request and asking amounts cannot coexist; return validation errors rather than suppressing contradictory amounts. Dates and missing optional fields produce attention warnings initially; future business requirements may refine these defaults. `price_on_request` is an explicit new Boolean, not inferred from absent prices. Retain warnings for inconsistent total/unit prices without replacing source amounts with calculated values; expose those warnings in authenticated preview.

Preserve existing staff exports and snapshots behind sign-in. Disable anonymous legacy export; no new public export route is required for release one. If retained, a public export must select current eligible published-revision projections, never accept a base/map ID and never trust client-provided row contents or claimed publication state.

## Atomicity, concurrency and retries

Every save, publication change and archive/restore performs a compare-and-set on `inventory_terrain.version` inside the same transaction as the revision/pointer/history write. Zero updated rows means 409; roll back all coupled changes. Two employees editing version 7 cannot both succeed. Publication checks both expected version and reviewed revision ID to stop publishing someone else's new draft accidentally. Postgres's current broad advisory lock does not replace version checks, because stale browser state spans transactions.

A private-note change also increments the same record version in release one; this deliberately favors correctness over field-level merge complexity. History describes the true actor/time and prior/next revision. Require `Idempotency-Key` for direct creation and inventory import/adoption confirmation. Repeat requests must not duplicate terrain or import rows. Store success and idempotency-key result in the same business transaction; same key/body returns the original result, same key/different body conflicts. Recheck batch revision, source hashes and duplicate candidates at confirmation; stale decisions return 409 with no partial inventory writes. Do not consume a staging token irreversibly before the inventory transaction when designing the new path. A repeated independent import still needs duplicate review; idempotency is not an automatic identity system.

## Migration, adoption and recovery

1. Develop on disposable SQLite fixtures with cloud variables explicitly absent. Read source only until a named nonproduction Postgres test target is available. Do not inspect `.env.local` or connect to production for planning/development.
2. Add schema version 8 (or next unused version at merge), both SQLite and Postgres migrations, idempotent repeat tests, fresh initialization parity, indexes and backup manifests. Preserve unknown currencies and existing IDs exactly. Do not run schema changes on an ordinary cloud request.
3. Rehearse upgrades on synthetic/approved copies that include pre-v7 currency rows, nested saved maps, repeated names, arbitrary private extras and existing import metadata. Capture counts and stable field-level digests before/after. Existing base/terrain/map tables must be unchanged except explicit schema additions.
4. Keep schema migration separate from inventory adoption. An empty new inventory is acceptable after schema migration; no old row becomes public automatically. Employees select genuine inventory sources, compare duplicates, and explicitly adopt into drafts. Adoption needs durable source hashes and an idempotent result. Unselected examples/historical bases stay internal.
5. SQLite: take a consistent backup via `sqlite3.backup`; demonstrate restore to a separate file. Postgres: extend logical backup and restore support for all inventory/business/auth-account data with correct cyclic-FK ordering and exact sequence handling. Session rows are excluded/revoked. Encrypt/restrict backup storage containing password hashes and contacts. Existing `workspace_backup` inside the same DB alone is insufficient evidence of recovery from loss of that database; release needs an approved independent recovery artifact or verified service recovery capability.
6. Demonstrate restore in a named disposable target, compare counts/digests, log in with test identities, verify no anonymous private data and reopen unchanged snapshots. Reverting code is not a data rollback; any production restoration must account for writes after cutover. Prefer additive rollback with new writes retained; document the actual cutover/recovery decision separately.
7. Produce migration/adoption manifest, reviewed sample reconciliation, recovery evidence and deploy prerequisites. Supervisor owns release recommendation; this packet authorizes no live execution.

## Implementation order and handback

B1: shared route security classification, individual identity/session design and synthetic authorization tests. B2: additive schema/repositories, atomic draft saves/history and concurrency. B3: published-pointer projection and preview, public query routes and allowlist tests. B4: bulk import/adoption path with duplicate review and idempotency; connect existing parser/mapping modules. B5: migration/restore rehearsals and frontend integration evidence. Backend and frontend agree API examples after B1/B2 design, before broad UI wiring.

Hand back: changed-file list; exact schema/API decisions; test commands/results; synthetic data provenance; local run instructions; 100-terrain/three-session timings; remaining risks; migration and recovery evidence; no secrets or private customer data in artifacts. Explicitly distinguish implemented code, locally verified behavior, disposable-Postgres verification and live production status.

Required acceptance cases:

- Two distinct team users can perform identical actions on each other's records; actor identity cannot be forged.
- Save persists after server/session restart and never changes a published revision; explicit Publish changes the next public read. Preview matches exactly what is published.
- Every legacy GET and export surface is denied anonymously; private sentinel values cannot be retrieved via public list/detail/query/error/download or draft-ID guessing.
- Publish, unpublish, archive, restore and simultaneous draft edits enforce expected versions; interrupted transactions leave no partial event/pointer/revision.
- Repeat import/adoption does not duplicate rows; ambiguous duplicates require a choice; all created records are drafts; stale duplicate evidence cannot be accepted; confirmation supports add/skip only, and existing inventory is never bulk-overwritten.
- Currency, mixed-currency filters, NULL currency, decimal per-m² values, safe XLSX text, old saved snapshots and legacy imports retain established behavior.
- Attention flags distinguish missing confirmation from ordinary last edit; duplicate candidates never establish identity automatically.
- Both database engines migrate fresh and old fixtures twice safely, restore successfully, and retain all existing rows/snapshots. Public query pagination/map coverage returns all 100 representative published records without duplicates or omissions; also test 251 matching records to cross the maximum-250 page boundary. Use contract-v1 default/max page sizes, stable ID cursor, complete authorized facets and coherent map/table assembly.

Remaining future business inputs: public visitor-load target, operational account-provisioning contact, and any eventual stale-confirmation threshold. Availability, publication gate, auth approach, envelopes, route allowlist, add/skip-only inventory bulk and idempotency are frozen by supervisor contract v1. Do not reopen them as blockers. No further search characteristics or staff roles are needed for the inventory foundation.

Integrated delivery rule: authentication, catalog and legacy-route protection cut over together. Stage 1–3 work remains local and incomplete until acceptance; never deploy a partial stage. No application edits are authorized by this briefing assignment.

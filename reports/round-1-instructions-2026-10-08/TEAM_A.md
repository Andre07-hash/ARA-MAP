# Team A — packet 1A: combined baseline and master-record backend

Read START_HERE.md and ATTACHMENT_CONTRACT.md in this instruction commit first. Your corrected P2 dependency is accepted as recorded in P2_ACCEPTANCE.md. This replaces the completed A-2 correction assignment, not its accepted invariants.

## Deliver two reviewable checkpoints

**First:** assemble, verify and publish the baseline-only branch/PR using the exact protocol in START_HERE.md. It is the early handoff to B. Include the pinned module imports and their tests/reports without changing their behavior. Name every conflict resolution; if resolution changes a contract, request review of that narrow issue before declaring the checkpoint ready. Do not include the memory prototype or parked Excel work.

**Second:** on your separate feature branch, implement the backend below. This packet is backend only; custom-column management/editing and the employee grid are 2A, file handlers are 2B, DTO/file-widget mounting is 3A. Do not widen this into a frontend or release task.

## Record contract

One canonical `inventory_terrain` UUID; zero or one current `base_id`. Admins can work globally and with unassigned records; operators can create/read/edit only in assigned active work bases. Follow the approved workspace contract at `reports/workspace-contract-2026-10-07/SHARED_CONTRACT.md` from the supervisor instruction branch; this packet preserves its permissions and transfer semantics.

Core business fields are all optional. Persist a blank record with `{}` business content. Require only technical request identity/base context/idempotency, never a name, location, area, price, comment or file. The core mapping is:

| Column | Existing/domain field |
|---|---|
| Tipo de terreno | `tipo_terreno`, nullable free text; choose/document a bounded length |
| Nombre de terreno | `terreno` |
| Estado / Municipio | `estado` / `municipio` (Estado is the geographic state) |
| Superficie / HA | `superficie_m2` / `superficie_ha` |
| Afectaciones % | `afectaciones_pct` |
| Asking price / Asking $/m2 | `asking_price` / `asking_m2` |
| Comentarios | private `notas_internas` |
| Archivos / KMZ | separate attachment resources, not writable terrain cell fields |
| X / Y | `lat` / `lon`, respectively |

Missing values stay null. Remove the draft-only requirement that a manually supplied asking amount must have a currency; preserve unknown `moneda = null` explicitly and existing supported currency semantics. Do not guess MXN, convert prices/areas, derive HA or asking/m², swap coordinates, deduplicate blank records by name, or relax publication requirements. Retain finite/type/range validation and current warning semantics. Expose/save `tipo_terreno` without dropping any existing revision fields, provenance, `custom_json`, confirmation stamps or published pointers.

## API surface and authorization

Retain existing single-terrain detail/PATCH/history paths and response conventions. Add:

- `GET /api/maestra/bases/:bid/terrenos` — scoped list, `maestra.ver` plus `require_base`.
- `POST /api/maestra/bases/:bid/terrenos` — scoped blank or populated create, `maestra.editar`, fresh base authorization inside the write transaction; flat business-field body as existing create, no client-supplied actor or ownership override.
- Existing `GET /api/inventario/terrenos` remains admin aggregate; replace its whole-inventory Python filtering with bounded SQL queries. Existing global create remains admin-only and creates unassigned records. Do not expose the global route to operators simply to reuse it.
- `POST /api/inventario/terrenos/:id/archivar` and `/restaurar`, body `{expected_version}` — `maestra.archivar`, action-specific archived-state checks.
- `POST /api/inventario/terrenos/:id/transferir`, body `{expected_version, base_id}` — admin-only `bases.gestionar`; `base_id` is an active destination UUID or null for unassignment. Include a read-only transfer preview operation (document its exact path/response) for the later confirmation UI.

Declare every new route's capability in the actual shared registry. Authenticate real requests, then use `db.escritura()` with `auth.reverificar_terreno(..., exclusivo=True)` or `reverificar_base` as applicable before writes. Scope-changing mutations participate in P2's locking protocol; keep its advisory lock and controlled busy behavior. Resolve access before returning row-specific validation/conflict contents. Missing and unauthorized IDs are indistinguishable.

Creation remains idempotent. Isolate keys by actor and operation/base using the existing result table; include the normalized request/base in the hash. A guessed/reused key from another actor must never reveal or return that actor's record. Replays must reauthorize the current referenced record before serialization, including after transfer or grant loss; do not replay a private stored DTO blindly. Prove same-key retries create exactly one terrain/event and changed-body reuse conflicts. The same protections apply when retaining the legacy admin create endpoint.

## Queries and scale

Authorization, search, filters, sorting, counts and facets run in SQL before serialization. Preserve documented filter semantics and add base/unassigned and type filtering to the admin aggregate as appropriate. Lists return the existing `{terrenos, total, next_cursor, facets}` envelope, with bounded records and no geometry vertex arrays or file credentials. Keep default 100 and set terrain-list maximum 200 (not a blanket unrelated history-limit change). Use an allowlist for sort/filter identifiers, parameterized values, deterministic ordering with stable ID ties and documented cursor behavior. Invalid/reused cursors must not circumvent scope. Do not promise a frozen multi-request snapshot while concurrent edits are occurring.

Do not load every record or collect all browser pages to filter; eliminate N+1 row hydration/history queries. Use the same authorization/filter predicates for totals and facets, documenting any intentional self-excluding facet behavior. Preserve existing API behavior except explicit approved changes; update contract tests where the previous 250-row limit or draft currency requirement changes.

This packet does not expose/filter arbitrary cross-base custom fields or implement the live KMZ descriptor integration. Preserve custom values and stored attachments; keep current XY filters honest until the KMZ-aware DTO integration packet. Document that remaining step, rather than returning misleading new `ubicacion` placeholders.

## Archive, transfer and history

- Archival is reversible and shared; preserve stable ID, revisions, files and active layout. Restoring an archived terrain cannot reopen its archived base. Ordinary edits/uploads remain disallowed on archived terrain.
- Operators cannot change public visibility indirectly. If a published terrain's archival would alter public content, deny operator archival and require admin action. No publish/unpublish feature is added here.
- Transfer is one conflict-checked transaction: current ownership, new revision/base history, record version and audit change together. No record/file duplication; attachment decisions and terrain-cell concurrency stay independent.
- Check the current source and active destination consistently with P2; a transfer and base archival/grant change must serialize safely. Record old/new base and actor. Source-only users lose access immediately; stale edits cannot bypass the final scope check.
- Preserve base-local custom values under their original stable definition IDs. Do not remap by name. Operator DTOs and all history/conflict/replay responses expose only current-base custom definitions/values, not previous-base labels, hidden values or embedded history diffs. Admin full audit remains available. Moving back reveals retained values again. Source-only membership must not grant access to the moved core record.
- The transfer preview identifies destination access and columns that become hidden, without exposing credentials; the mutation rechecks version and permissions independently of the preview.

Prefer the existing schema. If a real schema gap emerges, put the smallest migration/test/release-note prerequisite in a separate draft checkpoint and request its review. Do not reinterpret P1 constraints or change B's storage/parser interface to accommodate record code.

## Acceptance

Use actual HTTP dispatch and fictional sessions, with the same matrix on SQLite and disposable Postgres:

1. Zero-grant, one-base and multi-base operators; two admins; active/archived bases; assigned/unassigned and archived terrains. Blank create succeeds where authorized and nowhere else. Core optional values round-trip, including amount with unknown currency and type alone.
2. Idempotency scope/replay cases above; two simultaneous cell edits give one accepted version and one controlled conflict; no duplicate audit or partial revision. Body-supplied role/base/actor cannot escalate access.
3. Archive/restore/transfer, both race orders with an edit or grant/base change, retained file/geometry references, stable ID, and custom-value/history redaction on transfer and transfer back. Use seeded valid attachment graphs; no dependency on unfinished B lifecycle functions.
4. Inaccessible rows never contribute to totals, facets, history, cursor results or error DTOs. Sorting/null/case/accent semantics have SQLite/Postgres parity. Injection-shaped query values remain values.
5. Synthetic 25,000-record inventory, 3,000-record base, five editing sessions: report query count, response size and latency for list/search/filter/count operations, plus plans/index use where relevant. Verify bounded hydration and five-session conflict outcomes. This is a backend measurement, not a whole-product capacity claim.
6. Preserve existing public allowlists, role/session tests, backups/migrations, legacy admin behavior and Python 3.9. Run combined suite/JS/lint/types and green CI on each reported checkpoint.

Report under `reports/team-a-master-record-backend-2026-10-08/START_HERE.md`, including request/response examples, API matrix, base manifest, measurement method/results and follow-ups reserved for 2A/3A. Stop for review. No merge or deployment.

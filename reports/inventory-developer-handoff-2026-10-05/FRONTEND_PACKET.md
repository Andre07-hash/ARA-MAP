# Frontend developer packet — shared terrain inventory

Prepared 2026-10-05. Scope: implementation instructions only; no application changes were made for this packet. Aligned with `INTEGRATION_DECISIONS.md` contract v1, which overrides provisional details in specialized packets. Read that document and `START_HERE.md` first.

## Product contract

Keep the visual language, map navigation, table, imports, saved maps, and mixed-currency safeguards already demonstrated. Extend the existing vanilla JavaScript DOM components and Leaflet integration; no framework rewrite. All new interface text is Spanish. One authenticated team user type has identical capabilities; no boss/editor/admin roles, approval queues, ownership restrictions, or role-management page. Anonymous visitors see only the approved public catalog. Individual accounts exist for attribution.

Release outcome: any of 1–3 authorized users can create and maintain at least 100 terrain records directly, save drafts, preview, publish, unpublish and archive; visitors can browse the current published map/table/details. Excel adds reviewed draft records. Include modest attention and duplicate review surfaces. Future AI search, new shortlists/saved searches, new PDF sheets, presentation mode, client accounts and enhanced comparisons are deferred. Preserve existing comparison/saved-map features internally.

## Source evidence and extension points

| Existing file | Observed behavior | Assignment |
|---|---|---|
| `web/components/app.js` | Shell, shared-password dialog, global base/map loading, latest-base landing, persistent Leaflet workspace and filters | Split public/internal data loading; inventory default; identity/session display; coherent navigation. Preserve persistent map and filter nodes. |
| `web/lib/store.js` | Single `terrenos` array, base/map pointers, filters and selected ID | Add explicit route/data context and lifecycle view; avoid mixing private records with public preview/catalog state. |
| `web/lib/api.js` | Central request wrapper already carries HTTP status and `detalle`; base-bound create/import APIs | Add inventory/session/public/preview/history methods after contract freeze; retain structured validation/conflict details. |
| `web/components/terrain/TerrainDetail.js` | Renders all `extra`, source row/ID and import findings; no edit controls | Extract reusable public facts renderer; separate authenticated metadata/actions/history. Do not pass full internal objects to the public renderer. |
| `web/components/terrain/TerrainTable.js` | Shared filtered list, keyboard-selectable rows, mixed-currency sorting guard | Retain public columns; internal status/attention columns optional by context. |
| `web/components/terrain/FilterRail.js` | Persistent inputs preserve caret/IME; state/municipality/area/price filters; long option lists currently truncate | Reuse filtering; make all values reachable through expand/search; add internal-only lifecycle/attention filtering. |
| `web/components/map/MapCanvas.js`, `Legend.js`, `BasemapSwitcher.js` | Existing map navigation and area circles | Feed correct dataset; preserve scale/geometry disclaimers, selection, zoom, basemap and currency behavior. |
| `web/components/bases/ImportDialog.js`, `web/components/import/ImportAssistant.js`, `AssistantViews.js` | Reviewed import, server preview revisions and conflict choices; create/append base modes | Add explicit inventory destination or reviewed adoption flow with backend; never treat an ordinary import as a publication action. |
| `web/components/bases/BaseGallery.js`, `web/components/maps/MapGallery.js`, `OverlayBuilder.js` | Existing source collections and dated maps/comparisons | Keep authenticated navigation and source/snapshot workflows; label dated copies without implying live inventory. |
| `web/styles/global.css`, `controls.css`, `panels.css`, `tokens.css` | Existing styling; below 960px the filter rail is hidden | Supply reachable mobile filters and maintain brand/layout, rather than just hiding the rail. |
| `web/components/ui/dialog.js`, `toast.js`, `web/lib/dom.js` | Existing UI primitives | Reuse keyboard/dialog patterns and text-safe DOM rendering. |

Create small modules as needed: `components/inventory/TerrainEditor.js`, `PublicationPreview.js`, `TerrainHistory.js`, `AttentionList.js`, `DuplicateReview.js`, and a route/session helper. Exact filenames can vary if responsibilities remain clear. Do not expand `app.js` into all form/conflict logic.

## Public and internal navigation

Use explicit bookmarkable context (simple hash routing is compatible with this application): public catalog, internal inventory, internal bases, internal saved maps, internal terrain edit. Backend endpoints remain the security boundary regardless of route. Anonymous startup must fetch only session/config plus public list/detail; it must not run today's `loadIndex()` against bases/maps/folders. Signed-in startup defaults to `Inventario`; preserve `Bases` and `Mapas guardados` in the team workspace, with `Ver catálogo público` reachable.

When a signed-in user opens the public context, fetch the actual public response. Do not locally hide fields from already-loaded internal records and call that public mode. On logout/session expiry, cancel pending private requests, clear internal datasets, draft/private detail DOM and caches, and return to public data. Browser Back and late request responses must not repopulate private content. An unauthorized deep link offers sign-in and a safe return path. No contacts/notes in URL, analytics, persistent browser storage or public error text.

Public screen: map/table toggle, existing supported filters, count, selected public terrain detail and sign-in. No bases, saved-map catalog, internal attention list or import controls. Public exports are absent in release one; the server must also deny anonymous legacy export. Internal exports and historical maps remain subject to authenticated API enforcement.

## Inventory and editing

Default inventory shows active draft/published/unpublished records; archived records are reachable using an explicit filter. Preserve filter/search/selection/viewport after a successful save. Represent server authoritative updated data and return the user to their context; avoid reopening a base and resetting their work. Show stable company ID rather than spreadsheet row as record identity.

Editor uses persistent form state separate from list rerenders. Sections: identification; location; size; commercial terms; verification dates; private contacts/notes. Use existing canonical fields and lifecycle additions agreed with backend, not invented industry search fields. Existing currency, total/per-m² amounts, original units and imported values must survive round trips. Derived amounts must be labeled; never silently convert currency, turn unknown into zero/no, or infer a verified boundary from the map circle. Drafts may be incomplete. Server publish validation drives blocking field messages.

Actions: `Guardar borrador`, `Vista previa`, `Publicar`; secondary `Retirar del catálogo` and `Archivar` as applicable. Unsaved form changes trigger a local leave/discard guard. Network errors retain entries; disable only in-flight controls. Successful save is announced with record/revision confirmation; uncertainty after a failed response triggers a reread, not a blind repeated create. Idempotency is a server/client contract for creating/importing.

Location correction happens directly in this form. Update the existing `Sin coordenadas` instruction: it currently tells the user to change the spreadsheet. Require clear latitude/longitude labels and coordinate validation; point picking is optional if an existing safe primitive is straightforward, not a prerequisite for release.

## Publication states and preview

| Situation | Team wording and behavior | Public behavior |
|---|---|---|
| New saved record | `Borrador · No publicado` | Not retrievable |
| Published, no pending changes | `Publicado` with publication date | Current published revision |
| Published, draft edited | `Publicado · Cambios pendientes`; conspicuous reminder if price/availability changed | Last published revision remains visible |
| Unpublished | `No publicado`; retained editable record/history | Removed from list and direct detail |
| Archived | `Archivado`; hidden from default internal list, retained history | Removed; archive must atomically withdraw public visibility |

`Vista previa` renders the authenticated server-produced public projection of the saved draft using the same presentation components as actual public detail. It must not show arbitrary imported extras or staff metadata. Clearly mark `Vista previa · Aún no publicada` and its saved revision. If the form is dirty, require saving/reviewing that draft first. Preview receives publish blockers/warnings; clicking `Publicar` submits the exact reviewed version and revision ID. A server conflict returns to review; never publish another user's intervening edit silently. Keep private comments separate from descriptions explicitly intended for the public.

Unpublish and archive confirmations name the terrain and explain the public effect; all authorized users have these actions. No manager approval. Show `Restaurar` for archived records; restoration returns an unpublished state and never silently republishes. Sold/withdrawn published revisions must not remain in the available catalog; do not derive this from a merely saved private change.

## Concurrent edits and history

Every mutation sends the expected server revision. A 409 conflict preserves the user's unsaved values and shows latest server values with changed fields, actor and time where available. Offer `Revisar cambios` and `Recargar versión actual`; require deliberate field reconciliation and resubmission with the new revision. Do not automatically overwrite or silently retry with a fresh revision. If latest version is archived/unpublished while editor was open, present that lifecycle conflict clearly.

`Historial` is an authenticated chronological panel with action, actor, timestamp and before/after field values. Distinguish save from publish/unpublish/archive/import. Private content in history is available to every authorized user but never public. History pagination can be simple; handle empty/error/retry states. Show confirmation dates separately from modification time.

## Needs attention and duplicate review

`Necesita atención` is a working list/filter within inventory, with count and per-record reasons supplied by the server: missing required publication data, never-confirmed price/availability, validation issues, unresolved possible duplicate, and outdated confirmation only if a business-approved threshold exists. No invented 30/60/90-day stale policy. Opening a row focuses the relevant edit section. Attention does not by itself silently unpublish a record; server lifecycle rules decide public visibility.

Duplicate warnings show candidate IDs, name/location/area and server evidence such as same source ID or nearby coordinates. Options are deliberate: open existing terrain, skip this addition, or continue creating a separate record after acknowledgment. Never equate same name with same parcel, auto-merge, or overwrite existing data. Keep input while reviewing. If commercial offers are ambiguous, retain separate records/source evidence and route the ambiguity to the supervisor instead of inventing a parcel-offer redesign.

## Excel bulk additions and existing inventory

Reuse existing analysis/correction/preview mechanisms and frozen preview revision semantics. Add a clear destination label `Inventario · Nuevos borradores`; do not require users to create a temporary base for daily maintenance. Existing sources use the separate reviewed adoption operation `Incorporar al inventario`, with reconciliation; ordinary new inventory imports use the explicit inventory destination in the existing assistant pipeline. Preserve source provenance and source bases/maps.

Before commit show create/skip/duplicate/unresolved counts, field errors, source file and currency interpretation. Review suspected existing master records, not only duplicates within the current file/base. Import cannot publish records and cannot overwrite published versions. Inventory confirmation accepts only `add` and `skip`; possible duplicates become distinct new records only after explicit acknowledgment. No inventory bulk update/merge/overwrite. Known already-adopted source records link to the existing master ID by default. Bulk replacements or spreadsheet sync are outside this release; preserve established legacy reviewed append behavior within authenticated bases. A rerun/retry must not duplicate committed records. After commit show server counts and links to new draft records/attention list. Cancellation must leave inventory unchanged.

## Frozen backend contract and wiring

`INTEGRATION_DECISIONS.md` contract v1 controls routes, envelopes and validation. Use these routes from `BACKEND_PACKET.md` as corrected there; do not choose alternatives during implementation.

| Operation | Route and payload |
|---|---|
| Session | GET `/api/session`: `{authenticated:false}` or `{authenticated:true,user:{id,display_name}}` |
| Login/logout | POST `/api/login` with `{username,password}`; POST `/api/logout` is idempotent |
| Public list/detail | GET `/api/publico/terrenos`; GET `/api/publico/terrenos/:id` |
| Internal list/create/detail | GET/POST `/api/inventario/terrenos`; GET `/api/inventario/terrenos/:id` |
| Save draft | PATCH `/api/inventario/terrenos/:id` with `{expected_version,changes}` |
| Preview | GET `/api/inventario/terrenos/:id/vista-publica?revision_id=…` |
| Publish | POST `/api/inventario/terrenos/:id/publicar` with `{expected_version,revision_id}` |
| Lifecycle | POST `/api/inventario/terrenos/:id/despublicar`, `/archivar`, `/restaurar` with `{expected_version}` |
| History | GET `/api/inventario/terrenos/:id/historial` |
| Duplicates | POST `/api/inventario/duplicados` with candidate terrain fields; read-only |
| Import | POST `/api/inventario/importaciones/vista-previa`; POST `/api/inventario/importaciones/:id/confirmar` |
| Adoption | POST `/api/inventario/adopciones/vista-previa`; POST `/api/inventario/adopciones/:id/confirmar` |

Internal detail/create/patch/action responses are `{terreno: InternalTerrain}`. Metadata includes `id`, `version`, `draft_revision_id`, `published_revision_id`, `publication_state`, `public_visible`, `has_pending_changes`, `archived_at`, `draft`, `attention`, and internal change metadata. Editable values live under `draft`; server metadata is never editable. Version is the concurrency counter; a revision ID identifies immutable content. Distinguish dirty form inputs from server `has_pending_changes`. For a published sold/withdrawn revision with `public_visible:false`, show `Fuera del catálogo · Vendido` or the matching withdrawal label, not just `Publicado`.

Preview response is `{id,version,revision_id,preview:true,terreno:PublicTerrain,blockers:[],warnings:[]}`. Publish sends the exact reviewed `{expected_version:version,revision_id}`. A changed draft requires another review. Do not introduce a separate preview token or implicit save.

Public DTO contains only contract v1's explicit fields, including `price_on_request`. Render that as `Precio a consultar`; null prices are never zero. Price-on-request and asking amounts cannot coexist for publication: present the validation error rather than silently clearing values. Old prices remain in history. Derive map placement from public coordinates; do not depend on private `ubicado` or import findings. Availability labels map `unknown`, `available`, `negotiation`, `sold`, `withdrawn` to Spanish; negotiation is visibly labeled publicly.

Both list routes return `{terrenos:[],total,next_cursor,facets}`, default page size 100, maximum 250. Assemble **all pages of the selected query** before labelling map/table/count complete; both views consume the same assembled result. Keep explicit loading state, cancel outdated searches, reject late-response replacement, clear accumulated private pages on logout and revalidate after writes. Facets cover the complete authorized candidate set and must not be recomputed from one page. Use server cursors. Include a 251-matching-record test in addition to the 100-record business baseline.

Public query vocabulary is `q`, `estado`, `municipio`, `area_min_m2`, `area_max_m2`, `moneda`, `price_min`, `price_max`, `price_basis` (`total` or `per_m2`), `cursor`, `limit`. Internal adds `publication_state`, `availability`, `attention`, `include_archived`. Do not send private-field selectors or invent business characteristics. New inventory/catalog monetary controls select one explicit USD/MXN currency and one price basis, then a range; records of other/unknown currencies do not enter that monetary result. Preserve legacy base/map filter behavior separately. Do not silently collapse two legacy price ranges into one API range. Confirm geographic multiselect serialization with the supervisor if fixtures do not specify it.

Require an `Idempotency-Key` header on direct create and import/adoption confirmation. Generate a key per logical attempt, preserve it across uncertain retries, and never reuse it with a different body. Successful retry returns original IDs/counts; a genuinely new request receives a new key. Inventory confirmation decisions are `add` and `skip` only and bind to the reviewed batch revision. There is no inventory bulk update mode.

Use `{error,detalle}` handling: 401 expires the private session, 404 is uniform absent public detail, 409 preserves work for conflict/review, 410 asks for new expired import preview, 422 maps field validation. Errors have Spanish summaries. Relevant APIs use `Cache-Control:no-store`. Open public pages refresh on explicit reload and visibility/focus revalidation; no push/polling work or promises of instantaneous idle-page updates.

## Delivery slices and acceptance evidence

1. Agree contract/DTO fixtures; public/internal routing and clean session transition. Demonstrate anonymous requests never include private bases/maps/fields and no private content resurfaces after logout/back.
2. Inventory read/create/edit with lifecycle metadata, local draft retention and conflict review. Demonstrate user A creates, user B edits without re-upload, all three sessions have identical actions, conflicting user C cannot silently replace changes.
3. Server-projection preview and explicit publication, withdrawal/archive/history. Demonstrate saved draft leaves public revision unchanged; Publish changes it within agreed freshness; private sentinel strings never appear publicly; old preview cannot publish new revision.
4. Import into drafts, duplicate/attention review, preservation of legacy imports/snapshots/currency. Demonstrate record-count reconciliation and idempotent repeat submit on a synthetic workbook.
5. Independent QA handoff with desktop and mobile evidence. At minimum use 1440×900, 768×1024 and 390×844. Exercise 251 matching records across the page boundary and prove map/table/count agreement. On phone, `Filtros` opens an accessible drawer/dialog containing all search controls; preserve filter state when it closes, make active filter count/clear action reachable, return focus to its trigger, invalidate Leaflet layout after panel changes. Keyboard-only users can sign in, edit, fix errors, preview, publish, select map/table records and close overlays. No clipping of primary actions, focus loss while typing, or inaccessible options past today's 6/8 item cutoff.

For each slice return changed files, concise behavior demo, automated test names/results, screenshots where visual state matters, known limitations, and any dependency requiring supervisor decision. Unit tests should target meaningful lifecycle/conflict/DTO behavior, while browser tests should exercise real server routes on disposable data. Stages 1–3 remain a local incomplete candidate: do not deploy a partial stage. Authentication, public catalog and legacy-route restrictions cut over together only after integrated acceptance and migration rehearsal. Do not mutate production data, deploy, auto-publish historical imports, or certify release readiness from frontend self-report alone.

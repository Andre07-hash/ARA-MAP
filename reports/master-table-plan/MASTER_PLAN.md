# ARA Map — master table, documents, and terrain layouts

Version 1 · Owner-directed product plan · October 6, 2026

Execution companion: [two-team parallel delivery plan](TWO_TEAM_DELIVERY_PLAN.md), with separate [Team A](TEAM_A_START_HERE.md) and [Team B](TEAM_B_START_HERE.md) kickoff briefs. This defines overlapping implementation work while keeping the acceptance milestones below.

Distribution: read this packet from GitHub using [GITHUB_HANDOFF.md](GITHUB_HANDOFF.md). The supervisor's desktop paths are not accessible to the two Claude Code accounts.

**The master terrain record will be maintained directly inside ARA Map. Employees add and edit records in an interactive table, attach documents and KMZ layouts, and generate filtered datasets and maps from that shared source.**

This is the overview we will use to develop detailed phase instructions. It records the owner's requirements, recommends defaults where choices remain, and defines milestones. Recommended defaults are not additional owner decisions. It is not an implementation specification or authorization to deploy.

## 1. Direction and precedence

The owner's six requirements in the current conversation supersede earlier Excel-first release assignments, including the October 6 connector completion instructions and next-steps brief.

- **Pause connected Excel/OneDrive work; preserve it.** Keep its branch, commit history, tests, and design reports available for future use. Do not delete the connector or merge it merely to start this plan. Record the retained implementation reference when the coder begins Phase 0; the last reviewed implementation was `415eb2640a42d99687fcef7a68ac3575ce8a651e` on PR #6.
- **Make ARA Map the editing authority for the new master table.** Existing ordinary spreadsheet import/export can remain available; automatic Excel refresh is not a dependency of this release.
- **Add PDF attachments, KMZ layouts, and two roles now.** These are newly requested scope, replacing the earlier deferral of KMZ and roles.
- **Keep BigQuery deferred.** The working recommendation is to retain Neon/Postgres and the existing application stack. No storage migration is needed to deliver this vision.
- Preserve existing business records and saved maps. A private master table does not authorize publishing its contents or documents. Existing public-site continuity must be handled explicitly during release.

## 2. The intended employee experience

1. Open **Tabla maestra** and see the shared terrain records.
2. Click **Agregar terreno**. A new record can be saved immediately, even if every business field is blank. The system assigns an internal ID; an unnamed record has a display label such as “Sin nombre,” without inventing a business name.
3. Edit cells directly, move between them with the keyboard, and see clear **Guardando / Guardado / Error** feedback. Search, sorting, filters, and pinned terrain identity make the table usable as it grows. A compact detail panel can handle longer comments and file lists.
4. Drop a PDF or KMZ into the appropriate cell, or use its upload button. Show filename, progress, processing result, and simple open/download actions. Employees do not manage storage folders or technical file paths.
5. Filter the master table and click **Crear base y ver mapa**. Create the saved dataset with a sensible default name, open its map, and allow renaming afterward. No export/re-upload loop.

The main editing experience is a real interactive grid, not just the existing read-only terrain table with a separate form. On narrower screens, use a compact record view/detail editor where needed instead of forcing fourteen columns into the viewport. Desktop entry remains the primary design target.

## 3. Columns and record rules

These fourteen core columns always exist. **None is mandatory to create a terrain.** Required system metadata, such as the internal ID and author, is generated automatically.

| Core column | Planned treatment |
|---|---|
| Tipo de terreno | Text or controlled choices; vocabulary decided with the owner |
| Nombre de terreno | Optional text |
| Estado | Optional text/selection |
| Municipio | Optional text/selection |
| Superficie | Numeric area; proposed unit: m², explicitly labelled |
| HA | Numeric hectares |
| Afectaciones % | Percentage with an unambiguous entry/display convention |
| Asking price | Optional total amount |
| Asking $/m2 | Optional unit amount |
| Comentarios | Long text, expandable from its cell |
| Archivos | PDF attachments; proposed default: multiple PDFs per terrain |
| KMZ | Original layout file, processing state, and active layout |
| X | Preserve ARA's existing convention: latitude |
| Y | Preserve ARA's existing convention: longitude |

Administrators can add and retire custom columns. The core fourteen cannot be deleted; hiding/reordering columns is a view preference and must not erase their data. Use stable column IDs so renaming a custom column does not break saved values or filters. Retiring a populated custom column should be reversible; permanent purging is a separate operation.

Working recommendation: start custom fields with a small useful set—text, number, choice, date, and supported attachment types. Decide the exact list in Phase 1. A generic attachment column should not silently become the source of the map geometry.

Blank means unknown, not zero. Entered values still receive sensible type validation, but an invalid cell or failed file should not destroy the saved record or unrelated edits. Missing coordinates, prices, area, documents, and name are allowed. The existing inventory rule that requires currency when typing prices needs explicit reconciliation with this flexible-entry requirement.

**Currency must remain explicit or unknown.** Recommended design: an optional USD/MXN currency control alongside the price fields, without replacing any core column or making creation dependent on it. Do not assume pesos from a dollar sign or rank unlike currencies together. Whether m²↔HA and total↔unit-price calculations are offered is a later decision; never silently overwrite entered amounts.

## 4. Master records and derived datasets

Reuse the existing internal inventory's stable IDs, revision history, and save-conflict handling as the foundation. Extend it into the canonical master record rather than introducing another independent editable terrain store.

```mermaid
flowchart LR
    A[Employees enter data and attach files] --> B[Master terrain records]
    B --> C[Search and filter]
    C --> D[Save filtered base]
    D --> E[Table and map]
    E --> F[Optional dated snapshot or export]
```

**Recommended default:** a new filtered base is a named live view of the master records. It stores the filter definition and references the same terrain IDs; editing the master updates its live views. Records enter or leave a rule-based view as they begin or cease matching. This avoids separate copies disagreeing about the same terrain.

Keep the distinction visible:

- **Tabla maestra:** the authoritative editable records.
- **Base filtrada:** a reusable subset, with table/map presentations.
- **Mapa guardado:** a dated snapshot when the user needs to preserve what was seen.

We will confirm live views versus fixed membership/copies before Phase 5. Existing frozen maps must stay frozen regardless of that choice. Their terrain values, geometry, and retained file-version references must not change merely because a master record or attachment is later replaced. Exported spreadsheets are copies, not additional editing authorities.

Existing bases can contain the same terrain in several months and include fictional samples. Phase 0 identifies the real source records and duplicate candidates before migration. Do not automatically dump every historical row into the master or merge records by name alone. Preserve provenance and unresolved duplicates for review.

## 5. Files and KMZ map behavior

**Files:** retain metadata and record relationships in the database, with original PDF/KMZ files in durable private file storage. The provider and upload mechanism will be selected in Phase 3 after checking typical file sizes, access rules, and recovery requirements. A server's temporary filesystem is not permanent storage. Reopening the app from another computer must retrieve the same attachments.

Uploads need simple progress, retry, and replace/remove behavior. File access follows the terrain's permissions on the server, including downloads; a storage URL must not make a private attachment public. Replacement retains the previous usable version until the new upload/processing succeeds. Version retention, orphan cleanup, and restoring files together with database records belong in the release plan.

**KMZ feasibility:** a KMZ is a compressed package containing KML and potentially supporting resources. KML can describe boundaries as polygons and grouped geometries; Leaflet, already used by ARA Map, can display converted GeoJSON polygons and multipolygons. We can therefore extend the existing map renderer rather than replace it. Sources: [Google KMZ documentation](https://developers.google.com/kml/documentation/kmzarchives), [KML reference](https://developers.google.com/kml/documentation/kmlreference), [Leaflet GeoJSON guide](https://leafletjs.com/examples/geojson/).

Proposed processing: upload and retain the original KMZ → validate/extract its usable layout → store a normalized geometry version → show the boundary on the existing map. Process once on upload, rather than unpacking the file every time someone opens a map.

The rendering rule is:

| Available information | Map behavior |
|---|---|
| Active, usable KMZ boundary | Draw the actual layout; fit the full boundary; do not substitute the existing estimated circle |
| No usable KMZ boundary, but valid X/Y | Use the existing X/Y marker behavior |
| Neither | Keep the terrain in the table, visibly marked as lacking a usable location |
| New KMZ is processing or fails | Keep the last valid layout if there is one; otherwise use X/Y; show the file's status |

A terrain with a usable KMZ boundary counts as located even with blank X/Y. Selecting a boundary selects its table record; filtering affects both representations. Do not overwrite stored X/Y with a KMZ centroid or overwrite declared area with a calculated area. Conflicting locations should be visible for review.

KML coordinate order is longitude, latitude, optional altitude; ARA's existing X/Y labels mean latitude/longitude. Conversion must respect that difference without altering the established X/Y workflow. [KML coordinate reference](https://developers.google.com/kml/documentation/kmlreference).

Phase 4 starts with representative company files. Proposed first scope: 2D polygon boundaries, multipart parcels, and holes. Multiple unrelated parcels, alternative layouts, or several KML documents require an explicit selection rule; never silently choose the first polygon. Preserve the original file and flag unsupported point-only, line-only, image-overlay, or 3D content. Review samples to decide whether internal roads/lot lines also belong in the first scope. This is not a promise to reproduce every Google Earth feature.

Bound archive expansion, XML parsing, geometry complexity, and upload size. Do not execute embedded descriptions or follow external network links automatically. Those controls should produce plain-language processing errors for employees.

## 6. Roles

| Capability | Administrator | Data operator |
|---|---|---|
| View master table | Yes | Yes |
| Add terrain; edit existing terrain fields | Yes | Yes |
| Upload/manage terrain PDFs and KMZ | Yes | Yes, proposed as part of editing |
| Search/filter/sort master table | Yes | Yes |
| Add/retire shared custom columns | Yes | Proposed: no |
| Manage users and roles | Yes | No |
| Archive/delete/restore terrain | Yes | Decision pending; proposed: admin only initially |
| Create/manage derived bases and maps | Yes | Decision pending; initial requirement guarantees table access only |
| Change global settings or public visibility | Yes | No |

Administrator access remains subject to the product's core rules: core columns stay present, saved history remains consistent, and actions have an audit trail. Do not turn “can edit anything” into permission to corrupt system metadata.

Permissions must be enforced in APIs and file access, not only by hiding buttons. Every existing account needs an explicit migration assignment; do not make every employee an administrator by default. Retain who changed each record, field definition, file, and role.

## 7. Delivery phases and completion gates

| Phase | Deliverable | What demonstrates completion |
|---|---|---|
| **0. Establish the new baseline** | Preserve and park the Excel connector; identify reusable inventory/maps/auth; retain necessary standalone deployment fixes; inventory real versus sample/duplicate data | Named starting commit, preserved connector reference, source-data migration list, no destructive changes to existing records/maps |
| **1. Agree the experience and data contract** | Table mockup, exact field meanings, custom-column behavior, role matrix, record/file/geometry/view relationships | Owner and supervisor can walk through add, edit, upload, filter, map, and recovery scenarios; only material choices are resolved |
| **2. Deliver master table and roles** | Persistent editable grid, optional fields, easy new record, search/filter/sort, custom columns, admin/operator enforcement, history/conflicts | Operator creates a blank terrain, edits it, reloads from a second session, and sees persistence; restricted actions fail server-side; simultaneous edits are not silently lost |
| **3. Deliver attachments** | Durable private storage, PDF upload/open/download, KMZ upload/status/version relationships | Files reopen from another device; interrupted upload can retry; failed replacement keeps the previous file; unauthorized download is denied |
| **4. Deliver KMZ layouts** | Representative-file support, processing/preview, layout rendering and X/Y fallback integrated into filters/details | Boundary-only terrain maps correctly; multipart/holes work within agreed scope; invalid/ambiguous files have clear outcomes; existing X/Y behavior still works |
| **5. Deliver derived bases and maps** | One-action creation from current filters, saved dataset organization, table/map synchronization, preserved dated snapshots | Saved view matches its filter; edits behave according to the agreed live/frozen model; snapshot geometry/files remain tied to their recorded versions |
| **6. Migrate, pilot, and release** | Reviewed master-data migration, production continuity, employee accounts/roles, file+database recovery rehearsal, hosted pilot, release guide | Administrator and operator complete the full workflow on the hosted app with the owner's Mac off; real records, old maps, permissions, and rollback are verified |

Acceptance dependencies: Phase 0 → 1 → 2; file relationship design begins in Phase 1, delivery follows in 3 → 4; Phase 5 depends on the master and geometry contracts; Phase 6 accepts the integrated result. Implementation overlaps under the [two-team delivery plan](TWO_TEAM_DELIVERY_PLAN.md): master-table work and attachment/KMZ work can proceed concurrently against agreed contracts. Documents do not dispatch agents or send assignments externally.

Do not provide a fixed completion date before Phase 1 establishes scale, sample-file complexity, storage, and the accepted interaction design. Estimate each phase against its concrete scope.

## 8. Choices to make at the relevant phase

| Choice | Working recommendation | Decide before |
|---|---|---|
| Operator deletion and map/base privileges | Table editing/files allowed; structural changes, deletion, and global management limited to admins initially | Phase 2 |
| Land-type choices, units, currency, and calculations | Explicit units, optional currency, no silent calculations; all business values optional | Phase 2 |
| Grid scale and entry conveniences | Confirm expected rows, simultaneous editors, desktop/mobile needs, and whether multi-cell paste is essential | Phase 2 |
| Custom-column types and removal | Small typed set; retire/recover populated columns | Phase 2 |
| File multiplicity, limits, provider, retention | Multiple PDFs; one active KMZ layout per terrain with retained replacements | Phase 3 |
| Real KMZ contents | Boundaries first; include internal layout lines only if representative files establish the need | Phase 4 |
| Derived-dataset behavior | Live filter-based views; explicitly dated snapshots for frozen history | Phase 5 |
| Initial records and public-site continuity | Reviewed business records only; no automatic publication of master data/files | Phase 6 |

These are deferred design choices, not reasons to stop preparing the plan or independently useful phase work.

## 9. How we work together

- **Owner:** defines priorities and business rules, settles the phase's meaningful choices, supplies business examples when needed, and evaluates whether the employee workflow is simple enough.
- **Supervisor:** maintains this master plan, expands the next phase into a developer packet, resolves architecture/contracts, reviews exact implementations and evidence, and reports readiness and risks. The supervisor does not implement application code.
- **AI coders:** implement the scoped packet, preserve existing work, write relevant tests, demonstrate the result, and return exact commits/PRs, verification evidence, and remaining issues. They do not independently revive the Excel-first assignment.
- **Authorized cloud operator:** handles storage/environment/account provisioning and deployment when a phase needs service access. The owner performs only account-holder actions that cannot be delegated.

For each phase: detailed packet → implementation → demonstration and verification → supervisory review → next phase. The existing GitHub coordination protocol still governs shared handoffs. Use the exact GitHub instruction commit supplied by the supervisor; do not assume an open documentation PR has already merged into main. Reading these instructions does not require merging application branches.

**The vision is complete when an operator can create even an incomplete terrain, edit it easily, attach its documents/layout, and have authorized users generate the correct filtered tables and maps from one shared source—with KMZ preferred over X/Y, roles enforced, and all data available without the owner's computer.**

# Developer handoff: folders for databases and saved maps

Prepared September 23, 2026, from the current ARA Map source. This document specifies an implementation; no application code or stored data was changed while preparing it.

Companion specification: [CSV import support](../csv-import-handoff-2026-09-23/IMPLEMENTATION_REPORT.md). These features should work together, but folders must also work with the existing Excel importer independently.

## 1. Outcome and scope

Add persistent folders to both **Bases de terrenos** and **Mapas guardados** so users can organize saved items by client, region, project, or reporting period. Users must be able to create and rename folders, move items between folders, return items to an unfiled state, and delete a folder without deleting its contents.

Recommended initial scope, because nesting and mixed content were not specified:

- Separate folder collections for databases and saved maps. A database folder contains databases; a saved-map folder contains simple maps and comparison maps.
- One folder per item, or no folder. No subfolders in the initial release.
- Folder assignments persist in SQLite locally and Postgres in the shared web workspace. They are not browser-only preferences or physical directories.
- Existing items start under **Sin carpeta**. Existing databases and maps remain available under **Todas las bases** or **Todos los mapas**.
- Moving a database does not move its derived maps. Their organization is independent.
- Folders do not create access restrictions. Existing viewers can browse them; existing editors can organize them.

These are proposed product decisions for the implementation, not functionality currently present. Nested folders, bulk moves, drag-and-drop, folder colors, and folder-level sharing can be future enhancements; do not make them prerequisites for the requested feature.

## 2. Current architecture and important constraints

Paths in this report are relative to `/Users/andrejasso/Desktop/ARA Map`.

| File | Current responsibility and required integration |
| --- | --- |
| `web/components/bases/BaseGallery.js` | Renders one flat database list with open, append, rename, delete, and import actions. Add folder navigation and move actions. |
| `web/components/maps/MapGallery.js` | Renders one flat saved-map list and launches comparisons. Add folder navigation and move actions without limiting comparison sources. |
| `web/components/app.js` | `loadIndex`, `renderBases`, and `renderMapas` load data and rebuild gallery DOM. Coordinate folder loading, selection, mutation, and refresh. |
| `web/lib/store.js` | Stores complete `bases` and `mapas` arrays plus active map state. Add distinct navigation state for each gallery. |
| `web/lib/api.js` | API wrappers. Add folder CRUD and item-move calls. |
| `web/components/bases/ImportDialog.js` | Preview and confirmation for importing; append is a separate flow. Include destination only for creation of a new base. |
| `web/components/maps/OverlayBuilder.js` | Saves simple maps, creates comparisons from bases, and merges saved maps. Add map-folder destination to all creation paths. |
| `server/db.py` | SQLite schema and migrations; current schema version is 4. Add a versioned folder migration and fresh-install schema. |
| `server/repo/bases.py`, `server/repo/mapas.py` | Persistence and API result shaping. Return folder IDs and add dedicated membership updates. |
| `server/api/bases.py`, `server/api/mapas.py`, `server/api/importar.py` | Validate requests and orchestrate writes. Integrate membership and creation destinations. |
| `server/app.py` | Registers routes and applies local read-only/origin rules. Register folder routes here. |
| `api/index.py` | Applies cloud edit authorization and same-origin checks. All folder mutations must remain behind these rules. |
| `server/postgres.py`, `scripts/setup_cloud.py` | Cloud schema generation, adapter-generated IDs, backups, and initial seeding. Folder tables and upgrades must be handled explicitly. |

Saved maps are frozen snapshots in `mapa_terreno`, with source information in `mapa_capa`. A folder move must update organization metadata only. Do not recreate maps, call `refresh_snapshot`, replace layers, modify `config_json`, change `nombre_sigue_base`, or alter terrain/source IDs.

The base rename API has existing name-propagation behavior. Use a dedicated membership endpoint rather than sending a folder move through the current rename handler. Map updates can also replace layers and refresh snapshots, so a dedicated membership operation is preferable there too.

## 3. User experience

### Gallery navigation

Add a folder navigation area to each dashboard: a left-hand list on wide screens and a compact labeled selector or collapsible section on mobile. Reuse the existing visual styles and native buttons/dialogs.

Database example:

```text
Bases de terrenos                    [Nueva carpeta] [Importar archivo]

Todas las bases (18)  |  Cliente Norte
Sin carpeta (4)       |  6 bases
Cliente Norte (6)     |  [Base agosto] [Base septiembre] ...
Proyecto Jalisco (8)  |
```

The saved-map dashboard uses the equivalent **Todos los mapas**, **Sin carpeta**, and named folders, while retaining **Nueva comparación**.

Counts represent saved items, not terrains or layers: a comparison map counts as one map. Include empty folders. Sort folders alphabetically with a stable tie-breaker; preserve the existing item ordering within each filtered list. All-items views show a small folder label on each item to make placement visible.

Keep the full `state.bases` and `state.mapas` arrays intact. Derive visible gallery items from the selection. Never overwrite global arrays with a folder-filtered subset: comparison eligibility and source selection currently rely on the full arrays.

Use distinct values for selection: `"all"`, `"unfiled"`, or a numeric folder ID. `null` represents unfiled membership in the database; it must not ambiguously mean both “all” and “unfiled” in UI state. Maintain independent selections when switching between the two dashboards. Remembering navigation across browser reloads is optional; actual membership must always come from the server.

### Create, rename, and move

- **Nueva carpeta** opens a name dialog. On success, refresh the appropriate folder list and select the new folder.
- Each folder has **Renombrar** and **Eliminar carpeta** actions available to editors.
- Each database/map card has **Mover a carpeta…**. Its dialog lists only folders of the matching type plus **Sin carpeta**. Preselect the current placement and identify the item by name.
- Moving the item out of the displayed folder removes its card only after server success. Update counts and the corresponding object in the full item list. A failed request leaves the previous placement visible with a readable error.
- Repeating a move to the same destination succeeds harmlessly. Use existing item IDs; moving must never duplicate content.
- Preserve the open map, its filters, terrain selection, zoom, and detail panel if organization changes while it is active. Update metadata references by ID without reopening the map.
- Dialogs must support keyboard navigation, Escape to cancel, associated labels, focus on entry, and sensible focus restoration on close. Do not require drag-and-drop.

Gallery rendering currently rebuilds DOM on store updates. Keep dialog inputs stable while typing; do not introduce a per-keystroke global update that destroys focus. The earlier map-search focus fix must remain intact.

### Folder removal keeps all content

Use a precise confirmation message, for example:

> ¿Eliminar la carpeta «Cliente Norte»? Sus 6 bases pasarán a «Sin carpeta». No se eliminarán bases ni terrenos.

For map folders, say that their maps will move to **Sin carpeta**. Offer **Cancelar** and **Eliminar carpeta**. This is folder deletion, never recursive content deletion.

Perform membership clearing and folder deletion atomically. Refresh counts after success. If the removed folder was selected, navigate to **Sin carpeta**. If another editor already removed a destination folder, explain that it no longer exists and reload destination choices; do not silently place the item elsewhere.

Preserve existing **Eliminar base** and **Eliminar mapa** behavior as separate, clearly labeled actions. Deleting an item should leave its folder in place even if now empty.

### Creation destinations

Add a **Carpeta** selector to these dialogs:

1. New database import confirmation: database folders only. Default to the selected database folder, otherwise **Sin carpeta**.
2. Save simple map: map folders only. Default to **Sin carpeta**, unless an explicit map-folder context was supplied. Do not infer a map folder from the source database's folder.
3. Comparison from bases and merge of saved maps: map folders only. Default to the currently selected map folder when launched from that gallery, otherwise **Sin carpeta**.

Capture the intended destination when opening the dialog. Submit it together with the create/import request and validate it on the server inside the creation transaction. Do not create an item and then make a second request to move it; a failed second request would leave it in the wrong place.

Appending terrain rows keeps the existing database's folder. **Actualizar mapa**, **Guardar vista**, renaming a source, and Excel export preserve all folder assignments.

Comparison builders must continue offering sources from every folder. Show each source's folder label to aid selection. A comparison can include maps or bases organized in different folders, and the resulting comparison has its own selected destination.

## 4. Data model and integrity

Recommended minimal model:

```sql
CREATE TABLE carpeta (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo           TEXT NOT NULL CHECK (tipo IN ('bases', 'mapas')),
  nombre         TEXT NOT NULL,
  nombre_clave   TEXT NOT NULL,
  creado_en      TEXT NOT NULL,
  actualizado_en TEXT NOT NULL,
  UNIQUE (tipo, nombre_clave)
);

-- Add to base and mapa, both nullable:
carpeta_id INTEGER REFERENCES carpeta(id) ON DELETE SET NULL
```

This is a schema sketch: adapt it to fresh-install and upgrade paths rather than executing it verbatim. Add indexes on `base(carpeta_id)` and `mapa(carpeta_id)` after those columns exist.

Use `NULL` for **Sin carpeta**. Do not create fake folder records for **Todas/Todos** or **Sin carpeta**. Folder IDs are stable and must not be recycled after deletion; use the project's SQLite AUTOINCREMENT/Postgres identity conversion.

Trim names, collapse repeated whitespace, and enforce a reasonable bound such as 1–100 characters. Normalize a uniqueness key consistently on the server, for example using the existing `fold` utility (which also folds accents). Preserve the display name. Reject duplicate normalized names within one folder type with HTTP 409; the same display name can exist once in each dashboard. Renaming to the same normalized name on the same folder should succeed. Reserve navigation labels within the relevant type so a user folder cannot be mistaken for **Sin carpeta** or **Todos los mapas**.

The simple foreign key establishes existence, not type. All membership-writing repository paths must additionally validate that `base.carpeta_id` refers to a `bases` folder and `mapa.carpeta_id` to a `mapas` folder. Perform that validation and the write within one transaction. Folder type is immutable. Do not rely on a filtered dropdown as the only protection.

Use the project's database abstraction and parameter binding. Translate expected constraint conflicts into the API's readable errors. Handle concurrent creation of the same normalized name with the database uniqueness constraint, not only a preflight query.

Folder removal should explicitly clear matching memberships and remove the folder in a transaction, with `ON DELETE SET NULL` as an additional integrity guarantee. Preserve all base/map IDs, timestamps that describe data import or snapshot refresh, counts, terrain values, layers, naming flags, and saved view configurations. A map-folder move must not change its displayed “actualizado” timestamp, which would suggest its saved data had been refreshed.

## 5. API contract

Add `server/repo/carpetas.py` and `server/api/carpetas.py`, with routes registered in `server/app.py`. The following contract avoids changes to existing rename operations:

| Method and route | Input | Success response |
| --- | --- | --- |
| `GET /api/carpetas?tipo=bases` (or `mapas`) | Required valid type | `{carpetas: [{id, tipo, nombre, conteo, creado_en, actualizado_en}], sin_carpeta: N, total: N}` |
| `POST /api/carpetas` | `{tipo, nombre}` | `{carpeta: {...}}` |
| `PATCH /api/carpetas/:id` | `{nombre}` | `{carpeta: {...}}` |
| `DELETE /api/carpetas/:id` | No recursive/delete-contents option | `{eliminada: nombre, tipo, trasladados: N}` |
| `PATCH /api/bases/:id/carpeta` | `{carpeta_id: integer|null}` | `{base: updatedBase}` |
| `PATCH /api/mapas/:id/carpeta` | `{carpeta_id: integer|null}` | `{mapa: updatedMap}` |

Return actual affected counts from the deletion transaction, not a stale client count. Folder counts should use grouped queries; avoid joining both item tables in a way that multiplies counts.

Existing list/detail responses for bases and maps must include `carpeta_id`, including `null`. Keep existing endpoints returning all items by default. `server/repo/bases.py` has an explicit `_SUMMARY` column list, so its query needs updating; map shaping currently starts from `SELECT *`, but still test all returned shapes.

Creation payload extensions:

- `POST /api/importar/confirmar`: optional `carpeta_id` for the new base.
- `POST /api/mapas`: optional `carpeta_id` for a simple map or comparison built from bases.
- `POST /api/mapas/combinar`: optional `carpeta_id` for the merged map.

Omission means `null` for newly created items, preserving old clients. In dedicated move requests, require the field: `{}` is invalid, while `{carpeta_id: null}` explicitly unfiles an item. Reject boolean, fractional, negative, zero, or string IDs in JSON; accept only positive integers or null. Use 400 for invalid input or wrong folder type, 404 for nonexistent items/folders, and 409 for duplicate folder names.

If a chosen folder disappears before import confirmation or map creation, fail without creating an item. Explain any need to reopen the import preview under the existing single-use token behavior. Do not bypass confirmation or leave a partial base behind.

All mutation routes must obey both local read-only mode and cloud authentication/origin protections. Hiding buttons is insufficient; verify direct HTTP calls too. This feature does not introduce new permissions or private folders.

## 6. SQLite, Postgres, migration, and backups

### Local SQLite

Increment the schema version from 4 to the next available version after checking concurrent changes. Add an idempotent migration that creates folders and adds nullable memberships to existing base/map tables. All existing rows initially remain unfiled.

Pay attention to migration ordering: `migrate` currently runs `conn.executescript(SCHEMA)` before its later migration helpers. A new index on `base.carpeta_id` placed in that script will fail on an existing base table until the column has been added. Separate or reorder column/index steps deliberately. Test fresh installs, upgrades from version 4, and older supported versions, including existing table-rebuild migrations.

Retain pre-upgrade backup behavior and advance the schema version only after successful migration. Do not connect to the user's live database to develop migration logic.

### Shared Postgres

Updating `SCHEMA` alone does not upgrade existing tables: `CREATE TABLE IF NOT EXISTS` leaves old definitions in place. Supply an explicit, repeatable cloud migration with the folder table, `ALTER TABLE ... ADD COLUMN`, foreign keys, indexes, and migration marker/checks. Use the existing cloud transaction/advisory-lock approach to coordinate upgrades. Document when it must run relative to releasing code that queries the new columns.

`scripts/setup_cloud.py` is an initial-seeding tool, not an established incremental migration runner. It checks a `seeded` marker and exits for an already initialized workspace; it also executes generated schema before that check. Do not depend on rerunning it to repair existing cloud columns, and ensure new indexes do not make that invocation fail against the old schema.

Update `server/postgres.py`:

- Include `carpeta` before referencing item tables in `TABLES`, so backup and seed paths include folders in dependency order.
- Ensure `ID_TABLES` includes `carpeta`, because the adapter uses it to append `RETURNING id` and supply `lastrowid`.
- Verify generated Postgres DDL for the new table and fresh schemas.
- Include memberships and folders in backup payloads and restore/seed handling; reset the folder identity sequence when seeding explicit IDs.
- Extend disposable Postgres test cleanup to clear folders as well as items so cases cannot contaminate each other.

Keep local and cloud workspaces independent as they currently are. Adding folders does not establish synchronization. Prepare the migration and verification instructions; deployment and running a migration against production are separate operations from implementing this report.

## 7. Verification and acceptance

Implement focused tests using fictional records and temporary SQLite databases. For actual Postgres integration, use the existing disposable-schema pattern in `tests/test_postgres.py` and an explicitly configured test connection, never the production workspace.

| Test | Expected result |
| --- | --- |
| Upgrade existing data | Existing bases, maps, orphaned-source maps, layers, and frozen terrain values survive. Each item has null membership. Migration can run again harmlessly. |
| Fresh install | Folder table, membership columns, indexes, and defaults exist in SQLite and generated Postgres schema. |
| Folder CRUD | Create, list, rename, and delete work separately for both types. Empty folders remain visible. Whitespace, normalized duplicates, name limits, and reserved labels are handled. |
| Placement | Move each item type from unfiled to folder, between folders, and back. Same-folder move is harmless. Wrong-type/nonexistent destinations fail without changing content. |
| Folder deletion | Populated folder removal unfiles all its items atomically, preserves item IDs/data, and leaves unrelated folders untouched. Injected failure rolls back. |
| Persistence | Folder assignments survive refresh, application restart, and separate cloud requests. Backup/seed round trips preserve the hierarchy and IDs. |
| Concurrent editors | Duplicate names cannot both commit. Destination deletion during a move/create gives a controlled result with no lost or orphaned items. |
| Create/import | Excel and, when implemented, CSV import honor the selected database destination. Simple-map save, base comparison, and map merge honor map destinations. Invalid destinations create no items. |
| Snapshot integrity | Before/after moving maps or deleting their folder, compare `mapa_terreno`, `mapa_capa`, view config, naming flag, and snapshot timestamp. They remain unchanged. |
| Existing actions | Append, rename propagation, map refresh, and saving a view preserve memberships. Deleting one item does not delete the folder. Deleting a source base still preserves its saved map. |
| Cross-folder comparison | Two sources in different folders remain selectable. The compare button uses the complete collection, not the currently displayed subset. Export retains per-base worksheets. |
| UI states | All/unfiled/named views have correct counts. Empty workspace, empty folder, loading failure, missing selected folder, and mobile navigation are distinguishable. |
| Accessibility/focus | Folder and move dialogs work with keyboard and retain typing focus. Escape cancels. Moving/removing a card restores focus sensibly. Existing map-search behavior remains correct. |
| Access control | Read-only viewers can browse but cannot create, rename, move, or delete through UI or direct requests. Cloud anonymous writes remain rejected. |

Extend `tests/test_migration.py`, API/repository tests, `tests/test_snapshots.py`, `tests/test_cloud.py`, and `tests/test_postgres.py`. Add pure JavaScript tests for gallery filtering and folder counts where useful, and browser tests for both complete dashboard workflows. UI acceptance must include browsing actual folders, not merely the presence of a folder button.

Run the project's established checks from its root:

```sh
python3 -m unittest discover -s tests -t .
node --test tests/js/*.test.mjs
./verificar.sh --todo
```

Run browser checks separately against a disposable database using `tests/e2e/README.md`; `verificar.sh --todo` prints browser instructions rather than executing them. Report unconfigured or skipped Postgres/browser checks explicitly.

## 8. Delivery checklist and developer assignment

Deliver the shared folder UI, endpoints, repository operations, migrations for both storage backends, test fixtures/results, and updated Spanish documentation. Explain that folders organize items independently on the two dashboards and that deleting a folder preserves its contents. Include migration prerequisites and any checks that could not be run.

Suggested assignment to paste to the implementing associate:

> Add persistent folders to ARA Map's Bases de terrenos and Mapas guardados dashboards following this report. Implement separate flat folder collections, all/unfiled views, create/rename/delete-folder actions, and moving existing items. Folder deletion must retain all contained data. Add destinations to database imports and every map-creation path. Preserve complete cross-folder comparison sources, existing names, IDs, frozen snapshots, saved view settings, Excel/CSV behavior, and read-only permissions. Implement and test SQLite upgrades and an explicit Postgres upgrade, including backups and seeding. Use isolated test resources and provide changes, test results, and deployment instructions without deploying or modifying production data.

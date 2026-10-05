# Release response: import assistant and saved-map merge correction

Response to [DEPLOYMENT_REVIEW.md](DEPLOYMENT_REVIEW.md). Carried out on September 24, 2026 (America/Mexico_City), which was September 25 UTC.

**Result: released.** All six steps of the deployment sequence were completed. Nothing failed.
- The shared web version runs the reviewed source on schema version 6, with AI disabled.
- The smoke test passed 31 of 31 checks, and its records were removed.
- The pre-existing bases, saved maps and folder are unchanged.

## 1. Snapshot, current deployment, target

| Item | Recorded value |
|---|---|
| Source | Matches [FINAL_SOURCE_SNAPSHOT.json](FINAL_SOURCE_SNAPSHOT.json) (142/142 files), checked before migrating and again after the smoke test |
| Previous production deployment (rollback target) | `dpl_6FJdk541wty2XfsqSehqCmBqRhRu` (`ara-6l0vxqb8s-aicore2.vercel.app`) |
| Vercel project | `aicore2/ara-map` |
| Database | Neon endpoint `ep-orange-mountain-av5088lz`, database `neondb`. The production `DATABASE_URL` points to the same workspace as the local `.env.local`. |
| AI | No `ARA_MAP_IA_*` variable exists in production, before or after the release. The simulated provider was not used in production. |

Pre-release workspace: 3 bases, 104 terrains, 54 findings, 1 folder, and 2 saved comparisons (5 layers, 196 frozen terrains). Schema version was 5.

## 2. Recoverable backup

- **Independent export** (taken before migration, `2026-09-25T04:18:11Z`):
  - A read-only, consistent snapshot of every table, one compressed CSV per table plus column types, row counts and SHA-256 hashes. It is stored in `datos/respaldos-nube/neon-antes-de-v6-20260925T041811Z/` with owner-only permissions.
  - The export was verified by re-reading it and checking every row count and hash.
  - It includes the 10 workspace backups that existed then.
  - `pg_dump` 17 cannot dump the Neon server (18.6), which is why a table export was used.
- **Migration's own backup:** `workspace_backup` id **15**, created `2026-09-25 04:18:47Z`. The cloud keeps only its 10 most recent backups, and the smoke test's writes rotated this one out of the cloud as expected. It was therefore copied to `datos/respaldos-nube/workspace_backup-15-migracion-v6.json.gz` before the smoke test (171,644 bytes; SHA-256 begins `552df662ccd02a78`).

## 3. Migration

- **Command:** `scripts/migrate_cloud.py --url-env ARA_MAP_PROD_URL`. The variable held the production direct (unpooled) connection. It was loaded without printing, and `.env.local` was not read.
- **Before:** `--check` reported version 5.
- **After:** `--check` reported version 6.
- **Existing data:** base, terreno, incidencia, carpeta, mapa, mapa_capa, mapa_terreno and workspace_metadata (apart from the recorded version) are **identical** to the pre-migration export.
- **New tables:** `formato_importacion`, `importacion`, `uso_ia` and `borrador_importacion` exist.

## 4. Deployment

| Item | Value |
|---|---|
| Deployment | `dpl_3VdC4NrQYuuf6tNBJLYdUFTnBGnV`, target production, status Ready |
| Deployment URL | `ara-58va1kzvw-aicore2.vercel.app` |
| Production aliases | https://ara-map-ivory.vercel.app, https://ara-map-aicore2.vercel.app |
| Checks | `/api/config` returns read-only for visitors (`cloud`, `authRequired`, 4 MB limit). The assistant's script and stylesheet are served. The page loads on desktop and phone with no script errors ([screenshots](lanzamiento/)). |

## 5. Smoke test (31/31)

**Method:**
- [lanzamiento/smoke.py](lanzamiento/smoke.py) ran against the production aliases, as an editor, over HTTPS.
- It used fictional records labeled **`SMOKE 2026-09-25`**. Each created ID went into a ledger, and the run was set to stop at the first failure.
- **Dry run:** before touching production, the same script and the cleanup were run against the real Vercel handler (`api/index.py`) on a throwaway local Postgres ([dryrun_server.py](lanzamiento/dryrun_server.py)), with a dummy password. It passed 31/31, and cleanup left the pre-existing record untouched. That cluster was then deleted.

| Area | Checks in production |
|---|---|
| Viewer vs editor access | Visitors are read-only; analysis, format listing and folder creation are refused (401). Visitors can read bases and export. Editor login works, and the editor session is editable. |
| Familiar CSV | Standard headers go straight to the preview with no questions ("no AI needed"). 4 terrains, all placed on the map, imported. |
| Ambiguous header | A `Valor` column asks **exactly one** question. Answering "Precio total (MXN)" puts prices on all 4 rows. A correction (Municipio → extra data) makes a new revision and clears the municipality; reverting it restores the municipality. Imported, and the format was remembered. |
| AI disabled | An unfamiliar file reports "not configured" and falls back to focused questions (first: which column is the terrain). No provider call is made. |
| Folders | Create a folder, move a base into it, and the listing counts it. |
| Save and reopen maps | Two simple maps saved, one per base (4 terrains each), and both reopened with their terrains. |
| **Merge fix** | Two **distinct** saved maps with **equal** terrain counts (4 and 4): the merge plan finds no duplicates. The comparison has **2 layers**, each keeping its own 4 terrains (the "Norte" rows in layer 0, the "Sur" rows in layer 1). |
| Excel export | The comparison exports one sheet per source, each with 4 data rows. It exports for visitors too. |
| Append | Adding 1 new row plus the 4 existing ones: the preview classifies 1 new and 4 duplicates. 1 added, and the base now has 5. The saved map stays a snapshot, still at 4. |

## 6. Cleanup and verification

[lanzamiento/cleanup.py](lanzamiento/cleanup.py) deleted exactly the records listed in the ledger, and confirmed that each one returns "not found":
- maps 6, 7, 8
- bases 32, 33
- folder 4 (it held nothing else)
- remembered format 1

Verification afterwards:
- No record labeled `SMOKE` remains.
- All **6 pre-existing records** (3 bases, 2 maps, 1 folder) are **identical** to the baseline taken at the start of the run, compared field by field as the listings return them.
- Each pre-existing base opens.
- Both saved comparisons open: `prueba comparación` (92 terrains) and the three-source comparison (104). That is 196 frozen terrains, as before the release.

**What remains from the smoke test, by design:**
- **One unconfirmed assistant draft.** It came from the AI-disabled check and holds only the fictional `SMOKE … Gama` row. Drafts expire after 60 minutes and are purged the next time anyone analyzes a file. There is no delete endpoint, and I did not run SQL on production.
- **Rotated cloud backups.** The cloud's rolling window of 10 workspace backups now holds states from the smoke run; the last one is the clean state after cleanup. The pre-release backups are preserved locally (section 2).
- **Used ID numbers.** Postgres sequences advanced (for example, the next base ID is 34 or higher). This is harmless.

## Existing comparisons (not modified)

I inspected them read-only.
- Neither shows signs of the merge defect. Every layer in them has a **different** terrain count (79/13; and 13/12/79), and the defect only discarded layers with equal counts.
- The three-source comparison has the three layers its title names.
- Following the review, nothing was recreated or deleted.
- If anyone remembers building a merge that should have had more layers, recreate it from its original maps.

## Release note

> Fixed merging saved maps in the shared web version: distinct layers with equal terrain counts could be discarded as duplicates. New merges preserve these layers. Previously saved comparisons missing layers must be recreated from their original source maps; this deployment does not repair them automatically.

Also in this release:
- The import assistant: automatic interpretation, only necessary questions, preview, corrections, remembered formats, and append.
- Folders were already present from schema 5.
- AI is **not active**. Files are interpreted by detection plus questions.

## Rollback plan (not needed)

- **Code:** promote the previous deployment `dpl_6FJdk541wty2XfsqSehqCmBqRhRu` in Vercel.
- **Schema:** the v6 migration only **adds** (tables, columns and indexes, all `IF NOT EXISTS`), and no existing table's data changed (section 3). The earlier code does not use the additions, so no schema rollback is expected. I have not tested the earlier code against schema 6.
- **Data:** the local export and backup 15 can recover the pre-release state. As the review instructs, they must not be restored automatically over newer data.

## Still open (unchanged by this release)

1. **Before the boss's demonstration:**
   - The stray `false` in the navigation.
   - The **header overflow on phones**, still visible in production ([screenshot](lanzamiento/produccion-telefono.png): the navigation and buttons are cut off at 375 px).
   - Then check the desktop and phone layouts.
2. **Before paid AI:** choose the model and set its prices, key and monthly limit. Then run a real-provider evaluation on fictional or approved samples ([scripts/evaluar_asistente.py](../../scripts/evaluar_asistente.py)), and set the `ARA_MAP_IA_*` variables in Vercel.
3. **Optional:** a rehearsal on an isolated Neon branch for hosted connection behavior.

No credentials, connection strings or uploaded file contents appear in this report or in the scripts.

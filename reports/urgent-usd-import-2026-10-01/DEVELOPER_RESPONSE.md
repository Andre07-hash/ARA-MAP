# Developer response: USD import correction

October 1, 2026. Reply to `DEVELOPER_HANDOFF.md`.

## Status first

**Live in production and verified there**, within the scope of the supervisor's decision: today's desktop demonstration with the existing original XLSX.

- **Deployment:** **`dpl_3vsdvzhV86Y1goinejgcHP83vNML`** (`ara-jysgewccu-aicore2.vercel.app`), serving **https://ara-map-ivory.vercel.app**, created 2026-10-01 15:16 CST.
- **Pre-release deployment:** `dpl_GtcUn7XczFo1FdciNZ9XUdjH3fkU`.
- **Neon schema:** upgraded 6 → 7 before the deploy.
- **Demonstration base:** **«Demo USD · Base Terrenos 09.26 (1 oct 2026)», id 37**, imported from `Base Terrenos 09.26 copy.xlsx` (sha256 `a5711517…9e32`) through the production browser dialog.
- **Saved map:** **«Demo USD · mapa (1 oct 2026)», id 9**.

| Production check (real browser, ara-map-ivory.vercel.app) | Result |
|---|---|
| Editor login with the existing password | Works. The password was not changed or copied into any file. |
| Questions asked | Three, as expected with format 4 present: restore «Asking Price» (Sí), restore «Asking $/m2» (Sí), currency (USD) |
| Preview | **79 terrains, 39 located, 59 total prices, 60 unit prices**, "Moneda de los precios: dólares estadounidenses (USD)" |
| Stored, via API | 79 / 39 / 59 / 60; every priced row is `USD` |
| Marceñas | **USD 388,689,722 and USD 600/m²** in preview, detail and storage. The source warning is preserved: "Asking Price es 388,689,722 USD pero 600 USD/m² × 64,429 m² da 38,657,322 USD." |
| El Dorado | **USD 122.50/m²** in preview, detail panel and table after reopening, and in the reopened saved map. Stored value is 122.5 USD. |
| Map | 39 marks; legend bands from "< USD 500" to "≥ USD 2.15 k"; 40 terrains listed off the map |
| Saved map | Created and reopened, 79 terrains / 39 located; frozen El Dorado is 122.5 USD |
| Excel export (from the reopened map) | One sheet, 79 rows. «Moneda» = USD on every priced row. El Dorado 122.5 with format `"USD "#,##0.00`; Marceñas 388689722 with `"USD "#,##0`. |
| Existing comparisons | Ids 1 and 4 are still present with the same layer counts (13/12/79 and 79/13); their frozen rows keep `moneda` NULL, shown as unconfirmed |
| Format 4 | Superseded by format 5 «Formato de «Base Terrenos 09.26 copy» (v2)», which remembers both prices and USD. Format 4 is kept, not deleted. Formats 2 and 3 are untouched. |
| Browser console | No errors |

Evidence: `evidence/production-2026-10-01/` holds the results JSON, five screenshots, and the Neon content checksums from before and after the migration. Source hashes for this release are in `evidence/release-source-hashes.json`.

## Production procedure followed

1. **State re-read** (read-only, before any change). 0 bases; saved comparisons 1 and 4 (196 frozen terrains); formats 2, 3 and 4; one empty base folder. No AI provider is configured in production.
2. **Pre-release record.** Deployment `dpl_GtcUn7XczFo1FdciNZ9XUdjH3fkU` and 95 source-file hashes were recorded.
3. **Independent backup**, kept outside the rotating list: every table exported with `COPY … CSV`, plus the column and constraint definitions, to `datos/respaldos-produccion/neon-pre-v7-completo-20261001-151342/`. That folder is owner-only and excluded from git and from Vercel uploads. `pg_dump` 17 cannot dump Neon's PostgreSQL 18.6, hence CSV.
   - **Recoverability verified:** the backup was restored into a fresh local Postgres with the v6 schema. Every table matched production's content checksum.
4. **Migration** with `scripts/migrate_cloud.py`. It wrote its own `workspace_backup` first, then applied v6 → v7.
   - **Checksums:** carpeta, base, terreno, incidencia, mapa, mapa_capa, mapa_terreno, formato_importacion and importacion are all unchanged.
   - **New column:** `moneda` exists on `terreno` (CHECK USD/MXN) and `mapa_terreno`. All 196 existing frozen rows have `moneda` NULL; nothing was guessed.
   - **Compatibility:** the old deployment kept serving the maps after the migration.
5. **Deploy** with `vercel deploy --prod` from the recorded source. Before deploying, the hashes were re-checked and the suites re-run: 624 Python tests and 68 JavaScript tests passing. Then the production browser flow above.

## What changed

**Currency travels with the price.** Each price is stored as USD or MXN, or as unknown (NULL), and is never converted.

- **Import.** `US$`, `USD`, `MXN`, `pesos`, a «Moneda» column, or an explicit Excel format such as `"USD "#,##0` decide the currency. A bare `$`, including `[$$-409]`, triggers one plain question. Magnitude and geography are never used. The file's explicit markers beat a saved format and any later correction.
- **Unsupported or mixed currencies.** EUR and other unsupported currencies, a column mixing two currencies, or price columns that disagree, are kept out of the price fields with an explanation. The plan refuses any attempt to force them in.
- **Plan version 2.** The plan now carries the currency and validates it against every price cell. It is version 2, so previews and drafts built under the old interpretation are refused.
- **Text amounts.** Amounts such as `US$ 600` are read only after the currency is settled. `US$ -` is no data, never zero.

**Format 4.** It is not deleted, and no other format is touched.

- **Legacy formats re-ask.** Any format saved before this change that keeps a recognised price column as additional data no longer applies that choice silently. The import asks "¿Importar «Asking Price» como precio total?" with the reason shown. A silent price-less import is no longer possible.
- **On confirm.** Confirming with "Recordar este formato" saves a new version that maps both price columns and remembers USD. Format 4 is marked superseded. The next upload of the same workbook goes straight to a USD preview.
- **Currency exclusions are not remembered.** A column kept out of the prices only because of its currency is left out of the saved format, so it can never again suppress a supported price.

**Schema decision.** There is a nullable `moneda` column on `terreno` (`CHECK IN ('USD','MXN')`) and on `mapa_terreno`. The schema version goes from 6 to 7.

- **Migrations.** Both are additive and idempotent: SQLite runs `db.migrate`, Postgres runs `scripts/migrate_cloud.py`.
- **Existing rows.** Existing records and saved-map snapshots keep NULL. They show as "$… · sin moneda" and are never relabelled. Saved maps 1 and 4 in production stay exactly as they are.
- **Where the currency is carried.** Repository column lists, snapshots, comparison merge, append change detection and layer fingerprints all include it. A layer with no known currency hashes exactly as before.
- **Comparing currencies.** 600 USD and 600 MXN are a conflict on "Moneda", never a duplicate.

**Display and export.**

- **Every price surface shows the currency code.** That covers table, detail panel, map tooltip, legend, filter rail and import preview, with unit-price cents kept.
- **Mixed currencies.** When the terrains in view mix currencies (including known with unknown), shared price colour bands, price filters and price sorting switch off with an explanation. Geographic comparison still works.
- **Export.** It adds a «Moneda» column as the last column, so the 13 original columns keep their positions. Price cells get a literal currency format, unit prices keep two decimals, and there is still one sheet per comparison source.
- **Re-import.** Exported files re-import as USD with no question and with 122.5 intact. Rows with no recorded currency are exported as "sin confirmar", and re-importing them cannot silently assign one.
- **Manual entry.** A manually added price via the API must state its currency.

## Acceptance checks (handoff list)

| # | Check | Result |
|---|---|---|
| 1 | Original XLSX, clean disposable workspace, real browser flow | **Pass**: 79 / 39 / 59 / 60, USD, no CSV involved |
| 2 | Confirm, reopen, values in storage/API and on screen | **Pass**: values above; the reopened table shows "USD 133,072,446 · USD 122.50/m²" |
| 3 | With format 4's stale mapping present | **Pass**: asks to restore both price columns plus the currency, then 79 / 39 / 59 / 60 USD. Format 4 is superseded, not deleted. Verified on SQLite and on disposable Postgres. |
| 4 | Genuine Numbers → Excel export, correct sheet | **Not verified.** Driving Numbers on this Mac timed out and produced no file. The original was untouched (hash checked before and after); only a copy was opened. **USD CSV, verified:** 79 / 39 / **58 / 59**, USD read from the file with no question. The single difference is Los Caudales, whose price is `0` in the XLSX and `US$ -` in the CSV, kept as no data. El Dorado is **123** in the CSV because Numbers already rounded it; that precision cannot be recovered. |
| 5 | Saved map, comparison, export/re-import, MXN fixture | **Pass**: USD and MXN layers keep their own currency. Shared price bands and filters are disabled and the legend explains why; 40 locations still draw. Export and re-import keep USD and 122.5. |
| 6 | Disposable PostgreSQL, migration, snapshot preservation | **Pass**: a v5 workspace with live data and a frozen snapshot was upgraded to v7 by `migrate_cloud.py`, twice. Data is byte-identical, `moneda` is NULL on every existing row, and `EUR` is rejected. 21/21 Postgres tests pass. The full incident flow was also run through the real handlers on Postgres. |
| 7 | Stale previews, auth, no paid AI, regressions | Plan v2 refuses old previews. Login works in production with the existing password. No AI provider is configured in production, and the AI code is unchanged. The full regression suite passes (below). Carried-forward changes are listed below. |
| 8 | Production backup, deploy, production browser verification | **Pass**: see "Status first" and "Production procedure followed" |

## Tests

- `./verificar.sh --todo`: **all OK**. Python 624 tests on 3.14 and on the macOS system 3.9 (21 skipped, all Postgres-only, run separately below). JavaScript 68 tests. ruff clean, mypy clean, coverage **94%**.
- Postgres, disposable local cluster: `tests.test_postgres` and `tests.test_postgres_aceptacion`, **21/21**.
- Browser, Chrome on a disposable SQLite workspace: **66/66**, including the new "incident 2026-10-01: the real ARA workbook imports in the browser with USD prices". No console errors.
- New tests: `tests/test_usd_incidente.py` (real workbook, format 4, maps, comparison, export, re-import, manual entry) and `tests/js/moneda.test.mjs`.
- Rewritten tests: `tests/test_asistente_monedas.py` and the R3 cases in `tests/test_revision_supervisor.py` now assert the confirmed rule. Prices may be USD or MXN, never relabelled, never converted, never guessed. Fixtures with unmarked amounts answer MXN, which is what they always meant.

## Files changed

- **Server:** `server/asistente/{campos,detectar,plan,servicio}.py`, `server/csv_numbers.py`, `server/importer.py`, `server/protocols.py`, `server/db.py`, `server/postgres.py`, `server/repo/{terrenos,mapas}.py`, `server/matching.py`, `server/validation.py`, `server/api/{exportar,bases}.py`
- **Web:** `web/lib/{format,filters,comparar}.js`, `web/components/app.js`, `web/components/import/AssistantViews.js`, `web/components/map/{Legend,MapCanvas}.js`, `web/components/terrain/{FilterRail,TerrainTable,TerrainDetail}.js`
- **Tests:** the two new files above, plus updates in `tests/test_asistente{,_api,_filas,_migracion,_monedas}.py`, `tests/test_postgres{,_aceptacion}.py`, `tests/test_revision_supervisor.py`, `tests/test_snapshots.py` and `tests/e2e/smoke.mjs`

## Carried-forward changes in this release

This deployment is not exclusively a currency patch. Following the supervisor's correction: the September 30 baseline already differed from the earlier polish release in these files, and they ship with this release:

- `server/asistente/campos.py`, `detectar.py`, `perfil.py`, `plan.py`, `rejilla.py`, `servicio.py`
- `server/csv_importer.py`
- `web/components/import/AssistantViews.js`, `ImportAssistant.js`
- `web/styles/assistant.css`, `controls.css`

They were covered by the supervisor's September 30 audit, and its documented limits still apply. This approval does not clear the worksheet-switch and excluded-row problems or the preview-control limits. **Avoid switching worksheets, excluding or restoring rows, or relying on the preview controls in today's rehearsal.**

## Still unverified or out of scope

- A genuine Numbers → Excel export. Not tested, and not claimed. The demonstration uses the exact existing XLSX verified above. Today's verification used the original Excel copy, which is the source the handoff names for the definitive import.
- The legacy `POST /api/importar/vista-previa` endpoint, which the UI no longer calls, still stores prices without a currency (NULL). They show as "sin moneda" and are never relabelled.
- Native `.numbers` upload, AI, other file types and unrelated UI: deferred as instructed.

## Rollback

If needed, redeploy `dpl_GtcUn7XczFo1FdciNZ9XUdjH3fkU`. It runs against schema v7, because the change only adds columns. **That is not an equivalent fix:** the old code labels the newly stored USD prices as MXN. After a rollback, suspend monetary demonstrations of the new records until labels are corrected. The full pre-migration data can be restored from the independent backup folder above.

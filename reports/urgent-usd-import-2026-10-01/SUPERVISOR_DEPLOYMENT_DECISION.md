# Supervisor decision on the USD correction

October 1, 2026

**Recommendation: proceed with a controlled deployment for today's prepared desktop demonstration, using the existing original XLSX.** This is not acceptance of arbitrary Numbers exports, every spreadsheet layout or unrestricted final handover. The USD correction itself is supported by the focused checks below. No deployment or production migration was performed by this review.

## Independent review performed

- Read `DEVELOPER_RESPONSE.md` and inspected currency detection, plan validation, currency formatting, mixed-currency view handling, migration SQL and the migration command.
- Re-ran `tests.test_usd_incidente` and `tests.test_asistente_monedas`: **43/43 pass**, using isolated test databases with production database variables cleared and AI disabled.
- Re-ran `tests/js/moneda.test.mjs`: **6/6 pass**.
- These runs verify the real workbook's counts and representative persisted USD values, the stale saved-format recovery, saved-map and comparison currency persistence, export/re-import precision, and currency-display helpers. The browser walkthrough and disposable PostgreSQL rehearsal remain developer-reported evidence; they were not repeated in this review.
- Compared current source hashes with the supervisor's September 30 snapshot. The **25 changed existing server/web files match the application-file list in the response**. Git history is not needed to make that comparison.

No new blocking defect was identified in this focused check of the original-workbook path. Existing broader import and mobile limitations remain outside this approval.

## Required production sequence

1. Re-read the current bases, saved maps and formats. Preserve all current records and the configured editor password. The earlier observation of an empty base list is historical, not permission to reset the database.
2. Record the pre-release deployment and current source hashes. Retain a recoverable pre-migration database backup and verify it is available before applying schema v7. Keep an independent copy outside the rotating backup list for this release.
3. Apply the additive migration before deploying code that queries `moneda`. Verify existing terrain and saved-map contents are preserved, with legacy currencies remaining NULL rather than guessed.
4. Deploy the reviewed source to the canonical production address, then verify the actual production browser flow. Local test success is not production verification.
5. Upload **`/Users/andrejasso/Desktop/ARA Map/Base Terrenos 09.26 copy.xlsx`** into a clearly named new demonstration base. Do not use the rounded CSV. If saved format 4 is present, answer Yes to restoring both price columns and answer USD to the currency question. Keep remembering enabled so the corrected format supersedes the old one.
6. Before calling the release ready, verify preview and persisted/reopened results: **79 terrains, 39 located, 59 total prices, 60 unit prices; Marceñas USD 388,689,722 and USD 600/m²; El Dorado USD 122.50/m²**. Preserve the source inconsistency warning.
7. Confirm login, map/detail display, saved-map reopen, and an Excel export with the USD currency and 122.5 value retained. Confirm the existing comparisons remain present. Report the deployment ID, new base name/id and production results.

## Release scope correction

The developer's statement that September 28 changes cannot be traced without Git is too broad. Hash snapshots exist. The September 30 baseline already differed from the earlier polish release in these files:

- `server/asistente/campos.py`, `detectar.py`, `perfil.py`, `plan.py`, `rejilla.py`, `servicio.py`
- `server/csv_importer.py`
- `web/components/import/AssistantViews.js`, `ImportAssistant.js`
- `web/styles/assistant.css`, `controls.css`

Those earlier changes were already part of the supervisor's September 30 audit, which documented remaining limitations. List them as carried-forward changes in the release response; do not describe the deployment as exclusively a currency patch. This scoped demonstration approval does not clear the previously reported worksheet-switch/excluded-row problems or preview-control limits. Avoid those operations in today's rehearsal.

## What can remain pending for this demonstration

- **Fresh Numbers-to-Excel export:** not a blocker when the presentation uses the exact existing XLSX verified above. Do not claim a newly exported file or direct `.numbers` upload has been tested.
- **CSV differences:** correctly explained by the source export. `US$ -` has no recoverable numeric zero, and the displayed 123 cannot recover 122.5. Those are reasons to use XLSX, not to invent values.
- **Existing maps without currency:** keep them unchanged and visibly unconfirmed. Use the newly imported USD base for the price demonstration.
- **Rollback:** an additive schema does not make an old application semantically safe. Old code can label newly stored USD as MXN. If rollback is necessary, suspend monetary demonstrations of those new records until labels are corrected; do not report rollback as an equivalent USD fix.

Update `DEVELOPER_RESPONSE.md` after the production check. Until then, the accurate status remains **verified locally, not yet live**.

# ARA Map — independent review of the F1–F5 fixes

Date: September 28, 2026.

**Decision: return for four focused corrections before deployment.** The original five fixtures now behave correctly, but F1 still has a currency-format bypass and the new row controls have three interaction defects. These are within the correction's scope, not the seven deferred layout capabilities. Do not enable AI to compensate for them.

## What I independently verified

| Check | Observed result |
|---|---|
| Original seven regressions, unmodified | 7/7 pass |
| New currency, reading and row-classification test modules | 59/59 pass |
| Original 36-file handler matrix, through confirmation/storage | 25 PASS, 6 MISMATCH, 1 UNRESOLVED, 4 REJECTED |
| Paid usage rows in that matrix | 0 |
| All original fixture hashes | 36/36 unchanged |
| Original evidence/results.json | Preserved; SHA-256 `58ebc70e81e619779eab644981672adc15d949eeea9d5b8999918544a1f4ba81` |
| New follow-up desired-outcome regressions | One control passes; four fail, covering R1–R3 |
| Three independent real-Chrome UI reproductions | Confirm R2–R4; zero page errors |

All new evidence is in this directory's `evidence/`; the earlier test evidence and developer response were not overwritten. Tests used fictional data and disposable SQLite. The temporary browser server, workbook and database were removed. No application source was edited, deployment performed, production database used, or paid AI call made. The running local app on 8420 was not used.

I did **not** independently rerun the full ordinary suite, all 65 developer browser checks, or disposable Postgres during this pass. Those remain developer-reported evidence. The response's ordinary Python count is 605 **including 21 skips**, hence 584 executed in that run; the separate 21-test Postgres run is reported separately.

## R1 — P1: valid currency formats still become stored MXN prices

**Location:** `server/asistente/campos.py:183–187` (`moneda_formato`, plus `_LITERAL_FORMATO`).

The new reader works for `"USD "#,##0.00`, but fails for these two equivalent forms of explicit foreign-currency evidence:

```text
\U\S\D\ #,##0.00
£#,##0.00
```

The first spells the literal USD prefix through adjacent escaped characters. The scanner extracts `U`, `S`, `D`, and a space, then inserts spaces between them with `" ".join(literales)`. `U S D` no longer matches USD. The second uses the pound symbol directly, which the literal regex never reads. Excel permits backslash-prefixed literal characters and permits certain symbols, including £, without quoting; see [Microsoft's custom-format guidance](https://support.microsoft.com/en-us/excel/review-guidelines-for-customizing-a-number-format).

**Reproduction:** use the four fictional rows from `tests.test_asistente_monedas.en_dolares`, substituting either format above on B2:B5. Analyze and confirm. Both receive a zero-question preview with four MXN prices; the database contains `[1200000, 2500000, 3750000, 4800000]` as `asking_price`. The quoted USD control stores four nulls, as intended. `review_regressions.py` reproduces both failures through actual confirmation and queries the stored rows.

**Correction:** tokenize number-format syntax while preserving adjacent literal characters and recognizing legal unquoted currency symbols. Separate sections and numerical/date tokens appropriately: simply joining all fragments without spaces could invent a currency across unrelated sections. Keep existing MXN/bare-dollar policy, quoted/bracket forms, and safe generic/date/percentage controls. Never interpret format syntax as permission to convert amounts.

**Acceptance:** both reproductions have null MXN prices in preview and storage, with the currency and original amount explained/preserved. Add coverage for adjacent escaped and quoted literal runs, £/¥ and supported currency symbols, bracket formats, and ordinary numeric/date formats. Exercise prepare and packed-draft reload as well as analyze. No need to add exchange-rate conversion.

## R2 — P1: a row decision transfers to a different worksheet

**Location:** `server/asistente/detectar.py:92–109` (`fusionar`); sheet corrections in `servicio._validar_correcciones`; worksheet selection in `AssistantViews.js`.

`incluir` and `excluir` are naked row-index arrays. Changing `hoja` leaves them in the draft. The same index is then applied to an unrelated worksheet.

**Reproduction, also completed in Chrome:** upload the two-sheet fictional workbook constructed by `review_regressions.two_sheets`. Select Table0, click **No importar** for its first terrain, then switch to Table1 under **Corregir interpretación**. Table1 contains three complete terrains but the preview lists only `Fictional 1-1` and `Fictional 1-2`; `Fictional 1-0` is excluded by a choice made on Table0. Confirmation stores only two records. Evidence: `worksheet-switch.png`, `browser.json`, and the failing storage regression.

**Correction:** scope row decisions to their source sheet/table identity, or clear them explicitly on a table change. A restored row must not automatically restore a footer at the same index on a different sheet either. Decide and document switch-back behavior. Apply this in the server for both question answers and manual corrections, not just the browser. CSV delimiter changes also create distinct candidate-table identities; do not transfer indexes between different readings without a proven source-row mapping. Header changes must discard or reconcile choices that are no longer data rows.

**Acceptance:** exclude on A, switch to B, preview and commit all three B terrains. Cover inclusion and exclusion, switching back to A, sheets with different header positions/row counts, and correction via public API. Confirm the resulting plan and saved rows, including after Postgres draft serialization.

## R3 — P2: removing the final terrain makes restoration inaccessible

**Location:** `server/asistente/servicio.py:194–200`; empty-state rendering in `web/components/import/ImportAssistant.js`.

**Reproduction:** upload a one-terrain CSV, then press **No importar**. `construir` correctly creates an excluded row, but `_responder` discards the entire built result because it contains zero accepted records. The dialog says **La tabla no contiene ningún terreno con nombre**, returns `estado=revisar`, and has zero restore buttons. The file did contain a name; it was the manager's reversible choice that removed it. Restarting the upload or calling the API directly is currently required. The same response path prevents recovery when initial classification excludes every row.

Evidence: `last-row.png`, `browser.json`, and `test_last_removed_row_keeps_a_recoverable_preview`.

**Correction:** retain excluded-row information and show a reversible review state even when zero rows are selected. Disable confirmation of an empty import, but keep **Sí es un terreno: importarla** or an equivalent restore/reset action. Distinguish zero selected rows from missing names. Do not allow old confirmation tokens to become reusable.

**Acceptance:** remove the final row, restore it in the same dialog, import exactly one terrain, and verify storage. Also cover a file whose rows are all automatically set aside and restoring after another correction. The supplied test uses an empty `vista_previa` as the concrete recovery contract; a separate review payload is acceptable if it provides the same browser recovery and is tested end to end.

## R4 — P2: row controls stop at arbitrary preview limits

**Locations:** `web/components/import/AssistantViews.js:150`, `server/asistente/servicio.py:293`.

**Reproduction completed in Chrome:** upload one complete terrain followed by 13 fictional note rows. The preview announces 13 excluded rows but renders only 12, with exactly 12 restore buttons; note 13 is absent. `excluidas.slice(0, 12)` has no pagination or show-more action. The backend sends all 13 exclusions. The existing display truncation is now also truncating the new correction capability.

There is a related limit on accepted rows: only the first 100 records are sent as `vista.filas`, and **No importar** exists only in that table. A later accepted row cannot be directly targeted through the UI. This latter limit was verified in code, not through a separate browser reproduction.

Evidence: `thirteen-exclusions.png` and `browser.json`.

**Correction:** provide paging, show-more, a source-row search, or an equivalent bounded interface that can reach every included and excluded source row. Keep physical file row numbers visible and translate to server-validated source identity. Do not solve this by rendering up to 50,000 full records at once.

**Acceptance:** restore excluded row 13 directly, without first changing decisions for rows 1–12; remove accepted row 101 directly, without excluding earlier valid terrains to reveal it. Confirm final storage, correct counts, keyboard access and row identity after pagination/corrections. Keep the maximum upload limits.

## Decisions on the two issues the developer flagged

**Remembered currency-derived mapping:** reproduced. Import quoted-USD cells with **Recordar este formato**, then upload a plain numeric MXN workbook with identical headings. It reaches preview with `con_precio=0` and no interpretation warning. It avoids wrong-currency prices, but a per-file observation has become a persistent instruction to ignore the price field. Schedule a follow-up: distinguish a user's intentional column mapping from a file-specific currency guard; reevaluate the latter on every upload. Keep the opposite-direction protection (MXN template followed by USD) intact. This is a known behavior, not counted as a new R1–R4 defect or expanded into the current layout work.

**Thin-evidence totals:** accepting a possible terrain is reasonable when evidence is inconclusive. This is acceptable provided the manager can reach and change the row decision. R3/R4 are necessary to make that safeguard usable. Do not replace it with broader name-prefix deletion.

## Return packet

1. Fix R1–R4 without implementing the seven separately scoped capabilities or enabling AI.
2. Preserve original fixtures and previous evidence. Add these reproductions and meaningful browser/storage checks to normal verification.
3. Rerun original seven checks and the 36-file matrix, plus the new tests. Return the per-file results, executed/skipped test counts, any changed behavior and exact source hashes.
4. Repeat relevant serialized-draft checks on disposable Postgres; production/Neon remains outside this correction pass.
5. Do not deploy until the follow-up review accepts the result.

Useful commands from the project root:

```sh
.venv-dev/bin/python reports/map-import-tests-2026-09-28/support/regressions.py -v
.venv-dev/bin/python reports/map-import-fixes-2026-09-28/supervisor-review/review_regressions.py -v
.venv-dev/bin/python reports/map-import-fixes-2026-09-28/supervisor-review/browser_run.py
```

The last command records observed UI behavior; it is an evidence collector, not a passing acceptance suite. Its current three reproductions confirm defects. Scripts depend on the repository test helpers and local Playwright/Chrome installation. All created servers/databases are disposable; none use the running app on 8420.

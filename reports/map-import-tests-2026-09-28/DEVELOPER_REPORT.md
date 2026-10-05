# ARA Map — varied-layout import review

Date: September 28, 2026. **36 fictional files: MapTest1 through MapTest36.**

**Decision:** conventional tables generally work, including several awkward layouts. The importer does not safely handle every presentation. Fix the five defects below first, then extend the explicitly listed layout capabilities. Do not enable AI as a substitute for fixing information lost before the model could see it.

## Deliverables and scope

- `files/`: **13 XLSX and 23 CSV** files, each with a distinct presentation or safety case. All names and amounts are fictional; coordinates are illustrative points in Mexico, not property boundaries.
- `TEST_MATRIX.md` / `TEST_MATRIX.csv`: every file, its purpose, observed result and recovery notes.
- `manifest.json`: source rows, intended column meanings and expected records. This is the reference for checking the implementation, not inferred output from the importer.
- `evidence/results.json`: complete analyze/prepare responses, chosen question answers, committed SQLite records and field-level mismatches for all 36 cases.
- `evidence/browser-results.json` and `browser-MapTest*.png`: actual browser uploads for five cases, including two confirmations.
- `support/regressions.py`: seven focused checks, **two controls pass and five defect checks fail** on the current code.
- `support/run_cases.py`: reproducible 36-file handler test; `support/browser_run.py` / `browser.mjs`: browser reproduction in a disposable database.
- `evidence/SOURCE_SNAPSHOT.json` and `FIXTURE_HASHES.json`: hashes of inspected application code and supplied files. Application files still match the previously deployed `POLISH_SOURCE_SNAPSHOT.json` (142/142 files).

No application code was changed. Production, Neon and normal local data were not modified. No paid AI call was made. The temporary browser server was stopped and its database deleted.

## What was actually tested

Every file was sent to the real application's analyze handler with AI disabled. Focused questions were answered using the known meaning of the fictional source columns; the exact choices are recorded. Every resulting preview was confirmed into a fresh temporary SQLite database and its stored records compared with the independent expected records. A separate re-upload tested manual correction for mismatches where feasible. Remembered formats were disabled on confirmation to prevent one case influencing the next.

This is **not** a claim that all cases imported automatically. The runner uses internal question decision objects only to select the corresponding public answer index; it does not bypass parsing, replace returned records or change source values. Manual API correction is explicitly distinguished from what the browser allows.

| Initial/guided outcome | Files | Meaning |
|---|---:|---|
| Expected outcome met | 20 | Includes 18 full-content imports and two safe foreign-currency/projected-coordinate limitations |
| Preview/committed content differs from the intended data | 10 | Includes defects, layouts beyond current support, and a case recoverable with manual mapping |
| No usable preview after the guided route | 2 | Transposed layout and header beyond the UI's search range |
| Clear rejection | 4 | UTF-16, Windows-1252, broken quoting, empty input |

These are designed boundary cases, not a representative accuracy benchmark. **Do not advertise 20/36 as model accuracy or 12 independent bugs.** No case crashed the tested handlers. Recorded paid-usage rows: zero.

Browser checks exercised MapTest1, 20, 22, 23 and 35 through the real file chooser. All analyze requests returned 200; MapTest20 and 22 also confirmed successfully with 200 despite their incorrect content. No JavaScript page exceptions occurred in the completed run. Browser automation initially encountered a response-body inspector error; the final run measured the rendered UI and HTTP status instead. A fresh database was initialized before serving concurrent browser requests. The final run's five completed cases are the browser evidence, not those preliminary harness attempts.

## F1 — P1: Excel currency formatting is discarded, turning USD into MXN

**File:** `MapTest20.xlsx`. Compare with `MapTest19.csv` (USD in header, handled safely) and `MapTest1.xlsx` (peso control).

**Steps:** upload the XLSX, inspect the preview, and confirm it in a test environment. Open the workbook to see that B2:B5 display `USD 1,200,000.00`, etc. The header is simply `Precio`; USD is expressed through the native Excel number format `"USD "#,##0.00`.

**Expected:** explicit foreign currency must not become an MXN price. Preserve the source amount/currency as additional information and explain that conversion is unsupported, or require a meaningful resolution before confirmation. Do not ask a generic price-column question that overrides the currency evidence.

**Actual:** zero questions; four priced terrains, labeled **“en MXN”**. `FICTICIO Encino` is committed with `asking_price=1200000.0`. All four prices are relabeled. The browser confirms this is offered and accepted in the ordinary flow.

**Cause:** `server/asistente/rejilla.py::_leer_hoja` uses `iter_rows(values_only=True)` for both workbook passes. `Hoja` and packed drafts retain cell values but no `number_format` currency information. `perfil.py`/`campos.moneda` consequently see neither USD nor a foreign-currency cell string; `plan.py::construir` cannot reject evidence already lost.

**Required change:** retain relevant per-cell Excel currency metadata in the structural grid and serialized draft. Parse number-format currency markers carefully, including quoted currency codes and currency locale sections; formatting is not itself permission to convert values. Feed this evidence through the same currency checks used for headers/text, including remembered formats, user overrides and future AI proposals. Preserve original currency context in preview/additional data.

**Acceptance:** MapTest20 cannot commit an MXN asking price, while MapTest1 and valid MXN/bare-dollar formatting still work. Include mixed-currency cells within one price column and explicit EUR formatting. Check both the preview and stored records; a warning that leaves incorrect MXN values writable is insufficient.

## F2 — P1: a real terrain beginning with “Total” is removed

**File:** `MapTest22.csv`; control `MapTest7.csv` contains a genuine summary row.

**Expected:** four terrains, including `Total FICTICIO Encino`, with its price, area and valid coordinates.

**Actual:** three terrains imported. The real row is marked `TOTALES` and excluded solely because its name starts with `Total `. The preview discloses the exclusion, but there is no browser control to restore the row. This is erroneous row deletion, not an invisible crash. The browser confirmation saved the three-row result.

**Cause:** `server/asistente/plan.py::_exclusion`, around lines 191–202, treats any `fold(nombre).startswith("total ")` as a summary without considering the rest of the row. An empty `excluir` list cannot override that automatic classification.

**Required change:** use more than a name prefix to classify totals. Where a totals-like label coexists with record evidence, ask whether it is a terrain or allow an explicit include override that survives preparation, preview and confirmation. Keep true summary rows excluded without sacrificing real records.

**Acceptance:** MapTest22 retains all four terrains, or asks and then retains the named terrain on confirmation. MapTest7 still excludes its genuine TOTAL row. Include `Total`, `Subtotal` and `Total …` as legitimate names as well as actual summary labels.

## F3 — P2: tab-separated CSV is accepted as a one-column terrain list

**File:** `MapTest29.csv`, an actual UTF-8 tab-delimited text table with five fields per line.

**Expected:** either detect tabs and recover five columns, or stop with a specific unsupported-delimiter message and instructions to export comma/semicolon CSV. Do not represent the whole row as a valid terrain name.

**Actual:** the reader tries comma and semicolon only. Both see a one-column file. The assistant asks which column is the terrain name; accepting the apparent name column leads to four committed names such as `FICTICIO Encino 1200000 2400 19.4326 -99.1332`, with no price or coordinates. This case is a parsing/support boundary that should be identified before business-field mapping.

**Locations:** `server/asistente/rejilla.py::_leer_csv`, `_lecturas_plausibles`; `server/csv_importer.py` delimiter reader; separator choices in `web/components/import/AssistantViews.js::Correcciones`.

**Required change:** add consistent tab detection and a labeled UI choice, or detect the repeated tab structure and reject it clearly. Do not reject genuine single-column terrain-name lists just because they have one field. Preserve CSV quoting and newlines.

**Acceptance:** five correctly separated columns and correct records, or a clear non-importable outcome. MapTest26 quoted/multiline text and ordinary comma/semicolon controls must remain valid.

## F4 — P2: the real header after row 50 cannot be selected in the UI

**File:** `MapTest35.xlsx`: 55 nonblank notes, header on physical row 56, four terrains below it.

**Actual:** automatic detection searches only the first 50 rows. More significantly, **Corregir interpretación → Fila de encabezados** offers only those same 50 rows. The browser has no row-56 option. The guided route cannot reach the intended table.

**Counter-check:** a new analysis followed by API corrections with `encabezado: 55` and the known column mapping produces all four correct terrains. This proves that parsing the data is supported and the recovery UI is the limiting step. That API-only recovery is not counted as a usable boss workflow.

**Locations:** `server/asistente/detectar.py::BUSQUEDA_ENCABEZADO` and `_candidatos_encabezado`; `server/asistente/servicio.py::_interpretacion` slices `encabezados[:50]`; `web/components/import/AssistantViews.js::Correcciones` builds only a select from those entries.

**Required change:** keep a bounded automatic search if needed, but provide “another row” with a validated physical-row selector, search or paging over the actual parsed sheet. Translate physical Excel row numbers to retained nonblank-row indices correctly. Do not make the user guess an internal zero-based index.

**Acceptance:** reach row 56 through the UI, preview the four terrains and import them. Add a control with blank rows before the true header so displayed and internal indices cannot be confused.

## F5 — P2: a footer becomes a terrain, with no row-exclusion control

**File:** `MapTest23.csv`: four complete terrains followed by `NOTA: valores sujetos a revisión` and four empty fields.

**Actual:** five terrains offered for import. The note is counted as a fifth terrain without location or price. The browser shows `Terrenos 5` and `Fuera del mapa 1`; it does not ask whether the footer is data. Mapping corrections offer sheets, headers, numeric convention and columns, but no exclude-row control.

**Counter-check:** `correcciones: {excluir: [5]}` through the existing prepare API yields the correct four records. The browser does not expose that existing backend capability. Unlike F2, there is already an API path to remove this row.

**Locations:** `_exclusion` and `construir` in `server/asistente/plan.py`; `Filas`, `Excluidas` and `Correcciones` in `web/components/import/AssistantViews.js`.

**Required change:** surface per-row include/exclude decisions with source row numbers and preview refresh. Flag plausible footer/note rows for review. Do not automatically discard every name starting with “Nota”, because that would repeat F2's mistake. An explicitly confirmed name-only terrain must remain supported.

**Acceptance:** default import must not quietly treat this obvious footer as a terrain; it should be excluded with an explanation or require classification. The boss must be able to remove it in the preview. Confirm exactly four rows, and test real name-only records separately.

## Additional capability gaps, separate from the five defects

| Files | Observed limitation | Developer direction |
|---|---|---|
| MapTest8 | First-time repeated `Precio` headings: choosing total leaves the second price as extra data. Full manual column mapping recovers both prices. | Improve the focused question so both meanings can be confirmed. Preserve the existing saved-format duplicate-heading protections. |
| MapTest12 | Transposed property cards do not become terrain rows. | Detect orientation and offer a transpose interpretation, or explain how to reshape the file. Never accept field labels as property names. |
| MapTest13 | Two side-by-side tables: the selected left table yields two terrains; the right table is extra data, not another two records. | Detect table regions and let the user choose/import each or combine compatible regions explicitly. The source has no area column; the oracle correctly makes no area assertion for this case. |
| MapTest15–16 | Combined coordinate strings and degrees/minutes/seconds reach previews with zero located terrains. Their contents are retained or produce numeric findings rather than usable coordinates. | Add explicit parsers and coordinate-order/hemisphere checks, or give precise preparation instructions. UTM (MapTest17) must remain unsupported until CRS-aware conversion is deliberately implemented. |
| MapTest18 | European price text with point-decimal coordinates cannot be represented by one global numeric convention. Choosing point-decimal drops prices with warnings; switching globally risks coordinate interpretation. | Support validated per-column conventions or stop for an actionable correction. Do not guess per cell from magnitude. |
| MapTest34 | No header row: the first terrain is treated as the header and lost even after field mapping. | Add an explicit “no header row” option with generated column labels and include the first source row as data. |

UTF-16 and Windows-1252 (MapTest27–28) are currently rejected with a clear UTF-8 export instruction. They are optional compatibility improvements, not unexpected crashes. Malformed quoting and empty files (MapTest30–31) should continue to fail clearly.

## Developer work order and return criteria

1. Address F1 and F2 first; they change the meaning or presence of otherwise valid records. Then F3–F5. Preserve original source values and explain any excluded/uninterpretable data.
2. Keep the supplied fixtures unchanged; their hashes are recorded. Add the focused regressions to normal verification, with equivalent stronger UI tests where the proposed solution needs interaction. Tests allowing a clarification must also complete that clarification and validate the final stored result—an endless question screen is not a fix.
3. Run the full 36-file matrix again and return file-by-file results. Do not count manual API-only fixes as browser successes. The manifest is an oracle, not a requirement to magically infer inherently ambiguous inputs without asking.
4. Verify currency metadata and row decisions through both SQLite and disposable Postgres draft serialization, then preview → confirm → saved map. This review did not rerun the 36 cases on Postgres or on production.
5. Preserve familiar-file zero-question behavior, focused ambiguities, CSV compatibility, folder choices, append conflicts, remembered formats and immutable saved snapshots. Re-run the ordinary suite and affected browser tests after changes.
6. Treat the additional capability table as the next scoped enhancement plan. Do not promise universal support for every file layout, file type or corrupted input. `.xls`, `.xlsm`, PDFs, images, password-protected workbooks, giant uploads and real AI were not covered by this 36-file set.

Run focused safety regressions from the project root:

```sh
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL python3 reports/map-import-tests-2026-09-28/support/regressions.py -v
```

Run all supplied files through the handlers:

```sh
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL python3 reports/map-import-tests-2026-09-28/support/run_cases.py
```

Return an updated developer response with each finding addressed, test outcomes, remaining limitations and source hashes. Do not deploy fixes as part of this review packet's instructions; the requested deliverable here is a reproducible diagnosis for implementation.

# Urgent decision: restore the real ARA workbook with correct USD prices

Prepared October 1, 2026, for the developer. The client meeting is today.

## Decision

**Implement a focused USD import-and-display correction. Do not roll back the entire application.** The original Excel reader still reads the real workbook. The missing prices have two reproduced causes: an MXN-only currency rule and a saved format that now maps both price columns to additional data.

The supervisor confirmed today that the source prices are **US dollars**. Apple Numbers displays `US$` in the actual attached document. The original application guessed MXN from the amounts; that assumption was wrong for this source. Showing the old numbers again with MXN semantics is not a valid repair.

This is a bounded correction, but **not a one-line currency-label change**. Give priority to the exact source, USD preservation, the stale saved format, and a verified Excel upload. Defer AI, new file types, other layout enhancements and unrelated UI work. No claim is made that this can be completed within a particular number of minutes.

If the minimum acceptance checks below cannot pass before the meeting, use the source workbook and the existing presentation for a limited demonstration. Do not substitute a rollback that mislabels dollars as pesos, and do not present a fresh import as working until it is verified.

## What was checked

No application code, source workbook, production record, saved format or deployment was modified in this review. Production access consisted of reads and editor login/logout. Parser reproductions ran locally without database writes or AI calls. Numbers was opened to read values and displayed formats; no export or save was performed.

| Source | Verified observation |
|---|---|
| `/Users/andrejasso/Desktop/Base Terrenos 09.26.numbers` | Native Numbers document; `Registro Análisis` has 81 rows and 14 columns. There is also a separate `Data Prospectos` table, 424 × 10. Import the intended terrain sheet, not all tables together. |
| Same document, `Registro Análisis`, J2 | Numeric value **388689722**, displayed **US$ 388,689,722**. |
| Same document, K2 | Numeric value **600**, displayed **US$ 600**. |
| Same document, K4 | Numeric value **122.5**, displayed **US$ 123** because the cell display rounds it. |
| `/Users/andrejasso/Desktop/ARA Map/Base Terrenos 09.26 copy.xlsx` | Original Excel copy, byte-identical to `tests/fixtures/base_terrenos_09_26.xlsx`. The current parser accepts it. |
| `/Users/andrejasso/Desktop/Base Terrenos 09.26 copy.csv` | Export modified today at 13:37 local time; explicitly contains `US$` in both price columns. The K4 equivalent has already been rounded to **123** in this CSV. |

**Use a genuine Excel export from Numbers for the definitive import. CSV is not a harmless substitute here:** it preserves displayed currency text but loses precision already rounded by Numbers. Do not claim the CSV can recover 122.5 from the exported value 123. The existing original Excel copy preserves 122.5.

The user identified the Desktop source as “Base Terrenos 09.26.” The file supplied there is `.numbers`, not `.xlsx`. The exact rejected `.xlsx` upload and its error were not supplied; a general XLSX upload failure has **not** been reproduced.

### Reproduced results

All cases below read the `Registro Análisis` inventory or its CSV equivalent.

| Parser / remembered settings | Terrains | Located | Total prices | Unit prices | Questions |
|---|---:|---:|---:|---:|---:|
| Legacy reader, original XLSX | 79 | 39 | 59 | 60 | — |
| Current assistant, original XLSX, clean settings | 79 | 39 | 59 | 60 | 0 |
| Current assistant, original XLSX, reconstructed production format 4 | 79 | 39 | **0** | **0** | 0 |
| Current assistant, today's CSV, clean settings | 79 | 39 | **0** | **0** | 0 |

The successful numeric XLSX cases do **not** establish correct currency handling. The source's `[$$-409]` number format currently passes as a bare dollar symbol and the application still labels the result MXN.

Machine-readable reproduction: `evidence/reproduction.json`. Format 4 was reconstructed from the authenticated read-only `/api/formatos` response; no database connection or modification was used to obtain it.

## Root causes and exact code locations

1. **Wrong original currency assumption.** `web/lib/format.js:3–10` explicitly says the workbook's format is US dollars but assumes pesos based on the magnitudes; it sets `CURRENCY = "MXN"`. Remove that assumption. Its comment claiming only one line needs changing is now false because the importer and preview enforce MXN independently.
2. **Explicit USD deliberately becomes extra data.** `server/asistente/campos.py` labels price destinations MXN and rejects foreign currencies. `server/asistente/detectar.py:372–389` remaps them to `extra`. `server/asistente/plan.py:128–136` rejects even an explicit user mapping to price when the column has foreign currency evidence. `server/asistente/servicio.py:324` reports `moneda: "MXN"`. This explains the CSV outcome; it is not missing price data in the source.
3. **The exclusion has been remembered.** Production format **id 4**, `Formato de «Base Terrenos 09.26 copy»`, created **2026-10-01 19:38:19 UTC**, maps `asking price` and `asking $/m2` to `extra`. `_aplicar_formato()` applies it and `_por_nombre()` skips fields already assigned by a saved format (`server/asistente/detectar.py`, approximately lines 280–335). That makes even the old numeric XLSX return zero prices on the next import. Reproduced locally with those exact relevant decisions.
4. **No native Numbers support.** `web/components/bases/ImportDialog.js:15` accepts `.xlsx,.xlsm,.csv`. `server/asistente/rejilla.py:136–146` reads those formats and explicitly tells Numbers users to export. An extension rename is not an Excel export. XLSX support was not removed in these code paths.
5. **Currency is not carried through the data model.** Price numbers exist in `TerrainRecord`, `terreno` and `mapa_terreno`; no currency accompanies them. Formatters, legends, filters and spreadsheet exports therefore share the old single-currency assumption. Removing only the USD blocker would recreate the earlier semantic error.

## Minimum implementation for this incident

### A. Carry the currency with the price

- Support **USD and MXN** for this release. Preserve amounts; perform **no exchange-rate conversion**.
- Store explicit currency with imported terrain prices and frozen saved-map records. A single currency per imported table is sufficient for this urgent release, provided the server validates that the total and unit-price fields do not contradict it. Persist it through new-base imports, append/corrections, API serialization, save/reopen, refresh, comparison merge and export. Do not infer a record's currency from whichever base or view is currently selected.
- If adding a `moneda` field, update SQLite and PostgreSQL schema/migration paths, `TerrainRecord`, repository column lists and serialization together. Include currency in append change detection and layer fingerprints. A value of 600 USD and 600 MXN must not compare as unchanged or duplicate content.
- Do not globally relabel existing records or saved maps USD. Their stored numbers have no reliable currency metadata. Preserve them, and require source-specific confirmation before changing their meaning. The source confirmation in this conversation applies to the attached real workbook, not every old fictional dataset.
- Recognize `US$`/`USD` in headers or cells. Treat unambiguous supported Excel currency declarations as evidence. When a bare `$` or a locale-based format leaves currency uncertain, ask one plain currency question rather than infer it from geography or price magnitude. For this exact workbook, the supervisor has confirmed USD; the acceptance test must reflect that.
- Parse the numeric amount only **after** resolving the currency. Do not strip `US$` and reuse a parser that implicitly means pesos. Maintain blanks, `SD` and other no-data markers as missing values, not zero.
- For mixed or conflicting currencies within one table, stop and ask for correction, or keep the unsupported/conflicting values out of priced fields with a clear explanation. Do not guess from the first nonempty row. Leave EUR and other unimplemented currencies explicitly unsupported for now.

### B. Remove the saved-format conflict without destroying user work

- Handle **format 4 specifically**. After the corrected importer is ready, forget or supersede that stale mapping and re-confirm the original file. Do not delete all saved formats or reset the production database.
- Merely forgetting format 4 **will not fix the USD CSV** until currency handling is corrected.
- Make currency-based exclusions distinct from deliberate user exclusions. A saved decision made because USD was unsupported must not permanently suppress recognized price fields once USD is supported. Preserve intentional mappings, and ask if their intent is uncertain.
- Store currency confirmation in the import plan/provenance and, if reused, the saved format. A saved USD template must not silently override a later file explicitly marked MXN. Update plan/version compatibility as needed and reject stale previews from the previous interpretation.

### C. Show and export USD consistently

- Update `web/lib/format.js` and every caller in terrain details, terrain table, map tooltip, filter rail, legend and import preview. Display **USD** explicitly, including compact labels; a generic `$` remains ambiguous. Keep unit-price cents: **USD 122.50/m²**, not 123.
- Update the import labels and summaries in `AssistantViews.js` and `servicio.py`; remove claims that all supported prices are MXN.
- For a USD-only selection, price filters and color bands operate on USD. If a comparison contains different currencies, keep geographic comparison available but disable shared price bands, common monetary sorting/filtering or totals until a single currency is selected. Do not rank 100 USD against 100 MXN as equal.
- Update `server/api/exportar.py` to include currency explicitly and retain sufficient unit-price decimals. Preserve one sheet per comparison source. Export and re-import must retain both numeric amount and currency. Do not treat a cosmetic cell number format alone as durable currency storage.
- Keep original source values and existing inconsistency warnings. J2 is **388,689,722 USD** in the source even though it conflicts with area × unit price. This incident does not authorize replacing it with a calculated price.

### D. Verify genuine Excel upload end to end

- In Numbers, use **File → Export To → Excel** into a new file, leaving the original untouched. Select `Registro Análisis` in the assistant if necessary. Do not rename `.numbers` to `.xlsx` or require a CSV conversion.
- First reproduce with `/Users/andrejasso/Desktop/ARA Map/Base Terrenos 09.26 copy.xlsx`, then with the new genuine Excel export. They are related sources, not proof of identical whole documents: the attached Numbers file has an additional worksheet.
- If a genuine XLSX still fails in the browser, capture its name, byte size, sheet selected, HTTP status and displayed error. Fix that specific error before declaring XLSX repaired. The existing 14,689-byte original workbook is well below the observed 4 MB upload limit.

## Required acceptance before deploying this correction

1. Upload the original XLSX into a clean **disposable** workspace through the actual browser flow. Reach a preview of **79 terrains, 39 located, 59 total prices and 60 unit prices**, explicitly USD, without a CSV conversion. Exclude neither genuine terrains nor their prices.
2. Confirm and reopen the base. Verify **Marceñas: 388,689,722 USD total; 600 USD/m²** and **El Dorado: 122.5 USD/m²**. Confirm values in storage/API as well as the visible labels. Missing coordinates remain missing.
3. Repeat with format 4's stale price-to-extra configuration present. The repaired flow must recover or explicitly request the necessary mapping correction; it must not silently report a successful price-less import.
4. Repeat using the genuine Numbers-to-Excel export and the correct sheet. Reconcile every accepted record and both price columns with native numeric source values, not only the first row. Test the USD CSV too, but acknowledge its existing rounding rather than invent precision.
5. Save and reopen a map, create a comparison, and export/re-import Excel. Verify currency and unit-price precision survive. Add a known MXN fixture to prove mixed-currency monetary comparisons are blocked or separated while geographic comparison still works.
6. Repeat the persistence/migration checks on disposable PostgreSQL. If schema changes, verify migration and existing snapshot preservation before applying it to Neon.
7. Ensure old previews are invalidated appropriately, existing auth still works, no paid AI is enabled, and no unrelated September 28 changes ride along without review. Run relevant regression suites plus the ordinary project verification.
8. Before production work, back up current data and identify the exact deployment baseline. After deploying the reviewed correction, verify the **production browser** upload/preview with this real file and an explicitly identified import destination. Do not overwrite or append to arbitrary old records. Report the new deployment ID and proof of the expected counts and currency.

## Rollback investigation and production state

The legacy reader in `server/importer.py` still produces the original 79 / 39 / 59 / 60 result today. Therefore broad import support has not destroyed its ability to read the original numeric XLSX. That is a valid compatibility baseline, **not a USD-correct release**: the UI already assumed MXN before the assistant.

The September release record identifies pre-assistant deployment **`dpl_6FJdk541wty2XfsqSehqCmBqRhRu`** as its previous production target. It has not been independently rebuilt or validated against today's schema in this incident, and is **not approved for a blind rollback**. No verified older end-to-end USD-correct version was found.

Current production inspected today: **`dpl_GtcUn7XczFo1FdciNZ9XUdjH3fkU`**, `ara-gktzas766-aicore2.vercel.app`, serving **https://ara-map-ivory.vercel.app**. This is the September 30 password-only redeployment of the previously live source, not an import fix. Preserve the currently configured production secret; do not restore credentials from an old deployment or put them in the handoff.

At review time, **`GET /api/bases` returned an empty list**, while **two saved comparisons still existed** (ids 1 and 4), containing frozen real and fictional layers whose source bases no longer exist. This fits the user's “from zero” attempt, but the review cannot attribute who deleted anything. Do not restore a historical database backup merely to change code, and do not assume old maps disappear when their bases are deleted. Recheck this state before any mutation.

The earlier presentation's instruction to open the old Gerardo base is therefore no longer a valid live-demo route until a verified replacement has been imported. Its captured screens remain historical evidence, not today's live inventory.

## Deliver back to the supervisor

Write `DEVELOPER_RESPONSE.md` beside this handoff. Lead with whether the exact real XLSX now imports correctly in production, its counts, and USD evidence. Include the saved-format resolution, schema decision, representative numeric checks, tests, files changed, deployment ID and anything still unverified. Do not lead with total passing tests while the real source remains untested.

**Success means the original terrain file works with its actual USD meaning. It does not mean merely making nonempty price numbers appear.**

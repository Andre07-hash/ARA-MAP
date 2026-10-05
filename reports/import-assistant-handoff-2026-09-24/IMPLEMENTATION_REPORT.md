# ARA Map — flexible import assistant

Developer handoff, September 24, 2026. Based on inspection of the current local source. This document specifies future behavior; no application changes, AI integration or deployment were performed in preparing it.

## 1. Approved experience and delivery sequence

Build an import assistant shared by **Importar base** and **Agregar terrenos**. It must turn differently organized Excel/CSV tables into the existing terrain model without requiring the manager to edit the source file.

**The approved manager experience is: upload → automatic analysis → answer only necessary questions → review data/map → import. There is no “Use AI?” choice, AI button or provider/model setting in the import flow.** This revision supersedes the earlier proposal for a separate “Sugerir con IA” action and a compulsory mapping wizard.

Deliver one feature in two internal implementation milestones:

1. Build discovery, deterministic detection, reusable formats, targeted clarification questions, optional correction controls, validation and exact preview/commit behavior.
2. Integrate automatic AI assistance for unresolved supported layouts, with server-side validation, cost controls and graceful fallback. Familiar formats should not call AI. A configured deployment automatically uses it when useful; the boss does not activate it per file.

The local edition must retain a usable no-key/offline path through deterministic detection and specific clarification questions. AI availability is an administrator/deployment concern, not a decision the manager must make during import. A milestone-1 demo is reviewable progress, but it is not delivery of the complete automatic AI-assisted feature.

Start milestone 1 now and build milestone 2 against a stubbed provider until server credentials and a spending limit are configured. Return code, fixtures, test results and a preview for review before publishing. No production deployment, purchase or paid API activation is part of preparing this handoff. Report missing provider configuration precisely; do not ask the boss to compensate with an AI toggle.

## 2. Existing behavior to preserve

ARA already supports `.xlsx`, `.xlsm` and UTF-8 `.csv`; reordered recognized columns; header aliases; validation; preview/confirmation; append conflict resolution; folders; saved maps and comparison exports. The local upload ceiling is 25 MB and the configured cloud ceiling is 4 MB. Preserve these contracts and editor authentication.

Only the terrain name is currently required to save a row. Coordinates are needed to map it; missing prices are permitted with appropriate disclosure. Do not silently make all three fields mandatory. Clearly distinguish a database that can be saved from one whose terrains can be plotted or priced.

Existing ARA files use **X = latitude, Y = longitude**, contrary to usual GIS usage. Existing saved maps are snapshots; importing or mapping a file must not refresh them implicitly. Preserve base/map folders, append behavior and comparison/export semantics.

Relevant source locations:

| Location | Current limitation / work required |
|---|---|
| `server/importer.py`: `COLUMN_ALIASES`, `map_headers`, `read_workbook`, `_build_record` | Fixed worksheet/header assumptions and alias mapping; introduce an explicit import plan without duplicating terrain construction |
| `server/csv_importer.py`: `_Reading.valid`, `_choose_reading`, `read_csv_bytes` | CSV recognition currently depends on identifying a terrain-name header; separate structural parsing from domain recognition so an unfamiliar header reaches the mapping editor |
| `server/csv_numbers.py`, `server/validation.py` | Reuse numeric and location validation; preserve source values and warnings |
| `server/api/importar.py` | Separate discovery, configured preview and confirmation; retain new-base/append paths |
| `server/staging.py` | Existing preview tokens are single-use, expire after 30 minutes, and use Postgres in cloud mode; extend deliberately for draft configurations and revisions |
| `web/components/bases/ImportDialog.js`, `web/lib/api.js` | Replace the file-picker/preview transition with the assistant while retaining folder selection and conflict decisions |
| `server/app.py`, `api/index.py` | Register new routes and enforce limits/editor access in both deployments |
| `server/db.py`, `server/postgres.py`, `scripts/migrate_cloud.py` | Persist templates/provenance with additive migrations, backups and cloud parity |

## 3. Manager workflow

Use Spanish labels in the product and explain decisions with actual sample values.

1. **Subir archivo.** Preserve the selected file, destination base or folder, and proposed database name throughout the flow.
2. **Analizando archivo…** Automatically identify the table, header, columns and compatible saved format. If deterministic evidence is insufficient and AI is configured, invoke it automatically in this step. Use ordinary progress wording; never make the manager choose an algorithm.
3. **Aclarar solo lo necesario.** Skip this step when the interpretation is clear. Otherwise show a short question with actual column names and sample values, such as “¿Cuál columna contiene el precio total de venta?” or “Encontramos dos tablas de terrenos. ¿Cuál quieres importar?”. Ask only unresolved questions, retain prior answers, and never require the boss to map all columns because one is unclear. When the needed field is absent, offer the appropriate missing-data outcome instead of forcing a false answer.
4. **Revisar datos y mapa.** Show interpreted rows beside original values, terrain counts, prices and units, a small map, invalid/unlocated rows, and warnings. Include an optional “Corregir interpretación” control for worksheet/header, field assignment, delimiter and numeric settings. This editor is available for corrections, not a compulsory stop on every import. Show original column labels/positions and samples; retain “Conservar como dato adicional” and explicit “No importar”. Technical detection provenance belongs in expandable details, not the main workflow.
5. **Importar / Agregar terrenos.** Retain explicit save confirmation and append conflict choices. Default “Recordar este formato” on, without requiring a template name or selection; persist only after successful confirmation. Provide optional format management outside the primary flow. Cancelling creates no base, terrain, map or reusable format; temporary draft storage is permitted and expires.

For familiar formats, the complete interaction is upload → preview → import. For unfamiliar but unambiguous layouts, automatic analysis should also lead directly to preview. Ask a question when evidence conflicts or remains ambiguous; an AI assertion alone cannot resolve a genuine ambiguity about price, units or coordinates. Do not show an “Apply AI suggestions” confirmation. The ordinary preview and final import confirmation cover a validated interpretation; explicit user corrections always win.

Example mapping the manager should be able to configure:

| Incoming column | ARA field |
|---|---|
| Nombre comercial | Terreno |
| Valor de venta MXN | Precio total |
| Área del predio (ha) | Superficie en hectáreas |
| Norte / Lat | Latitud |
| Este / Lon | Longitud |

These are examples, not unconditional synonyms: “Norte/Este” can refer to projected coordinates and must be checked against values/units before suggesting geographic latitude/longitude.

## 4. Discovery and mapping contract

Separate these stages: **parse file structure → choose table → map fields → normalize values → validate → preview → commit**. A structurally valid table with unknown headings must reach mapping, not fail with “Falta Terreno”. Malformed quoting, unsupported encoding and unsafe/unreadable workbooks still produce structural errors.

- Preserve strict CSV quoting, physical line numbers, UTF-8/BOM handling, comma/semicolon support and `sep=` directives. Delimiter selection must not depend on a known terrain alias. If multiple structural interpretations are plausible, show the sample and let the manager choose.
- Discover likely headers in a bounded leading sample, initially 50 nonempty rows, and permit explicit selection outside that suggestion range within the parsed sheet. Do not treat the search bound as the end of the file.
- Select one worksheet/table per import in this delivery. Automatically unpivoting reports, merging multiple sheets, OCR/PDFs, geocoding addresses, Google Maps URL resolution and UTM/DMS conversion are outside this delivery. Explain unsupported layouts without corrupting them.
- Give columns stable positional IDs, such as `sheet:2/column:5`, independent of their label. Duplicate/blank headings must remain separately selectable, with visible source positions. Never use a header-to-value dictionary that overwrites duplicates.
- Permit at most one source for each canonical target field, except an explicitly supported transformation with its own validated contract. For this delivery, use one-to-one field mapping; do not synthesize a name or combine cells automatically.
- Name, address, state and municipality map to the existing text fields. Map total price and price per m² separately; surface m² and hectares separately; percentage and affected m² separately. Preserve original identifiers; do not pretend row-number IDs are stable terrain identities.
- Repeated data columns claiming the same field require choosing the source or retaining the other as additional data. Unknown columns default to additional data. Give duplicate/blank extra labels unique display names while retaining their source ID and original label.
- Selected title/preamble rows and any explicitly excluded rows must be listed/countable. Within the selected data region, every nonblank row must be imported, rejected with a reason, or explicitly excluded. Totals/footer/repeated-header rows must not silently become terrains or disappear.

Deterministic suggestion priority: an unambiguously compatible saved format matched automatically; exact recognized names; normalized accents/case/spacing; a curated alias table; then value/type/range clues as supporting evidence. Conflicts reduce certainty. AI may propose remaining assignments after this pass, but must not override an explicit user answer or silently resolve contradictory evidence. Do not use a numeric column alone to infer whether it represents a total price, unit price, area or coordinate. Prefer plain questions and actionable warnings over uncalibrated probability percentages.

## 5. Coordinate, money and unit safeguards

For legacy ARA headers retain X→latitude and Y→longitude as visible defaults. In a generic import, X/Y alone are ambiguous: show both sample values, explain the convention, and require acknowledgement of the assignment when values conflict with it. Never silently swap axes, negate longitude or manufacture coordinates. Range checks can warn and suggest; only an accepted mapping changes interpretation.

Preserve Mexico-specific location validation. A point outside supported bounds remains visible as invalid/unmapped with its original values. Do not claim the map shows a surveyed parcel boundary; the existing area circle remains an approximation.

Keep an explicit numeric convention in every import plan. Reuse a compatible confirmed format or detect the convention only when the values establish it unambiguously; otherwise ask a concrete question showing the two interpretations, such as whether `1,234` means 1234 or 1.234. Do not require every CSV upload to pass through a decimal-settings dialog. For numeric **text** in flexible Excel layouts, use the same strict approach; actual typed Excel numeric cells should not change when the text-number convention changes. Do not globally alter the legacy Excel converter without documenting and testing compatibility. Show the interpreted convention in review details; never infer separators independently per cell or let AI's confidence settle an intrinsically ambiguous number.

Distinguish `ha`, `m²`, total price, price/m² and percentage. Assign an explicit hectare column to `superficie_ha`; do not place it directly into m². Any future conversion must show the exact rule and original value. This feature must not invent missing prices from area or vice versa.

ARA currently displays prices as MXN. Show that assumption. If USD/another currency is explicitly indicated, block treating it as MXN: retain it as additional data or require supported currency handling in a separately scoped change. No silent exchange-rate conversion or stripping “USD” to save a peso value. Missing price remains unknown, not zero.

## 6. Server contract and durable staging

The following route names are proposed; the developer may choose equivalent names but must document the final contract:

| Request | Purpose |
|---|---|
| `POST /api/importar/analizar` with raw file bytes and `X-Archivo` | Structural inspection, draft token, worksheet/header candidates, positional source columns and bounded samples |
| `POST /api/importar/preparar` with draft token, revision, selected sheet/header and mapping/settings | Deterministically construct and validate every row, perform append classification when applicable, issue a configured preview token |
| Existing confirmation/append endpoints | Commit the exact normalized result associated with the confirmed preview |
| Template CRUD routes | Persist reusable formats without storing source row samples |
| Internal AI suggestion step / authenticated route | Called automatically by analysis when needed; return a validated proposal for the active draft revision; no business-data commit |

Use an explicit versioned `ImportPlan` covering sheet identity, header/data-region selection, delimiter, numeric-text convention, source-column IDs, canonical targets, excluded columns/rows and provenance. Bind it to the source file hash and parser version. Validate all IDs, targets, options and bounds on the server; never trust client-provided normalized terrain records.

Keep the raw upload transport within the configured limits; do not base64-wrap a 4 MB upload in JSON. Bound rows, columns, decompressed workbook work, sample lengths and temporary storage, and return useful size/complexity errors. Macros and formulas must never execute; disclose missing cached formula results.

Store enough temporary source material or a lossless parsed grid to regenerate a preview after edits. In Vercel, this must survive separate worker invocations; process memory or `/tmp` alone is insufficient. Use the existing Postgres storage approach with explicit draft expiration/cleanup and a bounded capacity, rather than keeping uploaded files indefinitely. New draft/detail APIs must require editor access, including any GET that exposes samples; the current general GET policy is not sufficient for private draft retrieval.

Every mapping, sheet, row or numeric-setting edit invalidates the prior preview and append choices. Generate a new revision/token. Older responses must not replace newer UI choices, and the server must reject superseded confirmation tokens. Tie async suggestions to both draft and revision. Disable saving while the current preview is missing/in flight. Consume tokens atomically and preserve no-duplicate confirmation behavior.

Validate destination folder/base at commit and preserve atomic rollback. Keep the existing append reclassification against current stored rows; new mapping must not bypass conflict resolution. Keep external AI requests outside database sessions/advisory locks so model latency cannot block the shared workspace.

## 7. Reusable format templates

Persist reusable formats in the same local SQLite/shared Postgres workspace as the relevant installation. They are import configurations, distinct from database/map organization folders. Generate a readable default name from the confirmed import; editors may rename/delete them in optional format management. A successful import with “Recordar este formato” selected creates or explicitly versions a compatible format; do not silently overwrite another conflicting template. Do not rely solely on browser local storage for shared templates.

Store normalized header signatures with duplicate occurrences, source selectors, field assignments, numeric convention, explicit units, parser/plan version and creation/update times. Never store sample terrain values in a template. Keep per-import provenance separate: file hash/name, sheet/header selection, plan revision, selected template version and final accepted assignments. When appending, record the new import event without replacing the provenance of the base's original import.

If an incoming file only reorders uniquely named columns, resolve by its signatures, not old positions. Match automatically without requiring the manager to select a template. Missing fields, new collisions, ambiguous duplicates or incompatible settings require review of the affected decisions. If multiple templates disagree, do not choose by name or recency alone: resolve from file evidence or ask the specific resulting question. A matching template proposes a plan; it never skips final preview or per-file value validation. Editing/deleting a template must not alter previously imported data or saved maps.

Add schema changes through the existing backup/migration paths for SQLite and Neon. Include new durable tables in backup/restore coverage and ID handling where needed; exclude temporary drafts from durable business-data backups unless deliberately required. Test upgrading an existing folder-enabled schema without changing terrain/map content.

## 8. Automatic AI assistance — internal milestone 2

AI's only job is to suggest a mapping/configuration when deterministic detection is inconclusive. The application calls it automatically when configured, validates its proposal and builds the ordinary preview or targeted questions. It may return `unknown`; the application then asks the manager a concrete data question. It must not return new terrain rows, alter source values, infer a location from a customer name, invent a price or approve an import.

Request a constrained structured response with allowlisted source column IDs and target fields, a short reason per suggestion and ambiguity warnings. Validate the response against the schema **and** the actual draft/semantic rules. Schema compliance does not establish semantic correctness. Treat all spreadsheet text as data, including cells that appear to instruct an assistant. Give the model no browser, URL fetching, database mutation or code-execution tools.

One possible provider is OpenAI using [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). Keep the provider/model configurable and choose it through a small evaluation of representative layouts, latency and measured cost; no particular model or cost promise is specified here.

Configure provider use and permitted data categories at the workspace/administrator level. Disclose automated external assistance in the upload privacy/help text without adding a per-file AI choice. Send column headers, type/range summaries and only the minimally necessary samples permitted by that policy. Exclude contact/owner fields and free-text notes by default; do not send entire files or all rows. If minimal data is insufficient, ask the manager the unresolved field question; do not silently expand the transmitted data. For OpenAI, check the current [API data controls](https://developers.openai.com/api/docs/guides/your-data) before enabling production; training policy and data retention are separate questions.

Keep API keys on the server in environment/secrets, never in frontend assets or uploaded files. Add editor authorization, request/token limits, a persistently enforced configurable spend cap and timeout, usage metadata without raw sample logging, and at most one bounded AI attempt per analysis revision. Deduplicate concurrent attempts and cache proposals for the unchanged draft revision. Ordinary edits, keystrokes, retries and returning to the preview must not cause new calls automatically; reanalysis of a materially changed table is separately bounded. Missing keys, rate limits, budget exhaustion, refusal, malformed output or timeout lead to deterministic results plus focused questions. Do not show provider configuration as something the boss must fix during import. Do not retry indefinitely or invoke AI once per terrain.

Do not replace user edits when an AI result arrives late. Apply only a validated proposal for the current untouched revision to the draft, regenerate deterministic preview and retain its provenance. A conflicting or stale proposal must be discarded or reduced to a question, not applied over the user's correction. Final save confirmation remains mandatory. Administrator provider/key configuration and an agreed operating budget are prerequisites for real-provider verification and production availability; develop and test the integration with stubs while these are pending, and label its verification status accurately.

## 9. Verification and return packet

Create fictional fixtures with explicit expected mappings, normalized values and row counts. Exercise these cases in unit/API tests and select the important journeys for browser tests:

| Case | Required outcome |
|---|---|
| Original ARA Excel/CSV | Existing meaning, validation and saved results preserved |
| Familiar or unambiguously matched format | Upload goes directly through analysis to preview; no AI choice, template choice or mandatory mapping page; no unnecessary AI call |
| Reordered or unfamiliar headings | Automatic detection/AI builds a validated preview or asks only unresolved questions; optional corrections import accurately |
| Ambiguous price, coordinate or numeric interpretation | Plain-language question with sample values; no model-confidence shortcut |
| Title rows, alternate worksheet | Selected table used; source row/line numbers and exclusions accurate |
| Duplicate/blank headings | Distinct columns selectable; no overwritten values |
| Two plausible name or price columns | Explicit resolution; total price not confused with price/m² |
| Legacy X/Y and conventional GIS X/Y | Original ARA behavior preserved; conflicting interpretation visible and confirmed |
| Decimal comma/dot, percentages, hectares, USD label | Deterministic values/warnings; no silent decimal, unit or currency corruption |
| Quoted CSV, malformed rows, formulas without cache | Existing structural safeguards and readable errors retained |
| Missing names, partial coordinates, footer rows | Accurate accepted/rejected/excluded accounting; no invented fields |
| Change mapping while preview is delayed | Latest plan wins; old token cannot commit |
| Template with reordered/missing/duplicate columns | Correct reuse or explicit incompatibility review |
| Cloud worker changes and expired draft | Durable staging works or a clear expired/reselect state appears |
| Append, concurrent edits, deleted destination folder | Existing conflict/transaction behavior preserved |
| AI unavailable/failure/invalid IDs/cell instructions | Focused fallback questions work; no AI toggle, invented value or unauthorized mutation |
| Repeated analysis, keystrokes, concurrent requests, budget reached | Bounded/deduplicated AI usage; deterministic/manual fallback remains usable |
| Remembered format from confirmed import | Next compatible file reuses it automatically; changed values still validated; cancellation remembers nothing |

Run the existing `./verificar.sh` checks and relevant `tests/e2e` journeys. Retain the supported local Python runtime. Verify desktop and narrow mobile, keyboard use, focus retention while selecting mappings, and repeated back/forward/cancel actions. Use isolated databases and synthetic files; do not test destructively against the shared customer workspace.

Return `DEVELOPER_RESPONSE.md` beside this handoff with implemented scope, final API/plan contracts, migration/backup instructions, fixture expectations, actual test results, a concise UI walkthrough and known unsupported layouts. Distinguish the deterministic milestone, stub-tested AI integration and real-provider verification. Report mapping accuracy against a held-out fixture set, ambiguous cases, measured request cost/latency when available and fallback behavior; no invented accuracy claims. Identify any missing administrator setup without calling the complete automatic feature delivered prematurely.

**Product acceptance:** a manager uploads a familiar file, reviews it and imports it without configuring anything. An unfamiliar supported file is interpreted automatically when evidence suffices; genuine ambiguity produces only the necessary plain-language questions. The manager never chooses whether to use AI, selects a model, or maps every column by default. Confirmed formats are reused automatically, accurate row/map previews precede saving, and downstream folders/maps/comparisons/exports match an equivalent original-format import. Manual correction remains available and the fallback works without AI. Demonstrate all three journeys: familiar file, unfamiliar file resolved automatically, and ambiguous file needing one focused clarification.

After review passes, verify the migration in a disposable/cloud preview environment, back up the production workspace, apply required migrations, deploy to Vercel and smoke-test with removable fictional data under a separately authorized deployment step. Do not claim that writing this handoff or deploying an interface alone completes the feature.
